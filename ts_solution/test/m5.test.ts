import { test } from "node:test";
import assert from "node:assert/strict";
import { fmtG, parseTable } from "../src/table_parse.ts";
import { modelYears, termMonths, tierOf } from "../src/fact_match.ts";
import { stem } from "../src/stemmer.ts";
import { rateSentences } from "../src/sentence_facts.ts";
import { countConflicts } from "../src/conflicts_v2.ts";

test("number formatting like Python's :g", () => { assert.equal(fmtG(5.34), "5.34"); assert.equal(fmtG(12.5), "12.5"); assert.equal(fmtG(7), "7"); assert.equal(fmtG(0.15), "0.15"); });
test("term, tier and model-year readers", () => {
  assert.equal(termMonths("60 Months"), 60);
  assert.equal(termMonths("30-year fixed"), 360);
  assert.deepEqual(tierOf("$25,000+"), [25000, Infinity]);
  assert.deepEqual(tierOf("$10,000 - $24,999.99"), [10000, 24999.99]);
  assert.deepEqual(tierOf("$300,000 or less"), [0, 300000]);
  assert.deepEqual(modelYears("Model Years 2024-27"), [2024, 2027]);
  assert.deepEqual(modelYears("2016 Model Year (and older)"), [0, 2016]);
  assert.equal(stem("rates"), "rate");
});
test("a rate table becomes one cell per rate", () => {
  const table = "| Term | APY |\n|---|---|\n| 6 Months | 3.10% |\n| 12 Months | 3.25% |";
  const [cells] = parseTable({ url: "https://x/rates", title: "t", heading: "h", caption: "Certificates", table, note: "", effective: null, after: "" }, "s1");
  assert.deepEqual(cells.map((c) => [c.product, c.value, c.metric]), [["Certificates", "3.1%", "APY"], ["Certificates", "3.25%", "APY"]]);
});
test("rate sentences keep the text just before", () => {
  const m = rateSentences([{ url: "u", title: "T", markdown: "# H\nOur Share Certificate pays well.\nNow earn **3.66% APY** today.", fetchedAt: "2026-01-01" }]);
  const e = [...m.values()][0]!;
  assert.equal(e.heading, "H");
  assert.match(e.before, /Share Certificate/);
});
test("count conflicts need two different values", () => {
  const page = (v: string) => ({ url: `https://x/${v}`, title: "", fetchedAt: "", markdown: `Dupaco now operates ${v} branches.` });
  assert.equal(countConflicts({ snapshotId: "s", takenOn: "d", pages: [page("22")] }).length, 0);
  assert.equal(countConflicts({ snapshotId: "s", takenOn: "d", pages: [page("22"), page("23")] }).length, 1);
});
