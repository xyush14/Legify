"""Twilio WhatsApp provider (Sandbox + production).

Docs: https://www.twilio.com/docs/whatsapp/api

Why: Twilio's sandbox bypasses Meta's Business Verification gauntlet —
sign up, text "join <code>" from your WhatsApp to the sandbox number,
and you're talking to the API in 5 minutes. We use Twilio for dev /
soft-launch, switch to Meta direct at scale (PRD §6).

Env vars
--------
TWILIO_ACCOUNT_SID    starts with "AC..."
TWILIO_AUTH_TOKEN     used for HTTP Basic auth + webhook signature verify
TWILIO_WA_FROM        sandbox number, e.g. "whatsapp:+14155238886"
                      (omit "whatsapp:" prefix and we'll add it)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import requests
from fastapi import HTTPException

from . import InboundMessage, WAClientError

log = logging.getLogger(__name__)


def _account_sid() -> str:
    # .strip() defends against trailing newlines/spaces from Railway/Render
    # paste — without this, the SID gets embedded into the URL with a \n
    # and Twilio responds 404.
    return os.environ["TWILIO_ACCOUNT_SID"].strip()


def _auth_token() -> str:
    return os.environ["TWILIO_AUTH_TOKEN"].strip()


def _from_number() -> str:
    raw = os.environ["TWILIO_WA_FROM"].strip()
    return raw if raw.startswith("whatsapp:") else f"whatsapp:{raw}"


def _to_wa(to: str) -> str:
    """Canonical "+E.164" → Twilio's "whatsapp:+E.164" format."""
    to = to.strip()
    if to.startswith("whatsapp:"):
        return to
    if not to.startswith("+"):
        to = "+" + to
    return f"whatsapp:{to}"


def _messages_url() -> str:
    return f"https://api.twilio.com/2010-04-01/Accounts/{_account_sid()}/Messages.json"


# ---------------------------------------------------------------- outbound

def send_text(to: str, body: str, *, preview_url: bool = False) -> dict[str, Any]:
    # Twilio doesn't expose preview_url toggle — links auto-preview in WA UI.
    data = {
        "To": _to_wa(to),
        "From": _from_number(),
        "Body": body,
    }
    r = requests.post(
        _messages_url(),
        data=data,
        auth=(_account_sid(), _auth_token()),
        timeout=15,
    )
    if not r.ok:
        log.warning("twilio send_text failed: %s %s", r.status_code, r.text)
        raise WAClientError(r.status_code, r.text)
    return r.json()


def send_document(to: str, pdf_path: Path, *, caption: str | None = None,
                   filename: str | None = None) -> dict[str, Any]:
    """Twilio fetches the file from a public URL we provide.

    Unlike Meta's two-step upload, Twilio expects MediaUrl pointing to a
    URL its servers can reach. The caller is responsible for hosting the
    PDF (e.g. /api/whatsapp/media/<token>) and passing a usable URL.

    For Phase 1 we don't ship PDFs yet — this function will be wired
    once we have a public PDF-serving endpoint. See PRD Phase 2.
    """
    public_url = os.environ.get("TWILIO_WA_MEDIA_BASE_URL")
    if not public_url:
        raise WAClientError(0, "TWILIO_WA_MEDIA_BASE_URL not configured — cannot send media via Twilio")

    # Caller stages the PDF under public_url; we just reference it.
    # In practice, send_document() will be called with a pre-staged URL,
    # not a local path — interface kept for parity with meta.py.
    raise NotImplementedError(
        "Twilio media send is staged behind a public URL endpoint that "
        "lands in Phase 2. Use send_text() for Phase 1 echo."
    )


# ---------------------------------------------------------------- inbound

