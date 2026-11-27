// Fills a Decisions label cache for every question of the public eval (a few tiny calls), shared by the Python and TS parity checks.
import { readFileSync } from "node:fs";
import { DecisionsUnderstanding } from "../src/decisions.ts";
import { setReference } from "../src/dates.ts";
import { cost } from "../src/openai.ts";
setReference("2026-09-28");
const qs = readFileSync(process.argv[3] ?? "../eval/public_eval.jsonl", "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l).question as string);
const d = new DecisionsUnderstanding(process.argv[2]!);
let fail = 0;
for (let i = 0; i < qs.length; i += 8) await Promise.all(qs.slice(i, i + 8).map(async (q) => { if (!(await d.parse(q))) fail++; }));
console.log(qs.length, "questions,", d.calls, "calls,", fail, "failed; est. cost $", cost.usd.toFixed(4));
