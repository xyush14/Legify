"""The daily court sweep, and the Home widening that the new diary needs.

Two things are under test:

  1. `daily_sync.sync_all_dockets` — the job that did not exist. A matter used
     to be read from the court ONCE at import and never again, so dates went
     stale and (because the diary groups by next hearing date) matters silently
     dropped out of every day. These tests pin the behaviour that matters most:
     it must actually write the new date back, it must refuse to run in mock
     mode rather than quietly doing nothing, one dead matter must not sink the
     sweep, and the call ceiling must hold.

  2. `/api/home` gaining `span=3`, per-month calendar counts, and an `overdue`
     list — the data behind "Yesterday · Today · Tomorrow", the calendar dots,
     and the banner for dates that have passed with no new date.

No network: the vendor client is stubbed everywhere.
"""

from __future__ import annotations

import pytest

from headnote import config
from headnote.cases import courtsync, daily_sync
from headnote.cases import ecourts_client


UID = "u_test_sweep"


class _Store:
    """A stand-in for cases_storage: records what the sweep writes."""

    def __init__(self, rows):
        self.rows = {r["id"]: dict(r) for r in rows}
        self.identity_writes = 0

    def list_cases(self, *, user_id, limit=500):
        return [dict(r) for r in self.rows.values()]

    def replace_case_identity(self, case_id, *, user_id, case):
        self.identity_writes += 1
        self.rows[case_id]["case_json"] = case

    def set_next_date(self, case_id, *, user_id, next_hearing_date, stage):
        if next_hearing_date:
            self.rows[case_id]["next_hearing_date"] = next_hearing_date
        if stage:
            self.rows[case_id]["stage"] = stage

    def merge_prep(self, case_id, *, user_id, prep):
        cj = dict(self.rows[case_id].get("case_json") or {})
        cj["prep"] = prep
        self.rows[case_id]["case_json"] = cj

    def get_case(self, case_id, *, user_id):
        return dict(self.rows[case_id])


def _rows(n=3, cnr_prefix="MPGW01000012202"):
    return [{"id": f"c{i}", "cnr": f"{cnr_prefix}{i}", "case_json": {},
             "next_hearing_date": "01/01/2026", "stage": "old"} for i in range(n)]


@pytest.fixture
def live(monkeypatch):
    """Pretend the vendor is configured and reachable."""
    monkeypatch.setattr(config, "CNR_API_MODE", "live", raising=False)
    monkeypatch.setattr(daily_sync, "_GAP", 0, raising=False)
    monkeypatch.setattr(daily_sync, "_user_ids", lambda only_user_id=None: [UID])


def _wire(monkeypatch, store, fetch, listings=None):
    """`listings` is the cause-list answer. The sweep leads with the batch call
    now, and only spends a full case read on matters the court actually moved —
    so a test that stubs only fetch_cnr would see the sweep do nothing at all."""
    if listings is None:
        listings = {c["cnr"]: {"date": "05/09/2026", "item": 1, "court_no": "7"}
                    for c in store.rows.values() if c.get("cnr")}
    monkeypatch.setattr(ecourts_client, "fetch_causelist_batch", lambda cnrs: dict(listings))
    monkeypatch.setattr(daily_sync, "ecourts_client", ecourts_client, raising=False)
    monkeypatch.setattr(daily_sync, "cases_storage", store, raising=False)
    monkeypatch.setattr("headnote.cases.storage.replace_case_identity",
                        store.replace_case_identity, raising=False)
    monkeypatch.setattr("headnote.cases.storage.set_next_date",
                        store.set_next_date, raising=False)
    monkeypatch.setattr("headnote.cases.storage.merge_prep",
                        getattr(store, "merge_prep", lambda *a, **k: None), raising=False)
    monkeypatch.setattr("headnote.cases.storage.get_case",
                        store.get_case, raising=False)
    monkeypatch.setattr(ecourts_client, "fetch_cnr", fetch)
    monkeypatch.setattr(ecourts_client, "is_valid_cnr", lambda c: len(c or "") == 16)


