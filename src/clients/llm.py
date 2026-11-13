"""One entry point for "ask a model". Hosted APIs only (D-021: no local model).

Free OpenRouter models are tried one by one. Non-empty replies are cached by prompt
hash, so a repeated question is free and instant; empty ones are never cached. If
every model fails, NoModelAvailable says why, and the caller reports it instead of
crashing.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from src.clients.openrouter import PHRASING_MODELS, AllModelsExhausted, OpenRouterPool, read_cached, write_cached



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


class NoModelAvailable(RuntimeError):
    """Every hosted model failed or the daily quota is spent."""


def complete(prompt: str) -> tuple[str, str]:
    """Return (text, model). Cached responses come back without a network call."""
    started = time.time()
    cached = read_cached(prompt)
    if cached and cached[0].strip():
        USAGE.record(cached[1], time.time() - started, True)
        return cached
    global _api_paused_until
    if time.time() >= _api_paused_until:
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
    raise NoModelAvailable(
        "No hosted model answered. The free OpenRouter quota (50 requests a day) may be used up; "
        "it resets at 00:00 UTC. Add another provider key or wait."
    )


def parse_json(text: str) -> dict:
    """Models wrap JSON in prose or code fences. Take the outermost object."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])
