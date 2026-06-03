"""Read-side of the official Supreme Court open-data corpus.

Two jobs:
  1. Metadata lookup / search over the `sc_judgments` table (court-accepted
     citations + parties + judges + date), to power browse and the case-viewer
     header.
  2. Serve the ACTUAL official judgment PDF on demand.

How PDF serving works (the important bit)
-----------------------------------------
The judgments live as PDFs bundled into one ``english.tar`` per year on the
public AWS Open Data bucket (200–400 MB/tar, ~52 GB total). We do NOT download
or store those tars in production. Instead:

  - ``scripts/ingest_opendata_sc.py`` walks each tar ONCE and records, for every
    PDF, its byte ``offset`` and ``size`` inside the tar (table
    ``sc_tar_offsets``). That index is tiny (~2 ints per judgment).
  - To serve a judgment we issue a single HTTP **Range** request for exactly
    ``[offset, offset+size-1]`` of the tar. Tar stores file data uncompressed
    and contiguously, so those bytes ARE the PDF, byte-for-byte.
  - We cache only the PDFs users actually open (LRU, capped) — so disk stays
    tiny on Render even though the full corpus is 52 GB.

If a judgment's year hasn't been offset-indexed yet (rare once the overnight
build finishes), we fall back to a streaming tar-walk that finds just that one
file, serves it, and records the offset so the next hit is instant.

Dependencies: stdlib + ``requests`` only. No pyarrow, no boto3. (pyarrow is a
harvest-only dependency used by the ingestion script, not in production.)
"""

from __future__ import annotations

import io
import logging
import math
import os
import re
import sqlite3
import tarfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterator, Optional

import requests

from headnote import config


log = logging.getLogger(__name__)

# Shared HTTP session (connection pooling) for Range fetches.
_SESSION = requests.Session()
_HTTP_TIMEOUT = 60

# doc_id form: "sc:<path>"  e.g.  "sc:2024_10_108_125"
_DOC_PREFIX = "sc:"
# path is registry-controlled and only ever digits / underscores / hyphens —
# validate so it can never be used for traversal or to craft an odd URL.
_SAFE_PATH = re.compile(r"^[0-9A-Za-z_\-]{1,128}$")


# ----------------------------------------------------------------- DB access

@contextmanager
def _conn(db_path: Path | str = None) -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(str(db_path or config.JUDGMENTS_DB), timeout=15)
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


def _table_exists(c: sqlite3.Connection, name: str) -> bool:
    return c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


# ----------------------------------------------------------------- metadata

@dataclass(frozen=True)
class SCJudgment:
    doc_id: str           # "sc:2024_10_108_125"
    path: str             # "2024_10_108_125"
    year: int
    title: Optional[str]
    petitioner: Optional[str]
    respondent: Optional[str]
    neutral_citation: Optional[str]   # "2024INSC735"
    scr_citation: Optional[str]       # "[2024] 10 S.C.R. 108"
    cnr: Optional[str]
    judge: Optional[str]
    author_judge: Optional[str]
    decision_date: Optional[str]
    disposal_nature: Optional[str]
    court: str = "Supreme Court of India"

    @property
    def best_citation(self) -> Optional[str]:
        # Neutral citation is the court-accepted anchor; SCR is the reporter.
        if self.neutral_citation and self.scr_citation:
            return f"{self.neutral_citation}  ·  {self.scr_citation}"
        return self.neutral_citation or self.scr_citation


def _row_to_judgment(r: sqlite3.Row) -> SCJudgment:
    return SCJudgment(
        doc_id=_DOC_PREFIX + r["path"],
        path=r["path"],
        year=r["year"],
        title=r["title"],
        petitioner=r["petitioner"],
        respondent=r["respondent"],
        neutral_citation=r["neutral_citation"],
        scr_citation=r["scr_citation"],
        cnr=r["cnr"],
        judge=r["judge"],
        author_judge=r["author_judge"],
        decision_date=r["decision_date"],
        disposal_nature=r["disposal_nature"],
    )


def _path_from_doc_id(doc_id: str) -> Optional[str]:
    if not doc_id or not doc_id.startswith(_DOC_PREFIX):
        return None
    path = doc_id[len(_DOC_PREFIX):]
    return path if _SAFE_PATH.match(path) else None


def get_metadata(doc_id: str) -> Optional[SCJudgment]:
    """Look up one judgment's metadata by doc_id ("sc:<path>")."""
    path = _path_from_doc_id(doc_id)
    if not path:
        return None
    try:
        with _conn() as c:
            if not _table_exists(c, "sc_judgments"):
                return None
            r = c.execute(
                "SELECT * FROM sc_judgments WHERE path = ?", (path,)
            ).fetchone()
        return _row_to_judgment(r) if r else None
    except sqlite3.OperationalError:
        return None


