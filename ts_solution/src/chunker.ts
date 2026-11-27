// Markdown chunker for the crawled pages. Port of my_solution/chunker.py.
// splitSections re-implements LlamaIndex's MarkdownNodeParser; chunkPage adds the cleaning and the per-table-row pieces.

export interface Chunk {
  url: string; title: string; snapshotId: string; fetchedAt: string;
  headerPath: string;       // parent headings, "/A/B/"
  heading: string;          // this section's own heading ("" if none)
  kind: "section" | "row";
  text: string;
  effective: string | null; // ISO date from "Rates are effective as of MM/DD/YYYY"
  categories: string[];     // set at ingest
  published: string | null;
}

/** What BM25 sees: page title + heading path + body. */
export function indexText(c: Chunk): string {
  return `${c.title} ${c.headerPath.replaceAll("/", " ")} ${c.heading}\n${c.text}`;
}

const HEADER_RE = /^(#+)\s(.*)/s;   // s flag: Python "." matches U+2028, JS "." does not
const IMAGE_RE = /!\[[^\]]*\]\([^)]*\)/g;
const LINK_RE = /\[([^\]]*)\]\(([^)\s]*)[^)]*\)/g;
export const EFFECTIVE_RE = /effective\s+(?:as\s+of\s+)?(\d{1,2})\/(\d{1,2})\/(\d{2,4})/i;
const NOISE_LINES = new Set(["✕", "* * *", "---", "***"]);
const NOISE_LINE_RE = new RegExp(
  "^\\d+\\s+min\\s+read$" +
  "|^(open|closed)\\b[^\\n]{0,60}$" +
  "|^\\d+ results?$|^loading locations|^sorry, we couldn.t find any results|^try searching again" +
  "|^can.t find what you.re looking for", "is");
const FORM_LINE_RE = /\\\*\s*$|\(required\)|^please select|^previousnext$|^\d{1,3}%$/i;
const US_STATES = new Set(`alabama alaska arizona arkansas california colorado connecticut delaware florida georgia
hawaii idaho illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts michigan minnesota
mississippi missouri montana nebraska nevada ohio oklahoma oregon pennsylvania tennessee texas utah vermont
virginia washington wisconsin wyoming`.split(/\s+/).concat(["new hampshire", "new jersey", "new mexico", "new york",
  "north carolina", "north dakota", "rhode island", "south carolina", "south dakota", "west virginia", "district of columbia"]));
const DROP_SECTIONS = new Set(["handpicked for you"]);
export const MAX_SECTION_CHARS = Number(process.env.MY_SOLUTION_SPLIT_CHARS || 3000);

const words = (s: string): string[] => s.split(/\s+/).filter(Boolean);
const lstripChars = (s: string, chars: string): string => { let i = 0; while (i < s.length && chars.includes(s[i]!)) i++; return s.slice(i); };

// ---------------------------------------------------------------- step 1
export function splitSections(text: string, sep = "/"): Array<[string, string]> {
  const out: Array<[string, string]> = [];
  let current = "";
  const stack: Array<[number, string]> = [];
  let code = false;
  const path = (st: Array<[number, string]>): string => {
    const inner = st.map((h) => h[1]).join(sep);
    return inner ? sep + inner + sep : sep;
  };
  for (const line of text.split("\n")) {
    if (line.trimStart().startsWith("```")) { code = !code; current += line + "\n"; continue; }
    if (!code) {
      const m = HEADER_RE.exec(line);
      if (m) {
        if (current.trim()) out.push([path(stack.slice(0, -1)), current.trim()]);
        const level = m[1]!.length, htext = m[2]!;
        while (stack.length && stack[stack.length - 1]![0] >= level) stack.pop();
        stack.push([level, htext]);
        current = "#".repeat(level) + ` ${htext}\n`;
        continue;
      }
    }
    current += line + "\n";
  }
  if (current.trim()) out.push([path(stack.slice(0, -1)), current.trim()]);
  return out;
}

// ---------------------------------------------------------------- step 2
export function isForm(text: string): boolean {
  return text.split("\n").filter((l) => FORM_LINE_RE.test(l.trim())).length >= 2;
}

