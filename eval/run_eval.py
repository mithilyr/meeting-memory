"""Score the agent on our own hand-checked questions. Scoring is code, not a model judge.

Per question:
  correct          every must_include group matched in the answer (case-insensitive)
  citations_valid  share of the agent's quotes that pass the grader's rule (6+ words, one turn)
  multi_meeting    citations span 2+ meetings
  gold_overlap     the agent cited at least one gold meeting

    python -m eval.run_eval
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.agent.answer import answer, clean_answer
from src.ingest.verify import quote_in_turn
from src.memory.store import connect

HERE = Path(__file__).resolve().parent


def quote_ok(conn, meeting_id: str, quote: str) -> bool:
    return any(quote_in_turn(quote, r[0]) for r in conn.execute(
        "SELECT text FROM turns WHERE meeting_id = ?", (meeting_id,)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args = parser.parse_args(argv)
    conn = connect()
    spec = json.loads((HERE / "own_questions.json").read_text(encoding="utf-8"))

    bad_gold = [(q["id"], c["quote"]) for q in spec["questions"] for c in q["gold_citations"]
                if not quote_ok(conn, c["meeting_id"], c["quote"])]
    if bad_gold:
        print("GOLD QUOTES FAILING VERIFICATION (fix the eval set first):")
        for qid, quote in bad_gold:
            print(f"  {qid}: {quote}")
        return 1

    rows = []
    for q in spec["questions"]:
        result = answer(q["question"] if q["team"] in q["question"] else f"{q['team']}: {q['question']}",
                        conn=conn)
        text = clean_answer(result["answer"]).lower()  # same space and hyphen normalisation as the agent
        missing = [g for g in q["must_include"] if not any(alt.lower() in text for alt in g)]
        valid = [quote_ok(conn, c["meeting_id"], c["quote"]) for c in result["citations"]]
        meetings = {c["meeting_id"] for c in result["citations"]}
        rows.append({
            "id": q["id"], "team": q["team"], "correct": not missing, "missing": missing,
            "citations_valid": f"{sum(valid)}/{len(valid)}", "multi_meeting": len(meetings) >= 2,
            "gold_overlap": bool(meetings & {c["meeting_id"] for c in q["gold_citations"]}),
            "seconds": result["seconds"], "answer": result["answer"], "gold": q["gold_answer"],
            "citations": result["citations"], "trace": result["trace"],
        })
        r = rows[-1]
        print(f"{q['id']} {q['team']}: {'RIGHT' if r['correct'] else 'WRONG'}  cites {r['citations_valid']}  "
              f"multi={r['multi_meeting']}  {r['seconds']}s" + (f"  missing={missing}" if missing else ""))

    n = len(rows)
    summary = {
        "correct": f"{sum(r['correct'] for r in rows)}/{n}",
        "all_citations_valid": f"{sum(r['citations_valid'].split('/')[0] == r['citations_valid'].split('/')[1] != '0' for r in rows)}/{n}",
        "multi_meeting": f"{sum(r['multi_meeting'] for r in rows)}/{n}",
        "gold_meeting_cited": f"{sum(r['gold_overlap'] for r in rows)}/{n}",
        "avg_seconds": round(sum(r["seconds"] for r in rows) / n, 1),
    }
    print(json.dumps(summary, indent=2))
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    path = out / f"eval_{time.strftime('%Y-%m-%dT%H-%M-%S')}.json"
    path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
