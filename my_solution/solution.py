"""
my_solution, slice 1: BM25 retrieval over table-aware chunks + one gpt-6-luna call per question.

Without OPENAI_API_KEY, answer() falls back to returning the top-ranked chunk (retrieval only).
"""
from __future__ import annotations

import atexit
import json
import re
import os
import sys
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# The scorer's harness/ folder: normally a parent of this folder. When this folder is run from somewhere else, the scorer has
# already put its own harness/ on sys.path (run_eval.py), so `import contract` below still works without it.
_HARNESS = next((d / "harness" for d in HERE.parents if (d / "harness" / "contract.py").exists()), None)
if _HARNESS is not None:
    sys.path.insert(0, str(_HARNESS))
from contract import Answer, Conflict, Snapshot, Source  # noqa: E402

from categories import categories_for  # noqa: E402
from collections import defaultdict  # noqa: E402

from chunker import Chunk, chunk_page, norm_block, page_blocks, published_date  # noqa: E402
from facts import CONFLICT_METRICS, FactExtractor, group_facts, page_tables, resolve, winner  # noqa: E402
from dates import target_date  # noqa: E402
import dates as _dates  # noqa: E402
from count_facts import answer_text, count_facts, count_question, latest  # noqa: E402
from llm import AnswerLLM  # noqa: E402
from prompt import PAGE_TYPE_LABEL, build_user_message, developer_message_for, history_developer_message  # noqa: E402
from decisions_understanding import DecisionsUnderstanding  # noqa: E402
from query_understanding import ANSWER_TERMS, AnswerTerms, QueryUnderstanding, qualifier_patterns, search_text  # noqa: E402
from synonyms import expansion  # noqa: E402
from search import BM25Index  # noqa: E402
import enrich  # noqa: E402
ENRICH_FLAGS = enrich.FLAGS   # MY_SOLUTION_ENRICH, see enrich.py (empty = off)
from spellfix import SpellFix  # noqa: E402
from tiers import SECONDARY, page_rank  # noqa: E402

TOP_K = int(os.getenv("MY_SOLUTION_TOP_K", "8"))   # keyword pieces kept; experiment switch, default 8
# Some facts exist only on tier-2 pages (e.g. branch hours appear only in newsroom releases). The tier
# boost should break ties between pages stating the same fact, not hide facts no tier-1 page states,
# so the best tier-2 chunks always get a few of the top-k slots; the prompt's trust order decides.
SECONDARY_SLOTS = 2
# Fact prototype: rate tables become facts at loading time; rate/fee questions are answered from facts,
# with text RAG as the fallback. FACT_K = how many fact lines the answer AI sees.
USE_FACTS = True
FACT_K = 12
# A paragraph found on this many pages or more is site-wide boilerplate (form disclaimers, "About Dupaco"
# footers): it is kept once, on its most trusted page, and removed from the others.
BOILERPLATE_MIN_PAGES = 10**9   # off: removing repeated paragraphs also removed real facts (Hy-Vee closure, join link)
_RANK_ORDER = {"rate_sheet": 0, "product": 1, "promo": 2, "secondary": 3}
# Query understanding (gpt-6-luna turns the question into search parameters). Values are the defaults
# until slice measurements choose them.
# "synonyms" = hand-written synonym list, no LLM call at question time (the default: ~2 s faster).
# "none" | "keywords" | "categories" | "both" use the LLM query-understanding call instead.
QU_MODE = "both"
# Query-understanding engine: "decisions" (default: Decisions API labels + synonym list, no Responses call) or "luna" (the old Responses call that writes JSON; MY_SOLUTION_QU_ENGINE=luna rolls back).
QU_ENGINE = os.getenv("MY_SOLUTION_QU_ENGINE", "decisions")
SYNONYM_WEIGHT = 0.5
CAT_BOOST = 10.0
QUAL_BOOST = 0.0
VALUE_INTENTS = ("rate", "fee")
VALUE_QUESTION_RE = re.compile(r"\b(rates?|apr|apy|dividend|interest|fees?|costs?|charges?|price)\b", re.I)
# Spelling help (spellfix.py, default on since 2026-11-17; MY_SOLUTION_SPELLFIX=0 rolls back):
# question words the site does not use are matched to a site word one edit away and ADDED to the search text and the synonym lookup.
SPELLFIX = os.getenv("MY_SOLUTION_SPELLFIX", "1") != "0"
# Search cleanup (experiment switch, default off until the 40-question regression says otherwise):
# drop "Keep reading" teaser cards (previews of other articles) and merge the near-identical branch-finder
# address cards from /contact into one piece, so they cannot fill the 8 slots.
SEARCH_CLEANUP = os.getenv("MY_SOLUTION_SEARCH_CLEANUP", "0") == "1"
# Second search pass (experiment switch, default off): the first-pass top 8 stay unchanged; up to 4 unique pieces from a search with
# the answer-type terms alone (A) and up to 4 from a search with the question + those terms (B) are appended (max 16).
SECOND_PASS = os.getenv("MY_SOLUTION_SECOND_PASS", "0") == "1"
SECOND_PASS_EACH = 4
# Hybrid search (experiment switch MY_SOLUTION_HYBRID=1, default off): keyword (BM25) and meaning (embedding) rankings of the pieces are merged
# with reciprocal-rank fusion before the top 8 are chosen. Vectors come from my_solution/.embed_cache (missing ones are embedded at ingest).
# MY_SOLUTION_HYBRID=1 or fuse: merge the two rankings (can push keyword hits out); =append: keep the keyword top 8 exactly as they are and add up to
# 3 embedding-only pieces after them (keyword hits cannot be lost).
_HYB = os.getenv("MY_SOLUTION_HYBRID", "windows")   # default ON after the slice and 40-question tests; MY_SOLUTION_HYBRID=0 turns embeddings off
HYBRID = _HYB in ("1", "fuse", "append", "windows")
HYBRID_APPEND = _HYB == "append"
# MY_SOLUTION_HYBRID=windows: keyword top 8 kept; then the best overlapping 600-character windows (meaning search) are added, as many as the question's
# intent calls for: more for meaning-heavy intents, none for rate/fee (exact numbers and names are keyword and fact-table territory).
HYBRID_WINDOWS = _HYB == "windows"
WINDOW_WARMUP = os.getenv("MY_SOLUTION_WINDOW_WARMUP", "1") == "1"   # build each copy's window index while loading; =0 builds it at the first question that needs it
EMBED_MISSING = os.getenv("MY_SOLUTION_EMBED_MISSING", "1") == "1"   # at ingest, embed windows that have no stored vector (needs the key); =0 skips them
HYBRID_EXTRA = 3
WINDOW_EXTRA_BY_INTENT = {"eligibility": 6, "list": 6, "fact_about_dupaco": 6, "rate": 0, "fee": 0}
WINDOW_EXTRA_DEFAULT = 3
# "Are the hours the same at every branch?" (experiment switch MY_SOLUTION_HOURS_SCHEDULES, default on; set 0 to turn off). The keyword top 8 fill up with branch-finder
# cards and the pages that state a second schedule rank around 30th, so the answer AI sees one schedule only. For an hours question that asks about
# sameness or difference, up to HOURS_SCHEDULE_EXTRA more pieces that carry a lobby/drive-up schedule are appended (nothing else changes).
HOURS_SCHEDULES = os.getenv("MY_SOLUTION_HOURS_SCHEDULES", "1") == "1"
HOURS_SCHEDULE_EXTRA = 5
SAMENESS_RE = re.compile(r"\b(same|differ\w*|vary|varies|varying|uniform|consistent|identical)\b", re.I)
_SCHED_TIME_RE = re.compile(r"\d{1,2}(?::\d\d)?\s*(?:a\.?m\.?|p\.?m\.?)", re.I)
_SCHED_DAY_RE = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)", re.I)
# Reasoning effort for hours questions only (experiment switch MY_SOLUTION_HOURS_EFFORT = none | low | medium; default none = unchanged).
HOURS_EFFORT = os.getenv("MY_SOLUTION_HOURS_EFFORT") or None


