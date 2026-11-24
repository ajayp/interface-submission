import { test } from "node:test";
import assert from "node:assert/strict";
import { stem } from "../src/stemmer.ts";
import { questionDate, setReference } from "../src/dates.ts";
import { pageRank } from "../src/tiers.ts";
import { tokenize } from "../src/search.ts";
import { splitSections } from "../src/chunker.ts";

test("stemmer matches Snowball on known words", () => {
  assert.equal(stem("certificates"), "certif");
  assert.equal(stem("adding"), "add");
  assert.equal(stem("pasting"), "paste");
  assert.equal(stem("internal"), "internal");
});
test("dates", () => {
  setReference("2026-09-28");
  assert.equal(questionDate("rate as of May 2026"), "2026-05-31");
  assert.equal(questionDate("rate on 5/15/2026"), "2026-05-15");
  assert.equal(questionDate("rate before September 2026"), "2026-08-31");
  assert.equal(questionDate("rate in May"), "2026-05-31");
  assert.equal(questionDate("May I open an account"), null);
});
test("tiers and tokens", () => {
  assert.equal(pageRank("https://www.dupaco.com/rates"), "rate_sheet");
  assert.equal(pageRank("https://www.dupaco.com/learn/blog/x"), "secondary");
  assert.deepEqual(tokenize("What is Dupaco's 5.39% APY?"), ["5.39%", "api"]);
});
test("split sections tracks the heading path", () => {
  const s = splitSections("# A\ntext\n## B\nmore\n");
  assert.deepEqual(s.map((x) => x[0]), ["/", "/A/"]);
});
