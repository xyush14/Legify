"""V2 private-beta gate.

Two properties matter and both are load-bearing:

  1. A non-tester cannot reach a V2-only endpoint (403 not_in_beta).
  2. The gate is INVISIBLE to everyone else — the endpoints the live /app and
     /settings pages already call must keep working for non-testers. A
     regression here would break paying customers, which is far worse than
     the beta leaking.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from headnote import config
from headnote.entitlements import CurrentUser
from headnote.entitlements.auth import get_current_user
from headnote.entitlements import beta as beta_mod


TESTER = "tester@example.test"
STRANGER = "stranger@example.test"


@pytest.fixture(autouse=True)
def _clean_beta_table():
    """Each test starts with an empty DB allowlist and a private V2."""
    beta_mod.remove_tester(TESTER)
    beta_mod.remove_tester(STRANGER)
    original = config.V2_PUBLIC
    config.V2_PUBLIC = False
    yield
    config.V2_PUBLIC = original
    beta_mod.remove_tester(TESTER)
    beta_mod.remove_tester(STRANGER)


def _app_for(email: str) -> TestClient:
    """A tiny app exposing one beta-gated route, with auth stubbed to `email`."""
    app = FastAPI()

    @app.get("/gated")
    def gated(user: CurrentUser = Depends(beta_mod.require_beta)):
        return {"ok": True, "email": user.email}

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="00000000-0000-0000-0000-0000000000aa", email=email,
        role="authenticated", raw_claims={},
    )
    return TestClient(app)


# ------------------------------------------------------------------ is_beta

def test_stranger_is_not_beta():
    assert beta_mod.is_beta(STRANGER) is False


def test_founder_is_always_beta():
    founder = next(iter(config.FOUNDER_EMAILS))
    assert beta_mod.is_beta(founder) is True


def test_db_tester_is_beta_and_revocable():
    assert beta_mod.is_beta(TESTER) is False
    beta_mod.add_tester(TESTER, notes="unit test")
    assert beta_mod.is_beta(TESTER) is True
    assert beta_mod.remove_tester(TESTER) is True
    assert beta_mod.is_beta(TESTER) is False


def test_match_is_case_and_space_insensitive():
    beta_mod.add_tester(TESTER)
    assert beta_mod.is_beta("  " + TESTER.upper() + " ") is True


def test_no_email_is_not_beta():
    assert beta_mod.is_beta(None) is False
    assert beta_mod.is_beta("") is False


def test_v2_public_opens_the_door_for_everyone():
    """The ship switch: one env var, no code change, no emptying the list."""
    assert beta_mod.is_beta(STRANGER) is False
    config.V2_PUBLIC = True
    assert beta_mod.is_beta(STRANGER) is True


def test_add_tester_rejects_a_non_address():
    with pytest.raises(ValueError):
        beta_mod.add_tester("not-an-email")


# ------------------------------------------------------------- the dependency

def test_gated_endpoint_403s_for_a_stranger():
    r = _app_for(STRANGER).get("/gated")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_in_beta"


def test_gated_endpoint_allows_a_tester():
    beta_mod.add_tester(TESTER)
    r = _app_for(TESTER).get("/gated")
    assert r.status_code == 200
    assert r.json()["email"] == TESTER


# --------------------------------------------- the gate must stay invisible

def test_no_draft_dna_route_is_beta_gated():
    """Draft DNA belongs to every signed-in advocate, not to a beta list.

    The layout-mirroring routes (/layout /capture /template /generate /render)
    used to be `require_beta` because only /draft-dna called them. Two things
    changed: the beta is over (V2 is public), and the fields drafting screen at
    /draft/template/<id> — which every paying user is on — now calls /layout on
    load and offers ".docx in your own format". Leaving them gated meant unsetting
    one env var would silently switch the product's main differentiator off for
    the entire user base.

    Draft DNA is per-advocate by construction (every read and write is keyed by
    his own user id), so `get_current_user` is the whole access rule. This test is
    the tripwire against re-gating it.
    """
    from headnote.api import draft_dna

    for route in draft_dna.router.routes:
        dep = getattr(route, "dependant", None)
        deps = {d.call for d in dep.dependencies} if dep else set()
        assert beta_mod.require_beta not in deps, (
            f"{route.path} is beta-gated — Draft DNA must work for every "
            f"signed-in advocate, not only testers")


def test_every_home_route_is_gated():
    """home.html is the only caller of these, so all of them are beta-only."""
    from headnote.api import notesheets

    for route in notesheets.router.routes:
        dep = getattr(route, "dependant", None)
        deps = {d.call for d in dep.dependencies} if dep else set()
        assert beta_mod.require_beta in deps, f"{route.path} is not beta-gated"


def test_every_one_door_draft_route_is_gated():
    """The V2 /draft screen is the only caller of /api/draft/{one,skeleton,
    questions,preflight}. Nothing on the live /app surface touches them, so all
    four are beta-only — and the legacy /api/draft/* routes next to them stay
    ungated, which is why these live in their own router."""
    from headnote.api import draft_one

    for route in draft_one.router.routes:
        dep = getattr(route, "dependant", None)
        deps = {d.call for d in dep.dependencies} if dep else set()
        assert beta_mod.require_beta in deps, f"{route.path} is not beta-gated"
    assert {r.path for r in draft_one.router.routes} == {
        "/api/draft/one", "/api/draft/skeleton",
        "/api/draft/questions", "/api/draft/preflight"}


def test_the_legacy_drafting_endpoints_stay_open_for_existing_users():
    """/app and the 8 public /draft/<type> pages call /from-prompt and
    /from-document today. Gating either would break paying customers."""
    from headnote.drafter import api as drafter_api

    for route in drafter_api.router.routes:
        dep = getattr(route, "dependant", None)
        deps = {d.call for d in dep.dependencies} if dep else set()
        assert beta_mod.require_beta not in deps, f"{route.path} must not require beta"
