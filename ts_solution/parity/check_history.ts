// Compares the evidence of the "what changed" path with Python's. Usage: check_history.ts PY_DUMP.json QU_CACHE
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { loadSnapshots } from "../src/snapshots.ts";
process.env.MY_SOLUTION_QU_DEC_CACHE = process.argv[3]!;
const { Knowledge } = await import("../src/solution.ts");
const ref = JSON.parse(readFileSync(process.argv[2]!, "utf8")) as Record<string, { as_of: string | null; hits: any[] }>;
const ks = new Knowledge();
for (const s of loadSnapshots("../snapshots")) await ks.ingest(s);
const h = (t: string) => createHash("sha1").update(t).digest("hex").slice(0, 10);
let bad = 0, n = 0;
for (const [q, r] of Object.entries(ref)) {
  n++;
  const qu = await ks.understand(q);
  if (qu?.time_scope !== "change") { bad++; console.log("TS does not label as change:", q); continue; }
  const hits = (await ks.historyHits(q, r.as_of, qu)).map(([, c, urls, copies]) => [c.url, h(c.text), urls, copies]);
  if (JSON.stringify(hits) !== JSON.stringify(r.hits)) { bad++; console.log("DIFF", q, "\n ts", JSON.stringify(hits).slice(0, 300), "\n py", JSON.stringify(r.hits).slice(0, 300)); }
}
console.log(bad ? `${bad} of ${n} differ` : `all ${n} history evidence lists identical`);
process.exit(bad ? 1 : 0);
