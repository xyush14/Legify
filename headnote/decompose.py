"""Query decomposition.

Given a lawyer's English query, produce two parallel sub-queries (one for
case-law retrieval, one for statute lookup) and a one-line "researching: ..."
summary. Powers the transparency panel in the app UI.

Architectural notes:
  - Single Sonnet call, max ~250 output tokens → ~₹1.50 per query.
  - Failures fall back to a deterministic summary built from the query
    itself; never blocks the main pipeline.
  - The summary is what users actually see; sub-queries are debug detail.
"""

from __future__ import annotations

import json
import re
from typing import Optional, TypedDict

from headnote import config


class Decomposition(TypedDict):
    judgments_query: str
    statute_query: str
    user_facing_summary: str
    cost_paise: int


_SYSTEM_PROMPT = """You are preparing an Indian legal research query (criminal OR civil) for retrieval. Given the user's question, generate TWO focused sub-queries plus a one-line summary.

Return STRICT JSON only:
{
  "judgments_query": "A natural-language sub-query optimised for retrieving relevant precedents. Mention the legal question, fact pattern, and procedural stage if implied. 1-3 sentences.",
  "statute_query": "The specific sections the matter engages — BNS/BNSS/IEA/CrPC for criminal; the governing civil Act for civil matters (e.g. Transfer of Property Act 1882, Specific Relief Act 1963, Contract Act 1872, CPC, Registration Act 1908, Limitation Act 1963). Cite section numbers precisely. 1-2 sentences.",
  "user_facing_summary": "A single lowercase sentence describing what is being researched. Plain English. No marketing language. Example: 'researching s.125 crpc maintenance denials on living-in-adultery grounds and high-court revisional powers.'"
}

Rules:
- Do not invent facts not in the input.
- If the query is too vague to decompose meaningfully, set both sub-queries to the original query and the summary to "researching the broad question — narrow your query for better results."
- The two sub-queries should target different retrievers; do not duplicate.
- No preamble, no markdown fences, no prose outside the JSON object."""


def _fallback(query: str) -> Decomposition:
    """Cheap deterministic summary when the LLM call is unavailable or fails."""
    one_line = re.sub(r"\s+", " ", query).strip()
    if len(one_line) > 140:
        one_line = one_line[:137] + "..."
    return {
        "judgments_query": one_line,
        "statute_query": one_line,
        "user_facing_summary": f"researching: {one_line.lower()}",
        "cost_paise": 0,
    }


def decompose(query: str) -> Decomposition:
    """Run the decomposition. Never raises — always returns a usable dict."""
    if not config.ANTHROPIC_API_KEY or not query.strip():
        return _fallback(query)

    try:
        from headnote.llm import route_call
    except Exception:
        return _fallback(query)

    try:
        result = route_call(
            "extraction",  # cheap Haiku tier; decomposition doesn't need Sonnet quality
            {
                "system_prompt": _SYSTEM_PROMPT,
                "user_prompt": f"INPUT:\n{query}\n\nReturn JSON only.",
                "cache": True,  # system prompt is static
            },
        )
    except Exception as e:
        print(f"[decompose] route_call failed ({e}); using fallback")
        return _fallback(query)

    raw = (result.response or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except Exception as e:
        print(f"[decompose] non-JSON response ({e}); using fallback")
        fb = _fallback(query)
        fb["cost_paise"] = result.cost_paise
        return fb

    return {
        "judgments_query": str(parsed.get("judgments_query") or query).strip(),
        "statute_query": str(parsed.get("statute_query") or query).strip(),
        "user_facing_summary": str(
            parsed.get("user_facing_summary") or f"researching: {query.lower()}"
        ).strip(),
        "cost_paise": result.cost_paise,
    }
