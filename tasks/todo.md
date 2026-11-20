# Plan: ingest-time, page-type-aware chunk enrichment (not query-time HyDE)

Status: PLAN ONLY. Nothing implemented. Waiting for sign-off (see "Check-in").

## Goal
Raise accuracy on prose-path questions (hours, branches, eligibility, how-to, recognition, URLs).
Accuracy matters twice: it is 55% of the score, and speed and consistency are multiplied by it.
p95 is 3.4-4.1 s; the answer call is ~90% of that, so enrichment cannot cut it directly.
It can help indirectly: better evidence means fewer second-call fallbacks (about 1.4 s each) and no need for extra windows.

Budget cap: **$3.50** total for all experiments (pilot, full ingest, 3 regress runs).

## Research summary (verified by web search, 2026-11-20)
| Technique | Source | Takeaway for us |
|---|---|---|
| HyDE (query time) | Gao, Ma, Lin, Callan, ACL 2023, arXiv 2212.10496 | LLM drafts a fake answer, embeds it. Adds an LLM call per question, which hurts p95. **Rejected.** |
| Doc expansion by query prediction | Nogueira et al. 2019 (arXiv 1904.08375); docTTTTTquery (Nogueira & Lin) | Append predicted questions to each chunk, then index. MS MARCO MRR@10 0.184 to 0.277 with BM25. Index-time cost only. **Adopt (questions field).** |
| Contextual Retrieval | Anthropic engineering post, 2024 | Prepend a 50-100 token chunk-specific context line before embedding and BM25. Failure rate 5.7% to 3.7% (-35%) with embeddings, to 2.9% (-49%) with contextual BM25 too. Critics note gains are not isolated from plain hybrid search, so we must measure ourselves. **Adopt (context line).** |
| Propositions | Chen et al., arXiv 2312.06648 | Atomic, self-contained facts beat passages for retrieval (Recall@20 +10.1 unsupervised, +2.2 supervised). **Maybe later**, only if the first two fall short; costs more calls. |
| Multi-vector / hypothetical-question indexing | LangChain multi-vector guide; QuOTE (arXiv 2502.10976) | Index the enrichment, **return the original parent text**. Matches our "never rewrite what the model sees" rule. |
| Practice | Manning "AI Agents and Applications" ch. 8-9 | Test each variant; cache and dedupe ingest LLM calls; measure recall@k on a golden set first. |

Caveat: no source covered the hallucination risk of enrichment. The guards below are my own design.

## Eval review: which questions can ingest enrichment move?
Prose path (BM25 + windows), candidates: dup-054/055 routing number, dup-068 Galena address,
dup-074/075/076 Hy-Vee, dup-087 Forbes, dup-031 Home$tart, dup-060 update contact info,
dup-064/065/066/104 hours, dup-080 locator URL, dup-081 eligibility, dup-082 join online,
dup-094 mobile wallet, dup-101 student loans, dup-102 Mullan Ave (should refuse).

Not helped (rate path via extracted facts, already structured): 001, 009, 011, 016, 017, 028, 035, 045, 046, 050, 052, 006, 034, 040.

Known misses from NOTES.md section 8-9 that enrichment will NOT fix, because they are reference or scorer mismatches
(not retrieval): dup-049, dup-088, dup-005, dup-011, dup-066 source choice. Do not tune toward these.

Open item: re-run baseline with the judge to find the real per-question misses (needs key; results/ is empty in this checkout).

## Design guardrails
- Enrichment is an EXTRA index field per chunk (`context_line`, `questions`). The text sent to the answer prompt stays the original chunk. Never replace source text.
- Numeric guard in code: every number/date/percent in the generated text must appear in the source chunk or page title/date; otherwise drop that item. Preserves the "0 stale values" invariant.
- Prompt is chosen by page type (existing precedence: rate sheet, product, promo, other), and by sub-type for "other":
  - promo: include offer dates and ended/active status in the context line
  - news/press/blog: include publish date and the words "historical, not necessarily current"
  - hours/branch pages: include branch name and what kind of hours (lobby, drive-up, phone)
  - FAQ/how-to: questions only
  - Skip tables (already have facts.py and row chunks) and tiny chunks.
