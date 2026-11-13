# Failures

One entry per problem found: what happened, the cause, and what was done. Wrong answers on our own
eval set are under "Eval misses" (filled in from `eval/results/`).

## F-001: A free model returned an empty reply on a large prompt (Q18, ES2014)
**What happened:** In the first full run, Q18 came back as "The agent could not produce an answer."
The trace showed four "unparseable" replies in a row.
**Cause:** ES2014's ledger has 254 events. The full prompt was 55,793 characters (about 14K tokens)
and the free model returned an empty string. The client cached that empty string, so every retry
was served the same empty reply from the cache.
**Fix:** Empty replies are never cached, and the client tries the next free model before falling
back to the local one. Ledgers over 40,000 characters are now cut down by code to the topics that
best match the question (`retrieve.LEDGER_BUDGET`). This also matters at scale: a project with 100
meetings has thousands of events, and the prompt can't grow with them.

## F-002: Internal ids leaked into answer text (Q01, Q13)
**What happened:** Answers included strings like "(TS3006d-E13)" and "(TS3006b#0110)". The model
copied ledger ids and turn ids from the evidence into its sentences.
**Fix:** Code removes these ids from the answer text (`answer.clean_answer`). The citations already
carry the evidence.

## F-003: Too few actions are marked "reported back"
**What happened:** Only 15 of 220 action items have the status "reported". Reading a sample shows
more of them were followed up.
**Cause:** The rule needs a report-back event that either points at the action's id or has the
same topic and comes from the action's owner. The extractor often gives the report-back a
different topic name, or leaves `refers_to` empty.
**Effect:** Briefs can list an action as open after it was done.
**Not fixed yet.** Better options: have the extractor list open actions from the ledger and mark
which ones the meeting answers, or match on embedding similarity between the action and later report-backs.

## F-004: The validator dropped 40 of 7,239 extracted events (0.6%)
Each one had a quote that wasn't in the cited turn or the turns next to it, and couldn't be repaired
by code. The event is lost, not stored with a bad quote. Most of these were long paraphrases
written by the model in place of the speaker's words.

## Eval misses (details in eval/results/summary.md)

### F-005: The local model echoed the question as its answer (E01, qwen3:4b)
**Cause:** a 4B model given a 10K-token prompt lost the task and copied the question.
**Fix:** code now detects an echoed question and sends the repair round with that problem named.

### F-006: Right words, wrong claim (E02, E06, E07, qwen3:4b)
E02 said the final design had a screen (it had none). E06 had the right figures but said the
design was 1.5 Euros over budget (it was 3.5 over, or 0.5 without speech recognition). E07 said
the solar cells were kept and also dropped. The keyword scorer marked all three right.
**Cause:** the model reads the ledger but doesn't reason over it reliably at this size.
**What it shows:** the quote check guarantees the evidence is real, not that the sentence built on
it is right. The automatic score needs a hand check next to it, which is why both are reported.

### F-007: Missed a change between meetings (E04, qwen3:4b)
Meeting c debated soft rubber (C, D) against hard rubber (B), and the final meeting called it hard
rubber. The answer said "rubber" for both meetings.
**Cause, checked in the ledger:** the soft/hard debate was extracted only as proposals, never as a
decision, and the final meeting's "it's hard rubber" was not extracted as an event at all. So the
"replaced by" rule had nothing to link. This is an extraction gap, not a ranking problem.
**Also:** writing this up showed our own gold answer was too sure that c "chose soft rubber". It was
rewritten to say the two versions were debated. The question changed with it, so this miss was found by re-reading the transcript.
