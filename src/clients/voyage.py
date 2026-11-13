"""Hosted embeddings from Voyage AI (D-022). Replaces the local Ollama embedder (D-021).

Plain urllib: one endpoint does not justify an SDK. voyage-4-lite gives 1024-dim
vectors; Voyage embeds documents and queries asymmetrically, so callers say which.
Up to 128 inputs per request keeps the full corpus to about 125 requests.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from src.clients.retry import with_retry
from src.settings import get_settings

API_URL = "https://api.voyageai.com/v1/embeddings"
BATCH_SIZE = 128


def _post(texts: list[str], input_type: str) -> list[list[float]]:
    settings = get_settings()
    if not settings.voyage_api_key:
        raise RuntimeError("VOYAGE_API_KEY is not set. Get a free key at https://dashboard.voyageai.com")
    body = {"input": texts, "model": settings.embed_model, "input_type": input_type, "truncation": True}
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings.voyage_api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:  # keep the body: it says which limit was hit
        raise RuntimeError(f"HTTP {error.code} from Voyage: {error.read()[:300]!r}") from error
    return [item["embedding"] for item in sorted(payload["data"], key=lambda d: d["index"])]


def embed(texts: list[str], *, input_type: str = "document") -> list[list[float]]:
    """Embed texts in batches. input_type: "document" when indexing, "query" when searching."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        part = texts[start : start + BATCH_SIZE]
        vectors.extend(with_retry(lambda part=part: _post(part, input_type), description="voyage embed"))
    return vectors