# ------------------------------------------------------------------ the sweep

def test_sweep_writes_the_new_date_back(monkeypatch, live):
    """The whole point: a date given by the court must reach the diary."""
    store = _Store(_rows(2))
    _wire(monkeypatch, store,
          lambda cnr: {"cnr": cnr, "next_hearing_date": "05/09/2026", "stage": "final"})

    res = daily_sync.sync_all_dockets(only_user_id=UID)

    assert res["ok"] and res["failed"] == 0
    assert res["listed"] == 2 and res["synced"] == 2
    for row in store.rows.values():
        assert row["next_hearing_date"] == "05/09/2026"
        assert row["stage"] == "final"


def test_sweep_reports_what_changed(monkeypatch, live):
    store = _Store(_rows(1))
    _wire(monkeypatch, store,
          lambda cnr: {"cnr": cnr, "next_hearing_date": "05/09/2026", "stage": "final"})

    res = daily_sync.sync_all_dockets(only_user_id=UID)

    assert res["changed"] == 1
    kinds = {u["kind"] for u in res["updates"][0]["updates"]}
    assert "next_date" in kinds


def test_mock_mode_refuses_loudly_instead_of_doing_nothing(monkeypatch):
    """A sweep that silently no-ops is how a diary rots for months. In mock mode
    the adapter returns the SAME fixture for every CNR, so running it would also
    overwrite real matters with someone else's parties."""
    monkeypatch.setattr(config, "CNR_API_MODE", "mock", raising=False)
    res = daily_sync.sync_all_dockets()
    assert res["ok"] is False
    assert "not 'live'" in res["reason"]
    assert res["synced"] == 0


def test_one_dead_matter_does_not_sink_the_sweep(monkeypatch, live):
    store = _Store(_rows(4))
    calls = {"n": 0}

    def flaky(cnr):
        calls["n"] += 1
        if calls["n"] % 2 == 0:
            raise RuntimeError("vendor 502 request blocked")
        return {"cnr": cnr, "next_hearing_date": "05/09/2026"}

    _wire(monkeypatch, store, flaky)
    res = daily_sync.sync_all_dockets(only_user_id=UID)

    assert res["ok"] is True
    # the cause list listed all four; the full read is what half-failed
    assert res["listed"] == 4
    assert res["synced"] == 2 and res["failed"] == 2
    assert res["matters"] == 4          # every matter was still attempted


def test_matters_without_a_cnr_are_skipped_not_failed(monkeypatch, live):
    rows = _rows(2) + [{"id": "hand", "cnr": "", "case_json": {},
                        "next_hearing_date": "01/01/2026", "stage": None}]
    store = _Store(rows)
    _wire(monkeypatch, store, lambda cnr: {"cnr": cnr, "next_hearing_date": "05/09/2026"})

    res = daily_sync.sync_all_dockets(only_user_id=UID)

    assert res["skipped_no_cnr"] == 1
    assert res["failed"] == 0
    assert store.rows["hand"]["next_hearing_date"] == "01/01/2026"


def test_call_ceiling_stops_a_runaway_sweep(monkeypatch, live):
    store = _Store(_rows(10))
    _wire(monkeypatch, store, lambda cnr: {"cnr": cnr, "next_hearing_date": "05/09/2026"})

    res = daily_sync.sync_all_dockets(only_user_id=UID, max_calls=3)

    assert res["calls"] <= 3


def test_dry_run_touches_nothing(monkeypatch, live):
    store = _Store(_rows(3))
    _wire(monkeypatch, store, lambda cnr: {"cnr": cnr, "next_hearing_date": "05/09/2026"})

    res = daily_sync.sync_all_dockets(only_user_id=UID, dry_run=True)

    assert res["dry_run"] is True and res["synced"] == 0
    assert store.identity_writes == 0
    for row in store.rows.values():
        assert row["next_hearing_date"] == "01/01/2026"


