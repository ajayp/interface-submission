"""
Count facts about the credit union itself (branches, employees, members, assets, counties served) for conflicts().

These numbers sit in "about the credit union" boilerplate at the end of news releases and blog posts ("It has over 600 employees and
23 branch office locations", "membership has grown to more than 178,000 with assets exceeding $3.5 billion"). Every release keeps the
count of its own day, so the site shows many values for one measure. Extraction is by fixed sentence patterns (no AI): only
statements about the whole credit union are taken, never sub-counts ("9 branches in Dubuque") or other institutions ("100,000
branches across the U.S."). Current value = the statement on the most recently published page (then the latest fetch).
Scenario 34 in tasks/conflict_scenarios.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from chunker import published_date
from tiers import page_rank

NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
QUANT = r"(?:over|more than|nearly|almost|about|approximately)\s+"
PATTERNS = {
    "branches": [
        re.compile(rf"\bit has\s+(?:{QUANT})?[\d,]+\s+employees and\s+{NUM}\s+branch office locations", re.I),
        re.compile(rf"\bdupaco(?:’s|'s)\s+{NUM}\s+(?:full-service\s+)?branches\b", re.I),
        re.compile(rf"\bdupaco (?:now )?operates\s+{NUM}\s+branches\b", re.I),
    ],
    "employees": [
        re.compile(rf"\bit has\s+(?:{QUANT})?{NUM}\s+employees and\b", re.I),
        re.compile(rf"\bdupaco and its\s+(?:{QUANT})?{NUM}\s+employees\b", re.I),
        re.compile(rf"\bthe credit union currently employs\s+(?:{QUANT})?{NUM}\s+employees\b", re.I),
    ],
    "members": [
        re.compile(rf"\bmembership (?:has grown to|totals)\s+(?:{QUANT})?{NUM}\b", re.I),
        re.compile(rf"\bdupaco and its\s+(?:{QUANT})?[\d,]+\s+employees are proud to serve\s+(?:{QUANT})?{NUM}\s+members\b", re.I),
        re.compile(rf"\bdupaco now operates\s+\d+\s+branches and serves\s+(?:{QUANT})?{NUM}\s+members\b", re.I),
    ],
    "counties": [
        re.compile(rf"\bdupaco serves (?:residents|members) in\s+{NUM}\s+counties\b", re.I),
    ],
    "assets": [
        re.compile(rf"\bmembership (?:has grown to|totals)\s+(?:{QUANT})?[\d,]+\s+with assets exceeding\s+\$\s?{NUM}\s*billion", re.I),
    ],
}
TOPIC = {"branches": "Number of Dupaco branch locations", "employees": "Number of Dupaco employees",
         "members": "Number of Dupaco members (membership)", "assets": "Dupaco total assets",
         "counties": "Number of counties Dupaco serves"}
UNIT = {"branches": "{} branches", "employees": "{} employees", "members": "{} members", "assets": "${} billion",
        "counties": "{} counties"}


@dataclass
class CountFact:
    measure: str
    value: str
    url: str
    page_type: str
    published: Optional[str]
    fetched_at: Optional[str]
    sentence: str


def count_facts(pages) -> list[CountFact]:
    out = []
    for p in pages:
        md = p.markdown
        flat = re.sub(r"\s+", " ", md)
        pub = published_date(p.url, md)
        for measure, rxs in PATTERNS.items():
            for rx in rxs:
                for m in rx.finditer(flat):
                    v = m.group(1)
                    if measure == "branches" and int(v.replace(",", "")) > 200:
                        continue
                    out.append(CountFact(measure, v, p.url, page_rank(p.url), pub, getattr(p, "fetched_at", None),
                                         flat[max(0, m.start() - 40):m.end() + 20]))
    return out


def latest(facts: list[CountFact]) -> CountFact:
    """Most recently published statement. Undated pages (e.g. an old staff bio) rank below every dated one: a fetch date says when
    we saw the page, not when the number was true."""
    return max(facts, key=lambda f: (f.published is not None, f.published or "", f.fetched_at or ""))


def label(measure: str, value: str) -> str:
    """The value as the site words it plus the plain form: "22 branches (22 branch office locations)"."""
    if measure == "branches":
        return f"{value} branches ({value} branch office locations)"
    return UNIT[measure].format(value)


# ---------------------------------------------------------------- answering count questions (MY_SOLUTION_COUNT_ANSWERS)
ASK = {
    "branches": re.compile(r"\bhow many\b[^?]*\b(branch(es)?|branch (office )?locations|locations|offices)\b|\bnumber of (branch(es)?|branch "
                           r"(office )?locations|locations|offices)\b", re.I),
    "employees": re.compile(r"\bhow many\b[^?]*\b(employees|people work|staff|team members|workers)\b|\bnumber of (employees|staff)\b", re.I),
    "members": re.compile(r"\bhow many\b[^?]*\bmembers\b|\bnumber of members\b|\bmembership (size|count)\b", re.I),
    "assets": re.compile(r"\b(total |in )?assets\b|\basset size\b", re.I),
}
# A place, a year or a sub-group means a different question ("branches in Cedar Rapids", "members in 2023", "ATMs", "board members").
SCOPE_RE = re.compile(r"\b(in|near|around|within|across)\s+(?!total\b)(?!(january|february|march|april|may|june|july|august|september|"
                      r"october|november|december)\b)[A-Za-z]|\blast year\b|\bATMs?\b|\bboard\b|"
                      r"\bvolunteer|\bpromoted\b|\bused\b|\bopen(ed)?\b|\bnew\b|\bclos", re.I)
QUANT_RE = re.compile(r"\b(over|more than|nearly|almost|about|approximately|exceeding)\s+\$?\s?[\d,.]+\s*(billion)?\s*(employees|branch|$|with|members)?", re.I)


YEAR_RE = re.compile(r"\b(19|20)\d\d\b")


def count_question(question: str, website_date: Optional[str] = None) -> Optional[str]:
    """The measure a question asks about Dupaco as a whole, or None (sub-scopes and other counts go the normal way).
    A year is allowed only as a website date ("as of May 2026": the copy of the site from then); otherwise ("members in 2023")
    it asks about history, which the newest statement does not answer."""
    if SCOPE_RE.search(question) or (YEAR_RE.search(question) and not website_date):
        return None
    for measure, rx in ASK.items():
        if rx.search(question):
            return measure
    return None


def answer_text(f: CountFact) -> str:
    """One plain sentence with the value and where it comes from."""
    m = QUANT_RE.search(f.sentence)
    q = (m.group(1).lower() + " ") if m and f.measure != "branches" else ""
    q = "more than " if q == "exceeding " else q
    when = f" (published {f.published})" if f.published else ""
    what = {"branches": f"{f.value} branch office locations", "employees": f"{q}{f.value} employees",
            "members": f"{q}{f.value} members", "assets": f"{q}${f.value} billion in assets",
            "counties": f"{f.value} counties"}[f.measure]
    return f"Dupaco has {what}, according to its most recent news release or article on the website{when}."
