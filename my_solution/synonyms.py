"""
Hand-written synonym groups: general credit-union vocabulary, not the practice questions' answers.

Each group lists words or phrases that members and the website use for the same thing. When any phrase
in a group appears in a question, the group's other phrases are added to the search at reduced weight
(see search.BM25Index.search), so the member's own words still count most. No LLM call at question time.
"""
from __future__ import annotations

from search import tokenize

GROUPS: list[list[str]] = [
    # products
    ["mortgage", "home loan", "house loan", "home purchase", "refinance"],
    ["home equity", "heloc", "home equity line of credit", "second mortgage"],
    ["certificate", "cd", "certificate of deposit", "share certificate", "term deposit"],
    ["ira", "individual retirement account", "retirement account"],
    ["savings", "savings account", "share savings", "share account"],
    ["checking", "checking account", "share draft"],
    ["money market", "money market account"],
    ["auto loan", "car loan", "vehicle loan", "auto & motorcycle loans"],
    ["car", "auto", "vehicle", "truck", "motorcycle"],
    ["boat", "rv", "camper", "atv", "recreational vehicle", "recreational loan"],
    ["personal loan", "signature loan", "unsecured loan"],
    ["student loan", "education loan", "college loan"],
    ["credit card", "visa", "card"],
    ["debit card", "atm card", "check card"],
    ["business", "commercial", "small business"],
    # rates and money
    ["interest rate", "rate", "apr", "apy", "dividend rate", "annual percentage"],
    ["fee", "charge", "cost", "price"],
    ["minimum", "minimum deposit", "minimum balance", "to open"],
    ["balance", "deposit amount", "tier"],
    # service and places
    ["hours", "lobby hours", "drive-up hours", "branch hours", "open", "closed"],
    ["drive-up", "drive up", "drive-thru", "drive through"],
    ["branch", "location", "office"],
    ["atm", "cash machine", "surcharge-free atm"],
    ["address", "located", "location", "directions"],
    ["contact information", "contact info", "personal information", "phone number", "email address",
     "mailing address", "call us", "contact us"],
    ["update", "change", "edit"],
    ["phone", "telephone", "call"],
    ["routing number", "aba number", "routing transit number", "aba"],
    ["join", "become a member", "membership", "member", "eligible", "eligibility"],
    ["online banking", "mobile banking", "shine", "app"],
    ["mobile wallet", "apple pay", "google pay", "samsung pay", "digital wallet"],
    ["wire transfer", "wire"],
    ["overdraft", "nsf", "insufficient funds"],
    ["lost card", "stolen card", "replacement card", "card replacement"],
]

_GROUP_TOKENS = [[tuple(tokenize(p)) for p in g] for g in GROUPS]


def _contains(tokens: list[str], phrase: tuple) -> bool:
    n = len(phrase)
    return n > 0 and any(tuple(tokens[i:i + n]) == phrase for i in range(len(tokens) - n + 1))


def expansion(question: str) -> list[str]:
    """Stemmed tokens to add to the search: the other phrases of every group whose phrase appears in the question."""
    toks = tokenize(question)
    extra: list[str] = []
    for phrases in _GROUP_TOKENS:
        if any(_contains(toks, p) for p in phrases):
            for p in phrases:
                if not _contains(toks, p):
                    extra.extend(p)
    seen = set(toks)
    out = []
    for t in extra:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
