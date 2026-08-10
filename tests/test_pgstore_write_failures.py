"""A durable write that fails must say so.

Why these tests exist
---------------------
Both of the bugs below reported success for a write that never happened, which is
the worst possible failure for a store holding a lawyer's drafts: it stops them
retyping the thing that was lost.

  update()  `_supabase.update()` logs HTTP errors and returns [], so a PATCH that
            never reached the database was indistinguishable from one that matched
            no rows. The old code discarded both and returned `get()` — the row as
            it was BEFORE the edit — so the route answered 200 with the pre-edit
            row and the editor printed "Saved".

  insert()  any empty result called mark_absent(), so ONE 5s timeout sent that row
            to SQLite, switched reads to SQLite for the rest of the process, and
            orphaned every row already written to Postgres by that process.
"""

from __future__ import annotations

import pytest

from headnote import pgstore
from headnote.entitlements import _supabase


ROW = {"id": "abc123", "story_id": "friendly_cash_loan", "title": "before"}


@pytest.fixture(autouse=True)
def _clean_table_state():
    """The absent/present sets are process-global; don't leak between tests."""
    pgstore._absent.clear()
    pgstore._present.clear()
    yield
    pgstore._absent.clear()
    pgstore._present.clear()


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    monkeypatch.setattr(pgstore.time, "sleep", lambda _s: None)


def _http(status: int) -> _supabase.SupabaseError:
    return _supabase.SupabaseError(f"HTTP {status}", status=status, body="")


def _timeout() -> _supabase.SupabaseError:
    return _supabase.SupabaseError("PATCH drafts: ReadTimeout")   # status=None


def _missing() -> _supabase.SupabaseError:
    return _supabase.SupabaseError(
        "POST drafts: HTTP 404: Could not find the table 'public.drafts'",
        status=404)


# ------------------------------------------------------------------- update()

def test_update_raises_instead_of_returning_the_pre_edit_row(monkeypatch):
    """The whole bug in one test: the failed save must not look like a save."""
    monkeypatch.setattr(_supabase, "update_or_raise",
                        lambda *a, **k: (_ for _ in ()).throw(_timeout()))
    # If update() ever falls back to a read again, this is the stale row it would
    # hand back with a 200.
    monkeypatch.setattr(_supabase, "select", lambda *a, **k: [dict(ROW)])

    with pytest.raises(pgstore.WriteFailed):
        pgstore.update("drafts", "abc123", {"title": "after"})


def test_update_returns_none_when_no_row_matched(monkeypatch):
    """An empty representation from a 2xx is a real answer — nothing matched the
    filter — so the caller's 404 is right. It must not be confused with failure."""
    monkeypatch.setattr(_supabase, "update_or_raise", lambda *a, **k: [])
    assert pgstore.update("drafts", "nope", {"title": "after"}) is None


def test_update_returns_the_row_the_database_actually_stored(monkeypatch):
    """Straight from the PATCH's own representation, not a follow-up read, so
    what the caller returns is what Postgres holds."""
    seen = {}

    def fake(table, payload, *, params, **_k):
        seen.update(payload=payload, params=params)
        return [{"id": "abc123", "title": "after"}]

    monkeypatch.setattr(_supabase, "update_or_raise", fake)
    monkeypatch.setattr(_supabase, "select",
                        lambda *a, **k: pytest.fail("update must not re-read"))

    row = pgstore.update("drafts", "abc123", {"title": "after"}, user_id="u1")
    assert row == {"id": "abc123", "title": "after"}
    assert seen["params"] == {"id": "eq.abc123", "user_id": "eq.u1"}
    assert "updated_at" in seen["payload"]


def test_update_retries_a_transient_failure_before_giving_up(monkeypatch):
    calls = []

    def flaky(*_a, **_k):
        calls.append(1)
        if len(calls) < 3:
            raise _http(503)
        return [{"id": "abc123", "title": "after"}]

    monkeypatch.setattr(_supabase, "update_or_raise", flaky)
    assert pgstore.update("drafts", "abc123", {"title": "after"})["title"] == "after"
    assert len(calls) == 3


