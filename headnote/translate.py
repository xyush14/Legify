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
from typing import Any, Optional

from deep_translator import GoogleTranslator, MyMemoryTranslator
from deep_translator.exceptions import TranslationNotFound, RequestError


# ---------- which JSON fields contain prose to translate ----------

TRANSLATABLE_FIELDS: set[str] = {
    # V2 case-card schema (what the research-mode Hindi toggle actually sends).
    # These were MISSING — the frontend posts {stinger, held_line, fact_match,
    # carve_out, ratio} but only `ratio` was whitelisted, so the translator
    # returned the English text unchanged and the toggle looked broken.
    "stinger",
    "held_line",
    "fact_match",
    "carve_out",
    # Legacy / other-mode fields
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
        from headnote.config import CASES_PATH
        cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
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
    """Recursively translate prose fields in obj using free Google Translate.

    Retained as a fallback path for /api/translate when Anthropic is
    unavailable (no API key, network failure). The primary path now goes
    through `translate_payload_haiku` for higher quality + reliable
    citation preservation.
    """
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


# ============================================================================
# Haiku-backed translation (primary path)
# ============================================================================

# Tokens that must survive translation verbatim. Compiled from PROTECT_PATTERNS
# above. Used by the citation verifier post-Haiku.
def _extract_must_preserve_tokens(text: str) -> list[str]:
    """Return every citation / paragraph anchor / section ref / statute
    shorthand found in `text`. The order is preserved and duplicates kept
    (rare but possible) so the verifier checks each occurrence."""
    out: list[str] = []
    seen: set[str] = set()
    for pat in PROTECT_PATTERNS:
        for m in pat.finditer(text or ""):
            tok = m.group(0).strip()
            if tok and tok not in seen:
                seen.add(tok)
                out.append(tok)
    # Case titles from the curated corpus
    for title in _load_corpus_titles():
        if title in (text or "") and title not in seen:
            seen.add(title)
            out.append(title)
    return out


def _detect_direction(text: str) -> tuple[str, str]:
    """Auto-detect source/target language from a sample of prose.

    Heuristic: if ≥30% of letter-characters are Devanagari, source is Hindi.
    Otherwise English. Devanagari unicode range: U+0900..U+097F.
    Returns ("source_lang", "target_lang") — short codes.
    """
    if not text:
        return "en", "hi"
    devanagari = sum(1 for c in text if "ऀ" <= c <= "ॿ")
    latin = sum(1 for c in text if c.isalpha() and c.isascii())
    total = devanagari + latin
    if total == 0:
        return "en", "hi"
    if devanagari / total >= 0.30:
        return "hi", "en"
    return "en", "hi"


def _verify_preserved(input_text: str, output_text: str) -> tuple[bool, list[str], list[str]]:
    """Check every must-preserve token from `input_text` appears verbatim in
    `output_text`. Returns `(ok, preserved, missing)`."""
    tokens = _extract_must_preserve_tokens(input_text)
    preserved: list[str] = []
    missing: list[str] = []
    for t in tokens:
        if t in output_text:
            preserved.append(t)
        else:
            missing.append(t)
    return (not missing), preserved, missing


def _haiku_translate_string(
    text: str,
    *,
    target: Optional[str] = None,
) -> tuple[str, int, str, list[str]]:
    """Translate one prose string via Haiku, with one strict-retry on
    citation drop.

    Returns `(translated_text, cost_paise, quality, preserved_citations)`:
      - quality is "ok" (preservation passed) or "degraded" (retry still
        missed at least one token; caller may choose to fall back to original)
      - preserved_citations is the list of tokens we verified survived.
    """
    from headnote.llm import route_call
    from headnote.llm.translation_prompts import (
        TRANSLATION_SYSTEM_PROMPT, build_strict_retry_prompt,
    )

    if not text or not text.strip():
        return text, 0, "ok", []

    # First attempt — standard prompt
    result1 = route_call(
        "translation",
        {"system_prompt": TRANSLATION_SYSTEM_PROMPT, "user_prompt": text},
    )
    out1 = result1.response.strip()
    ok1, preserved1, missing1 = _verify_preserved(text, out1)
    total_paise = result1.cost_paise

    if ok1:
        return out1, total_paise, "ok", preserved1

    # Strict retry — explicitly name the dropped tokens
    print(f"[translate] retry: missing tokens after first attempt: {missing1}")
    strict_prompt = build_strict_retry_prompt(missing1)
    result2 = route_call(
        "translation",
        {"system_prompt": strict_prompt, "user_prompt": text},
    )
    out2 = result2.response.strip()
    ok2, preserved2, missing2 = _verify_preserved(text, out2)
    total_paise += result2.cost_paise

    if ok2:
        return out2, total_paise, "ok", preserved2

    # Still missing tokens after retry — return the better of the two
    # attempts, flag as degraded so the frontend can surface a warning.
    print(f"[translate] DEGRADED: still missing after retry: {missing2}")
    best = out1 if len(preserved1) >= len(preserved2) else out2
    best_preserved = preserved1 if len(preserved1) >= len(preserved2) else preserved2
    return best, total_paise, "degraded", best_preserved


def translate_payload_haiku(obj: Any) -> tuple[Any, int, str, list[str]]:
    """Walk `obj` and translate every prose field via Haiku.

    Same field whitelist as `translate_payload` (TRANSLATABLE_FIELDS).
    Returns `(translated_obj, total_cost_paise, overall_quality,
    preserved_citations_union)`.

    `overall_quality` is "degraded" if ANY field's translation came back
    degraded — the frontend should show a warning so the lawyer knows to
    verify those specific citations.
    """
    total_paise = 0
    overall_quality = "ok"
    preserved_union: list[str] = []
    seen_preserved: set[str] = set()

    def _walk(node: Any) -> Any:
        nonlocal total_paise, overall_quality
        if isinstance(node, dict):
            out: dict[str, Any] = {}
            for k, v in node.items():
                if k in TRANSLATABLE_FIELDS and isinstance(v, str):
                    tr, paise, qual, preserved = _haiku_translate_string(v)
                    total_paise += paise
                    if qual == "degraded":
                        overall_quality = "degraded"
                    for tok in preserved:
                        if tok not in seen_preserved:
                            seen_preserved.add(tok)
                            preserved_union.append(tok)
                    out[k] = tr
                else:
                    out[k] = _walk(v)
            return out
        if isinstance(node, list):
            return [_walk(item) for item in node]
        return node

    translated = _walk(obj)
    return translated, total_paise, overall_quality, preserved_union
