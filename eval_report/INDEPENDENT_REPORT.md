# Independent evaluation: can ingest changes improve accuracy or shrink the prompt?

Date: 2026-11-20. Branch `claude/independent-eval`, cut from `claude/eloquent-bardeen-9r4xbs` at `5d65a63`.
Every number here comes from runs made today in this session, and every one of them can be checked in `eval_report/results.csv`
(end-to-end runs, one row per arm and run, plus retrieval-only rows) or rebuilt with the commands in section 1.
I formed these results before reading NOTES.md section 10 or `tasks/todo.md`; section 4 compares them afterwards.

## Bottom line

**No ingest change beats the baseline on accuracy, and none improves latency.**

- **Accuracy.** Thirteen end-to-end arms on the public set (3 runs each, interleaved) and seven on 100 non-public questions
  (3 runs each): every difference against the baseline is either inside the noise or a loss. {{STAGEB_BOTTOM}}
- **Latency.** The answer call's duration does not depend on how much evidence it is sent (correlation 0.015 over 1,599 calls,
  arm means 1.48 to 1.65 s for prompts of 5.4k to 9.0k characters). It depends on how much it writes (7.3 ms per output token).
  Shrinking the prompt therefore buys no measurable speed, and the input tokens it saves are worth about $0.0002 per question.
- **The prompt can be made smaller without a measurable loss**: TOP_K=6 cuts the text-path prompt by 17% with no recall or
  accuracy change. It earns nothing in return (previous point), so I would not change the default for it.
- **Two arms broke the zero-stale invariant**: propositions sent to the model instead of chunks (stale in 3 of 3 runs) and
  TOP_K=6 with at most 2 window pieces (1 of 3). Both remove the meaning-search window pieces that surface the newer press release.
- **HyDE is not worth testing end to end**: the hypothetical-answer call takes 1.2 s at the median and would sit on the timed
  path of every text-search answer, and in the cheap retrieval test it lost 1 to 3 questions instead of gaining any.
- **The baseline's retrieval is already near its ceiling** on these sets: on the questions answered by text search, 61 of 62 have
  every required string in the evidence; every public miss in my baseline runs is a reference/scorer mismatch already listed in
  NOTES section 9, with the required strings present in the evidence. Ingest changes cannot raise public accuracy without gaming.

{{SPEND_LINE}}

## 1. What I ran and how to reproduce it

Environment: Python 3.13.18 (CLAUDE.md says 3.11; nothing failed), `openai` 3.57.0, numpy 2.5.3, branch `claude/independent-eval`
cut from `claude/eloquent-bardeen-9r4xbs` at `5d65a63`. Snapshots from PR 23 unzipped into `snapshots/` (git-ignored, not committed).
OpenAI service tier: **default (priority off) for every call**, confirmed per call in the ledger (`tier` field). All runs sequential.

Tools (all in `eval_report/tools/`, none changes answers):

| Tool | What it does |
|---|---|
| `usercustomize.py` + `ledger.py` | Every OpenAI call (Responses, Decisions, Embeddings) appends its tokens to `results/ledger.jsonl`; `ledger.py` prices them |
| `e2e.py` | Harness runs (`harness/run_eval.py`, unchanged), one at a time, arms interleaved with rotating order; per-run accuracy, stale hits, latency p50/mean/p95/max, chars and tokens actually sent to the answer model; a run whose log shows a rate limit, a failed call or meaning search switched off is marked INVALID and not counted |
| `rcheck.py` + `screen.py` + `rc_table.py` | Retrieval-only screening (no answer calls): per question, the path `answer()` really takes (text / facts / history / count), whether the evidence holds every `must_include` string, the shortest covering prefix, and the length of the real user message. Labels frozen in one cache so arms differ only in ingest |
| `hyde.py` | One hypothetical answer per question (gpt-6-luna) and the latency of each call |

Protective settings in every run: committed vector files are never written (question, enrichment and window vectors go to copies
under `results/`), facts come from one shared cache (`results/fact_cache.json`, built once in the pilot), and
`MY_SOLUTION_NONCE_SALT` is set per run so the evidence part of each prompt is never served from the provider's prompt cache
(see section 3, finding P1).

Reproduce:

