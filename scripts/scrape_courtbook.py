#!/usr/bin/env python3
"""Scrape courtbook.in/draft into a local research corpus (JSONL).

RESEARCH / COMPETITIVE-ANALYSIS ONLY
------------------------------------
The scraped text is third-party content from courtbook.in. Do NOT import this
corpus into the ``headnote/`` package, do NOT serve it via any API, and never
rehost it verbatim. It exists to (a) map courtbook's taxonomy as a roadmap for
which native templates to build next, and (b) act as reference while we build
our own native Kruti-Dev templates from real filed sources. Output is gitignored
(``.courtbook_cache/`` + ``research/courtbook/``).

Pipeline
--------
    /draft/<lang> index page  ->  leaf /draft/<lang>/<slug>-<id> links
    ->  polite cached fetch  ->  BeautifulSoup DOM parse  ->  JSONL

(The XML sitemap indexes only the /posts/ news section — the draft templates are
not sitemapped — so we enumerate them from the per-language index page, which
serves the full flat catalog as anchors: english 119, hindi 23, marathi 74,
gujarati 75 templates as of June 2026.)

Courtbook is Next.js (App Router, RSC streaming) but fully server-rendered: a
plain GET returns the <h1>, <title>, JSON-LD, and full body text in the DOM, so
``requests`` + ``beautifulsoup4`` (both already in requirements.txt) suffice — no
headless browser. We strip <script>/<style>/<nav>/<header>/<footer> before
extracting text so the RSC flight payload (self.__next_f) never pollutes the body.

robots.txt is ``Allow: /`` for all bots (only /api/, /posts/search, /subscription,
/embed, AMP, ?_rsc= are disallowed) — template pages are crawl-permitted. We use a
descriptive User-Agent, ~1 req/sec rate-limit, and an on-disk cache so a page is
never fetched twice.

Usage
-----
    python scripts/scrape_courtbook.py --langs english --limit 5   # dry run
    python scripts/scrape_courtbook.py                             # full (english+hindi)
    python scripts/scrape_courtbook.py --langs english,hindi,marathi,gujarati

Resumable: cached pages are reused on re-run, so interrupting and restarting only
fetches the pages not yet on disk.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    from tqdm import tqdm
except Exception:  # tqdm is in requirements, but degrade gracefully
    def tqdm(it, **_kw):
        return it

BASE = "https://courtbook.in"
INDEX_URL = BASE + "/draft/{lang}"
USER_AGENT = (
    "HeadnoteResearchBot/1.0 (competitive analysis; contact: kshitij@loopai.com)"
)
DEFAULT_CACHE = Path(".courtbook_cache")
DEFAULT_OUT = Path("research/courtbook/courtbook_corpus.jsonl")

# Trailing Mongo-style ObjectId (24 hex) that marks a leaf template page, e.g.
# /draft/english/affidavit-282cf1eff64646ca94c71695
HEXID_RE = re.compile(r"-([0-9a-f]{16,})$")
# CrPC/BNSS/IPC/Act section references in title or body (English + Devanagari).
# Captures just the section token (number + optional letter + optional subsection)
# — NOT the trailing Act name, which otherwise greedily swallows prose.
SECTION_RE = re.compile(
    r"(?:Section|Sec\.?|§|धारा)\s*\d+[A-Z]?(?:\(\d+[A-Za-z]?\))?",
    re.IGNORECASE,
)
NOISE_TAGS = ("script", "style", "nav", "header", "footer", "noscript", "svg", "form")


def split_slug_id(path_tail: str) -> tuple[str, str]:
    """('affidavit-282cf1...') -> ('affidavit', '282cf1...'). Falls back to (tail, '')."""
    m = HEXID_RE.search(path_tail)
    if not m:
        return path_tail, ""
    return path_tail[: m.start()], m.group(1)


def enumerate_draft_urls(langs: set[str], session: requests.Session,
                         limit: int | None = None) -> list[tuple[str, str, str, str]]:
    """Crawl each /draft/<lang> index page and return its leaf template pages as
    (lang, slug, hexid, url). Stops early once `limit` is reached."""
    out: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for lang in sorted(langs):
        try:
            html = session.get(INDEX_URL.format(lang=lang), timeout=30,
                               allow_redirects=True).text
        except requests.RequestException as e:
            print(f"      ! {lang}: index fetch failed ({e})")
            continue
        soup = BeautifulSoup(html, "html.parser")
        before = len(out)
        for a in soup.find_all("a"):
            href = a.get("href") or ""
            parts = [p for p in urlparse(href).path.split("/") if p]
            if len(parts) < 3 or parts[0] != "draft" or parts[1].lower() != lang:
                continue
            slug, hexid = split_slug_id(parts[-1])
            if not hexid:  # language nav / non-template link
                continue
            full = BASE + urlparse(href).path
            if full in seen:
                continue
            seen.add(full)
            out.append((lang, slug, hexid, full))
            if limit and len(out) >= limit:
                return out
        print(f"      {lang}: {len(out) - before} templates")
        time.sleep(0.5)  # polite between index fetches
    return out


def fetch(url: str, lang: str, hexid: str, cache_dir: Path, delay: float,
          session: requests.Session) -> str | None:
    """Return page HTML, from disk cache if present else a polite network GET."""
    cache_file = cache_dir / lang / f"{hexid}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    for attempt in range(4):
        try:
            r = session.get(url, timeout=30, allow_redirects=True)
        except requests.RequestException:
            time.sleep(delay * (2 ** attempt) + 1)
            continue
        if r.status_code == 200:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(r.text, encoding="utf-8")
            time.sleep(delay)  # rate-limit only on real network hits
            return r.text
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(delay * (2 ** attempt) + 1)
            continue
        return None  # 404/403/etc — give up on this URL
    return None


def _jsonld_breadcrumb(soup: BeautifulSoup) -> list[str]:
    """Pull the BreadcrumbList name path from JSON-LD, if present."""
    crumbs: list[str] = []
    for s in soup.find_all("script", type="application/ld+json"):
        raw = s.string or s.get_text() or ""
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        stack = [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                if obj.get("@type") == "BreadcrumbList":
                    names = [it.get("name") for it in obj.get("itemListElement", [])
                             if isinstance(it, dict) and it.get("name")]
                    if names:
                        crumbs = names
                stack.extend(obj.values())
            elif isinstance(obj, list):
                stack.extend(obj)
    return crumbs


def parse(html: str, url: str, lang: str, slug: str, hexid: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # Title: <h1>, then og:title, then <title>.
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""
    if not title:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            title = og["content"].strip()
    if not title and soup.title:
        title = soup.title.get_text(strip=True)

    # Breadcrumb BEFORE we strip <script>. Courtbook's tree is flat
    # (Home > <Lang> Drafts > <Type>), so the leaf crumb is the clean type name;
    # there is no practice-area taxonomy on the site — we bucket that in coverage.
    breadcrumb = _jsonld_breadcrumb(soup)
    type_name = breadcrumb[-1] if breadcrumb else ""
    if not type_name:
        type_name = slug.replace("-", " ").strip().title()
    type_name = re.sub(r"\s+Format(\s+in\s+India)?$", "", type_name,
                       flags=re.IGNORECASE).strip()

    # Strip noise, then extract the main content text.
    for tag in soup(list(NOISE_TAGS)):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    subheadings = [h.get_text(" ", strip=True)
                   for h in main.find_all(["h2", "h3"])
                   if h.get_text(strip=True)]
    body_text = main.get_text("\n", strip=True)
    body_text = re.sub(r"\n{3,}", "\n\n", body_text)

    haystack = f"{title}\n{body_text}"
    sections = sorted({re.sub(r"\s+", " ", m.group(0)).strip()
                       for m in SECTION_RE.finditer(haystack)})

    return {
        "id": hexid,
        "slug": slug,
        "lang": lang,
        "title": title,
        "type_name": type_name,
        "breadcrumb": breadcrumb,
        "sections": sections,
        "subheadings": subheadings,
        "word_count": len(body_text.split()),
        "url": url,
        "text": body_text,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--langs", default="english,hindi",
                    help="comma list of langs to keep (default: english,hindi)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap number of pages (for dry runs)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output JSONL path")
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE), help="raw-HTML cache dir")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="seconds between network fetches (default: 1.0)")
    args = ap.parse_args()

    langs = {s.strip().lower() for s in args.langs.split(",") if s.strip()}
    cache_dir = Path(args.cache_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    print(f"[1/3] Enumerating /draft URLs (langs={sorted(langs)})...")
    urls = enumerate_draft_urls(langs, session, limit=args.limit)
    print(f"      {len(urls)} leaf template URLs")
    if not urls:
        sys.exit("No URLs found — sitemap structure may have changed.")

    print(f"[2/3] Fetching + parsing (cache={cache_dir}, delay={args.delay}s)...")
    records, skipped = [], 0
    for lang, slug, hexid, url in tqdm(urls, desc="pages", unit="pg"):
        html = fetch(url, lang, hexid, cache_dir, args.delay, session)
        if not html:
            skipped += 1
            continue
        rec = parse(html, url, lang, slug, hexid)
        if not rec["title"] and not rec["text"]:
            skipped += 1
            continue
        records.append(rec)

    print(f"[3/3] Writing {len(records)} records -> {out_path}  ({skipped} skipped)")
    with out_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    by_lang: dict[str, int] = {}
    for r in records:
        by_lang[r["lang"]] = by_lang.get(r["lang"], 0) + 1
    words = sorted(r["word_count"] for r in records)
    print(f"\nDone. {len(records)} records.")
    print(f"  by lang: {by_lang}")
    print(f"  median words/page: {words[len(words) // 2] if words else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
