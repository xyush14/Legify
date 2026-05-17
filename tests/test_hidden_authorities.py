"""Hidden Authorities ranker tests.

Covers the mode-specific scoring formulas + the moat demonstration:
when 5 candidate cases include a famous-but-tangential one and an
obscure-but-relevant one, HIDDEN mode ranks the obscure case higher,
FAMOUS mode ranks the famous one higher, and MIXED mode favours
fact-pattern match without fame bias.

All Sonnet rerank calls are bypassed via `skip_sonnet_rerank=True` so
tests are deterministic and free.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from headnote.retrieval.hidden_authorities import (
    Candidate, ScoredCandidate,
    _recency_score, _jurisdiction_match, _good_law_score, _fame_factor,
    _score_hidden, _score_famous, _score_mixed,
    rank_candidates, explain_score,
)


# ====================================================================
# Helper scoring functions
# ====================================================================

def test_recency_score_recent_is_high():
    this_year = datetime.now(timezone.utc).year
    assert _recency_score(this_year) == 1.0
    assert _recency_score(this_year - 5) == pytest.approx(0.2, abs=0.05)
    # Older than the cap floors at 0.2
    assert _recency_score(this_year - 20) == 0.2
    assert _recency_score(0) == 0.2  # unknown year


def test_jurisdiction_match_sc_always_wins():
    assert _jurisdiction_match("Supreme Court of India", None) == 1.0
    assert _jurisdiction_match("Supreme Court of India", "Bombay High Court") == 1.0


def test_jurisdiction_match_same_hc():
    assert _jurisdiction_match("Bombay High Court", "Bombay High Court") == 1.0


def test_jurisdiction_match_different_hc():
    assert _jurisdiction_match("Madras High Court", "Bombay High Court") == 0.5


def test_jurisdiction_match_district():
    assert _jurisdiction_match("Bangalore District Court", "Bombay High Court") == 0.2


def test_good_law_default_when_no_treatment():
    assert _good_law_score("") == 1.0
    assert _good_law_score("Followed in numerous cases.") == 1.0


def test_good_law_overruled_drops_to_zero():
    assert _good_law_score("Subsequently overruled by larger bench.") == 0.0


def test_good_law_distinguished():
    assert _good_law_score("Distinguished on facts in later decisions.") == 0.3


def test_fame_factor_scales_with_citations():
    assert _fame_factor(0) == 0.0
    assert _fame_factor(50) == 0.5
    assert _fame_factor(100) == 1.0
    assert _fame_factor(500) == 1.0   # capped


# ====================================================================
# Mode-specific scoring formulas
# ====================================================================

def _make_scored(*, fpm=0.5, sim=0.5, cit=0, jm=1.0, rs=0.5, gls=1.0) -> ScoredCandidate:
    c = Candidate(
        case_id="x", title="x", court="Supreme Court of India",
        year=2020, citation="", numcitedby=cit, semantic_similarity=sim,
        summary="", subsequent_treatment="", source="ik",
    )
    fame = min(1.0, cit / 100)
    return ScoredCandidate(
        candidate=c, fact_pattern_match=fpm, semantic_similarity=sim,
        citation_count=cit, jurisdiction_match=jm, recency_score=rs,
        good_law_score=gls, fame_penalty=fame, fame_boost=fame,
        final_score=0.0, explanation={},
    )


def test_hidden_score_penalises_fame():
    obscure = _make_scored(fpm=0.9, sim=0.8, cit=5, jm=1.0, rs=0.7)
    famous  = _make_scored(fpm=0.9, sim=0.8, cit=500, jm=1.0, rs=0.7)
    assert _score_hidden(obscure) > _score_hidden(famous)


def test_famous_score_boosts_fame():
    obscure = _make_scored(fpm=0.9, sim=0.8, cit=5, jm=1.0, rs=0.7)
    famous  = _make_scored(fpm=0.9, sim=0.8, cit=500, jm=1.0, rs=0.7)
    assert _score_famous(famous) > _score_famous(obscure)


def test_mixed_score_neutral_to_fame():
    """Same fact-pattern and semantic scores → fame shouldn't break the tie."""
    obscure = _make_scored(fpm=0.9, sim=0.8, cit=5, jm=1.0, rs=0.7)
    famous  = _make_scored(fpm=0.9, sim=0.8, cit=500, jm=1.0, rs=0.7)
    # Mixed mode formula uses only fact-pattern + semantic + jurisdiction
    # + recency + good_law. Identical inputs → identical scores.
    assert _score_mixed(obscure) == pytest.approx(_score_mixed(famous), abs=1e-6)


