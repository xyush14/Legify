"""Smart Drafter — conversational LLM-driven document composer.

This module powers the /api/draft/compose endpoint. The lawyer either picks
a template type ("vakalatnama", "anticipatory_bail", "quashing_petition",
…) or describes the matter and the system infers the type. From there:

  1. The conductor inspects which required fields are still empty.
  2. It picks the next field to ask about, in a natural lawyer-flow order.
  3. Sonnet generates a contextual question (in the user's language) that
     references prior answers — not a robotic form prompt.
  4. The lawyer answers (voice or text). Sonnet parses the answer into the
     structured field.
  5. When required fields are filled (or the lawyer hits "Draft Now"),
     Sonnet writes the full document using the template's format spec
     and few-shot examples.

State is held client-side: the FE passes `conversation` + `collected` on
each call. The backend is stateless. That's deliberate — keeps deployment
simple and matches the LocalStorage chat model we already use.

Cost: ~₹0.5 per question (Haiku) + ~₹6 per generation (Sonnet w/ thinking).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

log = logging.getLogger(__name__)


# ----------------------------------------------------------------- Templates
#
# Each entry declares:
#   id           — stable key used in URLs + API calls
#   name_en/hi   — display names for the picker
#   category     — bail | civil | writ | revision | family | misc
#   tier         — 1 (daily) | 2 (weekly) | 3 (situational)
#   description  — one-line for the picker tile
#   fields       — required + optional structured fields the conductor collects
#   format_spec  — the system prompt for the final generation step
#   example_prompts — sample lawyer phrasings the picker shows as hints
#
# Each `field` is { key, label_en, label_hi, type, required, hint }.
# type is one of: text | longtext | name | address | date | phone | section_list

TEMPLATES: dict[str, dict] = {

    # -------------------------------------------------------------- VAKALATNAMA
    "vakalatnama": {
        "id":         "vakalatnama",
        "name_en":    "Vakalatnama",
        "name_hi":    "वकालतनामा",
        "category":   "misc",
        "tier":       1,
        "description": "Authorisation for advocate to appear on behalf of the party. Required for every matter.",
        "fields": [
            {"key": "court_name",          "label_en": "Court name",                "label_hi": "न्यायालय का नाम",        "type": "text",      "required": True,  "hint": "e.g. 'Court of the Sessions Judge, Gwalior' or 'MP High Court, Gwalior Bench'"},
            {"key": "case_no",             "label_en": "Case / Crime number",       "label_hi": "केस / अपराध क्रमांक",   "type": "text",      "required": False, "hint": "If a case number is assigned"},
            {"key": "client_name",         "label_en": "Client (party) name",       "label_hi": "मुवक्किल का नाम",       "type": "name",      "required": True},
            {"key": "client_father",       "label_en": "Client father's name",      "label_hi": "मुवक्किल के पिता का नाम", "type": "name",      "required": True},
            {"key": "client_address",      "label_en": "Client address",            "label_hi": "मुवक्किल का पता",         "type": "address",   "required": True},
            {"key": "party_role",          "label_en": "Party role",                "label_hi": "पक्षकार की भूमिका",        "type": "text",      "required": True,  "hint": "applicant / petitioner / respondent / accused / plaintiff"},
            {"key": "opposite_party",      "label_en": "Opposite party",            "label_hi": "विपक्षी पक्ष",            "type": "text",      "required": False, "hint": "e.g. 'State of MP' for criminal matters"},
            {"key": "advocate_name",       "label_en": "Advocate name",             "label_hi": "अधिवक्ता का नाम",         "type": "name",      "required": True},
            {"key": "advocate_enrollment", "label_en": "Bar Council enrolment no.", "label_hi": "बार काउंसिल पंजीयन क्रमांक","type": "text",      "required": False, "hint": "e.g. 'MP/1234/2018'"},
            {"key": "advocate_address",    "label_en": "Advocate chamber address",  "label_hi": "अधिवक्ता का पता",          "type": "address",   "required": True},
            {"key": "place",               "label_en": "Place of execution",        "label_hi": "स्थान",                    "type": "text",      "required": True},
            {"key": "date",                "label_en": "Date",                      "label_hi": "दिनांक",                    "type": "date",      "required": True},
        ],
        "format_spec": (
            "Generate a standard Indian Vakalatnama on behalf of the client, in the "
            "language requested. Structure:\n"
            "  1. Heading: 'VAKALATNAMA' / 'वकालतनामा'\n"
            "  2. 'IN THE COURT OF …' / 'न्यायालय …' line\n"
            "  3. Case / Crime no. block (skip if none)\n"
            "  4. Parties: <Party Role> <Client Name>, s/o <Father>, r/o <Address>\n"
            "     Vs. <Opposite Party>\n"
            "  5. Standard appointment + authorisation paragraph (engage to appear, "
            "     plead, act, file documents, withdraw money, compromise as advised, etc.).\n"
            "  6. Acceptance line: 'Accepted, <Advocate Name>, Enrollment No. ___'\n"
            "  7. Signature blocks for client + advocate, with place + date.\n\n"
            "Use proper court Hindi if lang='hi' (vocabulary: माननीय न्यायालय, "
            "मुवक्किल, अधिवक्ता, हस्ताक्षर, etc.). Use formal English legal register "
            "if lang='en'. Do NOT add markdown — return plain text with line breaks."
        ),
        "example_prompts": [
            "मुझे ग्वालियर सेशन कोर्ट के लिए वकालतनामा चाहिए, मेरे मुवक्किल अनिल मोर्य के लिए",
            "Need a vakalatnama for my client Vivek Sharma in MP HC Gwalior bench",
        ],
    },

    # -------------------------------------------------------- ANTICIPATORY BAIL
    "anticipatory_bail": {
        "id":         "anticipatory_bail",
        "name_en":    "Anticipatory Bail (S.482 BNSS / S.438 CrPC)",
        "name_hi":    "अग्रिम जमानत आवेदन (धारा 482 BNSS / 438 दं.प्र.सं.)",
        "category":   "bail",
        "tier":       1,
        "description": "Pre-arrest bail application before Sessions / High Court.",
        "fields": [
            {"key": "court_name",          "label_en": "Court",                       "label_hi": "न्यायालय",                "type": "text",     "required": True,  "hint": "Sessions / HC bench"},
            {"key": "applicant_name",      "label_en": "Applicant name",              "label_hi": "आवेदक का नाम",            "type": "name",     "required": True},
            {"key": "applicant_father",    "label_en": "Father's name",               "label_hi": "पिता का नाम",             "type": "name",     "required": True},
            {"key": "applicant_age",       "label_en": "Age",                         "label_hi": "आयु",                     "type": "text",     "required": False},
            {"key": "applicant_occupation","label_en": "Occupation",                  "label_hi": "व्यवसाय",                 "type": "text",     "required": False},
            {"key": "applicant_address",   "label_en": "Address",                     "label_hi": "पता",                     "type": "address",  "required": True},
            {"key": "district",            "label_en": "District",                    "label_hi": "जिला",                    "type": "text",     "required": True},
            {"key": "state_name",          "label_en": "State",                       "label_hi": "राज्य",                   "type": "text",     "required": False},
            {"key": "fir_number",          "label_en": "FIR No.",                     "label_hi": "FIR क्रमांक",             "type": "text",     "required": True},
            {"key": "fir_date",            "label_en": "FIR date",                    "label_hi": "FIR दिनांक",              "type": "date",     "required": False},
            {"key": "police_station",      "label_en": "Police Station",              "label_hi": "पुलिस थाना",              "type": "text",     "required": True},
            {"key": "sections_str",        "label_en": "Sections invoked",            "label_hi": "धाराएं",                  "type": "section_list", "required": True, "hint": "e.g. '420 IPC, 406 IPC, 506 IPC'"},
            {"key": "apprehension_reason", "label_en": "Reason for apprehension",     "label_hi": "गिरफ्तारी की आशंका का कारण","type": "longtext", "required": True, "hint": "Why the applicant fears arrest"},
            {"key": "facts_narrative",     "label_en": "Brief facts / defence",       "label_hi": "तथ्य व बचाव",             "type": "longtext", "required": True},
            {"key": "advocate_name",       "label_en": "Advocate name",               "label_hi": "अधिवक्ता का नाम",          "type": "name",     "required": True},
            {"key": "place",               "label_en": "Place of filing",             "label_hi": "स्थान",                   "type": "text",     "required": True},
            {"key": "filing_date",         "label_en": "Filing date",                 "label_hi": "दिनांक",                  "type": "date",     "required": True},
        ],
        "format_spec": (
            "Generate a complete anticipatory bail application under Section 482 of "
            "the Bharatiya Nagarik Suraksha Sanhita, 2023 (or Section 438 CrPC for "
            "pre-Jul-2024 cases). Structure:\n"
            "  - Heading: Court name in formal style\n"
            "  - 'Application No. ___ of <year>' block (leave blank if none)\n"
            "  - Parties: Applicant (with full S/o + R/o details) Vs. State of <State>\n"
            "  - 'APPLICATION UNDER SECTION 482 BNSS, 2023 FOR ANTICIPATORY BAIL'\n"
            "  - 'The humble applicant most respectfully submits as follows:—'\n"
            "  - Numbered paragraphs (1 to N) covering: \n"
            "      1. This is the FIRST anticipatory bail application of the applicant under §482 BNSS in this Honourable Court.\n"
            "      2. No similar application was filed before this Hon'ble Court or before the Hon'ble Supreme Court of India.\n"
            "      3. Brief facts as alleged in the FIR.\n"
            "      4. The applicant has reasonable apprehension of arrest because…\n"
            "      5. Grounds for granting anticipatory bail (innocence, false implication, no flight risk, cooperation with investigation, etc.).\n"
            "      6. Applicant undertakes to cooperate with the investigation and abide by such conditions as the Hon'ble Court may impose.\n"
            "  - PRAYER: 'It is, therefore, most respectfully prayed that this Honourable Court may be pleased to grant anticipatory bail to the applicant in the event of his arrest in connection with FIR No. ___ / ___ registered at P.S. ___ under Sections ___ …'\n"
            "  - Signature blocks: Applicant + Through Counsel (name)\n"
            "  - Place + Date at bottom\n\n"
            "Use formal court Hindi (legal vocab: माननीय न्यायालय, आवेदक, सादर निवेदन, "
            "अग्रिम जमानत, सहयोग) if lang='hi'. Use formal Indian legal English if "
            "lang='en'. Return plain text — no markdown fences."
        ),
        "example_prompts": [
            "अग्रिम जमानत चाहिए, मुवक्किल विकेश शर्मा, धारा 420, FIR नंबर 95/2025, थाना मुरार",
            "Anticipatory bail for Anil Morya, S.420 IPC, FIR 95/2025 PS Murar Gwalior",
        ],
    },
}


def list_templates_slim() -> list[dict]:
    """Slim metadata for the FE picker."""
    return [
        {"id": t["id"], "name_en": t["name_en"], "name_hi": t["name_hi"],
         "category": t.get("category"), "tier": t.get("tier"),
         "description": t.get("description"),
         "example_prompts": t.get("example_prompts", [])}
        for t in TEMPLATES.values()
    ]


def get_template(doc_type: str) -> dict | None:
    return TEMPLATES.get(doc_type)


# ----------------------------------------------------------------- Conductor

def _missing_required(template: dict, collected: dict) -> list[dict]:
    """Return ordered list of required fields that haven't been collected yet."""
    out = []
    for f in template["fields"]:
        if not f.get("required"):
            continue
        v = collected.get(f["key"])
        if v is None or (isinstance(v, str) and not v.strip()):
            out.append(f)
    return out


