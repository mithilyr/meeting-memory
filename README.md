# Meeting Memory

Turns meeting transcripts into a memory you can question. It keeps a running record of decisions,
commitments and disagreements, knows which version is current, proves every claim with the
speaker's exact words, and writes a brief before a team's next meeting.

Built for the Catalist Agentic AI Intern build test, on 138 AMI meetings (676,745 words).

- [The idea](docs/idea.md)
- [Architecture and diagram](docs/architecture.md)
- [One-page write-up](docs/writeup.md)
- [Design decisions, D-001 onward](docs/decisions.md)
- [Where it fails](docs/failures.md)
- [The submission: out/answers.json](out/answers.json)

## Try it hosted
A read-only copy runs on Render's free tier (link in the submission email; the first visit after a quiet
spell takes about a minute to wake). It holds all 138 meetings; uploads are switched off there. It is
built from `deploy/render/Dockerfile`, which downloads the prebuilt memory from a public Hugging Face
dataset. API keys go in the service's environment settings, never in the image.

## Run it (about 10 minutes, $0)

You need Python 3.11+ and three free API keys (no local models, D-021).

```
python -m venv .venv
.venv\Scripts\activate                # Windows   (source .venv/bin/activate elsewhere)
pip install -r requirements.txt
copy .env.example .env                # add OPENROUTER_API_KEY, GROQ_API_KEY and VOYAGE_API_KEY (all free)
```

The data folder is expected next to this repo (`../Catalist_AI_Intern_Build_Test_Data`); set
`DATA_PATH` in `.env` if it is elsewhere.

### Load the memory that is already extracted (a few minutes, no language-model calls)
The model's extraction output for all 138 meetings ships in `snapshot/extracted/`. Rebuilding the
store from it re-runs only code (parse, index, validate, statuses) plus Voyage embeddings:

```
python -m src.memory.store ingest
python -m src.ingest.extract import-all                  # also runs the truth audit on every event
python -m src.memory.store embed                          # Voyage vectors for turns and ledger events (about 5 minutes)
python -m src.memory.names                                # project names for the picker (35 free model calls)
python -m src.agent.route                                 # project profiles, for questions that name no project (1 Voyage call)
```

### Use it
```
python -m src.ui.server                                   # web page at http://localhost:8765
python -m src.agent.answer "Who proposed kinetic energy in team ES2015?" --trace
python -m src.agent.brief TS3012                          # brief before TS3012's last meeting (uses a-c only)
python run.py                                             # regenerates out/answers.json
python -m eval.run_eval                                   # scores the agent on our 10 hand-checked questions
python -m eval.route_check                                # project suggestions for questions that name no project
python -m eval.run_abstain                                # questions it must decline or correct (should be 7/7)
python -m src.memory.audit                                # truth checks on every stored event
python -m pytest -q
```

### Rebuild the memory from the transcripts
```
python -m src.memory.store ingest     # parse + full-text index; unchanged files are skipped (1.6 s for 138)
python -m src.memory.store embed      # Voyage embeddings for new chunks
python -m src.ingest.extract api --team ES2002     # extract a team with Claude Haiku 5.5 (needs ANTHROPIC_API_KEY)
```

**Disclosure (D-007, D-010):** to keep the build at $0, the 138 meetings were extracted by
Claude Haiku 5.5 running as Claude Code subagents. They filled the job files this pipeline
generates (`python -m src.ingest.extract next --team X`) and every output went through the same
code validator (`import`). The `api` command sends the identical prompt and JSON schema to the
Claude API. That path is written but was not run during the build.

## What is code and what is a model

| Code (never a model) | Model |
|---|---|
| Parsing, ids, content hashes, incremental ingest | Pulling events out of messy speech (Haiku 5.5) |
| Team filter, meeting cutoff for briefs | Writing the answer and the brief from given evidence |
| Keyword (BM25) search; vectors come from Voyage AI | Asking for more searches when evidence is thin |
| What is current / superseded / open (rules on meeting order) | |
| Quote verification and repair, output format, eval scoring | |
| Truth audit: figures, currencies, speakers checked against the transcripts | |
| Answer checks: figures and people in the answer must be in the evidence | |
| Prompt-injection screening of uploads; project suggestions when none is named | |

## Layout
```
run.py                 answers.json for the 25 questions + TS3012 brief
src/ingest/            parse.py (files -> turns), verify.py (quote rule), extract.py (jobs, validation, API path),
                       numbers.py (spoken figures), screen.py (prompt-injection screening)
src/memory/            store.py (SQLite, FTS5, vectors), ledger.py (status rules), audit.py (truth checks),
                       refresh.py (one-step update), names.py (project names)
src/agent/             retrieve.py (search), answer.py (question loop), grounding.py (answer checks),
                       route.py (project suggestions), brief.py
src/clients/           openrouter.py + retry.py (from CodeFest), groq.py, voyage.py, llm.py (provider chain)
src/ui/                server.py + index.html (demo page)
eval/                  own_questions.json (10, unseen teams), abstain_questions.json (7 that need a no),
                       route_check.py, run_eval.py, run_abstain.py, results/
docs/                  idea, architecture, write-up, decisions, failures, build log
```
