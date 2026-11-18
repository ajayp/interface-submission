"""
Source tiers (see CLAUDE.md "Decisions so far"; to be written up in NOTES.md).

Tier 1 = authoritative: rate sheets first, then product/service pages, promo/landing pages last.
Tier 2 = everything else: newsroom, blog, business/resources articles, dated paths, calculators,
PDFs/files, and any page we have not classified.
"""
from __future__ import annotations

from urllib.parse import urlparse

RATE_SHEETS = {"rates", "business-rates"}
TIER1_PREFIXES = ("personal/", "business/", "about/")
TIER1_EXACT = {"personal", "business", "about", "contact", "checking", "disclosures", ""}
TIER2_PREFIXES = ("business/resources", "learn/", "newsroom", "calculators", "business-calculators",
                  "hubfs/", "dupacodaily/")
PROMO_EXACT = {"switch-and-earn"}

# Every other page on the main site (/membership, /loans, /personal-loans, /first-time-homebuyer-grant, /mortgage-refi, ...) is an
# official page we have not vetted one by one: Dupaco's own statement, so more trusted than a blog post or press release, but some are
# campaign pages whose rates go stale, so they rank with promotion pages: below the rate sheets and the product pages.
# MY_SOLUTION_OFFICIAL_RANK = secondary (the earlier behaviour) | promo | product. Article index pages (/resources/...) only list
# teasers of blog posts and stay secondary.
INDEX_PREFIXES = ("resources",)
OFFICIAL_RANK = __import__("os").getenv("MY_SOLUTION_OFFICIAL_RANK", "secondary")
assert OFFICIAL_RANK in ("secondary", "promo", "product")

# Rank labels, best first. Boost weights live in search.py so they can be tuned in one place.
RATE_SHEET, PRODUCT, PROMO, SECONDARY = "rate_sheet", "product", "promo", "secondary"


def path_of(url: str) -> str:
    return urlparse(url).path.strip("/").lower()


def page_rank(url: str) -> str:
    path = path_of(url)  # urlparse drops any #fragment
    if path in RATE_SHEETS:
        return RATE_SHEET
    if path.endswith(".pdf") or path.startswith(TIER2_PREFIXES) or path[:4].isdigit():
        return SECONDARY
    if path in PROMO_EXACT or path.endswith("-lp") or "-lp/" in path:
        return PROMO
    if path in TIER1_EXACT or path.startswith(TIER1_PREFIXES):
        return PRODUCT
    if path.startswith(INDEX_PREFIXES):
        return SECONDARY
    return OFFICIAL_RANK


def tier(url: str) -> int:
    return 2 if page_rank(url) == SECONDARY else 1