```bash
pip install -r my_solution/requirements.txt
git fetch origin pull/23/head:pr23 && mkdir -p snapshots_zip && for z in 01_2026-05-12_baseline 02_2026-05-19_recrawl \
  03_2026-06-09_recrawl 04_2026-08-27_rebaseline 05_2026-09-28_latest; do git show pr23:snapshots_zip/$z.zip > snapshots_zip/$z.zip; done
for z in snapshots_zip/*.zip; do unzip -q -o $z -d snapshots/; done

python eval_report/tools/e2e.py --config eval_report/configs/pilot.json --out results/e2e/pilot      # cold run, builds the fact cache
python eval_report/tools/hyde.py --sets eval/public_eval.jsonl eval/subsets/heldout.jsonl eval/subsets/typo_robustness.jsonl \
  eval/subsets/slice2_branch_contact.jsonl eval/subsets/heldout_temporal.jsonl --out results/hyde.json
python eval_report/tools/screen.py --config eval_report/configs/screen.json --out results/rc          # retrieval-only, all arms
python eval_report/tools/rc_table.py results/rc
python eval_report/tools/e2e.py --config eval_report/configs/stageA.json --out results/e2e/stageA      # public, 13 arms x 3
python eval_report/tools/e2e.py --config eval_report/configs/stageB.json --out results/e2e/stageB      # 100 non-public questions, 7 arms x 3
python eval_report/tools/e2e.py --config eval_report/configs/priority.json --out results/e2e/priority  # priority tier on/off, 3 + 3
python eval_report/tools/compare.py --config eval_report/configs/stageA.json --dir results/e2e/stageA [--md]
python eval_report/tools/compare.py --config eval_report/configs/stageB.json --dir results/e2e/stageB --groups eval_report/configs/stageB_groups.json
python eval_report/tools/build_csv.py --e2e results/e2e/stageA results/e2e/stageB results/e2e/priority --rc results/rc --out eval_report/results.csv
python eval_report/tools/ledger.py results/ledger.jsonl                                              # spend
```

Stages, in the order run:

1. **Pilot**: one cold baseline run on the public set (builds the fact cache, measures cost and time per run).
2. **Retrieval-only screening** of 37 arms on the 124 questions with `must_include` in five eval files (public, held-out, typo,
   branch/contact, temporal). Deterministic: re-running four arms gave identical rows.
3. **Stage A, end to end on the public set**: 13 arms (every technique at least once), 3 runs each, 39 runs, interleaved.
   Live question labels (the Decisions call is on the timed path, as in grading).
4. **Stage B, end to end on 100 non-public questions** (typo 48, held-out 22, temporal 21, branch/contact 9 in one file,
   `eval_report/configs/stageB_eval.jsonl`, so each run pays one ingest): the 7 arms that were ties or prompt shrinkers in
   stage A, 3 runs each. To save money the question labels come from the frozen cache for every arm (the labels are
   deterministic: 12 of 12 identical on repeat calls), so stage B latency excludes the ~0.3 s labels call for every arm alike.
5. **Priority tier**: 3 runs with `MY_SOLUTION_PRIORITY=1` interleaved with 3 runs without, public set, baseline otherwise.

What the accuracy numbers can and cannot show: on the public set every baseline miss is a reference or scorer mismatch already
listed in NOTES section 9 (dup-049, dup-005, dup-088, the source part of dup-064/066), with the required strings present in the
evidence, plus the hours questions dup-064/065/104 that flip between runs whatever the arm. One flip moves accuracy by about 0.023,
so a 3-run mean can hide an effect of about +-0.02. Stage B exists because the public set has almost no headroom left for retrieval.


## 2. Results by technique

Baseline = this branch with no switches set. "Text recall" = share of questions answered by text search whose evidence holds
every `must_include` string (5 eval files, 62 questions; facts-path questions are counted separately because the extracted facts
answer them and text search is only their fallback). "Public acc." = harness keyword accuracy, mean of 3 runs (baseline 0.8786).
"Diff" = paired difference against the baseline with a 95% bootstrap interval over questions. Stale = stale-trap hits over all runs.

{{TECH_TABLE}}

Confidence: **high** = the retrieval test (deterministic) and 3 end-to-end runs agree; **medium** = a tie within noise that
could hide an effect of about +-0.02; **low** = retrieval only, not run end to end.

### 2a. End-to-end, public set (40 questions, 3 runs per arm)

{{STAGEA_TABLE}}

### 2b. End-to-end, 100 non-public questions (typo 48 + held-out 22 + temporal 21 + branch/contact 9), 3 runs per arm

{{STAGEB_TABLE}}

### 2c. Retrieval-only screening (no answer calls; all 37 arms)

Text = 62 questions answered by text search; facts = 58 rate/fee questions on their text fallback; history = 3 "what changed"
questions. "Cover" = mean number of pieces, in the order sent, needed to hold every required string (lower = earlier).

