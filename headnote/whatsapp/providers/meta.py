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
