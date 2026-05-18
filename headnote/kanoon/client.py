"""
Indian Kanoon API client with on-disk cache and rate limiting.

Wraps three endpoints:
  - POST /search/?formInput=<q>&pagenum=<n>  -> case list (paginated, 10/page)
  - POST /doc/{tid}/                          -> full judgment HTML + metadata
  - POST /docmeta/{tid}/                      -> lightweight metadata only

Cache: a single SQLite file (kanoon_cache.sqlite, gitignored) keyed by query
or tid. Repeated lookups are free. Cache entries have no TTL by default
(judgments don't change), but search results can be invalidated via
`max_age_days` on `search()`.

Rate limit: configurable sleep between live API hits (default 0.6s). Cache
hits bypass it. IK API meters per request, so the cache is also the cost
control.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote_plus

import requests

# Load .env if present (no-op if python-dotenv not installed)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# --------------------------------------------------------------------- config

API_BASE = "https://api.indiankanoon.org"
# Cache path comes from central config so it can be overridden via env var
# (KANOON_CACHE_PATH) for production deploys with persistent disks.
try:
    from headnote.config import KANOON_CACHE_PATH as DEFAULT_CACHE_PATH
except ImportError:
    DEFAULT_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "kanoon_cache.sqlite"
DEFAULT_THROTTLE_SECONDS = 0.6
DEFAULT_TIMEOUT_SECONDS = 30

# Indian Kanoon pricing — INR per request. From the user's IK dashboard.
# These drive the cost ledger and daily cap; update if IK changes pricing.
COST_INR = {
    "search":   0.50,
    "doc":      0.20,
    "docmeta":  0.02,
    "original": 0.50,
    "fragment": 0.05,
}

# Default daily spend cap. Override with INDIAN_KANOON_DAILY_CAP_INR in .env.
# Set to None for no cap (not recommended).
DEFAULT_DAILY_CAP_INR = 100.0


# ----------------------------------------------------------------- exceptions

class KanoonError(Exception):
    """Base for any IK API failure."""


class KanoonAuthError(KanoonError):
    """401/403 — token invalid or rate-limited at auth layer."""


class KanoonNotFound(KanoonError):
    """404 — tid does not exist."""


class KanoonRateLimited(KanoonError):
    """429 — slow down."""


class KanoonServerError(KanoonError):
    """5xx — IK side."""


class KanoonBudgetExceeded(KanoonError):
    """Daily INR cap would be exceeded if this call were made. Refusing the call
    is the safe default; raise the cap in .env if you really mean to spend more."""


# ------------------------------------------------------------------- DTOs

@dataclass(frozen=True)
class SearchHit:
    """One result from /search/."""
    tid: int
    title: str
    docsource: str          # "Supreme Court of India", "Bombay High Court", ...
    publishdate: str        # ISO "YYYY-MM-DD"
    headline: str           # snippet with <b>...</b> highlights around query terms
    numcites: int           # how many cases this judgment cites
    numcitedby: int         # how many cases cite this judgment (citation weight!)
    doctype: int            # numeric IK code (1000 = SC, etc.)
    bench: str | None

    @classmethod
    def from_raw(cls, d: dict) -> "SearchHit":
        return cls(
            tid=int(d["tid"]),
            title=d.get("title", ""),
            docsource=d.get("docsource", ""),
            publishdate=d.get("publishdate", ""),
            headline=d.get("headline", ""),
            numcites=int(d.get("numcites") or 0),
            numcitedby=int(d.get("numcitedby") or 0),
            doctype=int(d.get("doctype") or 0),
            bench=d.get("bench"),
        )


@dataclass(frozen=True)
class SearchPage:
    hits: list[SearchHit]
    found_label: str        # e.g. "1 - 10 of 28"
    page: int
    raw: dict               # full upstream JSON (categories, encodedformInput, ...)


@dataclass(frozen=True)
class Document:
    tid: int
    title: str
    publishdate: str
    docsource: str
    doc_html: str           # the judgment body (HTML — parse separately)
    numcites: int
    numcitedby: int
    cats: list[dict]        # IK AI-extracted topic tags
    raw: dict


# ----------------------------------------------------------------- the client

class KanoonClient:
    """Thread-safe-ish IK API client with SQLite cache.

    Each instance owns its own requests.Session and a lock for the throttle.
    SQLite connections are per-call (sqlite3 module is not thread-safe for
    shared connections, but new ones-per-call is fine for our request volume).
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        cache_path: str | os.PathLike | None = None,
        throttle_seconds: float = DEFAULT_THROTTLE_SECONDS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        daily_cap_inr: float | None = None,
    ):
        # Accept either canonical (INDIAN_KANOON_TOKEN) or legacy
        # (KANOON_API_TOKEN) env var name — some Render dashboards use the
        # shorter alias.
        self.token = (
            token
            or os.environ.get("INDIAN_KANOON_TOKEN")
            or os.environ.get("KANOON_API_TOKEN")
            or ""
        )
        if not self.token:
            raise KanoonAuthError(
                "Indian Kanoon token not set. Add INDIAN_KANOON_TOKEN "
                "(or legacy KANOON_API_TOKEN) to .env or pass token=..."
            )
        self.cache_path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        self.throttle_seconds = throttle_seconds
        self.timeout_seconds = timeout_seconds

        # Daily cap precedence: explicit kwarg > env var > module default
        if daily_cap_inr is not None:
            self.daily_cap_inr: float | None = daily_cap_inr
        else:
            env_cap = os.environ.get("INDIAN_KANOON_DAILY_CAP_INR")
            if env_cap is not None:
                try:
                    self.daily_cap_inr = float(env_cap) if env_cap.strip() else None
                except ValueError:
                    self.daily_cap_inr = DEFAULT_DAILY_CAP_INR
            else:
                self.daily_cap_inr = DEFAULT_DAILY_CAP_INR

        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Token {self.token}",
            "Accept": "application/json",
            "User-Agent": "Headnote/0.4 (legal research; respectful client)",
        })

        self._throttle_lock = threading.Lock()
        self._last_request_at = 0.0

        self._init_cache()

    # --- cache plumbing

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.cache_path, timeout=10)
        try:
            yield c
        finally:
            c.close()

    def _init_cache(self) -> None:
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS ik_search (
                    query_hash TEXT NOT NULL,
                    pagenum    INTEGER NOT NULL,
                    response   TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (query_hash, pagenum)
                );
                CREATE TABLE IF NOT EXISTS ik_doc (
                    tid        INTEGER PRIMARY KEY,
                    response   TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ik_docmeta (
                    tid        INTEGER PRIMARY KEY,
                    response   TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                -- Cost ledger: one row per LIVE (non-cached) IK API call.
                -- Used to enforce daily spend cap and surface running totals.
                CREATE TABLE IF NOT EXISTS ik_spend (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts          TEXT NOT NULL,        -- UTC ISO
                    day_local   TEXT NOT NULL,        -- YYYY-MM-DD in local time, for daily totals
                    kind        TEXT NOT NULL,        -- search / doc / docmeta / ...
                    path        TEXT NOT NULL,
                    cost_inr    REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_spend_day_local ON ik_spend(day_local);

                -- HuggingFace IL-TUR imported corpus. Populated by
                -- scripts/harvest_hf_corpus.py; queried by
                -- headnote/retrieval/hf_corpus.py. Lives in the same SQLite
                -- file as the IK cache so a single Railway Volume covers both.
                --
                -- doc_id format: "hf:<source>:<original_id>" (e.g. "hf:cjpe:115651329").
                -- The "hf:" prefix is what the retrieval layer keys on to know
                -- this isn't an IK case (which uses "ik:<tid>").
                CREATE TABLE IF NOT EXISTS hf_judgments (
                    rowid        INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id       TEXT NOT NULL UNIQUE,
                    source       TEXT NOT NULL,        -- cjpe / summ / bail / pcr / lsi
                    court        TEXT,                  -- supreme_court / high_court / district_court
                    title        TEXT,                  -- synthesised from first line of judgment
                    text         TEXT NOT NULL,         -- full judgment text
                    summary      TEXT,                  -- gold summary if present (SUMM subset)
                    label        TEXT,                  -- granted/rejected/accepted for CJPE & BAIL
                    district     TEXT,                  -- district court for BAIL subset
                    language     TEXT NOT NULL DEFAULT 'en',
                    word_count   INTEGER NOT NULL DEFAULT 0,
                    raw_metadata TEXT,                  -- JSON: split name + any extra fields
                    imported_at  TEXT NOT NULL          -- UTC ISO
                );
                CREATE INDEX IF NOT EXISTS idx_hf_source   ON hf_judgments(source);
                CREATE INDEX IF NOT EXISTS idx_hf_court    ON hf_judgments(court);
                CREATE INDEX IF NOT EXISTS idx_hf_district ON hf_judgments(district);
                CREATE INDEX IF NOT EXISTS idx_hf_language ON hf_judgments(language);
                CREATE INDEX IF NOT EXISTS idx_hf_label    ON hf_judgments(label);
            """)
            c.commit()

    # --- request plumbing

    def _throttle(self) -> None:
        with self._throttle_lock:
            elapsed = time.monotonic() - self._last_request_at
            wait = self.throttle_seconds - elapsed
            if wait > 0:
                time.sleep(wait)
            self._last_request_at = time.monotonic()

    def _post(self, path: str, *, kind: str) -> dict:
        """POST to IK API path; raise typed exceptions on non-2xx; return JSON.

        `kind` identifies the cost class (search / doc / docmeta / ...). The
        method enforces the daily spend cap BEFORE the call goes out, then
        records the cost in the ledger after a successful 200.
        """
        cost = COST_INR.get(kind, 0.0)
        self._check_daily_cap(cost)
        self._throttle()
        url = f"{API_BASE}{path}"
        try:
            r = self._session.post(url, timeout=self.timeout_seconds)
        except requests.RequestException as e:
            raise KanoonError(f"network failure for {url}: {e}") from e

        if r.status_code == 200:
            try:
                payload = r.json()
            except ValueError as e:
                raise KanoonError(f"non-JSON 200 from {url}: {e}") from e
            self._record_spend(kind, path, cost)
            return payload
        if r.status_code == 401 or r.status_code == 403:
            raise KanoonAuthError(f"{r.status_code} from {url}: {r.text[:300]}")
        if r.status_code == 404:
            raise KanoonNotFound(f"404 for {url}")
        if r.status_code == 429:
            raise KanoonRateLimited(f"429 for {url}: {r.text[:300]}")
        if 500 <= r.status_code < 600:
            raise KanoonServerError(f"{r.status_code} from {url}: {r.text[:300]}")
        raise KanoonError(f"{r.status_code} from {url}: {r.text[:300]}")

    # --- cost ledger / cap

    @staticmethod
    def _today_local() -> str:
        # Local-day grouping. Lawyers think in IST days, not UTC days.
        return datetime.now().strftime("%Y-%m-%d")

    def _spend_today(self) -> float:
        with self._conn() as c:
            row = c.execute(
                "SELECT COALESCE(SUM(cost_inr), 0.0) FROM ik_spend WHERE day_local = ?",
                (self._today_local(),),
            ).fetchone()
        return float(row[0]) if row else 0.0

    def _check_daily_cap(self, cost_inr: float) -> None:
        if self.daily_cap_inr is None:
            return
        spent = self._spend_today()
        if spent + cost_inr > self.daily_cap_inr:
            raise KanoonBudgetExceeded(
                f"Daily IK spend cap (₹{self.daily_cap_inr:.2f}) would be exceeded. "
                f"Spent today: ₹{spent:.2f}; this call: ₹{cost_inr:.2f}. "
                f"Raise INDIAN_KANOON_DAILY_CAP_INR in .env to override."
            )

    def _record_spend(self, kind: str, path: str, cost_inr: float) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO ik_spend (ts, day_local, kind, path, cost_inr) "
                "VALUES (?, ?, ?, ?, ?)",
                (_now_iso(), self._today_local(), kind, path, cost_inr),
            )
            c.commit()

    def spend_summary(self) -> dict:
        """Today + lifetime totals, broken down by kind. For the cost meter UI."""
        today = self._today_local()
        with self._conn() as c:
            today_total = c.execute(
                "SELECT COALESCE(SUM(cost_inr), 0.0) FROM ik_spend WHERE day_local=?",
                (today,),
            ).fetchone()[0]
            today_calls = c.execute(
                "SELECT COUNT(*) FROM ik_spend WHERE day_local=?", (today,)
            ).fetchone()[0]
            lifetime_total = c.execute(
                "SELECT COALESCE(SUM(cost_inr), 0.0) FROM ik_spend"
            ).fetchone()[0]
            lifetime_calls = c.execute("SELECT COUNT(*) FROM ik_spend").fetchone()[0]
            by_kind_rows = c.execute(
                "SELECT kind, COUNT(*), SUM(cost_inr) FROM ik_spend GROUP BY kind"
            ).fetchall()
        return {
            "today_local_date": today,
            "today_total_inr": round(float(today_total), 4),
            "today_calls": int(today_calls),
            "today_remaining_inr": (
                None if self.daily_cap_inr is None
                else round(max(0.0, self.daily_cap_inr - float(today_total)), 4)
            ),
            "daily_cap_inr": self.daily_cap_inr,
            "lifetime_total_inr": round(float(lifetime_total), 4),
            "lifetime_calls": int(lifetime_calls),
            "by_kind": {k: {"calls": int(n), "inr": round(float(s), 4)}
                        for k, n, s in by_kind_rows},
        }

    # --- public: search

    @staticmethod
    def _hash_query(form_input: str) -> str:
        return hashlib.sha256(form_input.encode("utf-8")).hexdigest()[:16]

    def search(
        self,
        form_input: str,
        *,
        pagenum: int = 0,
        use_cache: bool = True,
        max_age_days: int | None = 30,
    ) -> SearchPage:
        """Search IK. `form_input` is the IK query string (supports filters like
        'doctypes:supremecourt' and 'tag:cheque-dishonour').
        """
        qhash = self._hash_query(form_input)

        if use_cache:
            cached = self._get_cached_search(qhash, pagenum, max_age_days)
            if cached is not None:
                return self._search_page_from_raw(cached, pagenum)

        path = f"/search/?formInput={quote_plus(form_input)}&pagenum={pagenum}"
        raw = self._post(path, kind="search")

        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO ik_search (query_hash, pagenum, response, fetched_at) "
                "VALUES (?, ?, ?, ?)",
                (qhash, pagenum, json.dumps(raw, ensure_ascii=False), _now_iso()),
            )
            c.commit()
        return self._search_page_from_raw(raw, pagenum)

    def _get_cached_search(
        self, qhash: str, pagenum: int, max_age_days: int | None
    ) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT response, fetched_at FROM ik_search "
                "WHERE query_hash=? AND pagenum=?",
                (qhash, pagenum),
            ).fetchone()
        if row is None:
            return None
        response_text, fetched_at = row
        if max_age_days is not None and _age_days(fetched_at) > max_age_days:
            return None
        return json.loads(response_text)

    @staticmethod
    def _search_page_from_raw(raw: dict, pagenum: int) -> SearchPage:
        hits = [SearchHit.from_raw(d) for d in raw.get("docs", [])]
        return SearchPage(
            hits=hits,
            found_label=str(raw.get("found", "")),
            page=pagenum,
            raw=raw,
        )

    # --- public: doc

    def get_doc(self, tid: int, *, use_cache: bool = True) -> Document:
        """Fetch full judgment by tid. Judgments don't change, so cache forever."""
        if use_cache:
            cached = self._get_cached_doc(tid)
            if cached is not None:
                return _document_from_raw(cached)

        raw = self._post(f"/doc/{int(tid)}/", kind="doc")
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO ik_doc (tid, response, fetched_at) "
                "VALUES (?, ?, ?)",
                (int(tid), json.dumps(raw, ensure_ascii=False), _now_iso()),
            )
            c.commit()
        return _document_from_raw(raw)

    def _get_cached_doc(self, tid: int) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT response FROM ik_doc WHERE tid=?", (int(tid),)
            ).fetchone()
        return json.loads(row[0]) if row else None

    # --- public: docmeta

    def get_docmeta(self, tid: int, *, use_cache: bool = True) -> dict:
        """Lightweight metadata fetch. Use when you only need title/date/court."""
        if use_cache:
            with self._conn() as c:
                row = c.execute(
                    "SELECT response FROM ik_docmeta WHERE tid=?", (int(tid),)
                ).fetchone()
            if row:
                return json.loads(row[0])
        raw = self._post(f"/docmeta/{int(tid)}/", kind="docmeta")
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO ik_docmeta (tid, response, fetched_at) "
                "VALUES (?, ?, ?)",
                (int(tid), json.dumps(raw, ensure_ascii=False), _now_iso()),
            )
            c.commit()
        return raw

    # --- cache stats (for the cost meter / debugging)

    def cache_stats(self) -> dict:
        with self._conn() as c:
            n_search = c.execute("SELECT COUNT(*) FROM ik_search").fetchone()[0]
            n_doc = c.execute("SELECT COUNT(*) FROM ik_doc").fetchone()[0]
            n_meta = c.execute("SELECT COUNT(*) FROM ik_docmeta").fetchone()[0]
            size_bytes = self.cache_path.stat().st_size if self.cache_path.exists() else 0
        return {
            "search_pages_cached": n_search,
            "documents_cached": n_doc,
            "docmeta_cached": n_meta,
            "cache_path": str(self.cache_path),
            "cache_size_bytes": size_bytes,
        }


# ----------------------------------------------------------------- helpers

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _age_days(iso_ts: str) -> float:
    try:
        ts = datetime.fromisoformat(iso_ts)
    except ValueError:
        return float("inf")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0


def _document_from_raw(raw: dict) -> Document:
    return Document(
        tid=int(raw.get("tid") or 0),
        title=raw.get("title", ""),
        publishdate=raw.get("publishdate", ""),
        docsource=raw.get("docsource", ""),
        doc_html=raw.get("doc", ""),
        numcites=int(raw.get("numcites") or 0),
        numcitedby=int(raw.get("numcitedby") or 0),
        cats=list(raw.get("cats") or []),
        raw=raw,
    )
