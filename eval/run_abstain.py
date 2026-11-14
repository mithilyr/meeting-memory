"""Score the agent on questions it should decline or correct (eval/abstain_questions.json).

A pass needs the expected status, and a "not discussed" reply must cite nothing (nothing was said).
Saying no to an answerable question is caught by the main eval (eval/run_eval.py).

    python -m eval.run_abstain
"""

from __future__ import annotations

import json
from pathlib import Path

from src.agent.answer import answer
from src.memory.store import connect

HERE = Path(__file__).parent


def main() -> int:
    cases = json.loads((HERE / "abstain_questions.json").read_text(encoding="utf-8"))["questions"]
    conn, rows, passed = connect(), [], 0
    for case in cases:
        r = answer(case["question"], conn=conn)
        ok = r.get("status") in case["expect"] and not (r.get("status") == "not_discussed" and r["citations"])
        passed += ok
        rows.append({"id": case["id"], "question": case["question"], "expect": case["expect"], "status": r.get("status"),
                     "answer": r["answer"], "citations": r["citations"], "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'} {case['id']} expected {'/'.join(case['expect'])}, got {r.get('status')}: {r['answer'][:110]}")
    print(f"{passed}/{len(cases)} declined or corrected as expected")
    (HERE / "results" / "abstain_latest.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
