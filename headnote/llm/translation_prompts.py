"""Haiku translation prompts.

Two prompts: the standard system prompt, and a stricter retry prompt used
when the first attempt drops a must-preserve token. Both load the
EN↔HI legal glossary from headnote/data/legal_hindi_terms.json so the
model uses Bar-standard phrasing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


_GLOSSARY_PATH = Path(__file__).resolve().parent.parent / "data" / "legal_hindi_terms.json"


def _glossary_block() -> str:
    """Render the term dictionary as a compact two-column glossary the model
    can scan quickly. Cached at module load (file is tiny)."""
    if not _GLOSSARY_PATH.exists():
        return ""
    try:
        data = json.loads(_GLOSSARY_PATH.read_text(encoding="utf-8"))
        pairs = data.get("pairs", [])
    except Exception:
        return ""
    lines = ["GLOSSARY (Bar-standard EN↔HI legal terms — use these spellings):"]
    for p in pairs:
        lines.append(f"  {p['en']}  ↔  {p['hi']}")
    return "\n".join(lines)


_GLOSSARY = _glossary_block()


TRANSLATION_SYSTEM_PROMPT = (
    """You are a legal translator for an Indian criminal-law journal. You translate prose between English and Hindi.

DIRECTION
  - Auto-detect from input: if the input is mostly Latin script, translate English→Hindi (Devanagari).
  - If the input is mostly Devanagari, translate Hindi→English.

PRESERVATION RULES — absolute, no exceptions:
  1. Every case citation appears VERBATIM in the output, in the SAME script.
     Examples: "(2019) 4 SCC 1", "AIR 1999 SC 3762", "2014 Cri.L.J. 4350", "2023 INSC 839"
  2. Every paragraph anchor appears VERBATIM:
     "(Para 14)", "(Paras 16-17)", "Para 42", "para 153"
  3. Every section reference appears VERBATIM, in Hindu-Arabic numerals (NEVER Devanagari numerals):
     "Section 482 CrPC", "S. 138 NI Act", "Section 103 BNS", "Article 21"
  4. Statute names with year stay in English form:
     "Negotiable Instruments Act, 1881", "Indian Penal Code, 1860", "Bharatiya Nyaya Sanhita, 2023"
  5. Case party names (e.g. "Dashrath Rupsingh Rathod v. State of Maharashtra"):
     - Keep "v." in the citation
     - Keep proper-noun names in original script unless commonly known by a Hindi spelling
       (e.g. "Supreme Court" → "सर्वोच्च न्यायालय" is fine; "Dashrath Rupsingh" stays in Latin)
  6. Latin legal terms stay verbatim in Latin: ratio decidendi, obiter dicta, mens rea, actus reus, prima facie, suo motu, ex parte, in limine.
  7. Bar-standard Hindi terms from the glossary below take precedence over generic Devanagari renderings.

OUTPUT
  - Return ONLY the translated text. No preamble, no notes, no "Translation:" prefix, no explanations.
  - Preserve the original paragraph breaks and structure.
  - If a piece of input is already in the target language, return it unchanged.

"""
    + _GLOSSARY
)


# Stricter retry prompt — used when verifier finds a must-preserve token
# was dropped or altered in the first attempt.
def build_strict_retry_prompt(missing_tokens: Iterable[str]) -> str:
    """Build a focused retry prompt that names the exact tokens that must
    appear verbatim. Used after the first attempt drops a citation/anchor/section.
    """
    must_list = "\n".join(f"  • {t}" for t in missing_tokens)
    return (
        TRANSLATION_SYSTEM_PROMPT
        + "\n\n---\n\nRETRY — your previous attempt dropped or altered these tokens. "
        "Each MUST appear character-for-character in your output:\n\n"
        + must_list
        + "\n\nRe-translate the input below. The translation must contain each of the above tokens verbatim."
    )
