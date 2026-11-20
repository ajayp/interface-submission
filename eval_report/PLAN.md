# Independent ingest evaluation: plan and progress

Plan for the audit requested on 2026-11-20. It lives here, not in `tasks/todo.md`: the task says not to read that file (or
`tasks/lessons.md`, or NOTES.md section 10) until my own results are finished.

Question: can changes to ingest (what is indexed, how pages are chunked) raise accuracy, or shrink the prompt sent to the
answer model without hurting accuracy or latency? Baseline = current branch, no switches set.

## Plan

- [x] 0. Setup: branch `claude/independent-eval`; snapshot zips from PR 23 (git-ignored, never committed); deps; key present
- [x] 1. Read CLAUDE.md, NOTES.md sections 1-9, workflow.md; read the experiment code
- [x] 2. Code review of `enrich.py`, `retrieval_check.py` and their hooks in `solution.py` / `chunker.py` (cache keys, index vs return,
         floor, leakage of generated text, number guard). Fix or note each defect
- [x] 3. Instrumentation that does not change behaviour:
  - [x] spend ledger: every OpenAI call (responses, decisions, embeddings) appends its token usage to a JSONL file (a
        `usercustomize` in `eval_report/tools/`, loaded via PYTHONPATH, so the solution code is untouched)
  - [x] runner: sequential, interleaved arms; per run accuracy, stale, p50/mean/p95/max, chars and input tokens of answer calls;
        log scan for `RateLimit`, `meaning search is off`, `have no vector`
  - [x] committed caches protected: question, window and enrichment vector files pointed at copies under `results/`
- [x] 4. Pilot: one baseline run cold (builds the fact cache, measures cost per run); project total spend against $3.50
- [ ] 5. Retrieval-only screening (no answer calls) on public, held-out, typo, branch/contact, temporal sets; split by the path a
        question really takes (facts / text / history) so rate questions are not miscounted
- [x] 6. New code needed for techniques the branch does not cover:
  - [x] Contextual Retrieval, embedding half: context line + window embedded together
  - [x] Propositions sent to the model instead of the full chunk
  - [x] HyDE (retrieval-only test; it costs an answer-sized call per question at query time)
  - [x] Reranking (embedding rerank of the keyword candidates, no extra API call)
- [ ] 7. End-to-end: public set, 3 runs per arm, baseline interleaved; priority tier off for every arm (the branch default)
- [ ] 8. Chunk size 1500 / 800 / 600 / 400 (window caches built one at a time, on copies)
- [ ] 9. Write `eval_report/INDEPENDENT_REPORT.md` and `eval_report/results.csv`
- [ ] 10. Only then read NOTES.md section 10 and `tasks/todo.md`; list every discrepancy; check NOTES.md section 7 latency
- [ ] 11. Commit code and report only (no snapshots, zips or `results/`); push to `claude/independent-eval`

## Budget

$3.50 ceiling for OpenAI. Prices used (looked up 2026-11-20): gpt-6-luna $0.10 / 1M input, $0.01 cached, $0.50 output;
Decisions API $0.10 / 1M input; text-embedding-3-small $0.02 / 1M; judge gpt-6.1-sol $2 / $10 (used sparingly or not at all).

## Progress notes

- Pilot (1 cold baseline run, public): accuracy 0.9054, stale 0, p50 1.85 s, p95 3.79 s; $0.12 cold of which $0.093 is the
  one-off fact extraction; a warm public run costs about $0.027 (mostly the Decisions call, ~5k uncached tokens per question).
- Every pilot miss is a known reference/scorer mismatch (dup-064/066 source, dup-049, dup-005, dup-088); the evidence held all
  required strings each time, so the public set is at its ceiling for retrieval changes.
- Baseline retrieval: text-path recall 0.984 (61/62), facts-fallback 0.983: little headroom; the realistic gain is a smaller prompt.
- Answer-call time follows output tokens (r=0.54), not input size (r=-0.10): a smaller prompt should barely change latency.
- Prompt-cache confound: 28 of 41 pilot answer calls were fully cached (identical prompts sent earlier today). Added
  MY_SOLUTION_NONCE_SALT (default off) and set a per-run salt in e2e.py so every arm runs with cold evidence, as graded questions do.
- HyDE call latency p50 1.20 s, p95 1.65 s (would sit on the timed path of every text-search answer).
- Labels from the Decisions API were identical across repeated calls (12/12); screening still freezes them (saves money).
