"""Clearing the court-update band must cost ONE request, not one per matter.

The band on Home carried a ✕ per row and nothing else. Each ✕ was a round trip
that also triggered a full reload of the board, so an advocate with a fortnight
of court movement had to click twenty times and wait for twenty repaints to get
back to an empty band.

These tests pin the two properties that fix cost:

  * the bulk endpoint writes once per matter that actually has something
    unread — not once per notification, and not once per matter on the docket;
  * marking updates seen touches ONLY the seen flags. It used to go through
    `replace_case_identity`, which rewrites nine columns from a payload
    assembled at the call site — an enormous amount of machinery for setting a
    boolean, and a real risk to the matter's identity.
"""
from unittest import mock

import pytest

import headnote.api.notesheets as ns
from headnote.cases import storage as cases_storage


USER = "user-1"


def _case(cid, updates):
    return {"id": cid, "cnr": f"CNR{cid}", "case_title": f"Matter {cid}",
            "court_name": "DISTRICT COURT", "case_number": cid, "case_year": "2025",
            "stage": "Arguments", "next_hearing_date": "13/08/2026",
            "case_json": {"updates": updates, "client": {"name": f"Client {cid}"}}}


def _unseen(n):
    return [{"kind": "next_date", "text": f"change {i}", "seen": False} for i in range(n)]


def _seen(n):
    return [{"kind": "next_date", "text": f"change {i}", "seen": True} for i in range(n)]


def _local_store(monkeypatch, db_path):
    """Point the cases store at a throwaway SQLite file for this test.

    Two things have to be redirected, and missing either one is silent:
      * Supabase, or the store would prefer it and these writes would leave
        the machine entirely;
      * KANOON_CACHE_PATH, which is the name `_conn()` actually opens. Patching
        anything else looks like it worked — the test passes — while writing
        into the developer's real local database.
    """
    monkeypatch.setattr(cases_storage._supabase, "SUPABASE_URL", "")
    monkeypatch.setattr(cases_storage._supabase, "SERVICE_ROLE_KEY", "")
    monkeypatch.setattr(cases_storage, "KANOON_CACHE_PATH", str(db_path))
    assert not cases_storage._use_sb(), "this test must exercise the local store"
    return db_path


@pytest.fixture
def store():
    """Stand in for the cases store, counting writes.

    Swaps the WHOLE `cases_storage` name on the module rather than patching
    attributes on whatever object is currently bound there. `test_court_sync`
    assigns its own stub to `ns.cases_storage` and never puts the real module
    back, so patching an attribute of it fails outright when these tests run
    after that file — and would silently target the wrong object if the stub
    ever grew a same-named method.
    """
    calls = {"marked": [], "list": 0, "rows": []}

    class _Store:
        def list_cases(self, *, user_id, limit=100):
            calls["list"] += 1
            return calls["rows"]

        def mark_updates_seen(self, case_id, *, user_id, case_json=None):
            cj = case_json or {}
            ups = [u for u in (cj.get("updates") or []) if isinstance(u, dict)]
            if not any(not u.get("seen") for u in ups):
                return 0
            calls["marked"].append(case_id)
            return len(ups)

    with mock.patch.object(ns, "cases_storage", _Store()):
        yield calls


def test_bulk_clear_writes_once_per_unread_matter(store):
    store["rows"] = [_case("a", _unseen(3)), _case("b", _unseen(2)),
                     _case("c", _unseen(1))]
    out = ns.mark_all_updates_read(user=mock.Mock(id=USER))
    assert out == {"ok": True, "cleared": 6, "matters": 3}
    assert store["marked"] == ["a", "b", "c"]
    assert store["list"] == 1, "the docket must be read once, not once per matter"


