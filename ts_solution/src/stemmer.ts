// Snowball English stemmer (current english.sbl as shipped in PyStemmer 3.x), hand-ported so no dependency is needed.
// Verified word-for-word against PyStemmer on the site vocabulary (parity/stem_check.ts).
const isV = (c: string | undefined): boolean => c !== undefined && "aeiouy".includes(c);
const DOUBLES = ["bb", "dd", "ff", "gg", "mm", "nn", "pp", "rr", "tt"];
const VALID_LI = "cdeghkmnrt";
const R1_PREFIXES = ["gener", "commun", "arsen", "past", "univers", "later", "emerg", "organ", "inter"];
const EXCEPTIONS: Record<string, string> = {
  skis: "ski", skies: "sky", idly: "idl", gently: "gentl", ugly: "ugli", early: "earli", only: "onli", singly: "singl",
  sky: "sky", news: "news", howe: "howe", atlas: "atlas", cosmos: "cosmos", bias: "bias", andes: "andes",
};
const ING_KEEP = ["inn", "out", "cann", "herr", "earr", "even"];

function longest(w: string, sufs: string[]): string | null {
  let best: string | null = null;
  for (const s of sufs) if (w.endsWith(s) && (best === null || s.length > best.length)) best = s;
  return best;
}
const hasVowel = (s: string): boolean => [...s].some((c) => isV(c));

/** end-of-word short syllable (Snowball shortv). */
function shortv(w: string): boolean {
  const n = w.length;
  const last = w[n - 1];
  if (n >= 3 && !isV(w[n - 3]) && isV(w[n - 2]) && last !== undefined && !isV(last) && !"wxY".includes(last)) return true;
  if (n === 2 && isV(w[0]) && !isV(w[1])) return true;
  return w.endsWith("past");
}

export function stem(input: string): string {
  if (input in EXCEPTIONS) return EXCEPTIONS[input]!;
  if (input.length < 3) return input;
  let w = input;

  // prelude
  let yFound = false;
  if (w.startsWith("'")) w = w.slice(1);
  if (w[0] === "y") { w = "Y" + w.slice(1); yFound = true; }
  { const a = [...w]; for (let i = 1; i < a.length; i++) if (a[i] === "y" && isV(a[i - 1])) { a[i] = "Y"; yFound = true; } w = a.join(""); }

  // mark regions
  let p1 = w.length, p2 = w.length;
  const gopast = (from: number): number => {   // past the first vowel then the first non-vowel, from index `from`
    let i = from;
    while (i < w.length && !isV(w[i])) i++;
    while (i < w.length && isV(w[i])) i++;
    return i < w.length ? i + 1 : w.length;
  };
  const prefix = R1_PREFIXES.find((p) => w.startsWith(p));
  p1 = prefix ? prefix.length : gopast(0);
  p2 = p1 >= w.length ? w.length : gopast(p1);
  const inR1 = (suf: string) => w.length - suf.length >= p1;
  const inR2 = (suf: string) => w.length - suf.length >= p2;

  // step 1a
  const s0 = longest(w, ["'", "'s", "'s'"]);
  if (s0) w = w.slice(0, -s0.length);
  const s1a = longest(w, ["sses", "ied", "ies", "s", "us", "ss"]);
  if (s1a === "sses") w = w.slice(0, -2);
  else if (s1a === "ied" || s1a === "ies") w = w.slice(0, -s1a.length) + (w.length - s1a.length >= 2 ? "i" : "ie");
  else if (s1a === "s" && hasVowel(w.slice(0, -2))) w = w.slice(0, -1);

  // step 1b
  const s1b = longest(w, ["eedly", "eed", "edly", "ed", "ingly", "ing"]);
  if (s1b === "eed" || s1b === "eedly") {
    if (inR1(s1b)) {
      const before = w.slice(0, -s1b.length);
      if (!["proc", "exc", "succ"].includes(before)) w = before + "ee";
    }
  } else if (s1b) {
    let handled = false;
    const before = w.slice(0, -s1b.length);
    if (s1b === "ing") {
      if (before.endsWith("y") && before.length === 2 && !isV(before[0])) { w = before.slice(0, -1) + "ie"; handled = true; }
      else if (ING_KEEP.some((k) => before === k)) handled = true;
    }
    if (!handled && hasVowel(before)) {
      w = before;
      if (/(at|bl|iz)$/.test(w)) w += "e";
      else if (DOUBLES.some((d) => w.endsWith(d))) {
        if (!(w.length === 3 && "aeo".includes(w[0]!))) w = w.slice(0, -1);   // not [aeo]+double ("add", "err")
      } else if (w.length === p1 && shortv(w)) w += "e";
    }
  }

  // step 1c
  if (/[yY]$/.test(w) && w.length >= 3 && !isV(w[w.length - 2])) w = w.slice(0, -1) + "i";

  // step 2
  const s2 = longest(w, ["tional", "enci", "anci", "abli", "entli", "izer", "ization", "ational", "ation", "ator", "alism", "aliti", "alli",
    "fulness", "ousli", "ousness", "iveness", "iviti", "biliti", "bli", "ogist", "ogi", "fulli", "lessli", "li"]);
  if (s2 && inR1(s2)) {
    const head = w.slice(0, -s2.length);
    const rep: Record<string, string> = { tional: "tion", enci: "ence", anci: "ance", abli: "able", entli: "ent", izer: "ize", ization: "ize",
      ational: "ate", ation: "ate", ator: "ate", alism: "al", aliti: "al", alli: "al", fulness: "ful", ousli: "ous", ousness: "ous",
      iveness: "ive", iviti: "ive", biliti: "ble", bli: "ble", ogist: "og", fulli: "ful", lessli: "less" };
    if (s2 === "ogi") { if (head.endsWith("l")) w = head + "og"; }
    else if (s2 === "li") { if (head.length && VALID_LI.includes(head.at(-1)!)) w = head; }
    else w = head + rep[s2]!;
  }

  // step 3
  const s3 = longest(w, ["tional", "ational", "alize", "icate", "iciti", "ical", "ful", "ness", "ative"]);
  if (s3 && inR1(s3)) {
    const head = w.slice(0, -s3.length);
    const rep: Record<string, string> = { tional: "tion", ational: "ate", alize: "al", icate: "ic", iciti: "ic", ical: "ic" };
    if (s3 === "ful" || s3 === "ness") w = head;
    else if (s3 === "ative") { if (inR2(s3)) w = head; }
    else w = head + rep[s3]!;
  }

  // step 4
  const s4 = longest(w, ["al", "ance", "ence", "er", "ic", "able", "ible", "ant", "ement", "ment", "ent", "ism", "ate", "iti", "ous", "ive", "ize", "ion"]);
  if (s4 && inR2(s4)) {
    const head = w.slice(0, -s4.length);
    if (s4 === "ion") { if (/[st]$/.test(head)) w = head; }
    else w = head;
  }

  // step 5
  if (w.endsWith("e")) {
    const head = w.slice(0, -1);
    if (inR2("e") || (inR1("e") && !shortv(head))) w = head;
  } else if (w.endsWith("ll") && inR2("l")) w = w.slice(0, -1);

  return yFound ? w.replace(/Y/g, "y") : w;
}
