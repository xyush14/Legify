"""FIR photo/PDF OCR + structured extraction via Claude vision.

The Indian FIR is a near-universally standard document: the NCRB I.I.F.-I
(Integrated Investigation Form-I) printed under Section 154 CrPC. It has a
fixed 15-field structure (district → P.S. → FIR no/year → acts/sections →
occurrence date/time/place → complainant → accused → narrative #12 → IO/
action taken #13). We bias the prompt to that form so Claude can lock onto
field positions even when handwriting/stamps degrade the image, and we
accept multiple pages in a single call because real FIRs are 3-5 pages.

Cost: ~₹3-8 per OCR call (one image cheap, multi-page more).
Latency: 4-10s.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Iterable, Optional, Sequence

from headnote.llm.client import get_client


log = logging.getLogger(__name__)


OCR_FIR_PROMPT = """You are reading an Indian FIR (First Information Report) registered under Section 154 CrPC. 99% of Indian FIRs use the standard **NCRB I.I.F.-I (Integrated Investigation Form-I)** format with this fixed structure:

  1. District / P.S. (Police Station) / FIR No. / Year
  2. Acts & Sections (table — Act column, Section column)
  3. Occurrence: (a) Day, Date From/To, Time From/To  (b) Information received at P.S. date+time  (c) General Diary entry no + date
  4. Type of Information (Oral / Written)
  5. Place of Occurrence — (a) direction & distance from P.S., beat no  (b) address  (c) outside-PS-limit
  6. Complainant / Informant — Name, Father, DOB, Nationality, ID details, Address, Occupation, Mobile
  7. Details of Accused (table — Name, Alias, Relative's Name [पिता/पति का नाम], Present Address — one row per accused)
  8. Reasons for delay in reporting
  9. Particulars of property
 10. Total value of property
 11. Inquest Report / U.D. case No.
 12. **First Information contents** (the narrative — usually long Hindi prose written by the SI/IO recording what the complainant said)
 13. Action taken — case registered, I.O. directed (Name + Rank), refused investigation reason, transferred to another P.S.
 14. Signature of complainant
 15. Date & time of dispatch to court

Pages may be in Hindi (Devanagari), English, or both. Stamps, signatures, and handwriting are common. Multiple images may be sent — they are consecutive pages of the SAME FIR (process them as one document).

Extract the following structured JSON. Return ONLY a JSON object — no markdown fences, no prose.

{
  "fir_number":        "string — exactly as written, e.g. '0895' or '95/2022'. null if not found",
  "fir_year":          "string — 4-digit year, e.g. '2022'. null if not found",
  "fir_date":          "string — DD.MM.YYYY (date FIR was registered, field 1/2/3b)",
  "police_station":    "string — e.g. 'मुरार' or 'Murar' (verbatim, same script as FIR)",
  "district":          "string — e.g. 'ग्वालियर' or 'Gwalior'",
  "state":             "string — usually inferred from district; if visible, use that",

  "sections":          ["array of statute references. Combine Act + Section columns. Format: '<section> <Act>'. Examples: '306 IPC', '34 IPC', '302 BNS', '25 Arms Act', '8/22 NDPS', '4 POCSO'. Use 'IPC' for भा.द.सं. 1860, 'BNS' for भारतीय न्याय संहिता 2023, 'BNSS' for भारतीय नागरिक सुरक्षा संहिता."],

  "occurrence_date":   "string — DD.MM.YYYY when offence took place (field 3a 'Date From'). null if not present",
  "occurrence_time":   "string — HH:MM 24-hour (field 3a 'Time From'). null if not present",
  "occurrence_place":  "string — landmark/locality (field 5b address), verbatim",
  "occurrence_distance": "string — direction + distance from PS, e.g. 'दक्षिण-पूर्व, 03 किमी' (field 5a). null if not present",

  "complainant_name":  "string — name of person who lodged the FIR (field 6a)",
  "complainant_father": "string — complainant's father's name (field 6b). null if not present",
  "complainant_dob":   "string — birth year or DD.MM.YYYY (field 6c). null if not present",
  "complainant_address": "string — current address (field 6h). null if not present",
  "complainant_mobile": "string — phone number (field 6j). null if not present",

  "accused_details":   [
    {
      "name":         "string — verbatim, same script as FIR",
      "alias":        "string or null",
      "relative":     "string — father's/husband's name (field 7 'Relative's Name')",
      "relative_type": "'father' | 'husband' | 'mother' | 'other' | null",
      "address":      "string — accused's present address",
      "age":          "string or null — if mentioned"
    }
  ],
  "accused_count":     "integer — number of named accused. 0 if 'unknown' / 'अज्ञात'",

  "io_name":           "string — Investigating Officer's name (field 13 #2 'Name of I.O.'). Watch for strikethroughs — use the FINAL non-cancelled name",
  "io_rank":           "string — e.g. 'SI', 'ASI', 'Inspector'. null if not present",

  "gd_entry_no":       "string — General Diary entry number (field 3c)",
  "gd_date":           "string — DD.MM.YYYY of GD entry. null if not present",
  "type_of_info":      "'oral' | 'written' | null",
  "reasons_for_delay": "string — field 8, often blank. null if blank",

  "narrative_hi":      "string — Hindi (Devanagari) version of Para 5.1. MUST be 100% in Devanagari script — NO Latin letters mixed in. Names and places in Devanagari (e.g. 'सीमा श्रीवास', 'मुरार', 'ग्वालियर'). Start with: 'यह कि दिनांक <DD.MM.YYYY> को लगभग <HH:MM बजे> समय पर <स्थान> में अभियोजन का आरोप है कि...'. Strip police boilerplate ('मैं उप निरीक्षक...', 'सूचना पर मर्ग जांच...', 'विवेचना में लिया जाता है'). Preserve all factual content — what each accused allegedly did. Third-person. Max 500 words.",

  "narrative_en":      "string — English version of Para 5.1. MUST be 100% in English — NO Devanagari mixed in. Transliterate names and places to Roman (e.g. 'Sima Shrivas', 'Murar', 'Gwalior'). Start with: 'It is alleged that on <DD.MM.YYYY> at about <HH:MM> hours at <place>, ...'. Same content as narrative_hi, third-person, neutral prosecution recitation. Max 500 words.",

  "narrative_raw":     "string — verbatim transcription of field 12 text BEFORE cleanup, in the original script. Useful as fallback. Max 800 words.",

  "language":          "'hi' | 'en' | 'mixed'",
  "confidence":        "'high' | 'medium' | 'low' — overall confidence in the extraction",
  "notes":             "string — caveats: 'page 3 partially illegible', 'sections column smudged', 'IO name struck through, used replacement', 'no accused named (unknown)', etc. null if clean"
}

CRITICAL RULES
==============
1. **The accused, NOT the complainant, becomes the bail-application APPLICANT.** Extract accused_details accurately — full name, relative's name, address — because that data populates the bail applicant fields.
2. **Multiple accused → list ALL of them** in accused_details. The bail-app frontend will pick one (the applicant in this draft) and the rest become co-accused.
3. **Sections must combine the Act column + Section column** from field 2. If you see 'भा.द.सं. 1860' in Acts and '306, 34' in Sections, output ['306 IPC', '34 IPC'] — separate entries.
4. **Don't transliterate names.** Hindi names stay in Devanagari, English names stay in Roman.
5. **For struck-through values (especially IO names)**, use the FINAL non-cancelled value.
6. **Mobile numbers**: strip 'mobile:', '91-', spaces. Return just digits or '+91XXXXXXXXXX'.
7. **If a field is not present**, return null (not "" or "N/A"). Numbers/arrays not present → null or [].
8. **If the image is not an FIR** (e.g. a charge-sheet, summons, complaint letter), set confidence='low', notes='not an FIR — appears to be <X>', and return null for FIR-specific fields.

Return ONLY the JSON object. No commentary, no markdown."""


OCR_BAIL_ORDER_PROMPT = """You are reading an Indian SESSIONS COURT (or Magistrate) BAIL ORDER — the order disposing of a bail / anticipatory-bail application. These orders are used to draft a SUCCESSIVE bail application before the High Court, so extract every field a High Court bail draft needs.

Typical structure (Hindi Devanagari, English, or mixed; may be typed with a scanned signature):
  - Header: court name + presiding judge, bail case number, order date
  - Parties: applicant(s) / accused (name, father/husband, age, address) ; vs ; State through the Police Station
  - Appearances: applicant's advocate, the Public Prosecutor / APP
  - Crime block: Crime/FIR number, Police Station, Sections + Act, FIR date, incident date
  - The provision the application was filed under (S.482/483 BNSS or S.438/439/437 CrPC)
  - Whether it's the first / second / third bail application
  - Brief facts (the prosecution case)
  - Grounds urged by the accused + the prosecution's objections
  - The court's REASONING and the final operative ORDER (granted / rejected / withdrawn / dismissed)

Multiple images may be sent — they are consecutive pages of the SAME order. Process as one document.

Extract this JSON. Return ONLY the JSON object — no markdown fences, no prose.

{
  "court_name":        "string — full court as written, e.g. 'प्रथम अपर सत्र न्यायाधीश, ग्वालियर' or 'First Additional Sessions Judge, Gwalior'. Same script as the order.",
  "court_level":       "'sessions' | 'magistrate' | 'special_court' | null",
  "presiding_judge":   "string — the judge who signed (from the signature block / पीठासीन अधिकारी). null if not visible.",
  "bail_case_number":  "string — the bail application/case number, e.g. '2528/2024'. null if not found.",
  "order_date":        "string — DD.MM.YYYY the order was passed. null if not found.",

  "applicants": [
    {
      "name":     "string — verbatim, same script",
      "relative": "string — father's/husband's name",
      "relative_type": "'father'|'husband'|'mother'|'other'|null",
      "age":      "string or null",
      "address":  "string or null"
    }
  ],

  "state_name":        "string — e.g. 'मध्य प्रदेश' / 'Madhya Pradesh'. null if not found.",
  "police_station":    "string — investigating P.S., e.g. 'मुरार' / 'Murar'.",
  "district":          "string or null",

  "fir_number":        "string — crime/FIR number, e.g. '409/2021'. null if not found.",
  "fir_date":          "string — DD.MM.YYYY. null if not found.",
  "incident_date":     "string — DD.MM.YYYY of the alleged offence. null if not found.",
  "sections":          ["array — statute refs combining section + Act, e.g. '34(2) Excise Act', '49(a) Excise Act', '302 IPC', '420 BNS'. Same script for act names is fine but prefer roman act abbreviations."],

  "bail_provision":    "string — the section the application was filed under, e.g. '482 BNSS' or '438 CrPC' or '439 CrPC'. null if not found.",
  "bail_type":         "'anticipatory' | 'regular' | 'default' | null  — anticipatory = 438 CrPC / 482 BNSS; regular = 437/439 CrPC / 480/483 BNSS.",
  "application_number": "integer — 1 for first bail, 2 for second (द्वितीय), 3 for third. Default 1 if the order doesn't say it's a successive application.",

  "main_case_number":  "string — the underlying trial/criminal case number if mentioned (e.g. '70/2023'), distinct from the bail case number. null if not present.",
  "trial_court":       "string — the court where the main case is pending/tried, if named. null if not present.",

  "co_accused":        ["array of strings — names of co-accused mentioned in the order. [] if none."],

  "outcome":           "'rejected' | 'granted' | 'withdrawn' | 'dismissed' | 'allowed' | null  — the FINAL operative result for THIS application.",
  "outcome_reasoning": "string — 2-4 sentence neutral summary of WHY the court decided as it did (the ratio of the order). This goes into the HC draft's 'lower court history'. Third-person. Max 250 words. Preserve statutory bars the court relied on (e.g. 'S.59-A MP Excise Act bars anticipatory bail where quantity exceeds 50 bulk litres').",

  "facts_narrative_hi": "string — Hindi (100% Devanagari) prosecution-case summary from the order. Third-person. Strip boilerplate. Max 400 words. null if order has no facts recital.",
  "facts_narrative_en": "string — English (100% roman) version of the same facts. Max 400 words.",

  "applicant_advocate": "string — counsel for the applicant, if named. null otherwise.",
  "public_prosecutor":  "string — APP/PP for the State, if named. null otherwise.",

  "language":          "'hi' | 'en' | 'mixed'",
  "confidence":        "'high' | 'medium' | 'low'",
  "notes":             "string — caveats (illegible pages, ambiguous outcome, etc.). null if clean."
}

CRITICAL RULES
==============
1. The ACCUSED / APPLICANT in the order becomes the bail APPLICANT in the new HC draft — extract applicants[] accurately (name, relative, age, address).
2. `outcome` is the result for the application THIS order disposes of — read the operative last paragraph ('निरस्त' = rejected, 'स्वीकार' = granted/allowed, 'खारिज' = dismissed, 'वापस' = withdrawn).
3. `outcome_reasoning` must capture the COURT'S actual reason — especially any statutory bar — because the HC draft must address it.
4. Don't transliterate names — keep Devanagari names in Devanagari, roman in roman.
5. Distinguish the BAIL case number from the MAIN/trial case number — they are different.
6. If a field is absent, return null (not "" or "N/A").
7. If the image is NOT a bail order (e.g. it's an FIR or a charge-sheet), set confidence='low', notes='not a bail order — appears to be <X>', and null the order-specific fields.

Return ONLY the JSON object. No commentary, no markdown."""


def _img_block(image_bytes: bytes, media_type: str) -> dict:
    """Build an Anthropic content block for an image or PDF."""
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    if media_type == "application/pdf":
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": b64,
            },
        }
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": b64,
        },
    }


def ocr_fir_image(
    image_bytes: bytes,
    media_type: str = "image/jpeg",
) -> dict:
    """Backwards-compatible single-page OCR — wraps the multi-page entry point."""
    return ocr_fir_pages([(image_bytes, media_type)])


def _parse_json_response(raw: str) -> dict:
    """Extract and parse JSON from a model response string."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise ValueError(f"Response is not JSON. Start: {raw[:300]}")
        return json.loads(m.group(0))


def _normalise(parsed: dict) -> dict:
    """Post-process the model output into canonical form."""
    if isinstance(parsed.get("accused_details"), list):
        parsed["accused_count"] = len(parsed["accused_details"])
    if parsed.get("fir_number") and parsed.get("fir_year"):
        fir_no = str(parsed["fir_number"]).strip()
        fir_yr = str(parsed["fir_year"]).strip()
        if "/" not in fir_no and fir_yr not in fir_no:
            parsed["fir_number_full"] = f"{fir_no}/{fir_yr}"
        else:
            parsed["fir_number_full"] = fir_no
    return parsed


def _ocr_via_groq(pages: Sequence[tuple[bytes, str]], prompt: str = OCR_FIR_PROMPT) -> dict:
    """Use Groq + Llama-4-Scout vision (free tier, 14400 req/day).

    Groq accepts multiple image blocks in a single chat message — we send
    all pages together so the model can reconcile fields that span pages
    (narrative on p3, IO name on p4, etc.).

    `prompt` selects the extraction schema (FIR vs bail-order vs ...).
    """
    from groq import Groq

    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        raise RuntimeError("GROQ_API_KEY not set")

    client = Groq(api_key=groq_key)
    model = os.environ.get("GROQ_OCR_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

    content: list[dict] = []
    for idx, (img_bytes, mt) in enumerate(pages, start=1):
        if len(pages) > 1:
            content.append({"type": "text", "text": f"--- Page {idx} of {len(pages)} ---"})
        b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mt};base64,{b64}"},
        })
    content.append({"type": "text", "text": prompt})

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=4000,
        temperature=0.1,
    )
    raw = resp.choices[0].message.content or ""
    return _parse_json_response(raw)


