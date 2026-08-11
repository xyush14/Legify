"""The court's own orders and judgments, filed into the matter's folder.

eCourts publishes the court's signed order PDFs. Listing them is free (they ride
along in the case record we already hold); each PDF costs a vendor credit (₹3.75
measured 2026-08-10). Every behaviour pinned here protects one of two things:

  • the lawyer's file — a JSON error body must never be filed as "Judgment
    dated 04/01/2026", and an order already held must never be bought twice
  • the request path — the filename reaches a paid, authenticated URL, so only a
    filename the COURT gave us for THAT matter may ever be fetched
"""

from __future__ import annotations

import httpx
import pytest

from headnote import config
from headnote.cases import courtsync
from headnote.cases import ecourts_client as ec


def _case(interim=(), judgments=()):
    return ec._normalise_webapi({
        "cnr": "MP07010272252017", "registrationNumber": "6345/2017",
        "courtName": "District and Sessions Court Gwalior",
        "petitioners": ["State Government"], "respondents": ["Viney"],
        "interimOrders": list(interim), "judgmentOrders": list(judgments),
    }, "MP07010272252017")


_INTERIM = {"orderDate": "2025-07-10", "orderType": "Interim Order",
            "orderUrl": "https://v/api/partner/case/MP07010272252017/order/order-1.pdf"}
_JUDGMENT = {"orderDate": "2026-01-04", "orderType": "Judgment",
             "orderUrl": "https://v/api/partner/case/MP07010272252017/order/judgment-1.pdf"}


class _Resp:
    def __init__(self, status=200, content=b"", ctype="application/pdf", payload=None):
        self.status_code = status
        self.content = content
        self.headers = {"content-type": ctype}
        self._payload = payload or {}
        self.text = "{}"
        self.url = "https://vendor.test/order"

    def json(self):
        return self._payload


# ------------------------------------------------- both order lists survive
def test_interim_and_judgment_orders_are_both_kept():
    """_first() returned whichever list was non-empty FIRST, so a case carrying
    interim orders AND a judgment silently lost the judgment — the single most
    important document on the file."""
    c = _case(interim=[_INTERIM], judgments=[_JUDGMENT])
    kinds = [o["kind"] for o in ec.case_orders(c)]
    assert kinds == ["interim", "judgment"]


def test_order_list_carries_date_title_and_filename():
    o = ec.case_orders(_case(interim=[_INTERIM]))[0]
    assert o["date"] == "2025-07-10"
    assert o["title"] == "Interim Order"
    assert o["filename"] == "order-1.pdf"
    assert o["fetchable"] is True


def test_an_order_with_no_downloadable_copy_is_still_listed():
    """"The court has an order here that we cannot pull" is information the
    lawyer needs. Hiding the row would read as the order not existing."""
    o = ec.case_orders(_case(interim=[{"orderDate": "2025-07-10",
                                       "orderType": "Interim Order"}]))[0]
    assert o["fetchable"] is False
    assert o["date"] == "2025-07-10", "the row still tells him it exists"


def test_no_orders_is_an_empty_list():
    assert ec.case_orders(_case()) == []
    assert ec.case_orders({}) == []


# ------------------------------------------------- filename discipline
@pytest.mark.parametrize("bad", [
    "../../etc/passwd", "a/b.pdf", "order-1.exe", "order-1", "", "   ",
    "x" * 200 + ".pdf", "order 1.pdf",
])
def test_bad_filenames_are_refused_before_any_call(bad, monkeypatch):
    """This value comes from a THIRD PARTY and lands in a URL path on a paid,
    authenticated endpoint. A slash or '..' must never redirect the fetch."""
    monkeypatch.setattr(httpx, "get", lambda *a, **k: pytest.fail("must not call the vendor"))
    with pytest.raises(ValueError):
        ec.fetch_order_pdf("MP07010272252017", bad)


def test_a_bad_cnr_is_refused(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: pytest.fail("must not call the vendor"))
    with pytest.raises(ValueError):
        ec.fetch_order_pdf("nope", "order-1.pdf")


def test_filename_is_taken_from_the_url_tail_or_a_bare_field():
    assert ec._order_filename({"orderUrl": "https://x/y/order-7.pdf?t=1"}) == "order-7.pdf"
    assert ec._order_filename({"filename": "judgment-2.pdf"}) == "judgment-2.pdf"
    assert ec._order_filename({"orderUrl": "https://x/y/../z"}) == ""
    assert ec._order_filename({}) == ""


# ------------------------------------------------- the download itself
def _live(monkeypatch, resp, second=None):
    monkeypatch.setattr(config, "CNR_API_MODE", "live")
    monkeypatch.setattr(config, "CNR_API_TOKEN", "t0ken")
    calls = []

    def fake_get(url, **kw):
        calls.append((url, kw.get("params")))
        return second if (second and len(calls) > 1) else resp

    monkeypatch.setattr(httpx, "get", fake_get)
    return calls


