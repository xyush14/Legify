"""Translation pipeline tests — Haiku translation with citation verifier.

All Anthropic calls mocked. Verifies:
  - English legal paragraph with 3 citations -> all preserved on first try
  - Hindi -> English preserves Devanagari proper nouns + Latin citations
  - Citation dropped on first attempt -> retry succeeds
  - Citation missing after retry -> response flagged as "degraded"
  - Direction auto-detection
  - Must-preserve token extraction is exhaustive
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from headnote.translate import (
    _detect_direction,
    _extract_must_preserve_tokens,
    _verify_preserved,
    translate_payload_haiku,
)


# ---- mock infra shared with the router tests, copied to keep tests independent

class FakeAnthropic:
    def __init__(self):
        self.calls: list[dict] = []
        self.responses: list[tuple[str, dict]] = []

    def queue(self, text, usage=None):
        usage = usage or {"input_tokens": 200, "output_tokens": 100,
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
def fake_anthropic():
    fake = FakeAnthropic()
    with patch("headnote.llm.router.call_claude_cached", side_effect=fake):
        yield fake


# ============================================================================
# Helper unit tests (no API)
# ============================================================================

def test_detect_direction_english():
    assert _detect_direction("Held: the offence under S. 138 NI Act") == ("en", "hi")


def test_detect_direction_hindi():
    assert _detect_direction("अभिनिर्धारित — धारा 138 के अंतर्गत अपराध बनता है") == ("hi", "en")


def test_detect_direction_empty():
    assert _detect_direction("") == ("en", "hi")


def test_extract_must_preserve_tokens_catches_everything():
    text = ("Held — under S. 138 NI Act ((2014) 9 SCC 129) "
            "and Article 21 (Paras 14, 16-17). Also AIR 1999 SC 3762.")
    tokens = _extract_must_preserve_tokens(text)
    assert "(2014) 9 SCC 129" in tokens
    assert "S. 138" in tokens
    assert "Article 21" in tokens
    # Paragraph anchors in headnotes are always parenthesised — regex
    # only matches the canonical form to avoid false-positives in prose.
    assert any("Paras" in t and t.startswith("(") for t in tokens)
    assert "AIR 1999 SC 3762" in tokens
    assert "NI Act" in tokens


def test_verify_preserved_passes_when_all_present():
    inp = "ratio — S. 138 and Article 21. (Paras 14)"
    out = "अनुपात — S. 138 और Article 21. (Paras 14)"
    ok, preserved, missing = _verify_preserved(inp, out)
    assert ok
    assert not missing
    assert "S. 138" in preserved


def test_verify_preserved_fails_when_token_dropped():
    inp = "Held under S. 138 (2014) 9 SCC 129"
    out_with_drop = "अभिनिर्धारित S. 138 के तहत"  # dropped (2014) 9 SCC 129
    ok, preserved, missing = _verify_preserved(inp, out_with_drop)
    assert not ok
    assert "(2014) 9 SCC 129" in missing


# ============================================================================
# Full payload translation — mocked Haiku
# ============================================================================

def test_english_with_three_citations_all_preserved(fake_anthropic):
    """First-attempt success: Haiku returns all 3 citations verbatim."""
    payload = {
        "cases": [{
            "ratio": "Held — under S. 138 NI Act (per (2014) 9 SCC 129); see Article 21.",
            "case_id": "DASH-2014-SC",  # not a translatable field, skipped
        }],
    }
    # Haiku returns translation with all tokens preserved
    fake_anthropic.queue(
        "अभिनिर्धारित — S. 138 NI Act के अंतर्गत ((2014) 9 SCC 129 के अनुसार); Article 21 देखें."
    )

    translated, paise, quality, preserved = translate_payload_haiku(payload)

    assert quality == "ok"
    assert "(2014) 9 SCC 129" in preserved
    assert "S. 138" in preserved
    assert "Article 21" in preserved
    assert paise > 0
    # Only one Haiku call (no retry needed)
    assert len(fake_anthropic.calls) == 1
    # Case_id (technical field) is not translated
    assert translated["cases"][0]["case_id"] == "DASH-2014-SC"


def test_hindi_to_english_preserves_citations(fake_anthropic):
    """Auto-detects Hindi input, translates to English, preserves citations."""
    payload = {
        "cases": [{
            "ratio": "अभिनिर्धारित — S. 138 NI Act (2014) 9 SCC 129 के अंतर्गत।",
        }],
    }
    fake_anthropic.queue(
        "Held — under S. 138 NI Act (2014) 9 SCC 129."
    )
    translated, paise, quality, preserved = translate_payload_haiku(payload)
    assert quality == "ok"
    assert "(2014) 9 SCC 129" in preserved
    assert "S. 138" in preserved


def test_dropped_citation_triggers_retry_then_succeeds(fake_anthropic):
    """First attempt drops a citation -> retry with strict prompt -> succeeds."""
    payload = {
        "cases": [{
            "ratio": "Held — under (2014) 9 SCC 129; see Article 21 also.",
        }],
    }
    # First attempt drops (2014) 9 SCC 129
    fake_anthropic.queue("अभिनिर्धारित — के अंतर्गत; Article 21 भी देखें.")
    # Strict retry preserves both
    fake_anthropic.queue(
        "अभिनिर्धारित — (2014) 9 SCC 129 के अंतर्गत; Article 21 भी देखें."
    )

    translated, paise, quality, preserved = translate_payload_haiku(payload)

    assert quality == "ok"
    assert "(2014) 9 SCC 129" in preserved
    assert "Article 21" in preserved
    # Two calls: original + strict retry
    assert len(fake_anthropic.calls) == 2
    # Second call uses the stricter prompt (different system text)
    sys_first = fake_anthropic.calls[0]["system_prompt"]
    sys_retry = fake_anthropic.calls[1]["system_prompt"]
    assert sys_retry != sys_first
    assert "RETRY" in sys_retry
    assert "(2014) 9 SCC 129" in sys_retry  # explicitly listed as must-preserve


def test_still_missing_after_retry_returns_degraded(fake_anthropic):
    """If retry still drops a token, return best-effort + quality=degraded."""
    payload = {
        "cases": [{
            "ratio": "Held — under (2014) 9 SCC 129 and Article 21.",
        }],
    }
    # Both attempts drop (2014) 9 SCC 129
    fake_anthropic.queue("अभिनिर्धारित — Article 21 के अंतर्गत.")
    fake_anthropic.queue("अभिनिर्धारित — Article 21 केवल.")

    translated, paise, quality, preserved = translate_payload_haiku(payload)

    assert quality == "degraded"
    # Article 21 was preserved at least
    assert "Article 21" in preserved
    # (2014) 9 SCC 129 was dropped — not in preserved
    assert "(2014) 9 SCC 129" not in preserved
    assert len(fake_anthropic.calls) == 2


def test_multiple_fields_one_degraded_taints_overall(fake_anthropic):
    """One field's degradation makes the WHOLE response 'degraded'."""
    payload = {
        "cases": [
            {"ratio": "Under S. 138 NI Act."},                      # ok
            {"ratio": "Under (2019) 4 SCC 1."},                     # will fail
        ],
    }
    fake_anthropic.queue("S. 138 NI Act के अंतर्गत.")               # case 1: ok
    fake_anthropic.queue("के अंतर्गत.")                              # case 2: drop
    fake_anthropic.queue("केवल अंतर्गत.")                            # retry still drops
    translated, paise, quality, preserved = translate_payload_haiku(payload)
    assert quality == "degraded"


