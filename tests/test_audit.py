"""A new meeting gets the same truth audit as the corpus: store_events runs it on every import (D-032)."""

import json

from src.ingest.extract import store_events
from src.memory.store import connect


def test_new_meeting_is_audited_on_import(tmp_path):
    conn = connect(tmp_path / "memory.db")
    conn.execute("INSERT INTO meetings VALUES ('TS9999a', 'TS9999', 'a', 'h', 2, NULL)")
    turns = [(0, "A", "The price should be about twelve fifty, in Euros, I think we can do that."),
             (1, "B", "It was sixteen Francs last time we asked the supplier about it.")]
    for idx, speaker, text in turns:
        conn.execute("INSERT INTO turns VALUES (?, 'TS9999a', 'TS9999', 'a', ?, 0, ?, ?)",
                     (f"TS9999a#{idx:04d}", idx, speaker, text))
    data = {"speakers": [], "events": [
        {"id": "E1", "type": "number", "topic": "price", "summary": "Speaker A set the price at 12.50 EUR.",
         "speaker": "A", "value": "12.50 EUR", "turn": 0, "quote": "The price should be about twelve fifty"},
        {"id": "E2", "type": "number", "topic": "supplier_price", "summary": "Speaker B said it cost 16 EUR.",
         "speaker": "B", "value": "16 EUR", "turn": 1, "quote": "It was sixteen Francs last time we asked"},
        {"id": "E3", "type": "number", "topic": "units", "summary": "Speaker B expects 40 units a day.",
         "speaker": "B", "value": "40 units", "turn": 1, "quote": "It was sixteen Francs last time we asked"},
    ]}
    store_events(conn, "TS9999a", data)
    flags = {r["event_id"]: json.loads(r["flags"]) if r["flags"] else [] for r in conn.execute("SELECT * FROM events")}
    assert flags["TS9999a-E01"] == []                      # "twelve fifty" backs 12.50
    assert "unit_differs" in flags["TS9999a-E02"]          # stored EUR, said Francs
    assert "figure_not_said" in flags["TS9999a-E03"]       # nobody said 40
