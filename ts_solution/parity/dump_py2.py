"""Python side: dates, synonym expansion, spellfix for every question of every eval file. Usage: dump_py2.py OUT.json"""
import json, sys, glob
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "my_solution")); sys.path.insert(0, str(ROOT / "harness"))
import dates, synonyms, spellfix, run_eval
dates.REFERENCE = "2026-09-28"
qs = []
for f in [ROOT / "eval/public_eval.jsonl", *sorted((ROOT / "eval/subsets").glob("*.jsonl")), *sorted((ROOT / "eval").glob("*.jsonl"))]:
    for l in open(f):
        if l.strip():
            try: qs.append(json.loads(l)["question"])
            except Exception: pass
qs = list(dict.fromkeys(qs))
extra = ["what was the rate before September 2026", "mid-May 2026 checking", "rate as of 7/15/2026", "back in June auto", "May I open an account",
         "in early August 2026", "late in March", "rate prior to the start of June 2026", "as of 2026-07-04", "savngs rate", "moneymarket rate", "sav ings account"]
qs += [q for q in extra if q not in qs]
sp = spellfix.SpellFix()
for s in run_eval.load_snapshots(ROOT / "snapshots"):
    for p in s.pages: sp.add_text(p.markdown)
out = {"questions": qs, "dates": {q: [dates.question_date(q), dates.asks_before_date(q)] for q in qs},
       "syn": {q: synonyms.expansion(q) for q in qs}, "spell": {q: sp.extra_words(q) for q in qs}}
json.dump(out, open(sys.argv[1], "w"))
print(len(qs), "questions;", sum(1 for q in qs if out["spell"][q]), "with spell fixes")
