// Loads the crawls: snapshots/<id>/manifest.json + pages; unpacks snapshots_zip/*.zip on first use (same as harness/run_eval.py).
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync, statSync } from "node:fs";
import { join, resolve, dirname, sep } from "node:path";
import { listZip, readEntry } from "./zip.ts";
import type { Snapshot } from "./types.ts";

export function ensureSnapshots(root: string): void {
  const zipDir = [join(dirname(root), "snapshots_zip"), root].find((d) => existsSync(d) && readdirSync(d).some((f) => f.endsWith(".zip")));
  if (!zipDir) return;
  mkdirSync(root, { recursive: true });
  for (const z of readdirSync(zipDir).filter((f) => f.endsWith(".zip")).sort()) {
    if (existsSync(join(root, z.slice(0, -4), "manifest.json"))) continue;
    const buf = readFileSync(join(zipDir, z));
    for (const e of listZip(buf)) {
      const dest = resolve(root, e.name);
      if (!dest.startsWith(resolve(root) + sep)) throw new Error(`unsafe path in ${z}: ${e.name}`);
      if (e.name.endsWith("/")) { mkdirSync(dest, { recursive: true }); continue; }
      mkdirSync(dirname(dest), { recursive: true });
      writeFileSync(dest, readEntry(buf, e));
    }
  }
}

export function loadSnapshots(root: string): Snapshot[] {
  ensureSnapshots(root);
  const snaps: Snapshot[] = [];
  for (const name of readdirSync(root).sort()) {
    const d = join(root, name);
    if (!statSync(d).isDirectory() || !existsSync(join(d, "manifest.json"))) continue;
    const m = JSON.parse(readFileSync(join(d, "manifest.json"), "utf8"));
    snaps.push({
      snapshotId: m.snapshot_id, takenOn: m.taken_on,
      pages: m.pages.map((p: any) => ({
        url: p.url, title: p.title ?? "", markdown: readFileSync(join(d, p.file), "utf8"), fetchedAt: p.fetched_at ?? m.taken_on,
      })),
    });
  }
  return snaps.sort((a, b) => (a.takenOn < b.takenOn ? -1 : a.takenOn > b.takenOn ? 1 : 0));
}
