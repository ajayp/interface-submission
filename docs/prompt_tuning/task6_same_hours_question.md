# Task 6: a yes/no question about all branches is answered with "the excerpts don't establish it"

Case (in `cases/`): **dup-104** "Do all Dupaco branches keep the same lobby hours?"
Guards (in `cases/guard/`, must keep passing): **dup-064**, **dup-065** (lobby hours), **dup-066** (drive-up hours),
**dup-102** (hours for a branch no excerpt covers: must still be declined), **dup-073** (branch count),
**dup-016**, **dup-017**, **dup-035**, **dup-045** (stale or tier values) and **dup-145**, **dup-147** (must refuse).

## What we know
- The excerpts sent to the model do contain two different lobby schedules for two named branches (one of them closes Saturday 12:30 p.m.).
  The reference answer is "No", with each schedule and its branch. The answer that scores zero has no times at all.
- Today's answer opens with "The excerpts don't establish whether all Dupaco branches have the same lobby hours ... which branch are you
  asking about?". Over 5 repeats with the current prompt, 1 answer in 5 contains the 12:30 time. The model hedges instead of answering "No".
- One hand-written extra rule in the hours block ("if it asks whether branches share the same hours and the excerpts show different
  schedules, answer No and give each schedule") gave 2 in 5. That is within noise, so it was not kept.
- The hours questions dup-064, dup-065 and dup-066 pass 5 of 5 today (they give the schedule of one named branch).

## Question to settle
Is there a general instruction that makes the model answer a "same for all?" or "do all ... have ...?" question from the evidence it has
(No, with each case it shows), without making it invent a universal answer when the excerpts cover only one case and say nothing about the others?

**Ask for OpenAI (copy this):**

> You are helping improve the SYSTEM MESSAGE of a question-answering step for a credit union. A second model grades each answer
> against a reference answer: 1 if it states the reference facts correctly and nothing contradicting them, 0.5 if partially correct,
> 0 if wrong, stale or evasive. Separately, an answer scores zero if it contains any value from a forbidden list. I will paste, for each
> case: the reference answer, what the model answered today, the exact system message and the exact user message. The case is a
> yes/no question about whether something is the same for all branches. The excerpts show different values for different branches, but
> the answer says the excerpts do not establish it, and gives no values.
> 1. Say which sentence of the system message makes the model hedge instead of answering.
> 2. Propose the smallest change to the SYSTEM MESSAGE (the exact text to add, change or remove) so that a question asking whether a
>    fact is the same for all branches, products or cases is answered "No" and with each different value and its branch, when the excerpts
>    show two or more different values, while a question about a branch or case that no excerpt covers is still answered "I don't know".
> Constraints: the rule must be general, so it makes sense for any member question; it must not mention this question, a product, a
> branch, a number or a page. Do not change the JSON schema. Answers stay 1 to 3 sentences. Keep "I don't know" for questions the
> excerpts do not answer.
> 3. Tell me which kinds of questions the change could make worse, in particular questions about one named branch, and questions where
>    the excerpts show only one value and say nothing about the others.

## Acceptance
- [ ] dup-104 contains "12:30" or "noon" in most repeats (the current prompt: 1 in 5).
- [ ] Every guard still passes: dup-064/065/066 keep giving the named branch's schedule; dup-102 is still declined; the stale and tier
      guards still give their right values and never the forbidden ones; dup-145 and dup-147 still refuse with no number.
- [ ] Then, in the repo: 3 runs of the 40 public questions with the new prompt, compared with 3 runs of the current one, with and
      without `judge_eval.py`. Adopt only if judged accuracy rises and no stale value appears in any run.

## Results
