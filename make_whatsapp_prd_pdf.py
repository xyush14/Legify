"""Render docs/WHATSAPP_BOT_PRD.md to a brand-consistent A4 PDF.

Markdown → HTML → Chrome headless → PDF. Same pipeline pattern as the
brochure / pricing / distributor packs. Output: Headnote_WhatsApp_Bot_PRD.pdf
at repo root.
"""
from __future__ import annotations

import base64
import pathlib
import shutil
import subprocess
import sys

import markdown

ROOT = pathlib.Path(__file__).resolve().parent
SRC_MD = ROOT / "docs" / "WHATSAPP_BOT_PRD.md"
OUT_PDF = ROOT / "Headnote_WhatsApp_Bot_PRD.pdf"
BUILD = ROOT / "_build" / "wa_prd"
BUILD.mkdir(parents=True, exist_ok=True)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

GEIST_URL = "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/geist/Geist%5Bwght%5D.ttf"
MONO_URL = "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf"


def fetch_font(url: str, dest: pathlib.Path) -> pathlib.Path:
    if dest.exists() and dest.stat().st_size > 50_000:
        return dest
    import urllib.request
    urllib.request.urlretrieve(url, dest)
    return dest


def font_b64(path: pathlib.Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def parse_front_matter(md_text: str) -> tuple[dict, str]:
    if not md_text.startswith("---"):
        return {}, md_text
    end = md_text.find("\n---", 4)
    if end < 0:
        return {}, md_text
    head = md_text[4:end].strip()
    rest = md_text[end + 4:].lstrip("\n")
    meta = {}
    for line in head.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta, rest


def build_html(meta: dict, body_md: str, geist_b64: str, mono_b64: str) -> str:
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
        extension_configs={"toc": {"permalink": False}},
    )
    body_html = md.convert(body_md)
    logo_svg = (ROOT / "static" / "headnote-logo.svg").read_text()
    title = "WhatsApp Bot — PRD"
    subtitle = "End-to-end legal research over WhatsApp"
    version = meta.get("version", "0.1")
    owner = meta.get("owner", "Ayush (xyush14)")
    updated = meta.get("last_updated", "2026-06-15")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Headnote — WhatsApp Bot PRD</title>
