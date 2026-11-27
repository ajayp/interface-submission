// The knowledge system: ingest -> answer -> conflicts. Port of my_solution/solution.py (default switches; same MY_SOLUTION_* names).
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chunkPage, normBlock, type Chunk } from "./chunker.ts";
import { buildChunks } from "./corpus.ts";
import { answerText, countFacts, countQuestion, latest, type CountFact } from "./count_facts.ts";
import { MONTH_YEAR_RE, describe, setReference, targetDate, yearlessMonth } from "./dates.ts";
import { DecisionsUnderstanding, type QU } from "./decisions.ts";
import { WindowIndex, prefetchQuery } from "./embed_index.ts";
import { FactExtractor, groupFacts, pageTables, winner, type Fact } from "./facts.ts";
import { AnswerLLM } from "./llm.ts";
import { PAGE_TYPE_LABEL, buildUserMessage, developerMessageFor, historyDeveloperMessage, stateDateOn, type Excerpt } from "./prompt.ts";
import { BM25Index } from "./search.ts";
import { SpellFix } from "./spellfix.ts";
import { expansion } from "./synonyms.ts";
import { SECONDARY, pageRank } from "./tiers.ts";
import type { Answer, Conflict, KnowledgeSystem, Snapshot, Source } from "./types.ts";
import { publishedDate } from "./chunker.ts";
import { buildConflicts } from "./conflicts_v2.ts";
import { loadSentenceCache, saveSentenceCache, type SentenceCache } from "./sentence_facts.ts";

void chunkPage; void normBlock;
const env = (name: string, dflt: string): string => process.env[`MY_SOLUTION_${name}`] ?? dflt;
const HERE = dirname(fileURLToPath(import.meta.url));

