"""Parser regression tests. Cover both modern (Dashrath 2014) and old
(Bhaskaran 1999) judgment markup to prevent regressions when we tweak
extraction heuristics.
"""

from __future__ import annotations

from headnote.kanoon.parser import parse_judgment, extract_statutes


def test_modern_judgment_full_extraction(kanoon_client, known_tids):
    doc = kanoon_client.get_doc(known_tids["dashrath_2014"])
    parsed = parse_judgment(doc.doc_html, tid=doc.tid,
                            title_hint=doc.title, court_hint=doc.docsource,
                            publishdate_hint=doc.publishdate)
    assert "Dashrath" in parsed.title
    assert len(parsed.paragraphs) >= 40
    assert len(parsed.parallel_citations) >= 5
    assert parsed.primary_citation, "modern SC must have a primary citation"
    assert len(parsed.bench) >= 2
    assert parsed.author_judge, "modern judgments have <h3 class=doc_author>"
    assert parsed.case_number, "modern preambles include CRIMINAL APPEAL NO. ..."


def test_old_judgment_graceful_degradation(kanoon_client, known_tids):
    """Older judgments lack author/case_number markup but core fields must work."""
    doc = kanoon_client.get_doc(known_tids["bhaskaran_1999"])
    parsed = parse_judgment(doc.doc_html, tid=doc.tid,
                            title_hint=doc.title, court_hint=doc.docsource,
                            publishdate_hint=doc.publishdate)
    assert "Bhaskaran" in parsed.title
    assert len(parsed.paragraphs) >= 15
    assert len(parsed.parallel_citations) >= 3
    assert len(parsed.bench) >= 2
    # author and case_number expected to be missing for this vintage
    assert parsed.author_judge is None
    assert parsed.case_number == ""


def test_paragraph_structure_annotation(kanoon_client, known_tids):
    """IK tags paragraphs with structure (facts/issue/conclusion/...)."""
    doc = kanoon_client.get_doc(known_tids["dashrath_2014"])
    parsed = parse_judgment(doc.doc_html, tid=doc.tid)
    structs = {p.structure for p in parsed.paragraphs}
    assert "conclusion" in structs, "should have at least one conclusion paragraph"
    assert "precedent" in structs, "should have at least one precedent paragraph"
    assert parsed.conclusion_paragraphs(), "helper should return non-empty"


def test_statute_two_pass_extraction(kanoon_client, known_tids):
    """The 'Section 138' / 'the Act' pattern must be handled — old Bhaskaran
    uses long-form 'Section 138' without re-naming NI Act on each reference."""
    doc = kanoon_client.get_doc(known_tids["bhaskaran_1999"])
    parsed = parse_judgment(doc.doc_html, tid=doc.tid)
    statutes_text = " ".join(parsed.statutes)
    assert "Negotiable Instruments Act, 1881" in statutes_text
    # the foundational S.138 reference must be extracted
    assert any("S. 138" in s for s in parsed.statutes), f"missing S.138 in {parsed.statutes!r}"


def test_extract_statutes_handles_articles():
    text = "Article 21 of the Constitution of India guarantees personal liberty."
    out = extract_statutes(text)
    assert "Constitution of India" in out
    assert "Constitution of India, Art. 21" in out


def test_extract_statutes_handles_section_long_and_short():
    text = "Under the Indian Penal Code, Section 302 and S. 304 Part I are relevant."
    out = extract_statutes(text)
    assert any("Penal Code, 1860, S. 302" in s for s in out)
    assert any("S. 304" in s for s in out)