def test_button_and_sweep_share_one_implementation(monkeypatch):
    """The per-file sync button and the nightly sweep must never drift — a
    lawyer comparing them would have no way to tell which one was lying. So the
    route must DELEGATE, not carry its own copy of the logic."""
    from headnote.api import notesheets

    seen = {}

    def spy(case, user_id):
        seen["case"] = case
        seen["user_id"] = user_id
        return {"id": case["id"], "ok": True, "updates": []}

    monkeypatch.setattr(notesheets.courtsync, "sync_case", spy)
    out = notesheets._sync_one({"id": "c1", "cnr": "X" * 16}, UID)

    assert out["ok"] is True
    assert seen["user_id"] == UID and seen["case"]["id"] == "c1"


def test_sync_case_refuses_a_matter_with_no_fetchable_cnr(monkeypatch):
    monkeypatch.setattr(config, "CNR_API_MODE", "live", raising=False)
    res = courtsync.sync_case({"id": "x", "cnr": "", "case_json": {}}, UID)
    assert res["ok"] is False and "no fetchable CNR" in res["reason"]


# --------------------------------------------------- Home: the diary's new data

def _home_client(rows):
    """A TestClient over just /api/home, with storage and the beta gate stubbed."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from headnote.api import notesheets as ns
    from headnote.entitlements import CurrentUser

    app = FastAPI()
    app.include_router(ns.router)
    app.dependency_overrides[ns.require_beta] = lambda: CurrentUser(
        id=UID, email="t@t.in", role="authenticated", raw_claims={"sub": UID})

    class _S:
        def list_cases(self, *, user_id, limit=500):
            return [dict(r) for r in rows]
    ns.cases_storage = _S()
    ns.ns_storage.list_for_date = lambda uid, d: set()
    return TestClient(app)


def _case(cid, dmy):
    return {"id": cid, "cnr": "X" * 16, "case_title": f"A vs B {cid}",
            "court_name": "Court", "case_number": "1", "case_year": "2026",
            "stage": None, "next_hearing_date": dmy, "case_json": {}}


def test_span_3_returns_three_boards(monkeypatch):
    monkeypatch.setattr("headnote.api.notesheets._today_iso", lambda: "2026-08-08")
    c = _home_client([_case("a", "07/08/2026"), _case("b", "08/08/2026"),
                      _case("c", "09/08/2026"), _case("d", "20/09/2026")])
    d = c.get("/api/home?date=2026-08-08&span=3").json()

    assert d["span"] == 3
    assert sorted(d["boards"]) == ["2026-08-07", "2026-08-08", "2026-08-09"]
    assert [len(d["boards"][k]) for k in sorted(d["boards"])] == [1, 1, 1]
    # `board` stays the selected day, so nothing that read it before breaks
    assert len(d["board"]) == 1


def test_span_1_is_the_default_and_unchanged(monkeypatch):
    monkeypatch.setattr("headnote.api.notesheets._today_iso", lambda: "2026-08-08")
    c = _home_client([_case("a", "08/08/2026")])
    d = c.get("/api/home?date=2026-08-08").json()
    assert d["span"] == 1 and list(d["boards"]) == ["2026-08-08"]


def test_overdue_matters_are_reported_not_dropped(monkeypatch):
    """A date that has passed with no new date used to vanish from every day of
    the diary, because the diary groups strictly by next hearing date."""
    monkeypatch.setattr("headnote.api.notesheets._today_iso", lambda: "2026-08-08")
    c = _home_client([_case("old", "28/07/2026"), _case("now", "08/08/2026")])
    d = c.get("/api/home?date=2026-08-08").json()

    assert d["counts"]["overdue"] == 1
    assert d["overdue"][0]["next_hearing_iso"] == "2026-07-28"


def test_month_days_feeds_the_calendar_dots(monkeypatch):
    monkeypatch.setattr("headnote.api.notesheets._today_iso", lambda: "2026-08-08")
    c = _home_client([_case("a", "08/08/2026"), _case("b", "08/08/2026"),
                      _case("c", "19/08/2026"), _case("d", "19/11/2026")])
    d = c.get("/api/home?date=2026-08-08").json()

    assert d["month_days"] == {"2026-08-08": 2, "2026-08-19": 1}   # November excluded


def test_month_endpoint_counts_any_month(monkeypatch):
    monkeypatch.setattr("headnote.api.notesheets._today_iso", lambda: "2026-08-08")
    c = _home_client([_case("a", "19/11/2026"), _case("b", "08/08/2026")])
    d = c.get("/api/home/month?month=2026-11").json()

    assert d["month"] == "2026-11" and d["days"] == {"2026-11-19": 1} and d["total"] == 1


def test_month_endpoint_rejects_rubbish(monkeypatch):
    c = _home_client([])
    assert c.get("/api/home/month?month=nonsense").status_code == 400


# ------------------------------------------------- the court's own cause list
#
# The cause list is the board the court is actually sitting on. It is fresher
# than the case record's next date (which is only as new as the last time that
# file was written) and it alone carries court number, item and judge. Observed
# live: a case record said 2026-07-17 while the court had it listed 2026-08-13.

def _listing(date="2026-08-13", **kw):
    base = {"date": date, "court_no": "79", "item": 17, "judge": "B S Kushwah",
            "purpose": "Final arguments", "bench": "1", "court_name": "XV CJ SD",
            "list_type": "CRIMINAL", "case_number": "RCT/6345/2017"}
    base.update(kw)
    return base


class _OneStore:
    def __init__(self, case):
        self.case = dict(case)
        self.prep_writes = []

    def get_case(self, case_id, *, user_id):
        return dict(self.case)

    def merge_prep(self, case_id, *, user_id, prep):
        self.prep_writes.append(prep)
        cj = dict(self.case.get("case_json") or {})
        cj["prep"] = prep
        self.case["case_json"] = cj

    def set_next_date(self, case_id, *, user_id, next_hearing_date, stage):
        if next_hearing_date:
            self.case["next_hearing_date"] = next_hearing_date

    def replace_case_identity(self, case_id, *, user_id, case):
        self.case["case_json"] = case
        if case.get("next_hearing_date"):
            self.case["next_hearing_date"] = case["next_hearing_date"]


def _wire_one(monkeypatch, store):
    for name in ("get_case", "merge_prep", "set_next_date", "replace_case_identity"):
        monkeypatch.setattr(f"headnote.cases.storage.{name}", getattr(store, name), raising=False)


def test_causelist_beats_a_stale_case_record(monkeypatch):
    case = {"id": "c1", "cnr": "X" * 16, "next_hearing_date": "2026-07-17", "case_json": {}}
    store = _OneStore(case)
    _wire_one(monkeypatch, store)

    res = courtsync.apply_listing(case, _listing(), UID)

    assert res["ok"] is True
    assert store.case["next_hearing_date"] == "2026-08-13"
    kinds = [u["kind"] for u in res["updates"]]
    assert "next_date" in kinds


def test_listing_carries_the_board_position(monkeypatch):
    """Court number, item and judge exist nowhere in the case record."""
    case = {"id": "c1", "cnr": "X" * 16, "next_hearing_date": "2026-07-17", "case_json": {}}
    store = _OneStore(case)
    _wire_one(monkeypatch, store)

    courtsync.apply_listing(case, _listing(), UID)
    prep = store.prep_writes[-1]

    assert prep["court_no"] == "79"
    assert prep["item"] == 17
    assert prep["judge"] == "B S Kushwah"
    assert prep["listed_on"] == "2026-08-13"


def test_update_text_uses_the_key_the_inbox_renders(monkeypatch):
    """The inbox renders `text`; anything else showed a present-but-blank row."""
    case = {"id": "c1", "cnr": "X" * 16, "next_hearing_date": "2026-07-17", "case_json": {}}
    _wire_one(monkeypatch, _OneStore(case))
    res = courtsync.apply_listing(case, _listing(), UID)
    for u in res["updates"]:
        assert u.get("text"), f"update with no text: {u}"
    assert "court no. 79" in res["updates"][0]["text"]


def test_a_hand_written_purpose_is_never_overwritten(monkeypatch):
    case = {"id": "c1", "cnr": "X" * 16, "next_hearing_date": "2026-08-13",
            "case_json": {"prep": {"purpose": "My own note", "purpose_manual": True}}}
    store = _OneStore(case)
    _wire_one(monkeypatch, store)

    courtsync.apply_listing(case, _listing(), UID)

    assert store.prep_writes[-1]["purpose"] == "My own note"


def test_boilerplate_purpose_is_ignored(monkeypatch):
    """"Miscellanceous matters not defined otherwise" says nothing; letting it
    overwrite a real purpose drops readiness to Review."""
    case = {"id": "c1", "cnr": "X" * 16, "next_hearing_date": "2026-08-13",
            "case_json": {"prep": {"purpose": "Recording of evidence"}}}
    store = _OneStore(case)
    _wire_one(monkeypatch, store)

    courtsync.apply_listing(
        case, _listing(purpose="Miscellanceous matters not defined otherwise"), UID)

    assert store.prep_writes[-1]["purpose"] == "Recording of evidence"


def test_trust_listing_suppresses_the_stale_date(monkeypatch):
    """With a cause list in hand, the full case read must not report the case
    FILE's older date — that showed two contradictory next-date lines at once."""
    case = {"id": "c1", "cnr": "X" * 16, "next_hearing_date": "2026-08-13", "case_json": {}}
    store = _OneStore(case)
    _wire_one(monkeypatch, store)
    monkeypatch.setattr(config, "CNR_API_MODE", "live", raising=False)
    monkeypatch.setattr(ecourts_client, "is_valid_cnr", lambda c: True)
    monkeypatch.setattr(ecourts_client, "fetch_cnr",
                        lambda cnr: {"cnr": cnr, "next_hearing_date": "2026-07-17",
                                     "stage": "evidence"})

    res = courtsync.sync_case(case, UID, trust_listing=True)

    kinds = [u["kind"] for u in res["updates"]]
    assert "next_date" not in kinds            # the stale file date is suppressed
    assert "stage" in kinds                    # everything else still reported
    assert store.case["next_hearing_date"] == "2026-08-13"     # cause list held