# Boilerplate caption tokens that carry no discriminating signal — dropped from
# the party-name token match so "STATE", "UNION", "OF" etc. don't force matches.
_SEARCH_STOP = {
    "THE", "AND", "ORS", "ANR", "ETC", "VS", "VERSUS", "STATE", "UNION",
    "INDIA", "GOVT", "GOVERNMENT", "REP", "THROUGH", "OTHERS", "ANOTHER",
}


def search(query: str, limit: int = 25) -> list[SCJudgment]:
    """Keyword search over parties + citations. Good enough for browse; the
    LLM retrieval pipeline can wrap this later.

    Matching is whitespace- and punctuation-insensitive so a lawyer's
    full-name search resolves against the terse, OCR-noisy SCR captions the
    corpus actually stores. e.g. the corpus holds "SHARAD BIRDHI CHAND SARDA"
    (note the space) — a search for "Sharad Birdhichand Sarda" still matches
    because we compare the space-collapsed forms and require every significant
    name token (collapsed) to appear in the caption. Citation forms
    (neutral / SCR / spaced neutral case_id) match independently."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        with _conn() as c:
            if not _table_exists(c, "sc_judgments"):
                return []
            compact = re.sub(r"\s+", "", q).upper()
            # Significant name tokens (collapsed, upper-cased), boilerplate dropped.
            tokens = [
                t.upper() for t in re.findall(r"[A-Za-z0-9]+", q)
                if len(t) >= 3 and t.upper() not in _SEARCH_STOP
            ]
            clauses: list[str] = []
            params: list = []
            # Citation matches (always tried, independent of name tokens):
            #   - SCR citation substring ("[2014] 8 S.C.R. 128")
            #   - compact neutral citation ("2014INSC463", user may type spaced)
            #   - spaced neutral stored in case_id ("2014 INSC 463")
            clauses.append("scr_citation LIKE ?")
            params.append(f"%{q}%")
            clauses.append("REPLACE(UPPER(neutral_citation),' ','') LIKE ?")
            params.append(f"%{compact}%")
            clauses.append("REPLACE(UPPER(COALESCE(case_id,'')),' ','') LIKE ?")
            params.append(f"%{compact}%")
            if tokens:
                # Name match: every token must appear in the space-collapsed
                # caption (title + petitioner + respondent). The collapse makes
                # "BIRDHI CHAND" match "Birdhichand"; the AND keeps precision.
                cap = (
                    "REPLACE(UPPER(COALESCE(title,'')||' '||"
                    "COALESCE(petitioner,'')||' '||COALESCE(respondent,'')),' ','')"
                )
                token_and = " AND ".join([f"{cap} LIKE ?"] * len(tokens))
                clauses.append(f"({token_and})")
                params.extend(f"%{t}%" for t in tokens)
            else:
                # No usable name tokens (e.g. a bare citation) — fall back to a
                # raw substring on the caption fields.
                like = f"%{q}%"
                clauses.append("(title LIKE ? OR petitioner LIKE ? OR respondent LIKE ?)")
                params.extend([like, like, like])
            params.append(limit)
            rows = c.execute(
                f"SELECT * FROM sc_judgments WHERE {' OR '.join(clauses)} "
                f"ORDER BY year DESC LIMIT ?",
                params,
            ).fetchall()
        return [_row_to_judgment(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def corpus_stats() -> dict:
    """Counts for /api/health and the admin dashboard."""
    out = {"configured": False, "judgments": 0, "offsets": 0,
           "years_indexed": 0, "year_min": None, "year_max": None,
           "texts": 0, "years_with_text": 0}
    try:
        with _conn() as c:
            if _table_exists(c, "sc_judgments"):
                row = c.execute(
                    "SELECT COUNT(*) n, MIN(year) lo, MAX(year) hi FROM sc_judgments"
                ).fetchone()
                out["judgments"] = row["n"]
                out["year_min"], out["year_max"] = row["lo"], row["hi"]
                out["configured"] = row["n"] > 0
            if _table_exists(c, "sc_tar_offsets"):
                out["offsets"] = c.execute(
                    "SELECT COUNT(*) FROM sc_tar_offsets"
                ).fetchone()[0]
                out["years_indexed"] = c.execute(
                    "SELECT COUNT(DISTINCT year) FROM sc_tar_offsets"
                ).fetchone()[0]
            if _table_exists(c, "sc_text"):
                out["texts"] = c.execute(
                    "SELECT COUNT(*) FROM sc_text"
                ).fetchone()[0]
                out["years_with_text"] = c.execute(
                    "SELECT COUNT(DISTINCT year) FROM sc_text"
                ).fetchone()[0]
    except sqlite3.OperationalError:
        pass
    return out


# ---------------------------------------------------- cross-resolution / match
#
# The research pipeline discovers cases via Indian Kanoon (an aggregator that
# is NOT a court-accepted authority). When such a case is a Supreme Court
# matter, we try to find the SAME judgment in our official open-data corpus and,
# on a match, hand back the court-accepted neutral/SCR citation + the official
# signed PDF. Matching is deterministic where possible (neutral citation, then
# SCR citation) and falls back to a conservative parties+year fuzzy match.

# "2024 INSC 735" / "(2024) INSC 735"  → canonical compact form "2024INSC735"
_NEUTRAL_RX = re.compile(r"((?:19|20)\d{2})\s*INSC\s*(\d+)", re.IGNORECASE)
# SCR forms: "[2024] 10 S.C.R. 108", "(2024) 10 SCR 108", "2024 10 S C R 108"
_SCR_RX = re.compile(
    r"[\[\(]?\s*((?:19|20)\d{2})\s*[\]\)]?\s*,?\s*(\d{1,3})\s*S\.?\s*C\.?\s*R\.?\s*,?\s*(\d{1,4})",
    re.IGNORECASE,
)


def _norm_alnum(s: Optional[str]) -> str:
    return re.sub(r"[^0-9A-Z]", "", (s or "").upper())


def _neutral_key(s: Optional[str]) -> Optional[str]:
    """Canonical neutral-citation key, e.g. '2024INSC735', or None."""
    m = _NEUTRAL_RX.search(s or "")
    return f"{m.group(1)}INSC{m.group(2)}" if m else None


def _scr_key(s: Optional[str]) -> Optional[tuple[int, int, int]]:
    """(year, volume, page) tuple from an SCR citation, or None."""
    m = _SCR_RX.search(s or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _coerce_year(y) -> Optional[int]:
    m = re.search(r"(?:19|20)\d{2}", str(y or ""))
    return int(m.group(0)) if m else None


def _norm_parties(petitioner: Optional[str], respondent: Optional[str],
                  title: Optional[str]) -> str:
    """Normalise a party caption for fuzzy comparison: drop the 'v./vs/versus'
    separator and punctuation, lowercase, collapse whitespace."""
    base = (f"{petitioner or ''} {respondent or ''}").strip() or (title or "")
    base = base.lower()
    base = re.sub(r"\bv(?:s|ersus|\.)?\b", " ", base)   # drop the "vs"
    base = re.sub(r"[^a-z0-9 ]", " ", base)
    return re.sub(r"\s+", " ", base).strip()


# Minimum fuzzy ratio to accept a parties+year match. Set high: attributing the
# WRONG official copy is worse than attaching none, so we only swap in a copy on
# a near-identical caption within the exact same year.
_PARTIES_MATCH_MIN = 0.88


def match_ik_case(
    *,
    citations: Optional[list[str]] = None,
    title: str = "",
    petitioner: str = "",
    respondent: str = "",
    year=None,
    court: str = "",
) -> Optional[SCJudgment]:
    """Find the official Supreme Court judgment in our corpus that corresponds
    to a case discovered elsewhere (e.g. an Indian Kanoon hit).

    Strategy, most-precise first:
      1. Neutral citation (e.g. 2024 INSC 735) — deterministic.
      2. SCR citation (e.g. [2024] 10 S.C.R. 108) — deterministic.
      3. Parties + exact year — conservative fuzzy match (>= 0.88).

    Only Supreme Court matters are considered. Returns the matched
    ``SCJudgment`` (carrying its doc_id / PDF / court-accepted citation) or None.
    Pure-read and exception-safe — never raises into the retrieval hot path.
    """
    if court and "supreme court" not in court.lower():
        return None

    cites = [s for s in (citations or []) if s]
    insc = next((k for k in (_neutral_key(s) for s in cites) if k), None)
    scrk = next((k for k in (_scr_key(s) for s in cites) if k), None)

    # Candidate years to scope the scan (citation year is authoritative).
    years: set[int] = set()
    if insc:
        years.add(int(insc[:4]))
    if scrk:
        years.add(scrk[0])
    yc = _coerce_year(year)
    if yc:
        years.add(yc)
    if not years:
        return None  # no year to scope by → unsafe / unbounded; skip

    try:
        with _conn() as c:
            if not _table_exists(c, "sc_judgments"):
                return None
            placeholders = ",".join("?" * len(years))
            rows = c.execute(
                f"SELECT * FROM sc_judgments WHERE year IN ({placeholders})",
                tuple(sorted(years)),
            ).fetchall()
    except sqlite3.OperationalError:
        return None

    if not rows:
        return None

    # 1) Neutral citation — exact, court-accepted anchor.
    if insc:
        for r in rows:
            if r["neutral_citation"] and _norm_alnum(r["neutral_citation"]) == insc:
                return _row_to_judgment(r)

    # 2) SCR citation — exact (year, volume, page).
    if scrk:
        for r in rows:
            if r["scr_citation"] and _scr_key(r["scr_citation"]) == scrk:
                return _row_to_judgment(r)

    # 3) Parties + year — conservative fuzzy fallback.
    target = _norm_parties(petitioner, respondent, title)
    if len(target) >= 10:
        best, best_sim = None, 0.0
        for r in rows:
            cand = _norm_parties(r["petitioner"], r["respondent"], r["title"])
            if len(cand) < 6:
                continue
            sim = SequenceMatcher(None, target, cand).ratio()
            if sim > best_sim:
                best_sim, best = sim, r
        if best is not None and best_sim >= _PARTIES_MATCH_MIN:
            return _row_to_judgment(best)

    return None


# ----------------------------------------------------------------- tar / S3

def _tar_url(year: int) -> str:
    return f"{config.OPENDATA_SC_BUCKET}/data/tar/year={year}/english/english.tar"


class _HttpRangeFile(io.RawIOBase):
    """A seekable file-like object over an S3 object via HTTP Range requests.
    Only used for the rare fallback tar-walk; the hot path uses direct Range
    GETs and never instantiates this."""

    def __init__(self, url: str):
        self.url = url
        self.pos = 0
        r = _SESSION.head(url, timeout=_HTTP_TIMEOUT)
        r.raise_for_status()
        self.size = int(r.headers["Content-Length"])

    def seekable(self) -> bool:
        return True

    def seek(self, off, whence=0):
        if whence == 0:
            self.pos = off
        elif whence == 1:
            self.pos += off
        elif whence == 2:
            self.pos = self.size + off
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        if n == -1:
            n = self.size - self.pos
        if n <= 0:
            return b""
        end = min(self.pos + n - 1, self.size - 1)
        r = _SESSION.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"},
                         timeout=_HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.content
        self.pos += len(data)
        return data

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def _range_get(url: str, offset: int, size: int) -> bytes:
    """Fetch exactly [offset, offset+size-1]. One small retry on transient
    network failure."""
    headers = {"Range": f"bytes={offset}-{offset + size - 1}"}
    last_exc = None
    for attempt in range(2):
        try:
            r = _SESSION.get(url, headers=headers, timeout=_HTTP_TIMEOUT)
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:  # pragma: no cover
            last_exc = e
            time.sleep(0.5 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


# ----------------------------------------------------------------- offsets

def _lookup_offset(path: str) -> Optional[tuple[int, int, int]]:
    """Return (year, offset, size) for a path, or None if not indexed yet."""
    try:
        with _conn() as c:
            if not _table_exists(c, "sc_tar_offsets"):
                return None
            r = c.execute(
                "SELECT year, offset, size FROM sc_tar_offsets WHERE path = ?",
                (path,),
            ).fetchone()
        return (r["year"], r["offset"], r["size"]) if r else None
    except sqlite3.OperationalError:
        return None


def _store_offset(path: str, year: int, offset: int, size: int,
                  filename: str) -> None:
    """Persist a discovered offset so the next request is an instant Range GET.
    Best-effort: a write failure (e.g. read-only FS) must not break serving."""
    try:
        with _conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS sc_tar_offsets (
                       path TEXT PRIMARY KEY, year INTEGER NOT NULL,
                       filename TEXT, offset INTEGER NOT NULL,
                       size INTEGER NOT NULL)"""
            )
            c.execute(
                "INSERT OR REPLACE INTO sc_tar_offsets"
                " (path, year, filename, offset, size) VALUES (?,?,?,?,?)",
                (path, year, filename, offset, size),
            )
            c.commit()
    except sqlite3.OperationalError as e:  # pragma: no cover
        log.warning("could not persist offset for %s: %s", path, e)


