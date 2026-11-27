// Facts (GraphRAG-style, in memory): rate tables become facts at loading time. Port of my_solution/facts.py.
// Each distinct table is read once by the model (structured output via a zod schema); the result is cached on disk as JSON in the same
// format as the Python cache ({table_key: [fact, ...]}), so the two implementations can share a cache file.
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { z } from "zod";
import { CATEGORIES } from "./categories.ts";
import { EFFECTIVE_RE, blocksOf, cleanText, effectiveOf, isForm, splitHeading, splitSections } from "./chunker.ts";
import { askJson } from "./openai.ts";
import prompts from "../data/prompts.json" with { type: "json" };
import { pageRank } from "./tiers.ts";

export const METRICS = ["APR", "APY", "dividend rate", "interest rate", "rate", "fee", "minimum", "maximum", "points", "other"] as const;

export const FactSchema = z.object({
  facts: z.array(z.object({
    product: z.string().describe("The specific product or account the row is about."),
    family: z.enum(CATEGORIES as [string, ...string[]]),
    qualifiers: z.array(z.object({ name: z.string(), value: z.string() })),
    metric: z.enum(METRICS),
    value: z.string().describe("The value exactly as the table shows it, e.g. '5.39%'."),
  })),
});
type RawFact = z.infer<typeof FactSchema>["facts"][number];

const RANK_ORDER: Record<string, number> = { rate_sheet: 0, product: 1, promo: 2, secondary: 3 };
const NOTE_FIX = (process.env.MY_SOLUTION_NOTE_FIX ?? "1") === "1";
export const CONFLICT_METRICS = new Set(["APR", "APY", "dividend rate", "interest rate", "rate", "fee"]);
const NAMED_METRICS = new Set(["fee", "minimum", "maximum", "other", "points"]);
const RANGE_RE = /\b((?:19|20)\d\d)(?:\s*[-–]\s*(\d{2}|\d{4}))?\b/;
const TERM_RE = /(\d+)\s*-?\s*(month|mo|year|yr)/i;
const YEARS_VALUE_RE = /\b(19|20)\d\d\s*(?:[-–]\s*\d{2,4})?\b.*model|model.*\b(19|20)\d\d/i;
const VARIANT_WORDS = ["jumbo", "special", "business", "ira", "roth", "traditional", "fixed", "variable", "regular", "rewards", "platinum",
  "refinance", "purchase", "heloc", "line of credit", "kids", "health", "money market", "high-yield", "holiday", "launchpad", "bright",
  "you name it", "share", "checking", "1st rate", "free", "boat", "atv", "home improvement", "personal"];
const FOOTNOTE_RE = /(?<=%)\d+$/;
const YEARS_RE = /\b(?:model\s*)?years?\b/i;

export interface Fact {
  product: string; family: string; qualifiers: Record<string, string>; metric: string; value: string;
  url: string; pageType: string; effective: string | null; published: string | null; snapshotId: string; caption: string;
  categories: string[];   // so BM25Index can apply the category bonus
  text: string;           // "product (family) | q: v | metric: value"
}

const norm = (s: string): string => s.toLowerCase().replace(/[^a-z0-9.%$]+/g, " ").trim();

export function factText(f: Pick<Fact, "product" | "family" | "qualifiers" | "metric" | "value">): string {
  const q = Object.entries(f.qualifiers).map(([k, v]) => `${k}: ${v}`).join("; ");
  return `${f.product} (${f.family}) | ${q} | ${f.metric}: ${f.value}`;
}
export const factIndexText = (f: Fact): string => `${f.caption} ${f.text}`;

/** The same fact = same family, metric, term, product variant words and remaining qualifier values (values, not names). */
export function factKey(f: Fact): string {
  const values = Object.entries(f.qualifiers).filter(([k, v]) => !YEARS_RE.test(k) && !YEARS_VALUE_RE.test(v)).map(([, v]) => v);
  let term: string | null = null;
  const rest: string[] = [];
  for (const v of values) {
    const m = TERM_RE.exec(v);
    if (m && term === null) term = `${m[1]} ${m[2]!.toLowerCase().startsWith("mo") ? "month" : "year"}`;
    else rest.push(norm(v));
  }
  if (term === null) {
    const m = TERM_RE.exec(f.product);
    if (m) term = `${m[1]} ${m[2]!.toLowerCase().startsWith("mo") ? "month" : "year"}`;
  }
  const p = f.product.toLowerCase();
  const variant = VARIANT_WORDS.filter((w) => p.includes(w));
  const name = NAMED_METRICS.has(f.metric) ? norm(f.product) : "";
  return JSON.stringify([f.family, f.metric, term, variant, name, [...rest].sort()]);
}

