"""
Headnote — FastAPI application.

Endpoints
---------
GET  /                     marketing landing page
GET  /app                  research tool UI
GET  /api/health           liveness + config summary
GET  /api/corpus           slim list of curated cases
GET  /api/spend            IK API cost ledger (today + lifetime)
POST /api/situation        situation -> 3-5 relevant cases w/ verified citations
POST /api/digest           topic    -> research digest
POST /api/headnote         judgment text -> Cri.L.J. headnote(s)
POST /api/translate        any English JSON result -> Hindi
POST /api/feedback         lawyer thumbs-up / down + comment

Architecture
------------
- Curated corpus: hand-vetted cases.json (highest trust).
- IK-backed retrieval (USE_IK_RETRIEVAL=1): semantic search over locally
  embedded paragraphs + on-demand IK fetches. See headnote.kanoon.retrieval.
- Verification: every cited case_id, paragraph anchor, and quoted phrase
  is checked against the source paragraphs the LLM was shown. See
  headnote.verify.
- Regeneration: if verification fails, one retry with targeted feedback.

All settings come from headnote.config (env-driven; .env is auto-loaded).
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from headnote import __version__, config
from headnote.api.models import (
    SituationRequest, DigestRequest, HeadnoteRequest,
    TranslateRequest, FeedbackRequest,
)
from headnote.llm import (
    build_situation_system_prompt, SITUATION_USER_TEMPLATE,
    build_digest_system_prompt, DIGEST_USER_TEMPLATE,
    HEADNOTE_SYSTEM_PROMPT, HEADNOTE_USER_TEMPLATE,
    HEADNOTE_VERIFY_SYSTEM_PROMPT, HEADNOTE_VERIFY_USER_TEMPLATE,
    parse_json_response,
    route_call, build_router_meta, OPUS_MODEL,
)
from headnote.retrieval.keyword import prefilter_cases
from headnote.translate import translate_payload, translate_payload_haiku
from headnote.translate_input import maybe_translate
from headnote.decompose import decompose as decompose_query
from headnote.verify import (
    EvidenceParagraph, verify_situation_response, build_regen_feedback,
)
from headnote.api.telemetry import init_telemetry_db, record_query
from headnote.api.admin import router as admin_router


# ----- Helpers shared by /api/situation and /api/browse -----

def _kanoon_doc_id_from_case_id(case_id: str) -> Optional[str]:
    """Extract numeric IK doc id from an internal case_id ('ik:529907' → '529907').
    Returns None for curated case_ids that don't carry an IK id directly."""
    if isinstance(case_id, str) and case_id.startswith("ik:"):
        return case_id.split(":", 1)[1]
    return None


def _fame_indicator(numcitedby: int) -> str:
    """Map raw IK citation count to the three-bucket label used in the UI."""
    if numcitedby is None:
        return "unknown"
    if numcitedby >= 50:
        return "famous"
    if numcitedby >= 10:
        return "lesser-known"
    return "obscure"


