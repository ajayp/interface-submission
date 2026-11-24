import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { loadSnapshots } from "../src/snapshots.ts";
import { buildChunks } from "../src/corpus.ts";
import { BM25Index } from "../src/search.ts";
const ref = JSON.parse(readFileSync(process.argv[2]!, "utf8"));
let bad = 0;
for (const snap of loadSnapshots("../snapshots")) {
  const chunks = buildChunks(snap);
  const r = ref[snap.snapshotId];
  const key = (t: string) => createHash("sha1").update(t).digest("hex").slice(0, 12);
  let diff = 0;
  if (chunks.length !== r.chunks.length) console.log(snap.snapshotId, "chunk count", chunks.length, "vs", r.chunks.length);
  chunks.forEach((c, i) => {
    const e = r.chunks[i]; if (!e) return;
    const got = JSON.stringify([c.url, c.kind, c.heading, c.headerPath, c.effective, c.published, c.categories, key(c.text)]);
    if (got !== JSON.stringify(e)) { if (diff++ < 3) console.log("chunk", i, "\n ts ", got, "\n py ", JSON.stringify(e)); }
  });
  const idx = new BM25Index(chunks);
  let sdiff = 0, tot = 0;
  for (const [q, exp] of Object.entries<any>(r.search)) {
    tot++;
    const got = idx.search(q, { k: 8 }).map(([s, c]) => [Math.round(s * 1e6) / 1e6, chunks.indexOf(c)]);
    const same = got.length === exp.length && got.every((g, j) => g[1] === exp[j][1] && Math.abs(g[0]! - exp[j][0]) < 1e-5);
    if (!same && sdiff++ < 2) console.log("search diff:", q, "\n ts", JSON.stringify(got.slice(0, 4)), "\n py", JSON.stringify(exp.slice(0, 4)));
  }
  console.log(snap.snapshotId, `chunks ${chunks.length}, chunk diffs ${diff}, search diffs ${sdiff}/${tot}`);
  bad += diff + sdiff;
}
process.exit(bad ? 1 : 0);