| arm | what | text recall (/62) | text chars (vs base) | cover | facts-fallback recall (/58) | history (/3) | questions lost / gained vs base |
|---|---|---|---|---|---|---|---|
| base | baseline (no switch) | 61 | 11300 (+0.0%) | 4.79 | 57 | 3 | - |
| ctx_kw | CR keyword half: LLM context line added to BM25 text (`ENRICH=ctx`) | 61 | 11264 (-0.3%) | 4.74 | 57 | 3 | - |
| q_kw | doc2query: generated questions added to BM25 text (`ENRICH=q`) | 61 | 10903 (-3.5%) | 4.39 | 57 | 3 | - |
| prop_kw | propositions added to BM25 text (`ENRICH=prop`) | 61 | 11345 (+0.4%) | 4.62 | 57 | 3 | - |
| mv_q | multi-vector: meaning search over generated questions, original chunk returned, BM25 untouched (`ENRICH=embq`) | 61 | 13968 (+23.6%) | 4.79 | 57 | 3 | - |
| mv_prop | multi-vector over propositions, original chunk returned (`ENRICH=embprop`) | 61 | 13965 (+23.6%) | 4.79 | 57 | 3 | - |
| q_kw_emb | previous author's D_q: questions in BM25 + multi-vector (`ENRICH=q,emb`) | 61 | 13610 (+20.4%) | 4.39 | 57 | 3 | - |
| prop_kw_emb | previous author's C_prop (`ENRICH=prop,emb`) | 61 | 14031 (+24.2%) | 4.62 | 57 | 3 | - |
| all_enrich | previous author's E_all (`ENRICH=ctx,q,prop,emb`) | 61 | 13941 (+23.4%) | 4.33 | 57 | 3 | - |
| cr_emb_llm | CR embedding half: window vectors from "LLM context line + window" (`WINDOW_CTX=llm`) | 61 | 11268 (-0.3%) | 4.77 | 57 | 3 | - |
| cr_full_llm | CR both halves (`ENRICH=ctx` + `WINDOW_CTX=llm`) | 61 | 11225 (-0.7%) | 4.72 | 57 | 3 | - |
| cr_emb_head | code-written context (title > headings) on window vectors (`WINDOW_CTX=head`) | 57 | 11157 (-1.3%) | 4.46 | 57 | 3 | lost dup-031, dup-081, dup-081-typo1, dup-081-typo2 |
| propunit_repl | Dense X: propositions sent to the model in place of the window pieces (`PROP_UNIT=replace`) | 51 | 11010 (-2.6%) | 3.92 | 57 | 3 | lost dup-087, dup-031, dup-081, dup-081-typo1, dup-081-typo2, dup-087-typo1, dup-087-typo2, tm-001, tm-003, tm-006 |
| propunit_union | propositions sent in addition to the windows (`PROP_UNIT=union`) | 61 | 15958 (+41.2%) | 4.79 | 57 | 3 | - |
| k6 | `TOP_K=6` | 61 | 9415 (-16.7%) | 4.08 | 57 | 3 | - |
| k5 | `TOP_K=5` | 61 | 8547 (-24.4%) | 3.62 | 56 | 3 | lost dup-049 |
| k4 | `TOP_K=4` (also hits defect D6) | 59 | 7665 (-32.2%) | 2.95 | 53 | 3 | lost dup-040, dup-049, dup-081, ho-012, dup-081-typo1, ho-012-typo1 |
| cap2 | `WINDOW_EXTRA_CAP=2` | 57 | 10185 (-9.9%) | 4.28 | 57 | 3 | lost dup-031, dup-081, dup-081-typo1, dup-081-typo2 |
| cap1 | `WINDOW_EXTRA_CAP=1` | 55 | 9559 (-15.4%) | 4.07 | 57 | 3 | lost dup-087, dup-031, dup-081, dup-081-typo1, dup-081-typo2, dup-087-typo1 |
| cap0 | `WINDOW_EXTRA_CAP=0` (no window pieces) | 51 | 8951 (-20.8%) | 3.69 | 57 | 2 | lost dup-087, dup-031, dup-081, dup-081-typo1, dup-081-typo2, dup-087-typo1, dup-087-typo2, tm-001, tm-003, tm-006, tm-007 |
| k6_cap2 | previous author's G_k6w2 (`TOP_K=6`, `CAP=2`) | 54 | 8273 (-26.8%) | 3.31 | 57 | 3 | lost dup-087, dup-031, dup-081, dup-082, dup-081-typo1, dup-081-typo2, dup-087-typo1 |
| rr_rrf | rerank keyword top 40 by best-window similarity, RRF with keyword rank | 61 | 13161 (+16.5%) | 3.56 | 57 | 3 | - |
| rr_rrf_k6 | RRF rerank + `TOP_K=6` | 61 | 10599 (-6.2%) | 3.26 | 57 | 3 | - |
| rr_rrf_k5 | RRF rerank + `TOP_K=5` | 61 | 9387 (-16.9%) | 3.07 | 56 | 3 | lost dup-040 |
| rr_dense_k5 | dense rerank, K=5 | 62 | 9993 (-11.6%) | 2.32 | 57 | 3 | gained dup-034 |
| s1500 | `SPLIT_CHARS=1500` | 57 | 9217 (-18.4%) | 4.21 | 57 | 3 | lost dup-031, dup-081, dup-081-typo1, dup-081-typo2 |
| s800 | `SPLIT_CHARS=800` | 60 | 7702 (-31.8%) | 4.78 | 56 | 3 | lost dup-011, dup-081-typo2 |
| s600 | `SPLIT_CHARS=600` | 59 | 7114 (-37.0%) | 4.76 | 56 | 3 | lost dup-011, dup-081-typo1, dup-081-typo2 |
| s400 | `SPLIT_CHARS=400` | 56 | 5785 (-48.8%) | 4.77 | 56 | 3 | lost dup-011, dup-031, dup-081, dup-008-typo2, dup-081-typo1, dup-081-typo2 |
| hyde_concat | HyDE: window search with question + hypothetical answer | 60 | 11332 (+0.3%) | 4.65 | 57 | 3 | lost dup-081-typo1 |
| hyde_replace | HyDE: window search with the hypothetical answer only | 58 | 11243 (-0.5%) | 4.62 | 57 | 3 | lost dup-087, dup-081, dup-087-typo2 |
| rr_dense | dense rerank (meaning rank only), K=8 | 62 | 14065 (+24.5%) | 2.44 | 57 | 3 | gained dup-034 |
| rr_dense_k6 | dense rerank, K=6 | 62 | 11397 (+0.9%) | 2.40 | 57 | 3 | gained dup-034 |
| rr_dense_k4 | dense rerank, K=4 | 62 | 8924 (-21.0%) | 2.21 | 56 | 3 | lost ho-004-typo1; gained dup-034 |
| rr_dense_k3 | dense rerank, K=3 | 60 | 7652 (-32.3%) | 1.97 | 51 | 3 | lost dup-016, dup-081, ho-006, ho-009, ho-004-typo1, ho-004-typo2, ho-009-typo1 |
| rr_dense_k5_cap2 | dense rerank, K=5, CAP=2 | 58 | 8895 (-21.3%) | 1.86 | 57 | 3 | lost dup-031, dup-081, dup-081-typo1, dup-081-typo2; gained dup-034 |
| rr_dense_k5_pool20 | dense rerank, K=5, pool 20 | 61 | 9999 (-11.5%) | 2.15 | 57 | 3 | - |

