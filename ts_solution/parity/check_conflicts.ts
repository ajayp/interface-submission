// Compares conflicts() with the Python output, using the same sentence cache (so no model calls unless a sentence is missing).
// Usage: check_conflicts.ts PY_CONFLICTS.json SENTENCE_CACHE.json
import { readFileSync } from "node:fs";
import { loadSnapshots } from "../src/snapshots.ts";
import { buildConflicts } from "../src/conflicts_v2.ts";
import { loadSentenceCache } from "../src/sentence_facts.ts";
import { cost } from "../src/openai.ts";

const ref = JSON.parse(readFileSync(process.argv[2]!, "utf8")) as Array<{ topic: string; values: string[]; sources: Array<{ url: string }>; resolution: string; reason: string }>;
const snap = loadSnapshots("../snapshots").at(-1)!;
const t = Date.now();
const out = await buildConflicts(snap, "gpt-6-luna", loadSentenceCache(process.argv[3]!));
console.log(`ts: ${out.length} conflicts in ${Date.now() - t} ms, py: ${ref.length}, model calls ${cost.calls}`);
const norm = (c: { topic: string; values: string[]; sources: Array<{ url: string }>; resolution?: string | null; reason?: string | null }) =>
  JSON.stringify([c.topic, c.values, c.sources.map((s) => s.url), c.resolution, c.reason]);
let bad = 0;
const n = Math.max(out.length, ref.length);
for (let i = 0; i < n; i++) {
  const a = out[i] ? norm(out[i]!) : "(none)", b = ref[i] ? norm(ref[i]!) : "(none)";
  if (a !== b && bad++ < 5) console.log(`DIFF #${i}\n ts ${a.slice(0, 300)}\n py ${b.slice(0, 300)}`);
}
console.log(bad ? `${bad} entries differ` : "all conflict entries identical");
process.exit(bad ? 1 : 0);