def _ocr_via_anthropic(pages: Sequence[tuple[bytes, str]], prompt: str = OCR_FIR_PROMPT) -> dict:
    """Fallback: use Anthropic Claude Sonnet vision.

    `prompt` selects the extraction schema (FIR vs bail-order vs ...).
    """
    client = get_client()
    model = (
        os.environ.get("BEDROCK_SONNET_ID", "us.anthropic.claude-sonnet-4-6")
        if os.environ.get("AWS_ACCESS_KEY_ID")
        else "claude-sonnet-4-6"
    )
    content_blocks: list[dict] = []
    for idx, (img_bytes, mt) in enumerate(pages, start=1):
        if len(pages) > 1:
            content_blocks.append({"type": "text", "text": f"--- Page {idx} of {len(pages)} ---"})
        content_blocks.append(_img_block(img_bytes, mt))
    content_blocks.append({"type": "text", "text": prompt})
    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        messages=[{"role": "user", "content": content_blocks}],
        timeout=90.0,
    )
    text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return _parse_json_response("\n".join(text_blocks))


def _run_ocr(pages, prompt, normalise_fn):
    """Generic multi-page OCR runner. Provider priority: Groq (free/fast) →
    Anthropic Sonnet (when a real key is set). `prompt` selects the schema;
    `normalise_fn` post-processes the parsed JSON. Raises ValueError with a
    clear, provider-accurate message when all configured providers fail."""
    if not pages:
        raise ValueError("no pages provided")

    groq_key      = os.environ.get("GROQ_API_KEY", "").strip()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    bedrock_key   = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()

    groq_err: Optional[Exception] = None
    anthropic_err: Optional[Exception] = None

    if groq_key:
        try:
            return normalise_fn(_ocr_via_groq(pages, prompt))
        except Exception as e:
            log.warning("Groq OCR failed: %s", e)
            groq_err = e

    if anthropic_key or bedrock_key:
        try:
            return normalise_fn(_ocr_via_anthropic(pages, prompt))
        except Exception as e:
            log.warning("Anthropic OCR failed: %s", e)
            anthropic_err = e

    # All configured providers exhausted. Build a clear, user-facing
    # message that names the actual failure(s) instead of leaking
    # the wrong provider's error.
    if groq_err and not anthropic_key and not bedrock_key:
        # Common production case — Groq is the only configured backend.
        # Show the real Groq error with guidance.
        msg = _format_groq_error(groq_err)
        raise ValueError(msg)
    if groq_err and anthropic_err:
        raise ValueError(
            f"OCR failed on both providers. Groq: {groq_err}. Anthropic: {anthropic_err}"
        )
    if anthropic_err:
        raise ValueError(f"OCR failed: {anthropic_err}")
    if groq_err:
        raise ValueError(_format_groq_error(groq_err))
    raise ValueError("OCR is not configured. Set GROQ_API_KEY on the server.")


