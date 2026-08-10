#!/usr/bin/env python3
"""OCR-engine bake-off — decide the Documents OCR backend from evidence.

Runs the same pages through every configured engine, twice each: once on the
RAW phone photo, once after deterministic preprocessing (upright + contrast +
upscale). Scores both against a hand-verified fact list and prints a scorecard.

Two questions this answers, which guessing cannot:
  1. Can Sarvam Document Intelligence read these pages as well as we need?
  2. How much of the quality is the ENGINE vs the PREPROCESSING in front of it?

The second matters most. config.py:137 already records that the Sarvam-DI-text
path mis-slotted court/case/party on a photographed ruled table because the
columns collapsed into one run-on line. The gang chart here is that exact shape,
so the row-integrity check below is the one to watch.

Ground truth was established by reading two independent documents against each
other (the handwritten chart and the typed आख्या covering it), so the facts
below are cross-verified, not one reading.

Keys (only engines with a key are run):
    SARVAM_API_KEY
    GEMINI_API_KEY or GOOGLE_API_KEY

Usage:
    SARVAM_API_KEY=... python scripts/ocr_bakeoff.py
    SARVAM_API_KEY=... python scripts/ocr_bakeoff.py --only gangchart
Output: docs/ocr-bakeoff/<engine>-<mode>-<page>.md  +  scorecard on stdout
"""
from __future__ import annotations

import argparse
import io
import re
import os
import pathlib
import sys
import time
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

DL = pathlib.Path.home() / "Downloads"
OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "ocr-bakeoff"

# --- the pages, and what a correct read must contain --------------------------
# Every string below was verified against BOTH source documents where possible.
PAGES = {
    "gangchart": {
        "file": "WhatsApp Image 2026-08-07 at 20.07.44.jpeg",
        "facts": [
            "सोनू", "फरीद", "खालिद", "सीकरी", "भोपा",
            "कुन्ना", "मुजफ्फर", "काला", "कय्यूम", "तनवीर", "सलीम",
            "फैसल", "मुन्ना", "दाऊद", "मुदस्सिर", "जुनैद",
            "चरथावल", "भिमलाना", "खालापार", "155",
            "355/25", "359/25", "371/25",
            "जमानत", "जनपदीय",
        ],
        # the documented failure mode: does each member stay on a line with his
        # own age, or do the columns collapse into one run-on blob?
        "rows": [("सोनू", "34"), ("कुन्ना", "35"), ("मुजफ्फर", "40"),
                 ("तनवीर", "40"), ("फैसल", "25"), ("मुन्ना", "35"),
                 ("जुनैद", "24"), ("दाऊद", "25"), ("मुदस्सिर", "26")],
    },
    "aakhya1": {
        "file": "WhatsApp Image 2026-08-07 at 23.08.31.jpeg",
        "facts": [
            "गैंगलीडर", "सोनू", "फरीद", "मुर्सलीन", "नहर बस्ती", "मकान",
            "355/25", "359/25", "371/25", "354/2025", "394/25", "11/26",
            "318(4)", "336(2)", "गौवध", "109(1)", "बीएनएस",
            "आर्मस", "3/4/25/28", "3/25/28",
            "09.10.2025", "11.10.25", "17.10.25", "27.11.2025",
            "24.12", "10.01.2026", "खाजापुर", "गौकशी", "मुठभेड़",
        ],
        "rows": [],
    },
    "aakhya2": {
        "file": "WhatsApp Image 2026-08-07 at 23.08.32.jpeg",
        "facts": [
            "गिरोहबन्द", "1986", "3(1)", "2(ख)",
            "288/22", "368/17", "292/23", "325/22", "05/2020",
            "छपार", "चरथावल", "अनुमोदन", "प्रार्थना",
            # handwritten endorsements — the hard tier
            "अमृत जैन", "पुलिस अधीक्षक", "मजिस्ट्रेट", "परिशीलन",
        ],
        "rows": [],
    },
}


def preprocess(raw: bytes) -> bytes:
    """The real production conditioner — headnote.documents.prepare.

    Previously a hand-tuned copy that hardcoded rotate(90). Now the shipped
    module, so this bake-off measures what users will actually get.
    """
    from headnote.documents.prepare import prepare as _prep

    return _prep(raw)


# --- engines ------------------------------------------------------------------
def run_sarvam(data: bytes, name: str) -> str:
    from headnote.integrations import sarvam

    return sarvam.digitize_to_text(data, filename=f"{name}.jpg",
                                   mime="image/jpeg", language="hi-IN",
                                   poll_timeout=180.0)


