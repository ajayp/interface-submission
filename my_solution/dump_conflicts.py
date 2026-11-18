"""
Load every website copy, call conflicts() once and save the list as JSON (for score_conflict_lists.py).

    python my_solution/dump_conflicts.py --out results/conflicts/base.json

Uses the same environment switches as a normal run (MY_SOLUTION_SENTENCE_CONTEXT, MY_SOLUTION_FACT_CACHE, ...). About 3 minutes and
$0.10 the first time; set MY_SOLUTION_FACT_CACHE and MY_SOLUTION_SENTENCE_CACHE to reuse earlier calls.
"""
import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "harness"), str(ROOT / "my_solution")]
from run_eval import load_snapshots, load_submission  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--snapshots", type=Path, default=ROOT / "snapshots")
    a = ap.parse_args()
    ks = load_submission(ROOT / "my_solution")
    t = time.time()
    for s in load_snapshots(a.snapshots):
        ks.ingest(s)
    print(f"loaded in {time.time() - t:.0f} s")
    out = ks.conflicts()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps([dataclasses.asdict(c) for c in out], indent=1, default=str))
    print(f"conflicts(): {len(out)} entries -> {a.out}")


if __name__ == "__main__":
    main()
