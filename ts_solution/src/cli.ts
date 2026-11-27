// Command line: eval, ask, conflicts, score-conflicts. Run with: node --experimental-strip-types src/cli.ts <command> [options]
import { mkdirSync, readFileSync, writeFileSync, readdirSync } from "node:fs";
import { basename, join, resolve } from "node:path";
import { parseArgs } from "node:util";
import { cost } from "./openai.ts";
import { loadSnapshots } from "./snapshots.ts";
import { Knowledge } from "./solution.ts";
import { scoreConflicts, scoreItem, summarize, type EvalItem, type GoldConflict, type ItemResult } from "./scoring.ts";
import type { Answer, Conflict } from "./types.ts";

const ANSWER_TIMEOUT_MS = 60_000;
const ROOT = resolve(import.meta.dirname, "..", "..");

async function load(snapshotsDir: string): Promise<{ ks: Knowledge; seconds: number }> {
  const t = Date.now();
  const ks = new Knowledge();
  for (const s of loadSnapshots(snapshotsDir)) { console.error(`ingest ${s.snapshotId} (${s.pages.length} pages)`); await ks.ingest(s); }
  return { ks, seconds: (Date.now() - t) / 1000 };
}

/** One answer with the harness's 60 s limit; a timeout or crash scores zero and the run continues. */
async function timed(ks: Knowledge, q: string, asOf: string | null | undefined): Promise<{ ans: Answer; err: string | null; s: number }> {
  const t = Date.now();
  try {
    const ans = await Promise.race([ks.answer(q, asOf), new Promise<never>((_, rej) => setTimeout(() => rej(new Error("answer timed out after 60 s")), ANSWER_TIMEOUT_MS).unref())]);
    return { ans, err: null, s: (Date.now() - t) / 1000 };
  } catch (e) {
    console.error(e);
    return { ans: { text: "", sources: [], confident: false }, err: `${(e as Error).name}: ${(e as Error).message}`, s: (Date.now() - t) / 1000 };
  }
}

const asDict = (a: Answer) => ({ text: a.text, sources: a.sources.map((s) => ({ url: s.url, snapshot_id: s.snapshotId ?? null, quote: s.quote ?? null })), confident: a.confident, conflict_note: a.conflictNote ?? null });
const asConflictDict = (c: Conflict) => ({ topic: c.topic, values: c.values, sources: c.sources.map((s) => ({ url: s.url, snapshot_id: s.snapshotId ?? null, quote: s.quote ?? null })), resolution: c.resolution ?? null, reason: c.reason ?? null });

async function cmdEval(args: string[]): Promise<void> {
  const { values: o } = parseArgs({ args, options: {
    eval: { type: "string" }, out: { type: "string", default: "results" }, snapshots: { type: "string", default: join(ROOT, "snapshots") },
    "repeat-sample": { type: "string", default: "20" }, "conflicts-gold": { type: "string", multiple: true }, ids: { type: "string" }, limit: { type: "string" } } });
  if (!o.eval) throw new Error("--eval FILE is required");
  let items: EvalItem[] = readFileSync(o.eval, "utf8").split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
  if (o.ids) { const ids = new Set(o.ids.split(",")); items = items.filter((i) => ids.has(i.id)); }
  if (o.limit) items = items.slice(0, Number(o.limit));
  const { ks, seconds } = await load(o.snapshots!);

  const results: ItemResult[] = [];
  for (const it of items) {
    const { ans, err, s } = await timed(ks, it.question, it.as_of);
    results.push({ ...scoreItem(it, ans), latency_s: Math.round(s * 100) / 100, error: err, answer: asDict(ans) });
  }
  // Consistency: ask a deterministic sample of questions a second time.
  const rs = Number(o["repeat-sample"]);
  const step = Math.max(1, Math.floor(items.length / (rs || 1)));
  const repeats: Array<{ id: string; text: string }> = [];
  if (rs) for (let i = 0; i < items.length; i += step) { const { ans } = await timed(ks, items[i]!.question, items[i]!.as_of); repeats.push({ id: items[i]!.id, text: ans.text }); }

  let conflictReport = null;
  const golds = o["conflicts-gold"] ?? [];
  if (golds.length) {
    let submitted: Conflict[] = [];
    try { submitted = await ks.conflicts(); } catch (e) { console.error(`conflicts() failed: ${(e as Error).message}`); }
    for (const g of golds) {
      const rep = scoreConflicts(JSON.parse(readFileSync(g, "utf8")) as GoldConflict[], submitted);
      console.error(`conflicts vs ${basename(g)}:`, JSON.stringify(rep));
      conflictReport ??= rep;   // the first gold list feeds the report, as the harness's single --conflicts-gold would
    }
  }
  const report = summarize(results, conflictReport, repeats);
  report.ingest_seconds = Math.round(seconds * 10) / 10;
  report.openai_cost_estimate_usd = Math.round(cost.usd * 1e4) / 1e4;
  mkdirSync(o.out!, { recursive: true });
  writeFileSync(join(o.out!, "per_question.jsonl"), results.map((r) => JSON.stringify(r)).join("\n"));
  writeFileSync(join(o.out!, "report.json"), JSON.stringify(report, null, 2));
  const { by_category, ...rest } = report;
  console.log(JSON.stringify(rest, null, 2));
  console.log("by category:");
  for (const [cat, v] of Object.entries<any>(by_category)) console.log(`  ${cat.padEnd(24)} ${v.score.toFixed(2)}  (n=${v.n})`);
}

