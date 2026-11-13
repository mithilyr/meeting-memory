"""Readable project names, so people pick "Fruit-shaped kinetic remote" instead of "ES2015" (D-025).

The transcripts carry only a team id. A name is written by the model from the team's current
decisions, stored with a hash of those decisions, and rewritten only when they change. The page
always shows the id next to the name: the name is a summary, the id is the fact.

    python -m src.memory.names          name every team that has no name or a stale one
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from src.clients.llm import complete, parse_json
from src.memory import ledger
from src.memory.store import connect

SCHEMA = "CREATE TABLE IF NOT EXISTS projects (team TEXT PRIMARY KEY, name TEXT NOT NULL, source_hash TEXT NOT NULL)"
MAX_CHARS = 40

PROMPT = """Below are the final decisions of a product design team. Give the product a short name
a colleague would recognise it by: 2 to 5 words, describing what makes it distinct (shape, power,
materials, features). No team ids, no quotes, no brand names.

Reply with JSON only: {{"name": "..."}}
{taken}
DECISIONS:
{decisions}"""


def _decisions(conn: sqlite3.Connection, team: str) -> str:
    current = [e for e in ledger.load(conn, team)
               if e["type"] in ("decision", "number") and e["status"] == "current"]
    return "\n".join(f"- {e['topic'].replace('_', ' ')}: {e['summary']}" for e in current)[:4000]


def _tidy(name: str) -> str:
    """Sentence case, so the list reads evenly; acronyms (LCD, TV) stay as they are."""
    name = name.strip().strip('"').rstrip(".").translate({0x2010: "-", 0x2011: "-", 0x2013: "-", 0x2014: "-"})
    words = [w if w.isupper() and len(w) > 1 else w.lower() for w in name.split()]
    return " ".join(words)[:1].upper() + " ".join(words)[1:]


def _key(name: str) -> frozenset[str]:
    """Names with the same words in any order ("curved kinetic rubber", "kinetic curve rubber") clash."""
    return frozenset(w[:5] for w in name.lower().replace("-", " ").split())


def name_team(conn: sqlite3.Connection, team: str) -> str | None:
    """Write or refresh one team's name. Returns the name, or None when there is nothing to name yet."""
    decisions = _decisions(conn, team)
    if not decisions:
        return None
    source_hash = hashlib.sha256(decisions.encode("utf-8")).hexdigest()[:16]
    row = conn.execute("SELECT name, source_hash FROM projects WHERE team = ?", (team,)).fetchone()
    if row and row["source_hash"] == source_hash:
        return row["name"]
    taken = {r["name"] for r in conn.execute("SELECT name FROM projects WHERE team != ?", (team,))}
    text, _ = complete(PROMPT.format(decisions=decisions, taken=""))
    name = _tidy(str(parse_json(text).get("name", "")))
    if _key(name) in {_key(n) for n in taken}:  # too close to another team's name: ask once more
        text, _ = complete(PROMPT.format(decisions=decisions, taken="\nThese names are taken; yours must differ "
                                         "by at least one distinctive word: " + "; ".join(sorted(taken)) + "\n"))
        name = _tidy(str(parse_json(text).get("name", "")))
    if not name or len(name) > MAX_CHARS or team in name:
        return row["name"] if row else None  # a bad reply keeps the old name; the id still works
    conn.execute("INSERT OR REPLACE INTO projects VALUES (?, ?, ?)", (team, name, source_hash))
    conn.commit()
    return name


def name_all(conn: sqlite3.Connection | None = None) -> dict[str, str | None]:
    conn = conn or connect()
    conn.execute(SCHEMA)
    out = {}
    for (team,) in conn.execute("SELECT DISTINCT team FROM meetings ORDER BY team").fetchall():
        try:
            out[team] = name_team(conn, team)
        except Exception as error:  # noqa: BLE001 - one team failing must not stop the rest
            out[team] = f"(failed: {str(error)[:80]})"
    return out


def names(conn: sqlite3.Connection) -> dict[str, str]:
    conn.execute(SCHEMA)
    return {r["team"]: r["name"] for r in conn.execute("SELECT team, name FROM projects")}


if __name__ == "__main__":
    print(json.dumps(name_all(), indent=2))
