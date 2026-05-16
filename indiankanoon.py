"""
Indian Kanoon API helper for Legify.

Provides:
    search_ik(query, max_results, from_date, court) -> list[dict]
    fetch_ik(doc_id)                                -> dict
    expand_query_for_ik(situation, anthropic_client)-> list[str]

Configuration via env vars:
    KANOON_API_TOKEN     (required)

Errors:
    IKError       generic
    IKAuthError   token rejected (401/403)
    IKRateLimit   429
"""

from __future__ import annotations

import os
import re
import json
import requests
from typing import Optional


# -------------------------------------------------------------------- config

KANOON_BASE = "https://api.indiankanoon.org"
TIMEOUT_SEARCH = 30
TIMEOUT_FETCH = 60

# Cheap model for expanding a lawyer's plain-English situation into IK queries
EXPAND_MODEL = "claude-sonnet-4-6"


def _token() -> str:
    tok = os.environ.get("KANOON_API_TOKEN")
    if not tok:
        raise IKAuthError(
            "KANOON_API_TOKEN env var not set. "
            "Add it in Render → Environment, then restart the service."
        )
    return tok


def _headers() -> dict:
    return {
        "Authorization": f"Token {_token()}",
        "Accept": "application/json",
    }


# -------------------------------------------------------------------- errors

class IKError(Exception):
    """Generic Indian Kanoon error."""


class IKAuthError(IKError):
    """Token missing, invalid, or revoked."""


class IKRateLimit(IKError):
    """IK is throttling — back off and retry."""


# -------------------------------------------------------------------- helpers

def _clean_html(raw: str) -> str:
    if not raw:
        return ""
    t = re.sub(r"<[^>]+>", " ", raw)
    t = (
        t.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&#8377;", "₹")
    )
    return re.sub(r"\s+", " ", t).strip()


def _check_status(resp: requests.Response, context: str) -> None:
    if resp.status_code == 200:
        return
    if resp.status_code in (401, 403):
        raise IKAuthError(
            f"{context}: IK token rejected ({resp.status_code}). "
            f"Token may be revoked or invalid."
        )
    if resp.status_code == 429:
        raise IKRateLimit(f"{context}: IK rate-limited (429). Back off and retry.")
    raise IKError(f"{context}: IK returned {resp.status_code} — {resp.text[:200]}")


# -------------------------------------------------------------------- search

def search_ik(
    query: str,
    max_results: int = 5,
    from_date: Optional[str] = None,
    court: Optional[str] = None,
) -> list[dict]:
    """Search Indian Kanoon. Returns judgment summaries."""
    if not query or not query.strip():
        return []

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
    except requests.RequestException as e:
        raise IKError(f"search_ik network error: {e}") from e

    _check_status(resp, "search_ik")
    docs = resp.json().get("docs", [])

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

    return out


# -------------------------------------------------------------------- fetch

def fetch_ik(doc_id: str) -> dict:
    """Fetch full clean text of one judgment."""
    doc_id = str(doc_id).strip()
    if not doc_id.isdigit():
        raise IKError(f"fetch_ik: invalid doc_id '{doc_id}'")

    try:
        resp = requests.post(
            f"{KANOON_BASE}/doc/{doc_id}/",
            headers=_headers(),
            timeout=TIMEOUT_FETCH,
        )
    except requests.RequestException as e:
        raise IKError(f"fetch_ik network error: {e}") from e

    _check_status(resp, f"fetch_ik(doc_id={doc_id})")
    payload = resp.json()
    full_text = _clean_html(payload.get("doc", ""))
    if not full_text:
        raise IKError(f"fetch_ik(doc_id={doc_id}): empty judgment body")

    return {
        "doc_id":     doc_id,
        "title":      _clean_html(payload.get("title", "")),
        "court":      payload.get("docsource", ""),
        "date":       payload.get("publishdate", ""),
        "full_text":  full_text,
        "char_count": len(full_text),
        "url":        f"https://indiankanoon.org/doc/{doc_id}/",
    }


# -------------------------------------------------------------------- expand

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
    """Turn lawyer's situation/topic into 2-3 IK-optimized queries.
    Falls back to [situation] if expansion fails — never crashes the request.
    """
    if not situation or not situation.strip():
        return []

    try:
        msg = anthropic_client.messages.create(
            model=EXPAND_MODEL,
            max_tokens=300,
            system=_EXPAND_SYSTEM,
            messages=[{"role": "user", "content": situation.strip()}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        queries = json.loads(raw)
        if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
            return [q.strip() for q in queries if q.strip()][:3]
    except Exception:
        pass

    return [situation.strip()]


# -------------------------------------------------------------------- compose

def gather_relevant_judgments(
    situation_or_topic: str,
    anthropic_client,
    *,
    max_total: int = 3,
    max_chars_per_doc: int = 40_000,
    from_date: Optional[str] = "2010-01-01",
    court: Optional[str] = "Supreme Court",
) -> list[dict]:
    """High-level: situation/topic in, full-text judgments out.

    1. Expand the input into 2-3 IK search queries (Sonnet).
    2. Run each query; take union; dedupe by doc_id.
    3. Fetch full text for the top `max_total` results.
    4. Truncate each doc to `max_chars_per_doc` to control LLM cost.

    Returns judgment dicts in the shape the prompts expect.
    """
    queries = expand_query_for_ik(situation_or_topic, anthropic_client)
    if not queries:
        return []

    seen: dict[str, dict] = {}
    for q in queries:
        try:
            hits = search_ik(q, max_results=5, from_date=from_date, court=court)
        except IKError:
            continue
        for h in hits:
            if h["doc_id"] not in seen:
                seen[h["doc_id"]] = h
            if len(seen) >= max_total * 3:  # gather extra, trim after
                break
        if len(seen) >= max_total * 3:
            break

    # Take the first max_total in insertion order (already rank-prioritized
    # because IK returns by relevance and we process top-results queries first)
    picks = list(seen.values())[:max_total]

    judgments = []
    for p in picks:
        try:
            full = fetch_ik(p["doc_id"])
        except IKError:
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

    return judgments


def _year_from_date(date_str: str) -> Optional[int]:
    if not date_str:
        return None
    m = re.search(r"(19|20)\d{2}", date_str)
    return int(m.group(0)) if m else None


# -------------------------------------------------------------------- smoke

if __name__ == "__main__":
    print("Smoke-testing indiankanoon.py …")
    print("-" * 60)
    print("\n[1] search_ik for 'Section 482 CrPC quashing'")
    try:
        hits = search_ik(
            "Section 482 CrPC quashing Supreme Court",
            max_results=3, from_date="2020-01-01", court="Supreme Court",
        )
        for h in hits:
            print(f"   - {h['doc_id']:>10}  {h['date']}  {h['title'][:60]}")
    except IKError as e:
        print(f"   ERROR: {e}")
        raise SystemExit(1)
    if not hits:
        print("   No hits. Investigate.")
        raise SystemExit(1)

    print(f"\n[2] fetch_ik for doc_id={hits[0]['doc_id']}")
    try:
        case = fetch_ik(hits[0]["doc_id"])
        print(f"   title:      {case['title'][:70]}")
        print(f"   court:      {case['court']}")
        print(f"   char_count: {case['char_count']:,}")
        print(f"   preview:    {case['full_text'][:160]}…")
    except IKError as e:
        print(f"   ERROR: {e}")
        raise SystemExit(1)

    print("\n✓ IK helper working. Ready to wire into endpoints.")
