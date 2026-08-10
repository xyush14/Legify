"""Deterministic page preparation — make a phone photo readable before OCR.

Measured on three real pages (a handwritten UP gang chart and the two typed
आख्या pages covering it) through Sarvam Document Intelligence:

    page                 raw photo      after prepare()
    gang chart            0 / 25 facts    14 / 25
    आख्या page 1         16 / 29         26 / 29
    आख्या page 2          0 / 17         15 / 17

Two of the three scored **zero** on the raw photo. Worse, one raw run came back
with 130,142 characters of base64 image data instead of text — a silent garbage
response, not an error, which a naive pipeline would store as "the document".
See ``looks_like_garbage`` for the guard that catches that shape.

None of this needs a model. It is rotation, deskew, contrast and upscale: about
a second of CPU, the same result every time, and the single largest quality
lever in the whole document pipeline. Run it in front of every OCR engine.

Deliberately PIL + numpy only — no OpenCV. Perspective ("page flattening") would
need cv2 and is the obvious next gain; it is not implemented here rather than
pulling a heavy dependency in for it. See ``KNOWN GAPS`` below.

KNOWN GAPS
    * 180° flips are not detected — see ``detect_orientation``.
    * No perspective/quad correction: a page photographed at a steep angle is
      straightened in-plane but not un-warped.
"""
from __future__ import annotations

import io
import logging

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

log = logging.getLogger(__name__)

# Detection runs on a downscaled copy: orientation and skew are global
# properties, so paying full resolution for them buys nothing.
_ANALYSIS_WIDTH = 1000
_SKEW_RANGE_DEG = 6.0
_SKEW_STEP_DEG = 0.5
_MAX_EDGE = 4000  # keep the upscaled result inside typical API upload limits


def _page_crop(img: Image.Image) -> Image.Image:
    """Crop to the sheet of paper, discarding whatever it was photographed on.

    Load-bearing, not cosmetic. On the real captures — a page lying on a
    mottled concrete floor — the background's own light/dark variation is
    larger than the text's, so orientation measured over the whole frame reads
    the floor instead of the document and picks the wrong rotation. Cropping to
    the bright region first is what makes the signal below mean anything.
    """
    g = np.asarray(img.convert("L"), dtype=np.float32)
    if g.size == 0:
        return img
    bright = g > np.percentile(g, 70)
    cols, rows = bright.mean(axis=0), bright.mean(axis=1)
    xs, ys = np.where(cols > 0.35)[0], np.where(rows > 0.35)[0]
    if xs.size < 2 or ys.size < 2:
        return img  # no clear sheet — analyse the frame as given
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    if (box[2] - box[0]) < img.width * 0.15 or (box[3] - box[1]) < img.height * 0.15:
        return img  # implausibly small: trust the full frame over a bad crop
    return img.crop(box)


def _ink_profile_score(img: Image.Image) -> float:
    """How strongly does this image look like horizontal lines of text?

    Text lines make the row-wise ink profile oscillate — dark rows where the
    glyphs sit, light rows in the leading between them. Rotate the page 90° and
    that oscillation flattens out, so the variance of the row profile is a
    cheap, script-agnostic "is the text horizontal?" score.

    The profile is taken over *binarised ink*, not raw grey. Averaging grey
    lets broad shading gradients (a shadow across the sheet, uneven light)
    dominate the variance and drown the text; thresholding to ink-or-not
    measures only the thing we care about. On a real page this changed the
    0°-vs-90° decision from wrong to right by a 4x margin.
    """
    a = np.asarray(img.convert("L"), dtype=np.float32)
    if a.size == 0:
        return 0.0
    ink = (a < (a.mean() - 0.6 * a.std())).astype(np.float32)
    return float(ink.mean(axis=1).var())


