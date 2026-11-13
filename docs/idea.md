# The idea we present to Catalist

## One sentence
**A meeting memory that keeps a running record of decisions, commitments and disagreements,
knows which version is current, proves every claim with the speaker's exact words, and briefs
each team before its next meeting without anyone asking.**

## The problem, in the company's words
- "We decided that weeks ago." Nobody can find where, or whether it was changed since.
- "Who said they'd do that?" Promises made in meetings are lost by the next one.
- "Why are we arguing about this again?" Objections are never recorded as resolved or open.
- Nobody reads hours of transcripts before a meeting, so every meeting restarts from memory.

## What we built: five ideas

### 1. A decision record
Plain search finds every place a topic came up, but cannot say which one is the answer now.
We keep a **ledger**: every decision is stored with the meeting it came from. When a later
meeting decides the same thing differently, the old entry is marked "replaced by" the new one.
"What did we decide about the battery?" returns the current answer *and* the history of how it got there.

### 2. Every claim comes with the exact words that prove it
Each answer cites the meeting and the speaker's exact words. Code checks every quote word for word
before it is shown. A claim that cannot be backed by the transcript is not shown. Staff can trust
an answer without re-reading the meeting.

### 3. Commitments are tracked until they are done
When someone says "I'll find out what the display costs", that becomes an open action with an
owner. When a later meeting reports back, it is marked done. When nobody reports back, it stays
open and appears in the next brief. (questions.json asks about "commitments and whether they were followed up".)

### 4. Briefs arrive on their own
Before each meeting, the system writes a one-page brief for that team: what is decided, what
changed, open actions and owners, and disagreements still open. Each point is cited. It only uses
meetings that have already happened. Nobody has to request it.

### 5. Cost grows only with new meetings
Each meeting is read by a model **once**, when it arrives (about $0.0016 per meeting on Haiku 5.5 batch).
After that, a question searches only the team or project it is about, so it costs the same at
10 meetings or 10,000. Old meetings are never re-processed unless we choose to improve the extractor.

## What makes it work on messy, real speech
- When meeting c says "let's go with the other one",
  the extractor is given the team's ledger so far, so "the other one" is linked to the earlier
  option. Meetings of a team are read in order for this reason.
- The model turns messy speech into structured events. Code handles ordering, "replaced by",
  filters, quote checks and the output format. A mistake in those parts would be silent and
  costly, so no model touches them.
- If the evidence does not cover the question, the answer says so and does not guess.

## Daily use, with almost no effort from staff
| Moment | What happens | Staff effort |
|---|---|---|
| A meeting ends | The transcript lands in the inbox folder (or is uploaded on the Add meetings page) and Refresh reads it | None, once Refresh runs on a schedule |
| 1 hour before a meeting | The brief is posted to the team by email or Slack (planned; today it is one click on the Brief page) | Read it: 2 minutes |
| Any time | Ask a question in plain English and get an answer with cited quotes | One question |
| An answer is wrong | Flag it; it becomes a test case for the next version (planned) | One click |

## Three price points, one system
| | Best quality | **Recommended** | Free demo (this build) |
|---|---|---|---|
| Per 1,000 meetings ingested | ~$32 | **~$1.60** | $0 |
| Per question | ~$0.10 | **under $0.01** | $0 |
Details: `docs/architecture.md`.
