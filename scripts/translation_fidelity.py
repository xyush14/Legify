#!/usr/bin/env python3
"""Translation-fidelity bake-off — pick the engine for DOCUMENT translation.

Different question from scripts/i18n_bakeoff.py, which compares engines on short
template lines against a reviewed glossary. This one runs REAL legal prose (a
paragraph of a live gang-chart आख्या, dense with citations) and asks the only
question that is objectively checkable on a legal document:

    does every case number, section, date and figure survive the translation
    EXACTLY, and is nothing added or dropped?

An engine that renders beautiful prose but mangles "मु0अ0सं0 355/25 धारा 318(4)"
is unusable here, however fluent it sounds. Register is a judgement call and is
printed side-by-side for a human; citation fidelity is machine-checked.

Keys (only engines with a key are run):
    SARVAM_API_KEY       -> Mayura translate
    ANTHROPIC_API_KEY    -> Claude (model via --claude-model)

Usage:
    SARVAM_API_KEY=... python scripts/translation_fidelity.py
Output: docs/ocr-bakeoff/translation-fidelity.md + scorecard on stdout
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
import time
import traceback

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "ocr-bakeoff"

# A real paragraph from the आख्या transcribed this session. Citation-dense on
# purpose: three statutes, two case numbers, three dates, four proper nouns.
HI = (
    "दिनांक 11.10.25 को अभियुक्त गण कुन्ना उर्फ पुन्नन उर्फ पुन्नी उर्फ नजर पुत्र खालिद "
    "नि0 ग्राम सीकरी थाना भोपा मु0नगर व सोनू उर्फ फरीद पुत्र खालिद के द्वारा पानीपत-खटीमा "
    "मार्ग पर बाननगर अंडरपास के पास पुलिस पार्टी पर जान से मारने की नीयत से फायर करना, "
    "व बाद पुलिस मुठभेड़ मय नाजायज असलाह के गिरफ्तार किया गया। उक्त सम्बन्ध में थाना "
    "को0नगर मु0नगर पर मु0अ0सं0 359/25 धारा 109(1) बीएनएस व 3/4/25/28 आर्मस एक्ट "
    "पंजीकृत किया गया। उक्त अभियोग की विवेचना में अभियुक्त गण के विरूद्ध बाद विवेचना "
    "आरोप पत्र – 394/25 दि0 24.12.2025 को मा० न्यायालय में प्रेषित किया गया।"
)

# The reverse direction: English legal prose a district advocate would need in Hindi.
EN = (
    "The applicant is in judicial custody since 11.10.2025 in Case Crime No. 359/25 "
    "under Section 109(1) BNS read with Sections 3/4/25/28 of the Arms Act, "
    "Police Station Kotwali Nagar, Muzaffarnagar. Charge-sheet No. 394/25 dated "
    "24.12.2025 has already been filed before the learned Court, and the applicant "
    "has no previous conviction. It is therefore prayed that the applicant be "
    "released on bail under Section 483 BNSS."
)

# Tokens that MUST survive unchanged in either direction.
CITES = ["11.10", "359/25", "109(1)", "3/4/25/28", "394/25", "24.12.2025"]
CITES_EN = CITES + ["483"]


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def fidelity(out: str, cites: list[str]) -> tuple[list[str], list[str]]:
    flat = _norm(out)
    return [c for c in cites if _norm(c) in flat], [c for c in cites if _norm(c) not in flat]


# --- engines ------------------------------------------------------------------
LEGAL_RULES = (
    "You translate Indian legal documents for a practising advocate. Rules, in order:\n"
    "1. Reproduce every case number, section number, statute name, date and figure "
    "EXACTLY as in the source. Never renumber, reformat or convert them.\n"
    "2. Use the register of an Indian court filing, not conversational prose.\n"
    "3. Transliterate proper nouns; never translate a person's or a place's name.\n"
    "4. Do not add, omit, explain or summarise anything. Never state as completed an "
    "act the source describes only as attempted or intended.\n"
    "Return only the translation."
)


def sarvam_translate(text: str, src: str, tgt: str) -> str:
    import httpx

    r = httpx.post(
        "https://api.sarvam.ai/translate",
        headers={"api-subscription-key": os.environ["SARVAM_API_KEY"],
                 "Content-Type": "application/json"},
        json={"input": text, "source_language_code": src, "target_language_code": tgt,
              "mode": "formal", "enable_preprocessing": False},
        timeout=90.0,
    )
    r.raise_for_status()
    j = r.json()
    return j.get("translated_text") or j.get("output") or str(j)[:400]


def claude_translate(text: str, src: str, tgt: str) -> str:
    import anthropic

    tgt_name = {"en-IN": "English", "hi-IN": "Hindi"}[tgt]
    sysmsg = LEGAL_RULES
    m = anthropic.Anthropic().messages.create(
        model=os.environ.get("CLAUDE_TR_MODEL", "claude-sonnet-5"),
        max_tokens=2000, system=sysmsg,
        messages=[{"role": "user", "content": f"Translate into {tgt_name}:\n\n{text}"}],
    )
    return "".join(b.text for b in m.content if b.type == "text").strip()


def sarvam_llm(text: str, src: str, tgt: str) -> str:
    """Sarvam's instruction-following LLM — NOT Mayura.

    Mayura is a machine-translation model: it cannot be told to protect a
    citation, so it renumbers and drops them. An LLM can be given the same
    court-register rules Claude gets, at a fraction of the token price.
    """
    import httpx

    tgt_name = {"en-IN": "English", "hi-IN": "Hindi"}[tgt]
    model = os.environ.get("SARVAM_TR_MODEL", "sarvam-m")
    r = httpx.post(
        "https://api.sarvam.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['SARVAM_API_KEY']}",
                 "Content-Type": "application/json"},
        json={"model": model, "temperature": 0.1, "max_tokens": 2000,
              "messages": [{"role": "system", "content": LEGAL_RULES},
                           {"role": "user",
                            "content": f"Translate into {tgt_name}:\n\n{text}"}]},
        timeout=120.0,
    )
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"].strip()


def gemini_translate(text: str, src: str, tgt: str) -> str:
    """Gemini Flash Lite — the cheap default candidate.

    Already the repo's choice for Devanagari handwriting (config.py:140), so
    using it here means one vendor fewer, not one more.
    """
    import httpx

    tgt_name = {"en-IN": "English", "hi-IN": "Hindi"}[tgt]
    key = os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"]
    model = os.environ.get("GEMINI_TR_MODEL", "gemini-flash-lite-latest")
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={"system_instruction": {"parts": [{"text": LEGAL_RULES}]},
              "contents": [{"parts": [{"text": f"Translate into {tgt_name}:\n\n{text}"}]}],
              "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2000}},
        timeout=120.0)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:200]}")
    c = r.json()["candidates"][0]
    return "".join(p.get("text", "") for p in c["content"]["parts"]).strip()


ENGINES = {
    "gemini-flash-lite": (gemini_translate,
                          lambda: bool(os.environ.get("GEMINI_API_KEY")
                                       or os.environ.get("GOOGLE_API_KEY"))),
    "sarvam-105b": (sarvam_llm, lambda: bool(os.environ.get("SARVAM_API_KEY"))),
    "sarvam-mayura": (sarvam_translate, lambda: bool(os.environ.get("SARVAM_API_KEY"))),
    "claude": (claude_translate, lambda: bool(os.environ.get("ANTHROPIC_API_KEY"))),
}

JOBS = [("hi->en", HI, "hi-IN", "en-IN", CITES), ("en->hi", EN, "en-IN", "hi-IN", CITES_EN)]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    live = {n: fn for n, (fn, ok) in ENGINES.items() if ok()}
    if not live:
        print("no engine keys set", file=sys.stderr)
        return 2
    print(f"engines: {', '.join(live)}\n")

    md, rows = ["# Translation fidelity — legal prose\n"], []
    for label, text, src, tgt, cites in JOBS:
        md.append(f"\n## {label}\n\n**Source**\n\n> {text}\n")
        for name, fn in live.items():
            t0 = time.time()
            try:
                out, err = fn(text, src, tgt), ""
            except Exception as e:  # noqa: BLE001 — report, never abort the sweep
                out, err = "", f"{type(e).__name__}: {e}"
                traceback.print_exc(limit=1, file=sys.stderr)
            dt = time.time() - t0
            hit, miss = fidelity(out, cites)
            rows.append((label, name, len(hit), len(cites), dt, err, miss))
            print(f"  {label:8} {name:14} citations {len(hit)}/{len(cites)}  {dt:5.1f}s"
                  + (f"  {err[:40]}" if err else "")
                  + (f"  DROPPED: {', '.join(miss)}" if miss else ""))
            md.append(f"\n**{name}** — citations {len(hit)}/{len(cites)}"
                      + (f", dropped `{'`, `'.join(miss)}`" if miss else "")
                      + f"\n\n> {out or '(failed) ' + err}\n")

    print("\n" + "=" * 66)
    print(f"{'direction':11}{'engine':16}{'citations':>11}{'secs':>8}")
    print("-" * 66)
    for label, name, h, tot, dt, err, _ in rows:
        print(f"{label:11}{name:16}{f'{h}/{tot}':>11}{dt:>8.1f}" + ("  " + err[:24] if err else ""))
    print("=" * 66)
    p = OUT / "translation-fidelity.md"
    p.write_text("\n".join(md))
    print(f"\nside-by-side for register judgement: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
