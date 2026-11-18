#!/usr/bin/env python3
"""
One resumable regression run: every eval set against every arm (a set of environment switches), N runs each, scored with the judge.

    python my_solution/regress.py --config tasks/regress_example.json --out results/regress          # run what is missing, then the table
    python my_solution/regress.py --config tasks/regress_example.json --out results/regress --table  # only read finished runs

A run is finished when <out>/<set>_<arm><n>/judged.jsonl exists, so a restart of the machine loses at most the runs in progress:
start the same command again and it skips everything done. Arms are interleaved (run 1 of each arm, then run 2 ...) so API drift
hits every arm alike. The first arm is the control: the table shows each other arm's accuracy change and the questions that moved.

Config (JSON):
  {"repo": ".",                               # folder with harness/ and my_solution/ (default: this repo; use a clone to test uncommitted work)
   "runs": 3, "workers": 3,
   "fact_cache": "results/heldout/fact_cache.json",   # copied once per worker so parallel runs never write the same file (optional)
   "arms": {"base": {"env": {}}, "new": {"env": {"MY_SOLUTION_SOMETHING": "1"}}},
   "sets": [{"name": "public", "eval": "eval/public_eval.jsonl", "arms": ["base", "new"], "repeat_sample": 20}]}   # arms optional (default all)
"""
import argparse
import json
import os
import shutil
import queue
import statistics as st
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent


def jobs(cfg, runs):
    arms = cfg["arms"]
    out = []
    for n in range(1, runs + 1):
        for s in cfg["sets"]:
            for a in s.get("arms", list(arms)):
                out.append((s, a, n))
    return out