def _is_teaser(c) -> bool:
    return "Keep reading (" in c.text and len(c.text) < 600


def _is_locator_card(c) -> bool:
    return c.url.rstrip("/").endswith("/contact") and c.text.lstrip().startswith(("Dupaco Branch", "Surcharge-Free ATM"))


def _clean_hits(hits):
    out, cards, first = [], [], None
    for score, c in hits:
        if _is_teaser(c):
            continue
        if _is_locator_card(c):
            if first is None:
                first = (score, len(out))
            cards.append(c)
            continue
        out.append((score, c))
    if cards:
        c0 = cards[0]
        merged = Chunk(c0.url, c0.title, c0.snapshot_id, c0.fetched_at, "/", "Branch and ATM locator", "section",
                       "Branch and ATM locations (addresses and services only, no hours):\n"
                       + "\n".join(" ".join(c.text.split()) for c in cards[:12]),
                       categories=c0.categories)
        out.insert(first[1], (first[0], merged))
    return out


def _expansion_for(question: str, qu: Optional[dict], qu_mode: str):
    """Synonym tokens added to the chunk search: always in synonyms mode, and for the decisions engine (which has no LLM keywords)."""
    if qu_mode == "synonyms":
        return expansion(question)
    return (qu or {}).get("synonym_tokens", ())


REFUSAL = "I don't know. That isn't listed on Dupaco's website, so please contact Dupaco directly."
# A failed model call (timeout, API down, bad reply) must not look like an honest "I don't know". Its text says what happened, and
# conflict_note names the error so the evaluation output shows it. answer() returns it with confident=True: the scorer counts
# confident=False as a refusal, which would credit a should-refuse question with a refusal the system never made.
FAILED_PREFIX = "LLM call failed: "
TIMEOUT_TEXT = ("The language model did not respond in time, so no answer was produced. This was a system timeout and says nothing "
                "about what the website lists. Please try again.")
ERROR_TEXT = ("The language model call failed, so no answer was produced. This was a system error and says nothing "
              "about what the website lists. Please try again.")
# A question about a date earlier than our oldest website copy: say so instead of answering from the oldest copy. No digits in the text
# (the scorer treats numbers outside the question as an answer). MY_SOLUTION_REFUSE_BEFORE_FIRST=0 rolls back.
REFUSE_BEFORE_FIRST = os.getenv("MY_SOLUTION_REFUSE_BEFORE_FIRST", "1") == "1"
BEFORE_FIRST_REFUSAL = ("I don't know. Dupaco's website copies on file start after that date, so I can't say how the website looked then. "
                        "Please contact Dupaco directly.")


