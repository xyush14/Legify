"""Sarvam AI translation client — Indic-native NMT with a legal/formal mode.

Why it's a strong fit for court drafts (vs raw Bhashini):
  * `mode="formal"` — Sarvam's own "professional, pure language forms" mode,
    documented as intended for official documents and legal papers.
  * `numerals_format="international"` — keeps 498, 240/2021, dates in roman
    digits instead of transliterating to Devanagari (४९८), so citations survive.
  * document/paragraph-level terminology consistency.

Still raw NMT (no free-text glossary), so we ALSO mask statute short-forms /
citations / Latin runs the same way as Bhashini, belt-and-suspenders.

API: POST https://api.sarvam.ai/translate, header `api-subscription-key`,
response field `translated_text`. Lang codes are BCP-47-ish: hi-IN, mr-IN,
bn-IN, gu-IN, en-IN.

Config (env):
    SARVAM_API_KEY      subscription key from dashboard.sarvam.ai
    SARVAM_MODEL        default "mayura:v1"
    SARVAM_MODE         default "formal"
"""
from __future__ import annotations

import logging
import os

import httpx

from headnote.drafter.i18n.tokens import mask as _mask, unmask as _unmask

log = logging.getLogger(__name__)

_URL = os.environ.get("SARVAM_URL", "https://api.sarvam.ai/translate")
_TIMEOUT = float(os.environ.get("SARVAM_TIMEOUT", "30"))
_MODEL = os.environ.get("SARVAM_MODEL", "mayura:v1")
_MODE = os.environ.get("SARVAM_MODE", "formal")

_LANG = {"hi": "hi-IN", "mr": "mr-IN", "bn": "bn-IN", "gu": "gu-IN", "en": "en-IN"}


class SarvamError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(os.environ.get("SARVAM_API_KEY"))


def _code(lang: str) -> str:
    c = _LANG.get(lang)
    if not c:
        raise SarvamError(f"Sarvam: unsupported language {lang!r}")
    return c


def translate(text: str, source_lang: str, target_lang: str) -> str:
    """Translate one segment src→tgt via Sarvam (formal mode), masking
    preserved tokens. Raises SarvamError on any failure so callers can fall back."""
    if not text or not text.strip() or source_lang == target_lang:
        return text
    key = os.environ.get("SARVAM_API_KEY", "").strip()
    if not key:
        raise SarvamError("SARVAM_API_KEY not set")

    masked, toks = _mask(text)
    body = {
        "input": masked,
        "source_language_code": _code(source_lang),
        "target_language_code": _code(target_lang),
        "model": _MODEL,
        "mode": _MODE,                       # "formal" → legal/official register
        "numerals_format": "international",   # keep 498/240 in roman digits
    }
    try:
        r = httpx.post(_URL, json=body, timeout=_TIMEOUT,
                       headers={"api-subscription-key": key,
                                "Content-Type": "application/json"})
        r.raise_for_status()
        out = r.json()["translated_text"]
    except Exception as e:
        raise SarvamError(f"Sarvam translate failed: {type(e).__name__}: {e}") from e
    return _unmask(out, toks)
