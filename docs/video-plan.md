# Walkthrough video plan (3 to 5 minutes)

The PDF asks for a 3 to 5 minute walkthrough. Catalist says they care about judgment over polish, so
the video shows decisions and honest failures, not a feature tour. Target: 4 minutes 30 seconds.
Spoken lines are suggestions; say them in your own words.

## Before recording (about 20 minutes, the day before)
1. Warm the answers so the demo is instant and doesn't depend on free quotas on the day. Run each
   demo question once (step 3 below); the reply is cached on disk and comes back in about 1 second.
2. Start the page: `python -m src.ui.server`, open http://localhost:8765, browser zoom 110%.
3. Have open in tabs: the page, `docs/architecture.md` on GitHub (the diagram renders there),
   `docs/decisions.md` index, `docs/failures.md`.
4. Record at 1080p with Xbox Game Bar (Win+Alt+R) or OBS. Close notifications.

Demo questions to warm (paste each into Ask once):
- `What energy source did Team ES2015 end up with, and who proposed it?`
- `How much were the designers in Team IS1004 paid for the project?`
- `Why did Team TS3008 decide to include an LCD display in the final remote?`
- `What is the backup energy source for the remote?` (no project named)

## Shot list

| Time | Show | Say (the point) |
|---|---|---|
| 0:00-0:20 | Ask page | The problem: hundreds of hours of meetings nobody can search. This turns them into memory you can question, with the exact words as proof. |
| 0:20-1:00 | Architecture diagram | Each meeting is read once into a ledger of decisions, proposals, actions, figures and objections, each tied to its turn. Questions go to one project only, so cost stays flat at 10,000 meetings. SQLite plus Voyage vectors, no framework. |
| 1:00-1:40 | Timeline, TS3009 | Memory over time: code, not the model, decides what is current from meeting order. Show the titanium decisions struck through as replaced, and the final one marked current. |
| 1:40-2:30 | Ask: ES2015 energy question | The live steps (find project, search, write, check every quote). The answer, the checked quotes, "show in transcript", "Whole meeting". |
| 2:30-3:00 | Ask: IS1004 pay, then TS3008 LCD | Saying no beats guessing: "Not discussed" for something never said; "the assumption does not match the record" for a false premise. Then the no-project question: it lists the closest projects instead of guessing. |
| 3:00-3:25 | Brief, TS3012 | Built from meetings 1 to 3 only. The cutoff is in code, so the final meeting can't leak in. Every point cites its words. |
| 3:25-3:55 | README table, then Timeline IS1000 "unverified" chip | The model-vs-code line: code does anything with one right answer, the model reads messy speech and writes. Code even audits the model's own notes: 16 figures nobody said were caught and flagged. |
| 3:55-4:30 | eval/results/summary.md, docs/failures.md | Proof: 8/10 on my own questions checked by hand, 7/7 correct refusals, all 25 graded answers verified word for word. Three it got wrong and why (E03, E08, E04). Cost: about $1.60 per 1,000 meetings on Haiku 5.5 Batch. Free tiers broke: 50 requests a day, 8K-token cap. |
| 4:30-4:50 | decisions.md index | Every decision is logged with what was rejected (35 of them). Production needs: paid models, Postgres, login and review for uploads. Close. |

## If they ask for a live demo instead
Questions they give you run the same way. If the free daily quota is spent, the page says so and shows
the search results word for word, so it still answers with evidence. Paid keys on the day avoid that.
