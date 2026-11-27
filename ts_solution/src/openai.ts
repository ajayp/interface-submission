// Minimal OpenAI client on built-in fetch. Structured outputs come from zod schemas (z.toJSONSchema, strict).
// Keeps a running cost tally and refuses calls once the budget is spent (MY_SOLUTION_BUDGET_USD, default 2).
import { z } from "zod";

const BASE = process.env.OPENAI_BASE_URL ?? "https://api.openai.com/v1";

// USD per 1M tokens: [input, cached input, output]. Rough, for the budget guard only; override via MY_SOLUTION_PRICES JSON.
const PRICES: Record<string, [number, number, number]> = JSON.parse(process.env.MY_SOLUTION_PRICES ?? "{}");
const DEFAULT_PRICE: [number, number, number] = [0.5, 0.05, 2.0]; // conservative guess when the model is unknown
const EMBED_PRICE = 0.02; // text-embedding-3-small, per 1M tokens

export class BudgetExceeded extends Error {}

export const cost = { usd: 0, calls: 0, inputTokens: 0, outputTokens: 0, embedTokens: 0 };
const BUDGET = Number(process.env.MY_SOLUTION_BUDGET_USD ?? "2");

function guard(): void {
  if (cost.usd >= BUDGET) throw new BudgetExceeded(`OpenAI budget of $${BUDGET} reached ($${cost.usd.toFixed(4)} spent)`);
}

export function available(): boolean { return Boolean(process.env.OPENAI_API_KEY); }

export async function post<T = any>(path: string, body: unknown, timeoutMs: number, retries = 1): Promise<T> {
  guard();
  let last: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const r = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${process.env.OPENAI_API_KEY}` },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(timeoutMs),
      });
      if (!r.ok) {
        const err = Object.assign(new Error(`OpenAI ${path} ${r.status}: ${(await r.text()).slice(0, 300)}`), { status: r.status });
        if (r.status < 500 && r.status !== 429) throw Object.assign(err, { fatal: true });
        throw err;
      }
      return (await r.json()) as T;
    } catch (e) {
      last = e;
      if ((e as any)?.fatal) throw e;
    }
  }
  throw last;
}

export interface JsonCallOptions<S extends z.ZodType> {
  model: string; instructions: string; input: string; schema: S; name: string;
  cacheKey?: string; maxTokens?: number; timeoutMs?: number; effort?: string;
}

/** One structured Responses call. Returns the parsed, zod-validated object. */
export async function askJson<S extends z.ZodType>(o: JsonCallOptions<S>): Promise<z.infer<S>> {
  const { $schema: _drop, ...schema } = z.toJSONSchema(o.schema) as Record<string, unknown>;
  const effort = o.effort ?? "none";
  const body: Record<string, unknown> = {
    model: o.model, instructions: o.instructions, input: o.input,
    reasoning: { effort },
    text: { format: { type: "json_schema", name: o.name, schema, strict: true } },
    max_output_tokens: o.maxTokens ?? 600,
  };
  if (effort === "none") body.temperature = 0;
  if (o.cacheKey) body.prompt_cache_key = o.cacheKey;
  // No service_tier option is ever sent: the default tier only (no "priority"/fast mode).
  const r: any = await post("/responses", body, o.timeoutMs ?? 6000);
  const u = r.usage ?? {};
  const cached = u.input_tokens_details?.cached_tokens ?? 0;
  const [pin, pcache, pout] = PRICES[o.model] ?? DEFAULT_PRICE;
  cost.calls++; cost.inputTokens += u.input_tokens ?? 0; cost.outputTokens += u.output_tokens ?? 0;
  cost.usd += (((u.input_tokens ?? 0) - cached) * pin + cached * pcache + (u.output_tokens ?? 0) * pout) / 1e6;
  return o.schema.parse(parseFirstJson(outputText(r)));
}

function outputText(r: any): string {
  if (typeof r.output_text === "string") return r.output_text;
  return (r.output ?? []).flatMap((m: any) => m.content ?? []).map((c: any) => c.text ?? "").join("");
}

/** First JSON object in the text (gpt-6-luna once returned an object followed by extra data). */
export function parseFirstJson(text: string): unknown {
  const s = text.trim();
  const start = s.indexOf("{");
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < s.length; i++) {
    const c = s[i]!;
    if (inStr) { esc = c === "\\" ? !esc : false; if (c === '"' && !esc) inStr = false; continue; }
    if (c === '"') inStr = true;
    else if (c === "{") depth++;
    else if (c === "}" && --depth === 0) return JSON.parse(s.slice(start, i + 1));
  }
  throw new Error("no JSON object in model output");
}

export async function embed(model: string, texts: string[]): Promise<Float32Array[]> {
  const r = await post<any>("/embeddings", { model, input: texts }, 60000, 2);
  cost.embedTokens += r.usage?.total_tokens ?? 0;
  cost.usd += (r.usage?.total_tokens ?? 0) * EMBED_PRICE / 1e6;
  return r.data.map((d: any) => {
    const v = Float32Array.from(d.embedding as number[]);
    const n = Math.hypot(...v) || 1;
    return v.map((x) => x / n);
  });
}
