// Live check of the TS sentence extractor: re-extracts a sample of sentences and compares with the Python cache. Usage: ... SENTENCE_CACHE.json [N]
import { loadSnapshots } from "../src/snapshots.ts";
import { extract, loadSentenceCache, rateSentences } from "../src/sentence_facts.ts";
import { cost } from "../src/openai.ts";

const ref = loadSentenceCache(process.argv[2]!);
const n = Number(process.argv[3] ?? 20);
const all = rateSentences(loadSnapshots("../snapshots").at(-1)!.pages);
const sample = new Map([...all].filter(([k]) => k in ref).filter((_, i) => i % Math.max(1, Math.floor(all.size / n)) === 0).slice(0, n));
const got = await extract(sample, "gpt-6-luna", {});
const sig = (r: Array<{ kind: string; value: string; bound: string; rate_type: string; intro: boolean }>) => JSON.stringify(r.map((x) => [x.kind, x.value, x.bound, x.rate_type, x.intro]));
let same = 0;
for (const [k] of sample) { if (got[k] && sig(got[k]!) === sig(ref[k]!)) same++; else console.log("differs:", all.get(k)!.text.slice(0, 100), "\n ts", got[k] && sig(got[k]!), "\n py", sig(ref[k]!)); }
console.log(`${same}/${sample.size} sentences extracted identically; est. cost $${cost.usd.toFixed(4)}`);
