// Source tiers (NOTES.md section 3). Port of my_solution/tiers.py.
export const RATE_SHEET = "rate_sheet", PRODUCT = "product", PROMO = "promo", SECONDARY = "secondary";
export type Rank = typeof RATE_SHEET | typeof PRODUCT | typeof PROMO | typeof SECONDARY;

const RATE_SHEETS = new Set(["rates", "business-rates"]);
const TIER1_PREFIXES = ["personal/", "business/", "about/"];
const TIER1_EXACT = new Set(["personal", "business", "about", "contact", "checking", "disclosures", ""]);
const TIER2_PREFIXES = ["business/resources", "learn/", "newsroom", "calculators", "business-calculators", "hubfs/", "dupacodaily/"];
const PROMO_EXACT = new Set(["switch-and-earn"]);
const INDEX_PREFIXES = ["resources"];
const OFFICIAL_RANK = (process.env.MY_SOLUTION_OFFICIAL_RANK ?? "secondary") as Rank | "secondary";

export function pathOf(url: string): string {
  let p: string;
  try { p = new URL(url).pathname; } catch { p = url; }
  return p.replace(/^\/+|\/+$/g, "").toLowerCase();   // URL drops any #fragment, like urlparse().path
}

const startsAny = (s: string, ps: string[]) => ps.some((p) => s.startsWith(p));

export function pageRank(url: string): Rank {
  const path = pathOf(url);
  if (RATE_SHEETS.has(path)) return RATE_SHEET;
  if (path.endsWith(".pdf") || startsAny(path, TIER2_PREFIXES) || /^\d{4}/.test(path)) return SECONDARY;
  if (PROMO_EXACT.has(path) || path.endsWith("-lp") || path.includes("-lp/")) return PROMO;
  if (TIER1_EXACT.has(path) || startsAny(path, TIER1_PREFIXES)) return PRODUCT;
  if (startsAny(path, INDEX_PREFIXES)) return SECONDARY;
  return OFFICIAL_RANK as Rank;
}

export const tier = (url: string): number => (pageRank(url) === SECONDARY ? 2 : 1);
