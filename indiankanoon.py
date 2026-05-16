"""
Indian Kanoon API helper for Legify — WITH DEBUG LOGGING.

Every call prints to stdout so Render Logs shows what's happening.
Once we find the bug, we can remove the print() statements.
"""

from __future__ import annotations

import os
import re
import sys
import json
import requests
from typing import Optional


KANOON_BASE = "https://api.indiankanoon.org"
TIMEOUT_SEARCH = 30
TIMEOUT_FETCH = 60
EXPAND_MODEL = "claude-sonnet-4-6"


def _log(msg: str) -> None:
    """Force flush so Render Logs sees it immediately."""
    print(f"[ik] {msg}", flush=True)
    sys.stdout.flush()


def _token() -> str:
    tok = os.environ.get("KANOON_API_TOKEN")
    if not tok:
        _log("ERROR: KANOON_API_TOKEN env var is empty or not set!")
        raise IKAuthError(
            "KANOON_API_TOKEN env var not set. "
            "Add it in Render → Environment, then restart the service."
        )
    _log(f"token loaded, first 8 chars: {tok[:8]}...")
    return tok


def _headers() -> dict:
    return {
        "Authorization": f"Token {_token()}",
        "Accept": "application/json",
    }


class IKError(Exception):
    pass


class IKAuthError(IKError):
    pass


class IKRateLimit(IKError):
    pass


def _clean_html(raw: str) -> str:
    if not raw:
        return ""
    t = re.sub(r"<[^>]+>", " ", raw)
    t = (t.replace("&amp;", "&")
          .replace("&lt;", "<")
          .replace("&gt;", ">")
          .replace("&nbsp;", " ")
          .replace("&quot;", '"')
          .replace("&#39;", "'")
          .replace("&#8377;", "₹"))
    return re.sub(r"\s+", " ", t).strip()


def _check_status(resp: requests.Response, context: str) -> None:
    if resp.status_code == 200:
        return
    _log(f"ERROR: {context} returned HTTP {resp.status_code}")
    _log(f"       body: {resp.text[:300]}")
    if resp.status_code in (401, 403):
        raise IKAuthError(f"{context}: IK token rejected ({resp.status_code})")
    if resp.status_code == 429:
        raise IKRateLimit(f"{context}: IK rate-limited (429)")
    raise IKError(f"{context}: IK returned {resp.status_code} — {resp.text[:200]}")


def search_ik(
    query: str,
    max_results: int = 5,
    from_date: Optional[str] = None,
    court: Optional[str] = None,
) -> list[dict]:
    if not query or not query.strip():
        _log("search_ik called with empty query, returning []")
        return []

    _log(f"search_ik: query='{query}' from_date={from_date} court={court}")

    data = {"formInput": query.strip(), "pagenum": 0}
    if from_date:
        data["fromdate"] = from_date

    try:
        resp = requests.post(
            f"{KANOON_BASE}/search/",
            headers=_headers(),
            data=data,
            timeout=TIMEOUT_SEARCH,
        )
        _log(f"search_ik HTTP status: {resp.status_code}, body length: {len(resp.text)}")
    except requests.RequestException as e:
        _log(f"search_ik network error: {e}")
        raise IKError(f"search_ik network error: {e}") from e

    _check_status(resp, "search_ik")

    try:
        payload = resp.json()
    except Exception as e:
        _log(f"search_ik JSON parse failed: {e}")
        _log(f"       raw body: {resp.text[:500]}")
        raise IKError(f"search_ik: bad JSON from IK") from e

    docs = payload.get("docs", [])
    _log(f"search_ik: IK returned {len(docs)} raw docs")

    out = []
    for d in docs:
        doc_id = str(d.get("tid", "")).strip()
        if not doc_id:
            continue
        court_name = d.get("docsource", "") or ""
        if court and court.lower() not in court_name.lower():
            continue
        out.append({
            "doc_id":  doc_id,
            "title":   _clean_html(d.get("title", "")),
            "court":   court_name,
            "date":    d.get("publishdate", ""),
            "snippet": _clean_html(d.get("headline", "")),
            "url":     f"https://indiankanoon.org/doc/{doc_id}/",
        })
        if len(out) >= max_results:
            break

    _log(f"search_ik returning {len(out)} filtered results")
    return out


def fetch_ik(doc_id: str) -> dict:
    doc_id = str(doc_id).strip()
    _log(f"fetch_ik: doc_id={doc_id}")
    if not doc_id.isdigit():
        raise IKError(f"fetch_ik: invalid doc_id '{doc_id}'")

    try:
        resp = requests.post(
            f"{KANOON_BASE}/doc/{doc_id}/",
            headers=_headers(),
            timeout=TIMEOUT_FETCH,
        )
        _log(f"fetch_ik HTTP status: {resp.status_code}")
    except requests.RequestException as e:
        _log(f"fetch_ik network error: {e}")
        raise IKError(f"fetch_ik network error: {e}") from e

    _check_status(resp, f"fetch_ik(doc_id={doc_id})")
    payload = resp.json()
    full_text = _clean_html(payload.get("doc", ""))
    if not full_text:
        _log(f"fetch_ik: empty judgment body for doc_id={doc_id}")
        raise IKError(f"fetch_ik: empty judgment body")

    _log(f"fetch_ik: got {len(full_text)} chars for doc_id={doc_id}")
    return {
        "doc_id":     doc_id,
        "title":      _clean_html(payload.get("title", "")),
        "court":      payload.get("docsource", ""),
        "date":       payload.get("publishdate", ""),
        "full_text":  full_text,
        "char_count": len(full_text),
        "url":        f"https://indiankanoon.org/doc/{doc_id}/",
    }