def run_gemini(data: bytes, name: str) -> str:
    import base64

    import httpx

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    model = os.environ.get("GEMINI_OCR_MODEL", "gemini-flash-lite-latest")
    prompt = ("Transcribe every word of this Hindi legal document exactly as written. "
              "Preserve the table structure: one line per row, columns separated by ' | '. "
              "Do not translate, summarise, correct or omit anything. "
              "Where text is genuinely illegible write [अपठनीय].")
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={"contents": [{"parts": [
            {"inline_data": {"mime_type": "image/jpeg",
                             "data": base64.b64encode(data).decode()}},
            {"text": prompt}]}]},
        timeout=180.0,
    )
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


ENGINES = {
    "sarvam": (run_sarvam, lambda: bool(os.environ.get("SARVAM_API_KEY", "").strip())),
    "gemini": (run_gemini, lambda: bool(os.environ.get("GEMINI_API_KEY")
                                        or os.environ.get("GOOGLE_API_KEY"))),
}


def _row_units(text: str) -> list[str]:
    """One string per table row, whichever way the engine emitted the table.

    Engines return either an HTML <table> (Sarvam) or one row per newline. In
    HTML each cell is on its own line, so splitting on newlines scores every
    row as broken — that was a bug in this scorer, not a fault in the engine.
    """
    html = re.findall(r"<tr>(.*?)</tr>", text, re.S)
    if html:
        return [re.sub(r"<[^>]+>", " | ", r) for r in html]
    return text.splitlines()


def score(text: str, spec: dict) -> tuple[int, int, int, int, list[str]]:
    """Return (facts_hit, facts_total, rows_intact, rows_total, misses)."""
    # strip markup and collapse whitespace: a fact split across a tag or a
    # line-wrap is still a fact the engine read correctly
    flat = re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", text))
    keys = [(f, re.sub(r"\s+", "", f)) for f in spec["facts"]]
    hits = [f for f, k in keys if k in flat]
    misses = [f for f, k in keys if k not in flat]
    units = _row_units(text)
    intact = sum(1 for name, age in spec["rows"]
                 if any(name in u and age in u for u in units))
    return len(hits), len(spec["facts"]), intact, len(spec["rows"]), misses


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run a single page key")
    ap.add_argument("--raw-only", action="store_true", help="skip the preprocessed pass")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    live = {n: fn for n, (fn, ok) in ENGINES.items() if ok()}
    if not live:
        print("no engine keys set — nothing to run", file=sys.stderr)
        return 2
    print(f"engines: {', '.join(live)}\n")

    modes = ["raw"] if args.raw_only else ["raw", "prep"]
    rows = []
    for pkey, spec in PAGES.items():
        if args.only and args.only != pkey:
            continue
        src = DL / spec["file"]
        if not src.exists():
            print(f"!! missing {src}", file=sys.stderr)
            continue
        raw = src.read_bytes()
        for mode in modes:
            data = raw if mode == "raw" else preprocess(raw)
            for ename, fn in live.items():
                t0 = time.time()
                try:
                    text = fn(data, f"{pkey}-{mode}")
                    err = ""
                except Exception as e:  # noqa: BLE001 - report, never abort the sweep
                    text, err = "", f"{type(e).__name__}: {e}"
                    traceback.print_exc(limit=1, file=sys.stderr)
                dt = time.time() - t0
                (OUT / f"{ename}-{mode}-{pkey}.md").write_text(text or f"FAILED\n{err}\n")
                h, tot, ri, rtot, misses = score(text, spec)
                rows.append((pkey, mode, ename, h, tot, ri, rtot, dt, err, misses))
                tail = err or (f"rows {ri}/{rtot}" if rtot else "")
                print(f"  {pkey:10} {mode:4} {ename:7} facts {h:2}/{tot:<2} "
                      f"{tail:24} {dt:5.1f}s  {len(text):6} chars")

    print("\n" + "=" * 78)
    print(f"{'page':11}{'mode':6}{'engine':9}{'facts':>8}{'rows':>8}{'secs':>7}")
    print("-" * 78)
    for p, m, e, h, tot, ri, rtot, dt, err, _ in rows:
        rr = f"{ri}/{rtot}" if rtot else "-"
        print(f"{p:11}{m:6}{e:9}{f'{h}/{tot}':>8}{rr:>8}{dt:>7.1f}"
              + ("  " + err[:30] if err else ""))
    print("=" * 78)
    for p, m, e, h, tot, _, _, _, err, misses in rows:
        if misses and not err:
            print(f"\n{e}/{m}/{p} missed {len(misses)}: {', '.join(misses[:14])}")
    print(f"\nfull text: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
