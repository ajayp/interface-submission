// Hand-written synonym groups (general credit-union vocabulary). Port of my_solution/synonyms.py.
import { tokenize } from "./search.ts";

export const GROUPS: string[][] = [["mortgage", "home loan", "house loan", "home purchase", "refinance"], ["home equity", "heloc", "home equity line of credit", "second mortgage"], ["certificate", "cd", "certificate of deposit", "share certificate", "term deposit"], ["ira", "individual retirement account", "retirement account"], ["savings", "savings account", "share savings", "share account"], ["checking", "checking account", "share draft"], ["money market", "money market account"], ["auto loan", "car loan", "vehicle loan", "auto & motorcycle loans"], ["car", "auto", "vehicle", "truck", "motorcycle"], ["boat", "rv", "camper", "atv", "recreational vehicle", "recreational loan"], ["personal loan", "signature loan", "unsecured loan"], ["student loan", "education loan", "college loan"], ["credit card", "visa", "card"], ["debit card", "atm card", "check card"], ["business", "commercial", "small business"], ["interest rate", "rate", "apr", "apy", "dividend rate", "annual percentage"], ["fee", "charge", "cost", "price"], ["minimum", "minimum deposit", "minimum balance", "to open"], ["balance", "deposit amount", "tier"], ["hours", "lobby hours", "drive-up hours", "branch hours", "open", "closed"], ["drive-up", "drive up", "drive-thru", "drive through"], ["branch", "location", "office"], ["atm", "cash machine", "surcharge-free atm"], ["address", "located", "location", "directions"], ["contact information", "contact info", "personal information", "phone number", "email address", "mailing address", "call us", "contact us"], ["update", "change", "edit"], ["phone", "telephone", "call"], ["routing number", "aba number", "routing transit number", "aba"], ["join", "become a member", "membership", "member", "eligible", "eligibility"], ["online banking", "mobile banking", "shine", "app"], ["mobile wallet", "apple pay", "google pay", "samsung pay", "digital wallet"], ["wire transfer", "wire"], ["overdraft", "nsf", "insufficient funds"], ["lost card", "stolen card", "replacement card", "card replacement"]];

const GROUP_TOKENS: string[][][] = GROUPS.map((g) => g.map((p) => tokenize(p)));

function contains(tokens: string[], phrase: string[]): boolean {
  const n = phrase.length;
  if (n === 0) return false;
  for (let i = 0; i + n <= tokens.length; i++) if (phrase.every((t, j) => tokens[i + j] === t)) return true;
  return false;
}

/** Stemmed tokens to add to the search: the other phrases of every group whose phrase appears in the question. */
export function expansion(question: string): string[] {
  const toks = tokenize(question);
  const extra: string[] = [];
  for (const phrases of GROUP_TOKENS) {
    if (phrases.some((p) => contains(toks, p))) for (const p of phrases) if (!contains(toks, p)) extra.push(...p);
  }
  const seen = new Set(toks);
  const out: string[] = [];
  for (const t of extra) if (!seen.has(t)) { seen.add(t); out.push(t); }
  return out;
}
