"""FIR photo/PDF OCR + structured extraction via Groq Llama-4-Scout vision.

The Indian FIR is a near-universally standard document: the NCRB I.I.F.-I
(Integrated Investigation Form-I) printed under Section 154 CrPC. It has a
fixed 15-field structure (district → P.S. → FIR no/year → acts/sections →
occurrence date/time/place → complainant → accused → narrative #12 → IO/
action taken #13). We bias the prompt to that form so the model can lock
onto field positions even when handwriting/stamps degrade the image, and we
accept multiple pages because real FIRs are 3-5 pages.

Provider policy (cost): Groq Llama-4-Scout is the free/near-free primary. A
hard scan that Groq reads as empty triggers a free higher-DPI Groq retry,
NOT a paid Claude call. An optional OpenAI-compatible vision fallback
(OCR_FALLBACK_API_KEY — e.g. DeepSeek-VL2 / DeepSeek-V4 via OpenRouter) can
be switched on to rescue scans Groq can't read; it stays DORMANT unless that
key is set, so the out-of-the-box behavior is unchanged and adding it cannot
break OCR for any user. The Anthropic Claude vision fallback is kept in code
but DISABLED by default (set OCR_ENABLE_ANTHROPIC=1 to re-enable); Claude
vision costs ~30x more per page.

Cost: ~₹0.1-0.3 per OCR call on Groq.
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
  "police_station":    "string — e.g. 'कोतवाली' or 'Kotwali' (verbatim, same script as FIR)",
  "district":          "string — e.g. 'लखनऊ' or 'Lucknow'",
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
  "arrest_date":       "string — DD.MM.YYYY the accused was arrested, ONLY if explicitly stated (action-taken / GD / narrative, e.g. 'गिरफ्तारी दिनांक' / 'गिरफ्तार किया'). Most FIRs do NOT record an arrest date — return null if not clearly stated. Never infer it from the FIR or occurrence date.",
  "type_of_info":      "'oral' | 'written' | null",
  "reasons_for_delay": "string — field 8, often blank. null if blank",

  "narrative_hi":      "string — Hindi (Devanagari) version of Para 5.1. MUST be 100% in Devanagari script — NO Latin letters mixed in. Names and places in Devanagari (e.g. 'सीमा वर्मा', 'कोतवाली', 'लखनऊ'). Start with: 'यह कि दिनांक <DD.MM.YYYY> को लगभग <HH:MM बजे> समय पर <स्थान> में अभियोजन का आरोप है कि...'. Strip police boilerplate ('मैं उप निरीक्षक...', 'सूचना पर मर्ग जांच...', 'विवेचना में लिया जाता है'). Preserve all factual content — what each accused allegedly did. Third-person. Max 500 words.",

  "narrative_en":      "string — English version of Para 5.1. MUST be 100% in English — NO Devanagari mixed in. Transliterate names and places to Roman (e.g. 'Sima Verma', 'Kotwali', 'Lucknow'). Start with: 'It is alleged that on <DD.MM.YYYY> at about <HH:MM> hours at <place>, ...'. Same content as narrative_hi, third-person, neutral prosecution recitation. Max 500 words.",

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
  "court_name":        "string — full court as written, e.g. 'प्रथम अपर सत्र न्यायाधीश, लखनऊ' or 'First Additional Sessions Judge, Lucknow'. Same script as the order.",
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

  "state_name":        "string — e.g. 'उत्तर प्रदेश' / 'Uttar Pradesh'. null if not found.",
  "police_station":    "string — investigating P.S., e.g. 'कोतवाली' / 'Kotwali'.",
  "district":          "string or null",

  "fir_number":        "string — crime/FIR number, e.g. '409/2021'. null if not found.",
  "fir_date":          "string — DD.MM.YYYY. null if not found.",
  "incident_date":     "string — DD.MM.YYYY of the alleged offence. null if not found.",
  "arrest_date":       "string — DD.MM.YYYY the applicant/accused was arrested or first taken into judicial custody, as recited anywhere in the order (e.g. 'दिनांक ... को गिरफ्तार', 'दिनांक ... से न्यायिक अभिरक्षा में'). null if not stated.",
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


OCR_IMPUGNED_ORDER_PROMPT = """You are reading an Indian government / lower-court / tribunal ORDER that is about to be challenged in a High Court writ petition under Article 226. The order may be from a Revenue authority (Tehsildar, SDO, Collector), Service authority (transfer / suspension / departmental enquiry), Municipal authority, Tribunal (CAT, MAT, Tax Tribunal, MACT), Civil court, Election Commission, or similar.

