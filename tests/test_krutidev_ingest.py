"""Draft DNA Stage 0 — font-aware Kruti Dev ingest.

Guards the foundation of Draft DNA extraction: an advocate's real Kruti Dev
.docx must decode to Unicode, while Unicode/English runs in the same document
are left untouched (blindly decoding Unicode corrupts it).
"""
import io

import pytest

from headnote.drafter import krutidev as kd


def test_convert_decodes_known_kruti_dev():
    # Documented examples from the converter + the load-bearing ground prefix.
    assert kd.convert("ekuuh; mPp U;k;ky;") == "माननीय उच्च न्यायालय"
    assert kd.convert("vkosnd") == "आवेदक"
    assert kd.convert(";g fd") == "यह कि"


def test_convert_corrupts_real_unicode_lines():
    # Blanket-decoding real Unicode drafts mangles them — which is why ingest
    # must be font-aware, never blanket. (A pure-Devanagari fragment with no
    # ASCII survives by luck; real lines always carry Latin/digits/punctuation.)
    for s in ("State Vs Ram Prasad", "वाद क्रमांक 12/2026, ग्वालियर", "धारा 302 IPC"):
        assert kd.convert(s) != s, s


def test_font_detection():
    for name in ("Kruti Dev 010", "KrutiDev010", "DevLys 010", "kruti dev"):
        assert kd.is_krutidev_font(name), name
    for name in ("Mangal", "Nirmala UI", "Calibri", "Times New Roman", None):
        assert not kd.is_krutidev_font(name), name


def test_heuristic_flags_kruti_gibberish_not_plain_text():
    assert kd.looks_like_krutidev(";g fd vkosnd fun~Zk"[:] + " ekuuh; U;k;ky;")
    assert not kd.looks_like_krutidev("IN THE COURT OF SESSIONS JUDGE, GWALIOR")
    assert not kd.looks_like_krutidev("माननीय न्यायालय के समक्ष प्रस्तुत")


def test_encoder_inverts_the_decoder():
    # to_krutidev is the exact inverse of convert() on real drafting text.
    for w in ("धारा", "यह कि", "माननीय न्यायालय", "अन्तर्गत", "सुरक्षा",
              "सिंह", "पार्किंग", "एनेक्जर", "द्ध", "प्रार्थी", "विनम्र निवेदन है कि"):
        assert kd.convert(kd.to_krutidev(w)) == w, w


def test_encoder_full_roundtrip_on_real_drafts():
    # Every paragraph of his 3 real filed Kruti Dev drafts must round-trip
    # exactly: decode → encode → decode == decode. (Files are gitignored /
    # machine-local; skip cleanly when absent so CI stays green.)
    import glob
    import os

    docx = pytest.importorskip("docx")
    base = os.path.expanduser("~/Downloads/High court")
    files = sorted(glob.glob(os.path.join(base, "*.docx")))
    if not files:
        pytest.skip("real sample drafts not present on this machine")
    total = ok = 0
    for f in files:
        for p in docx.Document(f).paragraphs:
            if not p.text.strip():
                continue
            uni = kd.convert(p.text)
            total += 1
            ok += (kd.convert(kd.to_krutidev(uni)) == uni)
    assert total and ok == total, f"{ok}/{total} paragraphs round-tripped"


def _mixed_docx() -> bytes:
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    r1 = doc.add_paragraph().add_run(";g fd vkosnd")   # KD: "यह कि आवेदक"
    r1.font.name = "Kruti Dev 010"
    r2 = doc.add_paragraph().add_run("माननीय न्यायालय के समक्ष")
    r2.font.name = "Mangal"
    r3 = doc.add_paragraph().add_run("IN THE COURT OF SESSIONS JUDGE")
    r3.font.name = "Calibri"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extract_docx_fontaware_decodes_only_kruti_runs():
    out = kd.extract_docx_fontaware(_mixed_docx())
    assert "यह कि आवेदक" in out                 # Kruti Dev decoded
    assert "माननीय न्यायालय के समक्ष" in out    # Unicode intact
    assert "IN THE COURT OF SESSIONS JUDGE" in out  # English intact
    assert ";g fd" not in out                    # no gibberish leaked
