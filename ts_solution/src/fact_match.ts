// "Same fact?" for table cells (and rate sentences): normalise without looking at the number, block candidate pairs, match by rules,
// pick the winner by trust. Port of my_solution/fact_match.py.
import type { TableCell } from "./table_parse.ts";

const RATE_METRICS: Record<string, string> = { APR: "APR", APY: "APY", "dividend rate": "dividend rate", "interest rate": "rate", rate: "rate" };
export const TERM_RE = /(\d+)\s*-?\s*(months?|mos?\b|mo\.|years?|yrs?)/i;
const TERM_RE_G = new RegExp(TERM_RE.source, "gi");
const YEARS_RE = /\b((?:19|20)\d\d)\s*(?:[-–]\s*((?:19|20)?\d\d))?\b/;
const MONEY = "\\$\\s?([\\d,]+(?:\\.\\d+)?)";
export const NOISE_QUALIFIERS = /^(points|min\.?|max\.?|min\. to|minimum|maximum)/i;
const SENTENCE_UNSTATED = (process.env.MY_SOLUTION_SENTENCE_UNSTATED ?? "1") === "1";
const RANK: Record<string, number> = { rate_sheet: 0, product: 1, promo: 2, secondary: 3 };

const money = (s: string): number => parseFloat(s.replaceAll(",", ""));
export type Tier = [number, number] | null;
export type Years = [number, number] | null;

export function termMonths(text: string): number | null {
  const m = TERM_RE.exec(text);
  if (!m) return null;
  const n = parseInt(m[1]!, 10);
  return m[2]!.toLowerCase().startsWith("y") ? n * 12 : n;
}

/** Balance or loan-amount band as [low, high]; null when the text names no band. 'or less' -> [0, x]; '+' -> [x, Infinity]. */
export function tierOf(text: string): Tier {
  const t = text.replaceAll("–", "-");
  let m = new RegExp(MONEY + "\\s*(?:-|to)\\s*\\$?\\s?([\\d,]+(?:\\.\\d+)?)").exec(t);
  if (m) return [money(m[1]!), money(m[2]!)];
  m = new RegExp(MONEY + "\\s*(\\+|or more|and (?:up|over|above))", "i").exec(t);
  if (m) return [money(m[1]!), Infinity];
  m = new RegExp(MONEY + "\\s*(or less|and (?:under|below))", "i").exec(t) ?? new RegExp("(?:up to|less than|under)\\s+" + MONEY, "i").exec(t);
  if (m) return [0, money(m[1]!)];
  return null;
}

export function modelYears(text: string): Years {
  if (!/model|year/i.test(text)) return null;
  const m = YEARS_RE.exec(text);
  if (!m) return null;
  const a = parseInt(m[1]!, 10);
  const b = m[2];
  if (b === undefined) return /older|and before|or older/i.test(text) ? [0, a] : [a, a];
  const bb = b.length === 4 ? parseInt(b, 10) : parseInt(String(a).slice(0, 2) + b, 10);
  return [Math.min(a, bb), Math.max(a, bb)];
}

export interface RateFact {
  url: string; pageType: string; tableId: string; effective: string | null; fetchedAt: string | null; product: string;
  qualifiers: Array<[string, string]>; column: string; raw: string; value: string; metric: string; period: string | null; term: number | null;
  tier: Tier; years: Years; asLowAs: boolean; heading: string; caption: string; after: string; headers: string[]; rowCells: string[];
  expired?: boolean;
}

/** The row's own words once term, tier, model years and numbers are removed: what separates jumbo from regular, special from standard. */
export function variantOf(f: RateFact): string {
  let q = f.qualifiers.filter(([k]) => !NOISE_QUALIFIERS.test(k)).map(([, v]) => v).join(" ");
  q = q.replace(TERM_RE_G, " ");
  q = q.replace(/\$\s?[\d,.]+|\b(19|20)\d\d\b|[\d,.]+|\bmodel years?\b|\byears?\b|\bor (less|more)\b|\(and older\)|older/gi, " ");
  return (q.toLowerCase().match(/[a-z]+/g) ?? []).join(" ");
}

export function labelOf(f: RateFact): string {
  const q = f.qualifiers.filter(([k]) => !NOISE_QUALIFIERS.test(k)).map(([k, v]) => `${k}: ${v}`).join("; ");
  return `${f.product} | ${q} | ${f.column}`;
}

export function toFact(c: TableCell): RateFact | null {
  if (c.kind !== "rate" || !(c.metric in RATE_METRICS)) return null;
  const quals = c.qualifiers.filter(([k]) => !NOISE_QUALIFIERS.test(k));
  const text = [c.product, ...quals.map(([, v]) => v)].join(" ");
  return { url: c.url, pageType: c.pageType, tableId: c.tableId, effective: c.effective, fetchedAt: c.fetchedAt, product: c.product, qualifiers: c.qualifiers,
    column: c.column, raw: c.raw, value: c.value, metric: RATE_METRICS[c.metric]!, period: c.period, term: termMonths(text), tier: tierOf(text), years: modelYears(text),
    asLowAs: c.asLowAs, heading: c.heading, caption: c.caption, after: c.after ?? "", headers: c.headers, rowCells: c.row };
}

