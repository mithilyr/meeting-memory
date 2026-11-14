"""Find the figures in a piece of text, written as digits or as spoken words. Code only.

Transcripts spell numbers the way people say them ("twelve and a half Euros", "nought point eight",
"twenty five"), while extracted values use digits ("12.5 EUR"). To check that a stored figure was
really said, both sides are turned into numbers and compared.

    figures("we've got nought point eight left")      -> {0.8}
    figures("twelve and a half Euros, about 25")      -> {12.5, 25.0}
"""

from __future__ import annotations

import re

UNITS = {"zero": 0, "nought": 0, "nil": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
         "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
         "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
         "a": 1, "an": 1}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000,
          "hundreds": 100, "thousands": 1000, "millions": 1_000_000}
FRACTIONS = {"half": 0.5, "quarter": 0.25}
PLURAL_FRACTIONS = {"halves": 0.5, "quarters": 0.25, "thirds": 1 / 3}
WORDS = set(UNITS) | set(TENS) | set(SCALES)

DIGITS = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)")


def _words_to_numbers(tokens: list[str]) -> list[float]:
    """Read runs of number words. "oh", "a" and "an" only count inside a run, never alone."""
    out, i = [], 0
    while i < len(tokens):
        t = tokens[i]
        if t not in WORDS or t in ("a", "an", "oh"):
            i += 1
            continue
        total, current, j = 0.0, 0.0, i
        while j < len(tokens) and tokens[j] in WORDS | {"and"}:
            w = tokens[j]
            if w in ("and", "a") and any(f in tokens[j + 1:j + 3] for f in FRACTIONS):
                break  # "and a half": the fraction step below adds it
            if w == "and":
                # "twelve and a half", "a hundred and twenty": keep reading only if a number follows
                if j + 1 < len(tokens) and (tokens[j + 1] in WORDS | {"a"}):
                    j += 1
                    continue
                break
            if w in UNITS:
                # "twenty one", "a hundred and five" extend the number; "ten ten" or "one two" do not
                if current == 0 or (current >= 20 and current % 10 == 0 and UNITS[w] < 10) or current % 100 == 0:
                    current += UNITS[w]
                else:  # "one two" said as separate numbers: close the first
                    out.append(total + current)
                    total, current = 0.0, float(UNITS[w])
            elif w in TENS:
                if current % 100:  # "twelve fifty", "two twenty": two numbers, often a price
                    out.append(total + current)
                    if 1 <= current < 100:
                        out.append(total + current + TENS[w] / 100)
                    if 1 <= current < 10:  # "one fifty" can also mean 150
                        out.append(current * 100 + TENS[w])
                    total, current = 0.0, 0.0
                current += TENS[w]
            elif w in SCALES:
                current = (current or 1) * SCALES[w]
                if SCALES[w] >= 1000:
                    total, current = total + current, 0.0
            j += 1
        value = total + current
        # "point eight", "point two five"
        if j < len(tokens) and tokens[j] in ("point", "dot"):
            k, decimals = j + 1, ""
            while k < len(tokens) and tokens[k] in UNITS and UNITS[tokens[k]] < 10 and tokens[k] not in ("a", "an"):
                decimals += str(UNITS[tokens[k]])
                k += 1
            if decimals:
                value = float(f"{int(value)}.{decimals}")
                j = k
        # "and a half", "a quarter"
        if j + 1 < len(tokens) and tokens[j] in ("a", "and") and tokens[j + 1] in FRACTIONS:
            value += FRACTIONS[tokens[j + 1]]
        elif j + 2 < len(tokens) and tokens[j] == "and" and tokens[j + 1] == "a" and tokens[j + 2] in FRACTIONS:
            value += FRACTIONS[tokens[j + 2]]
        out.append(value)
        i = max(j, i + 1)
    return out


MONEY = r"(?:euros?|pounds?|dollars?|francs?|bucks?)"


