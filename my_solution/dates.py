"""Work out which date a question is asking about: the `as_of` argument, or a date in the text."""
from __future__ import annotations

import calendar
import datetime
import os
import re
from typing import Optional

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9
_MONTH = "(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + ")"
MONTH_YEAR_RE = re.compile(r"\b" + _MONTH + r"\.?\s+(\d{1,2}(?:st|nd|rd|th)?,?\s*)?(20\d\d)\b", re.I)
ISO_RE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
# US-style numeric dates: 5/15/2026, 05/15/26. A year is required, so "7/1 adjustable-rate" is not a date.
NUMERIC_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d\d|\d\d)\b")
# "before September 2026" asks about the website up to the day before; "early / mid June 2026" about that part of the month.
BEFORE_RE = re.compile(r"\b(before|prior to|until|up to)\s+(the\s+)?(start of\s+|beginning of\s+)?$", re.I)
PART_RE = re.compile(r"\b(early|mid|middle of|late|end of)[\s-]+(in\s+)?$", re.I)
PART_DAY = {"early": 10, "mid": 15, "middle of": 15}   # late / end of = the last day of the month


# A month with no year ("what was the rate in May?") means the most recent such month that is not after the newest website copy: every
# copy is from one stretch of time, so there is only one such month. MY_SOLUTION_YEARLESS_DATE=0 turns this off. REFERENCE (the newest
# copy's date) is set by solution.py when the copies are loaded.
YEARLESS = os.getenv("MY_SOLUTION_YEARLESS_DATE", "1") == "1"
REFERENCE: Optional[str] = None
_FULL_MONTHS = "(" + "|".join(sorted({m.lower() for m in calendar.month_name if m} | {"sept"}, key=len, reverse=True)) + ")"
YEARLESS_RE = re.compile(
    r"\b(?:as of|back in|in|during|on|for|from|before|prior to|until|early|mid|late|end of)[\s-]+(?:the\s+)?(?:(?:early|mid|middle of|late|end of)[\s-]+)?"
    + _FULL_MONTHS + r"\b(?!\s*,?\s*(?:\d{1,2}(?:st|nd|rd|th)?,?\s*)?(?:20)?\d\d\b)", re.I)


def yearless_month(question: str) -> Optional[tuple]:
    """(match, month number) for a month named without a year, else None. Only after a date word ("in May", "as of March"), so the
    verb or modal ("May I ...") is not read as a month."""
    if not YEARLESS:
        return None
    m = YEARLESS_RE.search(question)
    return (m, MONTHS[m.group(1).lower()]) if m else None


def _yearless_date(question: str) -> Optional[str]:
    hit = yearless_month(question)
    if not hit or not REFERENCE:
        return None
    m, mo = hit
    ref = datetime.date.fromisoformat(REFERENCE)
    year = ref.year if mo <= ref.month else ref.year - 1
    part = PART_RE.search(question[:m.start(1)])
    day = PART_DAY.get(part.group(1).lower()) if part else None
    return _iso(year, mo, day or calendar.monthrange(year, mo)[1])


def _iso(year: int, month: int, day: int) -> Optional[str]:
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


def _day_before(iso: str) -> str:
    return (datetime.date.fromisoformat(iso) - datetime.timedelta(days=1)).isoformat()


def question_date(question: str) -> Optional[str]:
    """'as of May 2026' -> '2026-05-31'; 'May 3, 2026' -> '2026-05-03'; '5/15/2026' -> '2026-05-15'; ISO dates pass through;
    'before September 2026' -> '2026-08-31'; 'mid-May 2026' -> '2026-05-15'; 'early June 2026' -> '2026-06-10'."""
    m = ISO_RE.search(question)
    if m:
        date = _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        first = date
    else:
        date = first = None
        m = NUMERIC_RE.search(question)
        if m:
            year = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
            date = first = _iso(year, int(m.group(1)), int(m.group(2)))
        if date is None:
            m = MONTH_YEAR_RE.search(question)
            if m:
                mo, year = MONTHS[m.group(1).lower()], int(m.group(3))
                if m.group(2):
                    date = first = _iso(year, mo, int(re.match(r"\d+", m.group(2)).group()))
                else:
                    part = PART_RE.search(question[:m.start()])
                    day = PART_DAY.get(part.group(1).lower()) if part else None
                    date = _iso(year, mo, day or calendar.monthrange(year, mo)[1])
                    first = _iso(year, mo, 1)   # "before <month>" = before the month starts
    if date is None and m is None:
        return _yearless_date(question)
    if date is None or m is None:
        return date
    if BEFORE_RE.search(question[:m.start()]):
        return _day_before(first)
    return date


def target_date(question: str, as_of: Optional[str]) -> Optional[str]:
    return (as_of[:10] if as_of else None) or question_date(question)


def asks_before_date(question: str) -> bool:
    """True for "before / prior to / until <date>": a question about one point in time (the day before), not about a change."""
    for rx in (ISO_RE, NUMERIC_RE, MONTH_YEAR_RE):
        m = rx.search(question)
        if m:
            return bool(BEFORE_RE.search(question[:m.start()]))
    return False


def describe(question: str, iso: str, as_of: bool = False, assumed_year: bool = False) -> str:
    """The date as the member wrote it, for the answer: 'June 20, 2026' for a day, 'June 2026' for a month, the ISO date for as_of."""
    d = datetime.date.fromisoformat(iso)
    month = calendar.month_name[d.month]
    if as_of:
        return f"{month} {d.day}, {d.year}"
    if ISO_RE.search(question) or NUMERIC_RE.search(question):
        return f"{month} {d.day}, {d.year}"
    m = MONTH_YEAR_RE.search(question)
    if m and m.group(2):
        return f"{month} {d.day}, {d.year}"
    hit = yearless_month(question)
    if hit:
        part = PART_RE.search(question[:hit[0].start(1)])
        return (part.group(1).lower() + " " if part else "") + f"{month} {d.year}"
    part = PART_RE.search(question[:m.start()]) if m else None
    return (part.group(1).lower() + " " if part else "") + f"{month} {d.year}"