Multiple pages of the SAME order may be sent — process as one document. May be in Hindi (Devanagari), English, or mixed. Could be typed or printed; stamps and signatures common.

Extract this JSON for use in a writ petition draft. Return ONLY a JSON object — no markdown fences, no prose.

{
  "authority_name":     "string — full authority/court name as written, e.g. 'Sub Divisional Officer, Vidisha' or 'अनुविभागीय अधिकारी, विदिशा'. Same script as the order.",
  "authority_role":     "'sdo'|'tehsildar'|'collector'|'district_judge'|'magistrate'|'tribunal'|'commissioner'|'department'|'municipal'|'other'",
  "case_number":        "string — reference/case number, e.g. '144/B-121/2025-26' or '0358/A-12/2025-26'. null if not found.",
  "order_date":         "string — DD.MM.YYYY of the order. null if not found.",
  "passed_by":          "string — name + designation of the officer who signed (often handwritten/stamped at bottom). null if not readable.",

  "petitioner_name":    "string — the AGGRIEVED party (the one likely to file the writ) name, verbatim. Watch for: petitioner/applicant/अनावेदक/प्रतिवादी depending on the order. null if not clear.",
  "petitioner_relative": "string — father/husband name of petitioner",
  "petitioner_address": "string or null",

  "respondent_party":   "string — the OTHER side (often a private respondent if any) name. null if not present.",
  "subject_matter":     "string — 2-4 sentence neutral summary of WHAT the order decided. Cite the statute the order was passed under (e.g. 'Section 129(5) of MP Land Revenue Code', 'Rule 14 of CCS(CCA) Rules'). Max 300 words.",
  "operative_direction": "string — the OPERATIVE part of the order (the final direction / dismissal / confirmation). 1-3 sentences. Max 150 words.",
  "outcome":            "'dismissed'|'allowed'|'remanded'|'rejected'|'confirmed'|'modified'|null  — for the petitioner/applicant before this authority.",

  "statutes_cited":     ["array of statute references invoked, e.g. 'Section 100 CPC', 'Article 14 Constitution', 'Order 39 Rule 1 CPC'."],

  "lower_proceeding_referenced": "string or null — if THIS order is itself an appeal/revision over an EARLIER order (very common — SDO's order over Tehsildar's, etc.), the earlier order's reference (case no + date + authority). Useful so the writ can challenge BOTH orders.",

  "place":              "string — district / city the authority is located in. null if not found.",
  "language":           "'hi'|'en'|'mixed'",
  "confidence":         "'high'|'medium'|'low'",
  "notes":              "string — caveats (illegible pages, ambiguous outcome, multiple orders in one doc, etc.). null if clean."
}

CRITICAL RULES
==============
1. The PETITIONER in the writ is the AGGRIEVED party before this authority — usually the one whose request was REJECTED or against whom proceedings ran. Identify them correctly.
2. `subject_matter` and `operative_direction` go straight into the writ petition's facts / grounds — write them in neutral, third-person, "court-tone" language ready to paste.
3. If the order references an EARLIER order (this is common: a SDO order confirming a Tehsildar order; a CAT order over a departmental order), capture it in `lower_proceeding_referenced` so the writ can challenge both.
4. Statute citations must be exact — '129(5) MP Land Revenue Code' not 'MPLRC' or 'Land Code'.
5. Don't transliterate proper names — Hindi names stay in Devanagari.
6. If a field is absent, return null (not "" or "N/A").
7. If the image is NOT a government/tribunal/court order (e.g. an FIR or a private letter), set confidence='low', notes='not an impugned order — appears to be <X>', and null the order-specific fields.

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


