"""Produce out/answers.json: the 25 questions plus the TS3012 brief.

    python run.py

Writes out/answers.json (the submission format, nothing else in it) and
out/run_log.json (per-question trace, model used, seconds, citation checks).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.agent.answer import answer
from src.agent.brief import write_brief
from src.clients.llm import USAGE
from src.ingest.verify import quote_in_turn
from src.memory.store import connect
from src.settings import get_settings

OUT = Path(__file__).resolve().parent / "out"


def check_citation(conn, citation: dict) -> bool:
    """Grader's rule, applied independently of the agent: 6+ words, inside one turn."""
    return any(quote_in_turn(citation["quote"], r[0]) for r in conn.execute(
        "SELECT text FROM turns WHERE meeting_id = ?", (citation["meeting_id"],)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", help="question ids to run, e.g. Q01 Q07")
    parser.add_argument("--out", default="answers.json", help="file name under out/ (compare before replacing)")
    args = parser.parse_args(argv)

    conn = connect()
    spec = json.loads(get_settings().questions_path.read_text(encoding="utf-8"))
    questions = [q for q in spec["questions"] if not args.only or q["question_id"] in args.only]
    answers, log = [], []
    started = time.time()
    shipped = OUT / "answers.json"
    previous = {a["question_id"]: a for a in json.loads(shipped.read_text(encoding="utf-8"))["answers"]}         if shipped.exists() else {}
    for q in questions:
        result = answer(q["question"], conn=conn)
        if result.get("fallback") == "no_model" and q["question_id"] in previous:
            # free-tier limits hit mid-run: keep the earlier answer rather than write "models unavailable"
            answers.append(previous[q["question_id"]])
            log.append({"question_id": q["question_id"], "kept_previous": "no model available"})
            print(f"{q['question_id']}: no model available, kept the previous answer")
            continue
        valid = [check_citation(conn, c) for c in result["citations"]]
        answers.append({"question_id": q["question_id"], "answer": result["answer"],
                        "citations": [c for c, ok in zip(result["citations"], valid) if ok]})
        log.append({"question_id": q["question_id"], "status": result.get("status"), "seconds": result["seconds"],
                    "citations_valid": f"{sum(valid)}/{len(valid)}", "trace": result["trace"]})
        print(f"{q['question_id']}: {sum(valid)}/{len(valid)} citations valid, {result['seconds']}s")

    team = spec["brief_task"]["team"]
    brief = write_brief(team, conn=conn)
    print(f"brief {team}: meetings up to {brief['upto_letter']}, model {brief['model']}")

    OUT.mkdir(exist_ok=True)
    if args.only and previous:  # partial run: merge into the existing file
        fresh = {a["question_id"]: a for a in answers}
        answers = [fresh.get(qid, a) for qid, a in previous.items()]
    (OUT / args.out).write_text(
        json.dumps({"answers": answers, "brief": brief["brief"]}, indent=2, ensure_ascii=False), encoding="utf-8")
    log_name = "run_log.json" if args.out == "answers.json" else f"run_log_{Path(args.out).stem}.json"
    (OUT / log_name).write_text(json.dumps({
        "seconds": round(time.time() - started, 1), "questions": log,
        "brief": {k: v for k, v in brief.items() if k != "brief"}, "model_calls": USAGE.calls,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT / args.out} in {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