- General rules only; no question-specific text. The hidden set rewords questions.
- Cache by hash(chunk text + page title + prompt version) on disk and commit it like `.embed_cache/`. Unchanged chunks across the 5 crawls cost nothing.
- Feature switch `MY_SOLUTION_ENRICH=0/1` so regress.py can A/B.
- Ingest must stay well under 30 min.

## Checklist
- [ ] 0. Check in with user on this plan (approve scope, model, budget)
- [x] 1. Free: count prose chunks per page type across the 5 snapshots, and distinct hashes after dedupe
  - Result: 15,465 distinct chunks (12,867 sections + 2,598 table rows). Sections by URL type: blog 5,428, other 4,143, news 2,595, calculator 389, rates 272, contact 40. About 1.99M tokens of section text (1.92M tokens in the 10,641 sections of 200+ chars). Per-snapshot chunk counts are 7,078-7,931.
  - Implication: enriching everything is too broad for the budget. Start with the newest snapshot (the default for answers) and the 'other' + contact pages (hours, branches, eligibility, how-to), then widen only if it helps.
- [ ] 2. Free: read `chunker.py`, `search.py`, `embed_index.py`, `solution.py` to find the insertion point for extra index fields
- [x] 3. Measure cost on a 50-chunk pilot, and extrapolate; stop if projected total > $3.50
  - Pilot (50 newest-snapshot 'other' section chunks, one combined call each, gpt-6-luna, effort none): 18,817 input and 9,592 output tokens total, i.e. about 376 in / 192 out per chunk, 2.6 s per call, 0 errors, 0 chunks with a number missing from the source. About 3.8 propositions and 4.0 questions per chunk.
  - Projection: per 1,000 chunks about 0.38M input + 0.19M output tokens. 5,000 chunks is about 1.9M in + 0.96M out. Dollar figure needs the gpt-6-luna price (not available to me); check the OpenAI usage page for the pilot's 50 calls.
  - Quality finding: the context line asserts 'current' without evidence, and says 'does not say whether current' when it has nothing. Fix in the prompt: state status only when the excerpt or page info says so (dates, 'ended', 'expired'); otherwise omit it. Tiny chunks give thin propositions; skip chunks under about 200 chars (already done).
- [ ] 4. Run baseline (3 runs via regress.py) and record per-question misses
- [ ] 5. Implement `enrich.py` (prompts per page type, numeric guard, disk cache)
- [ ] 6. Wire into BM25 text and embedding windows (index text = enrichment + chunk; returned text = chunk)
- [ ] 7. Re-embed only changed windows (check embed cost against the cap)
- [ ] 8. Run regress.py, 3 runs, enrichment on vs off, across all eval sets (public, held-out, dated, changed, typos)
- [ ] 9. Check the invariants: 0 stale, consistency 1.0, no new refusals on answerable questions, should-refuse questions (145, 147, 102) still refuse
- [ ] 10. Compare p50/p95 latency and QA score; keep only if it helps beyond run noise
- [ ] 11. Update NOTES.md (decisions table, cost, results) and workflow.md ingest diagram
- [ ] 12. Fill in the Review section below

## Risks
- Generated questions over-broaden a chunk and pull wrong pages in (e.g. branch hours attached to the wrong branch). Mitigation: branch/page name in the prompt, and compare dup-064/065/066/104 specifically.
- Gain may be small on this corpus because the section label, synonyms and window search already cover a lot. Decision rule: if <= noise over 3 runs, ship nothing and document the negative result.
- Cost overrun. Mitigation: pilot first, hard stop at $3.50.

