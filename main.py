"""
Headnote — Hybrid pipeline v0.5
================================
Layer 1: Curated 42 cases (v0.3 quality)
Layer 2: Two-stage live IK retrieval (SC + High Courts)
Quality gate: Honest rejection over forced 3.
Editorial parity: same Cri.L.J. style across both paths.
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


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
IK_TOKEN = "67350ec889bb47d1a3fd96f8568a341bf9b0ab23"

SONNET_MODEL = "claude-sonnet-4-6"
OPUS_MODEL   = "claude-opus-4-7"

# Two-stage retrieval params
IK_CANDIDATES_PER_QUERY = 8     # how many raw hits per IK search query
MAX_QUERIES             = 4     # how many search queries Sonnet generates
MAX_CANDIDATES_TO_RANK  = 30    # after dedupe, cap candidate pool
TOP_K_TO_FETCH          = 5     # how many full judgments to fetch
MAX_FINAL_CASES         = 3     # max cases returned to lawyer
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
# HTML / TEXT
# ─────────────────────────────────────────────

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
          .replace("&#8377;","₹"))
    return re.sub(r"\s+", " ", t).strip()


def strip_json_fences(raw: str) -> str:
    t = raw.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


# ─────────────────────────────────────────────
# INDIAN KANOON
# ─────────────────────────────────────────────

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
        log(f"  search body preview: {r.text[:300]}")
        return []

    try:
        data = r.json()
    except Exception as e:
        log(f"  search JSON parse failed: {e}")
        return []

    docs = data.get("docs", [])
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
        return None

    try:
        return r.json()
    except Exception as e:
        log(f"  fetch JSON parse failed: {e}")
        return None


def classify_court(docsource: str) -> dict:
    """Classify court level for badge display + ranking weight."""
    src = (docsource or "").lower()
    if "supreme court" in src:
        return {"tier": "SC",  "label": "Supreme Court of India", "weight": 10}
    if "high court" in src:
        # Try to extract state
        state = src.replace("high court", "").replace("of", "").strip(" ,-")
        state = state.title() if state else "High Court"
        return {"tier": "HC",  "label": f"High Court — {state}", "weight": 6}
    return {"tier": "OTHER", "label": docsource or "Other Court", "weight": 3}


# ─────────────────────────────────────────────
# ANTHROPIC
# ─────────────────────────────────────────────

def get_client() -> Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured.")
    return Anthropic(api_key=key)


def call_claude(model: str, system: str, user: str, max_tokens: int = 4000) -> tuple[str, dict]:
    log(f"call_claude: model={model}, sys_len={len(system)}, user_len={len(user)}")
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
        "input_tokens":  u.input_tokens,
        "output_tokens": u.output_tokens,
        "model":         model,
    }


def cost_inr(usage_list: list[dict]) -> float:
    """Sum cost across multiple Claude calls. Prices in USD per million tokens."""
    total_usd = 0.0
    for u in usage_list:
        m = u.get("model", "")
        if "sonnet" in m:
            in_price, out_price = 3.0, 15.0
        elif "haiku" in m:
            in_price, out_price = 0.8, 4.0
        else:  # opus
            in_price, out_price = 15.0, 75.0
        total_usd += u["input_tokens"] * in_price / 1_000_000
        total_usd += u["output_tokens"] * out_price / 1_000_000
    return round(total_usd * 84, 4)


# ─────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────

CURATED_PICK_PROMPT = """You are Headnote's senior research assistant, supervised by a senior criminal advocate (26 years at the Bar).

You will be given a lawyer's specific situation AND the full curated corpus of Supreme Court criminal judgments that Headnote has hand-vetted with editorial supervision.