const sameArr = (a: number[] | null, b: number[] | null): boolean => (a === null || b === null ? a === b : a.length === b.length && a.every((x, i) => x === b[i]));
const yearsOverlap = (a: Years, b: Years): boolean => (a === null || b === null ? a === null && b === null : Math.min(a[1], b[1]) >= Math.max(a[0], b[0]));
const isSentence = (f: RateFact): boolean => f.tableId.startsWith("s:");
const unstated = (f: RateFact): boolean => f.period === null && f.term === null;

/** Could a and b be the same fact? Uses no numbers and no product name. */
export function blocked(a: RateFact, b: RateFact): boolean {
  let samePeriodTerm = a.period === b.period && a.term === b.term;
  if (SENTENCE_UNSTATED && !samePeriodTerm && isSentence(a) && isSentence(b) && (unstated(a) || unstated(b))) samePeriodTerm = true;
  return a.tableId !== b.tableId && a.metric === b.metric && samePeriodTerm && sameArr(a.tier, b.tier) && yearsOverlap(a.years, b.years);
}

function bestBand(years: [number, number], bands: Array<[number, number]>): [number, number] | null {
  let best: [number, number] | null = null, bestKey: [number, number] | null = null;
  for (const b of bands) {
    const key: [number, number] = [Math.min(years[1], b[1]) - Math.max(years[0], b[0]), -Math.abs(b[0] - years[0])];
    if (!bestKey || key[0] > bestKey[0] || (key[0] === bestKey[0] && key[1] > bestKey[1])) { best = b; bestKey = key; }
  }
  return best && Math.min(years[1], best[1]) >= Math.max(years[0], best[0]) ? best : null;
}

/** Distinct candidate pairs with different numbers; copies of the same table on several pages collapse to one. */
export function candidatePairs(facts: RateFact[]): Array<[RateFact, RateFact]> {
  const bands = new Map<string, Array<[number, number]>>();
  for (const f of facts) if (f.years) { let a = bands.get(f.tableId); if (!a) bands.set(f.tableId, (a = [])); if (!a.some((y) => y[0] === f.years![0] && y[1] === f.years![1])) a.push(f.years); }
  const seen = new Set<string>(), out: Array<[RateFact, RateFact]> = [];
  for (let i = 0; i < facts.length; i++) {
    const a = facts[i]!;
    for (let j = i + 1; j < facts.length; j++) {
      const b = facts[j]!;
      if (a.value === b.value || !blocked(a, b)) continue;
      if (a.years && b.years) {
        const ba = bestBand(a.years, bands.get(b.tableId)!), bb = bestBand(b.years, bands.get(a.tableId)!);
        if (!ba || ba[0] !== b.years[0] || ba[1] !== b.years[1] || !bb || bb[0] !== a.years[0] || bb[1] !== a.years[1]) continue;
      }
      const ka: [string, string] = [labelOf(a), a.value], kb: [string, string] = [labelOf(b), b.value];
      const key = JSON.stringify(ka[0] < kb[0] || (ka[0] === kb[0] && ka[1] <= kb[1]) ? [ka, kb] : [kb, ka]);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push([a, b]);
    }
  }
  return out;
}

// ---------------------------------------------------------------- matching and winner
const basic = (name: string): string => name.toLowerCase().trim().replace(/(?<=\d),(?=\d{3})/g, "").replace(/\s+/g, " ");
const negDate = (d: string | null): string => (d ? [...d].map((ch) => String.fromCharCode(255 - ch.charCodeAt(0))).join("") : "ÿ");

/** Trust order: page type, then the later effective date, then the later fetch date. First of equals wins. */
export function winnerTiers(occ: RateFact[]): RateFact {
  const key = (f: RateFact): [number, string, string] => [RANK[f.pageType]!, negDate(f.effective), negDate((f.fetchedAt ?? "").slice(0, 10))];
  const less = (a: [number, string, string], b: [number, string, string]) => (a[0] !== b[0] ? a[0] < b[0] : a[1] !== b[1] ? a[1] < b[1] : a[2] < b[2]);
  let best = occ[0]!;
  for (const f of occ.slice(1)) if (less(key(f), key(best))) best = f;
  return best;
}