const TOP_K = Number(env("TOP_K", "8"));
const SECONDARY_SLOTS = 2;
const FACT_K = 12;
const SYNONYM_WEIGHT = 0.5, CAT_BOOST = 10.0;
const RANK_ORDER: Record<string, number> = { rate_sheet: 0, product: 1, promo: 2, secondary: 3 };
const SPELLFIX = env("SPELLFIX", "1") !== "0";
const HYBRID_WINDOWS = env("HYBRID", "windows") === "windows";
const EMBED_MISSING = env("EMBED_MISSING", "1") === "1";
const EMBED_PREFETCH = env("EMBED_PREFETCH", "1") === "1";
const WINDOW_EXTRA_BY_INTENT: Record<string, number> = { eligibility: 6, list: 6, fact_about_dupaco: 6, rate: 0, fee: 0 };
const WINDOW_EXTRA_DEFAULT = 3;
const HOURS_SCHEDULES = env("HOURS_SCHEDULES", "1") === "1";
const HOURS_SCHEDULE_EXTRA = 5;
const SAMENESS_RE = /\b(same|differ\w*|vary|varies|varying|uniform|consistent|identical)\b/i;
const SCHED_TIME_RE = /\d{1,2}(?::\d\d)?\s*(?:a\.?m\.?|p\.?m\.?)/gi;
const SCHED_DAY_RE = /\b(mon|tue|wed|thu|fri|sat|sun)/i;
const HOURS_EFFORT = process.env.MY_SOLUTION_HOURS_EFFORT || undefined;
const VALUE_INTENTS = ["rate", "fee"];
const VALUE_QUESTION_RE = /\b(rates?|apr|apy|dividend|interest|fees?|costs?|charges?|price)\b/i;
const VALUE_NUM_RE = /\d+(?:\.\d+)?\s*%|\$\s?\d[\d,]*(?:\.\d+)?/;
const REFUSE_BEFORE_FIRST = env("REFUSE_BEFORE_FIRST", "1") === "1";
const HISTORY = env("HISTORY", "1") === "1";
const HISTORY_FACTS_PER_COPY = 6, HISTORY_FACT_LINES = 16, HISTORY_PIECES_PER_COPY = 4, HISTORY_PIECES = 8, HISTORY_WINDOW_PIECES = 6;
const HISTORY_WINDOWS = env("HISTORY_WINDOWS", "1") === "1";
const DATE_NOTE_EXPLAIN = env("DATE_NOTE_EXPLAIN", "1") === "1";
const STATE_DATE_SKIP_CHANGE = env("STATE_DATE_SKIP_CHANGE", "1") === "1";
const CITE_SAME_VALUE = env("CITE_SAME_VALUE", "1") === "1";
const CITE_SAME_VALUE_MAX = 4;
const DISTINCT_VALUE_RE = /\d+(?:\.\d+)?\s*%|\$\s?\d[\d,]*(?:\.\d+)?|\b\d[\d-]{6,}\d\b/g;
const METRIC_FIRST = env("METRIC_FIRST", "1") === "1";
const STRIP_NOT_LISTED = env("STRIP_NOT_LISTED", "1") === "1";
const COUNT_ANSWERS = env("COUNT_ANSWERS", "1") === "1";
const METRIC_FOR_ASKED: Record<string, string[]> = { "interest rate": ["rate", "interest rate"], rate: ["rate", "interest rate"], apr: ["APR"], apy: ["APY"] };
const NOT_LISTED_RE = /\b(isn['’]t|is not|aren['’]t|are not|wasn['’]t|was not|not)\s+(listed|provided|included|shown|stated|available|specified|given|published)\b|\bdo(es)?(n['’]t| not)\s+(list|provide|include|state|show|specify|publish)\b|\bI don['’]t know\b/i;

export const REFUSAL = "I don't know. That isn't listed on Dupaco's website, so please contact Dupaco directly.";
const FAILED_PREFIX = "LLM call failed: ";
const TIMEOUT_TEXT = "The language model did not respond in time, so no answer was produced. This was a system timeout and says nothing about what the website lists. Please try again.";
const ERROR_TEXT = "The language model call failed, so no answer was produced. This was a system error and says nothing about what the website lists. Please try again.";
const BEFORE_FIRST_REFUSAL = "I don't know. Dupaco's website copies on file start after that date, so I can't say how the website looked then. Please contact Dupaco directly.";

type Piece = Chunk | Fact;
type Hit<T extends Piece = Piece> = [number, T, string[]];
interface Copy { takenOn: string; snapshotId: string; index: BM25Index<Chunk> }

const words = (s: string): string[] => s.split(/\s+/).filter(Boolean);
const normText = (s: string): string => words(s).join(" ").toLowerCase();
const isFact = (p: Piece): p is Fact => "product" in p;

export function stripNotListed(text: string): string {
  const parts = text.trim().split(/(?<=[.!?])\s+/);
  const keep = parts.filter((p) => !(NOT_LISTED_RE.test(p) && !VALUE_NUM_RE.test(p)));
  const rest = keep.join(" ");
  return keep.length && VALUE_NUM_RE.test(rest) && keep.length < parts.length ? rest : text;
}

function searchText(question: string, qu: QU | null, useKeywords = true): string {
  if (!qu || !useKeywords) return question;
  const extra = [...(qu.keywords ?? []), qu.product ?? "", qu.tier ?? ""];
  return question + " " + extra.filter(Boolean).join(" ");
}

function qualifierPatterns(qu: QU | null): RegExp[] {
  if (!qu) return [];
  const pats: RegExp[] = [];
  const m = /(\d+)\s*-?\s*(month|year)/i.exec(qu.term ?? "");
  if (m) pats.push(new RegExp(`\\b${m[1]}[\\s-]*${m[2]}`, "i"));
  return pats;
}

export class Knowledge implements KnowledgeSystem {
  readonly llm = new AnswerLLM();
  readonly useLlm: boolean;
  readonly useFacts: boolean;
  private readonly boost = "tiers";
  copies: Copy[] = [];
  private newest: Snapshot | null = null;
  private counts = new Map<string, CountFact[]>();
  private readonly qu: DecisionsUnderstanding | null;
  private readonly spell: SpellFix | null;
  private readonly extractor: FactExtractor | null;
  private factIndex = new Map<string, [Fact[], BM25Index<Fact>]>();
  private windows = new Map<string, WindowIndex | null>();
  private cache = new Map<string, Answer>();
  private warmed = false;

  constructor(opts: { useFacts?: boolean } = {}) {
    this.useLlm = this.llm.available();
    this.useFacts = (opts.useFacts ?? true) && this.llm.available();
    const dec = process.env.MY_SOLUTION_QU_DEC_CACHE;
    this.qu = this.llm.available() ? new DecisionsUnderstanding(dec ? resolve(dec) : null) : null;
    this.spell = SPELLFIX ? new SpellFix() : null;
    const dataCache = join(HERE, "..", "data", "facts_cache.json");
    const own = process.env.MY_SOLUTION_FACT_CACHE ?? join(HERE, "..", ".cache", "facts.json");
    this.extractor = this.useFacts ? new FactExtractor(this.llm.model, resolve(own), existsSync(dataCache) ? [dataCache] : []) : null;
  }

  // ------------------------------------------------------------------ ingest
  async ingest(snapshot: Snapshot): Promise<void> {
    if (this.spell) for (const p of snapshot.pages) this.spell.addText(p.markdown);
    const chunks = buildChunks(snapshot);
    const index = new BM25Index<Chunk>(chunks);
    this.copies.push({ takenOn: snapshot.takenOn, snapshotId: snapshot.snapshotId, index });
    setReference(this.copies.reduce((m, c) => (c.takenOn > m ? c.takenOn : m), ""));
    if (HYBRID_WINDOWS) await this.buildWindowIndex(snapshot.snapshotId, index, true);
    if (this.extractor) {
      const tables = snapshot.pages.flatMap((p) => pageTables(p.url, p.title, p.markdown).map((t) => [t, publishedDate(p.url, p.markdown)] as const));
      await this.extractor.extract(tables.map(([t]) => t));
      const facts = tables.flatMap(([t, pub]) => this.extractor!.factsFor(t, snapshot.snapshotId, pub));
      this.factIndex.set(snapshot.snapshotId, [facts, new BM25Index<Fact>(facts, (f) => `${f.caption} ${f.text}`)]);
    }
    this.copies.sort((a, b) => (a.takenOn < b.takenOn ? -1 : a.takenOn > b.takenOn ? 1 : 0));
    if (COUNT_ANSWERS) this.counts.set(snapshot.snapshotId, countFacts(snapshot.pages));
    if (!this.newest || snapshot.takenOn >= this.newest.takenOn) this.newest = snapshot;
    if (!this.warmed && (this.useLlm || this.qu)) { this.warmed = true; await this.llm.warmUp(); await this.qu?.warmUp(); }
  }

  private async buildWindowIndex(sid: string, index: BM25Index<Chunk>, embedMissing = false): Promise<void> {
    try {
      const wi = new WindowIndex(index.chunks);
      let left = wi.missing().length;
      if (left && embedMissing && EMBED_MISSING && this.llm.available()) {
        console.error(`[ts_solution] ${sid}: ${left} of ${wi.windows.length} windows have no vector (site changed or vector file incomplete); embedding them now`);
        try { left = await wi.build(true); } catch (e) { console.error(`[ts_solution] embedding the missing windows failed: ${(e as Error).message}`); left = wi.missing().length; }
      } else if (!left) left = await wi.build(false);
      if (left) { console.error(`[ts_solution] ${sid}: ${left} windows have no vector, so meaning search is off for this copy (keyword search only)`); this.windows.set(sid, null); }
      else this.windows.set(sid, wi);
    } catch (e) {
      console.error(`[ts_solution] window index unavailable: ${(e as Error).name}: ${(e as Error).message}`);
      this.windows.set(sid, null);
    }
  }

  // ------------------------------------------------------------------ question understanding and dates
  async understand(question: string): Promise<QU | null> {
    let qu = this.qu ? await this.qu.parse(question) : null;
    const extra = this.spellExtra(question);
    if (qu && extra) qu = { ...qu, synonym_tokens: [...new Set([...(qu.synonym_tokens ?? []), ...expansion(extra)])] };
    return qu;
  }

  private spellExtra(question: string): string {
    if (!this.spell) return "";
    const w = this.spell.extraWords(question);
    return w.length ? " " + w.join(" ") : "";
  }

  private askedDate(question: string, asOf: string | null | undefined, qu: QU | null): string | null {
    if (asOf) return asOf.slice(0, 10);
    if (qu) return qu.website_date;
    return targetDate(question, null);
  }

  copyFor(question: string, asOf: string | null | undefined, qu: QU | null): Copy {
    const date = this.askedDate(question, asOf, qu);
    const eligible = this.copies.filter((c) => date === null || c.takenOn <= date);
    return (eligible.length ? eligible : this.copies.slice(0, 1)).at(-1)!;
  }

  private beforeFirst(question: string, asOf: string | null | undefined, qu: QU | null): boolean {
    const date = this.askedDate(question, asOf, qu);
    return Boolean(date && this.copies.length && date < this.copies.reduce((m, c) => (c.takenOn < m ? c.takenOn : m), "9999"));
  }

  // ------------------------------------------------------------------ retrieval
  async retrieve(question: string, asOf?: string | null, k = TOP_K, quIn?: QU | null): Promise<Hit<Chunk>[]> {
    const qu = quIn === undefined ? await this.understand(question) : quIn;
    const hasQu = this.qu !== null;   // qu_mode "both" with a key, "none" without
    const index = this.copyFor(question, asOf, qu).index;
    const hits = index.search(searchText(question, qu, hasQu) + this.spellExtra(question), {
      k: k * 50, boost: this.boost, categories: hasQu ? qu?.categories ?? [] : [], catBoost: CAT_BOOST,
      qualifiers: qualifierPatterns(qu), qualBoost: 0, expansionTokens: qu?.synonym_tokens ?? [], expansionWeight: SYNONYM_WEIGHT });
    const byKey = new Map<string, string[]>();
    const unique: Hit<Chunk>[] = [];
    for (const [score, c] of hits) {
      const key = normText(c.text);
      const urls = byKey.get(key);
      if (urls) { if (!urls.includes(c.url)) urls.push(c.url); continue; }
      const fresh = [c.url];
      byKey.set(key, fresh);
      unique.push([score, c, fresh]);
    }
    let out = unique.slice(0, k);
    const reserve = Math.min(SECONDARY_SLOTS, k);
    const have = out.filter(([, c]) => pageRank(c.url) === SECONDARY).length;
    if (have < reserve) {
      const extra = unique.slice(k).filter(([, c]) => pageRank(c.url) === SECONDARY).slice(0, reserve - have);
      out = [...out.slice(0, k - extra.length), ...extra];
    }
    if (HYBRID_WINDOWS && k === TOP_K) out = [...out, ...(await this.windowExtras(question, out, asOf, qu))];
    if (HOURS_SCHEDULES && k === TOP_K && qu?.intent === "hours" && SAMENESS_RE.test(question)) out = [...out, ...this.scheduleExtras(question, out, asOf, qu)];
    return out;
  }

  /** Up to 5 best-ranked pieces whose text states a lobby or drive-up schedule (two clock times and a weekday right after the word). */
  private scheduleExtras(question: string, first: Hit<Chunk>[], asOf: string | null | undefined, qu: QU | null): Hit<Chunk>[] {
    const seen = new Set(first.map(([, c]) => normText(c.text)));
    const seenSched = new Set<string>();
    const out: Hit<Chunk>[] = [];
    const index = this.copyFor(question, asOf, qu).index;
    for (const [score, c] of index.search(searchText(question, qu, true), { k: 3000, boost: this.boost })) {
      const t = c.text;
      if (c.url.replace(/\/+$/, "").endsWith("/contact")) continue;
      const wins = [...t.matchAll(/\b(lobby|drive-?\s?(?:up|through|thru))/gi)].map((m) => t.slice(m.index! + m[0].length, m.index! + m[0].length + 160))
        .filter((w) => (w.match(SCHED_TIME_RE) ?? []).length >= 2 && SCHED_DAY_RE.test(w));
      if (!wins.length) continue;
      const sched = wins[0]!.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 70);
      const key = normText(t);
      if (seen.has(key) || seenSched.has(sched)) continue;
      seen.add(key); seenSched.add(sched);
      out.push([score, c, [c.url]]);
      if (out.length === HOURS_SCHEDULE_EXTRA) break;
    }
    return out;
  }

  /** Best overlapping windows by meaning that are not already in `first`; each carries its parent's page, title and dates. */
  private async windowExtras(question: string, first: Hit<Chunk>[], asOf: string | null | undefined, qu: QU | null): Promise<Hit<Chunk>[]> {
    const copy = this.copyFor(question, asOf, qu);
    if (!this.windows.has(copy.snapshotId)) await this.buildWindowIndex(copy.snapshotId, copy.index);
    const wi = this.windows.get(copy.snapshotId) ?? null;
    const n = WINDOW_EXTRA_BY_INTENT[qu?.intent ?? ""] ?? WINDOW_EXTRA_DEFAULT;
    if (!wi || n === 0) return [];
    let ranked;
    try { ranked = await wi.search(question, 40); } catch (e) { console.error(`[ts_solution] embedding search failed: ${(e as Error).name}: ${(e as Error).message}`); return []; }
    const seenTxt = new Set(first.map(([, c]) => normText(c.text)));
    const out: Hit<Chunk>[] = [];
    for (const { sim, chunkId, text } of ranked) {
      const key = normText(text);
      if (seenTxt.has(key) || [...seenTxt].some((t) => t.includes(key))) continue;
      seenTxt.add(key);
      const parent = wi.chunks[chunkId]!;
      out.push([sim, { ...parent, text }, [parent.url]]);
      if (out.length === n) break;
    }
    return out;
  }

  // ------------------------------------------------------------------ facts
  private asksValue(question: string, qu: QU | null): boolean { return qu ? VALUE_INTENTS.includes(qu.intent) : VALUE_QUESTION_RE.test(question); }

  /** Top-k facts of one website copy as [score, winning fact, urls]: only the winning value of each fact is kept, so stale values never reach the model. */
  factHits(question: string, snapshotId: string, qu: QU | null, k = FACT_K): Hit<Fact>[] {
    const entry = this.factIndex.get(snapshotId);
    if (!entry) return [];
    const hasQu = this.qu !== null;
    const found = entry[1].search(searchText(question, qu, hasQu) + this.spellExtra(question), {
      k: k * 6, boost: this.boost, categories: hasQu ? qu?.categories ?? [] : [], catBoost: CAT_BOOST, expansionTokens: qu?.synonym_tokens ?? [], expansionWeight: SYNONYM_WEIGHT });
    if (!found.length) return [];
    const scoreOf = new Map<Fact, number>(found.map(([s, f]) => [f, s]));
    const out: Hit<Fact>[] = [];
    for (const occ of groupFacts(found.map(([, f]) => f))) {
      const w = winner(occ);
      out.push([Math.max(...occ.map((f) => scoreOf.get(f)!)), w, [...new Set(occ.filter((f) => f.value === w.value).map((f) => f.url))]]);
    }
    out.sort((a, b) => b[0] - a[0]);
    if (METRIC_FIRST) {
      const asked = METRIC_FOR_ASKED[(qu?.rate_metric ?? "").toLowerCase()];
      if (asked && out.some((h) => asked.includes(h[1].metric))) out.sort((a, b) => Number(!asked.includes(a[1].metric)) - Number(!asked.includes(b[1].metric)) || b[0] - a[0]);
    }
    return out.slice(0, k);
  }

  // ------------------------------------------------------------------ answering
  async answer(question: string, asOf?: string | null): Promise<Answer> {
    const ans = await this.answerInner(question, asOf);
    if ((ans.conflictNote ?? "").startsWith(FAILED_PREFIX)) return { text: ans.text, sources: [], confident: true, conflictNote: ans.conflictNote };
    return ans;
  }

  private async answerInner(question: string, asOf?: string | null): Promise<Answer> {
    if (EMBED_PREFETCH && HYBRID_WINDOWS && this.llm.available()) prefetchQuery(question);   // runs while the labelling call is in flight
    const qu = await this.understand(question);
    if (HISTORY && this.useLlm && qu?.time_scope === "change") {
      const hkey = JSON.stringify([normText(question), "history", asOf ?? null]);
      const hit = this.cache.get(hkey);
      if (hit) return hit;
      const ans = await this.historyAnswer(question, asOf, qu);
      if (ans) { this.cache.set(hkey, ans); return ans; }   // null: fewer than two copies, nothing found, or not confident -> ordinary path
    }
    if (REFUSE_BEFORE_FIRST && this.beforeFirst(question, asOf, qu)) return { text: BEFORE_FIRST_REFUSAL, sources: [], confident: false };
    const copy = this.copyFor(question, asOf, qu);
    const key = JSON.stringify([normText(question), copy.snapshotId, asOf ?? null]);
    const cached = this.cache.get(key);
    if (cached) return cached;
    const measure = COUNT_ANSWERS ? countQuestion(question, qu?.website_date || asOf) : null;
    if (measure) {
      const fs = (this.counts.get(copy.snapshotId) ?? []).filter((f) => f.measure === measure);
      if (fs.length) {
        const w = latest(fs);
        const ans: Answer = { text: answerText(w), sources: [{ url: w.url, snapshotId: copy.snapshotId }], confident: true };
        this.cache.set(key, ans);
        return ans;
      }
    }
    const asked = this.askedNote(question, asOf, qu);
    if (this.extractor && this.useLlm && this.asksValue(question, qu)) {
      const fh = this.factHits(question, copy.snapshotId, qu);
      if (fh.length) {
        const ans = await this.llmAnswer(question, fh, copy.takenOn, qu, asked);
        if (ans.confident) { this.cache.set(key, ans); return ans; }   // otherwise fall back to text RAG
      }
    }
    const hits = await this.retrieve(question, asOf, TOP_K, qu);
    if (!hits.length) return { text: REFUSAL, sources: [], confident: false };
    const ans = this.useLlm ? await this.llmAnswer(question, hits, copy.takenOn, qu, asked) : topChunk(hits);
    if (!(ans.conflictNote ?? "").startsWith(FAILED_PREFIX)) this.cache.set(key, ans);   // a failure is not remembered: asking again retries
    return ans;
  }

  userMessage(question: string, hits: Hit[], takenOn: string, asked: string | null): string {
    const excerpts: Excerpt[] = hits.map(([, c], i) => ({ n: i + 1, pageType: PAGE_TYPE_LABEL[pageRank(c.url)], url: c.url, effective: c.effective, published: c.published, text: c.text }));
    const dated = takenOn !== this.copies.at(-1)!.takenOn ? takenOn : null;
    return buildUserMessage(question, excerpts, dated, asked);
  }

  /** The `Question date:` text for the answer step when the question is about a date, else null. */
  askedNote(question: string, asOf: string | null | undefined, qu: QU | null): string | null {
    if (!stateDateOn()) return null;
    if (STATE_DATE_SKIP_CHANGE && qu?.time_scope === "change") return null;
    const date = this.askedDate(question, asOf, qu);
    if (!date) return null;
    const assumed = !asOf && Boolean(yearlessMonth(question)) && !MONTH_YEAR_RE.test(question);
    let text = describe(question, date, Boolean(asOf));
    if (DATE_NOTE_EXPLAIN && !/\d{1,2}, \d{4}$/.test(text)) text += ` (read as ${date})`;
    return text + (assumed ? " (the question gave no year; the year was assumed)" : "");
  }

  private async llmAnswer(question: string, hits: Hit[], takenOn: string, qu: QU | null, asked: string | null): Promise<Answer> {
    let out;
    try {
      const intent = qu?.intent;
      out = await this.llm.ask(this.userMessage(question, hits, takenOn, asked), developerMessageFor(question, intent, Boolean(asked)), intent === "hours" ? HOURS_EFFORT : undefined);
    } catch (e) {
      const err = e as Error;
      console.error(`[ts_solution] LLM call failed: ${err.name}: ${err.message}`);
      // confident=false lets the facts path fall back to text search; answer() turns a final failure into a visible one
      return { text: err.name.toLowerCase().includes("timeout") ? TIMEOUT_TEXT : ERROR_TEXT, sources: [], confident: false, conflictNote: `${FAILED_PREFIX}${err.name}` };
    }
    if (!out.confident) return { text: REFUSAL, sources: [], confident: false };
    const asksValue = this.asksValue(question, qu);
    if (asksValue && !/\d/.test(out.answer)) return { text: REFUSAL, sources: [], confident: false };
    if (STRIP_NOT_LISTED && asksValue) out = { ...out, answer: stripNotListed(out.answer) };
    const used = out.used_excerpts.filter((n) => n >= 1 && n <= hits.length);
    if (!used.length) used.push(1);
    const sources: Source[] = [];
    const seen = new Set<string>();
    for (const n of used) { const [, c, urls] = hits[n - 1]!; for (const u of urls) if (!seen.has(u)) { seen.add(u); sources.push({ url: u, snapshotId: c.snapshotId }); } }
    if (CITE_SAME_VALUE) sources.push(...sameValueSources(out.answer, hits, used, seen));
    return { text: out.answer.trim(), sources, confident: true, conflictNote: out.conflict_note };
  }

  // ------------------------------------------------------------------ "what changed" questions
  async historyHits(question: string, asOf: string | null | undefined, qu: QU): Promise<Array<[number, Piece, string[], string[]]>> {
    const snaps = this.copies.filter((c) => !asOf || c.takenOn <= asOf.slice(0, 10));
    if (snaps.length < 2) return [];
    type Entry = [number, Piece, string[], string[]];
    const norm = (c: Piece) => normText(c.text).replace(/\bmonths\b/g, "month");
    const merged = new Map<string, Entry>();
    const add = (target: Map<string, Entry>, score: number, c: Piece, urls: string[], takenOn: string) => {
      const key = norm(c);
      let e = target.get(key);
      if (!e) target.set(key, (e = [score, c, [], []]));
      e[0] = Math.max(e[0], score);
      e[1] = c;   // keep the newest occurrence (its page and dates)
      for (const u of urls) if (!e[2].includes(u)) e[2].push(u);
      e[3].push(takenOn);
    };
    let limit = HISTORY_PIECES;
    if (this.extractor && this.asksValue(question, qu)) {
      for (const { takenOn, snapshotId } of snaps) {
        const found = this.factHits(question, snapshotId, qu, HISTORY_FACTS_PER_COPY * 4);
        // read each copy's history from the most trusted page type that answered in it (a stale table on another page is the copy contradicting itself)
        const best = found.length ? Math.min(...found.map(([, f]) => RANK_ORDER[f.pageType]!)) : null;
        let kept = found.filter((h) => RANK_ORDER[h[1].pageType] === best);
        // two tables of that page type can still disagree inside one copy: keep, per product and rate type, the rows of the table with the latest effective date
        const newest = new Map<string, string>();
        for (const [, f] of kept) { const k = JSON.stringify([f.product.toLowerCase(), f.metric]); newest.set(k, [newest.get(k) ?? "", f.effective ?? ""].reduce((a, b) => (a > b ? a : b))); }
        const current = new Map<string, Set<string>>();
        for (const [, f] of kept) { const k = JSON.stringify([f.product.toLowerCase(), f.metric]); if ((f.effective ?? "") === newest.get(k)) { let s = current.get(k); if (!s) current.set(k, (s = new Set())); s.add(f.value); } }
        kept = kept.filter((h) => current.get(JSON.stringify([h[1].product.toLowerCase(), h[1].metric]))?.has(h[1].value));
        for (const [score, f, urls] of kept.slice(0, HISTORY_FACTS_PER_COPY)) add(merged, score, f, urls, takenOn);
      }
      limit = HISTORY_FACT_LINES;
    }
    const extras = new Map<string, Entry>();   // embedding-window pieces of each copy: kept after the keyword pieces, never cut by the limit
    if (!merged.size) {
      for (const { takenOn } of snaps) {
        const quNow: QU = { ...qu, website_date: null };
        const found = await this.retrieve(question, takenOn, HISTORY_PIECES_PER_COPY, quNow);
        for (const [score, c, urls] of found) add(merged, score, c, urls, takenOn);
        if (HISTORY_WINDOWS && HYBRID_WINDOWS) for (const [score, c, urls] of await this.windowExtras(question, found, takenOn, quNow)) add(extras, score, c, urls, takenOn);
      }
      limit = HISTORY_PIECES;
    }
    const top = [...merged.values()].sort((a, b) => b[0] - a[0]).slice(0, limit);
    if (extras.size) {
      const have = new Set(top.map((e) => norm(e[1])));
      top.push(...[...extras].sort((a, b) => b[1][0] - a[1][0]).filter(([k]) => !have.has(k)).map(([, e]) => e).slice(0, HISTORY_WINDOW_PIECES));
    }
    if (top.length && isFact(top[0]![1])) {
      // facts: the same product's lines next to each other, oldest copy first, so a change reads top to bottom
      const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
      top.sort((a, b) => { const fa = a[1] as Fact, fb = b[1] as Fact; return cmp(fa.product.toLowerCase(), fb.product.toLowerCase()) || cmp(fa.metric, fb.metric) || cmp(a[3][0]!, b[3][0]!); });
    }
    return top;
  }

  private async historyAnswer(question: string, asOf: string | null | undefined, qu: QU): Promise<Answer | null> {
    const hits = await this.historyHits(question, asOf, qu);
    if (!hits.length) return null;
    const excerpts: Excerpt[] = hits.map(([, c, , copies], i) => ({ n: i + 1, pageType: PAGE_TYPE_LABEL[pageRank(c.url)], url: c.url, effective: c.effective, published: c.published, copies: copies.join(", "), text: c.text }));
    let out;
    try { out = await this.llm.ask(buildUserMessage(question, excerpts, null), historyDeveloperMessage()); }
    catch (e) { console.error(`[ts_solution] LLM call failed (history): ${(e as Error).name}: ${(e as Error).message}`); return null; }
    const text = (out.answer ?? "").trim();
    if (!out.confident || !text) return null;
    if (this.asksValue(question, qu) && !VALUE_NUM_RE.test(text)) return null;
    const used = out.used_excerpts.filter((n) => n >= 1 && n <= hits.length);
    if (!used.length) used.push(1);
    const sources: Source[] = [];
    const seen = new Set<string>();
    for (const n of used) { const [, c, urls] = hits[n - 1]!; for (const u of urls) if (!seen.has(u)) { seen.add(u); sources.push({ url: u, snapshotId: c.snapshotId }); } }
    return { text, sources, confident: true, conflictNote: out.conflict_note };
  }

  // ------------------------------------------------------------------ conflicts
  private sentenceCache: SentenceCache | null = null;

  /** Contradictions in the newest website copy (conflicts_v2). Rate sentences cost one small model call each; results are cached on disk. */
  async conflicts(): Promise<Conflict[]> {
    if (!this.newest) return [];
    const seed = join(HERE, "..", "data", "sentence_cache.json");
    const own = resolve(process.env.MY_SOLUTION_SENTENCE_CACHE ?? join(HERE, "..", ".cache", "sentences.json"));
    this.sentenceCache ??= loadSentenceCache(seed, own);
    try {
      const out = await buildConflicts(this.newest, this.llm.available() ? this.llm.model : null, this.sentenceCache);
      saveSentenceCache(own, this.sentenceCache);
      return out;
    } catch (e) {
      console.error(`[ts_solution] conflicts failed: ${(e as Error).name}: ${(e as Error).message}`);
      return [];
    }
  }
}