def verify_signature(raw: bytes, headers: dict, url: str) -> None:
    """Twilio signs each webhook with HMAC-SHA1 of the full URL plus a
    concatenation of sorted POST-parameter key/value pairs, base64-encoded.

    `url` MUST be the EXACT public webhook URL Twilio called (scheme, host,
    path, no query string differences). Mismatch → signature failure.

    Sandbox messages CAN ship without a configured signature when
    TWILIO_AUTH_TOKEN isn't set; we log and accept. Production must set it.

    Behind reverse proxies (Railway, Cloudflare, etc.) `request.url` often
    differs from the public URL Twilio actually signed against, which would
    fail verification on every real call. Two escape hatches:
      1. Set TWILIO_WEBHOOK_URL to the exact public URL configured in Twilio.
      2. Set TWILIO_SKIP_SIGNATURE_VERIFY=1 to bypass verification entirely
         (sandbox / dev only — re-enable for production).
    """
    if os.environ.get("TWILIO_SKIP_SIGNATURE_VERIFY", "").strip().lower() in ("1", "true", "yes"):
        log.warning("TWILIO_SKIP_SIGNATURE_VERIFY=1 — accepting unverified webhook")
        return
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not token:
        log.warning("TWILIO_AUTH_TOKEN unset — accepting unsigned webhook (dev only)")
        return
    sig = headers.get("x-twilio-signature") or headers.get("X-Twilio-Signature")
    if not sig:
        raise HTTPException(status_code=403, detail="missing twilio signature")

    # Twilio sends form-encoded body — parse to sorted key+value concat
    params = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    flat = {k: v[0] for k, v in params.items()}
    payload_str = url
    for k in sorted(flat.keys()):
        payload_str += k + flat[k]
    expected = base64.b64encode(
        hmac.new(token.encode(), payload_str.encode(), hashlib.sha1).digest()
    ).decode()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=403, detail="bad twilio signature")


def parse_webhook(raw: bytes, content_type: str) -> list[InboundMessage]:
    """Twilio webhooks are form-encoded. One message per request."""
    if "application/x-www-form-urlencoded" not in (content_type or ""):
        log.warning("unexpected twilio content-type: %s", content_type)
    params = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    f = {k: v[0] for k, v in params.items()}

    raw_from = f.get("From", "")              # "whatsapp:+91987..."
    wa_phone = raw_from.removeprefix("whatsapp:").strip()
    if wa_phone and not wa_phone.startswith("+"):
        wa_phone = "+" + wa_phone

    body = f.get("Body", "") or ""
    num_media = int(f.get("NumMedia", "0") or "0")
    msg_type = "text"
    media_urls: list[str] = []
    media_types: list[str] = []
    if num_media > 0:
        ct0 = f.get("MediaContentType0", "")
        if ct0.startswith("image/"):
            msg_type = "image"
        elif ct0 == "application/pdf":
            msg_type = "document"
        elif ct0.startswith("audio/"):
            msg_type = "audio"
        else:
            msg_type = "media"
        for i in range(num_media):
            url = f.get(f"MediaUrl{i}")
            ct = f.get(f"MediaContentType{i}", "")
            if url:
                # Encode content type into URL fragment so it survives transport
                # without changing the InboundMessage shape.
                media_urls.append(url + (f"#ct={ct}" if ct else ""))
                media_types.append(ct)
    elif not body:
        msg_type = "unknown"

    return [InboundMessage(
        wa_phone=wa_phone,
        body=body,
        msg_type=msg_type,
        provider_msg_id=f.get("MessageSid", ""),
        media_urls=media_urls,
        raw=f,
    )]


# Magic-byte signatures for the file types lawyers actually send via
# WhatsApp. Order matters — longer prefixes first.
_MAGIC_TO_MIME: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff",                 "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n",            "image/png"),
    (b"GIF87a",                       "image/gif"),
    (b"GIF89a",                       "image/gif"),
    (b"RIFF",                         "image/webp"),     # second check needed for WEBP/WAVE
    (b"%PDF-",                        "application/pdf"),
    (b"II*\x00",                      "image/tiff"),
    (b"MM\x00*",                      "image/tiff"),
)


def _sniff_mime(data: bytes) -> str:
    """Identify the file type from its first few bytes. Returns '' if unknown."""
    if not data:
        return ""
    for sig, mime in _MAGIC_TO_MIME:
        if data.startswith(sig):
            if mime == "image/webp":
                # RIFF prefix is shared with WAV; verify WEBP marker at offset 8
                if data[8:12] == b"WEBP":
                    return "image/webp"
                continue
            return mime
    # HEIC/HEIF: ISO-BMFF box "ftyp" at offset 4, brand starts at 8
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx",
                     b"mif1", b"msf1", b"heif"):
            return "image/heic"
    return ""


