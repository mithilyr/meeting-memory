"""The memory store: one SQLite file. Plain code, no model.

Tables
  meetings   one row per meeting, with the content hash that makes ingestion incremental
  turns      every speaker turn, words exactly as transcribed
  turns_fts  full-text index over turns (BM25 keyword search)
  chunks     windows of consecutive turns, with an embedding for meaning-based search
  speakers   who holds which role, per meeting (from extraction)
  events     the ledger: decisions, proposals, actions, numbers, objections (from extraction)

Every query a caller makes is filtered by team first, so the work per question
stays the same size however many meetings are stored (D-006, D-008).
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

import numpy as np

from src.ingest.parse import Meeting, iter_meetings
from src.settings import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    meeting_id TEXT PRIMARY KEY, team TEXT NOT NULL, letter TEXT NOT NULL,
    content_hash TEXT NOT NULL, n_turns INTEGER NOT NULL,
    extracted_hash TEXT  -- content hash the ledger rows were built from; NULL = not extracted
);
CREATE INDEX IF NOT EXISTS meetings_team ON meetings(team);

CREATE TABLE IF NOT EXISTS turns (
    turn_id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL, team TEXT NOT NULL,
    letter TEXT NOT NULL, idx INTEGER NOT NULL, seconds INTEGER NOT NULL,
    speaker TEXT NOT NULL, text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_team ON turns(team, letter, idx);
CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
    text, content='turns', content_rowid='rowid', tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL, team TEXT NOT NULL,
    first_idx INTEGER NOT NULL, last_idx INTEGER NOT NULL, text TEXT NOT NULL,
    vector BLOB  -- float32, L2-normalised; NULL until embedded
);
CREATE INDEX IF NOT EXISTS chunks_team ON chunks(team);

CREATE TABLE IF NOT EXISTS speakers (
    meeting_id TEXT NOT NULL, speaker TEXT NOT NULL, role TEXT, name TEXT, turn_id TEXT,
    PRIMARY KEY (meeting_id, speaker)
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY, team TEXT NOT NULL, meeting_id TEXT NOT NULL,
    letter TEXT NOT NULL, turn_idx INTEGER NOT NULL,
    type TEXT NOT NULL, topic TEXT NOT NULL, summary TEXT NOT NULL,
    speaker TEXT, owner TEXT, value TEXT,
    turn_id TEXT NOT NULL, quote TEXT NOT NULL,
    refers_to TEXT,       -- event this one answers or revisits (model's link, checked by code)
    status TEXT,          -- code-computed: current | superseded | open | reported | (NULL)
    superseded_by TEXT    -- code-computed
);
CREATE INDEX IF NOT EXISTS events_team ON events(team, topic);
"""

#: Turns per chunk and step between chunk starts. Six turns is about one exchange
#: of views; overlapping by three keeps an exchange whole in at least one chunk.
CHUNK_TURNS = 6
CHUNK_STEP = 3


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    if "flags" not in {r["name"] for r in conn.execute("PRAGMA table_info(events)")}:
        conn.execute("ALTER TABLE events ADD COLUMN flags TEXT")  # audit findings, JSON list (D-032)
    return conn


def _delete_meeting(conn: sqlite3.Connection, meeting_id: str) -> None:
    rows = conn.execute("SELECT rowid, text FROM turns WHERE meeting_id = ?", (meeting_id,))
    for rowid, text in rows.fetchall():
        conn.execute("INSERT INTO turns_fts(turns_fts, rowid, text) VALUES('delete', ?, ?)", (rowid, text))
    for table in ("turns", "chunks", "speakers", "events"):
        conn.execute(f"DELETE FROM {table} WHERE meeting_id = ?", (meeting_id,))
    conn.execute("DELETE FROM meetings WHERE meeting_id = ?", (meeting_id,))


