// Reads rate/fee tables straight from the Markdown, with no AI: every numeric cell keeps the exact row, column header, page and dates.
// Port of my_solution/table_parse.py (parse_table / parse_pages; the script-only summary code is not ported).
import { cellsOf } from "./chunker.ts";
import { pageTables, tableKey, type TableInfo } from "./facts.ts";
import { pageRank } from "./tiers.ts";
import type { Page } from "./types.ts";

const EMPTY = new Set(["", "—", "–", "-", "none", "n/a", "na", "--"]);
const HEADER_METRICS: Array<[RegExp, string]> = [
  [/annual percentage yield|\bapy\b/i, "APY"], [/annual percentage rate|\bapr\b/i, "APR"], [/dividend rate/i, "dividend rate"],
  [/interest rate/i, "interest rate"], [/\bfee/i, "fee"], [/payment/i, "payment"], [/\bpoints?\b/i, "points"],
  [/\bmin(imum)?\b|min\./i, "minimum"], [/\bmax(imum)?\b|max\./i, "maximum"], [/\brates?\b/i, "rate"],
];
const CELL_UNIT_RE = /%\s*\**\s*(APR|APY)\b/i;
const INTRO_RE = /\b(1st|first)\s+\d+\s+months?\b|\bintro(ductory)?\b|\bpromotional rate\b/i;
const AFTER_RE = /\bafter\s+(the\s+)?(promotional|promo|intro)/i;
const AS_LOW_AS_RE = /as low as/i;
const NUM = "\\d{1,3}(?:,\\d{3})*(?:\\.\\d+)?|\\d+(?:\\.\\d+)?";
const PCT_RE = new RegExp(`(${NUM})\\s*%`);
const MONEY_RE = new RegExp(`\\$\\s?(${NUM})`);
const RANGE_RE = new RegExp(`(${NUM})\\s*%?\\s*(?:to|-|–)\\s*(${NUM})\\s*%`, "i");
const FOOTNOTE_RE = /((?:%|APR|APY))\s*\\?\*?\d{1,2}\b/gi;
const QUALIFIER_CELL_RE = /^\s*(model\s+years?\s+|\d+\s*(-|to)?\s*\d*\s*(months?|mos?\.?|years?|yrs?)\b|(19|20)\d\d|\$|up to|\d[\d,.]*\s*(\+|or less|or more)|less than|over|under|minimum|maximum)/i;
const TIER_CELL_RE = /\$\s?[\d,.]+\s*(\+|or less|or more|and (up|over|above|below))|\$\s?[\d,.]+\s*(-|–|to)\s*\$?\s?[\d,.]+|\b(up to|less than|over|under)\s+\$/i;
const LABEL_HEADER_RE = /tier|balance$|^balance\b(?!.*(payment|with))|loan amount|amount range|program|loan type|ira type|term/i;
const PRODUCT_HEADER_RE = /account|product|loan type|card|certificate|program|plan|category|type/i;
const FORM_RE = /signature|for office use|applicant|co-applicant|name\/address|social security|statement of financial|creditor|insurance company|no\. shares|address and type of property|\bassets\b|liabilities|date of birth|employer/i;
const SEPARATOR_RE = /^\|?\s*:?-{3,}/;
const RATE_TYPES = new Set(["APR", "APY", "dividend rate", "interest rate", "rate"]);

export interface TableCell {
  url: string; pageType: string; snapshotId: string; fetchedAt: string | null; heading: string; caption: string; note: string;
  effective: string | null; after: string; tableId: string; rowIndex: number; headers: string[]; row: string[]; column: string; raw: string;
  value: string; kind: string; metric: string; unitInCell: string | null; unitConflict: boolean; period: string | null; asLowAs: boolean;
  product: string; productSource: string; qualifiers: Array<[string, string]>;   // insertion-ordered label cells (a Python dict)
}

/** Python's format(x, "g") for the magnitudes seen in rate tables. */
export const fmtG = (x: number): string => String(Number(x.toPrecision(6)));
const fmtMoney = (x: number): string => "$" + x.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const stripChars = (s: string, chars: string): string => { let a = 0, b = s.length; while (a < b && chars.includes(s[a]!)) a++; while (b > a && chars.includes(s[b - 1]!)) b--; return s.slice(a, b); };

export function clean(cell: string): string {
  let c = cell.replace(/\\([*_])/g, "$1").replace(/\*\*|__/g, "");
  c = c.replace(FOOTNOTE_RE, "$1");
  return c.trim();
}

function valueOf(cell: string): [string | null, string] {
  const c = clean(cell);
  if (EMPTY.has(stripChars(c.toLowerCase(), " .*"))) return [null, ""];
  let m = RANGE_RE.exec(c);
  if (m && c.includes("%")) return [`${fmtG(parseFloat(m[1]!.replaceAll(",", "")))}%-${fmtG(parseFloat(m[2]!.replaceAll(",", "")))}%`, "rate"];
  m = PCT_RE.exec(c);
  if (m) return [`${fmtG(parseFloat(m[1]!.replaceAll(",", "")))}%`, "rate"];
  m = MONEY_RE.exec(c);
  if (m) return [fmtMoney(parseFloat(m[1]!.replaceAll(",", ""))), "money"];
  return [null, ""];
}

const headerMetric = (h: string): string | null => { for (const [rx, name] of HEADER_METRICS) if (rx.test(h)) return name; return null; };

function formReason(headers: string[], rows: string[][]): string | null {
  const text = [...headers, ...rows.flat()].join(" ");
  const m = FORM_RE.exec(text);
  if (m) return `form word: ${m[0]}`;
  const cells = rows.flat();
  if (cells.length && cells.filter((c) => !c.trim()).length / cells.length > 0.6) return "mostly empty cells";
  return null;
}

