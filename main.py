"""
Headnote — Hybrid v0.5.1 — robust JSON
======================================
Same hybrid pipeline as v0.5.0, plus:
- JSON prefill (forces { at start of response)
- Robust JSON extractor (handles preamble/postamble)
- Better error visibility (logs actual Sonnet response when parse fails)
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

try:
    from translate import translate_payload
    TRANSLATE_AVAILABLE = True
except Exception:
    TRANSLATE_AVAILABLE = False


# ─── Config ───
IK_TOKEN = "67350ec889bb47d1a3fd96f8568a341bf9b0ab23"

SONNET_MODEL = "claude-sonnet-4-6"
OPUS_MODEL   = "claude-opus-4-7"

IK_CANDIDATES_PER_QUERY = 8
MAX_QUERIES             = 4
MAX_CANDIDATES_TO_RANK  = 30
TOP_K_TO_FETCH          = 5
MAX_FINAL_CASES         = 3
MAX_CHARS_PER_DOC       = 30_000

IK_TIMEOUT_SEARCH = 30
IK_TIMEOUT_FETCH  = 60

APP_DIR     = Path(__file__).parent
STATIC_DIR  = APP_DIR / "static"
CASES_PATH  = APP_DIR / "cases.json"
FEEDBACK_DB = Path(os.environ.get("FEEDBACK_DB", str(APP_DIR / "feedback.db")))


def log(msg: str) -> None:
    print(f"[hn] {msg}", flush=True)
    sys.stdout.flush()


# ─────────────────────────────────────────────
# JSON HANDLING — robust, multi-fallback
# ─────────────────────────────────────────────

def robust_json_parse(raw: str, expected_start: str = "{") -> dict | list:
    """
    Try multiple strategies to extract valid JSON from a model response.
    Order: strip fences → find first balanced brace → eager regex.
    """
    if not raw:
        raise ValueError("Empty response")

    # Strategy 1: strip code fences and parse directly
    t = raw.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    t = t.strip()

    # Sometimes responses start with prose like "Here is the JSON:" — strip until { or [
    if t and not t.startswith(("{", "[")):
        idx = min((t.find(c) for c in "{[" if t.find(c) != -1), default=-1)
        if idx > 0:
            t = t[idx:]

    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass

    # Strategy 2: find the first balanced JSON object via bracket counting
    start_char = expected_start
    end_char = "}" if start_char == "{" else "]"
    depth = 0
    start_idx = -1
    in_string = False
    escape = False

    for i, ch in enumerate(t):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == start_char:
            if start_idx == -1:
                start_idx = i
            depth += 1
        elif ch == end_char:
            depth -= 1
            if depth == 0 and start_idx != -1:
                candidate = t[start_idx:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start_idx = -1
                    continue

    # Strategy 3: prepend assumed start character (for prefill cases)
    try:
        return json.loads(start_char + t)
    except json.JSONDecodeError:
        pass

    # All failed
    raise json.JSONDecodeError(
        f"Could not extract JSON. Response start: {t[:200]}",
        t, 0
    )


def clean_html(raw: str) -> str:
    if not raw:
        return ""
    t = re.sub(r"<[^>]+>", " ", raw)
    t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")
          .replace("&#8377;", "₹"))
    return re.sub(r"\s+", " ", t).strip()


# ─── Indian Kanoon ───

def ik_headers() -> dict:
    return {"Authorization": f"Token {IK_TOKEN}", "Accept": "application/json"}


def ik_search(query: str, max_results: int = 8) -> list:
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
    log(f"  search status: {r.status_code}")
    if r.status_code != 200:
        return []
    try:
        return r.json().get("docs", [])[:max_results]
    except Exception:
        return []


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
        return None
    try:
        return r.json()
    except Exception:
        return None


def classify_court(docsource: str) -> dict:
    src = (docsource or "").lower()
    if "supreme court" in src:
        return {"tier": "SC", "label": "Supreme Court of India", "weight": 10}
    if "high court" in src:
        state = src.replace("high court", "").replace("of", "").strip(" ,-")
        state = state.title() if state else "High Court"
        return {"tier": "HC", "label": f"High Court — {state}", "weight": 6}
    return {"tier": "OTHER", "label": docsource or "Other Court", "weight": 3}


# ─── Anthropic with JSON prefill ───

def get_client() -> Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured.")
    return Anthropic(api_key=key)


def call_claude_json(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 4000,
    prefill: str = "{",
) -> tuple[str, dict]:
    """Call Claude with assistant prefill — forces response to start with `{`."""
    log(f"call_claude_json: model={model}, sys_len={len(system)}, user_len={len(user)}, prefill='{prefill}'")
    client = get_client()
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[
                {"role": "user", "content": user},
                {"role": "assistant", "content": prefill},
            ],
        )
    except Exception as e:
        log(f"  ANTHROPIC ERROR: {type(e).__name__}: {e}")
        raise

    # The prefill is the FIRST char of the assistant's "thinking" — model continues from it.
    # We prepend it back so the parser sees full valid JSON.
    raw = prefill + resp.content[0].text
    u = resp.usage
    log(f"  response: {len(raw)} chars (incl. prefill), in={u.input_tokens}, out={u.output_tokens}")
    return raw, {
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "model": model,
    }


def call_claude_text(model: str, system: str, user: str, max_tokens: int = 4000) -> tuple[str, dict]:
    """Plain text response — no prefill. Used for /api/headnote which may legitimately have lettered headnotes."""
    log(f"call_claude_text: model={model}")
    client = get_client()
    resp = client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = resp.content[0].text
    u = resp.usage
    return raw, {
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "model": model,
    }


def cost_inr(usage_list: list[dict]) -> float:
    total_usd = 0.0
    for u in usage_list:
        m = u.get("model", "")
        if "sonnet" in m:
            in_p, out_p = 3.0, 15.0
        elif "haiku" in m:
            in_p, out_p = 0.8, 4.0
        else:
            in_p, out_p = 15.0, 75.0
        total_usd += u["input_tokens"] * in_p / 1_000_000
        total_usd += u["output_tokens"] * out_p / 1_000_000
    return round(total_usd * 84, 4)


# ─────────────────────────────────────────────
# PROMPTS — simplified for reliable JSON
# ─────────────────────────────────────────────

CURATED_PICK_PROMPT = """You are Headnote's senior research assistant, supervised by a senior criminal advocate (26 years at the Bar).

