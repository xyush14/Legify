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


# ------------------------------------------------------------------ transport
#
# ONE pooled client for the whole process, instead of httpx's module-level
# convenience functions.
#
# `httpx.get(...)` builds a brand new Client, opens a fresh TCP connection and
# does a full TLS handshake for EVERY call, then throws the connection away.
# Supabase is a network hop away, so that handshake — not the query — was most
# of the cost of talking to the database. Measured against the live project:
#
#     new client per call : 611 ms per request
#     pooled client       : 259 ms per request
#
# Painting Home costs several of these calls, and every page load costs several
# more before it even gets there, so the handshakes alone were seconds of the
# advocate's wait. Keep-alive removes them entirely after the first call.
#
# Thread-safe: httpx.Client is safe to share across threads, which matters
# because FastAPI runs these sync endpoints in a worker threadpool.
_client: httpx.Client | None = None


def _http() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            # Comfortably above the handful of threads FastAPI runs sync
            # endpoints on, so a request never waits for a free connection.
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=40,
                                keepalive_expiry=60.0),
            # Per-request timeouts are still passed explicitly at each call
            # site; this is only the floor for anything that forgets.
            timeout=10.0,
            follow_redirects=True,
        )
    return _client


def close() -> None:
    """Release the pooled connections (used by tests and shutdown hooks)."""
    global _client
    if _client is not None:
        try:
            _client.close()
        finally:
            _client = None


def _headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_ROLE_KEY or "",
        "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


class SupabaseError(RuntimeError):
    """A request failed at the transport or HTTP level.

    Raised ONLY by the *_or_raise helpers. The plain select/upsert/update/delete
    below keep their log-and-return-[] behaviour, which is right for
    entitlements: there, a miss and a failure both mean "assume no entitlement".

    It is wrong for a write. `[]` from update() is indistinguishable from a
    successful PATCH that matched no rows, so a save that never reached the
    database looks exactly like a save with nothing to do. Callers that must
    tell the difference use the raising variants.

    `status` is None when there was no response at all (timeout, DNS, reset).
    """

    def __init__(self, message: str, *, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body

    @property
    def transient(self) -> bool:
        """Is a retry worth anything?

        No response, a timeout, rate limiting or a server-side error can all
        succeed on the next attempt. A 400/403/404/409 is a considered answer —
        retrying just sends the same rejected request again.
        """
        if self.status is None:
            return True
        return self.status in (408, 425, 429) or self.status >= 500


def _send(method: str, table: str, *, params: dict[str, str] | None = None,
          payload: Any = None, headers: dict[str, str] | None = None,
          timeout: float = 10.0) -> list[dict]:
    """One REST call that raises on failure instead of logging it away."""
    if not _enabled():
        raise SupabaseError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        r = _http().request(
            method, url, headers=headers or _headers(), params=params,
            content=None if payload is None else _json.dumps(payload),
            timeout=timeout,
        )
    except Exception as e:  # noqa: BLE001 — httpx raises several unrelated types
        raise SupabaseError(f"{method} {table}: {e}") from e
    if r.status_code >= 400:
        raise SupabaseError(
            f"{method} {table}: HTTP {r.status_code}: {r.text[:300]}",
            status=r.status_code, body=r.text[:2000],
        )
    try:
        return r.json() or []
    except ValueError:      # 204, or a body PostgREST didn't make JSON
        return []


def upsert_or_raise(table: str, payload: dict | list[dict], *,
                    on_conflict: str | None = None,
                    timeout: float = 10.0) -> list[dict]:
    """upsert(), but a failed request raises SupabaseError.

    Returns the stored row(s): `Prefer: return=representation` means a success
    always echoes what landed, so an empty list back from a 2xx is a genuine
    oddity rather than the usual shape of an error.
    """
    headers = _headers()
    headers["Prefer"] = "return=representation,resolution=merge-duplicates"
    params = {"on_conflict": on_conflict} if on_conflict else None
    return _send("POST", table, params=params, payload=payload,
                 headers=headers, timeout=timeout)


def update_or_raise(table: str, payload: dict, *, params: dict[str, str],
                    timeout: float = 10.0) -> list[dict]:
    """update(), but a failed request raises SupabaseError.

    So the return value carries exactly one meaning: the rows that changed.
    Empty = the filter matched nothing. Anything else came back as an exception.
    """
    if not params:
        raise SupabaseError("update needs a filter — refusing to PATCH every row")
    return _send("PATCH", table, params=params, payload=payload, timeout=timeout)


def select(table: str, *, params: dict[str, str] | None = None) -> list[dict]:
    """GET /rest/v1/<table>?<params> — returns parsed JSON list."""
    if not _enabled():
        log.warning("supabase select skipped: SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set")
        return []
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        r = _http().get(url, headers=_headers(), params=params or {}, timeout=5.0)
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
        r = _http().post(
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
        r = _http().patch(
            url, headers=_headers(), params=params,
            content=_json.dumps(payload), timeout=5.0,
        )
        r.raise_for_status()
        return r.json() or []
    except httpx.HTTPError as e:
        log.error("supabase update %s failed: %s", table, e)
        return []


def delete(table: str, *, params: dict[str, str]) -> list[dict]:
    """DELETE /rest/v1/<table>?<filter> — filter required to prevent mass delete."""
    if not _enabled() or not params:
        return []
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        r = _http().delete(url, headers=_headers(), params=params, timeout=5.0)
        r.raise_for_status()
        return r.json() or []
    except httpx.HTTPError as e:
        log.error("supabase delete %s failed: %s", table, e)
        return []


def rpc(fn_name: str, payload: dict | None = None) -> Any:
    """Call a Postgres function via POST /rest/v1/rpc/<fn_name>."""
    if not _enabled():
        return None
    url = f"{SUPABASE_URL}/rest/v1/rpc/{fn_name}"
    try:
        r = _http().post(
            url, headers=_headers(),
            content=_json.dumps(payload or {}), timeout=5.0,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        log.error("supabase rpc %s failed: %s", fn_name, e)
        return None
