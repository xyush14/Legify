"""Transcript → structured legal work-product report.

The recorder captures a lawyer–client conversation, Groq Whisper transcribes it,
and this module turns that raw transcript into the structured consultation
memorandum the UI renders: matter header, parties, chronology, key facts, key
admissions / risk flags, legal issues, applicable provisions, documents,
action items with deadlines, open questions, key quotes, and the
"confirm before pleading" guardrail — plus a draft-handoff prompt.

Design rules (carry the drafter's discipline):
  • ZERO fabrication. Every fact/quote must trace to something actually said in
    the transcript. Anything vague — an amount, a date, an opponent's income
    "he thinks is around ₹1.2L" — goes into `unverified` (grounded=False),
    never asserted as fact.
  • Two sections cross from transcription into inference and are held to strict
    rules: `key_admissions` (risk flags) derive ONLY from facts the client
    actually stated; `provisions` are labelled "discussed" (named in the
    conversation) vs "to_research" (governing but not named) — a citation to a
    JUDGMENT is never invented under any label.
  • Empty sections are dropped, not padded — a thin consult yields a short
    honest report.
  • The report is written in the conversation's own language (Hindi stays
    Hindi); only the JSON keys are English. `key_quotes` are copied verbatim.

The LLM call goes DeepSeek V3 (deepseek-chat) first, Groq Llama as the free
fallback — never Claude — per the house cost preference. If both fail we still
return a minimal transcript-only report so the flow never dies.
"""

from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


# doc_type → human label used for the handoff button. Keys align with the
# drafter's classifier vocab (headnote/drafter/from_prompt.py _VOCAB) so the
# generated prompt lands on the right template.
_DRAFT_LABELS = {
    "bail": "bail application",
    "anticipatory_bail": "anticipatory bail",
    "maintenance": "maintenance petition",
    "dv": "domestic violence complaint",
    "divorce_13": "divorce petition",
    "restitution_9": "restitution petition",
    "cheque_138": "§138 NI complaint",
    "recovery_suit": "recovery suit",
    "injunction_suit": "injunction suit",
    "eviction_suit": "eviction suit",
    "consumer_complaint": "consumer complaint",
    "legal_notice": "legal notice",
    "mact_166": "MACT claim",
    "quashing": "quashing petition",
    "complaint_156": "§156(3) complaint",
    "other_civil": "civil petition",
    "other_criminal": "criminal application",
}


