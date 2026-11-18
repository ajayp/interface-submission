"""Spelling help for member questions (default on; MY_SOLUTION_SPELLFIX=0 rolls back).

A typo can remove the one product word a search depends on ("savngs"). This module learns the words the website itself uses
(raw lowercase words with counts, built while the snapshots load) and, for each question word the site does not use, finds the
site word one edit away. It also merges a split word ("sav ings") and splits a run-together word ("moneymarket") when both halves
are common site words.

It only ADDS words: solution.py appends them to the search text and to the synonym lookup, and the member's own words stay. The
Decisions call, the embedding search and the answer model still get the question as typed. No model call, no new package.

Guards (each one stops a wrong correction): a word is left alone if it is a stop word, shorter than 5 letters, or the site uses
it 3 or more times; a candidate must share the first letter, be at least 10 times as common on the site as the typed word
(and appear 5 or more times), and be 1 edit away (2 edits for words of 9 or more letters; a swap of neighbours counts as 1).
Numbers are never touched.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from search import STOP   # the same stop words the search ignores

POSS = re.compile(r"['’]s\b")
WORD = re.compile(r"[a-z]+")
MIN_LEN = 5       # shorter words are not corrected
MIN_CAND = 5      # a correction must be a word the site uses at least this often
RATIO = 10        # ... and at least this many times more often than the typed word
KNOWN = 3         # a word the site uses this often is a real word
SPLIT_MIN = 20    # both halves of a split / merged word must be common site words


def words(text: str) -> list[str]:
    """Raw lowercase words, with the same possessive and comma handling as search.tokenize (letters only)."""
    return WORD.findall(POSS.sub("", text.lower()).replace(",", ""))


def _max_edits(w: str) -> int:
    return 2 if len(w) >= 9 else 1


def _deletes(w: str, d: int) -> set[str]:
    out = {w}
    frontier = {w}
    for _ in range(d):
        frontier = {x[:i] + x[i + 1:] for x in frontier for i in range(len(x))}
        out |= frontier
    return out


def _edit_distance(a: str, b: str) -> int:
    """Edit distance where swapping two neighbouring letters counts as one edit."""
    m, n = len(a), len(b)
    d = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        d[i][0] = i
    for j in range(n + 1):
        d[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            c = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[m][n]


class SpellFix:
    def __init__(self) -> None:
        self.counts: Counter = Counter()
        self._index: dict[str, set[str]] | None = None   # one-letter-deleted forms -> site words (built on first use)
        self._memo: dict[str, list[str]] = {}

    def add_text(self, text: str) -> None:
        """Count the words of one page (called while a snapshot loads)."""
        self.counts.update(words(text))
        self._index = None
        self._memo.clear()

    def _build(self) -> dict[str, set[str]]:
        index: dict[str, set[str]] = defaultdict(set)
        for w, c in self.counts.items():
            if len(w) >= MIN_LEN and c >= MIN_CAND:
                for dl in _deletes(w, _max_edits(w)):
                    index[dl].add(w)
        self._index = index
        return index

    def correct(self, w: str) -> str | None:
        """The site word this word was probably meant to be, or None (also None for anything the guards rule out)."""
        if len(w) < MIN_LEN or w in STOP or self.counts.get(w, 0) >= KNOWN:
            return None
        index = self._index if self._index is not None else self._build()
        d = _max_edits(w)
        cands: set[str] = set()
        for dl in _deletes(w, d):
            cands |= index.get(dl, set())
        best = None
        for c in cands:
            if c[0] != w[0]:
                continue
            dist = _edit_distance(w, c)
            if dist > d or self.counts[c] < RATIO * max(self.counts.get(w, 0), 1):
                continue
            key = (-self.counts[c], dist)
            if best is None or key < best[0]:
                best = (key, c)
        return best[1] if best else None

    def _split(self, w: str) -> tuple[str, str] | None:
        """'moneymarket' -> ('money', 'market'): only for a long word the site does not use, when both halves are common site words."""
        if len(w) < 7 or w in STOP or self.counts.get(w, 0) >= KNOWN:
            return None
        best = None
        for i in range(3, len(w) - 2):
            a, b = w[:i], w[i:]
            if self.counts.get(a, 0) >= SPLIT_MIN and self.counts.get(b, 0) >= SPLIT_MIN:
                score = min(self.counts[a], self.counts[b])
                if best is None or score > best[0]:
                    best = (score, a, b)
        return (best[1], best[2]) if best else None

    def extra_words(self, question: str) -> list[str]:
        """Words to ADD to the search for this question (empty for a question without typos)."""
        if question in self._memo:
            return self._memo[question]
        toks = words(question)
        extra: list[str] = []
        merged: set[int] = set()
        for i in range(len(toks) - 1):   # a split word: 'sav ings' -> 'savings'
            a, b = toks[i], toks[i + 1]
            if ((self.counts.get(a, 0) < KNOWN or self.counts.get(b, 0) < KNOWN) and self.counts.get(a + b, 0) >= SPLIT_MIN
                    and a not in STOP and b not in STOP):
                extra.append(a + b)
                merged |= {i, i + 1}
        for i, w in enumerate(toks):
            if i in merged:
                continue
            c = self.correct(w)
            if c:
                extra.append(c)
                continue
            parts = self._split(w)
            if parts:
                extra += list(parts)
        self._memo[question] = extra
        return extra
