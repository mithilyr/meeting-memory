from pathlib import Path

from src.ingest.parse import parse_meeting
from src.ingest.verify import find_turn, quote_in_turn

SAMPLE = """Meeting: XX9999b
Team: XX9999

00:00:50 Speaker B
Okay. Right. Um well this is the kick-off meeting for our our project.

00:01:06 Speaker D
Mm-hmm. Great.
"""


def test_parse_turns(tmp_path: Path):
    path = tmp_path / "XX9999b.txt"
    path.write_text(SAMPLE, encoding="utf-8")
    meeting = parse_meeting(path)
    assert meeting.team == "XX9999" and meeting.letter == "b"
    assert [t.speaker for t in meeting.turns] == ["B", "D"]
    assert meeting.turns[0].seconds == 50
    assert meeting.turns[1].turn_id == "XX9999b#0001"


def test_quote_rules():
    turn = "Okay. Right. Um well this is the kick-off meeting for our our project."
    assert quote_in_turn("um WELL this is   the kick-off meeting", turn)  # case + spacing ignored
    assert not quote_in_turn("um well this is the kickoff meeting", turn)  # punctuation kept
    assert not quote_in_turn("the kick-off meeting", turn)  # under six words
    assert find_turn("this is the kick-off meeting for", ["nope", turn]) == 1
