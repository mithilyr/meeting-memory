# Voiceover script (ElevenLabs)

Paste one section at a time, so each clip lines up with its shot and is easy to re-record.
About 700 words: 4 minutes 45 seconds at a calm 145 words a minute.

**Settings:** model Eleven Multilingual v2; a calm narrator voice from the library; Stability 55,
Similarity 75, Style 0, Speaker boost on. The `<break time="..." />` tags add pauses; ElevenLabs
reads them as silence. Numbers are written the way they should be spoken.

---

## 1. The problem (card 01, then the Ask page) · about 25 s

A founder records every meeting. After a few months, there are hundreds of hours of transcripts, and nobody can find the decision they need when it matters. <break time="0.6s" /> I built Meeting Memory to fix that. It turns meeting transcripts into memory you can question, and it proves every answer with the speaker's exact words.

## 2. How it works (card 02, then the architecture diagram) · about 40 s

Each meeting is read once, in order, and turned into a ledger: decisions, proposals, actions, figures and objections. Every entry points back to the exact line it came from. <break time="0.5s" /> The transcripts stay the source of truth, stored in SQLite with a keyword index and vector search. <break time="0.5s" /> When a question comes in, the agent works on one project only. It searches that project's ledger and transcripts, writes an answer, and code checks it before you see it. Because each question touches one project, the cost stays flat, whether there are a hundred meetings or ten thousand.

## 3. Memory over time (card 03, then Timeline on team T S thirty oh nine) · about 40 s

The hard part is memory over time. A decision in the third meeting can replace one from the first. <break time="0.5s" /> That isn't left to the model. Code orders every decision by meeting, and marks the latest one on each topic as current. <break time="0.5s" /> This team planned a titanium back, argued about it across two meetings, and finally dropped it to meet the cost target. The earlier decisions are struck through as replaced, and the final one is marked current. <break time="0.5s" /> And when someone refers back to "the other one", the extractor links it to the earlier option, because it reads each meeting with the ledger so far.

## 4. Ask a question (card 04, then Ask) · about 45 s

Let's ask a question. <break time="0.5s" /> While it runs, the page shows the agent's real steps: find the project, search its meetings, read and write, then check every quote. <break time="0.8s" /> The answer comes back in a sentence or two, with up to three quotes. Each quote has been checked word for word against the transcript, so it can't be paraphrased or made up. <break time="0.5s" /> If you want more proof, open it in the transcript, read the whole meeting, or download the original file.

## 5. Saying no (card 05, then the three questions) · about 30 s

Saying no matters as much as answering. <break time="0.5s" /> Ask what the designers were paid, and it tells you the meetings never discussed it, instead of guessing. <break time="0.5s" /> Ask why a team chose an L C D screen when they actually rejected it, and it corrects the question. <break time="0.5s" /> Ask without naming a project, and it lists the projects that discuss it most, with the line that matched, and lets you choose.

## 6. The brief (card 06, then Brief) · about 25 s

Before a team's final meeting, it writes a brief: what was decided, what changed, open actions and who owns them, and disagreements still open. <break time="0.5s" /> It only reads the meetings that have already happened. That cutoff is enforced in code, so the final meeting can't leak in. Every point cites its source.

## 7. Model or code (card 07, then the README table and the "unverified" chip) · about 35 s

Where the model stops and code starts was a deliberate choice. Anything with one right answer is plain code: parsing, ordering, what is current, quote checks, and the output format. <break time="0.5s" /> The model only does what rules can't: reading messy speech, and writing clear answers. <break time="0.5s" /> Code even audits the model's own notes. It found sixteen figures that nobody actually said, and one price stored in Euros that was spoken in Francs. Those are flagged, and never repeated as fact.

## 8. Proof and failures (card 08, then the results and failures pages) · about 40 s

Does it work? <break time="0.5s" /> On ten questions of my own, checked by hand against the transcripts, it got eight right. On seven questions that should get a no, it said no all seven times. All twenty-five graded answers pass the word-for-word quote check. <break time="0.5s" /> Three answers it got wrong are written up, with their causes. <break time="0.5s" /> Ingesting a thousand meetings costs about one dollar sixty with Claude Haiku on the Batch API, and takes under four hours. <break time="0.5s" /> The free tiers I built on broke at this size: fifty requests a day, and an eight-thousand-token cap per request.

## 9. What production needs (card 09, then the decision index) · about 20 s

Every design decision is logged, with what I rejected and why. <break time="0.5s" /> For production, it would need paid models, Postgres, and a login with review for uploaded meetings. <break time="0.5s" /> The code, the write-up and the answers are all in the repository. Thank you.
