# Eval results

Our 10 questions (eval/own_questions.json) are on teams the agent was never pointed at. Two scores
are kept: the automatic one from `run_eval.py` (keyword groups, run by code) and a hand check
against the gold answer. The hand check exists because the keyword scorer can be fooled: an answer
can contain the right words and still say the wrong thing.

## Run 1: local model only (qwen3:4b), 2026-11-13
Free API quota was used up, so this measures the fallback.

| Q | Auto | Hand | Note |
|---|---|---|---|
| E01 | wrong | wrong | Echoed the question back as the answer |
| E02 | right | wrong | Says the final design "included speech recognition and a screen"; it had no screen |
| E03 | right | right | |
| E04 | wrong | wrong | Missed soft rubber (c) changing to hard rubber (d) |
| E05 | right | right | |
| E06 | right | wrong | Right figures (16 and 3 Euros) but wrong arithmetic: "1.5 euros over" |
| E07 | right | wrong | Says the solar cells were both kept and dropped |
| E08 | right | right | |
| E09 | right | right | |
| E10 | right | right | Names only C; B also favoured titanium |

Auto 8/10, hand 5/10. Citations: 10/10 answers had every quote verified (by construction).
Citations from 2+ meetings: 5/10. Average 70 s per question on a laptop GPU.

## Run 2: hosted models only (Groq: gpt-oss-120b, then qwen3.8-27b), 2026-11-13
Local models were removed after run 1 (D-021). Prompts are capped near 16 to 22K characters to fit
Groq's free tier (8K tokens per request).

| Q | Auto | Hand | Note |
|---|---|---|---|
| E01 | right | right | 14.60 to 11.60 Euros, Speaker C |
| E02 | right | right | Vote for speech recognition, no screen in the final design |
| E03 | wrong | wrong | Missed the microphone for speech recognition in the final remote |
| E04 | wrong | wrong | Said the final case was "spongy rubber"; the final meeting says hard rubber |
| E05 | right | right | Speaker A's objection and no LCD are right; it also lists B as objecting, which is loose |
| E06 | right | right | 16 Euros, 3 for speech recognition, over the 12.50 budget |
| E07 | wrong | right | The answer says "drop"; the scorer only looked for "dropped". Scorer fixed |
| E08 | wrong | wrong | Named "the advanced chip" instead of the LCD as a dropped feature |
| E09 | right | right | |
| E10 | right | right | Adds D as favouring titanium, which the transcript supports; says plastic and rubber were "decided", which overstates it |

Auto 6/10 at first, 7/10 after the scorer fix; hand-checked 7/10. Every quote verified: 10/10.
Citations from 2+ meetings: 9/10 at first, 10/10 after the agent got a second repair round (E06 now
cites meetings c and d). Latest run: eval/results/eval_2026-11-13T17-15-54.json.

## Run 3: with the truth checks (D-032 to D-034), 2026-11-14
Same hosted models. Answers now carry a status and pass grounding checks; the audit flags reach the prompt.

| Q | Auto | Hand | Note |
|---|---|---|---|
| E01 | right | right | 14.60 to 11.60 Euros. A first draft was withheld until figures were backed (D-033) |
| E02 | right | right | |
| E03 | wrong | wrong | LCD, no buttons, recharger; still misses the microphone (F-008, partly fixed) |
| E04 | right | right | Hard rubber in the final meeting is now reported (was wrong in run 2) |
| E05 | right | right | All three objectors named, with reasons; no LCD in the end. Four sentences, over the limit (scoring now ranks length, see D-033) |
| E06 | wrong | right | 16 Euros, 3 for speech recognition, over 12.50. The scorer wanted "13" |
| E07 | wrong | right | "rejected the solar-cell idea": the scorer's word list lacks "rejected" |
| E08 | wrong | wrong | Again names "the advanced chip" instead of the LCD (F-010) |
| E09 | wrong | right | Right answer; the model wrote "Speaker" with a narrow no-break space, which the scorer missed. Both the agent and the scorer now normalise spaces and hyphens |
| E10 | right | right | |

Auto 5/10, hand-checked 8/10 (run 2: 7/10). Every quote verified: 10/10. Results:
eval/results/eval_2026-11-14T13-46-07.json.

## Abstention: questions the agent must decline or correct (D-033)
`python -m eval.run_abstain`, 7 own questions: 7/7. Supplier, salaries and Bluetooth (never discussed)
got "not discussed" with nothing cited; "why did TS3008 include an LCD" got "assumption does not match
the record" (they skipped it); IS1002's missing first meeting and TS3012's non-existent fifth meeting got
a plain no; a half-answerable question got "partly answered". Results: eval/results/abstain_latest.json.

## Comparison

| Run | Hand-checked right | All quotes verified | 2+ meetings cited |
|---|---|---|---|
| Local qwen3:4b | 5/10 | 10/10 | 5/10 |
| Hosted (Groq) | 7/10 | 10/10 | 10/10 |
| Hosted + truth checks | 8/10 | 10/10 | 7/10 |
