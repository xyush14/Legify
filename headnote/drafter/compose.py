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
# Template scaffolds live in compose_templates.py so we can add new document
# types without touching the conductor logic in this file. Re-export the
# helpers here so existing imports of compose.{TEMPLATES, get_template,
# list_templates_slim} keep working.

from headnote.drafter.compose_templates import (  # noqa: E402
    TEMPLATES,
    get_template,
    list_templates_slim,
    list_templates_by_court,
)



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
    """Single dispatch for all drafter LLM calls (question-asking, answer
    parsing, document generation, field translation, prose polish).

    Routes to DeepSeek V3 (deepseek-chat) with Groq llama as last-resort
    fallback, via the shared client in headnote.llm.client. We deliberately
    do NOT use Groq llama-3.3-70b as the PRIMARY drafter anymore: it ignored
    the Hindi format_spec (re-introducing the forbidden 'गैर-न्यायिक स्टांप
    पेपर' / 'समक्ष' lines on the affidavit) and leaked English structural
    words (e.g. 'VERIFICATION') into otherwise-Devanagari output. That weak
    model — not the spec — was the root cause of the broken, wrong-format,
    half-translated drafts.

    Why V3 (deepseek-chat) and not R1 (deepseek-reasoner): the template
    drafter regenerates the WHOLE document on every debounced edit (live
    preview). R1's chain-of-thought runs 60-180s — unusable for that. V3 is
    5-15s and follows the spec cleanly. Claude is intentionally not used here
    (cost); if DeepSeek is unconfigured/down, _call_deepseek_or_groq degrades
    to Groq llama rather than erroring.

    `model='fast'`    → cheap calls (ask question, parse answer)
    `model='quality'` → document generation / field translation
    Both currently map to V3; the knob is kept for future routing.
    """
    from headnote.llm.client import _call_deepseek_or_groq
    # claude_model picks the DeepSeek tier: 'claude-haiku-4-5' → deepseek-chat
    # (V3). _call_deepseek_or_groq tries DeepSeek first, then Groq llama.
    text, _ = _call_deepseek_or_groq(
        system, user,
        max_tokens=max_tokens,
        claude_model="claude-haiku-4-5",
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
    the lawyer says the client is 'Anil Verma', the next question becomes
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

    Most answers are simple ('Anil Verma') and can be stored directly.
    But voice answers often contain noise ('um, the name is Anil Verma'
    or 'मेरे क्लाइंट का नाम है अनिल वर्मा') — the LLM extracts the clean value.
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


def _strip_llm_wrapping(text: str) -> str:
    """Remove wrapping artifacts the model occasionally adds despite the
    prompt forbidding them: a ```code fence``` around the whole document, and
    a single leading English chit-chat preamble line ('Here is the draft:',
    'Sure,', 'Below is ...', 'I have drafted ...').

    Deliberately conservative. A real court document opens with the court name
    (Hindi) or 'IN THE COURT OF ...' (English) — never with these phrases — so
    stripping them is safe. We do NOT strip Hindi leading lines, because a
    legitimate intro like 'प्रार्थी की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है :-'
    would be a false positive. Body text is never touched.
    """
    if not text:
        return text
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:[a-z]+)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    t = re.sub(
        r"^(?:sure|certainly|of course|here(?:'s| is)|below is|"
        r"i have (?:drafted|prepared|created))\b[^\n]*\n+",
        "", t, count=1, flags=re.IGNORECASE,
    ).strip()
    return t


