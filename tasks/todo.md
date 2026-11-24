# TypeScript port (`ts_solution/`) — plan

Status: M0 in progress (budget cap $2 OpenAI; zod for structured outputs, the one runtime dependency).

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

### M1 Data + search (no LLM) — parity tested against Python dumps
- [ ] Snapshot loader (manifest + `pages/*.md`, optional zip unpack).
- [ ] `chunker.ts` (heading split identical to the library, table-row pieces).
- [ ] `stemmer.ts` (Snowball English) + `search.ts` (BM25 per snapshot, stop words, trust-tier slots).
- [ ] `dates.ts`, `synonyms.ts`, `spellfix.ts`, `tiers.ts`, `categories.ts`, `category_words.ts`.
- [ ] Gate: chunk count, BM25 top-8 ids and date parsing match Python on all 40 public questions + the `eval/subsets/*` files.

### M2 Embeddings
- [ ] `npz.ts` reader, `embed_index.ts` (lookup only; no vectors built while answering; missing vectors embedded at ingest only), RRF fusion.
- [ ] Gate: window-search results match `retrieval_diff` output from Python.

### M3 LLM layer + facts
- [ ] `llm.ts` (Responses API, strict JSON schema, cache per (question, snapshot)), `decisions_understanding.ts`, `query_understanding.ts` fallback.
- [ ] `facts.ts`, `table_parse.ts`, `fact_match.ts`, `count_facts.ts` (facts cache on disk as JSON, reuse the Python one if the format allows).
- [ ] `prompt.ts` (variant G2 default; port the prompt text verbatim, other variants behind the same env switches).

### M4 Answer path
- [ ] `solution.ts`: ingest, snapshot choice, history path, fact path, text fallback, post-check refusal, all `MY_SOLUTION_*` switches kept with the same names and defaults.

### M5 conflicts()
- [ ] `sentence_facts.ts`, `conflicts_v2.ts`; score with a TS port of `score_conflict_lists` against `docs/gold/*.json`.

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
