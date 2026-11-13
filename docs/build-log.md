# Build log

Append one entry per session: what changed, what was measured. For the video and write-up.

## 2026-11-13: Session 1, analysis + scaffold
- Read the brief PDF, questions.json (25 questions, brief task = TS3012), and sample transcripts.
- Format check: 138 meetings, 35 teams, every turn = header line + one text line.
- Found traps: exact-quote grading, TS3012d leakage, 15/25 questions about changed decisions.
- Audited the CodeFest ashen-assistant for reuse (see D-005).
- Set the $0 budget: local Ollama qwen3:8b on an RTX 3060 6GB (D-002).
- Scaffolded the repo: CLAUDE.md (must/don't rules), parser, quote verifier, tests, decision log.
- Benchmarked local models (D-007): qwen3:8b 120 s/chunk (spills to CPU), qwen3:4b 28 s/chunk but invents turn ids.
- Decision: build-time extraction via Claude Code, production proposal Haiku 5.5 Batch (~$0.75 per 1,000 meetings).
- Wrote docs/architecture.md: three-tier cost table, Mermaid system diagram, plain-English walk-through of every box (D-008).
- Wrote docs/idea.md (the pitch). Added D-009: in-order extraction with prior ledger context, commitment tracking.

## 2026-11-13: Session 2, build
- Store: 138 meetings → 48,148 turns, 15,868 chunks in 1.6 s; re-run skips all 138. Embedding all chunks locally (nomic-embed-text) took ~10 min.
- Extraction pipeline: job files, code validator with quote snapping, ledger status rules (4 unit tests).
- Launched 7 Haiku subagents for 35 teams (D-010).
- Answer agent + brief writer + run.py. First smoke test: 9 s, 3 verified citations across 2 meetings.
- Own eval set: 10 questions on 7 unseen teams; all 25 gold quotes pass the verifier.
- Web UI on http.server styled after catalist.media.
