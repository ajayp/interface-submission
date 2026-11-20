#!/usr/bin/env python3
"""End-to-end A/B runner for the independent evaluation (harness/run_eval.py, unchanged, one process per run).

    python eval_report/tools/e2e.py --config eval_report/configs/<name>.json --out results/e2e/<name>

- Runs are SEQUENTIAL (one at a time): parallel runs share the network, distort latency, and hit the embedding rate limit.
- Arms are interleaved (run 1 of every arm, then run 2 ...) and the arm order rotates each round, so API drift over time and
  position effects hit every arm alike.
- Every run gets the same protective environment: committed vector files are never written (question vectors go to a copy
  under results/), extracted facts come from one shared cache, and every OpenAI call is recorded in the spend ledger.
- A run is INVALID (re-run on the next call) if its log shows a rate limit, failed model calls, or meaning search switched off.
- Resumable: a finished valid run is skipped. Summary rows go to <out>/runs.csv; `--table` only prints the summary.

Config: {"runs": 3, "sets": {"public": "eval/public_eval.jsonl"}, "arms": {"base": {}, "k6": {"MY_SOLUTION_TOP_K": "6"}},
         "repeat_sample": 0}
"""
import argparse
import csv
import json
import os
import shutil
import statistics as st
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
RESULTS = REPO / "results"
# "N windows have no vector ... embedding them now" is NOT a failure (new window texts are embedded at ingest by design);
# only "meaning search is off" / "units have no vector" mean the search was really switched off.
BAD = ("RateLimit", "rate_limit", "Error code: 429", "Too Many Requests", "meaning search is off", "LLM call failed", "decisions call failed",
       "enrichment index unavailable", "units have no vector", "embedding search failed", "enrichment search failed",
       "window index unavailable", "rerank failed", "insufficient_quota", "AuthenticationError")


def base_env(tag: str) -> dict:
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(TOOLS) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
        "EVAL_LEDGER": str(RESULTS / "ledger.jsonl"),
        "EVAL_TAG": tag,
        "MY_SOLUTION_FACT_CACHE": str(RESULTS / "fact_cache.json"),
        "MY_SOLUTION_QUESTION_CACHE": str(RESULTS / "question_vectors.npz"),
        "MY_SOLUTION_ENRICH_VEC_CACHE": str(RESULTS / "enrich_vectors.npz"),
        "MY_SOLUTION_USAGE": "1",
        "MY_SOLUTION_NONCE_SALT": tag,   # every run starts with cold evidence in the prompt cache, as graded questions do
    })
    return env


def prepare_copies() -> None:
    """Copies of the committed vector files, so nothing a run embeds is written into my_solution/.embed_cache."""
    RESULTS.mkdir(exist_ok=True)
    src = REPO / "my_solution" / ".embed_cache"
    for name, dst in (("questions-text-embedding-3-small.npz", "question_vectors.npz"),
                      ("enrich-text-embedding-3-small.npz", "enrich_vectors.npz")):
        if not (RESULTS / dst).exists():
            shutil.copy(src / name, RESULTS / dst)


def bad_lines(log: Path) -> list:
    if not log.exists():
        return ["no log"]
    return [l.strip()[:200] for l in log.read_text(errors="ignore").splitlines() if any(b in l for b in BAD)]


def pctl(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]   # same rule as harness/scoring.py


def summarize(d: Path, tag: str) -> dict:
    rep = json.loads((d / "report.json").read_text())
    rows = [json.loads(l) for l in (d / "per_question.jsonl").read_text().splitlines() if l.strip()]
    lat = [r["latency_s"] for r in rows if not r.get("error")]
    led = [json.loads(l) for l in (RESULTS / "ledger.jsonl").read_text().splitlines() if l.strip()]
    ans = [r for r in led if r.get("tag") == tag and r.get("name") == "member_answer"]
    n = len(rows)
    judged = None
    if (d / "judged.jsonl").exists():
        J = [json.loads(l) for l in (d / "judged.jsonl").read_text().splitlines() if l.strip()]
        w = sum(j["weight"] for j in J) or 1
        judged = round(sum((j["score_judged"] or 0) * j["weight"] for j in J) / w, 4)
    return {"accuracy": rep["qa_score"], "judged": judged, "stale": rep["stale_trap_hits"], "errors": rep["errors"],
            "p50": round(pctl(lat, 0.5), 2), "mean": round(st.mean(lat), 2), "p95": round(pctl(lat, 0.95), 2),
            "max": round(max(lat), 2), "answer_calls": len(ans),
            "chars_per_q": round(sum(r["chars"] or 0 for r in ans) / n), "in_tok_per_q": round(sum(r["in"] for r in ans) / n),
            "chars_per_call": round(sum(r["chars"] or 0 for r in ans) / max(1, len(ans))),
            "refusals": sum(1 for r in rows if r["answer"]["text"].startswith("I don't know")),
            "ingest_s": rep.get("ingest_seconds")}