def test_raw_pdf_bytes_are_returned(monkeypatch):
    calls = _live(monkeypatch, _Resp(content=b"%PDF-1.4 real order"))
    data, ctype = ec.fetch_order_pdf("MP07010272252017", "order-1.pdf")
    assert data.startswith(b"%PDF-")
    assert "pdf" in ctype
    assert "/order/order-1.pdf" in calls[0][0]


def test_a_json_envelope_pointing_at_the_pdf_is_followed(monkeypatch):
    """The endpoint may hand back the PDF or a JSON envelope naming a URL."""
    _live(monkeypatch,
          _Resp(content=b'{"data":{"url":"https://cdn/x.pdf"}}', ctype="application/json",
                payload={"data": {"url": "https://cdn/x.pdf"}}),
          second=_Resp(content=b"%PDF-1.4 downloaded"))
    data, _ = ec.fetch_order_pdf("MP07010272252017", "order-1.pdf")
    assert data == b"%PDF-1.4 downloaded"


def test_a_json_error_body_is_never_returned_as_the_order(monkeypatch):
    """Filing a JSON error blob into a case folder captioned "Judgment dated
    04/01/2026" is the worst outcome available here."""
    _live(monkeypatch, _Resp(content=b'{"error":"nope"}', ctype="application/json",
                             payload={"error": "nope"}))
    with pytest.raises(ValueError):
        ec.fetch_order_pdf("MP07010272252017", "order-1.pdf")


def test_html_or_any_non_pdf_is_refused(monkeypatch):
    _live(monkeypatch, _Resp(content=b"<html>login</html>", ctype="text/html"))
    with pytest.raises(ValueError, match="not a PDF"):
        ec.fetch_order_pdf("MP07010272252017", "order-1.pdf")


def test_an_empty_file_is_refused(monkeypatch):
    _live(monkeypatch, _Resp(content=b"", ctype="application/pdf"))
    with pytest.raises(ValueError, match="empty"):
        ec.fetch_order_pdf("MP07010272252017", "order-1.pdf")


def test_out_of_credit_is_an_account_error_not_a_missing_order(monkeypatch):
    r = _Resp(status=402)
    r.text = '{"error":{"code":"INSUFFICIENT_CREDITS"}}'
    _live(monkeypatch, r)
    with pytest.raises(ec.VendorAccountError):
        ec.fetch_order_pdf("MP07010272252017", "order-1.pdf")


def test_signed_defaults_to_the_certified_copy(monkeypatch):
    """An advocate filing or serving a copy wants the one bearing the court's
    signature, so the certified copy is the default and signed=False is opt-in."""
    calls = _live(monkeypatch, _Resp(content=b"%PDF-1.4 x"))
    ec.fetch_order_pdf("MP07010272252017", "order-1.pdf")
    assert not calls[0][1], "no signed param → the vendor's certified default"
    calls.clear()
    ec.fetch_order_pdf("MP07010272252017", "order-1.pdf", signed=False)
    assert calls[0][1] == {"signed": "false"}


def test_mock_mode_returns_a_genuinely_valid_pdf(monkeypatch):
    monkeypatch.setattr(config, "CNR_API_MODE", "mock")
    data, ctype = ec.fetch_order_pdf("MP07010272252017", "order-1.pdf")
    assert data.startswith(b"%PDF-") and data.rstrip().endswith(b"%%EOF")
    assert ctype == "application/pdf"


# ------------------------------------------------- the sweep notices new orders
def test_a_new_order_is_reported_with_the_courts_filename():
    stored = {"orders": [_INTERIM]}
    fresh = {"orders": [_INTERIM, _JUDGMENT]}
    new = [u for u in courtsync.diff(stored, fresh) if u["kind"] == "new_order"]
    assert len(new) == 1
    assert new[0]["court_filename"] == "judgment-1.pdf"
    assert new[0]["date"] == "2026-01-04"
    assert new[0]["order_type"] == "Judgment"


def test_the_same_orders_twice_are_not_new():
    """_order_key read date/type/link while the vendor sends
    orderDate/orderType/orderUrl, so every live order hashed to the same empty
    string — which cut both ways and is why this needs pinning."""
    fresh = {"orders": [_INTERIM, _JUDGMENT]}
    assert [u for u in courtsync.diff(fresh, fresh) if u["kind"] == "new_order"] == []


def test_two_distinct_orders_do_not_collide():
    stored = {"orders": []}
    fresh = {"orders": [_INTERIM, _JUDGMENT]}
    new = [u for u in courtsync.diff(stored, fresh) if u["kind"] == "new_order"]
    assert len(new) == 2, "distinct orders must hash distinctly"