def test_non_translatable_fields_left_alone(fake_anthropic):
    """Technical fields like case_id, citation, paragraph_anchor are
    not in TRANSLATABLE_FIELDS — they stay unchanged."""
    payload = {
        "cases": [{
            "case_id": "DASH-2014-SC",
            "citation": "(2014) 9 SCC 129",
            "year": 2014,
            "paragraph_anchor": "(Paras 14, 16-17)",
            "ratio": "Held — under S. 138 NI Act.",  # only this gets translated
        }],
    }
    fake_anthropic.queue("अभिनिर्धारित — S. 138 NI Act के अंतर्गत.")
    translated, paise, quality, preserved = translate_payload_haiku(payload)
    case = translated["cases"][0]
    assert case["case_id"] == "DASH-2014-SC"
    assert case["citation"] == "(2014) 9 SCC 129"
    assert case["year"] == 2014
    assert case["paragraph_anchor"] == "(Paras 14, 16-17)"
    # Only one Haiku call — the ratio field
    assert len(fake_anthropic.calls) == 1


def test_empty_string_field_skipped(fake_anthropic):
    """Empty / whitespace-only fields return as-is, no API call."""
    payload = {"cases": [{"ratio": ""}]}
    translated, paise, quality, preserved = translate_payload_haiku(payload)
    assert translated["cases"][0]["ratio"] == ""
    assert paise == 0
    assert len(fake_anthropic.calls) == 0
