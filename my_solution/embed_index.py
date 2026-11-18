"""
Embedding retriever (meaning-based search) to sit beside the BM25 index.

- EmbeddingStore: a file of vectors keyed by the SHA-1 of each piece's text, so the file survives re-chunking, is shared by
  all website copies (the same paragraph is embedded once) and is reused on later runs. Only texts missing from the file are embedded.
- DenseIndex: the vectors of one website copy's pieces, aligned to its chunk list; search(question) -> ranked chunk ids.
- fuse(): reciprocal-rank fusion of any number of ranked lists (BM25 + embeddings = hybrid).

Needs OPENAI_API_KEY (text-embedding-3-small by default; override with MY_SOLUTION_EMBED_MODEL). Nothing here is wired into answer()
yet; the file is plain numpy (.npz), vectors stored as float16 and normalised.
"""
from __future__ import annotations

import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import numpy as np

MODEL = os.getenv("MY_SOLUTION_EMBED_MODEL", "text-embedding-3-small")
CACHE_PATH = Path(os.getenv("MY_SOLUTION_EMBED_CACHE") or Path(__file__).resolve().parent / ".embed_cache" / f"{MODEL}.npz")
QUESTION_CACHE = Path(os.getenv("MY_SOLUTION_QUESTION_CACHE") or Path(__file__).resolve().parent / ".embed_cache" / f"questions-{MODEL}.npz")
MAX_CHARS = 6000   # a piece longer than this is cut before embedding (the model limit is 8,191 tokens)


def text_key(text: str) -> str:
    return hashlib.sha1(" ".join(text.split()).lower().encode()).hexdigest()


