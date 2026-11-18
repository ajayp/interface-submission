#!/usr/bin/env python3
"""
Prompt-tuning loop with an OpenAI model (development tool, not used when graded and never at answer time).

It automates the manual process: give a model the exact system and user messages and the expected answers for a set of cases,
get a proposed change to the system message, test it, and give the model the results to evaluate. The test step runs the real
pipeline (harness + judge_eval.py) instead of the playground. Run from the repo root. Needs OPENAI_API_KEY.

A proposal is a list of exact text edits (find / replace) against the current default system message. Proposal H<n> is stored
in my_solution/prompt_h<n>_edits.json and switched on with MY_SOLUTION_PROMPT_VARIANT=H<n> (prompt.py); nothing becomes the
default by itself.

  1. Test the baseline (and any variant) on the task's questions, each run judged:
       python my_solution/prompt_tune.py test --variant G2 --eval eval/subsets/task5_cases.jsonl
  2. Open the conversation: the task's ask, the rules, the baseline results and every case file; the reply is saved as H1:
       python my_solution/prompt_tune.py ask --task docs/prompt_tuning/task5_judge_too_short.md \\
           --cases docs/prompt_tuning/cases --eval eval/subsets/task5_cases.jsonl --next H1 --new
  3. Test the proposal, then send its results back and get the next one:
       python my_solution/prompt_tune.py test --variant H1 --eval eval/subsets/task5_cases.jsonl
       python my_solution/prompt_tune.py ask --task ... --cases ... --eval ... --tested H1 --next H2
     Repeat until the model recommends stopping or a proposal clearly wins; then run the full public set with that variant
     (3 runs against 3 of the baseline) before making anything the default.

Inputs it expects:
  --task   a Markdown file with a "**Ask for OpenAI (copy this):**" block of "> " lines followed by a "## Acceptance" heading
           (the layout of docs/prompt_tuning/task*.md).
  --cases  a folder of case files (one .md per question id, with the system message, user message and expected answer); files
           in its guard/ subfolder are questions that pass today and must keep passing.
  --eval   a JSONL subset of the eval holding every question to test (cases, guards, should-refuse questions).

Outputs: <task folder>/<task stem>_round<N>_message.md and _reply.md (N counts up per task), the edits file, and working files
under results/tune/ (ignored by git): run results, the conversation id, and private caches so test runs leave the repo's
embedding cache untouched. Use --dry-run with `ask` to write the message without calling the API.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
TUNE = ROOT / "results" / "tune"
MODEL = os.getenv("MY_SOLUTION_TUNE_MODEL", "gpt-6.1-sol")
EFFORT = os.getenv("MY_SOLUTION_TUNE_EFFORT", "medium")
BASELINE = "G2"   # the variant name of the current default prompt (prompt.py)

RULES = (
    "Constraints for every proposal: a general rule that makes sense for any member question; never name this question, a product, a "
    "branch, a number or a page. Do not change the JSON schema. Answers stay 1 to 3 sentences. A question that asks for a specific "
    "value the excerpts do not state must still get the standard \"I don't know\" answer with no number. Never quote a value for a "
    "product, tier, term or promotion the question did not ask about: an answer containing a forbidden value (an old rate, another "
    "tier's rate, a promotional rate) scores zero.\n"
    "Return the proposal as exact text edits against the ORIGINAL system message shown in the case files (not against an earlier "
    "proposal): each edit has `find` (copied exactly, character for character, long enough to occur once) and `replace`. Edit only "
    "the shared parts (Identity, Instructions, Context), never a `# Question type` block. Also evaluate the results I give you: say "
    "what worked, what did not and why. If no further general improvement is available, say so and return no edits.")
SCHEMA = {
    "type": "object",
    "properties": {
        "evaluation": {"type": "string"},
        "edits": {"type": "array", "items": {
            "type": "object", "properties": {"find": {"type": "string"}, "replace": {"type": "string"}},
            "required": ["find", "replace"], "additionalProperties": False}},
        "risks": {"type": "string"},
        "recommend_stop": {"type": "boolean"},
        "keep_version": {"type": "string"},
    },
    "required": ["evaluation", "edits", "risks", "recommend_stop", "keep_version"],
    "additionalProperties": False,
}


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _env(variant: str) -> dict:
    env = dict(os.environ, MY_SOLUTION_PROMPT_VARIANT=variant)
    env.setdefault("MY_SOLUTION_FACT_CACHE", str(TUNE / "fact_cache.json"))          # facts are extracted once, then reused
    env.setdefault("MY_SOLUTION_QUESTION_CACHE", str(TUNE / "question_vectors.npz"))  # keep the committed cache untouched
    return env


def run_dir(variant: str, eval_path: Path, i: int) -> Path:
    return TUNE / f"{eval_path.stem}_{variant}_{i}"


def cmd_test(args) -> None:
    """Run the eval subset `--runs` times with one prompt variant and judge each run."""
    TUNE.mkdir(parents=True, exist_ok=True)
    for i in range(1, args.runs + 1):
        out = run_dir(args.variant, args.eval, i)
        r = subprocess.run([sys.executable, str(ROOT / "harness/run_eval.py"), "--submission", str(HERE), "--eval", str(args.eval),
                            "--out", str(out), "--repeat-sample", "0"], env=_env(args.variant), cwd=ROOT, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"harness failed for {args.variant} run {i}:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
        j = subprocess.run([sys.executable, str(HERE / "judge_eval.py"), "--results", str(out / "per_question.jsonl"),
                            "--eval", str(args.eval)], env=_env(args.variant), cwd=ROOT, capture_output=True, text=True)
        report = json.loads((out / "report.json").read_text())
        judged = next((l for l in j.stdout.splitlines() if l.startswith("accuracy without judge")), j.stderr.strip()[-300:])
        print(f"{args.variant} run {i}: stale values {report['stale_trap_hits']}, errors {report['errors']}, {judged}")
    print(f"results: {run_dir(args.variant, args.eval, 1).parent}/{args.eval.stem}_{args.variant}_<run>/")


def roles(cases: Path, items: dict) -> dict:
    """What each test question is to the task: a case to improve, a guard, or a question that must be declined."""
    case_ids = {p.stem for p in cases.glob("*.md")}
    guard_ids = {p.stem for p in (cases / "guard").glob("*.md")}
    out = {}
    for q, it in items.items():
        out[q] = ("must refuse" if it.get("category") == "should_refuse" else "case" if q in case_ids
                  else "guard" if q in guard_ids else "other")
    return out


def results_text(variant: str, eval_path: Path, items: dict, role: dict) -> str:
    """Every answer, score and judge reason of each recorded run of a variant, as text for the model."""
    runs = [i for i in range(1, 10) if (run_dir(variant, eval_path, i) / "judged.jsonl").exists()]
    if not runs:
        sys.exit(f"no results for {variant}: run `prompt_tune.py test --variant {variant} --eval {eval_path}` first")
    judged = {i: {r["id"]: r for r in _jsonl(run_dir(variant, eval_path, i) / "judged.jsonl")} for i in runs}
    plain = {i: {r["id"]: r for r in _jsonl(run_dir(variant, eval_path, i) / "per_question.jsonl")} for i in runs}
    out = []
    for q, it in items.items():
        rows = []
        for i in runs:
            r, p = judged[i][q], plain[i][q]
            grade = f", grader {r['judge_score']} ({r['judge_reason']})" if r["judge_score"] is not None else ""
            rows.append(f"  run {i}: keyword score {r['score']}, forbidden values hit {r['trap_hits'] or 'none'}, "
                        f"declined={not p['answer']['confident']}{grade}\n    answer: {r['answer']}")
        out.append(f"- {q} [{role[q]}] {it['question']}\n" + "\n".join(rows))
    return "\n".join(out)


def ask_block(task: Path) -> str:
    t = task.read_text()
    block = t[t.index("**Ask for OpenAI (copy this):**"):t.index("## Acceptance")]
    return "\n".join(l[2:] if l.startswith("> ") else l[1:] for l in block.splitlines() if l.startswith(">"))


def edits_file(variant: str) -> Path:
    return HERE / f"prompt_{variant.lower()}_edits.json"


def cmd_ask(args) -> None:
    """Send one message of the conversation and save the reply as the next proposal."""
    TUNE.mkdir(parents=True, exist_ok=True)
    if not re.fullmatch(r"H\d+", args.next):
        sys.exit("--next must be H<number>, for example H1")
    items = {i["id"]: i for i in _jsonl(args.eval)}
    role = roles(args.cases, items)
    state_path = TUNE / f"{args.task.stem}_state.json"
    state = {} if args.new or not state_path.exists() else json.loads(state_path.read_text())
    n = state.get("rounds", 0) + 1
    note = (args.note + "\n") if args.note else ""
    if not state.get("last_id"):   # opening message: the ask, the rules, what is known, every case file
        msg = ask_block(args.task) + "\n\n" + RULES + "\n\n"
        msg += f"Results on the test questions with the ORIGINAL system message:\n{results_text(BASELINE, args.eval, items, role)}\n\n"
        if args.tested:
            tried = json.loads(edits_file(args.tested).read_text())["edits"]
            msg += (f"=========== WHAT HAS BEEN TRIED ===========\nA first set of edits ({args.tested}) was tested. The edits were:\n"
                    + "\n".join(f"FIND: {e['find'].strip()}\nREPLACE: {e['replace'].strip()}\n" for e in tried)
                    + f"\nResults with {args.tested}:\n{results_text(args.tested, args.eval, items, role)}\n\n")
        msg += note + f"Please propose a set of edits ({args.next}).\n\n"
        msg += "=========== CASE FILES (exact system and user messages) ===========\n"
        msg += "\n\n-----\n\n".join(p.read_text() for p in sorted(args.cases.glob("*.md")))
        guards = sorted((args.cases / "guard").glob("*.md"))
        if guards:
            msg += "\n\n=========== GUARD AND MUST-REFUSE CASE FILES ===========\n" + "\n\n-----\n\n".join(p.read_text() for p in guards)
    else:
        if not args.tested:
            sys.exit("--tested H<n> is required after the opening message (the proposal whose results are sent back)")
        msg = (f"I tested your edits ({args.tested}). Results on the test questions:\n{results_text(args.tested, args.eval, items, role)}\n\n"
               "For comparison, the ORIGINAL system message on the same questions is in my first message.\n" + note
               + f"Evaluate these results, then propose the next set of edits ({args.next}) against the ORIGINAL system message, or say "
                 "that no further general improvement is available and which version you would keep.\n\n" + RULES)
    out_dir = args.task.parent
    (out_dir / f"{args.task.stem}_round{n}_message.md").write_text(
        f"# {args.task.stem}, round {n}: message sent to {MODEL}\n\n{msg}\n")
    print(f"round {n}: message of {len(msg):,} characters written to {out_dir / (args.task.stem + f'_round{n}_message.md')}")
    if args.dry_run:
        print("dry run: nothing sent")
        return

    from openai import OpenAI
    kw = dict(model=MODEL, input=msg, reasoning={"effort": EFFORT}, max_output_tokens=14000,
              text={"format": {"type": "json_schema", "name": "proposal", "schema": SCHEMA, "strict": True}})
    if state.get("last_id"):
        kw["previous_response_id"] = state["last_id"]
    r = OpenAI(timeout=900, max_retries=1).responses.create(**kw)
    out = json.loads(r.output_text)
    state.update(last_id=r.id, rounds=n)
    state.setdefault("usage", []).append([r.usage.input_tokens, r.usage.output_tokens])
    state_path.write_text(json.dumps(state))

    sys.path.insert(0, str(HERE))
    os.environ["MY_SOLUTION_PROMPT_VARIANT"] = BASELINE
    import prompt   # the baseline system message, to check that each edit's anchor occurs exactly once
    missing = [e["find"][:70] for e in out["edits"] if prompt.DEVELOPER_MESSAGE.count(e["find"].strip()) != 1]
    if out["edits"]:
        edits_file(args.next).write_text(json.dumps(
            {"source": f"{args.task.stem} conversation round {n} ({args.task.stem}_round{n}_reply.md)", "edits": out["edits"]},
            indent=1) + "\n")
    md = [f"# {args.task.stem}, round {n}: reply from {MODEL} (proposal {args.next})", "",
          f"Tokens: {r.usage.input_tokens} input, {r.usage.output_tokens} output.", "",
          "## Its evaluation of the results", "", out["evaluation"], "", "## Proposed edits (against the original system message)", ""]
    for i, e in enumerate(out["edits"], 1):
        md += [f"### Edit {i}", "", "Find:", "", "> " + e["find"].strip(), "", "Replace with:", "", "> " + e["replace"].strip(), ""]
    md += ["## Risks it named", "", out["risks"], "",
           f"Recommends stopping: {out['recommend_stop']}. Version it would keep: {out['keep_version']}"]
    (out_dir / f"{args.task.stem}_round{n}_reply.md").write_text("\n".join(md) + "\n")
    print(f"tokens: {r.usage.input_tokens} input, {r.usage.output_tokens} output")
    print(f"edits: {len(out['edits'])}" + (f" -> {edits_file(args.next)}" if out["edits"] else " (no proposal)"))
    if missing:
        print(f"WARNING: {len(missing)} edit anchor(s) not found exactly once in the baseline prompt; {args.next} will not load: {missing}")
    print(f"recommends stopping: {out['recommend_stop']}; would keep: {out['keep_version']}")
    print(f"reply: {out_dir / (args.task.stem + f'_round{n}_reply.md')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    t = sub.add_parser("test", help="run the eval subset with one prompt variant and judge each run")
    t.add_argument("--variant", required=True, help=f"{BASELINE} (the current default) or H<n>")
    t.add_argument("--eval", required=True, type=Path)
    t.add_argument("--runs", type=int, default=2)
    t.set_defaults(func=cmd_test)
    a = sub.add_parser("ask", help="send one message of the tuning conversation and save the reply as the next proposal")
    a.add_argument("--task", required=True, type=Path)
    a.add_argument("--cases", required=True, type=Path)
    a.add_argument("--eval", required=True, type=Path)
    a.add_argument("--next", required=True, help="name for the proposal the reply will hold, e.g. H1")
    a.add_argument("--tested", help="the proposal whose test results are sent (required after the opening message)")
    a.add_argument("--note", help="one extra paragraph for the model, e.g. a finding from a full 40-question run")
    a.add_argument("--new", action="store_true", help="start a new conversation for this task")
    a.add_argument("--dry-run", action="store_true", help="write the message file, send nothing")
    a.set_defaults(func=cmd_ask)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
