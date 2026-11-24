import { loadSnapshots } from "../src/snapshots.ts";
import { writeFileSync } from "node:fs";
const words = new Set<string>();
for (const s of loadSnapshots(process.argv[2]!)) for (const p of s.pages) for (const w of p.markdown.toLowerCase().match(/[a-z]+/g) ?? []) words.add(w);
writeFileSync(process.argv[3]!, [...words].sort().join("\n"));
console.log(words.size);
