# LLM-as-a-judge workflow

How answers are judged during development. This is separate from the day-to-day answering flow in [`workflow.md`](workflow.md): nothing here runs when the system answers a question, and the grader never calls it.

## Why a judge

The harness scores an answer by matching required values, which is strict and cheap but cannot tell a complete answer from a bare one. The organizers' scorer has an optional judge for that (`harness/run_eval.py --judge`, an Anthropic model, `claude-opus-5-5`). The stand-in in `my_solution/judge_eval.py` uses an OpenAI model (`gpt-6.1-sol`, reasoning effort low) so a run can be re-scored without asking the questions again. It uses the same question wording, the same 1 / 0.5 / 0 scale and the same 50/50 blend as the harness. It is a stand-in and not a prediction of the organizers' score. It is used to compare two versions and to read why an answer was marked down.

## 1. Judging one finished run

```mermaid
flowchart TD
    EV[Questions with reference answers<br/>eval/public_eval.jsonl or a file in eval/subsets/] --> RUN[harness/run_eval.py<br/>asks my_solution each question]
    RUN --> PQ[per_question.jsonl<br/>answer, sources, matched and missed values, stale hits]
    PQ --> SKIP{Should-refuse question,<br/>or no reference answer?}
    SKIP -- yes --> KEEP[Keep the keyword score as it is]
    SKIP -- no --> J[[Judge: gpt-6.1-sol<br/>reads question, reference answer,<br/>values that must not appear, the answer<br/>returns 1, 0.5 or 0 and a reason]]
    J --> BLEND[Correctness<br/>half the share of required values found<br/>plus half the judge score]
    BLEND --> STALE{Stale or wrong value in the answer?}
    STALE -- yes --> ZERO[Correctness 0]
    STALE -- no --> SRC[Add source credit<br/>85% correctness plus 15% if the right page is cited]
    KEEP --> OUTR
    ZERO --> OUTR
    SRC --> OUTR([judged.jsonl and a summary<br/>accuracy with and without the judge,<br/>and each answer marked below 1 with its reason])
```

- A question with no required values is scored by the judge alone.
- If the judge call fails for one answer, that answer keeps its keyword score.
- The judge never changes a should-refuse question.

```bash
python harness/run_eval.py --submission my_solution --eval eval/public_eval.jsonl --out results/run1
python my_solution/judge_eval.py --results results/run1/per_question.jsonl --eval eval/public_eval.jsonl
```

Result on the public set: judged accuracy about 0.81 to 0.82, against 0.85 from keyword matching. The answers are short on purpose, and the judge sometimes wants extra detail such as a minimum deposit.

## 2. Using the judge to tune the prompt

```mermaid
flowchart TD
    A[Failing or marked-down questions<br/>with the exact system and user messages] --> ASK[[prompt_tune.py ask<br/>an OpenAI model proposes exact text edits<br/>to the system message]]
    ASK --> EDIT[Saved as a switchable variant<br/>my_solution/prompt_hN_edits.json]
    EDIT --> TEST[prompt_tune.py test<br/>runs the questions with the variant through the harness<br/>2 runs, each judged by judge_eval.py]
    TEST --> RES[Answers, scores and judge reasons of every run]
    RES --> BACK[[Sent back to the model<br/>to evaluate and propose the next edit]]
    BACK --> ASK
    RES --> DEC{Over 3 runs of the 40 public questions:<br/>judged accuracy up, no stale value,<br/>no lost refusal?}
    DEC -- yes --> ADOPT([Adopt as the default])
    DEC -- no --> STAY([Keep the current prompt])
```

- Nothing becomes the default by itself. A variant is switched on with `MY_SOLUTION_PROMPT_VARIANT=H1` and so on.
- Outcome of the three rounds so far: no edit helped reliably without costing a refusal, so the current prompt stayed. The rounds and the questions they used are in `docs/prompt_tuning/`.
