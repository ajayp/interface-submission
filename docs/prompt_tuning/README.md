# Testing the 9 failing questions with OpenAI

Your process: paste a case's system message, user message and expected answer into the OpenAI chat; OpenAI diagnoses it and proposes a better
system prompt; you test it; the result comes back here. These files prepare that.

## How to run one task
1. Open the task file (`task1` to `task4`). Copy its **Ask for OpenAI** block into the chat.
2. For each case, paste the case file from `../playground_current/<id>.md` (it has the expected answer, our answer today, the system message,
   the user message and the output schema). Where a case has two user messages (rate questions), call 2 only happens if call 1 is not confident.
3. Ask OpenAI for (a) why the answer is what it is, and (b) the smallest change to the SYSTEM MESSAGE that fixes it.
4. Test the proposed system message on every case of the task **and on the guard cases** (`../playground_current/guard/`).
5. Fill in the results table at the bottom of the task file. Do not adopt a change that breaks a guard case.

## Rules for any proposed change (put these in every ask)
- General rule only: it must make sense for any member question. It must not name this question, a product, a branch, a number or a page.
- Do not change the JSON output schema and do not make answers longer (1 to 3 sentences). A longer answer or extra reasoning fields make the slow step slower.
- Keep "I don't know" for questions the excerpts do not answer. Do not make the model guess.

## How the grader scores a case (harness/scoring.py)
- `must_include` values must appear in the answer (numbers match by value: 3.5% = 3.50%). If any `must_not_include` value appears, correctness is 0.
- Should-refuse questions need `confident` = false (or a refusal phrase) and no numbers beyond those in the question.
- Source credit is 15%: a cited URL must match an expected page by path. Our cited URLs are the pages of the excerpts the model lists in `used_excerpts`.
- Speed counts the whole answer time, so a longer output costs time.

## Task list
| Task | Cases | Kind of problem |
|---|---|---|
| `task1_cited_page.md` | dup-054, dup-064, dup-066 | the answer is right but cites a different page than expected |
| `task2_two_readings.md` | dup-088, dup-049 | the question can be read two ways; the model picks the other reading |
| `task3_refusal_and_link.md` | dup-147, dup-008 | a refusal that breaks the scorer's rule; a required link that is sometimes left out |
| `task4_retrieval_dup104.md` | dup-104 | the right evidence does not reach the model (a retrieval question, not a prompt one) |
| `task5_judge_too_short.md` | dup-001, dup-052, dup-009, dup-050, dup-040 (case files in `../playground_current/judge/`) | the answer is correct but the judge calls it partial: it leaves out detail the reference answer includes |
| not a task | dup-005 | local scoring quirk (no required values); nothing to test |

Guard cases (currently passing, must stay passing): dup-028, dup-034, dup-001, dup-145 in `../playground_current/guard/`.

## Running a task automatically (`my_solution/prompt_tune.py`)

The same process without the copy and paste: the script sends the task's ask, the rules above, the baseline results and every case
file to an OpenAI model (`gpt-6.1-sol`), saves the proposed prompt change as a switchable variant, tests it through the real pipeline
with the judge, and sends the results back for the model to evaluate. Nothing becomes the default by itself.

```bash
# 1. baseline on the task's questions (2 runs, each judged)
python my_solution/prompt_tune.py test --variant G2 --eval eval/subsets/task5_cases.jsonl
# 2. open the conversation; the reply is saved as proposal H1 (my_solution/prompt_h1_edits.json)
python my_solution/prompt_tune.py ask --task tasks/openai_tests/task5_judge_too_short.md \
    --cases tasks/playground_current/judge --eval eval/subsets/task5_cases.jsonl --next H1 --new
# 3. test the proposal, send its results back, get the next one; repeat
python my_solution/prompt_tune.py test --variant H1 --eval eval/subsets/task5_cases.jsonl
python my_solution/prompt_tune.py ask --task tasks/openai_tests/task5_judge_too_short.md \
    --cases tasks/playground_current/judge --eval eval/subsets/task5_cases.jsonl --tested H1 --next H2
```

- A new task needs three things: a task file in this folder with an "Ask for OpenAI" block, a folder of case files (guards in a
  `guard/` subfolder), and a JSONL subset of the eval with every question to test (cases, guards, should-refuse questions).
- Each round writes `<task>_round<N>_message.md` and `<task>_round<N>_reply.md` here. `--dry-run` writes the message without sending.
- Working files (run results, the conversation id, private caches) go to `results/tune/`, which git ignores.
- Before adopting a proposal: 3 runs of the 40 public questions with it against 3 of the current prompt, with and without
  `judge_eval.py`. Adopt only if judged accuracy rises and no stale value or lost refusal appears.
- Task 5 was run this way (3 rounds, about $0.40): the outcome was to keep the current prompt. Note that the task 5 files in this
  folder were produced by the first version of the script, so its round numbers and proposal names (H2, H3) are one ahead.
