// Pages of one snapshot -> chunks with categories (the chunking part of Python's ingest). Boilerplate removal is off in the Python
// default (BOILERPLATE_MIN_PAGES = 10**9), so it is not ported.
import { chunkPage, type Chunk } from "./chunker.ts";
import { categoriesFor } from "./categories.ts";
import type { Snapshot } from "./types.ts";

export function buildChunks(snap: Snapshot): Chunk[] {
  const chunks: Chunk[] = [];
  for (const p of snap.pages) chunks.push(...chunkPage(p.url, p.title, p.markdown, snap.snapshotId, p.fetchedAt));
  for (const c of chunks) {
    const caption = c.kind === "row" ? c.text.split(" | ")[0]! : "";
    c.categories = categoriesFor(c.url, `${c.headerPath} ${c.heading} ${caption}`, c.text);
  }
  return chunks;
}
