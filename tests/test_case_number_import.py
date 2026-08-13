"""Add a matter by CASE NUMBER + court — the door for advocates who do not carry
the 16-character CNR in their head.

The behaviours pinned here are the ones that would silently mislead a lawyer:
  • the number alone is refused (the same number exists in every district)
  • the vendor's RELEVANCE match is re-graded on our side, so a near miss is
    never presented as the case he asked for
  • a BILLING refusal from the vendor never reads as "no such case"
"""

from __future__ import annotations

import httpx
import pytest

from headnote import config
from headnote.cases import ecourts_client as ec


# --------------------------------------------------------------- helpers
class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload or {}
        self.text = text or "{}"
        self.url = "https://vendor.test/api/partner/search"

    def json(self):
        return self._payload


def _row(cnr, regno, filing="", **kw):
    row = {
        "cnr": cnr, "registrationNumber": regno, "filingNumber": filing or regno,
        "caseType": "CC", "caseStatus": "PENDING",
        "courtName": "District and Sessions Court Gwalior",
        "petitioners": ["State Government"], "respondents": ["Viney"],
        "respondentAdvocates": ["VISHNU SHIVAHARE"],
        "nextHearingDate": "2026-08-13",
    }
    row.update(kw)
    return row


def _live(monkeypatch, rows, status=200, text=""):
    monkeypatch.setattr(config, "CNR_API_MODE", "live")
    monkeypatch.setattr(config, "CNR_API_TOKEN", "t0ken")
    payload = {"data": {"results": rows}}
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _Resp(status, payload, text)

    monkeypatch.setattr(httpx, "get", fake_get)
    return captured


# --------------------------------------------------------------- guards
def test_number_without_a_court_is_refused():
    """'6345/2017' exists in dozens of courts across India. Searching it unscoped
    would return strangers' cases, so this must fail before any credit is spent."""
    with pytest.raises(ValueError, match="Pick the court"):
        ec.search_by_case_number(case_number="6345/2017")


def test_state_alone_is_an_acceptable_scope(monkeypatch):
    cap = _live(monkeypatch, [_row("MP07010272252017", "6345/2017")])
    ec.search_by_case_number(case_number="6345/2017", state="MP")
    assert ("StateCodes", "MP") in cap["params"]


def test_empty_number_is_refused():
    with pytest.raises(ValueError, match="case number"):
        ec.search_by_case_number(case_number="   ", court_code="MP0701")


# --------------------------------------------------- exactness re-grading
def test_exact_match_is_computed_here_not_trusted_from_the_vendor(monkeypatch):
    """The vendor ranks by relevance: asking for 1/2024 also returns 396/2024.
    Only OUR normalised comparison decides what counts as the case he typed."""
    _live(monkeypatch, [
        _row("MP07010026132024", "396/2024", filing="17409/2023"),   # near miss
        _row("MP07010346922023", "1/2024", filing="17330/2023"),     # exact
    ])
    out = ec.search_by_case_number(case_number="1/2024", court_code="MP0701")
    assert [c["exact_match"] for c in out] == [True, False], "exact must sort first"
    assert out[0]["registration_number"] == "1/2024"


def test_a_filing_number_match_is_shown_but_is_NOT_exact(monkeypatch):
    """The vendor searches registration OR filing number, but only the
    REGISTRATION number is what the court and the lawyer call the case by. A row
    that matched on the filing number alone is still worth showing — it may be
    his matter, not yet registered — but it must arrive UNTICKED and labelled,
    never presented as the case he asked for."""
    _live(monkeypatch, [_row("MP07010272252017", "6345/2017", filing="22284/2017")])
    out = ec.search_by_case_number(case_number="22284/2017", court_code="MP0701")
    assert out[0]["exact_match"] is False
    assert out[0]["matched_on"] == "filing"


def test_a_registration_match_ranks_above_a_filing_match(monkeypatch):
    """Two rows can both legitimately carry the typed number — one as its
    registration number, one as its filing number. The registration one is his."""
    _live(monkeypatch, [
        _row("MP07010346922023", "9001/2024", filing="1/2024"),   # filing match
        _row("MP07010026132024", "1/2024", filing="17409/2023"),  # registration match
    ])
    out = ec.search_by_case_number(case_number="1/2024", court_code="MP0701")
    assert [c["matched_on"] for c in out] == ["registration", "filing"]
    assert [c["exact_match"] for c in out] == [True, False]


def test_the_matter_number_is_the_registration_number(monkeypatch):
    """The number stored on the matter — the one printed on the board, in the
    diary and in every draft's cause-title — is the registration number. The
    filing number is kept as a fact on the record and used as the number only
    when the court record carries no registration number at all."""
    c = ec._normalise_webapi(_row("MP07010272252017", "6345/2017", filing="22284/2017"))
    assert (c["case_number"], c["case_year"]) == ("6345", "2017")
    assert c["filing_number"] == "22284/2017"
    assert c["case_number_source"] == "registration"

    unregistered = _row("MP07010272252017", "", filing="22284/2017")
    unregistered["registrationNumber"] = ""
    c2 = ec._normalise_webapi(unregistered)
    assert (c2["case_number"], c2["case_year"]) == ("22284", "2017")
    assert c2["case_number_source"] == "filing"


def test_two_digit_year_matches_a_four_digit_record(monkeypatch):
    """A handwritten '6345/17' must match the court's '6345/2017'."""
    _live(monkeypatch, [_row("MP07010272252017", "6345/2017")])
    out = ec.search_by_case_number(case_number="6345/17", court_code="MP0701")
    assert out[0]["exact_match"] is True


