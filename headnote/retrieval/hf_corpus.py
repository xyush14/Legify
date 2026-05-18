"""
Retrieval over the locally-stored HuggingFace IL-TUR corpus.

The `hf_judgments` SQLite table is populated by scripts/harvest_hf_corpus.py
(typically once per Railway redeploy or on a weekly cron). This module
provides the read-side: keyword search + by-id lookup that the existing
retrieval pipeline can call alongside curated + IK candidates.

Why a separate module
---------------------
The IK retrieval path (headnote.kanoon.retrieval) is built around the IK
API's live + cached search semantics. The HF corpus is a static local
table — different access pattern (no rate limit, no cost, larger N).
Keeping them apart means we don't entangle "pay-per-call IK budget" logic
with "free local search" logic.

Performance note
----------------
At ~50K rows with LIKE on TEXT fields, SQLite scan is fast enough for
beta (< 200 ms per query). When the corpus grows past ~100K judgments,
switch to FTS5 — see _ENABLE_FTS comment at bottom of file.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from headnote.config import KANOON_CACHE_PATH


# ----------------------------------------------------------------- DTO

@dataclass(frozen=True)
class HFJudgment:
    """One row from the hf_judgments table, materialised."""
    doc_id: str            # "hf:cjpe:115651329"
    source: str            # "cjpe" / "summ" / "bail"
    court: Optional[str]
    title: Optional[str]
    text: str
    summary: Optional[str]
    label: Optional[str]
    district: Optional[str]
    language: str          # "en" | "hi"
    word_count: int

    @property
    def preview(self) -> str:
        """First ~300 chars of text, for UI snippets."""
        if not self.text:
            return ""
        snippet = self.text[:300].rsplit(" ", 1)[0]
        return snippet + ("…" if len(self.text) > 300 else "")


# ----------------------------------------------------------------- internals

@contextmanager
def _conn(db_path: Path | str = KANOON_CACHE_PATH) -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(db_path, timeout=10)
    try:
        yield c
    finally:
        c.close()


def _row_to_judgment(row: tuple) -> HFJudgment:
    return HFJudgment(
        doc_id=row[0],
        source=row[1],
        court=row[2],
        title=row[3],
        text=row[4],
        summary=row[5],
        label=row[6],
        district=row[7],
        language=row[8],
        word_count=row[9],
    )


_SELECT_COLS = (
    "doc_id, source, court, title, text, summary, "
    "label, district, language, word_count"
)


# ----------------------------------------------------------------- public API

def corpus_stats(db_path: Path | str = KANOON_CACHE_PATH) -> dict:
    """Lightweight stats for /api/health and the admin dashboard.

    Returns total rows, per-source counts, and DB size. Cheap (single
    aggregate query) so safe to call on every health-check.
    """
    try:
        with _conn(db_path) as c:
            total = c.execute("SELECT COUNT(*) FROM hf_judgments").fetchone()[0]
            by_source = c.execute("""
                SELECT source, language, COUNT(*)
                FROM hf_judgments
                GROUP BY source, language
                ORDER BY source, language
            """).fetchall()
    except sqlite3.OperationalError:
        # Table doesn't exist yet (harvest not run)
        return {"total": 0, "by_source": [], "configured": False}

    return {
        "total": total,
        "by_source": [
            {"source": s, "language": lang, "count": n}
            for s, lang, n in by_source
        ],
        "configured": total > 0,
    }


def get_by_id(
    doc_id: str,
    db_path: Path | str = KANOON_CACHE_PATH,
) -> Optional[HFJudgment]:
    """Fetch one judgment by its `hf:<source>:<id>` key."""
    with _conn(db_path) as c:
        row = c.execute(
            f"SELECT {_SELECT_COLS} FROM hf_judgments WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
    return _row_to_judgment(row) if row else None


def search(
    query_terms: list[str],
    *,
    language: str = "en",
    source_filter: Optional[list[str]] = None,
    label_filter: Optional[list[str]] = None,
    district_filter: Optional[str] = None,
    limit: int = 20,
    db_path: Path | str = KANOON_CACHE_PATH,
) -> list[HFJudgment]:
    """Keyword search over the HF corpus.

    Multi-term OR over title + text. Each term contributes one LIKE per
    indexed text column; SQLite picks an index where it can. Results are
    sorted by a simple match-count heuristic: rows that contain more of
    the query terms come first, ties broken by word_count desc (longer
    judgment ≈ more material to reason about).

    Parameters
    ----------
    query_terms : list[str]
        Already-distilled tokens from the situation. Pass the same output
        your existing prefilter uses — this function does NOT do query
        understanding (statute extraction, stopwords) on its own.
    language : str
        'en' for CJPE/SUMM (English SC + HC), 'hi' for BAIL (Hindi
        district court). Mixing in one query rarely helps so we require
        an explicit choice.
    source_filter : list[str] | None
        Restrict to specific IL-TUR subsets, e.g. ['cjpe', 'summ'] to
        skip district-court bail apps.
    label_filter : list[str] | None
        e.g. ['granted', 'accepted'] to pull only successful outcomes —
        useful when the lawyer is searching for favourable precedents.
    district_filter : str | None
        BAIL only. Match a single district (case-insensitive contains).
    limit : int
        Max rows returned. Default 20 is intentionally generous — the
        Sonnet reranker downstream will pick the best 3-5.

    Returns
    -------
    list[HFJudgment]
        Materialised rows, ranked by term-match heuristic. Empty list if
        no terms, table missing, or no matches.
    """
    if not query_terms:
        return []

    # Cap query terms — beyond ~6 the LIKE explosion costs more than the
    # extra recall is worth. Already-prefiltered terms are sorted by
    # importance, so taking the first N is fine.
    terms = [t.strip() for t in query_terms if t and t.strip()][:6]
    if not terms:
        return []

    where_parts = ["language = ?"]
    params: list = [language]

    if source_filter:
        placeholders = ",".join("?" * len(source_filter))
        where_parts.append(f"source IN ({placeholders})")
        params.extend(source_filter)

    if label_filter:
        placeholders = ",".join("?" * len(label_filter))
        where_parts.append(f"label IN ({placeholders})")
        params.extend(label_filter)

    if district_filter:
        where_parts.append("LOWER(district) LIKE ?")
        params.append(f"%{district_filter.lower()}%")

    # OR over (text LIKE term OR title LIKE term) for each term.
    # We also score: SUM of CASE-WHEN(LIKE) — gives us a match-count
    # ranking without needing FTS5.
    or_clauses = []
    score_clauses = []
    for term in terms:
        wildcard = f"%{term}%"
        or_clauses.append("(text LIKE ? OR title LIKE ?)")
        params.extend([wildcard, wildcard])
        score_clauses.append("(CASE WHEN text LIKE ? OR title LIKE ? THEN 1 ELSE 0 END)")

    where_parts.append("(" + " OR ".join(or_clauses) + ")")

    score_sql = " + ".join(score_clauses) if score_clauses else "0"

    # Score params come FIRST because SQLite binds parameters left-to-right
    # across the full statement, and the score expression appears in the
    # SELECT clause which is parsed before the WHERE clause.
    score_params: list = []
    for term in terms:
        wildcard = f"%{term}%"
        score_params.extend([wildcard, wildcard])

    sql = f"""
        SELECT {_SELECT_COLS},
               ({score_sql}) AS match_score
        FROM hf_judgments
        WHERE {' AND '.join(where_parts)}
        ORDER BY match_score DESC, word_count DESC
        LIMIT ?
    """
    full_params = score_params + params + [limit]

    try:
        with _conn(db_path) as c:
            rows = c.execute(sql, full_params).fetchall()
    except sqlite3.OperationalError:
        # Table missing — harvest not run yet
        return []

    # Drop the match_score column when materialising
    return [_row_to_judgment(row[:10]) for row in rows]


# _ENABLE_FTS:
# When the corpus crosses ~100K rows (BAIL imported), the LIKE-scan
# starts taking > 1 sec on cold cache. Migration to FTS5:
#
#   CREATE VIRTUAL TABLE hf_judgments_fts USING fts5(
#       title, text, summary, content='hf_judgments', content_rowid='rowid'
#   );
#   INSERT INTO hf_judgments_fts(rowid, title, text, summary)
#     SELECT rowid, title, text, summary FROM hf_judgments;
#
# Then replace LIKE with MATCH '"term1" OR "term2"' — same shape, 10×
# faster on large tables. Hindi tokenization in FTS5 needs the
# `unicode61` tokenizer (default) plus `tokenchars` for Devanagari range.
