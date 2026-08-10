"""Home must resolve a whole board in a fixed number of storage calls.

Home used to look artifacts up per matter: three SQLite reads (each opening a
connection and re-running the schema DDL) plus one HTTP call to Postgres for
saved authorities, for EVERY card. A 40-matter board cost ~160 sequential round
trips before anything could paint, which is what made Home and the date switcher
feel broken.

These tests pin the batching. The important property is that the call count does
not grow with the size of the docket — so they assert a CONSTANT, not a ratio.
"""
from unittest import mock

import pytest

import headnote.api.notesheets as ns


@pytest.fixture
def counted():
    """Patch the four bulk lookups and count how many times each is called."""
    calls = {"drafts": 0, "docs": 0, "recs": 0, "auth": 0}

    def mk(key, ret):
        def fn(user_id, ids):
            calls[key] += 1
            return ret
        return fn

    with mock.patch.object(ns.draft_storage, "drafts_for_cases", mk("drafts", {})), \
         mock.patch.object(ns.docs_storage, "counts_by_case", mk("docs", {})), \
         mock.patch.object(ns.consult_storage, "counts_by_case", mk("recs", {})), \
         mock.patch.object(ns.saved_caselaw, "counts_by_matter", mk("auth", {})):
        yield calls


@pytest.mark.parametrize("n", [1, 10, 40, 200])
def test_bulk_lookup_is_constant_regardless_of_docket_size(counted, n):
    ns._artifacts_bulk([f"case-{i}" for i in range(n)], "user-1")
    assert counted == {"drafts": 1, "docs": 1, "recs": 1, "auth": 1}, (
        f"a {n}-matter board must still cost exactly 4 lookups")


def test_empty_board_makes_no_calls(counted):
    assert ns._artifacts_bulk([], "user-1") == {}
    assert sum(counted.values()) == 0, "an empty board must not touch storage"


def test_falsy_case_ids_are_dropped(counted):
    out = ns._artifacts_bulk(["a", None, "", "b"], "user-1")
    assert set(out) == {"a", "b"}


def test_bulk_shape_matches_what_the_card_expects():
    """Drafts come back whole (readiness reads title + status); the rest as counts."""
    with mock.patch.object(ns.draft_storage, "drafts_for_cases",
                           lambda u, i: {"c1": [{"id": "d1", "title": "Bail", "status": "filed"}]}), \
         mock.patch.object(ns.docs_storage, "counts_by_case", lambda u, i: {"c1": 3}), \
         mock.patch.object(ns.consult_storage, "counts_by_case", lambda u, i: {}), \
         mock.patch.object(ns.saved_caselaw, "counts_by_matter", lambda u, i: {"c1": 2}):
        out = ns._artifacts_bulk(["c1", "c2"], "u")

    assert out["c1"]["drafts"][0]["title"] == "Bail"
    assert out["c1"]["documents"] == 3
    assert out["c1"]["authorities"] == 2
    assert out["c1"]["recordings"] == 0
    # A matter with nothing filed must still get an entry, not a KeyError.
    assert out["c2"] == {"drafts": [], "documents": 0, "recordings": 0, "authorities": 0}


class TestAsRows:
    """Readiness takes lists; the bulk path carries counts."""

    def test_int_becomes_that_many_rows(self):
        assert len(ns._as_rows(3)) == 3

    def test_zero_and_none_are_empty(self):
        assert ns._as_rows(0) == []
        assert ns._as_rows(None) == []

    def test_negative_does_not_explode(self):
        assert ns._as_rows(-1) == []

    def test_real_rows_pass_through_untouched(self):
        rows = [{"title": "Bail", "status": "filed"}]
        assert ns._as_rows(rows) == rows


def test_card_built_from_counts_matches_card_built_from_rows():
    """The batched path must produce the same readiness verdict as the old one.

    This is the regression that matters: a faster Home that grades matters
    differently would be worse than a slow one.
    """
    case = {"id": "c1", "case_title": "A vs B", "next_hearing_date": "2026-08-20",
            "case_json": {"prep": {"purpose": "Final arguments"}}}
    drafts = [{"id": "d1", "title": "Written arguments", "status": "draft"}]

    with mock.patch.object(ns.ns_storage, "get_prep",
                           lambda c: (c.get("case_json") or {}).get("prep") or {}):
        from_rows = ns._matter_card(case, "u", arts={
            "drafts": drafts, "documents": [{}, {}], "recordings": [], "authorities": [{}, {}]})
        from_counts = ns._matter_card(case, "u", arts={
            "drafts": drafts, "documents": 2, "recordings": 0, "authorities": 2})

    assert from_rows["readiness"] == from_counts["readiness"]
    assert from_rows["counts"] == from_counts["counts"] == {
        "drafts": 1, "documents": 2, "recordings": 0, "authorities": 2}