export function cleanText(text: string, form = false): string {
  const lines: string[] = [];
  for (let line of text.split("\n")) {
    line = line.replace(IMAGE_RE, "");
    line = line.replace(LINK_RE, (_m, a: string, b: string) => (a.trim() ? `${a} (${b})` : b));
    const s = line.trim();
    if (NOISE_LINES.has(s) || NOISE_LINE_RE.test(s) || FORM_LINE_RE.test(s)) continue;
    if (s.startsWith("- ") && US_STATES.has(s.slice(2).trim().toLowerCase())) continue;
    if (form && s && !s.startsWith("|") && words(lstripChars(s, "-* ")).length <= 3) continue;
    lines.push(line.trimEnd());
  }
  return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export function splitHeading(section: string): [string, string] {
  const i = section.indexOf("\n");
  const first = i < 0 ? section : section.slice(0, i), rest = i < 0 ? "" : section.slice(i + 1);
  const m = HEADER_RE.exec(first);
  return m ? [m[2]!.trim(), rest.trim()] : ["", section.trim()];
}

function effectiveOf(text: string): string | null {
  const m = EFFECTIVE_RE.exec(text);
  if (!m) return null;
  const mo = +m[1]!, d = +m[2]!;
  let y = +m[3]!;
  if (y < 100) y += 2000;
  const p = (n: number, w: number) => String(n).padStart(w, "0");
  return mo >= 1 && mo <= 12 && d >= 1 && d <= 31 ? `${p(y, 4)}-${p(mo, 2)}-${p(d, 2)}` : null;
}
export { effectiveOf };

export function blocksOf(body: string): string[] {
  const blocks: string[] = [];
  let cur: string[] = [], inTable = false;
  for (const line of body.split("\n")) {
    const isRow = line.trimStart().startsWith("|");
    if (isRow !== inTable && cur.length) { blocks.push(cur.join("\n")); cur = []; }
    inTable = isRow;
    if (!line.trim() && !inTable) { if (cur.length) { blocks.push(cur.join("\n")); cur = []; } continue; }
    cur.push(line);
  }
  if (cur.length) blocks.push(cur.join("\n"));
  return blocks.filter((b) => b.trim());
}

export const cellsOf = (line: string): string[] => line.trim().replace(/^\|+/, "").replace(/\|+$/, "").split("|").map((c) => c.trim());

function rowChunks(blocks: string[], heading: string): Array<[string, string | null]> {
  const out: Array<[string, string | null]> = [];
  blocks.forEach((b, i) => {
    if (!b.trimStart().startsWith("|")) return;
    const lines = b.split("\n").filter((l) => l.trim());
    if (lines.length < 3) return;
    const headers = cellsOf(lines[0]!);
    const rows = lines.slice(1).filter((l) => !/^[\s|:\-]+$/.test(l));
    let caption = heading;
    for (let j = i - 1; j >= 0; j--) if (!blocks[j]!.trimStart().startsWith("|")) { caption = blocks[j]!; break; }
    caption = caption ? caption.split("\n").at(-1)!.trim() : heading;
    const after = blocks.slice(i + 1, i + 3).join(" ");
    const note = after.split(/(?<=\.)\s/).map((s) => s.trim()).find((s) => EFFECTIVE_RE.test(s)) ?? "";
    for (const r of rows) {
      const cells = cellsOf(r);
      const pairs = headers.slice(0, cells.length).map((h, k) => (h ? `${h}: ${cells[k]}` : cells[k]!)).concat(cells.slice(headers.length));
      out.push([[caption, ...pairs, note].filter(Boolean).join(" | "), effectiveOf(note)]);
    }
  });
  return out;
}

const MONTH_DATE_RE = /\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d\d)\b/;
const URL_DATE_RE = /\/(20\d\d)\/(\d\d)\/(\d\d)\//;
const URL_YEAR_RE = /[-_/](20\d\d)[-_.]/;
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

export function publishedDate(url: string, markdown: string): string | null {
  let m = URL_DATE_RE.exec(url);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  m = MONTH_DATE_RE.exec(markdown.slice(0, 1500));
  if (m) return `${m[3]}-${String(MONTHS.indexOf(m[1]!) + 1).padStart(2, "0")}-${String(+m[2]!).padStart(2, "0")}`;
  m = URL_YEAR_RE.exec(url);
  return m ? `${m[1]}-12-31` : null;
}

export const normBlock = (b: string): string => words(b.toLowerCase()).join(" ");

export function pageBlocks(markdown: string): string[] {
  const out: string[] = [];
  for (const [, section] of splitSections(markdown)) {
    const [heading, body] = splitHeading(section);
    if (DROP_SECTIONS.has(heading.trim().toLowerCase())) continue;
    out.push(...blocksOf(cleanText(body, isForm(body))));
  }
  return out;
}

export function chunkPage(url: string, title: string, markdown: string, snapshotId: string, fetchedAt: string,
                          dropBlocks: ReadonlySet<string> = new Set()): Chunk[] {
  const chunks: Chunk[] = [];
  let carry = "";
  const mk = (headerPath: string, heading: string, kind: "section" | "row", text: string, effective: string | null): Chunk =>
    ({ url, title, snapshotId, fetchedAt, headerPath, heading, kind, text, effective, categories: [], published: null });
  for (const [headerPath, section] of splitSections(markdown)) {
    let [heading, body] = splitHeading(section);
    if (DROP_SECTIONS.has(heading.trim().toLowerCase())) { carry = ""; continue; }
    body = cleanText(body, isForm(body));
    if (!body) { carry = `${carry} ${heading}`.trim(); continue; }
    if (carry) { heading = heading ? `${carry} / ${heading}` : carry; carry = ""; }
    const blocks = blocksOf(body).filter((b) => b.trimStart().startsWith("|") || !dropBlocks.has(normBlock(b)));
    if (!blocks.length) continue;
    const eff = effectiveOf(body);
    let cur: string[] = [];
    for (const b of blocks) {
      if (cur.length && cur.reduce((n, x) => n + x.length, 0) + b.length > MAX_SECTION_CHARS) {
        chunks.push(mk(headerPath, heading, "section", cur.join("\n\n"), eff));
        cur = [];
      }
      cur.push(b);
    }
    if (cur.length) chunks.push(mk(headerPath, heading, "section", cur.join("\n\n"), eff));
    for (const [text, rowEff] of rowChunks(blocks, heading)) chunks.push(mk(headerPath, heading, "row", text, rowEff ?? eff));
  }
  const pub = publishedDate(url, markdown);
  for (const c of chunks) c.published = pub;
  return chunks;
}
