"""WhatsApp provider implementations.

Each provider module exposes the same surface:

    send_text(to: str, body: str, **kw) -> dict
    send_document(to: str, pdf_path: Path, *, caption=None, filename=None) -> dict
    verify_signature(raw: bytes, headers: dict, url: str) -> None  # raises HTTPException on bad sig
    parse_webhook(raw: bytes, content_type: str) -> list[InboundMessage]

`to` is in canonical E.164 form WITH leading "+" (e.g. "+919876543210").
Provider modules adapt to their wire format internally.

Currently implemented:
- meta    — Meta Cloud API direct (PRD §6 primary plan; gated by FB Business Verification)
- twilio  — Twilio WhatsApp Sandbox (dev/test bypass; no business verification needed)
"""
from dataclasses import dataclass


class WAClientError(RuntimeError):
    """Shared error type so callers don't need provider-specific catches."""
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"WA API {status}: {body[:300]}")
        self.status = status
        self.body = body


@dataclass
class InboundMessage:
    """Normalized inbound message shape, independent of provider."""
    wa_phone: str           # canonical E.164 with leading "+"
    body: str               # text body (empty for non-text)
    msg_type: str           # "text" | "image" | "document" | "audio" | ...
    provider_msg_id: str    # provider's unique message id (for dedupe)
    media_urls: list[str]   # provider-fetchable URLs for any media (Twilio) or media_ids (Meta)
    raw: dict               # full raw payload for debugging
