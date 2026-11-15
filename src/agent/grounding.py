"""Does the answer say only what its cited evidence says? Code only, no model (D-033).

A citation proves its own quote, not the sentence around it. A model can cite a real quote and still
name the wrong person or add a figure nobody said. Every answer is checked before it is shown:

  speakers   every "Speaker X" in the answer speaks in, or is named by, the cited evidence
  figures    every number in the answer is said in the cited evidence (spoken forms count:
             "twelve fifty" backs 12.50)
  stale      a cited ledger decision or figure that was later replaced, when the replacement is
             not cited: the answer may be giving an old position as the final one

Evidence for a citation = the full turn it quotes, plus any ledger event built on that quote
(its summary and value), plus that event's speaker.
"""

from __future__ import annotations

import re
import sqlite3

from src.ingest.numbers import figures, same, stated
from src.ingest.verify import normalise

SPEAKERS = re.compile(r"\bSpeakers?\s+([A-D](?:\s*(?:,|and|&|/|or)\s*(?:Speaker\s+)?[A-D]\b)*)")
ORDINALS = r"first|second|third|fourth|fifth|last|final|1st|2nd|3rd|4th"


def evidence(conn: sqlite3.Connection, citations: list[dict]) -> list[dict]:
    """For each citation: the speakers, the text that backs it, and any ledger event built on it."""
    out = []
    for c in citations:
        turn = next((r for r in conn.execute("SELECT idx, speaker, text FROM turns WHERE meeting_id = ? ORDER BY idx",
                                              (c["meeting_id"],))
                     if normalise(c["quote"]) in normalise(r["text"])), None)
        events = conn.execute("SELECT * FROM events WHERE meeting_id = ? AND quote = ?",
                              (c["meeting_id"], c["quote"])).fetchall()
        speakers = {turn["speaker"]} if turn else set()
        text = turn["text"] if turn else c["quote"]
        for e in events:
            speakers.add(e["speaker"]) if e["speaker"] else None
            text += f" {e['summary']} {e['value'] or ''}"
        speakers |= set(re.findall(r"\bSpeaker ([A-D])\b", text))  # "Speaker B said Speaker A's idea..."
        out.append({"speakers": speakers, "text": text, "events": [dict(e) for e in events]})
    return out


def _letters(text: str) -> set[str]:
    return {l for group in SPEAKERS.findall(text) for l in re.findall(r"[A-D]", group)}


def _claimed_figures(answer: str) -> set[float]:
    """Numbers the answer asserts. Meeting numbers, speaker letters and project IDs are labels, not claims."""
    text = re.sub(r"\b[A-Z]{2}\d{4}[a-d]?\b", " ", answer)                      # project / meeting ids
    text = re.sub(r"\bSpeakers?\s+[A-D]\b", " ", text)
    text = re.sub(rf"\bmeetings?\s+(?:\d+|one|two|three|four)(?:\s*(?:,|and|to|-)\s*(?:\d+|one|two|three|four))*",
                  " ", text, flags=re.I)
    text = re.sub(rf"\b(?:{ORDINALS})\s+meeting\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:\d+|one|two|three|four)\s+of\s+(?:\d+|four)\s+meetings\b", " ", text, flags=re.I)
    return stated(text)


def check(conn: sqlite3.Connection, answer: str, citations: list[dict]) -> list[str]:
    """Problems with the answer's grounding, in words a model can act on. Empty = grounded."""
    if not citations:
        return []
    found = evidence(conn, citations)
    problems = []
    allowed = set().union(*(f["speakers"] for f in found))
    missing = sorted(_letters(answer) - allowed)
    if missing:
        problems.append(f"The answer names Speaker {', '.join(missing)}, but no cited evidence shows "
                        f"{'them' if len(missing) > 1 else 'that speaker'} saying or doing it. Cite evidence "
                        "for every person you name, or leave them out.")
    said = figures(" ".join(f["text"] for f in found))
    unbacked = sorted(n for n in _claimed_figures(answer) if not any(same(n, x) for x in said))
    if unbacked:
        shown = ", ".join(f"{n:g}" for n in unbacked)
        problems.append(f"The answer states {shown}, which no cited evidence says. Cite where each figure "
                        "is said, or leave it out.")
    return problems


