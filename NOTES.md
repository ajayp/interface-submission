# NOTES

## Contents

- [Concepts at a glance](#concepts-at-a-glance)

1. [Setup, keys and cost](#1-setup-keys-and-cost)
2. [How it works](#2-how-it-works)
3. [How "current" is decided](#3-how-current-is-decided)
4. [Key decisions](#4-key-decisions)
5. [How an answer is produced and checked](#5-how-an-answer-is-produced-and-checked)
6. [Evaluation, including the LLM judge](#6-evaluation-including-the-llm-judge)
7. [Results](#7-results)
8. [Known limits](#8-known-limits)
9. [Reference mismatches and scoring quirks](#9-reference-mismatches-and-scoring-quirks)

A question-answering system over five dated crawls of a credit union's website. It answers with the **current**, correctly-tiered value, a source, and an honest "I don't know" when the site does not say. It also lists where the website contradicts itself.

The submission is `my_solution/` (entry point `solution.py`, `build()`). Diagrams of the three flows are in [`workflow.md`](workflow.md).

## Concepts at a glance

| Concept | What it is here | Where |
|---|---|---|
| LLM query understanding | One Decisions call labels each question (section, rate type, date, change) and steers the search | [section 2](#2-how-it-works), [section 4](#4-key-decisions) |
| Structured fact extraction | Each rate table is read once by the model into facts; rate and fee questions are answered from the winning fact | [section 2](#2-how-it-works) |
| Hybrid search | Keyword search plus meaning search over short text windows | [section 2](#2-how-it-works), [`workflow.md`](workflow.md) |
| Source trust and recency | Rate sheet over product page over promotion over everything else, then the later effective date | [section 3](#3-how-current-is-decided) |
| Time-aware answers | Dated questions are answered from the right website copy; "what changed" questions compare copies | [section 3](#3-how-current-is-decided), [`workflow.md`](workflow.md) |
| Grounded answers and refusals | The model sees only the evidence, and the answer becomes "I don't know" when the site does not say | [section 5](#5-how-an-answer-is-produced-and-checked) |
| Conflict detection | `conflicts()` finds where the site contradicts itself, and picks the value to believe | [section 2](#2-how-it-works), [`docs/gold/`](docs/gold/README.md) |
| LLM-as-a-judge | A stand-in judge re-scores finished runs, for comparing versions | [section 6](#6-evaluation-including-the-llm-judge), [`judge-workflow.md`](judge-workflow.md) |
| Prompt tuning with an LLM | An OpenAI model proposes prompt edits, tested with the judge | [`judge-workflow.md`](judge-workflow.md), [`docs/prompt_tuning/`](docs/prompt_tuning/README.md) |

## 1. Setup, keys and cost

- Python 3.11 and `pip install -r my_solution/requirements.txt`.
- **Needs `OPENAI_API_KEY`** (paid OpenAI API) with access to `gpt-6-luna` (answers and fact extraction), the Decisions API `/v1/decisions` (question labels) and `text-embedding-3-small` (one question embedding per answer).
- **Cost:** loading the five snapshots is untimed, takes about 3 minutes and costs about $0.10 (one model call per distinct rate table). Each answer makes about three small calls. A full 40-question run costs a few cents. `conflicts()` makes about 77 small calls once.
- **Faster tier:** answer-time calls ask OpenAI for its faster service tier (about 2x the price per answer call; not confirmed for every account). If the account refuses that option, the call is retried once on the default tier.
- Without a key the system still runs on search alone, but it cannot refuse and scores about 0.34 on the public set.

## 2. How it works

Three flows, each drawn in `workflow.md`:

1. **Loading** ([diagram](workflow.md#1-loading-the-snapshots-ingest-once-per-snapshot-untimed)). Each page is split by heading, with one piece per table row. Every website copy gets a keyword index, and every rate table is read once by the model into structured facts (product, term, tier, value, source, dates).
2. **Answering** ([diagram](workflow.md#2-answering-one-question-answer-timed)). In order:
   - **Understand the question** with one LLM call to the Decisions API ([Query understanding](#query-understanding-llm-decisions-api)).
   - **Pick the website copy:** the newest by default, or the latest one on or before a date that is asked.
   - **A count question** ("how many branches") is answered by code, with no LLM call.
   - **A rate or fee question** goes to the extracted facts, keeping only the winning value per product and tier. **LLM call 1** answers from those facts. If it cannot answer, or no fact matched, the system **falls back to a text search and makes LLM call 2** over the best page pieces. In our check, this second call found a real number in 10 of 25 such cases.
   - **Any other question** uses the best keyword pieces plus a few meaning-search pieces, and one LLM call answers from them.
   - **Check.** If the model says it cannot answer, or a value was asked for and the answer has no new number, the answer becomes "I don't know".
   - **Return** the answer with the pages it came from.
3. **Contradictions** ([diagram](workflow.md#3-listing-contradictions-conflicts-once-at-the-end)). Only the newest copy is read. Rate tables are read by code, rate sentences by one small model call each, and counts about the credit union (branches, employees, members, assets, counties) by fixed patterns.

### Query understanding (LLM, Decisions API)

Before any search, an LLM reads the question, so the rest of the system knows what is being asked. This uses OpenAI's Decisions API (`POST /v1/decisions`), which runs `gpt-6-luna` but returns only labels and their probabilities, with no generated text. That makes it fast: about 0.3 s. One request asks 29 questions about the member's question and gets all the labels back.

**What it labels**

- **Intent**, one of 10: rate, fee, hours, address or location, phone or contact, how-to, eligibility, list, fact about the credit union, other.
- **Rate type:** APR, APY, dividend rate, interest rate, or none.
- **Past date:** does the question ask how things stood on a named past date?
- **Change:** does it ask how something changed over time?
- **Section:** for each of the 25 website sections, would the answer be filed there?

**What the labels do**

| Label | Effect |
|---|---|
| Intent: rate or fee | The answer comes from the extracted facts. Other intents use text search |
| Intent, any type | Adds a short instruction block for that question type to the answer prompt (hours, list or eligibility, how-to, facts about the credit union) and sets how many meaning-search windows are added: none for rate and fee, 6 for list, eligibility and facts, 3 otherwise |
| Rate type | Picks the APR, APY or dividend-rate column when a table shows several |
| Section | Boosts pages in that section in the keyword search. Only the top section is used, and only at probability 0.5 or more |
| Past date | With a date written in the question, selects the website copy as it stood then |
| Change | With a change word in the question, searches every copy and answers with each value and its dates |

**Safeguards**

- **Code checks back up the labels.** A date counts only if the label or the wording says so ("as of", "back in", a past-tense rate question) and the question contains a date. A change counts only if the label says so and the question has a change word, and it does not apply to "what was it before <date>". A "dividend rate" label becomes APY unless the question says "dividend".
- **The question is passed as data**, not as instructions.
- **Some things stay in code.** Terms and amounts are read by pattern, search synonyms come from a hand-written list, and dates are parsed by code.
- **If the call fails** (3 s timeout, one retry), the search runs on the plain question without labels.
- **Known limit:** the section label is right about 78% of the time on our check, so it only steers the search and the answer.

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
| "Are the lobby hours the same at every branch?" gets its own prompt bullet and up to 5 extra schedule excerpts (`MY_SOLUTION_HOURS_SAME`, `MY_SOLUTION_HOURS_SCHEDULES`, both on; 0 turns them off) | The branch-finder cards from `/contact` filled the keyword top 8 and the pages with a second schedule ranked about 30th, so the model saw one schedule and hedged. The bullet makes it answer "No" with each branch's schedule | dup-104 passes about 2 runs in 3 (the miss leaves out the Platteville schedule, the only one with "noon"). A "copy every day and time exactly" sentence was tried and dropped: it made dup-064 refuse in the pipeline (0 of 3) |
| A question asking which link or page shows a product's rates gets the product's own page, not the sitewide rates page (`MY_SOLUTION_LINK_PRODUCT`, on; 0 turns it off; one bullet in the "other" and how-to blocks) | The base rules rank rate sheets above product pages, so "which link shows the CD rates?" was answered with `/rates` and missed the product page the grader expects (dup-008) | Only applies when an excerpt from the product page is present. Tested: dup-008 3 of 3, dup-080 (locator URL) 3 of 3, dup-031 2 of 2; full public run QA 0.8822 to 0.9054 with no other question changed |

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
- **LLM judge:** the organizers' scorer has an optional judge (`--judge`). A stand-in, `my_solution/judge_eval.py`, re-scores a finished run with an OpenAI judge (`gpt-6.1-sol`): same question wording, same 1 / 0.5 / 0 scale and the same 50/50 blend as the scorer. It is used to compare two versions and to read why an answer was marked down. It is a development tool and is never used at answer time. The workflow is drawn in [`judge-workflow.md`](judge-workflow.md).

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

- The 2 s full-marks speed line is not met. The answer call is about 90% of the time. One run had a single 8.3 s answer (probably a timed-out call that was retried). A failed answer call (such as a timeout after the 6 s limit and one retry) is not turned into "I don't know": the answer says the model did not respond, `conflict_note` names the error, and it is not cached. In one 3-pass test, 2 of 120 answers timed out, both on hours questions, which have the longest answers.
- Accepted misses on the public set: dup-049, dup-008, dup-088 (two readings of the question), dup-104 (partly fixed by the hours switches in section 4: about 2 runs in 3 now list every schedule; the stand-in judge still marks it down because the reference quotes Cedar Rapids and the answer leads with Cedar Falls) and dup-005 (a range instead of every rate). dup-008 was fixed by the link rule in section 4. dup-005 has an empty `must_include`, so the harness keyword score is 0.0 for it whatever the answer says (`scoring.py` line 122); only the judge can score it.
- Several public questions score below full marks because the benchmark's reference and the website disagree, or because of how the scorer works. Two of them (dup-005, dup-088) are also partly our own misses. They are listed in section 9.
- Hours, awards and similar facts are not in the fact table, so they depend on text search.
- On the tiny selftest fixture, a reworded certificate question is sometimes refused. This was not seen with "current" wordings on the real data.
- Window search needs the committed vectors in `my_solution/.embed_cache`. If a snapshot changes, they must be rebuilt, and until then that snapshot silently falls back to keyword search.

## 9. Reference mismatches and scoring quirks

These public questions score below full marks for reasons tied to `eval/public_eval.jsonl` or `harness/scoring.py`: the expected answer or source does not match what the website says, the reference reads the question one way and the answer another, or the scorer gives 0.0 whatever the answer says. They are not site conflicts: `conflicts()` lists places where the website contradicts itself, and none of these is that. The first five rows (dup-064, dup-066, dup-005, dup-049, dup-088) lower the harness score directly. The dup-011 row and the hours-style row (dup-064, dup-065, dup-066) cost nothing in the harness keyword check and could only matter if the judge marks the answer down. The "Cause" column says whose issue it is, and two rows (dup-005, dup-088) are partly ours. We did not change any answer to match the reference, because that would mean stating something the site does not say. Scores are in section 7; this section lists causes and the relative size of each effect.

| Question | What the benchmark expects | What the website and our answer say | Cause | Effect on score | Why we left it |
|---|---|---|---|---|---|
| dup-064 general lobby hours | Sources: the homepage and `/contact` | The homepage has no hours. `/contact` gives only when staff reply to general questions (8:30 a.m.-5:30 p.m.), not lobby hours. The lobby schedule is in the branch articles, which we cite | Reference | Small: the source check fails (15% of the question) | Citing `/contact` for lobby hours would be wrong, and the prompt says not to treat reply hours as lobby hours |
| dup-066 drive-up hours | Source: the Cedar Rapids article | Five branch articles (Cedar Rapids, Cedar Falls, Waukee, Grimes, Platteville) state the same Monday-Friday 8 a.m.-6 p.m. drive-up hours, so which one is cited is arbitrary. Two Madison articles say 9 a.m.-5 p.m. | Reference | Small: the source check fails (15% of the question) | A rule that favours one named branch's article would be typed in for this question |
| dup-005 certificate rate | The reference wants every certificate rate; `must_include` is empty | We give a range (rule 5) instead of every rate. Separately, `scoring.py` line 122 gives a keyword score of 0.0 for an empty list, whatever the answer says | Scorer, and partly ours (range, not every rate) | Large: the whole question without `--judge`; only the judge can score it | A rule change for certificates risks the tier questions that score 1.0 |
| dup-049 "Do any savings tiers pay 0.35% APY?" | No: Share Savings tops out at 0.20% | We answered yes: Investor's Choice Money Market pays 0.35% APY, as `/rates` and the savings pages state (the Health Savings Account row says 0.35% too). Both 0.35% tiers are on `/rates` in all five copies | Reference reads "savings tiers" as Share Savings only | Large: the whole question | Fitting to that reading is question-specific |
| dup-088 volunteer time off last year | 294 (the 2023 figure) | The answer varies between runs: the latest stated count (256, for 2024) with a note that the latest year gives none, or "I don't know". Two readings of "last year": the 2023 count (294) and the 2024 count (256) are both on the site, in every copy | Reference, and partly ours (the answer is unstable between runs) | Large: the whole question | Giving 294 means answering with an older year for a "last year" question |
| dup-011 mortgage rates right now | Headline 30-year 7.13% plus a 15-year rate of 6.25% | The newest `/rates` page shows 15-year fixed conventional at 6.75% (APR 6.88%), which is what we give. 6.25% appears only as a home-equity line (HELOC) rate. No copy of `/rates` in any of the five crawls shows a 15-year conventional rate of 6.25% (it ran 5.625% to 6.75%) | Reference | None locally (only "7.13" is checked); the judge could mark it down | Our figure matches the page |
| dup-064, dup-065, dup-066 hours (style) | "Give a typical schedule and ask which branch"; drive-up hours "at most branches" | We say general hours are not established, give the one branch schedule the excerpts hold, and ask which branch. The prompt forbids inventing a typical schedule | Reference (style) | None locally (keyword check passes); the judge could mark the answers down | A typical schedule would state something the excerpts do not |

How to read this: a source check that fails costs 15% of that question's score, because `score = 0.85 x correctness + 0.15 x source`. Extra sources are not penalised, but padding the list with pages the answer did not use would be gaming the check, so we cite only the pages that state the facts we give.
