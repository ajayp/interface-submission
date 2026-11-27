"""Python side: tables, facts (from a cache file, no API), grouping/winners, fact search, count facts. Usage: dump_py4.py FACTS_CACHE OUT.json"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "my_solution")); sys.path.insert(0, str(ROOT / "harness"))
from chunker import published_date
from facts import FactExtractor, group_facts, page_tables, table_key, winner
from count_facts import count_facts, count_question, answer_text, latest
from search import BM25Index
import run_eval

questions = [json.loads(l)["question"] for l in open(ROOT / "eval/public_eval.jsonl") if l.strip()]
fx = FactExtractor(None, Path(sys.argv[1]))
out = {}
for s in run_eval.load_snapshots(ROOT / "snapshots"):
    tables = [(t, published_date(p.url, p.markdown)) for p in s.pages for t in page_tables(p.url, p.title, p.markdown)]
    facts = [f for t, pub in tables for f in fx.facts_for(t, s.snapshot_id, pub)]
    idx = BM25Index(facts)
    groups = group_facts(facts)
    cf = count_facts(s.pages)
    out[s.snapshot_id] = {
        "tables": [[table_key(t)[:12], t["caption"], t["effective"], t["note"][:60]] for t, _ in tables],
        "facts": [[f.text, f.url, f.effective, f.published, f.page_type, f.key().__repr__()] for f in facts],
        "groups": [[len(g), winner(g).text, winner(g).url] for g in groups],
        "search": {q: [[round(sc, 5), facts.index(f)] for sc, f in idx.search(q, k=20)] for q in questions},
        "counts": [[c.measure, c.value, c.url, c.published, c.sentence] for c in cf],
        "count_q": {q: count_question(q) for q in questions},
    }
json.dump(out, open(sys.argv[2], "w"))
print({k: (len(v["tables"]), len(v["facts"]), len(v["groups"]), len(v["counts"])) for k, v in out.items()})
