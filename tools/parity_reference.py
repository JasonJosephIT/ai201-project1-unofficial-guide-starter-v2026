"""
Python side of the static-site parity check. Run by tools/check_static_parity.mjs.

Reads {"corpus": ..., "questions": [...]} as JSON on stdin, adds the
questions from questions.py (your five, plus OUT_OF_SCOPE), runs each through
the real `store.search` and `gate.check`, and prints the results as JSON.

Needs a real index for the corpus: `python app.py --corpus <name> index`.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import gate  # noqa: E402
import questions  # noqa: E402
import store  # noqa: E402


def main() -> None:
    request = json.load(sys.stdin)
    corpus = request["corpus"]
    if not store.index_exists(corpus):
        sys.exit(f"No index for {corpus}. Run: python app.py --corpus {corpus} index")

    wanted = [q["question"] for q in questions.answered()] + questions.OUT_OF_SCOPE
    wanted += request.get("questions", [])

    out = []
    for q in dict.fromkeys(wanted):  # de-duplicate, keep order
        results = store.search(q, corpus=corpus)
        decision = gate.check(results)
        out.append({
            "question": q,
            "top": [{"label": r.label, "distance": r.distance} for r in results],
            "best": decision.best_distance,
            "passed": decision.passed,
        })
    json.dump({"corpus": corpus, "top_k": config.top_k_for(corpus),
               "threshold": config.THRESHOLD, "results": out}, sys.stdout)


if __name__ == "__main__":
    main()
