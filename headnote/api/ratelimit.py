"""Dependency-free, in-memory, per-IP rate limiter for public endpoints.

Used by the anonymous `POST /api/try` "taste the product" endpoint so a
single visitor can't hammer the (cheap but non-free) retrieval path.

Design
------
- Sliding-window log: per IP we keep the UNIX timestamps of recent hits and
  drop anything older than `window_seconds`. A request is allowed iff the
  number of hits still inside the window is < `max_requests`.
- Async-safe: all mutation happens under a single `asyncio.Lock`, so it is
  safe to call from FastAPI async/sync request handlers running on the event
  loop. (FastAPI runs sync handlers in a threadpool; `check()` is async and is
  awaited on the event loop, so there is no cross-thread race on the dict.)
- Self-pruning: each `check()` opportunistically evicts IPs whose entire
  window has expired, so memory stays bounded even under churny traffic.

IMPORTANT (scale): this state lives in THIS PROCESS ONLY (a plain dict). With
multiple workers / instances each process keeps its own counter, so the
effective global limit is `max_requests * num_processes`. For real multi-
instance scale this must move to a shared store (e.g. Redis with INCR + EXPIRE
or a sorted-set sliding window). Good enough for a single-worker launch.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional


def client_ip_from_request(request) -> str:
    """Best-effort client IP for rate-limiting keys.

    Prefers the FIRST hop in `X-Forwarded-For` (the original client when the
    app sits behind a proxy / load balancer such as Railway/Render), falling
    back to the direct socket peer. Never raises.
    """
    try:
        xff = request.headers.get("x-forwarded-for")
    except Exception:
        xff = None
    if xff:
        # "client, proxy1, proxy2" — the left-most entry is the origin client.
        first = xff.split(",")[0].strip()
        if first:
            return first
    try:
        if request.client and request.client.host:
            return request.client.host
    except Exception:
        pass
    return "unknown"


class RateLimitResult:
    """Outcome of a limiter check.

    allowed         — whether this request may proceed.
    remaining       — requests still permitted in the current window AFTER this
                      one (0 when blocked).
    retry_after     — seconds until at least one slot frees up (only meaningful
                      when blocked; 0 otherwise).
    """

    __slots__ = ("allowed", "remaining", "retry_after")

    def __init__(self, allowed: bool, remaining: int, retry_after: int):
        self.allowed = allowed
        self.remaining = remaining
        self.retry_after = retry_after


class InMemoryRateLimiter:
    """Per-key sliding-window limiter. Keys are typically client IPs."""

    def __init__(self, max_requests: int = 5, window_seconds: int = 3600):
        self.max_requests = int(max_requests)
        self.window_seconds = int(window_seconds)
        # key -> list[float] of hit timestamps (kept sorted/ascending by append)
        self._hits: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str, *, now: Optional[float] = None) -> RateLimitResult:
        """Record-and-check one request for `key`.

        If the request is within budget it is recorded and `allowed=True`.
        If it would exceed the budget NOTHING is recorded and `allowed=False`
        with a `retry_after` hint.
        """
        if now is None:
            now = time.time()
        cutoff = now - self.window_seconds

        async with self._lock:
            # Opportunistic global prune so idle keys don't accumulate forever.
            if len(self._hits) > 4096:
                self._prune(cutoff)

            timestamps = self._hits.get(key)
            if timestamps is None:
                timestamps = []
                self._hits[key] = timestamps

            # Drop expired hits for this key.
            if timestamps and timestamps[0] <= cutoff:
                kept = [t for t in timestamps if t > cutoff]
                timestamps[:] = kept

            if len(timestamps) >= self.max_requests:
                # Blocked. Oldest hit governs when a slot next opens up.
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + self.window_seconds - now) + 1)
                return RateLimitResult(False, 0, retry_after)

            # Allowed — record this hit.
            timestamps.append(now)
            if not self._hits.get(key):
                # paranoia: ensure the key is present
                self._hits[key] = timestamps
            remaining = max(0, self.max_requests - len(timestamps))
            return RateLimitResult(True, remaining, 0)

    def _prune(self, cutoff: float) -> None:
        """Evict keys whose entire window has expired. Caller holds the lock."""
        dead = [k for k, ts in self._hits.items() if not ts or ts[-1] <= cutoff]
        for k in dead:
            self._hits.pop(k, None)
