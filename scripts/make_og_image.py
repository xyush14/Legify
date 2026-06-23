#!/usr/bin/env python3
"""Generate the Headnote Open Graph / social-share card -> static/og-image.png

On-brand: warm ivory paper, ink wordmark, a single deep-gold accent — matches
the live landing aesthetic (warm paper + ink + one gold accent). This is the
image WhatsApp / LinkedIn / X render when a headnote.in link is shared
(referenced by og:image + twitter:image on the marketing pages).

Output is a 1200x630 PNG (the universal social-card size). Regenerate after a
brand or tagline change:

    python3 scripts/make_og_image.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
PAPER = (251, 250, 245)   # #FBFAF5  warm ivory (landing --bg)
INK = (26, 24, 20)        # near-black ink
MUTED = (120, 112, 96)    # warm grey sub-text
GOLD = (201, 169, 110)    # #C9A96E  brand gold (favicon mark)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "og-image.png"


def _font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    """First loadable TTF from candidates, else PIL's default bitmap."""
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


SERIF = [
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/Library/Fonts/Georgia.ttf",
]
SERIF_BI = [
    "/System/Library/Fonts/Supplemental/Georgia Bold Italic.ttf",
    *SERIF,
]
SANS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]
SANS_B = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    *SANS,
]

img = Image.new("RGB", (W, H), PAPER)
d = ImageDraw.Draw(img)

# Top gold rule — the single accent.
d.rectangle([0, 0, W, 10], fill=GOLD)

PAD = 90

# Small gold "h." mark, top-left (echoes the favicon).
d.text((PAD, 64), "h.", font=_font(SERIF_BI, 72), fill=GOLD)

# Wordmark.
d.text((PAD, 208), "Headnote", font=_font(SERIF, 132), fill=INK)

# Tagline.
d.text(
    (PAD + 4, 378),
    "AI co-counsel for India’s criminal advocates",
    font=_font(SANS, 40),
    fill=MUTED,
)

# Short gold divider.
d.rectangle([PAD + 4, 468, PAD + 4 + 520, 471], fill=GOLD)

# Footer: domain in gold + proof points in muted.
foot_b = _font(SANS_B, 30)
foot_f = _font(SANS, 30)
d.text((PAD + 4, 503), "headnote.in", font=foot_b, fill=GOLD)
wlen = d.textlength("headnote.in", font=foot_b)
d.text(
    (PAD + 4 + wlen, 503),
    "   ·   3.5 crore+ judgments  ·  Hindi & English",
    font=foot_f,
    fill=MUTED,
)

OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT, "PNG")
print("wrote", OUT, img.size)
