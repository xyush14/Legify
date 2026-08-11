"""The admin console's door: password sign-in, session tokens, and the
promise that a session is accepted everywhere the root token is.

The point of these tests is that the console is the ONLY admin surface a
non-technical operator will ever use, and it is protected by one password.
So the things worth pinning are the ones that would quietly open it: a
missing password behaving as "no password required", a tampered token being
accepted, an expired session still working, or one of the three older admin
routers not honouring the session and silently falling back to a prompt.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from headnote import config
from headnote.api import admin_session


TOKEN = "test-admin-token-1234567890"
EMAIL = "hello@headnote.in"
PASSWORD = "correct-horse-battery"


@pytest.fixture
def admin_env(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(config, "ADMIN_EMAIL", EMAIL)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setattr(config, "ADMIN_SESSION_DAYS", 30)
    admin_session._FAILURES.clear()
    yield
    admin_session._FAILURES.clear()


@pytest.fixture
def client():
    from headnote.api.app import app
    return TestClient(app)


# ------------------------------------------------------------------ config

def test_login_unavailable_without_password(monkeypatch):
    """No ADMIN_PASSWORD must mean 'nobody can sign in', never 'anybody can'."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(config, "ADMIN_EMAIL", EMAIL)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", None)
    assert admin_session.password_login_available() is False
    assert admin_session.check_credentials(EMAIL, "") is False
    assert admin_session.check_credentials(EMAIL, "anything") is False


