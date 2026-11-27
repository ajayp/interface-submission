// conflicts() v2: contradictions in the newest website copy, found without guessing. Port of my_solution/conflicts_v2.py.
//  1. Tables are read by code (table_parse.ts). 2. Rate sentences are read by one small model call each (cached).
//  3. "Same fact?" is decided without the numbers (fact_match.ts). 4. The winner: rate sheet > product page > promo page > other, then the later
//  effective date, then the later fetch date; a value the page itself says has ended always loses.
import { TOPIC, countFacts, label, latest, type Measure } from "./count_facts.ts";
import { NOISE_QUALIFIERS, TERM_RE, candidatePairs, conflictsFrom, toFact, type RateFact } from "./fact_match.ts";
import { extract, rateSentences, sameStrict, toFacts, winner, type SentenceCache } from "./sentence_facts.ts";
import { parsePages } from "./table_parse.ts";
import type { Conflict, Snapshot, Source } from "./types.ts";

const PLAIN_TOPIC = (process.env.MY_SOLUTION_PLAIN_TOPIC ?? "1") === "1";
const PAGE_WORD: Record<string, string> = { rate_sheet: "rate sheet", product: "product page", promo: "promotion page", secondary: "secondary page" };

const singular = (w: string): string => (w.endsWith("s") && !w.endsWith("ss") && w.length > 3 ? w.slice(0, -1) : w);
const split = (s: string): string[] => s.split(/\s+/).filter(Boolean);
const TERM_G = new RegExp(TERM_RE.source, "gi");

/** The fact as a member would say it: "60-month auto loan APR". */
function plain(f: RateFact): string {
  const text = [f.product, ...f.qualifiers.map(([, v]) => String(v))].join(" ");
  const m = TERM_RE.exec(text);
  const term = m ? `${m[1]}-${m[2]!.toLowerCase().startsWith("y") ? "year" : "month"}` : "";
  let name = f.product.replace(TERM_G, " ").toLowerCase();
  name = name.replace(/[^a-z0-9&' ]+/g, " ");
  let names: string[] = [];
  if (name.includes(" & ") || name.includes(" and ")) {
    const mm = / & | and /.exec(name)!;
    const left = name.slice(0, mm.index), right = name.slice(mm.index + mm[0].length);
    const rw = split(right);
    if (rw.length) { const noun = singular(rw.at(-1)!); names = [[...split(left), noun].join(" "), [...rw.slice(0, -1), noun].join(" ")]; }
  }
  if (!names.length) { const w = split(name); names = w.length ? [[...w.slice(0, -1), singular(w.at(-1)!)].join(" ")] : []; }
  const p = [term, names[0] ?? "", f.metric].filter(Boolean).join(" ");
  return p + (names.length > 1 ? "; " + names.slice(1).join("; ") : "");
}

function topic(f: RateFact): string {
  const quals = f.qualifiers.filter(([k, v]) => !NOISE_QUALIFIERS.test(k) && v !== f.product).map(([, v]) => v);
  const period = ({ intro: " (introductory)", after_promo: " (after the promotion)" } as Record<string, string>)[f.period ?? ""] ?? "";
  const product = f.product.length <= 80 ? f.product : (() => { const c = f.product.slice(0, 80); const i = c.lastIndexOf(" "); return i < 0 ? c : c.slice(0, i); })();
  const table = [product, quals.join(", "), f.metric + period].join(" ").replaceAll("  ", " ").trim();
  const pl = PLAIN_TOPIC ? plain(f) : "";
  return pl && pl.toLowerCase() !== table.toLowerCase() ? `${pl} (${table})` : table;
}

function reason(w: RateFact, occ: RateFact[]): string {
  const others = [...new Set(occ.filter((f) => f.value !== w.value).map((f) => f.url))].sort();
  const dated = w.effective ? `, effective ${w.effective}` : "";
  const ended = occ.some((f) => f.expired) ? " The other value is from an offer the page says has ended." : "";
  return `The ${PAGE_WORD[w.pageType] ?? "page"} ${w.url}${dated} is the most trusted source for this fact; ${others.length} other page(s) show a different value (older or less authoritative copies).${ended}`;
}

const cmpList = (a: string[], b: string[]): number => { for (let i = 0; i < Math.min(a.length, b.length); i++) if (a[i]! !== b[i]!) return a[i]! < b[i]! ? -1 : 1; return a.length - b.length; };

/** Contradictions in one website copy (call with the newest). `model` null = no model: tables and counts only. */
export async function buildConflicts(snapshot: Snapshot, model: string | null, sentenceCache: SentenceCache): Promise<Conflict[]> {
  const facts = parsePages(snapshot.pages, snapshot.snapshotId).map(toFact).filter((f): f is RateFact => f !== null);
  if (model) {
    const sentences = rateSentences(snapshot.pages);
    await extract(sentences, model, sentenceCache);
    facts.push(...toFacts(sentences, sentenceCache));
  }
  const out: Conflict[] = [];
  for (const c of conflictsFrom(facts, candidatePairs(facts), sameStrict)) {
    const w = winner(c.occ);
    const urls = [w.url, ...[...new Set(c.occ.map((f) => f.url))].filter((u) => u !== w.url).sort()];
    out.push({ topic: topic(w), values: [w.value, ...c.values.filter((v) => v !== w.value)], sources: urls.map((u): Source => ({ url: u, snapshotId: snapshot.snapshotId })),
      resolution: w.value, reason: reason(w, c.occ) });
  }
  out.push(...countConflicts(snapshot));
  out.sort((a, b) => (a.topic !== b.topic ? (a.topic < b.topic ? -1 : 1) : cmpList(a.values, b.values)));
  return out;
}

/** Branches, employees, members, assets, counties: every value the site states for the whole credit union; the newest dated wins. */
export function countConflicts(snapshot: Snapshot): Conflict[] {
  const facts = countFacts(snapshot.pages);
  const out: Conflict[] = [];
  for (const measure of Object.keys(TOPIC) as Measure[]) {
    const fs = facts.filter((f) => f.measure === measure);
    if (new Set(fs.map((f) => f.value)).size < 2) continue;
    const w = latest(fs);
    const counts = new Map<string, number>();
    for (const f of fs) if (f.value !== w.value) counts.set(f.value, (counts.get(f.value) ?? 0) + 1);
    const others = [...counts].sort((a, b) => b[1] - a[1]).map(([v]) => v);   // stable: ties keep first-seen order, like Counter.most_common
    const urls = [w.url, ...[...new Set(fs.filter((f) => f.value !== w.value).map((f) => f.url))].sort().slice(0, 15)];
    out.push({ topic: TOPIC[measure], values: [w.value, ...others].map((v) => label(measure, v)), sources: urls.map((u): Source => ({ url: u, snapshotId: snapshot.snapshotId })),
      resolution: label(measure, w.value),
      reason: `Each news release and blog post repeats the count of its own day. The most recently published one (${w.url}, ${w.published}) says ${label(measure, w.value)}; ${others.length} older value(s) appear on ${new Set(fs.map((f) => f.url)).size - 1} other page(s).` });
  }
  return out;
}
