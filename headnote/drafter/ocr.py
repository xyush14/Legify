"""FIR photo/PDF OCR + structured extraction via Claude vision.

Approach: skip Tesseract entirely. Claude (Sonnet via Bedrock) does
OCR + structured parsing in a single multimodal call. Handles Hindi
+ English handwritten/printed FIRs equally well, returns a clean JSON
ready to populate the bail-application form.

Cost: ~₹2-5 per OCR call (subsidised by AWS credits).
Latency: 3-6s.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Optional

from headnote.llm.client import get_client


log = logging.getLogger(__name__)


OCR_FIR_PROMPT = """You are reading a First Information Report (FIR) from an Indian police station. The FIR may be in Hindi (Devanagari) or English. It is a photographed/scanned document — text may be handwritten, printed, or both.

Extract the following structured fields. Return ONLY a JSON object — no markdown fences, no prose.

{
  "fir_number":        "string — e.g., '95/2016' or null if not found",
  "fir_date":          "string — DD.MM.YYYY format, or null",
  "police_station":    "string — e.g., 'गोला का मंदिर' or 'Gola Ka Mandir', or null",
  "district":          "string — e.g., 'ग्वालियर' or 'Gwalior', or null",
  "state":             "string — e.g., 'मध्य प्रदेश' or 'Madhya Pradesh', or null",
  "sections":          ["array of statute sections — e.g., '302 IPC', '147 IPC', '25 Arms Act', '13 Dacoity Act'"],
  "complainant_name":  "string — name of person who filed the FIR",
  "complainant_father": "string — father's name, or null",
  "complainant_address": "string — or null",
  "accused_names":     ["array of named accused as written in the FIR"],
  "occurrence_date":   "string — DD.MM.YYYY when crime took place, or null",
  "occurrence_time":   "string — HH:MM 24-hour, or null",
  "occurrence_place":  "string — landmark/locality where crime occurred",
  "narrative":         "string — the complainant's statement, written verbatim in Hindi if FIR is Hindi, English if English. Preserve names, dates, sections as they appear. Max 600 words. This becomes Para 5.1 of the bail application after style adjustment.",
  "arrest_date":       "string — DD.MM.YYYY of arrest if mentioned, else null",
  "language":          "'hi' if FIR is in Hindi/Devanagari, 'en' if English, 'mixed' if both",
  "confidence":        "'high' | 'medium' | 'low' — your confidence in the extraction overall",
  "notes":             "string — any caveats: 'parts illegible', 'sections list partial', etc., or null"
}

RULES
=====
- If a field is not present in the FIR, return null (not an empty string).
- For sections: include the act name (IPC / BNS / Arms Act / NDPS / POCSO / etc.)
- For names: write in the same script as the FIR. Don't transliterate.
- For the narrative: write a clean version of the complainant's statement. Remove FIR boilerplate ("मैंने यह रिपोर्ट दर्ज करायी कि...") but PRESERVE all factual content — names, times, places, sequence of events, what each accused did.
- If the image is unreadable or not an FIR, set confidence='low' and notes='not an FIR' or 'illegible'.

Return ONLY the JSON object. No commentary."""


def ocr_fir_image(
    image_bytes: bytes,
    media_type: str = "image/jpeg",
) -> dict:
    """OCR + parse an FIR photo. Returns the structured dict above.

    `media_type` should be one of:
      - 'image/jpeg', 'image/png', 'image/webp', 'image/gif'
      - 'application/pdf'  (Bedrock supports PDF too)

    Raises ValueError if Claude returns something unparseable.
    """
    import os

    client = get_client()
    model = (
        os.environ.get("BEDROCK_SONNET_ID", "us.anthropic.claude-sonnet-4-6")
        if os.environ.get("AWS_ACCESS_KEY_ID")
        else "claude-sonnet-4-6"
    )

    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    if media_type == "application/pdf":
        content_blocks = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": b64,
                },
            },
            {"type": "text", "text": OCR_FIR_PROMPT},
        ]
    else:
        content_blocks = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64,
                },
            },
            {"type": "text", "text": OCR_FIR_PROMPT},
        ]

    resp = client.messages.create(
        model=model,
        max_tokens=3000,
        messages=[{"role": "user", "content": content_blocks}],
        timeout=60.0,
    )

    text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    raw = "\n".join(text_blocks).strip()

    # Strip code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract first JSON object
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        raise ValueError(f"OCR returned non-JSON. Raw start: {raw[:300]}")
