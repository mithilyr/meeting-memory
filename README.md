# Meeting Memory Agent

Turns meeting transcripts into searchable memory, answers questions with exact-quote citations,
and writes pre-meeting briefs. Built for the Catalist Agentic AI Intern build test.

Status: scaffold. See `CLAUDE.md` for the rules and `docs/decisions.md` for the design.

## Setup ($0, runs locally)

1. Python 3.11+, and [Ollama](https://ollama.com) running.
2. `ollama pull qwen3:8b` and `ollama pull nomic-embed-text`
3. `python -m venv .venv` then `.venv\Scripts\activate` (Windows)
4. `pip install -r requirements.txt`
5. `copy .env.example .env` (the defaults expect the data folder next to this repo)

## Run

```
python -m src.ingest.parse --check
python -m pytest -q
```
