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

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional, Any

from headnote.config import KANOON_CACHE_PATH
from headnote.retrieval.fact_extractor import extract_facts, score_overlap


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
    facts: dict[str, Any] = field(default_factory=dict)
    fact_score: float = 0.0
    fact_breakdown: dict[str, float] = field(default_factory=dict)

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


def _row_to_judgment(
    row: tuple,
    *,
    fact_score: float = 0.0,
    fact_breakdown: Optional[dict[str, float]] = None,
) -> HFJudgment:
    """Materialise a SQL row into HFJudgment.

    Row layout MUST match _SELECT_COLS order. The optional facts_json
    column (index 10) is parsed into a dict; missing/malformed values
    yield an empty dict.
    """
    facts: dict[str, Any] = {}
    if len(row) >= 11 and row[10]:
        try:
            facts = json.loads(row[10]) or {}
        except (json.JSONDecodeError, TypeError):
            facts = {}

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
        facts=facts,
        fact_score=fact_score,
        fact_breakdown=fact_breakdown or {},
    )


_SELECT_COLS = (
    "doc_id, source, court, title, text, summary, "
    "label, district, language, word_count, facts_json"
)


# ----------------------------------------------------------------- public API

def corpus_stats(db_path: Path | str = KANOON_CACHE_PATH) -> dict:
    """Lightweight stats for /api/health and the admin dashboard.

    Returns total rows, per-source counts, fact backfill progress, and DB
    size. Cheap (single aggregate query) so safe to call on every health-
    check.
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
            # Backfill progress: how many rows have facts_json populated.
            # Wrap in try because facts_json column may not yet exist on
            # very old DBs that haven't been migrated.
            try:
                facts_populated = c.execute(
                    "SELECT COUNT(*) FROM hf_judgments WHERE facts_json IS NOT NULL AND facts_json != ''"
                ).fetchone()[0]
            except sqlite3.OperationalError:
                facts_populated = None
    except sqlite3.OperationalError:
        # Table doesn't exist yet (harvest not run)
        return {"total": 0, "by_source": [], "configured": False, "facts_populated": 0}

    return {
        "total": total,
        "by_source": [
            {"source": s, "language": lang, "count": n}
            for s, lang, n in by_source
        ],
        "configured": total > 0,
        "facts_populated": facts_populated,
        "facts_pct": (
            round(100.0 * facts_populated / total, 1)
            if facts_populated is not None and total else 0
        ),
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
    situation: Optional[str] = None,
    language: str = "en",
    source_filter: Optional[list[str]] = None,
    label_filter: Optional[list[str]] = None,
    district_filter: Optional[str] = None,
    limit: int = 20,
    candidate_pool: int = 200,
    db_path: Path | str = KANOON_CACHE_PATH,
) -> list[HFJudgment]:
    """Fact-aware search over the HF corpus.

    Two-stage pipeline:
      1. **Candidate pool** — SQLite LIKE-match on query terms pulls a
         wide pool (default 200) of remotely relevant judgments. This is
         what the old search returned — fast, recall-oriented, no
         precision.
      2. **Fact rescore** — for each candidate, parse its pre-extracted
         `facts_json` and score the overlap with the facts extracted from
         `situation`. Cases that share statute / stage / minor-victim /
         outcome rank far above bare keyword hits.

    The fact rescore is where the quality comes from. A POCSO query
    against a corpus full of 'POCSO' keyword hits returns the cases that
    ALSO share fact-pattern dimensions (minor victim, consent doctrine,
    bail stage), not just any case that mentions POCSO once.

    Backward compatibility
    ----------------------
    Existing callers passing only `query_terms` still work — they get the
    same keyword-match ranking they had before. To unlock fact-vector
    scoring, pass `situation` (the raw query text).

    Parameters
    ----------
    query_terms : list[str]
        Distilled tokens from the situation, used for SQLite LIKE filtering.
        Same input you'd give the curated-corpus prefilter.
    situation : str | None
        The raw lawyer query. When provided, we extract facts from it and
        rescore candidates by fact overlap. Big quality jump.
    language : str
        'en' for CJPE/SUMM, 'hi' for BAIL.
    source_filter, label_filter, district_filter
        Same semantics as before.
    limit : int
        Max rows in the final ranked output.
    candidate_pool : int
        How many cases to pull from SQL before fact rescoring. 200 is a
        good default — wide enough that the fact rescorer has something
        to discriminate from, narrow enough that rescoring 200 dicts
        stays sub-50 ms.
    """
    # --- Stage 1: candidate pool via keyword LIKE ---------------------------

    if not query_terms:
        return []

    # Cap query terms — beyond ~6 the LIKE explosion costs more than the
    # extra recall is worth.
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

    or_clauses = []
    score_clauses = []
    for term in terms:
        wildcard = f"%{term}%"
        or_clauses.append("(text LIKE ? OR title LIKE ?)")
        params.extend([wildcard, wildcard])
        score_clauses.append("(CASE WHEN text LIKE ? OR title LIKE ? THEN 1 ELSE 0 END)")

    where_parts.append("(" + " OR ".join(or_clauses) + ")")

    score_sql = " + ".join(score_clauses) if score_clauses else "0"

    score_params: list = []
    for term in terms:
        wildcard = f"%{term}%"
        score_params.extend([wildcard, wildcard])

    # Pull candidate_pool rows, not just `limit`. Stage 2 rescore picks
    # the top `limit` from this wider pool.
    sql = f"""
        SELECT {_SELECT_COLS},
               ({score_sql}) AS match_score
        FROM hf_judgments
        WHERE {' AND '.join(where_parts)}
        ORDER BY match_score DESC, word_count DESC
        LIMIT ?
    """
    full_params = score_params + params + [candidate_pool]

    try:
        with _conn(db_path) as c:
            rows = c.execute(sql, full_params).fetchall()
    except sqlite3.OperationalError:
        # Table missing — harvest not run yet
        return []

    if not rows:
        return []

    # --- Stage 2: fact-vector rescore ---------------------------------------

    # If no situation provided, just return keyword-ranked results (legacy mode).
    if not situation or not situation.strip():
        return [_row_to_judgment(row[:11]) for row in rows[:limit]]

    query_facts = extract_facts(situation)

    # If the extractor pulled nothing usable from the query, fall back to
    # keyword ranking — better to return rough matches than nothing.
    if not query_facts:
        return [_row_to_judgment(row[:11]) for row in rows[:limit]]

    # Rescore every candidate. Keyword keyword-rank is a soft tiebreaker
    # so cases with zero fact overlap but heavy keyword presence still
    # have an ordering (and a chance to surface if the fact scorer found
    # nothing).
    scored: list[tuple[float, dict[str, float], int, tuple]] = []
    for row in rows:
        case_facts = {}
        if len(row) >= 11 and row[10]:
            try:
                case_facts = json.loads(row[10]) or {}
            except (json.JSONDecodeError, TypeError):
                case_facts = {}

        fact_score, breakdown = score_overlap(query_facts, case_facts)
        keyword_score = int(row[-1]) if row[-1] is not None else 0
        # Use keyword_score as ~10% tiebreaker (small constant so it can't
        # outrank a real fact match). Word count gives a final stable
        # ordering for cases that tie on both signals.
        composite = fact_score + 0.1 * keyword_score
        scored.append((composite, breakdown, keyword_score, row))

    # Sort: composite DESC, then word_count DESC
    scored.sort(key=lambda x: (-x[0], -x[3][9]))

    out: list[HFJudgment] = []
    for composite, breakdown, kw_score, row in scored[:limit]:
        out.append(
            _row_to_judgment(
                row[:11],
                fact_score=round(composite, 2),
                fact_breakdown=breakdown,
            )
        )
    return out


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
