"""
Rate facts stated in sentences (outside tables), for conflicts(). One gpt-6-luna call per distinct rate sentence labels it
(offer / example / education / other) and extracts product, rate type, term, tier, value, intro, expired and bound
(exact / minimum / maximum / as low as / up to / range). Only exact "offer" values are compared (tasks/conflict_scenarios.md, 32).
Measured in my_solution/sentence_poc.py.
"""
from __future__ import annotations

import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor

from fact_match import RateFact, product_name, same_rules, term_months, tier, winner_tiers, words
from tiers import page_rank

# A rate fragment such as "**3.66% APY**" names no product on its own; the text just before it does. With this switch on, each
# sentence is read together with the sentence or line before it (MY_SOLUTION_SENTENCE_CONTEXT=0 restores the sentence alone).
SENTENCE_CONTEXT = os.getenv("MY_SOLUTION_SENTENCE_CONTEXT", "1") == "1"
CONTEXT_CHARS = 300

RATE_SENT_RE = re.compile(r"\d+(?:\.\d+)?\s*%[^.]{0,40}?(APR|APY|annual percentage|dividend|rate|interest)"
                          r"|(APR|APY|rate|dividend)[^.%]{0,60}?\d+(?:\.\d+)?\s*%", re.I)
LINK_RE = re.compile(r"\]\((?:https?://)[^)]*\)")

SYSTEM = """You read one sentence from a credit union's website (with the page title and the heading above it) and extract the
interest rates it states. Return one entry per rate value in the sentence.
- kind: "offer" when the sentence states a rate this credit union offers or charges on a product (a current or past offer, a
  promotion, a minimum or maximum APR); "example" when the rate is part of an illustrative payment example ("If you borrow
  $10,000 at 7.24% APR ..."); "education" for general finance content, quotes, market averages or other institutions;
  "other" for anything else (a percentage that is not an interest rate, such as a loan-to-value or a match).
- product: the product name as the sentence or heading gives it (e.g. "6-month certificate", "Platinum Visa", "Mortgage Rate
  Relief program"). rate_type: one of APR, APY, dividend rate, rate. term: the term as written (e.g. "60 months") or "".
  tier: the balance or loan-amount band as written (e.g. "$25,000-$99,999.99") or "". value: the number with % (e.g. "3.50%").
- intro: true only when the sentence says the rate applies for an initial period and then changes ("introductory", "for the
  first 6 months", "after that, your rate will be"). A "special" or promotional rate that is not described as changing later is
  NOT intro. expired: true when the sentence says the offer ended or expired.
- bound: "exact" for a single stated rate; "minimum" / "maximum" for a floor or cap ("never less than", "Maximum APR");
  "as_low_as" for "as low as" / "starting at"; "up_to" for "up to" / "earn up to"; "range" for "12.50% to 19.50%" (put the low
  end in value and the high end in value_high; otherwise value_high is "").
Answer with JSON only."""
CONTEXT_RULE = """
When "Text just before" is given and the sentence names no product (for example a bare "3.66% APY"), take the product, tier and
introductory wording from that text; never from the page title alone."""
SCHEMA = {"type": "object", "properties": {"rates": {"type": "array", "items": {"type": "object", "properties": {
    "kind": {"type": "string", "enum": ["offer", "example", "education", "other"]},
    "product": {"type": "string"}, "rate_type": {"type": "string", "enum": ["APR", "APY", "dividend rate", "rate"]},
    "term": {"type": "string"}, "tier": {"type": "string"}, "value": {"type": "string"},
    "intro": {"type": "boolean"}, "expired": {"type": "boolean"},
    "bound": {"type": "string", "enum": ["exact", "minimum", "maximum", "as_low_as", "up_to", "range"]},
    "value_high": {"type": "string"}},
    "required": ["kind", "product", "rate_type", "term", "tier", "value", "intro", "expired", "bound", "value_high"], "additionalProperties": False}}},
    "required": ["rates"], "additionalProperties": False}



