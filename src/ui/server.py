"""Local web page for the demo. Python stdlib only (no framework, D-006).

    python -m src.ui.server        then open http://localhost:8765

Endpoints (JSON):
  GET  /api/teams                      team ids with meeting count and extraction progress
  GET  /api/ledger?team=TS3012         the team's events with statuses, grouped by meeting
  GET  /api/turns?meeting=X&idx=N      the turn and its neighbours, for "show in transcript"
  GET  /api/health                     which model backends this machine can use
  POST /api/ask     {"question", "team"} the question agent (answer.py)
  POST /api/brief   {"team", "upto"}     the brief writer (brief.py)
  POST /api/upload  {"filename", "content"}  save a transcript to inbox/
  POST /api/refresh                     ingest + embed + extract anything new (refresh.py)
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.agent.answer import answer
from src.agent.brief import write_brief
from src.ingest.parse import MEETING_ID, TURN_HEADER
from src.memory import ledger
from src.memory.refresh import refresh
from src.memory.store import connect
from src.settings import get_settings

PAGE = Path(__file__).resolve().parent / "index.html"
PORT = 8765
_local = threading.local()
_refresh_lock = threading.Lock()  # one refresh at a time


def db() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        _local.conn = connect()
    return _local.conn


def teams() -> list[dict]:
    rows = db().execute(
        "SELECT team, COUNT(*) n, SUM(extracted_hash = content_hash) done FROM meetings GROUP BY team ORDER BY team"
    ).fetchall()
    return [{"team": r["team"], "meetings": r["n"], "extracted": r["done"] or 0} for r in rows]


def team_ledger(team: str) -> dict:
    events = ledger.load(db(), team)
    letters = [r[0] for r in db().execute("SELECT letter FROM meetings WHERE team = ? ORDER BY letter", (team,))]
    roles = {}
    for r in db().execute("SELECT s.speaker, s.role FROM speakers s JOIN meetings m USING (meeting_id) "
                          "WHERE m.team = ? AND s.role IS NOT NULL ORDER BY m.letter", (team,)):
        roles.setdefault(r["speaker"], r["role"])
    return {"team": team, "letters": letters, "roles": roles,
            "events": [{k: e[k] for k in ("event_id", "letter", "meeting_id", "turn_idx", "type", "topic", "summary",
                                          "speaker", "owner", "value", "quote", "status", "superseded_by")}
                       for e in events]}


def turns_around(meeting_id: str, idx: int, quote: str | None = None) -> dict:
    if idx < 0 and quote:  # locate a quote cited without a turn number
        from src.ingest.verify import normalise
        for r in db().execute("SELECT idx, text FROM turns WHERE meeting_id = ?", (meeting_id,)):
            if normalise(quote) in normalise(r["text"]):
                idx = r["idx"]
                break
    rows = db().execute("SELECT idx, speaker, text FROM turns WHERE meeting_id = ? AND idx BETWEEN ? AND ? ORDER BY idx",
                        (meeting_id, idx - 4, idx + 4)).fetchall()
    return {"meeting_id": meeting_id, "focus": idx, "turns": [dict(r) for r in rows]}


def health() -> dict:
    """Which hosted services this server has keys for. The page shows it on Add meetings."""
    settings = get_settings()
    return {"free_api": bool(settings.openrouter_api_key), "groq_api": bool(os.getenv("GROQ_API_KEY")),
            "embeddings": bool(settings.voyage_api_key), "anthropic_api": bool(os.getenv("ANTHROPIC_API_KEY"))}


def save_upload(filename: str, content: str) -> dict:
    """Accept a transcript into inbox/. Code checks the name and format before anything runs."""
    stem = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].removesuffix(".txt")
    if not MEETING_ID.match(stem):
        raise ValueError("File name must be a meeting id: team id + meeting letter, e.g. TS3013a.txt")
    if not any(TURN_HEADER.match(line) for line in content.splitlines()):
        raise ValueError("No turns found. Each turn needs a line like '00:01:06 Speaker B' followed by the words.")
    if (get_settings().transcripts_dir / f"{stem}.txt").exists():
        raise ValueError(f"{stem} is already in the corpus.")
    inbox = get_settings().inbox_dir
    inbox.mkdir(exist_ok=True)
    (inbox / f"{stem}.txt").write_text(content, encoding="utf-8")
    return {"saved": f"inbox/{stem}.txt"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, kind: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, fmt, *args) -> None:  # keep the terminal quiet during a demo
        pass

    def do_GET(self) -> None:
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ("/", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html")
            elif url.path == "/api/health":
                self._json(health())
            elif url.path == "/api/teams":
                self._json(teams())
            elif url.path == "/api/ledger":
                self._json(team_ledger(q["team"]))
            elif url.path == "/api/turns":
                self._json(turns_around(q["meeting"], int(q.get("idx", -1)), q.get("quote")))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as error:  # noqa: BLE001 - a demo page must report, not crash
            self._json({"error": str(error)}, 500)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        try:
            if self.path == "/api/ask":
                self._json(answer(body["question"], conn=db(), team=body.get("team") or None))
            elif self.path == "/api/brief":
                self._json(write_brief(body["team"], conn=db(), upto_letter=body.get("upto") or None))
            elif self.path == "/api/upload":
                self._json(save_upload(body["filename"], body["content"]))
            elif self.path == "/api/refresh":
                with _refresh_lock:
                    self._json(refresh(db()))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as error:  # noqa: BLE001
            self._json({"error": str(error)}, 500)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Meeting Memory running at http://localhost:{PORT}  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
