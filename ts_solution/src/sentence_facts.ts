// Rate facts stated in sentences (outside tables), for conflicts(). One small model call per distinct rate sentence labels it
// (offer / example / education / other) and extracts product, rate type, term, tier, value, intro, expired and bound. Only exact
// "offer" values are compared. Port of my_solution/sentence_facts.py (prompt text comes from data/prompts.json).
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { z } from "zod";
import prompts from "../data/prompts.json" with { type: "json" };
import { pool } from "./facts.ts";
import { productName, sameRules, termMonths, tierOf, winnerTiers, words, type RateFact } from "./fact_match.ts";
import { fmtG } from "./table_parse.ts";
import { askJson } from "./openai.ts";
import { pageRank } from "./tiers.ts";
import type { Page } from "./types.ts";

const SENTENCE_CONTEXT = (process.env.MY_SOLUTION_SENTENCE_CONTEXT ?? "1") === "1";
const CONTEXT_CHARS = 300;
const RATE_SENT_RE = /\d+(?:\.\d+)?\s*%[^.]{0,40}?(APR|APY|annual percentage|dividend|rate|interest)|(APR|APY|rate|dividend)[^.%]{0,60}?\d+(?:\.\d+)?\s*%/i;
const LINK_RE = /\]\((?:https?:\/\/)[^)]*\)/g;

export const SentenceSchema = z.object({
  rates: z.array(z.object({
    kind: z.enum(["offer", "example", "education", "other"]), product: z.string(), rate_type: z.enum(["APR", "APY", "dividend rate", "rate"]),
    term: z.string(), tier: z.string(), value: z.string(), intro: z.boolean(), expired: z.boolean(),
    bound: z.enum(["exact", "minimum", "maximum", "as_low_as", "up_to", "range"]), value_high: z.string(),
  })),
});
export type ExtractedRate = z.infer<typeof SentenceSchema>["rates"][number];

export interface SentenceEntry { text: string; title: string; heading: string; before: string; pages: Array<[string, string | null]> }

/** Distinct rate sentences -> {text, title, heading, before, pages}. The key is the sentence plus the text just before it. */
export function rateSentences(pages: Page[]): Map<string, SentenceEntry> {
  const out = new Map<string, SentenceEntry>();
  for (const p of pages) {
    let heading = "";
    let recent: string[] = [];   // the last two sentences or lines of this page that are not headings or table rows
    for (const line of (p.markdown ?? "").split("\n")) {
      const s = line.trim();
      if (s.startsWith("#")) { heading = s.replace(/^[# ]+/, "").trim(); recent = []; continue; }
      if (s.startsWith("|")) continue;
      for (const sent of s.replace(LINK_RE, "]").split(/(?<=[.!?])\s+/)) {
        if (RATE_SENT_RE.test(sent) && sent.length < 700) {
          const before = SENTENCE_CONTEXT ? recent.join(" ").slice(-CONTEXT_CHARS) : "";
          const key = sent.trim() + (before ? "\u001f" + before : "");
          let e = out.get(key);
          if (!e) out.set(key, (e = { text: sent.trim(), title: p.title ?? "", heading, before, pages: [] }));
          e.pages.push([p.url, p.fetchedAt ?? null]);
        }
        if (sent.trim()) recent = [...recent, sent.trim()].slice(-2);
      }
    }
  }
  return out;
}

export type SentenceCache = Record<string, ExtractedRate[]>;

export function loadSentenceCache(...paths: string[]): SentenceCache {
  const cache: SentenceCache = {};
  for (const p of paths) if (existsSync(p)) Object.assign(cache, JSON.parse(readFileSync(p, "utf8")));
  return cache;
}
export function saveSentenceCache(path: string, cache: SentenceCache): void { mkdirSync(dirname(path), { recursive: true }); writeFileSync(path, JSON.stringify(cache)); }

/** Fills `cache` for sentences not in it yet; failed calls are left out (retried next time). */
export async function extract(sentences: Map<string, SentenceEntry>, model: string, cache: SentenceCache): Promise<SentenceCache> {
  const todo = [...sentences].filter(([k]) => !(k in cache));
  const one = async ([, e]: [string, SentenceEntry]): Promise<ExtractedRate[] | null> => {
    const before = e.before ? `Text just before: ${e.before}\n` : "";
    const msg = `Page title: ${e.title}\nHeading above: ${e.heading}\n${before}Sentence: ${e.text}`;
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        return (await askJson({ model, instructions: prompts.sentence_system + (SENTENCE_CONTEXT ? prompts.sentence_context_rule : ""), input: msg, schema: SentenceSchema,
          name: "sentence_rates", cacheKey: SENTENCE_CONTEXT ? "dupaco-sentrates-v4" : "dupaco-sentrates-v3", maxTokens: 800, timeoutMs: 60000 })).rates;
      } catch (e2) { if ((e2 as Error).name === "BudgetExceeded") return null; }
    }
    return null;
  };
  const results = await pool(todo, 8, one);
  todo.forEach(([k], i) => { if (results[i]) cache[k] = results[i]!; });
  return cache;
}

export function toFacts(sentences: Map<string, SentenceEntry>, extracted: SentenceCache): RateFact[] {
  const out: RateFact[] = [];
  for (const [text, rates] of Object.entries(extracted)) {
    const e = sentences.get(text);
    if (!e) continue;
    for (const r of rates) {
      if (r.kind !== "offer" || r.bound !== "exact") continue;   // floors, caps, "as low as", "up to", ranges are not one rate
      const m = /\d+(?:\.\d+)?/.exec(r.value);
      if (!m) continue;
      const desc = `${r.product} ${r.term} ${r.tier}`;
      for (const [url, fetched] of e.pages) {
        out.push({ url, pageType: pageRank(url), tableId: "s:" + createHash("sha1").update(text).digest("hex").slice(0, 10), effective: null, fetchedAt: fetched,
          product: r.product, qualifiers: [], column: r.rate_type, raw: e.text, value: `${fmtG(parseFloat(m[0]))}%`, metric: r.rate_type,
          period: r.intro ? "intro" : null, term: termMonths(desc), tier: tierOf(desc), years: null, asLowAs: false, heading: e.heading, caption: e.title,
          after: "", headers: [], rowCells: [text], expired: r.expired });
      }
    }
  }
  return out;
}

/** Tables keep the rule matcher; a pair involving a sentence also needs at least two meaningful product words on the shorter name. */
export function sameStrict(a: RateFact, b: RateFact): boolean {
  if (!(a.tableId.startsWith("s:") || b.tableId.startsWith("s:"))) return sameRules(a, b);
  const size = (f: RateFact): number => { const [e, r] = words(productName(f)); return r.size + [...e].reduce((n, w) => n + w.split(" ").length, 0); };
  return sameRules(a, b) && Math.min(size(a), size(b)) >= 2;
}

/** Trust order, except that a value the page itself says has ended always loses. */
export function winner(occ: RateFact[]): RateFact {
  const live = occ.filter((f) => !f.expired);
  return winnerTiers(live.length ? live : occ);
}
