// Micro-benchmark of the TS client: N sequential Decisions calls and N answer calls on distinct questions, per-call latency.
// Usage: bench_ts.ts [N]   (a few cents at most)
import { DecisionsUnderstanding } from "../src/decisions.ts";
import { AnswerLLM } from "../src/llm.ts";
import { buildUserMessage, developerMessageFor } from "../src/prompt.ts";
import { cost } from "../src/openai.ts";

const n = Number(process.argv[2] ?? 10);
const stats = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); const r = (x: number) => Math.round(x); return { first_ms: r(xs[0]!), rest_mean_ms: r(xs.slice(1).reduce((a, b) => a + b, 0) / Math.max(1, xs.length - 1)), median_ms: r(s[Math.floor(s.length / 2)]!), max_ms: r(s.at(-1)!) }; };
const t = async <T>(f: () => Promise<T>): Promise<number> => { const t0 = performance.now(); await f(); return performance.now() - t0; };

const dec = new DecisionsUnderstanding();
const decMs: number[] = [];
for (let i = 0; i < n; i++) decMs.push(await t(() => dec.parse(`What is the rate for a ${12 + i}-month certificate this week?`)));   // first call includes connection setup
const llm = new AnswerLLM();
const ansMs: number[] = [];
for (let i = 0; i < n; i++) {
  const q = `What is the routing number? (variant ${i})`;
  const msg = buildUserMessage(q, [{ n: 1, pageType: "product_page", url: "https://www.dupaco.com/x", text: "Dupaco's routing number is 273976369." }], null);
  ansMs.push(await t(() => llm.ask(msg, developerMessageFor(q, "fact_about_dupaco"))));
}
console.log(JSON.stringify({ client: "ts-fetch", decisions: stats(decMs), answer: stats(ansMs), est_cost_usd: Math.round(cost.usd * 1e4) / 1e4 }));
