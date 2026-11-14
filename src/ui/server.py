"""Local web page for the demo. Python stdlib only (no framework, D-006).

    python -m src.ui.server        then open http://localhost:8765

Endpoints (JSON):
  GET  /api/teams                      team ids with meeting count and extraction progress
  GET  /api/ledger?team=TS3012         the team's events with statuses, grouped by meeting
  GET  /api/turns?meeting=X&idx=N      the turn and its neighbours, for "show in transcript"
  GET  /api/transcript?meeting=X       every turn of the meeting, for "whole meeting"
  GET  /api/raw?meeting=X              the original .txt file, unchanged, as a download
  GET  /api/suggest?q=...               projects whose meetings discuss the words (picker fallback, no model)
  GET  /api/held                       uploads held for review because they read like instructions to a model
  GET  /api/health                     which model backends this machine can use
  POST /api/ask     {"question", "team"} the question agent (answer.py), streamed as one JSON line per
                                       step so the page can show progress; the last line holds the answer
  POST /api/brief   {"team", "upto"}     the brief writer (brief.py)
  POST /api/upload  {"filename", "content"}  save a transcript to inbox/, or inbox/held/ if screening flags it
  POST /api/held    {"meeting", "action"}    approve (move into inbox/) or discard a held upload
  POST /api/refresh                     ingest + embed + extract anything new (refresh.py)
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.agent.answer import answer
from src.agent.brief import write_brief
from src.agent.route import suggest
from src.ingest import screen
from src.ingest.parse import MEETING_ID, TURN_HEADER
from src.memory import ledger, names
from src.memory.refresh import refresh
from src.memory.store import connect
from src.settings import get_settings

PAGE = Path(__file__).resolve().parent / "index.html"
PORT = int(os.getenv("PORT", "8765"))
HOST = os.getenv("HOST", "127.0.0.1")  # the hosted demo sets 0.0.0.0
#: Hosted demo (D-037): no uploads, refresh or review, so visitors can't add meetings or spend
#: extraction quota. Questions and briefs are limited per visitor to protect the free model quota.
READ_ONLY = os.getenv("READ_ONLY") == "1"
MODEL_CALLS_PER_HOUR = int(os.getenv("MODEL_CALLS_PER_HOUR", "20"))
_visits: dict[str, list[float]] = {}
_visits_lock = threading.Lock()
_local = threading.local()
_refresh_lock = threading.Lock()  # one refresh at a time


def db() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        _local.conn = connect()
    return _local.conn


def teams() -> list[dict]:
    """Every team with its name, meetings and last activity, most recently active first.
    Activity is when the team's newest transcript file arrived: the corpus has no meeting dates."""
    rows = db().execute(
        "SELECT team, COUNT(*) n, SUM(extracted_hash = content_hash) done, MAX(letter) last "
        "FROM meetings GROUP BY team"
    ).fetchall()
    named = names.names(db())
    out = []
    for r in rows:
        try:
            active = raw_file(f"{r['team']}{r['last']}").stat().st_mtime
        except (FileNotFoundError, ValueError):
            active = 0
        out.append({"team": r["team"], "name": named.get(r["team"]), "meetings": r["n"],
                    "extracted": r["done"] or 0, "last": r["last"], "active": active})
    return sorted(out, key=lambda t: (-t["active"], t["name"] or t["team"]))


def cite_context(citations: list[dict]) -> list[dict]:
    """Add who said each quote, their role, the turn before it, and which meeting of the series it is,
    so a short quote like "Okay we put it on top" can be read in context."""
    from src.ingest.verify import normalise

    out = []
    for c in citations:
        c = dict(c)
        team, letter = c["meeting_id"][:-1], c["meeting_id"][-1]
        rows = db().execute("SELECT idx, speaker, text FROM turns WHERE meeting_id = ? ORDER BY idx",
                            (c["meeting_id"],)).fetchall()
        hit = next((r for r in rows if normalise(c["quote"]) in normalise(r["text"])), None)
        if hit:
            role = db().execute("SELECT s.role FROM speakers s JOIN meetings m USING (meeting_id) "
                                "WHERE m.team = ? AND s.speaker = ? AND s.role IS NOT NULL ORDER BY m.letter LIMIT 1",
                                (team, hit["speaker"])).fetchone()
            before = next((r for r in reversed(rows) if r["idx"] < hit["idx"] and len(r["text"]) > 15), None)
            c.update(idx=hit["idx"], speaker=hit["speaker"], role=role["role"] if role else None,
                     before={"speaker": before["speaker"], "text": before["text"][:240]} if before else None)
        last = db().execute("SELECT MAX(letter) FROM meetings WHERE team = ?", (team,)).fetchone()[0] or letter
        c.update(number=ord(letter) - 96, of=ord(last) - 96)
        out.append(c)
    return out