def test_causelist_batch_chunks_and_skips_junk(monkeypatch):
    monkeypatch.setattr(config, "CNR_API_MODE", "live", raising=False)
    monkeypatch.setattr(config, "CNR_API_TOKEN", "t", raising=False)
    seen = []

    class _R:
        status_code = 200
        def json(self):
            return {"data": [{"cnr": c, "nextListing": {"date": "2026-08-13", "listingNo": 1}}
                             for c in seen[-1]]}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.append(json["cnrs"])
        return _R()

    monkeypatch.setattr(ecourts_client.httpx, "post", fake_post)
    monkeypatch.setattr(ecourts_client, "is_valid_cnr", lambda c: len(c) == 16)

    cnrs = [f"{i:016d}" for i in range(120)] + ["too-short"]
    out = ecourts_client.fetch_causelist_batch(cnrs)

    assert len(seen) == 3                    # 120 valid CNRs / 50 per call
    assert all(len(c) <= 50 for c in seen)
    assert "too-short" not in out


# ------------------------------------------------------------- the scheduler
#
# The sweep must run on a WORKER THREAD, never on the event loop: it is blocking
# HTTP to the vendor, and stalling the loop stalls /api/live — the Fly health
# check — which is how this site was pulled from the routing pool twice while
# the app was serving fine.

