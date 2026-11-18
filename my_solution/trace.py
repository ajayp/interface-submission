#!/usr/bin/env python3
"""
Trace what the system sends to the AI for one or more questions. Run from the repo root:

    python my_solution/trace.py --eval eval/subsets/failing.jsonl [--ids dup-088 dup-087]
    python my_solution/trace.py --question "How can I update my contact information?"

Writes one Markdown file per question to results/traces/ (git-ignored) with: the query-understanding output,
the website copy used, the 8 pieces with scores, the full system (developer) message, the full user message,
the AI's raw reply and the final answer. Makes the same OpenAI calls as a real answer.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import load_snapshots  # noqa: E402
from scoring import score_item  # noqa: E402

import solution  # noqa: E402
from prompt import DEVELOPER_MESSAGE  # noqa: E402
from query_understanding import QU_DEVELOPER_MESSAGE, build_qu_message  # noqa: E402
from tiers import page_rank  # noqa: E402

OUT = ROOT / "results" / "traces"


def trace(ks, item: dict) -> Path:
    q, as_of = item["question"], item.get("as_of")
    qu = ks.understand(q)
    taken_on, snap_id, _ = ks._snapshot_for(q, as_of, qu)
    hits = ks.retrieve(q, as_of, qu=qu)
    user_msg = ks.user_message(q, hits, taken_on)
    raw = ks.llm.ask(user_msg)
    final = ks.answer(q, as_of)
    lines = [f"# Trace: {q}", ""]
    if item.get("id"):
        sc = score_item(item, final)
        lines += [f"- eval id: {item['id']} ({item.get('category')}), score {sc['score']}, "
                  f"missing {sc['missed']}, stale/wrong values {sc['trap_hits']}",
                  f"- expected: {item.get('expected_answer')}"]
    lines += [f"- mode: {ks.qu_mode}; website copy used: {snap_id} (as_of={as_of})", "",
              "## 1. Query understanding output", "", "```json", json.dumps(qu, indent=1), "```", "",
              "## 2. The 8 pieces sent (score, page type, page)", ""]
    for i, (s, c, urls) in enumerate(hits, 1):
        extra = f" (+{len(urls) - 1} copies)" if len(urls) > 1 else ""
        lines.append(f"{i}. {s:.1f} | {page_rank(c.url)} | {c.url}{extra} | effective {c.effective}")
    lines += ["", "## 3. System (developer) message for the answer AI", "", "```", DEVELOPER_MESSAGE, "```", "",
              "## 4. User message for the answer AI (exactly as sent)", "", "```", user_msg, "```", "",
              "## 5. AI raw reply", "", "```json", json.dumps(raw, indent=1), "```", "",
              "## 6. Final answer returned", "", final.text, "",
              "Sources: " + ", ".join(s.url for s in final.sources), "",
              "## Appendix: query-understanding messages", "", "```", QU_DEVELOPER_MESSAGE, "```", "", "```",
              build_qu_message(q), "```"]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{item.get('id') or 'question'}.md"
    path.write_text("\n".join(lines))
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--question")
    a = ap.parse_args()
    items = [{"question": a.question}] if a.question else \
        [json.loads(l) for l in Path(a.eval).read_text().splitlines() if l.strip()]
    if a.ids:
        items = [i for i in items if i.get("id") in a.ids]
    ks = solution.Knowledge()
    for s in load_snapshots(ROOT / "snapshots"):
        ks.ingest(s)
    for it in items:
        print(trace(ks, it))
