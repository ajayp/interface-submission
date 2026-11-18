# Hand-made conflicts gold list (andretodo Step 1)

Status: accepted by the user 2026-11-16 (counts kept, marked less sure; 3 headline mortgage rows; branch count 22 unverified).

File: `tasks/conflicts_gold_hand.json` (same format as `harness/selftest/conflicts_gold.json`).
Made 2026-11-16 by reading the newest copy (05) with plain text searches, NOT with our extraction code
(`table_parse.py`, `fact_match.py`, `conflicts_v2.py`), so it is independent of what `conflicts()` can see.
Kept separate from the older 35+1 table key (`tasks/conflicts_answer_key.md`); both get scored.

How the grader matches (harness/scoring.py:145): an entry counts as found when our conflict names both gold values,
or one value plus a topic keyword. Winner credit when our `resolution` contains `correct_value`.

## Rates (high confidence)

| id | Fact | Values on the site | Winner and why |
|---|---|---|---|
| r1 | Achieve Money Market intro APY | 3.25% on `/membermoneymarket-lp` (page carried over, fetched 2026-06-15) | **3.66%** on `/earn-more` and `/personal/savings-account` ("As of 8/24/26 ... 4.00% dividend rate and 3.66% APY"); newer, product page |
| r2 | Auto loan 60-month APR (payment example) | 5.34% on `/calculators/vehicle-affordability`, `/switch-and-earn` (fetched 2026-06-09) | **5.39%** on `/rates` (effective 08/31/2026) and both auto loan pages |
| r3 | 1st Rate Checking top APY | "up to 3.00% APY" on `/newcard-balancetransfer-lp` | **2.50%** on `/rates` ($5,000-$24,999.99 tier, effective 06/02/2026); rate sheet wins over promo page |
| r4 | Mortgage Rate Relief special APR | 5.210% (news release March 31, 2025), 4.967% ("as low as", news release March 02, 2026) | **5.196%** in the `/homebuying-guidance` table (effective 04/22/2026): newest date and a product page. Not on `/rates`. Corrected after scoring: the first draft missed this table and chose 4.967% |
| m1 | Purchase 30-year fixed conventional, $832,750 or less: rate | 6.000% on `/homebuying-guidance` (effective 04/22/2026) | **7.25%** on `/rates` (effective 09/25/2026) |
| m2 | Same row: APR | 6.037% on `/homebuying-guidance` | **7.29%** on `/rates` |
| m3 | Refinance 30-year fixed conventional, $832,750 or less: APR | 6.049% on `/mortgage-refi` (effective 04/22/2026) | **7.30%** on `/rates` |

m1-m3 stand for a whole stale table (all purchase/refinance rows on those two pages); the older key lists 24 such rows
separately. The organizers' granularity is unknown, so only the headline rows are here.

## Counts about Dupaco (medium confidence: the organizers may treat old press releases as history, not conflicts)

Every news release ends with an "about Dupaco" paragraph carrying that day's numbers; 114 releases are still on the site.

| id | Fact | Older values still on the site | Winner and why |
|---|---|---|---|
| c1 | Assets | $2.1 to $3.5 billion (releases 2020-2026) | **$3.6 billion** (newest releases, May 2026; Owners Manual Summer 2026 "as of May 31, 2026") |
| c2 | Employees | "nearly 700" / "more than 650" (2022-2024 releases) | **600** ("over 600", 2026 releases; `/about` "600+ employees") |
| c3 | Branches | 23 (Jan-Mar 2026 releases), 24 (one 2024 release), 18 (`/about`, in a staff bio) | **22** (newest release, May 05, 2026). Least sure: the site's location list was not counted |
| c4 | Members | 129,000 to 170,000 (2020-2024 releases) | **182,627** (Owners Manual Summer 2026, "as of May 31, 2026"; the May 2026 release says "more than 179,000", which agrees) |

## Checked, no conflict found

- **Fees:** overdraft $30 everywhere; card late fee $15 (personal) vs up to $35 (business) are two different cards.
- **Card rates:** Platinum 12.50%-19.50%, Rewards 15.50%-21.00%, Business Platinum 15.50% agree across pages.
- **Hours:** stated only in news releases, each about a different branch; branch pages carry no hours text. No same-branch
  disagreement found.
- **Other loan payment examples** (personal 10.49%, boat 7.09%, ATV 8.34%, home improvement 8.50%) match `/rates`.

## Questions for the user (answered: accept all three suggestions)

1. Keep the count entries (c1-c4)? They depend on whether the organizers count old releases as conflicts.
2. m1-m3: keep three headline rows, or list every stale mortgage row (as the old key does)?
3. c3: is 22 the right branch count? (Not verified against a location list.)

## Score (2026-11-16, current head, one loading run with the key, 165 s)

`conflicts()` returned 40 entries (24 mortgage rows, 4 other mortgage rows... in short: 35 table rows, Mortgage Rate Relief, 4 counts; see `results/experiments/conflicts/conflicts_now.json`, not committed).

| Answer sheet | Found | Recall | Precision | F1 | Right winner | Pillar score (0.7 F1 + 0.3 winner) |
|---|---|---|---|---|---|---|
| Hand list (11, after the r4 fix) | 10 | 0.91 | 0.25 | 0.39 | 9/11 | 0.52 |
| Old key (35 table rows, rebuilt with `conflict_poc.py`) | 35 | 1.00 | 0.88 | 0.93 | 33/35 | 0.94 |

