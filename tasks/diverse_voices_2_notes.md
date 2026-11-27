# diverse_voices_2 eval set: gold notes

File: `eval/subsets/diverse_voices_2.jsonl` (60 questions = 15 NEW facts x 4 voices; same format and voices as set 1: T typos/texting, S second-language, K terse keywords, R rambling/anxious, F fluent; 12 questions per voice).
Written to test the four general fixes made after set 1 fairly: the facts and wordings were chosen without reference to the failure forms of set 1 ("number of dupaco branches", "banking in person", "May of 2026", an uncertain refusal), and no question or fact repeats the public, held-out or set 1 questions (checked: 0 overlap). Gold comes from the snapshot pages only.

| Group | Fact (expected) | Source of the gold |
|---|---|---|
| g01 | 24-month regular certificate: 2.50% APY | `/rates` latest, `24 Month | 2.48% | 2.50%` |
| g02 | 18-month Roth IRA certificate: 2.70% APY | `/rates`, `Roth: 18 Months | 2.68% | 2.70%` |
| g03 | Variable Traditional IRA, $15,000+: 0.60% | `/rates`, `Traditional: $15,000+ | 0.60% | 0.60%` |
| g04 | Investor's Choice Money Market, $100,000+: 0.40% | `/rates`, `$100,000+ | 0.40% | 0.40%` |
| g05 | Platinum Visa introductory balance transfer: 2.90% | `/rates`, `Introductory Balance Transfer Rate | 2.90%` |
| g06 | Fixed home equity loan, 120 months: 7.24% APR (not 6.74%) | `/rates`, `Loan - Standard (120 mo) | 7.24%` |
| g07 | Home improvement $20,001-$50,000, 180 months: 8.75% (not 8.50%) | `/rates`, `$20,001.00 - $50,000.00 | 180 Months | 8.75%` |
| g08 | 24-month personal loan: 9.99% APR | `/rates`, `24 Months | 9.99%` |
| g09 | 72-month auto, 2022 model year: 5.79% (stale 5.59% from the old 2021-22 table) | `/rates` latest `2021-23 Model Year | 72 Months | 5.79%`; copies 01-04 `2021-22 ... 5.59%` |
| g10 | 48-month regular certificate: 1.90% APY | `/rates`, `48 Month | 1.89% | 1.90%` |
| g11 | Flint Hill branch: 2245 Flint Hill Dr., Dubuque, IA 52003 | `/contact` branch card |
| g12 | Foreign currency exchange fee (incl. Canadian checks): $35.00 | fee schedule PDF (`/hubfs/dupaco-credit-union-fee-schedule-miscellaneous-fees...`) |
| g13 | 12-month certificate APY as of May 2026: 2.90% (from June 9: 3.40%) | copy 02 (2026-05-19) `/rates` `12 Month | 2.88% | 2.90%`; copy 03 `3.37% | 3.40%` |
| g14 | 25-month special certificate APY as of May 2026: 3.60% (product gone after copy 02) | copy 02 `/rates` `25 Month Fixed Certificate Special | 3.57% | 3.60%`; absent from copies 03-05. The K variant passes `as_of=2026-05-31` and has no date in the words |
| g15 | Reverse mortgage rate: not listed (should refuse) | the text "reverse mortgage" occurs in none of the five copies |

Checks before running: 15 groups x 4, unique ids, 0 overlap with earlier sets, every `must_include` value found in the page text of the right copy (copy 02 for g13 and g14, latest copy otherwise), absence of the refusal fact confirmed in all copies.
Reading the results: g13 and g14 are dated (g14 is a product that vanished from later copies, answerable only from the older copy); g15 tests an honest refusal where nearby mortgage rates exist.
