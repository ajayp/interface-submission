"""Draft search words per website section. Used only when MY_SOLUTION_QU_CATWORDS=1."""
from __future__ import annotations

from search import tokenize

WORDS: dict[str, list[str]] = {
 "Savings accounts": [
  "savings account",
  "share savings",
  "dividend rate",
  "APY",
  "minimum balance",
  "balance tier",
  "money market",
  "youth savings",
  "holiday club"
 ],
 "Certificates and IRAs": [
  "certificate",
  "CD",
  "term",
  "APY",
  "dividend rate",
  "early withdrawal",
  "special certificate",
  "IRA",
  "rollover",
  "maturity"
 ],
 "Health Savings Account": [
  "HSA",
  "health savings",
  "medical expenses",
  "contribution limit",
  "qualified expenses"
 ],
 "Checking accounts": [
  "checking account",
  "share draft",
  "overdraft",
  "debit card",
  "monthly fee",
  "minimum balance",
  "APY",
  "rewards checking"
 ],
 "Credit cards": [
  "credit card",
  "Visa",
  "APR",
  "rewards",
  "balance transfer",
  "cash advance",
  "annual fee",
  "credit limit"
 ],
 "Auto and motorcycle loans": [
  "auto loan",
  "car loan",
  "vehicle",
  "motorcycle",
  "new",
  "used",
  "model year",
  "APR",
  "term",
  "months"
 ],
 "Mortgages and home loans": [
  "mortgage",
  "fixed rate",
  "adjustable rate",
  "ARM",
  "jumbo",
  "APR",
  "term",
  "years",
  "refinance",
  "down payment"
 ],
 "Home equity": [
  "home equity",
  "HELOC",
  "line of credit",
  "second mortgage",
  "APR",
  "draw period"
 ],
 "Home improvement loans": [
  "home improvement",
  "remodel",
  "renovation",
  "APR",
  "term"
 ],
 "Personal loans": [
  "personal loan",
  "signature loan",
  "unsecured",
  "APR",
  "term",
  "months"
 ],
 "Recreational loans": [
  "boat",
  "RV",
  "camper",
  "ATV",
  "recreational vehicle",
  "APR",
  "term"
 ],
 "Student loans": [
  "student loan",
  "education loan",
  "college",
  "tuition",
  "APR",
  "repayment"
 ],
 "Loan protection": [
  "loan protection",
  "payment protection",
  "debt protection",
  "disability",
  "cost per month"
 ],
 "Insurance": [
  "insurance",
  "auto insurance",
  "home insurance",
  "life insurance",
  "quote",
  "agent",
  "coverage"
 ],
 "Business savings and certificates": [
  "business savings",
  "business certificate",
  "business money market",
  "APY",
  "minimum balance"
 ],
 "Business checking and cash management": [
  "business checking",
  "cash management",
  "merchant services",
  "treasury",
  "monthly fee",
  "transactions"
 ],
 "Business credit cards": [
  "business credit card",
  "business Visa",
  "APR",
  "rewards",
  "credit limit"
 ],
 "Business loans and credit lines": [
  "business loan",
  "commercial loan",
  "line of credit",
  "SBA",
  "equipment",
  "APR",
  "term"
 ],
 "Branches, ATMs and hours": [
  "branch",
  "lobby hours",
  "drive-up hours",
  "hours vary by branch",
  "same hours",
  "open",
  "closed",
  "Saturday",
  "Sunday",
  "address",
  "ATM",
  "24-hour ATM",
  "video teller",
  "holiday hours"
 ],
 "Contact and member services": [
  "contact",
  "phone number",
  "call",
  "email",
  "member service",
  "update",
  "address change",
  "secure message",
  "support hours"
 ],
 "Membership and joining": [
  "become a member",
  "join",
  "eligibility",
  "who can join",
  "membership",
  "open an account",
  "requirements",
  "field of membership"
 ],
 "Online and mobile banking": [
  "online banking",
  "mobile app",
  "mobile deposit",
  "bill pay",
  "digital banking",
  "sign in",
  "enroll",
  "Zelle"
 ],
 "Routing number and account details": [
  "routing number",
  "account number",
  "wire",
  "ACH",
  "direct deposit",
  "transit number"
 ],
 "Fees and disclosures": [
  "fee schedule",
  "fees",
  "disclosure",
  "overdraft fee",
  "wire fee",
  "stop payment",
  "terms and conditions",
  "truth in savings"
 ],
 "About Dupaco": [
  "about Dupaco",
  "history",
  "chartered",
  "founded",
  "members",
  "assets",
  "employees",
  "branches",
  "awards",
  "ranked",
  "community"
 ]
}


def tokens_for(categories) -> list[str]:
    """Stemmed search tokens for the chosen sections (same tokenizer as the search index)."""
    seen, out = set(), []
    for c in categories:
        for phrase in WORDS.get(c, ()):
            for t in tokenize(phrase):
                if t not in seen:
                    seen.add(t)
                    out.append(t)
    return out