async function cmdAsk(args: string[]): Promise<void> {
  const { values: o, positionals } = parseArgs({ args, allowPositionals: true, options: { "as-of": { type: "string" }, snapshots: { type: "string", default: join(ROOT, "snapshots") } } });
  const q = positionals.join(" ");
  if (!q) throw new Error('usage: cli.ts ask "question" [--as-of YYYY-MM-DD]');
  const { ks } = await load(o.snapshots!);
  const a = await ks.answer(q, o["as-of"]);
  console.log(JSON.stringify(asDict(a), null, 2));
}

async function cmdConflicts(args: string[]): Promise<void> {
  const { values: o } = parseArgs({ args, options: { out: { type: "string" }, snapshots: { type: "string", default: join(ROOT, "snapshots") } } });
  const { ks } = await load(o.snapshots!);
  const out = (await ks.conflicts()).map(asConflictDict);
  if (o.out) { mkdirSync(resolve(o.out, ".."), { recursive: true }); writeFileSync(o.out, JSON.stringify(out, null, 1)); }
  console.log(`conflicts(): ${out.length} entries${o.out ? " -> " + o.out : ""}`);
}

/** Score a saved conflicts list against every docs/gold/conflicts_gold_*.json (no model calls). */
function cmdScoreConflicts(args: string[]): void {
  const { values: o, positionals } = parseArgs({ args, allowPositionals: true, options: { gold: { type: "string", multiple: true } } });
  const goldDir = join(ROOT, "docs", "gold");
  const files = o.gold?.length ? o.gold : readdirSync(goldDir).filter((f) => /^conflicts_gold_.*\.json$/.test(f)).sort().map((f) => join(goldDir, f));
  const subs = (JSON.parse(readFileSync(positionals[0]!, "utf8")) as any[]).map((c) => ({ ...c, sources: c.sources ?? [] }) as Conflict);
  console.log(`${positionals[0]}: ${subs.length} entries`);
  console.log(`${"gold list".padEnd(38)} ${"n".padStart(3)} ${"found".padStart(5)} ${"recall".padStart(6)} ${"prec".padStart(5)} ${"F1".padStart(5)} ${"winner".padStart(7)} ${"pillar".padStart(6)}`);
  for (const f of files) {
    const r = scoreConflicts(JSON.parse(readFileSync(f, "utf8")), subs);
    const pillar = 0.7 * r.f1 + 0.3 * (r.resolution_accuracy ?? 0);
    console.log(`${basename(f).padEnd(38)} ${String(r.gold).padStart(3)} ${String(r.matched).padStart(5)} ${r.recall.toFixed(2).padStart(6)} ${r.precision.toFixed(2).padStart(5)} ${r.f1.toFixed(2).padStart(5)} ${(r.resolution_accuracy ?? 0).toFixed(2).padStart(7)} ${pillar.toFixed(3).padStart(6)}`);
  }
}

const [cmd, ...rest] = process.argv.slice(2);
try {
  if (cmd === "eval") await cmdEval(rest);
  else if (cmd === "ask") await cmdAsk(rest);
  else if (cmd === "conflicts") await cmdConflicts(rest);
  else if (cmd === "score-conflicts") cmdScoreConflicts(rest);
  else { console.error("commands: eval --eval FILE [--out DIR] [--repeat-sample N] [--conflicts-gold FILE]... [--ids a,b] [--limit N] | ask \"question\" [--as-of DATE] | conflicts [--out FILE] | score-conflicts FILE"); process.exit(2); }
} catch (e) { console.error((e as Error).message); process.exit(1); }
process.exit(0);