# ====================================================================
# THE MOAT DEMONSTRATION TEST
# 5 candidates, mix of famous and obscure, prove Hidden mode surfaces
# the obscure-but-relevant case above the famous-but-tangential one.
# ====================================================================

def test_hidden_mode_surfaces_obscure_relevant_over_famous_tangential():
    """The defining test for Hidden Authorities mode.

    Setup: lawyer's query is about a niche cheque-dishonour fact pattern.
    Among 5 candidates:
      - Bhaskaran (famous, 3000 citations) — fame is overwhelming but
        only tangentially related to THIS fact pattern (low fpm 0.4)
      - Obscure 2018 Bombay HC case (only 6 citations) — directly on
        point for the fact pattern (high fpm 0.9)
      - Three filler cases

    Hidden mode MUST rank the obscure case above Bhaskaran.
    Famous mode MUST rank Bhaskaran above the obscure case.
    """
    bhaskaran = Candidate(
        case_id="ik:529907", title="K. Bhaskaran v. Sankaran Vaidhyan Balan",
        court="Supreme Court of India", year=1999, citation="(1999) 7 SCC 510",
        numcitedby=3240,
        # We use semantic_similarity as the proxy for fact-pattern in tests
        # (skip_sonnet_rerank=True maps fact_pattern_match = semantic_similarity)
        semantic_similarity=0.40,
        summary="Foundational five-component analysis of S. 138 NI Act offence.",
        source="ik",
    )
    obscure_bombay = Candidate(
        case_id="ik:obscure-2018", title="ABC Pvt Ltd v. State of Maharashtra",
        court="Bombay High Court", year=2018, citation="2018 SCC OnLine Bom 1234",
        numcitedby=6,
        semantic_similarity=0.90,
        summary="Cheque dishonour case directly on the fact pattern presented.",
        source="ik",
    )
    filler1 = Candidate(
        case_id="ik:filler1", title="Filler One v. State",
        court="Delhi High Court", year=2015, citation="...",
        numcitedby=15, semantic_similarity=0.5, summary="...", source="ik",
    )
    filler2 = Candidate(
        case_id="ik:filler2", title="Filler Two v. State",
        court="Madras High Court", year=2010, citation="...",
        numcitedby=80, semantic_similarity=0.45, summary="...", source="ik",
    )
    filler3 = Candidate(
        case_id="ik:filler3", title="Filler Three v. State",
        court="Calcutta High Court", year=2005, citation="...",
        numcitedby=200, semantic_similarity=0.55, summary="...", source="ik",
    )
    candidates = [bhaskaran, obscure_bombay, filler1, filler2, filler3]

    # HIDDEN MODE — obscure-relevant should top the list
    ranked_hidden = rank_candidates(
        "cheque dishonour fact pattern...", candidates, mode="hidden",
        skip_sonnet_rerank=True,  # deterministic
    )
    top_hidden = ranked_hidden[0].candidate
    assert top_hidden.case_id == "ik:obscure-2018", (
        f"Hidden mode should top the obscure case, got {top_hidden.case_id!r} "
        f"with score {ranked_hidden[0].final_score:.3f}"
    )
    # Bhaskaran (famous) should rank lower
    bhaskaran_rank = next(
        i for i, s in enumerate(ranked_hidden) if s.candidate.case_id == "ik:529907"
    )
    obscure_rank = next(
        i for i, s in enumerate(ranked_hidden) if s.candidate.case_id == "ik:obscure-2018"
    )
    assert obscure_rank < bhaskaran_rank, (
        f"Obscure case ranked #{obscure_rank}, Bhaskaran #{bhaskaran_rank} — "
        "should be reversed in hidden mode"
    )

    # FAMOUS MODE — Bhaskaran should top the list (or beat the obscure case)
    ranked_famous = rank_candidates(
        "cheque dishonour fact pattern...", candidates, mode="famous",
        skip_sonnet_rerank=True,
    )
    bhaskaran_famous_rank = next(
        i for i, s in enumerate(ranked_famous) if s.candidate.case_id == "ik:529907"
    )
    obscure_famous_rank = next(
        i for i, s in enumerate(ranked_famous) if s.candidate.case_id == "ik:obscure-2018"
    )
    assert bhaskaran_famous_rank < obscure_famous_rank, (
        f"Famous mode: Bhaskaran ranked #{bhaskaran_famous_rank}, "
        f"obscure #{obscure_famous_rank} — should be reversed"
    )


