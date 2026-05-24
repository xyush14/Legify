#!/usr/bin/env python3
"""Scrape criminal-law judgments + orders from sci.gov.in into hf_judgments.

WHY THIS EXISTS
---------------
IL-TUR (via scripts/harvest_hf_corpus.py) gives us ~34K historical SC
judgments but its snapshot ends in ~2022. This script keeps the corpus
current by pulling the latest criminal-law judgments + orders straight
from the Supreme Court's public archive.

WHAT IT CAN AND CANNOT DO
-------------------------
sci.gov.in puts a SecurImage captcha in front of every query form
(`/judgements-judgement-date/`, `/judgements-judge/`, `/free-text-judgements/`,
`/judgements-case-no/`) — the AJAX endpoint at /wp-admin/admin-ajax.php
returns {"success":false,"data":"The captcha code entered was incorrect."}
without it. We do NOT bypass that — the captcha is deliberate anti-bot.

The one captcha-FREE listing is /latest-orders/, which serves the most
recent ~900-1000 uploaded judgments + orders on a single page. There is
no pagination; `/latest-orders/page/2/`, `?paged=2`, `/2025/` all return
the same page.

So the realistic ceiling for one run is ~500 criminal entries (after the
case-type filter). To hit the 2K-5K target asked for in the spec, run
this on a daily/weekly cron — INSERT OR IGNORE makes that idempotent and
the listing churns as the court publishes more.

For historical bulk backfill, use scripts/harvest_hf_corpus.py instead.

USAGE
-----
    python scripts/scrape_sci.py                       # everything from /latest-orders/
    python scripts/scrape_sci.py --limit 50            # cap (testing)
    python scripts/scrape_sci.py --year-from 2024      # only orders dated >= 2024
    python scripts/scrape_sci.py --db /data/cache.db   # alt DB
    python scripts/scrape_sci.py --include-civil       # disable criminal-only filter
    python scripts/scrape_sci.py --throttle 2.0        # slower crawl (default 1.5s)

WHAT GETS INSERTED
------------------
    doc_id   : "sci:{YYYY-MM-DD}_{diary_no}_{type}"   e.g. sci:2026-05-21_299892026_o
    source   : "sci_scrape"
    court    : "supreme_court"
    language : "en"
    label    : "judgment" | "order"
    title    : the caption shown on /latest-orders/ ("PARTY A VS. PARTY B - SLP(Crl) ...")
    text     : full PDF text via pypdf (skipped if PDF unreadable)
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import httpx
from bs4 import BeautifulSoup

# Put repo root on sys.path so `from headnote.config import …` works regardless
# of where this script is invoked from. Mirrors harvest_hf_corpus.py.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    import pypdf
except ImportError:
    sys.exit("ERROR: pypdf not installed.\nRun: pip install pypdf")

from headnote.config import KANOON_CACHE_PATH

# fact_extractor is optional — if it isn't importable (e.g. missing torch on a
# minimal env), we still ingest the row, just without facts_json.
try:
    from headnote.retrieval.fact_extractor import extract_facts  # type: ignore
except Exception:                                                  # pragma: no cover
    extract_facts = None  # type: ignore


# ---------------------------------------------------------------- constants

BASE_URL = "https://www.sci.gov.in"
LISTING_URL = f"{BASE_URL}/latest-orders/"

# We use a real-browser UA. SCI's WAF (NIC) refuses some default httpx UAs.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Criminal-law indicators in the case-number / caption. Matches the case-type
# codes from the /judgements-case-no/ form (CRIMINAL APPEAL = 4, SLP(CRL) = 2,
# W.P.(CRL) = 6, etc.). The order of patterns doesn't matter — any match wins.
#
# WHY this list rather than a body-text scan: the listing page only gives us
# the case caption, not the PDF body. We need to decide whether to download
# each PDF (40-100KB) BEFORE fetching, so the filter has to run on the
# caption alone. Caption-based filtering is also what an advocate would
# eyeball, so false positives are limited to genuine criminal cases.
_CRIMINAL_PATTERNS = [
    re.compile(r"\bSLP\s*\(\s*Crl\.?\s*\)", re.I),           # SLP(Crl)
    re.compile(r"\bCrl\.?\s*A\.?\s*N?o?\.?", re.I),          # Crl.A. No. / Crl A No.
    re.compile(r"\bCrl\.?\s*M(isc|P|A)\.?", re.I),           # Crl.Misc., Crl.MP, Crl.MA
    re.compile(r"\bW\.?\s*P\.?\s*\(\s*Crl\.?\s*\)", re.I),   # W.P.(Crl.)
    re.compile(r"\bR\.?\s*P\.?\s*\(\s*Crl\.?\s*\)", re.I),   # R.P.(Crl.)
    re.compile(r"\bT\.?\s*P\.?\s*\(\s*Crl\.?\s*\)", re.I),   # T.P.(Crl.) — transfer petition
    re.compile(r"\bContempt\s*\(\s*Crl", re.I),              # Contempt (Crl
    re.compile(r"\bMA\s+\d[\d\s\-/]*\s+in\s+SLP\s*\(\s*Crl", re.I),  # MA in SLP(Crl)
    re.compile(r"\bCRIMINAL\s+APPEAL\b", re.I),
    re.compile(r"\bDEATH\s+REFERENCE\b", re.I),
    re.compile(r"\bBAIL\s+APPL", re.I),                      # bail application
]


# --------------------------------------------------------------- data types

@dataclass(frozen=True)
class ListingEntry:
    """One row pulled from /latest-orders/."""
    diary_no: str       # e.g. "299892026"
    order_type: str     # "j" (judgment) or "o" (order)
    order_date: str     # ISO "YYYY-MM-DD"
    caption: str        # cleaned-up title from the <a>'s text
    view_url: str       # original /view-pdf/ url (for debugging)

    @property
    def doc_id(self) -> str:
        return f"sci:{self.order_date}_{self.diary_no}_{self.order_type}"

    @property
    def pdf_url(self) -> str:
        # /sci-get-pdf/ is the actual binary endpoint /view-pdf/'s iframe
        # points to — confirmed via the JS source on the view-pdf page.
        return (
            f"{BASE_URL}/sci-get-pdf/?diary_no={self.diary_no}"
            f"&type={self.order_type}&order_date={self.order_date}"
            f"&from=latest_judgements_order"
        )

    @property
    def is_criminal(self) -> bool:
        return any(p.search(self.caption) for p in _CRIMINAL_PATTERNS)

    @property
    def label(self) -> str:
        return "judgment" if self.order_type == "j" else "order"


# ------------------------------------------------------------- DB plumbing

def _open_db(db_path: Path) -> sqlite3.Connection:
    """Open the cache DB and make sure hf_judgments exists.

    The table is normally created by headnote.kanoon.client._init_cache on
    app boot, and again by harvest_hf_corpus.py — we mirror the DDL here
    for the case where this script runs on a fresh volume before either.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS hf_judgments (
            rowid        INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id       TEXT NOT NULL UNIQUE,
            source       TEXT NOT NULL,
            court        TEXT,
            title        TEXT,
            text         TEXT NOT NULL,
            summary      TEXT,
            label        TEXT,
            district     TEXT,
            language     TEXT NOT NULL DEFAULT 'en',
            word_count   INTEGER NOT NULL DEFAULT 0,
            raw_metadata TEXT,
            facts_json   TEXT,
            imported_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hf_source   ON hf_judgments(source);
        CREATE INDEX IF NOT EXISTS idx_hf_court    ON hf_judgments(court);
        CREATE INDEX IF NOT EXISTS idx_hf_language ON hf_judgments(language);
        CREATE INDEX IF NOT EXISTS idx_hf_label    ON hf_judgments(label);
    """)
    try:
        conn.execute("ALTER TABLE hf_judgments ADD COLUMN facts_json TEXT")
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise
    return conn


def _existing_doc_ids(conn: sqlite3.Connection, doc_ids: Iterable[str]) -> set[str]:
    """Bulk-check which doc_ids already live in hf_judgments. One round-trip
    via a temp table beats N selects when --limit is large."""
    ids = list(doc_ids)
    if not ids:
        return set()
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT doc_id FROM hf_judgments WHERE doc_id IN ({placeholders})", ids,
    ).fetchall()
    return {r[0] for r in rows}


# ---------------------------------------------------------- listing parsing

# Matches the order_date attribute we care about inside the entry text.
_DATE_RE = re.compile(r"order_date=(\d{4}-\d{2}-\d{2})")
_DIARY_RE = re.compile(r"diary_no=(\d+)")
_TYPE_RE = re.compile(r"type=([jo])")


def _clean_caption(text: str) -> str:
    """Strip extra whitespace and the trailing '(Uploaded On …)' suffix.

    The raw <a> text looks like:
       "AKASH ... VS. STATE OF HARYANA - SLP(Crl) No. 9451/2026 - Diary
        Number 29989 / 2026 -  21-May-2026  (Uploaded On 23-05-2026 15:28:49)"

    The uploaded-on is metadata, not part of the legal caption — drop it.
    """
    cleaned = " ".join(text.split())
    cleaned = re.sub(r"\s*\(\s*Uploaded On [^)]*\)\s*$", "", cleaned)
    return cleaned.strip(" -")


def parse_listing(html: str) -> list[ListingEntry]:
    """Pull every (diary_no, type, order_date, caption) tuple out of
    /latest-orders/. Returns them in the order they appeared on the page
    (which is upload-time DESC, so newest first)."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[ListingEntry] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "view-pdf" not in href or "diary_no=" not in href:
            continue
        m_diary = _DIARY_RE.search(href)
        m_type = _TYPE_RE.search(href)
        m_date = _DATE_RE.search(href)
        if not (m_diary and m_type and m_date):
            continue
        diary_no = m_diary.group(1)
        order_type = m_type.group(1)
        order_date = m_date.group(1)
        # Dedupe within the page (the same case can appear twice if multiple
        # orders share an upload batch — same diary/date/type triplet).
        key = f"{diary_no}_{order_type}_{order_date}"
        if key in seen:
            continue
        seen.add(key)
        out.append(ListingEntry(
            diary_no=diary_no,
            order_type=order_type,
            order_date=order_date,
            caption=_clean_caption(a.get_text(" ", strip=True)),
            view_url=href,
        ))
    return out


# ------------------------------------------------------------ PDF fetching

def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Run pypdf over the bytes, concatenate every page. Returns "" on
    any failure — the caller decides whether to skip the row."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                # pypdf occasionally trips on weird font tables — skip the
                # page, don't kill the whole document.
                continue
        return "\n".join(parts).strip()
    except Exception:
        return ""


async def _fetch_pdf(client: httpx.AsyncClient, entry: ListingEntry) -> Optional[bytes]:
    """GET the PDF or return None on 4xx/5xx/timeout. We return None rather
    than raising so the main loop can mark this entry as failed and move on
    without crashing the whole batch."""
    try:
        r = await client.get(entry.pdf_url, timeout=30.0)
    except (httpx.HTTPError, asyncio.TimeoutError) as e:
        print(f"    [net] {entry.doc_id}: {e}")
        return None
    if r.status_code != 200:
        print(f"    [http {r.status_code}] {entry.doc_id}")
        return None
    if not r.content.startswith(b"%PDF"):
        # SCI sometimes serves an HTML "file not available" page with 200 OK
        # — distinguish by sniffing the magic bytes.
        print(f"    [non-pdf body] {entry.doc_id}")
        return None
    return r.content


# ------------------------------------------------------------------ main

async def _run(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    print(f"Target DB: {db_path}")

    # Listing fetch. The page is large (~3800 lines) and NIC's CDN can be
    # sluggish, so we use a generous timeout and retry once on read timeout.
    print(f"Fetching listing: {LISTING_URL}")
    listing_html = ""
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        follow_redirects=True,
    ) as client:
        for attempt in (1, 2):
            try:
                listing_resp = await client.get(LISTING_URL, timeout=60.0)
                if listing_resp.status_code != 200:
                    print(f"FATAL: listing returned HTTP {listing_resp.status_code}")
                    return 2
                listing_html = listing_resp.text
                break
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                if attempt == 2:
                    print(f"FATAL: listing timed out twice: {e}")
                    return 2
                print(f"  listing timeout ({e}); retrying in 3s…")
                await asyncio.sleep(3.0)

    entries = parse_listing(listing_html)
    print(f"  parsed {len(entries)} entries")
    if not entries:
        print("FATAL: no entries — listing page format may have changed")
        return 2

    # Filter to criminal-law cases unless --include-civil.
    if not args.include_civil:
        before = len(entries)
        entries = [e for e in entries if e.is_criminal]
        print(f"  filtered to criminal: {len(entries)} of {before}")

    # Filter by --year-from on the order_date (YYYY-MM-DD lexical compare works).
    if args.year_from:
        cutoff = f"{args.year_from}-01-01"
        before = len(entries)
        entries = [e for e in entries if e.order_date >= cutoff]
        print(f"  filtered to order_date >= {cutoff}: {len(entries)} of {before}")

    # Drop duplicates already in the DB BEFORE we burn a PDF download on them.
    conn = _open_db(db_path)
    try:
        existing = _existing_doc_ids(conn, (e.doc_id for e in entries))
        if existing:
            entries = [e for e in entries if e.doc_id not in existing]
        print(f"  after dedup vs. DB: {len(entries)} new")

        if args.limit and len(entries) > args.limit:
            entries = entries[: args.limit]
            print(f"  limit applied: {len(entries)}")

        if not entries:
            print("Nothing to fetch. Done.")
            return 0

        # PDF fetch loop. We're polite: one request at a time with a global
        # throttle between requests. The SCI WAF (NIC) tolerates this fine
        # at 0.5-2 req/s but will start 429'ing at higher rates.
        ok = 0
        skipped_no_text = 0
        failed = 0
        now = datetime.now(timezone.utc).isoformat()

        async with httpx.AsyncClient(
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/pdf,*/*",
                "Referer": LISTING_URL,
            },
            follow_redirects=True,
        ) as client:
            for i, entry in enumerate(entries, start=1):
                print(f"[{i}/{len(entries)}] {entry.doc_id}  {entry.caption[:80]}")
                pdf_bytes = await _fetch_pdf(client, entry)
                if pdf_bytes is None:
                    failed += 1
                    await asyncio.sleep(args.throttle)
                    continue

                text = _extract_pdf_text(pdf_bytes)
                if not text or len(text) < 100:
                    # Some scanned-image PDFs (older SCI scans) have no
                    # extractable text — pypdf returns an empty string.
                    # We don't OCR them; the IL-TUR corpus already covers
                    # text-rich historical SC.
                    skipped_no_text += 1
                    await asyncio.sleep(args.throttle)
                    continue

                facts_json: Optional[str] = None
                if extract_facts is not None:
                    try:
                        facts = extract_facts(text[:20000])
                        if facts:
                            facts_json = json.dumps(facts, ensure_ascii=False)
                    except Exception:
                        # Don't let a fact-extraction failure kill the row.
                        facts_json = None

                raw_meta = json.dumps({
                    "diary_no": entry.diary_no,
                    "order_date": entry.order_date,
                    "type": entry.order_type,
                    "view_url": entry.view_url,
                    "pdf_url": entry.pdf_url,
                    "pdf_bytes": len(pdf_bytes),
                }, ensure_ascii=False)

                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO hf_judgments
                        (doc_id, source, court, title, text, summary, label,
                         district, language, word_count, raw_metadata,
                         facts_json, imported_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        entry.doc_id,
                        "sci_scrape",
                        "supreme_court",
                        entry.caption,
                        text,
                        None,
                        entry.label,
                        None,
                        "en",
                        len(text.split()),
                        raw_meta,
                        facts_json,
                        now,
                    ))
                    conn.commit()
                    ok += 1
                except sqlite3.Error as e:
                    print(f"    [db error] {entry.doc_id}: {e}")
                    failed += 1

                await asyncio.sleep(args.throttle)

        print()
        print("=" * 60)
        print(f"  inserted={ok}  no_text={skipped_no_text}  failed={failed}")
        print(f"  DB: {db_path}")
        print("=" * 60)
        return 0

    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--limit", type=int, default=None,
        help="Cap number of new PDFs fetched this run (for testing).",
    )
    p.add_argument(
        "--year-from", type=int, default=None,
        help="Only ingest entries whose order_date is in or after this year.",
    )
    p.add_argument(
        "--db", default=str(KANOON_CACHE_PATH),
        help=f"Target SQLite path (default: {KANOON_CACHE_PATH})",
    )
    p.add_argument(
        "--throttle", type=float, default=1.5,
        help="Seconds to sleep between PDF requests (default: 1.5).",
    )
    p.add_argument(
        "--include-civil", action="store_true",
        help="Disable the criminal-only caption filter (ingest everything).",
    )
    args = p.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
