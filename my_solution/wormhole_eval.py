"""
Retrieval-only test of the wormhole switch (no answer model): do the pieces sent to the model contain the gold facts?

For each eval item: understand() once (the Decisions label is frozen across arms), then retrieve() under each arm.
  full  = every must_include value appears in the text of the retrieved pieces (scoring.contains, same matching as the scorer)
  trap  = some must_not_include value appears in them (a stale / other-tier value reached the model)
  chars = total characters of the pieces (a stand-in for prompt tokens)
Items with no must_include (should-refuse) only count trap and chars.

  python my_solution/wormhole_eval.py --eval eval/public_eval.jsonl [--eval ...] [--arms off,d2s,s2d,both] [--show 12]
Only retrieval is run: no facts, no answer call (an embedding call per new question, a Decisions call per question).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import scoring  # noqa: E402
from run_eval import load_snapshots  # noqa: E402
import solution  # noqa: E402
import wormhole as wh  # noqa: E402

KNOBS = {"fg": "FOREGROUND_K", "terms": "TERM_LIMIT", "minfg": "MIN_FG", "lift": "MIN_LIFT"}


def set_arm(sol, arm: str) -> None:
    """arm = mode or mode:knob=value,... e.g. d2s:lift=6,minfg=5,terms=4 (knobs: fg terms minfg lift; unlisted ones go back to the defaults)."""
    mode, _, kv = arm.partition(":")
    for k, name in KNOBS.items():
        setattr(wh, name, DEFAULTS[name])
    for part in filter(None, kv.split(",")):
        k, v = part.split("=")
        setattr(wh, KNOBS[k], float(v) if k == "lift" else int(v))
    sol.wormhole = mode


DEFAULTS = {n: getattr(wh, n) for n in KNOBS.values()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", action="append", required=True)
    ap.add_argument("--arms", default="off,d2s,s2d,both")
    ap.add_argument("--snapshots", default=str(ROOT / "snapshots"))
    ap.add_argument("--show", type=int, default=10, help="how many changed questions to print per arm")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    arms = a.arms.split("|") if "|" in a.arms else a.arms.split(",")

    sol = solution.Knowledge(use_facts=False)
    for snap in load_snapshots(Path(a.snapshots)):
        sol.ingest(snap)

    report = {}
    for path in a.eval:
        items = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        qus = {}
        for it in items:
            qus[it["id"]] = sol.understand(it["question"])
        res = {arm: {} for arm in arms}
        terms = {}
        for arm in arms:
            set_arm(sol, arm)
            for it in items:
                sol._last_wormhole_terms = []
                hits = sol.retrieve(it["question"], it.get("as_of"), qu=qus[it["id"]])
                text = "\n".join(c.text for _, c, _ in hits)
                must, not_ = it.get("must_include") or [], it.get("must_not_include") or []
                res[arm][it["id"]] = {
                    "full": bool(must) and all(scoring.contains(text, m) for m in must) if must else None,
                    "found": sum(scoring.contains(text, m) for m in must) if must else None,
                    "trap": any(scoring.contains(text, t) for t in not_),
                    "chars": len(text), "n": len(hits),
                }
                if arm.split(":")[0] in ("d2s", "both"):
                    terms[it["id"]] = [t for t, _ in getattr(sol, "_last_wormhole_terms", [])]
        name = Path(path).stem
        print(f"\n=== {name}  ({len(items)} items)")
        print(f"{'arm':6} {'full-hit':>10} {'facts-found':>12} {'trap':>5} {'avg chars':>10}")
        for arm in arms:
            r = list(res[arm].values())
            gold = [x for x in r if x["full"] is not None]
            full = sum(1 for x in gold if x["full"])
            fnd = sum(x["found"] for x in gold)
            tot = sum(len(it.get("must_include") or []) for it in items)
            print(f"{arm:6} {full:>4}/{len(gold):<5} {fnd:>5}/{tot:<6} {sum(x['trap'] for x in r):>5} {sum(x['chars'] for x in r) / len(r):>10.0f}")
        base = res[arms[0]]
        for arm in arms[1:]:
            ch = [(it["id"], base[it["id"]]["full"], res[arm][it["id"]]["full"], base[it["id"]]["trap"], res[arm][it["id"]]["trap"])
                  for it in items if (base[it["id"]]["full"], base[it["id"]]["trap"]) != (res[arm][it["id"]]["full"], res[arm][it["id"]]["trap"])]
            print(f"  {arm} vs {arms[0]}: {len(ch)} items differ (id, full {arms[0]}->{arm}, trap {arms[0]}->{arm})")
            for c in ch[:a.show]:
                extra = f"  terms={terms.get(c[0])}" if arm.split(":")[0] in ("d2s", "both") else ""
                print("   ", c, extra)
        report[name] = {"res": res, "terms": terms}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