def _next_field(template: dict, collected: dict) -> dict | None:
    """Pick the next field to ask about. v1 = first missing required, in
    declared order. Future: branch on prior answers (e.g. skip "current
    jail" if anticipatory bail)."""
    miss = _missing_required(template, collected)
    return miss[0] if miss else None


def _llm_call(system: str, user: str, *, max_tokens: int = 1200, model: str = "fast") -> str:
    """Single dispatch for all LLM calls in the conductor.

    Backend priority:
      1. Groq (free, fast)  — preferred for both Q-asking and document gen
      2. Anthropic Claude   — fallback if GROQ_API_KEY not set

    `model='fast'` → Groq llama-3.1-8b-instant / Haiku  (question generation)
    `model='quality'` → Groq llama-3.3-70b-versatile / Sonnet  (document drafting)
    """
    import os
    if os.environ.get("GROQ_API_KEY"):
        from groq import Groq
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        m = (
            os.environ.get("GROQ_TEXT_FAST", "llama-3.1-8b-instant")
            if model == "fast" else
            os.environ.get("GROQ_TEXT_QUALITY", "llama-3.3-70b-versatile")
        )
        try:
            resp = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=0.2 if model == "quality" else 0.4,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            log.warning("Groq %s failed (%s); trying Anthropic", m, e)

    # Anthropic fallback
    from headnote.llm.client import call_claude_cached
    anthr_model = "claude-haiku-4-5" if model == "fast" else "claude-sonnet-4-6"
    text, _ = call_claude_cached(
        system_prompt=system, user_prompt=user,
        model=anthr_model, max_tokens=max_tokens, cache=False,
    )
    return text