import asyncio
from datetime import datetime, timedelta, timezone

from headnote.cases import sync_scheduler as sched


def test_scheduler_is_off_unless_explicitly_armed(monkeypatch):
    monkeypatch.delenv("COURT_SYNC_SCHEDULE", raising=False)
    assert sched.enabled() is False
    monkeypatch.setenv("COURT_SYNC_SCHEDULE", "1")
    assert sched.enabled() is True


def test_default_time_is_six_pm_ist(monkeypatch):
    monkeypatch.delenv("COURT_SYNC_AT_UTC", raising=False)
    monkeypatch.setenv("COURT_SYNC_SCHEDULE", "1")
    st = sched.status()
    assert st["at_utc"] == "12:30"
    assert st["at_ist"] == "18:00"


def test_a_bad_time_falls_back_rather_than_crashing(monkeypatch):
    monkeypatch.setenv("COURT_SYNC_AT_UTC", "not-a-time")
    assert sched._target_hm() == (12, 30)


def test_next_run_never_returns_the_past():
    now = datetime(2026, 8, 8, 13, 0, tzinfo=timezone.utc)
    nxt = sched._next_run(now, 12, 30)          # already gone today
    assert nxt == datetime(2026, 8, 9, 12, 30, tzinfo=timezone.utc)
    nxt2 = sched._next_run(now, 23, 0)          # still to come today
    assert nxt2 == datetime(2026, 8, 8, 23, 0, tzinfo=timezone.utc)