/** Model-year range (low, high) from the qualifiers or product ("2024-27" -> [2024, 2027]); null when the fact has none. */
export function factYears(f: Fact): [number, number] | null {
  for (const text of [...Object.values(f.qualifiers), f.product]) {
    if (!/model|year/i.test(text) && !YEARS_VALUE_RE.test(text)) continue;
    const m = RANGE_RE.exec(text);
    if (!m) continue;
    const a = +m[1]!;
    const b = m[2];
    if (b === undefined) return /older|earlier|prior/i.test(text) ? [1900, a] : [a, a];
    const bb = b.length === 4 ? +b : +(String(a).slice(0, 2) + b);
    return [Math.min(a, bb), Math.max(a, bb)];
  }
  return null;
}

// ---------------------------------------------------------------- tables
export interface TableInfo { url: string; title: string; heading: string; caption: string; table: string; note: string; effective: string | null; after: string }

export function pageTables(url: string, title: string, markdown: string): TableInfo[] {
  const out: TableInfo[] = [];
  for (const [, section] of splitSections(markdown)) {
    const [heading, body] = splitHeading(section);
    const blocks = blocksOf(cleanText(body, isForm(body)));
    blocks.forEach((b, i) => {
      if (!b.trimStart().startsWith("|") || b.split("\n").filter((l) => l.trim()).length < 3) return;
      let caption = "";
      for (let j = i - 1; j >= 0; j--) if (!blocks[j]!.trimStart().startsWith("|")) { caption = blocks[j]!; break; }
      caption = caption ? caption.split("\n").at(-1)!.trim() : heading;
      const after = blocks.slice(i + 1, i + 3).join(" ");
      let noteSrc = after;
      if (NOTE_FIX) {
        const below: string[] = [];
        for (const b2 of blocks.slice(i + 1, i + 3)) { if (b2.trimStart().startsWith("|")) break; below.push(b2); }
        noteSrc = below.join(" ");
      }
      const note = noteSrc.split(/(?<=\.)\s/).map((s) => s.trim()).find((s) => EFFECTIVE_RE.test(s)) ?? "";
      out.push({ url, title, heading, caption, table: b, note, effective: effectiveOf(note), after: after.slice(0, 400) });
    });
  }
  return out;
}

export const tableKey = (t: TableInfo): string => createHash("sha1").update(t.caption + "\n" + t.table).digest("hex");

function tableMessage(t: TableInfo): string {
  const nonce = tableKey(t).slice(0, 12);
  return `Input id: ${nonce}\n<table id="${nonce}">\nPage: ${t.url}\nTitle: ${t.title}\nHeading: ${t.heading}\nCaption: ${t.caption}\n\n${t.table}\n\nNote: ${t.note}\n</table>`;
}

/** Runs async work with a concurrency limit, keeping result order. */
export async function pool<T, R>(items: T[], limit: number, fn: (x: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) { const i = next++; out[i] = await fn(items[i]!); }
  }));
  return out;
}

export class FactExtractor {
  cache: Record<string, RawFact[]> = {};
  private readonly model: string;
  private readonly cachePath: string | null;
  private readonly workers: number;
  constructor(model: string, cachePath: string | null, seedPaths: string[] = [], workers = 8) {
    this.model = model; this.cachePath = cachePath; this.workers = workers;
    for (const p of [...seedPaths, ...(cachePath ? [cachePath] : [])]) if (existsSync(p)) Object.assign(this.cache, JSON.parse(readFileSync(p, "utf8")));
  }