def team_ledger(team: str) -> dict:
    events = ledger.load(db(), team)
    letters = [r[0] for r in db().execute("SELECT letter FROM meetings WHERE team = ? ORDER BY letter", (team,))]
    roles = {}
    for r in db().execute("SELECT s.speaker, s.role FROM speakers s JOIN meetings m USING (meeting_id) "
                          "WHERE m.team = ? AND s.role IS NOT NULL ORDER BY m.letter", (team,)):
        roles.setdefault(r["speaker"], r["role"])
    return {"team": team, "letters": letters, "roles": roles,
            "events": [{k: e[k] for k in ("event_id", "letter", "meeting_id", "turn_idx", "type", "topic", "summary",
                                          "speaker", "owner", "value", "quote", "status", "superseded_by", "flags")}
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


def transcript(meeting_id: str) -> dict:
    rows = db().execute("SELECT idx, speaker, text FROM turns WHERE meeting_id = ? ORDER BY idx", (meeting_id,)).fetchall()
    return {"meeting_id": meeting_id, "turns": [dict(r) for r in rows]}


def raw_file(meeting_id: str) -> Path:
    """The original transcript as it arrived. The id is checked first, so no other path can be read."""
    if not MEETING_ID.match(meeting_id):
        raise ValueError("not a meeting id")
    settings = get_settings()
    for folder in (settings.transcripts_dir, settings.inbox_dir):
        if (folder / f"{meeting_id}.txt").is_file():
            return folder / f"{meeting_id}.txt"
    raise FileNotFoundError(f"{meeting_id}.txt not found")


def health() -> dict:
    """Which hosted services this server has keys for. The page shows it on Add meetings."""
    settings = get_settings()
    return {"free_api": bool(settings.openrouter_api_key), "groq_api": bool(os.getenv("GROQ_API_KEY")),
            "embeddings": bool(settings.voyage_api_key), "anthropic_api": bool(os.getenv("ANTHROPIC_API_KEY")),
            "read_only": READ_ONLY}


def allow(visitor: str) -> bool:
    """At most MODEL_CALLS_PER_HOUR questions or briefs per visitor in the hosted demo."""
    if not READ_ONLY:
        return True
    now = time.time()
    with _visits_lock:
        recent = [t for t in _visits.get(visitor, []) if now - t < 3600]
        if len(recent) >= MODEL_CALLS_PER_HOUR:
            _visits[visitor] = recent
            return False
        _visits[visitor] = recent + [now]
        return True


def save_upload(filename: str, content: str) -> dict:
    """Accept a transcript into inbox/. Code checks the name and format before anything runs."""
    stem = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].removesuffix(".txt")
    if not MEETING_ID.match(stem):
        raise ValueError("File name must be a meeting id: team id + meeting letter, e.g. TS3013a.txt")
    if not any(TURN_HEADER.match(line) for line in content.splitlines()):
        raise ValueError("No turns found. Each turn needs a line like '00:01:06 Speaker B' followed by the words.")
    if (get_settings().transcripts_dir / f"{stem}.txt").exists():
        raise ValueError(f"{stem} is already in the corpus.")
    if len(content.encode("utf-8")) > screen.MAX_UPLOAD_BYTES:
        raise ValueError(f"{stem} is larger than {screen.MAX_UPLOAD_BYTES // 1_000_000} MB; a transcript is usually under 100 KB.")
    copy_of = screen.duplicate_of(db(), content)
    if copy_of and copy_of != stem:
        raise ValueError(f"{stem} repeats meeting {copy_of}, which is already in memory.")
    flagged = screen.flags(content)
    folder = screen.held_dir() if flagged and not screen.is_approved(content) else get_settings().inbox_dir
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{stem}.txt").write_text(content, encoding="utf-8")
    if folder == screen.held_dir():
        return {"held": stem, "flags": flagged}
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

    def _stream_answer(self, question: str, team: str | None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def line(data: dict) -> None:
            self.wfile.write((json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

        try:
            result = answer(question, conn=db(), team=team, on_step=line)
            result["citations"] = cite_context(result["citations"])
            line({"step": "done", "result": result})
        except Exception as error:  # noqa: BLE001 - headers are sent; report the error as the last line
            line({"step": "error", "error": str(error)})

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
            elif url.path == "/api/held":
                self._json({"held": screen.held(db())})
            elif url.path == "/api/suggest":
                self._json(suggest(q.get("q", "")[:300], conn=db(), k=5))
            elif url.path == "/api/transcript":
                self._json(transcript(q["meeting"]))
            elif url.path == "/api/raw":
                path = raw_file(q["meeting"])
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
                body = path.read_bytes()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json({"error": "not found"}, 404)
        except Exception as error:  # noqa: BLE001 - a demo page must report, not crash
            self._json({"error": str(error)}, 500)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        if length > screen.MAX_UPLOAD_BYTES * 2:  # JSON escaping can double a file's size
            self._json({"error": f"Request too large (limit {screen.MAX_UPLOAD_BYTES // 1_000_000} MB per file)."}, 413)
            return
        body = json.loads(self.rfile.read(length) or b"{}")
        if READ_ONLY and self.path in ("/api/upload", "/api/refresh", "/api/held"):
            self._json({"error": "This is a read-only demo. To add meetings, run it locally (see the README)."}, 403)
            return
        visitor = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        if self.path in ("/api/ask", "/api/brief") and not allow(visitor):
            self._json({"error": f"Demo limit: {MODEL_CALLS_PER_HOUR} questions or briefs an hour per visitor, "
                                 "to keep the free model quota for everyone. Please try again later."}, 429)
            return
        try:
            if self.path == "/api/ask":
                self._stream_answer(body["question"], body.get("team") or None)
            elif self.path == "/api/held":
                if body.get("action") not in ("approve", "discard") or not MEETING_ID.match(body.get("meeting", "")):
                    raise ValueError("action must be approve or discard, with a meeting id")
                (screen.approve if body["action"] == "approve" else screen.discard)(body["meeting"])
                self._json({"held": screen.held(db())})
            elif self.path == "/api/brief":
                self._json(write_brief(body["team"], conn=db(), upto_letter=body.get("upto") or None))
            elif self.path == "/api/upload":
                self._json(save_upload(body["filename"], body["content"]))
            elif self.path == "/api/refresh":
                with _refresh_lock:
                    self._json(refresh(db()))
            else:
                self._json({"error": "not found"}, 404)
        except ValueError as error:  # the request was wrong, not the server
            self._json({"error": str(error)}, 400)
        except Exception as error:  # noqa: BLE001
            self._json({"error": str(error)}, 500)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Meeting Memory running at http://localhost:{PORT}  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
