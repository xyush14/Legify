#!/usr/bin/env python3
"""
End-to-end smoke test for the IK pipeline: search -> fetch -> parse -> cache.

Uses two cases that are also in cases.json so we can sanity-check the parsed
output against our hand-curated ground truth:
  - K. Bhaskaran v. Sankaran Vaidhyan Balan (1999)            tid=529907
  - Dashrath Rupsingh Rathod v. State of Maharashtra (2014)   tid=100995424

Run: .venv/bin/python smoke_test_kanoon.py
Cost: ~0 — both cases get cached on first run; reruns are free.

Exits 0 on pass, non-zero on any failed check.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

from headnote.kanoon.client import KanoonClient, KanoonError
from headnote.kanoon.parser import parse_judgment


# --- known anchors

KNOWN_CASES = [
    # (tid, expected_corpus_id, query, expected_title_substring, min_paragraphs,
    #  modern: True iff IK populates author+case_number for this vintage)
    (529907,    "BHASK-1999-SC", "K Bhaskaran cheque dishonour 1999",       "Bhaskaran",      15, False),
    (100995424, "DASH-2014-SC",  "Dashrath Rupsingh Rathod cheque 2014",    "Dashrath",       40, True),
]


def green(s: str) -> str: return f"\033[32m{s}\033[0m"
def red(s: str) -> str: return f"\033[31m{s}\033[0m"
def yellow(s: str) -> str: return f"\033[33m{s}\033[0m"


fail_count = 0
def check(cond: bool, msg: str) -> None:
    global fail_count
    if cond:
        print(f"  {green('PASS')} {msg}")
    else:
        print(f"  {red('FAIL')} {msg}")
        fail_count += 1


def info(cond: bool, msg: str) -> None:
    """Soft check: report status but don't fail the build. For honest data
    limits (e.g. older judgments lacking author/case_number markup)."""
    label = green('OK ') if cond else yellow('n/a')
    print(f"  {label}  {msg}")


def section(title: str) -> None:
    print(f"\n{'='*72}\n{title}\n{'='*72}")


def main() -> int:
    section("0. Init client (token from .env)")
    try:
        client = KanoonClient()
    except KanoonError as e:
        print(red(f"FATAL: {e}"))
        return 2
    print(f"  cache: {client.cache_path}")
    stats_before = client.cache_stats()
    print(f"  before: {stats_before['search_pages_cached']} search pages, "
          f"{stats_before['documents_cached']} docs cached")

    # ------------------------------------------------------------------ search
    section("1. Search: find a known landmark, confirm ranking signals present")
    query = "K. Bhaskaran cheque dishonour"
    t0 = time.time()
    page = client.search(query)
    print(f"  query: {query!r}  -> {len(page.hits)} hits  ({time.time()-t0:.2f}s)")
    check(len(page.hits) > 0, "search returns >=1 hit")
    if page.hits:
        top_by_citedby = max(page.hits, key=lambda h: h.numcitedby)
        print(f"  top by citation weight: tid={top_by_citedby.tid} "
              f"citedby={top_by_citedby.numcitedby}  '{top_by_citedby.title[:60]}'")
        check(top_by_citedby.numcitedby > 100,
              "numcitedby is a real ranking signal (top hit cited >100 times)")

    # ----------------------------------------------------------------- fetch+parse
    corpus = json.loads(Path("cases.json").read_text())
    corpus_by_id = {c["id"]: c for c in corpus}

    for tid, corpus_id, _query, title_sub, min_paras, modern in KNOWN_CASES:
        section(f"2. Fetch + parse: tid={tid}  (corpus id: {corpus_id})")
        t0 = time.time()
        doc = client.get_doc(tid)
        fetch_time = time.time() - t0
        print(f"  fetch: html_len={len(doc.doc_html):,}  ({fetch_time:.2f}s)")
        check(len(doc.doc_html) > 5000, "fetched HTML is substantial")
        check(title_sub.lower() in doc.title.lower(),
              f"title contains {title_sub!r}: {doc.title[:80]!r}")

        t0 = time.time()
        parsed = parse_judgment(
            doc.doc_html,
            tid=tid,
            title_hint=doc.title,
            court_hint=doc.docsource,
            publishdate_hint=doc.publishdate,
        )
        print(f"  parse: {len(parsed.paragraphs)} paragraphs  ({time.time()-t0:.2f}s)")

        # --- hard checks (must pass for the pipeline to be load-bearing)
        check(len(parsed.paragraphs) >= min_paras,
              f"parsed >= {min_paras} paragraphs (got {len(parsed.paragraphs)})")
        check(len(parsed.parallel_citations) >= 3,
              f"parsed >= 3 parallel citations (got {len(parsed.parallel_citations)})")
        check(bool(parsed.primary_citation), "primary citation chosen")
        check(len(parsed.bench) >= 2, f"bench has >=2 judges (got {parsed.bench})")
        check(len(parsed.statutes) >= 1,
              f"statutes detected (got {len(parsed.statutes)}, first: {parsed.statutes[:2]})")

        # --- soft checks (data limits on older judgments — IK doesn't markup these consistently)
        if modern:
            check(bool(parsed.author_judge),
                  f"author judge identified: {parsed.author_judge}")
            check(bool(parsed.case_number),
                  f"case number parsed: {parsed.case_number!r}")
        else:
            info(bool(parsed.author_judge),
                 f"author judge (IK markup often absent pre-2010): {parsed.author_judge}")
            info(bool(parsed.case_number),
                 f"case number (often absent in IK older preambles): {parsed.case_number!r}")

        # --- structural annotations
        struct_counts = Counter(p.structure for p in parsed.paragraphs)
        print(f"  structures: {dict(struct_counts)}")
        check(struct_counts.get("conclusion", 0) >= 1,
              "at least one 'conclusion' paragraph")
        check(struct_counts.get("precedent", 0) >= 1,
              "at least one 'precedent' paragraph (for cases-referred)")

        # --- preview most useful paragraphs
        conc = parsed.conclusion_paragraphs()
        if conc:
            preview = conc[0].text[:200].replace("\n", " ")
            print(f"  conclusion[0]: {conc[0].anchor()}  {preview!r}...")

        # --- compare to curated corpus entry where possible
        corpus_entry = corpus_by_id.get(corpus_id)
        if corpus_entry:
            curated_title = corpus_entry["title"]
            check(
                _name_match(parsed.title, curated_title),
                f"parsed title matches corpus ({parsed.title!r} ~ {curated_title!r})"
            )
            curated_bench = corpus_entry.get("bench", "")
            # rough sanity check: at least one judge name from bench list appears in curated bench string
            if parsed.bench:
                any_judge = any(
                    _last_name(j) in curated_bench for j in parsed.bench if j
                )
                check(any_judge,
                      f"at least one parsed judge appears in curated bench")

    # ---------------------------------------------------------------- cache 2nd run
    section("3. Cache is doing its job (repeat fetch should be instant)")
    for tid, *_rest in KNOWN_CASES:
        t0 = time.time()
        client.get_doc(tid)
        ms = (time.time() - t0) * 1000
        print(f"  tid={tid} cached fetch: {ms:.1f}ms")
        check(ms < 30, f"cached fetch under 30ms (was {ms:.1f}ms)")

    stats_after = client.cache_stats()
    print(f"\nfinal cache: {stats_after['search_pages_cached']} search pages, "
          f"{stats_after['documents_cached']} docs, "
          f"{stats_after['cache_size_bytes']/1024:.1f} KB on disk")

    # ----------------------------------------------------------------- summary
    section("RESULT")
    if fail_count == 0:
        print(green(f"All checks passed."))
        return 0
    print(red(f"{fail_count} check(s) failed."))
    return 1


def _name_match(a: str, b: str) -> bool:
    """Loose match: ignore punctuation/case, both contain the first-party name."""
    norm = lambda s: " ".join(s.lower().split())
    first_party_a = norm(a).split(" v.")[0]
    first_party_b = norm(b).split(" v.")[0]
    return first_party_a in first_party_b or first_party_b in first_party_a


def _last_name(judge: str) -> str:
    """Return the most distinctive token of a judge's name for fuzzy matching."""
    parts = [p for p in judge.replace(",", " ").split() if len(p) > 2]
    return parts[-1] if parts else judge


if __name__ == "__main__":
    sys.exit(main())
