#!/usr/bin/env python3
"""Retrieval-only check (no answer calls): does the evidence sent to the model contain what the question needs?

For each eval question that has `must_include`, run the same retrieve() as answer() and test whether every required string occurs in
the text of the retrieved pieces. Also records the number of pieces and characters (the size of the user message) and, for pieces added
by enrichment, their similarity and whether they hold a required string (to choose a floor). Arms are environment switches, so run one
process per arm:

    MY_SOLUTION_ENRICH=ctx,q,prop,emb python my_solution/retrieval_check.py --out results/rc_E.json
"""
import argparse, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "harness"))
DEFAULT_SETS = ["eval/public_eval.jsonl", "eval/subsets/heldout.jsonl", "eval/subsets/typo_robustness.jsonl",
                "eval/subsets/slice2_branch_contact.jsonl", "eval/subsets/heldout_temporal.jsonl"]


def norm(s: str) -> str:
    return " ".join(s.lower().replace("–", "-").replace("’", "'").split())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="*", default=DEFAULT_SETS)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    from run_eval import load_snapshots
    import solution
    k = solution.Knowledge(use_facts=False)
    for s in load_snapshots(HERE.parent / "snapshots"):
        k.ingest(s)
    rows = []
    for f in a.sets:
        for l in open(HERE.parent / f):
            r = json.loads(l)
            if not r.get("must_include"):
                continue
            qu = k.understand(r["question"])
            hits = k.retrieve(r["question"], r.get("as_of"), qu=qu)
            text = norm(" ".join(c.text for _, c, _ in hits))
            need = [norm(m) for m in r["must_include"]]
            extras = [(round(sc, 3), any(n in norm(c.text) for n in need)) for sc, c, _ in hits if c.via.startswith("enrich")]
            rows.append({"set": Path(f).stem, "id": r["id"], "intent": (qu or {}).get("intent"), "hit": all(n in text for n in need),
                         "pieces": len(hits), "chars": sum(len(c.text) for _, c, _ in hits), "enrich_extras": extras})
    json.dump(rows, open(a.out, "w"))
    n = len(rows)
    print(f"{a.out}: n={n} recall={sum(r['hit'] for r in rows)/n:.3f} pieces={sum(r['pieces'] for r in rows)/n:.1f} chars={sum(r['chars'] for r in rows)/n:.0f}")


if __name__ == "__main__":
    main()
