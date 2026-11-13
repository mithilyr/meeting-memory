"""Transcript files -> Turn rows. Plain code, no model.

The format is fixed and machine-written (see CREDITS.txt): a header block, then
turns of exactly two lines, `HH:MM:SS Speaker X` and the spoken text. Checked
across all 138 files on 2026-11-13: every turn has exactly one text line.

A model adds nothing here except cost and the chance of altering the words we
later have to quote exactly.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from src.settings import get_settings

TURN_HEADER = re.compile(r"^(\d{2}):(\d{2}):(\d{2}) Speaker ([A-Z])$")
MEETING_ID = re.compile(r"^([A-Z]{2}\d{4})([a-d])$")


@dataclass(frozen=True)
class Turn:
    meeting_id: str  # "TS3012c"
    team: str  # "TS3012"
    letter: str  # "c": meeting order within the team
    turn_index: int  # 0-based position within the meeting
    seconds: int  # start time from recording start
    speaker: str  # "A".."D"
    text: str  # exactly as transcribed. Never modified.

    @property
    def turn_id(self) -> str:
        return f"{self.meeting_id}#{self.turn_index:04d}"


@dataclass(frozen=True)
class Meeting:
    meeting_id: str
    team: str
    letter: str
    content_hash: str  # drives incremental ingestion
    turns: tuple[Turn, ...]


def parse_meeting(path: Path) -> Meeting:
    raw = path.read_bytes()
    meeting_id = path.stem
    match = MEETING_ID.match(meeting_id)
    if not match:
        raise ValueError(f"{path.name}: file name is not a meeting id like ES2002a")
    team, letter = match.groups()

    lines = raw.decode("utf-8").splitlines()
    turns: list[Turn] = []
    i = 0
    while i < len(lines):
        header = TURN_HEADER.match(lines[i])
        if not header:
            i += 1
            continue
        hh, mm, ss, speaker = header.groups()
        text = lines[i + 1] if i + 1 < len(lines) else ""
        if not text.strip():
            raise ValueError(f"{path.name}:{i + 1}: turn header with no text line")
        turns.append(
            Turn(
                meeting_id=meeting_id,
                team=team,
                letter=letter,
                turn_index=len(turns),
                seconds=int(hh) * 3600 + int(mm) * 60 + int(ss),
                speaker=speaker,
                text=text,
            )
        )
        i += 2

    return Meeting(
        meeting_id=meeting_id,
        team=team,
        letter=letter,
        content_hash=hashlib.sha256(raw).hexdigest(),
        turns=tuple(turns),
    )


def iter_meetings(transcripts_dir: Path | None = None):
    """Every transcript in the data folder, plus any new ones dropped in the inbox."""
    settings = get_settings()
    directories = [transcripts_dir] if transcripts_dir else [settings.require_data(), settings.inbox_dir]
    for directory in directories:
        for path in sorted(directory.glob("*.txt")) if directory.is_dir() else []:
            yield parse_meeting(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="parse everything and print counts")
    args = parser.parse_args(argv)
    if not args.check:
        parser.print_help()
        return 0

    meetings = list(iter_meetings())
    teams = Counter(m.team for m in meetings)
    turns = sum(len(m.turns) for m in meetings)
    words = sum(len(t.text.split()) for m in meetings for t in m.turns)
    print(f"meetings: {len(meetings)}  teams: {len(teams)}  turns: {turns}  words: {words}")
    short = sorted(team for team, n in teams.items() if n < 4)
    print(f"teams with fewer than 4 meetings: {short}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
