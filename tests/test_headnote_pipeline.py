"""Headnote pipeline tests — Opus generation -> Haiku verification ->
per-headnote Opus retry on failure.

All Anthropic calls mocked. Verifies:
  - Opus called first with cache=True (so the cached examples land)
  - Haiku called second with the generated headnotes + judgment text
  - Failed headnote triggers a third Opus call (retry)
  - cost_paise is the sum of all stages
  - meta.verifications and meta.retried_letters surface in the response
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---- shared mock infrastructure

class FakeAnthropic:
    def __init__(self):
        self.calls: list[dict] = []
        self.responses: list[tuple[str, dict]] = []

    def queue(self, text, usage=None):
        usage = usage or {"input_tokens": 1000, "output_tokens": 500,
                          "cache_creation_input_tokens": 0,
                          "cache_read_input_tokens": 0}
        self.responses.append((text, usage))

    def __call__(self, system_prompt, user_prompt, *, model="", cache=True, **kwargs):
        self.calls.append({"model": model, "system_prompt": system_prompt,
                           "user_prompt": user_prompt, "cache": cache})
        if not self.responses:
            raise RuntimeError(f"FakeAnthropic exhausted at call #{len(self.calls)}")
        return self.responses.pop(0)


@pytest.fixture
def fake_anthropic():
    fake = FakeAnthropic()
    with patch("headnote.llm.router.call_claude_cached", side_effect=fake):
        yield fake


@pytest.fixture
def client(fake_anthropic, tmp_path, monkeypatch):
    monkeypatch.setattr("headnote.config.FEEDBACK_DB", tmp_path / "feedback.db")
    monkeypatch.setattr("headnote.config.ADMIN_TOKEN", None)
    from headnote.api.telemetry import init_telemetry_db
    init_telemetry_db()
    with patch("headnote.api.app._get_kanoon_client", return_value=None):
        from headnote.api.app import app
        with TestClient(app) as c:
            yield c


# ============================================================================
# Helpers — canned response bodies
# ============================================================================

def _opus_response(letters: list[str]) -> str:
    """Build an Opus response JSON with one journal_headnote per letter."""
    return json.dumps({
        "case_metadata": {
            "title": "Test v. State", "court": "Supreme Court",
            "bench": "X, Y, JJ.", "date_of_decision": "01-01-2020",
            "appeal_number": "Crl. App. 1 of 2020",
        },
        "headnotes": [
            {
                "letter": L,
                "journal_headnote": {
                    "statute_index": "Negotiable Instruments Act (26 of 1881), S. 138",
                    "catchword_chain": f"Catchword {L}",
                    "ratio": f"Held — ratio for {L}",
                    "negative_carve_out": "",
                    "paragraph_anchor": f"(Para {ord(L)})",
                    "per_judge_attribution": "",
                },
                "practitioner_notes": {
                    "one_line_topic": f"Topic {L}",
                    "gist": f"Gist {L}",
                    "quotable_phrase": f"Quote {L}",
                    "cross_refs": [],
                },
            }
            for L in letters
        ],
        "cases_referred": [],
    })


def _verify_response(letters_and_status: list[tuple[str, str]]) -> str:
    """Build a Haiku verification response.

    Each tuple: (letter, overall_status). status in {"verified","warning","failed"}.
    """
    return json.dumps({
        "verifications": [
            {
                "letter": L,
                "ratio_match": status,
                "anchor_match": status,
                "statute_format": "verified",
                "overall": status,
                "issues": [] if status == "verified" else [f"some issue with {L}"],
            }
            for L, status in letters_and_status
        ]
    })


_VALID_JUDGMENT = "1. " + ("This is judgment body text. " * 30)


# ============================================================================
# Tests
# ============================================================================

def test_headnote_clean_response_skips_retry(client, fake_anthropic):
    """All headnotes verified -> no retry, total cost = Opus + Haiku."""
    fake_anthropic.queue(_opus_response(["A", "B"]))
    fake_anthropic.queue(_verify_response([("A", "verified"), ("B", "verified")]))

    resp = client.post("/api/headnote", json={"judgment_text": _VALID_JUDGMENT})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"]["model"] == "claude-opus-4-6"
    # Verifications surfaced in meta
    assert len(body["meta"]["verifications"]) == 2
    assert all(v["overall"] == "verified" for v in body["meta"]["verifications"])
    assert body["meta"]["retried_letters"] == []
    # Two calls: Opus (generate) + Haiku (verify). No retry.
    assert len(fake_anthropic.calls) == 2
    assert fake_anthropic.calls[0]["model"] == "claude-opus-4-6"
    assert fake_anthropic.calls[0]["cache"] is True   # examples must be cached
    assert fake_anthropic.calls[1]["model"] == "claude-haiku-4-5"


def test_headnote_failed_verification_triggers_retry(client, fake_anthropic):
    """One headnote fails verification -> single Opus retry just for that letter."""
    fake_anthropic.queue(_opus_response(["A", "B"]))                    # initial
    fake_anthropic.queue(_verify_response([("A", "verified"), ("B", "failed")]))  # verify
    fake_anthropic.queue(_opus_response(["A", "B"]))                    # retry

    resp = client.post("/api/headnote", json={"judgment_text": _VALID_JUDGMENT})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "B" in body["meta"]["retried_letters"]
    assert "A" not in body["meta"]["retried_letters"]
    # 3 calls: Opus initial + Haiku verify + Opus retry
    assert len(fake_anthropic.calls) == 3
    # Retry call references the issue in the prompt
    retry_user_prompt = fake_anthropic.calls[2]["user_prompt"]
    assert "REGENERATE HEADNOTE (B)" in retry_user_prompt
    assert "issue with B" in retry_user_prompt


def test_headnote_warning_does_not_trigger_retry(client, fake_anthropic):
    """'warning' status (paraphrased, minor format) is NOT a retry trigger;
    only 'failed' (genuine fabrication) is. Avoids burning Opus credits on
    cosmetic issues."""
    fake_anthropic.queue(_opus_response(["A"]))
    fake_anthropic.queue(_verify_response([("A", "warning")]))
    resp = client.post("/api/headnote", json={"judgment_text": _VALID_JUDGMENT})
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["retried_letters"] == []
    # 2 calls only — no retry
    assert len(fake_anthropic.calls) == 2


def test_headnote_total_cost_sums_all_stages(client, fake_anthropic):
    """cost_paise must include Opus generation + Haiku verify + Opus retry."""
    # Each stage uses different token counts so we can identify them in the sum
    fake_anthropic.queue(
        _opus_response(["A"]),
        {"input_tokens": 10_000, "output_tokens": 1000,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    )
    fake_anthropic.queue(
        _verify_response([("A", "failed")]),
        {"input_tokens": 5_000, "output_tokens": 200,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    )
    fake_anthropic.queue(
        _opus_response(["A"]),
        {"input_tokens": 10_000, "output_tokens": 1000,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    )
    resp = client.post("/api/headnote", json={"judgment_text": _VALID_JUDGMENT})
    body = resp.json()
    # Expected: 2 × Opus(10K in + 1K out) + 1 × Haiku(5K in + 200 out)
    # Opus: 10K * 15/1M + 1K * 75/1M = 0.15 + 0.075 = 0.225 USD per call
    # Haiku: 5K * 0.8/1M + 200 * 4/1M = 0.004 + 0.0008 = 0.0048 USD
    # Total: 0.225 + 0.0048 + 0.225 = 0.4548 USD * 84 INR * 100 paise ≈ 3820
    # Just check the cost is in the right ballpark (Opus dominates).
    paise = body["meta"]["cost_paise"]
    assert paise > 3000, f"expected >3000 paise (Opus×2 + Haiku); got {paise}"
    assert paise < 5000, f"expected <5000 paise; got {paise}"


def test_headnote_verification_failure_does_not_crash(client, fake_anthropic):
    """If Haiku returns non-JSON, we degrade gracefully — no retry,
    no verifications, but the Opus headnotes still ship."""
    fake_anthropic.queue(_opus_response(["A"]))
    fake_anthropic.queue("this is not JSON at all")  # Haiku misbehaves
    resp = client.post("/api/headnote", json={"judgment_text": _VALID_JUDGMENT})
    assert resp.status_code == 200
    body = resp.json()
    # Opus headnote still shipped
    assert len(body["result"]["headnotes"]) == 1
    # Verifications empty (parse failed), no retry attempted
    assert body["meta"]["verifications"] == []
    assert body["meta"]["retried_letters"] == []
    # Just the two calls — Opus + Haiku (which returned garbage)
    assert len(fake_anthropic.calls) == 2


def test_headnote_caches_system_prompt(client, fake_anthropic):
    """Confirm cache=True is set on every Opus call so the cached examples
    in the system prompt land on the prompt cache."""
    fake_anthropic.queue(_opus_response(["A"]))
    fake_anthropic.queue(_verify_response([("A", "verified")]))
    resp = client.post("/api/headnote", json={"judgment_text": _VALID_JUDGMENT})
    assert resp.status_code == 200
    opus_call = fake_anthropic.calls[0]
    assert opus_call["model"] == "claude-opus-4-6"
    assert opus_call["cache"] is True
    # System prompt contains the cached examples
    assert "GOLD-STANDARD EXAMPLE" in opus_call["system_prompt"]
    assert "EXAMPLE 1" in opus_call["system_prompt"]


def test_headnote_empty_headnotes_skips_verification(client, fake_anthropic):
    """If Opus returns zero headnotes, no verification needed (Haiku not called)."""
    empty = json.dumps({"case_metadata": {}, "headnotes": [], "cases_referred": []})
    fake_anthropic.queue(empty)
    resp = client.post("/api/headnote", json={"judgment_text": _VALID_JUDGMENT})
    assert resp.status_code == 200
    # Only one call (Opus); no Haiku verify
    assert len(fake_anthropic.calls) == 1
