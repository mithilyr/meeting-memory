"""Groq: second free provider, tried after OpenRouter (D-023).

Groq's API is OpenAI-compatible, so this is one POST. Its free allowance is separate
from OpenRouter's, so when OpenRouter's 50-a-day limit is spent the agent keeps going.
Model ids come from GROQ_MODELS (comma-separated) and are checked against the live
/models list with `python -m src.clients.groq`.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from src.clients.retry import with_retry

API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODELS_URL = "https://api.groq.com/openai/v1/models"
DEFAULT_MODELS = "openai/gpt-oss-120b,llama-3.3-70b-versatile"


def models() -> list[str]:
    return [m.strip() for m in os.getenv("GROQ_MODELS", DEFAULT_MODELS).split(",") if m.strip()]


def _key() -> str:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set (free key: https://console.groq.com/keys)")
    return key


def _call(model: str, prompt: str) -> str:
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0}
    request = urllib.request.Request(
        API_URL, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:  # keep the body: it names the limit that was hit
        raise RuntimeError(f"HTTP {error.code} from Groq ({model}): {error.read()[:300]!r}") from error
    return (payload["choices"][0]["message"]["content"] or "").strip()


def generate(prompt: str) -> tuple[str, str]:
    """Try each configured model once (with retry on transient errors). Returns (text, model)."""
    last: Exception | None = None
    for model in models():
        try:
            text = with_retry(lambda model=model: _call(model, prompt), description=f"groq {model}", attempts=2)
            if text:
                return text, f"groq/{model}"
        except Exception as error:  # noqa: BLE001 - try the next model
            last = error
    raise RuntimeError(f"all Groq models failed: {last}")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    request = urllib.request.Request(MODELS_URL, headers={"Authorization": f"Bearer {_key()}"})
    live = {m["id"] for m in json.load(urllib.request.urlopen(request, timeout=30))["data"]}
    for m in models():
        print(("OK      " if m in live else "MISSING ") + m)
    sys.exit(0)