What the hand list shows that the old key could not:
- **Missed: r1, Achieve Money Market 3.25% vs 3.66% APY** (a rate written in a sentence on a carried-over promo page).
  A real gap in the sentence path.
- **Winner disagrees: c4 members.** `conflicts()` picks "179,000" (newest release, May 05, 2026); the sheet says 182,627
  (Owners Manual PDF, "as of May 31, 2026"). Both are true on their day; which one the organizers would pick is unclear.
- **Precision depends on granularity**, not on errors: 26 of the 40 entries are separate mortgage rows that the hand list
  folds into 3 headline rows (decision 2). If the organizers list rows one by one, precision is near the old key's 0.88.
- The 4 count entries are all found with the right winner except c4 (above).

## After the sentence fix (2026-11-17)

Two switches in the sentence path of `conflicts()` (both default on; `MY_SOLUTION_SENTENCE_CONTEXT=0` and `MY_SOLUTION_SENTENCE_UNSTATED=0` roll back):
1. **Context:** each rate sentence is read together with the sentence or line before it (`sentence_facts.py`), so a bare
   "3.66% APY" takes its product from the text just before it ("Achieve Money Market Account ...") instead of the page title.
2. **Unstated qualifiers:** two sentence facts of the same rate type and tier pair when one of them states no term and no intro
   (`fact_match.py` `blocked`). Tables keep the strict rule. A looser rule (ignoring tier, or intro) was tried first and rejected:
   it paired 0% for the $0 tier with 3.25%, and intro with after-promotion rates.

| Answer sheet | Before | After | Entries |
|---|---|---|---|
| Hand list (11) | found 10, winners 9, pillar 0.520 | **found 11, winners 10, pillar 0.569** | 40 -> 41 |
| Old key (35) | found 35, pillar 0.936 | found 35, pillar 0.928 | 40 -> 41 |

- The context switch alone changed nothing (0.000 on both lists). The two together add exactly one entry: Achieve Money Market APY
  3.25% vs 3.66% (winner 3.66%, the product page). The old key does not contain that conflict (it is built from tables only), so its
  precision falls by one entry (-0.009) although the entry is real.
- Stable: two further runs with fresh sentence calls gave the identical lists and scores. Selftest fixture: conflict found, right winner (F1 1.0).
- Evidence is one case. The rule is narrow (sentence vs sentence only, same product words, rate type and tier), but it was found
  by looking at this miss, so a new gold list is the way to check it.

## Adding more gold lists

`python my_solution/dump_conflicts.py --out results/conflicts/<name>.json` saves what `conflicts()` returns (about 40 s with the
caches set, 3 minutes without). `python my_solution/score_conflict_lists.py results/conflicts/<name>.json [--compare earlier.json] -v`
then scores it against EVERY `tasks/conflicts_gold_*.json` (no model calls): one line per list with found, precision, F1, winners
and pillar, and the misses with `-v`. A new list is added by saving a file with that name pattern. Current lists:
`conflicts_gold_hand.json` (11, hand-read), `conflicts_gold_table_key.json` (35, table rows, built with our reader: partly circular).

## Code-only scan for fees, hours and counts (2026-11-17, no API calls)

Scanned the newest copy by code (not by reading): fee rows and sentences grouped by label, hours lines per page, counts in text grouped by noun.
- **Fees: 0 real conflicts.** 6 labels carry more than one amount; 3 are the same fee written two ways in the two copies of the fee-schedule PDF
  ("$25.00 per hour" vs "$25.00"), 2 are the card late and returned payment fees (business card $35 vs personal $15: two products; returned payment $25 everywhere),
  1 is a formatting difference. Matches the earlier hand check.
- **Hours: 0 real conflicts.** Only 6 pages carry hours text; four news releases give hours for four different Learning Lab branches (four phone numbers),
  so the differences are different branches, not one branch with two schedules. `/contact` states phone-support hours 8:30 to 5:30 only.
- **Counts: one new candidate, c5, counties served.** The "about Dupaco" paragraph says 108 counties (2020-2021 releases), 112 (2020-2022), 118 (2022-2026
  releases and `/about`); winner 118. The 99 in a business article is Iowa's own county count, not Dupaco's. `conflicts()` does NOT list it: `count_facts.py`
  covers only assets, branches, employees and members. Added to the gold list as c5 (medium confidence, same kind as c1 to c4).
- Not conflicts: employees 627 (2025 Impact Report) against "600+" elsewhere (627 is over 600); 30,000 surcharge-free ATMs (one value only); 13 vs 50 states (the 13 is another context).

## Counties added to conflicts() (2026-11-17)

`count_facts.py` reads "Dupaco serves residents in N counties" as a fifth count (values 118, 112, 108; winner 118). Scored on the saved list (cached sentence reads,
no API cost): hand list found 12 of 12 (was 11 of 12), winners 11 of 12 (only c4 members is still disputed), pillar 0.541 -> 0.586; old table key found 35 of 35,
pillar 0.928 -> 0.919 (one extra, real, entry it cannot contain). `conflicts()` now returns 42 entries.
