"""Provider facade — picks the WhatsApp backend based on env.

Set WA_PROVIDER=twilio (default for dev) or WA_PROVIDER=meta (for prod
once FB Business Verification clears). Both providers expose the same
surface; this facade dispatches.

Concrete provider modules: headnote/whatsapp/providers/{meta,twilio}.py
"""
from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType
from typing import Any

from headnote.whatsapp.providers import (
    InboundMessage,
    WAClientError,
    meta as _meta,
    twilio as _twilio,
)

_REGISTRY: dict[str, ModuleType] = {"meta": _meta, "twilio": _twilio}


def _resolve(name: str | None = None) -> ModuleType:
    key = (name or os.getenv("WA_PROVIDER", "twilio")).lower()
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        raise RuntimeError(f"unknown WA_PROVIDER: {key!r} (expected one of {list(_REGISTRY)})") from exc


def provider_for(name: str | None = None) -> ModuleType:
    """Public accessor — webhook routes pass their provider name explicitly
    so inbound-via-Twilio always replies via Twilio regardless of env."""
    return _resolve(name)


# ---------------------------------------------------------------- outbound facade


def send_text(to: str, body: str, *, provider: str | None = None, **kwargs: Any) -> dict[str, Any]:
    return _resolve(provider).send_text(to, body, **kwargs)


def send_document(to: str, pdf_path: Path, *, provider: str | None = None, **kwargs: Any) -> dict[str, Any]:
    return _resolve(provider).send_document(to, pdf_path, **kwargs)


__all__ = ["send_text", "send_document", "WAClientError", "provider_for", "InboundMessage"]
