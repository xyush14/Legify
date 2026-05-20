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
from headnote.refine import refine_query, shallow_refine
from headnote.ranking import prerank_candidates
from headnote.api.models import (
    SituationRequest, DigestRequest, HeadnoteRequest,
    TranslateRequest, FeedbackRequest,
)
from headnote.llm import (
    build_situation_system_prompt, SITUATION_USER_TEMPLATE,
    build_situation_user_v2,
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
from headnote.entitlements import (
    get_current_user,
    check_and_record,
    require_feature,
    CurrentUser,
)
from fastapi import Depends


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
    path and as a fallback for digest mode (which doesn't go through IK yet).

    Strips `_prefilter_*` diagnostic fields before serialisation — those
    exist for tuning + cost-dashboard reporting, not for the LLM to read.
    """
    from headnote.retrieval.keyword import strip_debug_fields
    cases = prefilter_cases(
        config.load_curated_corpus(), query,
        top_k=top_k or config.PREFILTER_TOP_K,
    )
    return json.dumps(strip_debug_fields(cases), ensure_ascii=False)


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

# Drafting engine (10 document types, story-first). Per-type templates
# ship one at a time; the API surface lives here from v0 so the FE can
# integrate against `/api/draft/*` while individual templates are ported.
from headnote.drafter.api import router as _drafter_router
from headnote.drafter.storage import init_drafts_db as _init_drafts_db

app.include_router(_drafter_router)
_init_drafts_db()

# Subscription / entitlements: /api/me, /api/plans, /admin/v2/*
from headnote.api.me import router as _me_router
from headnote.api.admin_v2 import router as _admin_v2_router

app.include_router(_me_router)
app.include_router(_admin_v2_router)

# Pre-extract universal facts for the 42 curated cases at boot. ~50ms
# one-time cost that removes a per-query latency spike for the first user.
# Safe to skip via env var if the curated corpus changes at runtime (which
# it currently doesn't — it's a static JSON file).
try:
    from headnote.retrieval.keyword import prime_case_facts_cache as _prime_cache
    _prime_cache(config.load_curated_corpus())
except Exception as _e:
    # Never fail app boot on a cache miss; the cache primes lazily anyway.
    print(f"[boot] curated facts cache priming failed (non-fatal): {_e}")


# Warm the fastembed model at boot. Loading BAAI/bge-small-en-v1.5 takes
# 5-15s the first time (cold container, model download or disk read).
# Without this warm-up the FIRST /api/situation request after a deploy
# pays that 15s latency hit on top of everything else — the user sees
# a 30-50s wait and assumes the app is broken. We do this in a thread
# so it doesn't block uvicorn from accepting connections; if the user
# arrives before warm-up finishes they pay the latency once and then
# every subsequent request is fast.
def _warm_embedding_model():
    import threading

    def _warm():
        try:
            import time as _time
            t0 = _time.time()
            from headnote.retrieval.embeddings import EmbeddingIndex
            idx = EmbeddingIndex()
            # Touch the model so fastembed downloads + loads the ONNX file.
            # We don't actually embed anything; _get_model() handles the load.
            idx._get_model()
            print(f"[boot] embedding model warmed in {_time.time()-t0:.1f}s")
        except Exception as e:
            print(f"[boot] embedding warm-up failed (non-fatal): {e}")

    threading.Thread(target=_warm, name="warm-embeddings", daemon=True).start()


_warm_embedding_model()


@app.get("/", include_in_schema=False)
def landing():
    return FileResponse(config.STATIC_DIR / "landing.html")


@app.get("/app", include_in_schema=False)
@app.get("/app/", include_in_schema=False)
def app_index():
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/pricing", include_in_schema=False)
@app.get("/pricing/", include_in_schema=False)
def pricing_page():
    """Public pricing page — shows the four tiers + a CTA per plan."""
    return FileResponse(config.STATIC_DIR / "pricing.html")


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
def admin_panel():
    """Admin panel SPA. Access controlled by JWT (admin_users table) or
    ADMIN_TOKEN bearer; the HTML shell itself is inert without auth."""
    return FileResponse(config.STATIC_DIR / "admin.html")


@app.get("/drafter", include_in_schema=False)
@app.get("/drafter/", include_in_schema=False)
def drafter_standalone():
    """Standalone §138 NI Act complaint drafter prototype.

    Intentionally served as an isolated single-file SPA — no auth wrapper,
    no main-app shell — so it can be shared with reviewers (lawyers,
    advocates) for usability testing without leaking the rest of the
    product surface. The drafter HTML is self-contained: inline CSS, inline
    JS, only external dependency is Google Fonts.

    See HEADNOTE_DRAFTING_HANDOFF.md for the full design spec.
    """
    return FileResponse(config.STATIC_DIR / "drafter.html")


@app.get("/draft/bail", include_in_schema=False)
@app.get("/draft/bail/", include_in_schema=False)
def draft_bail_application():
    """Bail Application drafter — live split-pane UI with FIR-photo OCR.

    Form on the left, court-Hindi document rendering live on the right.
    Camera/file upload at top hits /api/draft/ocr-fir which uses Claude
    vision (via Bedrock) to extract structured FIR fields and auto-fill
    60% of the form in 4-8 seconds.

    Output: print-perfect Hindi PDF for filing at MP/UP/Bihar/Rajasthan
    courts. English render falls back for HC English benches.
    """
    return FileResponse(config.STATIC_DIR / "draft-bail.html")


@app.get("/api/config", summary="Public frontend configuration (non-secret)")
def api_config():
    """Returns the public Supabase credentials so auth.js can initialise the
    Supabase client without hardcoding keys in static files.

    The anon key is intentionally public — it is constrained by Supabase RLS
    policies and is safe to expose in the browser.
    """
    return {
        "supabase_url":      config.SUPABASE_URL or "",
        "supabase_anon_key": config.SUPABASE_ANON_KEY or "",
    }


@app.get("/api/debug/auth", summary="OAuth configuration diagnostics (dev only)")
def debug_auth():
    """Returns diagnostic information about OAuth setup. This helps identify
    misconfiguration between Google Cloud, Supabase, and the app.

    Only call this if you're debugging auth issues.
    """
    return {
        "supabase_configured": bool(config.SUPABASE_URL and config.SUPABASE_ANON_KEY),
        "supabase_url": config.SUPABASE_URL or "(not set)",
        "supabase_url_valid": bool(config.SUPABASE_URL and "supabase.co" in config.SUPABASE_URL),
        "expected_redirect_uri": "https://<your-supabase-project>.supabase.co/auth/v1/callback",
        "app_origin_note": "The frontend will send redirectTo: window.location.origin + '/app'",
        "debug_instructions": [
            "1. Open browser DevTools (F12)",
            "2. Go to Console tab",
            "3. Click 'Continue with Google'",
            "4. Look for [auth] prefixed logs",
            "5. Share the full console output to debug",
        ]
    }


@app.get("/api/health", summary="Liveness check + config summary")
def health():
    # Add HF corpus stats so we can confirm the import landed without
    # querying the DB directly.
    try:
        from headnote.retrieval.hf_corpus import corpus_stats
        hf = corpus_stats()
    except Exception:
        hf = {"total": 0, "configured": False}
    return {"ok": True, **config.summary(), "hf_corpus": hf}


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


@app.get("/api/hf_search", summary="Search the HuggingFace IL-TUR local corpus")
def api_hf_search(
    q: str,
    language: str = "en",
    source: Optional[str] = None,       # comma-separated: "cjpe,summ"
    label: Optional[str] = None,        # comma-separated: "accepted,granted"
    district: Optional[str] = None,
    limit: int = 20,
):
    """Keyword search over the local HF corpus populated by
    scripts/harvest_hf_corpus.py. Intended for testing the import + as a
    fallback retrieval source separate from IK API and the 42 curated cases.

    Returns title + preview only (not full text) to keep responses small.
    Hit /api/hf_doc/<doc_id> for full text.
    """
    from headnote.retrieval.hf_corpus import search, corpus_stats

    stats = corpus_stats()
    if not stats["configured"]:
        return {
            "ok": False,
            "error": "HF corpus not imported yet.",
            "hint": "Run: pip install -r requirements-harvest.txt && "
                    "python scripts/harvest_hf_corpus.py --subsets cjpe summ",
            "results": [],
        }

    # Same tokenisation we'd use for IK prefilter: split on whitespace,
    # lower, drop very short tokens. Caller can also pass quoted phrases.
    tokens = [t for t in q.lower().split() if len(t) > 2]

    # Pass the raw query as `situation` so search() can extract facts and
    # rescore candidates by fact-vector overlap (the big quality lever).
    results = search(
        tokens,
        situation=q,
        language=language,
        source_filter=[s.strip() for s in source.split(",")] if source else None,
        label_filter=[l.strip() for l in label.split(",")] if label else None,
        district_filter=district,
        limit=min(max(limit, 1), 100),
    )

    # Surface the extracted query facts so a tester can see exactly what
    # the regex pulled out — invaluable when tuning extractor patterns.
    from headnote.retrieval.fact_extractor import extract_facts as _xf
    query_facts = _xf(q)

    return {
        "ok": True,
        "query": q,
        "tokens_used": tokens,
        "query_facts": query_facts,
        "count": len(results),
        "total_in_corpus": stats["total"],
        "facts_populated": stats.get("facts_populated"),
        "facts_pct": stats.get("facts_pct"),
        "results": [
            {
                "doc_id": r.doc_id,
                "source": r.source,
                "court": r.court,
                "title": r.title,
                "preview": r.preview,
                "label": r.label,
                "district": r.district,
                "language": r.language,
                "word_count": r.word_count,
                "has_summary": bool(r.summary),
                "fact_score": r.fact_score,
                "fact_breakdown": r.fact_breakdown,
                "facts": r.facts,
            }
            for r in results
        ],
    }


@app.get("/api/hf_doc/{doc_id:path}", summary="Fetch one HF corpus judgment by doc_id")
def api_hf_doc(doc_id: str):
    """Returns the full text + summary (if any) for a single HF judgment.

    doc_id format: "hf:<source>:<original_id>" — e.g. "hf:cjpe:115651329".
    Path converter `:path` allows the colons through unmodified.
    """
    from headnote.retrieval.hf_corpus import get_by_id

    judgment = get_by_id(doc_id)
    if not judgment:
        raise HTTPException(status_code=404, detail=f"No HF judgment with doc_id={doc_id!r}")

    return {
        "doc_id": judgment.doc_id,
        "source": judgment.source,
        "court": judgment.court,
        "title": judgment.title,
        "text": judgment.text,
        "summary": judgment.summary,
        "label": judgment.label,
        "district": judgment.district,
        "language": judgment.language,
        "word_count": judgment.word_count,
    }


@app.post("/api/situation", summary="Situation -> relevant precedents")
def api_situation(
    req: SituationRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Returns 3-5 most relevant cases for the lawyer's situation.

    Two retrieval paths depending on USE_IK_RETRIEVAL:
      - curated-only:  pre-filter cases.json, send to Claude.
      - IK+curated:    hybrid retrieval (curated + semantic + IK live),
                       three-check verification, one regen retry on failure,
                       verification status surfaced in meta.

    Gated: deep_search feature. Counts against the user's quota; 402 if exhausted.
    """
    with check_and_record(user.id, "deep_search", endpoint="situation") as _record:
        return _api_situation_impl(req, _record)


def _api_situation_impl(req: SituationRequest, _record):
    # Per-stage wall-clock timing. Logged at the end of the function so
    # Railway logs show exactly where the seconds went on a slow query.
    # This is the difference between "blindly tweaking the pipeline" and
    # "lower max_new_fetches because IK fetches actually took 12s."
    _stage_t: dict[str, float] = {}
    _t_total = time.time()
    def _stage(name: str, since: float) -> None:
        _stage_t[name] = round(time.time() - since, 2)

    _t = time.time()
    client = _get_kanoon_client()
    curated = config.load_curated_corpus()
    _stage("01_setup", _t)

    # Hindi pre-translation: if the lawyer wrote in Devanagari, translate
    # to English via Haiku BEFORE retrieval and generation run. The
    # original Hindi is preserved in the response so the UI can show both.
    _t = time.time()
    translation_info = maybe_translate(req.situation)
    working_situation = translation_info["english_query"]
    _stage("02_translate", _t)

    # Stage 1: shallow query refinement (regex normalize only, NO Haiku).
    # Trade-off chosen: saves ~3-5s. Sonnet's V2 prompt already handles
    # query understanding well, and retrieval doesn't actually use the
    # Haiku-produced facets (it works off raw situation text). The deep
    # `refine_query()` is preserved for future use if we wire facets
    # into retrieval properly.
    _t = time.time()
    refined = shallow_refine(working_situation)
    _stage("02b_refine", _t)

    ik_meta_extra: dict = {}
    prerank_scores: list = []
    verification_report: Optional[dict] = None
    evidence: list = []
    retrieval_cases: list = []

    if client is not None:
        from headnote.kanoon.retrieval import (
            retrieve_for_situation, result_to_prompt_corpus_json, IK_PROMPT_ADDENDUM,
        )
        _t = time.time()
        ret = retrieve_for_situation(
            working_situation,
            client=client,
            curated_corpus=curated,
            mode=req.mode,
            jurisdiction=req.jurisdiction,
        )
        _stage("03_retrieve", _t)
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
        # Curated-only path: prefilter the 42-case corpus → prerank with Haiku →
        # build the corpus JSON from the pruned list.
        from headnote.retrieval.keyword import strip_debug_fields as _strip_debug
        _t = time.time()
        candidate_pool = prefilter_cases(
            config.load_curated_corpus(), working_situation,
            top_k=config.PREFILTER_TOP_K,
        )
        # Stage 3 pre-rank — Haiku scores the curated candidates on the 5-dim
        # rubric BEFORE Sonnet sees them. Drops poor matches, keeps top 10.
        _t_pre = time.time()
        pruned, prerank_scores_objs, prerank_cost = prerank_candidates(
            refined, candidate_pool, top_n=10,
        )
        prerank_scores = [s.to_dict() for s in prerank_scores_objs]
        _stage("03b_prerank", _t_pre)
        # If prerank kept nothing (everything below threshold), fall back to
        # the raw prefilter result rather than sending Sonnet an empty pool.
        pool_for_llm = pruned if pruned else candidate_pool[:10]
        corpus_json = json.dumps(_strip_debug(pool_for_llm), ensure_ascii=False)
        sys_prompt = build_situation_system_prompt(req.style, corpus_json)
        ik_meta_extra = {
            "retrieval_path":   "curated-only",
            "candidate_pool":   len(candidate_pool),
            "prerank_kept":     len(pruned),
            "prerank_dropped":  len(candidate_pool) - len(pruned),
            "prerank_cost_paise": prerank_cost,
        }

    t0 = time.time()
    # ---------- Single-call generation (predictable latency) ----------
    # The two-phase pipeline (Phase 1 Haiku + Phase 2 parallel Sonnet) was
    # bottlenecking in production: parallelism wasn't materialising over the
    # network (suspected httpx connection pool / Anthropic rate-limit
    # serialisation on Render's outbound). 5 Sonnet calls in sequence = 70s+
    # = 502 every time.
    #
    # Going back to a single Sonnet call with TWO key wins versus the legacy
    # single call:
    #   1. Hidden Authorities reranker has already trimmed the corpus to 3
    #      candidates — so the LLM only writes up 3 cases worth of output
    #      (not 5), keeping wall-clock under Render's 25s budget.
    #   2. The system prompt is now PURELY cacheable (base + style block);
    #      the corpus moves into the user prompt. After the first call,
    #      every subsequent call hits Anthropic's prompt cache for ~90%
    #      of system-prompt input cost.
    # V2 user prompt — feeds the refined query envelope + prerank scores
    # to the LLM. This is the symmetry layer: Sonnet sees the SAME structured
    # view of the question that retrieval and prerank used.
    user_prompt = build_situation_user_v2(
        raw_situation  = working_situation,
        refined        = refined.to_dict(),
        prerank_scores = prerank_scores,
        style          = req.style,
    )
    # Model selection is env-var driven so the same code runs on Render
    # free (set SITUATION_MODEL=haiku) AND Railway / Pro (SITUATION_MODEL
    # defaults to sonnet) without redeploying.
    force_model_choice = (
        config.SITUATION_DEEP_MODEL if req.deep_mode else config.SITUATION_MODEL
    )

    # Extended thinking gives Sonnet/Opus a scratch space to actually execute
    # the four-dimension scoring rubric in the v2 prompt before writing JSON.
    # Haiku doesn't support it (skipped silently inside call_claude_cached).
    payload = {
        "system_prompt": sys_prompt,
        "user_prompt": user_prompt,
        "cache": True,
        "enable_thinking": config.ENABLE_THINKING,
        "thinking_budget": config.THINKING_BUDGET_TOKENS,
    }
    _t = time.time()
    route_result = route_call("situation", payload, force_model=force_model_choice)
    _stage("04_llm_primary", _t)
    elapsed = time.time() - t0
    raw = route_result.response
    total_paise = route_result.cost_paise
    chosen_model = route_result.model_name
    primary_model = chosen_model
    escalated = False
    parsed = parse_json_response(raw)

    # Existence filter (drop case_ids we don't recognise)
    if client is not None:
        known_ids = {c["id"] for c in curated} | {e.case_id for e in evidence}
    else:
        known_ids = {c["id"] for c in curated}

    # Defensive parsing for the v2 schema (rubric + internal_reasoning).
    # The model is instructed to populate these fields, but production code
    # should never assume the model followed instructions.
    parsed.setdefault("internal_reasoning", {})
    parsed.setdefault("confidence", "medium")
    for c in parsed.get("cases", []):
        c.setdefault("relevance_scores", {
            "fact_archetype_match": 0,
            "doctrinal_match": 0,
            "outcome_alignment": 0,
            "authority_weight": 0,
            "total": 0,
        })

    verified, dropped = [], []
    for c in parsed.get("cases", []):
        if c.get("case_id") in known_ids:
            verified.append(c)
        else:
            dropped.append(c.get("title", "?"))

    # Defensive filter: the v2 prompt instructs the model to drop any case
    # scoring 0 on fact-archetype match. Enforce here too in case the
    # model didn't comply.
    filtered_zero_archetype = 0
    final = []
    for c in verified:
        score = c.get("relevance_scores", {}).get("fact_archetype_match", 0)
        if score > 0:
            final.append(c)
        else:
            filtered_zero_archetype += 1
    parsed["cases"] = final
    parsed["filtered_zero_archetype"] = filtered_zero_archetype

    # Verification (in-process, no LLM call): the three-check verifier
    # cross-references each cited paragraph_anchor and quotable_phrase
    # against the source evidence. We DROP the failing case rather than
    # regenerating — the two-phase pipeline produces much cleaner output
    # than the legacy single-call path, so regen rarely helps and always
    # adds 30-60s of latency.
    regen_attempted = False
    regen_helped = False
    if evidence:
        _t = time.time()
        report = verify_situation_response(parsed, evidence)
        _stage("05_verify", _t)
        if not report.is_clean():
            # Drop only the cases that actually failed verification
            failed_ids = {f.case_id for f in report.findings if not f.is_clean()}
            kept = [c for c in parsed.get("cases", []) if c.get("case_id") not in failed_ids]
            if kept and len(kept) < len(parsed["cases"]):
                parsed["cases"] = kept
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

    # Surface Stage 1 (query refinement) for transparency. The FE can show
    # "we understood your question as: ..." which builds trust + helps the
    # lawyer correct misinterpretations early.
    meta["refined_query"] = {
        "canonical_question":   refined.canonical_question,
        "intent_type":          refined.intent_type,
        "primary_statute":      refined.primary_statute,
        "secondary_statutes":   refined.secondary_statutes,
        "stage":                refined.stage,
        "doctrines_at_issue":   refined.doctrines_at_issue,
        "expected_answer_shape": refined.expected_answer_shape,
        "ranking_hint":         refined.ranking_hint,
        "cost_paise":           refined.cost_paise,
        "elapsed_ms":           refined.elapsed_ms,
    }
    if prerank_scores:
        meta["prerank_scores"] = prerank_scores
    meta["total_cost_paise"] = (
        total_paise
        + translation_info.get("translation_cost_paise", 0)
        + refined.cost_paise
        + ik_meta_extra.get("prerank_cost_paise", 0)
    )

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

    _stage("99_total", _t_total)
    meta["stage_timings_seconds"] = _stage_t
    # Surfaced to Railway logs so we can see per-stage breakdown without
    # digging into the JSON response. Format: "stage=Xs ..."
    print(
        "[situation-timing] "
        + " ".join(f"{k}={v}s" for k, v in _stage_t.items())
    )

    _record(cost_paise=int(meta.get("cost_paise", 0) or 0), model=meta.get("model"))

    return {
        "result": parsed,
        "raw": raw,
        "dropped_hallucinations": dropped,
        "meta": meta,
    }


@app.post("/api/digest", summary="Topic -> research digest")
def api_digest(
    req: DigestRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Gated: deep_search feature."""
    with check_and_record(user.id, "deep_search", endpoint="digest") as _record:
        return _api_digest_impl(req, _record)


def _api_digest_impl(req: DigestRequest, _record):
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
        route_result.model_name == "claude-opus-4-7"
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

    _record(cost_paise=int(route_result.cost_paise or 0), model=primary_model)

    return {
        "result": parsed,
        "raw": route_result.response,
        "meta": meta,
    }


@app.post("/api/headnote", summary="Judgment text -> Cri.L.J. headnote(s)")
def api_headnote(
    req: HeadnoteRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Gated: deep_search feature."""
    with check_and_record(user.id, "deep_search", endpoint="headnote") as _record:
        return _api_headnote_impl(req, _record)


def _api_headnote_impl(req: HeadnoteRequest, _record):
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
    _record(cost_paise=int(total_paise or 0), model=opus_result.model_name)
    return {
        "result": parsed,
        "raw": opus_result.response,
        "meta": meta,
    }


@app.post("/api/translate", summary="Translate English JSON result to Hindi")
def api_translate(
    req: TranslateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Translate to Hindi. Gated: hindi_export feature (Monthly+ only).

    Demo and Weekly users get FeatureLocked → 402 with upgrade hint.
    """
    require_feature(user.id, "hindi_export")
    return _api_translate_impl(req)


def _api_translate_impl(req: TranslateRequest):
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

def _curated_browse_fallback(q: str) -> list[dict]:
    """Keyword-rank the curated corpus when IK is unavailable. Always works,
    even on an under-configured server. Returns up to 20 hits, browse-shaped."""
    cases = prefilter_cases(config.load_curated_corpus(), q, top_k=20)
    out: list[dict] = []
    for c in cases:
        kdoc = str(c.get("kanoon_doc_id") or "") or None
        headline = (c.get("holding") or c.get("facts") or "")[:300]
        out.append({
            "tid": kdoc or c.get("id"),
            "title": c.get("title", ""),
            "court": c.get("court", ""),
            "publishdate": str(c.get("year", "")),
            "headline": headline,
            "numcitedby": 0,
            "fame_indicator": "curated",
            "kanoon_url": f"https://indiankanoon.org/doc/{kdoc}/" if kdoc else None,
            "_source": "curated",
        })
    return out


@app.get("/api/browse/search", summary="Direct Indian Kanoon search (Browse view)")
def api_browse_search(
    q: str,
    court: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    judge: Optional[str] = None,
    statute: Optional[str] = None,
    sort: Optional[str] = None,
    page: int = 0,
):
    """Browse Judgments: pass a query through to Indian Kanoon and return
    light search-hit metadata for the UI list.

    Costs: ₹0.50 per search page (cached for 30 days). When IK isn't
    configured, falls back to keyword-ranking the curated corpus so the
    surface always returns *something*.

    Filters (translated into IK formInput tokens):
      court     — 'supremecourt', 'highcourts', or a partial HC name
      year_from / year_to — ISO years; appended as fromdate / todate
      judge     — bench-name substring (IK supports `bench:`)
      statute   — text the judgment must cite (IK `cites:`)
      sort      — 'recent' | 'cited' | 'relevance' (default)
    """
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="q is required")

    client = _get_kanoon_client()
    translation = maybe_translate(q)
    working = translation["english_query"]

    # Fallback path: IK is off → use the curated 42-case corpus
    if client is None:
        hits = _curated_browse_fallback(working)
        return {
            "query": q,
            "english_query": working,
            "input_script": translation["script"],
            "filters": {"court": court, "year_from": year_from, "year_to": year_to,
                        "judge": judge, "statute": statute, "sort": sort},
            "page": 0,
            "found": f"{len(hits)} curated matches",
            "hits": hits,
            "source": "curated-fallback",
            "note": "Indian Kanoon search is offline (token not set). Showing curated matches.",
        }

    # Build IK formInput from filters.
    #
    # IK's per-HC doctypes are single tokens (no spaces). We map common
    # human-typed values to the canonical token here, so a stale-cache UI
    # sending "madhya pradesh" still works.
    _HC_ALIASES = {
        "supreme court": "supremecourt", "sc": "supremecourt",
        "all high courts": "highcourts", "hc": "highcourts", "high court": "highcourts", "high courts": "highcourts",
        "allahabad": "allahabad", "allahabad hc": "allahabad", "allahabad high court": "allahabad",
        "andhra": "andhra", "andhra pradesh": "andhra", "andhra hc": "andhra", "andhra pradesh high court": "andhra",
        "bombay": "bombay", "bombay hc": "bombay", "bombay high court": "bombay",
        "calcutta": "kolkata", "kolkata": "kolkata", "calcutta hc": "kolkata", "calcutta high court": "kolkata",
        "chhattisgarh": "chattisgarh", "chattisgarh": "chattisgarh", "chhattisgarh high court": "chattisgarh",
        "delhi": "delhi", "delhi hc": "delhi", "delhi high court": "delhi",
        "gauhati": "gauhati", "guwahati": "gauhati", "gauhati high court": "gauhati",
        "gujarat": "gujarat", "gujarat hc": "gujarat", "gujarat high court": "gujarat",
        "himachal": "himachal_pradesh", "himachal pradesh": "himachal_pradesh", "himachal pradesh high court": "himachal_pradesh",
        "jammu": "jammu", "j&k": "jammu", "jammu and kashmir": "jammu", "jk": "jammu",
        "jharkhand": "jharkhand", "jharkhand high court": "jharkhand",
        "karnataka": "karnataka", "karnataka hc": "karnataka", "karnataka high court": "karnataka",
        "kerala": "kerala", "kerala hc": "kerala", "kerala high court": "kerala",
        "madhya pradesh": "madhyapradesh", "madhyapradesh": "madhyapradesh",
        "mp": "madhyapradesh", "mp hc": "madhyapradesh", "madhya pradesh high court": "madhyapradesh",
        "madras": "chennai", "chennai": "chennai", "tamil nadu": "chennai",
        "madras hc": "chennai", "madras high court": "chennai",
        "manipur": "manipur", "manipur high court": "manipur",
        "meghalaya": "meghalaya", "meghalaya high court": "meghalaya",
        "orissa": "orissa", "odisha": "orissa", "orissa high court": "orissa",
        "patna": "patna", "bihar": "patna", "patna high court": "patna",
        "punjab": "punjab", "punjab and haryana": "punjab", "punjab & haryana": "punjab",
        "p&h": "punjab", "punjab haryana": "punjab", "punjab and haryana high court": "punjab",
        "rajasthan": "rajasthan", "rajasthan hc": "rajasthan", "rajasthan high court": "rajasthan",
        "sikkim": "sikkim", "sikkim high court": "sikkim",
        "telangana": "telangana", "telangana hc": "telangana", "telangana high court": "telangana",
        "tripura": "tripura", "tripura high court": "tripura",
        "uttarakhand": "uttaranchal", "uttaranchal": "uttaranchal", "uttarakhand high court": "uttaranchal",
    }

    filters: list[str] = []
    if court:
        c = court.lower().strip()
        token = _HC_ALIASES.get(c, c)   # fall through with whatever the user sent
        filters.append(f"doctypes:{token}")
    else:
        filters.append("doctypes:supremecourt,highcourts")
    if year_from:
        filters.append(f"fromdate:{int(year_from)}-01-01")
    if year_to:
        filters.append(f"todate:{int(year_to)}-12-31")
    if judge and judge.strip():
        filters.append(f'bench:"{judge.strip()}"')
    if statute and statute.strip():
        # IK lets us pin search to documents that cite a specific statute
        filters.append(f'cites:"{statute.strip()}"')
    if sort == "recent":
        filters.append("sortby:mostrecent")
    elif sort == "cited":
        filters.append("sortby:citedcount")

    form_input = " ".join([working.strip()] + filters)

    try:
        page_result = client.search(form_input, pagenum=int(page or 0))
    except Exception as e:
        # Fall back rather than 502 — user gets *something*
        hits = _curated_browse_fallback(working)
        return {
            "query": q,
            "english_query": working,
            "input_script": translation["script"],
            "filters": {"court": court, "year_from": year_from, "year_to": year_to,
                        "judge": judge, "statute": statute, "sort": sort},
            "page": 0,
            "found": f"{len(hits)} curated matches",
            "hits": hits,
            "source": "curated-fallback",
            "note": f"IK search failed ({type(e).__name__}); showing curated matches.",
        }

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
            "_source": "ik",
        }
        for h in page_result.hits
    ]
    return {
        "query": q,
        "english_query": working,
        "input_script": translation["script"],
        "filters": {"court": court, "year_from": year_from, "year_to": year_to,
                    "judge": judge, "statute": statute, "sort": sort},
        "page": page_result.page,
        "found": page_result.found_label,
        "hits": hits,
        "source": "ik",
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
