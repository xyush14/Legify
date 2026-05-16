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
    call_claude_cached, parse_json_response, build_meta,
)
from headnote.retrieval.keyword import prefilter_cases
from headnote.translate import translate_payload
from headnote.verify import (
    EvidenceParagraph, verify_situation_response, build_regen_feedback,
)


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

    ik_meta_extra: dict = {}
    verification_report: Optional[dict] = None
    evidence: list = []

    if client is not None:
        from headnote.kanoon.retrieval import (
            retrieve_for_situation, result_to_prompt_corpus_json, IK_PROMPT_ADDENDUM,
        )
        ret = retrieve_for_situation(
            req.situation, client=client, curated_corpus=curated,
        )
        evidence = ret.evidence
        curated_lookup = {c["id"]: c for c in curated}
        corpus_json = result_to_prompt_corpus_json(ret, curated_lookup)
        sys_prompt = build_situation_system_prompt(req.style, corpus_json) + IK_PROMPT_ADDENDUM
        ik_meta_extra = {
            "retrieval_path": "ik+curated",
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
            req.style, _filtered_corpus_json(req.situation),
        )
        ik_meta_extra = {"retrieval_path": "curated-only"}

    user_prompt = SITUATION_USER_TEMPLATE.format(situation=req.situation, style=req.style)
    t0 = time.time()
    raw, usage = call_claude_cached(sys_prompt, user_prompt)
    elapsed = time.time() - t0

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
                retry_raw, retry_usage = call_claude_cached(sys_prompt, retry_prompt)
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
                    regen_helped = True
                    for k in ("input_tokens", "output_tokens",
                              "cache_creation_input_tokens", "cache_read_input_tokens"):
                        usage[k] = usage.get(k, 0) + retry_usage.get(k, 0)
            except HTTPException:
                pass

        verification_report = report.summary()

    meta = build_meta(usage, elapsed)
    meta.update(ik_meta_extra)
    if verification_report is not None:
        meta["verification"] = verification_report
        meta["verification_regen_attempted"] = regen_attempted
        meta["verification_regen_helped"] = regen_helped

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
    t0 = time.time()
    raw, usage = call_claude_cached(sys_prompt, user_prompt)
    elapsed = time.time() - t0

    parsed = parse_json_response(raw)
    return {"result": parsed, "raw": raw, "meta": build_meta(usage, elapsed)}


@app.post("/api/headnote", summary="Judgment text -> Cri.L.J. headnote(s)")
def api_headnote(req: HeadnoteRequest):
    user_prompt = HEADNOTE_USER_TEMPLATE.format(judgment_text=req.judgment_text[:30000])
    t0 = time.time()
    raw, usage = call_claude_cached(HEADNOTE_SYSTEM_PROMPT, user_prompt, cache=False)
    elapsed = time.time() - t0

    parsed = parse_json_response(raw)
    return {"result": parsed, "raw": raw, "meta": build_meta(usage, elapsed)}


@app.post("/api/translate", summary="Translate English JSON result to Hindi")
def api_translate(req: TranslateRequest):
    """Translates prose fields to Hindi via free Google Translate. Citations,
    case titles, statute names, and paragraph anchors are protected from
    translation via placeholder substitution. No LLM cost."""
    t0 = time.time()
    try:
        translated = translate_payload(req.payload, target=req.target_language)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Translation failed: {e}")
    elapsed = time.time() - t0

    return {
        "result": translated,
        "raw": json.dumps(translated, ensure_ascii=False),
        "meta": {
            "elapsed_seconds": round(elapsed, 2),
            "model": "google-translate (free)",
            "input_tokens": 0, "output_tokens": 0,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
            "cost_usd": 0.0, "cost_inr": 0.0, "free": True,
        },
    }


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


@app.exception_handler(Exception)
async def all_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return JSONResponse(status_code=500, content={"error": str(exc)})


# Mount static last so /api/* takes priority
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
