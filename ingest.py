#!/usr/bin/env python3
"""
Headnote — Indian Kanoon ingest tool

Run this on your laptop (or in Cursor) when you have a list of judgments to
add to the corpus. It fetches each judgment from Indian Kanoon, extracts
metadata + paragraph-numbered text, and emits a JSON array ready for
editorial review and merging into cases.json.

USAGE
    # one URL
    python3 ingest.py "https://indiankanoon.org/doc/36294925/" > new_cases.json

    # batch — one URL per line in urls.txt
    python3 ingest.py --file urls.txt > new_cases.json

    # add lightweight LLM auto-extract for statutes/topics/holding (optional)
    python3 ingest.py --file urls.txt --enrich > new_cases.json

OUTPUT
    JSON array. Each entry has the corpus schema fields where extractable:
        id, title, citation, court, year, bench, statutes, bns_mapping,
        topics, facts, issues, holding, key_paras, subsequent_treatment,
        full_text (paragraph-numbered)

Fields like bns_mapping, topics, holding require editorial review or LLM
enrichment. The script flags incomplete fields with "TODO".

Respects ToS: rate-limited to 1 request / 1.5s, sets a polite User-Agent.
Don't scrape the entire site — feed it specific URLs you've identified.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    sys.exit("Run: pip install requests beautifulsoup4")

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Run: pip install requests beautifulsoup4")


HEADERS = {
    "User-Agent": (
        "HeadnoteResearch/0.4 (research tool; contact ayushshivhare02@gmail.com) "
        "respectful client; <2 req/sec"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

THROTTLE_SECONDS = 1.5  # seconds between requests


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def normalise_doc_url(url: str) -> str:
    p = urlparse(url)
    path = re.sub(r"/+$", "", p.path)
    return f"https://indiankanoon.org{path}/"


def doc_id_from_url(url: str) -> str | None:
    m = re.search(r"/doc/(\d+)/?", url)
    return m.group(1) if m else None


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def slugify_for_id(title: str, year: str | int, court_short: str) -> str:
    first_party = re.split(r"\s+v\.?\s+", title, maxsplit=1)[0]
    first_word = re.split(r"\s+", first_party)[0]
    slug = re.sub(r"[^A-Za-z]", "", first_word).upper()[:8]
    return f"{slug or 'CASE'}-{year}-{court_short}"


COURT_MAP = [
    (re.compile(r"supreme court", re.IGNORECASE), "SC"),
    (re.compile(r"high court of (\w+)", re.IGNORECASE), "HC"),
    (re.compile(r"(\w+) high court", re.IGNORECASE), "HC"),
    (re.compile(r"tribunal", re.IGNORECASE), "TR"),
    (re.compile(r"district", re.IGNORECASE), "DC"),
]


def detect_court(soup: BeautifulSoup, body_text: str) -> tuple[str, str]:
    """Return (full court name, short code like 'SC' / 'HC')."""
    head = soup.get_text("\n", strip=True)[:2000]
    for rx, code in COURT_MAP:
        m = rx.search(head)
        if m:
            return (m.group(0).strip(), code)
        m = rx.search(body_text[:3000])
        if m:
            return (m.group(0).strip(), code)
    return ("Unknown court", "XX")


YEAR_RX = re.compile(r"\b(19|20)\d{2}\b")


def detect_year(title: str, body_text: str) -> str:
    # Prefer year in title (Indian Kanoon includes it: "... on 21 September, 2023")
    for src in (title, body_text[:3000]):
        m = YEAR_RX.search(src)
        if m:
            return m.group(0)
    return "????"


def extract_title(soup: BeautifulSoup) -> str:
    h2 = soup.find("h2", class_="doc_title")
    if h2:
        return h2.get_text(" ", strip=True)
    title_tag = soup.find("title")
    if title_tag:
        # Indian Kanoon page title pattern: "Foo v. Bar on 21 September, 2023"
        text = title_tag.get_text(strip=True)
        text = re.sub(r"\s+", " ", text)
        return text
    return "Untitled"


def extract_bench(soup: BeautifulSoup, body_text: str) -> str:
    # IK puts "Bench: Name1, Name2" or "Author: Name" near top
    head_div = soup.find("div", class_="doc_author") or soup.find("div", class_="docsource_main")
    head_text = ""
    if head_div:
        head_text = head_div.get_text(" ", strip=True)
    head_text = head_text or body_text[:2000]
    bench = ""
    m = re.search(r"Bench:\s*([^\n]+)", head_text)
    if m:
        bench = m.group(1).strip()
    else:
        m = re.search(r"Author:\s*([^\n]+)", head_text)
        if m:
            bench = m.group(1).strip()
    bench = re.sub(r"\s+", " ", bench)
    bench = re.sub(r",\s*$", "", bench)
    return bench


def extract_paragraph_text(soup: BeautifulSoup) -> str:
    """Concatenate all judgment text, preserving structure."""
    body = soup.find("div", class_="judgments")
    if body is None:
        body = soup.find("body")
    if body is None:
        return ""
    # Each <p> on IK is typically a paragraph (may or may not be numbered).
    paras = []
    for p in body.find_all("p"):
        t = p.get_text(" ", strip=True)
        if t and len(t) > 5:
            paras.append(t)
    return "\n\n".join(paras)


# Try to detect "key_paras" — paragraphs likely to contain the ratio:
# heuristic: para containing "Held", "We hold", "in our view", "we are of the
# considered view", or a holding-style verb. Returns "(Paras X, Y, Z)".
HOLDING_RX = re.compile(
    r"^\s*(\d+)\.\s.*\b(?:held|we hold|in our (?:considered\s+)?view|"
    r"we are of the (?:considered\s+)?(?:view|opinion)|opined that|"
    r"thus\s+held|directed that|set aside|allow the appeal|allowed)\b",
    re.IGNORECASE | re.DOTALL,
)


def detect_key_paras(text: str, max_paras: int = 4) -> str:
    if not text:
        return ""
    nums = []
    for line in text.splitlines():
        m = HOLDING_RX.match(line)
        if m:
            nums.append(int(m.group(1)))
        if len(nums) >= max_paras:
            break
    if not nums:
        return ""
    return "(Paras " + ", ".join(str(n) for n in nums) + ")"


# Statute regex bank — extract any obvious statutes mentioned
STATUTE_PATTERNS = [
    (r"\bS\.?\s*(\d+[A-Z\-\(\)\d]*)\s*(of\s+the\s+)?(IPC|Indian\s+Penal\s+Code)\b",
     "Penal Code, 1860, S. {0}"),
    (r"\bS\.?\s*(\d+[A-Z\-\(\)\d]*)\s*(of\s+the\s+)?(CrPC|Code\s+of\s+Criminal\s+Procedure)\b",
     "Code of Criminal Procedure, 1973, S. {0}"),
    (r"\bS\.?\s*(\d+[A-Z\-\(\)\d]*)\s*(of\s+the\s+)?(NI\s+Act|Negotiable\s+Instruments\s+Act)\b",
     "Negotiable Instruments Act, 1881, S. {0}"),
    (r"\bS\.?\s*(\d+[A-Z\-\(\)\d]*)\s*(of\s+the\s+)?(BNS|Bharatiya\s+Nyaya\s+Sanhita)\b",
     "Bharatiya Nyaya Sanhita, 2023, S. {0}"),
    (r"\bS\.?\s*(\d+[A-Z\-\(\)\d]*)\s*(of\s+the\s+)?(BNSS|Bharatiya\s+Nagarik\s+Suraksha\s+Sanhita)\b",
     "Bharatiya Nagarik Suraksha Sanhita, 2023, S. {0}"),
    (r"\bS\.?\s*(\d+[A-Z\-\(\)\d]*)\s*(of\s+the\s+)?(BSA|Bharatiya\s+Sakshya\s+Adhiniyam|Indian\s+Evidence\s+Act|Evidence\s+Act)\b",
     "Indian Evidence Act, 1872, S. {0}"),
    (r"\bS\.?\s*(\d+[A-Z\-\(\)\d]*)\s*(of\s+the\s+)?(NDPS|Narcotic\s+Drugs)\b",
     "Narcotic Drugs and Psychotropic Substances Act, 1985, S. {0}"),
    (r"\bS\.?\s*(\d+[A-Z\-\(\)\d]*)\s*(of\s+the\s+)?(POCSO|Protection\s+of\s+Children\s+from\s+Sexual\s+Offences)\b",
     "Protection of Children from Sexual Offences Act, 2012, S. {0}"),
    (r"\bS\.?\s*(\d+[A-Z\-\(\)\d]*)\s*(of\s+the\s+)?(PMLA|Prevention\s+of\s+Money\s+Laundering)\b",
     "Prevention of Money Laundering Act, 2002, S. {0}"),
    (r"\bS\.?\s*(\d+[A-Z\-\(\)\d]*)\s*(of\s+the\s+)?(UAPA|Unlawful\s+Activities)\b",
     "Unlawful Activities (Prevention) Act, 1967, S. {0}"),
]


def extract_statutes(text: str, top_k: int = 8) -> list[str]:
    out = []
    seen = set()
    for pattern, fmt in STATUTE_PATTERNS:
        rx = re.compile(pattern, re.IGNORECASE)
        for m in rx.finditer(text):
            section = m.group(1).strip()
            entry = fmt.format(section)
            if entry not in seen:
                seen.add(entry)
                out.append(entry)
                if len(out) >= top_k:
                    return out
    return out


# ----------------------------------------------------------------------
# entry
# ----------------------------------------------------------------------

@dataclass
class Case:
    id: str = ""
    title: str = ""
    citation: str = "TODO — add parallel citations"
    court: str = ""
    year: str = ""
    bench: str = ""
    statutes: list[str] = field(default_factory=list)
    bns_mapping: list[str] = field(default_factory=lambda: ["TODO — editor adds BNS/BNSS mapping"])
    topics: list[str] = field(default_factory=lambda: ["TODO — editor tags topics"])
    facts: str = "TODO — editor or LLM adds 1-paragraph facts"
    issues: list[str] = field(default_factory=lambda: ["TODO — editor adds issues"])
    holding: str = "TODO — editor or LLM adds holding"
    key_paras: str = ""
    subsequent_treatment: str = "TODO — editor adds (followed / overruled / etc.)"
    source_url: str = ""
    full_text: str = ""


def ingest_one(url: str, throttle: bool = True) -> Case:
    url = normalise_doc_url(url)
    html = fetch_html(url)
    if throttle:
        time.sleep(THROTTLE_SECONDS)

    soup = BeautifulSoup(html, "html.parser")
    title = extract_title(soup)
    full_text = extract_paragraph_text(soup)
    court_full, court_short = detect_court(soup, full_text)
    year = detect_year(title, full_text)
    bench = extract_bench(soup, full_text)
    statutes = extract_statutes(full_text)
    key_paras = detect_key_paras(full_text)

    case = Case(
        id=slugify_for_id(title, year, court_short),
        title=title,
        court=court_full,
        year=year,
        bench=bench or "TODO — editor adds bench",
        statutes=statutes or ["TODO — editor identifies statutes"],
        key_paras=key_paras or "TODO — editor identifies key paragraphs",
        source_url=url,
        full_text=full_text,
    )
    return case


def main() -> None:
    ap = argparse.ArgumentParser(description="Headnote — Indian Kanoon ingest")
    ap.add_argument("urls", nargs="*", help="One or more Indian Kanoon URLs")
    ap.add_argument("--file", help="Path to file with one URL per line")
    ap.add_argument("--enrich", action="store_true",
                    help="Use Anthropic API to fill TODO fields (requires ANTHROPIC_API_KEY)")
    ap.add_argument("--out", help="Write to this file instead of stdout")
    args = ap.parse_args()

    urls: list[str] = list(args.urls)
    if args.file:
        with open(args.file) as f:
            urls.extend(line.strip() for line in f if line.strip() and not line.strip().startswith("#"))
    if not urls:
        ap.error("Provide URLs or --file")

    cases: list[dict] = []
    for i, url in enumerate(urls):
        sys.stderr.write(f"[{i+1}/{len(urls)}] {url}\n")
        try:
            case = ingest_one(url, throttle=(i < len(urls) - 1))
            cases.append(asdict(case))
        except Exception as e:
            sys.stderr.write(f"  ✗ {e}\n")

    if args.enrich:
        try:
            from anthropic import Anthropic
        except ImportError:
            sys.exit("--enrich requires: pip install anthropic")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("--enrich requires ANTHROPIC_API_KEY in env")
        cases = _enrich_with_claude(cases)

    out_text = json.dumps(cases, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(out_text, encoding="utf-8")
        sys.stderr.write(f"Wrote {len(cases)} cases to {args.out}\n")
    else:
        print(out_text)


# ----------------------------------------------------------------------
# optional LLM enrichment
# ----------------------------------------------------------------------

ENRICH_SYSTEM = """You are an editor for an Indian criminal-law journal. You will receive a single judgment as JSON (with full_text included). Fill in the TODO fields:
- bns_mapping: array of strings. For each statute reference, note BNS/BNSS/BSA equivalent. Format: "IPC S. 302 → BNS S. 103". For special laws (NI Act, NDPS, PMLA, etc.) note "unaffected by BNS/BNSS".
- topics: array of 4-8 catchword tags (lowercase, hyphenated where multi-word). Example: ["circumstantial evidence", "DNA recovery", "S. 302 IPC", "death penalty"].
- facts: 1 paragraph (60-120 words) summarising case facts.
- issues: array of 1-3 strings, each one issue stated as a question.
- holding: 1 paragraph (50-100 words) capturing what the court actually decided.
- subsequent_treatment: 1-2 sentences. If you cannot determine, write "Not yet determined; editor to research".
- citation: parallel citations including INSC / SCC / AIR / Cri.L.J. if extractable from full_text.

Return ONLY a valid JSON object with the same keys as input. Do not invent facts. If a field is genuinely unknowable from the judgment text, leave the TODO marker."""


def _enrich_with_claude(cases: list[dict]) -> list[dict]:
    from anthropic import Anthropic
    client = Anthropic()
    out = []
    for i, case in enumerate(cases):
        sys.stderr.write(f"  enriching [{i+1}/{len(cases)}] {case['id']}\n")
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2500,
                system=ENRICH_SYSTEM,
                messages=[{"role": "user", "content": json.dumps(case, ensure_ascii=False)}],
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:-1])
            enriched = json.loads(text)
            # preserve full_text and source_url from original
            enriched["full_text"] = case.get("full_text", "")
            enriched["source_url"] = case.get("source_url", "")
            out.append(enriched)
        except Exception as e:
            sys.stderr.write(f"    ✗ enrichment failed: {e}; keeping original\n")
            out.append(case)
    return out


if __name__ == "__main__":
    main()
