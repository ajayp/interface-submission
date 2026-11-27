// Count facts about the credit union itself (branches, employees, members, assets, counties) and answers to "how many" questions.
// Port of my_solution/count_facts.py. Fixed sentence patterns, no AI.
import { publishedDate } from "./chunker.ts";
import { pageRank } from "./tiers.ts";
import type { Page } from "./types.ts";

const NUM = "(\\d{1,3}(?:,\\d{3})+|\\d+(?:\\.\\d+)?)";
const QUANT = "(?:over|more than|nearly|almost|about|approximately)\\s+";
const rx = (s: string): RegExp => new RegExp(s, "gi");
export type Measure = "branches" | "employees" | "members" | "counties" | "assets";
const PATTERNS: Record<Measure, RegExp[]> = {
  branches: [
    rx(`\\bit has\\s+(?:${QUANT})?[\\d,]+\\s+employees and\\s+${NUM}\\s+branch office locations`),
    rx(`\\bdupaco(?:’s|'s)\\s+${NUM}\\s+(?:full-service\\s+)?branches\\b`),
    rx(`\\bdupaco (?:now )?operates\\s+${NUM}\\s+branches\\b`),
  ],
  employees: [
    rx(`\\bit has\\s+(?:${QUANT})?${NUM}\\s+employees and\\b`),
    rx(`\\bdupaco and its\\s+(?:${QUANT})?${NUM}\\s+employees\\b`),
    rx(`\\bthe credit union currently employs\\s+(?:${QUANT})?${NUM}\\s+employees\\b`),
  ],
  members: [
    rx(`\\bmembership (?:has grown to|totals)\\s+(?:${QUANT})?${NUM}\\b`),
    rx(`\\bdupaco and its\\s+(?:${QUANT})?[\\d,]+\\s+employees are proud to serve\\s+(?:${QUANT})?${NUM}\\s+members\\b`),
    rx(`\\bdupaco now operates\\s+\\d+\\s+branches and serves\\s+(?:${QUANT})?${NUM}\\s+members\\b`),
  ],
  counties: [rx(`\\bdupaco serves (?:residents|members) in\\s+${NUM}\\s+counties\\b`)],
  assets: [rx(`\\bmembership (?:has grown to|totals)\\s+(?:${QUANT})?[\\d,]+\\s+with assets exceeding\\s+\\$\\s?${NUM}\\s*billion`)],
};
export const TOPIC: Record<Measure, string> = {
  branches: "Number of Dupaco branch locations", employees: "Number of Dupaco employees", members: "Number of Dupaco members (membership)",
  assets: "Dupaco total assets", counties: "Number of counties Dupaco serves",
};
export const UNIT: Record<Measure, string> = { branches: "{} branches", employees: "{} employees", members: "{} members", assets: "${} billion", counties: "{} counties" };

export interface CountFact {
  measure: Measure; value: string; url: string; pageType: string; published: string | null; fetchedAt: string | null; sentence: string;
}

export function countFacts(pages: Page[]): CountFact[] {
  const out: CountFact[] = [];
  for (const p of pages) {
    const flat = p.markdown.replace(/\s+/g, " ");
    const pub = publishedDate(p.url, p.markdown);
    for (const [measure, rxs] of Object.entries(PATTERNS) as Array<[Measure, RegExp[]]>) {
      for (const r of rxs) for (const m of flat.matchAll(r)) {
        const v = m[1]!;
        if (measure === "branches" && parseInt(v.replaceAll(",", ""), 10) > 200) continue;
        out.push({ measure, value: v, url: p.url, pageType: pageRank(p.url), published: pub, fetchedAt: p.fetchedAt ?? null,
          sentence: flat.slice(Math.max(0, m.index! - 40), m.index! + m[0].length + 20) });
      }
    }
  }
  return out;
}

/** Most recently published statement; undated pages rank below every dated one. */
export function latest(facts: CountFact[]): CountFact {
  const key = (f: CountFact): [number, string, string] => [f.published !== null ? 1 : 0, f.published ?? "", f.fetchedAt ?? ""];
  let best = facts[0]!;
  for (const f of facts.slice(1)) {
    const a = key(f), b = key(best);
    if (a[0] > b[0] || (a[0] === b[0] && (a[1] > b[1] || (a[1] === b[1] && a[2] > b[2])))) best = f;
  }
  return best;
}

export function label(measure: Measure, value: string): string {
  return measure === "branches" ? `${value} branches (${value} branch office locations)` : UNIT[measure].replace("{}", value);
}

// ---- answering count questions
const ASK: Record<string, RegExp> = {
  branches: /\bhow many\b[^?]*\b(branch(es)?|branch (office )?locations|locations|offices)\b|\bnumber of (?:\w+\s+){0,2}(branch(es)?|branch (office )?locations|locations|offices)\b/i,
  employees: /\bhow many\b[^?]*\b(employees|people work|staff|team members|workers)\b|\bnumber of (?:\w+\s+){0,2}(employees|staff)\b/i,
  members: /\bhow many\b[^?]*\bmembers\b|\bnumber of (?:\w+\s+){0,2}members\b|\bmembership (size|count)\b/i,
  assets: /\b(total |in )?assets\b|\basset size\b/i,
};
const SCOPE_RE = /\b(in|near|around|within|across)\s+(?!(?:total|person|store|branch(?:es)?|general|all)\b)(?!(january|february|march|april|may|june|july|august|september|october|november|december)\b)[A-Za-z]|\blast year\b|\bATMs?\b|\bboard\b|\bvolunteer|\bpromoted\b|\bused\b|\bopen(ed)?\b|\bnew\b|\bclos/i;
const QUANT_RE = /\b(over|more than|nearly|almost|about|approximately|exceeding)\s+\$?\s?[\d,.]+\s*(billion)?\s*(employees|branch|$|with|members)?/i;
const YEAR_RE = /\b(19|20)\d\d\b/;

/** The measure a question asks about Dupaco as a whole, or null (sub-scopes and other counts go the normal way). */
export function countQuestion(question: string, websiteDate?: string | null): Measure | null {
  if (SCOPE_RE.test(question) || (YEAR_RE.test(question) && !websiteDate)) return null;
  for (const [measure, r] of Object.entries(ASK)) if (r.test(question)) return measure as Measure;
  return null;
}

export function answerText(f: CountFact): string {
  const m = QUANT_RE.exec(f.sentence);
  let q = m && f.measure !== "branches" ? m[1]!.toLowerCase() + " " : "";
  if (q === "exceeding ") q = "more than ";
  const when = f.published ? ` (published ${f.published})` : "";
  const what: Record<Measure, string> = {
    branches: `${f.value} branch office locations`, employees: `${q}${f.value} employees`, members: `${q}${f.value} members`,
    assets: `${q}$${f.value} billion in assets`, counties: `${f.value} counties`,
  };
  return `Dupaco has ${what[f.measure]}, according to its most recent news release or article on the website${when}.`;
}
