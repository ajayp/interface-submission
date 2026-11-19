# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A hackathon submission (`Knowledge-Hackathon-Assignment.pdf`): a question-answering system over five dated crawls of the Dupaco credit union website. It answers with the **current**, correctly-tiered value plus a source, refuses ("I don't know") when the site does not say, and lists places where the site contradicts itself. The submission is `my_solution/` (entry `solution.py`, `build()`). `harness/` and `starter/` are the organizers' code; don't change `harness/` behavior.

Read `NOTES.md` (design, decisions, results, known limits) and `workflow.md` (diagrams) before making non-trivial changes. `judge-workflow.md` covers the LLM judge.

## Commands

Python 3.11. Needs `OPENAI_API_KEY` (paid; models `gpt-6-luna`, the Decisions API, `text-embedding-3-small`). Without a key it runs on keyword search only and scores ~0.34.

```bash
pip install -r my_solution/requirements.txt

# Full public eval (40 questions). First run unzips snapshots_zip/*.zip into snapshots/ (zips are not in the repo)
python harness/run_eval.py --submission my_solution --eval eval/public_eval.jsonl --out results/run1

# Tiny offline-ish fixture (harness/selftest)
python harness/run_eval.py --submission my_solution --snapshots harness/selftest/snapshots --eval harness/selftest/eval.jsonl

# Re-score a finished run with the LLM judge (stand-in for the scorer's --judge)
python my_solution/judge_eval.py --results results/run1/per_question.jsonl --eval eval/public_eval.jsonl

# Inspect exactly what is sent to the model (writes results/traces/*.md)
python my_solution/trace.py --eval eval/public_eval.jsonl --ids dup-088
python my_solution/trace.py --question "..."

# Regression across all eval sets and env-switch arms (resumable)
python my_solution/regress.py --config docs/regress_example.json --out results/regress

# conflicts() output and scoring against docs/gold/
python my_solution/dump_conflicts.py --out results/conflicts/now.json
python my_solution/score_conflict_lists.py results/conflicts/now.json -v
```

There is no unit-test suite or linter; "tests" are the eval runs. To run one question, use `trace.py --ids` or an `--eval` file with a single line. Loading costs ~3 min and ~$0.10 cold. A single run is within model noise, so compare changes over ~3 runs (use `regress.py`). `results/` is git-ignored.

## Architecture

The harness calls `build()`, then `ingest(Snapshot)` per crawl (oldest to newest), `answer(question, as_of=)` per question, and finally `conflicts()`; types are in `harness/contract.py`. `my_solution/solution.py` orchestrates three flows:

1. **Ingest:** `chunker.py` splits pages by heading and also emits one extra self-describing chunk per table row; `search.py` builds a per-snapshot BM25 index; `facts.py`/`table_parse.py` have the LLM read each rate table once into structured facts (product, term, tier, value, source, dates), cached on disk.
2. **Answer:** `decisions_understanding.py` makes one Decisions API call that labels intent, rate type, past-date, change and section (falls back to the plain question on failure; code checks in `query_understanding.py`/`dates.py` back up the labels). Then: pick the snapshot (newest, or latest on or before a date); count questions are answered in code (`count_facts.py`); rate/fee questions go to the extracted facts (`fact_match.py`, `tiers.py` rank winners) with a second text-search call as fallback; everything else uses BM25 plus embedding windows (`embed_index.py`). `prompt.py` and `llm.py` build and make the answer call. A post-check turns "can't answer" or a number-less value answer into the standard refusal.
3. **Conflicts:** only the newest snapshot; rate tables by code, rate sentences via small LLM calls (`sentence_facts.py`), org counts via patterns (`count_facts.py`); `conflicts_v2.py`.

## Constraints that are easy to violate

- **"Current" rules** (NOTES.md section 3): newest copy by default; page-type precedence is rate sheet > product page > promo > everything else; later effective date wins; ended offers always lose; qualifiers (tier, term, personal vs business, rate vs APY) are distinct facts, never conflicts. Stale values must never reach the model (0 stale in every run is the invariant).
- **General rules only**: nothing typed in for a specific public question, because the hidden set rewords questions.
- `chunker.py`'s `split_sections` re-implements LlamaIndex's `MarkdownNodeParser` (llama-index is not a dependency); keep its output identical to the library's. Everything after it in `chunk_page` is custom.
- Question text is passed to the LLM as data, not instructions.
- Embedding windows use the vectors in `my_solution/.embed_cache/` (committed; keep them committed so a run embeds nothing). At `ingest` only, windows with no vector (file missing or site changed) are embedded and saved; never while answering. Without a key or if that fails, the snapshot falls back to keyword search with a warning.
- `my_solution/` imports `contract` from the nearest parent `harness/` (see top of `solution.py`); keep it runnable when copied elsewhere.
- Prompt variants (`prompt_*.md`, `prompt_*_edits.json`) and `docs/prompt_tuning/` come from the prompt-tuning loop (`prompt_tune.py`); no tried change helped reliably, so the current prompt stayed.
