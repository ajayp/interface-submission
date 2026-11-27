# diverse_voices_3 eval set: gold notes

File: `eval/subsets/diverse_voices_3.jsonl` (60 questions = 15 NEW facts x 4 voices; voices T typos/texting, S second-language, K terse keywords, R rambling/anxious, F fluent; 12 per voice).
Aimed at the categories sets 1 and 2 barely tested: counts and conflicting statements, branch hours, lists, eligibility and conditions, minimums, refusals. 0 questions overlap earlier sets. Gold from the latest snapshot copy's page text only (sentences quoted below); counts were checked by reading the release dates myself, not through the system's "latest statement" rule.

| Group | Fact (expected) | Source of the gold |
|---|---|---|
| g01 | 118 counties served (not 112 / 108) | `/about` "118 counties"; releases "Dupaco serves residents in 118 counties" |
| g02 | over 600 employees (not 700) | newest dated releases (2026-04-06, 04-23, 05-05): "It has over 600 employees and 22 branch office locations"; an older post said "nearly 700" |
| g03 | Platteville lobby closes Friday 5:30 p.m. | `/newsroom/dupaco-community-credit-union-celebrates-completion-of-expanded-branch`: Lobby Friday 8:30 a.m.-5:30 p.m. (Cedar Rapids Friday is 6 p.m., a trap) |
| g04 | Cedar Rapids Learning Lab lobby Saturday 8:30 a.m.-12:30 p.m. | `/newsroom/dupaco-celebrates-completion-of-newest-learning-lab` (Platteville Saturday is 9-noon, a trap) |
| g05 | ways to join: charter area, immediate family member, Rural Ideas Network | `/about/join` "You're Eligible to Join If..." |
| g06 | $25 to join | `/about/join` "open a savings account with $25 or more" |
| g07 | Bright Savings: consumer members only | `/rates` Bright Savings note "available exclusively to consumer members. Business, fiduciary, minor, estate, and trust accounts are not eligible" (gold needs the word "consumer": an answer saying only "individuals" would be a gold-wording miss) |
| g08 | Bright Savings cap $1,000,000 | same note "limited to One Million dollars ($1,000,000.00)" |
| g09 | Bright Savings dividends need eStatements | same note "To earn dividends, make sure you're signed up for eStatements" |
| g10 | Launchpad: at $1,000 move to an IRA within 90 days | `/rates` Launchpad limitations |
| g11 | Investor's Choice minimum to open $2,500 | `/rates` table, Min. to Open $2,500.00 |
| g12 | regular certificate terms 6, 12, 18, 24, 30, 36, 48, 60 months | `/rates` Regular Certificates table (checked: exactly these eight terms) |
| g13 | IRA types: Roth and Traditional | `/rates` Retirement / IRAs tables |
| g14 | mobile check deposit daily limit: not listed (should refuse) | "mobile deposit" appears 113 times across the copies, never with a limit, amount or "per day" nearby |
| g15 | night depository: not listed (should refuse) | the text "night depository" occurs in no copy |

Checks before running: 15 groups x 4, unique ids, 0 overlap with the public, held-out and set 1 and 2 questions, every `must_include` found in the latest copy's page text (the g12 terms checked against the table), refusal absence checked across all five copies.
Known limits: gold uses substring matching, so g07 ("consumer"), g05 ("family member", "Rural Ideas") and the list groups depend on the answer using those words; a miss there is first checked for being a gold-wording problem. The hours (g03, g04) come from 2021 news releases, the only place the site states them.