function topChunk(hits: Hit[]): Answer {
  const [, c, urls] = hits[0]!;
  return { text: c.text.slice(0, 600), sources: urls.map((u) => ({ url: u, snapshotId: c.snapshotId })), confident: true };
}

/** Other evidence pages that state the same value as the answer (text pieces only; every distinctive value of the answer that the cited pieces contain). */
function sameValueSources(answer: string, hits: Hit[], used: number[], seen: Set<string>): Source[] {
  if (!hits.length || isFact(hits[0]![1])) return [];
  const norm = (s: string) => s.replace(/[\s,]/g, "");
  const cited = norm(used.map((n) => hits[n - 1]![1].text).join(" "));
  const values = new Set([...(answer.match(DISTINCT_VALUE_RE) ?? [])].map(norm).filter((v) => cited.includes(v)));
  if (!values.size) return [];
  const extra: Source[] = [];
  hits.forEach(([, c, urls], i) => {
    if (used.includes(i + 1) || ![...values].every((v) => norm(c.text).includes(v))) return;
    for (const u of urls) if (!seen.has(u) && extra.length < CITE_SAME_VALUE_MAX) { seen.add(u); extra.push({ url: u, snapshotId: c.snapshotId }); }
  });
  return extra;
}

export function build(): Knowledge { return new Knowledge({ useFacts: process.env.MY_SOLUTION_FACTS !== "0" }); }
