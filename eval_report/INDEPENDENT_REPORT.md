# Independent evaluation: can ingest changes improve accuracy or shrink the prompt?

Date: 2026-11-20. Branch `claude/independent-eval`, cut from `claude/eloquent-bardeen-9r4xbs` at `5d65a63`.
Every number here comes from runs made today in this session, and every one of them can be checked in `eval_report/results.csv`
(end-to-end runs, one row per arm and run, plus retrieval-only rows) or rebuilt with the commands in section 1.
I formed these results before reading NOTES.md section 10 or `tasks/todo.md`; section 4 compares them afterwards.

## Bottom line

**No ingest change beats the baseline on accuracy, and none improves latency.**

- **Accuracy.** Thirteen end-to-end arms on the public set (3 runs each, interleaved) and seven on 100 non-public questions
  (3 runs each): every difference against the baseline is either inside the noise or a loss. On the 100 non-public questions the best arms are ties (TOP_K=6 +0.003, interval -0.015 to +0.022; dense rerank +0.000 / +0.001) and 800-character chunks lose (-0.031, interval -0.070 to -0.001).
- **Latency.** The answer call's duration does not depend on how much evidence it is sent (correlation 0.015 over 1,599 calls,
  arm means 1.48 to 1.65 s for prompts of 5.4k to 9.0k characters). It depends on how much it writes (7.3 ms per output token).
  Shrinking the prompt therefore buys no measurable speed, and the input tokens it saves are worth about $0.0002 per question.
- **The prompt can be made smaller without a measurable loss**: TOP_K=6 cuts the text-path prompt by 17% (12-14% per question)
  with no recall, accuracy or latency change on either eval set, so it meets the "shrink without harm" bar. It buys no speed
  (previous point) and saves about 250 tokens per question, so keeping the default of 8 is equally defensible.
- **Two arms broke the zero-stale invariant**: propositions sent to the model instead of chunks (stale in 3 of 3 runs) and
  TOP_K=6 with at most 2 window pieces (1 of 3). Both remove the meaning-search window pieces that surface the newer press release.
- **HyDE is not worth testing end to end**: the hypothetical-answer call takes 1.2 s at the median and would sit on the timed
  path of every text-search answer, and in the cheap retrieval test it lost 1 to 3 questions instead of gaining any.
- **The baseline's retrieval is already near its ceiling** on these sets: on the questions answered by text search, 61 of 62 have
  every required string in the evidence; every public miss in my baseline runs is a reference/scorer mismatch already listed in
  NOTES section 9, with the required strings present in the evidence. Ingest changes cannot raise public accuracy without gaming.

OpenAI spend for the whole session: **$2.25** of the $3.50 ceiling (section 5). The priority-tier on/off check was not run (section 2d).

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

