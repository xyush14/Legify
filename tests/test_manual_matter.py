"""Adding a matter BY HAND — the lane for everything the court record cannot give.

A matter filed this morning is not on eCourts yet; an arbitration or a revenue
court never will be; and the vendor is sometimes simply not answering. Before
this lane the only way to put a single matter on the board was to photograph a
cause-list page.

What is pinned here is what would quietly hurt a lawyer:
  • a hand-added matter must land on the diary date he typed;
  • it must NOT masquerade as court-linked — its id has to stay outside the CNR
    shape, or the nightly sweep would try to sync a case the court has never
    heard of, and the "not linked" banner would stop offering to link it;
  • submitting the same matter twice must not give him two copies of it;
  • a matter with neither a number nor a party is unfindable, so it is refused.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from headnote.api import cases as api_cases
from headnote.cases import ecourts_client as ec


class _User:
    id = "u-manual-1"
    email = "adv@example.com"
    role = "authenticated"
    raw_claims: dict = {}


@pytest.fixture()
def store(monkeypatch):
    """A stand-in for the matters store that records what was actually saved."""
    saved: list[dict] = []

    class _S:
        rows = saved

        @staticmethod
        def add_case(*, user_id, case):
            row = {"id": f"m{len(saved)+1}", "user_id": user_id, **case,
                   "case_json": dict(case)}
            saved.append(row)
            return row

        @staticmethod
        def find_case_by_number(*, user_id, case_number, case_year=None, court_name=None):
            for r in saved:
                if r["case_number"] and r["case_number"] == case_number:
                    return r
            return None

        @staticmethod
        def get_case(case_id, *, user_id):
            return next((r for r in saved if r["id"] == case_id), None)

    monkeypatch.setattr(api_cases, "cases_storage", _S)
    return _S


def _body(**kw):
    return api_cases.ManualCaseBody(**kw)


def add(**kw):
    return api_cases.add_case_manually(_body(**kw), user=_User())


# ─────────────────────────────────────────── the matter he typed

def test_a_hand_typed_matter_is_saved_with_its_own_particulars(store):
    out = add(case_number="6345/2017", case_type="Cr.A.",
              court_name="जिला न्यायालय ग्वालियर",
              petitioner_name="State Government", respondent_name="Viney",
              next_hearing_date="2026-09-04", stage="arguments",
              sections="IPC 302, IPC 34")
    c = out["case"]
    assert out["duplicate"] is False
    assert (c["case_number"], c["case_year"]) == ("6345", "2017")
    assert c["case_title"] == "State Government vs Viney"
    assert c["sections"] == ["IPC 302", "IPC 34"]
    assert c["source"] == "manual"


def test_the_date_is_stored_the_way_the_rest_of_the_board_carries_it(store):
    """The browser's date input sends ISO; every other matter on the diary holds
    dd/mm/yyyy. One board, one format."""
    c = add(case_number="1/2026", next_hearing_date="2026-09-04")["case"]
    assert c["next_hearing_date"] == "04/09/2026"


def test_a_date_we_cannot_parse_is_kept_verbatim_not_dropped(store):
    c = add(case_number="2/2026", next_hearing_date="after Diwali")["case"]
    assert c["next_hearing_date"] == "after Diwali"


def test_it_is_deliberately_not_court_linked(store):
    """The synthetic id must NOT pass as a CNR. If it did, the nightly sweep
    would ask the court about a case it has never heard of, and the 'not linked
    to the court record' banner would stop offering to link it."""
    c = add(case_number="6345/2017", court_name="Gwalior")["case"]
    assert not ec.is_valid_cnr(c["cnr"])
    assert c["cnr"].startswith("MN")


def test_a_bare_party_name_is_enough(store):
    """A consultation that is not yet a case has no number at all."""
    c = add(petitioner_name="रामप्रसाद")["case"]
    assert c["case_title"].startswith("रामप्रसाद")


def test_nothing_identifying_is_refused(store):
    with pytest.raises(HTTPException) as e:
        add(court_name="Gwalior", stage="arguments")
    assert e.value.status_code == 400
    assert store.rows == []


# ─────────────────────────────────────────── not two copies of one matter

def test_the_same_matter_twice_does_not_become_two_matters(store):
    first = add(case_number="6345/2017", court_name="Gwalior",
                petitioner_name="State", respondent_name="Viney")
    again = add(case_number="6345/2017", court_name="Gwalior",
                petitioner_name="State", respondent_name="Viney")
    assert again["duplicate"] is True
    assert again["case"]["id"] == first["case"]["id"]
    assert len(store.rows) == 1


def test_the_client_he_typed_is_saved_with_the_matter(store):
    c = add(case_number="9/2026", client={"name": "रामप्रसाद", "mobile": "9425012345"})["case"]
    assert c["client"] == {"name": "रामप्रसाद", "mobile": "9425012345"}