class Knowledge:
    def __init__(self, boost: str = "tiers", use_llm: bool = True, secondary_slots: int = SECONDARY_SLOTS,
                 qu_mode: str = QU_MODE, cat_boost: float = CAT_BOOST, qual_boost: float = QUAL_BOOST,
                 qu_cache_path=None, use_facts: bool = USE_FACTS, fact_cache_path=None):
        self.boost = boost
        self.secondary_slots = secondary_slots
        self.cat_boost, self.qual_boost = cat_boost, qual_boost
        self.snapshots: list[tuple[str, str, BM25Index]] = []   # (taken_on, snapshot_id, index), oldest first
        self._newest: Optional[Snapshot] = None
        self._sentence_cache: dict = {}   # rate sentence -> extracted rates (conflicts v2)
        self._counts: dict = {}           # website copy -> count facts (branches, employees, members, assets)
        self.llm = AnswerLLM()
        self.use_llm = use_llm and self.llm.available()
        self.qu_mode = qu_mode if (qu_mode == "synonyms" or self.llm.available()) else "none"
        self.qu = QueryUnderstanding(self.llm, qu_cache_path) if self.qu_mode not in ("none", "synonyms") else None
        self.qu_decisions = None   # MY_SOLUTION_QU_ENGINE=decisions: labels from the Decisions API instead of the gpt-6-luna call
        if self.qu and QU_ENGINE == "decisions":
            dc = os.getenv("MY_SOLUTION_QU_DEC_CACHE")
            self.qu_decisions = DecisionsUnderstanding(self.llm, Path(dc) if dc else None)
        self.aq = (AnswerTerms(self.llm, Path(os.environ["MY_SOLUTION_AQ_CACHE"]) if os.getenv("MY_SOLUTION_AQ_CACHE") else None)
                   if (ANSWER_TERMS or SECOND_PASS) and self.qu else None)
        self.dense: dict[str, object] = {}     # snapshot_id -> DenseIndex (hybrid switch only)
        self._enrich_idx: dict[str, object] = {}   # snapshot_id -> enrich.EnrichIndex (MY_SOLUTION_ENRICH has emb)
        self._windows: dict[str, object] = {}  # snapshot_id -> WindowIndex or None (windows mode; built lazily, only from vectors already in the file)
        self._embed_store = None
        self._cache: dict[tuple, Answer] = {}
        self.spell = SpellFix() if SPELLFIX else None   # the site's own vocabulary, learned while the snapshots load
        self.spellfix = SPELLFIX                         # an instance flag so a test run can switch it on and off
        self.use_facts = use_facts and self.llm.available()
        self.facts = FactExtractor(self.llm, fact_cache_path) if self.use_facts else None
        self.fact_index: dict[str, tuple[list, BM25Index]] = {}   # snapshot_id -> (facts, index)
        if os.getenv("MY_SOLUTION_USAGE"):   # measurement aid: print OpenAI token usage when the run ends
            atexit.register(lambda: print(f"[my_solution] OpenAI usage: {self.llm.usage}", file=sys.stderr))

    def _chunks_for(self, snapshot: Snapshot) -> list:
        """Chunks of one website copy (boilerplate paragraphs kept on one page only, categories set)."""
        pages_with: dict[str, set] = defaultdict(set)
        for p in snapshot.pages:
            for b in page_blocks(p.markdown):
                if len(b) >= 40 and not b.lstrip().startswith("|"):
                    pages_with[norm_block(b)].add(p.url)
        keep_on = {b: min(urls, key=lambda u: (_RANK_ORDER[page_rank(u)], len(u), u))
                   for b, urls in pages_with.items() if len(urls) >= BOILERPLATE_MIN_PAGES}
        drop_for: dict[str, set] = defaultdict(set)
        for b, keeper in keep_on.items():
            for u in pages_with[b]:
                if u != keeper:
                    drop_for[u].add(b)
        chunks = []
        for p in snapshot.pages:
            chunks.extend(chunk_page(p.url, p.title, p.markdown, snapshot.snapshot_id, p.fetched_at,
                                     frozenset(drop_for.get(p.url, ()))))
        for c in chunks:
            caption = c.text.split(" | ")[0] if c.kind == "row" else ""
            c.categories = tuple(categories_for(c.url, f"{c.header_path} {c.heading} {caption}", c.text))
        return chunks

    def ingest(self, snapshot: Snapshot) -> None:
        if self.spell:
            for p in snapshot.pages:
                self.spell.add_text(p.markdown)
        chunks = self._chunks_for(snapshot)
        if ENRICH_FLAGS:   # search-only fields from the committed cache (enrich.py); the text sent to the model is unchanged
            enrich.apply(chunks)
        bm_index = BM25Index(chunks)
        self.snapshots.append((snapshot.taken_on, snapshot.snapshot_id, bm_index))
        _dates.REFERENCE = max(s[0] for s in self.snapshots)   # newest copy: a month named without a year is read relative to it
        if HYBRID and not HYBRID_WINDOWS and self.llm.available():
            from embed_index import DenseIndex, EmbeddingStore
            self._embed_store = self._embed_store or EmbeddingStore()
            self.dense[snapshot.snapshot_id] = DenseIndex(bm_index.chunks, self._embed_store)
        if HYBRID_WINDOWS and WINDOW_WARMUP:
            self._build_window_index(snapshot.snapshot_id, bm_index, embed_missing=True)
        if "emb" in ENRICH_FLAGS:
            try:
                self._enrich_idx[snapshot.snapshot_id] = enrich.EnrichIndex(bm_index.chunks, embed_missing=EMBED_MISSING and self.llm.available())
            except Exception as e:
                print(f"[my_solution] enrichment index unavailable: {type(e).__name__}: {e}", file=sys.stderr)
        if self.facts:
            tables = [(t, published_date(p.url, p.markdown)) for p in snapshot.pages
                      for t in page_tables(p.url, p.title, p.markdown)]
            self.facts.extract([t for t, _ in tables])
            facts = [f for t, pub in tables for f in self.facts.facts_for(t, snapshot.snapshot_id, pub)]
            self.fact_index[snapshot.snapshot_id] = (facts, BM25Index(facts))
        self.snapshots.sort(key=lambda s: s[0])
        if COUNT_ANSWERS:
            self._counts[snapshot.snapshot_id] = count_facts(snapshot.pages)
        if self._newest is None or snapshot.taken_on >= self._newest.taken_on:
            self._newest = snapshot          # conflicts() v2 reads the newest website copy's pages
        if self.use_llm or self.qu:
            self.llm.warm_up()
        if self.qu_decisions:
            self.qu_decisions.warm_up()

    def understand(self, question: str) -> Optional[dict]:
        qu = (self.qu_decisions or self.qu).parse(question) if self.qu else None
        if qu is not None and self.aq:
            qu = {**qu, **self.aq.parse(question)}   # copy: the cached query-understanding entry stays unchanged
        extra = self._spell_extra(question)
        if qu is not None and extra:   # synonyms of the corrected words too ("savngs" -> savings -> its synonym group)
            qu = {**qu, "synonym_tokens": list(dict.fromkeys(list(qu.get("synonym_tokens") or []) + list(expansion(extra))))}
        return qu

    def _spell_extra(self, question: str) -> str:
        """Corrected words to add to the search text, with a leading space; '' when spelling help is off or nothing needed fixing."""
        if not (self.spellfix and self.spell):
            return ""
        words = self.spell.extra_words(question)
        return (" " + " ".join(words)) if words else ""

    def _snapshot_for(self, question: str, as_of: Optional[str], qu: Optional[dict] = None):
        """Latest snapshot taken on or before the target date; the newest one if no date applies.
        With query understanding, its website_date (which ignores event dates) replaces the regex."""
        date = self._asked_date(question, as_of, qu)
        eligible = [s for s in self.snapshots if date is None or s[0] <= date]
        return (eligible or self.snapshots[:1])[-1]

    @staticmethod
    def _asked_date(question: str, as_of: Optional[str], qu: Optional[dict]) -> Optional[str]:
        """The date the member asks about (YYYY-MM-DD) or None for "now": the harness's as_of, else query understanding's website_date, else a date in the text."""
        if as_of:
            return as_of[:10]
        if qu is not None:
            return qu.get("website_date")
        return target_date(question, None)

    def _before_first_snapshot(self, question: str, as_of: Optional[str], qu: Optional[dict]) -> bool:
        """True when the question asks about a date earlier than our oldest website copy (we would otherwise answer from the oldest copy as if it were that date)."""
        date = self._asked_date(question, as_of, qu)
        return bool(date and self.snapshots and date < min(s[0] for s in self.snapshots))

    def index_for(self, question: str, as_of: Optional[str] = None, qu: Optional[dict] = None) -> BM25Index:
        return self._snapshot_for(question, as_of, qu)[2]

    def retrieve(self, question: str, as_of: Optional[str] = None, k: int = TOP_K, qu: Optional[dict] = None):
        """Top-k (score, chunk, urls) with exact-duplicate text merged. The same table is published
        on several pages: the highest-ranked copy is kept and `urls` lists every page carrying it,
        so the answer can cite all of them (source credit is any-match, extra URLs cost nothing)."""
        if qu is None:
            qu = self.understand(question)
        use_kw = self.qu_mode in ("keywords", "both")
        use_cat = self.qu_mode in ("categories", "both")
        hits = self.index_for(question, as_of, qu).search(
            search_text(question, qu, use_kw) + self._spell_extra(question), k=k * (50 if (HYBRID and not HYBRID_APPEND) else (30 if SEARCH_CLEANUP else 10)), boost=self.boost,
            categories=(qu or {}).get("categories", ()) if use_cat else (), cat_boost=self.cat_boost,
            qualifiers=qualifier_patterns(qu), qual_boost=self.qual_boost,
            expansion_tokens=_expansion_for(question, qu, self.qu_mode),
            expansion_weight=SYNONYM_WEIGHT)
        if SEARCH_CLEANUP:
            hits = _clean_hits(hits)
        if HYBRID and not HYBRID_APPEND:
            hits = self._hybrid(question, as_of, qu, hits)
        by_key: dict[str, list] = {}
        unique = []
        for score, c in hits:
            key = " ".join(c.text.split()).lower()
            if key in by_key:
                if c.url not in by_key[key]:
                    by_key[key].append(c.url)
                continue
            by_key[key] = [c.url]
            unique.append((score, c, by_key[key]))
        out = unique[:k]
        reserve = min(self.secondary_slots, k)
        have = sum(1 for _, c, _ in out if page_rank(c.url) == SECONDARY)
        if have < reserve:
            extra = [h for h in unique[k:] if page_rank(h[1].url) == SECONDARY][:reserve - have]
            out = out[:k - len(extra)] + extra
        if HYBRID_APPEND and k == TOP_K:
            out = out + self._dense_extra(question, out, as_of, qu)
        if HYBRID_WINDOWS and k == TOP_K:
            out = out + self._window_extras(question, out, as_of, qu)
        if "emb" in ENRICH_FLAGS and k == TOP_K:
            out = out + self._enrich_extras(question, out, as_of, qu)
        if SECOND_PASS and k == TOP_K and (qu or {}).get("answer_terms"):
            out = out + self._second_pass(question, out, as_of, qu)
        if HOURS_SCHEDULES and k == TOP_K and (qu or {}).get("intent") == "hours" and SAMENESS_RE.search(question):
            out = out + self._schedule_extras(question, out, as_of, qu)
        return out

    def _schedule_extras(self, question: str, first, as_of, qu):
        """Up to HOURS_SCHEDULE_EXTRA best-ranked pieces (not already in `first`) whose text states a lobby or drive-up schedule:
        the word lobby/drive plus at least two clock times and a weekday. Branch-finder pages are skipped (addresses only)."""
        seen = {" ".join(c.text.split()).lower() for _, c, _ in first}
        seen_sched: set = set()
        out = []
        for score, c in self.index_for(question, as_of, qu).search(search_text(question, qu, True), k=3000, boost=self.boost):
            t = c.text
            if c.url.rstrip("/").endswith("/contact"):
                continue
            # the times must follow the word right away ("Lobby Monday-Friday: 9 a.m.-5 p.m."), not sit elsewhere in an article that mentions the lobby
            windows = [t[m.end():m.end() + 160] for m in re.finditer(r"\b(lobby|drive-?\s?(?:up|through|thru))", t, re.I)]
            windows = [w for w in windows if len(_SCHED_TIME_RE.findall(w)) >= 2 and _SCHED_DAY_RE.search(w)]
            if not windows:
                continue
            # one piece per distinct schedule: the same hours repeated across articles would use up the slots
            sched = re.sub(r"[^a-z0-9]", "", windows[0].lower())[:70]
            key = " ".join(t.split()).lower()
            if key in seen or sched in seen_sched:
                continue
            seen.add(key)
            seen_sched.add(sched)
            out.append((score, c, [c.url]))
            if len(out) == HOURS_SCHEDULE_EXTRA:
                break
        return out

    def _hybrid(self, question: str, as_of, qu, hits):
        """Merge the keyword ranking `hits` with the meaning ranking (reciprocal-rank fusion); returns (score, chunk) in fused order."""
        sid = self._snapshot_for(question, as_of, qu)[1]
        dense = self.dense.get(sid)
        if dense is None:
            return hits
        from embed_index import fuse
        pos = {id(c): i for i, c in enumerate(dense.chunks)}
        bm_ids = [pos[id(c)] for _, c in hits if id(c) in pos]
        try:
            dn_ids = [i for _, i in dense.search(question, k=100)]
        except Exception as e:   # embedding call failed: keep keyword results
            print(f"[my_solution] embedding search failed: {type(e).__name__}: {e}", file=sys.stderr)
            return hits
        fused = fuse([bm_ids, dn_ids])
        return [(1.0 / (60 + r), dense.chunks[i]) for r, i in enumerate(fused, 1)]

    def _dense_extra(self, question: str, first, as_of, qu):
        """Up to HYBRID_EXTRA top embedding pieces that are not already among the keyword pieces (exact duplicate text removed)."""
        dense = self.dense.get(self._snapshot_for(question, as_of, qu)[1])
        if dense is None:
            return []
        try:
            ranked = dense.search(question, k=30)
        except Exception as e:
            print(f"[my_solution] embedding search failed: {type(e).__name__}: {e}", file=sys.stderr)
            return []
        seen = {" ".join(c.text.split()).lower() for _, c, _ in first}
        out = []
        for sim, i in ranked:
            c = dense.chunks[i]
            key = " ".join(c.text.split()).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append((sim, c, [c.url]))
            if len(out) == HYBRID_EXTRA:
                break
        return out

    def _build_window_index(self, sid: str, index, embed_missing: bool = False) -> None:
        """Window index of one website copy (reads the vector file, cuts the windows, stacks the matrix; about 2.5 s the first time).
        Called while loading (MY_SOLUTION_WINDOW_WARMUP, default on) so the first meaning search in a timed answer does not pay for it.
        embed_missing=True (only from ingest, which is untimed; MY_SOLUTION_EMBED_MISSING=0 turns it off): windows with no vector in the
        file (the site changed, or the file is incomplete) are embedded now and saved, so the file repairs itself."""
        from embed_index import EmbeddingStore, WindowIndex, WINDOW_CACHE, text_key
        store = EmbeddingStore(path=WINDOW_CACHE)
        try:   # only use windows whose vectors are already in the file: never embed a whole copy while answering
            wi = WindowIndex.__new__(WindowIndex)
            wi.chunks, wi.store = index.chunks, store
            seen, wi.windows = set(), []
            from embed_index import WINDOW_CHARS, WINDOW_STRIDE
            for ci, c in enumerate(index.chunks):
                t = c.text
                for st in range(0, max(len(t) - (WINDOW_CHARS - WINDOW_STRIDE), 1), WINDOW_STRIDE):
                    w = t[st:st + WINDOW_CHARS].strip()
                    kk = text_key(w)
                    if len(w) >= 40 and kk not in seen:
                        seen.add(kk); wi.windows.append((w, ci))
            import numpy as np
            missing = [w for w, _ in wi.windows if text_key(w) not in store.vecs]
            if missing and embed_missing and EMBED_MISSING and self.llm.available():
                print(f"[my_solution] {sid}: {len(missing)} of {len(wi.windows)} windows have no vector (site changed or vector file "
                      f"incomplete); embedding them now", file=sys.stderr)
                try:
                    store.ensure(missing)   # sets the vectors in memory, then saves the file; a failed save (read-only folder) keeps them
                except Exception as e:
                    print(f"[my_solution] embedding the missing windows failed: {type(e).__name__}: {e}", file=sys.stderr)
                missing = [w for w, _ in wi.windows if text_key(w) not in store.vecs]
            if not missing:
                wi.matrix = np.stack([store.vecs[text_key(w)] for w, _ in wi.windows]).astype(np.float32)
                self._windows[sid] = wi
            else:
                print(f"[my_solution] {sid}: {len(missing)} windows have no vector, so meaning search is off for this copy "
                      f"(keyword search only)", file=sys.stderr)
                self._windows[sid] = None
        except Exception as e:
            print(f"[my_solution] window index unavailable: {type(e).__name__}: {e}", file=sys.stderr)
            self._windows[sid] = None

    def _window_extras(self, question: str, first, as_of, qu):
        """Best overlapping windows by meaning that are not already in `first`; each is returned as a small piece carrying its parent's page, title and dates."""
        import dataclasses
        sid, index = self._snapshot_for(question, as_of, qu)[1], self.index_for(question, as_of, qu)
        if sid not in self._windows:
            self._build_window_index(sid, index)
        wi = self._windows[sid]
        intent = (qu or {}).get("intent")
        n = WINDOW_EXTRA_BY_INTENT.get(intent, WINDOW_EXTRA_DEFAULT)
        if wi is None or n == 0:
            return []
        try:
            ranked = wi.search(question, k=40)
        except Exception as e:
            print(f"[my_solution] embedding search failed: {type(e).__name__}: {e}", file=sys.stderr)
            return []
        seen_txt = {" ".join(c.text.split()).lower() for _, c, _ in first}
        out = []
        for sim, ci, w in ranked:
            key = " ".join(w.split()).lower()
            if key in seen_txt or any(key in t for t in seen_txt):   # already inside a keyword piece
                continue
            seen_txt.add(key)
            parent = wi.chunks[ci]
            out.append((sim, dataclasses.replace(parent, text=w), [parent.url]))
            if len(out) == n:
                break
        return out

    def _enrich_extras(self, question: str, first, as_of, qu):
        """Up to enrich.EXTRA_N parent chunks found by meaning search over the propositions/questions (union: nothing is removed).
        The parent's ORIGINAL text is returned; `via` records which field found it (MY_SOLUTION_PROV=<file> logs it)."""
        import dataclasses
        ix = self._enrich_idx.get(self._snapshot_for(question, as_of, qu)[1])
        if ix is None:
            return []
        try:
            ranked = ix.search(question, k=30)
        except Exception as e:
            print(f"[my_solution] enrichment search failed: {type(e).__name__}: {e}", file=sys.stderr)
            return []
        seen = {" ".join(c.text.split()).lower() for _, c, _ in first}
        out = []
        for sim, ci, field in ranked:
            c = ix.chunks[ci]
            key = " ".join(c.text.split()).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append((sim, dataclasses.replace(c, via=f"enrich:{field}"), [c.url]))
            if len(out) == enrich.EXTRA_N:
                break
        if os.getenv("MY_SOLUTION_PROV"):
            with open(os.environ["MY_SOLUTION_PROV"], "a") as f:
                f.write(json.dumps({"q": question, "added": [[c.via, c.url, round(s, 3)] for s, c, _ in out]}) + "\n")
        return out

    def _second_pass(self, question: str, first, as_of, qu: dict):
        """Pieces from two extra searches, appended after the unchanged first-pass pieces. Exact duplicate text is dropped."""
        terms = " ".join(qu["answer_terms"])
        seen = {" ".join(c.text.split()).lower() for _, c, _ in first}
        ix = self.index_for(question, as_of, qu)
        added = []
        for query in (terms, question + " " + terms):
            hits = ix.search(query, k=400, boost=self.boost, categories=qu.get("categories", ()), cat_boost=self.cat_boost,
                             qualifiers=qualifier_patterns(qu), qual_boost=self.qual_boost)
            n = 0
            for score, c in hits:
                key = " ".join(c.text.split()).lower()
                if key in seen:
                    continue
                seen.add(key)
                added.append((score, c, [c.url]))
                n += 1
                if n == SECOND_PASS_EACH:
                    break
        return added

    def answer(self, question: str, as_of: Optional[str] = None) -> Answer:
        ans = self._answer(question, as_of)
        if (ans.conflict_note or "").startswith(FAILED_PREFIX):
            return Answer(text=ans.text, sources=[], confident=True, conflict_note=ans.conflict_note)
        return ans

    def _answer(self, question: str, as_of: Optional[str] = None) -> Answer:
        if EMBED_PREFETCH and HYBRID and self.llm.available():
            from embed_index import prefetch_query
            prefetch_query(question)   # embedding runs while the query-understanding call is in flight
        qu = self.understand(question)
        if HISTORY and self.use_llm and (qu or {}).get("time_scope") == "change":
            hkey = (" ".join(question.lower().split()), "history", as_of)
            if hkey in self._cache:
                return self._cache[hkey]
            ans = self._history_answer(question, as_of, qu)
            if ans is not None:   # None: fewer than two copies, nothing found, or not confident -> the ordinary path below
                self._cache[hkey] = ans
                return ans
        if REFUSE_BEFORE_FIRST and self._before_first_snapshot(question, as_of, qu):
            return Answer(text=BEFORE_FIRST_REFUSAL, confident=False)
        taken_on, snapshot_id, _ = self._snapshot_for(question, as_of, qu)
        key = (" ".join(question.lower().split()), snapshot_id, as_of)   # as_of shapes the "Question date" note, so it is part of the key
        if key in self._cache:
            return self._cache[key]
        measure = count_question(question, (qu or {}).get("website_date") or as_of) if COUNT_ANSWERS else None
        if measure:
            # Counts about Dupaco as a whole sit in "about Dupaco" boilerplate that every release repeats with its own day's
            # number: answer from the most recently published statement in this website copy (count_facts.py).
            fs = [f for f in self._counts.get(snapshot_id, []) if f.measure == measure]
            if fs:
                w = latest(fs)
                ans = Answer(text=answer_text(w), sources=[Source(url=w.url, snapshot_id=snapshot_id)], confident=True)
                self._cache[key] = ans
                return ans
        if self.facts and self.use_llm and self._asks_value(question, qu):
            fact_hits = self.fact_hits(question, snapshot_id, qu)
            if fact_hits:
                ans = self._llm_answer(question, fact_hits, taken_on, qu, self._asked_note(question, as_of, qu))
                if ans.confident:   # otherwise fall back to text RAG
                    self._cache[key] = ans
                    return ans
        hits = self.retrieve(question, as_of, qu=qu)
        if not hits:
            return Answer(text=REFUSAL, confident=False)
        ans = self._llm_answer(question, hits, taken_on, qu, self._asked_note(question, as_of, qu)) if self.use_llm else self._top_chunk(hits)
        if not (ans.conflict_note or "").startswith(FAILED_PREFIX):   # a failure is not remembered: asking again retries the call
            self._cache[key] = ans
        return ans

    def _history_hits(self, question: str, as_of: Optional[str], qu: dict):
        """Evidence for a "what changed" question: the same search run in every website copy (up to `as_of`), merged so that a piece
        of identical text is listed once with the dates of the copies it was seen in. Returns (hit, urls, copy dates) lists.
        Rate and fee questions use each copy's winning facts (stale pages are already resolved inside a copy); others use text pieces."""
        snaps = [s for s in self.snapshots if not as_of or s[0] <= as_of[:10]]
        if len(snaps) < 2:
            return []
        merged: dict[str, list] = {}
        def add(score, c, urls, taken_on):
            key = re.sub(r"\bmonths\b", "month", " ".join(c.text.split()).lower())
            e = merged.setdefault(key, [score, c, [], []])
            e[0] = max(e[0], score)
            e[1] = c                                   # keep the newest occurrence (its page and dates)
            e[2] += [u for u in urls if u not in e[2]]
            e[3].append(taken_on)
        if self.facts and self._asks_value(question, qu):
            for taken_on, sid, _ in snaps:
                found = self.fact_hits(question, sid, qu, k=HISTORY_FACTS_PER_COPY * 4)
                # A copy's history is read from the most trusted page type that answered in that copy (normally the rate sheet):
                # a stale table left on another page is that copy contradicting itself, not a change over time.
                best = min((_RANK_ORDER[f.page_type] for _, f, _ in found), default=None)
                kept = [h for h in found if _RANK_ORDER[h[1].page_type] == best]
                # Two tables of that page type can still disagree inside one copy (a page carried over from an earlier crawl):
                # for each product and rate type keep the rows of the table with the latest "effective" date.
                # (An older-dated row that shows the same value as the newest table is the same fact and stays.)
                newest: dict[tuple, str] = {}
                for _, f, _ in kept:
                    k = (f.product.lower(), f.metric)
                    newest[k] = max(newest.get(k, ""), f.effective or "")
                current: dict[tuple, set] = defaultdict(set)
                for _, f, _ in kept:
                    k = (f.product.lower(), f.metric)
                    if (f.effective or "") == newest[k]:
                        current[k].add(f.value)
                kept = [h for h in kept if h[1].value in current[(h[1].product.lower(), h[1].metric)]]
                for score, f, urls in kept[:HISTORY_FACTS_PER_COPY]:
                    add(score, f, urls, taken_on)
            limit = HISTORY_FACT_LINES
        extras: dict[str, list] = {}   # embedding-window pieces of each copy (HISTORY_WINDOWS): kept after the keyword pieces, never cut by the limit
        if not merged:
            for taken_on, sid, _ in snaps:
                qu_now = {**qu, "website_date": None}
                found = self.retrieve(question, as_of=taken_on, k=HISTORY_PIECES_PER_COPY, qu=qu_now)
                for score, c, urls in found:
                    add(score, c, urls, taken_on)
                if HISTORY_WINDOWS and HYBRID_WINDOWS:
                    for score, c, urls in self._window_extras(question, found, taken_on, qu_now):
                        key = re.sub(r"\bmonths\b", "month", " ".join(c.text.split()).lower())
                        e = extras.setdefault(key, [score, c, [], []])
                        e[0] = max(e[0], score)
                        e[1] = c
                        e[2] += [u for u in urls if u not in e[2]]
                        e[3].append(taken_on)
            limit = HISTORY_PIECES
        top = sorted(merged.values(), key=lambda e: -e[0])[:limit]
        if extras:
            have = {re.sub(r"\bmonths\b", "month", " ".join(e[1].text.split()).lower()) for e in top}
            top += [e for k, e in sorted(extras.items(), key=lambda kv: -kv[1][0]) if k not in have][:HISTORY_WINDOW_PIECES]
        if top and hasattr(top[0][1], "product"):
            # facts: the same product's lines next to each other, oldest copy first, so a change reads top to bottom
            top.sort(key=lambda e: (e[1].product.lower(), e[1].metric, e[3][0]))
        return top

    def _history_answer(self, question: str, as_of: Optional[str], qu: dict) -> Optional[Answer]:
        hits = self._history_hits(question, as_of, qu)
        if not hits:
            return None
        excerpts = [{"n": i, "page_type": PAGE_TYPE_LABEL[page_rank(c.url)], "url": c.url, "effective": c.effective,
                     "published": c.published, "copies": ", ".join(copies), "text": c.text}
                    for i, (_, c, _, copies) in enumerate(hits, 1)]
        try:
            out = self.llm.ask(build_user_message(question, excerpts, None), instructions=history_developer_message())
        except Exception as e:
            print(f"[my_solution] LLM call failed (history): {type(e).__name__}: {e}", file=sys.stderr)
            return None
        text = (out.get("answer") or "").strip()
        if out.get("answer_type") == "none" or not out.get("confident") or not text:
            return None
        if self._asks_value(question, qu) and not VALUE_NUM_RE.search(text):
            return None
        used = [n for n in out.get("used_excerpts", []) if 1 <= n <= len(hits)] or [1]
        sources, seen = [], set()
        for n in used:
            _, c, urls, _ = hits[n - 1]
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    sources.append(Source(url=u, snapshot_id=c.snapshot_id))
        return Answer(text=text, sources=sources, confident=True, conflict_note=out.get("conflict_note"))

    @staticmethod
    def _asks_value(question: str, qu: Optional[dict]) -> bool:
        return (qu.get("intent") in VALUE_INTENTS) if qu else bool(VALUE_QUESTION_RE.search(question))

    def fact_hits(self, question: str, snapshot_id: str, qu: Optional[dict] = None, k: int = FACT_K):
        """Top-k facts of one website copy as (score, fact, urls). For each fact only the winning value is kept
        (most trusted page, then latest date), so stale values never reach the answer AI."""
        if snapshot_id not in self.fact_index:
            return []
        _, ix = self.fact_index[snapshot_id]
        use_kw = self.qu_mode in ("keywords", "both")
        use_cat = self.qu_mode in ("categories", "both")
        found = ix.search(search_text(question, qu, use_kw) + self._spell_extra(question), k=k * 6, boost=self.boost,
                          categories=(qu or {}).get("categories", ()) if use_cat else (), cat_boost=self.cat_boost,
                          expansion_tokens=(qu or {}).get("synonym_tokens", ()), expansion_weight=SYNONYM_WEIGHT)
        if not found:
            return []
        score_of = {id(f): s for s, f in found}
        out = []
        for occ in group_facts([f for _, f in found]):
            w = winner(occ)
            urls = list(dict.fromkeys(f.url for f in occ if f.value == w.value))
            out.append((max(score_of[id(f)] for f in occ), w, urls))
        out.sort(key=lambda h: -h[0])
        if METRIC_FIRST:
            # Answer the rate type the member asked for first: "what rate" -> rate rows before APR rows ("APR" -> APR, "APY" -> APY).
            # Only re-orders; nothing is removed, and nothing changes when no fact of the asked type was found.
            asked = METRIC_FOR_ASKED.get(((qu or {}).get("rate_metric") or "").lower())
            if asked and any(h[1].metric in asked for h in out):
                out.sort(key=lambda h: (h[1].metric not in asked, -h[0]))
        return out[:k]

    @staticmethod
    def _top_chunk(hits) -> Answer:
        _, c, urls = hits[0]
        return Answer(text=c.text[:600], sources=[Source(url=u, snapshot_id=c.snapshot_id) for u in urls])

    def user_message(self, question: str, hits, taken_on: str, asked: Optional[str] = None) -> str:
        """The exact user message the answer AI receives (also used by trace.py)."""
        excerpts = [{"n": i, "page_type": PAGE_TYPE_LABEL[page_rank(c.url)], "url": c.url,
                     "effective": c.effective, "published": c.published, "text": c.text}
                    for i, (_, c, _) in enumerate(hits, 1)]
        dated = taken_on if taken_on != self.snapshots[-1][0] else None
        return build_user_message(question, excerpts, dated, asked)

    def _asked_note(self, question: str, as_of: Optional[str], qu: Optional[dict]) -> Optional[str]:
        """The `Question date:` text for the answer step when the question is about a date (MY_SOLUTION_STATE_DATE), else None."""
        from prompt import STATE_DATE
        if not STATE_DATE:
            return None
        # "since June 2026" / "between May and September" name the start of a comparison, not the date to answer for: no "As of" line there.
        if STATE_DATE_SKIP_CHANGE and (qu or {}).get("time_scope") == "change":
            return None
        date = self._asked_date(question, as_of, qu)
        if not date:
            return None
        assumed = not as_of and bool(_dates.yearless_month(question)) and not _dates.MONTH_YEAR_RE.search(question)
        text = _dates.describe(question, date, as_of=bool(as_of))
        # A period named loosely ("early August 2026", "June 2026") also carries the date it was read as, so the answer step can see that the
        # website copy (the latest one on or before that date) is the right one even though its own date is earlier.
        if DATE_NOTE_EXPLAIN and not re.search(r"\d{1,2}, \d{4}$", text):
            text += f" (read as {date})"
        return text + (" (the question gave no year; the year was assumed)" if assumed else "")

    def _llm_answer(self, question: str, hits, taken_on: str, qu: Optional[dict] = None, asked: Optional[str] = None) -> Answer:
        try:
            intent = (qu or {}).get("intent")
            out = self.llm.ask(self.user_message(question, hits, taken_on, asked),
                               instructions=developer_message_for(question, intent, bool(asked)),
                               effort=HOURS_EFFORT if intent == "hours" else None)
        except Exception as e:  # API down, timeout, bad JSON: decline rather than crash
            print(f"[my_solution] LLM call failed: {type(e).__name__}: {e}", file=sys.stderr)
            # confident=False here lets the facts path fall back to text search; answer() turns a final failure into a visible one
            return Answer(text=TIMEOUT_TEXT if "timeout" in type(e).__name__.lower() else ERROR_TEXT, confident=False,
                          conflict_note=f"{FAILED_PREFIX}{type(e).__name__}")
        # Prompt O1 labels each answer complete / partial / none: complete and partial answers are kept, only "none" is refused.
        atype = out.get("answer_type")
        if atype == "none" or (atype not in ("complete", "partial") and not out.get("confident")):
            return Answer(text=REFUSAL, confident=False)
        # A question asking for a value (a rate or a fee) answered without any number means the value
        # was not found: say so plainly instead of returning a description without the value.
        asks_value = (qu.get("intent") in VALUE_INTENTS) if qu else bool(VALUE_QUESTION_RE.search(question))
        if asks_value and not re.search(r"\d", out.get("answer", "")):
            return Answer(text=REFUSAL, confident=False)
        # Prompt O1: a PARTIAL answer to a rate/fee question must contain a number the question did not already contain
        # (digits copied from the question, like "7/1", are not the requested value); otherwise the value was not found.
        if asks_value and atype == "partial":
            nums = lambda t: set(re.findall(r"\d+(?:\.\d+)?", t))
            if not (nums(out.get("answer", "")) - nums(question)):
                return Answer(text=REFUSAL, confident=False)
        if SOFT_REFUSAL and asks_value and soft_refusal(out.get("answer", ""), question):
            return Answer(text=REFUSAL, confident=False)
        if STRIP_NOT_LISTED and asks_value:
            out = {**out, "answer": strip_not_listed(out.get("answer", ""))}
        used = [n for n in out.get("used_excerpts", []) if 1 <= n <= len(hits)] or [1]
        sources, seen = [], set()
        for n in used:
            _, c, urls = hits[n - 1]
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    sources.append(Source(url=u, snapshot_id=c.snapshot_id))
        if CITE_SAME_VALUE:
            sources += self._same_value_sources(out["answer"], hits, used, seen)
        return Answer(text=out["answer"].strip(), sources=sources, confident=True,
                      conflict_note=out.get("conflict_note"))

    @staticmethod
    def _same_value_sources(answer: str, hits, used, seen: set) -> list:
        """Other evidence pages that state the same value as the answer. The model usually names one excerpt even when several pages
        carry the fact (a routing number sits on eight pages); a member is better served by every page that confirms it. Text pieces
        only (fact rows of different products can share a rate), and only when the page contains every distinctive value of the answer
        that the cited pieces contain: percentages, dollar amounts and long numbers. The answer text is not changed."""
        if not hits or hasattr(hits[0][1], "product"):
            return []
        norm = lambda s: re.sub(r"[\s,]", "", s)
        cited = norm(" ".join(hits[n - 1][1].text for n in used))
        values = {norm(v) for v in DISTINCT_VALUE_RE.findall(answer)}
        values = {v for v in values if v in cited}
        if not values:
            return []
        extra = []
        for i, (_, c, urls) in enumerate(hits, 1):
            if i in used or not all(v in norm(c.text) for v in values):
                continue
            for u in urls:
                if u not in seen and len(extra) < CITE_SAME_VALUE_MAX:
                    seen.add(u)
                    extra.append(Source(url=u, snapshot_id=c.snapshot_id))
        return extra

    def conflicts(self) -> list[Conflict]:
        """Contradictions in the newest website copy. Default v2 (conflicts_v2.py: code-read tables + rate sentences, rule matching,
        trust-order winner). MY_SOLUTION_CONFLICTS=old -> the earlier version below (OpenAI-extracted table facts); v2 also falls
        back to it if it fails."""
        if CONFLICTS_MODE != "old" and self._newest is not None:
            try:
                import conflicts_v2
                llm = self.llm if self.llm.available() else None
                cache_file = os.getenv("MY_SOLUTION_SENTENCE_CACHE")   # experiments only: reuse sentence calls between runs
                if cache_file and Path(cache_file).exists() and not self._sentence_cache:
                    self._sentence_cache.update(json.loads(Path(cache_file).read_text()))
                out = conflicts_v2.build(self._newest, llm, self._sentence_cache)
                if cache_file:
                    Path(cache_file).write_text(json.dumps(self._sentence_cache))
                return out
            except Exception as e:   # noqa: BLE001
                print(f"[my_solution] conflicts v2 failed, using the earlier version: {type(e).__name__}: {e}", file=sys.stderr)
        return self._conflicts_old()

    def _conflicts_old(self) -> list[Conflict]:
        """Facts with more than one value in the newest website copy: the competing values, where each was
        seen, the value we believe (most trusted page, then latest date) and why."""
        if not self.facts or not self.snapshots:
            return []
        facts, _ = self.fact_index.get(self.snapshots[-1][1], ([], None))
        out = []
        for occ in group_facts(facts):
            if occ[0].metric not in CONFLICT_METRICS:
                continue
            values = list(dict.fromkeys(f.value for f in occ if re.search(r"\d", f.value)))
            if len(values) < 2:
                continue
            w = winner(occ)
            q = ", ".join(f"{k} {v}" for k, v in w.qualifiers.items())
            dated = f", effective {w.effective}" if w.effective else (f", published {w.published}" if w.published else "")
            out.append(Conflict(
                topic=f"{w.product} {q} {w.metric}".strip(),
                values=[w.value] + [v for v in values if v != w.value],
                sources=[Source(url=u, snapshot_id=w.snapshot_id) for u in dict.fromkeys(f.url for f in occ)],
                resolution=w.value,
                reason=f"{w.page_type.replace('_', ' ')} page {w.url}{dated} outranks the others"))
        return out


