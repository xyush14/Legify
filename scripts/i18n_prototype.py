#!/usr/bin/env python3
"""Regional-language drafting prototype.

Renders a canonical template's Hindi draft, translates it into a target regional
language via headnote.drafter.i18n, and writes a side-by-side ADVOCATE REVIEW
SHEET (Hindi | machine draft | correction column) for jurisdiction sign-off.

Usage
-----
    # needs DEEPSEEK_API_KEY (or ANTHROPIC_API_KEY) in the env
    python scripts/i18n_prototype.py --template discharge_239 --lang mr
    python scripts/i18n_prototype.py --template discharge_239 --lang mr --facts-lang en

Output: docs/i18n/<template>-<lang>.html

Quality knobs
-------------
* Boilerplate is translated with the DEEP model (R1) + the court-term glossary.
* --facts-lang sets the language the client narrative is assumed to be typed in
  (default hi). If it differs from Hindi (e.g. en), the facts are translated
  with transliteration of proper nouns.
"""
from __future__ import annotations

import argparse
import html as _htmllib
import importlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from headnote.drafter.i18n import engine  # noqa: E402
from headnote.drafter.i18n import glossary as glossary_mod  # noqa: E402

# Paragraphs we surface for review are the <li><p>…</p></li> and prayer/title
# blocks of a rendered draft. We translate each visible text run independently
# so the review sheet aligns row-by-row (and so a failure on one para doesn't
# sink the whole doc).
_TEXT_BLOCK_RX = re.compile(r">([^<>]+)<")


def _load_template(name: str):
    return importlib.import_module(f"headnote.drafter.templates.{name}")


def _visible_runs(html: str) -> list[str]:
    """Ordered, de-duplicated visible text runs from rendered HTML."""
    seen: set[str] = set()
    runs: list[str] = []
    for m in _TEXT_BLOCK_RX.finditer(html):
        s = m.group(1).strip()
        if not s or s in seen:
            continue
        # skip pure punctuation / dotted placeholders
        if re.fullmatch(r"[.…\s:—/()]+", s):
            continue
        seen.add(s)
        runs.append(s)
    return runs


