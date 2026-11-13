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
| E06 | right | right | 16 Euros, 3 for speech recognition, over the 12.50 budget. All citations from meeting d |
| E07 | wrong | right | The answer says "drop"; the scorer only looked for "dropped". Scorer fixed |
| E08 | wrong | wrong | Named "the advanced chip" instead of the LCD as a dropped feature |
| E09 | right | right | |
| E10 | right | right | Adds D as favouring titanium, which the transcript supports; says plastic and rubber were "decided", which overstates it |

Auto 6/10 (7/10 after the scorer fix), hand 7/10. Every quote verified: 10/10. Citations from 2+
meetings: 9/10. Average 25 s per question.

## Comparison

| Run | Hand-checked right | All quotes verified | 2+ meetings cited |
|---|---|---|---|
| Local qwen3:4b | 5/10 | 10/10 | 5/10 |
| Hosted (Groq) | 7/10 | 10/10 | 9/10 |