class EmbeddingStore:
    def __init__(self, path: Path = CACHE_PATH, client=None):
        self.path, self._client = path, client
        self.vecs: dict[str, np.ndarray] = {}
        self.usage = {"tokens": 0, "calls": 0}
        if path.exists():
            z = np.load(path, allow_pickle=False)
            self.vecs = {k: v for k, v in zip(z["keys"].tolist(), z["vectors"])}

    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(timeout=60, max_retries=2)
        return self._client

    def _embed(self, texts: list[str], batch: int = 128) -> np.ndarray:
        out = []
        for i in range(0, len(texts), batch):
            r = self.client().embeddings.create(model=MODEL, input=[t[:MAX_CHARS] for t in texts[i:i + batch]])
            self.usage["tokens"] += r.usage.total_tokens
            self.usage["calls"] += 1
            out += [d.embedding for d in r.data]
        v = np.array(out, dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    def ensure(self, texts: list[str]) -> None:
        """Embed every text not yet in the file, then save."""
        missing = {}
        for t in texts:
            k = text_key(t)
            if k not in self.vecs and k not in missing:
                missing[k] = t
        if missing:
            keys = list(missing)
            for k, v in zip(keys, self._embed([missing[k] for k in keys])):
                self.vecs[k] = v.astype(np.float16)
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        keys = list(self.vecs)
        np.savez_compressed(self.path, keys=np.array(keys), vectors=np.stack([self.vecs[k] for k in keys]))

    def embed_query(self, text: str) -> np.ndarray:
        """Question vector. Shared by every store in the process: a prefetch started at the top of answer() (prefetch_query) is
        awaited instead of embedding again; questions seen on earlier runs come from a small file (no API call)."""
        k = text_key(text)
        fut = _PENDING.get(k)
        if fut is not None:
            return fut.result().astype(np.float32)
        return _question_vector(self, text).astype(np.float32)


# ---------------------------------------------------------------- question vectors (shared, prefetched)
_QVECS: dict = {}            # text key -> vector, loaded from QUESTION_CACHE once
_QLOADED = False
_PENDING: dict = {}          # text key -> Future of a prefetch
_QLOCK = threading.Lock()
_POOL = ThreadPoolExecutor(max_workers=2)


def _load_questions() -> None:
    global _QLOADED
    with _QLOCK:
        if not _QLOADED:
            if QUESTION_CACHE.exists():
                z = np.load(QUESTION_CACHE, allow_pickle=False)
                _QVECS.update(zip(z["keys"].tolist(), z["vectors"]))
            _QLOADED = True


def _save_questions() -> None:
    with _QLOCK:
        keys = list(_QVECS)
        if keys:
            QUESTION_CACHE.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(QUESTION_CACHE, keys=np.array(keys), vectors=np.stack([_QVECS[a] for a in keys]))


def _question_vector(store: "EmbeddingStore", text: str) -> np.ndarray:
    _load_questions()
    k = text_key(text)
    v = _QVECS.get(k)
    if v is None:
        v = store._embed([text])[0].astype(np.float16)
        _QVECS[k] = v
        _POOL.submit(_save_questions)      # write the file in the background, off the answer's critical path
    return v


_PREFETCH_STORE = None


def prefetch_query(text: str, store: "Optional[EmbeddingStore]" = None) -> None:
    """Start embedding a question now (runs while the query-understanding call is in flight). Same text, same vector.
    Questions that end up not needing meaning search (rate and fee questions) cost one tiny unused embedding."""
    global _PREFETCH_STORE
    if store is None:
        _PREFETCH_STORE = _PREFETCH_STORE or EmbeddingStore(path=QUESTION_CACHE.parent / "_prefetch_client_only.npz")
        store = _PREFETCH_STORE
    k = text_key(text)
    with _QLOCK:
        if k in _PENDING or k in _QVECS:
            return
        _PENDING[k] = _POOL.submit(_question_vector, store, text)


class DenseIndex:
    def __init__(self, chunks, store: EmbeddingStore, text_of=lambda c: c.index_text()):
        self.chunks, self.store = chunks, store
        texts = [text_of(c) for c in chunks]
        store.ensure(texts)
        self.matrix = np.stack([store.vecs[text_key(t)] for t in texts]).astype(np.float32)

    def search(self, question: str, k: int = 100) -> list[tuple[float, int]]:
        """Top-k (similarity, chunk id) by meaning."""
        sims = self.matrix @ self.store.embed_query(question)
        top = np.argsort(-sims)[:k]
        return [(float(sims[i]), int(i)) for i in top]


def fuse(ranked_lists: list[list[int]], k: int = 60) -> list[int]:
    """Reciprocal-rank fusion: each list adds 1/(k+rank) to an id's score."""
    score: dict[int, float] = {}
    for L in ranked_lists:
        for r, i in enumerate(L, 1):
            score[i] = score.get(i, 0.0) + 1.0 / (k + r)
    return [i for i, _ in sorted(score.items(), key=lambda x: -x[1])]


# ---------------------------------------------------------------- overlapping windows
WINDOW_CHARS, WINDOW_STRIDE = 600, 400   # 600-character windows starting every 400 characters (200 overlap)
WINDOW_CACHE = Path(os.getenv("MY_SOLUTION_WINDOW_CACHE") or Path(__file__).resolve().parent / ".embed_cache" / f"windows-{MODEL}.npz")


class WindowIndex:
    """Meaning search over overlapping text windows cut from each piece (finds one sentence buried in a long piece).
    search(question) -> [(similarity, parent chunk id, window text)] best windows first, one hit per distinct window text."""

    def __init__(self, chunks, store: Optional[EmbeddingStore] = None):
        self.chunks = chunks
        self.store = store or EmbeddingStore(path=WINDOW_CACHE)
        seen, self.windows = set(), []      # (text, parent chunk id)
        for ci, c in enumerate(chunks):
            t = c.text
            for s in range(0, max(len(t) - (WINDOW_CHARS - WINDOW_STRIDE), 1), WINDOW_STRIDE):
                w = t[s:s + WINDOW_CHARS].strip()
                k = text_key(w)
                if len(w) >= 40 and k not in seen:
                    seen.add(k); self.windows.append((w, ci))
        self.store.ensure([w for w, _ in self.windows])
        self.matrix = np.stack([self.store.vecs[text_key(w)] for w, _ in self.windows]).astype(np.float32)

    def search(self, question: str, k: int = 10) -> list[tuple[float, int, str]]:
        sims = self.matrix @ self.store.embed_query(question)
        return [(float(sims[i]), self.windows[i][1], self.windows[i][0]) for i in np.argsort(-sims)[:k]]