# ── Multi-batch OCR merge ────────────────────────────────────────────────
# Narrative / free-text fields are CONCATENATED across page batches (the
# story can span pages); every other field is a header/scalar where the
# first non-empty value (earliest page) wins.
_NARRATIVE_MERGE_KEYS = {
    "narrative_hi", "narrative_en", "narrative_raw",
    "facts_narrative_hi", "facts_narrative_en",
    "outcome_reasoning", "subject_matter", "operative_direction", "notes",
}
_NULLISH_VALS = {"", "n/a", "null", "none", "nil", "-", "—"}


def _merge_ocr_results(results: Sequence[dict]) -> dict:
    """Merge per-batch OCR extractions of ONE document into a single result.

    Llama-4-Scout rejects >5 images per request, so a long FIR/order is
    OCR'd in batches and the structured results merged here:
      - scalars   → first non-empty value wins (header fields sit on p1-2)
      - lists     → concatenated + de-duplicated (accused, sections, ...)
      - narrative → concatenated in page order (the story spans pages)
    """
    merged: dict = {}
    for res in results:
        if not isinstance(res, dict):
            continue
        for k, v in res.items():
            if v is None:
                continue
            if isinstance(v, list):
                cur = merged.get(k)
                if not isinstance(cur, list):
                    cur = []
                    merged[k] = cur
                for item in v:
                    if item not in cur:
                        cur.append(item)
            elif isinstance(v, str):
                vs = v.strip()
                if not vs or vs.lower() in _NULLISH_VALS:
                    continue
                if k in _NARRATIVE_MERGE_KEYS:
                    prev = merged.get(k)
                    merged[k] = (str(prev) + "\n\n" + vs) if prev else vs
                elif not str(merged.get(k) or "").strip():
                    merged[k] = vs
            else:  # numbers, bools — first present wins
                merged.setdefault(k, v)
    return merged


def _vision_chat_one_call(client, model: str, pages: Sequence[tuple[bytes, str]],
                          prompt: str, *, page_offset: int = 0, total: int = 0) -> dict:
    """One vision request for a single batch of images over any OpenAI-compatible
    chat-completions client (Groq SDK and the openai SDK share this interface,
    so this helper backs both the Groq primary and the opt-in fallback)."""
    total = total or len(pages)
    content: list[dict] = []
    for idx, (img_bytes, mt) in enumerate(pages, start=1):
        if total > 1:
            content.append({"type": "text",
                            "text": f"--- Page {page_offset + idx} of {total} ---"})
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