def _year_for(path: str) -> Optional[int]:
    """Year from sc_judgments, falling back to the path's leading YYYY."""
    j = get_metadata(_DOC_PREFIX + path)
    if j:
        return j.year
    m = re.match(r"^(\d{4})_", path)
    return int(m.group(1)) if m else None


def _walk_for_offset(path: str, year: int) -> Optional[tuple[int, int, str]]:
    """Fallback: stream the year tar's headers until we hit ``<path>_EN.pdf``;
    return (offset, size, filename). Records offsets seen along the way so the
    index progressively fills. Slow (rare) path."""
    target = f"{path}_EN.pdf"
    url = _tar_url(year)
    try:
        f = _HttpRangeFile(url)
        tf = tarfile.open(fileobj=f, mode="r:")
    except Exception as e:
        log.warning("fallback walk: cannot open tar for %s: %s", year, e)
        return None
    found = None
    seen: list[tuple[str, int, int, str]] = []
    for m in tf:
        if not (m.isfile() and m.name.lower().endswith(".pdf")):
            continue
        stem = m.name[:-len("_EN.pdf")] if m.name.endswith("_EN.pdf") else m.name[:-4]
        seen.append((stem, m.offset_data, m.size, m.name))
        if m.name == target or stem == path:
            found = (m.offset_data, m.size, m.name)
            break
    # Persist everything we walked past (cheap, makes the next misses instant).
    for stem, off, sz, fname in seen:
        _store_offset(stem, year, off, sz, fname)
    return found