YOUR TASK: Determine if the curated corpus contains 3+ STRONG matches for this specific situation. Score every case against the situation on:
1. Statute overlap (same IPC/BNS/CrPC/BNSS/Evidence Act sections?)
2. Doctrinal overlap (same legal point — quashing, bail, conviction, evidence?)
3. Factual similarity (same fact pattern?)
4. Procedural posture (same stage of proceedings?)
5. Argument angle (does the case actually help the lawyer's specific argument?)

Be HONEST. Better to say "no strong matches" than to force-fit.

OUTPUT — pure JSON, no prose, no fences:

{
  "has_strong_matches": true | false,
  "reasoning": "1-2 sentences explaining your assessment",
  "selected_case_ids": ["id1", "id2", "id3"]
}

Rules:
- "has_strong_matches" is true ONLY if you find 3+ genuinely on-point cases in the corpus.
- If true, "selected_case_ids" lists EXACTLY 3 case ids, ranked by relevance (most relevant first).
- If false, "selected_case_ids" should be an empty array.
- Use the exact "id" field from the corpus for case ids.
- A "strong match" means: the case is directly on-point for the lawyer's specific question — same statute, same doctrine, same procedural posture or fact pattern. A landmark case on a vaguely related topic is NOT a strong match."""


QUERY_EXPAND_PROMPT = """You are a senior research clerk for Indian criminal law. Convert the advocate's situation into 3-4 search queries for Indian Kanoon (the IK search engine).

Output ONLY a JSON array of 3-4 strings. No prose. No markdown.

Each query: 4-8 words. Use Indian statute language: "Section 482 CrPC", "Section 498A IPC", "BNS 2023", "PMLA Section 45", "NDPS Section 37", etc.

Mix query styles:
- One narrow query using exact statute + doctrinal label (e.g., "Section 482 CrPC quashing settlement matrimonial")
- One query using leading case names if you know them (e.g., "Bhajan Lal categories quashing", "Arnesh Kumar 498A arrest")
- One query using the lawyer's procedural posture (e.g., "anticipatory bail economic offences PMLA")
- One broad query for general doctrine

Example input:
"My client accused under 498A. FIR filed by estranged wife. Marriage settled by mutual consent. Want to quash."

Example output:
["Section 482 CrPC quashing 498A matrimonial settlement", "Gian Singh quashing settlement matrimonial offence", "Bhajan Lal categories quashing 498A FIR", "compounding 498A IPC matrimonial dispute"]"""


CANDIDATE_RANK_PROMPT = """You are Headnote's senior research assistant. You have been given a lawyer's situation AND a list of candidate judgments (titles + courts + dates only) that Indian Kanoon returned for various search queries.

YOUR TASK: Rank these candidates by relevance to the lawyer's specific situation. Pick the TOP 5 (or fewer if fewer are genuinely relevant).

Score each candidate on:
1. Title relevance — does the case name suggest the right doctrinal area?
2. Court hierarchy — Supreme Court > High Court (but a recent on-point HC ruling can beat an off-point SC ruling)
3. Recency — for evolving doctrines (BNS, post-Arnesh Kumar, post-Satender Antil), recent matters more
4. Apparent fit — based on title alone, is this likely the precedent the lawyer wants?

Be RUTHLESS about irrelevance. If a "candidate" is clearly off-topic (e.g., a constitutional law case in a bail query, an old anti-defection case in a quashing query), DO NOT INCLUDE IT.

OUTPUT — pure JSON, no prose, no fences:

{
  "selected_indices": [0, 5, 7, 12, 18],
  "reasoning": "1-2 sentences on why these 5 (or fewer) were selected"
}

Rules:
- "selected_indices" is a list of indices (zero-based) from the candidate list, in ranked order (most relevant first).
- Maximum 5 indices. Can be fewer if fewer candidates are genuinely relevant.
- If NO candidates are relevant, return an empty array. (Better to say nothing than to return junk.)"""


SITUATION_OUTPUT_PROMPT = """You are Headnote's senior research assistant, supervised by a senior criminal advocate (26 years at the Bar). You produce Cri.L.J. journal-grade output for practising Indian criminal lawyers.

INPUT: A lawyer's specific situation + the full text of 1-{n} judgments. Each judgment may be from the Supreme Court or a High Court.

YOUR TASK: Produce structured Cri.L.J. headnotes for each judgment, FRAMED FOR THIS LAWYER'S SITUATION. Maximum 3 cases. If only 1-2 are genuinely strong matches, return only those — DO NOT pad with weak matches.

QUALITY GATE — Critical:
- Better to return 1 strong case than 3 weak ones.
- Better to return 0 cases with an honest "no match" message than to force a Kesavananda Bharati into a bail query.
- If a judgment is clearly off-point, EXCLUDE IT. Set confidence="low" and explain in no_match_reason.

OUTPUT — pure JSON, no prose, no fences:

{
  "confidence": "high" | "medium" | "low",
  "no_match_reason": "string (only if confidence=low or fewer than 3 cases returned)",
  "style": "journal" | "practitioner",
  "cases": [
    {
      "case_id": "ik_<doc_id> for IK-sourced cases, or the curated id",
      "title": "Parties (italicised in display)",
      "citation": "preferred reported citation if visible in text, else IK URL",
      "court": "Supreme Court of India" or "High Court of [State]",
      "court_tier": "SC" | "HC",
      "year": number,
      "relevance_explanation": "2-3 sentences on why THIS case is among the top for THIS specific situation. Cite the exact overlap (same statute? same doctrine? same fact pattern?)",
      "bns_note": "1 sentence mapping IPC/CrPC/IEA sections to BNS/BNSS/BSA for post-1-July-2024 matters",
      "journal_headnote": {
        "statute_index": "Formal statute names + sections, em-dash separated. Example: 'Code of Criminal Procedure (2 of 1974), S. 482 — Penal Code (45 of 1860), S. 498A'",
        "catchword_chain": "Domain — sub-domain — micro-issue, em-dash separated",
        "ratio": "Held — [the holding]. 1-3 sentences. Compressed citable Cri.L.J. cadence.",
        "negative_carve_out": "What this case does NOT decide. Empty string if none.",
        "paragraph_anchor": "(Paras X, Y-Z) referencing paragraphs in the text. If text lacks numbering, use '(see judgment text)'",
        "per_judge_attribution": "Empty unless multiple opinions"
      },
      "practitioner_notes": {
        "one_line_topic": "5-12 words capturing the proposition",
        "gist": "2-4 sentences in practitioner prose, framed for THIS situation",
        "quotable_phrase": "verbatim phrase from the judgment text",
        "cross_refs": ["other cases cited in this judgment text"]
      }
    }
  ]
}

RULES:
1. Sort by relevance — most relevant FIRST.
2. Every fact must come from the judgment text. Do not invent citations or hold facts not in the text.
3. case_id format: "ik_<doc_id>" for IK-sourced, or the original id for curated cases.
4. court_tier: "SC" for Supreme Court, "HC" for High Court.
5. If style is "journal" → populate journal_headnote richly, set practitioner_notes to null.
6. If style is "practitioner" → populate practitioner_notes richly, set journal_headnote to null.
7. Return ONLY JSON. No prose. No markdown fences."""


CURATED_OUTPUT_PROMPT = """You are Headnote's senior research assistant, supervised by a senior criminal advocate (26 years at the Bar). You produce Cri.L.J. journal-grade output for practising Indian criminal lawyers.

INPUT: A lawyer's specific situation + 3 hand-curated Supreme Court criminal judgments (with full pre-vetted headnote scaffolding).

YOUR TASK: Produce final structured output for each curated case, FRAMED FOR THIS LAWYER'S SITUATION. Use the pre-vetted fields as the source of truth — your job is to frame the relevance for this specific query.

OUTPUT — pure JSON, no prose, no fences:

{
  "confidence": "high" | "medium" | "low",
  "style": "journal" | "practitioner",
  "cases": [
    {
      "case_id": "<the curated id>",
      "title": "string",
      "citation": "string from curated entry",
      "court": "Supreme Court of India",
      "court_tier": "SC",
      "year": number,
      "relevance_explanation": "2-3 sentences on why THIS case is among the top for THIS situation. Cite the exact overlap.",
      "bns_note": "use the curated bns_mapping field, or 1 sentence mapping sections to BNS/BNSS/BSA",
      "journal_headnote": {
        "statute_index": "from curated headnote.statute_index",
        "catchword_chain": "from curated headnote.catchword_chain",
        "ratio": "from curated headnote.ratio (may be refined for this query's framing)",
        "negative_carve_out": "from curated headnote.negative_carve_out",
        "paragraph_anchor": "from curated headnote.paragraph_anchor or key_paras",
        "per_judge_attribution": "from curated, empty if none"
      },
      "practitioner_notes": {
        "one_line_topic": "from curated practitioner_notes.one_line_topic",
        "gist": "from curated practitioner_notes.gist, framed for this situation",
        "quotable_phrase": "from curated practitioner_notes.quotable_phrase",
        "cross_refs": "from curated practitioner_notes.cross_refs"
      }
    }
  ]
}

Rules:
- Sort by relevance (most relevant first).
- For style="journal" populate journal_headnote, null practitioner_notes.
- For style="practitioner" populate practitioner_notes, null journal_headnote.
- Return ONLY JSON. No prose. No fences."""


HEADNOTE_SYSTEM_PROMPT = """You are an expert legal research editor producing headnotes for the Criminal Law Journal (Cri.L.J.). Given the full text of an Indian criminal-law judgment, produce one or more Cri.L.J.-format headnotes for it.

RULES:
1. Each headnote addresses ONE discrete point of law. Multiple issues = lettered headnotes (A), (B), (C)...
2. NEVER fabricate citations. Every cited case must appear verbatim in the judgment text.
3. Paragraph anchors must reference paragraph numbers actually in the judgment.
4. Cri.L.J. style: formal statute naming, em-dash separators, clipped Indian legal English.
5. Produce parallel practitioner_notes for each headnote.
6. Pure JSON, no markdown fences.

SCHEMA:
{
  "case_metadata": {"title":"string","court":"string","bench":"string","date_of_decision":"string","appeal_number":"string"},
  "headnotes": [{
    "letter": "A" | "B" | ...,
    "journal_headnote": {"statute_index":"","catchword_chain":"","ratio":"","negative_carve_out":"","paragraph_anchor":"","per_judge_attribution":""},
    "practitioner_notes": {"one_line_topic":"","gist":"","quotable_phrase":"","cross_refs":[]}
  }],
  "cases_referred": [{"citation":"","treatment":"followed|distinguished|overruled|referred"}]
}"""


# ─────────────────────────────────────────────
# CURATED CORPUS
# ─────────────────────────────────────────────

def load_corpus() -> list[dict]:
    try:
        return json.loads(CASES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"WARN: could not load cases.json ({e}), using empty corpus")
        return []


def corpus_minimal(cases: list[dict]) -> str:
    """Return a JSON string of corpus with only fields needed for selection."""
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


# ─────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

class SituationReq(BaseModel):
    situation: str = Field(..., min_length=10, max_length=8000)
    style: Literal["journal", "practitioner"] = "journal"
    include_hc: bool = True   # default: include High Courts


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


# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

app = FastAPI(title="Headnote", version="0.5.0-hybrid")
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
        "version": "0.5.0-hybrid",
        "mode": "curated-first-then-live-ik",
        "anthropic_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "ik_token_set": bool(IK_TOKEN),
        "ik_token_prefix": IK_TOKEN[:8] + "..." if IK_TOKEN else None,
        "curated_corpus_size": len(load_corpus()),
        "translate_available": TRANSLATE_AVAILABLE,
        "default_model": SONNET_MODEL,
    }


