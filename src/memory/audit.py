"""Truth checks on the ledger. Code only, no model (D-032).

The extractor is a model, and a model can write a summary that says more than the meeting did.
Every stored event is checked against the transcript after extraction, for the whole corpus and for
every new meeting on ingest. A failed check never deletes the event (the quote is still real); it
flags it, and every reader of the ledger sees the flag:

  figure_not_said    a figure in the value or summary is never said in any of the team's meetings
                     (also catches averages the extractor worked out itself)
  unit_not_said      the value's currency (Euros, Francs, ...) is never used by the team
  speaker_mismatch   the event's speaker is not the speaker of the quoted turn (action items excepted:
                     "A asked B to ..." is quoted from A)
  unit_differs       the value says Euros but the quoted turn names another currency
  bad_link           refers_to points at an event that does not exist or comes later (ignored by ledger.compute)

    python -m src.memory.audit            check every event, store the flags, print a summary
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict

from src.ingest.numbers import currencies, figures, same, stated
from src.memory.store import connect

LABELS = {
    "figure_not_said": "figure not found in the transcripts",
    "unit_not_said": "currency not used in the transcripts",
    "speaker_mismatch": "speaker differs from the quoted turn",
    "bad_link": "refers to a later or missing event",
    "unit_differs": "currency differs from the quoted words",
}


def _team_facts(conn: sqlite3.Connection, team: str) -> tuple[set[float], set[str], dict[str, str], dict[str, str]]:
    said, money, speaker_of, text_of = set(), set(), {}, {}
    for r in conn.execute("SELECT turn_id, speaker, text FROM turns WHERE team = ?", (team,)):
        said |= figures(r["text"])
        money |= currencies(r["text"])
        speaker_of[r["turn_id"]] = r["speaker"]
        text_of[r["turn_id"]] = r["text"]
    return said, money, speaker_of, text_of


def check_team(conn: sqlite3.Connection, team: str) -> Counter:
    """Flag every event of one team. Returns counts per flag."""
    said, money, speaker_of, quoted = _team_facts(conn, team)
    events = conn.execute("SELECT * FROM events WHERE team = ?", (team,)).fetchall()
    order = {e["event_id"]: (e["letter"], e["turn_idx"]) for e in events}
    counts: Counter = Counter()
    for e in events:
        flags = []
        claim = re.sub(r"\bSpeaker [A-D]\b", "", f"{e['value'] or ''} {e['summary']}")
        if any(not any(same(n, x) for x in said) for n in stated(claim)):
            flags.append("figure_not_said")
        if e["value"] and currencies(e["value"]) and not (currencies(e["value"]) & money):
            flags.append("unit_not_said")
        quoted_money = currencies(quoted.get(e["turn_id"], ""))
        if e["value"] and currencies(e["value"]) and quoted_money and not (currencies(e["value"]) & quoted_money):
            flags.append("unit_differs")  # stored "3 EUR", but the quoted turn says "three Francs"
        turn_speaker = speaker_of.get(e["turn_id"])
        if e["type"] != "action_item" and e["speaker"] and turn_speaker and e["speaker"] != turn_speaker:
            flags.append("speaker_mismatch")
        ref = e["refers_to"]
        if ref and (ref not in order or order[ref] > order[e["event_id"]]):
            # an event cannot revise or answer something said after it. ledger.compute already only
            # follows links backwards in time, so the link changes no status; the flag records it.
            flags.append("bad_link")
        counts.update(flags)
        conn.execute("UPDATE events SET flags = ? WHERE event_id = ?", (json.dumps(flags) if flags else None, e["event_id"]))
    conn.commit()
    counts["events"] = len(events)
    return counts


def check_all(conn: sqlite3.Connection | None = None) -> Counter:
    conn = conn or connect()
    total: Counter = Counter()
    for (team,) in conn.execute("SELECT DISTINCT team FROM events ORDER BY team").fetchall():
        total += check_team(conn, team)
    return total


def coverage(conn: sqlite3.Connection, team: str) -> str:
    """Which meetings of the series are in the record, said plainly, so answers can say what is missing."""
    letters = [r[0] for r in conn.execute("SELECT letter FROM meetings WHERE team = ? ORDER BY letter", (team,))]
    if not letters:
        return f"No meetings of {team} are in the record."
    series = [chr(c) for c in range(ord("a"), ord(max(letters)) + 1)]
    missing = [f"meeting {ord(l) - 96} ({team}{l})" for l in series if l not in letters]
    text = (f"The record holds meetings {', '.join(str(ord(l) - 96) for l in letters)} of {team} "
            f"(latest: meeting {ord(letters[-1]) - 96}).")
    if missing:
        text += f" Missing from the record: {', '.join(missing)}. Nothing is known about what was said there."
    return text


if __name__ == "__main__":
    counts = check_all()
    print(f"{counts.pop('events')} events checked")
    for flag, n in counts.most_common():
        print(f"  {n:4}  {flag}: {LABELS[flag]}")