def conductor_step(
    doc_type: str,
    conversation: list[dict],
    collected: dict,
    user_message: str | None = None,
    lang: str = "hi",
    force_draft: bool = False,
) -> dict:
    """Run one step of the conversational drafter.

    Inputs
    ------
    doc_type      : key into TEMPLATES (e.g. 'vakalatnama')
    conversation  : list of {role, content} from the chat so far (excluding
                    the latest user_message, which is handled separately)
    collected     : dict of fields gathered so far
    user_message  : the lawyer's latest utterance (text or voice transcript).
                    If None, this is the "start" call — assistant asks first
                    question.
    lang          : 'hi' | 'en'
    force_draft   : if True, generate the draft now even if some fields
                    are missing (lawyer hit "Draft now")

    Returns
    -------
    {
      status:         'asking' | 'ready',
      collected:      updated dict (any fields parsed from user_message),
      next_question?: str (when asking),
      next_field?:    str (the key the question is targeting),
      document?:      str (the generated draft, when ready),
      missing?:       list of field labels still missing (when ready w/ gaps),
    }
    """
    template = get_template(doc_type)
    if not template:
        raise ValueError(f"unknown doc_type '{doc_type}'")

    # ── 1. If the lawyer just answered, parse their reply into the
    #       structured `collected` dict via Haiku.
    if user_message and user_message.strip():
        last_question = None
        last_field = None
        for msg in reversed(conversation):
            if msg.get("role") == "assistant" and msg.get("field_key"):
                last_question = msg.get("content")
                last_field    = msg.get("field_key")
                break
        if last_field:
            collected = dict(collected)  # copy
            try:
                collected = _parse_answer(template, last_field, last_question,
                                          user_message, collected, lang)
            except Exception as e:
                log.warning("Answer parse failed (%s); storing raw", e)
                collected[last_field] = user_message.strip()

    # ── 2. If lawyer pressed "Draft Now" OR all required fields are filled,
    #       generate the document.
    missing = _missing_required(template, collected)
    if force_draft or not missing:
        try:
            doc = _generate_document(template, collected, lang)
            return {
                "status":   "ready",
                "collected": collected,
                "document": doc,
                "missing":  [f["label_en"] for f in missing],
            }
        except Exception as e:
            raise RuntimeError(f"draft generation failed: {e}")

    # ── 3. Otherwise, ask the next question.
    nf = _next_field(template, collected)
    question = _ask_question(template, nf, collected, lang)
    return {
        "status":        "asking",
        "collected":     collected,
        "next_question": question,
        "next_field":    nf["key"],
    }