# ────────────────────────────────────────────────────────────────────
# /api/situation — HYBRID PIPELINE
# ────────────────────────────────────────────────────────────────────

@app.post("/api/situation")
def api_situation(req: SituationReq):
    log("=" * 70)
    log(f"SITUATION REQUEST")
    log(f"  situation: '{req.situation[:150]}'")
    log(f"  style: {req.style}, include_hc: {req.include_hc}")
    t0 = time.time()
    usage_list = []

    corpus = load_corpus()
    log(f"  curated corpus: {len(corpus)} cases")

    # ═══════════════════════════════════════════════════════════
    # LAYER 1 — CURATED CORPUS CHECK
    # ═══════════════════════════════════════════════════════════
    curated_used = False
    if len(corpus) >= 3:
        log("LAYER 1: checking curated corpus for strong matches")
        pick_user = (
            f"LAWYER'S SITUATION:\n{req.situation}\n\n"
            f"CURATED CORPUS (each entry has id, title, year, topics, ratio summary, gist):\n\n"
            f"{corpus_minimal(corpus)}\n\n"
            f"Decide: does the corpus contain 3+ STRONG matches for this situation? "
            f"If yes, return their ids ranked by relevance. If no, return empty array. JSON only."
        )
        try:
            raw, usage = call_claude(SONNET_MODEL, CURATED_PICK_PROMPT, pick_user, max_tokens=600)
            usage_list.append(usage)
            pick = json.loads(strip_json_fences(raw))
            log(f"  curated pick: has_strong={pick.get('has_strong_matches')} ids={pick.get('selected_case_ids')}")

            if pick.get("has_strong_matches") and len(pick.get("selected_case_ids", [])) >= 3:
                selected = find_curated_by_ids(corpus, pick["selected_case_ids"][:3])
                if len(selected) >= 3:
                    curated_used = True
                    log(f"  ✓ LAYER 1 HIT — using {len(selected)} curated cases")

                    # Generate final structured output using curated cases
                    out_user = (
                        f"LAWYER'S SITUATION:\n{req.situation}\n\n"
                        f"STYLE: {req.style}\n\n"
                        f"CURATED CASES (with full pre-vetted scaffolding):\n\n"
                        f"{json.dumps(selected, ensure_ascii=False)}\n\n"
                        f"Produce final JSON output for these {len(selected)} cases. JSON only."
                    )
                    raw2, usage2 = call_claude(SONNET_MODEL, CURATED_OUTPUT_PROMPT, out_user, max_tokens=4000)
                    usage_list.append(usage2)
                    parsed = json.loads(strip_json_fences(raw2))
                    parsed["_source"] = "curated"

                    for c in parsed.get("cases", []):
                        c["_quality"] = "curated"

                    elapsed = round(time.time() - t0, 2)
                    log(f"DONE (curated path) in {elapsed}s — {len(parsed.get('cases', []))} cases")
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
            log(f"  curated layer failed: {type(e).__name__}: {e}, falling through to IK")

    # ═══════════════════════════════════════════════════════════
    # LAYER 2 — LIVE IK TWO-STAGE RETRIEVAL
    # ═══════════════════════════════════════════════════════════
    if not curated_used:
        log("LAYER 2: falling through to live Indian Kanoon retrieval")

    # 2a — Expand into search queries
    log("step 2a: expanding situation into IK search queries")
    queries = []
    try:
        raw, usage = call_claude(SONNET_MODEL, QUERY_EXPAND_PROMPT, req.situation, max_tokens=300)
        usage_list.append(usage)
        queries = json.loads(strip_json_fences(raw))
        if not isinstance(queries, list):
            queries = [req.situation]
        queries = [q for q in queries if isinstance(q, str) and q.strip()][:MAX_QUERIES]
    except Exception as e:
        log(f"  expand failed: {e}, using raw situation")
        queries = [req.situation]
    log(f"  queries: {queries}")

    # 2b — Search IK across all queries, collect candidates
    log("step 2b: collecting candidates from IK")
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
                # Tier filter
                if court_info["tier"] == "OTHER":
                    continue
                if court_info["tier"] == "HC" and not req.include_hc:
                    continue
                candidates[doc_id] = {
                    **h,
                    "_court_info": court_info,
                }
                if len(candidates) >= MAX_CANDIDATES_TO_RANK:
                    break
        except Exception as e:
            log(f"  search failed for '{q}': {e}")
        if len(candidates) >= MAX_CANDIDATES_TO_RANK:
            break
    log(f"  collected {len(candidates)} candidates "
        f"(SC: {sum(1 for c in candidates.values() if c['_court_info']['tier']=='SC')}, "
        f"HC: {sum(1 for c in candidates.values() if c['_court_info']['tier']=='HC')})")

    if not candidates:
        return {
            "result": {
                "confidence": "low",
                "no_match_reason": "No Supreme Court or High Court criminal judgments found on Indian Kanoon for this situation. Try refining with specific statute sections.",
                "style": req.style,
                "cases": [],
            },
            "raw": "",
            "meta": {
                "elapsed_seconds": round(time.time() - t0, 2),
                "source": "ik_no_results",
                "model": SONNET_MODEL,
                "ik_judgments": 0,
                "cost_inr": cost_inr(usage_list),
            },
        }

    # 2c — Rank candidates, pick top 5
    log("step 2c: ranking candidates")
    cand_list = list(candidates.values())
    cand_summary = []
    for i, c in enumerate(cand_list):
        cand_summary.append({
            "index": i,
            "title": clean_html(c.get("title", "")),
            "court": c["_court_info"]["label"],
            "tier":  c["_court_info"]["tier"],
            "date":  c.get("publishdate", ""),
        })
    rank_user = (
        f"LAWYER'S SITUATION:\n{req.situation}\n\n"
        f"CANDIDATES (from Indian Kanoon, indexed 0-{len(cand_list)-1}):\n\n"
        f"{json.dumps(cand_summary, ensure_ascii=False)}\n\n"
        f"Rank by relevance. Return the top 5 indices (or fewer if fewer are genuinely on-point). JSON only."
    )
    try:
        raw, usage = call_claude(SONNET_MODEL, CANDIDATE_RANK_PROMPT, rank_user, max_tokens=400)
        usage_list.append(usage)
        rank = json.loads(strip_json_fences(raw))
        selected_indices = rank.get("selected_indices", [])[:TOP_K_TO_FETCH]
        log(f"  ranking picked indices: {selected_indices}")
        log(f"  ranking reasoning: {rank.get('reasoning', '')[:200]}")
    except Exception as e:
        log(f"  rank failed: {e}, using first 3")
        selected_indices = list(range(min(3, len(cand_list))))

    if not selected_indices:
        return {
            "result": {
                "confidence": "low",
                "no_match_reason": "Indian Kanoon returned candidates but none were directly relevant to this situation. Try refining your query with specific statute sections, leading case names, or doctrinal labels.",
                "style": req.style,
                "cases": [],
            },
            "raw": "",
            "meta": {
                "elapsed_seconds": round(time.time() - t0, 2),
                "source": "ik_no_relevant",
                "model": SONNET_MODEL,
                "ik_judgments": 0,
                "cost_inr": cost_inr(usage_list),
            },
        }

    # 2d — Fetch full text for selected
    log(f"step 2d: fetching full text for top {len(selected_indices)} candidates")
    judgments = []
    for idx in selected_indices:
        if idx < 0 or idx >= len(cand_list):
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
            text = text[:MAX_CHARS_PER_DOC] + "\n\n[...truncated...]"
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
        return {
            "result": {
                "confidence": "low",
                "no_match_reason": "Could not fetch judgment texts from Indian Kanoon. Try again.",
                "style": req.style,
                "cases": [],
            },
            "raw": "",
            "meta": {
                "elapsed_seconds": round(time.time() - t0, 2),
                "source": "ik_fetch_failed",
                "model": SONNET_MODEL,
                "ik_judgments": 0,
                "cost_inr": cost_inr(usage_list),
            },
        }

    # 2e — Generate structured output (with quality gate)
    log(f"step 2e: generating structured output for {len(judgments)} judgments")
    out_user = (
        f"LAWYER'S SITUATION:\n{req.situation}\n\n"
        f"STYLE: {req.style}\n\n"
        f"JUDGMENTS FETCHED FROM INDIAN KANOON:\n\n"
    )
    for j in judgments:
        out_user += (
            f"---\n"
            f"case_id: ik_{j['doc_id']}\n"
            f"title: {j['title']}\n"
            f"court: {j['court']}\n"
            f"court_tier: {j['court_tier']}\n"
            f"date: {j['date']}\n"
            f"url: {j['url']}\n\n"
            f"FULL JUDGMENT TEXT:\n{j['full_text']}\n\n"
        )
    out_user += (
        f"---\n\nProduce final JSON. Maximum 3 cases. QUALITY GATE: exclude any judgment that is not "
        f"directly on-point for this situation. Better to return 1-2 strong cases than 3 weak ones. "
        f"Return ONLY JSON."
    )

    system = SITUATION_OUTPUT_PROMPT.format(n=len(judgments))
    try:
        raw, usage = call_claude(SONNET_MODEL, system, out_user, max_tokens=4000)
        usage_list.append(usage)
    except Exception as e:
        raise HTTPException(502, f"LLM call failed: {e}")

    try:
        parsed = json.loads(strip_json_fences(raw))
    except json.JSONDecodeError as e:
        log(f"  output JSON parse failed: {e}")
        log(f"  raw start: {strip_json_fences(raw)[:500]}")
        raise HTTPException(502, f"Invalid JSON from model: {e}")

    if isinstance(parsed, dict) and "cases" in parsed:
        parsed["cases"] = parsed["cases"][:MAX_FINAL_CASES]
        for c in parsed["cases"]:
            if isinstance(c, dict):
                c["_quality"] = "ik_two_stage"
    parsed["_source"] = "ik_live"

    elapsed = round(time.time() - t0, 2)
    log(f"DONE (IK path) in {elapsed}s — returned {len(parsed.get('cases', []))} cases")

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


