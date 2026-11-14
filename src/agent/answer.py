"""The question agent: route, gather, ask, verify, loop.

  1. Route (code)       find the team; everything after is filtered to it
  2. Gather (code)      the team's ledger + speaker roles + keyword/vector search hits
  3. Ask (model)        the model either answers with citations, or asks for more
                        searches ({"search": [...]}), at most MAX_SEARCH_ROUNDS times
  4. Verify (code)      every citation becomes a meeting id + exact quote, or is dropped.
                        Citing a ledger event reuses its quote, already verified at ingest.
  5. Repair (model)     if no citation survives, or all come from one meeting, up to two retries
                        that tells the model exactly what failed

Model calls per question: 1 typically, at most 1 + MAX_SEARCH_ROUNDS + MAX_REPAIRS.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from collections.abc import Callable

from src.agent import retrieve
from src.clients.llm import complete, parse_json
from src.ingest.extract import _snap
from src.memory.store import connect

MAX_SEARCH_ROUNDS = 2
MAX_REPAIRS = 2
MAX_CITATIONS = 3

PROMPT = """You answer questions about a team's recorded meetings, using ONLY the evidence below.

QUESTION: {question}

HOW TO READ THE EVIDENCE
- LEDGER: events extracted from every meeting of team {team}, ordered by meeting (a, b, c, d).
  Statuses are computed by rule: "current" = the latest word on that topic, "superseded by X" =
  replaced later, "open"/"reported"/"addressed" for actions and objections.
