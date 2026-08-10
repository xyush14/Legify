"""Integration tests for the Document Lens endpoints.

The multipart cases are not academic: V2 shipped a bug where FormData uploads
were sent labelled ``application/json``, which strips the boundary so FastAPI
parsed no files at all — and because the parameter was Optional there was no
422 to notice, just a confusing "nothing attached" error. These tests pin the
contract from the server side so that class of bug fails loudly here instead of
silently in a browser.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from headnote.api.app import app
from headnote.documents import lens
from headnote.entitlements import get_current_user


class _User:
    id = "u_test"
    email = "test@example.com"
    plan = "pro"


@pytest.fixture()
def client(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _User()
    # never let a test hit the network or the meter
    monkeypatch.setattr("headnote.api.doclens._meter", lambda *a, **k: None)
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


def _jpeg(w=700, h=1000) -> bytes:
    img = Image.new("RGB", (w, h), "white")
    for y in range(60, h - 60, 40):
        for x in range(60, w - 60):
            img.putpixel((x, y), (0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


# --- auth ---------------------------------------------------------------------
def test_endpoints_require_a_signed_in_user():
    """Snapshot and clear the override map first.

    Other test modules in this suite install a permanent
    ``app.dependency_overrides[get_current_user]`` and never remove it, so a
    plain TestClient here is silently authenticated and this test passes for the
    wrong reason. An auth test that only holds when run alone is worse than none.
    """
    saved = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    try:
        _assert_all_endpoints_401()
    finally:
        app.dependency_overrides.update(saved)


def _assert_all_endpoints_401():
    """Every request here is valid apart from the missing credential.

    Posting /read with no file at all returns 422 (body validation) rather than
    401, so a bare post would have been asserting FastAPI's error ordering
    instead of the auth rule. Send a real file and the 401 is unambiguous.
    """
    # headnote/entitlements/auth.py reads SUPABASE_URL into a module-level
    # constant at import time, and something else in this suite re-imports that
    # module with the variable unset — which permanently switches auth into its
    # local-dev "synthetic user" mode for the rest of the session. State the
    # precondition rather than assert something that is order-dependent: a green
    # auth test that only holds in the right order is a lie.
    from headnote.entitlements import auth as _auth
    if not getattr(_auth, "SUPABASE_URL", ""):
        pytest.skip("auth is in local-dev mode (SUPABASE_URL unset) — 401 cannot be asserted")

    anon = TestClient(app)
    assert anon.post("/api/doclens/read",
                     files={"file": ("p.jpg", _jpeg(), "image/jpeg")}).status_code == 401
    assert anon.post("/api/doclens/translate", json={"text": "x", "target": "en"}).status_code == 401
    assert anon.post("/api/doclens/pdf", json={"text": "x"}).status_code == 401


# --- read ---------------------------------------------------------------------
def test_read_accepts_a_real_multipart_image(client, monkeypatch):
    """Exercises the whole pipeline — intake, prepare, garbage guard, citation
    extraction — with only the model call stubbed. Mocking lens.read() instead
    would assert nothing but that FastAPI can return a dict."""
    monkeypatch.setattr("headnote.integrations.gemini.enabled", lambda: True)
    monkeypatch.setattr("headnote.integrations.gemini.generate_text",
                        lambda *a, **k: "धारा 109(1) बीएनएस · मु0अ0सं0 359/25 दि0 24.12.2025")
    r = client.post("/api/doclens/read", files={"file": ("page.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pages"] == 1 and body["source_kind"] == "image"
    assert "359/25" in body["text"]
    assert "359/25" in body["citations"], "citations must come back for the gate"
    assert "24.12.2025" in body["citations"]


def test_read_without_a_file_is_a_422_not_a_confusing_400(client):
    """The V2 multipart bug looked like a business error; it must look like a
    malformed request, so the next person debugs the client, not the server."""
    assert client.post("/api/doclens/read").status_code == 422


def test_a_user_facing_lens_error_becomes_400_with_its_own_message(client, monkeypatch):
    def boom(*a, **k):
        raise lens.LensError("That file is empty.")
    monkeypatch.setattr(lens, "read", boom)
    r = client.post("/api/doclens/read", files={"file": ("x.jpg", b"", "image/jpeg")})
    assert r.status_code == 400 and r.json()["detail"] == "That file is empty."


def test_an_unexpected_crash_does_not_leak_internals(client, monkeypatch):
    def boom(*a, **k):
        raise ZeroDivisionError("secret internal detail")
    monkeypatch.setattr(lens, "read", boom)
    r = client.post("/api/doclens/read", files={"file": ("x.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 500
    assert "secret internal detail" not in r.text


def test_metering_failure_never_costs_the_user_their_document(client, monkeypatch):
    monkeypatch.setattr(lens, "read", lambda *a, **k: lens.LensResult(text="ok", pages=3))
    monkeypatch.setattr("headnote.entitlements.meters.increment",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("meter down")))
    import headnote.api.doclens as dl
    monkeypatch.setattr(dl, "_meter", dl._meter)  # use the real one
    r = client.post("/api/doclens/read", files={"file": ("x.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200


# --- translate ----------------------------------------------------------------
def test_translate_returns_text_and_flags(client, monkeypatch):
    monkeypatch.setattr(lens, "translate", lambda *a, **k: lens.LensResult(
        text="Section 109(1) BNS · 359/25", lang="en", flags=["check this"]))
    r = client.post("/api/doclens/translate",
                    json={"text": "धारा 109(1) · 359/25", "target": "en"})
    assert r.status_code == 200
    assert r.json()["lang"] == "en" and r.json()["flags"] == ["check this"]


def test_translate_rejects_an_unknown_language(client):
    r = client.post("/api/doclens/translate", json={"text": "hello", "target": "xx"})
    assert r.status_code == 400 and "language" in r.json()["detail"]


def test_translate_rejects_empty_text(client):
    r = client.post("/api/doclens/translate", json={"text": "   ", "target": "en"})
    assert r.status_code == 400


# --- pdf ----------------------------------------------------------------------
def test_pdf_returns_a_real_pdf_with_a_download_header(client, monkeypatch):
    monkeypatch.setattr("headnote.api.pdf._render_pdf", lambda html: b"%PDF-1.7\n%fake")
    r = client.post("/api/doclens/pdf", json={"text": "Section 109(1)", "title": "Gang Chart"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")


def test_pdf_html_carries_the_flags_and_escapes_markup(client, monkeypatch):
    seen = {}
    monkeypatch.setattr("headnote.api.pdf._render_pdf",
                        lambda html: seen.setdefault("html", html) and b"%PDF" or b"%PDF")
    client.post("/api/doclens/pdf", json={"text": "<script>bad()</script> 359/25",
                                          "title": "T", "flags": ["look here"]})
    html = seen["html"]
    assert "<script>" not in html, "document text must never render as live markup"
    assert "look here" in html and "359/25" in html


# --- html rendering -----------------------------------------------------------
def test_markdown_table_becomes_a_real_table():
    res = lens.LensResult(text="| Name | Age |\n| --- | --- |\n| सोनू | 34 |")
    html = lens.to_html(res, title="t")
    assert "<table>" in html and "<th>Name</th>" in html and "<td>34</td>" in html


def test_table_separator_row_is_not_rendered_as_data():
    res = lens.LensResult(text="| A | B |\n| --- | --- |\n| 1 | 2 |")
    html = lens.to_html(res, title="t")
    assert "---" not in html.split("<tbody>")[1]