def run(cfg, out: Path, set_name: str, arm: str, n: int, judge: bool) -> dict:
    d = out / f"{set_name}_{arm}{n}"
    # a retry of an INVALID run gets its own ledger tag, so its chars/tokens are not added to the failed attempt's
    tag = f"{out.name}:{set_name}_{arm}{n}" + (f"#retry{int(time.time())}" if (d / "INVALID").exists() else "")
    log = out / f"{set_name}_{arm}{n}.log"
    env = base_env(tag)
    env.update({k: str(v) for k, v in cfg["arms"][arm].items()})
    shutil.rmtree(d, ignore_errors=True)
    t = time.time()
    with open(log, "w") as f:
        subprocess.run([sys.executable, "harness/run_eval.py", "--submission", "my_solution", "--eval", cfg["sets"][set_name],
                        "--repeat-sample", str(cfg.get("repeat_sample", 0)), "--out", str(d)],
                       cwd=REPO, env=env, stdout=f, stderr=subprocess.STDOUT)
    if judge and (d / "per_question.jsonl").exists():
        with open(out / f"{set_name}_{arm}{n}.judge.log", "w") as f:
            subprocess.run([sys.executable, "my_solution/judge_eval.py", "--results", str(d / "per_question.jsonl"),
                            "--eval", cfg["sets"][set_name]], cwd=REPO, env=env, stdout=f, stderr=subprocess.STDOUT)
    bad = bad_lines(log)
    if bad or not (d / "report.json").exists():
        (d / "INVALID").parent.mkdir(parents=True, exist_ok=True)
        (d / "INVALID").write_text("\n".join(bad) or "no report")
        print(f"  {set_name}_{arm}{n}: INVALID ({len(bad)} bad log lines, e.g. {bad[:1]})", flush=True)
        return {}
    s = summarize(d, tag)
    s.update(set=set_name, arm=arm, run=n, wall_s=round(time.time() - t))
    print(f"  {set_name}_{arm}{n}: acc {s['accuracy']:.4f} stale {s['stale']} p50 {s['p50']} p95 {s['p95']} "
          f"chars/q {s['chars_per_q']} ({s['wall_s']} s)", flush=True)
    return s


FIELDS = ["set", "arm", "run", "accuracy", "judged", "stale", "errors", "refusals", "p50", "mean", "p95", "max", "answer_calls",
          "chars_per_q", "chars_per_call", "in_tok_per_q", "ingest_s", "wall_s"]


def table(out: Path, cfg) -> None:
    p = out / "runs.csv"
    if not p.exists():
        print("no runs yet"); return
    rows = list(csv.DictReader(open(p)))
    arms = list(cfg["arms"])
    for s in cfg["sets"]:
        base = [float(r["accuracy"]) for r in rows if r["set"] == s and r["arm"] == arms[0]]
        print(f"\n{s}: {'arm':14} {'n':>2} {'acc':>7} {'sd':>6} {'d_vs_'+arms[0]:>10} {'stale':>5} {'p50':>5} {'mean':>5} {'p95':>5} {'max':>5} {'chars/q':>8} {'tok/q':>6}")
        for a in arms:
            R = [r for r in rows if r["set"] == s and r["arm"] == a]
            if not R:
                continue
            acc = [float(r["accuracy"]) for r in R]
            f = lambda k: st.mean(float(r[k]) for r in R)
            d = f"{st.mean(acc) - st.mean(base):+.4f}" if base and a != arms[0] else ""
            print(f"{'':8}{a:14} {len(R):2d} {st.mean(acc):7.4f} {(st.stdev(acc) if len(acc) > 1 else 0):6.4f} {d:>10} "
                  f"{sum(int(r['stale']) for r in R):5d} {f('p50'):5.2f} {f('mean'):5.2f} {f('p95'):5.2f} {f('max'):5.2f} "
                  f"{f('chars_per_q'):8.0f} {f('in_tok_per_q'):6.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--runs", type=int)
    ap.add_argument("--judge", action="store_true", help="also score with my_solution/judge_eval.py (gpt-6.1-sol, costly)")
    ap.add_argument("--table", action="store_true")
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text())
    a.out.mkdir(parents=True, exist_ok=True)
    if not a.table:
        prepare_copies()
        runs = a.runs or cfg.get("runs", 3)
        arms = list(cfg["arms"])
        done = set()
        if (a.out / "runs.csv").exists():
            done = {(r["set"], r["arm"], int(r["run"])) for r in csv.DictReader(open(a.out / "runs.csv"))}
        for n in range(1, runs + 1):
            order = arms[(n - 1) % len(arms):] + arms[:(n - 1) % len(arms)]
            for s in cfg["sets"]:
                for arm in order:
                    if (s, arm, n) in done:
                        continue
                    row = run(cfg, a.out, s, arm, n, a.judge)
                    if row:
                        new = not (a.out / "runs.csv").exists()
                        with open(a.out / "runs.csv", "a", newline="") as f:
                            w = csv.DictWriter(f, fieldnames=FIELDS)
                            if new:
                                w.writeheader()
                            w.writerow({k: row.get(k) for k in FIELDS})
    table(a.out, cfg)


if __name__ == "__main__":
    main()
