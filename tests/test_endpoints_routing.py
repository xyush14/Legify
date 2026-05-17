"""Endpoint integration tests — prove each /api/* route picks the right
model via the smart router.

These are HTTP-level tests using FastAPI's TestClient. The underlying
Anthropic SDK is mocked (via the same `call_claude_cached` patching pattern
as test_model_router.py), so they're deterministic, free, and don't need
ANTHROPIC_API_KEY or any cache file.

What's covered:
  /api/situation  -> Sonnet by default (cheaper than Opus, was the old default)
  /api/situation  -> verification-failure regen uses force_model=opus
  /api/digest     -> Sonnet
  /api/headnote   -> Opus
  meta block contains model + cost_paise + confidence_score
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---- the FakeAnthropic helper from test_model_router lives there;
#      we re-import its shape here so endpoints can be exercised end-to-end.

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
        self.calls.append({
            "model": model, "system_prompt": system_prompt,
            "user_prompt": user_prompt, "cache": cache,
        })
        if not self.responses:
            raise RuntimeError(
                f"FakeAnthropic exhausted at call #{len(self.calls)} "
                f"(model={model}). Queue more responses."
            )
        return self.responses.pop(0)


@pytest.fixture
def fake_anthropic():
    """Patches the LLM call site that endpoints reach through the router.
    The router itself remains the real code path."""
    fake = FakeAnthropic()
    # The router imports `call_claude_cached` into its own namespace, so
    # we patch the name as used there.
    with patch("headnote.llm.router.call_claude_cached", side_effect=fake):
        yield fake


@pytest.fixture
def client(fake_anthropic):
    """TestClient against the real FastAPI app, with Anthropic mocked.

    Forces curated-only retrieval (USE_IK_RETRIEVAL off) so we don't need
    the IK cache. The endpoints still exercise the router for the LLM call.
    """
    # Disable IK retrieval path for these tests — we want to isolate the
    # router behaviour, not the retrieval pipeline.
    with patch("headnote.api.app._get_kanoon_client", return_value=None):
        from headnote.api.app import app
        with TestClient(app) as c:
            yield c


# ============================================================================
# /api/situation — Sonnet by default
# ============================================================================

def test_situation_routes_to_sonnet_by_default(client, fake_anthropic):
    # Valid JSON with no cases (avoids the existence-filter dropping anything)
    # plus the confidence suffix
    fake_anthropic.queue('{"cases": [], "confidence": "low"}\nCONFIDENCE: 8')

    resp = client.post("/api/situation", json={
        "situation": "Some legal scenario, at least ten characters.",
        "style": "journal",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"]["model"] == "claude-sonnet-4-6"
    assert body["meta"]["confidence_score"] == 8
    assert body["meta"]["cost_paise"] > 0
    # Anthropic was called exactly once (high confidence -> no retry)
    assert len(fake_anthropic.calls) == 1
    assert fake_anthropic.calls[0]["model"] == "claude-sonnet-4-6"


def test_situation_low_confidence_auto_upgrades_to_opus(client, fake_anthropic):
    # First call (Sonnet) returns low confidence -> auto-retry
    fake_anthropic.queue('{"cases": []}\nCONFIDENCE: 3')
    # Second call (Opus) returns clean
    fake_anthropic.queue('{"cases": []}\nCONFIDENCE: 9')

    resp = client.post("/api/situation", json={
        "situation": "Another scenario, well over ten characters in length.",
        "style": "journal",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"]["model"] == "claude-opus-4-6"
    # cost_paise is the sum of both calls
    assert body["meta"]["cost_paise"] > 0
    assert len(fake_anthropic.calls) == 2
    assert fake_anthropic.calls[0]["model"] == "claude-sonnet-4-6"
    assert fake_anthropic.calls[1]["model"] == "claude-opus-4-6"


# ============================================================================
# /api/digest — Sonnet
# ============================================================================

def test_digest_routes_to_sonnet(client, fake_anthropic):
    fake_anthropic.queue(
        '{"topic": "circumstantial evidence", "sub_topics": []}\nCONFIDENCE: 8'
    )
    resp = client.post("/api/digest", json={
        "topic": "Circumstantial evidence requirements under Indian law",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"]["model"] == "claude-sonnet-4-6"
    assert body["meta"]["confidence_score"] == 8
    assert fake_anthropic.calls[0]["model"] == "claude-sonnet-4-6"


def test_digest_low_confidence_upgrades_to_opus(client, fake_anthropic):
    fake_anthropic.queue('{"topic": "x", "sub_topics": []}\nCONFIDENCE: 5')
    fake_anthropic.queue('{"topic": "x", "sub_topics": []}\nCONFIDENCE: 9')
    resp = client.post("/api/digest", json={"topic": "Some doctrinal question"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"]["model"] == "claude-opus-4-6"
    assert len(fake_anthropic.calls) == 2


# ============================================================================
# /api/headnote — Opus (the moat)
# ============================================================================

def test_headnote_routes_to_opus(client, fake_anthropic):
    # Empty headnotes -> only Opus runs (no Haiku verify needed)
    fake_anthropic.queue(
        '{"case_metadata": {}, "headnotes": [], "cases_referred": []}\nCONFIDENCE: 9'
    )
    resp = client.post("/api/headnote", json={
        # min_length is 200; pad accordingly
        "judgment_text": "1. " + ("This is a long judgment passage. " * 20),
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"]["model"] == "claude-opus-4-6"
    assert fake_anthropic.calls[0]["model"] == "claude-opus-4-6"
    # Headnote endpoint now uses cache=True so the gold-standard example
    # headnotes in the system prompt hit the prompt cache.
    assert fake_anthropic.calls[0]["cache"] is True


def test_headnote_no_auto_retry_even_at_low_confidence(client, fake_anthropic):
    # Empty headnotes -> only Opus runs, no Haiku verify, no upgrade path
    fake_anthropic.queue(
        '{"case_metadata": {}, "headnotes": [], "cases_referred": []}\nCONFIDENCE: 4'
    )
    resp = client.post("/api/headnote", json={
        "judgment_text": "1. " + ("Judgment text body content. " * 20),
    })
    assert resp.status_code == 200, resp.text
    # Single Opus call — confidence-based retry doesn't fire for headnote
    # (the router has no upgrade path past Opus), and with no headnotes
    # in the response the Haiku verify step is skipped.
    assert len(fake_anthropic.calls) == 1
    assert resp.json()["meta"]["confidence_score"] == 4


# ============================================================================
# Meta block shape
# ============================================================================

def test_meta_block_has_router_fields(client, fake_anthropic):
    fake_anthropic.queue('{"cases": []}\nCONFIDENCE: 8')
    resp = client.post("/api/situation", json={
        "situation": "valid situation text for the request",
        "style": "journal",
    })
    meta = resp.json()["meta"]
    # Router-specific fields
    assert "model" in meta
    assert "cost_paise" in meta
    assert "confidence_score" in meta
    # Backward-compat cost fields (derived from paise)
    assert "cost_inr" in meta
    assert "cost_usd" in meta
    # Timing
    assert "elapsed_seconds" in meta
    # Retrieval path indicator (curated-only because IK is mocked off)
    assert meta["retrieval_path"] == "curated-only"


def test_meta_cost_inr_is_paise_divided_by_100(client, fake_anthropic):
    fake_anthropic.queue('{"cases": []}\nCONFIDENCE: 8')
    resp = client.post("/api/situation", json={
        "situation": "valid situation text here, well over 10 chars",
        "style": "journal",
    })
    meta = resp.json()["meta"]
    assert abs(meta["cost_inr"] - meta["cost_paise"] / 100) < 1e-6
