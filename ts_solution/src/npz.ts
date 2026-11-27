// Reader for numpy .npz files (zip of .npy): little-endian float16/float32 arrays and fixed-width unicode ("<U40") string arrays.
import { readFileSync } from "node:fs";
import { listZip, readEntry } from "./zip.ts";

export interface NpyArray { shape: number[]; dtype: string; data: Buffer }

export function parseNpy(buf: Buffer): NpyArray {
  if (buf.subarray(0, 6).toString("latin1") !== "\x93NUMPY") throw new Error("not an .npy array");
  const major = buf[6]!;
  const hlen = major === 1 ? buf.readUInt16LE(8) : buf.readUInt32LE(8);
  const start = major === 1 ? 10 : 12;
  const header = buf.toString("latin1", start, start + hlen);
  const dtype = /'descr':\s*'([^']+)'/.exec(header)?.[1];
  const shape = (/'shape':\s*\(([^)]*)\)/.exec(header)?.[1] ?? "").split(",").map((s) => s.trim()).filter(Boolean).map(Number);
  if (!dtype || /'fortran_order':\s*True/.test(header)) throw new Error(`unsupported .npy header: ${header}`);
  return { shape, dtype, data: buf.subarray(start + hlen) };
}

export function readNpz(path: string): Record<string, NpyArray> {
  const buf = readFileSync(path);
  const out: Record<string, NpyArray> = {};
  for (const e of listZip(buf)) out[e.name.replace(/\.npy$/, "")] = parseNpy(readEntry(buf, e));
  return out;
}

/** IEEE half -> float. */
export function half(h: number): number {
  const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 0x1f, f = h & 0x3ff;
  if (e === 0) return s * f * 2 ** -24;
  if (e === 31) return f ? NaN : s * Infinity;
  return s * (1 + f / 1024) * 2 ** (e - 15);
}

export function toFloat32(a: NpyArray): Float32Array {
  const n = a.shape.reduce((x, y) => x * y, 1);
  const out = new Float32Array(n);
  if (a.dtype === "<f2") { const dv = new DataView(a.data.buffer, a.data.byteOffset, n * 2); for (let i = 0; i < n; i++) out[i] = half(dv.getUint16(i * 2, true)); }
  else if (a.dtype === "<f4") { const dv = new DataView(a.data.buffer, a.data.byteOffset, n * 4); for (let i = 0; i < n; i++) out[i] = dv.getFloat32(i * 4, true); }
  else throw new Error(`unsupported dtype ${a.dtype}`);
  return out;
}

export function toStrings(a: NpyArray): string[] {
  const m = /^<U(\d+)$/.exec(a.dtype);
  if (!m) throw new Error(`unsupported dtype ${a.dtype}`);
  const w = +m[1]! * 4, n = a.shape[0] ?? 0, out: string[] = [];
  for (let i = 0; i < n; i++) {
    let s = "";
    for (let j = 0; j < +m[1]!; j++) { const cp = a.data.readUInt32LE(i * w + j * 4); if (cp === 0) break; s += String.fromCodePoint(cp); }
    out.push(s);
  }
  return out;
}
