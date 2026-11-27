// The answer-step model call. Port of my_solution/llm.py: gpt-6-luna, Responses API, reasoning effort "none" + temperature 0, strict
// JSON schema (zod), 6 s timeout with one retry. NEVER sends a service_tier option (no "fast"/priority mode).
import { AnswerSchema, DEVELOPER_MESSAGE, type AnswerOut } from "./prompt.ts";
import { askJson, available, cost } from "./openai.ts";

const ANSWER_EFFORT = process.env.MY_SOLUTION_ANSWER_EFFORT ?? "none";
const REASONING_TIMEOUT_MS = 45000;
const TIMEOUT_MS = 6000;   // with one retry a stuck call costs at most ~12 s

export class AnswerLLM {
  readonly model: string;
  private warned = false;
  constructor(model?: string) { this.model = model ?? process.env.OPENAI_MODEL ?? "gpt-6-luna"; }
  available(): boolean { return available(); }

  /** Opens the HTTPS connection during (untimed) ingest so the first answer is not slow. */
  async warmUp(): Promise<void> {
    try {
      const r = await fetch(`${process.env.OPENAI_BASE_URL ?? "https://api.openai.com/v1"}/models/${this.model}`, {
        headers: { authorization: `Bearer ${process.env.OPENAI_API_KEY}` }, signal: AbortSignal.timeout(10000) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
    } catch (e) {
      if (!this.warned) {
        this.warned = true;
        console.error(`[ts_solution] WARNING: the OpenAI model '${this.model}' could not be reached (${(e as Error).message}). Until this is fixed, answers will be "I don't know". Check OPENAI_API_KEY and access to the model.`);
      }
    }
  }

  /** The answer step. `instructions` overrides the system message; `effort` overrides the reasoning effort for this call. */
  ask(userMessage: string, instructions?: string, effort?: string): Promise<AnswerOut> {
    const e = effort ?? ANSWER_EFFORT;
    return askJson({ model: this.model, instructions: instructions ?? DEVELOPER_MESSAGE, input: userMessage, schema: AnswerSchema, name: "member_answer",
      cacheKey: "dupaco-answer-v1", effort: e, maxTokens: e === "none" ? 600 : 6000, timeoutMs: e === "none" ? TIMEOUT_MS : REASONING_TIMEOUT_MS });
  }

  get usage() { return cost; }
}