def _clock(steps):
    """A fake UTC clock: the Nth call to now() returns steps[N-1] (last repeats).
    Real datetimes, so _next_run's .replace()/comparisons behave normally."""
    n = {"i": 0}

    class _C:
        @staticmethod
        def now(tz=None):
            i = min(n["i"], len(steps) - 1)
            n["i"] += 1
            return steps[i]
    return _C


async def _drive(polls=400):
    task = asyncio.get_running_loop().create_task(sched._loop())
    for _ in range(polls):
        await asyncio.sleep(0.004)
        if _drive.stop and _drive.stop():
            break
    alive = not task.done()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return alive


_drive.stop = None


def test_loop_fires_at_the_appointed_time_and_off_the_event_loop(monkeypatch):
    """Drives the REAL loop with a fast tick and a controlled clock."""
    fired = {"n": 0, "on_loop": None}

    def fake_sweep():
        # If this ran on the event loop, there would BE a running loop here.
        try:
            asyncio.get_running_loop()
            fired["on_loop"] = True
        except RuntimeError:
            fired["on_loop"] = False
        fired["n"] += 1
        return {"ok": True, "users": 1}

    monkeypatch.setattr(sched, "_run_sweep", fake_sweep)
    monkeypatch.setattr(sched, "_TICK_SEC", 0.004)
    monkeypatch.setenv("COURT_SYNC_SCHEDULE", "1")

    d = datetime(2026, 8, 8, 12, 29, tzinfo=timezone.utc)
    # first call is BEFORE 12:30 (so nxt is today), then we walk across it
    monkeypatch.setattr(sched, "datetime",
                        _clock([d, d + timedelta(seconds=20), d + timedelta(seconds=40),
                                d + timedelta(seconds=60), d + timedelta(seconds=80)]))

    _drive.stop = lambda: fired["n"] > 0
    asyncio.run(_drive())

    assert fired["n"] >= 1, "the scheduler never fired"
    assert fired["on_loop"] is False, "the sweep ran ON the event loop — it must not"


