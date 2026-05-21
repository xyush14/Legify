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


def _ocr_via_groq(pages: Sequence[tuple[bytes, str]]) -> dict:
    """Use Groq + Llama-4-Scout vision (free tier, 14400 req/day).

    Groq accepts multiple image blocks in a single chat message — we send
    all pages together so the model can reconcile fields that span pages
    (narrative on p3, IO name on p4, etc.).
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
    content.append({"type": "text", "text": OCR_FIR_PROMPT})

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=4000,
        temperature=0.1,
    )
    raw = resp.choices[0].message.content or ""
    return _parse_json_response(raw)


def _ocr_via_anthropic(pages: Sequence[tuple[bytes, str]]) -> dict:
    """Fallback: use Anthropic Claude Sonnet vision."""
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
    content_blocks.append({"type": "text", "text": OCR_FIR_PROMPT})
    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        messages=[{"role": "user", "content": content_blocks}],
        timeout=90.0,
    )
    text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return _parse_json_response("\n".join(text_blocks))


def ocr_fir_pages(pages: Sequence[tuple[bytes, str]]) -> dict:
    """OCR + parse a multi-page FIR.

    Provider priority:
      1. Groq  (free, fast — llama-4-scout vision)   when GROQ_API_KEY set
      2. Anthropic Claude Sonnet                       when ANTHROPIC_API_KEY / Bedrock set
    """
    if not pages:
        raise ValueError("no pages provided")

    last_err: Optional[Exception] = None

    if os.environ.get("GROQ_API_KEY"):
        try:
            return _normalise(_ocr_via_groq(pages))
        except Exception as e:
            log.warning("Groq OCR failed (%s), trying Anthropic fallback", e)
            last_err = e

    try:
        return _normalise(_ocr_via_anthropic(pages))
    except Exception as e:
        last_err = e

    raise ValueError(f"All OCR backends failed. Last error: {last_err}")
