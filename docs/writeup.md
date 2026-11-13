# Meeting Memory: write-up

## What it does
Each meeting is read once and turned into a ledger of decisions, proposals, actions, report-backs,
figures and objections. Every entry points at the turn it came from. Code orders the ledger by
meeting and marks what is current and what was replaced. Questions and briefs are answered from
the ledger plus keyword and vector search over the raw turns, and every quote is checked against
the transcript word for word before it's shown. The architecture diagram is in `docs/architecture.md`.

## Architecture in one paragraph
Ingest is code: the parser turns files into turns, SQLite stores them with a full-text index, and
Voyage AI embeddings cover search by meaning. No model runs locally. A content hash skips files already stored. Extraction is one model call per meeting, in meeting
order per team, with the team's ledger so far in the prompt, so "the other one" can be linked to an
earlier option. The answer agent routes to one project, gathers ledger + search hits, and asks the
model. The model may ask for more searches (up to 2 rounds). Code then verifies citations and sends
up to two repair rounds if quotes fail, all come from one meeting, the answer runs past 3 sentences
or it repeats the question. The best attempt is kept.
The brief is grouped by code (current, replaced, open actions, open objections) and written by the model.

## Where the line between model and code sits, and why
Code handles everything that has one right answer or is graded by a machine: parsing, ids, the
project filter, the cutoff that keeps TS3012's meeting d out of its brief, meeting order, the
"replaced by" rule, quote checks, the JSON format and our eval scoring. A model in those places
could only add mistakes, and some of them (a leaked future meeting, a paraphrased quote) would be
silent. The model handles what rules can't: reading disfluent speech into events, writing two
clear sentences from evidence, and deciding it needs another search. Citing a ledger event by id
reuses a quote that code already verified, so the hardest part for a model (copying six exact
words of "um, uh" speech) is avoided.

## Tools, and where they broke
- qwen3:8b (local) needs 6.6 GB with context, so on a 6 GB laptop GPU it ran at 5.9 tokens/s. That would mean about 9 hours for the corpus. Rejected.
- qwen3:4b (local) was fast, but in extraction it invented turn ids (1, 2, 3...), and provenance is what citations depend on. As an answer fallback it scored 5/10 when checked by hand. Local models were then removed (D-021): staff work remotely, so the tool has to run on a server with no GPU.
- Claude Haiku 5.5 did the extraction, as 7 Claude Code subagents, to keep the build at $0. The plan's session limit stopped them at 111 of 138 meetings, and they resumed after the reset. The validator dropped 40 of 7,239 events (0.6%).
- OpenRouter free models answer in 2 to 30 s. The free tier allows 50 requests a day, and the first full run plus one re-run used them up. A free model also returned an empty reply on a 55K-character prompt, and that empty reply was cached. Both are fixed: daily-limit detection, no caching of empty replies, and a ledger budget (F-001).
- Groq (second free provider) rejected Python's default user agent (Cloudflare error 1010), caps a free request at 8K tokens, and caps gpt-oss-120b at 200K tokens a day. The 8K cap forced prompt budgets (ledger 11K characters, turns 8K), and that budget caused one of the three wrong answers (F-008).
- Voyage AI embedded all 15,868 chunks; the corpus used about 3M of the 200M free tokens.
- The Gemini key reused from an earlier project was revoked (401), so Gemini isn't used.
- SQLite FTS5 + numpy held up. Ingest takes 1.6 s for 138 meetings; rebuilding the store from the committed extraction snapshot takes 26 s.

## Proof it works
Ten questions of our own (`eval/own_questions.json`), on 7 teams that are not in questions.json,
each checked against the transcript. Scored by code and again by hand, because keyword scoring can
be fooled (`eval/results/summary.md`).

| Run | Right (hand check) | All quotes verified | Cited 2+ meetings |
|---|---|---|---|
| Hosted, Groq | 7/10 | 10/10 | 10/10 |
| Local qwen3:4b (since removed) | 5/10 | 10/10 | 5/10 |

The three wrong answers on the hosted run, with causes checked in the ledger (`docs/failures.md`):
- E03: the prompt budget dropped the microphone events, because the question never mentions a microphone.
- E04: the final meeting's "it's hard rubber" was never extracted, so the answer used an earlier mention.
- E08: the evidence was there, but the model named the wrong dropped feature.

On the 25 graded questions every citation passes the word-for-word check and 23 of 25 cite two or
more meetings (Q15 and Q20 cite one, even after two repair rounds). `out/run_log.json` has each answer's full trace.

## Cost and time for 1,000 meetings
Measured on the real run: about 10.6K input and 4.3K output tokens per meeting.
- Claude Haiku 5.5 via the Batch API: about **$1.60** (about $3.20 without batch). Sonnet 5.5: about $32 batched.
- Time: teams run in parallel and a team's meetings run in order, so it's 4 batch rounds (a, b, c, d), each usually under an hour. Voyage embeddings for 1,000 meetings (about 115K chunks, 22M tokens) take minutes and fit in the free allowance.
- A question costs one to three model calls on one project's evidence, so its cost doesn't grow with the archive.

## What production would need
1. The API extraction path run for real (`extract.py api`, written but not exercised), switched to the Batch API.
2. Postgres + pgvector in place of SQLite, and a paid model tier: free quotas (OpenRouter 50 requests a day, Groq 200K tokens a day) ran out during a single day of testing.
3. Project tagging per event and a meeting-to-projects table for meetings that cover several projects (designed in architecture.md section 6).
4. Better action follow-up matching: only 15 of 220 actions are linked to a report-back today (F-003).
5. Refresh on a schedule or a folder watcher, a calendar hook that posts each brief before the meeting, access control per project, and the eval set run in CI on every prompt change.
