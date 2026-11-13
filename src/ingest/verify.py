"""Quote verification, matching the grader's rule. Plain code, no model.

Grader rule (questions.json): a quote is at least six words, copied exactly
from within one speaker turn; case and spacing are ignored. So we lowercase and
collapse whitespace, and nothing else. Punctuation is kept on purpose: folding
it (as CodeFest's scoring.normalise does) would pass quotes the grader fails.
"""

from __future__ import annotations

import re

MIN_WORDS = 6


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_in_turn(quote: str, turn_text: str) -> bool:
    q = normalise(quote)
    return len(q.split(" ")) >= MIN_WORDS and q in normalise(turn_text)


def find_turn(quote: str, turn_texts: list[str]) -> int | None:
    """Index of the first turn that contains the quote, or None."""
    for index, text in enumerate(turn_texts):
        if quote_in_turn(quote, text):
            return index
    return None
