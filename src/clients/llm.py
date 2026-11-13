"""One entry point for "ask a model": free API first, local model as the safety net.

Tier C (D-007, D-008): OpenRouter free models are tried one by one; if all fail,
are rate-limited, or return nothing, the local qwen3:4b answers instead. A demo
must not die on a 429. Non-empty responses are cached by prompt hash, so a
repeated question is free and instant. Empty ones are never cached: a free model
that returned nothing once (seen on a 14K-token prompt) must get another chance.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from src.clients import ollama
from src.clients.openrouter import PHRASING_MODELS, AllModelsExhausted, OpenRouterPool, read_cached, write_cached

LOCAL_MODEL = "qwen3:4b"


@dataclass
class Usage:
    calls: list[dict] = field(default_factory=list)

    def record(self, model: str, seconds: float, cached: bool) -> None:
        self.calls.append({"model": model, "seconds": round(seconds, 2), "cached": cached})


USAGE = Usage()
_pools: dict[str, OpenRouterPool] = {}
#: OpenRouter's free allowance is per account, not per model: once one model reports the daily
#: limit, the others will too. Skip the API until this time instead of trying each model.
_api_paused_until = 0.0


def complete(prompt: str, *, local_only: bool = False) -> tuple[str, str]:
    """Return (text, model). Cached responses come back without a network call."""
    started = time.time()
    cached = read_cached(prompt)
    if cached and cached[0].strip() and not local_only:
        USAGE.record(cached[1], time.time() - started, True)
        return cached
    global _api_paused_until
    if not local_only and time.time() >= _api_paused_until:
        for model in PHRASING_MODELS:
            try:
                pool = _pools.setdefault(model, OpenRouterPool(models=(model,)))
                if not pool.available:
                    continue  # this model's daily quota is gone
                text, used = pool.generate([prompt], description="answer", use_cache=False, attempts=2)
            except (AllModelsExhausted, RuntimeError):
                if pool.usage.exhausted:
                    _api_paused_until = time.time() + 3600
                    break
                continue
            if text.strip():
                write_cached(prompt, text, used)
                USAGE.record(used, time.time() - started, False)
                return text, used
    # Local replies get their own cache key, so a later run with API quota back still asks the
    # stronger model instead of being served the fallback's answer.
    local = read_cached(prompt, LOCAL_MODEL)
    if local and local[0].strip():
        USAGE.record(local[1], time.time() - started, True)
        return local
    text = ollama.generate(prompt, model=LOCAL_MODEL)
    if text.strip():
        write_cached(prompt, text, f"ollama/{LOCAL_MODEL}", LOCAL_MODEL)
    USAGE.record(f"ollama/{LOCAL_MODEL}", time.time() - started, False)
    return text, f"ollama/{LOCAL_MODEL}"


def parse_json(text: str) -> dict:
    """Models wrap JSON in prose or code fences. Take the outermost object."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])