# ----------------------------------------------------------------- PDF cache

_CACHE_LOCK = threading.Lock()


def _cache_dir() -> Path:
    d = Path(config.JUDGMENTS_PDF_CACHE)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(path: str) -> Path:
    safe = re.sub(r"[^0-9A-Za-z_\-]", "_", path)
    return _cache_dir() / f"{safe}_EN.pdf"


def _evict_if_needed() -> None:
    """LRU eviction by mtime when the cache dir exceeds the configured cap."""
    cap_bytes = config.JUDGMENTS_PDF_CACHE_MB * 1024 * 1024
    try:
        files = [(p, p.stat()) for p in _cache_dir().glob("*.pdf")]
    except OSError:
        return
    total = sum(st.st_size for _, st in files)
    if total <= cap_bytes:
        return
    # Delete oldest-accessed first until we're under 90% of the cap.
    files.sort(key=lambda t: t[1].st_mtime)
    target = int(cap_bytes * 0.9)
    for p, st in files:
        if total <= target:
            break
        try:
            p.unlink()
            total -= st.st_size
        except OSError:
            pass


# ----------------------------------------------------------------- public: PDF

def resolve_pdf(doc_id: str) -> Optional[tuple[bytes, str]]:
    """Return (pdf_bytes, download_filename) for a judgment, or None.

    Order of operations: LRU cache → stored offset (single Range GET) →
    fallback tar-walk. Result is cached so subsequent reads are local.
    """
    path = _path_from_doc_id(doc_id)
    if not path:
        return None

    download_name = f"{path}_EN.pdf"
    cache_file = _cache_path(path)

    # 1) Cache hit — touch mtime for LRU and return.
    if cache_file.exists():
        try:
            os.utime(cache_file, None)
            data = cache_file.read_bytes()
            if data[:4] == b"%PDF":
                return data, download_name
            cache_file.unlink(missing_ok=True)  # corrupt cache entry
        except OSError:
            pass

    # 2) Stored offset → single Range GET.
    rec = _lookup_offset(path)
    if rec:
        year, offset, size = rec
        data = _range_get(_tar_url(year), offset, size)
        if data[:4] != b"%PDF":
            log.warning("range fetch for %s did not yield a PDF (got %r)",
                        path, data[:8])
            return None
        _write_cache(cache_file, data)
        return data, download_name

    # 3) Fallback: discover the offset by walking the tar, then serve.
    year = _year_for(path)
    if not year:
        return None
    found = _walk_for_offset(path, year)
    if not found:
        return None
    offset, size, fname = found
    data = _range_get(_tar_url(year), offset, size)
    if data[:4] != b"%PDF":
        return None
    _write_cache(cache_file, data)
    return data, fname or download_name


