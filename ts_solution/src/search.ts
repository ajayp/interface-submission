// BM25 keyword search over chunks, one index per snapshot, plus a source-tier boost. Port of my_solution/search.py.
import { indexText, type Chunk } from "./chunker.ts";
import { stem } from "./stemmer.ts";
import { pageRank, RATE_SHEET, PRODUCT, PROMO, SECONDARY, type Rank } from "./tiers.ts";

const TOKEN_RE = /\d+(?:\.\d+)?%?|[a-z]+/g;
export const STOP = new Set(`a an the of to in on for and or is are was were be by with at as it its this that what
which who how do does did can could you your i me my we our us there their from any all about
tell please get give provide right now currently current dupaco`.split(/\s+/));
const BOOSTS: Record<string, Record<Rank, number>> = {
  none: { [RATE_SHEET]: 1, [PRODUCT]: 1, [PROMO]: 1, [SECONDARY]: 1 },
  tiers: { [RATE_SHEET]: 1.3, [PRODUCT]: 1.2, [PROMO]: 1.1, [SECONDARY]: 0.6 },
};
const POSSESSIVE_RE = /['’]s\b/g;

const stemWord = (t: string): string => (/^\d/.test(t) ? t : stem(t));

export function tokenize(text: string): string[] {
  const t = text.toLowerCase().replace(POSSESSIVE_RE, "").replaceAll(",", "");
  return (t.match(TOKEN_RE) ?? []).filter((x) => !STOP.has(x)).map(stemWord);
}

export interface SearchOptions {
  k?: number; boost?: string; categories?: Iterable<string>; catBoost?: number;
  qualifiers?: RegExp[]; qualBoost?: number; expansionTokens?: Iterable<string>; expansionWeight?: number;
}

/** Anything BM25 can index: chunks and facts. */
export interface Searchable { url: string; categories: string[]; text: string }

export class BM25Index<T extends Searchable = Chunk> {
  readonly postings = new Map<string, Array<[number, number]>>();
  readonly lengths: number[] = [];
  readonly avgdl: number;
  readonly idf = new Map<string, number>();
  readonly rank: Rank[];
  readonly chunks: T[];
  readonly k1: number;
  readonly b: number;
  constructor(chunks: T[], textOf: (c: T) => string = (c) => indexText(c as unknown as Chunk), k1 = 1.2, b = 0.75) {
    this.chunks = chunks; this.k1 = k1; this.b = b;
    chunks.forEach((c, i) => {
      const tf = new Map<string, number>();
      const toks = tokenize(textOf(c));
      for (const t of toks) tf.set(t, (tf.get(t) ?? 0) + 1);
      this.lengths.push(toks.length);
      for (const [t, n] of tf) { let p = this.postings.get(t); if (!p) this.postings.set(t, (p = [])); p.push([i, n]); }
    });
    this.avgdl = this.lengths.length ? this.lengths.reduce((a, b) => a + b, 0) / this.lengths.length : 1;
    const N = chunks.length;
    for (const [t, p] of this.postings) this.idf.set(t, Math.log(1 + (N - p.length + 0.5) / (p.length + 0.5)));
    this.rank = chunks.map((c) => pageRank(c.url));
  }

  /** BM25 x page trust, plus fixed bonuses for pieces in a chosen category / containing a parsed qualifier. */
  search(query: string, o: SearchOptions = {}): Array<[number, T]> {
    const { k = 10, boost = "tiers", catBoost = 0, qualBoost = 0, expansionWeight = 0.5 } = o;
    const cats = new Set(o.categories ?? []);
    const qualifiers = o.qualifiers ?? [];
    const q = new Set(tokenize(query));
    const weighted: Array<[string, number]> = [...q].map((t) => [t, 1]);
    for (const t of new Set(o.expansionTokens ?? [])) if (!q.has(t)) weighted.push([t, expansionWeight]);
    const scores = new Map<number, number>();
    for (const [t, w] of weighted) {
      const idf = this.idf.get(t);
      if (idf === undefined) continue;
      for (const [i, tf] of this.postings.get(t)!) {
        const dl = this.lengths[i]!;
        scores.set(i, (scores.get(i) ?? 0) + (w * idf * tf * (this.k1 + 1)) / (tf + this.k1 * (1 - this.b + (this.b * dl) / this.avgdl)));
      }
    }
    const weights = BOOSTS[boost]!;
    const final: Array<[number, number]> = [];
    for (const [i, s] of scores) {
      const c = this.chunks[i]!;
      let v = s * weights[this.rank[i]!]!;
      if (catBoost && cats.size && c.categories.some((x) => cats.has(x))) v += catBoost;
      if (qualBoost && qualifiers.length && qualifiers.some((p) => p.test(c.text))) v += qualBoost;
      final.push([v, i]);
    }
    final.sort((a, b) => b[0] - a[0] || a[1] - b[1]);
    return final.slice(0, k).map(([s, i]) => [s, this.chunks[i]!]);
  }
}
