// Sends one answer call and one Decisions call through the TS client (to a mock server, see compare_requests.py).
import { DecisionsUnderstanding } from "../src/decisions.ts";
import { AnswerLLM } from "../src/llm.ts";
import { buildUserMessage, developerMessageFor } from "../src/prompt.ts";

const q = "What is the routing number?";
const msg = buildUserMessage(q, [{ n: 1, pageType: "product_page", url: "https://www.dupaco.com/x", text: "Dupaco's routing number is 273976369." }], null);
await new AnswerLLM().ask(msg, developerMessageFor(q, "fact_about_dupaco"));
await new DecisionsUnderstanding().parse(q);
