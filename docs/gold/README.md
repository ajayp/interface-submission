# Conflict gold lists

Two answer sheets for `conflicts()`, because the organizers' own list is not part of the kit. They check what `conflicts()` lists and which value it picks.

| File | Entries | How it was made |
|---|---|---|
| `conflicts_gold_hand.json` | 12 | Read by hand from the newest website copy with plain text search, **without** the extraction code, so it does not depend on what `conflicts()` can see. Table below. |
| `conflicts_gold_table_key.json` | 35 | Every stale-versus-current rate table row, built with the project's own table reader (so partly circular). |

Both use the same format as `harness/selftest/conflicts_gold.json`. A conflict counts as found when it names both gold values, or one value plus a topic
keyword (`harness/scoring.py`); the winner counts when the submitted `resolution` contains `correct_value`.

## Score the current system against them

```bash
python my_solution/dump_conflicts.py --out results/conflicts/now.json        # about 3 minutes cold, needs OPENAI_API_KEY
python my_solution/score_conflict_lists.py results/conflicts/now.json -v     # no model calls; scores against every docs/gold/conflicts_gold_*.json
```

Latest result (42 entries listed): hand list found 12 of 12, right winner on 11, precision 0.29; table key found 35 of 35. Precision is low against the hand
list only because it folds each stale mortgage table into one headline row (m1 to m3) while `conflicts()` lists every row separately. The rows are kept
separate because the organizers' granularity is unknown. The one disagreement on winners is the members count (c4): the system picks the newest news release
(179,000), the hand list picks a later PDF figure (182,627).

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
| c5 | Counties served | 108 (2020-2021 releases), 112 (2020-2022) | **118** (2022-2026 releases and `/about`) |

## Checked, no conflict found

- **Fees:** overdraft $30 everywhere; card late fee $15 (personal) vs up to $35 (business) are two different cards.
- **Card rates:** Platinum 12.50%-19.50%, Rewards 15.50%-21.00%, Business Platinum 15.50% agree across pages.
- **Hours:** stated only in news releases, each about a different branch; branch pages carry no hours text. No same-branch
  disagreement found.
- **Other loan payment examples** (personal 10.49%, boat 7.09%, ATV 8.34%, home improvement 8.50%) match `/rates`.
