"""Verification regression tests. These are the regulatory-moat checks —
if they fail, fabricated citations could slip through to the lawyer.
"""

from __future__ import annotations

import pytest

from headnote.kanoon.parser import parse_judgment
from headnote.verify import (
    EvidenceParagraph,
    verify_situation_response,
    build_regen_feedback,
)


@pytest.fixture
def bhaskaran_evidence(kanoon_client, known_tids):
    doc = kanoon_client.get_doc(known_tids["bhaskaran_1999"])
    parsed = parse_judgment(doc.doc_html, tid=doc.tid,
                            court_hint=doc.docsource, publishdate_hint=doc.publishdate)
    return [EvidenceParagraph(case_id="ik:529907", para_id=p.id, para_num=p.num, text=p.text)
            for p in parsed.paragraphs]


@pytest.fixture
def dashrath_evidence(kanoon_client, known_tids):
    doc = kanoon_client.get_doc(known_tids["dashrath_2014"])
    parsed = parse_judgment(doc.doc_html, tid=doc.tid,
                            court_hint=doc.docsource, publishdate_hint=doc.publishdate)
    return [EvidenceParagraph(case_id="ik:100995424", para_id=p.id, para_num=p.num, text=p.text)
            for p in parsed.paragraphs]


def test_clean_response_passes(bhaskaran_evidence):
    """A response that cites real cases with real quotes must pass."""
    # Pull a real paragraph and quote from it verbatim
    real_para = next(p for p in bhaskaran_evidence if len(p.text) > 100)
    output = {
        "cases": [{
            "case_id": "ik:529907",
            "title": "K. Bhaskaran",
            "journal_headnote": {"ratio": "Held — " + real_para.text[:120], "negative_carve_out": ""},
            "practitioner_notes": {"quotable_phrase": real_para.text[:80], "gist": "summary"},
        }]
    }
    report = verify_situation_response(output, bhaskaran_evidence)
    assert report.is_clean(), f"clean response was flagged: {report.summary()}"


def test_fabricated_case_id_caught(bhaskaran_evidence):
    output = {"cases": [{
        "case_id": "FAKE-2099-SC",
        "title": "Made Up v. Imaginary",
        "journal_headnote": {"ratio": "anything"},
    }]}
    report = verify_situation_response(output, bhaskaran_evidence)
    assert not report.is_clean()
    assert "FAKE-2099-SC" in report.orphan_case_ids


def test_fabricated_quote_caught(bhaskaran_evidence):
    output = {"cases": [{
        "case_id": "ik:529907",
        "title": "Bhaskaran",
        "journal_headnote": {
            "ratio": 'Held — "this exact phrase never appeared in any actual judgment of the court".',
        },
    }]}
    report = verify_situation_response(output, bhaskaran_evidence)
    assert not report.is_clean()
    f = report.findings[0]
    assert f.exists
    assert any(not q.matched for q in f.verbatim_checks)


def test_fabricated_anchor_caught_on_modern_judgment(dashrath_evidence):
    """Dashrath has numbered paragraphs; claiming Para 99999 must fail."""
    output = {"cases": [{
        "case_id": "ik:100995424",
        "title": "Dashrath",
        "journal_headnote": {"ratio": "x", "paragraph_anchor": "(Paras 99999)"},
    }]}
    report = verify_situation_response(output, dashrath_evidence)
    f = report.findings[0]
    assert f.exists
    assert not f.anchor_valid
    assert 99999 in f.anchors_missing


def test_fabricated_anchor_caught_on_unnumbered_judgment(bhaskaran_evidence):
    """Bhaskaran's paragraphs have no human numbers — any numeric anchor
    claim should be rejected (model should use para_id instead)."""
    output = {"cases": [{
        "case_id": "ik:529907",
        "title": "Bhaskaran",
        "journal_headnote": {"ratio": "x", "paragraph_anchor": "(Paras 5)"},
    }]}
    report = verify_situation_response(output, bhaskaran_evidence)
    f = report.findings[0]
    assert f.exists
    assert not f.anchor_valid, "must reject numbered anchors when source has none"


def test_regen_feedback_lists_specific_issues(bhaskaran_evidence):
    output = {"cases": [
        {"case_id": "NOPE", "title": "fake", "journal_headnote": {"ratio": "x"}},
        {"case_id": "ik:529907", "title": "Bhaskaran",
         "journal_headnote": {"ratio": '"a fabricated quote that does not appear in source whatsoever"',
                              "paragraph_anchor": "(Paras 9999)"}},
    ]}
    report = verify_situation_response(output, bhaskaran_evidence)
    feedback = build_regen_feedback(report)
    assert "NOPE" in feedback
    assert "9999" in feedback
    assert "fabricated quote" in feedback


def test_verbatim_threshold_tolerates_whitespace_drift(bhaskaran_evidence):
    """Real quotes with minor whitespace/punctuation differences should still match."""
    real_para = next(p for p in bhaskaran_evidence if len(p.text) > 100)
    # Inject extra whitespace and re-cased punctuation
    drifted = "  " + " ".join(real_para.text[:80].split()) + ".  "
    output = {"cases": [{
        "case_id": "ik:529907",
        "title": "Bhaskaran",
        "practitioner_notes": {"quotable_phrase": drifted, "gist": ""},
    }]}
    report = verify_situation_response(output, bhaskaran_evidence)
    f = report.findings[0]
    assert all(q.matched for q in f.verbatim_checks), \
        f"whitespace drift should not trigger false alarm: {[(q.quote, q.similarity) for q in f.verbatim_checks]}"
