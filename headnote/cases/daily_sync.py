"""The daily court sweep — re-read every matter from the court, once a day.

Why this exists
---------------
Everything needed to keep a lawyer's diary correct was already here: the CNR
adapter returns parties, advocates, judge, acts and sections, FIR details,
interim orders, IAs, stage/purpose and the next hearing date; `courtsync` diffs
that against what we stored. But nothing ever *ran* it. A matter was read once
at import and then never again, so the moment a court gave a new date the diary
silently went stale — and because the diary groups strictly by next hearing
date, a matter whose date had passed stopped appearing on any day at all.

That is the whole of "the cases are not getting fetched": not that we cannot
read the court record, but that we only ever read it once.

Runs at 18:00 IST (see /admin/cron/sync-court-dates) — the hour a lawyer is
back from court and about to look at tomorrow.

Design rules
------------
  • One matter's failure is one matter's failure. Every fetch is caught, so an
    unreachable case never sinks the sweep.
  • Only matters with a real CNR are fetched; a hand-entered diary matter has
    no court identifier and is skipped, counted, and reported.
  • Sequential with a small pause between calls. The vendor sits behind
    Cloudflare and this runs on a single shared vCPU beside the web server —
    a burst of parallel requests would risk both a rate-limit and the health
    check that has already taken this site down twice.
  • `dry_run` reports exactly what it would do and touches nothing.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from headnote import config
from headnote.cases import courtsync
from headnote.cases import dateutil as case_dates
from headnote.cases import ecourts_client
from headnote.cases import storage as cases_storage
from headnote.entitlements import _supabase

log = logging.getLogger(__name__)

# Politeness gap between vendor calls, seconds. The sweep is a background job —
# nobody is waiting on it, so there is no reason to be aggressive.
_GAP = float(getattr(config, "COURT_SYNC_GAP_SEC", 0.35) or 0.35)

# Stop before a runaway job burns the whole vendor quota in one night.
_MAX_CALLS = int(getattr(config, "COURT_SYNC_MAX_CALLS", 2000) or 2000)


def _chunks(n: int) -> int:
    """Vendor calls a cause-list batch of `n` CNRs costs."""
    size = ecourts_client._CAUSELIST_CHUNK
    return (n + size - 1) // size if n else 0


def _user_ids(only_user_id: Optional[str] = None) -> list[str]:
    """Every lawyer we might have matters for.

    Raises rather than returning [] on failure: an empty list is indistinguishable
    from "swept everyone, nothing to do", and a sweep that reports success while
    touching nobody is how a diary rots for a month before anyone notices.
    """
    if only_user_id:
        return [only_user_id]
    rows = _supabase.select("user_profiles",
                            params={"select": "id", "limit": "2000"}) or []
    return [r["id"] for r in rows if r.get("id")]


def sync_all_dockets(*, dry_run: bool = False, only_user_id: Optional[str] = None,
                     max_calls: int = _MAX_CALLS) -> dict:
    """Re-read every matter that has a CNR, for every lawyer.

    Returns a summary the cron caller can log or alert on. Never raises.
    """
    live = (config.CNR_API_MODE or "").lower() == "live"
    if not live:
        # Say so loudly rather than reporting a successful no-op: a sweep that
        # silently does nothing is how a diary goes stale for months.
        return {"ok": False, "reason": "CNR_API_MODE is not 'live' — nothing was synced",
                "dry_run": dry_run, "users": 0, "matters": 0, "synced": 0,
                "changed": 0, "skipped_no_cnr": 0, "failed": 0, "updates": []}

    try:
        users = _user_ids(only_user_id)
    except Exception as e:  # noqa: BLE001
        log.warning("court sweep could not list users: %s", e)
        return {"ok": False, "reason": f"could not list users: {str(e)[:200]}",
                "dry_run": dry_run, "users": 0, "matters": 0, "listed": 0, "synced": 0,
                "changed": 0, "skipped_no_cnr": 0, "failed": 0, "calls": 0, "updates": []}
    if not users:
        # Say it. "0 users" reported as success looks identical to a healthy
        # sweep in a log, and hides a broken Supabase read for as long as nobody
        # checks whether any date actually moved.
        log.warning("court sweep found NO users — nothing was swept")
        return {"ok": False, "reason": "no users found — nothing was swept",
                "dry_run": dry_run, "users": 0, "matters": 0, "listed": 0, "synced": 0,
                "changed": 0, "skipped_no_cnr": 0, "failed": 0, "calls": 0, "updates": []}

    calls = 0
    matters = listed = synced = changed = skipped = failed = 0
    changes: list[dict] = []
    preview: list[dict] = []

    for uid in users:
        try:
            rows = cases_storage.list_cases(user_id=uid, limit=500) or []
        except Exception as e:  # noqa: BLE001
            log.warning("court sweep could not list matters for %s: %s", uid, e)
            continue

        with_cnr = [c for c in rows if len((c.get("cnr") or "").strip()) == 16]
        matters += len(rows)
        skipped += len(rows) - len(with_cnr)

        if dry_run:
            preview.extend({"user_id": uid, "case_id": c["id"], "cnr": c["cnr"],
                            "next_hearing_date": c.get("next_hearing_date")}
                           for c in with_cnr)
            calls += _chunks(len(with_cnr))
            continue

        # ---- PASS 1: the court's own cause list, in ONE call per 50 matters.
        # Cheaper AND fresher than re-reading every case file: the case record's
        # next date is only as new as the last time that file was written, while
        # the cause list is the board the court is actually sitting on — and it
        # alone carries the court number, the item/serial and the judge.
        listings: dict = {}
        if calls < max_calls and with_cnr:
            try:
                listings = ecourts_client.fetch_causelist_batch(
                    [c["cnr"].strip() for c in with_cnr])
                calls += _chunks(len(with_cnr))
            except Exception as e:  # noqa: BLE001
                log.warning("cause list failed for %s: %s", uid, e)

        # Which matters the court has actually moved. Compared BEFORE anything is
        # written, so pass 2 knows what is worth a full read.
        on_board = [(c, listings[c["cnr"].strip()])
                    for c in with_cnr if listings.get((c.get("cnr") or "").strip())]
        moved = [(c, l) for c, l in on_board
                 if case_dates.to_iso(l.get("date")) != case_dates.to_iso(c.get("next_hearing_date"))]

        # ---- PASS 2: a full case read ONLY for matters whose listing moved.
        # That is where stage, orders and IAs are worth re-reading; spending a
        # call on a matter the court has not touched buys nothing.
        for case, _listing in moved:
            if calls >= max_calls:
                log.warning("court sweep hit the %s-call ceiling; stopping early", max_calls)
                break
            # the cause list already settled the date for this matter
            res = courtsync.sync_case(case, uid, trust_listing=True)
            calls += 1
            if res.get("ok"):
                synced += 1
            else:
                failed += 1
            if _GAP:
                time.sleep(_GAP)

        # ---- PASS 3: the cause list is applied LAST, and therefore WINS.
        # This ordering is the whole point and it is easy to get backwards: the
        # full case read carries the case FILE's next date, which is only as
        # fresh as the last time that file was written. Applying it after the
        # cause list overwrote the court's own board with a stale date and threw
        # away the court number, item and judge — observed doing exactly that.
        for case, listing in on_board:
            row = cases_storage.get_case(case["id"], user_id=uid) or case
            res = courtsync.apply_listing(row, listing, uid)
            if res.get("ok"):
                listed += 1
                if res.get("updates"):
                    changed += 1
                    changes.append({"user_id": uid, "case_id": case["id"],
                                    "cnr": case["cnr"], "updates": res["updates"],
                                    "source": "causelist"})
            else:
                failed += 1

        if calls >= max_calls:
            break

    out = {
        "ok": True, "dry_run": dry_run,
        "users": len(users), "matters": matters,
        "listed": listed,            # matters found on a court cause list
        "synced": synced,            # matters given a full re-read
        "changed": changed,
        "skipped_no_cnr": skipped, "failed": failed,
        "calls": calls,
        # what actually moved — the reason to look at the app tomorrow
        "updates": changes[:50],
    }
    if dry_run:
        out["preview"] = preview[:50]
    log.info("court sweep: %s", {k: v for k, v in out.items()
                                 if k not in ("updates", "preview")})
    return out