def run_one(cfg, repo, out_dir, job, slot):
    s, arm, n = job
    name = f"{s['name']}_{arm}{n}"
    d = out_dir / name
    if (d / "judged.jsonl").exists() and not api_failed(out_dir, name):
        return name, "skipped"
    env = {**os.environ, **{k: str(v) for k, v in cfg["arms"][arm].get("env", {}).items()}}
    if cfg.get("fact_cache"):
        slot_cache = out_dir / f"_fact_cache_{slot}.json"
        if not slot_cache.exists():
            shutil.copy(Path(cfg["fact_cache"]), slot_cache)
        env["MY_SOLUTION_FACT_CACHE"] = str(slot_cache.resolve())
    ev = str(Path(s["eval"]))
    shutil.rmtree(d, ignore_errors=True)
    with open(out_dir / f"{name}.log", "w") as log:
        r = subprocess.run([sys.executable, "harness/run_eval.py", "--submission", "my_solution", "--eval", ev,
                            "--repeat-sample", str(s.get("repeat_sample", 20)), "--out", str(d.resolve())],
                           cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
    if r.returncode != 0 or not (d / "per_question.jsonl").exists():
        return name, "FAILED (see log)"
    with open(out_dir / f"{name}.judge.log", "w") as log:
        subprocess.run([sys.executable, "my_solution/judge_eval.py", "--results", str((d / "per_question.jsonl").resolve()), "--eval", ev],
                       cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
    if api_failed(out_dir, name):
        return name, "INVALID: model calls failed (rate limit or outage); it will run again next time"
    return name, "done" if (d / "judged.jsonl").exists() else "judge FAILED"


API_FAIL = ("RateLimitError", "LLM call failed", "decisions call failed", "insufficient_quota", "AuthenticationError")


def api_failed(out_dir, name):
    """A run whose model calls failed (spend limit, bad key, outage) answers "I don't know" to everything: its numbers are not results."""
    log = out_dir / f"{name}.log"
    return log.exists() and any(k in log.read_text(errors="ignore") for k in API_FAIL)


def load(d):
    r = json.loads((d / "report.json").read_text())
    rows = {json.loads(l)["id"]: json.loads(l) for l in (d / "per_question.jsonl").read_text().splitlines() if l.strip()}
    J = [json.loads(l) for l in (d / "judged.jsonl").read_text().splitlines() if l.strip()]
    w = sum(j["weight"] for j in J) or 1
    return {"acc": r["qa_score"], "judged": sum((j["score_judged"] or 0) * j["weight"] for j in J) / w,
            "stale": r["stale_trap_hits"], "err": r["errors"], "p95": r["speed"]["p95_s"], "rows": rows,
            "refuse": [x["score"] for x in rows.values() if x["category"] == "should_refuse"]}


def table(cfg, runs, out_dir):
    arms = list(cfg["arms"])
    print(f"{'set':18} {'arm':8} {'runs':>4} {'accuracy':>8} {'judged':>6} {'stale':>5} {'err':>3} {'refuse':>6} {'p95':>5}  runs")
    for s in cfg["sets"]:
        res = {}
        for a in s.get("arms", arms):
            bad = [n for n in range(1, runs + 1) if (out_dir / f"{s['name']}_{a}{n}" / "judged.jsonl").exists()
                   and api_failed(out_dir, f"{s['name']}_{a}{n}")]
            if bad:
                print(f"{s['name']:18} {a:8} IGNORED runs {bad}: model calls failed (rate limit or outage); they run again next time")
            R = [load(out_dir / f"{s['name']}_{a}{n}") for n in range(1, runs + 1)
                 if (out_dir / f"{s['name']}_{a}{n}" / "judged.jsonl").exists() and n not in bad]
            res[a] = R
            if not R:
                print(f"{s['name']:18} {a:8} {0:>4}  (no finished runs)")
                continue
            ref = [x for r in R for x in r["refuse"]]
            first = arms[0] if arms[0] in res and res[arms[0]] else None
            delta = "" if a == first or not first else f"  ({st.mean(r['acc'] for r in R) - st.mean(r['acc'] for r in res[first]):+.3f} vs {first})"
            print(f"{s['name']:18} {a:8} {len(R):>4} {st.mean(r['acc'] for r in R):8.3f} {st.mean(r['judged'] for r in R):6.3f} "
                  f"{sum(r['stale'] for r in R):>5} {sum(r['err'] for r in R):>3} {(f'{st.mean(ref):.2f}' if ref else '-'):>6} "
                  f"{st.mean(r['p95'] for r in R):5.1f}  {[round(r['acc'], 3) for r in R]}{delta}")
        ctl = next((a for a in s.get("arms", arms) if res.get(a)), None)
        for a, R in res.items():
            if a == ctl or not R or not res.get(ctl):
                continue
            for i in res[ctl][0]["rows"]:
                mo = st.mean(r["rows"][i]["score"] for r in res[ctl] if i in r["rows"])
                mn = st.mean(r["rows"][i]["score"] for r in R if i in r["rows"])
                if abs(mo - mn) > 0.15:
                    print(f"      moved: {i} {mo:.2f} -> {mn:.2f} ({ctl} -> {a})  {res[ctl][0]['rows'][i]['category']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--table", action="store_true", help="only print the table from finished runs")
    ap.add_argument("--runs", type=int)
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text())
    repo = Path(cfg.get("repo", HERE.parent)).resolve()
    runs = a.runs or cfg.get("runs", 3)
    a.out.mkdir(parents=True, exist_ok=True)
    if not a.table:
        todo = [j for j in jobs(cfg, runs) if not ((a.out / f"{j[0]['name']}_{j[1]}{j[2]}" / "judged.jsonl").exists()
                                                    and not api_failed(a.out, f"{j[0]['name']}_{j[1]}{j[2]}"))]
        print(f"{len(todo)} runs to do ({len(jobs(cfg, runs)) - len(todo)} already finished)", flush=True)
        workers = cfg.get("workers", 3)
        slots = queue.Queue()
        for i in range(workers):
            slots.put(i)   # one fact-cache copy per concurrent worker, so two runs never write the same file

        def worker(j):
            slot = slots.get()
            try:
                name, status = run_one(cfg, repo, a.out, j, slot)
            finally:
                slots.put(slot)
            print(f"  {name}: {status}", flush=True)
        with ThreadPoolExecutor(workers) as pool:
            list(pool.map(worker, todo))
    table(cfg, runs, a.out)


if __name__ == "__main__":
    main()
