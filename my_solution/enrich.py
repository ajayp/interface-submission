"""Ingest-time chunk enrichment (Contextual Retrieval + propositions + hypothetical questions).

One gpt-6-luna call per prose chunk writes three extra, SEARCH-ONLY fields:
  context_line  - where the chunk sits (page / program / branch); a status word only if the text states it
  propositions  - standalone factual statements that name their subject (Chen et al., "Dense X Retrieval")
  questions     - how a member might ask what the chunk answers (doc2query / hypothetical questions)

The answer prompt never sees them: they only widen what the search can find, and the parent chunk's ORIGINAL text is what is
returned. Every number in a generated item must appear in the source (title, url, heading, text, date) or the item is dropped,
so the "no stale or invented value" rule holds.

Results are cached on disk by chunk content (.enrich_cache/enrich-v2.json, committed, shared by all website copies), so grading
never calls the model. Switch (experiments): MY_SOLUTION_ENRICH = comma list of
  ctx   add the context line to the keyword (BM25) text      q     add the questions to the keyword text
  prop  add the propositions to the keyword text              emb   also search the questions/propositions by meaning
Unset or empty = off. Build the cache:  python my_solution/enrich.py --snapshot snapshots/05_2026-09-28_latest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
CACHE_PATH = Path(os.getenv("MY_SOLUTION_ENRICH_CACHE") or HERE / ".enrich_cache" / "enrich-v2.json")
FLAGS = {f.strip() for f in os.getenv("MY_SOLUTION_ENRICH", "").split(",") if f.strip()}
FLOOR = float(os.getenv("MY_SOLUTION_ENRICH_FLOOR", "0"))   # meaning-search pieces below this similarity are not added (0 = no floor)
EXTRA_N = int(os.getenv("MY_SOLUTION_ENRICH_EXTRA", "3"))   # parents added by meaning search over the new fields
PROMPT_VERSION = "enrich-v2"
SKIP_URL_PARTS = ("/blog", "news", "calculator", "rates")    # first pass: not the dated posts, calculators or rate pages
MIN_CHARS, MAX_CHARS = 200, 2500

SYSTEM = (
    "You prepare one website excerpt of a credit union for search indexing. Use ONLY the excerpt and its page info. "
    "Never add a fact, number, date, name or status that is not in the excerpt or page info. "
    "context_line: one sentence (max 35 words) saying which page, program, branch or topic the excerpt is about. "
    "Say 'current', 'ended' or 'historical' ONLY if the excerpt or page info states it (an end date, 'expired', 'no longer'); "
    "otherwise say nothing about status and never write that the status is unknown. "
    "propositions: standalone factual statements, each naming its subject (branch, product, program) so it reads alone; "
    "copy numbers, times and names exactly. "
    "questions: 3 to 5 different ways a member might ask something this excerpt answers; do not put answers in them."
)
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["context_line", "propositions", "questions"],
          "properties": {"context_line": {"type": "string"},
                         "propositions": {"type": "array", "items": {"type": "string"}},
                         "questions": {"type": "array", "items": {"type": "string"}}}}
_NUM = re.compile(r"\d[\d,.:]*\d|\d")


def key(c) -> str:
    """Content key: the same chunk in every website copy shares one entry."""
    return hashlib.sha1(" ".join(f"{c.title}|{c.header_path}|{c.heading}|{c.text}".split()).lower().encode()).hexdigest()


def eligible(c) -> bool:
    u = c.url.lower()
    return c.kind == "section" and MIN_CHARS <= len(c.text) <= MAX_CHARS and not any(p in u for p in SKIP_URL_PARTS)


def _user_message(c) -> str:
    return (f"Page: {c.title}\nURL: {c.url}\nSection: {c.header_path} {c.heading}\n"
            f"Page copy date: {c.fetched_at[:10]}\n\nExcerpt:\n{c.text}")


def _grounded(c, items: list[str]) -> list[str]:
    """Keep only items whose numbers all occur in the source."""
    src = set(_NUM.findall(f"{c.title} {c.url} {c.header_path} {c.heading} {c.text} {c.fetched_at}"))
    return [i for i in items if i and set(_NUM.findall(i)) <= src]


def clean(c, r: dict) -> dict:
    ctx = _grounded(c, [r.get("context_line", "").strip()])
    return {"c": ctx[0] if ctx else "", "p": _grounded(c, [x.strip() for x in r.get("propositions", [])]),
            "q": _grounded(c, [x.strip() for x in r.get("questions", [])])}


_LOCK = threading.Lock()
_CACHE: Optional[dict] = None


def load() -> dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    return _CACHE


def save() -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        CACHE_PATH.write_text(json.dumps(load(), ensure_ascii=False, separators=(",", ":")))


def generate(chunks, llm, workers: int = 8, max_calls: Optional[int] = None) -> dict:
    """Enrich every eligible chunk not yet in the cache. Returns {'calls', 'errors', 'dropped'}."""
    cache, todo, seen = load(), [], set()
    for c in chunks:
        k = key(c)
        if eligible(c) and k not in cache and k not in seen:
            seen.add(k); todo.append((k, c))
    if max_calls is not None:
        todo = todo[:max_calls]
    stats = {"calls": 0, "errors": 0, "dropped": 0}

    def one(kc):
        k, c = kc
        try:
            r = llm.ask_json(SYSTEM, _user_message(c), SCHEMA, "enrich", PROMPT_VERSION, max_tokens=900, timeout=60)
        except Exception as e:
            stats["errors"] += 1
            print(f"[enrich] error {type(e).__name__}: {e}", file=sys.stderr)
            return
        e = clean(c, r)
        stats["dropped"] += (len(r.get("propositions", [])) + len(r.get("questions", [])) + 1) - (len(e["p"]) + len(e["q"]) + bool(e["c"]))
        cache[k] = e
        stats["calls"] += 1
        if stats["calls"] % 200 == 0:
            save(); print(f"[enrich] {stats['calls']}/{len(todo)} usage={llm.usage}", file=sys.stderr, flush=True)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, todo))
    save()
    return stats


def apply(chunks) -> int:
    """Set c.enrich (dict) and c.enrich_text (what BM25 sees beyond the original) from the cache, per MY_SOLUTION_ENRICH. Returns how many chunks got any."""
    if not FLAGS:
        return 0
    cache, n = load(), 0
    for c in chunks:
        e = cache.get(key(c)) if c.kind == "section" else None
        if not e:
            continue
        c.enrich = e
        parts = []
        if "ctx" in FLAGS and e["c"]:
            parts.append(e["c"])
        if "prop" in FLAGS:
            parts += e["p"]
        if "q" in FLAGS:
            parts += e["q"]
        c.enrich_text = " ".join(parts)
        n += bool(c.enrich_text) or ("emb" in FLAGS)
    return n


class EnrichIndex:
    """Meaning search over the propositions and questions of the enriched chunks. search(question) -> [(similarity, chunk id, field)]
    best parents first, one entry per parent (its best unit). A proposition is embedded with its context line in front."""

    def __init__(self, chunks, embed_missing: bool = False):
        from embed_index import EmbeddingStore, MODEL, text_key
        import numpy as np
        self.chunks, self.units = chunks, []
        for ci, c in enumerate(chunks):
            e = getattr(c, "enrich", None)
            if not e:
                continue
            if "prop" in FLAGS:
                self.units += [(f"{e['c']} {p}".strip(), ci, "prop") for p in e["p"]]
            if "q" in FLAGS:
                self.units += [(q, ci, "q") for q in e["q"]]
        self.store = EmbeddingStore(path=HERE / ".embed_cache" / f"enrich-{MODEL}.npz")
        missing = [t for t, _, _ in self.units if text_key(t) not in self.store.vecs]
        if missing and embed_missing:
            self.store.ensure(missing)
            missing = [t for t, _, _ in self.units if text_key(t) not in self.store.vecs]
        if missing:
            print(f"[my_solution] enrichment: {len(missing)} units have no vector; meaning search over them is off", file=sys.stderr)
            self.units, self.matrix = [], None
        else:
            self.matrix = np.stack([self.store.vecs[text_key(t)] for t, _, _ in self.units]).astype(np.float32) if self.units else None

    def search(self, question: str, k: int = 10):
        if self.matrix is None:
            return []
        import numpy as np
        sims = self.matrix @ self.store.embed_query(question)
        best: dict[int, tuple[float, str]] = {}
        for i in np.argsort(-sims)[:60]:
            _, ci, field = self.units[i]
            if ci not in best:
                best[ci] = (float(sims[i]), field)
        return [(s, ci, f) for ci, (s, f) in sorted(best.items(), key=lambda x: -x[1][0])[:k]]


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the enrichment cache from the NEWEST website copy (paid: gpt-6-luna calls).")
    ap.add_argument("--snapshots", default=str(HERE.parent / "snapshots"), help="folder holding the unzipped website copies")
    ap.add_argument("--max-calls", type=int, default=None, help="stop after this many model calls (budget guard)")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "harness"))
    from run_eval import load_snapshots
    import solution
    snap = load_snapshots(Path(a.snapshots))[-1]          # same chunks as ingest makes (boilerplate dropped), so cache keys match
    k = solution.Knowledge(use_facts=False)
    chunks = k._chunks_for(snap)
    print(f"{snap.snapshot_id}: eligible distinct {len({key(c) for c in chunks if eligible(c)})}; cached already {len(load())}")
    print(generate(chunks, k.llm, a.workers, a.max_calls), k.llm.usage)


if __name__ == "__main__":
    main()