def store_meeting(conn: sqlite3.Connection, meeting: Meeting) -> None:
    _delete_meeting(conn, meeting.meeting_id)
    conn.execute(
        "INSERT INTO meetings VALUES (?, ?, ?, ?, ?, NULL)",
        (meeting.meeting_id, meeting.team, meeting.letter, meeting.content_hash, len(meeting.turns)),
    )
    for t in meeting.turns:
        cur = conn.execute(
            "INSERT INTO turns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (t.turn_id, t.meeting_id, t.team, t.letter, t.turn_index, t.seconds, t.speaker, t.text),
        )
        conn.execute("INSERT INTO turns_fts(rowid, text) VALUES (?, ?)", (cur.lastrowid, t.text))
    turns = meeting.turns
    for start in range(0, max(len(turns) - CHUNK_TURNS, 0) + 1, CHUNK_STEP):
        window = turns[start : start + CHUNK_TURNS]
        text = "\n".join(f"{t.speaker}: {t.text}" for t in window)
        conn.execute(
            "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, NULL)",
            (f"{meeting.meeting_id}~{start:04d}", meeting.meeting_id, meeting.team,
             window[0].turn_index, window[-1].turn_index, text),
        )


def ingest(conn: sqlite3.Connection) -> dict:
    """Store every new or changed meeting. Unchanged meetings cost nothing."""
    known = dict(conn.execute("SELECT meeting_id, content_hash FROM meetings").fetchall())
    stats = {"new": 0, "changed": 0, "unchanged": 0}
    for meeting in iter_meetings():
        previous = known.get(meeting.meeting_id)
        if previous == meeting.content_hash:
            stats["unchanged"] += 1
            continue
        stats["changed" if previous else "new"] += 1
        store_meeting(conn, meeting)
    conn.commit()
    return stats


def embed_missing(conn: sqlite3.Connection, batch: int = 128) -> int:
    """Embed chunks that have no vector yet."""
    from src.clients.voyage import embed

    rows = conn.execute("SELECT chunk_id, text FROM chunks WHERE vector IS NULL").fetchall()
    for start in range(0, len(rows), batch):
        part = rows[start : start + batch]
        vectors = embed([r["text"] for r in part], input_type="document")
        for row, vector in zip(part, vectors):
            v = np.asarray(vector, dtype=np.float32)
            v /= np.linalg.norm(v) or 1.0
            conn.execute("UPDATE chunks SET vector = ? WHERE chunk_id = ?", (v.tobytes(), row["chunk_id"]))
        conn.commit()
        print(f"  embedded {min(start + batch, len(rows))}/{len(rows)}", end="\r")
    print()
    return len(rows)


EVENT_VECTORS = """CREATE TABLE IF NOT EXISTS event_vectors (
    event_id TEXT PRIMARY KEY, text_hash TEXT NOT NULL, vector BLOB NOT NULL)"""


def event_text(e: sqlite3.Row) -> str:
    return f"{e['topic'].replace('_', ' ')}: {e['summary']}"


def embed_events(conn: sqlite3.Connection, batch: int = 128) -> int:
    """Embed each ledger event (topic + summary), so the ledger can be ranked by meaning when it is
    too long for one prompt (F-008: "microphone" is part of the "interface", but shares no word with it).
    Only new or changed events are embedded; re-running costs nothing."""
    import hashlib

    from src.clients.voyage import embed

    conn.execute(EVENT_VECTORS)
    stored = dict(conn.execute("SELECT event_id, text_hash FROM event_vectors").fetchall())
    todo = []
    for e in conn.execute("SELECT event_id, topic, summary FROM events").fetchall():
        text = event_text(e)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        if stored.get(e["event_id"]) != digest:
            todo.append((e["event_id"], digest, text))
    for start in range(0, len(todo), batch):
        part = todo[start : start + batch]
        for (event_id, digest, _), vector in zip(part, embed([t for _, _, t in part], input_type="document")):
            v = np.asarray(vector, dtype=np.float32)
            v /= np.linalg.norm(v) or 1.0
            conn.execute("INSERT OR REPLACE INTO event_vectors VALUES (?, ?, ?)", (event_id, digest, v.tobytes()))
        conn.commit()
    return len(todo)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or update the memory store.")
    parser.add_argument("command", choices=["ingest", "embed", "stats"])
    args = parser.parse_args(argv)
    conn = connect()
    started = time.time()
    if args.command == "ingest":
        print(ingest(conn))
    elif args.command == "embed":
        print(f"embedded {embed_missing(conn)} chunks, {embed_events(conn)} ledger events")
    for table in ("meetings", "turns", "chunks", "events"):
        print(f"{table}: {conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]}")
    extracted = conn.execute("SELECT COUNT(*) FROM meetings WHERE extracted_hash = content_hash").fetchone()[0]
    print(f"meetings extracted: {extracted}")
    print(f"took {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