### 2d. Latency

{{LATENCY}}

## 3. Defects found in the experiment code, and what they do to earlier numbers

I reviewed `my_solution/enrich.py`, `my_solution/retrieval_check.py`, `my_solution/regress.py` and the enrichment hooks in
`solution.py` / `chunker.py` before running anything. Severity is about the experiment's conclusions, not about the
graded submission: every enrichment switch is off by default, so **none of these defects changes the submitted system's answers**.

| # | Defect | Evidence | Effect on earlier numbers | Status |
|---|---|---|---|---|
| D1 | **Coverage.** Enrichment was generated only for chunks that are sections of 200 to 2,500 characters on pages whose URL does not contain `/blog`, `news`, `calculator` or `rates`, and only from the newest copy | Enriched share of section text: 26% of the newest copy, 8 / 9 / 12 / 21% of the four older copies. Excluded: blog 33% of text, every `/newsroom` press release and `/resources/dupaco-news` (substring `news`, 18%), sections over 2,500 chars 17%. The `rates` filter also matches "celeb**rates**" | Any enrichment arm tested at most a quarter of the site, and almost nothing for dated questions (older copies). Press releases are where branch hours and closures live, so hours questions could not benefit. A negative result for enrichment is therefore a result for this coverage, not for the idea in general | Noted (regenerating for the rest of the site would cost roughly $1 to $1.5 at gpt-6-luna prices; not done) |
| D2 | **Leakage of generated text to the answer model** | Generated text reaches BM25 only through `Chunk.index_text()`; every prompt path uses `c.text`; enrichment extras return the parent's original text (`dataclasses.replace(c, via=...)`) | None: no leakage in the existing arms. (My `MY_SOLUTION_PROP_UNIT` arm sends propositions on purpose, see section 2) | Verified, no defect |
| D3 | **Number guard is weak** | Digits only: 295 propositions carry spelled-out numbers ("two", "five"), which pass unchecked. Any number anywhere in the source qualifies, so a value moved to the wrong product or day passes. The fetch date is in the prompt and in the allowed set | Harmless while generated text is search-only (D2). It matters as soon as generated text is shown to the model | Noted |
| D4 | **No floor, no intent gate on enrichment extras** (`MY_SOLUTION_ENRICH_FLOOR` default 0, `EXTRA_N` 3) | Measured with `q,emb` on 88 public + typo questions: exactly 3.00 extra full chunks per question, every question, including rate/fee questions (whose window count is 0); 79 of 264 had similarity below 0.5 | Every `emb` arm adds up to 3 x 2,500 chars per question: in my screening +20% to +24% characters on the text path. Any "emb" arm can only grow the prompt | Noted |
| D5 | **Extras dedupe only on exact full text**: a parent whose window is already in the evidence is added again in full | 5 of 264 extras (4,197 chars) on the same 88 questions | Small | Noted |
| D6 | **`k == TOP_K` gate collides with the history path when `MY_SOLUTION_TOP_K=4`**: `_history_hits` calls `retrieve(k=HISTORY_PIECES_PER_COPY=4)`, which then equals `TOP_K` and appends window, enrichment and schedule extras per website copy | Screening: the first history question goes from 12 to 14 pieces (11,694 to 13,855 chars) with `TOP_K=4` | Confounds any `TOP_K=4` arm on "what changed" questions, e.g. `F_all_topk4` in `docs/regress_enrich.json`. Other K values are unaffected | Noted (I avoided K=4 except with rerank, and flag it) |
| D7 | **Enrichment vector file path hard-coded** to the committed `.embed_cache/enrich-*.npz`: a run that embeds missing units rewrites a committed file | Code | Risk of silently changed committed vectors; no numeric effect | **Fixed**: `MY_SOLUTION_ENRICH_VEC_CACHE` |
| D8 | **Flags conflate the two halves**: `prop`/`q` both add keyword text *and* (with `emb`) choose the embedded units, so "meaning search over generated text, keyword index untouched" (pure multi-vector) could not be tested | Code | Earlier `C_prop` / `D_q` arms measured keyword + multi-vector together | **Fixed**: added `embq`, `embprop` (old flags unchanged) |
| D9 | **`retrieval_check.py` measures the wrong thing for half the questions**: facts off, so rate/fee questions (answered from facts in `answer()`) are scored on text search; "what changed" questions are scored on `retrieve()` although `answer()` uses `_history_hits()`; recall is pooled across paths; "chars" counts excerpt texts only | Of 124 questions with `must_include`, 58 take the facts path and 3 the history path | Pooled recall mixes the fallback with the main path; a union arm that adds pieces can only raise pooled recall, so the check rewards prompt growth | Replaced by `eval_report/tools/rcheck.py` (per path, real message length, frozen labels, rank metric) |
| D10 | **`regress.py` accepts runs whose meaning search was off** when the cause is not a rate limit (only `API_FAIL` strings are checked). `docs/regress_chunksize.json` runs 3 workers that each cold-embed ~18k windows into 3 empty cache files at once (`S800_k10` re-embeds the same windows as `S800`); `docs/regress_enrich.json` uses `runs: 1` | Code and configs | The configuration most likely to hit 429s; a single run is inside the noise (one hours question flips accuracy by 0.023) | Noted; my runner is sequential and treats "meaning search is off" as invalid |
| D11 | `enrich.generate()` serialises the shared cache dict while worker threads add to it; counters unlocked | Code | Build tool only; could crash a cache build | Noted |
| D12 | Any run that sees a new question writes the **committed** question-vector file (`embed_index.QUESTION_CACHE` default) | Code | Committed file drifts with every new eval set | Avoided by pointing `MY_SOLUTION_QUESTION_CACHE` at a copy |
| P1 | **Prompt-cache confound in latency comparisons**: the input id is a hash of the request, so re-running the same question with the same evidence sends a byte-identical prompt that the provider serves from its prompt cache | Pilot: 28 of 41 answer calls fully cached (identical prompts sent earlier today); fully cached calls 1.53 s vs 1.77 s mean | A baseline that was run many times has warm evidence; a new arm's evidence is cold. Graded questions are unseen, so cold evidence is the realistic case. Repeated-run latency figures are optimistic | Added `MY_SOLUTION_NONCE_SALT` (default off); every run here used a per-run salt |

## 4. Comparison with the previous author's notes

{{DISCREPANCIES}}

## 5. Spend

{{SPEND}}

## 6. Plain statement

{{FINAL}}
