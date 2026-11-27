import { test } from "node:test";
import assert from "node:assert/strict";
import { half } from "../src/npz.ts";
import { fuse, textKey } from "../src/embed_index.ts";

test("float16 decode", () => {
  assert.equal(half(0x3c00), 1);
  assert.equal(half(0xc000), -2);
  assert.equal(half(0x0000), 0);
  assert.ok(Math.abs(half(0x3555) - 0.33325) < 1e-4);
});
test("text key ignores case and whitespace", () => {
  assert.equal(textKey("Hello   World\n"), textKey("hello world"));
});
test("reciprocal-rank fusion", () => {
  assert.deepEqual(fuse([[1, 2, 3], [3, 1]]).slice(0, 2), [1, 3]);
});
