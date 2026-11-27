// End-to-end: answer a few public questions and show them next to the expected values. Usage: ask_some.ts N [offset]
import { readFileSync } from "node:fs";
import { loadSnapshots } from "../src/snapshots.ts";
import { Knowledge } from "../src/solution.ts";
import { cost } from "../src/openai.ts";

const n = Number(process.argv[2] ?? 6), off = Number(process.argv[3] ?? 0);
const items = readFileSync("../eval/public_eval.jsonl", "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)).slice(off, off + n);
const ks = new Knowledge();
let t = Date.now();
for (const s of loadSnapshots("../snapshots")) await ks.ingest(s);
console.log(`ingest ${((Date.now() - t) / 1000).toFixed(1)} s`);
for (const it of items) {
  t = Date.now();
  const a = await ks.answer(it.question, it.as_of);
  const ms = Date.now() - t;
  const hit = (it.must_include as string[]).map((m) => a.text.toLowerCase().includes(m.toLowerCase()));
  console.log(`\n[${it.id}] ${it.category} ${ms} ms conf=${a.confident}\nQ: ${it.question}\nA: ${a.text}\n   must_include ${JSON.stringify(it.must_include)} -> ${JSON.stringify(hit)}  traps ${JSON.stringify(it.must_not_include)}\n   src: ${a.sources.map((s) => s.url).slice(0, 2).join(" ")}`);
}
console.log("\ncost", cost);