## Decisions from user (2026-11-20)
- Model: `gpt-6-luna` for enrichment.
- Aim: better ingest context gives better retrieval, which gives better accuracy. A/B also whether the answer prompt (system + user message) can shrink, to cut latency.
- Enrichment cache is committed to the repo (like `.embed_cache/`).
- HyDE is meant at INGEST: precompute hypothetical questions per chunk (doc2query / HyPE style), not a query-time call. Adopt this.
- Priority tier in `my_solution/llm.py` is OFF while testing (`MY_SOLUTION_PRIORITY=1` turns it back on). **Re-enable and re-measure speed before final submission.**
- Interest ranking: Chen propositions (most), Contextual Retrieval, multi-vector indexing. Test all three as A/B arms.

- Retrieval integration: ADD enrichment candidates to the existing BM25 + window candidates (union, then fuse and rank); do not replace the current order. Every candidate carries provenance (retriever + field) written to the trace, so we can ablate which field found the winning chunk.
- Arm E tests top-k of 3-4 parents (smaller prompt), accepting a possible few extra refusals as the measured cost.
- Budget: user is adding $10 of OpenAI credit. Plan to spend <= $3.50; check in before going above that. $10 is the hard ceiling.

## A/B arms (regress.py)
- A: baseline (enrichment off)
- B: context line only (Contextual Retrieval)
- C: propositions as retrieval units, parent chunk returned (Chen + multi-vector)
- D: hypothetical questions per chunk (ingest-time HyDE / doc2query)
- E: best combination, plus a smaller answer prompt (fewer excerpts, shorter system message) to measure latency
Measure: QA score, refusal correctness, p50/p95, prompt tokens per answer, ingest cost.

## Grouping idea: stable intent "cards" (to test in arm E)
Group chunks by intent at ingest (hours, address, contact, eligibility, how-to, recognition) and compile one short,
code-checked card per entity (branch, program) with its source URL. At answer time send the card instead of 6-8 long excerpts,
which shrinks the user message and stabilises answers. Same guardrails: numbers must appear in the source; original text stays available as fallback.

## Check-in
Waiting for go-ahead to start steps 1-3 (all free except the 50-chunk pilot).

## Review (first A/B, public set, 1 run per arm, judged; priority tier off)
Built: `my_solution/enrich.py` (one combined gpt-6-luna call per chunk, number guard, committed cache), hooks in `solution.py`/`chunker.py`, all OFF unless `MY_SOLUTION_ENRICH` is set. Cache: 1,452 chunks from the newest copy (645k in / 249k out tokens, 0 errors, 3 items dropped by the guard). Enrichment embeddings cost about 0.3M embedding tokens.

| Arm | Accuracy | Judged | p95 s | vs base |
|---|---|---|---|---|
| A base | 0.905 | 0.830 | 2.8 | - |
| B ctx (context line in BM25) | 0.905 | 0.839 | 2.9 | +0.000 |
| C prop+emb | 0.905 | 0.840 | 3.1 | +0.000 |
| D q+emb | 0.840 | 0.778 | 2.9 | -0.065 |
| E all | 0.858 | 0.795 | 3.3 | -0.047 |
| F all + top-k 4 | 0.886 | 0.816 | 3.0 | -0.019 |

Moved questions: D lost dup-064 (0.85 to 0.00), dup-065 (1.00 to 0.00), dup-104 (1.00 to 0.50); E lost dup-034, dup-087, dup-104; F lost dup-008, dup-104. 0 stale, 0 errors in every arm.

Reading (one run each; model noise is about 0.02): no arm beat the baseline. B and C tie it on accuracy with a judged score about +0.01 (noise). Hypothetical questions (D, E) hurt, mostly on hours questions; my untested hypothesis is that "what are the lobby hours" questions attach to many near-identical branch chunks and push the right schedules out. A smaller prompt (top-k 4) did not lower p95 here and cost accuracy.
Decision for now: ship nothing; keep enrichment off. Possible follow-up: 3 runs of A/B/C on the public, held-out, dated and typo sets to see whether B or C help beyond noise; check the provenance log (`MY_SOLUTION_PROV`) for D's hours misses; consider widening B/C to news and older copies only if they win.

