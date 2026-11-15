# Meeting Memory: write-up

## Architecture
Each meeting is read once and turned into a ledger: decisions, proposals, actions, report-backs,
figures and objections, each pointing at the turn it came from. Turns sit in SQLite with a full-text
index and Voyage AI vectors. A question is routed to one project, and only that project's ledger and
search hits go to the model, so a question costs the same at 138 meetings or 10,000. The model can ask
for up to 2 more searches. Code then checks the answer and sends up to 2 repair rounds. The diagram is
in `docs/architecture.md`; every design decision is in `docs/decisions.md` (D-001 to D-035).

**What is current** is decided by code from meeting order: the latest decision or figure on a topic is
current and earlier ones are marked replaced. Extraction runs each team's meetings in order with the
ledger so far in the prompt, so "the other one" in meeting c can be linked to an option from meeting a.

## Model or code
Code does everything with one right answer: parsing, ids, the project filter, meeting order, the
"replaced by" rule, the cutoff that keeps TS3012's meeting d out of its brief, quote checks, the JSON
format, eval scoring, and the truth checks below. A model there could only add errors, and some would
be silent (a leaked future meeting, a paraphrased quote). The model does what rules can't: reading
disfluent speech into events, writing a sentence or two from evidence, and deciding it needs another
search. It may cite a ledger event by id, and code swaps in that event's already-checked quote.

**Saying no beats guessing.** Code checks every stored figure, currency and speaker against the
transcripts on each import, old meetings and new alike, and flags what doesn't match (16 figures nobody
said, 1 currency stored as Euros where the speaker said Francs, out of 7,199 events). Every answer
carries a status (answered, partial, not discussed, conflicting, wrong premise). An answer that keeps a
figure found nowhere in its evidence is withheld, and a "not discussed" reply is challenged once with
any matching ledger events before it is accepted.

## Tools, and where they broke
- Local models (qwen3:8b, qwen3:4b) were too slow on a 6 GB GPU or invented turn ids. Removed (D-021):
  staff work remotely, so the tool has to run on a server.
- Claude Haiku 5.5 did the extraction as Claude Code subagents, keeping the build at $0. The plan's
  session limit stopped them at 111 of 138 meetings; they resumed after the reset.
- OpenRouter's free tier allows 50 requests a day and returned an empty reply on a 55K-character prompt.
  Groq's free tier caps a request at 8K tokens, which forced prompt budgets, and cut off long JSON until
  the output cap was raised. Both ran out of daily quota during testing.
- Voyage AI embedded 15,868 chunks and 7,199 ledger events inside the free allowance.
- SQLite FTS5 and numpy held up: ingest takes 1.6 s, a full rebuild from the saved extraction 30 s.

## Proof it works
Ten questions of our own on 7 teams not in questions.json, checked by hand against the transcripts
(`eval/results/summary.md`): **8/10 right**, every quote verified. Seven more questions that should get
a no (never discussed, a meeting that doesn't exist, a false premise): **7/7** declined or corrected,
and 4 requests outside the meetings (a poem, general knowledge, code, instructions to the AI) all refused.
On the 25 graded questions every citation passes the word-for-word check and all 25 cite two or more
meetings.

**Three it got wrong** (`docs/failures.md`):
- E03: names the LCD but not the microphone. The microphone events were cut by the prompt budget;
  ranking the ledger by meaning now brings 2 of 13 into the prompt, and the model still leaves them out.
- E08: the evidence was there, but the model named "the advanced chip" instead of the LCD as dropped.
- E04: said "spongy rubber" when the final meeting says "hard rubber", because that line was never
  extracted. It came out right in the latest run, but the cause (a missed extraction) is still there.

## Cost and time for 1,000 meetings
Measured: about 10.6K input and 4.3K output tokens per meeting. With Claude Haiku 5.5 on the Batch API
that is about **$1.60** ($3.20 without batch). Teams run in parallel and each team's meetings in order,
so it is 4 batch rounds, each usually under an hour. Embeddings take minutes and fit the free allowance.

## What production would need
1. The API extraction path run for real on the Batch API (written, not exercised).
2. A paid answer model and Postgres with pgvector: free quotas ran out within one day of testing.
3. Login, a record of who uploaded each meeting, and review before uploaded meetings count.
4. A check for missed extractions (E04), better action follow-up matching (F-003), and project tags
   for meetings that cover several projects.
5. Refresh on a schedule, briefs posted before each meeting, and the eval run on every prompt change.