def test_update_does_not_retry_a_permanent_rejection(monkeypatch):
    """A 400 is a considered answer. Retrying sends the same bad payload again."""
    calls = []

    def bad(*_a, **_k):
        calls.append(1)
        raise _http(400)

    monkeypatch.setattr(_supabase, "update_or_raise", bad)
    with pytest.raises(pgstore.WriteFailed):
        pgstore.update("drafts", "abc123", {"title": "after"})
    assert len(calls) == 1


# ------------------------------------------------------------------- insert()

def test_one_timeout_does_not_condemn_the_table_to_sqlite(monkeypatch):
    """The orphaning bug: a transient failure must not flip reads to SQLite, or
    every row already written to Postgres this process becomes unreadable."""
    calls = []

    def flaky(table, payload, **_k):
        calls.append(1)
        if len(calls) == 1:
            raise _timeout()
        return [dict(payload)]

    monkeypatch.setattr(_supabase, "upsert_or_raise", flaky)
    row = pgstore.insert("drafts", dict(ROW))
    assert row["id"] == "abc123"
    assert "drafts" not in pgstore._absent, "a timeout must not mark the table absent"


def test_a_write_that_never_lands_raises_rather_than_degrading(monkeypatch):
    """After the retries: nothing was written and the caller is told. It must not
    return None, which the storage layer reads as 'write it to SQLite instead' —
    a row in SQLite is invisible while reads come from Postgres."""
    monkeypatch.setattr(_supabase, "upsert_or_raise",
                        lambda *a, **k: (_ for _ in ()).throw(_timeout()))
    with pytest.raises(pgstore.WriteFailed):
        pgstore.insert("drafts", dict(ROW))
    assert "drafts" not in pgstore._absent


def test_a_missing_table_is_the_one_case_that_degrades(monkeypatch):
    """The migration not being applied is a deployment state, not an error — and
    the only failure where Postgres cannot already hold rows, so SQLite is safe."""
    monkeypatch.setattr(_supabase, "upsert_or_raise",
                        lambda *a, **k: (_ for _ in ()).throw(_missing()))
    assert pgstore.insert("drafts", dict(ROW)) is None
    assert "drafts" in pgstore._absent
    assert pgstore.ready("drafts") is False


def test_an_empty_2xx_is_confirmed_by_reading_the_row_back(monkeypatch):
    """`return=representation` should always echo the row, so an empty body is
    ambiguous, not a failure. Ask the database before concluding anything."""
    monkeypatch.setattr(_supabase, "upsert_or_raise", lambda *a, **k: [])
    monkeypatch.setattr(_supabase, "select", lambda *a, **k: [dict(ROW)])
    assert pgstore.insert("drafts", dict(ROW))["id"] == "abc123"
    assert "drafts" not in pgstore._absent


def test_an_empty_2xx_with_nothing_stored_still_fails_loudly(monkeypatch):
    monkeypatch.setattr(_supabase, "upsert_or_raise", lambda *a, **k: [])
    monkeypatch.setattr(_supabase, "select", lambda *a, **k: [])
    with pytest.raises(pgstore.WriteFailed):
        pgstore.insert("drafts", dict(ROW))


def test_insert_still_stamps_timestamps_and_json(monkeypatch):
    seen = {}
    monkeypatch.setattr(_supabase, "upsert_or_raise",
                        lambda t, payload, **k: (seen.update(payload), [dict(payload)])[1])
    pgstore.insert("drafts", {**ROW, "answers_json": '{"a": 1}'},
                   json_cols=("answers_json",))
    assert seen["answers_json"] == {"a": 1}, "TEXT JSON must become a real object"
    assert seen["created_at"] and seen["updated_at"]


# --------------------------------------------------- the error classification

@pytest.mark.parametrize("status,transient", [
    (None, True),    # no response at all: timeout, DNS, connection reset
    (408, True), (429, True), (500, True), (502, True), (503, True),
    (400, False), (401, False), (403, False), (404, False), (409, False),
])
def test_only_retryable_failures_are_marked_transient(status, transient):
    assert _supabase.SupabaseError("x", status=status).transient is transient
