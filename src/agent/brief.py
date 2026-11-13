"""Pre-meeting brief. Code picks and groups the facts; the model only writes them up.

  1. Cutoff (code)    only meetings before the one being prepared for (TS3012: a-c, D-004)
  2. Group (code)     current decisions and figures, what changed, open actions, open objections
  3. Write (model)    turns each group into short points, each tied to ledger event ids
  4. Cite (code)      every event id becomes "meeting: exact quote", taken from the ledger,
                      where it was verified at ingest. A point with no valid id is dropped.
"""

from __future__ import annotations

import argparse
import json
import sqlite3

from src.agent import retrieve
from src.clients.llm import complete, parse_json
from src.memory import ledger
from src.memory.store import connect

SECTIONS = [
    ("decided", "What has been decided (current)"),
    ("changed", "What changed along the way"),
    ("actions", "Open actions and who owns them"),
    ("disagreements", "Disagreements still open"),
]

PROMPT = """Write the brief team {team} reads before their next meeting (meeting {next_letter}).
It covers meetings {first_letter} to {last_letter} only.

Below are the facts, already grouped by code. Each line starts with a ledger event id.
For each section, write 3 to 7 short points in plain English. Merge related events into one point.
Name people by speaker letter and role (roles are under SPEAKERS). Mention the meeting where it matters.
Every point must list the event ids it is based on (1 to 2 ids). Use only ids from the lines below.

Reply with JSON only:
{{"decided": [{{"text": "...", "events": ["id", ...]}}], "changed": [...], "actions": [...], "disagreements": [...]}}

SPEAKERS:
{speakers}

{groups}"""


def group_events(events: list[dict]) -> dict[str, list[dict]]:
    by_id = {e["event_id"]: e for e in events}
    groups: dict[str, list[dict]] = {key: [] for key, _ in SECTIONS}
    for e in events:
        if e["type"] in ("decision", "number") and e["status"] == "current":
            groups["decided"].append(e)
        elif e["status"] == "superseded":
            groups["changed"].append(e | {"replaced_by": by_id.get(e["superseded_by"], {}).get("summary")})
        elif e["type"] == "action_item" and e["status"] == "open":
            groups["actions"].append(e)
        elif e["type"] in ("objection", "proposal") and e["status"] == "open":
            groups["disagreements"].append(e)
    return groups


def _line(e: dict) -> str:
    extra = f" -> REPLACED BY: {e['replaced_by']}" if e.get("replaced_by") else ""
    owner = f" (owner: Speaker {e['owner']})" if e.get("owner") else ""
    return f"{e['event_id']} [meeting {e['letter']}, {e['type']}, {e['topic']}]{owner}: {e['summary']}{extra}"


def write_brief(team: str, *, conn: sqlite3.Connection | None = None, upto_letter: str | None = None,
                local_only: bool = False) -> dict:
    conn = conn or connect()
    letters = [r[0] for r in conn.execute("SELECT letter FROM meetings WHERE team = ? ORDER BY letter", (team,))]
    if upto_letter is None:  # default: brief for the team's last meeting, from everything before it
        upto_letter = letters[-2] if len(letters) > 1 else letters[-1]
    next_letter = chr(ord(upto_letter) + 1)
    events = ledger.load(conn, team, upto_letter=upto_letter)
    by_id = {e["event_id"]: e for e in events}
    groups = group_events(events)
    groups_text = "\n\n".join(
        f"{title.upper()} ({key}):\n" + ("\n".join(_line(e) for e in groups[key]) or "(none found)")
        for key, title in SECTIONS
    )
    prompt = PROMPT.format(team=team, next_letter=next_letter, first_letter=letters[0], last_letter=upto_letter,
                           speakers=retrieve.speakers(conn, team, upto_letter), groups=groups_text)
    text, model = complete(prompt, local_only=local_only)
    try:
        drafted = parse_json(text)
    except (ValueError, json.JSONDecodeError):
        drafted = {key: [{"text": e["summary"], "events": [e["event_id"]]} for e in groups[key]] for key, _ in SECTIONS}
        model += " (unparseable; fell back to ledger summaries)"

    lines = [f"BRIEF FOR TEAM {team}, before meeting {next_letter}. Based on meetings "
             f"{letters[0]} to {upto_letter} only."]
    dropped = 0
    for key, title in SECTIONS:
        lines.append(f"\n{title.upper()}")
        points = drafted.get(key) or []
        kept = 0
        for p in points if isinstance(points, list) else []:
            ids = [i for i in (p.get("events") or []) if i in by_id][:2] if isinstance(p, dict) else []
            if not ids:
                dropped += 1
                continue
            cites = "; ".join(f'{by_id[i]["meeting_id"]}: "{by_id[i]["quote"]}"' for i in ids)
            lines.append(f"- {str(p.get('text', '')).strip()} [{cites}]")
            kept += 1
        if kept == 0:
            lines.append("- None recorded.")
    return {"team": team, "upto_letter": upto_letter, "model": model, "dropped_points": dropped,
            "brief": "\n".join(lines)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a pre-meeting brief.")
    parser.add_argument("team")
    parser.add_argument("--upto", help="last meeting letter to include (default: all but the last)")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args(argv)
    result = write_brief(args.team, upto_letter=args.upto, local_only=args.local)
    print(result["brief"])
    print(f"\n(model: {result['model']}, points dropped for missing evidence: {result['dropped_points']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
