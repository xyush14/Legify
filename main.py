"""
Criminal Law AI — v0.4 (FastAPI + custom UI + LIVE Indian Kanoon)
=================================================================

Changes from v0.3:
  - /api/situation and /api/digest now fetch judgments LIVE from Indian Kanoon
    instead of using the curated 42-case cases.json. Coverage is now the
    full Indian criminal jurisprudence (~26M judgments).
  - cases.json is preserved as a fallback / test corpus (no longer the
    production source). /api/corpus returns the 42 as "test cases" for now.
  - /api/headnote and /api/translate are unchanged.
  - Default model for situation/digest is now Claude Sonnet 4.6 (5x cheaper
    than Opus; senior advocate review + three-check verification on output
    catches any quality gap). Headnote stays on Opus.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

# Auto-load .env if present (for local dev). Silent if not installed.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from anthropic import Anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from prompts import (
    # legacy (kept for fallback / future use)
    build_situation_system_prompt,
    build_digest_system_prompt,
    # live-IK (new)
    build_situation_system_prompt_live,
    build_digest_system_prompt_live,
    SITUATION_USER_TEMPLATE,
    HEADNOTE_SYSTEM_PROMPT,
    HEADNOTE_USER_TEMPLATE,
    DIGEST_USER_TEMPLATE,
)
from translate import translate_payload
from indiankanoon import (
    gather_relevant_judgments,
    IKError, IKAuthError, IKRateLimit,
)


# -------------------------------------------------------------------- config

APP_DIR    = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"
CASES_PATH = APP_DIR / "cases.json"   # legacy / test corpus

FEEDBACK_DB = Path(os.environ.get("FEEDBACK_DB", str(APP_DIR / "feedback.db")))

# Sonnet 4.6 for situation/digest (live IK = much larger context per call;
# Sonnet keeps cost in line with the v0.3 Opus + cached-corpus economics).
# Opus stays on /api/headnote where editorial quality matters most.
SITUATION_MODEL = os.environ.get("SITUATION_MODEL", "claude-sonnet-4-6")
DIGEST_MODEL    = os.environ.get("DIGEST_MODEL",    "claude-sonnet-4-6")
HEADNOTE_MODEL  = os.environ.get("HEADNOTE_MODEL",  "claude-opus-4-6")

MAX_TOKENS = 4000

# How many IK judgments to retrieve per request and how much of each to feed
# the LLM. These cap cost per query.
IK_MAX_JUDGMENTS  = 3
IK_MAX_CHARS_DOC  = 40_000
IK_FROM_DATE      = "2010-01-01"
IK_DEFAULT_COURT  = "Supreme Court"

PRICE_OPUS = {
    "input": 15.00, "input_cache_write": 18.75,
    "input_cache_read": 1.50, "output": 75.00,
}
PRICE_HAIKU = {
    "input": 0.80, "input_cache_write": 1.00,
    "input_cache_read": 0.08, "output": 4.00,
}
PRICE_SONNET = {
    "input": 3.00, "input_cache_write": 3.75,
    "input_cache_read": 0.30, "output": 15.00,
}
USD_TO_INR = 84.0


# -------------------------------------------------------------------- helpers

def load_corpus() -> list[dict]:
    """Load legacy/test corpus (42 cases). No longer the production source."""
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def get_client() -> Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY is not configured on the server.",
        )
    return Anthropic(api_key=key)


def init_feedback_db() -> None:
    try:
        conn = sqlite3.connect(FEEDBACK_DB)
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


def call_claude(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str,
    max_tokens: int = MAX_TOKENS,
    cache: bool = True,
) -> tuple[str, dict]:
    """Single LLM call. Optionally caches the system prompt block."""
    client = get_client()
    if cache:
        system = [
            {"type": "text", "text": system_prompt,
             "cache_control": {"type": "ephemeral"}}
        ]
    else:
        system = system_prompt

    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    usage = resp.usage
    usage_dict = {
        "model": model,
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
    }
    return resp.content[0].text, usage_dict


def estimate_cost_usd(usage: dict) -> float:
    model = usage.get("model", "")
    if "haiku" in model:
        pricing = PRICE_HAIKU
    elif "sonnet" in model:
        pricing = PRICE_SONNET
    else:
        pricing = PRICE_OPUS
    return (
        usage.get("input_tokens", 0) * pricing["input"] / 1_000_000
        + usage.get("cache_creation_input_tokens", 0) * pricing["input_cache_write"] / 1_000_000
        + usage.get("cache_read_input_tokens", 0) * pricing["input_cache_read"] / 1_000_000
        + usage.get("output_tokens", 0) * pricing["output"] / 1_000_000
    )


def parse_json_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Model returned invalid JSON: {e}. Raw start: {text[:200]}",
        )


def build_meta(usage: dict, elapsed: float, extra: dict | None = None) -> dict:
    cost_usd = estimate_cost_usd(usage)
    meta = {
        "elapsed_seconds": round(elapsed, 2),
        "model": usage.get("model"),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
        "cost_usd": round(cost_usd, 6),
        "cost_inr": round(cost_usd * USD_TO_INR, 4),
    }
    if extra:
        meta.update(extra)
    return meta


# -------------------------------------------------------------------- models

class SituationRequest(BaseModel):
    situation: str = Field(..., min_length=10, max_length=8000)
    style: Literal["journal", "practitioner"] = "journal"


class DigestRequest(BaseModel):
    topic: str = Field(..., min_length=5, max_length=2000)


class HeadnoteRequest(BaseModel):
    judgment_text: str = Field(..., min_length=200, max_length=80000)


class TranslateRequest(BaseModel):
    payload: dict
    target_language: Literal["hi"] = "hi"


class FeedbackRequest(BaseModel):
    mode: str
    input_text: str
    output_json: str
    rating: int
    correction: str | None = None
    lawyer_handle: str | None = None


# -------------------------------------------------------------------- app

app = FastAPI(title="Criminal Law AI", version="0.4.0")
init_feedback_db()


@app.get("/")
def landing():
    return FileResponse(STATIC_DIR / "landing.html")


@app.get("/app")
@app.get("/app/")
def app_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "version": "0.4.0",
        "mode": "live-ik",
        "situation_model": SITUATION_MODEL,
        "digest_model": DIGEST_MODEL,
        "headnote_model": HEADNOTE_MODEL,
    }


@app.get("/api/corpus")
def api_corpus():
    """Return slim listing of the legacy 42 cases. Now labelled as test corpus."""
    try:
        cases = load_corpus()
    except FileNotFoundError:
        return {"count": 0, "cases": [], "note": "test corpus not present"}
    return {
        "count": len(cases),
        "note": "These 42 cases are kept as a test/reference set. Production queries now retrieve live from Indian Kanoon.",
        "cases": [
            {
                "id": c["id"],
                "title": c["title"],
                "court": c["court"],
                "year": c["year"],
                "topics": c.get("topics", [])[:6],
            }
            for c in cases
        ],
    }


# ────────────────────────────────────────────────────────────────────
# /api/situation — LIVE Indian Kanoon
# ────────────────────────────────────────────────────────────────────

@app.post("/api/situation")
def api_situation(req: SituationRequest):
    t0 = time.time()
    client = get_client()

    # Step 1: fetch live from Indian Kanoon (expand query → search → fetch).
    try:
        judgments = gather_relevant_judgments(
            req.situation,
            client,
            max_total=IK_MAX_JUDGMENTS,
            max_chars_per_doc=IK_MAX_CHARS_DOC,
            from_date=IK_FROM_DATE,
            court=IK_DEFAULT_COURT,
        )
    except IKAuthError as e:
        raise HTTPException(status_code=500, detail=f"IK auth error: {e}")
    except IKRateLimit as e:
        raise HTTPException(status_code=503, detail=f"IK rate-limited: {e}")
    except IKError as e:
        raise HTTPException(status_code=502, detail=f"IK error: {e}")

    if not judgments:
        elapsed = time.time() - t0
        return {
            "result": {
                "confidence": "low",
                "no_match_reason": "No relevant judgments retrieved from Indian Kanoon for this situation. Try refining the query with statute references or factual specifics.",
                "style": req.style,
                "cases": [],
            },
            "raw": "",
            "dropped_hallucinations": [],
            "meta": build_meta({"model": SITUATION_MODEL}, elapsed,
                               {"ik_judgments_fetched": 0}),
        }

    # Step 2: build prompt with fetched judgments as the corpus.
    judgments_json = json.dumps(judgments, ensure_ascii=False)
    sys_prompt = build_situation_system_prompt_live(req.style, judgments_json)
    user_prompt = SITUATION_USER_TEMPLATE.format(
        situation=req.situation, style=req.style
    )

    # Step 3: call the LLM.
    raw, usage = call_claude(
        sys_prompt, user_prompt, model=SITUATION_MODEL, cache=False,
    )
    elapsed = time.time() - t0

    # Step 4: parse + verify case_ids against this request's fetched set.
    parsed = parse_json_response(raw)
    fetched_ids = {j["case_id"] for j in judgments}
    verified, dropped = [], []
    for c in parsed.get("cases", []):
        if c.get("case_id") in fetched_ids:
            verified.append(c)
        else:
            dropped.append(c.get("title", "?"))
    parsed["cases"] = verified

    return {
        "result": parsed,
        "raw": raw,
        "dropped_hallucinations": dropped,
        "meta": build_meta(usage, elapsed, {
            "ik_judgments_fetched": len(judgments),
            "ik_doc_ids": [j["case_id"] for j in judgments],
        }),
    }


# ────────────────────────────────────────────────────────────────────
# /api/digest — LIVE Indian Kanoon
# ────────────────────────────────────────────────────────────────────

@app.post("/api/digest")
def api_digest(req: DigestRequest):
    t0 = time.time()
    client = get_client()

    try:
        judgments = gather_relevant_judgments(
            req.topic,
            client,
            max_total=IK_MAX_JUDGMENTS,
            max_chars_per_doc=IK_MAX_CHARS_DOC,
            from_date=IK_FROM_DATE,
            court=IK_DEFAULT_COURT,
        )
    except IKAuthError as e:
        raise HTTPException(status_code=500, detail=f"IK auth error: {e}")
    except IKRateLimit as e:
        raise HTTPException(status_code=503, detail=f"IK rate-limited: {e}")
    except IKError as e:
        raise HTTPException(status_code=502, detail=f"IK error: {e}")

    if not judgments:
        elapsed = time.time() - t0
        return {
            "result": {
                "topic": req.topic,
                "confidence": "low",
                "sub_topics": [],
                "summary_takeaway": "No relevant judgments retrieved from Indian Kanoon for this topic.",
            },
            "raw": "",
            "meta": build_meta({"model": DIGEST_MODEL}, elapsed,
                               {"ik_judgments_fetched": 0}),
        }

    judgments_json = json.dumps(judgments, ensure_ascii=False)
    sys_prompt = build_digest_system_prompt_live(judgments_json)
    user_prompt = DIGEST_USER_TEMPLATE.format(topic=req.topic)

    raw, usage = call_claude(
        sys_prompt, user_prompt, model=DIGEST_MODEL, cache=False,
    )
    elapsed = time.time() - t0

    parsed = parse_json_response(raw)
    return {
        "result": parsed,
        "raw": raw,
        "meta": build_meta(usage, elapsed, {
            "ik_judgments_fetched": len(judgments),
            "ik_doc_ids": [j["case_id"] for j in judgments],
        }),
    }


# ────────────────────────────────────────────────────────────────────
# /api/headnote — UNCHANGED (corpus-independent; takes pasted text)
# ────────────────────────────────────────────────────────────────────

@app.post("/api/headnote")
def api_headnote(req: HeadnoteRequest):
    user_prompt = HEADNOTE_USER_TEMPLATE.format(
        judgment_text=req.judgment_text[:30000]
    )
    t0 = time.time()
    raw, usage = call_claude(
        HEADNOTE_SYSTEM_PROMPT, user_prompt,
        model=HEADNOTE_MODEL, cache=False,
    )
    elapsed = time.time() - t0
    parsed = parse_json_response(raw)
    return {
        "result": parsed,
        "raw": raw,
        "meta": build_meta(usage, elapsed),
    }


# ────────────────────────────────────────────────────────────────────
# /api/translate — UNCHANGED
# ────────────────────────────────────────────────────────────────────

@app.post("/api/translate")
def api_translate(req: TranslateRequest):
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
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cost_usd": 0.0,
            "cost_inr": 0.0,
            "free": True,
        },
    }


# ────────────────────────────────────────────────────────────────────
# /api/feedback — UNCHANGED
# ────────────────────────────────────────────────────────────────────

@app.post("/api/feedback")
def api_feedback(req: FeedbackRequest):
    conn = sqlite3.connect(FEEDBACK_DB)
    conn.execute(
        "INSERT INTO feedback (ts, mode, input_text, output_json, rating, correction, lawyer_handle) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.utcnow().isoformat(),
            req.mode,
            req.input_text,
            req.output_json,
            req.rating,
            req.correction or "",
            req.lawyer_handle or "",
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


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
