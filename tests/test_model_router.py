"""Model router regression tests.

All Anthropic SDK calls are mocked — these tests are deterministic, free,
and don't depend on the IK cache or API keys. They cover:

  - The routing table (task_type -> model)
  - `force_model` overrides routing AND disables auto-retry
  - Sonnet + low confidence + generation task -> retries with Opus
  - Confidence parsing edge cases
  - Cost-in-paise calculation across all three model tiers
  - `cost_paise` is the SUM of both calls when a retry fires
  - Haiku tasks return `confidence_score=None`
  - rerank (Sonnet but not a "generation" task) skips confidence + retry
  - Invalid task_type and force_model raise ValueError
"""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import patch

import pytest

from headnote.llm import router
from headnote.llm.router import (
    HAIKU_MODEL,
    SONNET_MODEL,
    OPUS_MODEL,
    RouteResult,
    calculate_cost_paise,
    parse_and_strip_confidence,
    route_call,
)


# ====================================================================
# Test infrastructure: fake `call_claude_cached` that records every call
# and returns canned responses programmed by the test.
# ====================================================================

class FakeAnthropic:
    """Records (model, system_prompt, user_prompt, cache) per call. The
    canned response queue is consumed FIFO; each entry is a `(text, usage)`
    pair. Tests pre-load this queue.
    """

    def __init__(self):
        self.calls: list[dict] = []
        self.responses: list[tuple[str, dict]] = []

    def queue(self, text: str, usage: Optional[dict] = None) -> None:
        usage = usage or {"input_tokens": 100, "output_tokens": 50,
                          "cache_creation_input_tokens": 0,
                          "cache_read_input_tokens": 0}
        self.responses.append((text, usage))

    def __call__(self, system_prompt, user_prompt, *, model="", cache=True):
        self.calls.append({
            "model": model,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "cache": cache,
        })
        if not self.responses:
            raise RuntimeError(
                f"FakeAnthropic exhausted — call #{len(self.calls)} unhandled "
                f"(model={model}, user_prompt={user_prompt[:80]!r}). "
                "Queue more responses with fake.queue(...)."
            )
        return self.responses.pop(0)


@pytest.fixture
def fake_anthropic():
    """Patch `call_claude_cached` so no real API hits."""
    fake = FakeAnthropic()
    with patch.object(router, "call_claude_cached", side_effect=fake):
        yield fake


# ====================================================================
# Routing table — task_type -> default model
# ====================================================================

@pytest.mark.parametrize("task_type,expected_model", [
    ("translation",  HAIKU_MODEL),
    ("verification", HAIKU_MODEL),
    ("extraction",   HAIKU_MODEL),
    ("situation",    SONNET_MODEL),
    ("digest",       SONNET_MODEL),
    ("rerank",       SONNET_MODEL),
    ("headnote",     OPUS_MODEL),
])
def test_routing_table_picks_correct_model(fake_anthropic, task_type, expected_model):
    fake_anthropic.queue("response text\nCONFIDENCE: 8")
    result = route_call(task_type, {"system_prompt": "sys", "user_prompt": "user"})
    assert result.model_name == expected_model
    assert fake_anthropic.calls[0]["model"] == expected_model


def test_unknown_task_type_raises():
    with pytest.raises(ValueError, match="Unknown task_type"):
        route_call("not_a_task", {"system_prompt": "x", "user_prompt": "y"})


# ====================================================================
# force_model overrides routing
# ====================================================================

@pytest.mark.parametrize("force,expected_model", [
    ("haiku",  HAIKU_MODEL),
    ("sonnet", SONNET_MODEL),
    ("opus",   OPUS_MODEL),
    ("HAIKU",  HAIKU_MODEL),  # case-insensitive alias
    ("claude-opus-4-7", "claude-opus-4-7"),  # full id passthrough
])
def test_force_model_overrides_routing(fake_anthropic, force, expected_model):
    fake_anthropic.queue("x\nCONFIDENCE: 8")
    result = route_call("situation", {"system_prompt": "s", "user_prompt": "u"}, force_model=force)
    assert result.model_name == expected_model
    assert fake_anthropic.calls[0]["model"] == expected_model


def test_invalid_force_model_raises():
    with pytest.raises(ValueError, match="force_model"):
        route_call(
            "situation",
            {"system_prompt": "x", "user_prompt": "y"},
            force_model="gpt-4-but-typoed",
        )


# ====================================================================
# Confidence injection — only for generation tasks
# ====================================================================

@pytest.mark.parametrize("gen_task", ["situation", "digest", "headnote"])
def test_generation_tasks_get_confidence_suffix(fake_anthropic, gen_task):
    fake_anthropic.queue("answer\nCONFIDENCE: 9")
    route_call(gen_task, {"system_prompt": "s", "user_prompt": "the question"})
    sent_user_prompt = fake_anthropic.calls[0]["user_prompt"]
    assert "the question" in sent_user_prompt
    assert "CONFIDENCE:" in sent_user_prompt
    assert "1-10" in sent_user_prompt