/** Two tables written back to back arrive as one block: a header line followed by a |---| line starts a new one. */
function splitTables(table: string): string[] {
  const lines = table.split("\n").filter((l) => l.trim().startsWith("|"));
  const starts: number[] = [];
  for (let i = 0; i < lines.length - 1; i++) if (SEPARATOR_RE.test(lines[i + 1]!.trim()) && !SEPARATOR_RE.test(lines[i]!.trim())) starts.push(i);
  if (starts.length <= 1) return [lines.join("\n")];
  starts.push(lines.length);
  const out: string[] = [];
  for (let k = 0; k < starts.length - 1; k++) if (starts[k + 1]! - starts[k]! >= 3) out.push(lines.slice(starts[k], starts[k + 1]).join("\n"));
  return out;
}

export function parseTable(t: TableInfo, snapshotId: string, fetchedAt: string | null = null): [TableCell[], string | null] {
  const parts = splitTables(t.table);
  if (parts.length > 1) {
    const cells: TableCell[] = [], reasons: string[] = [];
    for (const part of parts) { const [got, reason] = parseTable({ ...t, table: part }, snapshotId, fetchedAt); cells.push(...got); if (reason) reasons.push(reason); }
    return [cells, reasons.length && !cells.length ? reasons[0]! : null];
  }
  const lines = t.table.split("\n").filter((l) => l.trim().startsWith("|"));
  const headers = cellsOf(lines[0]!);
  let rows = lines.slice(1).filter((l) => !/^\|?\s*:?-{3,}/.test(l.trim())).map(cellsOf);
  rows = rows.filter((r) => JSON.stringify(r) !== JSON.stringify(headers));   // repeated header row
  const reason = formReason(headers, rows);
  if (reason) return [[], reason];
  const tid = tableKey(t).slice(0, 12);
  const ncol = headers.length;
  const isValueCol: boolean[] = [];
  for (let j = 0; j < ncol; j++) {
    const col = rows.filter((r) => j < r.length && !EMPTY.has(stripChars(clean(r[j]!).toLowerCase(), " .*"))).map((r) => r[j]!);
    const vals = col.map(valueOf);
    const rates = vals.filter(([, k]) => k === "rate").length, money = vals.filter(([, k]) => k === "money").length;
    const tierlike = col.filter((c) => TIER_CELL_RE.test(clean(c))).length;
    if (col.length && rates / col.length >= 0.5) isValueCol.push(true);
    else if (col.length && money / col.length >= 0.5) isValueCol.push(!(LABEL_HEADER_RE.test(headers[j]!) || tierlike / col.length >= 0.5));
    else isValueCol.push(false);
  }
  const out: TableCell[] = [];
  rows.forEach((r0, i) => {
    const r = [...r0, ...new Array<string>(Math.max(0, ncol - r0.length)).fill("")];
    const labels = new Map<string, string>();
    for (let j = 0; j < ncol; j++) if (!isValueCol[j] && r[j]!.trim()) labels.set(headers[j]! || `col${j + 1}`, clean(r[j]!));
    let product = "", source = "";
    for (let j = 0; j < ncol; j++) {
      if (isValueCol[j] || !r[j]!.trim()) continue;
      const cell = clean(r[j]!);
      if (!QUALIFIER_CELL_RE.test(cell) && (PRODUCT_HEADER_RE.test(headers[j]!) || j === 0)) { product = cell; source = "row"; break; }
    }
    if (!product) [product, source] = t.caption && t.caption !== t.heading ? [t.caption, "caption"] : [t.heading, "heading"];
    const qualifiers = [...labels].filter(([, v]) => v !== product);
    for (let j = 0; j < ncol; j++) {
      if (!isValueCol[j]) continue;
      const [value, kind] = valueOf(r[j]!);
      if (value === null) continue;
      const col = headers[j]!;
      const hm = headerMetric(col);
      const cu = CELL_UNIT_RE.exec(clean(r[j]!));
      const unit = cu ? cu[1]!.toUpperCase() : null;
      let metric = unit ?? hm ?? (kind === "rate" ? "rate" : "other");
      const conflict = Boolean(unit && hm && RATE_TYPES.has(hm) && hm !== "rate" && hm !== unit);
      if (hm === "points") metric = "points";
      if (kind === "money" && RATE_TYPES.has(metric)) metric = hm && !RATE_TYPES.has(hm) ? hm : "other";
      const period = AFTER_RE.test(col) ? "after_promo" : INTRO_RE.test(col) ? "intro" : null;
      out.push({ url: t.url, pageType: pageRank(t.url), snapshotId, fetchedAt, heading: t.heading, caption: t.caption, note: t.note, effective: t.effective,
        after: t.after ?? "", tableId: tid, rowIndex: i, headers, row: r, column: col, raw: r[j]!, value, kind, metric, unitInCell: unit, unitConflict: conflict,
        period, asLowAs: AS_LOW_AS_RE.test(col) || AS_LOW_AS_RE.test(r[j]!), product, productSource: source, qualifiers });
    }
  });
  return [out, null];
}

/** All numeric cells of a website copy given as page objects. */
export function parsePages(pages: Page[], snapshotId: string): TableCell[] {
  const cells: TableCell[] = [];
  for (const p of pages) for (const t of pageTables(p.url, p.title || "", p.markdown)) cells.push(...parseTable(t, snapshotId, p.fetchedAt ?? null)[0]);
  return cells;
}
