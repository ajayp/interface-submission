// Work out which date a question is asking about. Port of my_solution/dates.py.
const FULL = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];
const NAMES = FULL.map((m) => m[0]!.toUpperCase() + m.slice(1));
export const MONTHS: Record<string, number> = {};
FULL.forEach((m, i) => { MONTHS[m] = i + 1; MONTHS[m.slice(0, 3)] = i + 1; });
MONTHS["sept"] = 9;
const byLen = (a: string[]) => [...a].sort((x, y) => y.length - x.length);
const MONTH = "(" + byLen(Object.keys(MONTHS)).join("|") + ")";
export const MONTH_YEAR_RE = new RegExp("\\b" + MONTH + "\\.?\\s+(\\d{1,2}(?:st|nd|rd|th)?,?\\s*)?(20\\d\\d)\\b", "id");
export const ISO_RE = /\b(20\d\d)-(\d\d)-(\d\d)\b/d;
export const NUMERIC_RE = /\b(\d{1,2})\/(\d{1,2})\/(20\d\d|\d\d)\b/d;
const BEFORE_RE = /\b(before|prior to|until|up to)\s+(the\s+)?(start of\s+|beginning of\s+)?$/i;
export const PART_RE = /\b(early|mid|middle of|late|end of)[\s-]+(in\s+)?$/i;
const PART_DAY: Record<string, number> = { early: 10, mid: 15, "middle of": 15 };   // late / end of = last day of the month

export const YEARLESS = (process.env.MY_SOLUTION_YEARLESS_DATE ?? "1") === "1";
let REFERENCE: string | null = null;   // newest copy's date, set when the copies are loaded
export const setReference = (d: string | null): void => { REFERENCE = d; };
const FULL_MONTHS = "(" + byLen([...FULL, "sept"]).join("|") + ")";
const YEARLESS_RE = new RegExp(
  "\\b(?:as of|back in|in|during|on|for|from|before|prior to|until|early|mid|late|end of)[\\s-]+(?:the\\s+)?(?:(?:early|mid|middle of|late|end of)[\\s-]+)?" +
  FULL_MONTHS + "\\b(?!\\s*,?\\s*(?:\\d{1,2}(?:st|nd|rd|th)?,?\\s*)?(?:20)?\\d\\d\\b)", "id");

const monthLen = (y: number, m: number): number => new Date(Date.UTC(y, m, 0)).getUTCDate();
const pad = (n: number, w = 2): string => String(n).padStart(w, "0");

export function isoDate(year: number, month: number, day: number): string | null {
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > monthLen(year, month)) return null;
  return `${pad(year, 4)}-${pad(month)}-${pad(day)}`;
}
const dayBefore = (iso: string): string => new Date(Date.parse(iso + "T00:00:00Z") - 86400000).toISOString().slice(0, 10);
const startOf = (m: RegExpExecArray, g: number): number => (m as any).indices[g][0] as number;

export function yearlessMonth(question: string): [RegExpExecArray, number] | null {
  if (!YEARLESS) return null;
  const m = YEARLESS_RE.exec(question);
  return m ? [m, MONTHS[m[1]!.toLowerCase()]!] : null;
}

function yearlessDate(question: string): string | null {
  const hit = yearlessMonth(question);
  if (!hit || !REFERENCE) return null;
  const [m, mo] = hit;
  const ref = new Date(REFERENCE + "T00:00:00Z");
  const year = mo <= ref.getUTCMonth() + 1 ? ref.getUTCFullYear() : ref.getUTCFullYear() - 1;
  const part = PART_RE.exec(question.slice(0, startOf(m, 1)));
  const day = part ? PART_DAY[part[1]!.toLowerCase()] : undefined;
  return isoDate(year, mo, day ?? monthLen(year, mo));
}

export function questionDate(question: string): string | null {
  let date: string | null = null, first: string | null = null;
  let m: RegExpExecArray | null = ISO_RE.exec(question);
  if (m) { date = first = isoDate(+m[1]!, +m[2]!, +m[3]!); }
  else {
    m = NUMERIC_RE.exec(question);
    if (m) {
      const year = +m[3]! + (m[3]!.length === 2 ? 2000 : 0);
      date = first = isoDate(year, +m[1]!, +m[2]!);
    }
    if (date === null) {
      m = MONTH_YEAR_RE.exec(question);
      if (m) {
        const mo = MONTHS[m[1]!.toLowerCase()]!, year = +m[3]!;
        if (m[2]) date = first = isoDate(year, mo, parseInt(m[2]!, 10));
        else {
          const part = PART_RE.exec(question.slice(0, m.index));
          const day = part ? PART_DAY[part[1]!.toLowerCase()] : undefined;
          date = isoDate(year, mo, day ?? monthLen(year, mo));
          first = isoDate(year, mo, 1);   // "before <month>" = before the month starts
        }
      }
    }
  }
  if (date === null && m === null) return yearlessDate(question);
  if (date === null || m === null) return date;
  if (BEFORE_RE.test(question.slice(0, m.index))) return first ? dayBefore(first) : null;
  return date;
}

export const targetDate = (question: string, asOf?: string | null): string | null => (asOf ? asOf.slice(0, 10) : null) || questionDate(question);

/** "before / prior to / until <date>": one point in time (the day before), not a change question. */
export function asksBeforeDate(question: string): boolean {
  for (const rx of [ISO_RE, NUMERIC_RE, MONTH_YEAR_RE]) {
    const m = rx.exec(question);
    if (m) return BEFORE_RE.test(question.slice(0, m.index));
  }
  return false;
}

/** The date as the member wrote it: "June 20, 2026" for a day, "June 2026" for a month. */
export function describe(question: string, iso: string, asOf = false): string {
  const [y, mo, d] = iso.split("-").map(Number) as [number, number, number];
  const month = NAMES[mo - 1]!;
  if (asOf) return `${month} ${d}, ${y}`;
  if (ISO_RE.test(question) || NUMERIC_RE.test(question)) return `${month} ${d}, ${y}`;
  const m = MONTH_YEAR_RE.exec(question);
  if (m && m[2]) return `${month} ${d}, ${y}`;
  const hit = yearlessMonth(question);
  if (hit) {
    const part = PART_RE.exec(question.slice(0, startOf(hit[0], 1)));
    return (part ? part[1]!.toLowerCase() + " " : "") + `${month} ${y}`;
  }
  const part = m ? PART_RE.exec(question.slice(0, m.index)) : null;
  return (part ? part[1]!.toLowerCase() + " " : "") + `${month} ${y}`;
}