def test_bulk_clear_skips_matters_with_nothing_unread(store):
    """A 200-matter docket with 2 unread matters must cost 2 writes, not 200."""
    rows = [_case(f"seen-{i}", _seen(2)) for i in range(198)]
    rows += [_case("x", _unseen(1)), _case("y", _unseen(4))]
    store["rows"] = rows
    out = ns.mark_all_updates_read(user=mock.Mock(id=USER))
    assert out["matters"] == 2 and out["cleared"] == 5
    assert store["marked"] == ["x", "y"]


def test_bulk_clear_on_an_empty_band_writes_nothing(store):
    store["rows"] = [_case("a", _seen(2)), _case("b", [])]
    out = ns.mark_all_updates_read(user=mock.Mock(id=USER))
    assert out == {"ok": True, "cleared": 0, "matters": 0}
    assert store["marked"] == []


def test_bulk_clear_is_idempotent(store):
    store["rows"] = [_case("a", _unseen(2))]
    first = ns.mark_all_updates_read(user=mock.Mock(id=USER))
    assert first["cleared"] == 2
    # second pass sees them already ticked
    store["rows"] = [_case("a", _seen(2))]
    store["marked"].clear()
    second = ns.mark_all_updates_read(user=mock.Mock(id=USER))
    assert second["cleared"] == 0 and store["marked"] == []


# ------------------------------------------------- the write itself is narrow

def test_mark_updates_seen_touches_only_the_seen_flags(tmp_path, monkeypatch):
    """The identity columns and the lawyer's own prep must survive a dismiss."""
    _local_store(monkeypatch, tmp_path / "cases.db")

    row = cases_storage.add_case(user_id=USER, case={
        "cnr": "MP07010272252017", "case_title": "State vs X",
        "court_name": "DISTRICT AND SESSIONS COURT GWALIOR MP",
        "case_number": "6345", "case_year": "2017", "stage": "Arguments",
        "next_hearing_date": "13/08/2026", "source": "ecourts",
        "updates": _unseen(2)})
    cid = row["id"]
    cases_storage.merge_prep(cid, user_id=USER,
                             prep={"purpose": "Final arguments", "prepared": True,
                                   "assignee": "Adv. Priya", "item": 17})

    before = cases_storage.get_case(cid, user_id=USER)
    cols = ["cnr", "case_title", "court_name", "case_number", "case_year",
            "stage", "next_hearing_date", "source"]
    snap = {k: before.get(k) for k in cols}
    prep = (before["case_json"] or {}).get("prep")

    n = cases_storage.mark_updates_seen(cid, user_id=USER,
                                        case_json=before.get("case_json"))
    after = cases_storage.get_case(cid, user_id=USER)

    assert n == 2
    assert all(u.get("seen") for u in (after["case_json"] or {}).get("updates") or [])
    assert {k: after.get(k) for k in cols} == snap, "a dismiss must not rewrite identity"
    assert (after["case_json"] or {}).get("prep") == prep, (
        "the hearing purpose, the prepared tick and the assigned junior must survive")


def test_mark_updates_seen_does_not_write_when_nothing_is_unread(tmp_path, monkeypatch):
    _local_store(monkeypatch, tmp_path / "cases2.db")
    row = cases_storage.add_case(user_id=USER, case={
        "cnr": "MP0701027225ZZZZ", "case_title": "State vs Y",
        "next_hearing_date": "13/08/2026", "updates": _seen(3)})
    before = cases_storage.get_case(row["id"], user_id=USER)
    assert cases_storage.mark_updates_seen(row["id"], user_id=USER,
                                           case_json=before.get("case_json")) == 0
    assert cases_storage.get_case(row["id"], user_id=USER)["updated_at"] == before["updated_at"], (
        "nothing unread must mean no write at all")


# ------------------------------------------------- the band has enough to show

def test_home_sends_enough_updates_to_expand_into():
    """Home shows a few and hides the rest. The cap must not be below what the
    'Show N more' control offers to reveal."""
    import inspect
    src = inspect.getsource(ns.home)
    assert "inbox[:60]" in src, (
        "the court_updates slice feeds the band's expand control; at 12 the "
        "screen offered to show more rows than it had been sent")
