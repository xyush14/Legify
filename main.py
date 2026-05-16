"""
Headnote — Self-contained main.py with LIVE Indian Kanoon
==========================================================
ONE file. Hardcoded IK token (eat the security cost for demo).
Heavy logging at every step so Render Logs shows what's happening.
Returns EXACTLY 3 cases for /api/situation.

Depends only on: anthropic, fastapi, pydantic, requests, dotenv.
Falls back gracefully if translate.py is missing.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Literal

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

# Try to import translate; if missing, /api/translate returns a graceful error.
try:
    from translate import translate_payload
    TRANSLATE_AVAILABLE = True
except Exception:
    TRANSLATE_AVAILABLE = False


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
IK_TOKEN = "67350ec889bb47d1a3fd96f8568a341bf9b0ab23"

SONNET_MODEL = "claude-sonnet-4-6"
OPUS_MODEL   = "claude-opus-4-7"

MAX_JUDGMENTS_FETCH = 3
MAX_CHARS_PER_DOC   = 30_000
IK_TIMEOUT_SEARCH   = 30
IK_TIMEOUT_FETCH    = 60

APP_DIR     = Path(__file__).parent
STATIC_DIR  = APP_DIR / "static"
FEEDBACK_DB = Path(os.environ.get("FEEDBACK_DB", str(APP_DIR / "feedback.db")))


# ─── Logging helper ────────────────────────────

def log(msg: str) -> None:
    """Print to stdout, flush immediately so Render Logs sees it live."""
    print(f"[hn] {msg}", flush=True)
    sys.stdout.flush()


# ─── HTML cleaner ──────────────────────────────

def clean_html(raw: str) -> str:
    if not raw:
        return ""
    t = re.sub(r"<[^>]+>", " ", raw)
    t = (t.replace("&amp;",  "&")
          .replace("&lt;",   "<")
          .replace("&gt;",   ">")
          .replace("&nbsp;", " ")
          .replace("&quot;", '"')
          .replace("&#39;",  "'")
          .replace("&#8377;", "₹"))
    return re.sub(r"\s+", " ", t).strip()


# ─── Indian Kanoon ─────────────────────────────

def ik_headers() -> dict:
    return {"Authorization": f"Token {IK_TOKEN}", "Accept": "application/json"}


def ik_search(query: str, max_results: int = 5) -> list:
    log(f"ik_search: '{query[:80]}'")
    try:
        r = requests.post(
            "https://api.indiankanoon.org/search/",
            headers=ik_headers(),
            data={"formInput": query, "pagenum": 0},
            timeout=IK_TIMEOUT_SEARCH,
        )
    except requests.RequestException as e:
        log(f"  search NETWORK ERROR: {e}")
        return []

    log(f"  search status: {r.status_code}, body len: {len(r.text)}")
    if r.status_code != 200:
        log(f"  search body preview: {r.text[:300]}")
        return []

    try:
        data = r.json()
    except Exception as e:
        log(f"  search JSON parse failed: {e}")
        return []

    docs = data.get("docs", [])
    log(f"  search returned {len(docs)} raw docs")
    return docs[:max_results]


def ik_fetch(doc_id: str) -> dict | None:
    log(f"ik_fetch: {doc_id}")
    try:
        r = requests.post(
            f"https://api.indiankanoon.org/doc/{doc_id}/",
            headers=ik_headers(),
            timeout=IK_TIMEOUT_FETCH,
        )
    except requests.RequestException as e:
        log(f"  fetch NETWORK ERROR: {e}")
        return None

    log(f"  fetch status: {r.status_code}")
    if r.status_code != 200:
        log(f"  fetch body preview: {r.text[:300]}")
        return None

    try:
        return r.json()
    except Exception as e:
        log(f"  fetch JSON parse failed: {e}")
        return None


# ─── Anthropic ─────────────────────────────────

def get_client() -> Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        log("ANTHROPIC_API_KEY not set!")
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured.")
    return Anthropic(api_key=key)


def call_claude(model: str, system: str, user: str, max_tokens: int = 4000) -> tuple[str, dict]:
    log(f"call_claude: model={model}, system_len={len(system)}, user_len={len(user)}")
    client = get_client()
    try:
        resp = client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
    except Exception as e:
        log(f"  ANTHROPIC ERROR: {type(e).__name__}: {e}")
        raise

    raw = resp.content[0].text
    u = resp.usage
    log(f"  response: {len(raw)} chars, in={u.input_tokens}, out={u.output_tokens}")
    return raw, {
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "model": model,
    }


def strip_json_fences(raw: str) -> str:
    t = raw.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


# ─── Prompts ───────────────────────────────────

EXPAND_PROMPT = """You convert an Indian criminal advocate's situation into 2-3 search queries for the Indian Kanoon search engine.

