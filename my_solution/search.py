"""BM25 keyword search over chunks, one index per snapshot, plus a source-tier boost."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from chunker import Chunk
from tiers import PRODUCT, PROMO, RATE_SHEET, SECONDARY, page_rank

TOKEN_RE = re.compile(r"\d+(?:\.\d+)?%?|[a-z]+")
STOP = set("""a an the of to in on for and or is are was were be by with at as it its this that what
which who how do does did can could you your i me my we our us there their from any all about
tell please get give provide right now currently current dupaco""".split())

# Score multipliers by page rank. 1.0 everywhere = plain BM25 (the baseline).
BOOSTS = {
    "none": {RATE_SHEET: 1.0, PRODUCT: 1.0, PROMO: 1.0, SECONDARY: 1.0},
    "tiers": {RATE_SHEET: 1.3, PRODUCT: 1.2, PROMO: 1.1, SECONDARY: 0.6},
}


try:   # Snowball stemmer (PyStemmer), as in the cheat-at-search notebooks
    import Stemmer
    _SNOWBALL = Stemmer.Stemmer("english")
except ImportError:   # fall back to a crude plural stripper
    _SNOWBALL = None

POSSESSIVE_RE = re.compile(r"['’]s\b")


def _crude_stem(t: str) -> str:
    if t.endswith("ies") and len(t) > 4:
        return t[:-3] + "y"
    if t.endswith("s") and not t.endswith("ss") and len(t) > 3:
        return t[:-1]
    return t


def _stem(t: str) -> str:
    if t[0].isdigit():
        return t
    return _SNOWBALL.stemWord(t) if _SNOWBALL else _crude_stem(t)


def tokenize(text: str) -> list[str]:
    text = POSSESSIVE_RE.sub("", text.lower()).replace(",", "")
    return [_stem(t) for t in TOKEN_RE.findall(text) if t not in STOP]


class BM25Index:
    def __init__(self, chunks: list[Chunk], k1: float = 1.2, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.lengths = []
        for i, c in enumerate(chunks):
            tf = Counter(tokenize(c.index_text()))
            self.lengths.append(sum(tf.values()))
            for t, n in tf.items():
                self.postings[t].append((i, n))
        self.avgdl = (sum(self.lengths) / len(self.lengths)) if self.lengths else 1.0
        N = len(chunks)
        self.idf = {t: math.log(1 + (N - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}
        self.rank = [page_rank(c.url) for c in chunks]

    def search(self, query: str, k: int = 10, boost: str = "tiers", categories=(), cat_boost: float = 0.0,
               qualifiers=(), qual_boost: float = 0.0, expansion_tokens=(),
               expansion_weight: float = 0.5) -> list[tuple[float, Chunk]]:
        """BM25 x page trust, plus fixed bonuses (added, as in the cheat-at-search notebooks) for pieces
        in a chosen category and pieces containing a parsed qualifier. Bonuses only go to pieces that
        already match some query words, so a category alone cannot pull in unrelated pieces."""
        scores: dict[int, float] = defaultdict(float)
        q = set(tokenize(query))
        weighted = [(t, 1.0) for t in q] + [(t, expansion_weight) for t in set(expansion_tokens) if t not in q]
        for t, w in weighted:
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, tf in self.postings[t]:
                dl = self.lengths[i]
                scores[i] += w * idf * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        weights = BOOSTS[boost]
        cats = set(categories)
        final = {}
        for i, s in scores.items():
            c = self.chunks[i]
            v = s * weights[self.rank[i]]
            if cat_boost and cats and cats.intersection(c.categories):
                v += cat_boost
            if qual_boost and qualifiers and any(p.search(c.text) for p in qualifiers):
                v += qual_boost
            final[i] = v
        ranked = sorted(((v, i) for i, v in final.items()), key=lambda x: (-x[0], x[1]))
        return [(s, self.chunks[i]) for s, i in ranked[:k]]
