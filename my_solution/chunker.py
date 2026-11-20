"""
Markdown chunker for the crawled pages.

Step 1 (`split_sections`) is a re-implementation of LlamaIndex's MarkdownNodeParser
(llama-index-core, MIT licence, node_parser/file/markdown.py): split on `#` headings, ignore
headings inside fenced code blocks, and record the path of parent headings. It must produce the
same sections as the library; `retrieval_eval.py --parity` checks that when llama-index is
installed.

Step 2 (`chunk_page`) is ours and is what makes tiers searchable:
  - clean noise lines (images, the "✕" close button, separators, "N min read")
  - drop "Handpicked for You" related-post sections (blog teasers inside product pages)
  - fold heading-only sections into the section that follows them
  - split oversized sections at paragraph boundaries (never inside a table)
  - emit one extra chunk per table row that repeats the table caption, the column headers and
    the "effective as of" note, so "60-month 2024-27 model year" can match a single row
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

HEADER_RE = re.compile(r"^(#+)\s(.*)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]*)[^)]*\)")
EFFECTIVE_RE = re.compile(r"effective\s+(?:as\s+of\s+)?(\d{1,2})/(\d{1,2})/(\d{2,4})", re.I)
NOISE_LINES = {"✕", "* * *", "---", "***"}
NOISE_LINE_RE = re.compile(
    r"^\d+\s+min\s+read$"
    # live open/closed status from the branch-locator widget: true only at the moment of the crawl
    r"|^(open|closed)\b[^\n]{0,60}$"
    # search-widget furniture: result counts and status messages are not facts about the credit union
    r"|^\d+ results?$|^loading locations|^sorry, we couldn.t find any results|^try searching again"
    r"|^can.t find what you.re looking for", re.I)
# Web-form noise: field labels marked required ("First Name\\*", "(Required)"), select prompts,
# step indicators, and US-state pick lists. They are page furniture, not facts, and they matched
# questions about contact details while carrying no answer.
FORM_LINE_RE = re.compile(r"\\\*\s*$|\(required\)|^please select|^previousnext$|^\d{1,3}%$", re.I)
US_STATES = set("""alabama alaska arizona arkansas california colorado connecticut delaware florida georgia
hawaii idaho illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts michigan minnesota
mississippi missouri montana nebraska nevada ohio oklahoma oregon pennsylvania tennessee texas utah vermont
virginia washington wisconsin wyoming""".split()) | {"new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "rhode island", "south carolina", "south dakota", "west virginia",
    "district of columbia"}
DROP_SECTIONS = {"handpicked for you"}
# Experiment switch MY_SOLUTION_SPLIT_CHARS: paragraphs of a section are packed into one piece up to this many characters
# (never splitting inside a paragraph or table). Default 3000 = the original behaviour; smaller = paragraph-sized pieces.
MAX_SECTION_CHARS = int(os.getenv("MY_SOLUTION_SPLIT_CHARS") or 3000)


@dataclass
class Chunk:
    url: str
    title: str
    snapshot_id: str
    fetched_at: str
    header_path: str          # parent headings, LlamaIndex style: "/A/B/"
    heading: str              # this section's own heading text ("" if none)
    kind: str                 # "section" | "row"
    text: str
    effective: Optional[str] = None   # ISO date from "Rates are effective as of MM/DD/YYYY"
    categories: tuple = ()            # from categories.categories_for, set at ingest
    published: Optional[str] = None   # ISO date the page says it was published (press release, dated URL)
    enrich: Optional[dict] = None     # enrich.py: search-only context line / propositions / questions (never sent to the model)
    enrich_text: str = ""              # the part of that which BM25 sees (set by enrich.apply per MY_SOLUTION_ENRICH)
    via: str = ""                      # which retriever/field surfaced this piece (provenance, set on extras)

    def index_text(self) -> str:
        """What BM25 sees: page title + heading path + body."""
        return f"{self.title} {self.header_path.replace('/', ' ')} {self.heading}\n{self.text}" + (f"\n{self.enrich_text}" if self.enrich_text else "")


# ---------------------------------------------------------------- step 1: LlamaIndex-equivalent
def split_sections(text: str, sep: str = "/") -> list[tuple[str, str]]:
    """Return [(header_path, section_text)] exactly as MarkdownNodeParser would."""
    out: list[tuple[str, str]] = []
    current = ""
    stack: list[tuple[int, str]] = []
    code_block = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            code_block = not code_block
            current += line + "\n"
            continue
        if not code_block:
            m = HEADER_RE.match(line)
            if m:
                if current.strip():
                    out.append((_path(stack[:-1], sep), current.strip()))
                level, htext = len(m.group(1)), m.group(2)
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, htext))
                current = "#" * level + f" {htext}\n"
                continue
        current += line + "\n"
    if current.strip():
        out.append((_path(stack[:-1], sep), current.strip()))
    return out


def _path(stack, sep):
    inner = sep.join(h[1] for h in stack)
    return sep + inner + sep if inner else sep


# ---------------------------------------------------------------- step 2: our post-processing
def is_form(text: str) -> bool:
    """A section with two or more required-field labels is a web form."""
    return sum(1 for l in text.split("\n") if FORM_LINE_RE.search(l.strip())) >= 2


def clean_text(text: str, form: bool = False) -> str:
    """Drop page furniture. In a form section also drop its short option lines ("Email", "Phone",
    "- Contractor"), keeping real sentences and tables."""
    lines = []
    for line in text.split("\n"):
        line = IMAGE_RE.sub("", line)
        line = LINK_RE.sub(lambda m: f"{m.group(1)} ({m.group(2)})" if m.group(1).strip() else m.group(2), line)
        s = line.strip()
        if s in NOISE_LINES or NOISE_LINE_RE.match(s) or FORM_LINE_RE.search(s):
            continue
        if s.startswith("- ") and s[2:].strip().lower() in US_STATES:   # state pick-list item
            continue
        if form and s and not s.startswith("|") and len(s.lstrip("-* ").split()) <= 3:
            continue
        lines.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _split_heading(section: str) -> tuple[str, str]:
    first, _, rest = section.partition("\n")
    m = HEADER_RE.match(first)
    return (m.group(2).strip(), rest.strip()) if m else ("", section.strip())


def _effective(text: str) -> Optional[str]:
    m = EFFECTIVE_RE.search(text)
    if not m:
        return None
    mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y = y + 2000 if y < 100 else y
    return f"{y:04d}-{mo:02d}-{d:02d}" if 1 <= mo <= 12 and 1 <= d <= 31 else None


def _blocks(body: str) -> list[str]:
    """Paragraph blocks; a run of table lines is always one block."""
    blocks, cur, in_table = [], [], False
    for line in body.split("\n"):
        is_row = line.lstrip().startswith("|")
        if is_row != in_table and cur:
            blocks.append("\n".join(cur)); cur = []
        in_table = is_row
        if not line.strip() and not in_table:
            if cur:
                blocks.append("\n".join(cur)); cur = []
            continue
        cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return [b for b in blocks if b.strip()]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _row_chunks(blocks: list[str], heading: str) -> list[tuple[str, Optional[str]]]:
    """One text per data row: 'caption | Header: cell | ... | effective note'."""
    out = []
    for i, b in enumerate(blocks):
        if not b.lstrip().startswith("|"):
            continue
        lines = [l for l in b.split("\n") if l.strip()]
        if len(lines) < 3:
            continue
        headers = _cells(lines[0])
        rows = [l for l in lines[1:] if not re.fullmatch(r"[\s|:\-]+", l)]
        caption = next((blocks[j] for j in range(i - 1, -1, -1) if not blocks[j].lstrip().startswith("|")), heading)
        caption = caption.split("\n")[-1].strip() if caption else heading
        after = " ".join(blocks[i + 1:i + 3])
        note = next((s.strip() for s in re.split(r"(?<=\.)\s", after) if EFFECTIVE_RE.search(s)), "")
        for r in rows:
            cells = _cells(r)
            pairs = [f"{h}: {c}" if h else c for h, c in zip(headers, cells)] + cells[len(headers):]
            text = " | ".join([p for p in [caption, *pairs, note] if p])
            out.append((text, _effective(note)))
    return out


MONTH_DATE_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|"
                           r"December)\s+(\d{1,2}),\s+(20\d\d)\b")
URL_DATE_RE = re.compile(r"/(20\d\d)/(\d\d)/(\d\d)/")
URL_YEAR_RE = re.compile(r"[-_/](20\d\d)[-_.]")
_MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                        "September", "October", "November", "December"], 1)}


def published_date(url: str, markdown: str) -> Optional[str]:
    """When the page says it was published: a dated URL (/2018/09/25/), the first "Month D, YYYY" near the top
    (press-release and blog bylines), or a year in a file name (Dupaco-2025-Impact-Report.pdf -> 2025-12-31)."""
    m = URL_DATE_RE.search(url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = MONTH_DATE_RE.search(markdown[:1500])
    if m:
        return f"{m.group(3)}-{_MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
    m = URL_YEAR_RE.search(url)
    if m:
        return f"{m.group(1)}-12-31"
    return None


def norm_block(block: str) -> str:
    return " ".join(block.lower().split())


def page_blocks(markdown: str) -> list[str]:
    """Cleaned paragraph blocks of a page, as chunk_page sees them (used to find site-wide boilerplate)."""
    out = []
    for _, section in split_sections(markdown):
        heading, body = _split_heading(section)
        if heading.strip().lower() in DROP_SECTIONS:
            continue
        out.extend(_blocks(clean_text(body, form=is_form(body))))
    return out


def chunk_page(url: str, title: str, markdown: str, snapshot_id: str, fetched_at: str,
               drop_blocks: frozenset = frozenset()) -> list[Chunk]:
    """drop_blocks: normalized paragraphs to leave out (site-wide boilerplate kept on another page)."""
    sections = split_sections(markdown)
    chunks: list[Chunk] = []
    carry = ""  # headings of heading-only sections, prepended to the next section
    for header_path, section in sections:
        heading, body = _split_heading(section)
        if heading.strip().lower() in DROP_SECTIONS:
            carry = ""
            continue
        body = clean_text(body, form=is_form(body))
        if not body:
            carry = f"{carry} {heading}".strip()
            continue
        if carry:
            heading = f"{carry} / {heading}" if heading else carry
            carry = ""
        blocks = [b for b in _blocks(body) if b.lstrip().startswith("|") or norm_block(b) not in drop_blocks]
        if not blocks:
            continue
        eff = _effective(body)
        # section chunks, split at paragraph boundaries if oversized
        cur: list[str] = []
        for b in blocks:
            if cur and sum(len(x) for x in cur) + len(b) > MAX_SECTION_CHARS:
                chunks.append(Chunk(url, title, snapshot_id, fetched_at, header_path, heading, "section", "\n\n".join(cur), eff))
                cur = []
            cur.append(b)
        if cur:
            chunks.append(Chunk(url, title, snapshot_id, fetched_at, header_path, heading, "section", "\n\n".join(cur), eff))
        for text, row_eff in _row_chunks(blocks, heading):
            chunks.append(Chunk(url, title, snapshot_id, fetched_at, header_path, heading, "row", text, row_eff or eff))
    pub = published_date(url, markdown)
    for c in chunks:
        c.published = pub
    return chunks
