"""Cost dashboard tests.

Two layers:
  1. Telemetry aggregation extensions (per_task, confidence_histogram,
     hot_users, daily_trend, alerts) — direct calls to get_summary().
  2. The /admin/cost-dashboard HTML route — served publicly (auth lives
     in the JS that fetches /admin/telemetry).

All tests use a temp SQLite DB and require zero real API access.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "test_dash.db"
    monkeypatch.setattr("headnote.config.FEEDBACK_DB", db)
    from headnote.api import telemetry
    telemetry.init_telemetry_db()
    yield db


def _insert_row(db_path, *, task_type="situation", primary_model="claude-sonnet-4-6",
                 escalated=0, cost_paise=500, confidence=8, success=1,
                 user_id=None, hours_ago=0, latency_ms=2000):
    """Helper: insert a synthetic telemetry row."""
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO query_telemetry (ts, task_type, primary_model, escalated, "
        "total_cost_paise, confidence, latency_ms, success, user_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, task_type, primary_model, escalated, cost_paise, confidence,
         latency_ms, success, user_id),
    )
    conn.commit()
    conn.close()


# ============================================================================
# get_summary() — extended aggregations
# ============================================================================

def test_summary_per_task_aggregates(tmp_db):
    _insert_row(tmp_db, task_type="situation", cost_paise=400)
    _insert_row(tmp_db, task_type="situation", cost_paise=600)
    _insert_row(tmp_db, task_type="digest", cost_paise=300)
    _insert_row(tmp_db, task_type="headnote", cost_paise=5500)
    from headnote.api.telemetry import get_summary
    s = get_summary(days=7)
    assert s["per_task"]["situation"]["calls"] == 2
    assert s["per_task"]["situation"]["total_paise"] == 1000
    assert s["per_task"]["situation"]["avg_paise"] == 500.0
    assert s["per_task"]["headnote"]["avg_paise"] == 5500.0


def test_summary_confidence_histogram(tmp_db):
    for conf in [5, 5, 5, 7, 9, 9, None]:
        _insert_row(tmp_db, confidence=conf)
    from headnote.api.telemetry import get_summary
    s = get_summary(days=7)
    hist = s["confidence_histogram"]
    assert hist[5] == 3
    assert hist[7] == 1
    assert hist[9] == 2
    # NULL confidence rows excluded from histogram
    assert sum(hist.values()) == 6


def test_summary_hot_users_top_10_by_spend(tmp_db):
    for uid, paise in [("a", 100), ("b", 5000), ("c", 200), ("d", 3000)]:
        _insert_row(tmp_db, user_id=uid, cost_paise=paise)
    _insert_row(tmp_db, user_id=None, cost_paise=99999)  # anonymous bucket
    from headnote.api.telemetry import get_summary
    s = get_summary(days=7)
    # Anonymous tops the list (highest spend); then b > d > c > a
    ordered_ids = [u["user_id"] for u in s["hot_users"]]
    assert ordered_ids[0] == "(anonymous)"
    assert ordered_ids[1] == "b"
    assert ordered_ids[2] == "d"


def test_summary_daily_trend(tmp_db):
    _insert_row(tmp_db, cost_paise=100, hours_ago=0)
    _insert_row(tmp_db, cost_paise=200, hours_ago=25)  # yesterday
    _insert_row(tmp_db, cost_paise=300, hours_ago=49)  # 2 days ago
    from headnote.api.telemetry import get_summary
    s = get_summary(days=7)
    daily = s["daily_trend"]
    assert len(daily) >= 2
    days = {d["day"]: d for d in daily}
    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert today_key in days


def test_summary_alert_high_escalation_rate(tmp_db):
    # 5 generation calls, 3 escalated -> 60% > 25% threshold
    for _ in range(2):
        _insert_row(tmp_db, task_type="situation", escalated=0)
    for _ in range(3):
        _insert_row(tmp_db, task_type="situation", escalated=1,
                    primary_model="claude-opus-4-6")
    from headnote.api.telemetry import get_summary
    s = get_summary(days=7)
    assert s["escalation_rate_pct"] == 60.0
    msgs = [a["message"] for a in s["alerts"]]
    assert any("escalating" in m.lower() for m in msgs), s["alerts"]


def test_summary_alert_high_avg_cost(tmp_db):
    # Two queries averaging ₹15 each -> exceeds ₹12 threshold
    _insert_row(tmp_db, cost_paise=1500)
    _insert_row(tmp_db, cost_paise=1500)
    from headnote.api.telemetry import get_summary
    s = get_summary(days=7)
    assert s["avg_cost_paise_per_call"] == 1500
    msgs = [a["message"] for a in s["alerts"]]
    assert any("Average cost" in m for m in msgs)


def test_summary_alert_hot_user(tmp_db):
    # One identified user with ₹600/day spend (over ₹500 threshold)
    _insert_row(tmp_db, user_id="whale", cost_paise=60_000)
    from headnote.api.telemetry import get_summary
    s = get_summary(days=1)
    msgs = [a["message"] for a in s["alerts"]]
    assert any("whale" in m for m in msgs)


def test_summary_anonymous_not_in_hot_user_alerts(tmp_db):
    """Anonymous bucket should NEVER trigger the 'review this user' alert
    even if it dominates spend — there's no user to review."""
    _insert_row(tmp_db, user_id=None, cost_paise=1_000_000)
    from headnote.api.telemetry import get_summary
    s = get_summary(days=1)
    hot_user_alerts = [a for a in s["alerts"] if a.get("metric") == "hot_user"]
    assert hot_user_alerts == []


def test_summary_empty_db_returns_zeros(tmp_db):
    from headnote.api.telemetry import get_summary
    s = get_summary(days=7)
    assert s["total_queries"] == 0
    assert s["total_cost_paise"] == 0
    assert s["escalation_rate_pct"] == 0
    assert s["confidence_histogram"] == {}
    assert s["alerts"] == []


# ============================================================================
# /admin/cost-dashboard HTML route
# ============================================================================

@pytest.fixture
def client(tmp_db, monkeypatch):
    monkeypatch.setattr("headnote.config.ADMIN_TOKEN", "dash-test-token")
    with patch("headnote.api.app._get_kanoon_client", return_value=None):
        from headnote.api.app import app
        with TestClient(app) as c:
            yield c


def test_cost_dashboard_returns_html(client):
    """Dashboard HTML is served publicly — the JS inside it handles auth."""
    resp = client.get("/admin/cost-dashboard")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    # Sanity-check the page has the elements the dashboard needs
    assert "Cost Dashboard" in body
    assert "chart.js" in body.lower()
    assert "Authorization" in body  # token sent as Bearer
    assert "/admin/telemetry" in body


def test_cost_dashboard_loads_when_no_admin_token_set(monkeypatch, tmp_db):
    """Even without ADMIN_TOKEN, the HTML page still serves (so operator
    can SEE the misconfiguration message in the gate prompt rather than a 503)."""
    monkeypatch.setattr("headnote.config.ADMIN_TOKEN", None)
    with patch("headnote.api.app._get_kanoon_client", return_value=None):
        from headnote.api.app import app
        with TestClient(app) as c:
            resp = c.get("/admin/cost-dashboard")
    assert resp.status_code == 200
    # API endpoint still 503; HTML page itself is public
    with patch("headnote.api.app._get_kanoon_client", return_value=None):
        from headnote.api.app import app
        with TestClient(app) as c:
            api = c.get("/admin/telemetry",
                        headers={"Authorization": "Bearer anything"})
    assert api.status_code == 503
