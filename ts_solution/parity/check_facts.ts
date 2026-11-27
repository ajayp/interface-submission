import { readFileSync } from "node:fs";
import { loadSnapshots } from "../src/snapshots.ts";
import { publishedDate } from "../src/chunker.ts";
import { FactExtractor, factIndexText, factKey, groupFacts, pageTables, tableKey, winner } from "../src/facts.ts";
import { BM25Index } from "../src/search.ts";
import { countFacts, countQuestion } from "../src/count_facts.ts";

const ref = JSON.parse(readFileSync(process.argv[2]!, "utf8"));
const fx = new FactExtractor("none", null, [process.argv[3]!]);
let bad = 0;
const show = (what: string, a: unknown, b: unknown) => { bad++; console.log("DIFF", what, "\n ts", JSON.stringify(a).slice(0, 300), "\n py", JSON.stringify(b).slice(0, 300)); };
// Python's key() is a tuple repr; compare through a canonical form instead: the grouping (sizes + winners) must match.
for (const snap of loadSnapshots("../snapshots")) {
  const r = ref[snap.snapshotId];
  const tables = snap.pages.flatMap((p) => pageTables(p.url, p.title, p.markdown).map((t) => [t, publishedDate(p.url, p.markdown)] as const));
  const tk = tables.map(([t]) => [tableKey(t).slice(0, 12), t.caption, t.effective, t.note.slice(0, 60)]);
  if (JSON.stringify(tk) !== JSON.stringify(r.tables)) show(`${snap.snapshotId} tables (${tk.length} vs ${r.tables.length})`, tk.find((x, i) => JSON.stringify(x) !== JSON.stringify(r.tables[i])), r.tables.find((x: any, i: number) => JSON.stringify(x) !== JSON.stringify(tk[i])));
  const facts = tables.flatMap(([t, pub]) => fx.factsFor(t, snap.snapshotId, pub));
  const ft = facts.map((f) => [f.text, f.url, f.effective, f.published, f.pageType]);
  if (JSON.stringify(ft) !== JSON.stringify(r.facts.map((x: any[]) => x.slice(0, 5)))) show(`${snap.snapshotId} facts (${ft.length} vs ${r.facts.length})`, ft.find((x, i) => JSON.stringify(x) !== JSON.stringify(r.facts[i]?.slice(0, 5))), "");
  const groups = groupFacts(facts).map((g) => [g.length, winner(g).text, winner(g).url]);
  if (JSON.stringify(groups) !== JSON.stringify(r.groups)) show(`${snap.snapshotId} groups (${groups.length} vs ${r.groups.length})`, groups.find((x, i) => JSON.stringify(x) !== JSON.stringify(r.groups[i])), r.groups.find((x: any, i: number) => JSON.stringify(x) !== JSON.stringify(groups[i])));
  const idx = new BM25Index(facts, factIndexText);
  const firstEqual = new Map<unknown, number>(), seenKeys = new Map<string, number>();   // Python .index() uses dataclass equality
  facts.forEach((f, i) => { const k = JSON.stringify(f); if (!seenKeys.has(k)) seenKeys.set(k, i); firstEqual.set(f, seenKeys.get(k)!); });
  let sd = 0;
  for (const [q, exp] of Object.entries<any>(r.search)) {
    const got = idx.search(q, { k: 20 }).map(([s, f]) => [Math.round(s * 1e5) / 1e5, firstEqual.get(f)!]);
    const same = got.length === exp.length && got.every((g, i) => g[1] === exp[i][1] && Math.abs(g[0]! - exp[i][0]) < 2e-4);
    if (!same && sd++ < 1) show(`${snap.snapshotId} fact search "${q}"`, got.slice(0, 3), exp.slice(0, 3));
  }
  const cf = countFacts(snap.pages).map((c) => [c.measure, c.value, c.url, c.published, c.sentence]);
  if (JSON.stringify(cf) !== JSON.stringify(r.counts)) show(`${snap.snapshotId} count facts (${cf.length} vs ${r.counts.length})`, cf.find((x, i) => JSON.stringify(x) !== JSON.stringify(r.counts[i])), r.counts.find((x: any, i: number) => JSON.stringify(x) !== JSON.stringify(cf[i])));
  for (const [q, m] of Object.entries<any>(r.count_q)) if (countQuestion(q) !== m) show(`count question "${q}"`, countQuestion(q), m);
  console.log(snap.snapshotId, `tables ${tk.length}, facts ${facts.length}, groups ${groups.length}, count facts ${cf.length}, search diffs ${sd}/40`);
  void factKey;
}
console.log(bad ? `${bad} differences` : "all equal");
process.exit(bad ? 1 : 0);
