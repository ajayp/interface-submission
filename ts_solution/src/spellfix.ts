// Spelling help for member questions: learns the site's own vocabulary and ADDS corrections to the search text.
// Port of my_solution/spellfix.py (guards and thresholds are identical).
import { STOP } from "./search.ts";

const POSS = /['’]s\b/g;
const MIN_LEN = 5, MIN_CAND = 5, RATIO = 10, KNOWN = 3, SPLIT_MIN = 20;

export function words(text: string): string[] {
  return text.toLowerCase().replace(POSS, "").replaceAll(",", "").match(/[a-z]+/g) ?? [];
}
const maxEdits = (w: string): number => (w.length >= 9 ? 2 : 1);

function deletes(w: string, d: number): Set<string> {
  const out = new Set([w]);
  let frontier = new Set([w]);
  for (let k = 0; k < d; k++) {
    const next = new Set<string>();
    for (const x of frontier) for (let i = 0; i < x.length; i++) next.add(x.slice(0, i) + x.slice(i + 1));
    frontier = next;
    for (const x of next) out.add(x);
  }
  return out;
}

/** Edit distance where swapping two neighbouring letters counts as one edit. */
function editDistance(a: string, b: string): number {
  const m = a.length, n = b.length;
  const d: number[][] = Array.from({ length: m + 1 }, (_, i) => [i, ...new Array<number>(n).fill(0)]);
  for (let j = 0; j <= n; j++) d[0]![j] = j;
  for (let i = 1; i <= m; i++) for (let j = 1; j <= n; j++) {
    const c = a[i - 1] === b[j - 1] ? 0 : 1;
    d[i]![j] = Math.min(d[i - 1]![j]! + 1, d[i]![j - 1]! + 1, d[i - 1]![j - 1]! + c);
    if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i]![j] = Math.min(d[i]![j]!, d[i - 2]![j - 2]! + 1);
  }
  return d[m]![n]!;
}

export class SpellFix {
  readonly counts = new Map<string, number>();
  private index: Map<string, Set<string>> | null = null;
  private memo = new Map<string, string[]>();
  private count(w: string): number { return this.counts.get(w) ?? 0; }

  addText(text: string): void {
    for (const w of words(text)) this.counts.set(w, this.count(w) + 1);
    this.index = null; this.memo.clear();
  }

  private build(): Map<string, Set<string>> {
    const index = new Map<string, Set<string>>();
    for (const [w, c] of this.counts) {
      if (w.length >= MIN_LEN && c >= MIN_CAND) for (const dl of deletes(w, maxEdits(w))) {
        let s = index.get(dl); if (!s) index.set(dl, (s = new Set())); s.add(w);
      }
    }
    return (this.index = index);
  }

  correct(w: string): string | null {
    if (w.length < MIN_LEN || STOP.has(w) || this.count(w) >= KNOWN) return null;
    const index = this.index ?? this.build();
    const d = maxEdits(w);
    const cands = new Set<string>();
    for (const dl of deletes(w, d)) for (const c of index.get(dl) ?? []) cands.add(c);
    let best: [number, number, string] | null = null;
    for (const c of cands) {
      if (c[0] !== w[0]) continue;
      const dist = editDistance(w, c);
      if (dist > d || this.count(c) < RATIO * Math.max(this.count(w), 1)) continue;
      const key: [number, number] = [-this.count(c), dist];
      if (!best || key[0] < best[0] || (key[0] === best[0] && key[1] < best[1])) best = [key[0], key[1], c];
    }
    return best ? best[2] : null;
  }

  private split(w: string): [string, string] | null {
    if (w.length < 7 || STOP.has(w) || this.count(w) >= KNOWN) return null;
    let best: [number, string, string] | null = null;
    for (let i = 3; i < w.length - 2; i++) {
      const a = w.slice(0, i), b = w.slice(i);
      if (this.count(a) >= SPLIT_MIN && this.count(b) >= SPLIT_MIN) {
        const score = Math.min(this.count(a), this.count(b));
        if (!best || score > best[0]) best = [score, a, b];
      }
    }
    return best ? [best[1], best[2]] : null;
  }

  /** Words to ADD to the search for this question (empty for a question without typos). */
  extraWords(question: string): string[] {
    const hit = this.memo.get(question);
    if (hit) return hit;
    const toks = words(question);
    const extra: string[] = [];
    const merged = new Set<number>();
    for (let i = 0; i < toks.length - 1; i++) {
      const a = toks[i]!, b = toks[i + 1]!;
      if ((this.count(a) < KNOWN || this.count(b) < KNOWN) && this.count(a + b) >= SPLIT_MIN && !STOP.has(a) && !STOP.has(b)) {
        extra.push(a + b); merged.add(i); merged.add(i + 1);
      }
    }
    toks.forEach((w, i) => {
      if (merged.has(i)) return;
      const c = this.correct(w);
      if (c) { extra.push(c); return; }
      const parts = this.split(w);
      if (parts) extra.push(...parts);
    });
    this.memo.set(question, extra);
    return extra;
  }
}