# "What changed" questions (did it change, what was it before, is it higher than in June): the same search is run in every website
# copy and the answer model gets each piece with the dates of the copies it was seen in. Only when the Decisions label says the question
# is about change AND the question contains a change word (decisions_understanding.py). Default on since the Step 3 test
# change questions 0.28 -> 1.00 on eval/subsets/history_slice.jsonl, no practice question takes this path. 0 rolls back.
HISTORY = os.getenv("MY_SOLUTION_HISTORY", "1") == "1"
HISTORY_FACTS_PER_COPY, HISTORY_FACT_LINES = 6, 16
HISTORY_PIECES_PER_COPY, HISTORY_PIECES = 4, 8
# "What changed" questions about page text (not rates or fees): the embedding-window pieces of each copy are added too, because keyword
# search alone ranks the wrong pages first in a copy (same problem as for a dated question). MY_SOLUTION_HISTORY_WINDOWS=0 turns this off.
HISTORY_WINDOWS = os.getenv("MY_SOLUTION_HISTORY_WINDOWS", "1") == "1"
HISTORY_WINDOW_PIECES = 6
# The "Question date:" line gives the date a loose period was read as, and the answer step is told what "Website as of" means
# (MY_SOLUTION_DATE_NOTE_EXPLAIN=0 turns both off).
DATE_NOTE_EXPLAIN = os.getenv("MY_SOLUTION_DATE_NOTE_EXPLAIN", "1") == "1"
# A "what changed" question is not told to answer "As of <date>" (MY_SOLUTION_STATE_DATE_SKIP_CHANGE=0 turns this off).
STATE_DATE_SKIP_CHANGE = os.getenv("MY_SOLUTION_STATE_DATE_SKIP_CHANGE", "1") == "1"
# Also cite the other evidence pages that state the same value as the answer (see _same_value_sources). 0 rolls back.
CITE_SAME_VALUE = os.getenv("MY_SOLUTION_CITE_SAME_VALUE", "1") == "1"
CITE_SAME_VALUE_MAX = 4
DISTINCT_VALUE_RE = re.compile(r"\d+(?:\.\d+)?\s*%|\$\s?\d[\d,]*(?:\.\d+)?|\b\d[\d-]{6,}\d\b")
CONFLICTS_MODE = os.getenv("MY_SOLUTION_CONFLICTS", "v2")   # v2 (default) | old
# Put facts of the rate type the question asks for first (rate vs APR vs APY). Default on since the 3+3 test; 0 rolls back.
METRIC_FIRST = os.getenv("MY_SOLUTION_METRIC_FIRST", "1") == "1"
# Start the question's embedding at the same time as the query-understanding call (same input, so answers cannot change). 0 = off.
EMBED_PREFETCH = os.getenv("MY_SOLUTION_EMBED_PREFETCH", "1") == "1"
# In a rate/fee answer that gives the value, drop sentences that only say something isn't listed. Default on; 0 rolls back.
STRIP_NOT_LISTED = os.getenv("MY_SOLUTION_STRIP_NOT_LISTED", "1") == "1"
NOT_LISTED_RE = re.compile(r"\b(isn['’]t|is not|aren['’]t|are not|wasn['’]t|was not|not)\s+(listed|provided|included|shown|stated|"
                           r"available|specified|given|published)\b|\bdo(es)?(n['’]t| not)\s+(list|provide|include|state|show|specify|"
                           r"publish)\b|\bI don['’]t know\b", re.I)


