// Embedding retriever: lookup of stored vectors (Python's .embed_cache/*.npz, read-only) plus a small JSON side file for vectors this
// port had to embed itself (missing windows at ingest, new questions). Port of my_solution/embed_index.py (windows mode).
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { readNpz, toFloat32, toStrings } from "./npz.ts";
import { embed } from "./openai.ts";
import type { Chunk } from "./chunker.ts";

export const MODEL = process.env.MY_SOLUTION_EMBED_MODEL ?? "text-embedding-3-small";
const HERE = dirname(fileURLToPath(import.meta.url));
const PY_CACHE = resolve(process.env.MY_SOLUTION_PY_CACHE ?? join(HERE, "..", "..", "my_solution", ".embed_cache"));
const SIDE_CACHE = resolve(process.env.MY_SOLUTION_TS_CACHE ?? join(HERE, "..", ".cache"));
const MAX_CHARS = 6000;
export const WINDOW_CHARS = 600, WINDOW_STRIDE = 400;

export const textKey = (text: string): string => createHash("sha1").update(text.split(/\s+/).filter(Boolean).join(" ").toLowerCase()).digest("hex");

/** key -> vector store. Python npz files are loaded read-only; new vectors go to a JSON side file (base64 float32). */
export class EmbeddingStore {
  readonly vecs = new Map<string, Float32Array>();
  private readonly side: string;
  private readonly fromNpz = new Set<string>();   // keys that live in the Python file and are not rewritten
  constructor(npzFile: string, sideName: string) {
    this.side = join(SIDE_CACHE, sideName);
    if (existsSync(npzFile)) {
      const z = readNpz(npzFile);
      const keys = toStrings(z.keys!), all = toFloat32(z.vectors!), d = z.vectors!.shape[1]!;
      keys.forEach((k, i) => { this.vecs.set(k, all.subarray(i * d, (i + 1) * d)); this.fromNpz.add(k); });
    }
    if (existsSync(this.side)) {
      for (const [k, b64] of Object.entries<string>(JSON.parse(readFileSync(this.side, "utf8")))) {
        const b = Buffer.from(b64, "base64");
        this.vecs.set(k, new Float32Array(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength)));
      }
    }
  }
  /** Embed every text not stored yet (needs the key), then save the side file. */
  async ensure(texts: string[]): Promise<void> {
    const missing = new Map<string, string>();
    for (const t of texts) { const k = textKey(t); if (!this.vecs.has(k) && !missing.has(k)) missing.set(k, t); }
    if (!missing.size) return;
    const keys = [...missing.keys()];
    for (let i = 0; i < keys.length; i += 128) {
      const batch = keys.slice(i, i + 128);
      const vs = await embed(MODEL, batch.map((k) => missing.get(k)!.slice(0, MAX_CHARS)));
      batch.forEach((k, j) => this.vecs.set(k, vs[j]!));
    }
    this.save();
  }
  set(key: string, v: Float32Array): void { this.vecs.set(key, v); this.save(); }
  save(): void {
    mkdirSync(SIDE_CACHE, { recursive: true });
    const obj: Record<string, string> = {};
    for (const [k, v] of this.vecs) if (!this.fromNpz.has(k)) obj[k] = Buffer.from(v.buffer, v.byteOffset, v.byteLength).toString("base64");
    writeFileSync(this.side, JSON.stringify(obj));
  }
}

// ---- question vectors
let questionStore: EmbeddingStore | null = null;
function qstore(): EmbeddingStore {
  if (!questionStore) questionStore = new EmbeddingStore(join(PY_CACHE, `questions-${MODEL}.npz`), "questions.json");
  return questionStore;
}
const pending = new Map<string, Promise<Float32Array>>();

