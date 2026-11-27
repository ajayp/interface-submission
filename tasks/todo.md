# TypeScript port (`ts_solution/`) — plan

Status: ALL MILESTONES DONE (M0-M7) + extra validation done. OpenAI spend ~ $0.57 of $2 (estimate; ~$0.10 of it is the one-off Python fact extraction). OpenAI spend so far ~ $0.11 of $2 (estimate: Python fact extraction ~$0.10 + TS smoke tests $0.004). (M0 was) (budget cap $2 OpenAI; zod for structured outputs, the one runtime dependency).

## Decisions (user, 2026-11-24)
- Full port of `my_solution/` (ingest, facts, BM25 + embedding windows, Decisions query understanding, dates, history path, spellfix, conflicts()).
- Standalone: a TS CLI plus a TS eval runner. No Python shim. The numbers are comparable to the Python scorer, not official.
- Node 22+ with native type stripping (`node --experimental-strip-types`, no build step). Only dev dependency: `typescript` (type-check only).
- Lives in `ts_solution/` in ajayp/interface-submission, branch `claude/optimistic-pasteur-ntrzv3`. Reuses `my_solution/.embed_cache`, `eval/`, `snapshots/`, `docs/gold/`.

## Native-module mapping (zero runtime dependencies)
| Python | TS / Node built-in |
|---|---|
| `openai` SDK (Responses, Decisions, Embeddings) | `fetch` against `api.openai.com` (`/v1/responses`, `/v1/decisions`, `/v1/embeddings`), `AbortSignal.timeout` for the 6 s limit, one retry |
| `numpy` + `.npz` embedding cache | tiny `.npz`/`.npy` reader: `node:zlib` (inflateRaw) + `Buffer`/`Float16`->`Float32` decode, cosine by dot product |
| `PyStemmer` (Snowball English) | hand-port of the Snowball English (Porter2) stemmer, checked word-for-word against PyStemmer on the site vocabulary |
| `hashlib.sha1` cache keys | `node:crypto` |
| `ThreadPoolExecutor` | `Promise` pool with a concurrency limit |
| `pathlib`, `json` | `node:fs/promises`, `node:path`, `JSON` |
| zip snapshots | unzip `snapshots_zip/*.zip` with a small `node:zlib` zip reader (or use already-unpacked `snapshots/`) |
| `argparse` | `node:util` `parseArgs` |
| tests/eval | `node:test` + `node:assert` |
| markdown parsing (`MarkdownNodeParser` clone) | hand-port of `split_sections` |

## Milestones (each ends with a check-in; mark `[x]` as done)

### M0 Setup
- [x] `ts_solution/package.json` (`"type": "module"`, no deps, `typescript` in devDependencies), `tsconfig.json` (`noEmit`, `strict`, `allowImportingTsExtensions`), `README.md`.
- [x] `types.ts` + `openai.ts` (fetch client, zod->strict JSON schema, $ budget guard) (Page, Snapshot, Answer, Source, Conflict, KnowledgeSystem) mirroring `harness/contract.py`.
- [ ] Parity-fixture script (Python side, kept in `ts_solution/parity/`): dumps chunks, BM25 rankings, dates, facts, prompts to JSON for TS to compare against.