def _generate_document(template: dict, collected: dict, lang: str) -> str:
    """Generate the final document using the high-quality LLM + format_spec."""
    if lang == "hi":
        lang_clause = (
            "OUTPUT LANGUAGE — HINDI (DEVANAGARI). THIS OVERRIDES THE FORMAT "
            "SPEC.\n"
            "The ENTIRE document must be written in formal court Hindi in the "
            "Devanagari script — the court name, the case-number line, every "
            "party block, the title, every numbered paragraph, every heading, "
            "the prayer, the witness list, the date line and the signature "
            "block. There must be ZERO English words or Latin-script "
            "structural text anywhere.\n"
            "If the FORMAT SPEC below quotes any English (for example 'IN THE "
            "COURT OF ...', 'COMPLAINT UNDER SECTION ...', 'PRAYER', "
            "'VERIFICATION', 'That ...'), treat that English ONLY as a "
            "structural reference telling you WHAT the line is — you MUST "
            "render its proper Hindi equivalent and NEVER copy the English "
            "verbatim. For instance write 'परिवाद पत्र अन्तर्गत धारा 138 "
            "परक्राम्य लिखित अधिनियम', NOT 'COMPLAINT UNDER SECTION 138'.\n"
            "The ONLY things allowed in Latin letters / Arabic numerals are "
            "bare statute numbers (e.g. धारा 138), cheque or account numbers, "
            "and monetary figures. Proper names and place names stay in "
            "Devanagari."
        )
    else:
        lang_clause = (
            "OUTPUT LANGUAGE — ENGLISH. THIS OVERRIDES THE FORMAT SPEC.\n"
            "The ENTIRE document must be written in formal Indian legal "
            "English in the Latin script — the court name, the case-number "
            "line, every party block, the title, every numbered paragraph, "
            "every heading, the prayer, the witness list, the date line and "
            "the signature block. There must be ZERO Hindi / Devanagari words "
            "anywhere in the output.\n"
            "The FORMAT SPEC below is written in Hindi (Devanagari). Treat it "
            "ONLY as a structural reference telling you WHAT each line is and "
            "in WHAT ORDER they appear — you MUST render every line in its "
            "proper English equivalent and NEVER copy the Hindi verbatim. "
            "For example: 'न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी' "
            "-> \"IN THE COURT OF THE HON'BLE JUDICIAL MAGISTRATE FIRST "
            "CLASS\"; 'आवेदन पत्र अन्तर्गत धारा 12 घरेलू हिंसा से महिलाओं का "
            "संरक्षण अधिनियम 2005' -> 'APPLICATION UNDER SECTION 12 OF THE "
            "PROTECTION OF WOMEN FROM DOMESTIC VIOLENCE ACT, 2005'; 'प्रकरण "
            "क्रमांक' -> 'Case No.'; 'बनाम' -> 'VERSUS'; 'व्यथिता' / 'व्यथित' "
            "-> 'Aggrieved Person'; 'प्रत्यर्थी' / 'प्रत्यर्थीगण' -> "
            "'Respondent(s)'; 'निवासी' -> 'resident of'.\n"
            "Transliterate proper names and place names into the Latin script "
            "(e.g. 'अनिल वर्मा' -> 'Anil Verma', 'ग्वालियर' -> 'Gwalior'). "
            "The output must be pure English — do NOT emit a single "
            "Devanagari character."
        )

    title_clause = (
        "Output the document title as a plain Hindi line in Devanagari (for "
        "example 'याचिका अन्तर्गत धारा 9 हिन्दू विवाह अधिनियम, 1955') — the "
        "frontend automatically renders it centred + underlined + bold from "
        "the CSS. Never wrap the title in markup and never force Latin "
        "uppercase or English."
        if lang == "hi" else
        "Output PLAIN UPPERCASE for titles (e.g. 'PETITION UNDER S.9 OF THE "
        "HINDU MARRIAGE ACT, 1955') — the frontend automatically renders "
        "centred + underlined + bold styling from the CSS. Never wrap titles "
        "in markup."
    )

    sys = (
        f"You are a senior Indian criminal lawyer drafting a "
        f"{template['name_en']}. {lang_clause}\n\n"
        "FIELD VALUES MAY BE IN EITHER LANGUAGE — CONVERT THEM:\n"
        "The collected values further below may have been typed in English, "
        "Hindi, or a mix. Render EVERY value in the output language defined "
        "above; never copy a value verbatim when it is in the other language. "
        "Transliterate proper names and place names phonetically into the "
        "target script (e.g. 'Anil Verma' <-> 'अनिल वर्मा', 'Lucknow' <-> "
        "'लखनऊ'); translate occupations, court names, designations and all "
        "prose using standard Indian legal vocabulary. Keep statute numbers, "
        "FIR/case/cheque/account numbers, dates and monetary figures exactly "
        "as given.\n\n"
        f"FORMAT SPEC:\n{template['format_spec']}\n\n"
        "CRITICAL RULE — BLANK FIELDS:\n"
        "If a field's value is '[BLANK]' or empty, you MUST NOT invent a "
        "value. Use an underline placeholder (e.g. '_________________' for "
        "names, '____/____' for case numbers, '__.__.____' for dates) so "
        "the lawyer can fill it in later by hand. Never substitute fake "
        "names, addresses, dates, or sections.\n\n"
        "Return the document as PLAIN TEXT. Use double newlines between "
        "paragraphs. No markdown fences. No commentary.\n\n"
        "ABSOLUTELY DO NOT use any of these markup tokens — they will appear "
        "as literal text on the page and look unprofessional:\n"
        "  - HTML tags: <u>, <b>, <i>, <em>, <strong>\n"
        "  - Markdown: **bold**, _italic_, *emphasis*, # headings\n"
        f"{title_clause}"
    )
    fields_dump = "\n".join(
        f"- {f['label_en']} ({f['key']}): {collected.get(f['key']) or '[BLANK]'}"
        for f in template["fields"]
    )
    user = (
        f"Use these collected field values:\n\n{fields_dump}\n\n"
        f"Generate the complete {template['name_en']} now. "
        f"Remember — any [BLANK] value MUST be rendered as an underline "
        f"placeholder, never invented."
    )

    text = _llm_call(sys, user, max_tokens=4000, model="quality").strip()
    text = _strip_llm_wrapping(text)

    # GUARANTEE the language toggle. When English is requested but the model
    # leaned on the Hindi format_spec and produced Devanagari anyway, convert
    # it in ONE more pass. This is bounded to a single extra call and only on
    # the failure path, so cost/latency stay predictable. The Hindi direction
    # is never second-guessed here — only EN was historically under-instructed.
    if lang != "hi" and _devanagari_count(text) > 12:
        try:
            converted = _force_english(text)
            if converted and _devanagari_count(converted) < _devanagari_count(text):
                text = converted
        except Exception:  # never fail the whole render over the safety net
            log.warning("[render] force-English retry failed; keeping first pass")
    return text