def _write_cache(cache_file: Path, data: bytes) -> None:
    with _CACHE_LOCK:
        try:
            tmp = cache_file.with_suffix(".pdf.tmp")
            tmp.write_bytes(data)
            tmp.replace(cache_file)
            _evict_if_needed()
        except OSError as e:  # pragma: no cover — serving still succeeds
            log.warning("could not cache %s: %s", cache_file.name, e)


# ----------------------------------------------------------------- provenance

def provenance(j: SCJudgment) -> dict:
    """Source/verification card for the case-viewer footer. This is the
    court-accepted-source trust layer: official reportable judgment, neutral
    citation as the anchor, CC-BY-4.0."""
    bits = []
    if j.neutral_citation:
        bits.append(f"Neutral citation <strong>{j.neutral_citation}</strong>")
    if j.scr_citation:
        bits.append(f"reported at <strong>{j.scr_citation}</strong>")
    anchor = "; ".join(bits) if bits else "official reportable judgment"
    return {
        "source_name": "Supreme Court of India — official reportable judgment",
        "source_note": (
            f"The PDF served here is the official judgment copy from the "
            f"Supreme Court of India ({anchor}), distributed via the AWS Open "
            f"Data registry under CC-BY-4.0. Unlike an aggregator copy, the "
            f"neutral citation is the citation a court accepts."
        ),
        "verify_url": None,
        "license": "CC-BY-4.0 · Supreme Court of India / e-SCR",
    }


# ============================================================ full-text search
#
# e-SCR PDFs carry a clean digital text layer (no OCR needed). We extract that
# text once, store it, and index it in an SQLite FTS5 table so the research
# pipeline can discover Supreme Court precedent by FACT PATTERN — making the
# official corpus a first-class discovery source, not just a citation/PDF layer.
# Extraction is incremental (batch script, newest-first) with a lazy on-demand
# fallback for any judgment not yet extracted.

# Strip everything FTS5 might treat as a query operator; we OR plain terms.
_FTS_SANITISE = re.compile(r"[^0-9a-z ]+")
# Numbered-paragraph marker at line start ("12. ") — SC judgments are numbered.
_NUM_PARA_RX = re.compile(r"(?m)^\s*(\d{1,3})\.\s")