def _collapse_money(text: str) -> str:
    """ "twelve euros fifty" -> "12.5 euros", so a claim written that way is one figure, not two."""
    def join(m: re.Match) -> str:
        left, right = _words_to_numbers(m.group(1).lower().split()), _words_to_numbers(m.group(3).lower().split())
        if left and right and right[0] < 100:
            return f"{left[-1] + right[0] / 100!r} {m.group(2)}"
        return m.group(0)
    return re.sub(rf"\b((?:\w+ )?\w+) ({MONEY}) (\w+(?: \w+)?)", join, text, flags=re.I)


def stated(text: str) -> set[float]:
    """The figures a stored value or summary claims: "50 million" is 50,000,000 only, not also 50."""
    text = _collapse_money(text)
    scaled = re.sub(r"(\d+(?:\.\d+)?)\s*(hundred|thousand|million)\b",
                    lambda m: repr(float(m.group(1)) * SCALES[m.group(2).lower()]), text, flags=re.I)
    return {float(m.replace(",", ".")) for m in DIGITS.findall(scaled)} | set(
        _words_to_numbers(re.findall(r"[a-z]+", scaled.lower().replace("-", " "))))


def figures(text: str) -> set[float]:
    """Every number in the text, from digits and from words. Ranges like "60-65" give both ends."""
    found = {float(m.replace(",", ".")) for m in DIGITS.findall(text)}
    for number, scale in re.findall(r"(\d+(?:\.\d+)?)\s*(hundred|thousand|million)\b", text.lower()):
        found.add(float(number) * SCALES[scale])  # "50 million"
    tokens = re.findall(r"[a-z]+", text.lower().replace("-", " "))
    found |= set(_words_to_numbers(tokens))
    # "three quarters" (0.75, also said as 75 percent), "two thirds"
    for i, w in enumerate(tokens[1:], 1):
        if w in PLURAL_FRACTIONS and tokens[i - 1] in UNITS:
            found.add(round(UNITS[tokens[i - 1]] * PLURAL_FRACTIONS[w], 4))
        if w in FRACTIONS and tokens[i - 1] in ("a", "an", "one") and (i < 2 or tokens[i - 2] != "and"):
            found.add(FRACTIONS[w])  # "a quarter of people", "half the buttons"
    # "twelve Euros fifty": a price said with the currency in the middle
    money = r"(?:euros?|pounds?|dollars?|francs?|bucks?)"
    for a, b in re.findall(rf"\b((?:\w+ )?\w+) {money} (\w+(?: \w+)?)", text.lower()):
        left, right = _words_to_numbers(a.split()), _words_to_numbers(b.split())
        if left and right and right[0] < 100:
            found.add(left[-1] + right[0] / 100)
    # "zero point eight" with a leading "point": ".8"
    for m in re.finditer(r"\bpoint ((?:zero|nought|one|two|three|four|five|six|seven|eight|nine)(?: (?:zero|nought|one|two|three|four|five|six|seven|eight|nine))*)", text.lower()):
        found.add(float("0." + "".join(str(UNITS[w]) for w in m.group(1).split())))
    return found


def same(a: float, b: float) -> bool:
    """Equal, or the same share said two ways: 25 (percent) and "a quarter" (0.25)."""
    return abs(a - b) < 1e-6 or (b < 1 and abs(a - b * 100) < 1e-6) or (a < 1 and abs(a * 100 - b) < 1e-6)


def supported(claim: str, evidence: str) -> list[float]:
    """Figures in the claim that the evidence never says. Empty list = every figure is backed."""
    said = figures(evidence)
    return [n for n in stated(claim) if not any(same(n, x) for x in said)]


#: Currency and unit words: a stored value in Euros must come from talk in Euros, not Francs.
CURRENCIES = {
    "euro": re.compile(r"\beur(?:o|os)?\b|€", re.I),
    "franc": re.compile(r"\bfrancs?\b", re.I),
    "dollar": re.compile(r"\b(?:usd|dollars?)\b|\$", re.I),
    "pound": re.compile(r"\b(?:gbp|pounds?|quid)\b|£", re.I),
}


def currencies(text: str) -> set[str]:
    return {name for name, pattern in CURRENCIES.items() if pattern.search(text)}
