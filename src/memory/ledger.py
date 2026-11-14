"""What is current: statuses computed by rule from meeting order. Plain code, no model.

Rules (D-001, D-009), applied to one team's events sorted by (meeting letter, turn):
  decision, number  The latest one on a topic is `current`; each earlier one is
                    `superseded` by the next. A decision whose refers_to points at an
                    earlier decision also supersedes it, even across topics.
  action_item       `reported` if a report_back refers to it, or a later report_back on
                    the same topic comes from the owner. Otherwise `open`.
  objection         `addressed` if a decision on the same topic comes after it, or a
                    decision refers to it. Otherwise `open`.
  proposal          `decided` if a decision on the same topic comes after it. Otherwise `open`.

Statuses depend on which meetings are visible. The brief for a team's final meeting
must not see that meeting, so `compute` takes the visible events, and nothing here
reads a stored status when a cutoff applies.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict


def _key(e: dict) -> tuple[str, int]:
    return (e["letter"], e["turn_idx"])


def compute(events: list[dict]) -> dict[str, tuple[str | None, str | None]]:
    """event_id -> (status, superseded_by), from the visible events only."""
    events = sorted(events, key=_key)
    by_id = {e["event_id"]: e for e in events}
    result: dict[str, list] = {e["event_id"]: [None, None] for e in events}

    for kind in ("decision", "number"):
        by_topic: dict[str, list[dict]] = defaultdict(list)
        for e in events:
            if e["type"] == kind:
                by_topic[e["topic"]].append(e)
        for chain in by_topic.values():
            for earlier, later in zip(chain, chain[1:]):
                result[earlier["event_id"]] = ["superseded", later["event_id"]]
            result[chain[-1]["event_id"]][0] = "current"

    for e in events:
        target = by_id.get(e.get("refers_to") or "")
        if e["type"] == "decision" and target and target["type"] == "decision" and _key(target) < _key(e):
            result[target["event_id"]] = ["superseded", e["event_id"]]

    decisions = [e for e in events if e["type"] == "decision"]
    for e in events:
        later = [d for d in decisions if _key(d) > _key(e)]
        if e["type"] == "action_item":
            done = any(
                r["type"] == "report_back"
                and _key(r) > _key(e)
                and (r.get("refers_to") == e["event_id"]
                     or (r["topic"] == e["topic"] and r.get("speaker") == e.get("owner")))
                for r in events
            )
            result[e["event_id"]][0] = "reported" if done else "open"
        elif e["type"] == "objection":
            addressed = any(d["topic"] == e["topic"] or d.get("refers_to") == e["event_id"] for d in later)
            result[e["event_id"]][0] = "addressed" if addressed else "open"
        elif e["type"] == "proposal":
            decided = any(d["topic"] == e["topic"] or d.get("refers_to") == e["event_id"] for d in later)
            result[e["event_id"]][0] = "decided" if decided else "open"

    return {k: (v[0], v[1]) for k, v in result.items()}


def load(conn: sqlite3.Connection, team: str, *, before_letter: str | None = None,
         upto_letter: str | None = None) -> list[dict]:
    """A team's events with statuses computed for the visible meetings only."""
    sql, params = "SELECT * FROM events WHERE team = ?", [team]
    if before_letter:
        sql += " AND letter < ?"
        params.append(before_letter)
    if upto_letter:
        sql += " AND letter <= ?"
        params.append(upto_letter)
    events = [dict(r) for r in conn.execute(sql + " ORDER BY letter, turn_idx, event_id", params)]
    statuses = compute(events)
    for e in events:
        e["status"], e["superseded_by"] = statuses[e["event_id"]]
    return events


def recompute(conn: sqlite3.Connection, team: str) -> None:
    """Store the 'everything visible' statuses, used by the live question path."""
    for e in load(conn, team):
        conn.execute(
            "UPDATE events SET status = ?, superseded_by = ? WHERE event_id = ?",
            (e["status"], e["superseded_by"], e["event_id"]),
        )


def render(conn: sqlite3.Connection, team: str, **visible) -> str:
    """Compact text form of the ledger, one event per line, for a model to read."""
    lines = []
    events = load(conn, team, **visible)
    objections = [o for o in events if o["type"] == "objection"]
    for e in events:
        extra = []
        if e["type"] in ("decision", "number") and e.get("status") == "current":
            # The latest word, but someone objected after it and nothing later settled it: say so,
            # so an answer can report the disagreement instead of presenting it as settled (D-033).
            after = [o["event_id"] for o in objections if o["topic"] == e["topic"] and _key(o) > _key(e)]
            if after:
                extra.append(f"objected to afterwards: {', '.join(after[:3])}")
        if e.get("owner"):
            extra.append(f"owner {e['owner']}")
        if e.get("value"):
            extra.append(f"value {e['value']}")
        if e.get("refers_to"):
            extra.append(f"refers to {e['refers_to']}")
        if e.get("status"):
            extra.append(e["status"] + (f" by {e['superseded_by']}" if e.get("superseded_by") else ""))
        if e.get("flags"):  # audit findings (src/memory/audit.py): do not repeat these details as fact
            extra.append("UNVERIFIED: " + ", ".join(json.loads(e["flags"])))
        lines.append(
            f"{e['event_id']} | {e['type']} | {e['topic']} | Speaker {e.get('speaker')}: "
            f"{e['summary']}" + (f" [{'; '.join(extra)}]" if extra else "")
        )
    return "\n".join(lines)
