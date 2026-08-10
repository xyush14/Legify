"""Tests for headnote.documents.prepare — the pre-OCR page conditioner."""
from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from headnote.documents import prepare as P


def _page(w: int = 900, h: int = 1300, lines: int = 22) -> Image.Image:
    """A synthetic printed page: dark horizontal text bars on white."""
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    step = h // (lines + 2)
    for i in range(1, lines + 1):
        y = i * step
        d.rectangle([int(w * 0.10), y, int(w * 0.90), y + max(4, step // 4)], fill="black")
    return img


def _bytes(img: Image.Image, fmt: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, fmt)
    return buf.getvalue()


# --- orientation --------------------------------------------------------------
def test_upright_page_is_left_alone():
    assert P.detect_orientation(_page()) == 0


def test_sideways_page_is_detected():
    """The case that scored 0/25 on the real gang chart: a sideways phone photo."""
    assert P.detect_orientation(_page().rotate(90, expand=True)) == 90


def test_prepare_restores_portrait_from_a_sideways_photo():
    landscape = _page().rotate(90, expand=True)
    assert landscape.width > landscape.height
    out = Image.open(io.BytesIO(P.prepare(_bytes(landscape), upscale=1)))
    assert out.height > out.width, "sideways page should come back upright"


# --- skew ---------------------------------------------------------------------
@pytest.mark.parametrize("tilt", [-3.0, 2.0])
def test_skew_is_measured_in_the_right_direction(tilt):
    tilted = _page().rotate(-tilt, resample=Image.BICUBIC, fillcolor="white")
    got = P.detect_skew(tilted)
    assert got == pytest.approx(tilt, abs=1.0), f"tilt {tilt} read back as {got}"


def test_level_page_reports_no_meaningful_skew():
    assert abs(P.detect_skew(_page())) <= P._SKEW_STEP_DEG


# --- prepare() contract -------------------------------------------------------
def test_output_is_a_decodable_jpeg_and_upscaled():
    src = _page(300, 420)
    out = Image.open(io.BytesIO(P.prepare(_bytes(src), upscale=4)))
    assert out.format == "JPEG"
    assert out.width >= src.width * 3


def test_upscale_is_capped_so_uploads_stay_sane():
    out = Image.open(io.BytesIO(P.prepare(_bytes(_page(2000, 2600)), upscale=4)))
    assert max(out.size) <= P._MAX_EDGE * 1.05


def test_undecodable_bytes_pass_through_rather_than_losing_the_upload():
    junk = b"not an image at all"
    assert P.prepare(junk) is junk


# --- the garbage guard --------------------------------------------------------
def test_base64_blob_is_rejected():
    """The real failure: HTTP 200 carrying the image back as base64, not text."""
    blob = "![Image](data:image/jpeg;base64," + "A" * 5000 + ")"
    assert "encoded image" in P.looks_like_garbage(blob)


def test_absurd_length_for_one_page_is_rejected():
    assert "implausibly long" in P.looks_like_garbage("क " * 60_000, pages=1)


def test_empty_is_rejected():
    assert P.looks_like_garbage("   ") == "empty"


def test_real_hindi_page_text_passes():
    good = ("दिनांक 11.10.25 को अभियुक्त गण कुन्ना उर्फ पुन्नन पुत्र खालिद नि0 ग्राम सीकरी "
            "थाना भोपा मु0नगर के विरूद्ध मु0अ0सं0 359/25 धारा 109(1) बीएनएस व 3/4/25/28 "
            "आर्मस एक्ट पंजीकृत किया गया। आरोप पत्र 394/25 दि0 24.12.2025 प्रेषित।") * 6
    assert P.looks_like_garbage(good) == ""


def test_english_page_text_passes():
    good = ("The applicant is in judicial custody since 11.10.2025 in Case Crime "
            "No. 359/25 under Section 109(1) BNS read with the Arms Act. ") * 20
    assert P.looks_like_garbage(good) == ""
