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

## Run 2: free API model (nemotron-3-ultra), pending the daily quota reset