def _enrich_case(case: dict, meta_by_id: dict) -> dict:
    """Attach kanoon_doc_id, kanoon_url, kanoon_paragraph_url, fame_indicator,
    numcitedby, source to a single case dict produced by the LLM. Non-destructive —
    overwrites only when we have better data.

    Pulls paragraph_anchor out of the nested journal_headnote block if the LLM
    placed it there (per the prompt schema), so the deep-link helper can use it.
    """
    cid = case.get("case_id")
    meta = meta_by_id.get(cid) or {}
    case["source"] = meta.get("source", case.get("source") or "ik")

    # Anchor may live at top level OR nested under journal_headnote (journal style)
    anchor = (
        case.get("paragraph_anchor")
        or (case.get("journal_headnote") or {}).get("paragraph_anchor")
        or ""
    )
    if anchor and "paragraph_anchor" not in case:
        case["paragraph_anchor"] = anchor

    kdoc = meta.get("kanoon_doc_id") or _kanoon_doc_id_from_case_id(cid or "")
    if kdoc:
        case["kanoon_doc_id"] = str(kdoc)
        case["kanoon_url"] = f"https://indiankanoon.org/doc/{kdoc}/"
        if anchor:
            tok = re.sub(r"^[\(\s]*Para[s]?[\s\.]*", "", anchor, flags=re.IGNORECASE).rstrip(") ").strip()
            # Para anchors can list multiple ("14, 16-17"); take the first
            tok = re.split(r"[,\s]", tok, maxsplit=1)[0]
            if tok:
                case["kanoon_paragraph_url"] = f"https://indiankanoon.org/doc/{kdoc}/#{tok}"
    if "numcitedby" not in case and "numcitedby" in meta:
        case["numcitedby"] = meta["numcitedby"]
    if "fame_indicator" not in case:
        # Curated cases have no IK citation count, so the "obscure" bucket would
        # be misleading. Label them as curated to signal editorial provenance.
        if case["source"] == "curated":
            case["fame_indicator"] = "curated"
        else:
            case["fame_indicator"] = _fame_indicator(case.get("numcitedby") or meta.get("numcitedby") or 0)
    return case


# Lazy IK client singleton — only spun up if enabled AND token is configured.
_kanoon_client_singleton = None


def _get_kanoon_client():
    """Return a shared KanoonClient, or None if disabled / not configured.

    Module-level singleton so the SQLite cache connection + cost ledger stay
    consistent across requests within one worker process.
    """
    global _kanoon_client_singleton
    if _kanoon_client_singleton is not None:
        return _kanoon_client_singleton
    if not config.USE_IK_RETRIEVAL:
        return None
    if not config.INDIAN_KANOON_TOKEN:
        print("[warn] USE_IK_RETRIEVAL=1 but INDIAN_KANOON_TOKEN not set; staying on curated-only")
        return None
    from headnote.kanoon.client import KanoonClient
    try:
        _kanoon_client_singleton = KanoonClient()
        print(f"[info] IK retrieval enabled; daily cap ₹{_kanoon_client_singleton.daily_cap_inr}")
    except Exception as e:
        print(f"[warn] IK client init failed ({e}); staying on curated-only")
        _kanoon_client_singleton = None
    return _kanoon_client_singleton


def _filtered_corpus_json(query: str, *, top_k: Optional[int] = None) -> str:
    """JSON of the top-K most relevant curated cases. Used in the curated-only
    path and as a fallback for digest mode (which doesn't go through IK yet)."""
    cases = prefilter_cases(
        config.load_curated_corpus(), query,
        top_k=top_k or config.PREFILTER_TOP_K,
    )
    return json.dumps(cases, ensure_ascii=False)