# ────────────────────────────────────────────────────────────────────
# /api/headnote — paste mode, Opus
# ────────────────────────────────────────────────────────────────────

@app.post("/api/headnote")
def api_headnote(req: HeadnoteReq):
    log(f"HEADNOTE: text_len={len(req.judgment_text)}")
    t0 = time.time()
    user_msg = f"JUDGMENT TEXT:\n{req.judgment_text[:30000]}\n\n---\nProduce headnote(s) per schema. JSON only."
    raw, usage = call_claude(OPUS_MODEL, HEADNOTE_SYSTEM_PROMPT, user_msg, max_tokens=4000)
    parsed = json.loads(strip_json_fences(raw))
    return {
        "result": parsed,
        "raw": raw,
        "meta": {
            "elapsed_seconds": round(time.time() - t0, 2),
            "model": OPUS_MODEL,
            "cost_inr": cost_inr([usage]),
        },
    }


# ────────────────────────────────────────────────────────────────────
# /api/translate, /api/feedback
# ────────────────────────────────────────────────────────────────────

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
        "INSERT INTO feedback (ts, mode, input_text, output_json, rating, correction, lawyer_handle) VALUES (?, ?, ?, ?, ?, ?, ?)",
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

log("Headnote v0.5.0-hybrid loaded")
log(f"  Curated corpus: {len(load_corpus())} cases")
log(f"  IK token prefix: {IK_TOKEN[:8]}...")
log(f"  Anthropic key set: {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
