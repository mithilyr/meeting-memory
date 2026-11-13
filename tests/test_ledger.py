from src.memory.ledger import compute


def ev(event_id, letter, idx, type_, topic, **kw):
    return {"event_id": event_id, "letter": letter, "turn_idx": idx, "type": type_,
            "topic": topic, "refers_to": kw.get("refers_to"), "speaker": kw.get("speaker"),
            "owner": kw.get("owner")}


def test_later_decision_supersedes_earlier():
    s = compute([ev("a1", "a", 5, "decision", "case_material"),
                 ev("c1", "c", 9, "decision", "case_material")])
    assert s["a1"] == ("superseded", "c1")
    assert s["c1"] == ("current", None)


def test_cutoff_changes_what_is_current():
    a = ev("a1", "a", 5, "decision", "energy")
    d = ev("d1", "d", 2, "decision", "energy")
    assert compute([a, d])["a1"][0] == "superseded"
    assert compute([a])["a1"][0] == "current"  # meeting d not visible -> a is current


def test_action_reported_by_owner_later():
    s = compute([ev("b1", "b", 3, "action_item", "lcd_cost", owner="C"),
                 ev("c1", "c", 4, "report_back", "lcd_cost", speaker="C")])
    assert s["b1"][0] == "reported"


def test_objection_open_until_decided():
    obj = ev("b1", "b", 3, "objection", "speech_recognition")
    assert compute([obj])["b1"][0] == "open"
    assert compute([obj, ev("c1", "c", 1, "decision", "speech_recognition")])["b1"][0] == "addressed"
