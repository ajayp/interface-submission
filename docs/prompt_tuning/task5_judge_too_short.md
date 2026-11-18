# Task 5: the answer is correct, but the judge marks it down as too short

Cases (in `cases/`): **dup-001** 17-month special certificate APY; **dup-052** checking account rates;
**dup-009** 30-year mortgage rate; **dup-050** Bright Savings rate; **dup-040** credit card rates.
Guards (in `cases/guard/`, must keep passing): **dup-016**, **dup-017** (stale value on another page),
**dup-045** (balance tier), **dup-035** (standard vs promotional card rate).

## What we know
- The scorer has an optional judge (`harness/scoring.py`, `--judge`): a model compares our answer with the reference answer and gives
  1, 0.5 or 0; half of a question's correctness then comes from it. Our stand-in judge (`my_solution/judge_eval.py`, `gpt-6.1-sol`)
  lowered accuracy from 0.86 to 0.81 in three baseline runs. Each case file lists its reason from all three runs.
- All five answers pass the keyword check. The judge gives 0.5 because the reference answer contains detail ours leaves out:
  - dup-001: the minimum deposit ($1,000) and the jumbo version of the same special (4.20% APY, $100,000 minimum).
  - dup-052: the balance thresholds of each tier, not only the lowest-to-highest range.
  - dup-009: the APR beside the rate, and the loan-amount limit each rate applies to.
  - dup-050: the dividend rate beside the APY.
  - dup-040: the standard rate named as such (not a range that mixes in other card rates), and the business cards.
- The cause is our own instruction. Output format says: "Besides the values asked for, include only the tier they apply to: no
  effective dates, minimum deposits, payment examples or other figures unless the question asks for them." Rule 5 says to give one
  range when no tier is named, and rule 7 says one value per fact.
- Why that instruction exists: any `must_not_include` value in the answer zeroes the question (a stale rate, another tier's rate,
  a promotional rate). Every extra number is a chance to hit one. In ten practice runs today there were 0 such hits.

## Question to settle
Is there a general way to give the detail a careful human expert would add (what the value depends on, the condition to get it, the
closely related version of the same product) without quoting values the member did not ask about? Or is the safer choice to keep
answers short and accept the judge's 0.5 on these?

**Ask for OpenAI (copy this):**

