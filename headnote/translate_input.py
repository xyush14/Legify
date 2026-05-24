"""Hindi input pre-translation.

When a lawyer types a query in Devanagari (Hindi script), translate it to
English via Haiku BEFORE the main retrieval pipeline runs. Retrieval, IK
search, and LLM generation all operate on the English version. The original
Hindi is preserved on the response so the UI can show a bilingual strip
("आपकी क्वेरी: ... → translated to: ...") and let the lawyer override.

Cost: ~₹0.50 per Hindi query (Haiku, ~600 input + 200 output tokens). Skipped
entirely when the query has no Devanagari (no latency, no cost).
"""

from __future__ import annotations

import json
import re
from typing import Optional, Tuple

from headnote import config

_DEVANAGARI_RX = re.compile(r"[ऀ-ॿ]")


def detect_script(text: str) -> str:
    """Return 'devanagari' if >=15% of non-space chars are Devanagari, else 'latin'.

    The 15% threshold tolerates code-switched queries like
    `s.125 CrPC में भरण-पोषण` (statute refs in English, narrative in Hindi) —
    common in real lawyer phrasing.
    """
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return "latin"
    deva = sum(1 for c in chars if _DEVANAGARI_RX.match(c))
    return "devanagari" if deva / len(chars) >= 0.15 else "latin"


# Seed glossary — senior advocate will expand. Format: hindi → english.
# Keeping this inline (not YAML) for now so there's zero file-loading risk
# in production. Move to glossary/hi_en_criminal.yaml when it exceeds ~150 entries.
HI_EN_GLOSSARY: dict[str, str] = {
    # procedural
    "भरण-पोषण": "maintenance",
    "भरण पोषण": "maintenance",
    "ज़मानत": "bail",
    "जमानत": "bail",
    "अग्रिम जमानत": "anticipatory bail",
    "गिरफ्तारी": "arrest",
    "आरोप-पत्र": "chargesheet",
    "चार्जशीट": "chargesheet",
    "प्राथमिकी": "FIR",
    "एफ.आई.आर.": "FIR",
    "विचारण": "trial",
    "दोषसिद्धि": "conviction",
    "दोषमुक्ति": "acquittal",
    "बरी": "acquittal",
    "अपील": "appeal",
    "पुनरीक्षण": "revision",
    "पुनर्विचार": "review",
    "स्थगन": "stay",
    "रद्द": "quashed",
    "खारिज": "dismissed",
    "स्वीकार": "allowed",
    "अभिरक्षा": "custody",
    "पुलिस अभिरक्षा": "police custody",
    "न्यायिक अभिरक्षा": "judicial custody",
    "रिमांड": "remand",
    "संज्ञेय अपराध": "cognizable offence",
    "असंज्ञेय अपराध": "non-cognizable offence",
    "जमानती": "bailable",
    "गैर-जमानती": "non-bailable",
    "शमनीय": "compoundable",
    "गैर-शमनीय": "non-compoundable",
    # substantive
    "क्रूरता": "cruelty",
    "दहेज": "dowry",
    "घरेलू हिंसा": "domestic violence",
    "बलात्कार": "rape",
    "हत्या": "murder",
    "डकैती": "dacoity",
    "चोरी": "theft",
    "धोखाधड़ी": "cheating",
    "षड्यंत्र": "criminal conspiracy",
    "अभियुक्त": "accused",
    "आरोपी": "accused",
    "अभियोजन": "prosecution",
    "गवाह": "witness",
    "साक्ष्य": "evidence",
    "गवाही": "testimony",
    # courts / officers
    "उच्च न्यायालय": "High Court",
    "सर्वोच्च न्यायालय": "Supreme Court",
    "सत्र न्यायालय": "Sessions Court",
    "न्यायिक मजिस्ट्रेट": "Judicial Magistrate",
    "मुख्य न्यायिक मजिस्ट्रेट": "Chief Judicial Magistrate",
    "मुख्य महानगर मजिस्ट्रेट": "Chief Metropolitan Magistrate",
    "न्यायाधीश": "Judge",
    "न्यायालय": "Court",
    # statutes
    "भारतीय न्याय संहिता": "Bharatiya Nyaya Sanhita",
    "बी.एन.एस.": "BNS",
    "भारतीय नागरिक सुरक्षा संहिता": "Bharatiya Nagarik Suraksha Sanhita",
    "भारतीय साक्ष्य अधिनियम": "Bharatiya Sakshya Adhiniyam",
    "दण्ड संहिता": "Penal Code",
    "धारा": "section",
    "अधिनियम": "Act",
    # orders / judgments
    "आदेश": "order",
    "निर्णय": "judgment",
    "फैसला": "judgment",
    "अंतरिम आदेश": "interim order",
}