def test_a_failing_sweep_does_not_kill_the_scheduler(monkeypatch):
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("vendor down")

    monkeypatch.setattr(sched, "_run_sweep", boom)
    monkeypatch.setattr(sched, "_TICK_SEC", 0.004)
    monkeypatch.setenv("COURT_SYNC_SCHEDULE", "1")

    d = datetime(2026, 8, 8, 12, 29, tzinfo=timezone.utc)
    # cross 12:30 today, then cross it again the next day
    monkeypatch.setattr(sched, "datetime",
                        _clock([d, d + timedelta(minutes=2),
                                d + timedelta(days=1), d + timedelta(days=1, minutes=2),
                                d + timedelta(days=2), d + timedelta(days=2, minutes=2)]))

    _drive.stop = lambda: calls["n"] >= 2
    alive = asyncio.run(_drive())

    assert calls["n"] >= 2, "scheduler stopped after the first failure"
    assert alive, "an exception killed the scheduler task"


def test_sweep_says_so_when_it_finds_no_users(monkeypatch):
    """0 users reported as success is indistinguishable from a healthy sweep."""
    monkeypatch.setattr(config, "CNR_API_MODE", "live", raising=False)
    monkeypatch.setattr(daily_sync, "_user_ids", lambda only_user_id=None: [])
    res = daily_sync.sync_all_dockets()
    assert res["ok"] is False and "no users" in res["reason"]


def test_sweep_reports_a_broken_user_lookup(monkeypatch):
    monkeypatch.setattr(config, "CNR_API_MODE", "live", raising=False)
    def boom(only_user_id=None):
        raise RuntimeError("supabase 500")
    monkeypatch.setattr(daily_sync, "_user_ids", boom)
    res = daily_sync.sync_all_dockets()
    assert res["ok"] is False and "could not list users" in res["reason"]


# --------------------------------------- linking a diary docket to the court
#
# Production 2026-08-08: 123 of 125 matters were `source=diary` with a synthetic
# 14-char placeholder in the `cnr` column, so the sweep could do nothing for
# them. These pin the bridge that makes the sweep worth running.

def _bulk_client(rows, docket):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from headnote.api import cases as cases_api
    from headnote.entitlements import CurrentUser, get_current_user

    app = FastAPI()
    app.include_router(cases_api.router)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=UID, email="t@t.in", role="authenticated", raw_claims={"sub": UID})

    store = {r["id"]: dict(r) for r in rows}

    class _S:
        def list_cases(self, *, user_id, limit=500):
            return [dict(r) for r in store.values()]
        def get_case(self, cid, *, user_id):
            return dict(store[cid]) if cid in store else None
        def replace_case_identity(self, cid, *, user_id, case):
            if cid not in store:
                return None
            store[cid] = {**store[cid], "cnr": case.get("cnr"),
                          "case_title": case.get("case_title"), "case_json": case}
            return dict(store[cid])

    cases_api.cases_storage = _S()
    cases_api.ecourts_client.import_by_advocate = (
        lambda *a, **k: [dict(c) for c in docket])
    cases_api.ecourts_client.fetch_cnr = (
        lambda cnr: {"cnr": cnr, "case_title": "Fetched " + cnr, "source": "ecourtsindia"})
    return TestClient(app), store


def _diary(cid, no, yr):
    return {"id": cid, "cnr": f"DY{cid}PLACEHOLD"[:14], "case_number": no, "case_year": yr,
            "case_title": "diary row", "court_name": "Gwalior", "source": "diary",
            "next_hearing_date": "01/01/2020", "case_json": {}}


def test_bulk_matches_diary_matters_by_case_number():
    docket = [{"cnr": "MP07010272252017", "case_number": "6345", "case_year": "2017",
               "case_title": "State vs Viney", "court_name": "Gwalior",
               "next_hearing_date": "2026-07-17", "stage": "evidence"}]
    c, _ = _bulk_client([_diary("a", "6345", "2017"), _diary("b", "9999", "2099")], docket)

    d = c.post("/api/cases/resolve-cnr/bulk",
               json={"advocate_name": "Vishnu", "city": "Gwalior"}).json()

    assert d["unlinked"] == 2 and d["matched"] == 1 and d["unmatched"] == 1
    assert d["proposals"][0]["proposed"]["cnr"] == "MP07010272252017"


