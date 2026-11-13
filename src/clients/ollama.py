"""Local models through Ollama: embeddings, and a fallback answer model.

Plain urllib, no SDK: two endpoints do not justify a dependency.
"""

from __future__ import annotations

import json
import urllib.request

from src.clients.retry import with_retry
from src.settings import get_settings


def _post(path: str, body: dict, timeout: int = 600) -> dict:
    request = urllib.request.Request(
        get_settings().ollama_url + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def embed(texts: list[str], *, model: str | None = None) -> list[list[float]]:
    """Embed texts in one request. nomic-embed-text wants a task prefix on each side."""
    model = model or get_settings().embed_model
    payload = {"model": model, "input": texts, "truncate": True}
    result = with_retry(lambda: _post("/api/embed", payload), description="ollama embed")
    return result["embeddings"]


def generate(prompt: str, *, schema: dict | None = None, model: str = "qwen3:4b") -> str:
    """One completion. Thinking off: answers are short and the evidence is already chosen."""
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_ctx": 16384},
    }
    if schema is not None:
        body["format"] = schema
    result = with_retry(lambda: _post("/api/generate", body), description=f"ollama {model}")
    return result["response"].strip()
