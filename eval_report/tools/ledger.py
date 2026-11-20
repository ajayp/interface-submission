#!/usr/bin/env python3
"""Dollar cost of the calls recorded by usercustomize.py.  python eval_report/tools/ledger.py results/ledger.jsonl [--by tag]

Prices per 1M tokens (looked up 2026-11-20; standard tier, which every run here used):
  gpt-6-luna   input 0.10, cached input 0.01, output 0.50
  gpt-6.1-sol  input 2.00, cached input 0.10, output 10.00   (judge)
  decisions    input 0.10 (gpt-6-luna behind the Decisions API; output priced as gpt-6-luna output if any is reported)
  text-embedding-3-small  0.02
"""
import argparse
import collections
import json

PRICE = {  # (input, cached input, output) per 1M tokens
    ("responses", "gpt-6-luna"): (0.10, 0.01, 0.50),
    ("responses", "gpt-6.1-sol"): (2.00, 0.10, 10.00),
    ("decisions", "gpt-6-luna"): (0.10, 0.01, 0.50),
    ("embeddings", "text-embedding-3-small"): (0.02, 0.02, 0.0),
}


def cost(r):
    p = PRICE.get((r["api"], r.get("model")))
    if p is None:
        raise SystemExit(f"no price for {r['api']} {r.get('model')}")
    cached = r.get("cached") or 0
    return ((r["in"] - cached) * p[0] + cached * p[1] + (r.get("out") or 0) * p[2]) / 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ledger")
    ap.add_argument("--by", default="model", choices=["model", "tag", "name"])
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.ledger) if l.strip()]
    agg = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        k = f"{r['api']}:{r.get('model')}" if a.by == "model" else (r.get(a.by) or "-")
        agg[k]["calls"] += 1
        agg[k]["in"] += r["in"]
        agg[k]["cached"] += r.get("cached") or 0
        agg[k]["out"] += r.get("out") or 0
        agg[k]["usd"] += cost(r)
    total = 0.0
    print(f"{'key':48} {'calls':>7} {'input':>11} {'cached':>11} {'output':>9} {'USD':>8}")
    for k, v in sorted(agg.items(), key=lambda kv: -kv[1]["usd"]):
        total += v["usd"]
        print(f"{k[:48]:48} {v['calls']:7d} {v['in']:11d} {v['cached']:11d} {v['out']:9d} {v['usd']:8.4f}")
    print(f"{'TOTAL':48} {sum(v['calls'] for v in agg.values()):7d} {'':11} {'':11} {'':9} {total:8.4f}")


if __name__ == "__main__":
    main()
