# Prompt tuning with an LLM

How we tried to improve the answer prompt without guessing: give an OpenAI model the exact system message, user message and expected answer of the
questions that fail, let it propose a change, test the change through the real pipeline with the LLM judge, and hand the results back for the next round.

**Outcome: the current prompt stayed.** Three rounds on one problem (a correct answer that the judge marks down as too short) gave no change that helped
reliably without costing a refusal or a stale value. Writing this down is the point: a prompt change is only adopted if 3 runs of the 40 public questions
improve (judged accuracy up, no stale value, no lost refusal).

## Files

| File | What it is |
|---|---|
| `task5_judge_too_short.md` | The problem, the rules every proposal must follow, and the results of proposal 1 |
| `task5_proposal1.md` | Proposal 1 (variant H1) |
| `task5_round1_*`, `task5_round2_*`, `task5_round3_*` | The three API rounds: our message and the model's reply (proposals H2 and H3, then the final evaluation) |
| `cases/` | One file per question: expected answer, our answer, system message, user message. `cases/guard/` holds questions that pass today and must keep passing |
| `../../my_solution/prompt_h1_edits.json` to `prompt_h3_edits.json` | The proposals as exact text edits, switched on with `MY_SOLUTION_PROMPT_VARIANT=H1` etc. |

## Rules every proposal had to follow

- A general rule only: it must make sense for any member question, never name a question, product, branch, number or page.
- No change to the JSON output schema, and answers stay 1 to 3 sentences (longer output makes the slow step slower).
- Keep "I don't know" for questions the excerpts do not answer.

## Run it again (`my_solution/prompt_tune.py`, needs `OPENAI_API_KEY`)

```bash
# 1. baseline on the task's questions (2 runs, each judged by my_solution/judge_eval.py)
python my_solution/prompt_tune.py test --variant G2 --eval eval/subsets/task5_cases.jsonl
# 2. open the conversation; the reply is saved as proposal H1 (my_solution/prompt_h1_edits.json)
python my_solution/prompt_tune.py ask --task docs/prompt_tuning/task5_judge_too_short.md \
    --cases docs/prompt_tuning/cases --eval eval/subsets/task5_cases.jsonl --next H1 --new
# 3. test the proposal, send its results back, get the next one
python my_solution/prompt_tune.py test --variant H1 --eval eval/subsets/task5_cases.jsonl
python my_solution/prompt_tune.py ask --task docs/prompt_tuning/task5_judge_too_short.md \
    --cases docs/prompt_tuning/cases --eval eval/subsets/task5_cases.jsonl --tested H1 --next H2
```

`--dry-run` writes the message without sending it. Working files go to `results/tune/`, which git ignores.
