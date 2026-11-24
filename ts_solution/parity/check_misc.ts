import { readFileSync } from "node:fs";
import { loadSnapshots } from "../src/snapshots.ts";
import { questionDate, asksBeforeDate, setReference } from "../src/dates.ts";
import { expansion } from "../src/synonyms.ts";
import { SpellFix } from "../src/spellfix.ts";
const ref = JSON.parse(readFileSync(process.argv[2]!, "utf8"));
setReference("2026-09-28");
const sp = new SpellFix();
for (const s of loadSnapshots("../snapshots")) for (const p of s.pages) sp.addText(p.markdown);
let bad = 0;
for (const q of ref.questions as string[]) {
  const d = JSON.stringify([questionDate(q), asksBeforeDate(q)]);
  if (d !== JSON.stringify(ref.dates[q])) { bad++; console.log("DATE", q, d, JSON.stringify(ref.dates[q])); }
  if (JSON.stringify(expansion(q)) !== JSON.stringify(ref.syn[q])) { bad++; console.log("SYN", q); }
  if (JSON.stringify(sp.extraWords(q)) !== JSON.stringify(ref.spell[q])) { bad++; console.log("SPELL", q, sp.extraWords(q), ref.spell[q]); }
}
console.log(`${ref.questions.length} questions, ${bad} differences`);
process.exit(bad ? 1 : 0);
