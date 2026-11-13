"""One entry point for "ask a model": free API first, local model as the safety net.

Tier C (D-007, D-008): OpenRouter free models rotate on failure; if all are
rate-limited or the network is down, the local qwen3:4b answers instead. A demo
must not die on a 429. Every response is cached by prompt hash (the OpenRouter
client's cache, shared here for the local model), so a repeated question is free and instant.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from src.clients import ollama
from src.clients.openrouter import AllModelsExhausted, OpenRouterPool, read_cached, write_cached

LOCAL_MODEL = "qwen3:4b"


@dataclass
class Usage:
    calls: list[dict] = field(default_factory=list)

    def record(self, model: str, seconds: float, cached: bool) -> None:
        self.calls.append({"model": model, "seconds": round(seconds, 2), "cached": cached})


USAGE = Usage()
_pool: OpenRouterPool | None = None


def complete(prompt: str, *, local_only: bool = False) -> tuple[str, str]:
    """Return (text, model). Cached responses come back without a network call."""
    global _pool
    started = time.time()
    cached = read_cached(prompt)
    if cached:
        USAGE.record(cached[1], time.time() - started, True)
        return cached
    if not local_only:
        try:
            _pool = _pool or OpenRouterPool()
            text, model = _pool.generate([prompt], description="answer", use_cache=True, attempts=2)
            USAGE.record(model, time.time() - started, False)
            return text, model
        except (AllModelsExhausted, RuntimeError):
            pass
    text = ollama.generate(prompt, model=LOCAL_MODEL)
    write_cached(prompt, text, f"ollama/{LOCAL_MODEL}")
    USAGE.record(f"ollama/{LOCAL_MODEL}", time.time() - started, False)
    return text, f"ollama/{LOCAL_MODEL}"


def parse_json(text: str) -> dict:
    """Models wrap JSON in prose or code fences. Take the outermost object."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])
