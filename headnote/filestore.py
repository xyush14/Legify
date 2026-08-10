"""Durable file storage for uploads whose bytes cannot be regenerated.

Most bytes in Headnote are derived — page images and embeddings can be rebuilt
from an upload, so they live in the local cache. A CLIENT-uploaded original is
different: the client will not send it again, so it is the only copy and it must
survive a deploy. That is what this module is for.

Two backends behind one interface:
  • Supabase Storage, a PRIVATE bucket, when Supabase is configured. Files are
    never publicly readable; the lawyer previews them through a short-lived
    signed URL.
  • The local disk under KANOON_CACHE_PATH's directory, for local dev, so the
    flow works with no cloud setup.

`delete()` really deletes. When a lawyer discards a client's document, "discard"
has to mean gone — not a hidden row.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

import httpx

import headnote.config as config          # loads .env before _supabase binds
from headnote.entitlements import _supabase

log = logging.getLogger(__name__)

BUCKET = os.environ.get("INTAKE_BUCKET", "client-intake")
_ROOT = "storage/v1"
_bucket_ready = False


def enabled() -> bool:
    return _supabase._enabled()


def _base() -> str:
    return f"{_supabase.SUPABASE_URL}/{_ROOT}"


def _local_dir() -> Path:
    d = Path(config.KANOON_CACHE_PATH).parent / "intake_files"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_bucket() -> bool:
    """Create the private bucket on first use. Idempotent; a 409 means it exists."""
    global _bucket_ready
    if _bucket_ready or not enabled():
        return _bucket_ready
    try:
        r = httpx.post(f"{_base()}/bucket", headers=_supabase._headers(),
                       json={"id": BUCKET, "name": BUCKET, "public": False},
                       timeout=15.0)
        if r.status_code < 400 or r.status_code == 409:
            _bucket_ready = True
        else:
            log.warning("could not ensure bucket %s: %s %s", BUCKET, r.status_code, r.text[:140])
    except Exception as e:  # noqa: BLE001
        log.warning("bucket check failed: %s", e)
    return _bucket_ready


def put(path: str, data: bytes, *, mime: str = "application/octet-stream") -> Optional[str]:
    """Store bytes at `path`. Returns the stored path, or None if it did not land."""
    if not data:
        return None
    if enabled() and ensure_bucket():
        try:
            r = httpx.post(f"{_base()}/object/{BUCKET}/{path}",
                           headers={**_supabase._headers(), "Content-Type": mime,
                                    "x-upsert": "true"},
                           content=data, timeout=60.0)
            if r.status_code < 400:
                return path
            log.error("storage put failed %s: %s %s", path, r.status_code, r.text[:160])
        except Exception as e:  # noqa: BLE001
            log.error("storage put error %s: %s", path, e)
        return None
    # local dev
    try:
        f = _local_dir() / path.replace("/", "__")
        f.write_bytes(data)
        return path
    except Exception as e:  # noqa: BLE001
        log.error("local file write failed: %s", e)
        return None


def get(path: str) -> Optional[bytes]:
    if enabled():
        try:
            r = httpx.get(f"{_base()}/object/{BUCKET}/{path}",
                          headers=_supabase._headers(), timeout=60.0)
            if r.status_code < 400:
                return r.content
        except Exception as e:  # noqa: BLE001
            log.error("storage get error %s: %s", path, e)
        return None
    f = _local_dir() / path.replace("/", "__")
    return f.read_bytes() if f.exists() else None


def signed_url(path: str, *, seconds: int = 300) -> Optional[str]:
    """A short-lived URL for the lawyer's preview. The bucket stays private."""
    if not enabled():
        return None
    try:
        r = httpx.post(f"{_base()}/object/sign/{BUCKET}/{path}",
                       headers=_supabase._headers(), json={"expiresIn": seconds},
                       timeout=15.0)
        if r.status_code < 400:
            rel = (r.json() or {}).get("signedURL") or ""
            return f"{_supabase.SUPABASE_URL}/{_ROOT}{rel}" if rel.startswith("/") else rel
    except Exception as e:  # noqa: BLE001
        log.warning("sign url failed %s: %s", path, e)
    return None


def delete(path: str) -> bool:
    """Actually remove the object — 'discard' must mean gone."""
    if enabled():
        try:
            r = httpx.delete(f"{_base()}/object/{BUCKET}/{path}",
                             headers=_supabase._headers(), timeout=30.0)
            return r.status_code < 400
        except Exception as e:  # noqa: BLE001
            log.warning("storage delete failed %s: %s", path, e)
            return False
    f = _local_dir() / path.replace("/", "__")
    try:
        if f.exists():
            f.unlink()
        return True
    except Exception:  # noqa: BLE001
        return False
