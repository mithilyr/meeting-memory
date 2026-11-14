"""Bring the memory up to date with whatever transcripts exist. One command, no human steps.

    python -m src.memory.refresh

  1. Ingest (code)      new or changed files in the data folder and inbox/; unchanged ones skipped
  2. Embed (Voyage)     vectors for new chunks
  3. Extract (model)    every meeting without ledger rows, team by team in meeting order.
                        Backend: Claude Haiku 5.5 if ANTHROPIC_API_KEY is set (tier B), otherwise
                        the free OpenRouter models.
  4. Validate (code)    same validator as always; a rejected meeting is reported and left pending.
                        Then the truth audit (src/memory/audit.py) flags figures nobody said, wrong units,
                        wrong speakers and backwards links, exactly as for the original corpus.
  5. Name (model)       readable project names, rewritten only for teams whose decisions changed
  6. Profile (Voyage)   one embedding per project, used to suggest projects for questions that name none

Before step 1, files that read like instructions to a model are held for review (src/ingest/screen.py).
Run it from the UI's Refresh button, a scheduled task, or a folder watcher.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time

from src.clients.llm import complete, parse_json
from src.ingest import extract, screen
from src.agent import route
from src.memory import names
from src.memory.store import connect, embed_missing, ingest


def pending_meetings(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT meeting_id FROM meetings WHERE extracted_hash IS NULL OR extracted_hash != content_hash "
        "ORDER BY team, letter")]


def _extract_free(conn: sqlite3.Connection, meeting_id: str) -> str:
    text, model = complete(extract.build_prompt(conn, meeting_id))
    data = parse_json(text)
    path = extract.output_path(meeting_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return model


def refresh(conn: sqlite3.Connection | None = None) -> dict:
    conn = conn or connect()
    started = time.time()
    report: dict = {"held": screen.screen_inbox(conn)}  # files dropped straight into inbox/ get screened too
    report["ingest"] = ingest(conn)
    report["embedded_chunks"] = embed_missing(conn)
    use_api = bool(os.getenv("ANTHROPIC_API_KEY"))
    report["backend"] = "claude-haiku-5-5" if use_api else "free OpenRouter models"
    done, failed, new_ids = [], [], []
    for meeting_id in pending_meetings(conn):
        team = conn.execute("SELECT team FROM meetings WHERE meeting_id = ?", (meeting_id,)).fetchone()[0]
        if extract.next_meeting(conn, team) != meeting_id:
            continue  # an earlier meeting of this team failed; keep the order intact
        try:
            if use_api:
                extract.run_api(conn, team)
                done.append(f"{team} (all pending)")
                continue
            model = _extract_free(conn, meeting_id)
            count, _ = extract.import_output(conn, meeting_id)
            done.append(f"{meeting_id}: {count} events via {model}")
            new_ids.append(meeting_id)
        except Exception as error:  # noqa: BLE001 - report and move on; the meeting stays pending
            failed.append(f"{meeting_id}: {str(error).splitlines()[0][:200]}")
    # every new meeting went through the same truth checks as the corpus (audit runs on import, D-032)
    flagged = conn.execute(f"SELECT event_id, flags FROM events WHERE flags IS NOT NULL AND meeting_id IN "
                           f"({','.join('?' * len(new_ids))})", new_ids).fetchall() if new_ids else []
    report["unverified"] = [f"{r['event_id']}: {', '.join(json.loads(r['flags']))}" for r in flagged]
    report["names"] = names.name_all(conn)
    report["profiles_embedded"] = route.update_profiles(conn)  # for questions that name no project
    report.update(extracted=done, failed=failed, still_pending=len(pending_meetings(conn)),
                  seconds=round(time.time() - started, 1))
    return report


if __name__ == "__main__":
    print(json.dumps(refresh(), indent=2))
