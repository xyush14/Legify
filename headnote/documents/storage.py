"""Persistence + hybrid search for the Document Vault.

Mirrors headnote/cases/storage.py: SQLite tables in the same file as drafts +
cases + the IK cache (KANOON_CACHE_PATH), so one Railway Volume covers
everything and there's ZERO external setup to test locally.

Three tables, all keyed to the Supabase user.id (or the local-dev synthetic id):

  documents       one row per uploaded file — title, type, OCR'd full_text,
                  page count, metadata. The canonical record.
  documents_fts   FTS5 mirror of (title, full_text) for instant keyword/phrase
                  search (exact names, FIR numbers, section refs).
  document_chunks the full_text split into ~600-char windows, each with a
                  384-dim embedding BLOB. Powers semantic search that survives
                  OCR noise + paraphrase ("cause of death" → "Coma with
                  cumulative effect of haemorrhagic shock").

search_documents() runs BOTH and merges: keyword is precise, semantic is
forgiving. A doc surfaced by either appears, tagged so the UI can show why.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator, Optional

import numpy as np

from headnote.config import KANOON_CACHE_PATH
from headnote.retrieval.embeddings import EMBED_DIM, embed_texts


_COLS = ("id, user_id, title, doc_type, original_filename, mime, page_count, "
         "full_text, metadata_json, created_at, updated_at")

# Chunking for semantic search: ~600 chars per window with light overlap so a
# phrase straddling a boundary still lands inside one chunk.
_CHUNK_CHARS = 600
_CHUNK_OVERLAP = 100


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id                TEXT PRIMARY KEY,
            user_id           TEXT,                 -- Supabase user.id or NULL
            title             TEXT NOT NULL,
            doc_type          TEXT,                 -- 'postmortem' | 'fir' | 'affidavit' | 'order' | 'other'
            original_filename TEXT,
            mime              TEXT,
            page_count        INTEGER NOT NULL DEFAULT 1,
            full_text         TEXT NOT NULL,        -- the OCR'd transcription
            metadata_json     TEXT NOT NULL DEFAULT '{}',
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_docs_user    ON documents(user_id);
        CREATE INDEX IF NOT EXISTS idx_docs_updated ON documents(updated_at DESC);

        -- Keyword index. Standalone (not external-content) FTS5: we mirror rows
        -- in/out by hand so there are no triggers to keep in sync across the
        -- shared cache DB. doc_id is stored but not tokenised.
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
            doc_id UNINDEXED,
            title,
            body
        );

        CREATE TABLE IF NOT EXISTS document_chunks (
            doc_id     TEXT NOT NULL,
            user_id    TEXT,
            chunk_idx  INTEGER NOT NULL,
            text       TEXT NOT NULL,
            vec        BLOB NOT NULL,               -- float32 L2-normalised, EMBED_DIM dims
            PRIMARY KEY (doc_id, chunk_idx)
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_user ON document_chunks(user_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_doc  ON document_chunks(doc_id);

        -- The original page image(s), so the reader can show the scan beside
        -- the text. PDFs are rasterised to one PNG per page on upload. Kept in
        -- a separate table (never SELECT'd by list/search) so the BLOBs don't
        -- weigh down the metadata queries.
        CREATE TABLE IF NOT EXISTS document_pages (
            doc_id     TEXT NOT NULL,
            page_idx   INTEGER NOT NULL,
            mime       TEXT NOT NULL,
            image      BLOB NOT NULL,
            PRIMARY KEY (doc_id, page_idx)
        );
        CREATE INDEX IF NOT EXISTS idx_pages_doc ON document_pages(doc_id);
    """)
    conn.commit()


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(KANOON_CACHE_PATH, timeout=10)
    try:
        _init_schema(c)
        yield c
    finally:
        c.close()


def init_documents_db() -> None:
    """Call once at app boot to ensure the document tables exist."""
    with _conn() as _:
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(r) -> Optional[dict]:
    if not r:
        return None
    return {
        "id": r[0], "user_id": r[1], "title": r[2], "doc_type": r[3],
        "original_filename": r[4], "mime": r[5], "page_count": r[6],
        "full_text": r[7], "metadata": json.loads(r[8] or "{}"),
        "created_at": r[9], "updated_at": r[10],
    }