def rate_sentences(pages) -> dict[str, dict]:
    """Distinct rate sentences -> {text, title, heading, pages: [(url, fetched_at)]}. `pages`: objects or dicts with
    url, title, markdown, fetched_at."""
    out: dict[str, dict] = {}
    for p in pages:
        get = (lambda k: p.get(k, "")) if isinstance(p, dict) else (lambda k: getattr(p, k, "") or "")
        heading = ""
        recent: list[str] = []   # the last two sentences or lines of this page that are not headings or table rows
        for line in get("markdown").split("\n"):
            s = line.strip()
            if s.startswith("#"):
                heading = s.lstrip("# ").strip()
                recent = []
                continue
            if s.startswith("|"):
                continue
            for sent in re.split(r"(?<=[.!?])\s+", LINK_RE.sub("]", s)):
                if RATE_SENT_RE.search(sent) and len(sent) < 700:
                    before = " ".join(recent)[-CONTEXT_CHARS:] if SENTENCE_CONTEXT else ""
                    key = sent.strip() + ("\x1f" + before if before else "")
                    e = out.setdefault(key, {"text": sent.strip(), "title": get("title"), "heading": heading, "before": before,
                                             "pages": []})
                    e["pages"].append((get("url"), get("fetched_at")))
                if sent.strip():
                    recent = (recent + [sent.strip()])[-2:]
    return out


def extract(sentences: dict[str, dict], llm, cache: dict) -> dict[str, list]:
    """Fill `cache` (sentence -> extracted rates) for sentences not in it yet; failed calls are left out (retried next time)."""
    todo = {k: v for k, v in sentences.items() if k not in cache}

    def one(e):
        before = f"Text just before: {e['before']}\n" if e.get("before") else ""
        msg = f"Page title: {e['title']}\nHeading above: {e['heading']}\n{before}Sentence: {e['text']}"
        for _ in (1, 2):
            try:
                return llm.ask_json(SYSTEM + (CONTEXT_RULE if SENTENCE_CONTEXT else ""), msg, SCHEMA, "sentence_rates", "dupaco-sentrates-v4" if SENTENCE_CONTEXT else "dupaco-sentrates-v3", max_tokens=800, timeout=60)["rates"]
            except Exception:   # noqa: BLE001
                pass
        return None

    if todo:
        with ThreadPoolExecutor(8) as pool:
            for k, r in zip(todo, pool.map(one, todo.values())):
                if r is not None:
                    cache[k] = r
    return cache


def to_facts(sentences, extracted) -> list[RateFact]:
    out = []
    for text, rates in extracted.items():
        e = sentences.get(text)
        if not e:
            continue
        for r in rates:
            if r["kind"] != "offer" or r.get("bound") != "exact":   # floors, caps, "as low as", "up to", ranges are not one rate
                continue
            m = re.search(r"\d+(?:\.\d+)?", r["value"])
            if not m:
                continue
            desc = f"{r['product']} {r['term']} {r['tier']}"
            for url, fetched in e["pages"]:
                out.append(RateFact(
                    url=url, page_type=page_rank(url), table_id="s:" + hashlib.sha1(text.encode()).hexdigest()[:10],
                    effective=None, fetched_at=fetched, product=r["product"], qualifiers={}, column=r["rate_type"],
                    raw=e["text"], value=f"{float(m.group(0)):g}%", metric=r["rate_type"], period="intro" if r["intro"] else None,
                    term=term_months(desc), tier=tier(desc), years=None, as_low_as=False, heading=e["heading"],
                    caption=e["title"], after="", headers=(), row_cells=(text,)))
                out[-1].expired = r["expired"]
    return out


def same_strict(a: RateFact, b: RateFact) -> bool:
    """Tables keep the rule matcher; a pair involving a sentence also needs at least two meaningful product words on the shorter
    name (AI-extracted names are looser than table names: a bare "savings" must not match three different savings accounts)."""
    if not (a.table_id.startswith("s:") or b.table_id.startswith("s:")):
        return same_rules(a, b)

    def size(f):
        e, r = words(product_name(f))
        return len(r) + sum(len(w.split()) for w in e)
    return same_rules(a, b) and min(size(a), size(b)) >= 2


def winner(occ: list[RateFact]) -> RateFact:
    """Trust order, except that a value the page itself says has ended always loses."""
    live = [f for f in occ if not getattr(f, "expired", False)]
    return winner_tiers(live or occ)