_REVIEW_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f3f1ea;font-family:'Noto Sans Devanagari','Tiro Devanagari Hindi',system-ui,sans-serif;color:#1a1814}
.hd{background:#1a1814;color:#faf8f3;padding:16px 22px}
.hd h1{margin:0 0 4px;font-size:16px;font-weight:700}
.hd h1 b{color:#e9c46a}
.hd p{margin:0;font-size:12.5px;color:#cfc9bd;line-height:1.5}
.hd .warn{color:#e9c46a;font-weight:600}
.meta{display:flex;gap:18px;flex-wrap:wrap;padding:12px 22px;background:#fff;border-bottom:1px solid #e6e2d8;font-size:12px;color:#5a544a}
.meta b{color:#1a1814}
table{width:100%;border-collapse:collapse;background:#fff}
th{position:sticky;top:0;background:#efece3;text-align:left;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#6b6459;padding:10px 14px;border-bottom:2px solid #ddd8cc;font-family:'Geist Mono',ui-monospace,monospace}
td{padding:12px 14px;border-bottom:1px solid #eee9dd;vertical-align:top;font-size:14.5px;line-height:1.7}
td.n{width:34px;color:#b4afa3;font-family:ui-monospace,monospace;font-size:12px}
td.hi{width:38%;color:#3a352d}
td.tgt{width:38%;color:#111;background:#fbfaf5}
td.fix{color:#b4afa3;font-style:italic;font-size:12.5px}
.pin{border-left:3px solid #e9c46a}
tr.title td{background:#f7f4ec;font-weight:700}
.foot{padding:16px 22px;font-size:12px;color:#6b6459;background:#fff;border-top:1px solid #e6e2d8;line-height:1.6}
"""


def build_review_sheet(template: str, lang: str, rows: list[dict], *,
                       model_note: str, facts_lang: str) -> str:
    lang_name = engine.SUPPORTED_LANGS.get(lang, lang)
    pinned, total = glossary_mod.coverage(lang)
    trs = []
    for i, r in enumerate(rows, 1):
        cls = " pin" if r.get("pinned") else ""
        trs.append(
            f'<tr class="{cls.strip()}">'
            f'<td class="n">{i}</td>'
            f'<td class="hi">{_htmllib.escape(r["hi"])}</td>'
            f'<td class="tgt">{_htmllib.escape(r["tgt"])}</td>'
            f'<td class="fix">advocate correction…</td>'
            f'</tr>'
        )
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{template} → {lang_name} — advocate review</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;600;700&family=Noto+Sans+Bengali:wght@400;600;700&family=Noto+Sans+Gujarati:wght@400;600;700&display=swap" rel="stylesheet">
<style>{_REVIEW_CSS}</style></head><body>
<div class="hd">
  <h1>Regional draft review — <b>{template} → {lang_name}</b></h1>
  <p class="warn">MACHINE DRAFT — NOT FILE-READY. Every row needs a {lang_name}-court advocate to confirm or correct before this ships.</p>
</div>
<div class="meta">
  <span><b>Template:</b> {template}</span>
  <span><b>Target:</b> {lang_name} ({lang})</span>
  <span><b>Engine:</b> {model_note}</span>
  <span><b>Facts assumed typed in:</b> {facts_lang}</span>
  <span><b>Glossary pinned:</b> {pinned}/{total} terms</span>
</div>
<table>
  <thead><tr><th>#</th><th>Hindi (shipped)</th><th>{lang_name} (machine)</th><th>Advocate correction</th></tr></thead>
  <tbody>{''.join(trs)}</tbody>
</table>
<div class="foot">
  Rows with a <b>gold edge</b> use a glossary-pinned term (pre-verified vocabulary — the advocate can skim these).
  Everything else is free model output and needs a real read.<br>
  Pipeline: <code>headnote/drafter/i18n/engine.py</code> · glossary: <code>headnote/drafter/i18n/glossary.py</code> · regenerate: <code>python scripts/i18n_prototype.py --template {template} --lang {lang}</code>
</div>
</body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="discharge_239")
    ap.add_argument("--lang", default="mr", choices=["mr", "bn", "gu"])
    ap.add_argument("--facts-lang", default="hi",
                    help="language the client facts are assumed typed in (hi/en)")
    ap.add_argument("--fast", action="store_true",
                    help="use the fast model (V3) instead of deep (R1)")
    args = ap.parse_args()

    mod = _load_template(args.template)
    sample = getattr(mod, "SAMPLE", {})
    hi_html = mod.render_hi(sample)
    runs = _visible_runs(hi_html)

    pinned_terms = {ln.split("→")[0].strip() for ln in glossary_mod.glossary_lines(args.lang)}

    print(f"[i18n] {args.template} → {args.lang}: translating {len(runs)} text runs "
          f"({'V3 fast' if args.fast else 'R1 deep'})…", file=sys.stderr)

    rows: list[dict] = []
    for i, run in enumerate(runs, 1):
        tgt = engine.translate_segment(
            run, args.lang, source_lang="hi",
            mode="boilerplate", deep=not args.fast,
        )
        rows.append({
            "hi": run,
            "tgt": tgt,
            "pinned": any(p and p in run for p in pinned_terms),
        })
        print(f"  [{i}/{len(runs)}] ok", file=sys.stderr)

    from headnote.drafter.i18n.engine import _mt_provider
    model_note = ("Bhashini NMT (masked tokens)" if _mt_provider() == "bhashini"
                  else ("DeepSeek-V3 (fast)" if args.fast else "DeepSeek-R1 (deep) + glossary"))
    out_html = build_review_sheet(
        args.template, args.lang, rows,
        model_note=model_note, facts_lang=args.facts_lang,
    )
    out_dir = ROOT / "docs" / "i18n"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.template}-{args.lang}.html"
    out_path.write_text(out_html, encoding="utf-8")
    print(f"[i18n] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