def _chunk(text: str) -> list[str]:
    """Split transcribed text into overlapping ~600-char windows.

    Prefer to break on paragraph/line boundaries so a chunk stays coherent;
    fall back to a hard char window for long unbroken blocks.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= _CHUNK_CHARS:
        return [text]

    # Split on blank lines / newlines first, then pack greedily up to the cap.
    units = [u.strip() for u in re.split(r"\n\s*\n|\n", text) if u.strip()]
    chunks: list[str] = []
    buf = ""
    for u in units:
        if len(u) > _CHUNK_CHARS:
            # Hard-window an over-long single unit.
            if buf:
                chunks.append(buf)
                buf = ""
            for i in range(0, len(u), _CHUNK_CHARS - _CHUNK_OVERLAP):
                chunks.append(u[i:i + _CHUNK_CHARS])
            continue
        if buf and len(buf) + 1 + len(u) > _CHUNK_CHARS:
            chunks.append(buf)
            # carry a short overlap tail into the next buffer
            tail = buf[-_CHUNK_OVERLAP:]
            buf = (tail + " " + u).strip()
        else:
            buf = (buf + " " + u).strip() if buf else u
    if buf:
        chunks.append(buf)
    return chunks


def _index_chunks(conn: sqlite3.Connection, *, doc_id: str,
                  user_id: Optional[str], full_text: str) -> int:
    """Embed and store the chunks for a document. Returns chunk count.

    Embedding failures must never block a save — the document is still keyword
    searchable via FTS, so we swallow and skip the semantic layer if the model
    can't load.
    """
    chunks = _chunk(full_text)
    if not chunks:
        return 0
    try:
        vecs = embed_texts(chunks)
    except Exception as e:  # noqa: BLE001 — semantic layer is best-effort
        print(f"[documents] embedding skipped for {doc_id}: {e}")
        return 0
    rows = [
        (doc_id, user_id, i, ch, v.astype(np.float32, copy=False).tobytes())
        for i, (ch, v) in enumerate(zip(chunks, vecs))
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO document_chunks (doc_id, user_id, chunk_idx, text, vec) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def add_document(*, user_id: Optional[str], title: str, full_text: str,
                 doc_type: Optional[str] = None,
                 original_filename: Optional[str] = None,
                 mime: Optional[str] = None,
                 pages: Optional[list[tuple[bytes, str]]] = None,
                 metadata: Optional[dict] = None) -> Optional[dict]:
    """Store an OCR'd document + its page images + keyword/semantic indexes.

    `pages` is the list of display images [(bytes, mime), …] — the original
    photo(s), or one PNG per page for a rasterised PDF. page_count is derived
    from it.
    """
    now = _now()
    did = uuid.uuid4().hex
    meta = json.dumps(metadata or {}, ensure_ascii=False)
    pages = pages or []
    page_count = max(1, len(pages))
    with _conn() as c:
        c.execute(
            """INSERT INTO documents
                 (id, user_id, title, doc_type, original_filename, mime,
                  page_count, full_text, metadata_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (did, user_id, title, doc_type, original_filename, mime,
             page_count, full_text, meta, now, now),
        )
        c.execute(
            "INSERT INTO documents_fts (doc_id, title, body) VALUES (?, ?, ?)",
            (did, title, full_text),
        )
        if pages:
            c.executemany(
                "INSERT INTO document_pages (doc_id, page_idx, mime, image) "
                "VALUES (?, ?, ?, ?)",
                [(did, i, mt or "image/png", sqlite3.Binary(b))
                 for i, (b, mt) in enumerate(pages)],
            )
        _index_chunks(c, doc_id=did, user_id=user_id, full_text=full_text)
        c.commit()
        row = c.execute(
            f"SELECT {_COLS} FROM documents WHERE id = ?", (did,),
        ).fetchone()
    return _row(row)


def get_page(doc_id: str, page_idx: int, *, user_id: Optional[str]) -> Optional[tuple[str, bytes]]:
    """Return (mime, image_bytes) for one page, scoped to the owner."""
    with _conn() as c:
        row = c.execute(
            "SELECT p.mime, p.image FROM document_pages p "
            "JOIN documents d ON d.id = p.doc_id "
            "WHERE p.doc_id = ? AND p.page_idx = ? AND d.user_id IS ?",
            (doc_id, page_idx, user_id),
        ).fetchone()
    if not row:
        return None
    return (row[0], bytes(row[1]))


