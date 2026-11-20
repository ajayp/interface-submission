# Lessons (updated after each correction)

1. "HyDE" here means INGEST-time enrichment (hypothetical questions, context lines, propositions), not a query-time LLM call. Ask what the user means before ruling an idea out.
2. Turn provenance logging on in the FIRST run of any retrieval change (`MY_SOLUTION_PROV=<file>`), so we can see which pieces came from where and which the model cited. Do not explain a result with a guess.
3. A "smaller message" test must shrink the whole user message (keyword pieces, window pieces, enrichment pieces) and be measured in characters/tokens; cutting only keyword top-k is not that test.
4. The OpenAI priority tier is OFF while testing (credit saving; `MY_SOLUTION_PRIORITY=1` turns it on). Measured latency with it off (p50 about 1.7 s, p95 2.63-3.32 s) was LOWER than NOTES.md's original priority-on figures (p50 2.25-2.53, p95 3.4-4.1); I had assumed the opposite. Compare arms only with each other; a controlled on/off test (same time, 3 runs each) is the only way to know the switch's effect on speed.
5. Check retrieval first (does the evidence hold the required value? `retrieval_check.py`) before blaming the model or the prompt. Add relevance floors to anything that appends pieces unconditionally.
6. Never commit or push to main; work only on `claude/eloquent-bardeen-9r4xbs`.
7. One run per arm is within noise (about 0.02): repeat 3 times before calling a win or a loss.
