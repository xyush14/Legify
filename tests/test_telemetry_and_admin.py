"""Telemetry + admin endpoint tests.

Uses a temp SQLite DB per test (via monkeypatch on config.FEEDBACK_DB) so
real feedback.db isn't touched. Anthropic mocked the same way as the
other endpoint tests.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---- mock infra

class FakeAnthropic:
    def __init__(self):
        self.calls: list[dict] = []
        self.responses: list[tuple[str, dict]] = []

    def queue(self, text, usage=None):
        usage = usage or {"input_tokens": 100, "output_tokens": 50,
                          "cache_creation_input_tokens": 0,
                          "cache_read_input_tokens": 0}
        self.responses.append((text, usage))

    def __call__(self, system_prompt, user_prompt, *, model="", cache=True):
        self.calls.append({"model": model, "system_prompt": system_prompt,
                           "user_prompt": user_prompt, "cache": cache})
        if not self.responses:
            raise RuntimeError(f"FakeAnthropic exhausted at call #{len(self.calls)}")
        return self.responses.pop(0)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Redirect telemetry + feedback storage to a temp SQLite file."""
    db = tmp_path / "test_telemetry.db"
    monkeypatch.setattr("headnote.config.FEEDBACK_DB", db)
    # Re-init so the table exists in the new DB
    from headnote.api import telemetry
    telemetry.init_telemetry_db()
    yield db


@pytest.fixture
def fake_anthropic():
    fake = FakeAnthropic()
    with patch("headnote.llm.router.call_claude_cached", side_effect=fake):
        yield fake


@pytest.fixture
def client(fake_anthropic, tmp_db, monkeypatch):
    """TestClient with admin token configured."""
    monkeypatch.setattr("headnote.config.ADMIN_TOKEN", "test-token-12345")
    monkeypatch.setattr("headnote.config.ENABLE_OPUS_ESCALATION", True)
    with patch("headnote.api.app._get_kanoon_client", return_value=None):
        from headnote.api.app import app
        with TestClient(app) as c:
            yield c


# ============================================================================
# Telemetry recording
# ============================================================================

def test_situation_request_records_telemetry(client, fake_anthropic, tmp_db):
    fake_anthropic.queue('{"cases": []}\nCONFIDENCE: 8')
    resp = client.post("/api/situation", json={
        "situation": "Some legal scenario text here", "style": "journal",
    })
    assert resp.status_code == 200

    import sqlite3
    conn = sqlite3.connect(tmp_db)
    rows = conn.execute(
        "SELECT task_type, primary_model, escalated, total_cost_paise, confidence FROM query_telemetry"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "situation"
    assert row[1] == "claude-sonnet-4-6"
    assert row[2] == 0   # not escalated
    assert row[3] > 0    # paid something
    assert row[4] == 8   # confidence


def test_low_confidence_does_not_escalate(client, fake_anthropic, tmp_db):
    """Auto-escalation is off: low-confidence Sonnet stays on Sonnet.

    Lawyers can opt into Opus via the explicit deep_mode toggle; the
    auto-retry was stacking two LLM calls and blowing past Render's
    request budget.
    """
    fake_anthropic.queue('{"cases": []}\nCONFIDENCE: 4')
    resp = client.post("/api/situation", json={
        "situation": "Another situation that would have escalated",
        "style": "journal",
    })
    assert resp.status_code == 200
    assert resp.json()["meta"]["escalated_to_opus"] is False
    assert resp.json()["meta"]["model"] == "claude-sonnet-4-6"

    import sqlite3
    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT escalated, primary_model FROM query_telemetry"
    ).fetchone()
    conn.close()
    assert row[0] == 0                       # not escalated
    assert row[1] == "claude-sonnet-4-6"     # stayed on Sonnet


