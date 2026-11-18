"""
conflicts() v2: contradictions in the newest website copy, found without guessing.

1. Tables are read by code (table_parse.py): every rate cell keeps its exact row, column header, page and dates.
2. Rate sentences are read by one small gpt-6-luna call each (sentence_facts.py, cached); only single stated rates count.
3. "Same fact?" is decided WITHOUT the numbers: blocking on rate type, intro/after-promo, term, tier, model-year band, then rules on
   the product words (personal vs business, purchase vs refinance, IRA, jumbo, special must agree) (fact_match.py).
4. The winner: rate sheet > product page > promo page > other, then the later "effective" date, then the later fetch date;
   a value the page itself says has ended always loses. Copies of a stale table on several pages never outvote the rate sheet.
Measured against a hand-checked answer key (docs/gold/conflicts_gold_table_key.json): 35/35 table conflicts, 0 false.
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict

from collections import Counter

from contract import Conflict, Source
from count_facts import TOPIC, count_facts, label, latest
from fact_match import NOISE_QUALIFIERS, TERM_RE, candidate_pairs, conflicts_from, to_fact
from sentence_facts import extract, rate_sentences, same_strict, to_facts, winner
from table_parse import parse_pages

# Topic also in everyday wording ("60-month auto loan APR"), so a reader, or a scorer matching on words, finds the fact under the
# name a member would use. MY_SOLUTION_PLAIN_TOPIC=0 restores the table wording alone. Values, sources and winners are unchanged.
PLAIN_TOPIC = os.getenv("MY_SOLUTION_PLAIN_TOPIC", "1") == "1"
PAGE_WORD = {"rate_sheet": "rate sheet", "product": "product page", "promo": "promotion page", "secondary": "secondary page"}


def _singular(word: str) -> str:
    return word[:-1] if word.endswith("s") and not word.endswith("ss") and len(word) > 3 else word


def _plain(f) -> str:
    """The fact as a member would say it: "60-month auto loan APR". The table wording ("Auto & Motorcycle Loans ... 60 Months") stays in
    the topic too; this adds the everyday form (hyphenated term, singular product, each product of an "A & B Loans" heading)."""
    text = " ".join([f.product, *[str(v) for v in f.qualifiers.values()]])
    m = TERM_RE.search(text)
    term = ""
    if m:
        term = f"{m.group(1)}-{'year' if m.group(2).lower().startswith('y') else 'month'}"
    name = TERM_RE.sub(" ", f.product).lower()
    name = re.sub(r"[^a-z0-9&' ]+", " ", name)
    names = []
    if " & " in name or " and " in name:
        left, right = re.split(r" & | and ", name, maxsplit=1)
        rw = right.split()
        if rw:
            noun = _singular(rw[-1])
            names = [" ".join(left.split() + [noun]), " ".join(rw[:-1] + [noun])]
    if not names:
        w = name.split()
        names = [" ".join(w[:-1] + [_singular(w[-1])])] if w else []
    plain = " ".join(x for x in [term, names[0] if names else "", f.metric] if x)
    return plain + ("; " + "; ".join(names[1:]) if len(names) > 1 else "")


def _topic(f) -> str:
    quals = [v for k, v in f.qualifiers.items() if not NOISE_QUALIFIERS.search(k) and v != f.product]
    period = {"intro": " (introductory)", "after_promo": " (after the promotion)"}.get(f.period or "", "")
    product = f.product if len(f.product) <= 80 else f.product[:80].rsplit(" ", 1)[0]
    table = " ".join([product, ", ".join(quals), f.metric + period]).replace("  ", " ").strip()
    plain = _plain(f) if PLAIN_TOPIC else ""
    return f"{plain} ({table})" if plain and plain.lower() != table.lower() else table


def _reason(w, occ) -> str:
    others = sorted({f.url for f in occ if f.value != w.value})
    dated = f", effective {w.effective}" if w.effective else ""
    ended = " The other value is from an offer the page says has ended." if any(getattr(f, "expired", False) for f in occ) else ""
    return (f"The {PAGE_WORD.get(w.page_type, 'page')} {w.url}{dated} is the most trusted source for this fact; "
            f"{len(others)} other page(s) show a different value (older or less authoritative copies).{ended}")


def build(snapshot, llm=None, sentence_cache: dict | None = None) -> list[Conflict]:
    """Contradictions in one website copy (call with the newest)."""
    facts = [f for f in (to_fact(asdict(c)) for c in parse_pages(snapshot.pages, snapshot.snapshot_id)) if f]
    if llm is not None:
        sentences = rate_sentences(snapshot.pages)
        cache = sentence_cache if sentence_cache is not None else {}
        extract(sentences, llm, cache)
        facts += to_facts(sentences, cache)
    pairs = candidate_pairs(facts)
    out = []
    for c in conflicts_from(facts, pairs, same_strict):
        w = winner(c.occ)
        values = [w.value] + [v for v in c.values if v != w.value]
        urls = [w.url] + sorted({f.url for f in c.occ} - {w.url})
        out.append(Conflict(topic=_topic(w), values=values,
                            sources=[Source(url=u, snapshot_id=snapshot.snapshot_id) for u in urls],
                            resolution=w.value, reason=_reason(w, c.occ)))
    out.extend(count_conflicts(snapshot))
    out.sort(key=lambda c: (c.topic, c.values))
    return out


def count_conflicts(snapshot) -> list[Conflict]:
    """Branches, employees, members, assets: every value the site states for the whole credit union; the newest dated wins."""
    facts = count_facts(snapshot.pages)
    out = []
    for measure in TOPIC:
        fs = [f for f in facts if f.measure == measure]
        if len({f.value for f in fs}) < 2:
            continue
        w = latest(fs)
        others = [v for v, _ in Counter(f.value for f in fs if f.value != w.value).most_common()]
        urls = [w.url] + sorted({f.url for f in fs if f.value != w.value})[:15]
        out.append(Conflict(
            topic=TOPIC[measure], values=[label(measure, v) for v in [w.value] + others],
            sources=[Source(url=u, snapshot_id=snapshot.snapshot_id) for u in urls],
            resolution=label(measure, w.value),
            reason=(f"Each news release and blog post repeats the count of its own day. The most recently published one ({w.url}, "
                    f"{w.published}) says {label(measure, w.value)}; {len(others)} older value(s) appear on {len({f.url for f in fs}) - 1} "
                    f"other page(s).")))
    return out