- SPEAKERS: who holds which role.
- TURNS: exact transcript lines, as [meeting#turn] Speaker X: words.

ANSWER RULES
- 1 to 3 plain sentences. Give speakers by letter, plus role when known ("Speaker C, the Industrial Designer").
- Most questions span meetings: check the ledger for what changed and say what was current at the end.
- Cite 1 to 3 pieces of evidence, from different meetings when the answer spans meetings. A citation is either
  {{"event": "<ledger event id>"}}  or  {{"turn": "<meeting#turn>", "quote": "<6+ consecutive words copied exactly from that turn>"}}.
- If the evidence is missing something you need, reply instead with {{"search": ["query", ...]}} (up to 3 short queries).
  You have {rounds_left} search round(s) left.
- If the evidence does not contain the answer, say what is known and that the rest was not found. Never guess.

Reply with JSON only: {{"answer": "...", "citations": [...]}}  or  {{"search": [...]}}

LEDGER:
{ledger}

SPEAKERS:
{speakers}

TURNS:
{turns}
{feedback}"""


def _resolve_citations(conn: sqlite3.Connection, citations: list, team: str,
                       upto_letter: str | None) -> tuple[list[dict], list[str]]:
    """Turn model citations into verified {meeting_id, quote}. Code decides what survives."""
    out, problems = [], []
    for c in citations if isinstance(citations, list) else []:
        if not isinstance(c, dict):
            continue
        if c.get("event"):
            row = conn.execute("SELECT * FROM events WHERE event_id = ? AND team = ?",
                               (c["event"], team)).fetchone()
            if row is None or (upto_letter and row["letter"] > upto_letter):
                problems.append(f"event {c['event']} does not exist")
                continue
            out.append({"meeting_id": row["meeting_id"], "quote": row["quote"]})
            continue
        turn_id, quote = str(c.get("turn", "")), str(c.get("quote", ""))
        if "#" not in turn_id:
            problems.append(f"citation {c} has no turn id")
            continue
        meeting_id, _, idx = turn_id.partition("#")
        if not meeting_id.startswith(team) or (upto_letter and meeting_id[-1] > upto_letter):
            problems.append(f"turn {turn_id} is outside the allowed meetings")
            continue
        turns = {r["idx"]: r["text"] for r in conn.execute(
            "SELECT idx, text FROM turns WHERE meeting_id = ?", (meeting_id,))}
        snapped = _snap(quote, int(idx) if idx.isdigit() else -1, turns)
        if snapped is None:
            problems.append(f"quote not found in {turn_id}: {quote!r}")
            continue
        out.append({"meeting_id": meeting_id, "quote": snapped[1]})
    # de-duplicate, prefer spreading across meetings, cap at MAX_CITATIONS
    unique = list({(c["meeting_id"], c["quote"].lower()): c for c in out}.values())
    unique.sort(key=lambda c: c["meeting_id"])
    chosen, seen_meetings = [], set()
    for c in unique:
        if c["meeting_id"] not in seen_meetings:
            chosen.append(c)
            seen_meetings.add(c["meeting_id"])
    for c in unique:
        if c not in chosen:
            chosen.append(c)
    return chosen[:MAX_CITATIONS], problems


#: Ledger ids (TS3006d-E13, also with Unicode hyphens) and turn ids (TS3006b#0110).
INTERNAL_ID = re.compile(r"\b[A-Z]{2}\d{4}[a-d](?:#\d+|[-‐‑]E\d+)\b")


def clean_answer(text: str) -> str:
    """Strip internal ids the model sometimes copies into prose, keeping the words around them:
    "(Speaker C, ES2005d-E07)" becomes "(Speaker C)". The citations carry the evidence."""
    text = INTERNAL_ID.sub("", text)
    text = re.sub(r"\(\s*[,;\s]*\)", "", text)            # brackets left empty
    text = re.sub(r"[,;]\s*\)", ")", text)                 # "(Speaker C, )"
    text = re.sub(r"\(\s*[,;]\s*", "(", text)              # "( , Speaker C)"
    text = re.sub(r"\s{2,}", " ", text)
    return re.sub(r"\s+([.,;)])", r"\1", text).strip()


def answer(question: str, *, conn: sqlite3.Connection | None = None, team: str | None = None,
           upto_letter: str | None = None, on_step: Callable[[dict], None] | None = None) -> dict:
    """on_step gets each step as it happens, so the page can show progress while the model works."""
    conn = conn or connect()
    started = time.time()

    class Trace(list):
        def append(self, step: dict) -> None:
            super().append(step)
            if on_step:
                on_step(step)

    trace: list[dict] = Trace()
    notify = on_step or (lambda step: None)
    team = team or retrieve.team_from_question(question)
    if team is None or conn.execute("SELECT 1 FROM meetings WHERE team = ?", (team,)).fetchone() is None:
        return {"answer": "Name the team in the question, for example TS3012.",
                "citations": [], "trace": [{"step": "route", "result": "no team"}]}
    trace.append({"step": "route", "team": team})

    queries = [question]
    turns = retrieve.gather(conn, team, queries, upto_letter=upto_letter)
    trace.append({"step": "gather", "queries": queries, "turns": len(turns)})
    ledger_text = retrieve.ledger_text(conn, team, upto_letter, query=question)
    speakers = retrieve.speakers(conn, team, upto_letter)

    feedback, result, best, rounds, repairs = "", None, None, 0, 0
    for _ in range(MAX_SEARCH_ROUNDS + MAX_REPAIRS + 2):
        prompt = PROMPT.format(question=question, team=team, rounds_left=MAX_SEARCH_ROUNDS - rounds,
                               ledger=ledger_text or "(empty)", speakers=speakers or "(unknown)",
                               turns=retrieve.render_turns(turns), feedback=feedback)
        notify({"step": "thinking", "repair": repairs, "search_rounds": rounds})
        try:
            text, model = complete(prompt)
        except Exception as error:  # noqa: BLE001 - every backend down: report, don't crash the run
            trace.append({"step": "ask", "result": f"no model available: {str(error)[:200]}"})
            break
        try:
            reply = parse_json(text)
        except (ValueError, json.JSONDecodeError):
            trace.append({"step": "ask", "model": model, "result": "unparseable"})
            feedback = "\nYOUR PREVIOUS REPLY WAS NOT VALID JSON. Reply with JSON only."
            continue
        if reply.get("search") and rounds < MAX_SEARCH_ROUNDS:
            rounds += 1
            extra = [str(q) for q in reply["search"]][:3]
            before = len(turns)
            turns.update(retrieve.gather(conn, team, extra, upto_letter=upto_letter))
            trace.append({"step": "search", "model": model, "queries": extra, "new_turns": len(turns) - before})
            continue
        notify({"step": "verifying", "citations": len(reply.get("citations") or [])})
        citations, problems = _resolve_citations(conn, reply.get("citations", []), team, upto_letter)
        meetings = {c["meeting_id"] for c in citations}
        trace.append({"step": "answer", "model": model, "citations": len(citations),
                      "meetings": sorted(meetings), "problems": problems})
        result = {"answer": str(reply.get("answer", "")).strip(), "citations": citations}
        score = (len(meetings), len(citations))
        if best is None or score > best[0]:
            best = (score, result)  # a repair can make things worse; keep the best attempt
        too_long = len(re.findall(r"[.!?](?:\s|$)", result["answer"])) > 3
        echoed = question.lower()[:60] in result["answer"].lower()  # seen in testing (E01)
        if citations and len(meetings) >= 2 and not too_long and not echoed:
            break
        if repairs >= MAX_REPAIRS:
            break
        repairs += 1
        issues = list(problems)
        if not citations:
            issues.append("No citation could be verified.")
        elif len(meetings) < 2:
            issues.append("All citations come from one meeting; cite evidence from at least two meetings if the answer spans them.")
        if too_long:
            issues.append("The answer is longer than 3 sentences; shorten it to 1 to 3 sentences.")
        if echoed:
            issues.append("The answer repeats the question instead of answering it.")
        feedback = ("\nYOUR PREVIOUS ANSWER: " + json.dumps(reply)[:1500] +
                    "\nPROBLEMS: " + " ".join(issues) +
                    " Prefer citing ledger events by id. Reply with corrected JSON.")
    result = best[1] if best else {"answer": "The agent could not produce an answer.", "citations": []}
    result["answer"] = clean_answer(result["answer"])
    result["trace"] = list(trace)
    result["seconds"] = round(time.time() - started, 1)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask the meeting memory a question.")
    parser.add_argument("question")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args(argv)
    result = answer(args.question)
    if not args.trace:
        result.pop("trace")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