@pytest.mark.parametrize("non_gen", ["translation", "verification", "extraction", "rerank"])
def test_non_generation_tasks_do_not_get_confidence_suffix(fake_anthropic, non_gen):
    fake_anthropic.queue("any response")
    route_call(non_gen, {"system_prompt": "s", "user_prompt": "the input"})
    sent_user_prompt = fake_anthropic.calls[0]["user_prompt"]
    assert sent_user_prompt == "the input"
    assert "CONFIDENCE:" not in sent_user_prompt


def test_haiku_tasks_return_no_confidence_score(fake_anthropic):
    # Haiku tasks shouldn't even attempt to parse confidence
    fake_anthropic.queue("YES")
    result = route_call("verification", {"system_prompt": "s", "user_prompt": "u"})
    assert result.confidence_score is None
    assert result.response == "YES"


# ====================================================================
# Confidence stripping
# ====================================================================

def test_confidence_stripped_from_response(fake_anthropic):
    fake_anthropic.queue('{"answer": 42}\nCONFIDENCE: 8')
    result = route_call("situation", {"system_prompt": "s", "user_prompt": "u"})
    assert result.response == '{"answer": 42}'
    assert result.confidence_score == 8


def test_unparseable_confidence_returns_none_no_retry(fake_anthropic):
    # No CONFIDENCE line at all → confidence=None, no retry
    fake_anthropic.queue('{"answer": 42}')
    result = route_call("situation", {"system_prompt": "s", "user_prompt": "u"})
    assert result.confidence_score is None
    assert result.response == '{"answer": 42}'
    assert len(fake_anthropic.calls) == 1, "should not have retried"


def test_out_of_range_confidence_returns_none(fake_anthropic):
    fake_anthropic.queue("answer\nCONFIDENCE: 99")
    result = route_call("situation", {"system_prompt": "s", "user_prompt": "u"})
    assert result.confidence_score is None
    assert len(fake_anthropic.calls) == 1


# ====================================================================
# Sonnet -> Opus auto-retry
# ====================================================================

def test_sonnet_low_confidence_retries_with_opus(fake_anthropic):
    # First call: Sonnet returns low confidence
    fake_anthropic.queue("first attempt\nCONFIDENCE: 4")
    # Second call: Opus succeeds
    fake_anthropic.queue("upgraded answer\nCONFIDENCE: 9")

    result = route_call("situation", {"system_prompt": "s", "user_prompt": "u"})

    assert len(fake_anthropic.calls) == 2
    assert fake_anthropic.calls[0]["model"] == SONNET_MODEL
    assert fake_anthropic.calls[1]["model"] == OPUS_MODEL
    # Final result is from Opus
    assert result.model_name == OPUS_MODEL
    assert result.response == "upgraded answer"
    assert result.confidence_score == 9


def test_sonnet_high_confidence_no_retry(fake_anthropic):
    fake_anthropic.queue("good answer\nCONFIDENCE: 8")
    result = route_call("situation", {"system_prompt": "s", "user_prompt": "u"})
    assert result.model_name == SONNET_MODEL
    assert len(fake_anthropic.calls) == 1


def test_sonnet_exactly_threshold_does_not_retry(fake_anthropic):
    # Threshold is 7 — score of 7 does NOT trigger retry (strict <)
    fake_anthropic.queue("answer\nCONFIDENCE: 7")
    result = route_call("situation", {"system_prompt": "s", "user_prompt": "u"})
    assert result.model_name == SONNET_MODEL
    assert result.confidence_score == 7
    assert len(fake_anthropic.calls) == 1


def test_force_model_disables_auto_retry(fake_anthropic):
    # User forced Sonnet and got low confidence — we respect the force.
    fake_anthropic.queue("answer\nCONFIDENCE: 3")
    result = route_call(
        "situation",
        {"system_prompt": "s", "user_prompt": "u"},
        force_model="sonnet",
    )
    assert result.model_name == SONNET_MODEL
    assert result.confidence_score == 3
    assert len(fake_anthropic.calls) == 1


def test_opus_low_confidence_no_further_retry(fake_anthropic):
    # Headnote task -> Opus. Even at low confidence, no further upgrade exists.
    fake_anthropic.queue("opus answer\nCONFIDENCE: 4")
    result = route_call("headnote", {"system_prompt": "s", "user_prompt": "u"})
    assert result.model_name == OPUS_MODEL
    assert result.confidence_score == 4
    assert len(fake_anthropic.calls) == 1


def test_rerank_skips_confidence_and_retry(fake_anthropic):
    # rerank runs on Sonnet but is NOT a generation task — no confidence
    # injection, no retry even if response happens to contain a CONFIDENCE line.
    fake_anthropic.queue('[{"id":"A","score":0.9}]\nCONFIDENCE: 2')
    result = route_call("rerank", {"system_prompt": "s", "user_prompt": "u"})
    assert result.model_name == SONNET_MODEL
    assert result.confidence_score is None
    # Response NOT stripped (router doesn't parse confidence on non-gen tasks)
    assert "CONFIDENCE:" in result.response
    assert len(fake_anthropic.calls) == 1


