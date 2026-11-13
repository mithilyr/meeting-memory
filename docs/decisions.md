# Decisions

One entry per design decision: what, why, what was rejected. Newest at the bottom.
This file feeds the write-up and the video.

## D-001: Event ledger + retrieval, not a knowledge graph (2026-11-13)
**Decision:** Store raw turns as the source of truth. Extract typed events (decision, proposal,
action item, number, objection, role intro) per meeting, each pointing at the turn ids it came from.
Code works out which event is current.
**Why:** 15 of the 25 questions ask what changed over time. A ledger ordered by meeting makes
"first X, then Y" a lookup, not a model guess.
**Rejected:** The CodeFest infobox graph. Transcripts have no structured rows to build it from.
Plain RAG alone: it finds passages but cannot tell which decision is current.

## D-002: $0 budget, so local models via Ollama (2026-11-13)
**Decision:** `qwen3:8b` on the local RTX 3060 (6GB) for extraction and answering. Local embedding
model through Ollama. OpenRouter free tier is optional only.
**Why:** The user's constraint is zero spend. Local inference has no daily cap, so a full
re-ingest never stops halfway on a quota. Responses are cached, so it runs once.
**Rejected:** Paid Haiku/Sonnet (costs money). Gemini or OpenRouter free tiers as the main path
(daily request caps, about 20 to 50 a day, too few for about 300 extraction calls).
**Trade-off to report:** An 8B model extracts worse than a frontier model. Measure it on our own eval set.

## D-003: Parsing and quote verification are code, never a model (2026-11-13)
**Decision:** A regex parser (`src/ingest/parse.py`) and an exact-match verifier (`src/ingest/verify.py`).
**Why:** The file format is fixed: all 138 files checked, one text line per turn. Citations are
graded word for word, and a model in this path can only alter the words.
**Detail:** The verifier lowercases and collapses spaces only. It keeps punctuation, which is
stricter than CodeFest's `normalise()`. Matches the grader's stated rule.

## D-004: Brief for TS3012 uses meetings a to c only (2026-11-13)
**Decision:** The brief pipeline filters by a meeting cutoff in code.
**Why:** The brief is "before their final meeting". TS3012d exists in the data, but using it leaks the future.

## D-005: Reuse from CodeFest ashen-assistant (2026-11-13)
**Copied:** `clients/retry.py` (unchanged), `settings.py` pattern.
**Will adapt:** the OpenRouter client (optional free tier), the embedding cache pattern, and the
eval harness report format.
**Not reused:** graph/*, OCR, dedup, authority tiers, UI. They do not fit transcripts.

## D-006: SQLite (FTS5) + numpy, no vector DB, no framework (2026-11-13)
**Why:** Both are free and local. FTS5 is built into Python's sqlite3 (checked: 3.53.1).
About 48k turns fit in memory easily. Swapping to Postgres + pgvector at 10k meetings is a
storage change, not a redesign. A framework adds code nobody can explain on demand.
