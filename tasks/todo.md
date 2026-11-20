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
- [ ] 1. Free: count prose chunks per page type across the 5 snapshots, and distinct hashes after dedupe
- [ ] 2. Free: read `chunker.py`, `search.py`, `embed_index.py`, `solution.py` to find the insertion point for extra index fields
- [ ] 3. Measure cost on a 50-chunk pilot, and extrapolate; stop if projected total > $3.50
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

## Check-in (need answers before step 3)
1. Is the target model for enrichment `gpt-6-luna`, or a cheaper one if available?
2. Is "P95 hurts" about latency? I read it as "accuracy lifts the multiplied speed/consistency scores"; correct me if you meant something else.
3. Is it OK to commit the enrichment cache to the repo (like `.embed_cache/`)?

## Review
(to be filled in after implementation and measurement)
