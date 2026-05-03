"""
Criminal Law AI — v0.3 (FastAPI + custom UI)
============================================

A polished, fully responsive web app for AI-powered Indian criminal-law
research. Replaces the v0.2 Streamlit UI with a custom light-themed frontend.

Architecture
------------
  - FastAPI backend with four endpoints:
      POST /api/situation  — situation → relevant cases
      POST /api/digest     — topic → research digest
      POST /api/headnote   — judgment text → Cri.L.J.-format headnote(s)
      POST /api/translate  — translate any English JSON result to Hindi
  - Static HTML/CSS/JS frontend served from /static
  - SQLite for feedback storage
  - Anthropic prompt caching enabled for the corpus

Run locally
-----------
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...   # or put in .env
    uvicorn main:app --reload

Deploy
------
    Render.com free tier, Railway, Fly.io — see README.
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
    build_situation_system_prompt,
    SITUATION_USER_TEMPLATE,
    HEADNOTE_SYSTEM_PROMPT,
    HEADNOTE_USER_TEMPLATE,
    build_digest_system_prompt,
    DIGEST_USER_TEMPLATE,
)
from translate import translate_payload

# -------------------------------------------------------------------- config

APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"
CASES_PATH = APP_DIR / "cases.json"
# Allow override via env (Render free disk is ephemeral; use /tmp or external DB)
FEEDBACK_DB = Path(os.environ.get("FEEDBACK_DB", str(APP_DIR / "feedback.db")))

DEFAULT_MODEL = os.environ.get("MODEL", "claude-opus-4-6")
# Hindi translation uses FREE Google Translate (deep-translator) — no API
# call, no cost. See translate.py.
MAX_TOKENS = 4096

# Approximate Opus 4.6 prices (USD per million tokens). Adjust if Anthropic
# pricing changes; only used for the in-app cost meter.
PRICE_OPUS = {
    "input": 15.00,
    "input_cache_write": 18.75,
    "input_cache_read": 1.50,
    "output": 75.00,
}
PRICE_HAIKU = {
    "input": 0.80,
    "input_cache_write": 1.00,
    "input_cache_read": 0.08,
    "output": 4.00,
}
PRICE_SONNET = {
    "input": 3.00,
    "input_cache_write": 3.75,
    "input_cache_read": 0.30,
    "output": 15.00,
}
USD_TO_INR = 84.0

# -------------------------------------------------------------------- helpers

def load_corpus() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def corpus_json_str() -> str:
    """Stable serialisation of corpus for prompt caching."""
    if not hasattr(corpus_json_str, "_cache"):
        corpus_json_str._cache = json.dumps(load_corpus(), ensure_ascii=False)
    return corpus_json_str._cache


def get_client() -> Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY is not configured on the server.",
        )
    return Anthropic(api_key=key)


def init_feedback_db() -> None:
    """Best-effort feedback DB init. Skips silently on read-only filesystems."""
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


def call_claude_cached(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = MAX_TOKENS,
    cache: bool = True,
) -> tuple[str, dict]:
    client = get_client()
    if cache:
        system = [
            {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
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
        pricing = PRICE_OPUS  # default — also covers claude-opus-4-6 / 4-7
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
            text = text[: -3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Model returned invalid JSON: {e}. Raw start: {text[:200]}",
        )


def build_meta(usage: dict, elapsed: float) -> dict:
    cost_usd = estimate_cost_usd(usage)
    return {
        "elapsed_seconds": round(elapsed, 2),
        "model": usage.get("model"),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
        "cost_usd": round(cost_usd, 6),
        "cost_inr": round(cost_usd * USD_TO_INR, 4),
    }


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
    rating: int  # 1 or -1
    correction: str | None = None
    lawyer_handle: str | None = None


# -------------------------------------------------------------------- app

app = FastAPI(title="Criminal Law AI", version="0.3.0")
init_feedback_db()


@app.get("/")
def landing():
    """Marketing landing page."""
    return FileResponse(STATIC_DIR / "landing.html")


@app.get("/app")
@app.get("/app/")
def app_index():
    """The actual research tool."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.3.0", "model": DEFAULT_MODEL}


@app.get("/api/corpus")
def api_corpus():
    """Return slim corpus listing for the browse-corpus drawer."""
    cases = load_corpus()
    return {
        "count": len(cases),
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


@app.post("/api/situation")
def api_situation(req: SituationRequest):
    sys_prompt = build_situation_system_prompt(req.style, corpus_json_str())
    user_prompt = SITUATION_USER_TEMPLATE.format(situation=req.situation, style=req.style)
    t0 = time.time()
    raw, usage = call_claude_cached(sys_prompt, user_prompt)
    elapsed = time.time() - t0

    parsed = parse_json_response(raw)
    # Verify case_ids against corpus
    corpus_ids = {c["id"] for c in load_corpus()}
    verified = []
    dropped = []
    for c in parsed.get("cases", []):
        if c.get("case_id") in corpus_ids:
            verified.append(c)
        else:
            dropped.append(c.get("title", "?"))
    parsed["cases"] = verified

    return {
        "result": parsed,
        "raw": raw,
        "dropped_hallucinations": dropped,
        "meta": build_meta(usage, elapsed),
    }


@app.post("/api/digest")
def api_digest(req: DigestRequest):
    sys_prompt = build_digest_system_prompt(corpus_json_str())
    user_prompt = DIGEST_USER_TEMPLATE.format(topic=req.topic)
    t0 = time.time()
    raw, usage = call_claude_cached(sys_prompt, user_prompt)
    elapsed = time.time() - t0

    parsed = parse_json_response(raw)
    return {
        "result": parsed,
        "raw": raw,
        "meta": build_meta(usage, elapsed),
    }


@app.post("/api/headnote")
def api_headnote(req: HeadnoteRequest):
    user_prompt = HEADNOTE_USER_TEMPLATE.format(judgment_text=req.judgment_text[:30000])
    t0 = time.time()
    # Headnote system prompt is small and not corpus-dependent, so caching is
    # less impactful — but we still send as cacheable for consistency.
    raw, usage = call_claude_cached(HEADNOTE_SYSTEM_PROMPT, user_prompt, cache=False)
    elapsed = time.time() - t0

    parsed = parse_json_response(raw)
    return {
        "result": parsed,
        "raw": raw,
        "meta": build_meta(usage, elapsed),
    }


@app.post("/api/translate")
def api_translate(req: TranslateRequest):
    """Translate an English JSON result to Hindi using FREE Google Translate
    (no Anthropic API call, no API key, no LLM cost). Citations, statute names,
    paragraph anchors, and case titles are protected via placeholder
    substitution so they survive translation untouched.
    """
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


# Mount static files LAST so /api/* takes priority
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