def test_no_result_is_an_empty_list_not_an_error(monkeypatch):
    _live(monkeypatch, [])
    assert ec.search_by_case_number(case_number="9999/2030", court_code="MP0701") == []


# --------------------------------------------------- what we send the vendor
def test_court_and_optional_filters_are_sent(monkeypatch):
    cap = _live(monkeypatch, [])
    ec.search_by_case_number(case_number="6345/2017", court_code="MP0701",
                             case_type="CC", pending_only=True)
    p = cap["params"]
    assert ("CaseNumbers", "6345/2017") in p
    assert ("CourtCodes", "MP0701") in p
    assert ("CaseTypes", "CC") in p
    assert ("CaseStatuses", "PENDING") in p


def test_pending_filter_is_off_by_default(monkeypatch):
    """A disposed matter is still one an advocate may want on file (appeal,
    revision, execution) — never silently hide it."""
    cap = _live(monkeypatch, [])
    ec.search_by_case_number(case_number="6345/2017", court_code="MP0701")
    assert not any(k == "CaseStatuses" for k, _ in cap["params"])


# --------------------------------------------------- billing vs data failure
def test_out_of_credit_is_not_reported_as_no_such_case(monkeypatch):
    """Our wallet running dry must never look like the court having no such case.
    A distinct exception type keeps the two apart all the way to the UI."""
    _live(monkeypatch, [], status=402,
          text='{"error":{"code":"INSUFFICIENT_CREDITS"}}')
    with pytest.raises(ec.VendorAccountError):
        ec.search_by_case_number(case_number="6345/2017", court_code="MP0701")


def test_rate_limit_is_also_an_account_error(monkeypatch):
    _live(monkeypatch, [], status=429, text="slow down")
    with pytest.raises(ec.VendorAccountError):
        ec.search_by_case_number(case_number="6345/2017", court_code="MP0701")


def test_other_vendor_failures_stay_plain_errors(monkeypatch):
    _live(monkeypatch, [], status=500, text="boom")
    with pytest.raises(ValueError):
        ec.search_by_case_number(case_number="6345/2017", court_code="MP0701")


def test_live_mode_without_a_token_refuses(monkeypatch):
    monkeypatch.setattr(config, "CNR_API_MODE", "live")
    monkeypatch.setattr(config, "CNR_API_TOKEN", None)
    with pytest.raises(RuntimeError):
        ec.search_by_case_number(case_number="6345/2017", court_code="MP0701")


# --------------------------------------------------- the court picker
def test_court_options_filters_on_the_typed_fragment(monkeypatch):
    monkeypatch.setattr(ec, "_COURT_INDEX", [
        {"code": "UNKNOWN", "description": "Unknown Court"},
        {"code": "MP0701", "description": "District and Sessions Court, Gwalior, Madhya Pradesh"},
        {"code": "MPHC03", "description": "High Court of Madhya Pradesh, Gwalior"},
        {"code": "MH0101", "description": "District Court, Mumbai, Maharashtra"},
    ])
    codes = [c["code"] for c in ec.court_options("gwalior")]
    assert codes == ["MP0701", "MPHC03"], "UNKNOWN must never be offerable"
    assert [c["code"] for c in ec.court_options("mumbai")] == ["MH0101"]
    assert len(ec.court_options("")) == 3, "no query lists everything real"
    assert [c["code"] for c in ec.court_options("gwalior", limit=1)] == ["MP0701"]


def test_court_directory_failure_is_not_fatal(monkeypatch):
    """A dead enums call must leave the CNR lane working, not break the page."""
    monkeypatch.setattr(ec, "_COURT_INDEX", None)
    monkeypatch.setattr(config, "CNR_API_MODE", "live")

    def boom(*a, **k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(httpx, "get", boom)
    assert ec.court_options("gwalior") == []


# --------------------------------------------------- sections normalisation
def test_pipe_joined_acts_string_becomes_sections():
    """Live rows return actsAndSections as ONE string; only the list form used to
    be read, so every live case silently showed no sections at all."""
    c = ec._normalise_webapi(_row(
        "MP07010272252017", "6345/2017",
        actsAndSections="Indian Penal Code (I.P.C.), 1860 | Sections 304, 279, 337"))
    assert c["sections"] == ["Indian Penal Code (I.P.C.), 1860", "Sections 304, 279, 337"]
    assert c["sections_en"] == c["sections"]


def test_list_acts_still_work():
    c = ec._normalise_webapi(_row("X", "1/2020", actsAndSections=["IPC 302", "IPC 34"]))
    assert c["sections"] == ["IPC 302", "IPC 34"]


# --------------------------------------------------- mock mode
def test_mock_mode_returns_a_candidate_carrying_the_typed_number(monkeypatch):
    monkeypatch.setattr(config, "CNR_API_MODE", "mock")
    out = ec.search_by_case_number(case_number="6345/2017", court_code="MP0701")
    assert len(out) == 1
    assert out[0]["registration_number"] == "6345/2017"
    assert out[0]["exact_match"] is True
    assert out[0]["source"] == "mock"


def test_cnr_lookup_also_separates_billing_from_a_bad_number(monkeypatch):
    """The same wallet failure reaches the plain CNR lane, whose UI maps a 400 to
    'that is not a valid CNR' — so it must NOT come back as a ValueError."""
    monkeypatch.setattr(config, "CNR_API_MODE", "live")
    monkeypatch.setattr(config, "CNR_API_TOKEN", "t0ken")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(
        402, {}, '{"error":{"code":"INSUFFICIENT_CREDITS"}}'))
    with pytest.raises(ec.VendorAccountError):
        ec.fetch_cnr("MP07010272252017")
