"""POST /api/draft/{id}/blocks — the write-through behind the document field column.

The field column on the V2 document view lets the advocate edit a party, a ground or
the prayer in place. `GET /api/draft/{id}/docx` renders from the blocks PERSISTED with
the draft, so if an edit does not reach the server the page shows the correction while
the downloaded .docx still carries the old text — a lawyer handing the wrong document
across the counter. These tests pin the three things that stop that happening:

  1. the edit is actually stored, and the .docx source sees it;
  2. `answers` is MERGED, not replaced (it also holds html_hi/html_en/data — a
     wholesale write from the browser would silently drop them);
  3. somebody else's draft cannot be edited.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from headnote.api.app import app
from headnote.drafter import storage


@pytest.fixture()
def client():
    return TestClient(app)


def _make_draft(user_id=None):
    d = storage.create_draft(
        story_id="bail",
        template_version=1,
        lang="hi",
        answers={
            "html_hi": "<p>original</p>",
            "data": {"applicant_name": "Ramesh"},
            "blocks": [["court", "न्यायालय सत्र न्यायाधीश, ग्वालियर"],
                       ["applicant", "आवेदक —— रमेश वर्मा"],
                       ["ground", "1. यह कि, आवेदक निर्दोष है।"]],
        },
        user_id=user_id,
    )
    return d


EDITED = [["court", "न्यायालय सत्र न्यायाधीश, ग्वालियर"],
          ["applicant", "आवेदक —— श्रीमती सुनीता देवी"],
          ["ground", "1. यह कि, आवेदिका निर्दोष है।"]]


def test_edit_is_persisted_so_the_docx_matches_the_page(client):
    d = _make_draft()
    r = client.post(f"/api/draft/{d.id}/blocks", json={"blocks": EDITED})
    assert r.status_code == 200, r.text
    assert r.json()["saved"] == 3

    stored = storage.get_draft(d.id)
    blocks = (stored.answers or {}).get("blocks")
    assert blocks[1][1] == "आवेदक —— श्रीमती सुनीता देवी"
    assert "रमेश वर्मा" not in str(blocks), "the pre-edit text survived the save"


def test_answers_are_merged_not_replaced(client):
    """The browser only knows about `blocks`. If this endpoint wrote `answers`
    wholesale, the draft would lose its rendered HTML and its extracted data."""
    d = _make_draft()
    client.post(f"/api/draft/{d.id}/blocks", json={"blocks": EDITED})
    answers = storage.get_draft(d.id).answers or {}
    assert answers.get("html_hi") == "<p>original</p>"
    assert (answers.get("data") or {}).get("applicant_name") == "Ramesh"


def test_another_advocates_draft_cannot_be_edited(client):
    """A draft that belongs to somebody is only theirs to change — same rule the
    .docx export already applies."""
    d = _make_draft(user_id="00000000-0000-0000-0000-0000000000aa")
    r = client.post(f"/api/draft/{d.id}/blocks", json={"blocks": EDITED})
    assert r.status_code in (401, 403), r.status_code
    unchanged = (storage.get_draft(d.id).answers or {}).get("blocks")
    assert unchanged[1][1] == "आवेदक —— रमेश वर्मा"


def test_unknown_draft_is_404(client):
    r = client.post("/api/draft/does-not-exist/blocks", json={"blocks": EDITED})
    assert r.status_code == 404


def test_empty_or_malformed_blocks_are_refused(client):
    """Refusing loudly matters more than usual here: silently accepting an empty
    list would wipe the blocks and leave the .docx export with nothing to render."""
    d = _make_draft()
    for payload in ({"blocks": []}, {"blocks": ["not-a-pair"]}, {"blocks": [["only-role"]]}):
        r = client.post(f"/api/draft/{d.id}/blocks", json=payload)
        assert r.status_code == 400, (payload, r.status_code)
    kept = (storage.get_draft(d.id).answers or {}).get("blocks")
    assert len(kept) == 3, "a refused save must not have touched the stored blocks"


def test_a_table_block_survives_the_round_trip(client):
    """HC bail carries real tables (prior-bail history, crime details). They are
    dicts, not text, and must not be stringified into '[object Object]'."""
    d = _make_draft()
    table = {"widths": [1.5, 3.0], "rows": [["Date", "Court"], ["01.01.2026", "Sessions"]]}
    r = client.post(f"/api/draft/{d.id}/blocks",
                    json={"blocks": [["court", "X"], ["table", table]]})
    assert r.status_code == 200
    stored = (storage.get_draft(d.id).answers or {}).get("blocks")
    assert isinstance(stored[1][1], dict)
    assert stored[1][1]["rows"][1][0] == "01.01.2026"
