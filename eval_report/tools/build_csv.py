#!/usr/bin/env python3
"""Build eval_report/results.csv from the finished runs.

    python eval_report/tools/build_csv.py --e2e results/e2e/stageA results/e2e/stageB --rc results/rc --out eval_report/results.csv

Rows:
  kind=e2e        one per (set, arm, run): harness accuracy, judged (if scored), stale hits, latency p50/mean/p95/max (s),
                  recall (retrieval-only recall of that arm on the same eval file, all paths that use text search), chars sent to
                  the answer model per question (sum over the question's answer calls, excerpt headers included)
  kind=e2e_mean   the mean over that arm's runs (runs = how many)
  kind=retrieval  one per screened arm (no answer calls): recall over the 5 eval files on the text path, characters of the user message
                  on the text path; accuracy/latency empty
"""
import argparse
import csv
import json
import statistics as st
from pathlib import Path

SET_FILE = {"public": "public_eval", "typo": "typo_robustness", "heldout": "heldout", "temporal": "heldout_temporal",
            "branch": "slice2_branch_contact"}
COLS = ["kind", "set", "arm", "runs", "accuracy", "judged", "stale", "p50", "mean", "p95", "max", "recall", "chars_sent", "note"]


def rc_recall(rc_dir: Path, arm: str, set_stem: str):
    f = rc_dir / f"{arm}.json"
    if not f.exists():
        return None
    R = [r for r in json.loads(f.read_text()) if r["set"] == set_stem and r["path"] in ("text", "facts", "history")]
    return round(sum(bool(r["hit"]) for r in R) / len(R), 4) if R else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--e2e", nargs="*", default=[])
    ap.add_argument("--rc", type=Path)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = []
    for d in map(Path, a.e2e):
        if not (d / "runs.csv").exists():
            continue
        runs = list(csv.DictReader(open(d / "runs.csv")))
        groups = {}
        for r in runs:
            groups.setdefault((r["set"], r["arm"]), []).append(r)
        for (s, arm), R in groups.items():
            rec = rc_recall(a.rc, arm, SET_FILE.get(s, s)) if a.rc else None
            for r in sorted(R, key=lambda x: int(x["run"])):
                rows.append({"kind": "e2e", "set": s, "arm": arm, "runs": r["run"], "accuracy": r["accuracy"],
                             "judged": r["judged"] or "", "stale": r["stale"], "p50": r["p50"], "mean": r["mean"], "p95": r["p95"],
                             "max": r["max"], "recall": rec if rec is not None else "", "chars_sent": r["chars_per_q"], "note": d.name})
            f = lambda k: round(st.mean(float(x[k]) for x in R), 4)
            js = [float(x["judged"]) for x in R if x["judged"]]
            rows.append({"kind": "e2e_mean", "set": s, "arm": arm, "runs": len(R), "accuracy": f("accuracy"),
                         "judged": round(st.mean(js), 4) if js else "", "stale": sum(int(x["stale"]) for x in R),
                         "p50": f("p50"), "mean": f("mean"), "p95": f("p95"), "max": f("max"),
                         "recall": rec if rec is not None else "", "chars_sent": round(f("chars_per_q")), "note": d.name})
    if a.rc:
        summ = json.loads((a.rc / "summary.json").read_text()) if (a.rc / "summary.json").exists() else {}
        for f in sorted(a.rc.glob("*.json")):
            if f.name in ("summary.json",) or f.name.endswith(".tmp.json"):
                continue
            R = [r for r in json.loads(f.read_text()) if r["path"] == "text"]
            if not R:
                continue
            rows.append({"kind": "retrieval", "set": "5 sets, text path", "arm": f.stem, "runs": 1, "accuracy": "", "judged": "",
                         "stale": "", "p50": "", "mean": "", "p95": "", "max": "",
                         "recall": round(sum(bool(r["hit"]) for r in R) / len(R), 4),
                         "chars_sent": round(sum(r["chars"] for r in R) / len(R)), "note": f"n={len(R)} questions"})
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader(); w.writerows(rows)
    print(f"{a.out}: {len(rows)} rows")


if __name__ == "__main__":
    main()
