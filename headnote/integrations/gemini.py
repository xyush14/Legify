"""Gemini Flash — vision OCR + structuring for the Matters diary.

A photographed handwritten court cause-list page (म.प्र. विधि वार्षिकी) is a ruled
table whose columns collapse into one run-on line when OCR'd to flat text. Gemini
Flash reads the image DIRECTLY, preserving the columns, and returns structured rows
in a single call — cheaper and more accurate on Devanagari handwriting than the
Sarvam-DI-text → LLM path. Enabled only when GEMINI_API_KEY is set; callers fall
back to Sarvam + DeepSeek when it's absent, so nothing breaks locally.

REST (generativelanguage.googleapis.com) via httpx — no extra SDK dependency.
Docs: https://ai.google.dev/api/generate-content
"""

from __future__ import annotations

import base64
import json
import re

import httpx

from headnote import config

_BASE = "https://generativelanguage.googleapis.com/v1beta"


def enabled() -> bool:
    return bool(config.GEMINI_API_KEY)


def generate_json(prompt: str, *, image: bytes | None = None,
                  mime: str = "image/jpeg", model: str = "",
                  images: list[tuple[bytes, str]] | None = None,
                  max_tokens: int = 8192, temperature: float = 0.0) -> dict:
    """Call Gemini with an optional inline image, force a JSON response, and return
    the parsed object. Raises RuntimeError on any failure so the caller can fall
    back.

    Pass `images` (a list of (bytes, mime) pairs) instead of `image` for a
    multi-page document: every page goes in ONE call so the model can reconcile
    fields that span pages — a bail order's cause-title on page 1 with the
    operative direction on page 4. `image` remains for single-page callers.
    """
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    model = model or config.GEMINI_VISION_MODEL
    parts: list = [{"text": prompt}]
    for data, mt in (images or []):
        parts.append({"inline_data": {"mime_type": mt,
                                      "data": base64.b64encode(data).decode()}})
    if image:
        parts.append({"inline_data": {"mime_type": mime,
                                      "data": base64.b64encode(image).decode()}})
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    url = f"{_BASE}/models/{model}:generateContent"
    r = httpx.post(url, params={"key": config.GEMINI_API_KEY}, json=body, timeout=120.0)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")
    data = r.json() or {}
    cands = data.get("candidates") or []
    if not cands:
        raise RuntimeError(f"Gemini: no candidates ({json.dumps(data)[:200]})")
    parts_out = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts_out if isinstance(p, dict)).strip()
    if not text:
        raise RuntimeError("Gemini: empty response")
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001 — responseMimeType=json should prevent this
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise RuntimeError(f"Gemini: non-JSON response: {text[:200]}")


def generate_text(prompt: str, *, images: list[tuple[bytes, str]] | None = None,
                  system: str = "", model: str = "", max_tokens: int = 8192,
                  temperature: float = 0.0) -> str:
    """Call Gemini with optional inline images and return plain text.

    The sibling of ``generate_json`` for work whose output is prose, not a
    record: reading a page verbatim, or translating one. Multiple images go in
    one call so a multi-page document keeps its reading order and the model can
    resolve a word on page 2 from its use on page 1.
    """
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    model = model or config.GEMINI_VISION_MODEL
    parts: list = []
    for data, mime in (images or []):
        parts.append({"inline_data": {"mime_type": mime,
                                      "data": base64.b64encode(data).decode()}})
    parts.append({"text": prompt})
    body: dict = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    r = httpx.post(f"{_BASE}/models/{model}:generateContent",
                   params={"key": config.GEMINI_API_KEY}, json=body, timeout=180.0)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")
    cands = (r.json() or {}).get("candidates") or []
    if not cands:
        raise RuntimeError("Gemini: no candidates returned")
    out = "".join(p.get("text", "") for p in
                  ((cands[0].get("content") or {}).get("parts") or [])
                  if isinstance(p, dict)).strip()
    if not out:
        raise RuntimeError("Gemini: empty response")
    return out
