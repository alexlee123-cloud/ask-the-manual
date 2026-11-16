"""Score Ask the Manual against eval/questions.csv.

Metrics
- retrieval hit rate: the expected page/section is among the top-k excerpts
- answer accuracy: the answer contains the expected value (answerable questions)
- abstention: the assistant says "not found" for questions the manuals don't cover

    python eval/run_eval.py                    # full run (calls the Claude API)
    python eval/run_eval.py --retrieval-only   # free: scores search only
    python eval/run_eval.py --k 3              # try a different top-k
    python eval/run_eval.py --questions eval/questions-manuals.csv   # the real Haas/OSHA manuals
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from atm.answer import ask  # noqa: E402
from atm.retrieve import search  # noqa: E402


def contains(answer: str, expected: str) -> bool:
    """True if any '|'-separated alternative appears in the answer (case-insensitive)."""
    return any(alt.strip().lower() in answer.lower() for alt in expected.split("|") if alt.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default=ROOT / "eval" / "questions.csv")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--retrieval-only", action="store_true")
    args = parser.parse_args()

    rows = list(csv.DictReader(open(args.questions, newline="", encoding="utf-8")))
    results = []
    for row in rows:
        answerable = row["answerable"].strip().lower() == "yes"
        hits = search(row["question"], k=args.k)
        r = {"question": row["question"], "answerable": answerable}
        if answerable:
            # expected_location is a location ("PDF p. 12") or a full citation
            # ("Manual title, PDF p. 12"); '|' separates acceptable alternatives.
            expected = {e.strip() for e in row["expected_location"].split("|")}
            r["retrieval_hit"] = any(h.location in expected or h.citation in expected for h in hits)
        if not args.retrieval_only:
            ans = ask(row["question"], k=args.k)
            r["answer"] = ans.text
            r["correct"] = contains(ans.text, row["expected_contains"]) if answerable else not ans.found
        results.append(r)
        print(".", end="", flush=True)
    print()

    answerable = [r for r in results if r["answerable"]]
    unanswerable = [r for r in results if not r["answerable"]]

    def pct(xs):
        return f"{100 * sum(xs) / len(xs):.0f}% ({sum(xs)}/{len(xs)})" if xs else "n/a"

    print(f"Retrieval hit rate @k={args.k}: {pct([r['retrieval_hit'] for r in answerable])}")
    if not args.retrieval_only:
        print(f"Answer accuracy:          {pct([r['correct'] for r in answerable])}")
        print(f"Correct abstentions:      {pct([r['correct'] for r in unanswerable])}")

    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"run-{datetime.now():%Y%m%d-%H%M%S}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sorted({k for r in results for k in r}))
        writer.writeheader()
        writer.writerows(results)
    print(f"Saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
