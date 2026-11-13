"""Evidence fetching. Plain code, no model (except the embedding of the query).

Everything is filtered by team before searching, so a question costs the same at
138 meetings or 10,000. `upto_letter` hides later meetings (the brief's cutoff).
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict

import numpy as np

from src.memory import ledger

TEAM_PATTERN = re.compile(r"\b([A-Z]{2}\d{4})\b")
STOPWORDS = set(
    """a an the and or but of to in on at for with by from as is are was were be been being do did does
    what which who whom whose when where why how that this these those it its they them their team teams
    had has have would could should will can into than then there about after before first later final
    end did make made one two any some more most other same such only also just very their meeting meetings""".split()
)


def team_from_question(question: str) -> str | None:
    match = TEAM_PATTERN.search(question)
    return match.group(1) if match else None


def _fts_query(text: str) -> str:
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9]+", text.lower()) if w not in STOPWORDS]
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words))


def keyword_turns(conn: sqlite3.Connection, team: str, query: str, k: int = 12,
                  upto_letter: str | None = None) -> list[sqlite3.Row]:
    fts = _fts_query(query)
    if not fts:
        return []
    sql = (
        "SELECT t.*, bm25(turns_fts) AS score FROM turns_fts JOIN turns t ON t.rowid = turns_fts.rowid "
        "WHERE turns_fts MATCH ? AND t.team = ? AND length(t.text) > 40"
    )
    params: list = [fts, team]
    if upto_letter:
        sql += " AND t.letter <= ?"
        params.append(upto_letter)
    return conn.execute(sql + " ORDER BY score LIMIT ?", (*params, k)).fetchall()


def vector_chunks(conn: sqlite3.Connection, team: str, query: str, k: int = 6,
                  upto_letter: str | None = None) -> list[sqlite3.Row]:
    from src.clients.voyage import embed

    rows = conn.execute(
        "SELECT c.*, m.letter FROM chunks c JOIN meetings m USING (meeting_id) "
        "WHERE c.team = ? AND c.vector IS NOT NULL" + (" AND m.letter <= ?" if upto_letter else ""),
        (team, upto_letter) if upto_letter else (team,),
    ).fetchall()
    if not rows:
        return []
    q = np.asarray(embed([query], input_type="query")[0], dtype=np.float32)
    q /= np.linalg.norm(q) or 1.0
    matrix = np.stack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows])
    order = np.argsort(-(matrix @ q))[:k]
    return [rows[i] for i in order]


def turns_in_range(conn: sqlite3.Connection, meeting_id: str, first: int, last: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM turns WHERE meeting_id = ? AND idx BETWEEN ? AND ? ORDER BY idx",
        (meeting_id, first, last),
    ).fetchall()


def speakers(conn: sqlite3.Connection, team: str, upto_letter: str | None = None) -> str:
    """Speaker letter -> role, and whether it holds across the team's meetings."""
    rows = conn.execute(
        "SELECT m.letter, s.speaker, s.role, s.name FROM speakers s JOIN meetings m USING (meeting_id) "
        "WHERE m.team = ?" + (" AND m.letter <= ?" if upto_letter else "") + " ORDER BY s.speaker, m.letter",
        (team, upto_letter) if upto_letter else (team,),
    ).fetchall()
    seen: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        label = " ".join(x for x in (r["role"], f"({r['name']})" if r["name"] else None) if x)
        seen[r["speaker"]].append(f"{label} [meeting {r['letter']}]")
    return "\n".join(f"Speaker {s}: " + "; ".join(v) for s, v in sorted(seen.items()))


def gather(conn: sqlite3.Connection, team: str, queries: list[str],
           upto_letter: str | None = None) -> dict[str, sqlite3.Row]:
    """Keyword + vector search for each query, merged into turn_id -> turn."""
    found: dict[str, sqlite3.Row] = {}
    for query in queries:
        for t in keyword_turns(conn, team, query, upto_letter=upto_letter):
            found.setdefault(t["turn_id"], t)
        for c in vector_chunks(conn, team, query, upto_letter=upto_letter):
            for t in turns_in_range(conn, c["meeting_id"], c["first_idx"], c["last_idx"]):
                if len(t["text"]) > 25:
                    found.setdefault(t["turn_id"], t)
    return found


#: Prompt budget, in characters (about 3.8 characters per token). Groq's free tier caps a request
#: at 8,000 tokens per minute and OpenRouter returned an empty reply on a 55K-character prompt, so
#: a question's prompt is held near 22K characters (about 6K tokens): ledger 11K, transcript turns 8K.
#: At company scale a project's ledger grows without limit; these caps keep a question's cost flat.
LEDGER_BUDGET = 11_000
TURNS_BUDGET = 8_000


def render_turns(turns: dict[str, sqlite3.Row], budget: int = TURNS_BUDGET) -> str:
    """Turns in meeting order; when over budget, the best-ranked ones are kept."""
    kept, size = [], 0
    for t in turns.values():  # insertion order = search rank order (gather keeps the first hit)
        line = f"[{t['turn_id']}] Speaker {t['speaker']}: {t['text'][:600]}"
        if size + len(line) > budget:
            continue
        kept.append((t["letter"], t["idx"], line))
        size += len(line) + 1
    return "\n".join(line for _, _, line in sorted(kept))


def _words(text: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in STOPWORDS}


def ledger_text(conn: sqlite3.Connection, team: str, upto_letter: str | None = None,
                query: str | None = None) -> str:
    """The team's ledger; over budget, only the topics that best match the query (code, no model)."""
    full = ledger.render(conn, team, upto_letter=upto_letter) if upto_letter else ledger.render(conn, team)
    if len(full) <= LEDGER_BUDGET or not query:
        return full
    wanted = _words(query)
    lines = full.split("\n")
    def score(line: str) -> int:
        parts = line.split(" | ")
        bonus = 1 if len(parts) > 1 and parts[1] in ("decision", "number") else 0
        return len(wanted & _words(line)) * 2 + bonus
    topic_of = lambda line: line.split(" | ")[2] if line.count(" | ") >= 3 else ""
    keep_topics, size = [], 0
    for line in sorted(lines, key=score, reverse=True):
        topic = topic_of(line)
        if topic in keep_topics:
            continue
        topic_size = sum(len(l) + 1 for l in lines if topic_of(l) == topic)
        if size + topic_size > LEDGER_BUDGET:
            continue
        keep_topics.append(topic)
        size += topic_size
    kept = [l for l in lines if topic_of(l) in keep_topics]
    return "\n".join(kept) + f"\n(ledger filtered to the {len(keep_topics)} most relevant topics, {len(kept)} of {len(lines)} events)"