def set_translation(doc_id: str, *, user_id: Optional[str],
                    lang: str, text: str) -> None:
    """Cache a translation of the full text under metadata.translations[lang]."""
    row = get_document(doc_id, user_id=user_id)
    if row is None:
        return
    meta = row.get("metadata") or {}
    meta.setdefault("translations", {})[lang] = text
    with _conn() as c:
        c.execute(
            "UPDATE documents SET metadata_json = ? WHERE id = ? AND user_id IS ?",
            (json.dumps(meta, ensure_ascii=False), doc_id, user_id),
        )
        c.commit()


def get_document(doc_id: str, *, user_id: Optional[str]) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            f"SELECT {_COLS} FROM documents WHERE id = ? AND user_id IS ?",
            (doc_id, user_id),
        ).fetchone()
    return _row(row)


def list_documents(*, user_id: Optional[str], limit: int = 200) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            f"SELECT {_COLS} FROM documents WHERE user_id IS ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    # Trim full_text in list view — the card only needs a preview.
    out = []
    for r in rows:
        d = _row(r)
        if d:
            d["preview"] = (d["full_text"] or "")[:240]
            del d["full_text"]
            out.append(d)
    return out


def delete_document(doc_id: str, *, user_id: Optional[str]) -> bool:
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM documents WHERE id = ? AND user_id IS ?",
            (doc_id, user_id),
        )
        if cur.rowcount:
            c.execute("DELETE FROM documents_fts WHERE doc_id = ?", (doc_id,))
            c.execute("DELETE FROM document_chunks WHERE doc_id = ?", (doc_id,))
            c.execute("DELETE FROM document_pages WHERE doc_id = ?", (doc_id,))
        c.commit()
    return cur.rowcount > 0


# --- search ---------------------------------------------------------------

@dataclass
class _Hit:
    doc_id: str
    keyword_score: float = 0.0   # 0..1, from FTS bm25 (higher = better match)
    semantic_score: float = 0.0  # 0..1, best chunk cosine similarity
    snippet: str = ""

    @property
    def combined(self) -> float:
        # Either signal alone can carry a result; take the stronger, with a
        # small bonus when both agree.
        base = max(self.keyword_score, self.semantic_score)
        both = self.keyword_score > 0 and self.semantic_score > 0
        return min(1.0, base + (0.1 if both else 0.0))

    @property
    def match_type(self) -> str:
        if self.keyword_score > 0 and self.semantic_score > 0:
            return "both"
        return "keyword" if self.keyword_score > 0 else "meaning"


# Common words carry no keyword signal — they'd match nearly every document
# and drown the precise hits. The semantic layer handles them fine, so we drop
# them from the FTS expression only.
_STOPWORDS = {
    "the", "a", "an", "of", "for", "to", "in", "on", "at", "is", "are", "was",
    "were", "and", "or", "by", "with", "from", "as", "that", "this", "it",
    "what", "which", "who", "whom", "when", "where", "how", "why", "did", "do",
    "does", "be", "been", "has", "have", "had", "i", "me", "my",
}


def _fts_query(q: str) -> str:
    """Turn a raw query into a forgiving FTS5 MATCH expression.

    Each meaningful token becomes a prefix term (token*), OR-joined, so a
    partial / slightly-misspelt word still matches. Stopwords are dropped (they
    match everything); if the query is ALL stopwords we keep them so a literal
    phrase like "the order" still searches. Quotes/operators are stripped to
    avoid FTS syntax errors.
    """
    tokens = re.findall(r"\w+", q, flags=re.UNICODE)
    if not tokens:
        return ""
    meaningful = [t for t in tokens if t.lower() not in _STOPWORDS]
    use = meaningful or tokens
    return " OR ".join(f'"{t}"*' for t in use)


