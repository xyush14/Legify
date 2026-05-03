"""
Free Hindi translation — no API key, no LLM cost.

Uses deep-translator (Google Translate web endpoint) under the hood. We:
  1. Walk the result JSON.
  2. Translate only specific prose fields (relevance_explanation, ratio, gist…),
     leaving all citations, statute references, paragraph anchors, case_ids,
     and other technical fields untouched.
  3. Inside each prose field, replace citations / section refs / case names with
     placeholder tokens before translation, then restore the originals after.
     This protects them from being mangled or transliterated by the translator.

The output JSON has the SAME structure and the SAME keys as input — only the
prose values change. This matches the user's requirement of "word-to-word
translation without reframing our output & structure".

Fallback: if Google Translate fails (rate limit, network), the original
English text is returned for that field.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from deep_translator import GoogleTranslator, MyMemoryTranslator
from deep_translator.exceptions import TranslationNotFound, RequestError


# ---------- which JSON fields contain prose to translate ----------

TRANSLATABLE_FIELDS: set[str] = {
    "relevance_explanation",
    "bns_note",
    "ratio",
    "negative_carve_out",
    "gist",
    "one_line_topic",
    "quotable_phrase",
    "heading",
    "summary_takeaway",
    "no_match_reason",
    "facts",
    "holding",
    "topic",  # (digest mode normalises the lawyer's topic into this field)
}


# ---------- placeholder protection (citations, sections, case names) ----------

# Regexes for things that must NOT be translated: citations, statute refs,
# paragraph anchors, year refs, etc. Order matters — most specific first.
PROTECT_PATTERNS = [
    # Parallel citations like "(2014) 9 SCC 129", "(2014) 2 SCC Cri 241"
    re.compile(r"\(\d{4}\)\s*\d+\s*SCC(?:\s*Cri)?\s*\d+", re.IGNORECASE),
    re.compile(r"\(\d{4}\)\s*\d+\s*Cri\.?\s*L\.?\s*J\.?\s*\d+", re.IGNORECASE),
    # AIR-style: "AIR 1999 SC 3762", "AIR 2014 SC 3673"
    re.compile(r"\bAIR\s+\d{4}\s+\w+\s+\d+", re.IGNORECASE),
    # SCC OnLine: "2022 SCC OnLine SC 929"
    re.compile(r"\d{4}\s+SCC\s+OnLine\s+\w+\s+\d+", re.IGNORECASE),
    # Cri.L.J. style: "2014 Cri.L.J. 4350", "1992 Cri.L.J. 527"
    re.compile(r"\d{4}\s+Cri\.?\s*L\.?\s*J\.?\s+\d+", re.IGNORECASE),
    # SCW: "2014 AIR SCW 5477"
    re.compile(r"\d{4}\s+AIR\s+SCW\s+\d+", re.IGNORECASE),
    # INSC: "2023 INSC 839"
    re.compile(r"\d{4}\s+INSC\s+\d+", re.IGNORECASE),
    # Paragraph anchors: "(Para 14)", "(Paras 16, 17)", "(Paras 33-34, 37-39)"
    re.compile(r"\(Paras?\s+[\d\s,\-–]+\)", re.IGNORECASE),
    # Section refs: "S. 138", "Ss. 138, 142", "S. 3(1)(r)", "S. 376(2)(g)"
    re.compile(r"\bSs?\.\s*\d+[\d\w\(\)\.\-]*"),
    # Article refs: "Article 21", "Art. 22(1)"
    re.compile(r"\bArt(?:icle)?\.?\s*\d+(?:\([\w]+\))?"),
    # Standalone famous-statute shorthand: "BNS S. 103", "BNSS S. 482", "IPC", "CrPC", "BNS", "BSA", "PMLA", "UAPA", "NDPS", "POCSO", "NI Act"
    re.compile(r"\b(?:BNS|BNSS|BSA|IPC|CrPC|PMLA|UAPA|NDPS|POCSO|FIR|ECIR|SC-ST|NI\s+Act|MIRA)\b"),
    # "v." case-title separator (preserve so we can identify case names)
    re.compile(r"\bv\.\s*"),
]

# Build dynamic protect list from the corpus — every case title is added so
# it's never transliterated. Loaded lazily.
_corpus_titles_cache: list[str] | None = None


def _load_corpus_titles() -> list[str]:
    global _corpus_titles_cache
    if _corpus_titles_cache is not None:
        return _corpus_titles_cache
    try:
        cases = json.loads(
            (Path(__file__).parent / "cases.json").read_text(encoding="utf-8")
        )
        titles = [c["title"] for c in cases if "title" in c]
        # Sort longest first so we match the most specific name before partials
        titles.sort(key=len, reverse=True)
        _corpus_titles_cache = titles
    except Exception:
        _corpus_titles_cache = []
    return _corpus_titles_cache


def protect(text: str) -> tuple[str, list[str]]:
    """Replace all protected substrings with `<<N>>` placeholders.

    Returns (text_with_placeholders, list_of_originals_indexed_by_N).
    """
    if not text:
        return text, []

    originals: list[str] = []

    def take_placeholder(match: re.Match) -> str:
        idx = len(originals)
        originals.append(match.group(0))
        return f"<<{idx}>>"

    out = text
    # Case titles first (string-match, not regex), longest first
    for title in _load_corpus_titles():
        if title in out:
            idx = len(originals)
            originals.append(title)
            out = out.replace(title, f"<<{idx}>>")

    # Then patterns
    for pat in PROTECT_PATTERNS:
        out = pat.sub(take_placeholder, out)

    return out, originals


def restore(text: str, originals: list[str]) -> str:
    """Restore `<<N>>` (and minor variants) to originals."""
    if not text or not originals:
        return text
    out = text
    for i, original in enumerate(originals):
        # Try the canonical form first, then common mangled variants that
        # Google Translate sometimes produces around angle-bracket placeholders.
        for variant in (
            f"<<{i}>>",
            f"<< {i}>>",
            f"<<{i} >>",
            f"<< {i} >>",
            f"< <{i}> >",
            f"<{i}>",  # rare, last-resort
        ):
            if variant in out:
                out = out.replace(variant, original)
                break
    return out


# ---------- translation ----------

def _try_google(text: str, target: str) -> str | None:
    try:
        out = GoogleTranslator(source="en", target=target).translate(text)
        return out if out else None
    except Exception:
        return None


# MyMemory uses regional codes — map common targets.
_MYMEMORY_TARGET = {"hi": "hi-IN"}


def _try_mymemory(text: str, target: str) -> str | None:
    try:
        out = MyMemoryTranslator(
            source="en-GB",
            target=_MYMEMORY_TARGET.get(target, target),
        ).translate(text)
        return out if out else None
    except Exception:
        return None


def _translate_string(text: str, target: str = "hi") -> str:
    """Translate one prose string with provider fallback chain.

    Order: Google Translate → MyMemory → original English.
    Citations / case names are protected via placeholder substitution.
    """
    if not text or not text.strip():
        return text
    protected, originals = protect(text)

    # Try Google first (best quality, free, may rate-limit)
    out = _try_google(protected, target)
    if out is None:
        time.sleep(0.3)
        # MyMemory fallback (free, separate rate limit, slightly weaker)
        out = _try_mymemory(protected, target)

    if out is None:
        # Both providers failed — return original English so user sees something
        return text

    return restore(out, originals)


def translate_payload(obj: Any, target: str = "hi") -> Any:
    """Recursively translate prose fields in obj, preserving structure."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k in TRANSLATABLE_FIELDS and isinstance(v, str):
                out[k] = _translate_string(v, target)
            else:
                out[k] = translate_payload(v, target)
        return out
    if isinstance(obj, list):
        return [translate_payload(item, target) for item in obj]
    return obj
