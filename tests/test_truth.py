"""Truth checks: spoken figures (src/ingest/numbers.py) and answer grounding (src/agent/grounding.py)."""

from src.agent.grounding import _claimed_figures, _letters
from src.ingest.numbers import figures, stated, supported


def test_spoken_figures_are_read():
    assert figures("we've got nought point eight left") == {0.8}
    assert 12.5 in figures("twelve and a half Euros")
    assert 12.5 in figures("production cost's at twelve fifty, so")
    assert 12.5 in figures("we're trying to make it for twelve Euros fifty")
    assert 10.7 in figures("ten ten Euro seventy cents a unit")
    assert 17.8 in figures("So we are at seventeen dot eight.")
    assert 50_000_000 in figures("a profit of fifty million Euros")
    assert 150 in figures("you might have one fifty channels")
    assert 0.75 in figures("three quarters of users")


def test_stated_figures_are_not_split():
    assert stated("50 million EUR target") == {50_000_000.0}
    assert stated("below twelve euros fifty") == {12.5}


def test_supported_catches_a_figure_nobody_said():
    assert supported("The cost is 12.50 EUR", "twelve fifty, so") == []
    assert supported("25% said it was bad", "a quarter of people said") == []
    assert supported("The cost is 3 EUR", "it was about sixteen Francs") == [3.0]


def test_answer_labels_are_not_claims():
    claimed = _claimed_figures("In meeting 2, Speaker B of TS3012 proposed 25 Euros; the third meeting kept it.")
    assert claimed == {25.0}


def test_speaker_letters_are_found():
    assert _letters("Speaker A and Speaker C agreed; Speakers B and D objected.") == {"A", "B", "C", "D"}
