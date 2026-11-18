#!/usr/bin/env python3
"""
POC: "same fact?" for table cells read by table_parse.py (experiment; not wired into answers or conflicts()).

Pipeline, following entity-matching practice (cheap rules shortlist candidate pairs = "blocking"; a matcher then decides):
  1. normalise each rate cell into comparable parts WITHOUT looking at its number: rate type, period (intro/after promo),
     term in months, balance/loan-amount tier, model-year range, product words;
  2. blocking: candidate pairs = different tables, same rate type and period, same term, same tier, overlapping model years,
     different numbers. The product name is NOT used here, so renamed products still become candidates;
  3. matchers (POC 2) decide which candidates are the same fact: rules / rules + AI yes-no / Google-style voting.
Scenario list: tasks/conflict_scenarios.md
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
from types import SimpleNamespace
from typing import Optional

RATE_METRICS = {"APR": "APR", "APY": "APY", "dividend rate": "dividend rate", "interest rate": "rate", "rate": "rate"}
TERM_RE = re.compile(r"(\d+)\s*-?\s*(months?|mos?\b|mo\.|years?|yrs?)", re.I)
YEARS_RE = re.compile(r"\b((?:19|20)\d\d)\s*(?:[-–]\s*((?:19|20)?\d\d))?\b")
MONEY = r"\$\s?([\d,]+(?:\.\d+)?)"
NOISE_QUALIFIERS = re.compile(r"^(points|min\.?|max\.?|min\. to|minimum|maximum)", re.I)


def _money(s: str) -> float:
    return float(s.replace(",", ""))


def term_months(text: str) -> Optional[int]:
    m = TERM_RE.search(text)
    if not m:
        return None
    n = int(m.group(1))
    return n * 12 if m.group(2).lower().startswith(("y",)) else n


def tier(text: str) -> Optional[tuple]:
    """Balance or loan-amount band as (low, high); None when the text names no band. 'or less' -> (0, x); '+' -> (x, inf)."""
    t = text.replace("–", "-")
    m = re.search(MONEY + r"\s*(?:-|to)\s*\$?\s?([\d,]+(?:\.\d+)?)", t)
    if m:
        return (_money(m.group(1)), _money(m.group(2)))
    m = re.search(MONEY + r"\s*(\+|or more|and (?:up|over|above))", t, re.I)
    if m:
        return (_money(m.group(1)), float("inf"))
    m = re.search(MONEY + r"\s*(or less|and (?:under|below))", t, re.I) or re.search(r"(?:up to|less than|under)\s+" + MONEY, t, re.I)
    if m:
        return (0.0, _money(m.group(1)))
    return None


def model_years(text: str) -> Optional[tuple]:
    if not re.search(r"model|year", text, re.I):
        return None
    m = YEARS_RE.search(text)
    if not m:
        return None
    a = int(m.group(1))
    b = m.group(2)
    if b is None:
        lo, hi = (0, a) if re.search(r"older|and before|or older", text, re.I) else (a, a)
        return (lo, hi)
    b = int(b) if len(b) == 4 else int(str(a)[:2] + b)
    return (min(a, b), max(a, b))


@dataclass
class RateFact:
    """One rate cell, normalised. `parts` is what blocking compares; product words are kept for the matchers."""
    url: str
    page_type: str
    table_id: str
    effective: Optional[str]
    fetched_at: Optional[str]
    product: str
    qualifiers: dict
    column: str
    raw: str
    value: str
    metric: str
    period: Optional[str]
    term: Optional[int]
    tier: Optional[tuple]
    years: Optional[tuple]
    as_low_as: bool
    heading: str
    caption: str
    after: str = ""
    headers: tuple = ()
    row_cells: tuple = ()

    @property
    def variant(self) -> str:
        """The row's own words once term, tier, model years and numbers are removed ("10 Month Fixed Jumbo Special" ->
        "fixed jumbo special"): what separates jumbo from regular, special from standard, within one product line."""
        q = " ".join(v for k, v in self.qualifiers.items() if not NOISE_QUALIFIERS.search(k))
        q = TERM_RE.sub(" ", q)
        q = re.sub(r"\$\s?[\d,.]+|\b(19|20)\d\d\b|[\d,.]+|\bmodel years?\b|\byears?\b|\bor (less|more)\b|\(and older\)|older", " ", q, flags=re.I)
        return " ".join(re.findall(r"[a-z]+", q.lower()))

    @property
    def label(self) -> str:
        q = "; ".join(f"{k}: {v}" for k, v in self.qualifiers.items() if not NOISE_QUALIFIERS.search(k))
        return f"{self.product} | {q} | {self.column}"


def to_fact(c: dict) -> Optional[RateFact]:
    if c["kind"] != "rate" or c["metric"] not in RATE_METRICS:
        return None
    quals = {k: v for k, v in c["qualifiers"].items() if not NOISE_QUALIFIERS.search(k)}
    text = " ".join([c["product"], *quals.values()])
    return RateFact(url=c["url"], page_type=c["page_type"], table_id=c["table_id"], effective=c["effective"],
                    fetched_at=c["fetched_at"], product=c["product"], qualifiers=c["qualifiers"], column=c["column"],
                    raw=c["raw"], value=c["value"], metric=RATE_METRICS[c["metric"]], period=c["period"],
                    term=term_months(text), tier=tier(text), years=model_years(text), as_low_as=c["as_low_as"],
                    heading=c["heading"], caption=c["caption"], after=c.get("after", ""),
                    headers=tuple(c["headers"]), row_cells=tuple(c["row"]))


def load_facts(snapshot_id: str, cells_path: Path) -> list[RateFact]:
    out = []
    for line in cells_path.read_text().splitlines():
        c = json.loads(line)
        if c["snapshot_id"] == snapshot_id:
            f = to_fact(c)
            if f:
                out.append(f)
    return out


def _years_overlap(a: Optional[tuple], b: Optional[tuple]) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return min(a[1], b[1]) >= max(a[0], b[0])


# A rate sentence that says nothing about a term or an introductory period is not a different fact from a sentence of the same
# product that does: the reader cannot see what the page leaves out. With this switch on, two SENTENCE facts (never tables) with the
# same rate type and tier still pair when one of them states no term and no intro. MY_SOLUTION_SENTENCE_UNSTATED=0 restores the
# strict rule. Measured on the hand-made lists (tasks/andretodo.md).
SENTENCE_UNSTATED = os.getenv("MY_SOLUTION_SENTENCE_UNSTATED", "1") == "1"


def _unstated(f: RateFact) -> bool:
    return f.period is None and f.term is None


def blocked(a: RateFact, b: RateFact) -> bool:
    """Could a and b be the same fact? Uses no numbers and no product name."""
    same_period_term = a.period == b.period and a.term == b.term
    if (SENTENCE_UNSTATED and not same_period_term and a.table_id.startswith("s:") and b.table_id.startswith("s:")
            and (_unstated(a) or _unstated(b))):
        same_period_term = True
    return (a.table_id != b.table_id and a.metric == b.metric and same_period_term
            and a.tier == b.tier and _years_overlap(a.years, b.years))


def _best_band(years: tuple, bands: set) -> Optional[tuple]:
    """The band in `bands` that overlaps `years` most (a stale table's 2023-26 is the current 2024-27, not 2021-23)."""
    best = max(bands, key=lambda b: (min(years[1], b[1]) - max(years[0], b[0]), -abs(b[0] - years[0])), default=None)
    return best if best is not None and min(years[1], best[1]) >= max(years[0], best[0]) else None


def candidate_pairs(facts: list[RateFact]) -> list[tuple[RateFact, RateFact]]:
    """Distinct candidate pairs with different numbers. Copies of the same table on several pages collapse to one
    (pair kept once per distinct (label, value) on each side, with every page listed by the caller)."""
    bands: dict[str, set] = {}
    for f in facts:
        if f.years:
            bands.setdefault(f.table_id, set()).add(f.years)
    seen, out = set(), []
    for i, a in enumerate(facts):
        for b in facts[i + 1:]:
            if a.value == b.value or not blocked(a, b):
                continue
            if a.years and b.years and (_best_band(a.years, bands[b.table_id]) != b.years
                                        or _best_band(b.years, bands[a.table_id]) != a.years):
                continue
            ka, kb = (a.label, a.value), (b.label, b.value)
            key = tuple(sorted([ka, kb]))
            if key in seen:
                continue
            seen.add(key)
            out.append((a, b))
    return out


# ---------------------------------------------------------------- matching and winner (moved from conflict_poc.py)
RANK = {"rate_sheet": 0, "product": 1, "promo": 2, "secondary": 3}


def basic(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r"(?<=\d),(?=\d{3})", "", n)          # $200,000 -> $200000
    return re.sub(r"\s+", " ", n)


def winner_tiers(occ: list[RateFact]) -> RateFact:
    neg = lambda d: "".join(chr(255 - ord(ch)) for ch in d) if d else "\xff"
    return min(occ, key=lambda f: (RANK[f.page_type], neg(f.effective), neg((f.fetched_at or "")[:10])))


EXCLUSIVE = ("business", "purchase", "refinance", "roth", "traditional", "ira", "jumbo", "special", "atv", "snowmobile",
             "boat", "rv", "health", "heloc", "visa", "platinum", "rewards", "investor", "achieve", "you name it", "high-yield",
             "launchpad", "share", "checking", "savings", "money market", "certificate", "1st rate", "free", "kids",
             "holiday", "home equity", "personal", "auto", "motorcycle", "standard", "introductory", "balance transfer")
GENERIC = {"loan", "loans", "rate", "rates", "account", "accounts", "the", "and", "&", "for", "of", "program"}
OPEN_MY_RE = re.compile(r"open my ([a-z0-9' -]+?)(?: account)?(?:\]|\(|$)", re.I)


def product_name(f: RateFact) -> str:
    """The product line, or the 'Open my <product>' link below the table when the line above is not a name."""
    p = f.product.strip()
    if p.startswith(("-", "*")) or len(p.split()) > 8 or p.endswith((":", "?")):
        m = OPEN_MY_RE.search(f.after)
        if m:
            return m.group(1).strip()
    return p


def words(name: str) -> tuple[set, set]:
    n = basic(name)
    excl = {w for w in EXCLUSIVE if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", n)}
    rest = set(re.findall(r"[a-z0-9$.]+", n)) - GENERIC - {t for w in excl for t in w.split()}
    return excl, rest


def same_rules(a: RateFact, b: RateFact) -> bool:
    if words(a.variant)[0] != words(b.variant)[0]:      # jumbo vs regular, special vs standard within one table
        return False
    ea, ra = words(product_name(a))
    eb, rb = words(product_name(b))
    if ea != eb:
        # one side may carry an extra non-distinguishing word ("Auto & Motorcycle" vs "Auto"): allow only motorcycle/auto pairs
        # where one set contains the other and the extra words are not business/IRA/purchase/refinance/jumbo/special markers
        hard = {"business", "purchase", "refinance", "roth", "traditional", "ira", "jumbo", "special", "atv", "snowmobile",
                "boat", "rv", "health", "heloc", "introductory", "balance transfer", "standard", "rewards", "platinum"}
        extra = (ea ^ eb)
        category = {"savings", "checking", "money market", "certificate", "share"}
        smaller = ea if len(ea) <= len(eb) else eb
        if not (ea <= eb or eb <= ea) or extra & hard or not (ea & eb) or not (smaller - category):
            return False      # a bare category word ("savings") cannot identify a named product ("Launchpad Savings")
    return not ra or not rb or ra <= rb or rb <= ra


def conflicts_from(facts, pairs, same, winner="tiers", trust=None):
    parent = {id(f): id(f) for f in facts}
    byid = {id(f): f for f in facts}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    # the same row copied onto several pages (same product, row, rate type and number) is one fact: join the copies first, so the
    # rate sheet's copy and every page showing a value stay in the group (candidate_pairs keeps one copy of each)
    first: dict = {}
    for f in facts:
        k = (basic(f.product), f.variant, f.metric, f.period, f.term, f.tier, f.years, f.value)
        if k in first:
            parent[find(id(f))] = find(first[k])
        else:
            first[k] = id(f)
    for a, b in pairs:
        if same(a, b):
            parent[find(id(a))] = find(id(b))
    comp = defaultdict(list)
    for f in facts:
        comp[find(id(f))].append(f)
    out = []
    for occ in comp.values():
        vals = sorted({f.value for f in occ})
        if len(vals) < 2:
            continue
        w = winner_tiers(occ).value if winner == "tiers" else winner_vote(occ, trust or {})
        out.append(SimpleNamespace(topic=f"{occ[0].product} {occ[0].label}", values=vals, resolution=w, occ=occ))
    return out
