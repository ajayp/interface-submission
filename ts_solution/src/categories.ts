// Fixed category list built by rules (no LLM). Port of my_solution/categories.py (rules are data, copied verbatim).
interface Rule { url: string[]; heading: string[]; text: string[] }
export const RULES: Record<string, Rule> = {
  "Savings accounts": {
    "url": [
      "personal/savings"
    ],
    "heading": [
      "share savings",
      "bright savings",
      "you name it savings",
      "holiday club",
      "launchpad savings",
      "high-yield savings",
      "money market"
    ],
    "text": []
  },
  "Certificates and IRAs": {
    "url": [
      "personal/retirement"
    ],
    "heading": [
      "certificate",
      "ira"
    ],
    "text": [
      "certificate special",
      "jumbo certificate"
    ]
  },
  "Health Savings Account": {
    "url": [],
    "heading": [
      "health savings"
    ],
    "text": [
      "health savings account"
    ]
  },
  "Checking accounts": {
    "url": [
      "personal/checking",
      "/checking",
      "checking-offer"
    ],
    "heading": [
      "free checking",
      "1st rate checking"
    ],
    "text": []
  },
  "Credit cards": {
    "url": [
      "personal/credit-cards",
      "newcard-balancetransfer"
    ],
    "heading": [
      "platinum visa",
      "rewards visa"
    ],
    "text": []
  },
  "Auto and motorcycle loans": {
    "url": [
      "loans/auto"
    ],
    "heading": [
      "auto & motorcycle",
      "auto loan"
    ],
    "text": []
  },
  "Mortgages and home loans": {
    "url": [
      "loans/home-loans"
    ],
    "heading": [
      "home loans - purchase",
      "home loans - refinance",
      "mortgage"
    ],
    "text": [
      "30-year fixed",
      "15-year fixed"
    ]
  },
  "Home equity": {
    "url": [
      "loans/home-equity"
    ],
    "heading": [
      "home equity",
      "heloc"
    ],
    "text": []
  },
  "Home improvement loans": {
    "url": [
      "home-improvement-loan"
    ],
    "heading": [
      "home improvement"
    ],
    "text": []
  },
  "Personal loans": {
    "url": [
      "loans/personal-loans",
      "debt-consolidation"
    ],
    "heading": [
      "personal loan"
    ],
    "text": []
  },
  "Recreational loans": {
    "url": [
      "recreational-loans"
    ],
    "heading": [
      "boat & rv",
      "atv, snowmobile"
    ],
    "text": []
  },
  "Student loans": {
    "url": [
      "student-loans"
    ],
    "heading": [
      "student loan"
    ],
    "text": []
  },
  "Loan protection": {
    "url": [
      "loan-protection"
    ],
    "heading": [
      "loan protection"
    ],
    "text": []
  },
  "Insurance": {
    "url": [
      "/insurance"
    ],
    "heading": [
      "insurance"
    ],
    "text": []
  },
  "Business savings and certificates": {
    "url": [
      "business/savings",
      "business-rates"
    ],
    "heading": [
      "business share savings",
      "(business)",
      "business certificate"
    ],
    "text": []
  },
  "Business checking and cash management": {
    "url": [
      "business/business-checking",
      "business/checking",
      "business/cash-management"
    ],
    "heading": [
      "business 1st rate checking"
    ],
    "text": []
  },
  "Business credit cards": {
    "url": [
      "business/credit-cards"
    ],
    "heading": [
      "business platinum visa",
      "business rewards visa"
    ],
    "text": []
  },
  "Business loans and credit lines": {
    "url": [
      "business/loans",
      "business/credit-lines"
    ],
    "heading": [],
    "text": []
  },
  "Branches, ATMs and hours": {
    "url": [
      "/contact"
    ],
    "heading": [
      "branch",
      "atm",
      "location"
    ],
    "text": [
      "lobby hours",
      "drive-up",
      "branch hours",
      "lobby",
      "full-service branch",
      "surcharge-free atm"
    ]
  },
  "Contact and member services": {
    "url": [
      "/contact",
      "about/member-services",
      "connect/contact-us"
    ],
    "heading": [
      "contact"
    ],
    "text": [
      "800-373-7600",
      "call us",
      "contact us"
    ]
  },
  "Membership and joining": {
    "url": [
      "about/join"
    ],
    "heading": [
      "join",
      "membership"
    ],
    "text": [
      "become a member",
      "charter area",
      "join.dupaco.com"
    ]
  },
  "Online and mobile banking": {
    "url": [
      "connect/",
      "online-and-mobile"
    ],
    "heading": [
      "shine"
    ],
    "text": [
      "shine online",
      "mobile banking",
      "mobile wallet"
    ]
  },
  "Routing number and account details": {
    "url": [],
    "heading": [
      "routing"
    ],
    "text": [
      "routing number"
    ]
  },
  "Fees and disclosures": {
    "url": [
      "disclosures",
      "privacy-policy",
      "fee-schedule"
    ],
    "heading": [
      "fee"
    ],
    "text": [
      "fee schedule"
    ]
  },
  "About Dupaco": {
    "url": [
      "/about",
      "our-impact"
    ],
    "heading": [],
    "text": [
      "volunteer time off",
      "forbes"
    ]
  }
};

export const CATEGORIES: string[] = Object.keys(RULES);

const norm = (s: string): string => (s ?? "").toLowerCase().replace(/\s+/g, " ");
const esc = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
/** Whole-word, case-insensitive pattern ("ira" must not match "accurate"). */
const words = (ps: string[]): RegExp | null => (ps.length ? new RegExp("(?<![a-z0-9])(?:" + ps.map(esc).join("|") + ")(?![a-z0-9])") : null);

const COMPILED = Object.entries(RULES).map(([name, r]) => [name, r.url, words(r.heading), words(r.text)] as const);

export function categoriesFor(url: string, headingText: string, body: string): string[] {
  const u = url.toLowerCase(), h = norm(headingText), b = norm(body);
  const out: string[] = [];
  for (const [name, urls, headRe, textRe] of COMPILED)
    if (urls.some((x) => u.includes(x)) || (headRe && headRe.test(h)) || (textRe && textRe.test(b))) out.push(name);
  return out;
}
