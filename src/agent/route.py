"""Which project does a question mean, when it names none? Code plus one embedding, no model call (D-029).

Each project gets a profile: its name and current decisions, embedded once by Voyage and refreshed
only when the decisions change. A question with no project ID is scored two ways:

  meaning   the question's embedding against every profile (one vector per project, so this stays
            fast at thousands of projects)
  keywords  SQLite full-text search over every turn; a project scores by its best few hits

  ledger    rare words of the question against the ledger's event sentences (weighted highest)

The three rankings are merged by reciprocal rank fusion and the top 3 are offered to the person,
each with the line that matched, so they choose. Nothing is answered on a guess.

    python -m src.agent.route "what is the backup energy source for the remote?"
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import defaultdict

import numpy as np

from src.agent import retrieve
from src.memory import ledger, names
from src.memory.store import connect

SCHEMA = "CREATE TABLE IF NOT EXISTS project_profiles (team TEXT PRIMARY KEY, source_hash TEXT NOT NULL, vector BLOB NOT NULL)"
RRF_K = 60  # standard reciprocal-rank-fusion constant: rank 1 scores 1/61, rank 10 scores 1/70
LEDGER_WEIGHT = 4.0


def _profile_text(conn: sqlite3.Connection, team: str, name: str | None) -> str:
    current = [e for e in ledger.load(conn, team) if e["status"] == "current"]
    lines = [f"{e['topic'].replace('_', ' ')}: {e['summary']}" for e in current]
    return f"{name or team}\n" + "\n".join(lines)[:6000]


def update_profiles(conn: sqlite3.Connection | None = None) -> int:
    """Embed the profile of every project whose decisions changed. Returns how many were embedded."""
    from src.clients.voyage import embed

    conn = conn or connect()
    conn.execute(SCHEMA)
    named = names.names(conn)
    stored = dict(conn.execute("SELECT team, source_hash FROM project_profiles").fetchall())
    todo = []
    for (team,) in conn.execute("SELECT DISTINCT team FROM meetings ORDER BY team").fetchall():
        text = _profile_text(conn, team, named.get(team))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        if stored.get(team) != digest:
            todo.append((team, digest, text))
    if todo:
        for (team, digest, _), vector in zip(todo, embed([t for _, _, t in todo], input_type="document")):
            v = np.asarray(vector, dtype=np.float32)
            v /= np.linalg.norm(v) or 1.0
            conn.execute("INSERT OR REPLACE INTO project_profiles VALUES (?, ?, ?)", (team, digest, v.tobytes()))
        conn.commit()
    return len(todo)


def _by_meaning(conn: sqlite3.Connection, question: str) -> list[str]:
    from src.clients.voyage import embed

    rows = conn.execute("SELECT team, vector FROM project_profiles").fetchall()
    if not rows:
        return []
    q = np.asarray(embed([question], input_type="query")[0], dtype=np.float32)
    q /= np.linalg.norm(q) or 1.0
    scores = np.stack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows]) @ q
    return [rows[i]["team"] for i in np.argsort(-scores)]


def _by_keywords(conn: sqlite3.Connection, question: str) -> tuple[list[str], dict[str, sqlite3.Row]]:
    """Projects ranked by their 3 best-matching turns. Also returns each project's best turn."""
    fts = retrieve._fts_query(question)
    if not fts:
        return [], {}
    hits = conn.execute(
        "SELECT t.*, bm25(turns_fts) AS score FROM turns_fts JOIN turns t ON t.rowid = turns_fts.rowid "
        "WHERE turns_fts MATCH ? AND length(t.text) > 40 ORDER BY score LIMIT 400", (fts,)).fetchall()
    per_team: dict[str, list[float]] = defaultdict(list)
    best: dict[str, sqlite3.Row] = {}
    for h in hits:  # bm25 is lower-is-better, so negate it
        per_team[h["team"]].append(-h["score"])
        best.setdefault(h["team"], h)
    ranked = sorted(per_team, key=lambda t: -sum(sorted(per_team[t], reverse=True)[:3]))
    return ranked, best