def test_login_unavailable_without_admin_token(monkeypatch):
    """No signing key means sessions cannot exist at all."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", None)
    monkeypatch.setattr(config, "ADMIN_EMAIL", EMAIL)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", PASSWORD)
    assert admin_session.password_login_available() is False


# ------------------------------------------------------------------ credentials

def test_correct_credentials_accepted(admin_env):
    assert admin_session.check_credentials(EMAIL, PASSWORD) is True
    # Email is normalised the way a phone keyboard would produce it.
    assert admin_session.check_credentials("  HELLO@Headnote.IN  ", PASSWORD) is True


@pytest.mark.parametrize("email,password", [
    (EMAIL, "wrong"),
    (EMAIL, ""),
    ("someone@else.com", PASSWORD),
    ("", PASSWORD),
    (EMAIL, PASSWORD + "x"),
    (EMAIL, PASSWORD[:-1]),
])
def test_wrong_credentials_refused(admin_env, email, password):
    assert admin_session.check_credentials(email, password) is False


# ------------------------------------------------------------------ sessions

def test_session_roundtrip(admin_env):
    token, exp = admin_session.issue_session(EMAIL)
    assert exp > time.time()
    assert admin_session.verify_session(token) == EMAIL


def test_tampered_session_rejected(admin_env):
    token, _ = admin_session.issue_session(EMAIL)
    prefix, payload, sig = token.split(".", 2)

    # Flipped signature.
    assert admin_session.verify_session(f"{prefix}.{payload}.{sig[:-2]}xx") is None
    # Re-signed payload from a different key is what an attacker actually has.
    forged = admin_session._b64e(b'{"e":"attacker@evil.com","exp":9999999999}')
    assert admin_session.verify_session(f"{prefix}.{forged}.{sig}") is None
    # Garbage in every shape.
    for junk in ("", "nonsense", "hns1.", "hns1.a.b", "Bearer x"):
        assert admin_session.verify_session(junk) is None


def test_expired_session_rejected(admin_env):
    token, _ = admin_session.issue_session(EMAIL, ttl_days=-1)
    assert admin_session.verify_session(token) is None


def test_rotating_admin_token_invalidates_sessions(admin_env, monkeypatch):
    """The documented emergency lever: change ADMIN_TOKEN, everyone is out."""
    token, _ = admin_session.issue_session(EMAIL)
    assert admin_session.verify_session(token) == EMAIL
    monkeypatch.setattr(config, "ADMIN_TOKEN", "a-completely-different-token")
    assert admin_session.verify_session(token) is None


# ------------------------------------------------------------------ the shared gate

def test_bearer_accepts_root_token_and_session(admin_env):
    assert admin_session.verify_admin_bearer(f"Bearer {TOKEN}") == "ops"
    token, _ = admin_session.issue_session(EMAIL)
    assert admin_session.verify_admin_bearer(f"Bearer {token}") == EMAIL
    assert admin_session.verify_admin_bearer("Bearer nope") is None
    assert admin_session.verify_admin_bearer(None) is None
    assert admin_session.verify_admin_bearer(TOKEN) is None      # missing scheme


# ------------------------------------------------------------------ HTTP

def test_login_endpoint_happy_path(admin_env, client):
    r = client.post("/admin/api/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == EMAIL
    assert admin_session.verify_session(body["token"]) == EMAIL

    # And that session opens the door it was minted for.
    ok = client.get("/admin/api/session",
                    headers={"Authorization": f"Bearer {body['token']}"})
    assert ok.status_code == 200
    assert ok.json()["actor"] == EMAIL


def test_login_endpoint_rejects_wrong_password(admin_env, client):
    r = client.post("/admin/api/login", json={"email": EMAIL, "password": "nope"})
    assert r.status_code == 401
    # The refusal must not reveal which half was wrong.
    detail = r.json()["detail"].lower()
    assert "email or password" in detail


def test_login_lockout_after_repeated_failures(admin_env, client):
    for _ in range(admin_session._MAX_FAILURES):
        client.post("/admin/api/login", json={"email": EMAIL, "password": "nope"})
    # Even the CORRECT password is refused once locked out.
    r = client.post("/admin/api/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 429


def test_protected_routes_reject_anonymous(admin_env, client):
    for path in ("/admin/api/services", "/admin/api/overview", "/admin/api/ops",
                 "/admin/api/session"):
        assert client.get(path).status_code == 401, path


def test_session_opens_all_three_legacy_routers(admin_env, client):
    """A console session must work on admin.py, admin_v2.py AND
    partners_admin.py. If any one of them still compared against the raw
    ADMIN_TOKEN, that page would start prompting again — which is the exact
    thing this change exists to remove."""
    token, _ = admin_session.issue_session(EMAIL)
    h = {"Authorization": f"Bearer {token}"}
    for path in ("/admin/access-grants",      # admin.py
                 "/admin/v2/users?limit=1",   # admin_v2.py
                 "/admin/partners/list"):     # partners_admin.py
        r = client.get(path, headers=h)
        # 200 or a downstream 5xx (no Supabase in CI) — anything but a 401/403,
        # which would mean the gate rejected a valid session.
        assert r.status_code not in (401, 403), f"{path} -> {r.status_code}"


def test_login_config_is_public_and_leaks_nothing(admin_env, client):
    r = client.get("/admin/api/login-config")
    assert r.status_code == 200
    body = r.json()
    assert body == {"password_login": True, "admin_token_set": True}
    assert PASSWORD not in r.text and EMAIL not in r.text


# ------------------------------------------------------------------ wallet capture

def test_record_vendor_balance_parses_the_402_body(admin_env, tmp_path, monkeypatch):
    """The eCourts wallet figure exists in exactly one place — the refusal
    body — so parsing it is the whole mechanism behind the balance tile."""
    from headnote.api import admin_console
    monkeypatch.setattr(config, "FEEDBACK_DB", tmp_path / "t.db")

    body = ('{"error":{"code":"INSUFFICIENT_CREDITS",'
            '"message":"Insufficient credits. Required: ₹0.60, Available: ₹0.20"}}')
    assert admin_console.record_vendor_balance(body) == 0.20
    assert admin_console._kv_get("ecourts_balance_inr")[0] == "0.20"

    # A body that is not about credits must not overwrite a good reading.
    assert admin_console.record_vendor_balance('{"error":"something else"}') is None
    assert admin_console._kv_get("ecourts_balance_inr")[0] == "0.20"
