# Task 5, proposal 1 (gpt-6.1-sol through the API, reasoning effort medium)

Tokens: 39000 input, 2337 output.

## Diagnosis

- **dup-001**: The final Output format sentence explicitly excludes minimum deposits unless requested, explaining the missing minimum. Rule 5's sentence, "The standard (not jumbo) personal product is the default," explains excluding jumbo. Including jumbo would broaden the answer's scope, not merely add a qualifier; it conflicts with the requested scope protection.
- **dup-009**: The final Output format sentence excludes effective dates and other unrequested figures, discouraging the associated APRs and loan limits. Rule 5's first sentence requires only a range and what it depends on, not endpoint-to-tier mappings. However, Rule 6 already says, "For loans and cards, state the APR," so the missing APR is also an instruction-following failure, not solely a restriction imposed by the prompt.
- **dup-040**: Rule 4's sentence, "Personal products are the default unless the question says business," and Rule 5's personal-product default explain omitting business cards. The Platinum range is explicitly supported by the product excerpt and should not be reduced to its minimum to satisfy this grader. More importantly, none of this case's excerpts states the personal Rewards Visa's numeric APR range, so today's answer includes unsupported information. Qualifier edits cannot legitimately reproduce the entire reference.
- **dup-050**: No sentence requires omitting the dividend rate: Rule 6 explicitly requires it when the question asks for the rate. Rule 7's "State each fact once with one value" may encourage treating dividend rate and APY as alternatives, but that is an interpretation, not an established cause. The final Output format sentence explicitly explains excluding the effective date. Grader runs 2 and 3 incorrectly credit a dividend rate absent from the displayed answer.
- **dup-052**: There is no displayed omission: today's answer includes every threshold and APY the grader says is missing. Rule 5's range requirement and Rule 7's prohibition on other-tier values could cause omissions in other runs, but they did not cause the alleged omission here. This case needs grading or answer-log verification rather than a claim that the prompt suppressed those details.

## Proposed edits to the system message (applied as variant H1, `my_solution/prompt_h1_edits.json`)

### Edit 1

Find:

> When the question names no tier and a product's rate varies by tier (loan amount, balance, credit), always give that product's full range from its lowest to its highest value, and say what it depends on; that range counts as the product's one value under rule 7.

Replace with:

> When the question names no tier and the requested rate varies by tier, give the full applicable range with its endpoint tiers; if a range would hide a distinct intermediate rate or a reversal in how rates vary across tiers, give the applicable tier-to-rate mappings instead. Keep companion measures paired with their respective tiers.

### Edit 2

Find:

> Never list old, alternative or other-tier values in `answer`.

Replace with:

> Never list superseded or out-of-scope values in `answer`; applicable ranges, tier mappings and separately labeled companion measures are not conflicting alternatives.

### Edit 3

Find:

> Besides the values asked for, include only the tier they apply to: no effective dates, minimum deposits, payment examples or other figures unless the question asks for them.

Replace with:

> Alongside each requested value, include its directly applicable conditions and qualifiers, such as the minimum to open or earn it, tier boundaries, eligibility requirements and stated effective date. Include the corresponding APR with a requested interest rate, and the corresponding dividend rate with a requested APY, when stated. Select the applicable scope and resolve source conflicts before adding these details; use only matching rows and directly applicable disclosures, without borrowing companion values or dates from superseded records. These details do not authorize values for an unrequested offering, tier, term or promotion. Omit payment examples and unrelated figures unless requested.

## Risks it named

These are narrow completeness edits, not a promise of full reference scores. They preserve the schema, sentence limit, personal/standard defaults, source precedence and insufficient-information response. Ambiguous scope remains intentionally unchanged: satisfying the jumbo and business-card portions of the references would require a separate scope-policy change, not a qualifier exception. Older excerpts for the same offering are the main regression risk: the model could attach an older companion rate or date to a selected current value, so the replacement explicitly forbids that mixing. Existing trust precedence can still prefer an older higher-trust source over a newer lower-trust source; this proposal does not silently change that policy. Multi-tier tables create risks of attaching an APR to the wrong amount limit, treating overlapping 'or less' limits as disjoint bands, or hiding a nonmonotonic rate behind a range. Tier mappings and preserved row pairings reduce those risks, but large tables may produce dense answers within the unchanged sentence limit. Extra disclosures can also cause a forbidden-value match if the forbidden list itself includes an otherwise applicable qualifier; no general prompt can guarantee compliance with an undisclosed list. If forbidden-value scanning covers the entire JSON object, the existing requirement to name losing values in conflict_note can independently trigger zero scores. Validate that scanner's scope and repair the inconsistent grading/logs before attributing score changes to these edits.

## Answers it expected

- **dup-001**: The standard 17-month Fixed Certificate Special pays 4.10% APY with a corresponding 4.06% dividend rate and a $1,000 minimum to earn, effective September 1, 2026.
- **dup-009**: For 30-year fixed conventional purchase mortgages, quoted interest rates range from 7.13% with 7.27% APR for the row labeled $100,000 or less to 7.25% with 7.29% APR for the row labeled $832,750 or less, effective September 25, 2026. The other purchase rows quote 7.25% interest with 7.32% APR at $300,000 or less and 7.34% APR at $200,000 or less; refinance APRs differ.
- **dup-040**: The personal Platinum Visa's standard variable APR is 12.50%–19.50%, depending on creditworthiness, effective January 1, 2026. The excerpts do not state a numeric APR for the personal Rewards Visa.
- **dup-050**: Bright Savings pays a 2.23% dividend rate and 2.25% APY on balances of $0.01–$1,000,000, effective June 2, 2026. To earn dividends, you must be enrolled in eStatements by the end of the month.
- **dup-052**: Free Checking earns 0.00% APY, effective June 2, 2026. As of the same date, 1st Rate Checking earns 0.00% APY on $0.01–$4,999.99, 2.50% APY on $5,000–$24,999.99, and 0.10% APY on $25,000 or more.
- **dup-016**: For a 60-month auto loan on a 2025 vehicle, the applicable 2024–27 model-year tier offers an APR as low as 5.39%, effective August 31, 2026.
- **dup-017**: For an 84-month auto loan on a 2024 vehicle, the applicable 2024–27 model-year tier offers an APR as low as 5.59%, effective August 31, 2026.
- **dup-035**: The personal Platinum Visa's standard purchase APR is a variable 12.50%–19.50%, depending on creditworthiness, effective January 2, 2026.
- **dup-045**: Share Savings pays a 0.15% dividend rate and 0.15% APY for balances of $10,000–$24,999.99, effective June 15, 2026.