# ====================================================================
# Cost calculation (paise)
# ====================================================================

def test_cost_paise_haiku_basic():
    usage = {"input_tokens": 1_000_000, "output_tokens": 0,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    # Haiku input = $0.80 per 1M.  $0.80 * 84 INR/USD * 100 paise/INR = 6720 paise
    assert calculate_cost_paise(usage, HAIKU_MODEL) == 6720


def test_cost_paise_sonnet_output_dominates():
    usage = {"input_tokens": 0, "output_tokens": 1_000_000,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    # Sonnet output = $15 per 1M.  $15 * 84 * 100 = 126_000 paise
    assert calculate_cost_paise(usage, SONNET_MODEL) == 126_000


def test_cost_paise_opus_with_cache_tiers():
    # 1M input + 1M cache write + 1M cache read + 0 output, on Opus.
    # input $15, cache_write $18.75, cache_read $1.50.  Sum = $35.25
    # 35.25 * 84 * 100 = 296100 paise
    usage = {"input_tokens": 1_000_000, "output_tokens": 0,
             "cache_creation_input_tokens": 1_000_000,
             "cache_read_input_tokens": 1_000_000}
    assert calculate_cost_paise(usage, OPUS_MODEL) == 296_100


def test_cost_paise_includes_retry_total(fake_anthropic):
    """When Sonnet retries with Opus, cost_paise = Sonnet cost + Opus cost."""
    # Sonnet attempt: 1000 input, 500 output, low confidence
    fake_anthropic.queue(
        "bad\nCONFIDENCE: 3",
        {"input_tokens": 1000, "output_tokens": 500,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    )
    # Opus retry: same tokens
    fake_anthropic.queue(
        "good\nCONFIDENCE: 9",
        {"input_tokens": 1000, "output_tokens": 500,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    )

    result = route_call("situation", {"system_prompt": "s", "user_prompt": "u"})

    sonnet_cost = calculate_cost_paise(
        {"input_tokens": 1000, "output_tokens": 500,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        SONNET_MODEL,
    )
    opus_cost = calculate_cost_paise(
        {"input_tokens": 1000, "output_tokens": 500,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        OPUS_MODEL,
    )
    assert result.cost_paise == sonnet_cost + opus_cost
    # Sanity: Opus alone is much more expensive than Sonnet
    assert opus_cost > 3 * sonnet_cost


# ====================================================================
# Confidence parser unit tests (no API at all)
# ====================================================================

@pytest.mark.parametrize("input_text,expected_text,expected_score", [
    ("Answer.\nCONFIDENCE: 8",              "Answer.",                 8),
    ('{"x":1}\nCONFIDENCE: 5',              '{"x":1}',                 5),
    ("Trailing\nCONFIDENCE: 10\n\n",        "Trailing",                10),
    ("Just text",                            "Just text",               None),
    ("inline CONFIDENCE: 7 mid-sentence",    "inline CONFIDENCE: 7 mid-sentence", None),
    ("Answer\nCONFIDENCE: 0",                "Answer\nCONFIDENCE: 0",   None),  # out of range
    ("Answer\nCONFIDENCE: 11",               "Answer\nCONFIDENCE: 11",  None),
    ("Answer\nCONFIDENCE: abc",              "Answer\nCONFIDENCE: abc", None),
])
def test_parse_and_strip_confidence(input_text, expected_text, expected_score):
    text, score = parse_and_strip_confidence(input_text)
    assert text == expected_text
    assert score == expected_score


# ====================================================================
# RouteResult is a NamedTuple — unpacks as 4-tuple per spec
# ====================================================================

def test_route_result_unpacks_as_4_tuple(fake_anthropic):
    fake_anthropic.queue("hi\nCONFIDENCE: 9")
    model, response, cost, conf = route_call(
        "situation", {"system_prompt": "s", "user_prompt": "u"}
    )
    assert isinstance(model, str)
    assert isinstance(response, str)
    assert isinstance(cost, int)
    assert conf == 9


def test_route_result_named_access(fake_anthropic):
    fake_anthropic.queue("hi\nCONFIDENCE: 9")
    r = route_call("situation", {"system_prompt": "s", "user_prompt": "u"})
    assert r.model_name == SONNET_MODEL
    assert r.confidence_score == 9


# ====================================================================
# Cache flag passes through correctly
# ====================================================================

def test_cache_flag_passed_through(fake_anthropic):
    fake_anthropic.queue("ok\nCONFIDENCE: 8")
    route_call(
        "situation",
        {"system_prompt": "s", "user_prompt": "u", "cache": False},
    )
    assert fake_anthropic.calls[0]["cache"] is False


def test_cache_defaults_true(fake_anthropic):
    fake_anthropic.queue("ok\nCONFIDENCE: 8")
    route_call("situation", {"system_prompt": "s", "user_prompt": "u"})
    assert fake_anthropic.calls[0]["cache"] is True
