"""Python side: window index search for the public questions on every snapshot (no API key needed: every vector is cached)."""
import json, sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "my_solution")); sys.path.insert(0, str(ROOT / "harness"))
os.environ.pop("OPENAI_API_KEY", None)
from chunker import chunk_page
import embed_index as E
import run_eval
questions = [json.loads(l)["question"] for l in open(ROOT / "eval/public_eval.jsonl") if l.strip()]
out = {}
store = E.EmbeddingStore(path=E.WINDOW_CACHE)
for s in run_eval.load_snapshots(ROOT / "snapshots"):
    chunks = []
    for p in s.pages: chunks += chunk_page(p.url, p.title, p.markdown, s.snapshot_id, p.fetched_at)
    wi = E.WindowIndex(chunks, store)
    out[s.snapshot_id] = {"n": len(wi.windows),
        "search": {q: [[round(sim, 5), ci, E.text_key(w)[:10]] for sim, ci, w in wi.search(q, k=10)] for q in questions}}
json.dump(out, open(sys.argv[1], "w"))
print({k: v["n"] for k, v in out.items()})
