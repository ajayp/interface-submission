#!/usr/bin/env python3
"""Retrieval-only screening of many arms (rcheck.py once per arm, sequentially, same protective environment as e2e.py).

    python eval_report/tools/screen.py --config eval_report/configs/screen.json --out results/rc [--only arm1 arm2]

Config: {"sets": [...eval files...], "arms": {"base": {}, "s800": {"MY_SOLUTION_SPLIT_CHARS": "800",
         "MY_SOLUTION_WINDOW_CACHE": "results/win_s800.npz"}}, "hyde": {"arm": ["results/hyde.json", "concat"]}}
A window-cache path in an arm is first created as a COPY of the committed window file (so only new windows are embedded, and
the committed file is never written). An arm is INVALID if its log shows a rate limit or meaning search switched off.
"""
import argparse
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e import BAD, REPO, base_env, bad_lines, prepare_copies  # noqa: E402

COMMITTED_WINDOWS = REPO / "my_solution" / ".embed_cache" / "windows-text-embedding-3-small.npz"


def summary(rows):
    out = defaultdict(lambda: [0, 0, 0, 0])   # n, hits, chars, pieces
    for r in rows:
        if r["path"] not in ("text", "facts", "history"):
            continue
        for key in ((r["set"], r["path"]), ("ALL", r["path"])):
            o = out[key]; o[0] += 1; o[1] += bool(r["hit"]); o[2] += r["chars"]; o[3] += r["pieces"]
    return {f"{s}|{p}": {"n": v[0], "recall": round(v[1] / v[0], 4), "chars": round(v[2] / v[0]), "pieces": round(v[3] / v[0], 2)}
            for (s, p), v in sorted(out.items())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--revalidate", action="store_true", help="re-scan logs of arms left as .tmp.json with the current BAD list")
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text())
    a.out.mkdir(parents=True, exist_ok=True)
    prepare_copies()
    if a.revalidate:
        for t in a.out.glob("*.tmp.json"):
            arm = t.name[:-len(".tmp.json")]
            bad = bad_lines(a.out / f"{arm}.log")
            print(f"{arm}: {'still INVALID ' + str(bad[:2]) if bad else 'valid, accepted'}")
            if not bad:
                t.rename(a.out / f"{arm}.json")
    for arm, sw in cfg["arms"].items():
        if a.table or a.revalidate or (a.only and arm not in a.only) or (a.out / f"{arm}.json").exists():
            continue
        env = base_env(f"rc:{arm}")
        env["MY_SOLUTION_QU_DEC_CACHE"] = str(REPO / "results" / "qu_labels.json")   # frozen labels shared by every arm
        for k, v in sw.items():
            if k == "MY_SOLUTION_WINDOW_CACHE":
                v = str((REPO / v).resolve())
                if not Path(v).exists():
                    shutil.copy(COMMITTED_WINDOWS, v)
            env[k] = str(v)
        cmd = [sys.executable, str(REPO / "eval_report/tools/rcheck.py"), "--sets", *cfg["sets"], "--out", str(a.out / f"{arm}.tmp.json")]
        if arm in cfg.get("hyde", {}):
            f, mode = cfg["hyde"][arm]
            cmd += ["--hyde", str(REPO / f), "--hyde-mode", mode]
        log = a.out / f"{arm}.log"
        with open(log, "w") as fh:
            subprocess.run(cmd, cwd=REPO, env=env, stdout=fh, stderr=subprocess.STDOUT)
        bad = bad_lines(log)
        if bad or not (a.out / f"{arm}.tmp.json").exists():
            print(f"{arm}: INVALID {bad[:2]}", flush=True)
            continue
        (a.out / f"{arm}.tmp.json").rename(a.out / f"{arm}.json")
        print(f"{arm}: done  " + (log.read_text().strip().splitlines() or [''])[-1], flush=True)
    res = {arm: summary(json.loads((a.out / f"{arm}.json").read_text())) for arm in cfg["arms"] if (a.out / f"{arm}.json").exists()}
    (a.out / "summary.json").write_text(json.dumps(res, indent=1))
    keys = ["ALL|text", "ALL|facts", "ALL|history"]
    print(f"{'arm':22}" + "".join(f"{k:>26}" for k in keys))
    for arm, s in res.items():
        print(f"{arm:22}" + "".join(f"{(str(s[k]['recall']) + ' / ' + str(s[k]['chars'])) if k in s else '-':>26}" for k in keys))


if __name__ == "__main__":
    main()