  /** Facts for one table, or null when the call failed (failures are not cached, so a later run retries). */
  private async one(t: TableInfo): Promise<RawFact[] | null> {
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        const out = await askJson({ model: this.model, instructions: prompts.fact_developer, input: tableMessage(t), schema: FactSchema,
          name: "table_facts", cacheKey: "dupaco-facts-v1", maxTokens: 6000, timeoutMs: 90000 });
        return out.facts;
      } catch (e) {
        if (attempt === 2) console.error(`[ts_solution] fact extraction failed for ${t.url}: ${(e as Error).name}: ${(e as Error).message}`);
        if ((e as Error).name === "BudgetExceeded") return null;
      }
    }
    return null;
  }

  async extract(tables: TableInfo[]): Promise<void> {
    const todo = new Map<string, TableInfo>();
    for (const t of tables) { const k = tableKey(t); if (!(k in this.cache) && !todo.has(k)) todo.set(k, t); }
    if (!todo.size) return;
    const keys = [...todo.keys()];
    const results = await pool([...todo.values()], this.workers, (t) => this.one(t));
    keys.forEach((k, i) => { if (results[i]) this.cache[k] = results[i]!; });
    if (this.cachePath) { mkdirSync(dirname(this.cachePath), { recursive: true }); writeFileSync(this.cachePath, JSON.stringify(this.cache)); }
  }

  factsFor(t: TableInfo, snapshotId: string, published: string | null): Fact[] {
    return (this.cache[tableKey(t)] ?? []).map((f) => {
      const base = { product: f.product, family: f.family, qualifiers: Object.fromEntries(f.qualifiers.map((q) => [q.name, q.value])), metric: f.metric,
        value: f.value.trim().replace(FOOTNOTE_RE, "") };
      return { ...base, url: t.url, pageType: pageRank(t.url), effective: t.effective, published, snapshotId, caption: t.caption,
        categories: [f.family], text: factText(base) };
    });
  }
}

// ---------------------------------------------------------------- winner and grouping
const negDate = (d: string | null): string => (d ? [...d].map((c) => String.fromCharCode(255 - c.charCodeAt(0))).join("") : "ÿ");

/** Most trusted page type first, then the latest effective date, then the latest publish date. */
export function winner(occ: Fact[]): Fact {
  const key = (f: Fact): [number, string, string] => [RANK_ORDER[f.pageType]!, negDate(f.effective), negDate(f.published)];
  const less = (a: [number, string, string], b: [number, string, string]) => a[0] !== b[0] ? a[0] < b[0] : a[1] !== b[1] ? a[1] < b[1] : a[2] < b[2];
  let best = occ[0]!;
  for (const f of occ.slice(1)) if (less(key(f), key(best))) best = f;
  return best;
}

/** Occurrences of the same fact: same key, and model-year ranges that overlap; facts without model years form their own group. */
export function groupFacts(facts: Fact[]): Fact[][] {
  const byKey = new Map<string, Fact[]>();
  for (const f of facts) { const k = factKey(f); let a = byKey.get(k); if (!a) byKey.set(k, (a = [])); a.push(f); }
  const out: Fact[][] = [];
  for (const occ of byKey.values()) {
    const noYears = occ.filter((f) => factYears(f) === null);
    if (noYears.length) out.push(noYears);
    const ranged = occ.filter((f) => factYears(f) !== null);
    if (!ranged.length) continue;
    const top = Math.min(...ranged.map((f) => RANK_ORDER[f.pageType]!));
    const ykey = (y: [number, number]) => `${y[0]},${y[1]}`;
    const anchors: Array<[number, number]> = [];
    for (const f of ranged) if (RANK_ORDER[f.pageType] === top && !anchors.some((a) => ykey(a) === ykey(factYears(f)!))) anchors.push(factYears(f)!);
    const clusters = new Map<string, Fact[]>(anchors.map((a) => [ykey(a), []]));
    for (const f of ranged) {
      const [lo, hi] = factYears(f)!;
      const overlaps = anchors.filter((a) => Math.min(hi, a[1]) >= Math.max(lo, a[0])).map((a) => [Math.min(hi, a[1]) - Math.max(lo, a[0]), a] as [number, [number, number]]);
      const own = clusters.get(ykey([lo, hi]));
      if (own) own.push(f);
      else if (overlaps.length) {
        const best = overlaps.reduce((m, o) => (o[0] > m[0] || (o[0] === m[0] && (o[1][0] > m[1][0] || (o[1][0] === m[1][0] && o[1][1] > m[1][1]))) ? o : m));
        clusters.get(ykey(best[1]))!.push(f);
      } else { const k = ykey([lo, hi]); let a = clusters.get(k); if (!a) clusters.set(k, (a = [])); a.push(f); }
    }
    for (const c of clusters.values()) if (c.length) out.push(c);
  }
  return out;
}

/** One winner per fact group; also (winner, losing distinct values) for groups that disagree. */
export function resolve(facts: Fact[]): { winners: Fact[]; disagreements: Array<[Fact, string[]]> } {
  const winners: Fact[] = [], disagreements: Array<[Fact, string[]]> = [];
  for (const occ of groupFacts(facts)) {
    const w = winner(occ);
    winners.push(w);
    const other = [...new Set(occ.filter((f) => f.value !== w.value).map((f) => f.value))];
    if (other.length) disagreements.push([w, other]);
  }
  return { winners, disagreements };
}