def search_documents(*, user_id: Optional[str], query: str,
                     top_k: int = 20) -> list[dict]:
    """Hybrid keyword + semantic search over a user's documents.

    Returns ranked docs (newest metadata + best snippet + why-it-matched),
    NOT raw chunks. Robust to either layer being empty.
    """
    query = (query or "").strip()
    if not query:
        return []

    hits: dict[str, _Hit] = {}

    # 1) Keyword (FTS5) — scope to this user's docs via a join on documents.
    match = _fts_query(query)
    if match:
        with _conn() as c:
            try:
                rows = c.execute(
                    """SELECT f.doc_id,
                              bm25(documents_fts) AS rank,
                              snippet(documents_fts, 2, '[', ']', ' … ', 12) AS snip
                         FROM documents_fts f
                         JOIN documents d ON d.id = f.doc_id
                        WHERE documents_fts MATCH ?
                          AND d.user_id IS ?
                        ORDER BY rank
                        LIMIT ?""",
                    (match, user_id, top_k * 2),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        # bm25 is lower-is-better and unbounded; map to a 0..1 score by rank.
        for i, (doc_id, _rank, snip) in enumerate(rows):
            score = 1.0 - (i / max(1, len(rows)))  # 1.0 for the top hit, descending
            hits[doc_id] = _Hit(doc_id=doc_id, keyword_score=score, snippet=snip or "")

    # 2) Semantic — brute-force cosine over this user's chunks (small N/user).
    try:
        qvec = embed_texts([query])
    except Exception:  # noqa: BLE001 — model unavailable → keyword-only results
        qvec = []
    if qvec:
        q = qvec[0]
        with _conn() as c:
            chunk_rows = c.execute(
                "SELECT doc_id, text, vec FROM document_chunks WHERE user_id IS ?",
                (user_id,),
            ).fetchall()
        best: dict[str, tuple[float, str]] = {}
        for doc_id, text, vec_blob in chunk_rows:
            v = np.frombuffer(vec_blob, dtype=np.float32)
            if v.shape[0] != EMBED_DIM:
                continue
            sim = float(np.dot(q, v))
            if doc_id not in best or sim > best[doc_id][0]:
                best[doc_id] = (sim, text)
        for doc_id, (sim, text) in best.items():
            if sim < 0.35:   # ignore weak semantic noise
                continue
            h = hits.get(doc_id) or _Hit(doc_id=doc_id)
            h.semantic_score = sim
            if not h.snippet:
                h.snippet = text[:240]
            hits[doc_id] = h

    if not hits:
        return []

    ranked = sorted(hits.values(), key=lambda h: h.combined, reverse=True)[:top_k]

    # Attach document metadata for each hit.
    out: list[dict] = []
    with _conn() as c:
        for h in ranked:
            r = c.execute(
                f"SELECT {_COLS} FROM documents WHERE id = ? AND user_id IS ?",
                (h.doc_id, user_id),
            ).fetchone()
            d = _row(r)
            if not d:
                continue
            del d["full_text"]
            d["score"] = round(h.combined, 3)
            d["match_type"] = h.match_type
            d["snippet"] = h.snippet
            out.append(d)
    return out


# --- translation ----------------------------------------------------------

_TRANSLATE_CHUNK = 1800   # Google Translate handles ~5k; stay well under.


def translate_text(text: str, *, target: str) -> str:
    """Translate transcribed text to `target` ('en' or 'hi'), free + offline-LLM.

    Source language is auto-detected (a doc may be Hindi, English, or mixed).
    Uses Google Translate with a MyMemory fallback (both free) — no LLM cost,
    per the product's cost policy. Long text is chunked on line boundaries.
    Returns the original text if every provider fails.
    """
    text = (text or "").strip()
    if not text:
        return text
    try:
        from deep_translator import GoogleTranslator
    except Exception:  # noqa: BLE001
        return text

    # Pack lines into <= _TRANSLATE_CHUNK blocks to respect provider limits.
    blocks: list[str] = []
    buf = ""
    for line in text.split("\n"):
        if buf and len(buf) + 1 + len(line) > _TRANSLATE_CHUNK:
            blocks.append(buf)
            buf = line
        else:
            buf = (buf + "\n" + line) if buf else line
    if buf:
        blocks.append(buf)

    out: list[str] = []
    for blk in blocks:
        done = None
        try:
            done = GoogleTranslator(source="auto", target=target).translate(blk)
        except Exception:  # noqa: BLE001
            done = None
        if not done:
            try:
                from deep_translator import MyMemoryTranslator
                tgt = "hi-IN" if target == "hi" else "en-GB"
                done = MyMemoryTranslator(source="auto", target=tgt).translate(blk)
            except Exception:  # noqa: BLE001
                done = None
        out.append(done or blk)
    return "\n".join(out)
