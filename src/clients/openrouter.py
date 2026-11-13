"""OpenRouter free tier: model rotation and a disk response cache.

Copied from the CodeFest ashen-assistant (D-005) with its two live-found bugs
fixed there (HTTP 200 carrying an error body; unreachable network). Changes here:
the model list, re-verified against the live /models endpoint on 2026-11-13, and
the docstring. Gemini's key from CodeFest returned 401, so this is the only free
API provider; `src/clients/llm.py` falls back to a local model after it.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from src.clients.retry import DailyQuotaExhausted, RetriesExhausted, with_retry
from src.settings import get_settings

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"

#: Verified live 2026-09-01. Re-verified 2026-09-09 with `--verify`: OpenRouter
#: had delisted `z-ai/glm-5.2:free` and `minimax/minimax-m3:free` (both gone
#: from the live models endpoint entirely, not merely dropped from free tier).
#: Replaced with `nex-agi/nex-n2.5-pro:free` and `thinkingmachines/inkling:free`,
#: the two live free models `--verify` reported that were not already in
#: either rotation. Order is preference, not capability ranking.
PHRASING_MODELS: tuple[str, ...] = (
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "baidu/ernie-5.5-flash-preview:free",
    "google/gemma-4-31b-it:free",
)

#: Verified live 2026-09-01 as advertising `structured_outputs`. Re-verified
#: 2026-09-09: `z-ai/glm-5.2:free` delisted (see PHRASING_MODELS); replaced
#: with `nex-agi/nex-n2.5-mini:free`, confirmed structured-output-capable in
#: the same `--verify` run. A planner whose output is not schema-checkable is
#: a planner whose output we would have to trust, and this project does not
#: trust model output it cannot check.
PLANNER_MODELS: tuple[str, ...] = (
    "nex-agi/nex-n2.5-mini:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "dots-studio/dots-3-note-preview:free",
    "liquid/lfm-2.5-2.6b:free",
)

REQUEST_TIMEOUT_S = 60

#: Do not burn five retries on one model when others with separate quota are
#: waiting. The last one gets the full backoff because nothing follows it.
ATTEMPTS_WHILE_ALTERNATIVES_REMAIN = 2
ATTEMPTS_ON_LAST_MODEL = 5


class AllModelsExhausted(RuntimeError):
    """Every model in the rotation failed."""


class StructuredOutputInvalid(RuntimeError):
    """A model returned something that is not the JSON object we asked for."""


@dataclass
class OpenRouterUsage:
    """Per-model call counts, so quota spend stays visible.

    Same shape as `gemini.GeminiUsage` so a caller can treat either provider's
    usage identically - and so the harness can report how often each escalation
    actually fired, which CLAUDE.md requires of every LLM fallback.
    """

    calls: dict[str, int] = field(default_factory=dict)
    exhausted: set[str] = field(default_factory=set)
    cache_hits: int = 0

    def record(self, model: str) -> None:
        self.calls[model] = self.calls.get(model, 0) + 1

    @property
    def total_calls(self) -> int:
        return sum(self.calls.values())

    def summary(self) -> str:
        used = ", ".join(f"{m}={n}" for m, n in self.calls.items()) or "none"
        spent = ", ".join(sorted(self.exhausted)) or "none"
        return f"calls: {used} | cache hits: {self.cache_hits} | exhausted: {spent}"


# -- response cache --------------------------------------------------------
# Separate directory from gemini.py's: two providers can phrase the same prompt
# differently, and a shared key would let one serve the other's answer.


def cache_dir() -> Path:
    return get_settings().cache_dir / "responses_openrouter"


def _cache_key(prompt: str, schema_name: str | None) -> str:
    #: The schema is part of the key. The same prompt asked for prose and asked
    #: for a plan are different requests, and caching them together would serve
    #: a sentence where a plan was wanted.
    material = f"{schema_name or 'text'}\x00{prompt}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _cache_path(key: str) -> Path:
    return cache_dir() / key[:2] / f"{key}.json"


def read_cached(prompt: str, schema_name: str | None = None) -> tuple[str, str] | None:
    path = _cache_path(_cache_key(prompt, schema_name))
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        return record["text"], record["model"]
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def write_cached(
    prompt: str, text: str, model: str, schema_name: str | None = None
) -> None:
    path = _cache_path(_cache_key(prompt, schema_name))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "text": text,
                "model": model,
                "schema": schema_name,
                "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        ),
        encoding="utf-8",
    )


def _call_model(
    model: str,
    prompt: str,
    api_key: str,
    *,
    schema: dict | None = None,
    timeout: int = REQUEST_TIMEOUT_S,
) -> str:
    """One request to OpenRouter's OpenAI-compatible chat endpoint.

    Split out so tests can replace this one function and exercise rotation,
    caching and error handling without a network call.
    """
    body: dict = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema["name"], "strict": True, "schema": schema["schema"]},
        }

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        # The status line alone ("429 Too Many Requests") hides whether the limit is per
        # minute or per day. The body says ("free-models-per-day"), and retry.py needs it
        # to stop retrying a quota that only resets tomorrow.
        if error.code == 429:
            raise RuntimeError(f"HTTP 429 from OpenRouter: {error.read()[:300]!r}") from error
        raise

    # LIVE BUG 1, found by the sister team by actually running the thing.
    # OpenRouter can return HTTP 200 with an *error body* rather than a
    # completion - a retired or misspelled model id does this. Indexing
    # straight into "choices" then raises a bare KeyError, which is not one of
    # the exceptions `generate` treats as "try the next model", so it crashed
    # a live request instead of degrading. Raise something informative and
    # rotation-shaped instead.
    if "choices" not in payload:
        raise RuntimeError(
            f"OpenRouter returned no choices for {model}: {payload.get('error', payload)}"
        )

    return (payload["choices"][0]["message"]["content"] or "").strip()


class OpenRouterPool:
    """Calls OpenRouter, rotating to the next model on failure.

    Public shape matches `gemini.GeminiPool` (`generate(...) -> (text, model)`)
    so a caller can treat either provider as an interchangeable backend.
    """

    def __init__(self, models: tuple[str, ...] = PHRASING_MODELS) -> None:
        settings = get_settings()
        if not settings.openrouter_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Get a free key at "
                "https://openrouter.ai/keys and add it to .env"
            )
        self._api_key = settings.openrouter_api_key
        self._models = models
        self.usage = OpenRouterUsage()

    @property
    def available(self) -> list[str]:
        return [m for m in self._models if m not in self.usage.exhausted]

    def generate(
        self,
        contents: list[str],
        *,
        description: str = "OpenRouter call",
        use_cache: bool = True,
        schema: dict | None = None,
        timeout: int = REQUEST_TIMEOUT_S,
        attempts: int | None = None,
    ) -> tuple[str, str]:
        """Send a request, trying each available model in turn.

        Args:
            schema: A `{"name": str, "schema": {...}}` JSON-Schema wrapper. When
                given, the request asks for structured output and the response
                is parsed and validated before being returned.

        Returns:
            (text, model_used).

        Raises:
            AllModelsExhausted: every model in the rotation failed.
            StructuredOutputInvalid: a schema was requested and no model
                returned valid JSON for it.
        """
        prompt = "\n".join(contents)
        schema_name = schema["name"] if schema else None

        if use_cache:
            cached = read_cached(prompt, schema_name)
            if cached is not None:
                self.usage.cache_hits += 1
                return cached

        last_error: Exception | None = None
        candidates = self.available
        for position, model in enumerate(candidates):
            is_last = position == len(candidates) - 1

            def call(model: str = model) -> str:
                return _call_model(
                    model, prompt, self._api_key, schema=schema, timeout=timeout
                )

            try:
                text = with_retry(
                    call,
                    description=f"{description} [{model}]",
                    attempts=attempts
                    or (
                        ATTEMPTS_ON_LAST_MODEL
                        if is_last
                        else ATTEMPTS_WHILE_ALTERNATIVES_REMAIN
                    ),
                )
                if schema is not None:
                    # Validate before caching. A model that ignored the schema
                    # has failed this call, and the next model may honour it -
                    # so this is a rotation condition, not a raised error.
                    try:
                        json.loads(text)
                    except json.JSONDecodeError as error:
                        last_error = StructuredOutputInvalid(
                            f"{model} returned non-JSON for schema {schema_name!r}"
                        )
                        last_error.__cause__ = error
                        continue
                self.usage.record(model)
                if use_cache:
                    write_cached(prompt, text, model, schema_name)
                return text, model

            except RetriesExhausted as error:
                last_error = error  # transient on this model; try the next
                continue
            except DailyQuotaExhausted as error:
                self.usage.exhausted.add(model)
                last_error = error
                continue
            except urllib.error.HTTPError as error:
                if error.code in (401, 402, 403, 404):
                    # Bad key, no credit, or a retired model - not transient.
                    self.usage.exhausted.add(model)
                    last_error = error
                    continue
                raise
            except OSError as error:
                # LIVE BUG 2, also found by running it for real: a host with no
                # outbound route raises URLError("Network is unreachable"),
                # which `with_retry` does not classify as retryable (no "429",
                # "5xx" or "timeout" in the text) and re-raises unchanged. Left
                # uncaught it crashes the request instead of rotating or
                # reporting AllModelsExhausted.
                last_error = error
                continue
            except Exception as error:  # noqa: BLE001
                # Same reasoning as retry.py's own broad catch: better to
                # over-match than to crash a demo. A malformed response from
                # one model must not take down a request four other models
                # could still serve.
                last_error = error
                continue

        raise AllModelsExhausted(
            f"{description}: all {len(self._models)} OpenRouter models failed. "
            f"{self.usage.summary()}. Last error: {last_error}"
        )

    def generate_structured(
        self,
        contents: list[str],
        schema: dict,
        *,
        description: str = "structured call",
        timeout: int = REQUEST_TIMEOUT_S,
        attempts: int | None = None,
    ) -> tuple[dict, str]:
        """`generate` with a schema, returning the parsed object.

        Raises:
            StructuredOutputInvalid: if the text that came back is not a JSON
                object (a JSON array or scalar is not a plan).
        """
        text, model = self.generate(
            contents,
            description=description,
            schema=schema,
            timeout=timeout,
            attempts=attempts,
        )
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise StructuredOutputInvalid(f"{model} returned non-JSON: {text[:200]}") from error
        if not isinstance(value, dict):
            raise StructuredOutputInvalid(
                f"{model} returned {type(value).__name__}, expected an object"
            )
        return value, model


def verify_models(timeout: int = 30) -> dict:
    """Check the configured rotations against the live models endpoint.

    Needs no API key - the models list is public. This is the check that must
    be run before trusting either tuple above, and the reason neither was
    inherited from the sister repo unexamined.
    """
    with urllib.request.urlopen(MODELS_URL, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    models = payload["data"]
    by_id = {m["id"]: m for m in models}
    free = sorted(m["id"] for m in models if m["id"].endswith(":free"))
    structured = sorted(
        m["id"]
        for m in models
        if m["id"].endswith(":free")
        and "structured_outputs" in (m.get("supported_parameters") or [])
    )
    return {
        "total": len(models),
        "free": free,
        "structured_free": structured,
        "phrasing_missing": [m for m in PHRASING_MODELS if m not in by_id],
        "planner_missing": [m for m in PLANNER_MODELS if m not in by_id],
        "planner_without_structured": [
            m for m in PLANNER_MODELS if m in by_id and m not in structured
        ],
    }


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify", action="store_true", help="check rotations against the live endpoint"
    )
    args = parser.parse_args(argv)

    if not args.verify:
        parser.print_help()
        return

    report = verify_models()
    print(f"OpenRouter: {report['total']} models, {len(report['free'])} free-tier")
    print(f"free models advertising structured_outputs: {len(report['structured_free'])}")
    for label in ("phrasing_missing", "planner_missing", "planner_without_structured"):
        problems = report[label]
        print(f"  {label:28} {problems if problems else 'none'}")
    if any(report[k] for k in ("phrasing_missing", "planner_missing", "planner_without_structured")):
        raise SystemExit("model rotation is stale - update src/clients/openrouter.py")
    print("\nrotations verified against the live endpoint.")


if __name__ == "__main__":
    main()