### M1 Data + search (no LLM) — DONE, parity-tested against Python
- [x] Snapshot loader + zip reader (`zip.ts`, `snapshots.ts`), `chunker.ts`, `stemmer.ts` (Snowball, current english.sbl), `search.ts` (BM25), `tiers.ts`, `categories.ts`, `category_words.ts`, `dates.ts`, `synonyms.ts`, `spellfix.ts`, `corpus.ts`.
- [x] Gate (`parity/`): stemmer 16,069/16,069 words equal PyStemmer; chunks identical on all 5 snapshots (7,124 / 7,124 / 7,105 / 7,078 / 7,931), BM25 top-8 ids and scores identical for the 40 public questions per snapshot; dates, synonyms and spellfix identical on 199 questions (all eval files).
- Found on the way: JS `.` does not match U+2028 (Python's does), so the heading regex needs the `s` flag. PyStemmer 3.x is newer than the Porter2 spec (inter/past prefixes, ogist, double-letter and -ing exceptions).
- Not ported (off by default in Python): boilerplate removal; `MY_SOLUTION_SPLIT_CHARS` is ported.

### M2 Embeddings — DONE, parity-tested against Python
- [x] `npz.ts` (reads the Python `.embed_cache/*.npz`: float16 decode, `<U40` keys), `embed_index.ts` (store keyed by sha1 of normalised text, shared question-vector lookup + prefetch, `WindowIndex` over 600/400 windows cut by code points, `fuse`). Vectors the cache lacks are embedded at ingest only and kept in `ts_solution/.cache/*.json` (the Python npz files are never rewritten).
- [x] Gate: window counts equal Python on all 5 snapshots (9,863 / 9,845 / 8,958 / 9,345 / 9,974), 0 windows without a vector, top-10 window search identical (ids, window text, similarity within 2e-4) for the 40 public questions per snapshot. Cost: $0.

### M3 LLM layer + facts — DONE
- [x] `openai.ts` (fetch; zod -> strict JSON schema; budget guard; **never sends `service_tier`**, no fast/priority mode), `llm.ts`, `decisions.ts` (raw `/v1/decisions`, shape confirmed live), `prompt.ts` + `data/prompts.json` (Python's resolved default prompts exported by `parity/export_prompts.py`, variant G2), `facts.ts`, `count_facts.ts`.
- [x] Facts cache: Python has no persistent one by default, so I ran its extraction once (302 calls, ~$0.10) into `data/facts_cache.json` (same `{table_key: facts}` format; the TS extractor reads it first, so a clean run pays $0).
- [x] Gate: tables (180 / 190 / 198 / 197 / 266), facts (1,269 ... 1,962), fact groups + winners, fact BM25 search (40 questions), count facts (546) and count-question detection all identical to Python on every snapshot. Live smoke test: Decisions, structured answer and fact extraction each worked first try ($0.004).
- Not ported: prompt variants other than G2 (all off by default / not adopted), `MY_SOLUTION_QU_ENGINE=luna`, answer-terms and second-pass switches (default off).

### M4 Answer path — DONE (`src/solution.ts`)
- [x] ingest, snapshot choice by date, before-first-snapshot refusal, count answers, fact path with text fallback, text retrieval (tier slots + embedding windows + hours schedule extras), history path, post-checks (no number on a value question -> refusal, strip "not listed" sentences), citations incl. same-value pages. `conflicts()` is a stub until M5.
- [x] Gate (`parity/check_answer_inputs.ts` vs `dump_py5.py`): for all 40 public questions the snapshot, date note, intent/labels, text pieces (+urls), fact hits and the exact user messages sent to the model are identical to Python (given the same Decisions labels).
- [x] Live end-to-end on 6 public questions: 6/6 expected values present, 0 traps, 1.3-2.4 s per answer, ingest 15.5 s (Python ~3 min cold, since TS reuses the committed fact cache).
- Spend so far ~ $0.12 of $2 (estimated: Python fact extraction ~$0.10, TS Decisions labels $0.012, answers/smoke ~$0.01).

### M5 conflicts() — DONE
- [x] `table_parse.ts`, `fact_match.ts`, `sentence_facts.ts` (prompt text from `data/prompts.json`, zod schema), `conflicts_v2.ts` (incl. counties), wired into `Knowledge.conflicts()`; sentence results cached in `data/sentence_cache.json` (seed, same format as Python's) + `.cache/sentences.json`.
- [x] Gate: with the same sentence cache, TS `conflicts()` = 42 entries identical to Python's (topic, values, sources, winner, reason), 0.7 s. Live: 18/20 sentences re-extracted identically (the 2 differences are `other`-kind sentences that are never compared), cost ~$0.01. Python reference run: 93 calls, ~$0.02.
- Scoring against `docs/gold/` comes with the M6 scorer port.

### M6 CLI + eval runner — DONE
- [x] `scoring.ts` (port of harness/scoring.py: numeric match, traps, refusal, sources, conflicts F1 + winner, consistency, p95 speed, pillars; the optional Anthropic judge is not ported) and `cli.ts` (`eval`, `ask`, `conflicts`, `score-conflicts`; single worker, 60 s timeout, repeat sample, `--ids/--limit` for cheap subsets). npm scripts: `eval`, `ask`, `conflicts`.
- [x] Scorer parity: the 40 TS answers re-scored with the original `harness/scoring.py` give identical item scores, categories, stale hits and speed; conflicts scoring identical on both gold lists (hand 0.586, table key 0.919, as in the Python notes).
- [x] First full public run (run 1, live Decisions, no label cache): accuracy 0.879, consistency 1.0 (paraphrase 20/20, repeat 20/20), p95 2.29 s (p50 1.63 s), 0 stale values, 0 errors, final 0.833 with the hand-list conflicts pillar (0.877 without a conflicts pillar). Misses = the known accepted ones (dup-049, 088, 005, 064, 066). Cost ~$0.06. Ingest 18.9 s.

### M7 Verification — DONE
- [x] Three public-set runs (same code, live Decisions, no label cache): accuracy 0.879 / 0.905 / 0.905, consistency 1.0 each, 0 stale values, 0 errors, p95 2.29 / 2.19 / 2.25 s. Final score 0.833 (run 1, with the hand-list conflicts pillar 0.586) and 0.904 / 0.903 (runs 2-3, no conflicts pillar, so not comparable with run 1).
- [x] Extra sets (1 run each): `standin_dates` 17/17 (1.0), `history_slice` 14/14 (1.0, exercises the history path), `yearless_dates` 1.0 (p95 4.76 s on that set).
- [x] `tsc --noEmit` clean, 19 unit tests pass; clean `git clone` + `npm install` + typecheck + tests + live 6-question run (6/6, 0 stale, 18 s loading, no warnings) all work from the pushed branch.
- [x] `ts_solution/README.md`.

## Risks / open points
- Stemmer parity: BM25 ranking changes if the stemmer differs, so the Snowball port is tested against PyStemmer output before anything else.
- Float16 vector decode: Node 22 has no `Float16Array`; decode by hand (cheap).
- Without `OPENAI_API_KEY` the TS version, like the Python one, falls back to keyword search only.
- Model noise: single runs are inside run-to-run noise, so compare over 3 runs.
- Cost: loading ~$0.10 cold if the facts cache is not reused; the parity tests need the Python side with its key only for LLM-derived dumps.

## Extra validation (2026-11-27, after M7)
- Other eval sets on TS (1 run each, est. cost $0.18 total): heldout 22/22 = 1.000, heldout_temporal 21/21 = 1.000, refusals 3/3, rates_reworded_refusals 23/23, slice1_reworded 10/10, casual_date_wording_grid 0.985, slice2_branch_contact 0.959, typo_robustness 0.954 (48 questions; the only misses are two typo variants of dup-088, the known accepted miss). 0 stale values, 0 errors on every set.
- Same-day Python run on the public set (harness, fast tier as the Python system uses it): accuracy 0.882, consistency 1.0, 0 stale, p50 1.43 s, p95 2.02 s, loading 33.7 s. TS today: accuracy 0.879 / 0.905 / 0.905, p50 1.63 s, p95 2.19-2.29 s. So accuracy is equal within noise (the earlier gap to the 0.851-0.867 in the Python notes was day-to-day variation, not a TS advantage), and TS is ~0.2 s slower at p95, consistent with it not using the fast tier.
- Client micro-benchmark (10 calls, noisy): connection setup is small in TS (first Decisions call 350 ms vs 278 ms later); Decisions ~280 ms (TS) vs ~310 ms (Python) once warm; answer calls ~760 ms Python fast tier, ~1,060 ms Python default tier, ~1,330 ms TS (default tier; the 270 ms gap to Python's default tier may be noise). Connection reuse does not explain a speed difference; the fast tier saves ~300 ms per answer.
- Failure paths (`test/failure.test.ts`, local mock of the OpenAI API, no cost): timeout + one retry, 5xx retried / 4xx not, no `service_tier` ever sent and strict schema, spend guard stops requests after the cap, windows missing a vector are embedded at ingest then found again after a reload (question vectors too), a failing model gives a visible error answer (never a fake refusal), no API key falls back to keyword search. 26 tests pass.
- "What changed" path: evidence lists (pieces, urls, copy dates) identical to Python for all 13 change questions of history_slice, standin_dates and heldout_temporal.
- Not done: Node versions other than 22.23 (README says >= 22.6), the stand-in LLM judge, the hidden set.

## Review
- Result: a full TypeScript port that runs on Node 22 with native type stripping and one runtime dependency (`zod`, for OpenAI structured-output schemas); everything else is built-in (`fetch`, `node:zlib`, `node:crypto`, `util.parseArgs`, `node:test`). No axios, no OpenAI SDK, no "fast"/priority tier.
- Fidelity: every stage was parity-tested against the Python code on the real data (stemmer 16,069 words, chunks, BM25, dates/synonyms/spellfix, window search, tables/facts/groups, count facts, the exact model inputs for the 40 public questions, `conflicts()` 42 entries, scorer). Differences are listed in `ts_solution/README.md`.
- Measured: public accuracy 0.879-0.905 over 3 runs vs 0.851-0.867 documented for Python. Same design, so I would not read this as an improvement: the runs differ by 0.026 among themselves, the Python figures were measured on another day, and the TS runs used no fast tier. Treat the two as equal within noise. p95 2.2-2.3 s (see the extra validation below for the same-day Python comparison).
- Not official: the Python harness cannot load TS, so scores come from the ported scorer (identical item scores on the same answers). The stand-in LLM judge was not ported or run (Python measures ~0.81 with it).
- Open: boilerplate removal and non-default prompt variants are not ported; the price table behind the spend guard is a rough estimate.