# ─────────────────────────────────────────────────────────────── helpers

def _ask_question(template: dict, field: dict, collected: dict, lang: str) -> str:
    """Generate a contextual, natural question for the lawyer.

    The conductor doesn't just print 'Enter <field>?' — it phrases the
    question with reference to previously-collected context. E.g. after
    the lawyer says the client is 'Anil Morya', the next question becomes
    'And what's Anil's father's name?' not 'Enter applicant_father:'.
    """
    label = field["label_hi"] if lang == "hi" else field["label_en"]
    ftype = field.get("type", "text")
    hint  = field.get("hint", "")

    # For very short / boilerplate fields (date, place), skip the LLM and
    # just emit a fixed phrasing — saves a call.
    if ftype in {"date"}:
        return ("दिनांक क्या है?" if lang == "hi" else "What's the date?")
    if field["key"] == "place":
        return ("किस स्थान पर दाखिल कर रहे हैं?" if lang == "hi" else "Place of filing?")

    sys = (
        "You are a senior Indian criminal lawyer helping a junior draft a "
        f"{template['name_en']}. Ask the next question in a natural, "
        "conversational tone. Reference any context the junior has already "
        "given. Return ONLY the question — no preamble, no markdown."
    )
    if lang == "hi":
        sys += " Reply in formal-friendly legal Hindi (Devanagari)."
    else:
        sys += " Reply in clear professional Indian English."

    ctx_lines = []
    for k, v in collected.items():
        if not v:
            continue
        ctx_lines.append(f"- {k}: {v}")
    ctx = "\n".join(ctx_lines) or "(nothing collected yet)"

    user = (
        f"Context collected so far:\n{ctx}\n\n"
        f"Next field to fill: {label} ({field['key']}, type={ftype})\n"
        f"{('Hint: ' + hint) if hint else ''}\n\n"
        f"Ask the lawyer for this field in one short sentence."
    )

    try:
        text = _llm_call(sys, user, max_tokens=120, model="fast")
        return text.strip().strip('"').strip()
    except Exception as e:
        log.warning("ask_question LLM failed (%s); falling back to label", e)
        return (f"{label} क्या है?" if lang == "hi" else f"What is the {label.lower()}?")


