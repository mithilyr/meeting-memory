"""Routing check for questions that name no project (D-029, D-031). Own cases, not questions.json:
each lists teams whose ledger clearly covers the topic. A case passes if one is in the top 5.

    python -m eval.route_check
"""

from src.agent import route
CASES = [
    ("Who pushed back on the LCD display and why", {"TS3008"}),
    ("what is the backup energy source for the remote?", {"ES2009", "ES2012", "ES2015", "ES2002"}),
    ("who wanted the remote shaped like a fruit?", {"ES2016", "ES2005", "ES2008"}),
    ("who said the remote should glow in the dark?", {"ES2005", "ES2015", "ES2002"}),
    ("which team used a scroll wheel and a locator?", {"IS1002"}),
    ("who questioned the solar cells and were they kept?", {"IS1004"}),
]
hits = 0
for q, want in CASES:
    got = [s["team"] for s in route.suggest(q, k=5)]
    ok = bool(want & set(got)); hits += ok
    print("OK  " if ok else "MISS", q[:50], got)
print(f"{hits}/{len(CASES)}")
