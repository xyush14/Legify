"""Meta Cloud API (WhatsApp Business) provider.

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api

Env vars
--------
WA_PHONE_NUMBER_ID   Meta's ID for the bot's outgoing phone number
WA_ACCESS_TOKEN      System User permanent token (or temp dev token)
WA_APP_SECRET        FB App Secret — HMAC verifies inbound webhooks
WA_API_VERSION       Graph API version, default "v20.0"
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Any

import requests
from fastapi import HTTPException

from . import InboundMessage, WAClientError

log = logging.getLogger(__name__)


def _base_url() -> str:
    api_version = os.getenv("WA_API_VERSION", "v20.0")
    phone_id = os.environ["WA_PHONE_NUMBER_ID"]
    return f"https://graph.facebook.com/{api_version}/{phone_id}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['WA_ACCESS_TOKEN']}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------- outbound

def send_text(to: str, body: str, *, preview_url: bool = False) -> dict[str, Any]:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to.lstrip("+"),
        "type": "text",
        "text": {"preview_url": preview_url, "body": body},
    }
    r = requests.post(f"{_base_url()}/messages", json=payload, headers=_headers(), timeout=15)
    if not r.ok:
        log.warning("meta send_text failed: %s %s", r.status_code, r.text)
        raise WAClientError(r.status_code, r.text)
    return r.json()


def send_document(to: str, pdf_path: Path, *, caption: str | None = None,
                   filename: str | None = None) -> dict[str, Any]:
    media_id = _upload_media(pdf_path, mime="application/pdf")
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to.lstrip("+"),
        "type": "document",
        "document": {"id": media_id, "filename": filename or pdf_path.name},
    }
    if caption:
        payload["document"]["caption"] = caption
    r = requests.post(f"{_base_url()}/messages", json=payload, headers=_headers(), timeout=20)
    if not r.ok:
        log.warning("meta send_document failed: %s %s", r.status_code, r.text)
        raise WAClientError(r.status_code, r.text)
    return r.json()


def _upload_media(path: Path, *, mime: str) -> str:
    url = f"{_base_url()}/media"
    headers = {"Authorization": f"Bearer {os.environ['WA_ACCESS_TOKEN']}"}
    with path.open("rb") as fh:
        files = {"file": (path.name, fh, mime)}
        data = {"messaging_product": "whatsapp", "type": mime}
        r = requests.post(url, headers=headers, files=files, data=data, timeout=30)
    if not r.ok:
        log.warning("meta upload_media failed: %s %s", r.status_code, r.text)
        raise WAClientError(r.status_code, r.text)
    media_id = r.json().get("id")
    if not media_id:
        raise WAClientError(r.status_code, "no media_id in response")
    return media_id


# ---------------------------------------------------------------- media download

def download_media(url: str) -> tuple[bytes, str]:
    """Fetch inbound media from Meta and normalise its content-type so the OCR
    layer always sees a format it accepts.

    Meta's webhook gives us a media *id*, not a URL. parse_webhook() encodes it
    as "media_id:<id>". Resolving it is a two-step Graph API dance:

      1. GET /{media_id}                -> JSON {url, mime_type, ...}
      2. GET <that url> (Bearer token)  -> the binary bytes

    Both calls require the WA_ACCESS_TOKEN bearer. The lookup URL is
    short-lived and host-locked, so we fetch immediately.

    Returns (bytes, content_type). Mirrors twilio.download_media()'s
    HEIC→JPEG normalisation so iPhone photos survive.
    """
    api_version = os.getenv("WA_API_VERSION", "v20.0")
    token = os.environ["WA_ACCESS_TOKEN"]
    auth = {"Authorization": f"Bearer {token}"}

    media_id = url[len("media_id:"):] if url.startswith("media_id:") else url

    # Step 1 — resolve the id to a signed, short-lived download URL.
    meta_resp = requests.get(
        f"https://graph.facebook.com/{api_version}/{media_id}",
        headers=auth,
        timeout=20,
    )
    if not meta_resp.ok:
        raise WAClientError(meta_resp.status_code, meta_resp.text)
    info = meta_resp.json()
    dl_url = info.get("url")
    mime = (info.get("mime_type") or "").split(";", 1)[0].strip()
    if not dl_url:
        raise WAClientError(meta_resp.status_code, "no media url in Graph response")

    # Step 2 — download the bytes (Bearer required even on the CDN URL).
    bin_resp = requests.get(dl_url, headers=auth, timeout=30, allow_redirects=True)
    if not bin_resp.ok:
        raise WAClientError(bin_resp.status_code, bin_resp.text)
    data = bin_resp.content
    if not data:
        raise WAClientError(204, "Meta returned an empty media body")

    # Fall back to the response header if Graph didn't report a mime.
    if not mime:
        mime = (bin_resp.headers.get("content-type") or "").split(";", 1)[0].strip()

    # Normalise HEIC/HEIF (iPhone default) to JPEG so OCR/vision accepts it.
    if mime in ("image/heic", "image/heif") or data[4:12] in (b"ftypheic", b"ftypheix", b"ftyphevc", b"ftypmif1"):
        try:
            import io
            import pillow_heif  # type: ignore
            from PIL import Image

            pillow_heif.register_heif_opener()
            img = Image.open(io.BytesIO(data)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            data = buf.getvalue()
            mime = "image/jpeg"
        except Exception:  # noqa: BLE001 — keep raw bytes; caller sniffs
            log.warning("HEIC->JPEG conversion failed; passing raw meta media through")

    return data, (mime or "application/octet-stream")


# ---------------------------------------------------------------- inbound

def verify_signature(raw: bytes, headers: dict, url: str) -> None:
    """Meta signs payloads with HMAC-SHA256 of the raw body using WA_APP_SECRET.

    `url` is unused for Meta (Twilio needs it). Kept for interface parity.
    """
    secret = os.environ.get("WA_APP_SECRET", "")
    if not secret:
        log.warning("WA_APP_SECRET unset — accepting unsigned webhook (dev only)")
        return
    header = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256")
    if not header or not header.startswith("sha256="):
        raise HTTPException(status_code=403, detail="missing meta signature")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, header):
        raise HTTPException(status_code=403, detail="bad meta signature")


def parse_webhook(raw: bytes, content_type: str) -> list[InboundMessage]:
    """Flatten Meta's nested envelope into a list of InboundMessage."""
    try:
        payload = json.loads(raw)
    except Exception:
        return []

    out: list[InboundMessage] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                msg_type = msg.get("type", "unknown")
                wa_phone = msg.get("from", "")
                if wa_phone and not wa_phone.startswith("+"):
                    wa_phone = "+" + wa_phone   # Meta strips the +, we canonicalize
                body = ""
                if msg_type == "text":
                    body = (msg.get("text") or {}).get("body", "") or ""
                media_urls: list[str] = []
                if msg_type in ("image", "document", "audio", "video"):
                    media_id = (msg.get(msg_type) or {}).get("id")
                    if media_id:
                        media_urls.append(f"media_id:{media_id}")
                out.append(InboundMessage(
                    wa_phone=wa_phone,
                    body=body,
                    msg_type=msg_type,
                    provider_msg_id=msg.get("id", ""),
                    media_urls=media_urls,
                    raw=msg,
                ))
    return out