def _init_feedback_db() -> None:
    """Best-effort feedback DB init. Skips silently on read-only filesystems
    (e.g. Render's ephemeral disk after a restart)."""
    try:
        conn = sqlite3.connect(config.FEEDBACK_DB)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                mode TEXT NOT NULL,
                input_text TEXT NOT NULL,
                output_json TEXT NOT NULL,
                rating INTEGER NOT NULL,
                correction TEXT,
                lawyer_handle TEXT
            )"""
        )
        conn.commit()
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"[warn] feedback DB unavailable ({e}); /api/feedback will return errors.")


def _is_strictly_better(retry_report, original_report) -> bool:
    """True iff retry has strictly fewer failing citations than original."""
    n_retry_fail = sum(1 for f in retry_report.findings if not f.is_clean())
    n_orig_fail = sum(1 for f in original_report.findings if not f.is_clean())
    n_retry_orphans = len(retry_report.orphan_case_ids)
    n_orig_orphans = len(original_report.orphan_case_ids)
    return (n_retry_fail < n_orig_fail) or \
           (n_retry_fail == n_orig_fail and n_retry_orphans < n_orig_orphans)


# ============================================================================
# App + routes
# ============================================================================

app = FastAPI(title="Headnote", version=__version__,
              description="Verified AI legal research for Indian criminal advocates.")
_init_feedback_db()
init_telemetry_db()
app.include_router(admin_router)


@app.get("/", include_in_schema=False)
def landing():
    return FileResponse(config.STATIC_DIR / "landing.html")


@app.get("/app", include_in_schema=False)
@app.get("/app/", include_in_schema=False)
def app_index():
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/api/health", summary="Liveness check + config summary")
def health():
    return {"ok": True, **config.summary()}


@app.get("/api/spend", summary="Current Indian Kanoon API cost ledger")
def api_spend():
    """Today + lifetime IK spend. Returns ik_enabled=False if the feature
    is off or no token is configured."""
    client = _get_kanoon_client()
    if client is None:
        return {"ik_enabled": False, "note": "Set USE_IK_RETRIEVAL=1 and INDIAN_KANOON_TOKEN in .env."}
    return {"ik_enabled": True, **client.spend_summary()}


@app.get("/api/corpus", summary="Slim listing of the curated corpus")
def api_corpus():
    cases = config.load_curated_corpus()
    return {
        "count": len(cases),
        "cases": [
            {
                "id": c["id"], "title": c["title"], "court": c["court"], "year": c["year"],
                "topics": c.get("topics", [])[:6],
            }
            for c in cases
        ],
    }


@app.post("/api/situation", summary="Situation -> relevant precedents")
def api_situation(req: SituationRequest):
    """Returns 3-5 most relevant cases for the lawyer's situation.

    Two retrieval paths depending on USE_IK_RETRIEVAL:
      - curated-only:  pre-filter cases.json, send to Claude.
      - IK+curated:    hybrid retrieval (curated + semantic + IK live),
                       three-check verification, one regen retry on failure,
                       verification status surfaced in meta.
    """
    client = _get_kanoon_client()
    curated = config.load_curated_corpus()

    # Hindi pre-translation: if the lawyer wrote in Devanagari, translate
    # to English via Haiku BEFORE retrieval and generation run. The
    # original Hindi is preserved in the response so the UI can show both.
    translation_info = maybe_translate(req.situation)
    working_situation = translation_info["english_query"]

    ik_meta_extra: dict = {}
    verification_report: Optional[dict] = None
    evidence: list = []
    retrieval_cases: list = []

    if client is not None:
        from headnote.kanoon.retrieval import (
            retrieve_for_situation, result_to_prompt_corpus_json, IK_PROMPT_ADDENDUM,
        )
        ret = retrieve_for_situation(
            working_situation,
            client=client,
            curated_corpus=curated,
            mode=req.mode,
            jurisdiction=req.jurisdiction,
        )
        retrieval_cases = list(ret.cases)
        evidence = ret.evidence
        curated_lookup = {c["id"]: c for c in curated}
        corpus_json = result_to_prompt_corpus_json(ret, curated_lookup)
        sys_prompt = build_situation_system_prompt(req.style, corpus_json) + IK_PROMPT_ADDENDUM
        ik_meta_extra = {
            "retrieval_path": "ik+curated",
            "retrieval_mode": req.mode,
            "jurisdiction_hint": req.jurisdiction,
            "retrieval_elapsed_seconds": ret.meta.elapsed_seconds,
            "ik_search_calls": ret.meta.ik_search_calls,
            "ik_fetch_calls": ret.meta.ik_fetch_calls,
            "ik_cache_hits": ret.meta.cache_hits,
            "ik_inr_spent_this_call": ret.meta.inr_spent_this_call,
            "retrieval_notes": ret.meta.notes,
            "cases_returned": [
                {"case_id": cs.case_id, "title": cs.title, "source": cs.source,
                 "numcitedby": cs.numcitedby, "score": round(cs.relevance_score, 3)}
                for cs in ret.cases
            ],
        }
    else:
        sys_prompt = build_situation_system_prompt(
            req.style, _filtered_corpus_json(working_situation),
        )
        ik_meta_extra = {"retrieval_path": "curated-only"}

    user_prompt = SITUATION_USER_TEMPLATE.format(situation=working_situation, style=req.style)
    t0 = time.time()
    # deep_mode = user-opted premium: skip Sonnet, go straight to Opus, no
    # confidence retry. ENABLE_OPUS_ESCALATION=false (env override) also
    # disables the confidence retry — force Sonnet to commit to its first
    # answer (useful during a cost-spike incident).
    if req.deep_mode:
        route_force: Optional[str] = "opus"
    elif not config.ENABLE_OPUS_ESCALATION:
        route_force = "sonnet"
    else:
        route_force = None

    route_result = route_call(
        "situation",
        {"system_prompt": sys_prompt, "user_prompt": user_prompt},
        force_model=route_force,
    )
    elapsed = time.time() - t0
    raw = route_result.response
    total_paise = route_result.cost_paise
    chosen_model = route_result.model_name
    primary_model = chosen_model  # what the first call ran on (for telemetry)
    # Detect whether the router did an internal Sonnet -> Opus escalation
    # by comparing the chosen model to what routing would have selected
    # without force_model. Sonnet would have been default for "situation".
    escalated = (
        chosen_model == "claude-opus-4-6"
        and not req.deep_mode
        and config.ENABLE_OPUS_ESCALATION
    )

    parsed = parse_json_response(raw)

    # Existence filter (drop case_ids we don't recognise)
    if client is not None:
        known_ids = {c["id"] for c in curated} | {e.case_id for e in evidence}
    else:
        known_ids = {c["id"] for c in curated}

    verified, dropped = [], []
    for c in parsed.get("cases", []):
        if c.get("case_id") in known_ids:
            verified.append(c)
        else:
            dropped.append(c.get("title", "?"))
    parsed["cases"] = verified

    # Three-check verification + at most one regeneration retry
    regen_attempted = False
    regen_helped = False
    if evidence:
        report = verify_situation_response(parsed, evidence)

        if not report.is_clean():
            regen_attempted = True
            feedback = build_regen_feedback(report)
            try:
                retry_prompt = user_prompt + feedback
                # Verification-failure regen ALWAYS forces Opus. The router
                # already auto-upgrades on low confidence; reaching this
                # branch means the response was wrong in a way confidence
                # alone didn't catch (fabricated citation/quote/anchor),
                # so we commit to the highest-quality model.
                retry_result = route_call(
                    "situation",
                    {"system_prompt": sys_prompt, "user_prompt": retry_prompt},
                    force_model="opus",
                )
                retry_raw = retry_result.response
                total_paise += retry_result.cost_paise
                retry_parsed = parse_json_response(retry_raw)
                retry_parsed["cases"] = [
                    c for c in retry_parsed.get("cases", [])
                    if c.get("case_id") in known_ids
                ]
                retry_report = verify_situation_response(retry_parsed, evidence)
                if _is_strictly_better(retry_report, report):
                    parsed = retry_parsed
                    raw = retry_raw
                    report = retry_report
                    chosen_model = retry_result.model_name  # Opus
                    regen_helped = True
            except HTTPException:
                # Bad JSON from retry → keep the original
                pass

        verification_report = report.summary()

    # Synthesise a RouteResult-shaped object so build_router_meta sees the
    # final (possibly-regen-augmented) totals.
    from headnote.llm import RouteResult
    final_result = RouteResult(
        model_name=chosen_model,
        response=raw,
        cost_paise=total_paise,
        confidence_score=route_result.confidence_score,
    )
    meta = build_router_meta(final_result, elapsed)
    meta.update(ik_meta_extra)
    meta["deep_mode"] = req.deep_mode
    meta["escalated_to_opus"] = escalated
    # Hindi pipeline info — UI shows a bilingual strip when script == devanagari
    meta["input_script"] = translation_info["script"]
    meta["original_query"] = translation_info["original_query"]
    meta["english_query"] = translation_info["english_query"]
    meta["translation_cost_paise"] = translation_info["translation_cost_paise"]
    if translation_info["preserved_terms"]:
        meta["translation_preserved_terms"] = translation_info["preserved_terms"]
    if verification_report is not None:
        meta["verification"] = verification_report
        meta["verification_regen_attempted"] = regen_attempted
        meta["verification_regen_helped"] = regen_helped

    # Enrich each returned case with kanoon_doc_id, kanoon_url, fame_indicator.
    # Build a quick lookup from retrieval-time metadata (numcitedby, source).
    meta_by_id: dict = {}
    for cs in retrieval_cases:
        meta_by_id[cs.case_id] = {
            "kanoon_doc_id": _kanoon_doc_id_from_case_id(cs.case_id),
            "numcitedby": cs.numcitedby,
            "source": cs.source,
        }
    for c in curated:
        if c.get("id"):
            meta_by_id.setdefault(c["id"], {})
            if c.get("kanoon_doc_id"):
                meta_by_id[c["id"]]["kanoon_doc_id"] = str(c["kanoon_doc_id"])
    for case in parsed.get("cases", []):
        _enrich_case(case, meta_by_id)

    # Telemetry — fire-and-forget, never blocks the response
    record_query(
        task_type="situation",
        primary_model=primary_model,
        escalated=escalated or regen_attempted,
        total_cost_paise=total_paise + translation_info["translation_cost_paise"],
        latency_ms=int(elapsed * 1000),
        confidence=route_result.confidence_score,
        success=verification_report is None or verification_report.get("clean", True),
    )

    return {
        "result": parsed,
        "raw": raw,
        "dropped_hallucinations": dropped,
        "meta": meta,
    }


@app.post("/api/digest", summary="Topic -> research digest")
def api_digest(req: DigestRequest):
    sys_prompt = build_digest_system_prompt(_filtered_corpus_json(req.topic, top_k=18))
    user_prompt = DIGEST_USER_TEMPLATE.format(topic=req.topic)
    if req.deep_mode:
        route_force: Optional[str] = "opus"
    elif not config.ENABLE_OPUS_ESCALATION:
        route_force = "sonnet"
    else:
        route_force = None

    t0 = time.time()
    route_result = route_call(
        "digest",
        {"system_prompt": sys_prompt, "user_prompt": user_prompt},
        force_model=route_force,
    )
    elapsed = time.time() - t0
    primary_model = route_result.model_name
    escalated = (
        route_result.model_name == "claude-opus-4-6"
        and not req.deep_mode
        and config.ENABLE_OPUS_ESCALATION
    )

    parsed = parse_json_response(route_result.response)
    meta = build_router_meta(route_result, elapsed)
    meta["deep_mode"] = req.deep_mode
    meta["escalated_to_opus"] = escalated

    record_query(
        task_type="digest",
        primary_model=primary_model,
        escalated=escalated,
        total_cost_paise=route_result.cost_paise,
        latency_ms=int(elapsed * 1000),
        confidence=route_result.confidence_score,
    )

    return {
        "result": parsed,
        "raw": route_result.response,
        "meta": meta,
    }


@app.post("/api/headnote", summary="Judgment text -> Cri.L.J. headnote(s)")
def api_headnote(req: HeadnoteRequest):
    """Two-stage pipeline for headnote generation:

      1. Opus generates the headnotes from the full judgment text.
         The system prompt (with 3 gold-standard example headnotes) is
         cached — cache_read at 10% of input price keeps per-call Opus
         cost dominated by the variable judgment text, not the examples.

      2. Haiku verifies each generated headnote against the source
         judgment: checks that the quoted ratio appears in the source,
         that paragraph anchors point to real paragraphs, and that the
         statute_index uses formal Cri.L.J. style. Cheap (~Rs.0.50).

      3. If Haiku flags any headnote as "failed", that specific headnote
         is re-issued to Opus once with the verification errors pasted
         in as feedback. The retry response replaces the original entry.

    The Sonnet pre-process step from the original spec was dropped to
    avoid lossy compression — the headnote is the moat workflow and we
    want Opus to see the full judgment text directly.
    """
    judgment_text = req.judgment_text[:30000]
    user_prompt = HEADNOTE_USER_TEMPLATE.format(judgment_text=judgment_text)

    t0 = time.time()
    # Stage 1: Opus with cached examples.  cache=True so the (long, static)
    # system prompt with gold-standard examples hits the prompt cache after
    # the first call. The judgment text in the user prompt is per-request
    # and uncacheable, which is fine.
    opus_result = route_call(
        "headnote",
        {
            "system_prompt": HEADNOTE_SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "cache": True,
        },
    )
    parsed = parse_json_response(opus_result.response)
    total_paise = opus_result.cost_paise

    # Stage 2: Haiku verification — only meaningful if we got structured
    # headnotes back. Verify each, then collect any that failed.
    verifications: list[dict] = []
    retried_letters: list[str] = []
    headnotes = parsed.get("headnotes") or []
    if headnotes:
        verify_user = HEADNOTE_VERIFY_USER_TEMPLATE.format(
            judgment_text=judgment_text,
            headnotes_json=json.dumps(headnotes, ensure_ascii=False),
        )
        try:
            verify_result = route_call(
                "verification",
                {
                    "system_prompt": HEADNOTE_VERIFY_SYSTEM_PROMPT,
                    "user_prompt": verify_user,
                    "cache": False,
                },
            )
            total_paise += verify_result.cost_paise
            try:
                verify_parsed = parse_json_response(verify_result.response)
                verifications = list(verify_parsed.get("verifications") or [])
            except HTTPException:
                # Haiku returned non-JSON — skip verification but don't fail the request
                verifications = []
        except Exception as e:
            print(f"[headnote] verification step failed ({e}); skipping")
            verifications = []

        # Stage 3: per-headnote Opus retry where verification failed.
        # Single retry, only for entries marked "failed" (not "warning").
        verifications_by_letter = {v.get("letter"): v for v in verifications}
        new_headnotes = []
        for hn in headnotes:
            letter = hn.get("letter")
            v = verifications_by_letter.get(letter)
            if v and v.get("overall") == "failed":
                issues = "; ".join(v.get("issues") or [])
                retry_user = (
                    user_prompt
                    + f"\n\n---\n\nREGENERATE HEADNOTE ({letter}) ONLY. "
                    f"The previous attempt failed verification:\n  - {issues}\n\n"
                    "Re-emit the COMPLETE response JSON (all headnotes), but "
                    f"with headnote ({letter}) corrected to address these issues."
                )
                try:
                    retry_result = route_call(
                        "headnote",
                        {
                            "system_prompt": HEADNOTE_SYSTEM_PROMPT,
                            "user_prompt": retry_user,
                            "cache": True,
                        },
                    )
                    total_paise += retry_result.cost_paise
                    retry_parsed = parse_json_response(retry_result.response)
                    retry_headnotes = retry_parsed.get("headnotes") or []
                    retry_match = next(
                        (h for h in retry_headnotes if h.get("letter") == letter),
                        None,
                    )
                    if retry_match is not None:
                        new_headnotes.append(retry_match)
                        retried_letters.append(letter)
                        continue
                except (HTTPException, Exception) as e:
                    print(f"[headnote] retry for letter {letter} failed: {e}")
            new_headnotes.append(hn)
        parsed["headnotes"] = new_headnotes

    elapsed = time.time() - t0

    # Synthesise a RouteResult-shaped object for build_router_meta
    from headnote.llm import RouteResult
    final_result = RouteResult(
        model_name=opus_result.model_name,
        response=opus_result.response,
        cost_paise=total_paise,
        confidence_score=opus_result.confidence_score,
    )

    meta = build_router_meta(final_result, elapsed)
    meta["verifications"] = verifications
    meta["retried_letters"] = retried_letters

    record_query(
        task_type="headnote",
        primary_model=opus_result.model_name,
        escalated=bool(retried_letters),
        total_cost_paise=total_paise,
        latency_ms=int(elapsed * 1000),
        confidence=opus_result.confidence_score,
    )
    return {
        "result": parsed,
        "raw": opus_result.response,
        "meta": meta,
    }


@app.post("/api/translate", summary="Translate English JSON result to Hindi")
def api_translate(req: TranslateRequest):
    """Translate prose fields via Haiku 4.5 with a citation verifier.

    Primary path: Haiku 4.5 via the model router. Each translatable field
    gets a citation-preservation check; on failure, one retry with a
    stricter prompt that names the dropped tokens. If citations are still
    missing after retry, the response sets `meta.quality="degraded"` so
    the frontend can warn the lawyer to manually verify those specific
    citations.

    Fallback path: free Google Translate, used only if Anthropic is not
    configured (no API key) or fails outright. Meta block reflects which
    path ran.
    """
    t0 = time.time()
    try:
        if config.ANTHROPIC_API_KEY:
            translated, paise, quality, preserved = translate_payload_haiku(req.payload)
            elapsed = time.time() - t0
            record_query(
                task_type="translate",
                primary_model="claude-haiku-4-5",
                escalated=False,
                total_cost_paise=paise,
                latency_ms=int(elapsed * 1000),
                success=(quality == "ok"),
            )
            return {
                "result": translated,
                "raw": json.dumps(translated, ensure_ascii=False),
                "meta": {
                    "elapsed_seconds": round(elapsed, 2),
                    "model": "claude-haiku-4-5",
                    "cost_paise": paise,
                    "cost_inr": round(paise / 100, 4),
                    "cost_usd": round(paise / 100 / config.USD_TO_INR, 6),
                    "quality": quality,
                    "preserved_citations": preserved,
                    "translator": "haiku",
                },
            }
        # No Anthropic key configured — fall back to free Google Translate
        translated = translate_payload(req.payload, target=req.target_language)
        elapsed = time.time() - t0
        return {
            "result": translated,
            "raw": json.dumps(translated, ensure_ascii=False),
            "meta": {
                "elapsed_seconds": round(elapsed, 2),
                "model": "google-translate (free)",
                "cost_paise": 0, "cost_inr": 0.0, "cost_usd": 0.0,
                "quality": "ok",
                "preserved_citations": [],
                "translator": "google",
                "free": True,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Translation failed: {e}")


@app.post("/api/feedback", summary="Lawyer thumbs-up/down + comment")
def api_feedback(req: FeedbackRequest):
    conn = sqlite3.connect(config.FEEDBACK_DB)
    conn.execute(
        "INSERT INTO feedback (ts, mode, input_text, output_json, rating, correction, lawyer_handle) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            req.mode, req.input_text, req.output_json, req.rating,
            req.correction or "", req.lawyer_handle or "",
        ),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/decompose", summary="Query → two sub-queries + 'researching:' summary")
def api_decompose(payload: dict):
    """Generate the transparency panel content for a situation query.

    Body: {"query": "..."}.

    Pre-translates Devanagari input to English before decomposing so the
    panel reads naturally for Hindi queries too. Cheap Haiku call (~₹0.20).
    """
    query = (payload or {}).get("query", "")
    if not isinstance(query, str) or not query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    translation = maybe_translate(query)
    decomp = decompose_query(translation["english_query"])
    return {
        "input_script": translation["script"],
        "original_query": translation["original_query"],
        "english_query": translation["english_query"],
        "decomposition": decomp,
        "cost_paise": (translation["translation_cost_paise"] or 0) + (decomp.get("cost_paise") or 0),
    }


# -----------------------------------------------------------------------------
# Browse Judgments — direct IK search, AI-augmented from the UI.
# -----------------------------------------------------------------------------

@app.get("/api/browse/search", summary="Direct Indian Kanoon search (Browse view)")
def api_browse_search(
    q: str,
    court: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    page: int = 0,
):
    """Browse Judgments: pass a query through to Indian Kanoon and return
    light search-hit metadata for the UI list.

    Costs: ₹0.50 per search page (cached for 30 days). The UI is expected to
    use this as a free-tier-friendly browse surface.

    Filters supported (translated into IK formInput tokens):
      court     — e.g. 'supremecourt', 'highcourts', 'bombay' (partial match)
      year_from / year_to — ISO years; appended as `fromdate:` / `todate:`.
    """
    client = _get_kanoon_client()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Browse requires INDIAN_KANOON_TOKEN + USE_IK_RETRIEVAL=1.",
        )
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="q is required")

    # Pre-translate Hindi queries so IK keyword search works
    translation = maybe_translate(q)
    working = translation["english_query"]

    # Build IK formInput. Use doctype filter for SC/HC by default; honour
    # specific court hint when given.
    filters: list[str] = []
    if court:
        c = court.lower().strip()
        if c in ("supremecourt", "sc", "supreme court"):
            filters.append("doctypes:supremecourt")
        elif c in ("highcourts", "hc", "high court", "high courts"):
            filters.append("doctypes:highcourts")
        else:
            filters.append(f"doctypes:{c}")
    else:
        filters.append("doctypes:supremecourt,highcourts")
    if year_from:
        filters.append(f"fromdate:{int(year_from)}-01-01")
    if year_to:
        filters.append(f"todate:{int(year_to)}-12-31")

    form_input = " ".join([working.strip()] + filters)

    try:
        page_result = client.search(form_input, pagenum=int(page or 0))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"IK search failed: {e}")

    hits = [
        {
            "tid": h.tid,
            "title": h.title,
            "court": h.docsource,
            "publishdate": h.publishdate,
            "headline": h.headline,
            "numcitedby": h.numcitedby,
            "fame_indicator": _fame_indicator(h.numcitedby),
            "kanoon_url": f"https://indiankanoon.org/doc/{h.tid}/",
        }
        for h in page_result.hits
    ]
    return {
        "query": q,
        "english_query": working,
        "input_script": translation["script"],
        "filters": {"court": court, "year_from": year_from, "year_to": year_to},
        "page": page_result.page,
        "found": page_result.found_label,
        "hits": hits,
        "spend": client.spend_summary(),
    }


@app.get("/api/browse/doc/{tid}", summary="Fetch a single judgment's metadata + body")
def api_browse_doc(tid: int):
    """Fetch one full judgment by Indian Kanoon tid. Cached forever locally
    (judgments don't change). Cost: ₹0.20 on first fetch, free thereafter."""
    client = _get_kanoon_client()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Browse requires INDIAN_KANOON_TOKEN + USE_IK_RETRIEVAL=1.",
        )
    try:
        doc = client.get_doc(int(tid))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"IK fetch failed: {e}")
    return {
        "tid": doc.tid,
        "title": doc.title,
        "court": doc.docsource,
        "publishdate": doc.publishdate,
        "numcitedby": doc.numcitedby,
        "numcites": doc.numcites,
        "fame_indicator": _fame_indicator(doc.numcitedby),
        "kanoon_url": f"https://indiankanoon.org/doc/{doc.tid}/",
        "doc_html": doc.doc_html,
        "cats": doc.cats,
    }


@app.exception_handler(Exception)
async def all_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return JSONResponse(status_code=500, content={"error": str(exc)})


# Mount static last so /api/* takes priority
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