| # | Technique | What I ran | Result vs baseline | Verdict | Confidence |
|---|---|---|---|---|---|
| 1 | HyDE (query time) | gpt-6-luna writes a 2-3 sentence hypothetical answer per question; window (meaning) search uses question + answer (`hyde_concat`) or the answer alone (`hyde_replace`). Retrieval only | Generation call p50 1.20 s, p95 1.65 s, on the timed path of every text-search answer. Text recall 61/62 -> 60 (concat) / 58 (replace). It also invents values ("4.00% APY" for a 4.10% product) | **Not worth testing end to end**: slower and no better | high |
| 2 | Ingest-time hypothetical questions (doc2query), keyword | Committed questions appended to the BM25 text (`ENRICH=q`) | Recall unchanged; covering prefix 4.79 -> 4.39 (best keyword enrichment). Public +0.013 [0.000, +0.032]; 100 non-public -0.007 [-0.033, +0.017]; 0 stale | **Tie** | medium |
| 3 | Multi-vector (search generated text, return the ORIGINAL chunk) | Meaning search over the generated questions (`ENRICH=embq`) or propositions (`embprop`), parent chunk appended, BM25 untouched (new flags, defect D8); also the previous author's combined arms `q,emb`, `prop,emb`, `ctx,q,prop,emb` (retrieval only) | Recall unchanged in every variant; text-path prompt +20% to +24%. Public -0.007 [-0.047, +0.025], dup-065 0.67 -> 0.00 (hours answer refused with the extra pieces); 0 stale | **Tie on accuracy with a larger prompt: reject** | high |
| 4a | Contextual Retrieval, keyword half | LLM context line added to BM25 text (`ENRICH=ctx`) | Recall unchanged. Public -0.008 [-0.024, 0.000]; 0 stale | **Tie** | medium |
| 4b | Contextual Retrieval, embedding half (not tested before) | Window vectors computed from "context line + window" (`WINDOW_CTX=llm`); the model still gets the plain window. 2,193 new vectors | Recall unchanged. Public +0.011 [-0.016, +0.044]; 100 non-public -0.025 [-0.058, +0.002] (branch/contact 0.807 vs 0.897); 0 stale | **Tie, leaning loss** | medium |
| 4c | Contextual Retrieval, both halves | `ENRICH=ctx` + `WINDOW_CTX=llm` | Public -0.015 [-0.061, +0.022]; 0 stale | **Tie** | medium |
| 4d | Code-written context on windows (no LLM) | "title > headings" line embedded with each window (`WINDOW_CTX=head`) | Text recall 61 -> 57 (lost dup-031, dup-081 x3) | **Loss** | low (retrieval only) |
| 5a | Propositions (Dense X) sent to the model instead of chunks | Best propositions by meaning, grouped under their page, in place of the window pieces (`PROP_UNIT=replace`; same character budget) | Text recall 61 -> 51. Public -0.066 [-0.173, +0.021]; **stale answer in 3 of 3 runs** (dup-087 "fourth") | **Loss; breaks the zero-stale invariant** | high |
| 5b | Propositions added to the windows | `PROP_UNIT=union` | Recall unchanged, prompt +41% | **Reject** | high (retrieval only) |
| 6a | Fewer pieces: `TOP_K=6` | 6 keyword pieces instead of 8; windows unchanged | Text-path prompt -17%; per question -12% (public) / -14% (non-public). Public +0.002 [-0.026, +0.030]; non-public +0.003 [-0.015, +0.022]; 0 stale; latency unchanged (2d) | **Tie with a smaller prompt: meets the "shrink without harm" bar**, but the saving is ~250 tokens per question and buys no speed | medium-high |
| 6b | `TOP_K=5`, `TOP_K=4` | | K=5 loses dup-049's fallback; K=4 loses 6 questions (and triggers defect D6) | **Loss** | low (retrieval only) |
| 6c | Window cap `WINDOW_EXTRA_CAP=2/1/0` | | Text recall 57 / 55 / 51 of 62 | **Loss** | high (retrieval) |
| 6d | `TOP_K=6` + `WINDOW_EXTRA_CAP=2` (previous author's arm) | | Public -0.088 [-0.192, -0.003]; stale in 1 of 3 runs (dup-087) | **Loss** | high |
| 7a | Chunk size 1500 | `SPLIT_CHARS=1500`, window vectors re-embedded into a copy | Text recall 61 -> 57; public -0.028 [-0.092, +0.019], dup-031 and dup-080 lost in every run | **Loss** | medium-high |
| 7b | Chunk size 800 | `SPLIT_CHARS=800` | Text recall 61 -> 60, facts fallback 57 -> 56; prompt -26%. Public -0.009 [-0.035, +0.016]; **non-public -0.031 [-0.070, -0.001]** (held-out 0.917 vs 0.979, typo 0.905 vs 0.938) | **Loss** | high |
| 7c | Chunk size 600 / 400 | | Text recall 59 / 56 of 62 (all paths 118 / 115 of 123) | **Loss** | medium (retrieval only) |
| 8a | Reranking (new; no extra API call) | Keyword top 40 re-ordered by each chunk's best window similarity to the question (`RERANK=dense`), then top K | K=5: text recall 62/62 (recovers dup-034), covering prefix 4.79 -> 2.32; public +0.007 [-0.036, +0.046]; non-public +0.000 [-0.020, +0.020]; prompt about the same (the rerank favours longer chunks). K=4: public +0.010 [-0.008, +0.032]; non-public +0.001 [-0.030, +0.028]; prompt -8% / -19%; loses one facts-fallback question. 0 stale | **Tie; best ranking of all arms** | medium |
| 8b | RRF rerank (keyword + meaning rank) | `RERANK=rrf`, K=8/6/5 | Recall unchanged at K=8/6; K=5 loses dup-040 | Not better than dense | low (retrieval only) |

Confidence: **high** = the retrieval test (deterministic) and 3 end-to-end runs agree; **medium** = a tie within noise that
could hide an effect of about +-0.02; **low** = retrieval only, not run end to end.

### 2a. End-to-end, public set (40 questions, 3 runs per arm)

| arm | runs | accuracy (per run) | mean | diff vs base [95% CI] | stale | p50 | mean s | p95 | max | chars/q | questions moved >= 0.5 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 3 | 0.8822, 0.8899, 0.8636 | 0.8786 | - | 0 | 1.85 | 1.90 | 3.08 | 3.40 | 7572 | - |
| ctx_kw | 3 | 0.8403, 0.8822, 0.8899 | 0.8708 | -0.0078 [-0.024, +0.000] | 0 | 1.81 | 1.98 | 3.16 | 11.97 | 7635 | - |
| cr_emb_llm | 3 | 0.8589, 0.9054, 0.9054 | 0.8899 | +0.0114 [-0.016, +0.044] | 0 | 1.88 | 1.93 | 3.07 | 3.55 | 7559 | - |
| cr_full_llm | 3 | 0.8791, 0.8558, 0.8558 | 0.8636 | -0.0150 [-0.061, +0.022] | 0 | 1.86 | 2.02 | 3.73 | 4.73 | 7623 | dup-064 0.57->0.00 |
| q_kw | 3 | 0.8899, 0.9054, 0.8791 | 0.8915 | +0.0129 [+0.000, +0.032] | 0 | 1.82 | 1.86 | 2.71 | 3.54 | 7566 | - |
| mv_q | 3 | 0.8667, 0.8822, 0.8667 | 0.8718 | -0.0067 [-0.047, +0.025] | 0 | 1.77 | 1.84 | 2.80 | 3.94 | 9270 | dup-065 0.67->0.00 |
| propunit_repl | 3 | 0.8124, 0.8124, 0.8124 | 0.8124 | -0.0661 [-0.173, +0.021] | 3 (dup-087 run 1, dup-087 run 2, dup-087 run 3) | 1.80 | 2.00 | 2.97 | 8.32 | 7389 | dup-087 1.00->0.00; dup-008 1.00->0.00; dup-031 1.00->0.00; dup-081 1.00->0.00 |
| k6 | 3 | 0.8470, 0.8966, 0.8966 | 0.8801 | +0.0016 [-0.026, +0.030] | 0 | 1.77 | 1.87 | 2.73 | 3.92 | 6662 | - |
| k6_cap2 | 3 | 0.7992, 0.7729, 0.7992 | 0.7904 | -0.0881 [-0.192, -0.003] | 1 (dup-087 run 1) | 1.78 | 1.87 | 2.96 | 5.01 | 6024 | dup-087 1.00->0.00; dup-031 1.00->0.00; dup-081 1.00->0.00; dup-082 1.00->0.00 |
| s1500 | 3 | 0.8403, 0.8558, 0.8558 | 0.8506 | -0.0279 [-0.092, +0.019] | 0 | 1.82 | 1.89 | 2.71 | 3.70 | 6549 | dup-080 1.00->0.00; dup-031 1.00->0.00 |
| s800 | 3 | 0.8791, 0.8636, 0.8667 | 0.8698 | -0.0088 [-0.035, +0.016] | 0 | 1.78 | 1.90 | 2.87 | 3.80 | 5584 | - |
| rr_dense_k5 | 3 | 0.9066, 0.8833, 0.8678 | 0.8859 | +0.0074 [-0.036, +0.046] | 0 | 1.94 | 2.03 | 3.13 | 6.08 | 7676 | dup-087 1.00->0.33 |
| rr_dense_k4 | 3 | 0.9043, 0.8624, 0.8996 | 0.8888 | +0.0102 [-0.008, +0.032] | 0 | 1.84 | 1.93 | 3.06 | 6.72 | 6953 | - |

### 2b. End-to-end, 100 non-public questions (typo 48 + held-out 22 + temporal 21 + branch/contact 9), 3 runs per arm

| arm | runs | accuracy (per run) | mean | diff vs base [95% CI] | stale | p50 | mean s | p95 | max | chars/q | questions moved >= 0.5 | by subset |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 3 | 0.9559, 0.9594, 0.9466 | 0.9540 | - | 0 | 1.40 | 1.56 | 2.64 | 8.12 | 7914 | - | branch 0.897, heldout 0.979, temporal 0.986, typo 0.938 |
| k6 | 3 | 0.9594, 0.9510, 0.9594 | 0.9566 | +0.0026 [-0.015, +0.022] | 0 | 1.37 | 1.48 | 2.42 | 3.76 | 6804 | dup-087-typo1 0.33->1.00 | branch 0.885, heldout 0.958, temporal 0.993, typo 0.954 |
| s800 | 3 | 0.9002, 0.9336, 0.9350 | 0.9229 | -0.0310 [-0.070, -0.001] | 0 | 1.37 | 1.49 | 2.57 | 8.45 | 5629 | dup-081-typo2 1.00->0.00; ho-021 0.67->0.00 | branch 0.862, heldout 0.917, temporal 0.993, typo 0.905 |
| rr_dense_k5 | 3 | 0.9553, 0.9598, 0.9479 | 0.9543 | +0.0003 [-0.020, +0.020] | 0 | 1.37 | 1.54 | 2.70 | 8.12 | 7140 | dup-080-typo1 1.00->0.33 | branch 0.940, heldout 1.000, temporal 0.986, typo 0.919 |
| rr_dense_k4 | 3 | 0.9512, 0.9598, 0.9537 | 0.9549 | +0.0009 [-0.030, +0.028] | 0 | 1.35 | 1.51 | 2.54 | 4.95 | 6415 | dup-080-typo1 1.00->0.00; dup-087-typo1 0.33->1.00 | branch 0.956, heldout 1.000, temporal 0.982, typo 0.919 |
| q_kw | 3 | 0.9476, 0.9401, 0.9524 | 0.9467 | -0.0073 [-0.033, +0.017] | 0 | 1.35 | 1.48 | 2.45 | 3.72 | 7647 | dup-087-typo1 0.33->1.00; ho-022 1.00->0.33 | branch 0.874, heldout 0.917, temporal 0.995, typo 0.954 |
| cr_emb_llm | 3 | 0.9336, 0.9406, 0.9127 | 0.9290 | -0.0250 [-0.058, +0.002] | 0 | 1.29 | 1.42 | 2.32 | 3.55 | 7852 | dup-087-typo2 1.00->0.33; ho-022 1.00->0.33; dup-064 0.57->0.00 | branch 0.807, heldout 0.917, temporal 0.993, typo 0.931 |

`rr_dense_k5` run 3 was first invalidated by an answer-call timeout (`APITimeoutError`) and re-run after the other runs; its
characters were first double-counted (both attempts shared a ledger tag) and were recomputed from the valid attempt only; `e2e.py` now
tags a retry separately.

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

Setting: **priority tier off for every run** (`MY_SOLUTION_PRIORITY` unset; the ledger records `service_tier: default` for every
answer call). Each run's evidence was cold in the provider's prompt cache (per-run salt), as for unseen graded questions; the
instructions prefix was cached (about 45% of input tokens).

- Baseline, public set, live labels (stage A): per-run p50 1.80 / 1.80 / 1.94 s, p95 3.13 / 3.08 / 3.10 s, max 3.40 s; pooled
  p50 1.85, mean 1.90, p95 3.08. The un-salted pilot (28 of 41 answer calls fully served from the prompt cache): p50 1.85, p95 3.79.
- All 13 arms, pooled over 3 runs: p50 1.77 to 1.94 s, p95 2.71 to 3.73 s, with no pattern by prompt size.
- **Prompt size does not drive answer time.** Over 1,599 stage-A answer calls: seconds = 1.13 - 0.011 x (thousand characters)
  + 0.0073 x (output tokens); correlation with prompt size 0.015. Arm means of the answer call are 1.48 to 1.65 s for prompts of
  5.4k to 9.0k characters.
- **What sets p95** (baseline, slowest questions): dup-147 (3.19 s) and dup-145 (3.01 s) are rate questions the tables do not
  answer; they make two answer calls in a row (facts, then the text fallback) and end in "I don't know". Next is dup-104 (2.51 s),
  the longest answer (each branch's lobby hours). 5 of 1,560 stage-A answers took over 6 s: a call that hit the 6 s timeout and was
  retried. Answer latency follows answer length only weakly across questions (correlation 0.23).
- Labels call (Decisions API): p50 0.29 s, p95 0.62 s. HyDE call: p50 1.20 s, p95 1.65 s.
- Stage B latency excludes the labels call for every arm (frozen labels), so it is lower in absolute terms; compare arms within it only.
- **Priority tier on vs off: not measured.** The config is in `eval_report/configs/priority.json`; it was skipped at the end to
  stay within the instruction not to start new paid runs. It would cost about $0.25.

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

Read only after my results were final. "Theirs" = NOTES.md section 10 (and section 7 where noted) and `tasks/todo.md`.

| # | Claim in their notes | My result | Which is right, and why |
|---|---|---|---|
| 1 | Baseline retrieval recall 0.960 on 124 questions, 5 misses (dup-034, ho-010, tm-007, tm-016, tm-021) | 0.984 (121 of 123; 1 count question excluded), 2 misses (dup-034 on text search, ho-010 on the facts fallback) | **Mine, for what the model receives.** `retrieval_check.py` scores "what changed" questions on `retrieve()`, but `answer()` uses `_history_hits()`; on that path tm-007, tm-016 and tm-021 have every required string. Same conclusion either way: little headroom |
| 2 | "Fewer pieces (TOP_K=6, WINDOW_EXTRA_CAP=2): 0.799 vs 0.897 in 3 of 3 runs, one stale value. Do not ship"; "shrinking costs recall" | Same arm: 0.790 vs 0.879, stale in 1 of 3 runs (dup-087 "fourth"). But **TOP_K=6 alone** keeps recall and accuracy on both sets (3 runs each) with 12-14% fewer characters | **Both measured the arm correctly; their generalisation is wrong.** The damage comes from capping the window pieces (cap 2/1/0 lose 4/6/10 questions in retrieval), not from fewer keyword pieces. They never ran TOP_K without the cap |
| 3 | Chunk size 800: "accuracy is neutral" (public, 3 runs, 0.880 vs 0.879) | Public: tie (-0.009). **100 non-public questions: -0.031 [-0.070, -0.001]** | **Mine.** Their test was public-only, where the baseline is at its ceiling. Both keep the 3,000 default; the reason is a loss, not neutrality |
| 4 | Chunk size 1500 not tested at answer level (retrieval 0.927) | Public -0.028; dup-031 and dup-080 lost in every run | Mine adds this; consistent with their retrieval number |
| 5 | Hypothetical questions hurt: arm D (`q,emb`) 0.840 vs 0.905, 1 run; follow-up blames 3 unrelated extra pieces | Keyword half alone ties (public +0.013, non-public -0.007); meaning half alone ties overall but drops dup-065 (0.67 -> 0.00) | **Partly both.** Their 1-run -0.065 is inflated by the hours questions that flip in every arm; their provenance diagnosis (extras with no floor, defect D4) matches what I see on dup-065. The questions as keyword text do no harm |
| 6 | Enrichment cache "1,452 chunks of the newest copy (non-blog, non-news, non-rate pages)" | That is 26% of section text in the newest copy and 8-21% in older copies; every press release is excluded by the substring `news` (defect D1) | **Missing caveat on their side.** The negative enrichment result holds only for this coverage, and cannot speak to hours/closure questions, whose facts live in press releases |
| 7 | Propositions instead of chunks: recall 0.952, -4 to -9% characters, lost dup-082; "not worth an answer-level run" | My version (propositions in place of windows): recall -10 questions, accuracy -0.066, **stale in 3 of 3 runs** | **Same verdict.** Different designs; mine adds the stale-value finding, which a recall-only check cannot see (their own takeaway: "recall understates damage") |
| 8 | "Not planned (low expected gain): contextual embeddings, reranking" | Contextual embeddings: tie on public, -0.025 on non-public. Dense rerank: tie on accuracy, best ranking (covering prefix 4.79 -> 2.32, recovers dup-034) | **Their expectation holds for accuracy.** Reranking is the one change with a real retrieval gain, just not one that moves these scores |
| 9 | Query-time HyDE rejected without measurement ("an extra LLM call per answer") | Call p50 1.20 s, p95 1.65 s; retrieval lost 1-3 questions | **Agree**, now measured |
| 10 | NOTES 7/10: baseline (priority off) p50 1.65-1.71 s, p95 2.63-3.32 s | Same day, priority off: p50 1.80-1.94 s, p95 3.08-3.13 s (cold evidence); pilot with warm cache p50 1.85, p95 3.79 | **Cannot be settled across sessions**; plausibly part of the gap is prompt caching: their runs re-sent byte-identical prompts, which are served from the cache (finding P1; cached calls 0.24 s faster on average in my pilot). Unseen graded questions see cold evidence, so my figures are the realistic ones. Both agree a smaller prompt does not speed answers up |
| 11 | NOTES 7: priority-on runs p50 2.25-2.53 s, p95 3.4-4.1 s (not a controlled test, as NOTES says) | Not measured | **Open.** `tasks/todo.md` also says to re-enable the priority tier and re-measure before submission; on this branch it is still off by default |
| 12 | NOTES 7: public accuracy 0.851-0.867 over 5 runs | 4 baseline runs: 0.9054, 0.8822, 0.8899, 0.8636 (mean 0.885) | **Mine for the current code.** NOTES section 4 itself reports 0.8822 -> 0.9054 after the link-product rule; section 7 predates it |
| 13 | NOTES 8: "the answer call is about 90% of the time" | Answer call mean 1.53 s of a 1.90 s mean answer (about 80%); the labels call is about 0.33 s | Minor; mine is measured per call from the ledger. Two-call fallbacks are the slowest questions |
| 14 | Arm F (all enrichment + top-k 4) 0.886 | Defect D6 only changes "what changed" questions; the public set has none, so F's number is unaffected | No discrepancy |
| 15 | "Run embedding-heavy checks one at a time"; "recall understates damage from sending fewer pieces"; "hours questions flip in every arm, compare over 3 runs" | Confirmed on all three | Agree |

## 5. Spend

Prices (looked up 2026-11-20): gpt-6-luna $0.10 / 1M input, $0.01 cached, $0.50 output; Decisions API $0.10 / 1M input;
text-embedding-3-small $0.02 / 1M. Every call is in `results/ledger.jsonl` (not committed); `ledger.py` gives these tables.

| Model / API | Calls | Input tokens | of which cached | Output tokens | USD |
|---|---|---|---|---|---|
| gpt-6-luna, Decisions API (question labels) | 2,267 | 11,617,728 | 0 | 0 | 1.162 |
| gpt-6-luna, Responses (answers, fact extraction, HyDE) | 4,396 | 13,756,853 | 6,422,055 | 366,004 | 0.981 |
| text-embedding-3-small | 525 | 5,580,266 | - | - | 0.112 |
| gpt-6.1-sol (judge) | 0 | 0 | 0 | 0 | 0.000 |
| **Total** | 7,188 | | | | **2.254** |

By stage: end-to-end stage A $1.276, stage B $0.566, retrieval screening $0.273 (window re-embedding for chunk sizes and context
lines, plus 5 uncached label warm-ups per ingest), pilot $0.120 (of which $0.093 one-off fact extraction), HyDE generation $0.003,
checks $0.016. The LLM judge was not used: at about $0.18 per 40-question run it would have taken a third of the budget for a
stand-in metric, so `judged` is empty in `results.csv`.

## 6. Plain statement

**No ingest change beats the baseline on accuracy, and none beats it on latency.** Every technique asked about (HyDE,
hypothetical-question indexing, multi-vector indexing, Contextual Retrieval in both halves, propositions, fewer pieces, chunk
sizes 1500 / 800 / 600 / 400) and the extra one I added (reranking) is a tie within noise or a loss; propositions sent to the model
and capped window pieces also break the zero-stale invariant.

On the second question, **a smaller prompt without loss is possible: `MY_SOLUTION_TOP_K=6`** sends 12-14% fewer characters per
question with accuracy and latency unchanged within noise on both eval sets (3 runs each, 0 stale). The saving is about 250 input
tokens per question and buys no speed, because answer time does not depend on prompt size here; keeping the default of 8 is
equally defensible.

### What I learned that could improve the system (not ingest; none tested end to end)

1. **p95 is set by two-call fallbacks, not by evidence size.** The slowest baseline questions are rate questions the tables do not
   answer (dup-145, dup-147): a facts call, then a text-search call, then "I don't know". Deciding earlier that the facts cannot
   answer (or running the text search in parallel) is the latency lever; the 6 s timeout plus retry explains the rare 6-12 s answers.
2. **Prose questions can return stale values.** dup-087 says "fourth" whenever the newer release ("fifth") is not in the evidence;
   the newest copy still carries both releases. A rule that prefers the latest-dated release for repeated claims (like the existing
   count rule), and never cutting the window pieces, would close it.
3. **Dense rerank** (no extra API call) puts the needed evidence much earlier (covering prefix 4.79 -> 2.32) and recovers dup-034.
   It did not move these scores, but it is the retrieval change most likely to help on harder, reworded questions.
4. **Enrichment was only tested on 26% of the site.** A fair test needs press releases and blog posts enriched too (about $1 to $1.5).