def _fts_is_contentful(c: sqlite3.Connection) -> bool:
    """True if an existing ``sc_fts`` is the LEGACY *contentful* shape
    (``fts5(path UNINDEXED, body)``) that stores a second verbatim copy of every
    judgment body. The modern *external-content* shape exposes only a ``text``
    column and keeps no copy (the body lives once in ``sc_text``).

    Lets one code path serve both: dev DBs / a mid-extraction DB are still
    contentful; freshly built / shipped DBs are external-content. Returns False
    if ``sc_fts`` is absent (caller guards on _table_exists first anyway)."""
    try:
        cols = {r[1] for r in c.execute("PRAGMA table_info(sc_fts)").fetchall()}
    except sqlite3.OperationalError:
        return False
    return "body" in cols


def _ensure_text_schema(c: sqlite3.Connection) -> bool:
    """Create the text table + an FTS5 index over it. Returns True if FTS5 is
    available.

    Fresh DBs get the modern *external-content* ``sc_fts`` (no duplicated body)
    plus three triggers that keep the index in lock-step with ``sc_text`` on
    INSERT/DELETE/UPDATE. A pre-existing LEGACY contentful ``sc_fts`` is left
    untouched (its rows are maintained explicitly by ``store_text``) — converting
    it is a one-shot offline job (scripts/build_shippable_corpus.py), never done
    on the serving path."""
    c.execute(
        """CREATE TABLE IF NOT EXISTS sc_text (
               path TEXT PRIMARY KEY, year INTEGER, n_chars INTEGER,
               n_pages INTEGER, extracted_at TEXT, text TEXT)"""
    )
    legacy = _table_exists(c, "sc_fts") and _fts_is_contentful(c)
    try:
        if legacy:
            return True  # keep the legacy contentful index as-is
        c.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS sc_fts USING fts5("
            "text, content='sc_text', content_rowid='rowid', "
            "tokenize='porter unicode61')"
        )
        # Sync triggers. External-content FTS keeps NO copy of the body, so the
        # index must be told about every row change. Explicit DELETE+INSERT in
        # store_text (never INSERT OR REPLACE) means these fire deterministically
        # without depending on PRAGMA recursive_triggers.
        c.execute(
            "CREATE TRIGGER IF NOT EXISTS sc_text_ai AFTER INSERT ON sc_text "
            "BEGIN INSERT INTO sc_fts(rowid, text) VALUES (new.rowid, new.text); "
            "END"
        )
        c.execute(
            "CREATE TRIGGER IF NOT EXISTS sc_text_ad AFTER DELETE ON sc_text "
            "BEGIN INSERT INTO sc_fts(sc_fts, rowid, text) "
            "VALUES('delete', old.rowid, old.text); END"
        )
        c.execute(
            "CREATE TRIGGER IF NOT EXISTS sc_text_au AFTER UPDATE ON sc_text "
            "BEGIN INSERT INTO sc_fts(sc_fts, rowid, text) "
            "VALUES('delete', old.rowid, old.text); "
            "INSERT INTO sc_fts(rowid, text) VALUES (new.rowid, new.text); END"
        )
        return True
    except sqlite3.OperationalError as e:  # FTS5 not compiled in
        log.warning("FTS5 unavailable — full-text search disabled (%s)", e)
        return False


