import { test } from "node:test";
import assert from "node:assert/strict";
import { countQuestion } from "../src/count_facts.ts";
import { questionDate, yearlessMonth, setReference } from "../src/dates.ts";
import { softRefusal } from "../src/solution.ts";

test("count shortcut: filler words allowed, 'in person' is not a place", () => {
  assert.equal(countQuestion("number of dupaco branches"), "branches");
  assert.equal(countQuestion("what is the number of branches dupaco has"), "branches");
  assert.equal(countQuestion("We like banking in person. How many branches does Dupaco have altogether?"), "branches");
  assert.equal(countQuestion("number of dupaco employees"), "employees");
  // still a different question
  assert.equal(countQuestion("How many branches in Dubuque?"), null);
  assert.equal(countQuestion("number of new members"), null);
  assert.equal(countQuestion("How many ATMs does Dupaco have?"), null);
  assert.equal(countQuestion("How many branches in 2023?"), null);
});
test("dates: 'May of 2026' is read like 'May 2026'", () => {
  setReference("2026-09-28");
  assert.equal(questionDate("around May of 2026 I opened it"), "2026-05-31");
  assert.equal(questionDate("what was it in may of 2026"), "2026-05-31");
  assert.equal(questionDate("what was it in May 2026"), "2026-05-31");
  assert.equal(yearlessMonth("what was it in may of 2026"), null, "a stated year is not a year-less month");
  assert.equal(questionDate("what was it in May"), "2026-05-31");
  assert.equal(questionDate("May I open an account?"), null);
});
test("soft refusal: not-listed answer with no rate or dollar amount of its own", () => {
  assert.equal(softRefusal("Dupaco’s listed mortgage terms go up to 30 years; a 40-year mortgage and its rate aren’t listed.", "Do you have a 40 year mortgage? What is the rate?"), true);
  assert.equal(softRefusal("The rate isn't listed, but the 30-year fixed rate is 7.25%.", "What is the rate on a 40-year mortgage?"), false);
  assert.equal(softRefusal("The 12-month certificate pays 3.40% APY.", "What does the 12-month certificate pay?"), false);
});