def _ocr_via_groq(pages: Sequence[tuple[bytes, str]], prompt: str = OCR_FIR_PROMPT) -> dict:
    """Use Groq + Llama-4-Scout vision (free tier, 14400 req/day).

    Llama-4-Scout rejects requests with more than 5 images ("This model
    supports up to 5 images") — that was the hard failure on 6-8 page FIRs/
    bail orders. We now OCR in batches of <=GROQ_OCR_MAX_IMAGES and merge the
    structured results, so a long document reads cleanly on the free tier
    without depending on the Anthropic fallback. Documents within the cap
    still go in a single call so the model can reconcile cross-page fields.

    `prompt` selects the extraction schema (FIR vs bail-order vs ...).
    """
    from groq import Groq

    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        raise RuntimeError("GROQ_API_KEY not set")

    client = Groq(api_key=groq_key)
    model = os.environ.get("GROQ_OCR_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    max_imgs = max(1, int(os.environ.get("GROQ_OCR_MAX_IMAGES", "5")))
    total = len(pages)

    if total <= max_imgs:
        return _vision_chat_one_call(client, model, pages, prompt, page_offset=0, total=total)

    log.info("OCR: %d pages > %d-image cap — batching into %d Groq calls",
             total, max_imgs, (total + max_imgs - 1) // max_imgs)
    results: list[dict] = []
    for start in range(0, total, max_imgs):
        chunk = pages[start:start + max_imgs]
        results.append(_vision_chat_one_call(client, model, chunk, prompt,
                                             page_offset=start, total=total))
    return _merge_ocr_results(results)


def _ocr_via_openrouter(pages: Sequence[tuple[bytes, str]], prompt: str = OCR_FIR_PROMPT) -> dict:
    """OPT-IN OCR fallback over any OpenAI-compatible vision endpoint.

    This is the DeepSeek-VL2 / DeepSeek-V4 upgrade path. It stays DORMANT
    until OCR_FALLBACK_API_KEY is set, so by default it never runs and OCR
    behaves exactly as before. When enabled it rescues scans the free Groq
    primary can't read. It reuses the existing `openai` SDK (already a
    dependency — no new install) and the same batched-image + merge logic as
    Groq, because the chat-completions + image_url content format is identical
    across OpenAI-compatible providers.

    Defaults target DeepSeek vision via OpenRouter; point it at Together.ai,
    DeepSeek's own endpoint, or a self-hosted VL2 by overriding the base URL
    and model. Env:
      OCR_FALLBACK_API_KEY    — provider key (its PRESENCE enables this tier)
      OCR_FALLBACK_BASE_URL   — default https://openrouter.ai/api/v1
      OCR_FALLBACK_MODEL      — default deepseek/deepseek-v4-pro
      OCR_FALLBACK_MAX_IMAGES — per-request image cap (default 5)
      OCR_FALLBACK_TIMEOUT    — seconds (default 90)
    """
    from openai import OpenAI

    api_key = os.environ.get("OCR_FALLBACK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OCR_FALLBACK_API_KEY not set")

    base_url = os.environ.get("OCR_FALLBACK_BASE_URL", "https://openrouter.ai/api/v1").strip()
    model = os.environ.get("OCR_FALLBACK_MODEL", "deepseek/deepseek-v4-pro").strip()
    max_imgs = max(1, int(os.environ.get("OCR_FALLBACK_MAX_IMAGES", "5")))
    timeout = float(os.environ.get("OCR_FALLBACK_TIMEOUT", "90"))

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    total = len(pages)

    if total <= max_imgs:
        return _vision_chat_one_call(client, model, pages, prompt, page_offset=0, total=total)

    log.info("OCR fallback: %d pages > %d-image cap — batching into %d calls",
             total, max_imgs, (total + max_imgs - 1) // max_imgs)
    results: list[dict] = []
    for start in range(0, total, max_imgs):
        chunk = pages[start:start + max_imgs]
        results.append(_vision_chat_one_call(client, model, chunk, prompt,
                                             page_offset=start, total=total))
    return _merge_ocr_results(results)


def _ocr_via_anthropic(pages: Sequence[tuple[bytes, str]], prompt: str = OCR_FIR_PROMPT) -> dict:
    """Fallback: use Anthropic Claude Sonnet vision.

    DISABLED by default — Claude vision is ~30x Groq's per-page cost. Only
    reached when OCR_ENABLE_ANTHROPIC=1 (see _run_ocr). `prompt` selects the
    extraction schema (FIR vs bail-order vs ...).
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


def _rasterize_pdfs(
    pages: Sequence[tuple[bytes, str]],
    *, dpi: int = 150, max_total: int = 8,
) -> list[tuple[bytes, str]]:
    """Expand any PDF entries into per-page PNG images.

    Groq's vision model accepts images only ("invalid image data" on PDFs).
    We rasterize each PDF page with PyMuPDF (self-contained, no system
    poppler) so the downstream providers always receive images. Non-PDF
    entries pass through untouched. Capped at `max_total` images so a long
    PDF can't blow past Groq's per-request token limit.
    """
    out: list[tuple[bytes, str]] = []
    for data, mt in pages:
        if len(out) >= max_total:
            break
        if mt == "application/pdf":
            try:
                import fitz  # PyMuPDF
            except ImportError:
                # PyMuPDF not available — pass the PDF through; Anthropic
                # (if it has credits) can still read it. Groq will reject it.
                log.warning("PyMuPDF not installed — cannot rasterize PDF; passing through")
                out.append((data, mt))
                continue
            try:
                doc = fitz.open(stream=data, filetype="pdf")
                for page in doc:
                    if len(out) >= max_total:
                        break
                    pix = page.get_pixmap(dpi=dpi)
                    out.append((pix.tobytes("png"), "image/png"))
                doc.close()
            except Exception as e:
                log.warning("PDF rasterization failed (%s) — passing PDF through", e)
                out.append((data, mt))
        else:
            out.append((data, mt))
    return out


def _ocr_result_is_empty(parsed: dict) -> bool:
    """True when a RAW (pre-normalise) extraction carries no usable content —
    every field is null/blank/empty, ignoring the meta fields.

    Groq's free vision model sometimes returns syntactically-valid JSON with
    all fields null on hard or handwritten Devanagari scans. That parses fine,
    so the exception-based fallback never fires and the user just sees a blank
    form ("works on my clean docs, fails on theirs"). We use this to fall
    through to Anthropic in that case. Checked on the raw parse so the
    defaults that normalise_fn injects (application_number=1, *_count, …) don't
    mask an otherwise-empty result.
    """
    if not isinstance(parsed, dict):
        return True
    meta = {"confidence", "notes"}
    nullish = {"n/a", "null", "none", "nil", "-", "—"}
    for key, val in parsed.items():
        if key in meta or val is None:
            continue
        if isinstance(val, str):
            if val.strip() and val.strip().lower() not in nullish:
                return False
        elif isinstance(val, (list, dict)):
            if len(val) > 0:
                return False
        else:  # numbers, bools — a present scalar is real content
            return False
    return True


def _run_ocr(pages, prompt, normalise_fn):
    """Generic multi-page OCR runner — Groq-only by default (cost policy).

    Groq Llama-4-Scout is the sole provider we rely on: it's free/near-free.
    On a hard scan that Groq reads as EMPTY, we retry Groq once at a higher
    rasterization DPI (still free) instead of paying for Claude. The
    Anthropic vision fallback remains in the code but is DISABLED by default
    (Claude vision is ~30x the per-page cost); set OCR_ENABLE_ANTHROPIC=1 to
    turn it back on. `prompt` selects the schema; `normalise_fn`
    post-processes. Raises ValueError with a clear message when OCR fails."""
    if not pages:
        raise ValueError("no pages provided")

    original_pages = list(pages)  # pre-rasterization uploads, for the hi-DPI retry

    # Rasterize PDFs → images so Groq (images-only) can read them. No-op for
    # image uploads. Env-tunable DPI for OCR quality vs request size.
    _dpi       = int(os.environ.get("OCR_PDF_DPI", "150"))
    _retry_dpi = int(os.environ.get("OCR_RETRY_DPI", "220"))
    _max_pages = int(os.environ.get("OCR_MAX_PAGES", "10"))
    pages = _rasterize_pdfs(original_pages, dpi=_dpi, max_total=_max_pages)
    has_pdf = any(mt == "application/pdf" for _, mt in original_pages)

    groq_key      = os.environ.get("GROQ_API_KEY", "").strip()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    bedrock_key   = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    anthropic_on  = os.environ.get("OCR_ENABLE_ANTHROPIC", "0").strip().lower() in {"1", "true", "yes", "on"}

    groq_err: Optional[Exception] = None
    anthropic_err: Optional[Exception] = None
    fallback_err: Optional[Exception] = None
    groq_empty_result: Optional[dict] = None  # valid-but-empty Groq parse, kept as last resort

    if groq_key:
        try:
            groq_raw = _ocr_via_groq(pages, prompt)
            if not _ocr_result_is_empty(groq_raw):
                return normalise_fn(groq_raw)
            groq_empty_result = normalise_fn(groq_raw)
            # Silent-failure mode: valid JSON but every field null (common on
            # hard handwritten Devanagari). Re-rasterize the PDF sharper and
            # retry Groq once — free, and usually rescues the read sans Claude.
            if has_pdf and _retry_dpi > _dpi:
                log.warning("Groq OCR empty — retrying at %d DPI", _retry_dpi)
                try:
                    pages_hi = _rasterize_pdfs(original_pages, dpi=_retry_dpi, max_total=_max_pages)
                    groq_raw2 = _ocr_via_groq(pages_hi, prompt)
                    if not _ocr_result_is_empty(groq_raw2):
                        return normalise_fn(groq_raw2)
                except Exception as e:
                    log.warning("Groq hi-DPI retry failed: %s", e)
            else:
                log.warning("Groq OCR returned an empty extraction")
        except Exception as e:
            log.warning("Groq OCR failed: %s", e)
            groq_err = e

    # Opt-in OpenAI-compatible vision fallback (DeepSeek-VL2 / V4 via OpenRouter,
    # or any provider you point it at). DORMANT unless OCR_FALLBACK_API_KEY is
    # set — when unset this whole block is skipped and behavior is byte-for-byte
    # the Groq-only path. We only reach here if Groq did NOT already succeed
    # (both Groq success paths return early), so this rescues Groq failures and
    # silent-empty extractions alike. Fully failure-isolated: ANY error here
    # (including a missing `openai` import) is caught and we fall through to the
    # existing degrade path, so enabling it can never break OCR for a user.
    fallback_key = os.environ.get("OCR_FALLBACK_API_KEY", "").strip()
    if fallback_key:
        try:
            fb_raw = _ocr_via_openrouter(pages, prompt)
            if not _ocr_result_is_empty(fb_raw):
                log.info("OCR rescued by opt-in fallback provider")
                return normalise_fn(fb_raw)
            log.warning("OCR fallback provider returned an empty extraction")
        except Exception as e:
            log.warning("OCR fallback provider failed: %s", e)
            fallback_err = e

    # Anthropic vision is OFF by default (costly). Enable with OCR_ENABLE_ANTHROPIC=1.
    if anthropic_on and (anthropic_key or bedrock_key):
        try:
            return normalise_fn(_ocr_via_anthropic(pages, prompt))
        except Exception as e:
            log.warning("Anthropic OCR failed: %s", e)
            anthropic_err = e

    # Groq parsed but came back empty, and no enabled fallback rescued it:
    # return the empty form rather than hard-erroring — a blank form the
    # lawyer can fill by hand beats a red error mid-demo.
    if groq_empty_result is not None:
        return groq_empty_result

    # All available providers exhausted — surface a clear, friendly message.
    if groq_err and anthropic_err:
        raise ValueError(
            _format_groq_error(groq_err)
            + " The backup OCR provider is also unavailable right now."
        )
    if anthropic_err:
        raise ValueError(f"OCR failed: {anthropic_err}")
    if groq_err:
        raise ValueError(_format_groq_error(groq_err))
    if fallback_err:
        raise ValueError(f"OCR failed: {fallback_err}")
    raise ValueError("OCR is not configured. Set GROQ_API_KEY on the server.")


def ocr_fir_pages(pages: Sequence[tuple[bytes, str]]) -> dict:
    """OCR + parse a multi-page FIR (NCRB I.I.F.-I)."""
    return _run_ocr(pages, OCR_FIR_PROMPT, _normalise)


def ocr_generic_pages(pages: Sequence[tuple[bytes, str]],
                      fields: Sequence[dict],
                      doc_label: str = "") -> dict:
    """Generic field extraction from ANY uploaded document (image / PDF).

    Powers the universal "auto-fill from a document" uploader that every
    template gets — instead of a bespoke prompt per document type, we build the
    extraction schema on the fly from the template's own fields and reuse the
    same Groq-primary / DeepSeek-fallback runner (`_run_ocr`). Claude is NEVER
    used unless OCR_ENABLE_ANTHROPIC=1 (off by default).

    `fields` is a list of {"key", "label", "hint"} describing the form fields to
    fill. Returns {key: value-or-null}, verbatim in the document's own script.
    """
    targets = [f for f in (fields or []) if (f.get("key") or "").strip()]
    if not targets:
        return {}
    schema_lines = []
    for f in targets:
        key = f["key"].strip()
        label = (f.get("label") or key).strip()
        hint = (f.get("hint") or "").strip()
        desc = label + (f" — {hint}" if hint else "")
        schema_lines.append(f'  "{key}": "string or null  // {desc}"')
    schema = "{\n" + ",\n".join(schema_lines) + "\n}"
    doc_hint = f" The document is most likely a {doc_label}." if doc_label else ""
    prompt = (
        "You are a meticulous legal-document data-extraction engine for Indian "
        "court filings. Read the attached document image(s) — they may be in "
        "Hindi (Devanagari) or English, printed or handwritten." + doc_hint +
        " Extract ONLY the fields listed below, copying each value VERBATIM in "
        "the document's own script. Do NOT translate, summarise, infer, or "
        "invent anything. If a field is not clearly present in the document, "
        "set it to null. Respond with STRICT JSON only (no markdown, no prose), "
        "using exactly these keys:\n" + schema
    )

    def _normalise_generic(parsed: dict) -> dict:
        if not isinstance(parsed, dict):
            return {}
        wanted = {f["key"].strip() for f in targets}
        return {k: v for k, v in parsed.items() if k in wanted}

    return _run_ocr(pages, prompt, _normalise_generic)


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


def _normalise_impugned_order(parsed: dict) -> dict:
    """Post-process impugned-order extraction into canonical writ-draft form.

    Maps the raw OCR keys onto the writ-petition template field names so the
    frontend's `fills_fields` array can apply the values directly without a
    second mapping layer. We keep BOTH the raw keys and the mapped keys so
    debugging / inspection of the extracted JSON stays readable.
    """
    # Statutes_cited from the OCR comes as a list — render it as a string for
    # the writ's statutory-framework field. Keep the list too in case the FE
    # wants chips.
    statutes = parsed.get("statutes_cited") or []
    if isinstance(statutes, list):
        parsed["statutes_str"] = "; ".join(str(s) for s in statutes if s)
    # Build a one-line impugned-order summary (used in writ subject line +
    # cause-title cross-reference). Format: "<authority>, order dated <date>
    # in case <no>".
    bits = []
    if parsed.get("authority_name"):
        bits.append(str(parsed["authority_name"]).strip())
    if parsed.get("order_date"):
        bits.append(f"order dated {parsed['order_date']}")
    if parsed.get("case_number"):
        bits.append(f"in case {parsed['case_number']}")
    if bits:
        parsed["impugned_order_line"] = ", ".join(bits)
    return parsed


def ocr_impugned_order_pages(pages: Sequence[tuple[bytes, str]]) -> dict:
    """OCR + parse a multi-page GOVT / TRIBUNAL / LOWER-COURT order that is
    about to be challenged in a High Court writ petition under Article 226.

    Extracts: authority, case number, order date, signing officer, petitioner
    (aggrieved party) particulars, respondent, neutral subject-matter summary,
    operative direction, statutes cited, lower-proceeding reference (so the
    writ can challenge both the appellate and the original order in one go).
    Same provider chain as FIR OCR."""
    return _run_ocr(pages, OCR_IMPUGNED_ORDER_PROMPT, _normalise_impugned_order)


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
    if "too many images" in s or "supports up to" in s or "maximum number of images" in s:
        return (
            "This document has more pages than the OCR model takes in one "
            "request. Headnote now splits long files into batches "
            "automatically — if you still see this, upload up to 5 pages at "
            "a time."
        )
    if "401" in s or "unauthorized" in s or "invalid_api_key" in s:
        return "OCR provider rejected the API key. Contact hello@headnote.in."
    if "timeout" in s or "timed out" in s:
        return "OCR request timed out. Network or provider slow — please retry."
    return f"OCR failed: {err}"
