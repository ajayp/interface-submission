"""
Local LLM judge for a finished harness run (development tool, not used when graded and never at answer time).

The organizers' scorer has an optional judge (`harness/run_eval.py --judge`, Anthropic `claude-opus-5-5`) that blends
a model's verdict into each question's correctness. This script is our stand-in with an OpenAI model: it re-scores an
existing `per_question.jsonl` without asking the questions again. Same question wording and the same 1 / 0.5 / 0 scale as
`harness/scoring.py` (`_llm_judge`), same blend: correctness = 0.5 * keyword share + 0.5 * judge (judge alone when the
item has no `must_include`); a stale value still zeroes it; should-refuse items are left as scored.

A stand-in, not a prediction: use it to compare two versions of our answers and to read why an answer was marked down.

    python my_solution/judge_eval.py --results results/per_question.jsonl --eval eval/public_eval.jsonl

Needs OPENAI_API_KEY. Model: gpt-6.1-sol at reasoning effort low (override: MY_SOLUTION_JUDGE_MODEL, MY_SOLUTION_JUDGE_EFFORT).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MODEL = os.getenv("MY_SOLUTION_JUDGE_MODEL", "gpt-6.1-sol")
EFFORT = os.getenv("MY_SOLUTION_JUDGE_EFFORT", "low")   # gpt-6.1-sol has no effort "none", so no temperature either
VERDICT_SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "number", "enum": [0, 0.5, 1]}, "reason": {"type": "string"}},
    "required": ["score", "reason"],
    "additionalProperties": False,
}


def judge_message(item: dict, answer_text: str) -> str:
    """The exact text harness/scoring.py sends its judge."""
    return (
        "Grade a credit-union assistant's answer against the reference.\n"
        f"Question: {item['question']}\nReference answer: {item['expected_answer']}\n"
        f"Values that must NOT appear (stale/wrong): {item.get('must_not_include', [])}\n"
        f"Candidate answer: {answer_text}\n\n"
        "score = 1 if the candidate states the reference facts correctly and nothing "
        "contradicting them, 0.5 if partially correct, 0 if wrong, stale, or evasive."
    )


def judge_one(client, item: dict, answer_text: str, usage: dict) -> dict:
    r = client.responses.create(
        model=MODEL, input=judge_message(item, answer_text), reasoning={"effort": EFFORT},
        text={"format": {"type": "json_schema", "name": "verdict", "schema": VERDICT_SCHEMA, "strict": True}},
        max_output_tokens=4000)
    usage["input"] += r.usage.input_tokens
    usage["output"] += r.usage.output_tokens
    text = r.output_text.strip()
    obj, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
    return {"score": max(0.0, min(1.0, float(obj["score"]))), "reason": obj["reason"]}


def rescore(row: dict, judge_score) -> dict:
    """Blend the judge into one per_question row the way harness/scoring.py score_item does."""
    must_n = len(row["matched"]) + len(row["missed"])
    if row["category"] == "should_refuse" or judge_score is None:
        correctness = row["correctness"]
    else:
        share = len(row["matched"]) / must_n if must_n else 0.0
        correctness = 0.5 * share + 0.5 * judge_score if must_n else judge_score
        if row["trap_hits"]:
            correctness = 0.0
    src = row.get("source_hit")
    score = correctness if src is None else 0.85 * correctness + 0.15 * src
    return {"correctness_judged": round(correctness, 4), "score_judged": round(score, 4)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, default=Path("results/per_question.jsonl"))
    ap.add_argument("--eval", type=Path, default=Path("eval/public_eval.jsonl"))
    ap.add_argument("--out", type=Path, help="default: <results folder>/judged.jsonl")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    from openai import OpenAI
    client = OpenAI(timeout=120, max_retries=2)
    items = {i["id"]: i for i in (json.loads(l) for l in args.eval.read_text().splitlines() if l.strip())}
    rows = [json.loads(l) for l in args.results.read_text().splitlines() if l.strip()]
    usage = {"input": 0, "output": 0}

    def work(row):
        item = items[row["id"]]
        if row["category"] == "should_refuse" or not item.get("expected_answer"):
            return None
        try:
            return judge_one(client, item, row["answer"]["text"], usage)
        except Exception as e:   # like the harness: no verdict, keep the keyword score
            print(f"[judge] {row['id']} failed: {type(e).__name__}: {e}", file=sys.stderr)
            return None

    with ThreadPoolExecutor(args.workers) as pool:
        verdicts = list(pool.map(work, rows))

    out_rows = []
    for row, v in zip(rows, verdicts):
        out_rows.append({**{k: row[k] for k in ("id", "category", "weight", "score", "correctness", "matched", "missed", "trap_hits")},
                         "question": items[row["id"]]["question"], "answer": row["answer"]["text"],
                         "expected_answer": items[row["id"]].get("expected_answer"),
                         "judge_score": v and v["score"], "judge_reason": v and v["reason"],
                         **rescore(row, v and v["score"])})
    wsum = sum(r["weight"] for r in out_rows) or 1.0
    plain = sum(r["score"] * r["weight"] for r in out_rows) / wsum
    judged = sum(r["score_judged"] * r["weight"] for r in out_rows) / wsum
    out = args.out or args.results.parent / "judged.jsonl"
    out.write_text("\n".join(json.dumps(r) for r in out_rows))

    print(f"model {MODEL} (effort {EFFORT}); {sum(v is not None for v in verdicts)} of {len(rows)} answers judged")
    print(f"accuracy without judge: {plain:.4f}    with judge: {judged:.4f}    difference: {judged - plain:+.4f}")
    print(f"tokens: {usage['input']} input, {usage['output']} output")
    print("\nanswers the judge marked below 1 (keyword score -> judged score):")
    for r in sorted(out_rows, key=lambda r: r["score_judged"] - r["score"]):
        if r["judge_score"] is not None and r["judge_score"] < 1:
            print(f"  {r['id']:8s} {r['category']:20s} {r['score']:.2f} -> {r['score_judged']:.2f}  judge {r['judge_score']}: {r['judge_reason'][:160]}")
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
