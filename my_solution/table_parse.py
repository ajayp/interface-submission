#!/usr/bin/env python3
"""
Read rate/fee tables straight from the Markdown, with no AI (experiment; NOT wired into answers or conflicts()).

Every table cell that holds a number becomes a TableCell that keeps everything the page says about it: the page, page type,
website copy, heading, caption, the "effective" note, the exact column header, the row's other cells, and the raw cell text.
Rules are used only to label what is already written:
  - unit/metric: the unit written IN the cell ("5.34% APR") wins over the column header (a calculator header says
    "Annual Percentage Yield" above APR values); every disagreement is recorded (unit_conflict).
  - period: intro ("for 1st 6 Months", "introductory") vs after the promotion ("After Promotional Period"), from header words.
  - kind: rate / money (fee, minimum, payment) / other; ranges ("12.50% to 19.50%") stay one value; "as low as" is flagged.
  - product: from a row cell that names a product, otherwise from the caption above the table, otherwise the heading.
Form tables (loan applications) are skipped by an explicit test; the reason is recorded.

Run from the repo root for a summary of all five website copies:
    python my_solution/table_parse.py            (writes results/experiments/tables/cells.jsonl and summary.json)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from facts import page_tables, table_key  # noqa: E402
from tiers import page_rank  # noqa: E402

EMPTY = {"", "—", "–", "-", "none", "n/a", "na", "--"}

# Header words -> metric. Order matters: the most specific first.
HEADER_METRICS = [
    (re.compile(r"annual percentage yield|\bapy\b", re.I), "APY"),
    (re.compile(r"annual percentage rate|\bapr\b", re.I), "APR"),
    (re.compile(r"dividend rate", re.I), "dividend rate"),
    (re.compile(r"interest rate", re.I), "interest rate"),
    (re.compile(r"\bfee", re.I), "fee"),
    (re.compile(r"payment", re.I), "payment"),
    (re.compile(r"\bpoints?\b", re.I), "points"),
    (re.compile(r"\bmin(imum)?\b|min\.", re.I), "minimum"),
    (re.compile(r"\bmax(imum)?\b|max\.", re.I), "maximum"),
    (re.compile(r"\brates?\b", re.I), "rate"),
]
CELL_UNIT_RE = re.compile(r"%\s*\**\s*(APR|APY)\b", re.I)
INTRO_RE = re.compile(r"\b(1st|first)\s+\d+\s+months?\b|\bintro(ductory)?\b|\bpromotional rate\b", re.I)
AFTER_RE = re.compile(r"\bafter\s+(the\s+)?(promotional|promo|intro)", re.I)
AS_LOW_AS_RE = re.compile(r"as low as", re.I)
NUM = r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?"
PCT_RE = re.compile(rf"({NUM})\s*%")
MONEY_RE = re.compile(rf"\$\s?({NUM})")
RANGE_RE = re.compile(rf"({NUM})\s*%?\s*(?:to|-|–)\s*({NUM})\s*%", re.I)
FOOTNOTE_RE = re.compile(r"((?:%|APR|APY))\s*\\?\*?\d{1,2}\b", re.I)   # "5.19% APR1" -> "5.19% APR", "4.00%1" -> "4.00%"

# A cell that describes a tier/term/year rather than a product
QUALIFIER_CELL_RE = re.compile(
    r"^\s*(model\s+years?\s+|\d+\s*(-|to)?\s*\d*\s*(months?|mos?\.?|years?|yrs?)\b|(19|20)\d\d|\$|up to|\d[\d,.]*\s*(\+|or less|or more)|"
    r"less than|over|under|minimum|maximum)", re.I)
TIER_CELL_RE = re.compile(r"\$\s?[\d,.]+\s*(\+|or less|or more|and (up|over|above|below))|\$\s?[\d,.]+\s*(-|–|to)\s*\$?\s?[\d,.]+"
                          r"|\b(up to|less than|over|under)\s+\$", re.I)
LABEL_HEADER_RE = re.compile(r"tier|balance$|^balance\b(?!.*(payment|with))|loan amount|amount range|program|loan type|ira type|term", re.I)
PRODUCT_HEADER_RE =re.compile(r"account|product|loan type|card|certificate|program|plan|category|type", re.I)
FORM_RE = re.compile(r"signature|for office use|applicant|co-applicant|name/address|social security|statement of financial"
                     r"|creditor|insurance company|no\. shares|address and type of property|\bassets\b|liabilities"
                     r"|date of birth|employer", re.I)


@dataclass
class TableCell:
    url: str
    page_type: str
    snapshot_id: str
    fetched_at: Optional[str]
    heading: str
    caption: str
    note: str
    effective: Optional[str]
    after: str                    # text right below the table (product names sometimes sit there: "Open my 1st Rate Checking")
    table_id: str                 # same table text = same id, across pages and copies
    row_index: int
    headers: list
    row: list                     # the raw cells of the row
    column: str                   # exact column header of this cell
    raw: str                      # exact cell text
    value: str                    # normalised: "5.34%", "5.34%-6.00%", "$2,500.00"
    kind: str                     # rate | money | other
    metric: str                   # APR / APY / dividend rate / interest rate / rate / fee / payment / minimum / maximum / other
    unit_in_cell: Optional[str]   # APR / APY when the cell itself says so
    unit_conflict: bool           # header says one rate type, cell says another
    period: Optional[str]         # intro | after_promo | None
    as_low_as: bool
    product: str
    product_source: str           # row | caption | heading
    qualifiers: dict = field(default_factory=dict)   # the row's other label cells, keyed by their exact header


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _clean(cell: str) -> str:
    c = re.sub(r"\\([*_])", r"\1", cell)
    c = re.sub(r"\*\*|__", "", c)
    return FOOTNOTE_RE.sub(r"\1", c).strip()


def _value(cell: str) -> tuple[Optional[str], str]:
    """(normalised value, kind) or (None, '') when the cell holds no number we compare."""
    c = _clean(cell)
    if c.lower().strip(" .*") in EMPTY:
        return None, ""
    m = RANGE_RE.search(c)
    if m and "%" in c:
        return f"{float(m.group(1).replace(',', '')):g}%-{float(m.group(2).replace(',', '')):g}%", "rate"
    m = PCT_RE.search(c)
    if m:
        return f"{float(m.group(1).replace(',', '')):g}%", "rate"
    m = MONEY_RE.search(c)
    if m:
        return f"${float(m.group(1).replace(',', '')):,.2f}", "money"
    return None, ""


def _header_metric(h: str) -> Optional[str]:
    for rx, name in HEADER_METRICS:
        if rx.search(h):
            return name
    return None


def form_reason(headers: list[str], rows: list[list[str]]) -> Optional[str]:
    """Why a table is a form (to skip), or None. Explicit and listed, so skipped tables can be reviewed."""
    text = " ".join(headers + [c for r in rows for c in r])
    m = FORM_RE.search(text)
    if m:
        return f"form word: {m.group(0)}"
    cells = [c for r in rows for c in r]
    if cells and sum(1 for c in cells if not c.strip()) / len(cells) > 0.6:
        return "mostly empty cells"
    return None


SEPARATOR_RE = re.compile(r"^\|?\s*:?-{3,}")


def split_tables(table: str) -> list[str]:
    """Two tables written back to back (no blank line) arrive as one block: a header line followed by a |---| line starts a new one."""
    lines = [l for l in table.split("\n") if l.strip().startswith("|")]
    starts = [i for i in range(len(lines) - 1) if SEPARATOR_RE.match(lines[i + 1].strip()) and not SEPARATOR_RE.match(lines[i].strip())]
    if len(starts) <= 1:
        return ["\n".join(lines)]
    starts.append(len(lines))
    return ["\n".join(lines[a:b]) for a, b in zip(starts, starts[1:]) if b - a >= 3]


def parse_table(t: dict, snapshot_id: str, fetched_at: Optional[str] = None) -> tuple[list[TableCell], Optional[str]]:
    """All numeric cells of one table block (from facts.page_tables), and the form reason if it was skipped.
    A block holding several back-to-back tables is read table by table."""
    parts = split_tables(t["table"])
    if len(parts) > 1:
        cells, reasons = [], []
        for k, part in enumerate(parts):
            got, reason = parse_table({**t, "table": part}, snapshot_id, fetched_at)
            cells.extend(got)
            if reason:
                reasons.append(reason)
        return cells, (reasons[0] if reasons and not cells else None)
    lines = [l for l in t["table"].split("\n") if l.strip().startswith("|")]
    headers = _cells(lines[0])
    rows = [_cells(l) for l in lines[1:] if not re.match(r"^\|?\s*:?-{3,}", l.strip())]
    rows = [r for r in rows if r != headers]                       # repeated header row
    reason = form_reason(headers, rows)
    if reason:
        return [], reason
    tid = table_key(t)[:12]
    # value columns: a column where most filled cells are numbers with % or $
    ncol = len(headers)
    is_value_col = []
    for j in range(ncol):
        col = [r[j] for r in rows if j < len(r) and _clean(r[j]).lower().strip(" .*") not in EMPTY]
        vals = [_value(c) for c in col]
        rates = sum(1 for v, k in vals if k == "rate")
        money = sum(1 for v, k in vals if k == "money")
        tierlike = sum(1 for c in col if TIER_CELL_RE.search(_clean(c)))
        if col and rates / len(col) >= 0.5:
            is_value_col.append(True)
        elif col and money / len(col) >= 0.5:
            # "$25,000+", "$300,000 or less", "$10,000 – $20,000" under "Balance Tier"/"Loan Amount" describe the row (a tier), not a value
            is_value_col.append(not (LABEL_HEADER_RE.search(headers[j]) or tierlike / len(col) >= 0.5))
        else:
            is_value_col.append(False)
    out = []
    for i, r in enumerate(rows):
        r = r + [""] * (ncol - len(r))
        labels = {headers[j] or f"col{j + 1}": _clean(r[j]) for j in range(ncol) if not is_value_col[j] and r[j].strip()}
        product, source = "", ""
        for j in range(ncol):
            if is_value_col[j] or not r[j].strip():
                continue
            cell = _clean(r[j])
            if not QUALIFIER_CELL_RE.search(cell) and (PRODUCT_HEADER_RE.search(headers[j]) or j == 0):
                product, source = cell, "row"
                break
        if not product:
            product, source = (t["caption"], "caption") if t["caption"] and t["caption"] != t["heading"] else (t["heading"], "heading")
        qualifiers = {k: v for k, v in labels.items() if v != product}
        for j in range(ncol):
            if not is_value_col[j]:
                continue
            value, kind = _value(r[j])
            if value is None:
                continue
            col = headers[j]
            hm = _header_metric(col)
            cu = CELL_UNIT_RE.search(_clean(r[j]))
            unit = cu.group(1).upper() if cu else None
            rate_types = {"APR", "APY", "dividend rate", "interest rate", "rate"}
            metric = unit or hm or ("rate" if kind == "rate" else "other")
            conflict = bool(unit and hm in rate_types and hm != "rate" and hm != unit)
            if hm == "points":
                metric = "points"
            if kind == "money" and metric in rate_types:
                metric = hm if hm and hm not in rate_types else "other"
            period = "after_promo" if AFTER_RE.search(col) else ("intro" if INTRO_RE.search(col) else None)
            out.append(TableCell(
                url=t["url"], page_type=page_rank(t["url"]), snapshot_id=snapshot_id, fetched_at=fetched_at,
                heading=t["heading"], caption=t["caption"], note=t["note"], effective=t["effective"], after=t.get("after", ""), table_id=tid,
                row_index=i, headers=headers, row=r, column=col, raw=r[j], value=value, kind=kind, metric=metric,
                unit_in_cell=unit, unit_conflict=conflict, period=period,
                as_low_as=bool(AS_LOW_AS_RE.search(col) or AS_LOW_AS_RE.search(r[j])),
                product=product, product_source=source, qualifiers=qualifiers))
    return out, None


def parse_pages(pages, snapshot_id: str) -> list[TableCell]:
    """All numeric cells of a website copy given as page objects (url, title, markdown, fetched_at), as ingest() receives them."""
    cells = []
    for p in pages:
        for t in page_tables(p.url, p.title or "", p.markdown):
            got, _ = parse_table(t, snapshot_id, getattr(p, "fetched_at", None))
            cells.extend(got)
    return cells


def parse_snapshot(snapshot_dir: Path) -> tuple[list[TableCell], list[dict]]:
    """All numeric cells of one website copy, plus the list of skipped (form) tables."""
    m = json.loads((snapshot_dir / "manifest.json").read_text())
    cells, skipped = [], []
    for p in m["pages"]:
        md = (snapshot_dir / p["file"]).read_text(encoding="utf-8")
        for t in page_tables(p["url"], p.get("title", ""), md):
            got, reason = parse_table(t, m["snapshot_id"], p.get("fetched_at", m["taken_on"]))
            if reason:
                skipped.append({"url": p["url"], "caption": t["caption"], "reason": reason})
            cells.extend(got)
    return cells, skipped


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "results" / "experiments" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {}
    with (out_dir / "cells.jsonl").open("w") as f:
        for d in sorted((root / "snapshots").glob("0*")):
            cells, skipped = parse_snapshot(d)
            for c in cells:
                f.write(json.dumps(asdict(c)) + "\n")
            summary[d.name] = {
                "cells": len(cells),
                "tables": len({(c.url, c.table_id) for c in cells}),
                "distinct_tables": len({c.table_id for c in cells}),
                "skipped_form_tables": len(skipped),
                "skip_reasons": Counter(s["reason"] for s in skipped).most_common(),
                "by_kind": Counter(c.kind for c in cells).most_common(),
                "by_metric": Counter(c.metric for c in cells).most_common(),
                "by_period": Counter(str(c.period) for c in cells).most_common(),
                "product_source": Counter(c.product_source for c in cells).most_common(),
                "unit_in_cell": sum(1 for c in cells if c.unit_in_cell),
                "unit_conflicts": sorted({(c.url, c.column, c.raw) for c in cells if c.unit_conflict}),
                "ranges": sum(1 for c in cells if "-" in c.value and c.kind == "rate"),
                "as_low_as": sum(1 for c in cells if c.as_low_as),
            }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary["05_2026-09-28_latest"], indent=1))