<style>
@font-face {{
  font-family: 'Geist'; font-style: normal; font-weight: 100 900;
  src: url(data:font/ttf;base64,{geist_b64}) format('truetype-variations');
}}
@font-face {{
  font-family: 'JetBrainsMono'; font-style: normal; font-weight: 100 900;
  src: url(data:font/ttf;base64,{mono_b64}) format('truetype-variations');
}}
:root {{
  --ink: #1A1814;
  --body: #46402F;
  --mute: #8A8473;
  --paper: #FAF8F3;
  --card: #FFFFFF;
  --line: #E8E1D2;
  --soft: #F4EFE4;
  --gold-light: #B8924E;
  --gold-bright: #D4A858;
  --dark: #0F0C08;
  --green: #2D6A2D;
}}
* {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
html, body {{ margin: 0; padding: 0; background: var(--paper); color: var(--body);
              font-family: 'Geist', -apple-system, sans-serif; font-weight: 400;
              font-size: 10.5pt; line-height: 1.55; }}

@page {{ size: A4; margin: 18mm 16mm 18mm 16mm; }}

/* ───── COVER (light editorial) ───── */
.cover {{
  height: 261mm;
  display: flex; flex-direction: column;
  page-break-after: always;
  background: var(--paper); color: var(--ink);
}}
.cover .logo {{ width: 64mm; margin-bottom: 4mm; }}
.cover .logo svg {{ width: 100%; height: auto; }}
.cover .logo svg path {{ fill: var(--ink) !important; }}
.cover .kicker {{ font-family: 'JetBrainsMono', monospace; font-size: 8.5pt;
  letter-spacing: 0.16em; text-transform: uppercase; color: var(--gold-light);
  margin-top: 70mm; padding-bottom: 4mm;
  border-bottom: 1px solid var(--line); }}
.cover h1 {{ font-family: 'Geist', sans-serif; font-weight: 600;
  font-size: 42pt; line-height: 1.04; margin: 8mm 0 10mm 0;
  color: var(--ink); letter-spacing: -0.025em; max-width: 160mm; }}
.cover .accent-rule {{ width: 28mm; height: 3px; background: var(--gold-bright);
  margin: 0 0 12mm 0; }}
.cover .sub {{ font-size: 14pt; color: var(--body); max-width: 150mm;
  line-height: 1.45; font-weight: 400; }}
.cover .meta {{ margin-top: auto; font-family: 'JetBrainsMono', monospace;
  font-size: 8.5pt; color: var(--mute); line-height: 1.9;
  padding-top: 6mm; border-top: 1px solid var(--line); display: grid;
  grid-template-columns: 1fr 1fr; gap: 1mm 8mm; }}
.cover .meta b {{ color: var(--ink); font-weight: 500;
  display: inline-block; min-width: 24mm; }}

/* ───── BODY ───── */
.body {{ padding: 0; }}
h1, h2, h3, h4 {{ font-family: 'Geist', sans-serif; color: var(--ink);
  font-weight: 600; letter-spacing: -0.01em; }}
h1 {{ font-size: 20pt; margin: 14mm 0 4mm; line-height: 1.15;
  border-bottom: 1px solid var(--line); padding-bottom: 3mm;
  page-break-before: auto; page-break-after: avoid; }}
h2 {{ font-size: 14pt; margin: 10mm 0 3mm; line-height: 1.2; color: var(--ink);
  page-break-after: avoid; }}
h2::before {{ content: ""; display: inline-block; width: 6px; height: 6px;
  background: var(--gold-light); border-radius: 50%;
  margin-right: 8px; vertical-align: middle; transform: translateY(-2px); }}
h3 {{ font-size: 11.5pt; margin: 7mm 0 2mm; color: var(--ink);
  font-family: 'JetBrainsMono', monospace; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.06em; font-size: 9pt;
  page-break-after: avoid; }}
h4 {{ font-size: 10.5pt; margin: 5mm 0 2mm; color: var(--gold-light); }}
p {{ margin: 0 0 3mm; }}
strong {{ color: var(--ink); font-weight: 600; }}
em {{ color: var(--ink); font-style: italic; }}
a {{ color: var(--gold-light); text-decoration: none; border-bottom: 1px dotted var(--gold-light); }}

ul, ol {{ margin: 0 0 4mm 0; padding-left: 6mm; }}
li {{ margin: 0 0 1.5mm; }}
li > ul, li > ol {{ margin-top: 1mm; }}

/* code */
code {{ font-family: 'JetBrainsMono', monospace; font-size: 9pt;
  background: var(--soft); padding: 1px 4px; border-radius: 3px;
  color: var(--ink); }}
pre {{ background: var(--soft); border: 1px solid var(--line);
  border-left: 3px solid var(--gold-light);
  padding: 4mm 5mm; border-radius: 4px; overflow-x: auto;
  font-size: 8.5pt; line-height: 1.5; margin: 3mm 0 5mm;
  page-break-inside: avoid; }}
pre code {{ background: transparent; padding: 0; font-size: 8.5pt; }}

/* tables */
table {{ width: 100%; border-collapse: collapse; margin: 3mm 0 6mm;
  font-size: 9.5pt; page-break-inside: auto; }}
thead {{ display: table-header-group; }}
tr {{ page-break-inside: avoid; }}
th, td {{ text-align: left; padding: 2mm 3mm; border-bottom: 1px solid var(--line);
  vertical-align: top; }}
th {{ background: var(--soft); color: var(--ink); font-weight: 600;
  font-family: 'JetBrainsMono', monospace; font-size: 8.5pt;
  text-transform: uppercase; letter-spacing: 0.04em;
  border-bottom: 2px solid var(--gold-light); }}
tr:nth-child(even) td {{ background: #FCFAF4; }}

/* blockquote */
blockquote {{ margin: 3mm 0; padding: 3mm 5mm;
  background: #FFF8E5; border-left: 3px solid var(--gold-bright);
  border-radius: 0 4px 4px 0; color: var(--body); }}
blockquote p:last-child {{ margin-bottom: 0; }}

/* hr */
hr {{ border: 0; border-top: 1px solid var(--line); margin: 8mm 0; }}

/* task list checkboxes (GFM) — markdown lib renders them as bullets,
   we just style the literal "[ ]" / "[x]" prefix if present */

/* page-break helpers */
.section {{ page-break-before: always; }}
.no-break {{ page-break-inside: avoid; }}

/* small caps emphasis line */
em:first-child {{ }}
</style>
</head>
<body>

<section class="cover">
  <div class="logo">{logo_svg}</div>
  <div class="kicker">Product Requirements Document · v{version}</div>
  <h1>{title}</h1>
  <div class="accent-rule"></div>
  <div class="sub">{subtitle}. Verified citations and a downloadable PDF memo — delivered inside the chat thread Indian advocates already live in.</div>
  <div class="meta">
    <div><b>Owner</b> &nbsp; {owner}</div>
    <div><b>Last updated</b> &nbsp; {updated}</div>
    <div><b>Status</b> &nbsp; {meta.get('status', 'draft').upper()}</div>
    <div><b>Repo</b> &nbsp; docs/WHATSAPP_BOT_PRD.md</div>
  </div>
</section>

<section class="body">
{body_html}
</section>

</body>
</html>
"""


def main() -> None:
    if not SRC_MD.exists():
        sys.exit(f"missing: {SRC_MD}")
    if not pathlib.Path(CHROME).exists():
        sys.exit("Chrome not found at the expected path")

    meta, body_md = parse_front_matter(SRC_MD.read_text())

    geist = fetch_font(GEIST_URL, BUILD / "Geist.ttf")
    mono = fetch_font(MONO_URL, BUILD / "JetBrainsMono.ttf")

    html = build_html(meta, body_md, font_b64(geist), font_b64(mono))
    html_path = BUILD / "prd.html"
    html_path.write_text(html)

    print(f"→ html: {html_path}")
    print(f"→ rendering with Chrome headless …")

    subprocess.run(
        [
            CHROME, "--headless=new", "--disable-gpu",
            "--no-pdf-header-footer",
            "--virtual-time-budget=8000",
            f"--print-to-pdf={OUT_PDF}",
            f"file://{html_path}",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    size_kb = OUT_PDF.stat().st_size // 1024
    print(f"✓ wrote {OUT_PDF.name} ({size_kb} KB)")


if __name__ == "__main__":
    main()
