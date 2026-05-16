"""Retrieval pipeline regression tests. All run on cached data — zero IK
spend. The kanoon_client fixture has daily_cap_inr=0 so any accidental
live call raises KanoonBudgetExceeded immediately, surfacing the bug
rather than burning money.
"""

from __future__ import annotations

import pytest

from headnote.kanoon.retrieval import (
    _distill_query, _rank_search_hits, _rank_paragraphs, retrieve_for_situation,
)
from headnote.kanoon.client import SearchHit
from headnote.kanoon.parser import parse_judgment


# ----- query distillation

def test_distill_extracts_statutes_and_sections():
    q = ("Lawyer wants Supreme Court precedents on PMLA Section 45 twin "
         "conditions for bail, especially Vijay Madanlal Choudhary 2022.")
    out = _distill_query(q)
    assert "PMLA" in out
    assert "Section 45" in out
    assert "Vijay Madanlal Choudhary" in out
    # Stopwords filtered
    assert "Lawyer" not in out and "wants" not in out


def test_distill_handles_no_statutes():
    q = "Bank refused payment because account had insufficient funds."
    out = _distill_query(q)
    # Should still extract content words even without statute references
    assert "Bank" in out or "payment" in out.lower() or "insufficient" in out.lower()
    assert len(out.split()) <= 10


def test_distill_handles_articles():
    q = "Personal liberty under Article 21 of the Constitution."
    out = _distill_query(q)
    assert "Article 21" in out


# ----- search hit ranking

def test_rank_drops_dupes_already_in_curated():
    hits = [
        SearchHit(tid=1, title="K. Bhaskaran v. Sankaran", docsource="Supreme Court of India",
                  publishdate="1999-09-29", headline="cheque dishonour", numcites=10,
                  numcitedby=3000, doctype=1000, bench=None),
        SearchHit(tid=2, title="Other Case v. Ors", docsource="Supreme Court of India",
                  publishdate="2020-01-01", headline="cheque dishonour", numcites=5,
                  numcitedby=10, doctype=1000, bench=None),
    ]
    ranked = _rank_search_hits(hits, "cheque dishonour", curated_titles_lc={"k. bhaskaran v. sankaran"})
    # Bhaskaran should be excluded — already curated
    assert all("bhaskaran" not in h.title.lower() for _s, h in ranked)


def test_rank_prefers_high_citedby():
    hits = [
        SearchHit(tid=1, title="Recent Case", docsource="SC", publishdate="2024",
                  headline="x", numcites=0, numcitedby=0, doctype=1000, bench=None),
        SearchHit(tid=2, title="Landmark Case", docsource="Supreme Court of India",
                  publishdate="1990", headline="x", numcites=0, numcitedby=5000,
                  doctype=1000, bench=None),
    ]
    ranked = _rank_search_hits(hits, "x", curated_titles_lc=set())
    # Higher citedby wins
    assert ranked[0][1].tid == 2


# ----- paragraph ranking

def test_paragraph_ranker_prefers_conclusion(kanoon_client, known_tids):
    doc = kanoon_client.get_doc(known_tids["dashrath_2014"])
    parsed = parse_judgment(doc.doc_html, tid=doc.tid)
    top = _rank_paragraphs(parsed.paragraphs, "territorial jurisdiction cheque", top_k=4)
    # At least one Conclusion in the top-4
    assert any(p.structure in ("conclusion", "ratio") for p in top), \
        f"top paragraphs: {[(p.structure, p.id) for p in top]}"


# ----- end-to-end hybrid retrieval (no IK calls because daily_cap_inr=0)

def test_hybrid_retrieval_uses_semantic_when_paraphrased(kanoon_client, curated_corpus):
    """Paraphrased query that doesn't mention S.138/Bhaskaran/cheque should
    still find Bhaskaran via semantic search over the embedding index."""
    situation = (
        "Bank refused to honour a payment instrument because the account had "
        "insufficient funds. The drawer claims he never received the demand letter."
    )
    result = retrieve_for_situation(
        situation, client=kanoon_client, curated_corpus=[],
        top_cases=3, max_new_fetches=0,
        skip_ik_search_if_cases_at_least=2,  # skip IK once we have 2 from semantic
    )
    # Should NOT have made any IK calls (cap is ₹0)
    assert result.meta.inr_spent_this_call == 0
    # Should have surfaced relevant cached cases via semantic search
    case_ids = {c.case_id for c in result.cases}
    assert any("ik:" in cid for cid in case_ids), \
        f"semantic search should have surfaced cached IK cases: {case_ids}"


def test_retrieval_falls_back_gracefully_on_budget_exceeded(kanoon_client, curated_corpus):
    """With daily_cap=₹0 and a query that would normally trigger IK, the
    pipeline must still return *something* (curated only) rather than crash."""
    situation = "Some extremely unusual legal scenario with no curated coverage abcxyz"
    result = retrieve_for_situation(
        situation, client=kanoon_client, curated_corpus=curated_corpus,
        top_cases=3, max_new_fetches=2,
        skip_ik_search_if_cases_at_least=10,  # force IK attempt
    )
    # Should not crash; may have empty cases or curated fallback
    assert isinstance(result.cases, list)
    # Should record the budget failure in notes
    notes = " ".join(result.meta.notes).lower()
    assert "budget" in notes or "exceeded" in notes or len(result.cases) > 0