REPORT_SYSTEM = """You are a senior Indian litigation associate preparing a \
CONSULTATION MEMORANDUM after a lawyer met a client. You are given the raw \
transcript of that conversation (often Hindi or Hinglish, from speech-to-text \
so it may have small errors; lines may be prefixed with a [mm:ss] timestamp). \
Turn it into a structured, partner-ready intake memo.

Output ONLY valid JSON (no markdown fence) with EXACTLY these keys:
{
  "title":        string  — short matter title, e.g. "Sunita Verma vs Rakesh Verma",
  "matter_type":  string  — ONE of: bail, anticipatory_bail, maintenance, dv, divorce_13, restitution_9, cheque_138, recovery_suit, injunction_suit, eviction_suit, consumer_complaint, legal_notice, mact_166, quashing, complaint_156, other_civil, other_criminal,
  "matter_label": string  — human label incl. the governing provision if clearly stated, e.g. "Maintenance under §144 BNSS", else "",
  "court":        string  — court/forum if named, else "",
  "stage":        string  — e.g. pre-filing, notice issued, trial, appeal — if inferable, else "",
  "relief_sought":string  — the concrete relief/amount the client wants, else "",
  "urgency":      string  — short note if time-sensitive (e.g. "interim relief needed"), else "",
  "limitation_note": string — any limitation/deadline concern raised or evident, else "",
  "client_role":  string  — applicant | accused | complainant | petitioner | respondent | "",
  "parties": {
     "client":   { "name": string, "role": string, "detail": string (age/occupation/address/contact as stated, else "") },
     "opponent": { "name": string, "role": string, "detail": string },
     "others":   [ string ]  — other named persons (witnesses, co-accused, guarantor…)
  },
  "summary":   string  — 2-3 sentence plain-language overview,
  "chronology":[ { "date": string, "text": string, "grounded": boolean } ]  — DATED events, oldest first,
  "facts":     [ { "text": string, "grounded": boolean } ]  — key facts with NO clear date,
  "key_admissions": [ string ]  — facts the CLIENT stated that could HURT their own case or that the opponent could exploit; derive ONLY from what was said; [] if none,
  "issues":    [ string ]  — the legal questions a lawyer must resolve,
  "provisions":[ { "ref": string, "status": "discussed" | "to_research" } ]  — statutes/sections in play,
  "documents": { "on_record": [ string ], "to_collect": [ string ] },
  "action_items": [ { "text": string, "deadline": string (else "") } ],
  "open_questions": [ string ]  — gaps to close at the next meeting,
  "key_quotes":[ { "text": string, "time": string (mm:ss if a timestamp is near that line, else "") } ]  — 1-4 SHORT verbatim quotes,
  "unverified":[ string ]  — every claim that was vague, assumed, or needs proof before it can be pleaded
}

HARD RULES — follow exactly:
- Ground everything. A chronology/fact entry gets grounded=true ONLY if clearly \
stated. If a date/amount/name was fuzzy ("around", "maybe", "I think", "he \
said"), set grounded=false AND add a line to "unverified" naming what to confirm.
- key_admissions: ONLY adverse facts the client actually volunteered (e.g. "left \
home voluntarily", "no FIR lodged", "is qualified/employable"). Never invent a \
weakness that wasn't grounded in something said.
- provisions: status="discussed" ONLY if that section/Act was named aloud. A \
provision that plainly governs but was NOT named may be included as \
status="to_research". NEVER invent a case-law citation or judgment name under \
any status.
- key_quotes: copy the words EXACTLY as transcribed (do not clean up). Keep each \
under ~25 words. Prefer the client's core grievance and any pivotal admission. \
Use the nearest [mm:ss] marker as "time"; if none, "".
- NEVER fabricate parties, courts, dates, amounts, or documents. Empty string / \
empty array over a guess.
- Write all prose (summary/facts/issues/admissions/steps/questions) in the SAME \
language as the conversation (keep Hindi in Hindi). Keys stay English.
- REGISTER: write as an Indian advocate drafting a file note — कानूनी हिंदी, not \
casual speech. Refer to the lawyer's own client as «मुवक्किल» (or by procedural \
role: प्रार्थी / आवेदक / अभियुक्त / परिवादी / याचिकाकर्ता as the matter fits) — \
NEVER «ग्राहक» (that means a shop customer and is wrong for a client). Use the \
opponent's role too (राज्य/अभियोजन, प्रत्यर्थी, विपक्षी). Use correct legal terms \
(प्राथमिकी/FIR, आरोप-पत्र, जमानत, उन्मोचन, गुज़ारा-भत्ता, क्रूरता) and precise \
section names (e.g. "धारा 125 दं.प्र.सं." / "धारा 144 BNSS"). Keep it crisp and \
professional — no filler, no repetition.
- If a section has nothing real to say, return it EMPTY ([] or "") — do not pad.
- If the transcript is too short/unclear to build a real memo, still return the \
JSON with best-effort fields and note it in "unverified".
Return JSON only."""


def _norm_list(v) -> list:
    if isinstance(v, list):
        return v
    if v in (None, ""):
        return []
    return [v]


def _s(v) -> str:
    return (v or "").strip() if isinstance(v, str) else ("" if v is None else str(v).strip())


def _party(p) -> dict:
    p = p if isinstance(p, dict) else {}
    return {"name": _s(p.get("name")), "role": _s(p.get("role")), "detail": _s(p.get("detail"))}


def _normalize(report: dict, transcript: str) -> dict:
    """Defensive shaping so the UI always gets the keys/types it expects."""
    r = dict(report or {})
    r["title"] = _s(r.get("title")) or "Untitled consultation"
    mt = _s(r.get("matter_type"))
    if mt not in _DRAFT_LABELS:
        mt = "other_civil"
    r["matter_type"] = mt
    for k in ("matter_label", "court", "stage", "relief_sought", "urgency",
              "limitation_note", "client_role", "summary"):
        r[k] = _s(r.get(k))

    par = r.get("parties") if isinstance(r.get("parties"), dict) else {}
    r["parties"] = {
        "client": _party(par.get("client")),
        "opponent": _party(par.get("opponent")),
        "others": [_s(x) for x in _norm_list(par.get("others")) if _s(x)],
    }

    chrono = []
    for f in _norm_list(r.get("chronology")):
        if isinstance(f, dict) and _s(f.get("text")):
            chrono.append({"date": _s(f.get("date")), "text": _s(f.get("text")),
                           "grounded": bool(f.get("grounded", True))})
        elif isinstance(f, str) and f.strip():
            chrono.append({"date": "", "text": f.strip(), "grounded": True})
    r["chronology"] = chrono

    facts = []
    for f in _norm_list(r.get("facts")):
        if isinstance(f, dict) and _s(f.get("text")):
            facts.append({"text": _s(f.get("text")), "grounded": bool(f.get("grounded", True))})
        elif isinstance(f, str) and f.strip():
            facts.append({"text": f.strip(), "grounded": True})
    r["facts"] = facts

    r["key_admissions"] = [_s(x) for x in _norm_list(r.get("key_admissions")) if _s(x)]
    r["issues"] = [_s(x) for x in _norm_list(r.get("issues")) if _s(x)]
    r["open_questions"] = [_s(x) for x in _norm_list(r.get("open_questions")) if _s(x)]
    r["unverified"] = [_s(x) for x in _norm_list(r.get("unverified")) if _s(x)]

    provs = []
    for p in _norm_list(r.get("provisions")):
        if isinstance(p, dict) and _s(p.get("ref")):
            status = _s(p.get("status")).lower()
            provs.append({"ref": _s(p.get("ref")),
                          "status": "discussed" if status == "discussed" else "to_research"})
        elif isinstance(p, str) and p.strip():
            provs.append({"ref": p.strip(), "status": "to_research"})
    r["provisions"] = provs

    docs = r.get("documents") if isinstance(r.get("documents"), dict) else {}
    r["documents"] = {
        "on_record": [_s(x) for x in _norm_list(docs.get("on_record")) if _s(x)],
        "to_collect": [_s(x) for x in _norm_list(docs.get("to_collect")) if _s(x)],
    }

    items = []
    for a in _norm_list(r.get("action_items")):
        if isinstance(a, dict) and _s(a.get("text")):
            items.append({"text": _s(a.get("text")), "deadline": _s(a.get("deadline"))})
        elif isinstance(a, str) and a.strip():
            items.append({"text": a.strip(), "deadline": ""})
    r["action_items"] = items

    quotes = []
    for q in _norm_list(r.get("key_quotes")):
        if isinstance(q, dict) and _s(q.get("text")):
            quotes.append({"text": _s(q.get("text")), "time": _s(q.get("time"))})
        elif isinstance(q, str) and q.strip():
            quotes.append({"text": q.strip(), "time": ""})
    r["key_quotes"] = quotes

    r["suggested_draft"] = _build_handoff(r)
    return r