def by_letter(conn: sqlite3.Connection, team: str, text: str) -> str:
    """The output names people by speaker letter (with the role), not by the names said in meetings.
    "Project Manager Mark" becomes "Speaker A, the Project Manager"; "Dirk" becomes "Speaker D"."""
    rows = conn.execute("SELECT DISTINCT s.speaker, s.role, s.name FROM speakers s JOIN meetings m USING (meeting_id) "
                        "WHERE m.team = ? AND s.name IS NOT NULL", (team,)).fetchall()
    for r in rows:
        first = r["name"].split()[0]
        names = sorted({r["name"], first}, key=len, reverse=True)
        for name in names:
            if r["role"]:
                text = re.sub(rf"\b(?:the\s+)?{re.escape(r['role'])}\s*,?\s*{re.escape(name)}\b",
                              f"Speaker {r['speaker']}, the {r['role']},", text, flags=re.I)
            text = re.sub(rf"\b{re.escape(name)}\b(?:\s*\(Speaker {r['speaker']}\))?", f"Speaker {r['speaker']}", text)
    text = re.sub(r",\s*([.;:)\]])", r"\1", text)  # "the Project Manager, ." left by the role form
    return re.sub(r",,", ",", text)


def pick(conn: sqlite3.Connection, answer: str, citations: list[dict], k: int = 3) -> list[dict]:
    """Choose the k citations that back the most of the answer's people and figures, spreading across
    meetings on ties. The output format allows 3 citations; the model may offer more to choose from."""
    if len(citations) <= k:
        return citations
    found = evidence(conn, citations)
    claims = {("speaker", l) for l in _letters(answer)} | {("figure", n) for n in _claimed_figures(answer)}
    def covers(f: dict) -> set:
        said = figures(f["text"])
        return ({c for c in claims if c[0] == "speaker" and c[1] in f["speakers"]} |
                {c for c in claims if c[0] == "figure" and any(same(c[1], x) for x in said)})
    chosen, covered, meetings = [], set(), set()
    pool = list(zip(citations, found))
    while pool and len(chosen) < k:
        best = max(pool, key=lambda p: (len(covers(p[1]) - covered), p[0]["meeting_id"] not in meetings))
        pool.remove(best)
        chosen.append(best[0])
        covered |= covers(best[1])
        meetings.add(best[0]["meeting_id"])
    return sorted(chosen, key=lambda c: c["meeting_id"])


def overlap(conn: sqlite3.Connection, answer: str, citations: list[dict]) -> float:
    """Share of the answer's content words that appear in its cited evidence (D-038). Speaker labels don't count."""
    from src.agent.retrieve import _words

    said = _words(" ".join(f["text"] for f in evidence(conn, citations)))
    claimed = _words(re.sub(r"\bSpeakers?\s+[A-D]\b", " ", answer))
    return len(claimed & said) / max(len(claimed), 1)


def invented_figures(answer: str, shown: str) -> list[float]:
    """Figures in the answer that appear nowhere in the evidence the model was given. These cannot have
    come from the meetings, so an answer that keeps them after repair is withheld."""
    said = figures(shown)
    return sorted(n for n in _claimed_figures(answer) if not any(same(n, x) for x in said))


def stale(conn: sqlite3.Connection, citations: list[dict]) -> list[str]:
    """Cited decisions or figures that were replaced later, when the replacement is not cited."""
    found = evidence(conn, citations)
    cited_ids = {e["event_id"] for f in found for e in f["events"]}
    notes = []
    for f in found:
        for e in f["events"]:
            if e["status"] != "superseded":
                continue
            # follow the chain to the final word; fine if any later link in it is cited
            chain, current = [], e.get("superseded_by")
            while current and current not in chain:
                chain.append(current)
                row = conn.execute("SELECT superseded_by FROM events WHERE event_id = ?", (current,)).fetchone()
                current = row["superseded_by"] if row else None
            if chain and not cited_ids & set(chain):
                final = conn.execute("SELECT summary FROM events WHERE event_id = ?", (chain[-1],)).fetchone()
                notes.append(f"Cited event {e['event_id']} was later replaced; the final word on that topic is "
                             f"{chain[-1]}: \"{final['summary']}\". If the question asks what was current or "
                             "final, use and cite that one.")
    return notes
