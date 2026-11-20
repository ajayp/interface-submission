#!/usr/bin/env python3
"""Table of the retrieval-only screening: per arm, recall by path, questions gained / lost against base, and characters sent.

    python eval_report/tools/rc_table.py results/rc [--csv eval_report/retrieval_screen.csv] [--md]
"""
import argparse
import csv
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", type=Path)
    ap.add_argument("--csv")
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args()
    cfg = json.loads((Path(__file__).resolve().parents[1] / "configs" / "screen.json").read_text())
    arms = [x for x in cfg["arms"] if (a.dir / f"{x}.json").exists()]
    data = {x: {(r["set"], r["id"]): r for r in json.loads((a.dir / f"{x}.json").read_text())} for x in arms}
    base = data["base"]
    out = []
    for arm in arms:
        d = data[arm]
        row = {"arm": arm}
        for p in ("text", "facts", "history"):
            keys = [k for k, r in base.items() if r["path"] == p]
            row[f"{p}_n"] = len(keys)
            row[f"{p}_recall"] = round(sum(bool(d[k]["hit"]) for k in keys) / len(keys), 4) if keys else None
            row[f"{p}_chars"] = round(sum(d[k]["chars"] for k in keys) / len(keys)) if keys else None
            row[f"{p}_pieces"] = round(sum(d[k]["pieces"] for k in keys) / len(keys), 2) if keys else None
        tk = [k for k, r in base.items() if r["path"] in ("text", "facts", "history")]
        row["gained"] = " ".join(f"{k[1]}" for k in tk if d[k]["hit"] and not base[k]["hit"])
        row["lost"] = " ".join(f"{k[1]}" for k in tk if base[k]["hit"] and not d[k]["hit"])
        row["text_chars_vs_base"] = f"{row['text_chars'] / base_chars(base, 'text') - 1:+.1%}"
        # required strings found (finer than all-or-nothing recall)
        row["strings_found"] = sum(sum(d[k]["found"]) for k in tk)
        # rank: mean shortest covering prefix on text-path questions covered in this arm (lower = the evidence comes earlier)
        cov = [d[k].get("cover") for k in tk if base[k]["path"] == "text" and d[k].get("cover")]
        row["text_cover_mean"] = round(sum(cov) / len(cov), 2) if cov else None
        row["text_cover_le3"] = sum(1 for c in cov if c <= 3)
        out.append(row)
    cols = ["arm", "text_recall", "text_chars", "text_chars_vs_base", "text_pieces", "text_cover_mean", "text_cover_le3",
            "facts_recall", "facts_chars", "history_recall", "strings_found", "gained", "lost"]
    if a.md:
        print("| " + " | ".join(cols) + " |")
        print("|" + "---|" * len(cols))
        for r in out:
            print("| " + " | ".join(str(r[c]) for c in cols) + " |")
    else:
        print(f"{'arm':16} {'txtRec':>6} {'txtChars':>8} {'vsBase':>7} {'pcs':>5} {'cover':>5} {'c<=3':>4} {'factRec':>7} {'factCh':>6} {'hist':>5} {'strs':>5}  gained / lost")
        for r in out:
            print(f"{r['arm']:16} {r['text_recall']:6.3f} {r['text_chars']:8d} {r['text_chars_vs_base']:>7} {r['text_pieces']:5.1f} "
                  f"{str(r['text_cover_mean']):>5} {r['text_cover_le3']:4d} {r['facts_recall']:7.3f} {r['facts_chars']:6d} {r['history_recall']:5.2f} {r['strings_found']:5d}  "
                  f"+[{r['gained']}] -[{r['lost']}]")
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0]))
            w.writeheader(); w.writerows(out)


def base_chars(base, p):
    keys = [k for k, r in base.items() if r["path"] == p]
    return sum(base[k]["chars"] for k in keys) / len(keys)


if __name__ == "__main__":
    main()
