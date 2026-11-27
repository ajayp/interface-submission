"""Python side: the evidence of the "what changed" path (_history_hits) for every question of the given files whose label says change.
Usage: dump_py6.py QU_CACHE FACTS_CACHE OUT.json FILE.jsonl..."""
import hashlib, json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
os.environ["MY_SOLUTION_QU_DEC_CACHE"] = sys.argv[1]
os.environ["MY_SOLUTION_FACT_CACHE"] = sys.argv[2]
sys.path.insert(0, str(ROOT / "my_solution")); sys.path.insert(0, str(ROOT / "harness"))
import solution, run_eval
ks = solution.build()
for s in run_eval.load_snapshots(ROOT / "snapshots"):
    ks.ingest(s)
h = lambda t: hashlib.sha1(t.encode()).hexdigest()[:10]
out = {}
for f in sys.argv[4:]:
    for l in open(f):
        if not l.strip(): continue
        it = json.loads(l); q = it["question"]
        qu = ks.understand(q)
        if (qu or {}).get("time_scope") != "change": continue
        hits = ks._history_hits(q, it.get("as_of"), qu)
        out[q] = {"as_of": it.get("as_of"), "hits": [[c.url, h(c.text), urls, copies] for _, c, urls, copies in hits]}
json.dump(out, open(sys.argv[3], "w"))
print(len(out), "change questions dumped")
