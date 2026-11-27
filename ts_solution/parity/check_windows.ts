import { readFileSync } from "node:fs";
import { loadSnapshots } from "../src/snapshots.ts";
import { buildChunks } from "../src/corpus.ts";
import { WindowIndex, textKey } from "../src/embed_index.ts";
const ref = JSON.parse(readFileSync(process.argv[2]!, "utf8"));
let bad = 0;
for (const snap of loadSnapshots("../snapshots")) {
  const wi = new WindowIndex(buildChunks(snap));
  const left = await wi.build(false);
  const r = ref[snap.snapshotId];
  let diffs = 0;
  if (wi.windows.length !== r.n || left) console.log(snap.snapshotId, "windows", wi.windows.length, "vs", r.n, "missing", left);
  if (!left) for (const [q, exp] of Object.entries<any>(r.search)) {
    const got = (await wi.search(q, 10)).map((h) => [Math.round(h.sim * 1e5) / 1e5, h.chunkId, textKey(h.text).slice(0, 10)]);
    const same = got.length === exp.length && got.every((g, i) => g[1] === exp[i][1] && g[2] === exp[i][2] && Math.abs((g[0] as number) - exp[i][0]) < 2e-4);
    if (!same && diffs++ < 2) console.log("diff:", q, "\n ts", JSON.stringify(got.slice(0, 3)), "\n py", JSON.stringify(exp.slice(0, 3)));
  }
  console.log(snap.snapshotId, `windows ${wi.windows.length}, missing ${left}, search diffs ${diffs}/40`);
  bad += diffs + left;
}
process.exit(bad ? 1 : 0);