def _build_handoff(r: dict) -> dict:
    """Assemble the draft-handoff: which drafter type + a grounded seed prompt.

    The prompt carries ONLY grounded facts + relief. It tells the drafter to
    leave blanks (____) for anything missing rather than invent — same rule
    the drafter itself enforces."""
    dt = r["matter_type"]
    label = _DRAFT_LABELS.get(dt, "petition")

    lines = []
    if r.get("relief_sought"):
        lines.append(f"Relief sought: {r['relief_sought']}.")
    for f in r.get("chronology", []):
        if f.get("grounded") and f.get("text"):
            prefix = f"{f['date']}: " if f.get("date") else ""
            lines.append(prefix + f["text"])
    for f in r.get("facts", []):
        if f.get("grounded") and f.get("text"):
            lines.append(f["text"])

    body = "\n".join(f"- {ln}" for ln in lines) if lines else "(facts to be confirmed with the client)"
    court = f" for filing in {r['court']}" if r.get("court") else ""
    prompt = (
        f"Draft a {label}{court} based on this client consultation. "
        f"Use only these confirmed facts; leave a blank (____) for anything not stated — do not invent:\n{body}"
    )
    return {"doc_type": dt, "label": label, "prompt": prompt}


def _fallback_report(transcript: str, reason: str) -> dict:
    """Minimal report when the LLM is unavailable — keeps the flow alive."""
    snippet = (transcript or "").strip()
    summary = (snippet[:280] + "…") if len(snippet) > 280 else snippet
    return _normalize({
        "title": "Consultation " + (snippet[:40].strip() or "note"),
        "matter_type": "other_civil",
        "summary": summary or "Transcript captured; structured report unavailable.",
        "action_items": ["Review the full transcript and structure the matter manually."],
        "unverified": [f"Automatic report generation failed ({reason}); read the transcript."],
    }, transcript)


def build_report(transcript: str, *, lang: str = "hi", hint: str = "",
                 timestamped: str = "") -> dict:
    """Turn a consultation transcript into the structured report dict.

    `timestamped`, when provided, is the transcript with [mm:ss] line markers
    (built from Whisper segments) — passed to the model so key_quotes can carry
    a timestamp. Falls back to the plain transcript."""
    transcript = (transcript or "").strip()
    if not transcript:
        return _fallback_report("", "empty transcript")

    # DeepSeek V3 primary, Groq Llama free fallback — never Claude (house cost
    # rule). Same call shape as from_prompt.classify(). claude_model is just the
    # tier hint the router maps to deepseek-chat (V3, fast/cheap — right for
    # structured extraction; R1 would be slow and overkill).
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response

    source = (timestamped or "").strip() or transcript
    user = source
    if hint:
        user = f"Context from the lawyer: {hint}\n\n--- TRANSCRIPT ---\n{source}"

    try:
        raw, _meta = _call_deepseek_or_groq(
            REPORT_SYSTEM, user,
            max_tokens=3000,
            claude_model="claude-haiku-4-5",
        )
        parsed = parse_json_response(raw)
        return _normalize(parsed, transcript)
    except Exception as e:  # noqa: BLE001 — never let report gen kill the flow
        log.warning("consultation report generation failed: %s", e)
        return _fallback_report(transcript, str(e)[:120])
