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
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from headnote import __version__, config
from headnote import statute_map
from headnote.refine import refine_query, shallow_refine
from headnote.ranking import prerank_candidates
from headnote.api.models import (
    SituationRequest, DigestRequest, HeadnoteRequest,
    TranslateRequest, FeedbackRequest,
)
from headnote.api.ratelimit import (
    InMemoryRateLimiter as RateLimiter,
    client_ip_from_request,
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


# IPC ↔ BNS / CrPC ↔ BNSS / Evidence ↔ BSA mapping table.
# Used to auto-populate `bns_note` when the LLM leaves it blank or writes
# placeholder text. Covers the sections that show up most in criminal-law
# practice — extend as needed.
_BNS_MAP = [
    # (regex matching old code section, new code equivalent, short subject)
    (r"\bS(?:ection)?\.?\s*420\b.*?\bIPC\b",     "Section 318, BNS",   "cheating"),
    (r"\bS(?:ection)?\.?\s*406\b.*?\bIPC\b",     "Section 316, BNS",   "criminal breach of trust"),
    (r"\bS(?:ection)?\.?\s*376\b.*?\bIPC\b",     "Section 64, BNS",    "rape"),
    (r"\bS(?:ection)?\.?\s*498A\b.*?\bIPC\b",    "Section 85, BNS",    "cruelty by husband"),
    (r"\bS(?:ection)?\.?\s*302\b.*?\bIPC\b",     "Section 103, BNS",   "murder"),
    (r"\bS(?:ection)?\.?\s*304B\b.*?\bIPC\b",    "Section 80, BNS",    "dowry death"),
    (r"\bS(?:ection)?\.?\s*307\b.*?\bIPC\b",     "Section 109, BNS",   "attempt to murder"),
    (r"\bS(?:ection)?\.?\s*323\b.*?\bIPC\b",     "Section 115, BNS",   "voluntarily causing hurt"),
    (r"\bS(?:ection)?\.?\s*354\b.*?\bIPC\b",     "Section 74, BNS",    "outraging modesty"),
    (r"\bS(?:ection)?\.?\s*379\b.*?\bIPC\b",     "Section 303, BNS",   "theft"),
    (r"\bS(?:ection)?\.?\s*156\s*\(3\).*?\bCrPC\b", "Section 175(3), BNSS", "Magistrate FIR direction"),
    (r"\bS(?:ection)?\.?\s*482\b.*?\bCrPC\b",    "Section 528, BNSS",  "inherent powers"),
    (r"\bS(?:ection)?\.?\s*437\b.*?\bCrPC\b",    "Section 480, BNSS",  "regular bail"),
    (r"\bS(?:ection)?\.?\s*439\b.*?\bCrPC\b",    "Section 483, BNSS",  "HC/Sessions bail"),
    (r"\bS(?:ection)?\.?\s*438\b.*?\bCrPC\b",    "Section 482, BNSS",  "anticipatory bail"),
    (r"\bS(?:ection)?\.?\s*372\b.*?\bCrPC\b",    "Section 413, BNSS",  "victim appeal"),
    (r"\bS(?:ection)?\.?\s*27\b.*?\bEvidence\b", "Section 23, BSA",    "discovery statement"),
    (r"\bS(?:ection)?\.?\s*65B\b.*?\bEvidence\b","Section 63, BSA",    "electronic evidence"),
]


def _is_placeholder_bns(s: str) -> bool:
    """Detect the LLM's common 'no info' boilerplate so we can replace it
    with a real mapping rather than show 'pending editorial review' to a
    paying advocate."""
    if not s:
        return True
    sl = s.lower().strip()
    return (
        len(sl) < 8 or
        "pending" in sl or "tbd" in sl or "to be determined" in sl or
        "editorial review" in sl or "not applicable" in sl or
        "n/a" == sl or sl == "none"
    )


def _auto_bns_note(case: dict, refined_dual_map: list[dict] | None = None) -> str:
    """Build a real BNS/BNSS/BSA mapping note for the case.

    Strategy:
      1. If the refined query has a dual_statute_map (from canonicalize),
         use that — it's the authoritative cross-reference for THIS query.
      2. Otherwise, scan the case's text fields for known section refs and
         map via the local _BNS_MAP table.
      3. If nothing matches, return empty string (better than placeholder).
    """
    # Path 1: use refined.dual_statute_map verbatim
    if refined_dual_map:
        parts = []
        for ds in refined_dual_map[:4]:
            if isinstance(ds, dict) and ds.get("old") and ds.get("new"):
                subj = ds.get("subject", "")
                parts.append(
                    f"{ds['old']} → {ds['new']}"
                    + (f" ({subj})" if subj else "")
                )
        if parts:
            return "; ".join(parts)

    # Path 2: scan case content for sections, map via local table
    scan_text = " ".join(filter(None, [
        case.get("title") or "",
        case.get("relevance_explanation") or "",
        case.get("statute_index") or "",
        (case.get("journal_headnote") or {}).get("statute_index") or "",
        case.get("court_quote") or "",
    ]))
    hits = []
    seen = set()
    for pattern, new_section, subject in _BNS_MAP:
        if re.search(pattern, scan_text, flags=re.IGNORECASE):
            key = (new_section, subject)
            if key not in seen:
                seen.add(key)
                # Find the matched old section for a cleaner display
                m = re.search(pattern, scan_text, flags=re.IGNORECASE)
                old_token = m.group(0) if m else ""
                hits.append(f"{old_token} → {new_section} ({subject})")
    return "; ".join(hits[:3])


def _enrich_case(case: dict, meta_by_id: dict, refined_dual_map: list[dict] | None = None) -> dict:
    """Attach kanoon_doc_id, kanoon_url, kanoon_paragraph_url, fame_indicator,
    numcitedby, source, AND fix any title/outcome/bns_note degradations from
    the LLM. Non-destructive — overwrites only when we have better data.

    Pulls paragraph_anchor out of the nested journal_headnote block if the LLM
    placed it there (per the prompt schema), so the deep-link helper can use it.

    Backstops for the demo:
      - Title starting with '===' (broken HF import) → use meta.title
      - Outcome empty + meta.outcome present → use meta.outcome verbatim
      - bns_note placeholder ('pending editorial review') → compute from
        refined.dual_statute_map or scan-and-map.
    """
    cid = case.get("case_id")
    meta = meta_by_id.get(cid) or {}
    case["source"] = meta.get("source", case.get("source") or "ik")

    # Title backstop: if LLM echoed the broken '=== ... ===' title, replace
    # with the cleaned title from retrieval.
    t = (case.get("title") or "").strip()
    if (not t or t.startswith("===") or t.endswith("===") or "===" in t) and meta.get("clean_title"):
        case["title"] = meta["clean_title"]

    # Court backstop: prefer the retrieval-side label (which includes district)
    if meta.get("court") and not (case.get("court") or "").strip():
        case["court"] = meta["court"]

    # Outcome backstop: source label > LLM guess
    if meta.get("outcome"):
        # Only override if LLM left it empty or wrote vague text
        ll_outcome = (case.get("outcome") or "").strip().lower()
        if not ll_outcome or ll_outcome in {"other", "unknown", "tbd", "n/a"}:
            case["outcome"] = meta["outcome"]

    # BNS mapping backstop — replace placeholder text with real mapping
    if _is_placeholder_bns(case.get("bns_note") or ""):
        better = _auto_bns_note(case, refined_dual_map)
        if better:
            case["bns_note"] = better
        elif (case.get("bns_note") or "").lower().strip() in {
            "bns mapping pending editorial review", "pending", "tbd"
        }:
            # Strip placeholder rather than show it
            case["bns_note"] = ""

    # Anchor may live at top level OR nested under journal_headnote (journal style)
    anchor = (
        case.get("paragraph_anchor")
        or (case.get("journal_headnote") or {}).get("paragraph_anchor")
        or ""
    )
    if anchor and "paragraph_anchor" not in case:
        case["paragraph_anchor"] = anchor

    # Only use kanoon_doc_id if it came from the retrieval pool or curated corpus.
    # Removing the _kanoon_doc_id_from_case_id() fallback prevents LLM-hallucinated
    # case_ids from generating plausible-looking but wrong IK URLs.
    kdoc = meta.get("kanoon_doc_id")
    if kdoc:
        case["kanoon_doc_id"] = str(kdoc)
        case["kanoon_url"] = f"https://indiankanoon.org/doc/{kdoc}/"
        if anchor:
            tok = re.sub(r"^[\(\s]*Para[s]?[\s\.]*", "", anchor, flags=re.IGNORECASE).rstrip(") ").strip()
            # Para anchors can list multiple ("14, 16-17"); take the first
            tok = re.split(r"[,\s]", tok, maxsplit=1)[0].strip("()")
            # IK HTML uses id="p_14" for paragraphs — fragment must be #p_14 not #14
            if tok.isdigit():
                case["kanoon_paragraph_url"] = f"https://indiankanoon.org/doc/{kdoc}/#p_{tok}"
            elif tok:
                case["kanoon_paragraph_url"] = f"https://indiankanoon.org/doc/{kdoc}/#{tok}"
    if "numcitedby" not in case and "numcitedby" in meta:
        case["numcitedby"] = meta["numcitedby"]

    # Official Supreme Court copy — when retrieval cross-resolved this case to
    # our court-accepted open-data corpus, surface the official PDF + neutral
    # citation so the card can show the signed copy a court will accept (not
    # just the aggregator link).
    if meta.get("official_doc_id"):
        case["official_doc_id"]  = meta["official_doc_id"]
        case["official_pdf_url"] = (meta.get("official_pdf_url")
                                    or f"/api/judgment/pdf/{meta['official_doc_id']}")
        case["is_official_copy"] = True
        if meta.get("official_citation"):
            case["official_citation"] = meta["official_citation"]
    # "Reported in" row — every reporter the judgment appears in (SCC / AIR /
    # Cri.L.J. / SCALE …), plus the free court-issued neutral citation. Parsed
    # from IK but dropped on the way out until now; carry it through so the card
    # can show the full citation string a lawyer pastes into a pleading.
    cites_all = meta.get("citations_all") or []
    if cites_all and not case.get("citations_all"):
        case["citations_all"] = list(cites_all)
    neutral = meta.get("neutral_citation") or meta.get("official_citation") or ""
    if neutral and not case.get("neutral_citation"):
        case["neutral_citation"] = neutral
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


# ---- HSTS: force HTTPS for every browser that ever touches this domain ----
# Without HSTS, a browser that lands on http://headnote.in (e.g. user typed
# it without https://) is in an HTTP origin, which has SEPARATE localStorage
# from the HTTPS origin. Supabase session stored on HTTPS → invisible on
# HTTP → every API call returns 401 even though user "signed in". HSTS
# tells the browser "always use HTTPS for this domain", which prevents the
# split-origin trap entirely. max-age=1yr; includeSubDomains; preload.
@app.middleware("http")
async def _force_https_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    return response


_init_feedback_db()
init_telemetry_db()
app.include_router(admin_router)


# ----------------------------------------------------------------------
# HTTPS enforcement — fixes Chrome's "Not Secure" badge for HTTP visitors
# ----------------------------------------------------------------------
# Railway terminates TLS at its edge proxy and forwards plain HTTP to the
# container. The proxy sets X-Forwarded-Proto: https for HTTPS visitors
# and X-Forwarded-Proto: http for HTTP visitors. We use that header to
# redirect HTTP → HTTPS, and add HSTS so browsers remember to always use
# HTTPS for headnote.in.
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP requests to HTTPS based on the X-Forwarded-Proto
    header set by Railway's edge proxy. Skips /api/health for monitoring
    tools that may legitimately probe over HTTP."""

    async def dispatch(self, request, call_next):
        proto = request.headers.get("x-forwarded-proto", "").lower()
        # Only redirect if we know we're behind a proxy AND it's HTTP.
        # If header is missing (local dev, direct access), let it through.
        if proto == "http" and not request.url.path.startswith("/api/health"):
            https_url = str(request.url).replace("http://", "https://", 1)
            return RedirectResponse(url=https_url, status_code=301)
        response = await call_next(request)
        # HSTS — tell browsers to always use HTTPS for this domain for the
        # next year, include subdomains. Only set on actual HTTPS responses
        # so we don't accidentally lock HTTP visitors out before redirect.
        if proto == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


app.add_middleware(HTTPSRedirectMiddleware)


# -----------------------------------------------------------------------
# AUTO-RECOVERY: rebuild HF corpus + embeddings on boot if /data was wiped
# -----------------------------------------------------------------------
# Railway's volume mount is not persisting our /data SQLite across deploys
# (configuration issue we cannot fix from code). To make the system
# self-healing, on every container boot we check if the corpus is empty
# and, if so, spawn a background thread that:
#   1. Runs harvest_hf_corpus.py for all 5 IL-TUR subsets (~30 min)
#   2. Runs backfill_embeddings.py --skip-ik (~60-90 min)
#
# The server starts immediately and serves traffic against curated + IK
# live retrieval while the background rebuild runs. After ~90 min, full
# HF corpus is restored. Every deploy now self-heals.
#
# Gated by env var AUTO_REBUILD_CORPUS_ON_BOOT=true (defaults on).
# Requires HF_TOKEN to be set (already on Railway).

# Module-level rebuild status — visible on /api/health so we stop guessing
_AUTOREBUILD_STATUS: dict = {"state": "not_started", "detail": ""}


def _maybe_autorebuild_corpus_on_boot() -> None:
    import os as _os
    import threading as _threading
    import subprocess as _subprocess
    import logging as _log
    import time as _time
    from pathlib import Path as _Path

    global _AUTOREBUILD_STATUS
    logger = _log.getLogger("autorebuild")

    if _os.environ.get("AUTO_REBUILD_CORPUS_ON_BOOT", "true").lower() not in ("1", "true", "yes"):
        _AUTOREBUILD_STATUS = {"state": "disabled", "detail": "AUTO_REBUILD_CORPUS_ON_BOOT is off"}
        logger.info("[autorebuild] disabled via AUTO_REBUILD_CORPUS_ON_BOOT env")
        return

    hf_token_set = bool(_os.environ.get("HF_TOKEN", "").strip())
    if not hf_token_set:
        _AUTOREBUILD_STATUS = {
            "state": "skipped",
            "detail": "HF_TOKEN env var NOT SET on Railway. Set it to enable 290K corpus auto-rebuild.",
            "hf_token_configured": False,
        }
        logger.warning("[autorebuild] HF_TOKEN not set — skipping (set it on Railway to enable)")
        return

    # If the data path fell back to /tmp (Railway volume not properly
    # attached), the corpus we rebuild will be wiped on the next restart.
    # Don't burn CPU + SQLite I/O on work that won't survive. The system
    # will run on curated + IK live instead, which is faster anyway.
    try:
        from headnote import config as _cfg
        actual_path = str(_cfg.KANOON_CACHE_PATH)
        if "/tmp" in actual_path or actual_path.startswith("/tmp"):
            _AUTOREBUILD_STATUS = {
                "state": "skipped",
                "detail": f"Storage at {actual_path} (ephemeral /tmp). Attach Railway volume at /data.",
                "hf_token_configured": True,
            }
            logger.warning(
                "[autorebuild] data path is %s (ephemeral). Skipping rebuild — "
                "attach a Railway volume at /data to enable persistence + rebuild.",
                actual_path,
            )
            return
    except Exception as e:
        logger.warning("[autorebuild] could not check storage path (%s); proceeding anyway", e)

    # Check current corpus state
    try:
        from headnote.retrieval.hf_corpus import corpus_stats
        stats = corpus_stats()
        current_total = int(stats.get("total", 0) or 0)
    except Exception as e:
        logger.warning("[autorebuild] couldn't read corpus stats (%s); will attempt rebuild", e)
        current_total = 0

    # Target lowered to 40K (was 100K). We now import ONLY the display-clean
    # subsets: cjpe (35K, real SC judgments) + summ (7K) + pcr (~4K) = ~46K.
    # The lsi subset (66K) is DELIBERATELY EXCLUDED — it is anonymized
    # (<ACT>/<ENTITY>/<SECTION> masking) and unusable for legal display.
    # bail (176K Hindi district orders) is also excluded — no citations,
    # not verifiable. IK live retrieval (2.6 crore judgments) is the real
    # spine for breadth; the HF corpus is just a fast local semantic prior.
    _MIN_CORPUS_TARGET = int(os.environ.get("MIN_CORPUS_TARGET", "40000"))
    if current_total >= _MIN_CORPUS_TARGET:
        _AUTOREBUILD_STATUS = {
            "state": "healthy",
            "detail": f"Corpus has {current_total} rows (target ≥{_MIN_CORPUS_TARGET}) — no rebuild needed",
            "hf_token_configured": True,
            "corpus_total": current_total,
        }
        logger.info("[autorebuild] corpus already has %d rows (target %d); skipping rebuild", current_total, _MIN_CORPUS_TARGET)
        # Check embeddings separately — they may need backfill
        try:
            from headnote.retrieval.embeddings import EmbeddingIndex
            emb_stats = EmbeddingIndex().stats()
            emb_count = int(emb_stats.get("paragraph_count", 0) or 0)
            if emb_count < (current_total * 0.5):
                logger.info("[autorebuild] embeddings thin (%d paras for %d cases); spawning backfill",
                            emb_count, current_total)
                _spawn_backfill_thread(logger)
        except Exception as e:
            logger.warning("[autorebuild] embedding check failed: %s", e)
        return

    # Corpus is empty/thin — full rebuild needed
    _AUTOREBUILD_STATUS = {
        "state": "running",
        "detail": f"Corpus has {current_total} rows — FULL rebuild spawned (harvest → embed → metadata, ~90 min)",
        "hf_token_configured": True,
        "started_at": _time.time(),
    }
    logger.warning("[autorebuild] corpus has %d rows — spawning FULL rebuild thread", current_total)
    _spawn_full_rebuild_thread(logger)


# Module-level flag toggled by the rebuild worker thread. Read by
# retrieve_for_situation to skip HF corpus reads while a rebuild is
# actively writing to the same SQLite file. This prevents the
# single-writer lock contention that was making every user query
# wait 60+ sec behind the rebuild's writes.
import os as _bg_os
_REBUILD_FLAG_PATH = "/tmp/.headnote-rebuild-active"


def autorebuild_in_progress() -> bool:
    """True when the auto-rebuild worker is actively writing to SQLite.
    Retrieval skips HF reads during this window to avoid lock contention."""
    try:
        return _bg_os.path.exists(_REBUILD_FLAG_PATH)
    except Exception:
        return False


def _mark_rebuild_active(active: bool) -> None:
    try:
        if active:
            with open(_REBUILD_FLAG_PATH, "w") as f:
                f.write("1")
        else:
            try:
                _bg_os.remove(_REBUILD_FLAG_PATH)
            except FileNotFoundError:
                pass
    except Exception:
        pass


def _spawn_full_rebuild_thread(logger) -> None:
    import threading as _threading
    import subprocess as _subprocess
    import time as _time
    from pathlib import Path as _Path

    def _rebuild_worker():
        global _AUTOREBUILD_STATUS
        repo_root = _Path(__file__).resolve().parent.parent.parent
        t_start = _time.time()
        _mark_rebuild_active(True)
        try:
            # Phase 1: HARVEST — run subsets one at a time, smallest first.
            # The Railway volume may not fit all 5 subsets at once (bail=2.5GB,
            # lsi=1.5GB). By harvesting individually we guarantee the small
            # high-value subsets (cjpe, summ, pcr) get imported even if the
            # big ones don't fit. Each run is idempotent (INSERT OR IGNORE).
            _AUTOREBUILD_STATUS["phase"] = "harvest"
            # Priority order: English SC/HC first (most useful), then large
            # ONLY display-clean subsets. lsi (anonymized) and bail (no
            # citations) are excluded — see _MIN_CORPUS_TARGET comment.
            _subset_order = ["summ", "pcr", "cjpe"]
            harvested_subsets: list[str] = []
            failed_subsets: list[str] = []
            for subset in _subset_order:
                logger.warning("[autorebuild] === HARVEST subset=%s starting ===", subset)
                _AUTOREBUILD_STATUS["last_log"] = f"Harvesting subset: {subset}"
                harvest_cmd = ["python", "scripts/harvest_hf_corpus.py",
                              "--subsets", subset]
                proc = _subprocess.Popen(
                    harvest_cmd, cwd=str(repo_root),
                    stdout=_subprocess.PIPE, stderr=_subprocess.STDOUT,
                    text=True, bufsize=1,
                )
                last_lines: list[str] = []
                for line in proc.stdout or []:
                    logger.info("[autorebuild:harvest:%s] %s", subset, line.rstrip())
                    last_lines.append(line.rstrip())
                    if len(last_lines) > 5:
                        last_lines.pop(0)
                    _AUTOREBUILD_STATUS["last_log"] = line.rstrip()[:200]
                proc.wait()
                if proc.returncode == 0:
                    harvested_subsets.append(subset)
                    logger.warning("[autorebuild] === subset=%s done ===", subset)
                else:
                    failed_subsets.append(subset)
                    logger.warning(
                        "[autorebuild] subset=%s failed rc=%d (likely disk space) — continuing with others",
                        subset, proc.returncode,
                    )
            if not harvested_subsets:
                _AUTOREBUILD_STATUS = {
                    "state": "failed",
                    "phase": "harvest",
                    "detail": "All subsets failed — check Railway volume size (need ≥2GB free)",
                    "failed_subsets": failed_subsets,
                    "hf_token_configured": True,
                }
                logger.error("[autorebuild] ALL subsets failed; no corpus data imported")
                return
            logger.warning(
                "[autorebuild] === HARVEST done in %.0fs — imported: %s, failed: %s ===",
                _time.time() - t_start, harvested_subsets, failed_subsets or "none",
            )
            _AUTOREBUILD_STATUS["harvested_subsets"] = harvested_subsets
            _AUTOREBUILD_STATUS["failed_subsets"] = failed_subsets

            # Phase 2: EMBEDDINGS
            _AUTOREBUILD_STATUS["phase"] = "embeddings"
            t_emb = _time.time()
            logger.warning("[autorebuild] === EMBEDDING BACKFILL starting (~60-90 min) ===")
            backfill_cmd = ["python", "scripts/backfill_embeddings.py", "--skip-ik"]
            proc = _subprocess.Popen(
                backfill_cmd, cwd=str(repo_root),
                stdout=_subprocess.PIPE, stderr=_subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in proc.stdout or []:
                logger.info("[autorebuild:backfill] %s", line.rstrip())
                _AUTOREBUILD_STATUS["last_log"] = line.rstrip()[:200]
            proc.wait()
            logger.warning("[autorebuild] === EMBEDDING done in %.0fs ===", _time.time() - t_emb)

            # Phase 3: METADATA
            _AUTOREBUILD_STATUS["phase"] = "metadata"
            t_md = _time.time()
            logger.warning("[autorebuild] === METADATA BACKFILL starting (~15-25 min) ===")
            md_cmd = ["python", "scripts/backfill_metadata.py"]
            proc = _subprocess.Popen(
                md_cmd, cwd=str(repo_root),
                stdout=_subprocess.PIPE, stderr=_subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in proc.stdout or []:
                logger.info("[autorebuild:metadata] %s", line.rstrip())
                _AUTOREBUILD_STATUS["last_log"] = line.rstrip()[:200]
            proc.wait()
            total_elapsed = _time.time() - t_start
            logger.warning(
                "[autorebuild] === METADATA done in %.0fs, TOTAL %.0fs ===",
                _time.time() - t_md, total_elapsed,
            )

            # Done — update status with final corpus count
            try:
                from headnote.retrieval.hf_corpus import corpus_stats
                final_stats = corpus_stats()
                final_total = int(final_stats.get("total", 0) or 0)
            except Exception:
                final_total = -1
            _AUTOREBUILD_STATUS = {
                "state": "completed",
                "detail": f"Full rebuild done in {total_elapsed:.0f}s ({total_elapsed/60:.0f} min). Corpus: {final_total} rows.",
                "hf_token_configured": True,
                "corpus_total": final_total,
                "elapsed_seconds": round(total_elapsed, 0),
            }
        except Exception as e:
            _AUTOREBUILD_STATUS = {
                "state": "crashed",
                "detail": str(e)[:500],
                "hf_token_configured": True,
                "elapsed_seconds": round(_time.time() - t_start, 0),
            }
            logger.exception("[autorebuild] worker crashed: %s", e)
        finally:
            # Clear the circuit-breaker flag so retrieval re-enables HF reads
            _mark_rebuild_active(False)
            logger.warning("[autorebuild] rebuild flag cleared — HF reads re-enabled")

    t = _threading.Thread(target=_rebuild_worker, daemon=True, name="corpus-autorebuild")
    t.start()
    logger.warning("[autorebuild] background rebuild thread launched (server starts normally now)")


def _spawn_backfill_thread(logger) -> None:
    import threading as _threading
    import subprocess as _subprocess
    import time as _time
    from pathlib import Path as _Path

    def _backfill_only():
        repo_root = _Path(__file__).resolve().parent.parent.parent
        t_start = _time.time()
        _mark_rebuild_active(True)
        try:
            logger.warning("[autorebuild] embedding-only backfill starting")
            proc = _subprocess.Popen(
                ["python", "scripts/backfill_embeddings.py", "--skip-ik"],
                cwd=str(repo_root),
                stdout=_subprocess.PIPE, stderr=_subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in proc.stdout or []:
                logger.info("[autorebuild:backfill] %s", line.rstrip())
            proc.wait()
            logger.warning("[autorebuild] embedding-backfill done in %.0fs", _time.time() - t_start)

            # Metadata backfill — runs after embedding finishes since both
            # write to hf_judgments and SQLite write contention slows things.
            t_md = _time.time()
            logger.warning("[autorebuild] metadata backfill starting")
            proc = _subprocess.Popen(
                ["python", "scripts/backfill_metadata.py"],
                cwd=str(repo_root),
                stdout=_subprocess.PIPE, stderr=_subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in proc.stdout or []:
                logger.info("[autorebuild:metadata] %s", line.rstrip())
            proc.wait()
            logger.warning("[autorebuild] metadata-backfill done in %.0fs", _time.time() - t_md)
        except Exception as e:
            logger.exception("[autorebuild] backfill crashed: %s", e)
        finally:
            _mark_rebuild_active(False)
            logger.warning("[autorebuild] backfill flag cleared — HF reads re-enabled")

    t = _threading.Thread(target=_backfill_only, daemon=True, name="corpus-backfill")
    t.start()


# -----------------------------------------------------------------------
# SC OFFICIAL CORPUS: seed the persistent volume on first boot
# -----------------------------------------------------------------------
# The full judgments DB (metadata + offsets + extracted text + FTS) is ~950MB
# and grows; we DON'T ship that. What goes INSIDE the image is the ~14MB
# "core" (sc_judgments metadata + sc_tar_offsets) — enough to power the
# court-accepted moat the moment we go live:
#   • Supreme-Court-first ordering in research output
#   • IK→corpus cross-resolution (hand back the official neutral/SCR citation)
#   • tap → the REAL signed PDF (one HTTP Range GET, zero PDF storage)
# Full-text fact-pattern discovery (retrieval Stage 2.6) degrades gracefully to
# empty until the heavier text tables arrive later, so shipping core-only loses
# no correctness — only that one discovery feature.
#
# On boot, if the volume DB is absent/empty (and storage is a real volume, not
# ephemeral /tmp), we seed it from JUDGMENTS_CORE_URL (if set) or the baked-in
# judgments_core.sqlite. Backgrounded so it never blocks boot/healthcheck;
# never crashes the process. Gated by SC_BOOTSTRAP_ON_BOOT (default on).
_SC_BOOTSTRAP_STATUS: dict = {"state": "not_started", "detail": ""}


def _maybe_bootstrap_judgments_on_boot() -> None:
    import os as _os
    import shutil as _shutil
    import sqlite3 as _sq
    import threading as _threading
    import time as _time
    import logging as _log
    from pathlib import Path as _Path

    global _SC_BOOTSTRAP_STATUS
    logger = _log.getLogger("sc-bootstrap")

    if _os.environ.get("SC_BOOTSTRAP_ON_BOOT", "true").lower() not in ("1", "true", "yes"):
        _SC_BOOTSTRAP_STATUS = {"state": "disabled", "detail": "SC_BOOTSTRAP_ON_BOOT is off"}
        logger.info("[sc-bootstrap] disabled via SC_BOOTSTRAP_ON_BOOT env")
        return

    try:
        from headnote import config as _cfg
        from headnote.judgments import opendata as _od
        db_path = _Path(str(_cfg.JUDGMENTS_DB))
        baked = _Path(_cfg.PROJECT_ROOT) / "judgments_core.sqlite"
    except Exception as e:
        _SC_BOOTSTRAP_STATUS = {"state": "error", "detail": f"import/config failed: {e}"}
        logger.warning("[sc-bootstrap] config import failed: %s", e)
        return

    # Ephemeral storage (volume not attached) → a seed is wiped on next restart.
    # Don't bother; the app runs on curated + IK live + (degraded) SC anyway.
    sdb = str(db_path)
    if sdb.startswith("/tmp") or "/tmp/" in sdb:
        _SC_BOOTSTRAP_STATUS = {
            "state": "skipped",
            "detail": f"JUDGMENTS_DB at {sdb} (ephemeral /tmp). Attach a Railway volume at /data.",
        }
        logger.warning("[sc-bootstrap] %s is ephemeral — skipping seed", sdb)
        return

    # Two seed sources, in priority order:
    #   JUDGMENTS_FULL_URL — the heavy text-bearing DB (metadata + offsets +
    #       extracted text + deduped external-content FTS). Lights up full-text
    #       fact-pattern discovery (retrieval Stage 2.6). May be a .gz (streamed
    #       + gunzipped on the fly). Built by scripts/build_shippable_corpus.py.
    #   JUDGMENTS_CORE_URL / baked judgments_core.sqlite — the ~14MB metadata+
    #       offsets core (SC-first ordering, cross-resolution, tap→official PDF;
    #       full-text stays dark).
    full_url = _os.environ.get("JUDGMENTS_FULL_URL", "").strip()
    core_url = _os.environ.get("JUDGMENTS_CORE_URL", "").strip()

    # Inspect the current volume DB so we know what (if anything) to fetch.
    try:
        stats = _od.corpus_stats()
        judg = int(stats.get("judgments", 0) or 0)
        texts = int(stats.get("texts", 0) or 0)
    except Exception as e:
        judg = texts = 0
        logger.warning("[sc-bootstrap] stats check failed (%s); will attempt seed", e)

    # Steady state: full corpus already present (metadata + extracted text).
    if judg > 0 and texts > 0:
        _SC_BOOTSTRAP_STATUS = {
            "state": "healthy",
            "detail": f"corpus present — {judg} judgments, {texts} texts (full-text live)",
            "judgments": judg, "texts": texts,
        }
        logger.info("[sc-bootstrap] full corpus present (%s judgments, %s texts) — no seed",
                    judg, texts)
        return

    # Core present but NO text, and no source to upgrade from → serve degraded
    # (SC-first + official copies still work; only full-text discovery is dark).
    if judg > 0 and texts == 0 and not full_url:
        _SC_BOOTSTRAP_STATUS = {
            "state": "healthy",
            "detail": f"core present — {judg} judgments, 0 texts "
                      f"(full-text dark; set JUDGMENTS_FULL_URL to enable)",
            "judgments": judg, "texts": 0,
        }
        logger.info("[sc-bootstrap] core present, no text, no JUDGMENTS_FULL_URL — degraded")
        return

    # Otherwise seed/upgrade. Prefer the full DB (a superset of core) when a URL
    # is configured; else fall back to the remote/baked core.
    want = "full" if full_url else "core"
    cold = judg == 0  # brand-new volume → no SC capability at all yet

    def _download(url: str, tmp: _Path) -> None:
        """Stream a seed to ``tmp``; transparently gunzip when the URL ends .gz."""
        import requests as _rq
        import gzip as _gz
        with _rq.get(url, stream=True, timeout=(10, 120)) as r:
            r.raise_for_status()
            try:
                r.raw.decode_content = False  # we handle .gz ourselves
            except Exception:
                pass
            with open(tmp, "wb") as f:
                if url.endswith(".gz"):
                    with _gz.GzipFile(fileobj=r.raw) as gz:
                        _shutil.copyfileobj(gz, f, length=1 << 20)
                else:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        if chunk:
                            f.write(chunk)

    def _fetch(url: str, tmp: _Path, attempts: int = 4) -> None:
        """Download with retry + backoff. The multi-GB full-corpus pull is a
        once-per-volume event; a transient network blip mid-stream must
        self-heal rather than strand prod in degraded until the next redeploy."""
        last: Exception | None = None
        for i in range(1, attempts + 1):
            try:
                _download(url, tmp)
                return
            except Exception as e:  # noqa: BLE001 — retry any transport/IO error
                last = e
                try:
                    tmp.unlink()
                except FileNotFoundError:
                    pass
                if i < attempts:
                    wait = min(30, 2 ** i)
                    logger.warning("[sc-bootstrap] download attempt %s/%s failed "
                                   "(%s); retrying in %ss", i, attempts, e, wait)
                    _time.sleep(wait)
        raise last if last else RuntimeError("download failed")

    def _install(tmp: _Path) -> None:
        """Atomically swap ``tmp`` into place (drops stale wal/shm sidecars)."""
        for p in (db_path, _Path(sdb + "-wal"), _Path(sdb + "-shm")):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
        _os.replace(tmp, db_path)

    def _seed() -> None:
        global _SC_BOOTSTRAP_STATUS
        t0 = _time.time()
        tmp = _Path(sdb + ".seed-tmp")
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

            # Cold start + going for the (slow) full DB: install the baked core
            # FIRST so SC-first / official copies work within seconds, then
            # upgrade to full-text when the big download lands.
            if want == "full" and cold and baked.exists():
                _SC_BOOTSTRAP_STATUS = {"state": "running",
                    "detail": f"installing baked core {baked.name} before full download"}
                logger.warning("[sc-bootstrap] cold start — installing baked core first")
                _shutil.copyfile(baked, tmp)
                try:
                    cx = _sq.connect(f"file:{tmp.as_posix()}?mode=ro", uri=True)
                    nj0 = cx.execute("SELECT COUNT(*) FROM sc_judgments").fetchone()[0]
                    cx.close()
                except Exception:
                    nj0 = 0
                if nj0 > 0:
                    _install(tmp)
                    logger.warning("[sc-bootstrap] baked core live (%s judgments); "
                                   "downloading full corpus next", nj0)

            if want == "full":
                _SC_BOOTSTRAP_STATUS = {"state": "running",
                    "detail": f"downloading full corpus from {full_url}"}
                logger.warning("[sc-bootstrap] downloading FULL corpus from %s", full_url)
                _fetch(full_url, tmp)
                src_desc = full_url
            elif core_url:
                _SC_BOOTSTRAP_STATUS = {"state": "running",
                    "detail": f"downloading core from {core_url}"}
                logger.warning("[sc-bootstrap] downloading core DB from %s", core_url)
                _fetch(core_url, tmp)
                src_desc = core_url
            elif baked.exists():
                _SC_BOOTSTRAP_STATUS = {"state": "running",
                    "detail": f"copying baked-in {baked.name}"}
                logger.warning("[sc-bootstrap] copying baked-in core %s", baked)
                _shutil.copyfile(baked, tmp)
                src_desc = str(baked)
            else:
                _SC_BOOTSTRAP_STATUS = {
                    "state": "skipped",
                    "detail": "no JUDGMENTS_FULL_URL / JUDGMENTS_CORE_URL and no baked-in core",
                }
                logger.warning("[sc-bootstrap] no seed source available — skipping")
                return

            # Validate BEFORE swapping in. The full DB must carry text AND a
            # queryable FTS index — a truncated/corrupt download can yield a
            # structurally valid SQLite file whose sc_fts raises on MATCH, which
            # would 500 the research endpoint. Catch that here, stay degraded.
            nj = nt = 0
            fts_ok = (want != "full")  # core seeds carry no FTS — not required
            try:
                cx = _sq.connect(f"file:{tmp.as_posix()}?mode=ro", uri=True)
                nj = cx.execute("SELECT COUNT(*) FROM sc_judgments").fetchone()[0]
                try:
                    nt = cx.execute("SELECT COUNT(*) FROM sc_text").fetchone()[0]
                except Exception:
                    nt = 0
                if want == "full" and nt > 0:
                    try:
                        hits = cx.execute(
                            "SELECT COUNT(*) FROM sc_fts WHERE sc_fts MATCH 'evidence'"
                        ).fetchone()[0]
                        fts_ok = True  # queryable — hits count is informational
                        logger.warning("[sc-bootstrap] FTS probe ok — 'evidence' "
                                       "matches %s judgments", hits)
                    except Exception as fe:
                        fts_ok = False
                        logger.warning("[sc-bootstrap] FTS probe failed (%s) — "
                                       "rejecting seed as full-text-broken", fe)
                cx.close()
            except Exception as e:
                logger.warning("[sc-bootstrap] seed validation failed: %s", e)
            ok = nj > 0 and (nt > 0 if want == "full" else True) and fts_ok
            if not ok:
                _SC_BOOTSTRAP_STATUS = {"state": "error",
                    "detail": f"seed invalid (judgments={nj}, texts={nt}, "
                              f"fts_ok={fts_ok}, want={want}); not installed"}
                try:
                    tmp.unlink()
                except FileNotFoundError:
                    pass
                return

            _install(tmp)
            _SC_BOOTSTRAP_STATUS = {
                "state": "seeded",
                "detail": f"installed {nj} judgments / {nt} texts from {src_desc} "
                          f"in {_time.time()-t0:.1f}s",
                "judgments": nj, "texts": nt,
            }
            logger.warning("[sc-bootstrap] seeded %s judgments, %s texts → %s in %.1fs",
                           nj, nt, db_path, _time.time() - t0)
        except Exception as e:
            _SC_BOOTSTRAP_STATUS = {"state": "error", "detail": f"seed failed: {e}"}
            logger.exception("[sc-bootstrap] seed crashed: %s", e)
            try:
                tmp.unlink()
            except Exception:
                pass

    _SC_BOOTSTRAP_STATUS = {"state": "running", "detail": f"{want} seed scheduled"}
    _threading.Thread(target=_seed, daemon=True, name="sc-bootstrap").start()


# Fire the check at module import (uvicorn loads this before serving requests)
_maybe_autorebuild_corpus_on_boot()
_maybe_bootstrap_judgments_on_boot()

# Drafting engine (10 document types, story-first). Per-type templates
# ship one at a time; the API surface lives here from v0 so the FE can
# integrate against `/api/draft/*` while individual templates are ported.
from headnote.drafter.api import router as _drafter_router
from headnote.drafter.storage import init_drafts_db as _init_drafts_db

app.include_router(_drafter_router)
_init_drafts_db()

# Cases — CNR-driven case folders that pre-fill the drafter: /api/cases/*
# (SQLite, next to drafts; mock-first CNR adapter — see headnote/cases/.)
from headnote.api.cases import router as _cases_router
from headnote.cases.storage import init_cases_db as _init_cases_db
app.include_router(_cases_router)
_init_cases_db()

# Document Vault — OCR + searchable scanned case documents: /api/documents/*
# (SQLite, next to drafts/cases; reuses the Groq vision OCR + the shared
# fastembed model for hybrid keyword + semantic search — see headnote/documents/.)
from headnote.api.documents import router as _documents_router
from headnote.documents.storage import init_documents_db as _init_documents_db
app.include_router(_documents_router)
_init_documents_db()

# Recorder / consultations — record a client conversation → structured report
# that hands off to the drafter. See headnote/api/consultations.py.
from headnote.api.consultations import router as _consultations_router
from headnote.consultations.storage import init_consultations_db as _init_consultations_db
app.include_router(_consultations_router)
_init_consultations_db()

# ASK mode — the "AI for lawyers" conversational surface: /api/chat/message
# (streamed SSE, DeepSeek-backed, grounded on the IPC↔BNS concordance,
# no-bluff citation discipline — see headnote/api/chat.py + docs/CHAT_FEATURE.md.)
from headnote.api.chat import router as _chat_router
app.include_router(_chat_router)

# Legal Lens — annotate document text with explainable terms + statute refs
# (curated/verified data only): /api/lexicon/annotate. See headnote/api/lexicon.py.
from headnote.api.lexicon import router as _lexicon_router
app.include_router(_lexicon_router)

# In-app judgment viewer — /case/<doc_id> + /api/case/<doc_id>
# Lawyers click "Read judgment" → land here instead of an IK search redirect.
# Critical for the trust moat: full text, clean caption, provenance footer.
from headnote.api.case_viewer import router as _case_viewer_router
app.include_router(_case_viewer_router)

# Subscription / entitlements: /api/me, /api/plans, /admin/v2/*
from headnote.api.me import router as _me_router
from headnote.api.admin_v2 import router as _admin_v2_router

app.include_router(_me_router)
app.include_router(_admin_v2_router)

# Cashfree PG checkout: /api/payments/{create-order, webhook, verify, config}
from headnote.api.payments import router as _payments_router
app.include_router(_payments_router)

# Channel partners + referral codes admin: /admin/partners/*
from headnote.api.partners_admin import router as _partners_admin_router
app.include_router(_partners_admin_router)

# Onboarding side-effects: /api/onboarding/welcome-email
from headnote.api.onboarding import router as _onboarding_router
app.include_router(_onboarding_router)

# OTPless → Supabase auth bridge: /api/auth/otpless-exchange
# Verifies the OTPless short-lived token server-side, finds/creates the
# auth.users row, returns a hashed magic-link token the FE uses to mint a
# normal Supabase session (with refresh token + onAuthStateChange wiring).
from headnote.api.auth_otpless import router as _auth_otpless_router
app.include_router(_auth_otpless_router)

# Personal-assist escape hatches: /api/assist/{research,draft}
# Fired by the "Not satisfied? / Not finding what you need?" CTAs in the UI.
# Sends a Resend email to the founder inbox — SLA enforced manually.
from headnote.api.assist import router as _assist_router
app.include_router(_assist_router)

# Lawyer persona auto-fill: /api/lawyer-profile (GET, PATCH)
from headnote.api.lawyer_profile import router as _lawyer_profile_router
app.include_router(_lawyer_profile_router)

# Saved case-law library: /api/saved-caselaw (POST save, GET list, PATCH note,
# DELETE unsave). Per-user shelf of research hits the lawyer wants to keep. We
# snapshot the full situation-specific card as JSONB so it re-renders later
# with zero LLM cost. See migrations/008_saved_caselaw.sql.
from headnote.api.saved_caselaw import router as _saved_caselaw_router
app.include_router(_saved_caselaw_router)

# Lexlegis-style two-tier memorandum: /api/memorandum
from headnote.api.memorandum import router as _memorandum_router
app.include_router(_memorandum_router)

# Server-side PDF export: /api/draft/pdf — renders the drafted document to a
# real, text-selectable PDF (WeasyPrint). One blob powers Download, WhatsApp
# share, and the print fallback; replaces the broken html2canvas path.
from headnote.api.pdf import router as _draft_pdf_router
app.include_router(_draft_pdf_router)

# Official judgment corpus: /api/judgment/* — search the Supreme Court
# open-data set (court-accepted neutral + SCR citations) and stream the ACTUAL
# official judgment PDF on demand (single HTTP Range fetch from AWS Open Data,
# CC-BY-4.0; LRU-cached). This is the court-accepted-source layer that
# supplements Indian Kanoon's discovery aggregation.
from headnote.api.judgments import router as _judgments_router
app.include_router(_judgments_router)

# WhatsApp Business bot webhook: /api/whatsapp/webhook (GET handshake + POST).
# Phase 1 = echo bot to validate the round-trip with Meta's test number;
# the research pipeline gets wired in Phase 2. See docs/WHATSAPP_BOT_PRD.md.
from headnote.api.whatsapp import router as _whatsapp_router
app.include_router(_whatsapp_router)

# Bolna voice-agent sales pipeline: /api/bolna/* (webhook + 4 tool endpoints
# + admin /dial). Sits alongside whatsapp.py since both run off the same
# lead/phone identity. See docs/bolna_agent_prompt.md for the agent config.
from headnote.api.bolna import router as _bolna_router
app.include_router(_bolna_router)

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


@app.get("/auth-test", include_in_schema=False)
@app.get("/auth-test/", include_in_schema=False)
def auth_test():
    """Standalone auth diagnostic page — zero dependencies on auth.js or the
    app shell. Tests each step of the OAuth flow independently and shows
    results on-screen. Use when the main app's sign-in is broken and you
    can't open DevTools (e.g. testing on a phone)."""
    return FileResponse(config.STATIC_DIR / "auth-test.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/", include_in_schema=False)
def landing():
    return FileResponse(config.STATIC_DIR / "landing.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


# ---- SEO: sitemap.xml + robots.txt --------------------------------------
# Google can only rank what it discovers. The sitemap lists every public,
# crawlable page; robots.txt allows them, blocks app internals, and points
# crawlers at the sitemap. Submit https://headnote.in/sitemap.xml in Google
# Search Console after deploying.
_SITE_ORIGIN = "https://headnote.in"

# (url path, static file for <lastmod>, changefreq, priority)
_SITEMAP_PAGES = [
    ("/", "landing.html", "weekly", "1.0"),
    ("/pricing", "pricing.html", "monthly", "0.9"),
    ("/sections", "sections.html", "monthly", "0.9"),
    ("/app", "index.html", "weekly", "0.7"),
    ("/draft/bail", "draft-bail.html", "monthly", "0.8"),
    ("/draft/discharge", "draft-discharge.html", "monthly", "0.8"),
    ("/draft/complaint", "draft-complaint.html", "monthly", "0.8"),
    ("/draft/court", "draft-court.html", "monthly", "0.7"),
    ("/draft/smart", "draft-smart.html", "monthly", "0.7"),
    ("/contact", "contact.html", "yearly", "0.5"),
    ("/terms", "terms.html", "yearly", "0.3"),
    ("/privacy", "privacy.html", "yearly", "0.3"),
    ("/refund", "refund.html", "yearly", "0.3"),
]


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml():
    """XML sitemap of every public page — submit this URL in Search Console."""
    rows = []
    for path, fname, changefreq, priority in _SITEMAP_PAGES:
        lastmod = ""
        try:
            mtime = (config.STATIC_DIR / fname).stat().st_mtime
            day = datetime.fromtimestamp(mtime, timezone.utc).date().isoformat()
            lastmod = f"    <lastmod>{day}</lastmod>\n"
        except OSError:
            pass
        rows.append(
            "  <url>\n"
            f"    <loc>{_SITE_ORIGIN}{path}</loc>\n"
            f"{lastmod}"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            "  </url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(rows)
        + "\n</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    """Crawler directives: allow public pages, block app internals, point to sitemap."""
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /settings\n"
        "Disallow: /corpus\n"
        "Disallow: /drafter\n"
        "Disallow: /auth-test\n"
        "Disallow: /payment-success\n"
        "Disallow: /payment-failed\n"
        "Disallow: /api/\n"
        "\n"
        f"Sitemap: {_SITE_ORIGIN}/sitemap.xml\n"
    )
    return PlainTextResponse(body)


@app.get("/app", include_in_schema=False)
@app.get("/app/", include_in_schema=False)
def app_index():
    return FileResponse(config.STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/pricing", include_in_schema=False)
@app.get("/pricing/", include_in_schema=False)
def pricing_page():
    """Public pricing page — shows the four tiers + a CTA per plan."""
    return FileResponse(config.STATIC_DIR / "pricing.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


# ---- Legal & trust pages (required for Cashfree / RBI compliance) ----
@app.get("/terms", include_in_schema=False)
@app.get("/terms/", include_in_schema=False)
@app.get("/terms-of-service", include_in_schema=False)
def terms_page():
    return FileResponse(config.STATIC_DIR / "terms.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/privacy", include_in_schema=False)
@app.get("/privacy/", include_in_schema=False)
@app.get("/privacy-policy", include_in_schema=False)
def privacy_page():
    return FileResponse(config.STATIC_DIR / "privacy.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/refund", include_in_schema=False)
@app.get("/refund/", include_in_schema=False)
@app.get("/refund-policy", include_in_schema=False)
@app.get("/cancellation", include_in_schema=False)
def refund_page():
    return FileResponse(config.STATIC_DIR / "refund.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/contact", include_in_schema=False)
@app.get("/contact/", include_in_schema=False)
@app.get("/contact-us", include_in_schema=False)
def contact_page():
    return FileResponse(config.STATIC_DIR / "contact.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/settings", include_in_schema=False)
@app.get("/settings/", include_in_schema=False)
def settings_page():
    """Bar profile editor + sign-out. Auth handled client-side (settings.html
    reads /api/lawyer-profile; if not signed in, bounces to /app)."""
    return FileResponse(config.STATIC_DIR / "settings.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
def admin_panel():
    """Admin panel SPA. Access controlled by JWT (admin_users table) or
    ADMIN_TOKEN bearer; the HTML shell itself is inert without auth."""
    return FileResponse(config.STATIC_DIR / "admin.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/admin/partners", include_in_schema=False)
@app.get("/admin/partners/", include_in_schema=False)
def admin_partners_page():
    """Partner & referral-code dashboard. Inert shell — asks for ADMIN_TOKEN
    in-browser, then hits /admin/partners/list, /codes/all, /events, etc."""
    return FileResponse(config.STATIC_DIR / "admin-partners.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/corpus", include_in_schema=False)
@app.get("/corpus/", include_in_schema=False)
@app.get("/corpus.html", include_in_schema=False)
def corpus_admin():
    """Founder-only corpus admin page. One-click harvest + embedding backfill.
    Requires signed-in founder session — the page itself is inert without auth."""
    return FileResponse(config.STATIC_DIR / "corpus.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


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
    return FileResponse(config.STATIC_DIR / "drafter.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/sections", include_in_schema=False)
@app.get("/sections/", include_in_schema=False)
@app.get("/bns", include_in_schema=False)
@app.get("/ipc-to-bns", include_in_schema=False)
def sections_lookup_page():
    """Public IPC→BNS / CrPC→BNSS / Evidence→BSA section finder. Standalone
    page (no auth wrapper) — a free, shareable utility that doubles as an SEO
    funnel into the product. Data comes from the curated concordance via
    /api/mapping/lookup."""
    return FileResponse(config.STATIC_DIR / "sections.html",
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


# ---- Payment return pages (after Cashfree hosted checkout) ----
@app.get("/payments/return", include_in_schema=False)
@app.get("/payment-success", include_in_schema=False)
def payment_success_page():
    """Cashfree redirects here after the user finishes payment. The page
    polls /api/payments/verify?order_id=... to confirm with Cashfree and
    upgrade the subscription. Idempotent — webhook may have already run."""
    return FileResponse(config.STATIC_DIR / "payment-success.html",
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/payment-failed", include_in_schema=False)
def payment_failed_page():
    return FileResponse(config.STATIC_DIR / "payment-failed.html",
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/cases", include_in_schema=False)
@app.get("/cases/", include_in_schema=False)
def cases_page():
    """CNR-driven case folders → one-click pre-filled bail/discharge drafts."""
    return FileResponse(config.STATIC_DIR / "cases.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


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
    return FileResponse(config.STATIC_DIR / "draft-bail.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/documents", include_in_schema=False)
@app.get("/documents/", include_in_schema=False)
def documents_page():
    """Document Vault — upload scanned/handwritten case documents (postmortem
    notes, FIRs, affidavits, orders), OCR them, and search the whole pile by
    keyword AND meaning. Static SPA; talks to /api/documents/*."""
    return FileResponse(config.STATIC_DIR / "documents.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/recorder", include_in_schema=False)
@app.get("/recorder/", include_in_schema=False)
def recorder_page():
    """Recorder — record an in-person lawyer–client consultation, transcribe it
    (Groq Whisper), and generate a structured legal work-product report (facts,
    issues, next steps) that hands off to the drafter. Static SPA; talks to
    /api/consultations/*."""
    return FileResponse(config.STATIC_DIR / "recorder.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/recovery", include_in_schema=False)
@app.get("/draft/recovery/", include_in_schema=False)
def draft_recovery_page():
    """Recovery-of-money draft pack — pre-suit legal notice + summary-suit
    (Order XXXVII CPC) plaint with verification + affidavit. Civil/author-tier
    (outside the reviewed bail-family set): a fill-in, shareable template for the
    personal-assist queue. Static page; placeholders fill client-side. Marked
    noindex until advocate-reviewed."""
    return FileResponse(config.STATIC_DIR / "draft-recovery.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/maintenance", include_in_schema=False)
@app.get("/draft/maintenance/", include_in_schema=False)
def draft_maintenance_page():
    """Maintenance draft pack — §144 BNSS (§125 CrPC) petition + interim-maintenance
    application + the mandatory Rajnesh v. Neha Affidavit of Assets & Liabilities.
    Bilingual (EN/हिं), author-tier from the maintenance framework for advocate
    review. Static page; placeholders fill client-side. Marked noindex until reviewed."""
    return FileResponse(config.STATIC_DIR / "draft-maintenance.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/defamation", include_in_schema=False)
@app.get("/draft/defamation/", include_in_schema=False)
def draft_defamation_page():
    """Civil-defamation draft pack — cease-and-desist legal notice + plaint for damages
    & permanent injunction + Order XXXIX interim-injunction application. Bilingual
    (EN/हिं), author-tier (tort, off the reviewed bail set) for advocate review. Static
    page; placeholders fill client-side. Marked noindex until reviewed."""
    return FileResponse(config.STATIC_DIR / "draft-defamation.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/assist", include_in_schema=False)
@app.get("/assist/", include_in_schema=False)
def assist_intake_page():
    """Personal-Assist self-serve intake — a lawyer describes what they need and
    the page calls /api/draft/assist-route: known types return the clean
    /draft/<type> link instantly, everything else is authored on the spot by the
    guarded engine (no fabricated case law). Static page; marked noindex."""
    return FileResponse(config.STATIC_DIR / "assist.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/rfa", include_in_schema=False)
@app.get("/draft/rfa/", include_in_schema=False)
def draft_rfa_page():
    """Regular First Appeal (RFA) draft pack — civil first appeal from an original
    decree under §96 read with Order XLI CPC: Memorandum of Appeal (grounds of
    objection) + Order XLI Rule 5 stay-of-execution application + §5 Limitation Act
    condonation-of-delay application. Bilingual (EN/हिं) with a District/High-Court
    tier toggle; author-tier (civil, off the reviewed bail set) for advocate review.
    Static page; placeholders fill client-side. Marked noindex until reviewed."""
    return FileResponse(config.STATIC_DIR / "draft-rfa.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/rent", include_in_schema=False)
@app.get("/draft/rent/", include_in_schema=False)
def draft_rent_page():
    """Rent agreement / lease deed — a fill-in, shareable residential tenancy
    template (parties, premises, rent, term, security + standard covenants).
    Bilingual (EN/हिं) with English→Devanagari transliteration; deterministic
    client-side fill, server-PDF Print/WhatsApp/per-doc Save-PDF. Author-tier
    (personal-assist queue, outside the reviewed litigation set). Static page;
    marked noindex until reviewed."""
    return FileResponse(config.STATIC_DIR / "draft-rent.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/discharge", include_in_schema=False)
@app.get("/draft/discharge/", include_in_schema=False)
def draft_discharge_page():
    """§239 CrPC / §262 BNSS discharge drafter — live form + charge-sheet/FIR
    OCR + live preview + save + PDF, in the /draft/bail style. Deterministic
    render (no LLM writes any text)."""
    return FileResponse(config.STATIC_DIR / "draft-discharge.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/discharge/review", include_in_schema=False)
def draft_discharge_review(draft: str | None = None):
    """Read-only sample render — advocate quick-review fallback (no JS).
    Canonical-header rebuild (bilingual, court-parameterized §262/250). Supersedes
    the old discharge_239 render.

    ?draft=<id> renders that saved draft's answers instead of the sample —
    used by the Cases feature to preview a CNR-prefilled discharge application."""
    from fastapi.responses import HTMLResponse
    from headnote.drafter.templates.discharge import review_page_html
    data = None
    if draft:
        from headnote.drafter import storage as _ds
        d = _ds.get_draft(draft)
        if d is not None:
            data = d.answers
    return HTMLResponse(review_page_html(data),
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


# --- Phase-2 deterministic builders — advocate review pages (no JS, sample
# render). Each is a PROPOSAL pending Vishnu ji's sign-off; the full form/OCR
# pages are built once he approves the drafting. Same pattern as the discharge
# review route above. ---

@app.get("/draft/anticipatory/review", include_in_schema=False)
def draft_anticipatory_review():
    """§482 BNSS (438 CrPC) anticipatory bail — sample render for review."""
    from fastapi.responses import HTMLResponse
    from headnote.drafter.templates.anticipatory_bail import review_page_html
    return HTMLResponse(review_page_html(),
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/maintenance/review", include_in_schema=False)
def draft_maintenance_review():
    """§144 BNSS (125 CrPC) maintenance (कुटुम्ब न्यायालय) — sample render for review."""
    from fastapi.responses import HTMLResponse
    from headnote.drafter.templates.maintenance import review_page_html
    return HTMLResponse(review_page_html(),
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/appeal/review", include_in_schema=False)
def draft_appeal_review():
    """Criminal appeal against conviction §415 BNSS (374 CrPC) — bilingual sample on
    the canonical header (section-labelled; impugned-judgment recital · acquittal prayer).
    Repointed to the canonical-standard builder (supersedes appeal_conviction.py)."""
    from fastapi.responses import HTMLResponse
    from headnote.drafter.templates.appeal import review_page_html
    return HTMLResponse(review_page_html(),
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/vakalatnama/review", include_in_schema=False)
def draft_vakalatnama_review():
    """Vakalatnama (वकालतनामा) — sample render for review."""
    from fastapi.responses import HTMLResponse
    from headnote.drafter.templates.vakalatnama import review_page_html
    return HTMLResponse(review_page_html(),
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/cheque/review", include_in_schema=False)
def draft_cheque_review():
    """§138 NI Act cheque-dishonour complaint — BILINGUAL sample render (the first
    builder on the canonical pixel-exact header). Hindi sheet + English sheet."""
    from fastapi.responses import HTMLResponse
    from headnote.drafter.templates.cheque_138 import review_page_html
    return HTMLResponse(review_page_html(),
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/bail/review", include_in_schema=False)
def draft_bail_new_review(draft: str | None = None):
    """Unified bail engine (Magistrate §480 / Sessions §483 / HC §483 + anticipatory
    §482) on the canonical header — bilingual multi-court sample render.

    ?draft=<id> renders that saved draft's answers instead of the sample —
    used by the Cases feature to preview a CNR-prefilled bail application."""
    from fastapi.responses import HTMLResponse
    from headnote.drafter.templates.bail import review_page_html
    data = None
    if draft:
        from headnote.drafter import storage as _ds
        d = _ds.get_draft(draft)
        if d is not None:
            data = d.answers
    return HTMLResponse(review_page_html(data),
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/revision/review", include_in_schema=False)
def draft_revision_review():
    """Criminal revision §438-442/§397-401 (पुनरीक्षण) — bilingual sample on the
    canonical header (section-labelled; impugned-order recital + 90-day limitation)."""
    from fastapi.responses import HTMLResponse
    from headnote.drafter.templates.revision import review_page_html
    return HTMLResponse(review_page_html(),
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/dv/review", include_in_schema=False)
def draft_dv_review():
    """Domestic Violence §12 PWDVA — bilingual sample on the canonical header
    (व्यथित/प्रत्यर्थीगण · §17-22 relief blocks · सत्यापन)."""
    from fastapi.responses import HTMLResponse
    from headnote.drafter.templates.dv import review_page_html
    return HTMLResponse(review_page_html(),
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/quashing/review", include_in_schema=False)
def draft_quashing_review():
    """Quashing §528 BNSS / §482 CrPC — bilingual sample on the canonical header
    (आवेदक/अनावेदक · compromise/राजीनामा basis · संक्षेप विवरण + आधार)."""
    from fastapi.responses import HTMLResponse
    from headnote.drafter.templates.quashing import review_page_html
    return HTMLResponse(review_page_html(),
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/parivad/review", include_in_schema=False)
def draft_parivad_review():
    """Private complaint §223 BNSS / §200 CrPC — bilingual sample on the canonical
    header (परिवादी/आरोपीगण · cognizance-summon-punish prayer · witness list)."""
    from fastapi.responses import HTMLResponse
    from headnote.drafter.templates.parivad import review_page_html
    return HTMLResponse(review_page_html(),
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/api/draft/fields/{doc_type}", include_in_schema=False)
def draft_field_schema(doc_type: str, court: str = "sessions", bail_type: str = "regular"):
    """Input-field schema for a draft type — the per-client variables the lawyer
    fills + the toggles ('what more can change'). The form UI renders from this."""
    from fastapi.responses import JSONResponse
    if doc_type == "bail":
        from headnote.drafter.templates.bail import field_spec
        return JSONResponse(field_spec(court, bail_type))
    if doc_type in ("cheque", "cheque_138"):
        from headnote.drafter.templates.cheque_138 import field_spec
        return JSONResponse(field_spec())
    if doc_type == "discharge":
        from headnote.drafter.templates.discharge import field_spec
        return JSONResponse(field_spec(court))
    if doc_type == "maintenance":
        from headnote.drafter.templates.maintenance import field_spec
        return JSONResponse(field_spec())
    if doc_type == "revision":
        from headnote.drafter.templates.revision import field_spec
        return JSONResponse(field_spec(court))
    if doc_type == "appeal":
        from headnote.drafter.templates.appeal import field_spec
        return JSONResponse(field_spec(court))
    if doc_type == "dv":
        from headnote.drafter.templates.dv import field_spec
        return JSONResponse(field_spec())
    if doc_type == "quashing":
        from headnote.drafter.templates.quashing import field_spec
        return JSONResponse(field_spec())
    if doc_type == "parivad":
        from headnote.drafter.templates.parivad import field_spec
        return JSONResponse(field_spec())
    if doc_type == "vakalatnama":
        from headnote.drafter.templates.vakalatnama import field_spec
        return JSONResponse(field_spec())
    return JSONResponse({"error": f"no field schema registered for '{doc_type}'"}, status_code=404)


def _draft_module(doc_type: str):
    """Resolve a draft type → its builder module (field_spec + render_hi/render_en)."""
    if doc_type == "bail":
        from headnote.drafter.templates import bail as m; return m
    if doc_type in ("cheque", "cheque_138"):
        from headnote.drafter.templates import cheque_138 as m; return m
    if doc_type == "discharge":
        from headnote.drafter.templates import discharge as m; return m
    if doc_type == "maintenance":
        from headnote.drafter.templates import maintenance as m; return m
    if doc_type == "revision":
        from headnote.drafter.templates import revision as m; return m
    if doc_type == "appeal":
        from headnote.drafter.templates import appeal as m; return m
    if doc_type == "dv":
        from headnote.drafter.templates import dv as m; return m
    if doc_type == "quashing":
        from headnote.drafter.templates import quashing as m; return m
    if doc_type == "parivad":
        from headnote.drafter.templates import parivad as m; return m
    if doc_type == "vakalatnama":
        from headnote.drafter.templates import vakalatnama as m; return m
    return None


def _draft_spec(mod, doc_type: str, court: str, bail_type: str) -> dict:
    if doc_type == "bail":
        return mod.field_spec(court, bail_type)
    if doc_type in ("discharge", "revision", "appeal"):
        return mod.field_spec(court)
    return mod.field_spec()


class DraftTweakRequest(BaseModel):
    doc_type: str = Field(..., description="bail · cheque · discharge · maintenance · revision")
    data: dict = Field(default_factory=dict, description="current draft values")
    prompt: str = Field(..., description="the lawyer's natural-language tweak")
    court: str = "sessions"
    bail_type: str = "regular"
    use_llm: bool = True


@app.post("/api/draft/tweak", include_in_schema=False)
def draft_tweak(req: DraftTweakRequest):
    """Prompt-based tweak: a lawyer's natural-language change → STRUCTURED PATCH
    (DeepSeek intent-router → Groq → heuristic fallback) → deterministic re-render.
    The LLM only turns known knobs (field values · reviewed-ground toggles · variant)
    and captures the lawyer's own extra ground (flagged). It never writes boilerplate,
    sections, or citations — those stay template-/verified-sourced."""
    from fastapi.responses import JSONResponse
    from headnote.drafter import prompt_tweak
    mod = _draft_module(req.doc_type)
    if mod is None:
        return JSONResponse({"error": f"no draft builder for '{req.doc_type}'"}, status_code=404)
    spec = _draft_spec(mod, req.doc_type, req.court, req.bail_type)
    result = prompt_tweak.tweak(spec, req.data, req.prompt, use_llm=req.use_llm)
    out = {"ok": True, **result,
           "html_hi": mod.render_hi(result["data"]),
           "html_en": mod.render_en(result["data"])}
    return JSONResponse(out)


class DraftRenderRequest(BaseModel):
    doc_type: str = Field(..., description="bail · cheque · discharge · maintenance · revision · appeal · dv · quashing · parivad · vakalatnama")
    data: dict = Field(default_factory=dict, description="current draft field values")
    court: str = "sessions"
    bail_type: str = "regular"


@app.post("/api/draft/render", include_in_schema=False)
def draft_render(req: DraftRenderRequest):
    """Canonical live render — the Drafting Studio's preview engine. Maps a draft
    type + field values → the deterministic bilingual document (Hindi source of truth
    + English mirror). Same builders as the /draft/*/review pages; no LLM."""
    from fastapi.responses import JSONResponse
    from headnote.drafter.bundle import assemble
    mod = _draft_module(req.doc_type)
    if mod is None:
        return JSONResponse({"error": f"no draft builder for '{req.doc_type}'"}, status_code=404)
    return JSONResponse(assemble(mod, req.data))


class DraftTranslateRequest(BaseModel):
    fields: dict = Field(default_factory=dict)
    target: str = "hi"


@app.post("/api/draft/translate", include_in_schema=False)
def draft_translate(req: DraftTranslateRequest):
    """Live value-translation for the V2 editor — type in any language, the
    document renders in the document's language. Free Google→MyMemory (no key)."""
    from fastapi.responses import JSONResponse
    from headnote.translate import _translate_string
    out = {}
    for k, v in (req.fields or {}).items():
        out[k] = _translate_string(v, req.target) if isinstance(v, str) and v.strip() else v
    return JSONResponse({"ok": True, "translated": out})


@app.get("/draft/bail-regular/review", include_in_schema=False)
def draft_bail_regular_review():
    """Regular bail §483/439 (Sessions; §480/437 Magistrate) — BILINGUAL sample on
    the canonical header. (New-standard builder; the legacy /draft/bail live page
    still uses bail_application.py until migrated.)"""
    from fastapi.responses import HTMLResponse
    from headnote.drafter.templates.bail_regular import review_page_html
    return HTMLResponse(review_page_html(),
                        headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/complaint", include_in_schema=False)
@app.get("/draft/complaint/", include_in_schema=False)
def draft_complaint_application():
    """परिवाद (§498A complaint) drafter — deterministic bilingual split-pane UI.

    Same engine as the bail page: the document renders 100% client-side from
    the form, so the EN/हिं toggle is an instant, format-identical re-render
    (no LLM for layout). The cause-title sits in the right half of the page to
    mirror the court's filing format. Only the names + facts the lawyer types
    route through the best-effort /api/draft/translate-fields call on toggle;
    if it fails the UI still switches, so nothing breaks.

    Output: print-perfect Hindi/English PDF (server-side WeasyPrint) for filing
    before a Judicial Magistrate First Class.
    """
    return FileResponse(config.STATIC_DIR / "draft-complaint.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/template/{doc_type}", include_in_schema=False)
@app.get("/draft/template/{doc_type}/", include_in_schema=False)
def draft_template_drafter(doc_type: str):
    """The EXISTING universal editor (all V1 features). For the reviewed canonical
    types its /api/draft/template-schema + /api/draft/render-template calls are
    served by the V2 deterministic engine; for other ids, the legacy LLM path."""
    return FileResponse(config.STATIC_DIR / "draft-template.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/court", include_in_schema=False)
@app.get("/draft/court/", include_in_schema=False)
@app.get("/draft/court/{court_id}", include_in_schema=False)
@app.get("/draft/court/{court_id}/", include_in_schema=False)
def draft_court_page(court_id: str = "all"):
    """Court drill-down / template browser.

    With no court_id (or court_id='all'): shows all templates with filter chips.
    With a court_id: pre-selects that court's filter chip.

    court_id is one of: sc, hc, sessions, magistrate, family, procedural.
    Validation happens client-side; unknown ids render an empty state.

    Same SPA shell served regardless — JS calls /api/draft/courts and renders
    the matching filter using URL-based chip pre-selection."""
    return FileResponse(config.STATIC_DIR / "draft-court.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/draft/smart", include_in_schema=False)
@app.get("/draft/smart/", include_in_schema=False)
def draft_smart():
    """Smart Drafter — conversational AI document composer.

    Lawyer picks a template (Vakalatnama, Anticipatory Bail, Quashing
    Petition, Writ, …) or describes the matter in plain language, the
    conductor (Claude Haiku) asks contextual follow-ups one at a time, and
    Sonnet generates the full document at the end. Voice input on every
    chat turn. Live preview pane (pull-up sheet on mobile) renders the
    document as it materialises.
    """
    return FileResponse(config.STATIC_DIR / "draft-smart.html", headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@app.get("/api/config", summary="Public frontend configuration (non-secret)")
def api_config():
    """Returns the public Supabase credentials so auth.js can initialise the
    Supabase client without hardcoding keys in static files.

    The anon key is intentionally public — it is constrained by Supabase RLS
    policies and is safe to expose in the browser.

    code_version: bumped on every deploy so the frontend can detect stale JS
    running in an old browser tab. If the frontend's baked-in version is older,
    it force-reloads once to pick up the new code.
    """
    import os as _os_cfg
    return {
        "supabase_url":      config.SUPABASE_URL or "",
        "supabase_anon_key": config.SUPABASE_ANON_KEY or "",
        # OTPLESS_APP_ID is public-safe (their SDK requires it in a data-attr).
        # Only the client SECRET is server-side. If empty, auth.js keeps the
        # "Continue with phone" button hidden so users don't see a broken CTA.
        "otpless_app_id":    _os_cfg.environ.get("OTPLESS_APP_ID", ""),
        "code_version":      "20260527a",
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


@app.get("/api/auth-verify", summary="Verify a JWT and return decoded info")
def auth_verify(authorization: str | None = Header(default=None)):
    """Debug endpoint — send a Bearer token and see exactly how the backend
    interprets it. Returns user_id + email on success, or the exact error
    if verification fails. Useful for diagnosing 'always 401' issues from
    a phone browser where DevTools is unavailable."""
    import traceback as _tb
    from headnote.entitlements.auth import _extract_bearer, _decode_token, _user_from_claims
    token = _extract_bearer(authorization)
    if not token:
        return {
            "ok": False,
            "error": "no_token",
            "detail": "No 'Authorization: Bearer <token>' header found.",
            "hint": "Open browser DevTools → Console → run: "
                    "headnoteAuth.getAccessToken().then(t => console.log(t))",
        }
    try:
        claims = _decode_token(token)
        user = _user_from_claims(claims)
        return {
            "ok": True,
            "user_id": user.id,
            "email": user.email,
            "role": user.role,
            "exp": claims.get("exp"),
            "aud": claims.get("aud"),
            "iss": claims.get("iss"),
        }
    except HTTPException as e:
        return {"ok": False, "error": "jwt_invalid", "detail": e.detail}
    except Exception as e:
        return {"ok": False, "error": "unexpected", "detail": str(e),
                "trace": _tb.format_exc()[-500:]}


@app.get("/api/debug/paths", summary="Inspect actual storage paths in use (DEBUG)")
def debug_paths():
    """Show where the SQLite cache + embedding index are actually living.
    Critical for diagnosing Railway volume mount issues — if KANOON_CACHE_PATH
    fell back to /tmp, all corpus data is lost on restart.
    """
    import os as _os
    from pathlib import Path as _P
    paths = {}
    for env, default_attr in [
        ("KANOON_CACHE_PATH", "KANOON_CACHE_PATH"),
        ("FEEDBACK_DB",       "FEEDBACK_DB"),
    ]:
        configured = _os.environ.get(env)
        actual = getattr(config, default_attr, None)
        actual_path = _P(str(actual)) if actual else None
        exists = actual_path.exists() if actual_path else False
        size_mb = round(actual_path.stat().st_size / 1024 / 1024, 2) if exists else 0
        is_tmp = actual_path and "/tmp" in str(actual_path)
        # Check writability of parent dir
        parent_writable = False
        if actual_path:
            try:
                test = actual_path.parent / ".write_test"
                test.touch()
                test.unlink()
                parent_writable = True
            except Exception:
                parent_writable = False
        paths[env] = {
            "configured_env":  configured,
            "actual":          str(actual) if actual else None,
            "exists":          exists,
            "size_mb":         size_mb,
            "fell_back_to_tmp": bool(is_tmp),
            "parent_writable": parent_writable,
        }
    # Also list /data contents if present
    try:
        data_files = []
        if _P("/data").exists():
            for f in _P("/data").iterdir():
                try:
                    data_files.append({
                        "name": f.name,
                        "size_mb": round(f.stat().st_size / 1024 / 1024, 2),
                        "is_dir": f.is_dir(),
                    })
                except Exception:
                    pass
    except Exception as e:
        data_files = [{"error": str(e)[:200]}]
    return {
        "paths": paths,
        "/data_contents": data_files,
        "running_as_uid": _os.getuid() if hasattr(_os, "getuid") else None,
    }


@app.get("/api/debug/llm", summary="Minimal LLM invocation test (DEBUG)")
def debug_llm_invoke():
    """Fire a minimal LLM call through call_claude_cached so we can see the
    exact path taken (Anthropic / DeepSeek / Groq) and any errors without
    needing a signed-in /api/situation roundtrip.
    """
    import os as _os
    from headnote.llm.client import call_claude_cached, _LLM_PROVIDER, _deepseek_primary
    try:
        text, usage = call_claude_cached(
            system_prompt="Reply with exactly the single word: OK",
            user_prompt="Test ping",
            model="claude-haiku-4-5",
            max_tokens=20,
            cache=False,
        )
        return {
            "ok": True,
            "llm_provider_env": _LLM_PROVIDER,
            "deepseek_primary": _deepseek_primary(),
            "model_used": usage.get("model"),
            "response": text[:100],
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "exc_type": type(exc).__name__,
            "message": str(exc)[:1000],
            "llm_provider_env": _LLM_PROVIDER,
            "deepseek_primary": _deepseek_primary(),
        }


@app.get("/api/debug/deepseek", summary="Directly test DeepSeek API (DEBUG)")
def debug_deepseek_direct():
    """Bypass the Headnote fallback chain entirely — call DeepSeek's API
    directly and report the exact response (or error). This is the only
    way to confirm DEEPSEEK_API_KEY is valid + the endpoint is reachable
    + the model is being called correctly.
    """
    import os as _os
    key = _os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return {
            "ok": False,
            "error": "DEEPSEEK_API_KEY env var is empty or missing on Railway",
            "fix": "Open Railway → Variables → add DEEPSEEK_API_KEY with your key from platform.deepseek.com",
        }

    # Mask the key for the response so we can confirm it's set without leaking
    masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "(too short)"

    try:
        from openai import OpenAI
    except ImportError as e:
        return {"ok": False, "error": f"openai SDK not installed: {e}"}

    client = OpenAI(
        api_key=key,
        base_url="https://api.deepseek.com",
        timeout=30.0,
    )

    # Try both models — V3 (cheap) first, then R1
    results = {"key_masked": masked, "key_length": len(key)}
    for model in ["deepseek-chat", "deepseek-reasoner"]:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Reply with exactly OK."},
                    {"role": "user",   "content": "ping"},
                ],
                max_tokens=10,
                temperature=0.0,
            )
            results[model] = {
                "ok": True,
                "response": (resp.choices[0].message.content or "")[:50],
                "input_tokens": getattr(resp.usage, "prompt_tokens", 0) if resp.usage else 0,
                "output_tokens": getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0,
            }
        except Exception as e:
            # Surface the raw error so we can see exactly what DeepSeek is rejecting
            err_msg = str(e)[:800]
            err_type = type(e).__name__
            results[model] = {
                "ok": False,
                "error_type": err_type,
                "error": err_msg,
            }
    return results


def _effective_situation_model(deep_mode: bool) -> str:
    """The model alias the situation call will ACTUALLY use, after the latency
    guard.

    Under DeepSeek-primary (production), `sonnet`/`opus` map to
    deepseek-reasoner (R1) which runs 60-120s (up to its 180s client timeout).
    Stacked on IK retrieval that alone takes 30-70s, the request blows past
    Railway's edge proxy timeout and the user sees a 502/504 ("server took too
    long"). R1 is correct ONLY for the explicit deep-mode opt-in. For the
    DEFAULT (non-deep) first attempt we clamp to the fast model
    (haiku -> deepseek-chat / V3, ~10-30s) so a normal research query ALWAYS
    lands inside the budget. This keeps the code safe even when the Railway
    env var SITUATION_MODEL is left at `sonnet`.

    Returns a short alias: 'haiku' | 'sonnet' | 'opus' (or a full claude- id
    if an operator pinned one).
    """
    if deep_mode:
        return config.SITUATION_DEEP_MODEL
    choice = config.SITUATION_MODEL
    try:
        from headnote.llm.client import _deepseek_primary
        if _deepseek_primary() and choice in ("sonnet", "opus"):
            return "haiku"
    except Exception:
        pass
    return choice


@app.get("/api/health", summary="Liveness check + config summary")
def health():
    # Add HF corpus stats so we can confirm the import landed without
    # querying the DB directly.
    try:
        from headnote.retrieval.hf_corpus import corpus_stats
        hf = corpus_stats()
    except Exception:
        hf = {"total": 0, "configured": False}

    # Surface the LLM backend state so an operator can see which provider
    # path is active (Anthropic primary, DeepSeek primary, or fallback).
    import os as _os
    llm_block: dict = {
        "llm_provider_env":    _os.environ.get("LLM_PROVIDER", "auto"),
        "has_anthropic_key":   bool(config.ANTHROPIC_API_KEY),
        "has_deepseek_key":    bool(_os.environ.get("DEEPSEEK_API_KEY", "").strip()),
        "has_groq_key":        bool(_os.environ.get("GROQ_API_KEY", "").strip()),
    }
    try:
        from headnote.llm.client import (
            _deepseek_primary, _CLAUDE_TO_DEEPSEEK, _to_deepseek_model,
        )
        from headnote.llm.router import _resolve_force_model
        _dp = _deepseek_primary()
        llm_block["deepseek_primary"] = _dp
        llm_block["claude_to_deepseek_map"] = dict(_CLAUDE_TO_DEEPSEEK)
        # Which model research ACTUALLY runs on right now — the single most
        # important field for diagnosing "research is slow / times out". Under
        # DeepSeek-primary, sonnet/opus -> deepseek-reasoner (R1, slow);
        # haiku -> deepseek-chat (V3, fast). `*_effective` reflects the
        # non-deep latency-guard clamp (see _effective_situation_model).
        llm_block["situation_model_env"] = config.SITUATION_MODEL
        llm_block["situation_deep_model_env"] = config.SITUATION_DEEP_MODEL
        for _key, _alias in (
            ("situation_effective", _effective_situation_model(False)),
            ("situation_deep_effective", _effective_situation_model(True)),
        ):
            _claude_id = _resolve_force_model(_alias) or _alias
            llm_block[_key] = _to_deepseek_model(_claude_id) if _dp else _claude_id
    except Exception as e:
        llm_block["error"] = str(e)[:200]

    # Embedding index stats — confirms backfill ran
    try:
        from headnote.retrieval.embeddings import EmbeddingIndex
        emb = EmbeddingIndex().stats()
    except Exception as e:
        emb = {"error": str(e)[:200]}

    # Auto-rebuild status — the definitive answer to "why is corpus 0?"
    import os as _os2
    rebuild_block = dict(_AUTOREBUILD_STATUS)
    rebuild_block["hf_token_configured"] = bool(_os2.environ.get("HF_TOKEN", "").strip())
    rebuild_block["rebuild_flag_active"] = autorebuild_in_progress()

    # Official SC corpus — seed/bootstrap status + live counts (judgments,
    # offset coverage, extracted-text coverage). The answer to "is the SC
    # official-source layer live, and how much of it?"
    try:
        from headnote.judgments import opendata as _od_h
        sc_corpus_block = {"bootstrap": dict(_SC_BOOTSTRAP_STATUS), **_od_h.corpus_stats()}
    except Exception as e:
        sc_corpus_block = {"bootstrap": dict(_SC_BOOTSTRAP_STATUS), "error": str(e)[:200]}

    return {
        "ok":         True,
        **config.summary(),
        "hf_corpus":  hf,
        "embeddings": emb,
        "llm_backend": llm_block,
        "autorebuild": rebuild_block,
        "sc_corpus":  sc_corpus_block,
    }


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


@app.get("/api/mapping/lookup", summary="IPC↔BNS / CrPC↔BNSS / Evidence↔BSA section finder")
def api_mapping_lookup(q: str = "", limit: int = 8):
    """Resolve a free-text query ('420', 'IPC 302', 'BNS 318', 'cheating',
    '438 crpc', Devanagari digits) to ranked concordance entries with a
    side-by-side diff. Pure curated-data lookup — no LLM, no network."""
    limit = max(1, min(limit, 25))
    return statute_map.lookup(q, limit=limit)


@app.get("/api/mapping/popular", summary="Most-looked-up section chips for the empty state")
def api_mapping_popular():
    return {"suggestions": statute_map.popular(), "meta": statute_map._public_meta()}


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


# ---------------------------------------------------------------------------
# Public, anonymous "taste the product" endpoint.
#
# Landing-page visitors run ONE real research query and see up to 2 real
# authorities BEFORE signing up. NO auth, NO entitlement metering. Cost is
# kept near-zero: it serves the canned demo bank first, then a LOCAL-CORPUS-
# ONLY retrieval (no paid Indian Kanoon live calls, no reranker LLM, no
# refine LLM). Hard-capped at 2 cases and rate-limited per IP.
# ---------------------------------------------------------------------------

class TryRequest(BaseModel):
    """Input for the public POST /api/try. Permissive on length (we trim/cap
    and handle empty in the handler) so a landing-page visitor never hits a
    422 — unlike the authed SituationRequest which enforces min/max length."""
    situation: str = Field("", description="Lawyer's free-text query.")


# Per-process, in-memory limiter (see headnote.api.ratelimit). 5 tries / hour
# / IP. NOTE: this counter is per-worker — move to Redis for multi-instance
# scale (the module docstring explains the trade-off).
_TRY_RATE_LIMITER = RateLimiter(max_requests=5, window_seconds=3600)

_TRY_MAX_SITUATION_CHARS = 600


def _try_court_tier(court: str) -> str:
    """Map a court label to the contract tier. Default 'SC'."""
    c = (court or "").lower()
    if "constitution bench" in c or "constitutional bench" in c:
        return "CB"
    if "supreme court" in c:
        return "SC"
    if "high court" in c:
        return "HC"
    return "SC"


def _try_one_sentence(text: str, limit: int = 240) -> str:
    """Trim arbitrary case text to a single concise sentence for `held`."""
    if not text:
        return ""
    s = " ".join(str(text).split())
    # First sentence boundary (., !, ? followed by space/end), else hard cap.
    m = re.search(r"(.+?[.!?])(?:\s|$)", s)
    one = m.group(1) if m else s
    if len(one) > limit:
        one = one[:limit].rsplit(" ", 1)[0].rstrip() + "…"
    return one.strip()


def _try_map_demo_case(c: dict) -> dict:
    """Map a canned demo-bank case dict → the /api/try contract shape."""
    pn = c.get("practitioner_notes") or {}
    held = (pn.get("one_line_topic") or "").strip()
    if not held:
        held = _try_one_sentence(
            c.get("relevance_explanation")
            or c.get("quotable_phrase")
            or ""
        )
    return {
        "tier": _try_court_tier(c.get("court", "")),
        "title": c.get("title", "") or "",
        "citation": c.get("citation", "") or "",
        "held": held,
        "tag": "bail granted" if c.get("outcome") == "bail-granted" else None,
    }


def _try_map_retrieval_case(cs) -> dict:
    """Map a retrieval CaseSummary → the /api/try contract shape.

    `held` is derived WITHOUT an LLM call: the top paragraph text trimmed to a
    single sentence, falling back to the case title.
    """
    held = ""
    paras = getattr(cs, "paragraphs", None) or []
    if paras:
        held = _try_one_sentence(" ".join(p.text for p in paras[:1]))
    if not held:
        held = _try_one_sentence(getattr(cs, "title", "") or "")
    return {
        "tier": _try_court_tier(getattr(cs, "court", "")),
        "title": getattr(cs, "title", "") or "",
        "citation": getattr(cs, "citation", "") or "",
        "held": held,
        "tag": "bail granted" if getattr(cs, "outcome", "") == "bail-granted" else None,
    }


@app.post("/api/try", summary="Public anonymous taste-the-product query (rate-limited)")
async def api_try(req: TryRequest, request: Request):
    """ONE free research query for landing-page visitors. No auth, no metering.

    Cheap by construction: canned demo bank first, then LOCAL-CORPUS-ONLY
    retrieval (zero paid IK live calls, no reranker / refine LLM). Returns at
    most 2 authorities plus the true total so the UI can offer "Unlock all N".
    """
    # --- Rate limit (per IP, sliding window) ---
    ip = client_ip_from_request(request)
    verdict = await _TRY_RATE_LIMITER.check(ip)
    if not verdict.allowed:
        return JSONResponse(
            status_code=429,
            content={
                "ok": False,
                "error": "rate_limited",
                "message": (
                    "You've used your free preview queries for now. "
                    "Sign up to keep researching — or try again in a bit."
                ),
                "retry_after": verdict.retry_after,
            },
        )

    # --- Input hygiene: trim + cap; empty -> graceful empty result ---
    situation = (req.situation or "").strip()
    if len(situation) > _TRY_MAX_SITUATION_CHARS:
        situation = situation[:_TRY_MAX_SITUATION_CHARS].rstrip()
    if not situation:
        return {
            "ok": True,
            "source": "demo",
            "query": "",
            "cases": [],
            "total": 0,
            "remaining_tries": verdict.remaining,
        }

    # --- Source A: canned demo bank (free, instant) ---
    try:
        from headnote import demo_responses
        demo_hit = demo_responses.try_demo_response(situation)
    except Exception as e:
        print(f"[try] demo lookup failed: {type(e).__name__}: {e}")
        demo_hit = None

    if demo_hit is not None:
        all_cases = (demo_hit.get("result") or {}).get("cases") or []
        mapped = [_try_map_demo_case(c) for c in all_cases[:2]]
        return {
            "ok": True,
            "source": "demo",
            "query": situation,
            "cases": mapped,
            "total": len(all_cases),
            "remaining_tries": verdict.remaining,
        }

    # --- Source B: LOCAL-CORPUS-ONLY retrieval (no paid IK, no LLM) ---
    # We DO need a real KanoonClient object (retrieve_for_situation reads its
    # offline spend ledger + SQLite cache path), but the PAID IK live-search
    # stage is fully suppressed:
    #   * skip_ik_search_if_cases_at_least=0  -> run_ik_search is ALWAYS False
    #     (verifiable_count >= 0 is always true in mixed mode), so the only
    #     client.search()/client.get_doc() *paid* calls never execute.
    #   * mode="mixed"  -> does not force IK on (only 'hidden'/'famous' do).
    #   * refined_query=None  -> no refine_query() LLM call.
    #   * time_budget_seconds=0.0 -> the reranker time-gate trips, so the
    #     Sonnet/DeepSeek reranker LLM never fires (free semantic order used).
    # Net: free local sources only (curated + cached-paragraph semantic + HF
    # corpus). Held lines are derived from paragraph text — no LLM.
    client = _get_kanoon_client()
    if client is None:
        # IK disabled / no token -> no local retrieval path available here.
        # Degrade gracefully rather than reaching for any paid/LLM fallback.
        return {
            "ok": True,
            "source": "live",
            "query": situation,
            "cases": [],
            "total": 0,
            "remaining_tries": verdict.remaining,
        }

    cases = []
    try:
        from headnote.kanoon.retrieval import retrieve_for_situation
        ret = retrieve_for_situation(
            situation,
            client=client,
            curated_corpus=config.load_curated_corpus(),
            top_cases=2,
            mode="mixed",                       # never forces paid IK on
            refined_query=None,                 # no refine LLM
            skip_ik_search_if_cases_at_least=0,  # guarantees IK live is skipped
            time_budget_seconds=0.0,            # guarantees reranker LLM skipped
        )
        cases = list(ret.cases)
    except Exception as e:
        print(f"[try] local retrieval failed: {type(e).__name__}: {e}")
        cases = []

    mapped = [_try_map_retrieval_case(cs) for cs in cases[:2]]
    return {
        "ok": True,
        "source": "live",
        "query": situation,
        "cases": mapped,
        "total": len(cases),
        "remaining_tries": verdict.remaining,
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
    with check_and_record(user.id, "deep_search", endpoint="situation", email=user.email) as _record:
        return _api_situation_impl(req, _record)


def _build_situation_shells(retrieval_cases: list, limit: int = 6) -> list:
    """Lightweight, REAL card previews emitted before the LLM writes analysis.

    Each shell is a verified retrieved case (never fabricated) carrying enough
    to render a card immediately: title, court, year, the "Reported in"
    citations, authority count, and a provisional "why" lifted from the
    top-ranked Indian Kanoon paragraph. The LLM's final selection is a subset
    of these (the client matches by case_id), so painting them early never
    surfaces a case that later gets retracted.
    """
    shells: list = []
    ordered = sorted(
        retrieval_cases,
        key=lambda cs: getattr(cs, "relevance_score", 0.0) or 0.0,
        reverse=True,
    )
    for cs in ordered[:limit]:
        paras = getattr(cs, "paragraphs", None) or []
        why = ""
        if paras:
            why = (getattr(paras[0], "text", "") or "").strip()
            if len(why) > 240:
                why = why[:237].rstrip() + "…"
        src = getattr(cs, "source", "ik") or "ik"
        shells.append({
            "case_id": cs.case_id,
            "title": cs.title,
            "court": cs.court,
            "year": cs.year,
            "citation": cs.citation,
            "citations_all": list(getattr(cs, "citations_all", []) or []),
            "neutral_citation": (getattr(cs, "neutral_citation", "")
                                 or getattr(cs, "scr_citation", "") or ""),
            "numcitedby": getattr(cs, "numcitedby", 0) or 0,
            "fame_indicator": ("curated" if src == "curated"
                               else _fame_indicator(getattr(cs, "numcitedby", 0) or 0)),
            "official_doc_id": getattr(cs, "official_doc_id", "") or "",
            "source": src,
            "why_provisional": why,
        })
    return shells


@app.post("/api/situation/stream", summary="Situation -> progressive precedents (NDJSON)")
def api_situation_stream(
    req: SituationRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Progressive variant of /api/situation. Streams newline-delimited JSON:

      {"type":"shells","cases":[...]}   real verified cases, the instant
                                        retrieval finishes (before the LLM)
      {"type":"result", ...}            full payload, identical to
                                        /api/situation, once analysis is done
      {"type":"error","message":...}    pipeline failure; client falls back

    /api/situation is unchanged and remains the client's fallback. Same gate
    (deep_search) and same single quota charge as the classic endpoint.
    """
    # Gate up-front: quota / entitlement errors must surface as a clean status
    # BEFORE the 200 stream opens (a half-open stream can't carry a 402/429).
    _cm = check_and_record(user.id, "deep_search", endpoint="situation", email=user.email)
    _record = _cm.__enter__()

    def generate():
        import queue as _queue
        import threading as _threading
        _SENTINEL = object()
        bus: "_queue.Queue" = _queue.Queue()

        def _on_retrieved(shells):
            bus.put(("shells", {"cases": shells}))

        def _worker():
            try:
                res = _api_situation_impl(req, _record, on_retrieved=_on_retrieved)
                bus.put(("result", res))
            except Exception as exc:  # surfaced to the client + logged
                print(f"[situation-stream] pipeline error: {type(exc).__name__}: {exc}")
                bus.put(("error", {"message": str(exc)}))
            finally:
                bus.put(_SENTINEL)

        worker = _threading.Thread(target=_worker, daemon=True)
        worker.start()
        errored = False
        try:
            while True:
                item = bus.get()
                if item is _SENTINEL:
                    break
                kind, data = item
                if kind == "error":
                    errored = True
                payload = {"type": kind}
                payload.update(data)
                yield json.dumps(payload, ensure_ascii=False) + "\n"
            worker.join(timeout=2)
        finally:
            # Meter on success; on failure pass the exception into the CM so the
            # quota increment is SKIPPED — a client fallback to /api/situation
            # then charges exactly once.
            try:
                if errored:
                    _cm.__exit__(RuntimeError, RuntimeError("situation stream failed"), None)
                else:
                    _cm.__exit__(None, None, None)
            except Exception:
                pass

    return StreamingResponse(generate(), media_type="application/x-ndjson")


def _api_situation_impl(req: SituationRequest, _record, on_retrieved=None):
    # `on_retrieved`: optional callback(shells: list[dict]) invoked the moment
    # retrieval finishes — BEFORE the 10-30s LLM call — so the streaming
    # endpoint can paint real card shells immediately. None on the classic
    # JSON path, which then behaves exactly as before.
    # Per-stage wall-clock timing. Logged at the end of the function so
    # Railway logs show exactly where the seconds went on a slow query.
    # This is the difference between "blindly tweaking the pipeline" and
    # "lower max_new_fetches because IK fetches actually took 12s."
    _stage_t: dict[str, float] = {}
    _t_total = time.time()
    def _stage(name: str, since: float) -> None:
        _stage_t[name] = round(time.time() - since, 2)

    # ── DEMO MODE ── Pre-built research responses for a fixed bank of
    # canonical Indian criminal-law queries. Intercepts BEFORE any LLM call
    # or retrieval. Set DISABLE_DEMO_RESPONSES=true in env to bypass.
    #
    # AUTO-DISABLE when a real LLM provider is available: demo responses
    # use the old output schema (no stinger_sentence / held_line / court_quote
    # / match_dimensions / negative_carve_out). Serving them when DeepSeek
    # is working produces worse output than a real call. Only fall back to
    # demo mode when explicitly enabled AND no LLM provider is reachable.
    _demo_env = os.environ.get("DISABLE_DEMO_RESPONSES", "").lower()
    _demo_explicitly_enabled = _demo_env in {"0", "false", "no"}
    _demo_disabled = _demo_env in {"1", "true", "yes"}
    if not _demo_disabled:
        # Skip demo mode when a real LLM is available (DeepSeek or Anthropic)
        from headnote.llm.client import _deepseek_primary
        _has_real_llm = _deepseek_primary() or bool(config.ANTHROPIC_API_KEY)
        if _has_real_llm and not _demo_explicitly_enabled:
            pass  # skip demo — real LLM will produce better output
        else:
            from headnote import demo_responses
            demo_hit = demo_responses.try_demo_response(req.situation, req.deep_mode)
            if demo_hit is not None:
                # Sleep a realistic interval so the spinner pacing matches a real call.
                time.sleep(demo_responses.realistic_demo_delay())
                demo_hit["meta"]["original_query"] = req.situation
                demo_hit["meta"]["english_query"] = (
                    req.situation if demo_hit["meta"].get("input_script") == "latin" else ""
                )
                # Record against quota + cost meter exactly like a real call
                _record(
                    cost_paise=int(demo_hit["meta"].get("cost_paise", 0)),
                    model=demo_hit["meta"].get("model"),
                )
                print(f"[situation-demo] matched canned response, returning in "
                      f"{demo_hit['meta'].get('elapsed_seconds')}s")
                return demo_hit

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

    # Stage 1: query refinement — try LLM-powered refine_query() first with
    # a tight 12s timeout. If it completes (typical: 3-8s on V3), we get a
    # rich structured envelope (statutes, doctrines, parties, dual-code map,
    # factual archetype) that feeds into:
    #   - retrieval: search_terms() generates precise IK keywords
    #   - V2 prompt: LLM gets structured context instead of empty fields
    #   - reranker: uses structured query for better scoring
    #
    # If V3 is slow (>12s) or fails, fall back to shallow_refine() (instant,
    # regex-only) — no worse than before but AT MOST 12s of pipeline budget
    # spent, not the 45-65s that was causing 502s.
    _REFINE_TIMEOUT = 12.0
    _t = time.time()
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout
        with ThreadPoolExecutor(max_workers=1) as _pool:
            _future = _pool.submit(refine_query, working_situation)
            refined = _future.result(timeout=_REFINE_TIMEOUT)
        print(
            f"[situation] refine_query OK in {time.time()-_t:.1f}s — "
            f"statute={refined.primary_statute}, intent={refined.intent_type}, "
            f"doctrines={refined.doctrines_at_issue}"
        )
    except Exception as _refine_exc:
        refined = shallow_refine(working_situation)
        print(
            f"[situation] refine_query failed/timed out in {time.time()-_t:.1f}s "
            f"({type(_refine_exc).__name__}) — using shallow_refine fallback"
        )
    _stage("02b_refine", _t)

    ik_meta_extra: dict = {}
    prerank_scores: list = []
    verification_report: Optional[dict] = None
    evidence: list = []
    retrieval_cases: list = []

    # Pipeline time budget. The frontend AbortController fires at 180s.
    # The pipeline makes sequential LLM calls:
    #   - refine_query (capped at 12s thread timeout)
    #   - reranker (~5-15s, skippable by time budget gate)
    #   - main LLM (V3: typical 10-30s; deep_mode R1 60-120s)
    # V3 is the default again (R1 caused first-attempt timeouts). With the
    # anonymized-case filter the corpus JSON is smaller → V3 is faster still.
    # Budget: 150s total, leaves 30s safety buffer before 180s FE abort.
    _PIPELINE_DEADLINE_SECONDS = 150.0       # total cap (30s buffer before 180s FE abort)

    # Dynamic retrieval budget: subtract time already consumed by translate +
    # refine, then reserve 65s for the main V3 LLM call (typical 10-30s, with
    # headroom for the Groq fallback). Whatever's left is retrieval budget.
    _elapsed_before_retrieval = time.time() - _t_total
    _RETRIEVAL_TIME_BUDGET = max(
        45.0,  # absolute minimum — IK search + fetch needs 30-45s
        _PIPELINE_DEADLINE_SECONDS - _elapsed_before_retrieval - 65.0,
    )
    print(
        f"[situation] pipeline budget: {_elapsed_before_retrieval:.1f}s already used "
        f"(translate+refine), retrieval gets {_RETRIEVAL_TIME_BUDGET:.0f}s"
    )

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
            refined_query=refined.to_dict(),
            time_budget_seconds=_RETRIEVAL_TIME_BUDGET,
        )
        _stage("03_retrieve", _t)
        retrieval_cases = list(ret.cases)
        evidence = ret.evidence
        curated_lookup = {c["id"]: c for c in curated}
        corpus_json = result_to_prompt_corpus_json(ret, curated_lookup)
        sys_prompt = build_situation_system_prompt(req.style, corpus_json) + IK_PROMPT_ADDENDUM

        # Log what retrieval surfaced — critical for diagnosing "LLM
        # returned 0 cases" scenarios. Without this we can't tell whether
        # the retrieval pool was empty or the LLM rejected everything.
        _by_source: dict[str, int] = {}
        for cs in retrieval_cases:
            _by_source[cs.source] = _by_source.get(cs.source, 0) + 1
        print(
            f"[situation-retrieve] surfaced {len(retrieval_cases)} cases "
            f"by source={_by_source}, evidence_paragraphs={len(evidence)}, "
            f"corpus_json_chars={len(corpus_json)}"
        )
        for i, cs in enumerate(retrieval_cases[:10]):
            print(
                f"  [{i+1}] {cs.case_id} | {cs.source} | "
                f"score={cs.relevance_score:.2f} | {cs.title[:80]}"
            )
        if ret.meta.notes:
            print(f"[situation-retrieve-notes] {ret.meta.notes}")
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
        # Skip prerank when the candidate pool is small. The prerank LLM call
        # takes 5-15 sec; pointless to rank 10 candidates with an LLM before
        # the main LLM also picks 5 from those same 10. Just pass them all
        # through and let the main LLM rank in one shot.
        if len(candidate_pool) <= 12:
            pool_for_llm = candidate_pool
            pruned = candidate_pool          # keep `pruned` defined for meta block
            prerank_scores = []
            prerank_cost = 0
            print(f"[situation] prerank skipped — pool too small ({len(candidate_pool)} cases)")
        else:
            _t_pre = time.time()
            pruned, prerank_scores_objs, prerank_cost = prerank_candidates(
                refined, candidate_pool, top_n=10,
            )
            prerank_scores = [s.to_dict() for s in prerank_scores_objs]
            _stage("03b_prerank", _t_pre)
            # If prerank kept nothing (everything below threshold), fall back
            # to the raw prefilter result rather than sending Sonnet empty pool.
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
    # Model selection (env-var driven via SITUATION_MODEL / SITUATION_DEEP_MODEL)
    # with a hard LATENCY GUARD: under DeepSeek-primary, sonnet/opus map to
    # deepseek-reasoner (R1, 60-120s, 180s client timeout). Stacked on IK
    # retrieval (30-70s) that exceeds Railway's edge proxy timeout -> the user
    # sees a 502/504 ("server took too long"). So the DEFAULT (non-deep) first
    # attempt is clamped to the fast model (haiku -> V3); R1 is reserved for the
    # explicit deep-mode opt-in. See _effective_situation_model().
    force_model_choice = _effective_situation_model(req.deep_mode)
    if not req.deep_mode and force_model_choice != config.SITUATION_MODEL:
        print(
            f"[situation] latency-guard: SITUATION_MODEL='{config.SITUATION_MODEL}' "
            f"clamped -> '{force_model_choice}' for the non-deep first attempt "
            f"(R1 too slow under DeepSeek; use deep_mode for reasoning)"
        )

    # Extended thinking gives Sonnet/Opus a scratch space to actually execute
    # the four-dimension scoring rubric in the v2 prompt before writing JSON.
    # Haiku doesn't support it (skipped silently inside call_claude_cached).
    #
    # Pipeline deadline check: if retrieval + translation + refinement have
    # already consumed most of the budget, disable extended thinking to save
    # ~5-10s. The LLM still produces good output without thinking; it's the
    # difference between A+ and A, not A and F.
    _elapsed_so_far = time.time() - _t_total
    _remaining = _PIPELINE_DEADLINE_SECONDS - _elapsed_so_far
    _enable_thinking_this_call = config.ENABLE_THINKING
    # R1 has chain-of-thought built in; the thinking flag here only matters
    # for Anthropic Sonnet. Threshold raised to 100s (was 70s) since pipeline
    # budget grew to 240s; we have more room for quality.
    if _remaining < 100:
        _enable_thinking_this_call = False
        print(
            f"[situation] pipeline deadline: {_elapsed_so_far:.1f}s elapsed, "
            f"{_remaining:.1f}s remaining — disabling extended thinking"
        )

    # Progressive reveal (streaming endpoint only): emit the real, verified
    # cases now — retrieval is done, the LLM hasn't run yet — so the UI can
    # show card shells immediately and stream the analysis in. No-op on the
    # classic JSON path (on_retrieved is None).
    if on_retrieved is not None:
        try:
            on_retrieved(_build_situation_shells(retrieval_cases))
        except Exception as _shell_exc:  # never let shell-prep break the pipeline
            print(f"[situation-stream] shell build failed: {_shell_exc}")

    payload = {
        "system_prompt": sys_prompt,
        "user_prompt": user_prompt,
        "cache": True,
        "enable_thinking": _enable_thinking_this_call,
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

    # SAFETY NET: if the LLM returned 0 cases but retrieval surfaced ≥3,
    # the LLM was being too conservative (V3 is prone to this). Force the
    # top 3 retrieval results through with minimal LLM-generated content.
    # The lawyer can decide if they're useful — better than empty page.
    _llm_cases_count = len(parsed.get("cases", []))
    if _llm_cases_count == 0 and len(retrieval_cases) >= 3:
        print(
            f"[situation-safety] LLM returned 0 cases but retrieval surfaced "
            f"{len(retrieval_cases)} — injecting top 3 as fallback"
        )
        fallback_cases = []
        for cs in retrieval_cases[:3]:
            fallback_cases.append({
                "case_id": cs.case_id,
                "title": cs.title,
                "court": cs.court,
                "year": cs.year,
                "citation": cs.citation,
                "stinger_sentence": (
                    f"This case was surfaced from the corpus by relevance "
                    f"to your matter. Review the judgment to assess fit."
                ),
                "held_line": "",
                "negative_carve_out": "",
                "court_quote": "",
                "relevance_explanation": "",
                "match_dimensions": [],
                "relevance_scores": {
                    "fact_archetype_match": 1,
                    "doctrinal_match": 1,
                    "outcome_alignment": 1,
                    "authority_weight": 1,
                    "total": 4,
                },
                "fallback_safety_net": True,
            })
        parsed["cases"] = fallback_cases
        parsed.setdefault("confidence", "low")
        parsed.setdefault("internal_reasoning", {})
        parsed["internal_reasoning"]["safety_net_triggered"] = (
            "LLM returned 0 cases; retrieval pool had ≥3 candidates. "
            "Top 3 injected as fallback."
        )

    # Existence filter — a case_id is "known" if it appeared in ANY of:
    #   (a) curated corpus (42 hand-vetted cases)
    #   (b) evidence paragraphs (IK-fetched text we showed the LLM)
    #   (c) retrieval_cases (cases the reranker selected and we fed to the LLM)
    #
    # BUG FIX: previously only (a) + (b) were included. When IK paragraph
    # fetch was slow/partial, evidence could be empty while retrieval_cases
    # had 5 valid cases. The LLM cited those cases (correctly — they were in
    # the corpus we gave it) but the existence filter dropped ALL of them
    # as "unknown", producing "no cases survived verification."
    if client is not None:
        known_ids = (
            {c["id"] for c in curated}
            | {e.case_id for e in evidence}
            | {cs.case_id for cs in retrieval_cases}
        )
    else:
        known_ids = {c["id"] for c in curated}

    # Defensive parsing for the v2 schema (rubric + internal_reasoning).
    # The model is instructed to populate these fields, but production code
    # should never assume the model followed instructions.
    parsed.setdefault("internal_reasoning", {})
    parsed.setdefault("confidence", "medium")
    for c in parsed.get("cases", []):
        # Robust defaults: if DeepSeek returns relevance_scores={} or omits
        # individual keys, fill them with 1 (neutral) rather than 0 — the LLM
        # chose to include the case, so assume baseline relevance. Only a
        # completely absent relevance_scores dict gets the full default.
        rs = c.get("relevance_scores")
        if not rs or not isinstance(rs, dict):
            c["relevance_scores"] = {
                "fact_archetype_match": 1,
                "doctrinal_match": 1,
                "outcome_alignment": 1,
                "authority_weight": 1,
                "total": 4,
            }
        else:
            # Fill individual missing keys with neutral 1 (not 0)
            rs.setdefault("fact_archetype_match", 1)
            rs.setdefault("doctrinal_match", 1)
            rs.setdefault("outcome_alignment", 1)
            rs.setdefault("authority_weight", 1)
            rs.setdefault("total", sum(
                rs.get(k, 1) for k in
                ("fact_archetype_match", "doctrinal_match", "outcome_alignment", "authority_weight")
            ))

    _llm_returned_count = len(parsed.get("cases", []))
    verified, dropped = [], []
    for c in parsed.get("cases", []):
        if c.get("case_id") in known_ids:
            verified.append(c)
        else:
            dropped.append(c.get("title", "?"))
    print(
        f"[situation-filter] LLM returned {_llm_returned_count} cases, "
        f"{len(verified)} exist in corpus, {len(dropped)} dropped (unknown id): {dropped}"
    )

    # Defensive filter: the v2 prompt instructs the model to drop any case
    # scoring 0 on fact-archetype match. Enforce here BUT with a minimum-
    # cases guard — never drop below 3 cases. DeepSeek may not populate
    # relevance_scores as precisely as Claude; dropping too aggressively
    # on default values leaves the lawyer with only 1-2 results.
    _MIN_CASES_GUARD = 3
    filtered_zero_archetype = 0
    final = []
    zero_archetype_cases = []
    for c in verified:
        score = c.get("relevance_scores", {}).get("fact_archetype_match", 1)
        if score > 0:
            final.append(c)
        else:
            zero_archetype_cases.append(c)
            filtered_zero_archetype += 1
    # If dropping would leave fewer than 3 cases, keep the zero-archetype
    # cases too — better to show a lower-relevance case than an empty page.
    if len(final) < _MIN_CASES_GUARD and zero_archetype_cases:
        needed = _MIN_CASES_GUARD - len(final)
        final.extend(zero_archetype_cases[:needed])
        filtered_zero_archetype -= min(needed, len(zero_archetype_cases))
    if filtered_zero_archetype > 0:
        print(
            f"[situation-filter] archetype filter: {len(final)} kept, "
            f"{filtered_zero_archetype} dropped (score=0)"
        )
    parsed["cases"] = final
    parsed["filtered_zero_archetype"] = filtered_zero_archetype

    # Verification (in-process, no LLM call): the three-check verifier
    # cross-references each cited paragraph_anchor and quotable_phrase
    # against the source evidence.
    #
    # POLICY (post-SC-2026 ruling):
    #   - EXISTENCE failures (fabricated case_id not in corpus) → HARD DROP.
    #     Citing a non-existent case is professional misconduct.
    #   - ANCHOR / VERBATIM failures (wrong para numbers, paraphrased quotes)
    #     → FLAG but keep. These are quality issues, not fabrications. The
    #     case itself is real and in the corpus; the LLM just got a detail
    #     wrong. Dropping 4 of 5 real cases because of quote imprecision
    #     leaves the lawyer with 1 result — worse than showing 5 with a
    #     small accuracy note.
    #   - Minimum-cases guard: never drop below 3 cases even for existence
    #     failures (unless fewer than 3 passed the archetype filter above).
    regen_attempted = False
    regen_helped = False
    if evidence:
        _t = time.time()
        report = verify_situation_response(parsed, evidence)
        _stage("05_verify", _t)
        if not report.is_clean():
            # Only hard-drop cases that are FABRICATED (not in evidence set).
            # Anchor/quote failures get flagged in the verification report
            # but the case stays in the result.
            fabricated_ids = {
                f.case_id for f in report.findings
                if not f.exists  # case_id not in evidence = fabrication
            }
            _anchor_fails = sum(1 for f in report.findings if f.exists and not f.anchor_valid)
            _quote_fails = sum(1 for f in report.findings if f.exists and any(not q.matched for q in f.verbatim_checks))
            print(
                f"[situation-verify] {len(fabricated_ids)} fabricated (dropped), "
                f"{_anchor_fails} anchor fails (flagged), {_quote_fails} quote fails (flagged), "
                f"total cases before verify: {len(parsed.get('cases', []))}"
            )
            if fabricated_ids:
                kept = [
                    c for c in parsed.get("cases", [])
                    if c.get("case_id") not in fabricated_ids
                ]
                if not kept:
                    # ALL cases fabricated — keep originals (better than empty)
                    print("[situation-verify] all cases fabricated — keeping originals")
                elif len(kept) >= _MIN_CASES_GUARD:
                    parsed["cases"] = kept
                else:
                    # Not enough non-fabricated cases. The "fabricated" ones
                    # likely have reformatted case_ids (DeepSeek adds party
                    # names or reformats). Keep the non-fabricated ones, then
                    # re-add fabricated cases to reach the minimum — they're
                    # still from the corpus, just with mangled IDs.
                    fabricated_cases = [
                        c for c in parsed.get("cases", [])
                        if c.get("case_id") in fabricated_ids
                    ]
                    needed = _MIN_CASES_GUARD - len(kept)
                    kept.extend(fabricated_cases[:needed])
                    parsed["cases"] = kept
                    print(
                        f"[situation-verify] restored {min(needed, len(fabricated_cases))} "
                        f"fabricated cases to reach minimum {_MIN_CASES_GUARD}"
                    )
            # Flag anchor/quote issues on individual cases for transparency
            _flag_map = {}
            for f in report.findings:
                issues = []
                if not f.anchor_valid and f.exists:
                    issues.append("anchor_unverified")
                for qc in f.verbatim_checks:
                    if not qc.matched:
                        issues.append("quote_unverified")
                        break
                if issues:
                    _flag_map[f.case_id] = issues
            for c in parsed.get("cases", []):
                flags = _flag_map.get(c.get("case_id"), [])
                if flags:
                    c["verification_flags"] = flags
        verification_report = report.summary()

    # Final guard: log clearly if ALL cases were filtered out. This should
    # never happen with the minimum-cases guards above, but defensively
    # catch it so we can diagnose via Railway logs.
    _final_count = len(parsed.get("cases", []))
    if _final_count == 0:
        print(
            f"[situation-WARN] 0 cases survived all filters! "
            f"LLM returned {_llm_returned_count}, "
            f"existence={len(verified)}, archetype={len(final)}, "
            f"dropped_ids={dropped}"
        )
    else:
        print(f"[situation-filter] final: {_final_count} cases returned to frontend")

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
    # Build a quick lookup from retrieval-time metadata (numcitedby, source,
    # AND the verified outcome / clean title / court label from the HF
    # retrieval path so we can override LLM hallucinations).
    meta_by_id: dict = {}
    for cs in retrieval_cases:
        meta_by_id[cs.case_id] = {
            "kanoon_doc_id": _kanoon_doc_id_from_case_id(cs.case_id),
            "numcitedby":    cs.numcitedby,
            "source":        cs.source,
            "clean_title":   cs.title,                              # NEW
            "court":         cs.court,                              # NEW
            "outcome":       getattr(cs, "outcome", "") or "",      # NEW
            "district":      getattr(cs, "district", "") or "",     # NEW
            # Official SC open-data copy (cross-resolved in retrieval) — NEW
            "official_doc_id":  getattr(cs, "official_doc_id", "") or "",
            "official_pdf_url": getattr(cs, "official_pdf_url", "") or "",
            "official_citation": (getattr(cs, "neutral_citation", "")
                                  or getattr(cs, "scr_citation", "") or ""),
            "is_official_copy": bool(getattr(cs, "is_official_copy", False)),
            # Full reporter list for the "Reported in" row + the free court-issued
            # neutral citation (greyed apart from the paid reporters in the UI).
            "citations_all":    list(getattr(cs, "citations_all", []) or []),
            "neutral_citation": getattr(cs, "neutral_citation", "") or "",
        }
    for c in curated:
        if c.get("id"):
            meta_by_id.setdefault(c["id"], {})
            if c.get("kanoon_doc_id"):
                meta_by_id[c["id"]]["kanoon_doc_id"] = str(c["kanoon_doc_id"])
    # Pass refined.dual_statute_map so _auto_bns_note can use it for the
    # per-case BNS mapping note (replaces 'pending editorial review').
    refined_dual_map = (refined.dual_statute_map if hasattr(refined, "dual_statute_map") else []) or []
    for case in parsed.get("cases", []):
        _enrich_case(case, meta_by_id, refined_dual_map=refined_dual_map)

    # Supreme Court precedent always shows first, then High Court, then the
    # rest. Stable sort preserves the model's within-tier relevance ordering.
    if isinstance(parsed.get("cases"), list):
        def _court_tier_for_sort(c: dict) -> int:
            crt = (c.get("court") or "").lower()
            if "supreme court" in crt:
                return 0
            if "high court" in crt:
                return 1
            return 2
        parsed["cases"].sort(key=_court_tier_for_sort)

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
    meta["pipeline_deadline_seconds"] = _PIPELINE_DEADLINE_SECONDS
    meta["thinking_disabled_by_deadline"] = not _enable_thinking_this_call and config.ENABLE_THINKING
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
    with check_and_record(user.id, "deep_search", endpoint="digest", email=user.email) as _record:
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
    with check_and_record(user.id, "deep_search", endpoint="headnote", email=user.email) as _record:
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
    require_feature(user.id, "hindi_export", email=user.email)
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

    # Use the LLM translation path whenever ANY provider is available.
    # BUG FIX: the old gate was `if config.ANTHROPIC_API_KEY:` — but
    # production runs DeepSeek-primary with NO Anthropic key, so it always
    # fell through to Google Translate (which is unreliable / often fails,
    # breaking the Hindi toggle on the research page). translate_payload_haiku
    # routes through route_call("translation") → DeepSeek V3 when Anthropic
    # is absent, so it works fine in DeepSeek-primary mode.
    from headnote.llm.client import _deepseek_primary
    _llm_available = bool(config.ANTHROPIC_API_KEY) or _deepseek_primary()

    if _llm_available:
        try:
            translated, paise, quality, preserved = translate_payload_haiku(req.payload)
            elapsed = time.time() - t0
            record_query(
                task_type="translate",
                primary_model="deepseek/haiku",
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
                    "model": "deepseek/haiku",
                    "cost_paise": paise,
                    "cost_inr": round(paise / 100, 4),
                    "cost_usd": round(paise / 100 / config.USD_TO_INR, 6),
                    "quality": quality,
                    "preserved_citations": preserved,
                    "translator": "llm",
                },
            }
        except Exception as e:
            print(f"[translate] LLM path failed ({str(e)[:200]}) — falling back to Google")
            # fall through to Google Translate below

    # Last resort: free Google Translate (only when no LLM, or LLM failed).
    try:
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
    # Translate raw LLM-provider errors into actionable user messages so
    # lawyers don't see "429 RESOURCE_EXHAUSTED" or "credit balance is too low".
    msg = str(exc)
    lower = msg.lower()
    exc_type = type(exc).__name__

    # DEBUG: log the raw exception type + message + traceback to Railway logs
    # so an operator can diagnose Bedrock fallback chains, IAM denials, etc.
    import traceback as _tb
    print(f"[exc_handler] {exc_type}: {msg[:500]}", flush=True)
    _tb.print_exc()

    # Identify which provider actually raised — needed because the error
    # message used to always say "Anthropic" even when the active path was
    # DeepSeek or Groq, which is misleading for ops.
    def _which_provider(s: str) -> str:
        sl = s.lower()
        if "deepseek" in sl or "api.deepseek.com" in sl:
            return "DeepSeek"
        if "groq" in sl or "api.groq.com" in sl:
            return "Groq"
        if "anthropic" in sl or "api.anthropic.com" in sl:
            return "Anthropic"
        return "AI provider"

    provider = _which_provider(msg)

    # Rate limit / 429 — common when free-tier or fresh keys haven't warmed
    # up yet. DeepSeek is the most common offender on a new account.
    if "rate_limit" in lower or "ratelimit" in lower or "429" in msg or "rate limit" in lower:
        return JSONResponse(status_code=503, content={
            "error": f"{provider} is rate-limiting our requests. Retry in 10-15 seconds. If this persists, your {provider} key may be on a low free tier — top up or switch providers via LLM_PROVIDER env var.",
            "provider": provider,
        })

    # Invalid/missing API key
    if "api key" in lower or "unauthorized" in lower or "401" in msg or "invalid_api_key" in lower:
        return JSONResponse(status_code=503, content={
            "error": f"{provider} API key is invalid or missing on the server. Check Railway env vars (ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, GROQ_API_KEY).",
            "provider": provider,
        })

    # Out-of-credit / billing
    if "credit balance" in lower or "insufficient credit" in lower or "out of credits" in lower or "payment required" in lower or "402" in msg:
        return JSONResponse(status_code=503, content={
            "error": f"{provider} account is out of credit. Top up at the provider dashboard, or set LLM_PROVIDER=deepseek to route via DeepSeek instead (cheaper).",
            "provider": provider,
            "exception_type": exc_type,
        })

    # Connection / timeout
    if "timeout" in lower or "connection" in lower or "timed out" in lower or "connecterror" in lower:
        return JSONResponse(status_code=503, content={
            "error": f"{provider} connection timeout. Retry in a few seconds. If persistent, the provider may be having an outage.",
            "provider": provider,
        })

    # Model not found
    if "model identifier" in lower or "model not found" in lower or "model_not_found" in lower:
        return JSONResponse(status_code=500, content={
            "error": f"{provider} model ID is unrecognised — likely a stale model name in env vars. Check DEEPSEEK_MODEL_OVERRIDE / MODEL on Railway.",
            "provider": provider,
        })

    # Fallback — show the raw message with provider attribution so ops can
    # diagnose without grepping Railway logs.
    return JSONResponse(status_code=500, content={
        "error": f"{provider} error: {msg[:500]}",
        "provider": provider,
        "exception_type": exc_type,
    })


# Mount static last so /api/* takes priority.
# Wrap with a middleware-ish subclass to attach `Cache-Control: no-cache`
# on every static response. Why: during the active dev phase we ship new
# auth.js / drafter JS multiple times a day; without this, browsers hang
# onto the old version and users see broken behavior (sign-in loops,
# missing buttons) until they hard-refresh. Once the codebase stabilises
# this can be relaxed to `max-age=300, must-revalidate`.
class _NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        try:
            resp.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
        except Exception:
            pass
        return resp


app.mount("/static", _NoCacheStaticFiles(directory=config.STATIC_DIR), name="static")