_EXPAND_SYSTEM = """You convert an Indian criminal advocate's plain-English description of a legal situation, OR a doctrinal topic, into 2-3 search queries optimized for the Indian Kanoon search engine.

Rules:
- Output ONLY a JSON array of 2-3 strings. No prose, no markdown.
- Each query: 3-8 words, focused on statute sections + key doctrinal terms.
- Use Indian statute references: "Section 482 CrPC", "Section 498A IPC", "BNS 2023", "BNSS 2023", "PMLA", "NDPS", "POCSO", "S. 138 NI Act", etc.
- Cover different angles (different sections, different sub-issues, different doctrinal labels).
- Include "Supreme Court" unless the situation indicates a specific High Court.

Example input:
"My client is accused under 498A and the FIR seems malicious, we want to quash"

Example output:
["Section 482 CrPC quashing FIR 498A Supreme Court", "malicious prosecution 498A IPC quashing", "Bhajan Lal categories quashing FIR Supreme Court"]"""


def expand_query_for_ik(situation: str, anthropic_client) -> list[str]:
    if not situation or not situation.strip():
        return []

    _log(f"expand_query_for_ik input: '{situation[:80]}...'")

    try:
        msg = anthropic_client.messages.create(
            model=EXPAND_MODEL,
            max_tokens=300,
            system=_EXPAND_SYSTEM,
            messages=[{"role": "user", "content": situation.strip()}],
        )
        raw = msg.content[0].text.strip()
        _log(f"expand_query_for_ik raw response: {raw[:200]}")
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        queries = json.loads(raw)
        if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
            result = [q.strip() for q in queries if q.strip()][:3]
            _log(f"expand_query_for_ik produced: {result}")
            return result
    except Exception as e:
        _log(f"expand_query_for_ik FAILED: {type(e).__name__}: {e}")

    _log(f"expand_query_for_ik fallback to raw input")
    return [situation.strip()]


def gather_relevant_judgments(
    situation_or_topic: str,
    anthropic_client,
    *,
    max_total: int = 3,
    max_chars_per_doc: int = 40_000,
    from_date: Optional[str] = "2010-01-01",
    court: Optional[str] = "Supreme Court",
) -> list[dict]:
    _log("=" * 60)
    _log(f"gather_relevant_judgments START")
    _log(f"  input: '{situation_or_topic[:100]}'")
    _log(f"  court filter: {court}, from_date: {from_date}")

    queries = expand_query_for_ik(situation_or_topic, anthropic_client)
    _log(f"  queries to run: {queries}")

    if not queries:
        _log("  no queries — returning []")
        return []

    seen: dict[str, dict] = {}
    for q in queries:
        try:
            hits = search_ik(q, max_results=5, from_date=from_date, court=court)
            _log(f"  query '{q}' -> {len(hits)} hits after court filter")
        except IKError as e:
            _log(f"  query '{q}' FAILED: {e}")
            continue
        for h in hits:
            if h["doc_id"] not in seen:
                seen[h["doc_id"]] = h
            if len(seen) >= max_total * 3:
                break
        if len(seen) >= max_total * 3:
            break

    _log(f"  total unique judgments collected: {len(seen)}")
    picks = list(seen.values())[:max_total]
    _log(f"  fetching full text for top {len(picks)}")

    judgments = []
    for p in picks:
        try:
            full = fetch_ik(p["doc_id"])
        except IKError as e:
            _log(f"  fetch failed for {p['doc_id']}: {e}")
            continue
        text = full["full_text"]
        if len(text) > max_chars_per_doc:
            text = text[:max_chars_per_doc] + "\n\n[...judgment truncated for length...]"
        judgments.append({
            "case_id":   f"ik_{full['doc_id']}",
            "title":     full["title"] or p["title"],
            "court":     full["court"] or p["court"],
            "date":      full["date"] or p["date"],
            "url":       full["url"],
            "full_text": text,
            "year":      _year_from_date(full["date"] or p["date"]),
        })

    _log(f"gather_relevant_judgments END — returning {len(judgments)} judgments")
    _log("=" * 60)
    return judgments


def _year_from_date(date_str: str) -> Optional[int]:
    if not date_str:
        return None
    m = re.search(r"(19|20)\d{2}", date_str)
    return int(m.group(0)) if m else None
