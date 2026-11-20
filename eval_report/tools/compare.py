#!/usr/bin/env python3
"""Per-question comparison of every arm against the control (first arm) for one finished e2e stage.

    python eval_report/tools/compare.py --config eval_report/configs/stageA.json --dir results/e2e/stageA [--set public]

For each arm: mean weighted accuracy over its runs, the paired difference against the control with a 95% bootstrap interval
over QUESTIONS (each question's score averaged over that arm's runs first, so run noise is averaged before resampling),
the questions whose mean score moved by 0.5 or more, every stale hit (question, run, stale string), and pooled latency
percentiles over all of the arm's answers (more stable than the per-run p95 of 40 answers).
"""
import argparse
import csv
import json
import random
import statistics as st
from pathlib import Path


def load_runs(d: Path, s: str, arm: str):
    out = []
    for p in sorted(d.glob(f"{s}_{arm}[0-9]*")):
        if p.is_dir() and (p / "per_question.jsonl").exists() and not (p / "INVALID").exists() and p.name[len(s) + 1 + len(arm):].isdigit():
            out.append({json.loads(l)["id"]: json.loads(l) for l in (p / "per_question.jsonl").read_text().splitlines() if l.strip()})
    return out


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--set")
    ap.add_argument("--groups", help="optional JSON {id: subset name} for a per-subset breakdown")
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text())
    arms = list(cfg["arms"])
    groups = json.loads(Path(a.groups).read_text()) if a.groups else None
    for s in ([a.set] if a.set else list(cfg["sets"])):
        runs = {arm: load_runs(a.dir, s, arm) for arm in arms}
        ctl = runs[arms[0]]
        if not ctl:
            continue
        ids = list(ctl[0])
        w = {i: ctl[0][i]["weight"] for i in ids}
        W = sum(w.values())
        mean_q = lambda R: {i: st.mean(r[i]["score"] for r in R) for i in ids}
        base_q = mean_q(ctl)
        print(f"\n== {s}: control {arms[0]} ({len(ctl)} runs)")
        print(f"{'arm':14} {'n':>2} {'acc':>7} {'diff':>7} {'95% CI (questions)':>20} {'stale':>5} {'p50':>5} {'mean':>5} {'p95':>5} {'max':>5}  moved (control -> arm)")
        rng = random.Random(0)
        for arm in arms:
            R = runs[arm]
            if not R:
                continue
            q = mean_q(R)
            acc = [sum(r[i]["score"] * w[i] for i in ids) / W for r in R]
            d = {i: q[i] - base_q[i] for i in ids}
            diff = sum(d[i] * w[i] for i in ids) / W
            boots = []
            for _ in range(4000):
                sample = [rng.choice(ids) for _ in ids]
                boots.append(sum(d[i] * w[i] for i in sample) / sum(w[i] for i in sample))
            boots.sort()
            ci = f"[{boots[100]:+.3f}, {boots[3899]:+.3f}]" if arm != arms[0] else ""
            stale = [(i, n + 1, r[i]["trap_hits"]) for n, r in enumerate(R) for i in ids if r[i]["trap_hits"]]
            lat = [r[i]["latency_s"] for r in R for i in ids if not r[i].get("error")]
            moved = [f"{i} {base_q[i]:.2f}->{q[i]:.2f}" for i in ids if abs(d[i]) >= 0.5]
            print(f"{arm:14} {len(R):2d} {st.mean(acc):7.4f} {(diff if arm != arms[0] else 0):+7.4f} {ci:>20} {len(stale):5d} "
                  f"{pct(lat, .5):5.2f} {st.mean(lat):5.2f} {pct(lat, .95):5.2f} {max(lat):5.2f}  {'; '.join(moved)}")
            for x in stale:
                print(f"{'':16}stale: {x[0]} run {x[1]} {x[2]}")
            if groups:
                parts = []
                for g in sorted(set(groups.values())):
                    gi = [i for i in ids if groups.get(i) == g]
                    gw = sum(w[i] for i in gi) or 1
                    parts.append(f"{g} {sum(q[i] * w[i] for i in gi) / gw:.3f}")
                print(f"{'':16}by subset: " + ", ".join(parts))


if __name__ == "__main__":
    main()