def test_bulk_writes_nothing_until_confirmed():
    docket = [{"cnr": "MP07010272252017", "case_number": "6345", "case_year": "2017"}]
    c, store = _bulk_client([_diary("a", "6345", "2017")], docket)

    c.post("/api/cases/resolve-cnr/bulk", json={"advocate_name": "V"})

    assert store["a"]["cnr"].startswith("DY")      # untouched


def test_bulk_confirm_links_only_what_was_ticked():
    docket = [{"cnr": "MP07010272252017", "case_number": "6345", "case_year": "2017"},
              {"cnr": "MP07010139772020", "case_number": "2098", "case_year": "2020"}]
    c, store = _bulk_client([_diary("a", "6345", "2017"), _diary("b", "2098", "2020")], docket)

    d = c.post("/api/cases/resolve-cnr/bulk/confirm",
               json={"items": [{"case_id": "a", "cnr": "MP07010272252017"}]}).json()

    assert d["linked"] == 1 and d["failed"] == []
    assert store["a"]["cnr"] == "MP07010272252017"
    assert store["b"]["cnr"].startswith("DY")      # not ticked → untouched


def test_bulk_needs_an_advocate_name():
    c, _ = _bulk_client([_diary("a", "1", "2020")], [])
    assert c.post("/api/cases/resolve-cnr/bulk", json={"advocate_name": " "}).status_code == 400


def test_one_bad_cnr_does_not_undo_the_batch():
    from headnote.api import cases as cases_api
    c, store = _bulk_client([_diary("a", "1", "2020"), _diary("b", "2", "2020")], [])

    def flaky(cnr):
        if "BAD" in cnr:
            raise RuntimeError("vendor 404")
        return {"cnr": cnr, "case_title": "ok"}
    cases_api.ecourts_client.fetch_cnr = flaky

    d = c.post("/api/cases/resolve-cnr/bulk/confirm", json={"items": [
        {"case_id": "a", "cnr": "MP07010272BADXXX"},   # 16 chars; vendor will 404 it
        {"case_id": "b", "cnr": "MP07010139772020"}]}).json()

    assert d["linked"] == 1 and len(d["failed"]) == 1


def test_upgrading_identity_keeps_the_lawyers_prep(tmp_path, monkeypatch):
    """A diary matter carries the lawyer's OWN work — the hearing purpose, the
    prepared tick, the assigned junior. Linking it to the court replaces the
    matter's identity, and that must NOT silently reset any of it."""
    from headnote.cases import storage as st

    # Point the real SQLite backend at a throwaway file. KANOON_CACHE_PATH is read
    # per call, so no module reload is needed (reloading leaks into other tests).
    monkeypatch.setattr(st, "KANOON_CACHE_PATH", str(tmp_path / "c.sqlite"), raising=False)
    monkeypatch.setattr(st, "_use_sb", lambda: False)
    st.init_cases_db()

    row = st.add_case(user_id=UID, case={
        "cnr": "DY555D37A73195", "case_title": "diary row", "court_name": "Gwalior",
        "case_number": "6345", "case_year": "2017", "source": "diary",
        "prep": {"purpose": "Final arguments", "prepared": True, "assignee": "Adv. Priya"},
        "client": {"name": "Ramesh"}})
    assert row and row["cnr"] == "DY555D37A73195"

    # the court's version carries none of the lawyer's own work
    st.replace_case_identity(row["id"], user_id=UID, case={
        "cnr": "MP07010272252017", "case_title": "State vs Viney",
        "court_name": "District and Sessions Court, Gwalior", "source": "ecourtsindia"})

    after = st.get_case(row["id"], user_id=UID)
    cj = after["case_json"]
    assert after["cnr"] == "MP07010272252017"          # identity upgraded
    assert cj["prep"]["assignee"] == "Adv. Priya"      # ...and the prep survived
    assert cj["prep"]["prepared"] is True
    assert cj["prep"]["purpose"] == "Final arguments"
    assert cj["client"]["name"] == "Ramesh"
