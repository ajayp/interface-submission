"""Exports the resolved default prompts (variant G2, default env switches) to ts_solution/data/prompts.json so the TS port uses the
exact same text. Re-run after any change to my_solution/prompt.py or facts.py."""
import json, sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "my_solution"))
for k in [k for k in os.environ if k.startswith("MY_SOLUTION_")]: del os.environ[k]
import prompt as P, facts as F, sentence_facts as SF
out = {
    "developer": P.DEVELOPER_MESSAGE, "intent_blocks": P.INTENT_BLOCKS, "history_block": P.HISTORY_BLOCK,
    "date_block": P.DATE_BLOCK, "date_block_explain": P.DATE_BLOCK_EXPLAIN, "answer_schema": P.ANSWER_SCHEMA,
    "fact_developer": F.FACT_DEVELOPER_MESSAGE,
    "sentence_system": SF.SYSTEM, "sentence_context_rule": SF.CONTEXT_RULE,
}
(ROOT / "ts_solution/data/prompts.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print({k: (len(v) if not isinstance(v, dict) else list(v)) for k, v in out.items()})
