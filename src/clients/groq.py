"""Groq: second free provider, tried after OpenRouter (D-023).

Groq's API is OpenAI-compatible, so this is one POST. Its free allowance is separate
from OpenRouter's, so when OpenRouter's 50-a-day limit is spent the agent keeps going.
Model ids come from GROQ_MODELS (comma-separated) and are checked against the live
/models list with `python -m src.clients.groq`.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from src.clients.retry import with_retry

API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODELS_URL = "https://api.groq.com/openai/v1/models"
DEFAULT_MODELS = "openai/gpt-oss-120b,qwen/qwen3.8-27b"  # checked live 2026-11-13
#: Groq sits behind Cloudflare, which rejects Python's default "Python-urllib" agent (error 1010).
USER_AGENT = "meeting-memory/1.0"


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
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json",
                 "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:  # keep the body: it names the limit that was hit
        raise RuntimeError(f"HTTP {error.code} from Groq ({model}): {error.read()[:300]!r}") from error
    return (payload["choices"][0]["message"]["content"] or "").strip()


def _call_paced(model: str, prompt: str, attempts: int = 4) -> str:
    """Groq's free tier allows 8K tokens per minute, so a 5K-token prompt right after another
    gets a 429 with "try again in 1m2.5s". Wait exactly that long (plus a second) and retry."""
    for attempt in range(attempts):
        try:
            return _call(model, prompt)
        except RuntimeError as error:
            wait = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(error))
            if "HTTP 429" not in str(error) or not wait or attempt == attempts - 1:
                raise
            if "per day" in str(error):  # daily cap: waiting won't help soon, use the next model
                raise
            time.sleep(int(wait.group(1) or 0) * 60 + float(wait.group(2)) + 1)
    raise RuntimeError("unreachable")


def generate(prompt: str) -> tuple[str, str]:
    """Try each configured model once (with retry on transient errors). Returns (text, model)."""
    last: Exception | None = None
    for model in models():
        try:
            text = with_retry(lambda model=model: _call_paced(model, prompt), description=f"groq {model}", attempts=2)
            if text:
                return text, f"groq/{model}"
        except Exception as error:  # noqa: BLE001 - try the next model
            last = error
    raise RuntimeError(f"all Groq models failed: {last}")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    request = urllib.request.Request(MODELS_URL, headers={"Authorization": f"Bearer {_key()}", "User-Agent": USER_AGENT})
    live = {m["id"] for m in json.load(urllib.request.urlopen(request, timeout=30))["data"]}
    for m in models():
        print(("OK      " if m in live else "MISSING ") + m)
    sys.exit(0)