> You are helping improve the SYSTEM MESSAGE of a question-answering step for a credit union. A second model grades each answer
> against a reference answer: 1 if it states the reference facts correctly and nothing contradicting them, 0.5 if partially correct,
> 0 if wrong, stale or evasive. Separately, an answer scores zero if it contains any value from a forbidden list (an old rate, another
> tier's rate, a promotional rate). I will paste, for each case: the reference answer, the grader's reason, what the model answered
> today, the exact system message and the exact user message. The cases are answers that are correct but that the grader calls
> partial because they leave out detail the reference includes.
> 1. For each case, say which sentence of the system message made the model leave the detail out.
> 2. Propose the smallest change to the SYSTEM MESSAGE (the exact text to add, change or remove) that lets the answer include the
>    conditions and qualifiers that belong to the value asked for (for example the minimum to earn it, the tier boundary it applies
>    to, the APR that goes with a loan rate, the rate that goes with an APY), while still never quoting a value for a product, tier,
>    term or promotion the question did not ask about.
> Constraints: the rule must be general, so it makes sense for any member question; it must not mention this question, a product, a
> branch, a number or a page. Do not change the JSON schema. Answers stay 1 to 3 sentences. Keep "I don't know" for questions the
> excerpts do not answer.
> 3. Tell me which kinds of questions the change could make worse, in particular questions where another page shows an older value
>    for the same product, or where a table has several tiers.

## Acceptance
- [ ] Each case answer still contains its must-include values and none of its must-not-include values.
- [ ] The four guard cases still pass: dup-016 gives 5.39% and not 5.34%; dup-017 gives 5.59% and not 5.54%; dup-045 gives 0.15% and
      neither 0.30% nor 0.40%; dup-035 gives 12.5% and not 9.9%.
- [ ] Then, in the repo: 3 runs of the 40 public questions with the new prompt, compared with 3 runs of the current one, with and
      without `judge_eval.py`. Adopt only if judged accuracy rises and no stale value appears in any run.

## Not part of this task
- dup-011 ("What are the mortgage rates right now?", judged 0): our 15-year rate of 6.75% is what the rate sheet shows; the reference
  answer says 6.25%, which is not on the home-loans page in the newest website copy. Nothing to fix on our side.
- dup-064, dup-065, dup-066, dup-104 (hours given for one named branch): already covered by task 1 and task 4.

## Results

Proposal 1 (`task5_proposal1.md`, variant H1), judge = `gpt-6.1-sol` stand-in. Nine cases, one run; then 40 questions, 3 runs each arm.

| Case | Answer after (H1) | Judge before -> after | Pass? |
|---|---|---|---|
| dup-001 | "Dupaco's standard 17-month special certificate earns 4.10% APY." | 0.5 -> 0.5 | no change (still no minimum, no jumbo) |
| dup-052 | every tier with its balance range, plus effective date | 1.0 -> 1.0 (0.75, 0.75, 1.0 -> 1.0 x3 in the full runs) | better |
| dup-009 | 7.13% for $100,000 or less, 7.25% above, effective date | 0.5 -> 0.5 (APRs still missing) | no change |
| dup-050 | 2.25% APY (2.23% dividend rate), balance range, minimum, effective date | 0.5 -> 1.0 | better |
| dup-040 | same rates plus effective date | 0.5 -> 0.5 (business cards still missing) | no change |
| guards (4) | all correct, no forbidden value; each answer longer | 1.0 -> 1.0 | pass |
| 40 questions x 3 | accuracy 0.854 = 0.854; judged 0.806 -> 0.813; 0 stale values | | dup-147 (should refuse) failed in 1 of 3 runs |

Not adopted.

## Conversation through the API (3 rounds, gpt-6.1-sol): outcome = keep the current prompt

Files: `task5_round1_message.md` / `task5_round1_reply.md` (proposal H2), round 2 (H3), round 3 (its final evaluation; no new edits).
Each proposal was run twice on 13 questions (`eval/subsets/task5_cases.jsonl`: 5 cases, the mortgage category question, 4 guards,
3 must-refuse). Every version kept keyword score 1.00, 0 forbidden values and all three refusals.

| Version | Judged accuracy, 2 runs | What changed in the answers |
|---|---|---|
| G2 (current) | 0.884, 0.884 | |
| H1 (proposal 1) | see the table above (40 questions) | tier boundaries and dividend rate added; effective dates added; one refusal lost in the 40-question runs |
| H2 | 0.901, 0.921 | no effective dates; Bright Savings gains the dividend rate; mortgage answer lists loan limits |
| H3 | 0.901, 0.901 | same gains; still no certificate minimum and no mortgage APR although the edits require them |

The model's own verdict after round 3: stop, keep the original. Its reasons, which I agree with:
- The edits explicitly required the certificate minimum and the mortgage APR and the answer model still left them out: stronger
  wording is not fixing adherence at reasoning effort `none`.
- The judged gain comes almost entirely from one answer (Bright Savings), and that answer contains a new factual error: it calls the
  $0.00 minimum to open the "minimum to earn" (the table says $0.01). The judge gave it full credit, so the judge overstates it.
- One credit-card answer still quoted the introductory rate although the edits excluded it.
- Two references cannot be satisfied by a general rule: the credit-card reference wants business cards and rejects a range the
  excerpts support; the mortgage reference contains a value (6.25%) that is not on the page.

Decision: prompt G2 stays the default. H1, H2 and H3 remain available as variants (`MY_SOLUTION_PROMPT_VARIANT`) for the record.
Cost of the conversation: 175,597 input and 4,467 output tokens, about $0.40 at $2 / $10 per million.
