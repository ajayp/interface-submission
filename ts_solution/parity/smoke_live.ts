// Live smoke test: one Decisions call + one structured answer call + one fact-extraction call. Costs a fraction of a cent.
import { DecisionsUnderstanding } from "../src/decisions.ts";
import { AnswerLLM } from "../src/llm.ts";
import { buildUserMessage, developerMessageFor } from "../src/prompt.ts";
import { cost } from "../src/openai.ts";
import { loadSnapshots } from "../src/snapshots.ts";
import { FactExtractor, pageTables } from "../src/facts.ts";
import { setReference } from "../src/dates.ts";

setReference("2026-09-28");
const t0 = Date.now();
const d = new DecisionsUnderstanding();
for (const q of ["What is the APY on Dupaco's 17-month special certificate?", "what was the checking dividend in early August 2026", "Did the mortgage rate change since June 2026?"]) {
  const qu = await d.parse(q);
  console.log(q, "\n  ->", qu && { intent: qu.intent, metric: qu.rate_metric, cats: qu.categories, date: qu.website_date, scope: qu.time_scope, syn: qu.synonym_tokens.length });
}
console.log("decisions ms", Date.now() - t0);

const llm = new AnswerLLM();
const q = "What is the routing number?";
const msg = buildUserMessage(q, [{ n: 1, pageType: "product_page", url: "https://www.dupaco.com/x", text: "Dupaco's routing number is 273976369." }], null);
const t1 = Date.now();
const out = await llm.ask(msg, developerMessageFor(q, "fact_about_dupaco"));
console.log("answer:", out, "ms", Date.now() - t1);

// one real table through the fact extractor (no disk cache)
const snap = loadSnapshots("../snapshots").at(-1)!;
const t = snap.pages.flatMap((p) => pageTables(p.url, p.title, p.markdown)).find((x) => x.url.endsWith("/rates"))!;
const fx = new FactExtractor("gpt-6-luna", null);
await fx.extract([t]);
console.log("facts from one table:", fx.factsFor(t, snap.snapshotId, null).slice(0, 3).map((f) => f.text));
console.log("cost so far", cost);
