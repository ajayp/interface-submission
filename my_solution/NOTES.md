# NOTES

A question-answering system over five dated crawls of a credit union's website. It answers with the **current**, correctly-tiered value, a source, and an honest "I don't know" when the site does not say. It also lists where the website contradicts itself.

The submission is `my_solution/` (entry point `solution.py`, `build()`). Diagrams of the three flows are in [`workflow.md`](../workflow.md).

## 1. Setup, keys and cost

- Python 3.11 and `pip install -r my_solution/requirements.txt`.
- **Needs `OPENAI_API_KEY`** (paid OpenAI API) with access to `gpt-6-luna` (answers and fact extraction), the Decisions API `/v1/decisions` (question labels) and `text-embedding-3-small` (one question embedding per answer).
- **Cost:** loading the five snapshots is untimed, takes about 3 minutes and costs about $0.10 (one model call per distinct rate table). Each answer makes about three small calls. A full 40-question run costs a few cents. `conflicts()` makes about 77 small calls once.
- **Faster tier:** answer-time calls ask OpenAI for its faster service tier (about 2x the price per answer call; not confirmed for every account). If the account refuses that option, the call is retried once on the default tier.
- Without a key the system still runs on search alone, but it cannot refuse and scores about 0.34 on the public set.

## 2. How it works

Three flows, each drawn in `workflow.md`:

1. **Loading** ([diagram](../workflow.md#1-loading-the-snapshots-ingest-once-per-snapshot-untimed)). Each page is split by heading, with one piece per table row. Every website copy gets a keyword index, and every rate table is read once by the model into structured facts (product, term, tier, value, source, dates).
2. **Answering** ([diagram](../workflow.md#2-answering-one-question-answer-timed)). One Decisions call labels the question (section, rate type, is a date or a change asked). Rate and fee questions are answered from the facts, with only the winning value per product and tier shown to the model. Other questions use the best keyword pieces plus a few meaning-search pieces. The model returns one value with its sources.
3. **Contradictions** ([diagram](../workflow.md#3-listing-contradictions-conflicts-once-at-the-end)). Only the newest copy is read. Rate tables are read by code, rate sentences by one small model call each, and counts about the credit union (branches, employees, members, assets, counties) by fixed patterns.

## 3. How "current" is decided

1. **No date:** answer from the newest copy (2026-09-28).
2. **A date** (`as_of`, or a date in the question such as "as of June 2026" or a past-tense rate question): answer from the latest copy taken on or before it. A month with no year means the latest such month not after the newest copy. A date before the oldest copy (2026-05-12) gets "I don't know". A dated answer begins "As of <date>," and says when the year was assumed.
3. **Which page wins inside a copy:** rate sheet, then product and service page, then promotion page, then everything else (news, blog, calculators, PDFs). Between pages of the same type, the later "effective" date wins, then the later publish date. An offer the page itself says has ended always loses.
4. **Qualifiers make different facts:** tier, term, personal versus business, rate versus APY. They are never conflicts.
5. **"What changed" questions:** searched in every copy and answered with each value and the dates of the copies it appeared in.

## 4. Key decisions

| Decision | Why | What it costs |
|---|---|---|
| Rate and fee answers come from extracted facts, not raw pages | Stale values never reach the model: 0 stale values in every run | Facts cover rate tables only; hours and other prose use text search |
| A value that changed between copies, with no stale copy left in the newest one, is history, not a conflict | It is not a contradiction on the site today | Past changes are not listed by `conflicts()` |
| A fact that exists only on a page missing from the newest copy is not answered for a current question, but is answered for a dated one | The brief says to answer from the newest copy; an old PDF should not answer a should-refuse question | One lost-card fee on the tiny selftest fixture is "I don't know" on purpose |
| Every stale mortgage and auto-loan row is listed separately in `conflicts()` | The organizers' granularity is unknown; folding rows would lose recall if their list is row-level | Precision 0.29 against the hand-made list, which folds them |
| The members count winner is the newest news release (179,000), not a later PDF figure (182,627) | Counts are read from releases and posts by fixed patterns | One disagreement with the hand-made list |
| Rate or fee questions the tables do not answer get a second call that searches page text | It found a real number in 10 of 25 such cases across 141 questions from five sets | About 1.4 s extra on those questions |
| Ask for the faster service tier on answer calls, with a retry on the default tier | The answer call is about 90% of the time; p50 went from about 2.25 s to about 1.9 s | About 2x the price per answer call |
| Question labels come from the Decisions API, not a full model call | About 0.3 s instead of about 1.75 s, with equal accuracy | The section label is right about 78% of the time, so it only steers the search and the answer |
| General rules only, nothing typed in for a practice question | The hidden set rewords questions | Some practice misses are accepted (section 8) |

## 5. How an answer is produced and checked

The model sees only the evidence pieces, with their page type and dates, and must return one value, the sources it used, and a confidence flag. Then the code checks the reply:

- If the model says it cannot answer, or a value was asked for but the answer contains no new number, the answer becomes the standard refusal: "I don't know. That isn't listed on Dupaco's website, so please contact Dupaco directly."
- The sources are the pages the model used, plus other pages that state the same value.
- A refusal never contains a number.

Real answers from the public set:

| Question | Answer | Source |
|---|---|---|
| What is the APY on Dupaco's 17-month special certificate? | "Dupaco's 17-month special certificate earns 4.10% APY." | `/rates` |
| What was the rate on the 10-month fixed jumbo special certificate (dated question)? | "As of May 31, 2026, the 10-month fixed jumbo special certificate rate was 3.90% APY." | `/rates` |
| Is the Hy-Vee branch still open today (October 2026)? | "No. Dupaco's South Locust Street Hy-Vee branch in Dubuque closed March 31, 2026." | the closure news release |
| What interest rate do you charge on a construction loan? | "I don't know. That isn't listed on Dupaco's website, so please contact Dupaco directly." | none (the site does not say) |

## 6. Evaluation, including the LLM judge

- **Public set:** the organizers' scorer matches required values, zeroes an answer that contains a stale value, and gives credit for citing the right page.
- **LLM judge:** the organizers' scorer has an optional judge (`--judge`). A stand-in, `my_solution/judge_eval.py`, re-scores a finished run with an OpenAI judge (`gpt-6.1-sol`): same question wording, same 1 / 0.5 / 0 scale and the same 50/50 blend as the scorer. It is used to compare two versions and to read why an answer was marked down. It is a development tool and is never used at answer time.

  ```bash
  python harness/run_eval.py --submission my_solution --eval eval/public_eval.jsonl --out results/run1
  python my_solution/judge_eval.py --results results/run1/per_question.jsonl --eval eval/public_eval.jsonl
  ```

  The judged accuracy is about 0.81 to 0.82, against 0.85 for keyword matching. The answers are short on purpose, and the judge sometimes wants extra detail such as a minimum deposit. A prompt-tuning loop tried to close that gap (`my_solution/prompt_tune.py`, results in `docs/prompt_tuning/`). No change helped reliably without costing a refusal, so the current prompt stayed.
- **Question sets** (`eval/subsets/`, with expected answers): held-out (22), dated (21 and 17), what changed (14), year-less months (14), typos (48).
- **Conflicts:** two hand-made answer sheets in `docs/gold/`, scored with `my_solution/dump_conflicts.py` and `my_solution/score_conflict_lists.py`.
- **Other tools:** `trace.py` shows exactly what is sent to the model for a question; `regress.py` compares versions across all sets (example config in `docs/regress_example.json`).

## 7. Results

| | Result |
|---|---|
| Public set, accuracy | 0.851 to 0.867 over 5 runs |
| Public set, final score (no conflicts pillar locally) | 0.834 to 0.859 |
| Consistency, stale values, errors | 1.0, 0, 0 in every run |
| Speed, default tier | p50 2.25 to 2.53 s, p95 3.4 to 4.1 s |
| Speed, faster tier | p50 1.83 to 1.90 s, p95 2.9 to 3.2 s |
| Held-out / dated sets | 1.0 / 0.993 |
| `conflicts()` | 42 entries. Hand list (12): found 12, right winner 11, precision 0.29. Table key (35): found 35 |
| Loading | about 3 minutes and $0.10 cold |

## 8. Known limits

- The 2 s full-marks speed line is not met. The answer call is about 90% of the time. One run had a single 8.3 s answer (probably a timed-out call that was retried). A timeout becomes "I don't know" for that question.
- Accepted misses on the public set: dup-049, dup-008, dup-088 (two readings of the question), dup-104 (the lobby-hours piece misses the answer window) and dup-005 (a range instead of every rate).
- Hours, awards and similar facts are not in the fact table, so they depend on text search.
- On the tiny selftest fixture, a reworded certificate question is sometimes refused. This was not seen with "current" wordings on the real data.
- Window search needs the committed vectors in `my_solution/.embed_cache`. If a snapshot changes, they must be rebuilt, and until then that snapshot silently falls back to keyword search.