def _parse_answer(template: dict, field_key: str, question: str | None,
                  answer: str, collected: dict, lang: str) -> dict:
    """Extract the structured value from the lawyer's free-form answer.

    Most answers are simple ('Anil Morya') and can be stored directly.
    But voice answers often contain noise ('um, the name is Anil Morya'
    or 'मेरे क्लाइंट का नाम है अनिल मोर्य') — the LLM extracts the clean value.
    """
    field = next((f for f in template["fields"] if f["key"] == field_key), None)
    if not field:
        collected[field_key] = answer.strip()
        return collected

    # Cheap path — single short answer, no need to invoke the LLM
    a = answer.strip()
    if len(a) < 80 and not re.search(r"[।.?!,]", a) and field.get("type") in {"text", "name", "date", "phone"}:
        collected[field_key] = a
        return collected

    sys = (
        "You extract a single structured value from a lawyer's spoken or typed "
        "answer to a question, and return it as JSON. Discard filler words, "
        "honorifics, and lead-ins. Preserve names in their original script."
    )
    schema = (
        f'{{"value": "<clean value for {field_key} ({field["type"]})>"}}'
    )
    user = (
        f"Question asked: {question or field.get('label_en')}\n"
        f"Field type:     {field['type']}\n"
        f"Lawyer answer:  {answer}\n\n"
        f"Return ONLY this JSON: {schema}"
    )
    try:
        text = _llm_call(sys, user, max_tokens=200, model="fast")
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        obj = json.loads(text)
        v = obj.get("value")
        if v is not None:
            collected[field_key] = str(v).strip()
        else:
            collected[field_key] = answer.strip()
    except Exception as e:
        log.warning("parse_answer failed (%s); storing raw", e)
        collected[field_key] = answer.strip()
    return collected


def _generate_document(template: dict, collected: dict, lang: str) -> str:
    """Generate the final document using the high-quality LLM + format_spec."""
    lang_clause = (
        "The document must be entirely in formal court Hindi (Devanagari). "
        "Names and places stay in Devanagari."
        if lang == "hi" else
        "The document must be entirely in formal Indian legal English."
    )

    sys = (
        f"You are a senior Indian criminal lawyer drafting a "
        f"{template['name_en']}. {lang_clause}\n\n"
        f"FORMAT SPEC:\n{template['format_spec']}\n\n"
        "Return the document as PLAIN TEXT. Use double newlines between "
        "paragraphs. No markdown fences. No commentary."
    )
    fields_dump = "\n".join(
        f"- {f['label_en']} ({f['key']}): {collected.get(f['key']) or '[BLANK]'}"
        for f in template["fields"]
    )
    user = (
        f"Use these collected field values:\n\n{fields_dump}\n\n"
        f"Generate the complete {template['name_en']} now."
    )

    text = _llm_call(sys, user, max_tokens=4000, model="quality")
    return text.strip()