/** Question vector: from the stored file when this exact question was seen before, otherwise one API call (shared by all callers). */
export function embedQuery(text: string): Promise<Float32Array> {
  const k = textKey(text), s = qstore();
  const hit = s.vecs.get(k);
  if (hit) return Promise.resolve(hit);
  let p = pending.get(k);
  if (!p) {
    p = embed(MODEL, [text]).then(([v]) => { s.set(k, v!); return v!; });
    pending.set(k, p);
  }
  return p;
}
/** Start embedding a question now (runs while the query-understanding call is in flight). */
export function prefetchQuery(text: string): void { embedQuery(text).catch(() => {}); }

// ---- overlapping windows
/** Text cut by code points, like Python slicing (JS strings are UTF-16). */
function cut(t: string, from: number, to: number): string { return /[\ud800-\udfff]/.test(t) ? Array.from(t).slice(from, to).join("") : t.slice(from, to); }
const cpLen = (t: string): number => (/[\ud800-\udfff]/.test(t) ? Array.from(t).length : t.length);

export interface WindowHit { sim: number; chunkId: number; text: string }

export class WindowIndex {
  windows: Array<[string, number]> = [];   // (text, parent chunk id)
  matrix: Float32Array = new Float32Array(0);
  dim = 0;
  readonly store: EmbeddingStore;
  readonly chunks: Chunk[];
  constructor(chunks: Chunk[], store?: EmbeddingStore) {
    this.chunks = chunks;
    this.store = store ?? WindowIndex.defaultStore();
    const seen = new Set<string>();
    chunks.forEach((c, ci) => {
      const t = c.text, n = cpLen(t);
      for (let s = 0; s < Math.max(n - (WINDOW_CHARS - WINDOW_STRIDE), 1); s += WINDOW_STRIDE) {
        const w = cut(t, s, s + WINDOW_CHARS).trim();
        const k = textKey(w);
        if (w.length >= 40 && !seen.has(k)) { seen.add(k); this.windows.push([w, ci]); }
      }
    });
  }
  private static shared: EmbeddingStore | null = null;
  /** One store for every website copy (the same paragraph is embedded once; the 57 MB file is read once). */
  static defaultStore(): EmbeddingStore {
    return (WindowIndex.shared ??= new EmbeddingStore(join(PY_CACHE, `windows-${MODEL}.npz`), "windows.json"));
  }
  missing(): string[] { return this.windows.map(([w]) => w).filter((w) => !this.store.vecs.has(textKey(w))); }
  /** Embed what is missing (ingest only, needs the key), then stack the matrix. Returns the number still missing. */
  async build(embedMissing: boolean): Promise<number> {
    if (embedMissing && this.missing().length) await this.store.ensure(this.missing());
    const left = this.missing().length;
    if (left) return left;
    this.dim = this.store.vecs.get(textKey(this.windows[0]![0]))!.length;
    this.matrix = new Float32Array(this.windows.length * this.dim);
    this.windows.forEach(([w], i) => this.matrix.set(this.store.vecs.get(textKey(w))!, i * this.dim));
    return 0;
  }
  async search(question: string, k = 10): Promise<WindowHit[]> {
    const q = await embedQuery(question), d = this.dim, n = this.windows.length;
    const sims = new Float32Array(n);
    for (let i = 0; i < n; i++) { let s = 0; const o = i * d; for (let j = 0; j < d; j++) s += this.matrix[o + j]! * q[j]!; sims[i] = s; }
    const order = Array.from({ length: n }, (_, i) => i).sort((a, b) => sims[b]! - sims[a]! || a - b).slice(0, k);
    return order.map((i) => ({ sim: sims[i]!, chunkId: this.windows[i]![1], text: this.windows[i]![0] }));
  }
}

/** Reciprocal-rank fusion: each list adds 1/(k+rank) to an id's score. */
export function fuse(rankedLists: number[][], k = 60): number[] {
  const score = new Map<number, number>();
  for (const L of rankedLists) L.forEach((id, r) => score.set(id, (score.get(id) ?? 0) + 1 / (k + r + 1)));
  return [...score].sort((a, b) => b[1] - a[1]).map(([id]) => id);
}