def _by_ledger(conn: sqlite3.Connection, question: str) -> tuple[list[str], dict[str, sqlite3.Row]]:
    """Projects ranked by their best-matching ledger events. Summaries are clean sentences, so they
    match better than raw speech. Rare words count more (inverse document frequency), so "backup"
    outweighs "remote", which every project uses."""
    intent_types, rest = _intent(question)
    wanted = retrieve._words(rest)
    rows = conn.execute("SELECT team, meeting_id, speaker, type, topic, summary FROM events").fetchall()
    if not wanted or not rows:
        return [], {}
    words = [retrieve._words(r["summary"] + " " + r["topic"].replace("_", " ")) for r in rows]
    df = {w: sum(w in ws for ws in words) for w in wanted}
    idf = {w: np.log(len(rows) / (1 + df[w])) for w in wanted}
    per_team: dict[str, list[tuple[float, sqlite3.Row]]] = defaultdict(list)
    for row, ws in zip(rows, words):
        score = sum(idf[w] for w in wanted & ws)
        if score > 0:
            if row["type"] in intent_types:  # "who pushed back" wants objections, "what did they decide" decisions
                score *= INTENT_BOOST
            per_team[row["team"]].append((score, row))
    for hits in per_team.values():
        hits.sort(key=lambda h: -h[0])
    # The best event counts most, and depth counts too: a team with many matching events discussed it
    # more than a team with one passing mention. sqrt keeps a long list from swamping a precise match.
    ranked = sorted(per_team, key=lambda t: -(per_team[t][0][0] + np.sqrt(sum(s for s, _ in per_team[t][1:]))))
    return ranked, {t: per_team[t][0][1] for t in per_team}


#: Question phrasings that name the KIND of event wanted, mapped to ledger event types. The phrasing
#: itself is dropped from the topic words: summaries say "objected", people ask "who pushed back".
INTENTS = [
    (r"push(ed|es|ing)? back|object(ed|ion|s)?|against|disagree\w*|question(ed)?|critici[sz]\w*|concern\w*|"
     r"oppos\w*|reject\w*|argu\w*|doubt\w*|complain\w*|worr(y|ied|ies)", {"objection"}),
    (r"decid\w*|decision|chose|chosen|choose|settled?|end(ed)? up|final(ly)?|agreed|went with|picked", {"decision"}),
    (r"propos\w*|suggest\w*|idea|came up with|pitch(ed)?", {"proposal"}),
    (r"cost\w*|price\w*|budget|how much|euros?|dollars?|percent\w*", {"number"}),
    (r"promis\w*|assign\w*|task|action|follow[- ]?up|responsible|owner", {"action_item", "report_back"}),
]
INTENT_BOOST = 1.5


def _intent(question: str) -> tuple[set[str], str]:
    import re

    types, rest = set(), question
    for pattern, kinds in INTENTS:
        if re.search(rf"\b(?:{pattern})\b", rest, re.I):
            types |= kinds
            rest = re.sub(rf"\b(?:{pattern})\b", " ", rest, flags=re.I)
    return types, rest


def similar_ids(conn: sqlite3.Connection, team: str, k: int = 3) -> list[dict]:
    """Project IDs spelled like one that does not exist: TS3099 gives TS3009, TS3008... (a typo, usually)."""
    import difflib

    teams = [r[0] for r in conn.execute("SELECT DISTINCT team FROM meetings")]
    named = names.names(conn)
    return [{"team": t, "name": named.get(t), "match": None, "reason": f"Project ID spelled like {team}"}
            for t in difflib.get_close_matches(team, teams, n=k, cutoff=0.6)]


def suggest(question: str, conn: sqlite3.Connection | None = None, k: int = 3) -> list[dict]:
    conn = conn or connect()
    conn.execute(SCHEMA)
    try:
        meaning = _by_meaning(conn, question)
    except Exception:  # noqa: BLE001 - embeddings down: keywords alone still give an answer
        meaning = []
    keywords, best_turn = _by_keywords(conn, question)
    events, best_event = _by_ledger(conn, question)
    fused: dict[str, float] = defaultdict(float)
    # the ledger counts most: its sentences are clean and specific. Meaning and keyword search over raw
    # speech are noisy on broad questions, but rescue questions the ledger has no words for.
    for ranking, weight in ((events, LEDGER_WEIGHT), (meaning, 1.0), (keywords, 1.0)):
        for rank, team in enumerate(ranking):
            fused[team] += weight / (RRF_K + rank + 1)
    named = names.names(conn)
    out = []
    for team in sorted(fused, key=lambda t: -fused[t])[:k]:
        # show why: the matching ledger sentence reads better than raw speech
        hit = best_event.get(team) or best_turn.get(team)
        summary = bool(hit) and "summary" in hit.keys()
        out.append({"team": team, "name": named.get(team),
                    "match": {"meeting_id": hit["meeting_id"], "speaker": hit["speaker"],
                              "kind": "summary" if summary else "quote",  # a summary is not anyone's words
                              "text": (hit["summary"] if summary else hit["text"])[:220]} if hit else None})
    return out


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    print("profiles embedded:", update_profiles())
    print(json.dumps(suggest(" ".join(sys.argv[1:])), indent=2))
