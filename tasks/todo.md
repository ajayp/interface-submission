# TypeScript port (`ts_solution/`) — plan

Status: M0-M5 done; M6 (CLI + eval runner) next. Spend so far ~ $0.14 of $2 (estimate). OpenAI spend so far ~ $0.11 of $2 (estimate: Python fact extraction ~$0.10 + TS smoke tests $0.004). (M0 was) (budget cap $2 OpenAI; zod for structured outputs, the one runtime dependency).

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

### M6 CLI + eval runner
- [ ] `cli.ts` (`ask`, `eval`, `conflicts`, `trace`), `scoring.ts` ported from `harness/scoring.py` (numeric match, traps, refusal, sources, consistency, speed p95), single worker, 60 s timeout, repeat sample.
- [ ] `NOTES.md` section for the TS version: keys needed (`OPENAI_API_KEY`), how to run.

### M7 Verification
- [ ] 3 runs on the public set (judge optional): accuracy within noise of Python (0.85 +/- 0.02), consistency 1.0, 0 stale values, p95 <= Python.
- [ ] `tsc --noEmit` clean; `node --test` passes.

## Risks / open points
- Stemmer parity: BM25 ranking changes if the stemmer differs, so the Snowball port is tested against PyStemmer output before anything else.
- Float16 vector decode: Node 22 has no `Float16Array`; decode by hand (cheap).
- Without `OPENAI_API_KEY` the TS version, like the Python one, falls back to keyword search only.
- Model noise: single runs are inside run-to-run noise, so compare over 3 runs.
- Cost: loading ~$0.10 cold if the facts cache is not reused; the parity tests need the Python side with its key only for LLM-derived dumps.

## Review
(added when done)