def extract_pdf_text(pdf_bytes: bytes) -> tuple[str, int]:
    """Return (text, n_pages) from a judgment PDF's text layer. Prefers PyMuPDF
    (fitz, a production dependency); falls back to pypdf. No OCR — e-SCR PDFs
    are born-digital. Returns ("", 0) if both extractors fail."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            parts = [pg.get_text("text") for pg in doc]
            return ("\n".join(parts).strip(), doc.page_count)
        finally:
            doc.close()
    except Exception:
        pass
    try:
        import io as _io
        from pypdf import PdfReader
        r = PdfReader(_io.BytesIO(pdf_bytes))
        parts = [(pg.extract_text() or "") for pg in r.pages]
        return ("\n".join(parts).strip(), len(r.pages))
    except Exception as e:  # pragma: no cover
        log.warning("PDF text extraction failed: %s", e)
        return ("", 0)


def store_text(path: str, year: int, text: str, n_pages: int,
               title: Optional[str] = None) -> None:
    """Persist extracted text + FTS index entry for one judgment. Best-effort:
    a write failure (read-only FS) must never break serving."""
    if not text:
        return
    try:
        with _conn() as c:
            has_fts = _ensure_text_schema(c)
            legacy = has_fts and _fts_is_contentful(c)
            # Explicit DELETE+INSERT (never INSERT OR REPLACE): on the modern
            # external-content schema this makes the sync triggers fire
            # deterministically (REPLACE wouldn't fire the delete trigger unless
            # recursive_triggers is on). On the plain table it's equivalent.
            c.execute("DELETE FROM sc_text WHERE path = ?", (path,))
            c.execute(
                "INSERT INTO sc_text "
                "(path, year, n_chars, n_pages, extracted_at, text) "
                "VALUES (?,?,?,?,datetime('now'),?)",
                (path, year, len(text), n_pages, text),
            )
            if legacy:
                # Legacy contentful index has no triggers — maintain it by hand.
                c.execute("DELETE FROM sc_fts WHERE path = ?", (path,))
                c.execute("INSERT INTO sc_fts (path, body) VALUES (?, ?)",
                          (path, text))
            c.commit()
    except sqlite3.OperationalError as e:  # pragma: no cover
        log.warning("could not store text for %s: %s", path, e)


def get_text(doc_id: str) -> Optional[str]:
    """Stored judgment text for a doc_id, or None if not extracted yet."""
    path = _path_from_doc_id(doc_id)
    if not path:
        return None
    try:
        with _conn() as c:
            if not _table_exists(c, "sc_text"):
                return None
            r = c.execute("SELECT text FROM sc_text WHERE path = ?",
                          (path,)).fetchone()
        return r["text"] if r else None
    except sqlite3.OperationalError:
        return None


def ensure_text(doc_id: str) -> Optional[str]:
    """Return judgment text, extracting + caching from the PDF on first use.
    NOTE: triggers a PDF fetch + parse when missing — do NOT call in a tight
    loop on the hot path; the search path reads already-stored text instead."""
    t = get_text(doc_id)
    if t is not None:
        return t
    got = resolve_pdf(doc_id)
    if not got:
        return None
    pdf_bytes, _ = got
    text, n_pages = extract_pdf_text(pdf_bytes)
    if not text:
        return None
    path = _path_from_doc_id(doc_id)
    j = get_metadata(doc_id)
    store_text(path, j.year if j else (_year_for(path) or 0), text, n_pages,
               title=(j.title if j else None))
    return text


def _fts_terms(tokens) -> list[str]:
    """Sanitised, de-duped single-word MATCH terms (≤12) from raw tokens.
    Shared by the MATCH expression and the re-rank scorer so both see the same
    vocabulary."""
    if isinstance(tokens, str):
        tokens = tokens.split()
    terms: list[str] = []
    for t in tokens or []:
        t = _FTS_SANITISE.sub("", (t or "").lower()).strip()
        if len(t) >= 3 and t not in terms:
            terms.append(t)
        if len(terms) >= 12:
            break
    return terms


def _fts_query(tokens) -> str:
    """Build a safe FTS5 MATCH expression: OR of quoted single terms."""
    return " OR ".join(f'"{t}"' for t in _fts_terms(tokens))


# Length-agnostic re-rank knobs. FTS5's bm25() uses b=0.75 (aggressive length
# normalisation): it divides by document length, so the most THOROUGH judgment
# on a doctrine — invariably the longest — is pushed far down. The controlling
# precedent on circumstantial evidence (Sharad Birdhichand Sarda, 1985) sinks to
# bm25 rank ~117 behind shorter, shallower hits. We cannot retune FTS5's bm25(),
# so we take its top-_RERANK_CAP candidates and re-score them with BM25 b=0 (NO
# length penalty) + term saturation (k1). This is GENERAL — no per-topic tuning —
# and floats the comprehensive controlling authority to #1 for any fact pattern.
_RERANK_CAP = 400          # first-pass bm25 pool; ≥ worst-case landmark bm25 rank
_BM25_K1 = 1.2             # term saturation; b is pinned to 0 on purpose


def _idf_for_terms(c: sqlite3.Connection, terms: list[str]) -> dict[str, float]:
    """Robertson–Spärck-Jones idf per term from real document frequency, so a
    distinctive term ('circumstantial') outweighs a ubiquitous one ('evidence',
    'accused'). One indexed COUNT(MATCH) per term — cheap."""
    try:
        n = c.execute("SELECT COUNT(*) FROM sc_text").fetchone()[0] or 1
    except sqlite3.OperationalError:
        n = 1
    idf: dict[str, float] = {}
    for t in terms:
        try:
            df = c.execute("SELECT COUNT(*) FROM sc_fts WHERE sc_fts MATCH ?",
                           (f'"{t}"',)).fetchone()[0] or 1
        except sqlite3.OperationalError:
            df = 1
        idf[t] = math.log(1 + (n - df + 0.5) / (df + 0.5))
    return idf


def _length_agnostic_score(text: str, idf: dict[str, float],
                           rx: "re.Pattern[str]", k1: float = _BM25_K1) -> float:
    """BM25 with b=0 (no length normalisation). Counts query terms in one combined
    regex pass, saturates each via k1 so one stuffed term can't dominate, and
    weights by idf so distinctive doctrinal terms drive the ranking."""
    tf: dict[str, int] = {}
    for m in rx.finditer(text.lower()):
        g = m.group(1)
        tf[g] = tf.get(g, 0) + 1
    s = 0.0
    for t, f in tf.items():
        s += idf.get(t, 0.0) * (f * (k1 + 1)) / (f + k1)
    return s


def search_fulltext(tokens, limit: int = 12) -> list[SCJudgment]:
    """Full-text search over extracted judgment bodies (FTS5/BM25). Returns
    SCJudgment metadata for the best matches, ranked by relevance. Empty list
    if nothing is extracted yet or FTS5 is unavailable — so callers degrade
    gracefully before/while the corpus is being indexed."""
    terms = _fts_terms(tokens)
    if not terms:
        return []
    q = " OR ".join(f'"{t}"' for t in terms)
    cap = max(_RERANK_CAP, limit * 30)
    try:
        with _conn() as c:
            if not _table_exists(c, "sc_fts"):
                return []
            # First pass: FTS5/BM25 narrows the corpus to a candidate POOL (its
            # length-normalisation buries long landmarks, so we over-fetch and
            # re-rank below rather than trust this order). Carry the body so the
            # re-rank needn't re-read it.
            if _fts_is_contentful(c):
                # Legacy: path + body live on the FTS table itself.
                cand = c.execute(
                    "SELECT path AS path, body AS body FROM sc_fts "
                    "WHERE sc_fts MATCH ? ORDER BY bm25(sc_fts) LIMIT ?",
                    (q, cap),
                ).fetchall()
            else:
                # External-content: FTS rowid maps 1:1 to sc_text.rowid.
                cand = c.execute(
                    "SELECT t.path AS path, t.text AS body FROM sc_fts "
                    "JOIN sc_text t ON t.rowid = sc_fts.rowid "
                    "WHERE sc_fts MATCH ? ORDER BY bm25(sc_fts) LIMIT ?",
                    (q, cap),
                ).fetchall()
            if not cand:
                return []
            # Second pass: length-agnostic re-rank (BM25 b=0) floats the most
            # thorough controlling precedent up. Degrade to bm25 order if scoring
            # ever throws — never strand the caller with nothing.
            top_paths = [r["path"] for r in cand][:limit]
            try:
                idf = _idf_for_terms(c, terms)
                rx = re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b")
                scored = sorted(
                    ((r["path"], _length_agnostic_score(r["body"] or "", idf, rx))
                     for r in cand),
                    key=lambda x: x[1], reverse=True,
                )
                top_paths = [p for p, _ in scored[:limit]]
            except Exception:  # noqa: BLE001 — re-rank is best-effort over bm25
                log.exception("[sc-fts] length-agnostic re-rank failed; "
                              "falling back to bm25 order")
            out: list[SCJudgment] = []
            for p in top_paths:
                jr = c.execute("SELECT * FROM sc_judgments WHERE path = ?",
                               (p,)).fetchone()
                if jr:
                    out.append(_row_to_judgment(jr))
        return out
    except sqlite3.OperationalError:
        return []


def _split_paragraphs(text: str) -> list[dict]:
    """Split judgment text into renderable/citable paragraphs [{id,num,text}].
    Handles both blank-line-separated and single-newline (numbered) layouts."""
    text = re.sub(r"\r", "", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    chunks = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(chunks) < 5:
        # PDF used single newlines — segment on numbered-paragraph markers.
        parts = _NUM_PARA_RX.split(text)
        rebuilt: list[str] = []
        if parts:
            if parts[0].strip():
                rebuilt.append(parts[0].strip())
            for i in range(1, len(parts) - 1, 2):
                rebuilt.append((parts[i] + ". " + parts[i + 1]).strip())
        chunks = [c for c in rebuilt if c] or chunks
    out: list[dict] = []
    for i, ch in enumerate(chunks):
        if not (40 <= len(ch) <= 6000):
            continue
        m = re.match(r"^\s*(\d{1,3})[\.\)]", ch)
        out.append({"id": f"scp_{i}", "num": int(m.group(1)) if m else i + 1,
                    "text": ch})
    return out


def paragraphs_for(doc_id: str, *, lazy: bool = False) -> list[dict]:
    """Paragraphs for a judgment from its extracted text. Reads stored text
    only (fast) unless lazy=True, which extracts on demand."""
    text = ensure_text(doc_id) if lazy else get_text(doc_id)
    return _split_paragraphs(text) if text else []


def text_stats() -> dict:
    """Extraction coverage for /stats and the corpus dashboard."""
    out = {"texts": 0, "years_with_text": 0}
    try:
        with _conn() as c:
            if _table_exists(c, "sc_text"):
                out["texts"] = c.execute(
                    "SELECT COUNT(*) FROM sc_text").fetchone()[0]
                out["years_with_text"] = c.execute(
                    "SELECT COUNT(DISTINCT year) FROM sc_text").fetchone()[0]
    except sqlite3.OperationalError:
        pass
    return out