# MIME types our OCR providers (Groq / Anthropic vision) accept directly.
# Anything else gets normalised to JPEG before it reaches OCR.
_OCR_NATIVE_MIME = {
    "image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf",
}


def _normalise_for_ocr(data: bytes, mime: str) -> tuple[bytes, str]:
    """Convert formats OCR can't read (HEIC, HEIF, TIFF, BMP) → JPEG. PDFs +
    common image types pass through unchanged. Falls back to raw bytes on
    conversion failure so the caller can still try."""
    if mime in _OCR_NATIVE_MIME:
        return data, mime
    needs_conv = mime in ("image/heic", "image/heif", "image/tiff", "image/bmp", "image/x-icon")
    if not needs_conv:
        return data, mime

    try:
        import io
        from PIL import Image
        # HEIC needs the pillow-heif decoder registered with Pillow.
        if mime in ("image/heic", "image/heif"):
            try:
                from pillow_heif import register_heif_opener
                register_heif_opener()
            except Exception:
                log.warning(
                    "pillow-heif not installed — falling back to raw HEIC; "
                    "OCR will likely reject it"
                )
                return data, mime
        img = Image.open(io.BytesIO(data))
        # JPEG can't carry alpha — drop it.
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=92, optimize=True)
        log.info("normalise_for_ocr: %s → image/jpeg (%d → %d bytes)",
                 mime, len(data), out.tell())
        return out.getvalue(), "image/jpeg"
    except Exception:
        log.exception("normalise_for_ocr failed for %s; passing raw bytes", mime)
        return data, mime


def download_media(url: str) -> tuple[bytes, str]:
    """Fetch a Twilio media file (HTTP Basic auth required) and normalise
    its content-type so the OCR layer always sees a format it accepts.

    Pipeline:
      1. GET (auth + follow Twilio→S3 redirect)
      2. Pick content-type: Twilio response header > URL fragment > URL
         extension > magic-byte sniff. Last-write wins for accuracy.
      3. If HEIC/HEIF, convert to JPEG via Pillow + pillow-heif.

    Returns (bytes, content_type) where content_type is one of
    'image/jpeg' | 'image/png' | 'image/webp' | 'image/gif' |
    'image/tiff' | 'application/pdf' (or whatever Twilio sent if all
    detection fails — caller decides whether OCR will accept it).
    """
    import re as _re

    base = url.split("#", 1)[0]
    fragment_ct = ""
    m = _re.search(r"#ct=([^&]+)", url)
    if m:
        fragment_ct = m.group(1)

    r = requests.get(
        base,
        auth=(_account_sid(), _auth_token()),
        timeout=30,
        allow_redirects=True,                  # Twilio → S3 (signed URL)
    )
    if not r.ok:
        raise WAClientError(r.status_code, r.text)

    data = r.content
    if not data:
        raise WAClientError(204, "Twilio returned an empty media body")

    # ── Content-type detection — fall through if any step is missing ──
    ct = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not ct or ct in ("application/octet-stream", "binary/octet-stream"):
        ct = fragment_ct.lower()
    if not ct or ct in ("application/octet-stream", "binary/octet-stream"):
        # try URL extension
        path = base.split("?", 1)[0].lower()
        for ext, m in (
            (".jpg", "image/jpeg"), (".jpeg", "image/jpeg"),
            (".png", "image/png"),  (".gif", "image/gif"),
            (".webp", "image/webp"), (".heic", "image/heic"),
            (".heif", "image/heif"), (".pdf", "application/pdf"),
            (".tiff", "image/tiff"), (".tif", "image/tiff"),
        ):
            if path.endswith(ext):
                ct = m
                break
    if not ct or ct in ("application/octet-stream", "binary/octet-stream"):
        sniffed = _sniff_mime(data)
        if sniffed:
            ct = sniffed

    # Normalise to a format OCR can read (HEIC, TIFF, BMP → JPEG)
    data, ct = _normalise_for_ocr(data, ct)

    if not ct:
        # Last resort: default to JPEG (the most common WhatsApp media)
        ct = "image/jpeg"
        log.warning("download_media: unknown content-type, defaulting to image/jpeg")

    return data, ct
