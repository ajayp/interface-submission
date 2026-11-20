#!/usr/bin/env python3
"""HyDE inputs for the retrieval-only check: one hypothetical website passage per question (gpt-6-luna, effort none, temperature 0),
plus the latency of each call, because HyDE puts this call on the timed path of every answer.

    python eval_report/tools/hyde.py --sets eval/public_eval.jsonl ... --out results/hyde.json
"""
import argparse
import json
import statistics as st
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SYSTEM = ("You write text as it would appear on the website of a US credit union. Given a member's question, write 2 to 3 "
          "sentences of website text that would answer it. If you do not know a detail, write a plausible one. Do not say that "
          "you do not know, and do not address the member.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    qs = []
    for f in a.sets:
        for line in open(REPO / f):
            if line.strip():
                r = json.loads(line)
                if r.get("must_include") and r["question"] not in qs:
                    qs.append(r["question"])
    from openai import OpenAI
    client = OpenAI(timeout=20, max_retries=1)

    def one(q):
        t = time.time()
        r = client.responses.create(model="gpt-6-luna", instructions=SYSTEM, input=q, reasoning={"effort": "none"},
                                    temperature=0, max_output_tokens=160)
        return q, r.output_text.strip(), time.time() - t

    with ThreadPoolExecutor(2) as ex:
        res = list(ex.map(one, qs))
    Path(a.out).write_text(json.dumps({q: h for q, h, _ in res}, indent=1))
    lat = sorted(s for _, _, s in res)
    p = lambda x: lat[min(len(lat) - 1, int(x * len(lat)))]
    stats = {"n": len(lat), "p50": round(p(0.5), 3), "mean": round(st.mean(lat), 3), "p95": round(p(0.95), 3), "max": round(lat[-1], 3)}
    Path(a.out).with_suffix(".latency.json").write_text(json.dumps(stats))
    print(stats)


if __name__ == "__main__":
    main()