VALUE_NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*%|\$\s?\d[\d,]*(?:\.\d+)?")
# Treat a rate/fee answer that only says the value isn't listed as the standard refusal. Experiment switch, default off.
SOFT_REFUSAL = os.getenv("MY_SOLUTION_SOFT_REFUSAL", "0") == "1"


def strip_not_listed(text: str) -> str:
    """Drop sentences that say something isn't listed and contain no number, when the rest of the answer still gives a number
    ("Regular certificates pay 1.79% to 3.37%. The APY isn't listed." -> the first sentence only)."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    keep = [p for p in parts if not (NOT_LISTED_RE.search(p) and not VALUE_NUM_RE.search(p))]
    rest = " ".join(keep)
    # only when the rest still states a value (a % or $ amount); a phone number or "12 months" is not an answer to "what rate"
    return rest if keep and VALUE_NUM_RE.search(rest) and len(keep) < len(parts) else text


def soft_refusal(text: str, question: str) -> bool:
    """A rate/fee answer that says the value isn't listed and states no rate or dollar amount of its own (phone numbers and terms
    do not count) is a refusal in substance: "Dupaco doesn't list a specific construction-loan rate ... call 800-383-1700"."""
    values = set(VALUE_NUM_RE.findall(text)) - set(VALUE_NUM_RE.findall(question))
    return bool(NOT_LISTED_RE.search(text)) and not values


# Answer "how many branches / employees / members", "total assets" from the newest dated statement. Default on; 0 rolls back.
COUNT_ANSWERS = os.getenv("MY_SOLUTION_COUNT_ANSWERS", "1") == "1"
METRIC_FOR_ASKED = {"interest rate": {"rate", "interest rate"}, "rate": {"rate", "interest rate"}, "apr": {"APR"}, "apy": {"APY"}}


def build() -> Knowledge:
    # Experiment switches only (unset when graded): MY_SOLUTION_FACTS=0 turns the fact path off;
    # MY_SOLUTION_FACT_CACHE=<file> reuses extracted facts between runs instead of paying to extract again.
    # MY_SOLUTION_QU_CACHE=<file> reuses query-understanding results (freezes search inputs across experiment runs).
    cache = os.getenv("MY_SOLUTION_FACT_CACHE")
    qu_cache = os.getenv("MY_SOLUTION_QU_CACHE")
    return Knowledge(use_facts=os.getenv("MY_SOLUTION_FACTS", "1") != "0",
                     fact_cache_path=Path(cache) if cache else None,
                     qu_cache_path=Path(qu_cache) if qu_cache else None)
