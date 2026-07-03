#!/usr/bin/env python3
"""Translation-engine bake-off — pick the best-output backend from evidence.

Runs the same template lines through every configured engine (Sarvam / Bhashini
/ LLM) and writes a side-by-side HTML sheet: Hindi | Sarvam | Bhashini | LLM |
glossary-expected | advocate-pick. Whichever column the advocate keeps ticking
is your boilerplate engine.

Only engines with credentials present are run; the rest show "(no key)".

Keys (set whichever you have):
    SARVAM_API_KEY
    BHASHINI_USER_ID + BHASHINI_ULCA_API_KEY
    DEEPSEEK_API_KEY or ANTHROPIC_API_KEY   (the LLM column)

Usage:
    python scripts/i18n_bakeoff.py --template discharge_239 --lang mr --n 8
Output: docs/i18n/bakeoff-<template>-<lang>.html
"""
from __future__ import annotations

import argparse
import html as _htmllib
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from headnote.drafter.i18n import bhashini, sarvam, glossary as gmod  # noqa: E402


def _runs(template: str, n: int) -> list[str]:
    mod = importlib.import_module(f"headnote.drafter.templates.{template}")
    html = mod.render_hi(getattr(mod, "SAMPLE", {}))
    import re
    seen, out = set(), []
    for m in re.finditer(r">([^<>]+)<", html):
        s = m.group(1).strip()
        if s and s not in seen and not re.fullmatch(r"[.…\s:—/()]+", s) and len(s) > 12:
            seen.add(s); out.append(s)
        if len(out) >= n:
            break
    return out


def _llm_translate(text: str, lang: str) -> str:
    from headnote.drafter.i18n.engine import _translate_via_llm
    return _translate_via_llm(text, lang, "hi", "boilerplate", True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="discharge_239")
    ap.add_argument("--lang", default="mr", choices=["mr", "bn", "gu"])
    ap.add_argument("--n", type=int, default=8)
    args = ap.parse_args()

    engines = {
        "Sarvam (formal)": (sarvam.translate, sarvam.is_configured()),
        "Bhashini": (bhashini.translate, bhashini.is_configured()),
    }
    import os
    llm_ok = bool(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
    engines["LLM (+glossary)"] = (lambda t, s, tg: _llm_translate(t, tg), llm_ok)

    runs = _runs(args.template, args.n)
    gloss = {ln.split("→")[0].strip(): ln.split("→")[1].strip() for ln in gmod.glossary_lines(args.lang)}

    print(f"[bakeoff] {args.template} → {args.lang}: {len(runs)} lines · "
          f"engines: {[n for n,(_,ok) in engines.items() if ok] or 'NONE configured'}", file=sys.stderr)

    head = "".join(f"<th>{_htmllib.escape(n)}{'' if ok else ' (no key)'}</th>" for n,(_,ok) in engines.items())
    rows = []
    for i, src in enumerate(runs, 1):
        cells = []
        for name,(fn,ok) in engines.items():
            if not ok:
                cells.append('<td style="color:#c9c3b4">—</td>'); continue
            try:
                out = fn(src, "hi", args.lang)
                cells.append(f'<td>{_htmllib.escape(out)}</td>')
            except Exception as e:
                cells.append(f'<td style="color:#b00">✕ {_htmllib.escape(type(e).__name__)}: {_htmllib.escape(str(e)[:80])}</td>')
        gl = " · ".join(f"{h}→{t}" for h,t in gloss.items() if h in src) or "—"
        rows.append(f'<tr><td class="n">{i}</td><td class="hi">{_htmllib.escape(src)}</td>{"".join(cells)}'
                    f'<td class="gl">{_htmllib.escape(gl)}</td><td class="pick">▢</td></tr>')

    out_html = f"""<!doctype html><html lang="{args.lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Engine bake-off — {args.template} → {args.lang}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;600;700&display=swap" rel="stylesheet">
<style>
body{{margin:0;background:#f3f1ea;font-family:'Noto Sans Devanagari',system-ui,sans-serif;color:#1a1814}}
.hd{{background:#1a1814;color:#faf8f3;padding:16px 22px}}.hd h1{{margin:0;font-size:16px}}.hd h1 b{{color:#e9c46a}}
.hd p{{margin:4px 0 0;font-size:12.5px;color:#cfc9bd}}
table{{width:100%;border-collapse:collapse;background:#fff;font-size:13.5px}}
th{{position:sticky;top:0;background:#efece3;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#6b6459;padding:9px 12px;border-bottom:2px solid #ddd8cc}}
td{{padding:11px 12px;border-bottom:1px solid #eee9dd;vertical-align:top;line-height:1.7}}
td.n{{color:#b4afa3;font-family:monospace;font-size:11px}}td.hi{{color:#3a352d;width:24%}}
td.gl{{color:#8a6d1a;font-size:11.5px;width:12%}}td.pick{{text-align:center;font-size:16px;color:#c9c3b4}}
</style></head><body>
<div class="hd"><h1>Translation-engine bake-off — <b>{args.template} → {args.lang}</b></h1>
<p>Same Hindi line through each engine. Tick the column that reads closest to filing-grade court {args.lang}. That's your boilerplate engine.</p></div>
<table><thead><tr><th>#</th><th>Hindi</th>{head}<th>glossary expects</th><th>pick</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>"""
    out_dir = ROOT / "docs" / "i18n"; out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"bakeoff-{args.template}-{args.lang}.html"
    out_path.write_text(out_html, encoding="utf-8")
    print(f"[bakeoff] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
