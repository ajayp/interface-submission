import { test } from "node:test";
import assert from "node:assert/strict";
import { z } from "zod";
import { countQuestion, answerText, latest, type CountFact } from "../src/count_facts.ts";
import { AnswerSchema, buildUserMessage, developerMessageFor, intentBlockName } from "../src/prompt.ts";
import { interpret } from "../src/decisions.ts";
import { parseFirstJson } from "../src/openai.ts";
import { winner, type Fact } from "../src/facts.ts";
import prompts from "../data/prompts.json" with { type: "json" };

test("count questions", () => {
  assert.equal(countQuestion("How many branches does Dupaco have?"), "branches");
  assert.equal(countQuestion("How many branches in Dubuque?"), null);
  assert.equal(countQuestion("How many members in 2023?"), null);
});
test("count answer text and latest", () => {
  const f: CountFact = { measure: "employees", value: "600", url: "u", pageType: "secondary", published: "2026-01-02", fetchedAt: null, sentence: "It has over 600 employees and" };
  assert.match(answerText(f), /over 600 employees/);
  const older = { ...f, published: "2025-01-01" };
  assert.equal(latest([older, f]), f);
});
test("answer schema is strict JSON schema matching the Python one", () => {
  const js = z.toJSONSchema(AnswerSchema) as any;
  assert.equal(js.additionalProperties, false);
  assert.deepEqual(Object.keys(js.properties).sort(), Object.keys(prompts.answer_schema.properties).sort());
  assert.deepEqual([...js.required].sort(), [...prompts.answer_schema.required].sort());
});
test("prompt assembly", () => {
  assert.equal(intentBlockName("how many branches", "rate"), "fact_about_dupaco");
  assert.ok(developerMessageFor("hours?", "hours").includes("# Question type"));
  assert.ok(!developerMessageFor("rate?", "rate").includes("# Question type"));
  assert.ok(developerMessageFor("rate?", "rate", true).includes("# Dated question"));
  const m = buildUserMessage("q?", [{ n: 1, pageType: "rate_sheet", url: "https://x/y", text: "T", effective: "2026-01-01" }], "2026-05-12", "May 2026");
  assert.match(m, /^Input id: [0-9a-f]{12}\nWebsite as of: 2026-05-12\nQuestion date: May 2026\n<question id="/);
  assert.match(m, /<excerpt id="[0-9a-f]{12}" n="1" page_type="rate_sheet" url="https:\/\/x\/y" effective="2026-01-01">\nT\n<\/excerpt>/);
  assert.equal(m, buildUserMessage("q?", [{ n: 1, pageType: "rate_sheet", url: "https://x/y", text: "T", effective: "2026-01-01" }], "2026-05-12", "May 2026"));
});
test("decisions labels become search parameters", () => {
  const qu = interpret("What is the 60-month auto loan APR?", {
    intent: { choice: "rate" }, rate_metric: { choice: "APR" }, website_date: { probability: 0.1 }, "cat:Auto and motorcycle loans": { probability: 0.9 } });
  assert.equal(qu.intent, "rate");
  assert.equal(qu.rate_metric, "APR");
  assert.deepEqual(qu.categories, ["Auto and motorcycle loans"]);
  assert.equal(qu.term, "60 months");
  assert.equal(qu.website_date, null);
});
test("first JSON object is parsed even with trailing data", () => {
  assert.deepEqual(parseFirstJson('  {"a":"x}y","b":[1,2]} trailing {"c":1}'), { a: "x}y", b: [1, 2] });
});
test("winner prefers rate sheet, then later effective date", () => {
  const base = { product: "p", family: "f", qualifiers: {}, metric: "APY", value: "1%", url: "u", published: null, snapshotId: "s", caption: "", categories: [], text: "" };
  const a: Fact = { ...base, pageType: "secondary", effective: "2026-09-01" };
  const b: Fact = { ...base, pageType: "rate_sheet", effective: "2026-01-01" };
  const c: Fact = { ...base, pageType: "rate_sheet", effective: "2026-08-31" };
  assert.equal(winner([a, b, c]), c);
});