_TRANSLATE_SYSTEM_PROMPT = """You are a legal translator for Indian criminal law. Translate the user's Hindi query into English suitable for case-law retrieval.

STRICT RULES:
1. For any term in the glossary below, use the EXACT English equivalent. Do not paraphrase glossary terms.
2. Preserve all section numbers, statute names, and case citations verbatim.
3. For terms not in the glossary, translate naturally but keep Indian legal register (e.g. "FIR" not "police complaint", "chargesheet" not "indictment").
4. If the input mixes Hindi and English, translate only the Hindi portions; keep English portions unchanged.
5. Do not add information not in the original. Do not interpret. Translate only.

Return STRICT JSON only, no preamble:
{"english_query": "...", "preserved_terms": ["list of glossary terms you used"]}"""


def _build_glossary_block(glossary: dict[str, str]) -> str:
    return "\n".join(f"  {hi} → {en}" for hi, en in glossary.items())


def translate_hi_to_en(query: str) -> Tuple[str, list[str], int]:
    """Translate a Hindi (or mixed) query to English via Haiku.

    Returns (english_query, preserved_glossary_terms, cost_paise).

    On any failure (no API key, parse error, etc.) returns the original query
    unchanged with zero preserved terms and zero cost — the main pipeline still
    runs, just on the original text. Failures are silent on purpose: a lawyer
    shouldn't see "translation failed" when retrieval might still work.
    """
    if not config.ANTHROPIC_API_KEY:
        return query, [], 0

    try:
        from headnote.llm import route_call
    except Exception:
        return query, [], 0

    glossary_block = _build_glossary_block(HI_EN_GLOSSARY)
    user_prompt = (
        f"GLOSSARY:\n{glossary_block}\n\n"
        f"INPUT (Hindi or mixed):\n{query}\n\n"
        "Return JSON only."
    )
    try:
        # Cache the system prompt (static glossary block + role instructions).
        # On Haiku, cache_read is ~10% of input price → significant savings
        # across the ~hourly call frequency of Hindi/code-mix queries.
        result = route_call(
            "translation",
            {
                "system_prompt": _TRANSLATE_SYSTEM_PROMPT,
                "user_prompt": user_prompt,
                "cache": True,
            },
        )
    except Exception as e:
        print(f"[translate_input] Haiku call failed ({e}); using original query")
        return query, [], 0

    raw = (result.response or "").strip()
    # Strip code fences if Haiku added them
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
        english = (parsed.get("english_query") or "").strip()
        preserved = list(parsed.get("preserved_terms") or [])
    except Exception as e:
        print(f"[translate_input] non-JSON response ({e}); using original query")
        return query, [], result.cost_paise

    if not english:
        return query, [], result.cost_paise
    return english, preserved, result.cost_paise


def maybe_translate(query: str) -> dict:
    """Front-door helper. Returns a dict with:
        script:         "devanagari" | "latin"
        original_query: the input verbatim
        english_query:  translated if devanagari, else == original
        preserved_terms: glossary terms used (empty if latin or skipped)
        translation_cost_paise: 0 if no translation happened
    """
    script = detect_script(query)
    if script == "latin":
        return {
            "script": "latin",
            "original_query": query,
            "english_query": query,
            "preserved_terms": [],
            "translation_cost_paise": 0,
        }
    english, preserved, cost = translate_hi_to_en(query)
    return {
        "script": "devanagari",
        "original_query": query,
        "english_query": english,
        "preserved_terms": preserved,
        "translation_cost_paise": cost,
    }
