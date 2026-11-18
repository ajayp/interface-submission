"""
Score a saved conflicts() list against any number of hand-made gold lists, with the scorer's own matching rules
(harness/scoring.py score_conflicts; pillar = 0.7 * F1 + 0.3 * right-winner rate).

    python my_solution/score_conflict_lists.py results/conflicts/base.json
    python my_solution/score_conflict_lists.py results/conflicts/new.json --compare results/conflicts/base.json -v
    python my_solution/score_conflict_lists.py new.json --gold docs/gold/conflicts_gold_*.json other_list.json

Gold lists: every file matching docs/gold/conflicts_gold_*.json is used by default, so a new list is added by dropping a file with that
name (same format as harness/selftest/conflicts_gold.json: id, topic_keywords, values, correct_value). No model calls, no cost.
"""
import argparse
import glob
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
from scoring import _norm, contains, score_conflicts  # noqa: E402


def load(path):
    return [SimpleNamespace(**c) for c in json.loads(Path(path).read_text())]


def detail(gold, subs):
    """Per gold entry: found? right winner? (same matching as score_conflicts)."""
    rows, used = [], set()
    for g in gold:
        hit = None
        for i, c in enumerate(subs):
            if i in used:
                continue
            vals = " | ".join(c.values or [])
            vh = sum(contains(vals, v) for v in g["values"])
            kh = any(_norm(k) in _norm(c.topic or "") for k in g.get("topic_keywords", []))
            if vh >= 2 or (vh >= 1 and kh):
                hit = (i, c)
                used.add(i)
                break
        won = bool(hit and g.get("correct_value") and hit[1].resolution and contains(hit[1].resolution, g["correct_value"]))
        rows.append((g["id"], hit is not None, won, hit[1].topic[:60] if hit else ""))
    return rows


def pillar(r):
    return 0.7 * r["f1"] + 0.3 * (r["resolution_accuracy"] or 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("conflicts", type=Path, help="JSON written by dump_conflicts.py")
    ap.add_argument("--gold", nargs="*", help="gold files (default: docs/gold/conflicts_gold_*.json)")
    ap.add_argument("--compare", type=Path, help="an earlier dump to show the change against")
    ap.add_argument("-v", "--verbose", action="store_true", help="list misses and wrong winners per gold list")
    a = ap.parse_args()
    files = sorted(f for pat in (a.gold or [str(ROOT / "docs/gold/conflicts_gold_*.json")]) for f in glob.glob(pat))
    subs = load(a.conflicts)
    base = load(a.compare) if a.compare else None
    print(f"{a.conflicts}: {len(subs)} entries" + (f"   (compared with {a.compare}: {len(base)})" if base else ""))
    print(f"{'gold list':38} {'n':>3} {'found':>5} {'recall':>6} {'prec':>5} {'F1':>5} {'winner':>7} {'pillar':>6}" + ("   vs earlier" if base else ""))
    for f in files:
        gold = json.loads(Path(f).read_text())
        r = score_conflicts(gold, subs)
        line = (f"{Path(f).name:38} {r['gold']:>3} {r['matched']:>5} {r['recall']:>6.2f} {r['precision']:>5.2f} {r['f1']:>5.2f} "
                f"{(r['resolution_accuracy'] or 0):>7.2f} {pillar(r):>6.3f}")
        if base:
            b = score_conflicts(gold, base)
            line += f"   {pillar(r) - pillar(b):+.3f} (found {r['matched'] - b['matched']:+d}, entries {r['submitted'] - b['submitted']:+d})"
        print(line)
        if a.verbose:
            for gid, found, won, topic in detail(gold, subs):
                if not found:
                    print(f"      MISSED  {gid}")
                elif not won:
                    print(f"      WINNER WRONG  {gid}  ({topic})")


if __name__ == "__main__":
    main()
