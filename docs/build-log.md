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

## 2026-11-13: Session 3, hosted-only and finishing
- Extraction finished: 138/138 meetings, 7,199 events, 40 dropped by the validator (0.6%). Snapshot committed.
- Rebuild check: a fresh store built from snapshot/ in 26 s holds the same 7,199 events.
- First full run: 24/25 answered on OpenRouter; Q18 failed on an empty reply to a 55K-character prompt (F-001).
- OpenRouter's 50-a-day free limit was hit. Local qwen3:4b eval: auto 8/10, hand-checked 5/10.
- Local models removed (D-021). Embeddings moved to Voyage AI (D-022), 15,868 chunks re-embedded.
- Groq added (D-023). Groq rejects Python's default user agent (Cloudflare 1010) and caps a free request at 8K tokens,
  so prompts were cut to about 16 to 22K characters (ledger 11K, turns 8K).

## 2026-11-14: Session 4, usability and prompt-injection defences
- Ask page streams the agent's real steps (D-026). Run details folded under "How this answer was made".
- Project names generated per team (D-025), then a searchable picker on all three tabs (D-028).
- Whole transcript and the original .txt are one click from any quote; the download matches the file byte for byte.
- Screenshot review with headless Edge at 1366 px and 390 px: no sideways scroll on a phone.
- Prompt-injection defences (D-027): screening, fenced prompts, review queue, 2 MB cap. 0 of 138 real meetings flagged.
- Tests: 9 pass (3 new for screening).

## 2026-11-14: Session 5, saying no instead of guessing
- Truth audit over all 7,199 events (D-032): spoken-number reader, figure/unit/speaker/link checks,
  run on every import. 15 figures never said, 1 wrong currency, 7 backwards links; flags reach every prompt.
- Answer statuses and grounding checks (D-033): withheld answers, challenged "no"s, coverage of missing
  meetings, two-project questions, duplicate uploads refused.
- Ledger ranked by meaning when over budget (D-034, fix for F-008). 7,199 events embedded in 2.5 minutes.
- New eval: `eval/abstain_questions.json`, 7/7 declined or corrected. Tests: 14 pass.
- Re-ran the 25 graded questions with the checks: every citation valid, 25/25 cite 2+ meetings (was 23/25),
  all 25 status "answered", typographic spaces gone from the text. Q10 kept from the earlier agent run
  (the new answer cited one meeting). The brief was re-run after raising Groq's output cap (its JSON was
  cut off) and now names speakers by letter, as the output contract asks; 2 points were replaced by
  their events' own summaries by the grounding check.
- Tests: 15 pass, including one that a new meeting's import runs the audit.

