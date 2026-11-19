# Wormhole vectors: can they help retrieval, accuracy and answer latency?

Status: PLAN, waiting for approval. Nothing is built yet.
Source of the idea: `ajayp/wormhole-vectors` (Solr PoC, dense -> SKG terms -> BM25; also sparse -> pooled vector -> KNN).

## What we are testing, in plain words

Today BM25 and the embedding search run side by side and their results are only merged. A wormhole makes one drive the other:

- **W1, dense -> terms -> BM25 ("d2s").** Take the top-k embedding hits as the foreground set. Count which words are far more common in
  that set than in the whole snapshot (a small stand-in for Solr's SKG `relatedness()`; plain counting, no model call). Add the top
  terms to the BM25 query. Aim: wording gaps (reworded and casual questions, where rate questions fell 0.98 -> 0.90 and typo/casual
  sets score lower) without hand-kept synonym lists.
- **W2, sparse -> pooled vector -> KNN ("s2d").** Take the BM25 top-N, average their cached piece vectors (mean + L2 norm), and run KNN
  on that average. It needs NO question-embedding API call (vectors are already in `.embed_cache`), so it is the one variant with a
  possible latency win by itself.
- **W3, foreground tightness (specificity).** Mean cosine of the foreground to its centroid. Possible uses: how many pieces to send,
  or an early "broad / not covered" signal. Item 13 in the older notes showed naive refusal tests are dangerous, so this is only
  measured, never used to refuse, until it proves itself.

## Honest expectations (so we do not oversell)

- The wormhole repo's own large-corpus result: the disambiguation edge over BM25 did NOT reproduce on real messy text; eval wins were
  small (purity 0.973 -> 0.987). Expect a modest effect here too. Our corpus is one credit-union site, so the "java vs coffee" case
  barely exists; the realistic gain is vocabulary gaps and tier/qualifier words.
- Latency: the answer-call time is mostly the model call. A wormhole adds a little CPU and cannot make the model faster by itself.
  A real latency win has to come from (a) fewer or shorter pieces sent (fewer prompt tokens), (b) fewer second model calls (rate
  questions that fall back to the text path), (c) W2 skipping the embedding call, (d) possibly dropping the synonym step.
  So latency is measured as prompt tokens, number of model calls and p50/p95, not assumed.
- Solr SKG is not available in the grader (clean Python 3.11, no Solr). Everything must be in-memory Python/numpy, over the BM25
  index and the committed vectors. No new dependencies.

## Plan (check items off as done)

### Step 0: setup (no cost)
- [ ] Python 3.11 venv, `pip install -r my_solution/requirements.txt` (this box has 3.13 and no `openai`/`numpy`; the grader uses 3.11)
- [ ] Unzip snapshots (`harness/run_eval.py` does it on first run); confirm `OPENAI_API_KEY` works with a 1-question trace
- [ ] Baseline: 1 run of `public_eval.jsonl` on current `main` to confirm the notes' numbers (accuracy ~0.85, p95 ~3.7-4.5 s)

### Step 1: retrieval-only test (no answer model, nearly free), the gate
- [ ] New `my_solution/wormhole.py`: `skg_terms(foreground_chunks, index, k)`, `pool_vectors(...)`, `specificity(...)`. Pure functions, unit-checked by hand on 3 questions.
- [ ] Hook behind env switches, default OFF: `MY_SOLUTION_WORMHOLE=off|d2s|s2d|both` (follows the repo's rollback-switch convention)
- [ ] Retrieval score: does the gold evidence reach the top pieces (hit@8, hit@11) and is a stale/other-tier piece ranked above gold? Sets: public 40, heldout 22, heldout_temporal 21, typo_robustness, casual sets, slice1_reworded
  (note: `retrieval_eval.py` / `retrieval_diff.py` named in the older notes are not in this repo; either port them or write a small scorer from `must_include` strings)
- [ ] Gate: continue only if some slice gains hit@k and no slice gains trap-above-gold. Otherwise stop and write up a negative result.

### Step 2: answer-level test (costs API money, only if the gate passes)
- [ ] REDUCED (user asked, est. $0.3-0.5): sets public 40 + heldout 22 + typo_robustness 48 + slice1_reworded 10; arms `base` + only the variants that pass step 1; 3 runs, judge on. Date/change/temporal sets run only for a winning arm, as guards
- [ ] Record per arm: accuracy (scorer and judge), stale values (must stay 0), consistency, p50/p95, prompt tokens per answer, model calls per answer (fallback rate), cost
- [ ] Decision rule: adopt only if accuracy is up outside the 3-run noise (model disagrees with itself on ~13% of identical questions) with 0 stale, or if accuracy is equal and p95 / tokens drop clearly

### Step 3: latency angle (only for arms that survive)
- [ ] Try sending fewer pieces when the foreground is tight (W3); measure tokens, p95 and accuracy
- [ ] Try W2 as the embedding path (no question-embedding call); measure p95
- [ ] Try SKG terms in place of the `synonyms.py` lookup; measure accuracy

### Step 4: write-up
- [ ] Review section below, `tasks/lessons.md` entry, and a short NOTES.md paragraph only if something is adopted

## Review (fill in after the run)

_not started_
