#!/usr/bin/env python3
"""Retrieval-only check for ONE arm (no answer calls). Run by screen.py with the arm's switches in the environment.

Differences from my_solution/retrieval_check.py:
  - each question is put on the path answer() really takes: `text` (text search answers it), `facts` (a rate/fee question: the
    extracted facts answer it and text search is only the fallback), `history` ("what changed": evidence from every copy),
    `count` (answered by code) or `refuse` (date before the oldest copy). Ingest changes only matter on text, facts-fallback and
    history, so recall is reported per path instead of pooled.
  - `chars` is the length of the real user message the answer model would get (excerpt headers included), not just the texts.
  - the question labels come from a frozen cache (MY_SOLUTION_QU_DEC_CACHE), so every arm sees identical labels.
  - HyDE (--hyde FILE --hyde-mode replace|concat): the window (meaning) search uses a hypothetical answer instead of / added to
    the question. FILE maps question -> hypothetical answer (made by hyde.py).
"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "my_solution")); sys.path.insert(0, str(REPO / "harness"))


def norm(s: str) -> str:
    return " ".join(s.lower().replace("–", "-").replace("’", "'").split())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hyde")
    ap.add_argument("--hyde-mode", default="concat", choices=["replace", "concat"])
    a = ap.parse_args()
    from run_eval import load_snapshots
    import solution
    import embed_index
    from count_facts import count_question
    from prompt import PAGE_TYPE_LABEL, build_user_message
    from tiers import page_rank

    if a.hyde:
        hyde = json.loads(Path(a.hyde).read_text())
        orig = embed_index.WindowIndex.search

        def search(self, question, k=10):
            h = hyde.get(question)
            q = question if not h else (h if a.hyde_mode == "replace" else f"{question}\n{h}")
            return orig(self, q, k)
        embed_index.WindowIndex.search = search

    k = solution.Knowledge(use_facts=False)
    for s in load_snapshots(REPO / "snapshots"):
        k.ingest(s)
    rows = []
    for f in a.sets:
        for line in open(REPO / f):
            if not line.strip():
                continue
            r = json.loads(line)
            if not r.get("must_include"):
                continue
            q, as_of = r["question"], r.get("as_of")
            qu = k.understand(q)
            if solution.REFUSE_BEFORE_FIRST and k._before_first_snapshot(q, as_of, qu):
                path = "refuse"
            elif solution.HISTORY and (qu or {}).get("time_scope") == "change":
                path = "history"
            elif count_question(q, (qu or {}).get("website_date") or as_of) and solution.COUNT_ANSWERS:
                path = "count"
            elif k._asks_value(q, qu):
                path = "facts"
            else:
                path = "text"
            need = [norm(m) for m in r["must_include"]]
            if path == "history":
                hits = k._history_hits(q, as_of, qu)
                texts = [c.text for _, c, _, _ in hits]
                ex = [{"n": i, "page_type": PAGE_TYPE_LABEL[page_rank(c.url)], "url": c.url, "effective": c.effective,
                       "published": c.published, "copies": ", ".join(cp), "text": c.text} for i, (_, c, _, cp) in enumerate(hits, 1)]
                msg = build_user_message(q, ex, None) if hits else ""
                kinds = ["hist"] * len(hits)
            elif path in ("text", "facts"):
                taken_on = k._snapshot_for(q, as_of, qu)[0]
                hits = k.retrieve(q, as_of, qu=qu)
                texts = [c.text for _, c, _ in hits]
                msg = k.user_message(q, hits, taken_on, k._asked_note(q, as_of, qu)) if hits else ""
                kinds = []
                for i, (_, c, _) in enumerate(hits):
                    kinds.append(c.via or ("kw" if i < solution.TOP_K else "extra"))
            else:
                texts, msg, kinds = [], "", []
            blob = norm(" ".join(texts))
            # rank metric: the shortest prefix of the pieces, in the order sent, whose text holds every required string
            cover, acc = None, ""
            for i, t in enumerate(texts, 1):
                acc += " " + norm(t)
                if all(n in acc for n in need):
                    cover = i
                    break
            rows.append({"set": Path(f).stem, "id": r["id"], "path": path, "intent": (qu or {}).get("intent"),
                         "cover": cover,
                         "hit": all(n in blob for n in need) if texts else None,
                         "found": [n in blob for n in need], "pieces": len(texts), "chars": len(msg),
                         "text_chars": sum(len(t) for t in texts), "kinds": kinds})
    Path(a.out).write_text(json.dumps(rows))
    for p in ("text", "facts", "history"):
        R = [x for x in rows if x["path"] == p]
        if R:
            print(f"{p:8} n={len(R):3d} recall={sum(x['hit'] for x in R)/len(R):.3f} chars={sum(x['chars'] for x in R)/len(R):.0f}")


if __name__ == "__main__":
    main()