const EXCLUSIVE = ["business", "purchase", "refinance", "roth", "traditional", "ira", "jumbo", "special", "atv", "snowmobile", "boat", "rv", "health", "heloc", "visa",
  "platinum", "rewards", "investor", "achieve", "you name it", "high-yield", "launchpad", "share", "checking", "savings", "money market", "certificate", "1st rate", "free",
  "kids", "holiday", "home equity", "personal", "auto", "motorcycle", "standard", "introductory", "balance transfer"];
const GENERIC = new Set(["loan", "loans", "rate", "rates", "account", "accounts", "the", "and", "&", "for", "of", "program"]);
const OPEN_MY_RE = /open my ([a-z0-9' -]+?)(?: account)?(?:\]|\(|$)/i;
const esc = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const EXCL_RES = EXCLUSIVE.map((w) => [w, new RegExp(`(?<![a-z])${esc(w)}(?![a-z])`)] as const);

/** The product line, or the 'Open my <product>' link below the table when the line above is not a name. */
export function productName(f: RateFact): string {
  const p = f.product.trim();
  if (p.startsWith("-") || p.startsWith("*") || p.split(/\s+/).filter(Boolean).length > 8 || p.endsWith(":") || p.endsWith("?")) {
    const m = OPEN_MY_RE.exec(f.after);
    if (m) return m[1]!.trim();
  }
  return p;
}

export function words(name: string): [Set<string>, Set<string>] {
  const n = basic(name);
  const excl = new Set(EXCL_RES.filter(([, r]) => r.test(n)).map(([w]) => w));
  const inExcl = new Set([...excl].flatMap((w) => w.split(" ")));
  const rest = new Set((n.match(/[a-z0-9$.]+/g) ?? []).filter((t) => !GENERIC.has(t) && !inExcl.has(t)));
  return [excl, rest];
}

const sameSet = (a: Set<string>, b: Set<string>): boolean => a.size === b.size && [...a].every((x) => b.has(x));
const subset = (a: Set<string>, b: Set<string>): boolean => [...a].every((x) => b.has(x));
const HARD = new Set(["business", "purchase", "refinance", "roth", "traditional", "ira", "jumbo", "special", "atv", "snowmobile", "boat", "rv", "health", "heloc",
  "introductory", "balance transfer", "standard", "rewards", "platinum"]);
const CATEGORY = new Set(["savings", "checking", "money market", "certificate", "share"]);

export function sameRules(a: RateFact, b: RateFact): boolean {
  if (!sameSet(words(variantOf(a))[0], words(variantOf(b))[0])) return false;
  const [ea, ra] = words(productName(a)), [eb, rb] = words(productName(b));
  if (!sameSet(ea, eb)) {
    const extra = new Set([...ea, ...eb].filter((x) => ea.has(x) !== eb.has(x)));
    const smaller = ea.size <= eb.size ? ea : eb;
    const inter = [...ea].some((x) => eb.has(x));
    const smallerNoCat = [...smaller].some((x) => !CATEGORY.has(x));
    if (!(subset(ea, eb) || subset(eb, ea)) || [...extra].some((x) => HARD.has(x)) || !inter || !smallerNoCat) return false;
  }
  return ra.size === 0 || rb.size === 0 || subset(ra, rb) || subset(rb, ra);
}

export interface ConflictGroup { topic: string; values: string[]; resolution: string; occ: RateFact[] }

export function conflictsFrom(facts: RateFact[], pairs: Array<[RateFact, RateFact]>, same: (a: RateFact, b: RateFact) => boolean): ConflictGroup[] {
  const idx = new Map<RateFact, number>(facts.map((f, i) => [f, i]));
  const parent = facts.map((_, i) => i);
  const find = (x: number): number => { while (parent[x] !== x) { parent[x] = parent[parent[x]!]!; x = parent[x]!; } return x; };
  // the same row copied onto several pages (same product, row, rate type and number) is one fact: join the copies first
  const first = new Map<string, number>();
  facts.forEach((f, i) => {
    const k = JSON.stringify([basic(f.product), variantOf(f), f.metric, f.period, f.term, f.tier && f.tier.map((x) => (x === Infinity ? "inf" : x)), f.years, f.value]);
    const hit = first.get(k);
    if (hit !== undefined) parent[find(i)] = find(hit);
    else first.set(k, i);
  });
  for (const [a, b] of pairs) if (same(a, b)) parent[find(idx.get(a)!)] = find(idx.get(b)!);
  const comp = new Map<number, RateFact[]>();
  for (const f of facts) { const r = find(idx.get(f)!); let a = comp.get(r); if (!a) comp.set(r, (a = [])); a.push(f); }
  const out: ConflictGroup[] = [];
  for (const occ of comp.values()) {
    const vals = [...new Set(occ.map((f) => f.value))].sort();
    if (vals.length < 2) continue;
    out.push({ topic: `${occ[0]!.product} ${labelOf(occ[0]!)}`, values: vals, resolution: winnerTiers(occ).value, occ });
  }
  return out;
}