# ====================================================================
# Sonnet rerank integration (mocked)
# ====================================================================

def test_sonnet_rerank_uses_returned_scores(monkeypatch):
    """When skip_sonnet_rerank=False, the ranker should call Sonnet via
    the router and use the returned scores."""
    fake_scores = {"a": 0.95, "b": 0.10}

    def fake_route_call(task_type, payload, force_model=None):
        # Return a RouteResult-shaped tuple
        from headnote.llm.router import RouteResult
        import json
        body = json.dumps({
            "matches": [
                {"case_id": "a", "score": 0.95, "reasoning": "x"},
                {"case_id": "b", "score": 0.10, "reasoning": "y"},
            ]
        })
        return RouteResult(model_name="claude-sonnet-4-6", response=body,
                           cost_paise=50, confidence_score=None)

    monkeypatch.setattr("headnote.retrieval.hidden_authorities.route_call", fake_route_call)

    cands = [
        Candidate(case_id="a", title="A", court="Supreme Court of India",
                  year=2020, citation="", numcitedby=10,
                  semantic_similarity=0.5, summary="x", source="ik"),
        Candidate(case_id="b", title="B", court="Supreme Court of India",
                  year=2020, citation="", numcitedby=10,
                  semantic_similarity=0.5, summary="y", source="ik"),
    ]
    ranked = rank_candidates(
        "facts", cands, mode="mixed",
        skip_sonnet_rerank=False, result_top_k=2,
    )
    # In mixed mode, fact_pattern_match dominates ranking → "a" should top
    assert ranked[0].candidate.case_id == "a"
    assert ranked[0].fact_pattern_match == 0.95
    assert ranked[1].fact_pattern_match == 0.10


def test_sonnet_failure_falls_back_to_default(monkeypatch):
    """If Sonnet errors, all fact-pattern scores default to 0.5 — ranker
    still produces an ordered list rather than crashing."""
    def boom(task_type, payload, force_model=None):
        raise RuntimeError("simulated Sonnet failure")
    monkeypatch.setattr("headnote.retrieval.hidden_authorities.route_call", boom)

    cands = [
        Candidate(case_id="a", title="A", court="SC", year=2020,
                  citation="", numcitedby=10, semantic_similarity=0.5,
                  summary="", source="ik"),
    ]
    ranked = rank_candidates("facts", cands, mode="hidden", skip_sonnet_rerank=False)
    assert len(ranked) == 1
    assert ranked[0].fact_pattern_match == 0.5  # fallback


# ====================================================================
# explain_score for UI transparency
# ====================================================================

def test_explain_score_hidden_obscure_message():
    sc = _make_scored(fpm=0.9, sim=0.8, cit=6, jm=1.0, rs=0.7)
    msg = explain_score(sc, "hidden")
    assert "6" in msg
    assert "hidden authority" in msg.lower()


def test_explain_score_famous_leading_message():
    sc = _make_scored(fpm=0.9, sim=0.8, cit=1000, jm=1.0, rs=0.7)
    msg = explain_score(sc, "famous")
    assert "1000" in msg
    assert "leading authority" in msg.lower()


def test_explain_score_flags_bad_law():
    sc = _make_scored(fpm=0.9, sim=0.8, cit=100, jm=1.0, rs=0.7, gls=0.0)
    msg = explain_score(sc, "hidden")
    assert "not-fully-good-law" in msg.lower() or "good-law" in msg.lower()


# ====================================================================
# Edge cases
# ====================================================================

def test_empty_candidates_returns_empty():
    assert rank_candidates("facts", [], mode="hidden", skip_sonnet_rerank=True) == []


def test_single_candidate_returned():
    c = Candidate(case_id="a", title="A", court="Supreme Court of India",
                  year=2020, citation="", numcitedby=10,
                  semantic_similarity=0.8, summary="", source="ik")
    ranked = rank_candidates("facts", [c], mode="hidden", skip_sonnet_rerank=True)
    assert len(ranked) == 1
    assert ranked[0].candidate.case_id == "a"


def test_result_top_k_truncates():
    cands = [
        Candidate(case_id=f"c{i}", title=f"C{i}",
                  court="Supreme Court of India", year=2020,
                  citation="", numcitedby=10, semantic_similarity=0.5 + i * 0.05,
                  summary="", source="ik")
        for i in range(10)
    ]
    ranked = rank_candidates("facts", cands, mode="mixed",
                              skip_sonnet_rerank=True, result_top_k=3)
    assert len(ranked) == 3
