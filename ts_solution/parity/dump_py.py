"""Python side of the parity test: chunks + BM25 rankings for every snapshot / question. Usage: dump_py.py OUT.json"""
import hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "my_solution")); sys.path.insert(0, str(ROOT / "harness"))
from chunker import chunk_page
from categories import categories_for
from search import BM25Index
import run_eval

snaps = run_eval.load_snapshots(ROOT / "snapshots")
questions = [json.loads(l)["question"] for l in open(ROOT / "eval/public_eval.jsonl") if l.strip()]
out = {}
for s in snaps:
    chunks = []
    for p in s.pages:
        chunks += chunk_page(p.url, p.title, p.markdown, s.snapshot_id, p.fetched_at)
    for c in chunks:
        caption = c.text.split(" | ")[0] if c.kind == "row" else ""
        c.categories = tuple(categories_for(c.url, f"{c.header_path} {c.heading} {caption}", c.text))
    idx = BM25Index(chunks)
    key = lambda c: hashlib.sha1(c.text.encode()).hexdigest()[:12]
    out[s.snapshot_id] = {
        "chunks": [[c.url, c.kind, c.heading, c.header_path, c.effective, c.published, list(c.categories), key(c)] for c in chunks],
        "search": {q: [[round(sc, 6), chunks.index(c)] for sc, c in idx.search(q, k=8)] for q in questions},
    }
json.dump(out, open(sys.argv[1], "w"))
print({k: len(v["chunks"]) for k, v in out.items()})