def detect_orientation(img: Image.Image) -> int:
    """Return the rotation in degrees (0/90/180/270) that makes text horizontal.

    Resolves the common case — a page photographed sideways, which is most
    phone captures of a document lying on a desk or floor.

    LIMITATION: this cannot tell 0° from 180°, because upside-down text lines
    are still horizontal lines. Distinguishing them reliably needs script-aware
    cues (Devanagari's shirorekha sits above the glyphs, Latin hangs off a
    baseline), which flips the wrong way often enough that guessing is worse
    than not guessing. An upside-down page will read as garbage and should be
    caught downstream by ``looks_like_garbage`` or a confidence gate.
    """
    small = _page_crop(img)
    small.thumbnail((_ANALYSIS_WIDTH, _ANALYSIS_WIDTH), Image.LANCZOS)
    scores = {deg: _ink_profile_score(small.rotate(deg, expand=True))
              for deg in (0, 90, 180, 270)}
    best = max(scores, key=scores.get)
    # 0/180 and 90/270 are indistinguishable by this measure; prefer the
    # smaller rotation of the winning pair so behaviour is deterministic.
    return 0 if best in (0, 180) else 90


def detect_skew(img: Image.Image) -> float:
    """Return the small in-plane tilt in degrees, positive = counter-clockwise.

    Same signal as orientation: the row profile of level text oscillates hardest
    when lines are exactly horizontal, so sweep a narrow range and take the peak.
    """
    small = _page_crop(img).convert("L")
    small.thumbnail((_ANALYSIS_WIDTH, _ANALYSIS_WIDTH), Image.LANCZOS)
    steps = int(_SKEW_RANGE_DEG / _SKEW_STEP_DEG)
    angles = [i * _SKEW_STEP_DEG for i in range(-steps, steps + 1)]
    best, best_score = 0.0, -1.0
    for ang in angles:
        score = _ink_profile_score(small.rotate(ang, resample=Image.BILINEAR, fillcolor=255))
        if score > best_score:
            best, best_score = ang, score
    return best


def looks_like_garbage(text: str, *, pages: int = 1) -> str:
    """Return a reason string if OCR output should be rejected, else "".

    Sarvam returned 130,142 characters of base64 image data for one raw photo —
    HTTP 200, no error, just a blob. Stored unchecked that becomes the
    document's searchable text and its "translation" source. Cheap to catch:
    real prose is not a data URI and does not run to tens of thousands of
    characters a page.
    """
    if not text or not text.strip():
        return "empty"
    if "data:image/" in text[:2000] or ";base64," in text[:2000]:
        return "response is encoded image data, not text"
    if len(text) > 40_000 * max(pages, 1):
        return f"implausibly long for {pages} page(s): {len(text):,} chars"
    stripped = "".join(text.split())
    if stripped and sum(c.isalnum() for c in stripped) / len(stripped) < 0.30:
        return "mostly non-alphanumeric noise"
    return ""


def prepare(raw: bytes, *, upscale: int = 4, to_jpeg_quality: int = 92) -> bytes:
    """Return OCR-ready JPEG bytes for one page photographed on a phone.

    Upright → deskewed → greyscale → contrast-normalised → upscaled → sharpened.
    Never raises on a decodable image; on any unexpected failure the original
    bytes come back so a caller can still attempt OCR.
    """
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)  # honour the camera's own tag first

        deg = detect_orientation(img)
        if deg:
            img = img.rotate(deg, expand=True)

        skew = detect_skew(img)
        if abs(skew) >= _SKEW_STEP_DEG:
            img = img.rotate(skew, resample=Image.BICUBIC, expand=True, fillcolor=255)

        img = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1)

        factor = max(1, int(upscale))
        if factor > 1:
            cap = max(1.0, max(img.width, img.height) * factor / _MAX_EDGE)
            factor = max(1, int(factor / cap))
        if factor > 1:
            img = img.resize((img.width * factor, img.height * factor), Image.LANCZOS)

        img = ImageEnhance.Sharpness(img).enhance(2.5)

        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=to_jpeg_quality, optimize=True)
        log.debug("prepare: rot=%s skew=%.1f x%s -> %s", deg, skew, factor, img.size)
        return buf.getvalue()
    except Exception:  # noqa: BLE001 — preparation must never lose the upload
        log.warning("prepare() failed; passing the original bytes through", exc_info=True)
        return raw
