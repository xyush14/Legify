"""Thin Supabase REST wrapper used by the entitlements layer.

Why not supabase-py? It pulls in postgrest-py, gotrue, realtime, storage —
none of which we need server-side. A 40-line httpx wrapper is enough.

Access pattern: backend uses the SERVICE_ROLE_KEY which bypasses RLS, so all
selects/upserts succeed regardless of policies. Never expose this key to the
frontend.
"""

from __future__ import annotations

import json as _json
import logging
import os
from typing import Any

import httpx


log = logging.getLogger(__name__)


SUPABASE_URL = os.environ.get("SUPABASE_URL")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")


def _enabled() -> bool:
    return bool(SUPABASE_URL and SERVICE_ROLE_KEY)


def _headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_ROLE_KEY or "",
        "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def select(table: str, *, params: dict[str, str] | None = None) -> list[dict]:
    """GET /rest/v1/<table>?<params> — returns parsed JSON list."""
    if not _enabled():
        log.warning("supabase select skipped: SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set")
        return []
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        r = httpx.get(url, headers=_headers(), params=params or {}, timeout=5.0)
        r.raise_for_status()
        return r.json() or []
    except httpx.HTTPError as e:
        log.error("supabase select %s failed: %s", table, e)
        return []


def upsert(table: str, payload: dict | list[dict], *, on_conflict: str | None = None) -> list[dict]:
    """POST /rest/v1/<table> with Prefer: resolution=merge-duplicates."""
    if not _enabled():
        return []
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = _headers()
    headers["Prefer"] = "return=representation,resolution=merge-duplicates"
    params = {"on_conflict": on_conflict} if on_conflict else None
    try:
        r = httpx.post(
            url, headers=headers, params=params,
            content=_json.dumps(payload), timeout=5.0,
        )
        r.raise_for_status()
        return r.json() or []
    except httpx.HTTPError as e:
        log.error("supabase upsert %s failed: %s", table, e)
        return []


def update(table: str, payload: dict, *, params: dict[str, str]) -> list[dict]:
    """PATCH /rest/v1/<table>?<filter> — filter required to prevent mass update."""
    if not _enabled() or not params:
        return []
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        r = httpx.patch(
            url, headers=_headers(), params=params,
            content=_json.dumps(payload), timeout=5.0,
        )
        r.raise_for_status()
        return r.json() or []
    except httpx.HTTPError as e:
        log.error("supabase update %s failed: %s", table, e)
        return []


def rpc(fn_name: str, payload: dict | None = None) -> Any:
    """Call a Postgres function via POST /rest/v1/rpc/<fn_name>."""
    if not _enabled():
        return None
    url = f"{SUPABASE_URL}/rest/v1/rpc/{fn_name}"
    try:
        r = httpx.post(
            url, headers=_headers(),
            content=_json.dumps(payload or {}), timeout=5.0,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        log.error("supabase rpc %s failed: %s", fn_name, e)
        return None
