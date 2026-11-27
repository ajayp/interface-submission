// Compares everything that feeds the answer model with the Python dump (dump_py5.py). No answer calls.
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { loadSnapshots } from "../src/snapshots.ts";
import { Knowledge } from "../src/solution.ts";

const ref = JSON.parse(readFileSync(process.argv[2]!, "utf8"));
process.env.MY_SOLUTION_QU_DEC_CACHE = process.argv[3]!;
const ks = new Knowledge();
for (const s of loadSnapshots("../snapshots")) await ks.ingest(s);
const items = readFileSync("../eval/public_eval.jsonl", "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
const h = (t: string) => createHash("sha1").update(t).digest("hex").slice(0, 10);
const strip = (m: string) => m.replace(/[0-9a-f]{12}/g, "NONCE");
let bad = 0;
const cmp = (id: string, what: string, a: unknown, b: unknown) => {
  if (JSON.stringify(a) !== JSON.stringify(b)) { bad++; console.log(`DIFF ${id} ${what}\n ts ${JSON.stringify(a).slice(0, 400)}\n py ${JSON.stringify(b).slice(0, 400)}`); }
};
for (const it of items) {
  const q = it.question as string, asOf = it.as_of as string | null, r = ref[q];
  const qu = await ks.understand(q);
  const copy = ks.copyFor(q, asOf, qu);
  const asked = ks.askedNote(q, asOf, qu);
  cmp(it.id, "snapshot/date/intent", [copy.snapshotId, asked, qu?.intent, qu?.website_date, qu?.time_scope], [r.sid, r.asked, r.intent, r.date, r.scope]);
  const hits = await ks.retrieve(q, asOf, 8, qu);
  cmp(it.id, "text hits", hits.map(([, c, u]) => [c.url, h(c.text), u]), r.text_hits);
  cmp(it.id, "text message", strip(ks.userMessage(q, hits, copy.takenOn, asked)), r.text_msg);
  const fh = ks.factHits(q, copy.snapshotId, qu);
  cmp(it.id, "fact hits", fh.map(([, f, u]) => [f.text, f.url, u]), r.fact_hits);
  if (fh.length) cmp(it.id, "fact message", strip(ks.userMessage(q, fh, copy.takenOn, asked)), r.fact_msg);
}
console.log(bad ? `${bad} differences in ${items.length} questions` : `all ${items.length} questions equal`);
process.exit(bad ? 1 : 0);
