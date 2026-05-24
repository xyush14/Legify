"""POST /api/memorandum — produces a lexlegis.ai-style two-tier research note.

The output mirrors the structure used by Lexlegis: a quick Tier-1 Brief
(Understanding / Provisions table / Concepts / Question), followed by a
full Tier-2 IRAC Memorandum (Issues, Applicable Law, Analysis, Recommendations).

Pipeline:
  1. Accept Hindi/English/Hinglish question
  2. Retrieve relevant corpus cases (use_corpus=True; default)
  3. Build memo prompt with corpus summary
  4. Call LLM (Sonnet via Anthropic, or DeepSeek-Reasoner via primary path)
  5. Return structured JSON

Auth: required. Gated under `draft` feature (same quota bucket as drafting).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from headnote import config
from headnote.api.models import MemorandumRequest
from headnote.entitlements import CurrentUser, check_and_record, get_current_user
from headnote.llm import (
    build_memorandum_system_prompt,
    build_memorandum_user,
    parse_json_response,
    build_meta,
    call_claude_cached,
    SONNET_MODEL,
)


log = logging.getLogger(__name__)
router = APIRouter(tags=["research"])


def _build_corpus_summary(corpus_cases: list[dict], max_cases: int = 8) -> str:
    """Render retrieved corpus cases as a compact text block the LLM can
    consume as primary authorities. Each case: 2-3 lines with citation +
    one-line gist + paragraph anchor (if any).
    """
    if not corpus_cases:
        return ""
    lines: list[str] = []
    for i, c in enumerate(corpus_cases[:max_cases], start=1):
        title = c.get("title") or c.get("name") or "(untitled)"
        citation = c.get("citation") or c.get("year") or ""
        court = c.get("court") or ""
        gist = c.get("gist") or c.get("summary") or c.get("ratio") or ""
        anchor = c.get("paragraph_anchor") or ""
        lines.append(
            f"[{i}] {title} — {citation} — {court}\n    Gist: {gist[:280]}"
            + (f"\n    Anchor: {anchor}" if anchor else "")
        )
    return "\n\n".join(lines)


def _retrieve_corpus_for_memo(question: str, jurisdiction: str) -> list[dict]:
    """Best-effort corpus retrieval for the memo. Reuses the existing
    situation retrieval pipeline so we don't reimplement ranking.

    Returns a list of {case_id, title, citation, court, gist, paragraph_anchor}.
    Empty list if retrieval fails — memo still works, just without grounded
    citations.
    """
    try:
        from headnote.kanoon.retrieval import retrieve_for_situation
        from headnote.kanoon.client import KanoonClient
        from headnote.refine import shallow_refine

        # Load curated corpus
        try:
            curated = config.load_curated_corpus()
        except Exception:
            curated = []

        # Cheap upstream parse to populate refined query envelope
        try:
            refined = shallow_refine(question)
            refined_dict = refined.to_dict() if hasattr(refined, "to_dict") else None
        except Exception:
            refined_dict = None

        # If IK token configured, use full retrieval; else fall back to curated only
        try:
            client = KanoonClient()
        except Exception:
            client = None

        if client is None:
            # Curated-only path
            return [
                {
                    "case_id": c.get("case_id", ""),
                    "title":   c.get("title", ""),
                    "citation": c.get("citation", ""),
                    "court":   c.get("court", ""),
                    "gist":    (c.get("practitioner_notes") or {}).get("gist", ""),
                    "paragraph_anchor": "",
                }
                for c in curated[:8]
            ]

        ret = retrieve_for_situation(
            question,
            client=client,
            curated_corpus=curated,
            refined_query=refined_dict,
            mode="mixed",
            jurisdiction=jurisdiction or "India",
        )
        return [
            {
                "case_id": case.get("case_id", ""),
                "title":   case.get("title", ""),
                "citation": case.get("citation", ""),
                "court":   case.get("court", ""),
                "gist":    case.get("gist") or case.get("snippet") or "",
                "paragraph_anchor": case.get("paragraph_anchor", ""),
            }
            for case in (ret.cases if hasattr(ret, "cases") else [])[:8]
        ]
    except Exception as e:
        log.warning("[memo] corpus retrieval failed (continuing without): %s", e)
        return []


@router.post("/api/memorandum", summary="Two-tier legal research memorandum (lexlegis-style)")
def api_memorandum(
    req: MemorandumRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Generate a Quick Brief + Deep IRAC Memorandum for the lawyer's question.

    Pipeline:
      Hindi/English question
        → corpus retrieval (best-effort)
        → memo system prompt (with corpus cases as primary authorities)
        → LLM call (Sonnet preferred; DeepSeek-Reasoner if Anthropic out of credit)
        → JSON parse + structured response
    """
    started = time.time()

    # Quota gate: charge as 'draft' for now (drafts and memos are similar work).
    with check_and_record(
        user.id, "draft", endpoint="memorandum", email=user.email,
    ) as record:
        # Step 1: retrieve corpus if requested
        corpus_cases: list[dict] = []
        if req.use_corpus:
            corpus_cases = _retrieve_corpus_for_memo(
                req.question, req.jurisdiction or "India"
            )

        corpus_summary = _build_corpus_summary(corpus_cases)
        corpus_json = (
            json.dumps(corpus_cases, ensure_ascii=False, indent=2)
            if corpus_cases else ""
        )

        # Step 2: build prompts
        system_prompt = build_memorandum_system_prompt(corpus_json=corpus_json)
        user_prompt = build_memorandum_user(
            situation=req.question,
            corpus_summary=corpus_summary,
            jurisdiction=req.jurisdiction or "India",
            stage=req.stage or "pre-trial",
        )

        # Step 3: LLM call — Sonnet by default; client.py auto-routes to
        # DeepSeek-Reasoner when Anthropic has no credit OR when
        # LLM_PROVIDER=deepseek is set.
        try:
            raw, usage = call_claude_cached(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=SONNET_MODEL,
                max_tokens=8000,
                cache=True,
                enable_thinking=False,
            )
        except HTTPException:
            raise
        except Exception as e:
            log.exception("[memo] LLM call failed: %s", e)
            raise HTTPException(
                status_code=503,
                detail=f"Memorandum LLM call failed: {str(e)[:200]}",
            )

        # Step 4: parse JSON
        try:
            parsed = parse_json_response(raw)
        except HTTPException:
            # Sometimes models add prose before JSON — try a best-effort extract
            try:
                start = raw.index("{")
                end = raw.rindex("}") + 1
                parsed = json.loads(raw[start:end])
            except Exception:
                raise

        elapsed = time.time() - started
        meta = build_meta(usage, elapsed)

        # Record cost for entitlement event
        record(cost_paise=int(meta.get("cost_inr", 0) * 100), model=usage.get("model"))

        return {
            "memorandum": parsed,
            "corpus_cases_used": [
                {"case_id": c.get("case_id"), "title": c.get("title"),
                 "citation": c.get("citation")}
                for c in corpus_cases
            ],
            "meta": meta,
        }
