import { readFileSync } from "node:fs";
import { stem } from "../src/stemmer.ts";
const ref: Record<string, string> = JSON.parse(readFileSync(process.argv[2]!, "utf8"));
const bad = Object.entries(ref).filter(([w, s]) => stem(w) !== s);
console.log(`${Object.keys(ref).length - bad.length}/${Object.keys(ref).length} match`);
for (const [w, s] of bad.slice(0, 40)) console.log(w, "ref:", s, "ts:", stem(w));
