// The scorer: port of harness/scoring.py (rules identical; the optional Anthropic LLM judge is not ported).
// Per item: correctness (must_include by value or substring), trap (must_not_include zeroes it), refusal, sources (+15%).
// Final = accuracy 55% + conflicts 15% + consistency 15% + speed 15%; consistency and speed are multiplied by accuracy.
import type { Answer, Conflict } from "./types.ts";

const NUM_RE = /(\$)?\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(%|percent)?/gi;
const REFUSAL_RE = /\b(i (?:do not|don't|can't|cannot) (?:know|find|confirm)|not (?:sure|able to confirm)|no (?:longer )?(?:available|offered)|isn't listed|is not listed|please (?:contact|call|visit)|no information)\b/i;

type Num = [string, number];   // [unit, value]
const key = (n: Num): string => `${n[0]}|${n[1]}`;

export function numbers(text: string): Num[] {
  const out = new Map<string, Num>();
  for (const m of (text ?? "").matchAll(NUM_RE)) {
    const unit = m[1] ? "$" : m[4] ? "%" : "";
    const val = Number((parseFloat(m[2]!.replaceAll(",", "") + (m[3] ? "." + m[3] : ""))).toFixed(4));
    out.set(`${unit}|${val}`, [unit, val]);
  }
  return [...out.values()];
}

export function norm(s: string): string {
  const t = (s ?? "").toLowerCase().replace(/\b([ap])\.\s?m\.?/g, "$1m").replaceAll("–", "-").replaceAll("—", "-");
  return t.replace(/\s+/g, " ").trim();
}

/** Value-aware containment: numeric tokens match by value+unit, text by substring. */
export function contains(answer: string, token: string): boolean {
  const tnums = numbers(token);
  const leftover = token.toLowerCase().replace(/[\s$\d.,%]|\b(apr|apy|percent)\b/g, "");
  if (tnums.length && !leftover && token.length <= 20) {
    const anums = numbers(answer);
    const have = new Set(anums.map(key));
    return tnums.every((n) => have.has(key(n)) || (n[0] === "" && anums.some((a) => a[1] === n[1])));
  }
  return norm(answer).includes(norm(token));
}

export function urlKey(u: string): string {
  let p: URL;
  try { p = new URL(u.includes("//") ? u : "https://" + u); } catch { return u.toLowerCase(); }
  return p.host.toLowerCase().replace(/^www\./, "") + p.pathname.replace(/\/+$/, "").toLowerCase();
}

export interface EvalItem {
  id: string; question: string; as_of?: string | null; category?: string; group?: string | null; weight?: number;
  must_include?: string[]; must_not_include?: string[]; expected_sources?: string[]; expected_answer?: string;
}
export interface ItemResult {
  id: string; category: string; group: string | null; weight: number; score: number; correctness: number; source_hit: number | null;
  matched: string[]; missed: string[]; trap_hits: string[];
  latency_s?: number; error?: string | null; answer?: { text: string; sources: Array<{ url: string; snapshot_id?: string | null; quote?: string | null }>; confident: boolean; conflict_note?: string | null };
}

export function scoreItem(item: EvalItem, ans: Answer): ItemResult {
  const text = ans.text ?? "";
  const must = item.must_include ?? [], mustNot = item.must_not_include ?? [];
  const cat = item.category ?? "general";
  const hit = must.filter((t) => contains(text, t));
  const trap = mustNot.filter((t) => contains(text, t));
  const refused = !ans.confident || REFUSAL_RE.test(text);
  let correctness: number;
  if (cat === "should_refuse") {
    const qn = new Set(numbers(item.question).map(key));
    correctness = refused && !trap.length && !numbers(text).some((n) => !qn.has(key(n))) ? 1 : 0;
  } else {
    correctness = must.length ? hit.length / must.length : 0;
    if (trap.length) correctness = 0;
  }
  const exp = new Set((item.expected_sources ?? []).map(urlKey));
  const got = new Set((ans.sources ?? []).filter((s) => s?.url).map((s) => urlKey(s.url)));
  let src: number | null = null, score = correctness;
  if (exp.size) { src = [...exp].some((u) => got.has(u)) ? 1 : 0; score = 0.85 * correctness + 0.15 * src; }
  const r4 = (x: number) => Math.round(x * 1e4) / 1e4;
  return { id: item.id, category: cat, group: item.group ?? null, weight: item.weight ?? 1, score: r4(score), correctness: r4(correctness), source_hit: src,
    matched: hit, missed: must.filter((t) => !hit.includes(t)), trap_hits: trap };
}

export interface GoldConflict { id: string; topic_keywords?: string[]; values: string[]; correct_value?: string }
export interface ConflictReport { gold: number; submitted: number; matched: number; recall: number; precision: number; f1: number; resolution_accuracy: number | null }

/** Matched when the submitted conflict names >=2 of the gold values, or >=1 value plus a topic keyword; resolution credit for the right winner. */
export function scoreConflicts(gold: GoldConflict[], submitted: Conflict[]): ConflictReport {
  const subs = (submitted ?? []).map((c) => [norm(c.topic ?? ""), (c.values ?? []).join(" | "), c.resolution ?? ""] as const);
  let matched = 0, resolvedOk = 0;
  const used = new Set<number>();
  for (const g of gold) {
    for (let i = 0; i < subs.length; i++) {
      if (used.has(i)) continue;
      const [topic, vals, res] = subs[i]!;
      const vhits = g.values.filter((v) => contains(vals, v)).length;
      const khit = (g.topic_keywords ?? []).some((k) => topic.includes(norm(k)));
      if (vhits >= 2 || (vhits >= 1 && khit)) {
        matched++; used.add(i);
        if (g.correct_value && res && contains(res, g.correct_value)) resolvedOk++;
        break;
      }
    }
  }
  const recall = gold.length ? matched / gold.length : 0, precision = subs.length ? matched / subs.length : 0;
  const f = precision + recall ? (2 * precision * recall) / (precision + recall) : 0;
  const nRes = gold.filter((g) => g.correct_value).length;
  const r4 = (x: number) => Math.round(x * 1e4) / 1e4;
  return { gold: gold.length, submitted: subs.length, matched, recall: r4(recall), precision: r4(precision), f1: r4(f), resolution_accuracy: nRes ? r4(resolvedOk / nRes) : null };
}

export const SPEED_FAST_S = 2.0, SPEED_SLOW_S = 20.0;
const WEIGHTS: Record<string, number> = { accuracy: 0.55, conflicts: 0.15, consistency: 0.15, speed: 0.15 };
const core = (text: string): string => numbers(text).map(key).sort().join(";");

export function scoreConsistency(results: ItemResult[], repeats: Array<{ id: string; text: string }>) {
  const groups = new Map<string, ItemResult[]>();
  for (const r of results) if (r.group) { let a = groups.get(r.group); if (!a) groups.set(r.group, (a = [])); a.push(r); }
  let gOk = 0;
  for (const members of groups.values()) {
    const allRight = members.every((m) => m.correctness >= 0.999);
    const same = new Set(members.map((m) => core(m.answer?.text ?? ""))).size === 1;
    if (allRight || same) gOk++;
  }
  const byId = new Map(results.map((r) => [r.id, r]));
  const rOk = repeats.filter((rep) => core(rep.text) === core(byId.get(rep.id)?.answer?.text ?? "")).length;
  const para = groups.size ? gOk / groups.size : null, rep = repeats.length ? rOk / repeats.length : null;
  const parts = [para, rep].filter((x): x is number => x !== null);
  const r4 = (x: number | null) => (x === null ? null : Math.round(x * 1e4) / 1e4);
  return { paraphrase_groups: groups.size, paraphrase_consistency: r4(para), repeat_checks: repeats.length, repeat_consistency: r4(rep),
    score: parts.length ? r4(parts.reduce((a, b) => a + b, 0) / parts.length) : null };
}

export function scoreSpeed(latencies: number[]) {
  if (!latencies.length) return { score: 0 };
  const xs = [...latencies].sort((a, b) => a - b);
  const p = (q: number) => xs[Math.min(xs.length - 1, Math.floor(q * xs.length))]!;
  const p95 = p(0.95);
  const s = p95 <= SPEED_FAST_S ? 1 : Math.max(0, (SPEED_SLOW_S - p95) / (SPEED_SLOW_S - SPEED_FAST_S));
  const r = (x: number, d = 2) => Math.round(x * 10 ** d) / 10 ** d;
  return { p50_s: r(p(0.5)), p95_s: r(p95), max_s: r(xs.at(-1)!), score: r(s, 4) };
}

export function summarize(results: ItemResult[], conflictReport: ConflictReport | null, repeats: Array<{ id: string; text: string }> = []) {
  const by = new Map<string, ItemResult[]>();
  for (const r of results) { let a = by.get(r.category); if (!a) by.set(r.category, (a = [])); a.push(r); }
  const wsum = results.reduce((s, r) => s + r.weight, 0) || 1;
  const qa = results.reduce((s, r) => s + r.score * r.weight, 0) / wsum;
  const r4 = (x: number) => Math.round(x * 1e4) / 1e4;
  const cons = scoreConsistency(results, repeats);
  const speed = scoreSpeed(results.filter((r) => !r.error).map((r) => r.latency_s ?? 0));
  const report: Record<string, any> = {
    qa_score: r4(qa), questions: results.length, stale_trap_hits: results.filter((r) => r.trap_hits.length).length, errors: results.filter((r) => r.error).length,
    by_category: Object.fromEntries([...by].sort(([a], [b]) => (a < b ? -1 : 1)).map(([k, v]) => [k, { n: v.length, score: r4(v.reduce((s, x) => s + x.score, 0) / v.length) }])),
    consistency: cons, speed,
  };
  const pillars: Record<string, number | null> = { accuracy: qa, consistency: cons.score === null ? null : cons.score * qa, speed: speed.score * qa };
  if (conflictReport) { report.conflicts = conflictReport; pillars.conflicts = 0.7 * conflictReport.f1 + 0.3 * (conflictReport.resolution_accuracy ?? 0); }
  const used = Object.entries(pillars).filter(([, v]) => v !== null).map(([k]) => k);
  const totalW = used.reduce((s, k) => s + WEIGHTS[k]!, 0);
  report.pillars = Object.fromEntries(used.map((k) => [k, r4(pillars[k]!)]));
  report.final_score = r4(used.reduce((s, k) => s + pillars[k]! * WEIGHTS[k]!, 0) / totalW);
  return report;
}