## Follow-up: provenance check of arm D (hypothetical questions), 2026-11-20
- User point: all A/B runs had the OpenAI priority tier OFF (credit saving), so p95 values are not comparable to NOTES.md and do not predict graded speed. Final speed must be measured with `MY_SOLUTION_PRIORITY=1`. Arms are comparable with each other.
- Provenance (`MY_SOLUTION_PROV`) on the six moved questions, arm D: the enrichment search added exactly 3 pieces to EVERY question, with no similarity floor. For dup-065 their similarity was 0.37-0.48 and the pages were unrelated (a coffee-shop blog, a personal-resources page, the owner's-manual PDF); for dup-064 they were `/contact`, the owner's manual and a privacy-policy URL.
- The lobby-hours excerpts were still in the prompt (union keeps them), and the model still answered "I don't know". dup-064 and dup-065 refused in 3 of 3 D runs (regress, rerun, trace). Cause = noisy extra pieces and a longer prompt, i.e. a retrieval-quality problem (no relevance floor), not lost evidence.
- Of the answers that did cite sources, 2 of 6 cited one enrichment-added page (dup-034, dup-008), both answers unchanged from baseline (1.0). dup-034/087/008/104 flips seen in E/F were not reproduced in the rerun (noise).
- Prompt size was never reduced in any arm: arm F cut only keyword top-k 8 to 4; window and enrichment extras and the system message were unchanged. The smaller-message hypothesis is untested.
- Next: (1) similarity floor + add enrichment extras only when they beat the weakest kept piece; (2) a real size arm: keyword k 4, window extras 2, enrichment extras 2, shorter intent-specific system message; (3) re-run A/B/C/new arms 3x on public + held-out + dated + typo sets.

## Retrieval-only check (no answer calls), 124 questions with must_include (public, held-out, typo, branch/contact, temporal), 2026-11-20
Recall = every required string appears in the pieces sent to the model. Chars = average size of the pieces (user message).

| Config | Recall | Pieces | Chars |
|---|---|---|---|
| A base (keyword 8, windows up to 3) | 0.960 | 10.1 | 8,689 |
| E all enrichment, extras 3, no floor | 0.960 | 13.1 | 11,436 |
| A keyword 6, windows 2 | 0.903 | 7.2 | 6,551 |
| A keyword 4, windows 2 | 0.871 | 5.1 | 4,905 |
| B ctx, keyword 6, windows 2 | 0.903 | 7.1 | 6,575 |
| B ctx, keyword 4, windows 2 | 0.871 | 5.1 | 4,928 |
| C prop+emb, keyword 4, windows 2, extras 2 | 0.903 | 7.1 | 6,798 |
| E all, keyword 4, windows 2, extras 2 | 0.895 | 7.1 | 6,729 |

Findings:
- Baseline recall is already 0.960. Enrichment (E) fixed 0 and broke 0 of the 5 misses (dup-034, ho-010, tm-007, tm-016, tm-021) and added 3 pieces (+31% chars).
- Enrichment extras: 372 added, only 37 (10%) held a required value. Similarity does not separate them (median 0.66 useful vs 0.60 useless), so a floor cannot clean them up.
- Shrinking costs recall: -25% chars gives -5.7 points; -44% chars gives -8.9 points.
- Enrichment does not beat simply raising k: C at k4 (0.903, 6,798 chars) equals A at k6 (0.903, 6,551 chars). Context line (B) = baseline at equal size.
- Conclusion: on this corpus the retrieval hypothesis is not supported. Keep enrichment OFF. Recall is a text-presence proxy; the model may still answer correctly from smaller prompts, which only an answer-level run can show (not yet run).

## Compact-evidence check (retrieval only), 124 questions, 2026-11-20
Baseline pieces; any retrieved piece with enrichment and over 300 chars is replaced by its context line + the M propositions most similar to the question.
| M | Recall (full 0.960) | Chars (full 8,689) | Pieces replaced per question |
|---|---|---|---|
| 2 | 0.952 | 7,920 (-9%) | 1.72 |
| 3 | 0.952 | 8,083 (-7%) | 1.72 |
| 5 | 0.952 | 8,304 (-4%) | 1.72 |
Lost by compacting: dup-082 (all M). The saving is small because only about 1.7 of about 10 pieces per question have enrichment (cache covers only the newest copy's non-blog/news/rate section chunks); the rest of the prompt (tables, news, contact, windows) is untouched. Qualifiers (tier, branch, dates) can also be lost in a short proposition. Not worth an answer-level run as is. Wider coverage (news, blog, older copies) would cost another LLM pass and has no evidence yet that it would help.

## Status summary (2026-11-20) - what is tried, what is next
Tried, no gain (enrichment, i.e. HyDE-style ingest): context line (B), propositions (C), hypothetical questions (D), all (E/F), swapping chunks for propositions. Keep OFF.
Tried, bad: sending fewer pieces (keyword 6 / window 2): answer accuracy 0.799 vs 0.897 baseline in 3 of 3 runs, one stale value. Do not ship.

Chunk size (NEW lever, not in the original plan; no LLM at ingest; switch `MY_SOLUTION_SPLIT_CHARS`, default 3000). Retrieval-only check, 124 questions, no rate-limit warnings:
| Chunk limit | Recall | Avg chars |
|---|---|---|
| 3000 (baseline) | 0.960 | 8,689 |
| 1500 | 0.927 | 6,434 |
| 800 | 0.935 | 4,963 |
| 600 | 0.935 | 4,407 |
| 400 | 0.903 | 3,565 |
| 800 + keyword 10 | 0.952 | 5,728 |
(Earlier 600 and 800+k10 runs were invalid: embedding rate limit when run in parallel; reruns one at a time are the numbers above. Run embedding-heavy checks one at a time.)

Next:
- [ ] Answer-level test of chunk size: 3 runs each of baseline, 800, 600, 800 + keyword 10 on the public set (needs go-ahead; config to be written as docs/regress_chunksize.json)
- [ ] If a size arm holds accuracy: repeat 3x on held-out, dated, typo sets; check 0 stale; then measure latency with MY_SOLUTION_PRIORITY=1
- [ ] Otherwise: write the negative result into NOTES.md, turn priority tier back on, stop
Not planned (low expected gain): contextual embeddings, reranking, cards, widening enrichment, shorter system message.

## Chunk size, answer level (public set, 3 runs per arm, judged; priority tier off), 2026-11-20
| Arm | Accuracy (3 runs) | Judged | p50 s | p95 s | Stale |
|---|---|---|---|---|---|
| A base (3000) | 0.879 [0.879, 0.879, 0.879] | 0.823 | 1.65 | 2.63 | 0 |
| S800 | 0.880 [0.905, 0.882, 0.853] | 0.804 | 1.69 | 2.82 | 0 |
| S600 | 0.866 [0.868, 0.845, 0.884] | 0.819 | 1.81 | 2.78 | 0 |
| S800 + keyword 10 | 0.872 [0.882, 0.867, 0.867] | 0.795 | 1.68 | 2.70 | 0 |
Reading: accuracy is unchanged within noise (about 0.02) for every size; judged scores are 0.004-0.028 lower. 0 stale, 0 errors. Moved questions are the hours/branch ones (dup-064, 065, 066, 104) plus dup-080, which flip between runs in every arm, so they are noise-prone, not caused by chunk size. The ~43% smaller evidence (retrieval check) did NOT lower latency: p50 1.65 vs 1.69 s. With the priority tier off, answer time is not driven by input size here.
Conclusion: no arm beats the baseline. Chunk size is neutral on accuracy and gives no speed gain, so do not change the default (3000). Together with the enrichment results, no ingest change tested so far improves accuracy or latency.
