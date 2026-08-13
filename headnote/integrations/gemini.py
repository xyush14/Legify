"""Gemini Flash — vision OCR + structuring for the Matters diary.

A photographed handwritten court cause-list page (म.प्र. विधि वार्षिकी) is a
ruled table whose columns collapse into one run-on line when OCR'd to flat
text. Gemini Flash reads the image DIRECTLY, preserving the columns, and
returns structured rows in a single call — cheaper and more accurate on
Devanagari handwriting than the Sarvam-DI-text → LLM path.

Enabled only when GEMINI_API_KEY is set; callers fall back to Sarvam +
DeepSeek when it's absent, so nothing breaks locally.

REST (generativelanguage.googleapis.com) via httpx — no extra SDK dependency.
Docs: https://ai.google.dev/api/generate-content
"""

from __future__ import annotations

import base64
import json
import logging
import random
import re
import time

import httpx

from headnote import config

log = logging.getLogger(__name__)
_BASE = "https://generativelanguage.googleapis.com/v1beta"


def enabled() -> bool:
    return bool(config.GEMINI_API_KEY)


def generate_json(
    prompt: str,
    *,
    image: bytes | None = None,
    mime: str = "image/jpeg",
    model: str = "",
    max_tokens: int = 8192,
    temperature: float = 0.0,
) -> dict:
    """Call Gemini with an optional inline image, force a JSON response,
    and return the parsed object.
    """
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")

    model = model or config.GEMINI_VISION_MODEL
    log.info("Gemini JSON request start: model=%s", model)

    parts = [{"text": prompt}]
    if image:
        parts.append(
            {
                "inline_data": {
                    "mime_type": mime,
                    "data": base64.b64encode(image).decode(),
                }
            }
        )

    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }

    url = f"{_BASE}/models/{model}:generateContent"

    for attempt in range(3):
        try:
            r = httpx.post(
                url,
                params={"key": config.GEMINI_API_KEY},
                json=body,
                timeout=120.0,
            )

            if r.status_code == 200:
                break

            if r.status_code == 503 and attempt < 2:
                wait = (2 ** attempt) + random.uniform(0, 1)
                log.warning(
                    "Gemini JSON 503 (attempt %d), retrying in %.2fs",
                    attempt + 1,
                    wait,
                )
                time.sleep(wait)
                continue

            raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")

        except Exception as exc:
            if (
                attempt == 2
                or not isinstance(exc, RuntimeError)
                or "503" not in str(exc)
            ):
                r_status = getattr(locals().get("r"), "status_code", None)
                r_body = getattr(locals().get("r"), "text", None)

                log.exception(
                    "Gemini JSON request failed: "
                    "model=%s, "
                    "exception_type=%s, "
                    "exception_message=%s, "
                    "status_code=%s, "
                    "response_body=%s",
                    model,
                    type(exc).__name__,
                    str(exc),
                    r_status,
                    r_body,
                )
                raise

            continue

    data = r.json() or {}
    cands = data.get("candidates") or []

    if not cands:
        raise RuntimeError(
            f"Gemini: no candidates ({json.dumps(data)[:200]})"
        )

    parts_out = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(
        p.get("text", "")
        for p in parts_out
        if isinstance(p, dict)
    ).strip()

    if not text:
        raise RuntimeError("Gemini: empty response")

    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise RuntimeError(f"Gemini: non-JSON response: {text[:200]}")


def generate_text(
    prompt: str,
    *,
    images: list[tuple[bytes, str]] | None = None,
    system: str = "",
    model: str = "",
    max_tokens: int = 8192,
    temperature: float = 0.0,
) -> str:
    """Call Gemini with optional inline images and return plain text."""

    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")

    model = model or config.GEMINI_VISION_MODEL
    log.info("Gemini text request start: model=%s", model)

    parts = []

    for data, mime in (images or []):
        parts.append(
            {
                "inline_data": {
                    "mime_type": mime,
                    "data": base64.b64encode(data).decode(),
                }
            }
        )

    parts.append({"text": prompt})

    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }

    if system:
        body["system_instruction"] = {
            "parts": [{"text": system}]
        }

    for attempt in range(3):
        try:
            r = httpx.post(
                f"{_BASE}/models/{model}:generateContent",
                params={"key": config.GEMINI_API_KEY},
                json=body,
                timeout=180.0,
            )

            if r.status_code == 200:
                break

            if r.status_code == 503 and attempt < 2:
                wait = (2 ** attempt) + random.uniform(0, 1)
                log.warning(
                    "Gemini text 503 (attempt %d), retrying in %.2fs",
                    attempt + 1,
                    wait,
                )
                time.sleep(wait)
                continue

            raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")

        except Exception as exc:
            if (
                attempt == 2
                or not isinstance(exc, RuntimeError)
                or "503" not in str(exc)
            ):
                r_status = getattr(locals().get("r"), "status_code", None)
                r_body = getattr(locals().get("r"), "text", None)

                log.exception(
                    "Gemini text request failed: "
                    "model=%s, "
                    "exception_type=%s, "
                    "exception_message=%s, "
                    "status_code=%s, "
                    "response_body=%s",
                    model,
                    type(exc).__name__,
                    str(exc),
                    r_status,
                    r_body,
                )
                raise

            continue

    cands = (r.json() or {}).get("candidates") or []

    if not cands:
        raise RuntimeError("Gemini: no candidates returned")

    out = "".join(
        p.get("text", "")
        for p in ((cands[0].get("content") or {}).get("parts") or [])
        if isinstance(p, dict)
    ).strip()

    if not out:
        raise RuntimeError("Gemini: empty response")

    return out