_DEVANAGARI_RE = re.compile("[ऀ-ॿ]")


def _devanagari_count(s: str) -> int:
    """Number of Devanagari code points in `s` (0 for clean English output)."""
    return len(_DEVANAGARI_RE.findall(s or ""))


def _force_english(hindi_doc: str) -> str:
    """Convert a document that came back in Hindi into formal English while
    preserving its exact structure, paragraph order and '____' blanks. Used as
    a fallback so the EN toggle always yields English, even if the first
    generation ignored the language instruction."""
    sys = (
        "You are a senior Indian lawyer. The text below is a court document "
        "that was mistakenly produced in Hindi/Devanagari. Rewrite it in 100% "
        "formal Indian legal English in the Latin script.\n"
        "RULES:\n"
        "1. Output ZERO Devanagari characters — translate every Hindi word and "
        "transliterate every proper name / place name into the Latin script.\n"
        "2. Preserve the document's structure EXACTLY: same line/paragraph "
        "order, same headings, same numbered paragraphs.\n"
        "3. Keep every blank placeholder (runs of underscores like "
        "'________' or '____/____') EXACTLY as-is — do NOT fill them in.\n"
        "4. Keep statute numbers, case/FIR numbers, dates and monetary figures "
        "unchanged.\n"
        "5. Return PLAIN TEXT only — no markdown, no commentary, no fences."
    )
    user = "Convert this document to English now:\n\n" + hindi_doc
    return _strip_llm_wrapping(_llm_call(sys, user, max_tokens=4000, model="quality"))
