"""
Wormhole vectors (after Trey Grainger; PoC at github.com/ajayp/wormhole-vectors), in memory, no Solr, no model call.

Switch (default off): MY_SOLUTION_WORMHOLE = off | d2s | s2d | both
  d2s  dense -> terms -> BM25. The best embedding windows of the question (the foreground set) are read for words that are far more
       common there than in the whole website copy (a counting stand-in for Solr's SKG relatedness()). Those words are ADDED to the
       BM25 query at the synonym weight. Aim: wording gaps, with no hand-kept synonym list.
  s2d  BM25 -> pooled vector -> KNN. The vectors of the windows of the BM25 top pieces are averaged (mean + L2 norm) and the meaning
       search runs on that average instead of on the question vector (needs no question embedding).
  both d2s for the BM25 query, s2d for the window pieces.

Pure functions over a BM25Index and a WindowIndex (embed_index.py); nothing here calls an API.
"""
from __future__ import annotations

import math
import os
from collections import Counter

import numpy as np

from search import tokenize

MODE = os.getenv("MY_SOLUTION_WORMHOLE", "off")
FOREGROUND_K = int(os.getenv("MY_SOLUTION_WORMHOLE_FG", "15"))      # pieces in the foreground set
TERM_LIMIT = int(os.getenv("MY_SOLUTION_WORMHOLE_TERMS", "8"))      # terms added to the BM25 query
MIN_FG = int(os.getenv("MY_SOLUTION_WORMHOLE_MIN_FG", "3"))         # a term must appear in at least this many foreground pieces
MIN_LIFT = float(os.getenv("MY_SOLUTION_WORMHOLE_MIN_LIFT", "3"))   # ... and be at least this many times as common there as overall
POOL_N = int(os.getenv("MY_SOLUTION_WORMHOLE_POOL", "8"))           # BM25 pieces pooled for s2d


def foreground_chunk_ids(wi, question: str, n: int | None = None) -> list[int]:
    """Parent piece ids of the best embedding windows, best first, each piece once."""
    n = n or FOREGROUND_K
    seen, out = set(), []
    for _, ci, _ in wi.search(question, k=n * 6):
        if ci not in seen:
            seen.add(ci)
            out.append(ci)
            if len(out) == n:
                break
    return out


def skg_terms(index, chunk_ids: list[int], exclude=(), limit: int | None = None,
              min_fg: int | None = None, min_lift: float | None = None) -> list[tuple[str, float]]:
    """Terms over-represented in the foreground pieces against the whole index: score = p_fg * ln(p_fg / p_bg) (their share of the
    divergence), kept when present in >= min_fg pieces and >= min_lift times as common as in the whole copy. Terms are the stemmed
    tokens BM25 uses; numbers and the question's own words are left out."""
    limit, min_fg, min_lift = limit or TERM_LIMIT, min_fg or MIN_FG, min_lift or MIN_LIFT   # read at call time so a test can change them
    if len(chunk_ids) < min_fg:
        return []
    df = Counter()
    for ci in chunk_ids:
        df.update(set(tokenize(index.chunks[ci].index_text())))
    F, N, ex = len(chunk_ids), len(index.chunks), set(exclude)
    scored = []
    for t, n in df.items():
        if n < min_fg or t in ex or t[0].isdigit():
            continue
        bg = len(index.postings.get(t, ()))
        if not bg:
            continue
        p_f, p_b = n / F, bg / N
        lift = p_f / p_b
        if lift >= min_lift:
            scored.append((t, p_f * math.log(lift)))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored[:limit]


def _by_parent(wi) -> dict:
    m = getattr(wi, "_by_parent", None)
    if m is None:
        m = {}
        for wid, (_, ci) in enumerate(wi.windows):
            m.setdefault(ci, []).append(wid)
        wi._by_parent = m
    return m


def pooled_vector(wi, chunk_ids: list[int]):
    """Mean of the window vectors of the given pieces, L2-normalised; None when none of them has a window."""
    by = _by_parent(wi)
    ids = [w for ci in chunk_ids for w in by.get(ci, ())]
    if not ids:
        return None
    v = wi.matrix[ids].mean(axis=0)
    n = float(np.linalg.norm(v))
    return v / n if n else None


def search_vector(wi, vec, k: int = 40) -> list[tuple[float, int, str]]:
    """Same result shape as WindowIndex.search, for a ready-made vector."""
    sims = wi.matrix @ vec
    return [(float(sims[i]), wi.windows[i][1], wi.windows[i][0]) for i in np.argsort(-sims)[:k]]
