// Failure paths against a local mock of the OpenAI API (no network, no cost): timeouts and retries, no service_tier, the spend guard,
// embedding missing vectors at ingest and reloading them, and the no-key / failing-model behaviour of the whole system.
import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { z } from "zod";

type Handler = (path: string, body: any, res: ServerResponse) => void;
let handler: Handler = (_p, _b, res) => { res.statusCode = 404; res.end("{}"); };
const seen: Array<{ path: string; body: any }> = [];
const server = createServer((req: IncomingMessage, res: ServerResponse) => {
  let raw = "";
  req.on("data", (c) => (raw += c));
  req.on("end", () => { const body = raw ? JSON.parse(raw) : null; seen.push({ path: req.url!, body }); handler(req.url!, body, res); });
});
await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
const port = (server.address() as { port: number }).port;
const tmp = mkdtempSync(join(tmpdir(), "ts-failure-"));
process.env.OPENAI_BASE_URL = `http://127.0.0.1:${port}/v1`;
process.env.OPENAI_API_KEY = "test-key";
process.env.MY_SOLUTION_BUDGET_USD = "0.001";
process.env.MY_SOLUTION_PY_CACHE = join(tmp, "empty-py-cache");   // no stored vectors at all
process.env.MY_SOLUTION_TS_CACHE = join(tmp, "side");
process.env.MY_SOLUTION_FACT_CACHE = join(tmp, "facts.json");
process.env.MY_SOLUTION_SENTENCE_CACHE = join(tmp, "sent.json");

const { askJson, cost, BudgetExceeded, post } = await import("../src/openai.ts");
const { EmbeddingStore, WindowIndex, embedQuery } = await import("../src/embed_index.ts");
const { Knowledge } = await import("../src/solution.ts");
const Schema = z.object({ ok: z.boolean() });
const respOk = (res: ServerResponse, usage = { input_tokens: 10, output_tokens: 5 }) => {
  res.setHeader("content-type", "application/json");
  res.end(JSON.stringify({ output_text: '{"ok":true}', usage }));
};
const ask = (timeoutMs = 400) => askJson({ model: "m", instructions: "i", input: "x", schema: Schema, name: "n", timeoutMs });

before(() => { seen.length = 0; });
after(() => server.close());

test("a request that never answers times out and is retried once", async () => {
  seen.length = 0;
  handler = () => { /* never respond */ };
  await assert.rejects(ask(300), (e: Error) => e.name === "TimeoutError");
  assert.equal(seen.length, 2, "one try plus one retry");
});

test("a 5xx is retried, a 4xx is not", async () => {
  seen.length = 0;
  let n = 0;
  handler = (_p, _b, res) => { if (n++ === 0) { res.statusCode = 503; res.end("busy"); } else respOk(res); };
  assert.deepEqual(await ask(), { ok: true });
  assert.equal(seen.length, 2);
  seen.length = 0;
  handler = (_p, _b, res) => { res.statusCode = 400; res.end("bad"); };
  await assert.rejects(ask(), /400/);
  assert.equal(seen.length, 1);
});

test("the request never carries service_tier (no fast/priority mode) and uses a strict schema", async () => {
  seen.length = 0;
  handler = (_p, _b, res) => respOk(res);
  await ask();
  const b = seen[0]!.body;
  assert.ok(!("service_tier" in b));
  assert.equal(b.text.format.strict, true);
  assert.equal(b.text.format.schema.additionalProperties, false);
  assert.equal(b.temperature, 0);
  assert.deepEqual(b.reasoning, { effort: "none" });
});

test("the spend guard stops calls once the budget is spent", async () => {
  seen.length = 0;
  cost.usd = 0;
  handler = (_p, _b, res) => respOk(res, { input_tokens: 5_000_000, output_tokens: 0 });   // far more than the $0.001 budget
  await ask();                                   // this call is allowed and pushes the tally over the cap
  assert.ok(cost.usd >= 0.001);
  const before = seen.length;
  await assert.rejects(ask(), (e: Error) => e instanceof BudgetExceeded);
  await assert.rejects(post("/embeddings", {}, 100), (e: Error) => e instanceof BudgetExceeded);
  assert.equal(seen.length, before, "no request is sent after the cap");
  cost.usd = 0;
});

test("windows without a vector are embedded at ingest, saved, and found again after a reload", async () => {
  cost.usd = 0;
  seen.length = 0;
  const dim = 8;
  handler = (_p, body, res) => {
    const input: string[] = body.input;
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ usage: { total_tokens: input.length }, data: input.map((t, i) => ({ embedding: Array.from({ length: dim }, (_, j) => ((t.length + i + j) % 7) + 1) })) }));
  };
  const chunk = (text: string) => ({ url: "https://x/a", title: "t", snapshotId: "s", fetchedAt: "d", headerPath: "/", heading: "", kind: "section" as const, text, effective: null, categories: [], published: null });
  const chunks = [chunk("Lobby hours are Monday to Friday, 9 a.m. to 5 p.m. at the main branch in Dubuque."), chunk("The routing number is 273976369 for all Dupaco accounts everywhere.")];
  const wi = new WindowIndex(chunks);
  assert.equal(wi.missing().length, 2);
  assert.equal(await wi.build(true), 0);
  assert.ok(seen.some((r) => r.path.endsWith("/embeddings")));
  const hits = await wi.search("routing number", 2);   // also embeds the question through the mock
  assert.equal(hits.length, 2);
  // a second store reads the side file written by the first
  const again = new EmbeddingStore(join(tmp, "empty-py-cache", "windows-text-embedding-3-small.npz"), "windows.json");
  assert.equal(again.vecs.size, 2);
  const q1 = await embedQuery("a question the mock embeds once");
  const n0 = seen.length;
  const q2 = await embedQuery("a question the mock embeds once");
  assert.deepEqual([...q1], [...q2]);
  assert.equal(seen.length, n0, "the repeated question comes from the stored vector, no new call");
  const norm = Math.hypot(...q1);
  assert.ok(Math.abs(norm - 1) < 1e-5, "vectors are normalised");
});

const snapshot = {
  snapshotId: "s1", takenOn: "2026-05-12",
  pages: [{ url: "https://www.dupaco.com/personal/savings", title: "Savings", fetchedAt: "2026-05-12",
    markdown: "# Share Savings\n\nShare Savings earns 0.20% APY. The routing number is 273976369.\n" }],
};

test("a failing model gives a visible error answer, never a crash or a fake refusal", async () => {
  cost.usd = 0;
  handler = (_p, _b, res) => { res.statusCode = 500; res.end("down"); };
  const ks = new Knowledge();
  await ks.ingest(snapshot);
  const a = await ks.answer("What is the routing number?");
  assert.equal(a.confident, true);
  assert.match(a.conflictNote ?? "", /^LLM call failed: /);
  assert.match(a.text, /system error|did not respond in time/);
  assert.deepEqual(a.sources, []);
});

test("without an API key the system still answers from keyword search", async () => {
  delete process.env.OPENAI_API_KEY;
  const ks = new Knowledge();
  assert.equal(ks.useLlm, false);
  await ks.ingest(snapshot);
  const a = await ks.answer("What is the routing number?");
  assert.match(a.text, /273976369/);
  assert.ok(a.sources.length >= 1);
  assert.deepEqual(await ks.conflicts(), []);
  process.env.OPENAI_API_KEY = "test-key";
});