Output ONLY a JSON array of 2-3 strings. No prose. No markdown.

Each query: 4-8 words, focused on statute sections + key doctrinal terms.

Use Indian statute references like: "Section 482 CrPC", "Section 498A IPC", "BNS 2023", "BNSS 2023", "PMLA", "NDPS Act", "POCSO", "S. 138 NI Act".

Always include "Supreme Court" in at least one query.

Example input:
"My client is accused under 498A and the FIR seems malicious, we want to quash"

Example output:
["Section 482 CrPC quashing 498A Supreme Court", "malicious prosecution 498A IPC quashing", "Bhajan Lal categories quashing FIR Supreme Court"]"""


SITUATION_SYSTEM_PROMPT = """You are Headnote's senior research assistant, supervised by a senior criminal advocate (26 years at the Bar). You serve practising Indian criminal lawyers.

INPUT: A lawyer's specific situation + the full text of 1-3 Supreme Court criminal judgments fetched live from Indian Kanoon.

YOUR JOB: Produce EXACTLY top-3 case-law output (or fewer if only fewer judgments were fetched) in structured Cri.L.J. format, framed around THIS lawyer's situation.

For each judgment, score across these dimensions:
1. Statute overlap with lawyer's situation (which sections — same IPC/BNS/CrPC/BNSS/Evidence Act sections?)
2. Doctrinal overlap (same legal point — quashing, bail, conviction, evidence?)
3. Factual similarity (same fact pattern — matrimonial, commercial, custodial?)
4. Procedural posture (same stage — pre-trial, trial, appeal, bail?)
5. Argument angle (does the case help the lawyer's specific argument?)
6. Bench strength (Constitution Bench > 3-judge > 2-judge for same point)
7. Recency / current law (post-BNS, post-Arnesh Kumar, post-Satender Antil if relevant)

OUTPUT — pure JSON, no prose, no markdown fences:

{
  "confidence": "high" | "medium" | "low",
  "no_match_reason": "string (only if confidence=low)",
  "style": "journal" | "practitioner",
  "cases": [
    {
      "case_id": "ik_<doc_id from the fetched judgment>",
      "title": "Parties (e.g., 'State of Haryana v. Bhajan Lal')",
      "citation": "preferred reported citation if visible in judgment text, else IK URL",
      "court": "Supreme Court of India",
      "year": number,
      "relevance_explanation": "2-3 sentences on why this case is among the top for THIS specific situation",
      "bns_note": "1 sentence mapping IPC/CrPC/IEA sections to BNS/BNSS/BSA for post-1-July-2024 matters",
      "journal_headnote": {
        "statute_index": "Formal statute name and section, em-dash separated. Example: 'Code of Criminal Procedure (2 of 1974), S. 482 — Penal Code (45 of 1860), S. 498A'",
        "catchword_chain": "Domain — sub-domain — micro-issue, em-dash separated",
        "ratio": "Held — [the holding]. 1-3 sentences in compressed citable form.",
        "negative_carve_out": "What this case does NOT decide. Empty string if none.",
        "paragraph_anchor": "(Paras X, Y-Z) — must reference paragraphs that actually appear in the text. If text has no clean numbering, use '(see judgment text)'",
        "per_judge_attribution": "Empty unless multiple opinions"
      },
      "practitioner_notes": {
        "one_line_topic": "5-12 words capturing the proposition",
        "gist": "2-4 sentences in practitioner prose, FRAMED FOR THIS LAWYER'S SITUATION. Start with the proposition, no throat-clearing.",
        "quotable_phrase": "verbatim phrase from the judgment text",
        "cross_refs": ["other cases cited in this judgment text"]
      }
    }
  ]
}

RULES:
1. Sort cases by relevance — most relevant FIRST.
2. Every fact must come from the fetched judgment text provided below. Do not invent.
3. case_id must be exactly "ik_<doc_id>" using the IK doc IDs of the fetched judgments.
4. If style is "journal", populate journal_headnote richly and set practitioner_notes to null.
5. If style is "practitioner", populate practitioner_notes richly and set journal_headnote to null.
6. Paragraph anchors must reference real paragraphs in the text. If text lacks clear numbering, use "(see judgment text)".
7. Return ONLY JSON. No prose. No markdown fences."""


HEADNOTE_SYSTEM_PROMPT = """You are an expert legal research editor producing headnotes for the Criminal Law Journal (Cri.L.J.). Given the full text of an Indian criminal-law judgment, produce one or more Cri.L.J.-format headnotes for it.

RULES:
1. Each headnote addresses ONE discrete point of law. Multiple issues = lettered headnotes (A), (B), (C)...
2. NEVER fabricate citations. Every cited case must appear verbatim in the judgment text.
3. Paragraph anchors must reference paragraph numbers actually in the judgment.
4. Cri.L.J. style: formal statute naming, em-dash separators, clipped Indian legal English.
5. Produce parallel practitioner_notes for each headnote.
6. Output: pure JSON, no markdown fences.

SCHEMA:

{
  "case_metadata": {
    "title": "string",
    "court": "string",
    "bench": "string",
    "date_of_decision": "string (DD-MM-YYYY)",
    "appeal_number": "string"
  },
  "headnotes": [
    {
      "letter": "A" | "B" | "C" | ...,
      "journal_headnote": {
        "statute_index": "string",
        "catchword_chain": "string",
        "ratio": "string",
        "negative_carve_out": "string",
        "paragraph_anchor": "string",
        "per_judge_attribution": "string"
      },
      "practitioner_notes": {
        "one_line_topic": "string",
        "gist": "string",
        "quotable_phrase": "string",
        "cross_refs": ["string"]
      }
    }
  ],
  "cases_referred": [
    {"citation": "string", "treatment": "followed|distinguished|overruled|referred"}
  ]
}

Return only valid JSON. No markdown."""


# ─── DB ────────────────────────────────────────

def init_feedback_db() -> None:
    try:
        conn = sqlite3.connect(FEEDBACK_DB)
        conn.execute("""CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL, mode TEXT NOT NULL,
            input_text TEXT NOT NULL, output_json TEXT NOT NULL,
            rating INTEGER NOT NULL, correction TEXT, lawyer_handle TEXT
        )""")
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"db init failed: {e}")


# ─── Pydantic models ───────────────────────────

class SituationReq(BaseModel):
    situation: str = Field(..., min_length=10, max_length=8000)
    style: Literal["journal", "practitioner"] = "journal"


class DigestReq(BaseModel):
    topic: str = Field(..., min_length=5, max_length=2000)
    style: Literal["journal", "practitioner"] = "practitioner"


class HeadnoteReq(BaseModel):
    judgment_text: str = Field(..., min_length=200, max_length=80000)


class TranslateReq(BaseModel):
    payload: dict
    target_language: Literal["hi"] = "hi"


class FeedbackReq(BaseModel):
    mode: str
    input_text: str
    output_json: str
    rating: int
    correction: str | None = None
    lawyer_handle: str | None = None


# ─── App ───────────────────────────────────────

app = FastAPI(title="Headnote", version="0.4.1-demo")
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
        "version": "0.4.1-demo",
        "mode": "live-ik-standalone",
        "anthropic_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "ik_token_set": bool(IK_TOKEN),
        "ik_token_prefix": IK_TOKEN[:8] + "..." if IK_TOKEN else None,
        "translate_available": TRANSLATE_AVAILABLE,
        "default_model": SONNET_MODEL,
    }


# ────────────────────────────────────────────────────────────────────
# /api/situation — LIVE Indian Kanoon, exactly 3 cases max
# ────────────────────────────────────────────────────────────────────

@app.post("/api/situation")
def api_situation(req: SituationReq):
    log("=" * 60)
    log(f"SITUATION REQUEST")
    log(f"  situation: '{req.situation[:150]}'")
    log(f"  style: {req.style}")
    t0 = time.time()

    # ─── Step 1: Expand the situation into IK search queries ───
    log("step 1: expanding query via Sonnet")
    try:
        raw, _ = call_claude(SONNET_MODEL, EXPAND_PROMPT, req.situation, max_tokens=300)
        clean = strip_json_fences(raw)
        log(f"  expand cleaned: {clean[:200]}")
        queries = json.loads(clean)
        if not isinstance(queries, list) or not all(isinstance(q, str) for q in queries):
            log("  expand returned non-list, falling back to raw situation")
            queries = [req.situation]
        queries = [q.strip() for q in queries if q.strip()][:3]
    except Exception as e:
        log(f"  expand FAILED: {type(e).__name__}: {e}, falling back to raw situation")
        queries = [req.situation]
    log(f"  final queries: {queries}")

    # ─── Step 2: Search IK for each query, dedupe, filter to SC ───
    log("step 2: searching IK")
    seen: dict[str, dict] = {}
    for q in queries:
        try:
            hits = ik_search(q, max_results=5)
            for h in hits:
                doc_id = str(h.get("tid", "")).strip()
                court  = (h.get("docsource", "") or "")
                if not doc_id:
                    continue
                if "supreme court" not in court.lower():
                    continue
                if doc_id not in seen:
                    seen[doc_id] = h
                if len(seen) >= MAX_JUDGMENTS_FETCH * 2:
                    break
        except Exception as e:
            log(f"  search failed for query '{q}': {e}")
        if len(seen) >= MAX_JUDGMENTS_FETCH * 2:
            break
    log(f"  collected {len(seen)} unique SC docs")

    if not seen:
        log("  no SC judgments found, returning low-confidence empty")
        return {
            "result": {
                "confidence": "low",
                "no_match_reason": "No Supreme Court criminal judgments found on Indian Kanoon for this situation. Try refining with specific statute sections or fact details.",
                "style": req.style,
                "cases": [],
            },
            "raw": "",
            "dropped_hallucinations": [],
            "meta": {
                "elapsed_seconds": round(time.time() - t0, 2),
                "model": SONNET_MODEL,
                "ik_judgments": 0,
            },
        }

    # ─── Step 3: Fetch full text of top N ───
    log("step 3: fetching full judgment text")
    judgments = []
    for h in list(seen.values())[:MAX_JUDGMENTS_FETCH]:
        doc_id = str(h["tid"])
        full = ik_fetch(doc_id)
        if not full:
            continue
        text = clean_html(full.get("doc", ""))
        if not text:
            log(f"  fetched {doc_id} but text was empty")
            continue
        if len(text) > MAX_CHARS_PER_DOC:
            text = text[:MAX_CHARS_PER_DOC] + "\n\n[...judgment truncated for length...]"
        judgments.append({
            "doc_id":    doc_id,
            "title":     clean_html(h.get("title", "")),
            "court":     h.get("docsource", ""),
            "date":      h.get("publishdate", ""),
            "url":       f"https://indiankanoon.org/doc/{doc_id}/",
            "full_text": text,
        })
        log(f"  fetched {doc_id}: {len(text)} chars — {clean_html(h.get('title',''))[:60]}")

    if not judgments:
        log("  all fetches failed or returned empty")
        return {
            "result": {
                "confidence": "low",
                "no_match_reason": "Found relevant judgments on Indian Kanoon but could not fetch their text. Try again in a moment.",
                "style": req.style,
                "cases": [],
            },
            "raw": "",
            "dropped_hallucinations": [],
            "meta": {
                "elapsed_seconds": round(time.time() - t0, 2),
                "model": SONNET_MODEL,
                "ik_judgments": 0,
            },
        }

    # ─── Step 4: Send to Sonnet for structured 3-case output ───
    log(f"step 4: sending {len(judgments)} judgments to Sonnet")
    user_msg = (
        f"LAWYER'S SITUATION:\n{req.situation}\n\n"
        f"STYLE: {req.style}\n\n"
        f"JUDGMENTS FETCHED FROM INDIAN KANOON FOR THIS QUERY:\n\n"
    )
    for j in judgments:
        user_msg += (
            f"---\n"
            f"case_id: ik_{j['doc_id']}\n"
            f"title: {j['title']}\n"
            f"court: {j['court']}\n"
            f"date: {j['date']}\n"
            f"url: {j['url']}\n\n"
            f"FULL JUDGMENT TEXT:\n{j['full_text']}\n\n"
        )
    user_msg += (
        f"---\n\nReturn the JSON with EXACTLY {len(judgments)} cases in the schema, "
        f"ranked by relevance to the lawyer's situation. JSON only, no prose, no fences."
    )

    try:
        raw, usage = call_claude(SONNET_MODEL, SITUATION_SYSTEM_PROMPT, user_msg, max_tokens=4000)
    except Exception as e:
        log(f"  sonnet call FAILED: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")

    clean = strip_json_fences(raw)
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as e:
        log(f"  JSON parse FAILED: {e}")
        log(f"  raw start (500 chars): {clean[:500]}")
        raise HTTPException(status_code=502, detail=f"Invalid JSON from model: {e}")

    if isinstance(parsed, dict) and "cases" in parsed:
        parsed["cases"] = parsed["cases"][:3]
        for c in parsed["cases"]:
            if isinstance(c, dict):
                c["_quality"] = "sonnet"

    elapsed = round(time.time() - t0, 2)
    n_cases = len(parsed.get("cases", [])) if isinstance(parsed, dict) else 0
    log(f"DONE in {elapsed}s — returned {n_cases} cases")

    return {
        "result": parsed,
        "raw": raw,
        "dropped_hallucinations": [],
        "meta": {
            "elapsed_seconds": elapsed,
            "model": SONNET_MODEL,
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "cost_usd": round(
                usage["input_tokens"]  * 3.0  / 1_000_000
                + usage["output_tokens"] * 15.0 / 1_000_000, 6),
            "cost_inr": round(
                (usage["input_tokens"]  * 3.0  / 1_000_000
                 + usage["output_tokens"] * 15.0 / 1_000_000) * 84, 4),
            "ik_judgments": len(judgments),
            "ik_doc_ids": [j["doc_id"] for j in judgments],
        },
    }


# ────────────────────────────────────────────────────────────────────
# /api/digest — same flow as situation, topic-style output
# ────────────────────────────────────────────────────────────────────

@app.post("/api/digest")
def api_digest(req: DigestReq):
    # Reuse situation pipeline — the LLM frames output appropriately
    # based on the prompt's "style" handling.
    fake = SituationReq(situation=f"Topic / doctrinal question: {req.topic}", style=req.style)
    return api_situation(fake)


# ────────────────────────────────────────────────────────────────────
# /api/headnote — paste mode, Opus
# ────────────────────────────────────────────────────────────────────

@app.post("/api/headnote")
def api_headnote(req: HeadnoteReq):
    log("=" * 60)
    log(f"HEADNOTE REQUEST — text len={len(req.judgment_text)}")
    t0 = time.time()
    user_msg = f"JUDGMENT TEXT:\n{req.judgment_text[:30000]}\n\n---\nProduce headnote(s) per the schema. Return JSON only."
    try:
        raw, usage = call_claude(OPUS_MODEL, HEADNOTE_SYSTEM_PROMPT, user_msg, max_tokens=4000)
    except Exception as e:
        log(f"  opus call FAILED: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")

    clean = strip_json_fences(raw)
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as e:
        log(f"  JSON parse FAILED: {e}")
        raise HTTPException(status_code=502, detail=f"Invalid JSON: {e}")

    elapsed = round(time.time() - t0, 2)
    log(f"DONE headnote in {elapsed}s")
    return {
        "result": parsed,
        "raw": raw,
        "meta": {
            "elapsed_seconds": elapsed,
            "model": OPUS_MODEL,
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
        },
    }


# ────────────────────────────────────────────────────────────────────
# /api/translate
# ────────────────────────────────────────────────────────────────────

@app.post("/api/translate")
def api_translate(req: TranslateReq):
    if not TRANSLATE_AVAILABLE:
        raise HTTPException(503, "Translation service not available in this build.")
    t0 = time.time()
    try:
        translated = translate_payload(req.payload, target=req.target_language)
    except Exception as e:
        raise HTTPException(502, f"Translation failed: {e}")
    return {
        "result": translated,
        "raw": json.dumps(translated, ensure_ascii=False),
        "meta": {
            "elapsed_seconds": round(time.time() - t0, 2),
            "model": "google-translate (free)",
            "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0.0, "cost_inr": 0.0, "free": True,
        },
    }


# ────────────────────────────────────────────────────────────────────
# /api/feedback
# ────────────────────────────────────────────────────────────────────

@app.post("/api/feedback")
def api_feedback(req: FeedbackReq):
    try:
        conn = sqlite3.connect(FEEDBACK_DB)
        conn.execute(
            "INSERT INTO feedback (ts, mode, input_text, output_json, rating, correction, lawyer_handle) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), req.mode, req.input_text,
             req.output_json, req.rating, req.correction or "", req.lawyer_handle or ""),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"feedback save failed: {e}")
        raise HTTPException(500, f"feedback save failed: {e}")
    return {"ok": True}


# ────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def all_exception_handler(request: Request, exc: Exception):
    log(f"UNHANDLED EXCEPTION: {type(exc).__name__}: {exc}")
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return JSONResponse(status_code=500, content={"error": str(exc)})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

log("Headnote 0.4.1-demo loaded")
log(f"  IK token prefix: {IK_TOKEN[:8]}...")
log(f"  Anthropic key set: {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
log(f"  Translate available: {TRANSLATE_AVAILABLE}")
