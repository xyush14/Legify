"""Runs the daily court sweep at a fixed time, inside the app process.

Why in-process rather than an external cron
-------------------------------------------
The whole product runs on ONE Fly machine with one shared vCPU. Adding a second
scheduled machine would mean a second copy of the SQLite volume, and an external
cron service is one more account, one more secret, and one more thing to be
silently broken for a month. A sleeping asyncio task costs nothing and is
restored automatically on every restart.

Two rules this file exists to obey, both learnt from outages
------------------------------------------------------------
1. **Never do the work on the event loop.** The sweep is blocking HTTP against
   the eCourts vendor. Run on the loop, it would stall `/api/live` — the Fly
   health check — and Fly would pull the ONE machine out of the routing pool
   while the app was perfectly healthy. That is exactly how headnote.in went
   down on 2026-08-04 and again on 2026-08-07. So the sweep runs in a worker
   thread and the loop stays free to answer probes.
2. **Never let it kill the app.** Every iteration is wrapped; a vendor outage,
   a bad row or a raised exception costs one night's sweep, not the site.

Off by default. Set COURT_SYNC_SCHEDULE=1 to arm it, and unset it to disarm
without a deploy.

  COURT_SYNC_SCHEDULE   "1" to enable (default off)
  COURT_SYNC_AT_UTC     "HH:MM" UTC, default "12:30" = 18:00 IST
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

_TRUE = {"1", "true", "yes", "on"}

# How often we wake to check the clock. Deliberately coarse: this is a once-a-day
# job, and a tight loop on a shared vCPU is a cost with no benefit.
_TICK_SEC = 60


def enabled() -> bool:
    return str(os.environ.get("COURT_SYNC_SCHEDULE", "")).strip().lower() in _TRUE


def _target_hm() -> tuple[int, int]:
    """(hour, minute) in UTC. 12:30 UTC = 18:00 IST — the hour a lawyer is back
    from court and about to look at tomorrow."""
    raw = str(os.environ.get("COURT_SYNC_AT_UTC", "12:30")).strip()
    try:
        h, m = raw.split(":")
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except Exception:  # noqa: BLE001
        pass
    log.warning("COURT_SYNC_AT_UTC=%r is not HH:MM — falling back to 12:30", raw)
    return 12, 30


def _next_run(after: datetime, hour: int, minute: int) -> datetime:
    """The next occurrence of hour:minute UTC strictly after `after`."""
    cand = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if cand <= after:
        cand += timedelta(days=1)
    return cand


def _run_sweep() -> dict:
    """The blocking part. Called on a worker thread, never on the loop."""
    from headnote.cases.daily_sync import sync_all_dockets
    return sync_all_dockets()


async def _loop() -> None:
    hour, minute = _target_hm()
    now = datetime.now(timezone.utc)
    nxt = _next_run(now, hour, minute)
    log.info("court sweep scheduled daily at %02d:%02d UTC; first run %s",
             hour, minute, nxt.isoformat())

    while True:
        try:
            await asyncio.sleep(_TICK_SEC)
            now = datetime.now(timezone.utc)
            if now < nxt:
                continue
            nxt = _next_run(now, hour, minute)      # book the next one FIRST, so a
                                                    # failure cannot cause a hot loop
            log.info("court sweep starting (scheduled)")
            res = await asyncio.to_thread(_run_sweep)
            log.info("court sweep finished: %s",
                     {k: v for k, v in (res or {}).items()
                      if k not in ("updates", "preview")})
        except asyncio.CancelledError:
            log.info("court sweep scheduler stopped")
            raise
        except Exception as e:  # noqa: BLE001 — one bad night, not a dead app
            log.exception("court sweep scheduler iteration failed: %s", e)


_task: asyncio.Task | None = None


def start() -> bool:
    """Arm the scheduler. Safe to call more than once. Returns True if armed."""
    global _task
    if not enabled():
        log.info("court sweep scheduler is OFF (set COURT_SYNC_SCHEDULE=1 to arm)")
        return False
    if _task and not _task.done():
        return True
    try:
        _task = asyncio.get_running_loop().create_task(_loop())
    except RuntimeError:
        log.warning("court sweep scheduler needs a running event loop; not started")
        return False
    return True


def status() -> dict:
    hour, minute = _target_hm()
    running = bool(_task and not _task.done())
    now = datetime.now(timezone.utc)
    nxt = _next_run(now, hour, minute)
    ist = (nxt + timedelta(hours=5, minutes=30))     # let timedelta carry the hour
    return {
        "enabled": enabled(),
        "running": running,
        "at_utc": f"{hour:02d}:{minute:02d}",
        "at_ist": ist.strftime("%H:%M"),
        "next_run_utc": nxt.isoformat() if running else None,
    }
