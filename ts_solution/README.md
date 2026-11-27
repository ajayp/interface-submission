# ts_solution: TypeScript port of `my_solution/`

A question-answering system over the five dated crawls of the Dupaco website: the **current**, correctly-tiered value, a source, an honest
"I don't know", and a list of places where the site contradicts itself. It is a port of the Python system in `../my_solution/`
(same design, same defaults, same `MY_SOLUTION_*` switch names). How "current" is decided is in `../NOTES.md` section 3 and applies unchanged.

It runs **standalone** (its own CLI and scorer). The organizers' harness is Python and cannot load it; the scores here are comparable to
the Python harness's (the scorer is a line-for-line port, checked against `harness/scoring.py`), not official.

## Requirements

- Node 22.6 or newer. TypeScript files run directly with `node --experimental-strip-types` (no build step).
- `npm install` (one runtime dependency, `zod`, used to write the JSON schemas for OpenAI structured outputs; `typescript` and
  `@types/node` for type-checking only). Everything else is built in: `fetch`, `node:zlib` (zip and `.npz` reading), `node:crypto`,
  `node:util` `parseArgs`, `node:test`.
- `OPENAI_API_KEY` in the environment (never in the repo). Models: `gpt-6-luna` (answers, fact and sentence extraction, Decisions API) and
  `text-embedding-3-small`. Without a key it falls back to keyword search only and returns raw page text.
- The snapshots in `../snapshots/` (unpacked from `../snapshots_zip/*.zip` on first use).
- **No "fast"/priority service tier is ever requested** (`service_tier` is never sent).

## Run it

```bash
cd ts_solution && npm install
npm run eval                                   # the 40 public questions -> results/ (per_question.jsonl, report.json)
node --experimental-strip-types --no-warnings src/cli.ts eval --eval ../eval/subsets/standin_dates.jsonl --out results/dates --repeat-sample 0
npm run ask -- "What is the APY on the 17-month special certificate?"
npm run ask -- "What was the auto loan rate?" --as-of 2026-06-15
npm run conflicts -- --out results/conflicts.json
node --experimental-strip-types --no-warnings src/cli.ts score-conflicts results/conflicts.json   # vs ../docs/gold/*
npm run typecheck && npm test
```

Options for `eval`: `--out DIR`, `--repeat-sample N` (consistency re-asks, 0 = off), `--conflicts-gold FILE` (repeatable), `--ids a,b`,
`--limit N`, `--snapshots DIR`.

## Data and caches (what a clean checkout needs)

| File | What | Why it is committed |
|---|---|---|
| `../my_solution/.embed_cache/*.npz` | embedding vectors of every 600-character window of every copy, and of the public questions | read-only; a run embeds nothing |
| `data/facts_cache.json` | rate-table facts (302 tables, one model call each, ~$0.10 once) | loading costs $0 and takes ~19 s |
| `data/sentence_cache.json` | rate-sentence readings for `conflicts()` | `conflicts()` costs $0 |
| `data/prompts.json` | the answer, fact and sentence prompts exported from `my_solution/prompt.py` (`parity/export_prompts.py`) | identical wording to Python |
| `.cache/` (git-ignored) | anything new this port had to embed or extract | created on demand |

If the site changes, windows without a vector are embedded at ingest (needs the key; never while answering) and new tables or sentences are
extracted once and cached.

## Layout (`src/`)

`snapshots.ts`, `zip.ts` (load crawls) · `chunker.ts`, `corpus.ts`, `categories.ts`, `tiers.ts` (pieces and page trust) · `stemmer.ts`
(Snowball English, hand-ported), `search.ts` (BM25), `synonyms.ts`, `spellfix.ts`, `dates.ts` (question understanding without a model) ·
`npz.ts`, `embed_index.ts` (meaning search over windows) · `openai.ts` (fetch client, zod schemas, spend guard), `llm.ts`, `decisions.ts`,
`prompt.ts` · `facts.ts`, `count_facts.ts` (fact path) · `solution.ts` (ingest, answer, history path, conflicts) · `table_parse.ts`,
`fact_match.ts`, `sentence_facts.ts`, `conflicts_v2.ts` · `scoring.ts`, `cli.ts`.

## How it was checked against Python (`parity/`)

Each stage was compared with the Python code on the real data before the next was built: stemmer (16,069 words identical), chunks
(7,124 / 7,124 / 7,105 / 7,078 / 7,931) and BM25 rankings, dates / synonyms / spellfix (199 questions), window search, tables, facts,
fact groups and winners, count facts, everything that feeds the answer model for the 40 public questions (including the exact messages),
`conflicts()` (42 entries identical), and the scorer. Scripts: `dump_py*.py` (Python side) and `check_*.ts` (TS side); the Python
side needs a venv with `PyStemmer`, `numpy` and `openai`.

## Differences from the Python system

- Only prompt variant G2 is ported (every other variant is off by default there and was not adopted); the old `luna` query engine
  (`MY_SOLUTION_QU_ENGINE=luna`), the answer-terms and second-pass switches, and the boilerplate removal (off in Python) are not ported.
- The model's input id (nonce) is a SHA-256 of the request, as in Python, but over a JSON string, so it differs from Python's value; the
  prompts are otherwise identical.
- Vectors the cache lacks go to `.cache/*.json` instead of rewriting the `.npz` files.
- The optional LLM judge of the harness (Anthropic) is not ported.
- A hard spend guard stops OpenAI calls at `MY_SOLUTION_BUDGET_USD` (default 2); its prices are rough estimates.