def test_deep_mode_forces_opus_and_skips_retry(client, fake_anthropic, tmp_db):
    fake_anthropic.queue('{"cases": []}\nCONFIDENCE: 3')  # low conf, but...
    resp = client.post("/api/situation", json={
        "situation": "Premium-tier query with deep_mode",
        "style": "journal",
        "deep_mode": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["model"] == "claude-opus-4-6"
    assert body["meta"]["deep_mode"] is True
    # No retry — deep_mode disables confidence-based escalation
    assert len(fake_anthropic.calls) == 1
    # escalated_to_opus is False — Opus was the FIRST model, not an upgrade
    assert body["meta"]["escalated_to_opus"] is False


def test_translate_records_telemetry(client, fake_anthropic, tmp_db, monkeypatch):
    monkeypatch.setattr("headnote.config.ANTHROPIC_API_KEY", "sk-ant-test")
    fake_anthropic.queue("translated text")  # no must-preserve tokens -> OK
    resp = client.post("/api/translate", json={
        "payload": {"cases": [{"ratio": "Held — short ratio with no tokens"}]},
    })
    assert resp.status_code == 200

    import sqlite3
    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT task_type, primary_model FROM query_telemetry"
    ).fetchone()
    conn.close()
    assert row[0] == "translate"
    assert row[1] == "claude-haiku-4-5"


# ============================================================================
# /admin/telemetry endpoint
# ============================================================================

def test_admin_telemetry_requires_bearer_token(client):
    # No auth header
    resp = client.get("/admin/telemetry")
    assert resp.status_code == 401
    assert "Bearer" in resp.json()["detail"]


def test_admin_telemetry_rejects_wrong_token(client):
    resp = client.get("/admin/telemetry", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 403


def test_admin_telemetry_returns_empty_summary_initially(client):
    resp = client.get("/admin/telemetry",
                      headers={"Authorization": "Bearer test-token-12345"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_queries"] == 0
    assert body["total_cost_paise"] == 0


def test_admin_telemetry_summarises_recorded_queries(client, fake_anthropic, tmp_db):
    # Three queries: 2 situation (default Sonnet) + 1 digest (Sonnet)
    fake_anthropic.queue('{"cases": []}\nCONFIDENCE: 8')
    fake_anthropic.queue('{"topic": "x", "sub_topics": []}\nCONFIDENCE: 9')
    fake_anthropic.queue('{"cases": []}\nCONFIDENCE: 5')

    client.post("/api/situation", json={"situation": "abc def ghi jkl mno", "style": "journal"})
    client.post("/api/digest", json={"topic": "circumstantial evidence topic"})
    client.post("/api/situation", json={"situation": "another scenario to record", "style": "journal"})

    resp = client.get("/admin/telemetry?days=7",
                      headers={"Authorization": "Bearer test-token-12345"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_queries"] == 3
    assert body["total_cost_paise"] > 0
    # Auto-escalation is disabled; nothing escalated.
    assert body["escalation_rate_pct"] == 0.0
    assert any("sonnet" in m.lower() for m in body["cost_by_model"])


def test_admin_telemetry_disabled_when_no_token_configured(monkeypatch, fake_anthropic, tmp_db):
    monkeypatch.setattr("headnote.config.ADMIN_TOKEN", None)
    with patch("headnote.api.app._get_kanoon_client", return_value=None):
        from headnote.api.app import app
        with TestClient(app) as c:
            resp = c.get("/admin/telemetry", headers={"Authorization": "Bearer anything"})
    assert resp.status_code == 503
    assert "ADMIN_TOKEN" in resp.json()["detail"]


# ============================================================================
# ENABLE_OPUS_ESCALATION feature flag
# ============================================================================

def test_disable_opus_escalation_keeps_sonnet_on_low_confidence(monkeypatch, fake_anthropic, tmp_db):
    monkeypatch.setattr("headnote.config.ENABLE_OPUS_ESCALATION", False)
    monkeypatch.setattr("headnote.config.ADMIN_TOKEN", "test")
    with patch("headnote.api.app._get_kanoon_client", return_value=None):
        from headnote.api.app import app
        with TestClient(app) as c:
            # Low confidence — would normally trigger Opus, but disabled
            fake_anthropic.queue('{"cases": []}\nCONFIDENCE: 3')
            resp = c.post("/api/situation", json={
                "situation": "Test scenario with escalation disabled",
                "style": "journal",
            })
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["model"] == "claude-sonnet-4-6"
    assert body["meta"]["escalated_to_opus"] is False
    # Only ONE call — no auto-retry when flag is off
    assert len(fake_anthropic.calls) == 1
