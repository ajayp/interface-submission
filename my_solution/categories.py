"""
Fixed category list for query understanding, built by rules (no LLM, free).

A piece (chunk) gets every category whose rules match it:
  - url:     a path fragment of the page it came from          ("personal/loans/auto")
  - heading: a word or phrase in its table caption or headings  ("auto & motorcycle loans")
  - text:    a strong phrase in its body text                   ("lobby hours")
The query-understanding LLM may only choose from CATEGORIES (enforced by its JSON schema).
"""
from __future__ import annotations

import re

# name -> rules. Matching is case-insensitive substring matching.
RULES: dict[str, dict[str, list[str]]] = {
    # ---- personal deposits
    "Savings accounts": {
        "url": ["personal/savings"],
        "heading": ["share savings", "bright savings", "you name it savings", "holiday club", "launchpad savings",
                    "high-yield savings", "money market"],
        "text": [],
    },
    "Certificates and IRAs": {
        "url": ["personal/retirement"],
        "heading": ["certificate", "ira"],
        "text": ["certificate special", "jumbo certificate"],
    },
    "Health Savings Account": {"url": [], "heading": ["health savings"], "text": ["health savings account"]},
    "Checking accounts": {
        "url": ["personal/checking", "/checking", "checking-offer"],
        "heading": ["free checking", "1st rate checking"],
        "text": [],
    },
    # ---- personal cards and loans
    "Credit cards": {
        "url": ["personal/credit-cards", "newcard-balancetransfer"],
        "heading": ["platinum visa", "rewards visa"],
        "text": [],
    },
    "Auto and motorcycle loans": {"url": ["loans/auto"], "heading": ["auto & motorcycle", "auto loan"], "text": []},
    "Mortgages and home loans": {
        "url": ["loans/home-loans"],
        "heading": ["home loans - purchase", "home loans - refinance", "mortgage"],
        "text": ["30-year fixed", "15-year fixed"],
    },
    "Home equity": {"url": ["loans/home-equity"], "heading": ["home equity", "heloc"], "text": []},
    "Home improvement loans": {"url": ["home-improvement-loan"], "heading": ["home improvement"], "text": []},
    "Personal loans": {"url": ["loans/personal-loans", "debt-consolidation"], "heading": ["personal loan"], "text": []},
    "Recreational loans": {
        "url": ["recreational-loans"],
        "heading": ["boat & rv", "atv, snowmobile"],
        "text": [],
    },
    "Student loans": {"url": ["student-loans"], "heading": ["student loan"], "text": []},
    "Loan protection": {"url": ["loan-protection"], "heading": ["loan protection"], "text": []},
    "Insurance": {"url": ["/insurance"], "heading": ["insurance"], "text": []},
    # ---- business
    "Business savings and certificates": {
        "url": ["business/savings", "business-rates"],
        "heading": ["business share savings", "(business)", "business certificate"],
        "text": [],
    },
    "Business checking and cash management": {
        "url": ["business/business-checking", "business/checking", "business/cash-management"],
        "heading": ["business 1st rate checking"],
        "text": [],
    },
    "Business credit cards": {"url": ["business/credit-cards"], "heading": ["business platinum visa",
                                                                           "business rewards visa"], "text": []},
    "Business loans and credit lines": {"url": ["business/loans", "business/credit-lines"], "heading": [], "text": []},
    # ---- service and company
    "Branches, ATMs and hours": {
        "url": ["/contact"],
        "heading": ["branch", "atm", "location"],
        "text": ["lobby hours", "drive-up", "branch hours", "lobby", "full-service branch", "surcharge-free atm"],
    },
    "Contact and member services": {
        "url": ["/contact", "about/member-services", "connect/contact-us"],
        "heading": ["contact"],
        "text": ["800-373-7600", "call us", "contact us"],
    },
    "Membership and joining": {"url": ["about/join"], "heading": ["join", "membership"],
                               "text": ["become a member", "charter area", "join.dupaco.com"]},
    "Online and mobile banking": {"url": ["connect/", "online-and-mobile"], "heading": ["shine"],
                                  "text": ["shine online", "mobile banking", "mobile wallet"]},
    "Routing number and account details": {"url": [], "heading": ["routing"], "text": ["routing number"]},
    "Fees and disclosures": {"url": ["disclosures", "privacy-policy", "fee-schedule"], "heading": ["fee"],
                             "text": ["fee schedule"]},
    "About Dupaco": {"url": ["/about", "our-impact"], "heading": [], "text": ["volunteer time off", "forbes"]},
}

CATEGORIES: list[str] = list(RULES)

_SPACE = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _SPACE.sub(" ", (s or "").lower())


def _words(phrases: list[str]):
    """Whole-word, case-insensitive pattern ("ira" must not match "accurate")."""
    if not phrases:
        return None
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(p) for p in phrases) + r")(?![a-z0-9])")


_COMPILED = {name: (r["url"], _words(r["heading"]), _words(r["text"])) for name, r in RULES.items()}


def categories_for(url: str, heading_text: str, body: str) -> list[str]:
    """Every category whose url, heading or text rule matches this piece."""
    u, h, b = url.lower(), _norm(heading_text), _norm(body)
    out = []
    for name, (urls, head_re, text_re) in _COMPILED.items():
        if (any(x in u for x in urls) or (head_re is not None and head_re.search(h))
                or (text_re is not None and text_re.search(b))):
            out.append(name)
    return out
