"""
Local paragraph embeddings + cosine-similarity index.

Why local: at this stage we don't want a hard dep on a third-party embedding
API (Voyage / OpenAI / Cohere) — every paragraph would cost money to embed
and queries would carry latency. fastembed runs ONNX models locally, ~15ms
per paragraph on CPU. Model file is ~80MB, cached after first download.

Model: BAAI/bge-small-en-v1.5 (384-dim). Decent baseline for English legal
prose. Swap to a legal-tuned model (e.g. Voyage law-2) later by changing
EMBED_MODEL_NAME — re-embedding the corpus is fast enough on CPU that
that migration is a one-day chore.

Storage: piggyback on kanoon_cache.sqlite — same DB file, new table
`paragraph_embeddings`. Embeddings stored as float32 BLOBs (1,536 bytes
per 384-dim vector). For 50k paragraphs that's ~80MB on disk and ~75MB RAM
when loaded. Above that, swap to sqlite-vec extension or a real vector DB.

Search: brute-force cosine similarity using numpy. At 50k paragraphs that's
a single ~15ms matmul. Will scale to ~200k before becoming slow enough to
matter.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np


EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384

# Embeddings piggyback on the same SQLite file as the kanoon cache.
try:
    from headnote.config import KANOON_CACHE_PATH as DEFAULT_DB_PATH
except ImportError:
    DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "kanoon_cache.sqlite"

# Batch size for embedding — fastembed handles batches efficiently
EMBED_BATCH_SIZE = 32


# --- shared process-wide model singleton -----------------------------------
# The fastembed model is ~80MB in RAM. Everything that needs to embed text
# (the judgment index, the document vault, …) shares ONE instance via these
# module-level helpers so we never pay for the model twice. Whichever caller
# touches it first loads it; the boot-time warm-up primes it for the rest.
_SHARED_MODEL = None
_SHARED_MODEL_LOCK = threading.Lock()


def get_embedding_model():
    """Return the process-wide fastembed TextEmbedding, loading it on first use."""
    global _SHARED_MODEL
    if _SHARED_MODEL is not None:
        return _SHARED_MODEL
    with _SHARED_MODEL_LOCK:
        if _SHARED_MODEL is None:
            from fastembed import TextEmbedding  # heavy import — pay once
            t0 = time.time()
            _SHARED_MODEL = TextEmbedding(EMBED_MODEL_NAME)
            print(f"[embeddings] loaded {EMBED_MODEL_NAME} in {time.time()-t0:.1f}s")
    return _SHARED_MODEL


def embed_texts(texts: Iterable[str]) -> list["np.ndarray"]:
    """Embed strings → L2-normalised float32 unit vectors (cosine = dot product).

    The generic embedding entrypoint reused by callers outside the judgment
    index (e.g. the document vault). Returns one vector per input, in order.
    """
    items = list(texts)
    if not items:
        return []
    model = get_embedding_model()
    out: list[np.ndarray] = []
    for v in model.embed(items, batch_size=EMBED_BATCH_SIZE):
        v = v.astype(np.float32, copy=False)
        norm = float(np.linalg.norm(v))
        if norm > 0:
            v = v / norm
        out.append(v)
    return out


@dataclass(frozen=True)
class EmbeddingHit:
    case_id: str
    para_id: str
    para_num: int | None
    structure: str
    text: str
    similarity: float


class EmbeddingIndex:
    """Local paragraph embedding store + similarity search.

    Embeddings live in the same SQLite file as the kanoon cache. The
    fastembed model is lazy-loaded on first use (heavy import + model file).
    """

    def __init__(self, db_path: str | os.PathLike | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._model = None              # lazy
        self._model_lock = threading.Lock()
        # In-memory cache of (ids, vectors) for fast repeated search.
        # Invalidated whenever upsert_paragraphs() adds new rows.
        self._cache_loaded = False
        self._cache_lock = threading.Lock()
        self._cache_meta: list[tuple] = []      # [(case_id, para_id, para_num, structure, text)]
        self._cache_vecs: np.ndarray | None = None  # (N, EMBED_DIM) float32

        self._init_table()

    # --- db plumbing

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.db_path, timeout=10)
        try:
            yield c
        finally:
            c.close()

    def _init_table(self) -> None:
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS paragraph_embeddings (
                    case_id    TEXT NOT NULL,
                    para_id    TEXT NOT NULL,
                    para_num   INTEGER,
                    structure  TEXT,
                    text       TEXT NOT NULL,
                    vec        BLOB NOT NULL,        -- float32 little-endian, EMBED_DIM dims
                    model_name TEXT NOT NULL,        -- which model produced this vec
                    embedded_at TEXT NOT NULL,
                    PRIMARY KEY (case_id, para_id)
                );
                CREATE INDEX IF NOT EXISTS idx_emb_case ON paragraph_embeddings(case_id);
            """)
            c.commit()

    # --- model (lazy)

    def _get_model(self):
        # Share the process-wide singleton so the model loads at most once.
        if self._model is None:
            self._model = get_embedding_model()
        return self._model

    # --- upsert + load

    def upsert_paragraphs(self, paragraphs: Iterable[tuple]) -> int:
        """Embed and store a batch of paragraphs.

        Each paragraph: (case_id, para_id, para_num, structure, text).
        Skips paragraphs already present for the same (case_id, para_id) and
        same model. Returns count of newly embedded rows.

        Invalidates the in-memory cache so the next search reloads.
        """
        # Filter out (case_id, para_id) pairs we already have for this model
        candidates = list(paragraphs)
        if not candidates:
            return 0

        with self._conn() as c:
            existing = set()
            # SQLite IN clause needs explicit parameter binding for safety;
            # fall back to a JOIN-style check via a temp table if the batch
            # is large. For typical batches (~75 paragraphs), this is fine.
            for cid, pid, *_ in candidates:
                row = c.execute(
                    "SELECT 1 FROM paragraph_embeddings WHERE case_id=? AND para_id=? AND model_name=?",
                    (cid, pid, EMBED_MODEL_NAME),
                ).fetchone()
                if row:
                    existing.add((cid, pid))
        to_embed = [p for p in candidates if (p[0], p[1]) not in existing]
        if not to_embed:
            return 0

        model = self._get_model()
        texts = [p[4] for p in to_embed]
        # fastembed.embed returns a generator of np.ndarray vectors
        vecs = list(model.embed(texts, batch_size=EMBED_BATCH_SIZE))

        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        rows = []
        for (cid, pid, pnum, struct, text), vec in zip(to_embed, vecs):
            # L2-normalise so cosine = dot
            v = vec.astype(np.float32, copy=False)
            norm = float(np.linalg.norm(v))
            if norm > 0:
                v = v / norm
            rows.append((
                cid, pid, pnum, struct, text,
                v.tobytes(), EMBED_MODEL_NAME, now,
            ))

        with self._conn() as c:
            c.executemany(
                "INSERT OR REPLACE INTO paragraph_embeddings "
                "(case_id, para_id, para_num, structure, text, vec, model_name, embedded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            c.commit()

        # Invalidate in-memory cache
        with self._cache_lock:
            self._cache_loaded = False
            self._cache_meta = []
            self._cache_vecs = None

        return len(rows)

    def _ensure_cache_loaded(self) -> None:
        with self._cache_lock:
            if self._cache_loaded:
                return
            with self._conn() as c:
                rows = c.execute(
                    "SELECT case_id, para_id, para_num, structure, text, vec "
                    "FROM paragraph_embeddings WHERE model_name=?",
                    (EMBED_MODEL_NAME,),
                ).fetchall()
            if not rows:
                self._cache_meta = []
                self._cache_vecs = np.zeros((0, EMBED_DIM), dtype=np.float32)
                self._cache_loaded = True
                return
            self._cache_meta = [(r[0], r[1], r[2], r[3], r[4]) for r in rows]
            vecs = np.empty((len(rows), EMBED_DIM), dtype=np.float32)
            for i, r in enumerate(rows):
                vecs[i] = np.frombuffer(r[5], dtype=np.float32)
            self._cache_vecs = vecs
            self._cache_loaded = True

    # --- search

    def search(
        self,
        query_text: str,
        *,
        top_k: int = 20,
        min_similarity: float = 0.30,
        case_ids: set[str] | None = None,
    ) -> list[EmbeddingHit]:
        """Cosine-similarity search over the embedding index.

        Optionally restricted to `case_ids` (used to score paragraphs within
        a specific set of cases).
        """
        self._ensure_cache_loaded()
        if not self._cache_meta or self._cache_vecs is None or len(self._cache_vecs) == 0:
            return []

        # Embed the query
        model = self._get_model()
        q = next(iter(model.embed([query_text])))
        q = q.astype(np.float32, copy=False)
        qn = float(np.linalg.norm(q))
        if qn == 0:
            return []
        q = q / qn

        # Apply case_id filter via mask (cheap for small filters)
        if case_ids is not None:
            mask = np.array([m[0] in case_ids for m in self._cache_meta], dtype=bool)
            if not mask.any():
                return []
            vecs = self._cache_vecs[mask]
            metas = [m for m, keep in zip(self._cache_meta, mask) if keep]
        else:
            vecs = self._cache_vecs
            metas = self._cache_meta

        sims = vecs @ q          # (N,) — both sides L2-normalised, so this is cosine
        # Top-k via argpartition (faster than full sort for large N)
        k = min(top_k, len(sims))
        if k == 0:
            return []
        if k < len(sims):
            top_idx = np.argpartition(-sims, k - 1)[:k]
            # Sort the top-k by similarity
            top_idx = top_idx[np.argsort(-sims[top_idx])]
        else:
            top_idx = np.argsort(-sims)
        out: list[EmbeddingHit] = []
        for i in top_idx:
            sim = float(sims[i])
            if sim < min_similarity:
                continue
            m = metas[i]
            out.append(EmbeddingHit(
                case_id=m[0], para_id=m[1], para_num=m[2], structure=m[3] or "other",
                text=m[4], similarity=sim,
            ))
        return out

    # --- stats

    def stats(self) -> dict:
        with self._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM paragraph_embeddings").fetchone()[0]
            cases = c.execute(
                "SELECT COUNT(DISTINCT case_id) FROM paragraph_embeddings"
            ).fetchone()[0]
            models = c.execute(
                "SELECT model_name, COUNT(*) FROM paragraph_embeddings GROUP BY model_name"
            ).fetchall()
        return {
            "paragraph_count": int(n),
            "case_count": int(cases),
            "by_model": {m: int(c) for m, c in models},
            "active_model": EMBED_MODEL_NAME,
            "dim": EMBED_DIM,
        }
