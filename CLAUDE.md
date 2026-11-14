# CLAUDE.md: Meeting Memory Agent (Catalist build test)

Source of truth for requirements: `../Catalist_Agentic_AI_Intern_Build_Test.pdf` and
`../Catalist_AI_Intern_Build_Test_Data/questions.json`. If this file and those disagree,
those win. Fix this file.

## What we are building

An agent that turns 138 AMI meeting transcripts into searchable memory, answers 25
questions with exact-quote citations, and writes a pre-meeting brief for Team TS3012.
It must be designed as if there were 10,000 meetings and new ones arrived every day.

## MUST DO

### Output contract (graded automatically)
1. `out/answers.json` has this exact shape:
   `{"answers": [{"question_id", "answer", "citations": [{"meeting_id", "quote"}]}], "brief": "plain text"}`
2. Every answer is a sentence or two (1 or 2 plain sentences), with 1 to 3 citations. The PDF says "each in a sentence or two".
3. Every quote is at least 6 words, copied exactly from ONE speaker turn of the cited meeting.
   The grader ignores case and spacing only. Punctuation, "um", "uh" and word order must match.
4. Every quote passes `src/ingest/verify.py` before it is written. A quote that fails is
   repaired by snapping to a real span or dropped. Never ship an unverified quote.
5. Speakers are named by letter (Speaker A to D), with the role added when the transcripts make it clear.
6. Every answer uses evidence from at least 2 meetings of the named team. Every question requires it.
7. The TS3012 brief covers: decisions made, what changed along the way, open actions and their
   owners, and disagreements still open. Every point has a citation.
8. The brief uses ONLY TS3012 meetings a, b and c. Meeting d is the "final meeting" the brief
   is for. Reading d leaks the future. Enforce this with a cutoff filter in code, not a prompt.

### Architecture
9. Transcripts are a store we retrieve against. Nothing pastes a whole corpus or a whole team into one prompt.
10. Ingestion is incremental and idempotent: keyed by a content hash, so re-running skips
    meetings that have not changed. A new file is processed without reprocessing old ones.
11. Every derived fact (event, role, decision) stores the `meeting_id` and `turn_id`s it came from.
12. "What is current" (supersession) is decided by code from meeting order, not by the model.
13. The agent loops: retrieve, read, check timeline, answer, verify. It is not a single call.
13a. Saying no beats making things up (D-033). Every answer has a status (answered, partial,
    not_discussed, conflicting, premise_wrong; code adds not_found, unconfirmed). An answer stating a
    figure found nowhere in its evidence is withheld. A "not discussed" reply is challenged once.
13b. The truth audit (`src/memory/audit.py`) runs on every import, for the corpus and new meetings alike.
    Flagged ledger lines reach every prompt marked UNVERIFIED (D-032).

### Cost: $0 build, low-cost production proposal (D-007)
14. Build-time extraction runs through Claude Code (subscription, no API spend), using the SAME
    prompt and JSON schema the production extractor sends to the API. Outputs land in the same
    cache and are validated by code (schema, turn ids, quotes). One flag switches to the API backend.
15. The answering agent is code that calls hosted models only (OpenRouter free, then Groq free), with
    1 to 3 model calls per question. Embeddings come from Voyage AI. No local models (D-021).
16. Production proposal: Claude Haiku 5.5 via the Batch API for extraction. Pick the answering model by eval score.
17. Every LLM response is cached on disk by a prompt hash. Re-runs must cost nothing.
18. Record token counts and wall time per stage, for the "cost of 1,000 meetings" estimate.

### Deliverables the PDF asks for (track progress here)
- [x] Code + README with run instructions
- [x] `out/answers.json` produced by the agent, not by hand
- [x] 10+ own questions with hand-checked answers in `eval/own_questions.json`, scored by the agent
- [x] 3 questions the agent got wrong, with reasons (`docs/failures.md`)
- [x] Cost and time to ingest 1,000 meetings
- [x] One-page write-up: architecture, model-vs-code line, tools, where they broke, production needs
- [x] 3 to 5 minute walkthrough video (docs/video/walkthrough.mp4, 4 min 20 s; upload pending)

### Record keeping (for the video and write-up)
19. Every design decision gets an entry in `docs/decisions.md` (D-NNN: decision, why, alternatives rejected).
20. Every work session appends to `docs/build-log.md`: date, what changed, what was measured.
21. Every wrong answer found gets an entry in `docs/failures.md`: question, what we said, why it failed.
22. Commit after each working step, with a message saying what now works.

## DO NOT

1. Do not reverse-engineer or look up the held-back answers. Do not hand-write answers to the
   25 questions, and do not tune prompts against specific Q01 to Q25 wording.
2. Do not use TS3012 meeting d anywhere in the brief pipeline.
3. Do not paraphrase inside a `quote` field. Do not stitch a quote across two speaker turns.
4. Do not fold punctuation when verifying quotes. The CodeFest `scoring.normalise()` does this,
   so do not reuse it for citations. It would pass quotes the grader fails.
5. Do not call paid APIs or add a payment method. Ask the user first.
6. Do not let the model decide: file parsing, team or meeting filtering, meeting order,
   supersession, quote verification, the JSON shape, or scoring of our own eval set.
7. Do not add frameworks (LangChain, LlamaIndex, vector DBs) without a decision entry that
   justifies them. Stdlib + numpy + sqlite3 is the default.
8. Do not edit the data folder. It is read-only input.
9. Do not commit `.env`, API keys or `.cache/`.
10. Claude Code (the coding assistant) must not write `answers.json`, the brief, or any answer text.
    It may only fill extraction jobs that the pipeline generated (rule 14). The agent writes the answers.
11. Do not put meeting text into a prompt without `screen.fence()` and the <transcript> markers (D-027).
12. Do not add a path that shows model text to a user without `grounding` checks, or that stores
    extracted events without `audit.check_team` (the same standard for old and new meetings).

## Model vs code line (summary, details in docs/decisions.md)

| Code | Model |
|---|---|
| Parsing, turn ids, team/meeting metadata | Extracting events from messy speech |
| BM25 (SQLite FTS5) + vector search | Normalising topic labels |
| Cutoff filters, meeting order, supersession | Resolving vague back-references |
| Quote verification, JSON assembly | Planning searches, writing answers and the brief |
| Cost/token accounting, eval scoring | (optional) judging free-text correctness, spot-checked by hand |

## Layout

```
src/settings.py        paths, env, model names
src/clients/           retry.py (from CodeFest), llm.py (cache + provider order), openrouter.py, groq.py, voyage.py
src/ingest/parse.py    transcript -> Turn rows (code only)
src/ingest/verify.py   quote verification (code only)
src/ingest/screen.py   prompt-injection screening and the <transcript> fence (code only)
src/ingest/extract.py  per-meeting event extraction (model)            [TODO]
src/memory/            SQLite store, FTS5, vectors, event ledger      [TODO]
src/agent/             question loop + brief                          [TODO]
eval/                  own questions + scoring                        [TODO]
docs/                  decisions.md, build-log.md, failures.md
out/                   answers.json
```

## Commands

```
python -m src.ingest.parse --check      # parse all transcripts, print counts
python -m pytest -q                     # tests
python -m src.memory.audit              # truth checks on every ledger event
python -m eval.run_abstain              # questions the agent must decline or correct
```
