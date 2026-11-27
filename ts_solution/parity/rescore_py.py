"""Re-scores a TS eval run with the ORIGINAL harness scorer (harness/scoring.py) and compares every item score and the summary.
Usage: rescore_py.py RUN_DIR [EVAL.jsonl]   (RUN_DIR has per_question.jsonl and report.json written by the TS runner)"""
import json, sys
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import scoring

run = Path(sys.argv[1])
items = {json.loads(l)["id"]: json.loads(l) for l in open(sys.argv[2] if len(sys.argv) > 2 else ROOT / "eval/public_eval.jsonl") if l.strip()}
rows = [json.loads(l) for l in (run / "per_question.jsonl").read_text().splitlines() if l.strip()]
bad = 0
py = []
for r in rows:
    a = r["answer"]
    ans = SimpleNamespace(text=a["text"], confident=a["confident"], sources=[SimpleNamespace(url=s["url"]) for s in a["sources"]])
    p = scoring.score_item(items[r["id"]], ans)
    p.update(latency_s=r["latency_s"], error=r["error"], answer=a)
    py.append(p)
    for k in ("score", "correctness", "source_hit", "matched", "missed", "trap_hits"):
        if p[k] != r[k]:
            bad += 1; print("DIFF", r["id"], k, "py", p[k], "ts", r[k])
rep_ts = json.loads((run / "report.json").read_text())
conf = rep_ts.get("conflicts")
repeats = []  # consistency repeat texts are not stored; compare the parts that do not need them
rep_py = scoring.summarize(py, conf, [])
for k in ("qa_score", "stale_trap_hits", "errors", "by_category"):
    if rep_py[k] != rep_ts[k]:
        bad += 1; print("DIFF summary", k, rep_py[k], rep_ts[k])
if rep_py["consistency"]["paraphrase_consistency"] != rep_ts["consistency"]["paraphrase_consistency"]:
    bad += 1; print("DIFF paraphrase consistency")
if rep_py["speed"] != rep_ts["speed"]:
    bad += 1; print("DIFF speed", rep_py["speed"], rep_ts["speed"])
print(f"{len(rows)} items rescored with harness/scoring.py: {'all identical' if not bad else str(bad) + ' differences'}; py qa {rep_py['qa_score']} ts qa {rep_ts['qa_score']}")