You will receive a lawyer's situation AND a curated corpus of Supreme Court criminal judgments.

Determine if 3+ cases in the corpus are STRONG matches for this specific situation. Score on:
- Statute overlap (same sections?)
- Doctrinal overlap (same legal point?)
- Factual similarity (same fact pattern?)
- Procedural posture (same stage?)
- Argument angle (does it actually help the lawyer's argument?)

Be HONEST. Better to say "no strong matches" than to force-fit.

Return EXACTLY this JSON structure (no other text):
{"has_strong_matches": true_or_false, "reasoning": "1-2 sentences", "selected_case_ids": ["id1","id2","id3"]}

Rules:
- has_strong_matches is true ONLY if 3+ cases in the corpus are genuinely on-point.
- If true, selected_case_ids has exactly 3 corpus ids (most relevant first).
- If false, selected_case_ids is an empty array.
- A "strong match" means: same statute, same doctrine, same procedural posture or fact pattern. A landmark on a vaguely related topic is NOT strong."""


QUERY_EXPAND_PROMPT = """You are a senior research clerk for Indian criminal law. Convert the advocate's situation into 3-4 search queries for Indian Kanoon.

Return EXACTLY a JSON array of 3-4 strings, no other text. Example:
["query 1","query 2","query 3"]

Each query: 4-8 words. Use Indian statute language: "Section 482 CrPC", "Section 498A IPC", "BNS 2023", "PMLA Section 45", "NDPS Section 37".

Mix:
- One narrow query using exact statute + doctrinal label
- One using leading case names if you know them (e.g., "Bhajan Lal categories quashing")
- One using procedural posture
- One broad doctrinal query"""


CANDIDATE_RANK_PROMPT = """You are Headnote's senior research assistant. You have the lawyer's situation AND a list of candidate judgments (titles + courts + dates) from Indian Kanoon.

Rank by relevance to the SPECIFIC situation. Pick TOP 5 (or fewer if fewer are relevant).

Score on:
- Title relevance (right doctrinal area?)
- Court hierarchy (Supreme Court > High Court, but recent on-point HC > old off-point SC)
- Recency (for evolving doctrines, recent matters more)
- Apparent fit

Be RUTHLESS about irrelevance. If a candidate is clearly off-topic (constitutional case in a bail query, anti-defection in a quashing query) — DO NOT INCLUDE IT.

Return EXACTLY this JSON:
{"selected_indices": [0,5,7,12,18], "reasoning": "1-2 sentences"}

Rules:
- selected_indices: zero-based indices in ranked order, max 5.
- Can be fewer if fewer candidates are relevant.
- If NO candidates are relevant, return empty array."""


SITUATION_OUTPUT_PROMPT = """You are Headnote's senior research assistant, supervised by a senior criminal advocate (26 years at the Bar). You produce Cri.L.J. journal-grade output for Indian criminal lawyers.

INPUT: A lawyer's situation + full text of 1 to 5 judgments (Supreme Court or High Court).

YOUR TASK: Produce structured Cri.L.J. headnotes, FRAMED FOR THIS LAWYER'S SITUATION. Maximum 3 cases.

QUALITY GATE — Critical:
- Better to return 1 strong case than 3 weak ones.
- Better to return 0 with honest "no match" than force-fit irrelevant judgments.
- If a judgment is off-point, EXCLUDE IT.

Return EXACTLY this JSON structure:
{
  "confidence": "high",
  "no_match_reason": "",
  "style": "journal",
  "cases": [
    {
      "case_id": "ik_DOCID",
      "title": "Parties (Name v. Name)",
      "citation": "preferred citation if in text, else IK URL",
      "court": "Supreme Court of India",
      "court_tier": "SC",
      "year": 2022,
      "relevance_explanation": "2-3 sentences on why this case matches THIS specific situation",
      "bns_note": "1 sentence on IPC/CrPC/IEA to BNS/BNSS/BSA mapping",
      "journal_headnote": {
        "statute_index": "Code of Criminal Procedure (2 of 1974), S. 482 — Penal Code (45 of 1860), S. 498A",
        "catchword_chain": "Domain — sub-domain — micro-issue",
        "ratio": "Held — the holding in compressed Cri.L.J. cadence (1-3 sentences)",
        "negative_carve_out": "What this case does NOT decide, or empty string",
        "paragraph_anchor": "(Paras X, Y-Z)",
        "per_judge_attribution": "Empty unless multiple opinions"
      },
      "practitioner_notes": null
    }
  ]
}

Rules:
- confidence: "high" if all returned are strong, "medium" if some weaker, "low" if forced to return weak matches (also fill no_match_reason).
- Sort by relevance (most relevant first).
- Every fact from judgment text. Do not invent.
- case_id: "ik_<doc_id>" for IK-sourced.
- court_tier: "SC" or "HC".
- If style is "journal" → fill journal_headnote, set practitioner_notes to null.
- If style is "practitioner" → fill practitioner_notes (one_line_topic, gist, quotable_phrase, cross_refs), set journal_headnote to null.
- Return ONLY JSON. Nothing else."""


CURATED_OUTPUT_PROMPT = """You are Headnote's senior research assistant, supervised by a senior criminal advocate (26 years at the Bar).

INPUT: A lawyer's situation + 3 hand-curated Supreme Court judgments with pre-vetted scaffolding.

YOUR TASK: Produce final structured output, FRAMED FOR THIS LAWYER'S SITUATION. Use the curated fields as source of truth; your job is to frame relevance for this query.

Return EXACTLY this JSON:
{
  "confidence": "high",
  "style": "journal",
  "cases": [
    {
      "case_id": "the-curated-id",
      "title": "from curated",
      "citation": "from curated",
      "court": "Supreme Court of India",
      "court_tier": "SC",
      "year": 2022,
      "relevance_explanation": "2-3 sentences on why this case matches THIS specific situation",
      "bns_note": "from curated bns_mapping",
      "journal_headnote": {
        "statute_index": "from curated headnote.statute_index",
        "catchword_chain": "from curated headnote.catchword_chain",
        "ratio": "from curated headnote.ratio, refined for this query",
        "negative_carve_out": "from curated",
        "paragraph_anchor": "from curated",
        "per_judge_attribution": "from curated"
      },
      "practitioner_notes": null
    }
  ]
}

Rules:
- Sort by relevance.
- For style="journal": fill journal_headnote, null practitioner_notes.
- For style="practitioner": fill practitioner_notes, null journal_headnote.
- Return ONLY JSON."""


HEADNOTE_SYSTEM_PROMPT = """You are an expert legal editor producing Cri.L.J. headnotes for Indian criminal judgments.

RULES:
1. One headnote per discrete point of law (lettered A, B, C...).
2. No fabricated citations.
3. Paragraph anchors must reference real paragraphs.
4. Cri.L.J. style: formal statute naming, em-dash separators.

Return JSON:
{
  "case_metadata": {"title":"","court":"","bench":"","date_of_decision":"","appeal_number":""},
  "headnotes": [{"letter":"A","journal_headnote":{...},"practitioner_notes":{...}}],
  "cases_referred": [{"citation":"","treatment":"followed|distinguished|overruled|referred"}]
}"""


# ─── Corpus helpers ───

def load_corpus() -> list[dict]:
    try:
        return json.loads(CASES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"WARN: could not load cases.json ({e})")
        return []


def corpus_minimal(cases: list[dict]) -> str:
    mini = []
    for c in cases:
        mini.append({
            "id":     c.get("id"),
            "title":  c.get("title"),
            "year":   c.get("year"),
            "topics": c.get("topics", []),
            "ratio_summary": (c.get("headnote", {}) or {}).get("ratio", "")[:300],
            "gist":   (c.get("practitioner_notes", {}) or {}).get("gist", "")[:300],
        })
    return json.dumps(mini, ensure_ascii=False)


def find_curated_by_ids(corpus: list[dict], ids: list[str]) -> list[dict]:
    by_id = {c.get("id"): c for c in corpus}
    return [by_id[i] for i in ids if i in by_id]


# ─── DB ───

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


# ─── Models ───

class SituationReq(BaseModel):
    situation: str = Field(..., min_length=10, max_length=8000)
    style: Literal["journal", "practitioner"] = "journal"
    include_hc: bool = True


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


# ─── App ───

app = FastAPI(title="Headnote", version="0.5.1-hybrid-robust")
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
        "version": "0.5.1-hybrid-robust",
        "mode": "curated-first-then-live-ik",
        "anthropic_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "ik_token_set": bool(IK_TOKEN),
        "ik_token_prefix": IK_TOKEN[:8] + "..." if IK_TOKEN else None,
        "curated_corpus_size": len(load_corpus()),
        "translate_available": TRANSLATE_AVAILABLE,
        "default_model": SONNET_MODEL,
    }


@app.post("/api/situation")
def api_situation(req: SituationReq):
    log("=" * 70)
    log(f"SITUATION: '{req.situation[:120]}'")
    log(f"  style={req.style} include_hc={req.include_hc}")
    t0 = time.time()
    usage_list = []
    corpus = load_corpus()

    # ─── Layer 1: Curated check ───
    curated_used = False
    if len(corpus) >= 3:
        log("LAYER 1: checking curated corpus")
        try:
            pick_user = (
                f"LAWYER'S SITUATION:\n{req.situation}\n\n"
                f"CURATED CORPUS:\n\n{corpus_minimal(corpus)}\n\n"
                f"Return the JSON object now."
            )
            raw, usage = call_claude_json(SONNET_MODEL, CURATED_PICK_PROMPT, pick_user,
                                          max_tokens=600, prefill="{")
            usage_list.append(usage)
            pick = robust_json_parse(raw, expected_start="{")
            log(f"  curated pick: has_strong={pick.get('has_strong_matches')} "
                f"ids={pick.get('selected_case_ids')}")

            if pick.get("has_strong_matches") and len(pick.get("selected_case_ids", [])) >= 3:
                selected = find_curated_by_ids(corpus, pick["selected_case_ids"][:3])
                if len(selected) >= 3:
                    curated_used = True
                    log(f"  ✓ LAYER 1 HIT — using {len(selected)} curated cases")

                    out_user = (
                        f"LAWYER'S SITUATION:\n{req.situation}\n\n"
                        f"STYLE: {req.style}\n\n"
                        f"CURATED CASES:\n\n{json.dumps(selected, ensure_ascii=False)}\n\n"
                        f"Return the JSON object now."
                    )
                    raw2, usage2 = call_claude_json(SONNET_MODEL, CURATED_OUTPUT_PROMPT, out_user,
                                                    max_tokens=4000, prefill="{")
                    usage_list.append(usage2)
                    parsed = robust_json_parse(raw2, expected_start="{")
                    parsed["_source"] = "curated"

                    for c in parsed.get("cases", []):
                        if isinstance(c, dict):
                            c["_quality"] = "curated"

                    elapsed = round(time.time() - t0, 2)
                    log(f"DONE (curated) in {elapsed}s — {len(parsed.get('cases', []))} cases")
                    return {
                        "result": parsed,
                        "raw": raw2,
                        "meta": {
                            "elapsed_seconds": elapsed,
                            "source": "curated_corpus",
                            "model": SONNET_MODEL,
                            "ik_judgments": 0,
                            "cost_inr": cost_inr(usage_list),
                        },
                    }
        except Exception as e:
            log(f"  curated layer failed: {type(e).__name__}: {str(e)[:300]}")
            log(f"  falling through to IK")

    # ─── Layer 2: Live IK ───
    log("LAYER 2: live IK retrieval")

    # 2a expand
    queries = []
    try:
        raw, usage = call_claude_json(SONNET_MODEL, QUERY_EXPAND_PROMPT, req.situation,
                                      max_tokens=300, prefill="[")
        usage_list.append(usage)
        parsed_q = robust_json_parse(raw, expected_start="[")
        if isinstance(parsed_q, list):
            queries = [q for q in parsed_q if isinstance(q, str) and q.strip()][:MAX_QUERIES]
    except Exception as e:
        log(f"  expand failed: {e}, using situation as query")
    if not queries:
        queries = [req.situation[:200]]
    log(f"  queries: {queries}")

    # 2b candidates
    candidates: dict[str, dict] = {}
    for q in queries:
        try:
            hits = ik_search(q, max_results=IK_CANDIDATES_PER_QUERY)
            for h in hits:
                doc_id = str(h.get("tid", "")).strip()
                court  = (h.get("docsource", "") or "")
                if not doc_id or doc_id in candidates:
                    continue
                court_info = classify_court(court)
                if court_info["tier"] == "OTHER":
                    continue
                if court_info["tier"] == "HC" and not req.include_hc:
                    continue
                candidates[doc_id] = {**h, "_court_info": court_info}
                if len(candidates) >= MAX_CANDIDATES_TO_RANK:
                    break
        except Exception as e:
            log(f"  search failed: {e}")
        if len(candidates) >= MAX_CANDIDATES_TO_RANK:
            break

    log(f"  candidates: {len(candidates)} "
        f"(SC: {sum(1 for c in candidates.values() if c['_court_info']['tier']=='SC')}, "
        f"HC: {sum(1 for c in candidates.values() if c['_court_info']['tier']=='HC')})")

    if not candidates:
        return _empty_result("No SC/HC criminal judgments found on Indian Kanoon. Try refining your query.",
                              req.style, t0, usage_list)

    # 2c rank
    cand_list = list(candidates.values())
    cand_summary = [{
        "index": i,
        "title": clean_html(c.get("title", "")),
        "court": c["_court_info"]["label"],
        "tier":  c["_court_info"]["tier"],
        "date":  c.get("publishdate", ""),
    } for i, c in enumerate(cand_list)]

    selected_indices = []
    try:
        rank_user = (
            f"LAWYER'S SITUATION:\n{req.situation}\n\n"
            f"CANDIDATES (indexed 0-{len(cand_list)-1}):\n\n{json.dumps(cand_summary, ensure_ascii=False)}\n\n"
            f"Return the JSON object now."
        )
        raw, usage = call_claude_json(SONNET_MODEL, CANDIDATE_RANK_PROMPT, rank_user,
                                      max_tokens=400, prefill="{")
        usage_list.append(usage)
        rank = robust_json_parse(raw, expected_start="{")
        selected_indices = rank.get("selected_indices", [])[:TOP_K_TO_FETCH]
        log(f"  ranked: {selected_indices}")
    except Exception as e:
        log(f"  rank failed: {e}, defaulting to first 3")
        selected_indices = list(range(min(3, len(cand_list))))

    if not selected_indices:
        return _empty_result(
            "Indian Kanoon returned candidates but none were directly relevant. "
            "Try refining your query with specific statute sections or doctrinal labels.",
            req.style, t0, usage_list)

    # 2d fetch
    judgments = []
    for idx in selected_indices:
        if not (0 <= idx < len(cand_list)):
            continue
        c = cand_list[idx]
        doc_id = str(c["tid"])
        full = ik_fetch(doc_id)
        if not full:
            continue
        text = clean_html(full.get("doc", ""))
        if not text:
            continue
        if len(text) > MAX_CHARS_PER_DOC:
            text = text[:MAX_CHARS_PER_DOC] + "\n[...truncated...]"
        judgments.append({
            "doc_id":     doc_id,
            "title":      clean_html(c.get("title", "")),
            "court":      c["_court_info"]["label"],
            "court_tier": c["_court_info"]["tier"],
            "date":       c.get("publishdate", ""),
            "url":        f"https://indiankanoon.org/doc/{doc_id}/",
            "full_text":  text,
        })
        log(f"  fetched {doc_id} ({c['_court_info']['tier']}): {clean_html(c.get('title',''))[:50]}")

    if not judgments:
        return _empty_result("Could not fetch judgment texts. Try again.",
                              req.style, t0, usage_list)

    # 2e generate
    out_user = f"LAWYER'S SITUATION:\n{req.situation}\n\nSTYLE: {req.style}\n\nJUDGMENTS:\n\n"
    for j in judgments:
        out_user += (
            f"---\ncase_id: ik_{j['doc_id']}\ntitle: {j['title']}\n"
            f"court: {j['court']}\ncourt_tier: {j['court_tier']}\ndate: {j['date']}\n"
            f"url: {j['url']}\n\nFULL TEXT:\n{j['full_text']}\n\n"
        )
    out_user += (
        f"---\n\nProduce final JSON. Maximum 3 cases. EXCLUDE off-point judgments. "
        f"Better to return 1-2 strong cases than 3 weak ones. Return the JSON object now."
    )

    try:
        raw, usage = call_claude_json(SONNET_MODEL, SITUATION_OUTPUT_PROMPT, out_user,
                                      max_tokens=4000, prefill="{")
        usage_list.append(usage)
    except Exception as e:
        raise HTTPException(502, f"LLM call failed: {e}")

    try:
        parsed = robust_json_parse(raw, expected_start="{")
    except json.JSONDecodeError as e:
        log(f"  FINAL JSON parse failed: {e}")
        log(f"  raw (first 1000): {raw[:1000]}")
        raise HTTPException(502, f"Output formatting error. Render Logs have details. {str(e)[:200]}")

    if isinstance(parsed, dict) and "cases" in parsed:
        parsed["cases"] = parsed["cases"][:MAX_FINAL_CASES]
        for c in parsed["cases"]:
            if isinstance(c, dict):
                c["_quality"] = "ik_two_stage"
    parsed["_source"] = "ik_live"

    elapsed = round(time.time() - t0, 2)
    log(f"DONE (IK) in {elapsed}s — {len(parsed.get('cases', []))} cases")
    return {
        "result": parsed,
        "raw": raw,
        "meta": {
            "elapsed_seconds": elapsed,
            "source": "ik_two_stage",
            "model": SONNET_MODEL,
            "ik_candidates": len(candidates),
            "ik_judgments": len(judgments),
            "queries_used": queries,
            "cost_inr": cost_inr(usage_list),
        },
    }


def _empty_result(reason: str, style: str, t0: float, usage_list: list) -> dict:
    return {
        "result": {
            "confidence": "low",
            "no_match_reason": reason,
            "style": style,
            "cases": [],
        },
        "raw": "",
        "meta": {
            "elapsed_seconds": round(time.time() - t0, 2),
            "source": "no_match",
            "model": SONNET_MODEL,
            "ik_judgments": 0,
            "cost_inr": cost_inr(usage_list),
        },
    }


@app.post("/api/headnote")
def api_headnote(req: HeadnoteReq):
    log(f"HEADNOTE: len={len(req.judgment_text)}")
    t0 = time.time()
    user_msg = f"JUDGMENT TEXT:\n{req.judgment_text[:30000]}\n\nReturn the JSON object now."
    raw, usage = call_claude_json(OPUS_MODEL, HEADNOTE_SYSTEM_PROMPT, user_msg,
                                  max_tokens=4000, prefill="{")
    try:
        parsed = robust_json_parse(raw, expected_start="{")
    except json.JSONDecodeError as e:
        log(f"  headnote parse failed: raw={raw[:500]}")
        raise HTTPException(502, f"Output formatting error: {str(e)[:200]}")
    return {
        "result": parsed,
        "raw": raw,
        "meta": {
            "elapsed_seconds": round(time.time() - t0, 2),
            "model": OPUS_MODEL,
            "cost_inr": cost_inr([usage]),
        },
    }


@app.post("/api/translate")
def api_translate(req: TranslateReq):
    if not TRANSLATE_AVAILABLE:
        raise HTTPException(503, "Translation unavailable.")
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
            "model": "google-translate",
            "cost_inr": 0.0,
        },
    }


@app.post("/api/feedback")
def api_feedback(req: FeedbackReq):
    conn = sqlite3.connect(FEEDBACK_DB)
    conn.execute(
        "INSERT INTO feedback (ts, mode, input_text, output_json, rating, correction, lawyer_handle) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), req.mode, req.input_text,
         req.output_json, req.rating, req.correction or "", req.lawyer_handle or ""),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.exception_handler(Exception)
async def all_exception_handler(request: Request, exc: Exception):
    log(f"UNHANDLED: {type(exc).__name__}: {exc}")
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return JSONResponse(status_code=500, content={"error": str(exc)})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

log("Headnote v0.5.1-hybrid-robust loaded")
log(f"  Curated corpus: {len(load_corpus())} cases")
log(f"  IK token prefix: {IK_TOKEN[:8]}...")
log(f"  Anthropic key set: {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
