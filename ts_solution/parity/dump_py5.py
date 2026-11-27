"""Python side: everything that feeds the answer model, for the public questions, using a shared Decisions-label cache.
Usage: dump_py5.py QU_CACHE FACTS_CACHE OUT.json   (makes no answer calls; ingest only warms up connections)"""
import hashlib, json, os, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
os.environ["MY_SOLUTION_QU_DEC_CACHE"] = sys.argv[1]
os.environ["MY_SOLUTION_FACT_CACHE"] = sys.argv[2]
sys.path.insert(0, str(ROOT / "my_solution")); sys.path.insert(0, str(ROOT / "harness"))
import solution, run_eval
ks = solution.build()
for s in run_eval.load_snapshots(ROOT / "snapshots"):
    ks.ingest(s)
items = [json.loads(l) for l in open(ROOT / "eval/public_eval.jsonl") if l.strip()]
h = lambda t: hashlib.sha1(t.encode()).hexdigest()[:10]
strip = lambda m: re.sub(r"[0-9a-f]{12}", "NONCE", m)
out = {}
for it in items:
    q, as_of = it["question"], it.get("as_of")
    qu = ks.understand(q)
    taken_on, sid, _ = ks._snapshot_for(q, as_of, qu)
    rec = {"sid": sid, "asked": ks._asked_note(q, as_of, qu), "intent": (qu or {}).get("intent"), "date": (qu or {}).get("website_date"),
           "scope": (qu or {}).get("time_scope"), "before_first": ks._before_first_snapshot(q, as_of, qu)}
    hits = ks.retrieve(q, as_of, qu=qu)
    rec["text_hits"] = [[c.url, h(c.text), urls] for _, c, urls in hits]
    rec["text_msg"] = strip(ks.user_message(q, hits, taken_on, rec["asked"]))
    fh = ks.fact_hits(q, sid, qu) if ks.facts else []
    rec["fact_hits"] = [[f.text, f.url, urls] for _, f, urls in fh]
    rec["fact_msg"] = strip(ks.user_message(q, fh, taken_on, rec["asked"])) if fh else None
    out[q] = rec
json.dump(out, open(sys.argv[3], "w"))
print(len(out), "questions dumped")
