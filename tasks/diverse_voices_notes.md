# diverse_voices eval set: gold notes

File: `eval/subsets/diverse_voices.jsonl` (60 questions = 15 facts x 4 voices; same format as `public_eval.jsonl`, plus a `voice` field the scorer ignores).
Voices: **T** typos / texting / voice-to-text, **S** second-language / limited English, **K** terse keywords, **R** rambling or anxious, **F** fluent and precise.
Each group uses four of the five voices (T 13, S 11, K 11, R 13, F 12 questions). Gold was written from the snapshot pages, never from the system's answers.

| Group | Fact (expected) | Source of the gold | Origin |
|---|---|---|---|
| g01 | 17-month special certificate APY now: 4.10% | `/rates`, latest copy | known (dup-001) |
| g02 | 60-month auto, 2025 model year: 5.39% APR (not 5.34%) | `/rates`, `2024-27 Model Year | 60 Months | 5.39% APR` | known (dup-016) |
| g03 | Share Savings $10,000-$24,999.99 dividend: 0.15% | `/rates`, Share Savings table | known (dup-045) |
| g04 | Routing number 273974581 | `/business/cash-management`, "routing number (273974581)" | known (dup-054) |
| g05 | 22 branches (not "24 branch") | news releases, "22 branch office locations" | known (dup-073) |
| g06 | Hy-Vee branch closes March 31, 2026 | `/newsroom/dupaco-evolves-with-purpose...`, "This location will close March 31, 2026" | known (dup-074) |
| g07 | High-Yield Savings, $150,000: 1.85% APY | `/rates`, `$100,000 - $249,999.99 | 1.83% | 1.85%` | known (ho-009) |
| g08 | Launchpad Savings: 3.25% APY | `/rates`, `Launchpad Savings | $5 - $1,000 | 3.21% | 3.25%` | NEW |
| g09 | Health Savings Account $10,000-$24,999.99: 0.30% APY | `/rates`, HSA table | NEW |
| g10 | Boat & RV $25,000-$39,999, 72 months: 7.34% APR | `/rates`, `$25,000-39,999 | 72 Months | 7.34%` | NEW |
| g11 | Peosta branch: 185 Peosta St., Peosta, IA 52068 | `/contact`, "Dupaco Branch 185 Peosta St., Peosta, IA, 52068" | NEW |
| g12 | 17-month special APY as of July 2026: 3.85% (now 4.10%) | copy 03 (taken 2026-06-09), `/rates`, `17 Month Fixed Certificate Special | 3.81% | 3.85% | $1,000`; copy 04 (2026-08-27) shows 3.95%, latest 4.10% | NEW (dated) |
| g13 | 1st Rate Checking $5,000-$24,999.99 as of May 2026: 3.00% APY (from June 9: 2.50%) | copy 02 (taken 2026-05-19), `/rates`, `$5,000 - $24,999.99 | 2.96% | 3.00%`; copy 03 shows 2.47% / 2.50% | NEW (dated; the K variant uses `as_of=2026-05-31` and no date in the words) |
| g14 | 40-year fixed mortgage: not listed (should refuse) | `/rates` lists 30-, 20- and 15-year only; the text "40-year fixed" occurs nowhere in any copy | NEW (absence) |
| g15 | SWIFT/BIC code: not listed (should refuse) | the string "SWIFT" occurs nowhere in the latest copy | NEW (absence) |

## Checks done before running (step 3)
- 15 groups, every group has exactly 4 members, ids unique, valid JSONL.
- Every `must_include` value was found in the page text of the copy the question points to (latest copy; copy 03 for g12; copy 02 for g13).
- The two refusal facts were checked for absence across all five copies.
- One inherited trap value (271176899 in g04, from the public set's gold) does not occur on the site at all; it is harmless.

## Things to remember when reading results
- g05 (branch count) and g06 (Hy-Vee date) depend on rules the Python project already treats specially (count answers from the latest dated release); g14 and g15 test an honest refusal where nearby numbers exist.
- g12 and g13 test dated answers: g12 with a year-less month in one voice, g13 with an `as_of` argument in one voice.
- Question wording is invented by me, not collected from real members; it aims at realism (errors, word order, rambling) without caricature.