def ocr_fir_pages(pages: Sequence[tuple[bytes, str]]) -> dict:
    """OCR + parse a multi-page FIR (NCRB I.I.F.-I)."""
    return _run_ocr(pages, OCR_FIR_PROMPT, _normalise)


def _normalise_bail_order(parsed: dict) -> dict:
    """Post-process a bail-order extraction into canonical form."""
    if isinstance(parsed.get("applicants"), list):
        parsed["applicant_count"] = len(parsed["applicants"])
    # Normalise application_number to an int >= 1
    try:
        parsed["application_number"] = max(1, int(parsed.get("application_number") or 1))
    except (TypeError, ValueError):
        parsed["application_number"] = 1
    # Combine fir number + year if both present and separate
    fn = str(parsed.get("fir_number") or "").strip()
    if fn and "/" not in fn and parsed.get("incident_date"):
        yr = str(parsed["incident_date"])[-4:]
        if yr.isdigit():
            parsed["fir_number_full"] = f"{fn}/{yr}"
    return parsed


def ocr_bail_order_pages(pages: Sequence[tuple[bytes, str]]) -> dict:
    """OCR + parse a multi-page Sessions/Magistrate BAIL ORDER.

    Used to draft a successive High Court bail application: extracts the
    lower court, bail-case number, order date, applicants, crime details,
    outcome, and the court's reasoning. Same provider chain as FIR OCR."""
    return _run_ocr(pages, OCR_BAIL_ORDER_PROMPT, _normalise_bail_order)


def _format_groq_error(err: Exception) -> str:
    """Translate raw Groq exceptions into user-friendly guidance. Groq's
    common failure modes are token-per-minute rate limit (for multi-page
    FIRs) and request-too-large (single huge image)."""
    s = str(err).lower()
    if "rate_limit" in s or "rate limit" in s or "429" in s or "tpm" in s:
        return (
            "Hit Groq's per-minute rate limit while reading the FIR. "
            "Wait 60 seconds and retry, or upload fewer pages at a time. "
            "(Free tier: 6,000 tokens/min for vision.)"
        )
    if "request_too_large" in s or "request too large" in s or "413" in s:
        return (
            "FIR pages too large for one request. Try uploading 1-2 pages "
            "at a time, or compress the images before upload."
        )
    if "401" in s or "unauthorized" in s or "invalid_api_key" in s:
        return "OCR provider rejected the API key. Contact hello@headnote.in."
    if "timeout" in s or "timed out" in s:
        return "OCR request timed out. Network or provider slow — please retry."
    return f"OCR failed: {err}"
