// Answer-step prompts. The text lives in data/prompts.json, exported from my_solution/prompt.py (variant G2, default switches), so the
// wording is identical to the Python system. Only variant G2 is ported; the other variants are off by default there and were not adopted.
import { createHash } from "node:crypto";
import { z } from "zod";
import prompts from "../data/prompts.json" with { type: "json" };
import { PRODUCT, PROMO, RATE_SHEET, SECONDARY, type Rank } from "./tiers.ts";

export const PAGE_TYPE_LABEL: Record<Rank, string> = { [RATE_SHEET]: "rate_sheet", [PRODUCT]: "product_page", [PROMO]: "promo_page", [SECONDARY]: "secondary" };

export const AnswerSchema = z.object({
  answer: z.string().describe("The member-facing answer, 1-3 plain sentences."),
  confident: z.boolean().describe("false when the excerpts do not state the answer."),
  used_excerpts: z.array(z.number().int()).describe("n of every excerpt the answer's facts come from."),
  conflict_note: z.string().nullable().describe("When excerpts disagree: the competing values, which you chose and why. Else null."),
});
export type AnswerOut = z.infer<typeof AnswerSchema>;

export const DEVELOPER_MESSAGE: string = prompts.developer;
const INTENT_BLOCKS: Record<string, string> = prompts.intent_blocks;
export const HISTORY_BLOCK: string = prompts.history_block;
const STATE_DATE = (process.env.MY_SOLUTION_STATE_DATE ?? "1") === "1";
const INTENT_SWITCH = (process.env.MY_SOLUTION_INTENT_SWITCH ?? "1") === "1";
const DATE_NOTE_EXPLAIN = (process.env.MY_SOLUTION_DATE_NOTE_EXPLAIN ?? "1") === "1";
export const stateDateOn = (): boolean => STATE_DATE;

/** Which block applies: the question's wording wins over the label for counts ("how many"). */
export function intentBlockName(question: string, intent?: string | null): string | null {
  if (/\bhow many\b/i.test(question ?? "")) return "fact_about_dupaco";
  return intent && intent in INTENT_BLOCKS ? intent : null;
}

export function historyDeveloperMessage(): string { return DEVELOPER_MESSAGE + "\n\n# Question type\n" + HISTORY_BLOCK; }

/** The answer-step system message: the base prompt, the dated-question block when the question has a date, and the intent block. */
export function developerMessageFor(question: string, intent: string | null | undefined, stateDate = false): string {
  let msg = DEVELOPER_MESSAGE;
  if (stateDate && STATE_DATE) {
    msg += "\n\n" + prompts.date_block;
    if (DATE_NOTE_EXPLAIN) msg += prompts.date_block_explain;
  }
  const name = INTENT_SWITCH ? intentBlockName(question, intent) : null;
  if (name) msg += "\n\n# Question type\n" + INTENT_BLOCKS[name];
  return msg;
}

export interface Excerpt { n: number; pageType: string; url: string; text: string; effective?: string | null; published?: string | null; copies?: string | null }

/** The user message. The input id is derived from the request, so identical input gives an identical prompt (consistency). */
export function buildUserMessage(question: string, excerpts: Excerpt[], date: string | null, asked?: string | null): string {
  const nonce = createHash("sha256").update(JSON.stringify([question, date, excerpts, asked ?? null])).digest("hex").slice(0, 12);
  const lines = [`Input id: ${nonce}`];
  if (date) lines.push(`Website as of: ${date}`);
  if (asked && STATE_DATE) lines.push(`Question date: ${asked}`);
  lines.push(`<question id="${nonce}">${question}</question>`);
  for (const e of excerpts) {
    let attrs = e.effective ? ` effective="${e.effective}"` : "";
    if (e.published) attrs += ` published="${e.published}"`;
    if (e.copies) attrs += ` copies="${e.copies}"`;
    lines.push(`<excerpt id="${nonce}" n="${e.n}" page_type="${e.pageType}" url="${e.url}"${attrs}>\n${e.text}\n</excerpt>`);
  }
  return lines.join("\n");
}
