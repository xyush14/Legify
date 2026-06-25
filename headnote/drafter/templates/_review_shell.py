"""Shared read-only review shell for deterministic draft templates.

Every `templates/<type>.py` module that wants an advocate sign-off page
(a no-JS, self-contained HTML render in the EXACT court-paper format used by
/draft/bail and /draft/discharge) builds it through `review_shell()` here, so
the CSS, page geometry and fonts are identical across every draft type — the
same `.doc-page` + `.bail-doc` styles the live canvases use.

`discharge_239.py` keeps its own inline copy (it shipped first); every new
module shares this one. Keep the CSS byte-identical to discharge's `_REVIEW_CSS`
so the formats never drift.
"""
from __future__ import annotations


# Identical to discharge_239._REVIEW_CSS — court-paper geometry shared by every
# /draft/* canvas. Generic (.bail-doc / .doc-page); no per-type rules live here.
REVIEW_CSS = """
  *{box-sizing:border-box}
  body{margin:0;background:#e8e6df;font-family:'Tiro Devanagari Hindi','Noto Serif Devanagari',serif;color:#1a1814}
  .review-banner{background:#1a1814;color:#faf8f3;padding:12px 18px;font-size:13px;line-height:1.5;text-align:center}
  .review-banner b{color:#e9c46a}
  .review-banner small{display:block;color:#cfc9bd;font-size:11.5px;margin-top:3px}
  .doc-pane{padding:30px 16px 70px}
  .doc-page{background:#fff;max-width:760px;margin:0 auto;padding:60px 70px 80px;min-height:85vh;
    box-shadow:0 1px 3px rgba(0,0,0,.04),0 8px 24px rgba(0,0,0,.06);border-radius:4px;
    font-family:'Times New Roman','Tiro Devanagari Hindi','Noto Serif Devanagari',Times,serif;
    line-height:1.7;color:#000;font-size:14.5px}
  .bail-doc{font-size:14.5px}
  .bail-doc .bd-header{text-align:center;margin-bottom:20px}
  .bail-doc .bd-side{font-size:13px;margin-bottom:6px}
  .bail-doc .bd-court{font-size:16.5px;font-weight:700;margin:4px 0 12px;letter-spacing:.01em}
  .bail-doc .bd-caseno{font-size:14px;margin-bottom:6px}
  .bail-doc .bd-parties{margin:26px 0 14px}
  .bail-doc .bd-party{display:grid;grid-template-columns:1fr auto auto;gap:6px;margin-bottom:10px;align-items:end}
  .bail-doc .bd-party-label{font-weight:500;white-space:nowrap}
  .bail-doc .bd-party-dots{color:#555;overflow:hidden;white-space:nowrap}
  .bail-doc .bd-party-detail{text-align:left}
  .bail-doc .bd-versus{text-align:center;font-weight:700;margin:10px 0;font-size:15px}
  .bail-doc .bd-app-title{text-align:center;text-decoration:underline;font-size:16px;font-weight:700;margin:24px 0 18px}
  .bail-doc .bd-prelude{margin:16px 0 10px;text-align:justify}
  .bail-doc .bd-section-label{font-weight:700;margin:14px 0 6px}
  .bail-doc .bd-paras{padding-left:0;counter-reset:para;list-style:none}
  .bail-doc .bd-paras>li{counter-increment:para;position:relative;padding-left:36px;margin-bottom:14px;text-align:justify;line-height:1.75}
  .bail-doc .bd-paras>li::before{content:counter(para) ".";position:absolute;left:0;font-weight:700;width:30px;text-align:right;padding-right:6px}
  .bail-doc .bd-subparas{padding-left:0;counter-reset:sub;list-style:none;margin-top:8px}
  .bail-doc .bd-subparas>li{counter-increment:sub;position:relative;padding-left:34px;margin-bottom:10px;text-align:justify;line-height:1.75}
  .bail-doc .bd-subparas>li::before{content:"(" counter(sub) ")";position:absolute;left:0;width:30px;text-align:right;padding-right:6px}
  .bail-doc .bd-table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}
  .bail-doc .bd-table th,.bail-doc .bd-table td{border:1px solid #333;padding:5px 7px;text-align:left;vertical-align:top}
  .bail-doc .bd-prayer{margin:24px 0}
  .bail-doc .bd-prayer h3{text-align:center;text-decoration:underline;margin:10px 0 12px;font-size:16px;font-weight:700}
  .bail-doc .bd-prayer p{text-align:justify;padding-left:36px;text-indent:-10px;line-height:1.75}
  .bail-doc .bd-verification{margin:22px 0;text-align:justify}
  .bail-doc .bd-verification h3{text-align:center;text-decoration:underline;margin:10px 0 10px;font-size:15px;font-weight:700}
  .bail-doc .bd-sig{display:flex;justify-content:space-between;margin-top:38px;font-size:14px}
  .bail-doc .bd-sig-right{text-align:center}
  .bail-doc .bd-sig-name{margin-top:8px}
  .bail-doc .bd-sig-advocate{margin-top:14px}
  .bail-doc .bd-sig-advname{font-weight:600;margin-top:18px}
  .bail-doc .ph{color:#b4afa3;font-style:italic}
"""

_FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Tiro+Devanagari+Hindi'
    '&family=Noto+Serif+Devanagari:wght@400;600;700&display=swap" rel="stylesheet">'
)


def review_shell(*, page_title: str, banner_html: str, doc_html: str,
                 lang: str = "hi") -> str:
    """Wrap a rendered document in the standalone, read-only review page.

    page_title  — <title> text (browser tab).
    banner_html — inner HTML of the dark review banner (the <b>…</b><small>…
                  </small> sign-off context line). Caller supplies the text so
                  each draft type names its own benchmark.
    doc_html    — the document HTML from render_hi()/render_en().
    """
    return (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{page_title}</title>'
        + _FONT_LINKS +
        '<style>' + REVIEW_CSS + '</style></head><body>'
        f'<div class="review-banner">{banner_html}</div>'
        f'<div class="doc-pane"><div class="doc-page">{doc_html}</div></div>'
        '</body></html>'
    )
