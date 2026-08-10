"""Proof: a lawyer's natural-language prompt → STRUCTURED PATCH → deterministic re-render.
Writes .preview_tmp/reviews/tweak.html (before → prompt → after) for visual review.

Run:  venv/bin/python scripts/demo_prompt_tweak.py
"""
import copy
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from headnote.drafter.templates import bail
from headnote.drafter.templates._doc_header import HEADER_CSS, _FIT_SCRIPT
from headnote.drafter.prompt_tweak import parse_heuristic, apply_patch

# --- the lawyer's situation: a base HC bail draft already on screen --------------
base = copy.deepcopy(bail.SAMPLE_HC)
spec = bail.field_spec("hc", "regular")

# --- the lawyer types a plain-language tweak (English instruction + Hindi clause) -
PROMPT = ("Applicant is the sole breadwinner of his family and the alleged offence is "
          "punishable with imprisonment up to 7 years, so apply Arnesh Kumar. "
          "Add a ground that: आवेदक का कोई पूर्ववृत्त आपराधिक प्रकरण नहीं है एवं वह "
          "विवेचना में सहयोग हेतु सदैव तत्पर है।")

# --- intent-router (heuristic offline path; production = DeepSeek ROUTER_SYSTEM) --
patch = parse_heuristic(PROMPT, spec)
after, log = apply_patch(base, patch, spec)

# --- deterministic re-render: before vs after ------------------------------------
before_doc = bail.render_hi(base)
after_doc = bail.render_hi(after)

print("PROMPT:", PROMPT)
print("PATCH :", json.dumps(patch, ensure_ascii=False))
print("LOG   :", log)
print("grounds before:", base.get("grounds"))
print("grounds after :", after.get("grounds"))
print("custom after  :", after.get("custom_grounds"))

# --- build the review page -------------------------------------------------------
patch_json = html.escape(json.dumps(patch, ensure_ascii=False, indent=2))
log_items = "".join(f"<li>{html.escape(x)}</li>" for x in log)

panel = f"""
<div class="tw">
  <div class="tw-row">
    <div class="tw-col">
      <div class="tw-lbl">लॉयर का प्रॉम्प्ट · the lawyer types</div>
      <div class="bubble">{html.escape(PROMPT)}</div>
    </div>
    <div class="tw-col">
      <div class="tw-lbl">→ संरचित पैच (LLM केवल knobs घुमाता है · no free text)</div>
      <pre class="patch">{patch_json}</pre>
    </div>
  </div>
  <div class="tw-lbl" style="margin-top:10px">परिवर्तन-लॉग · changelog (advocate-review)</div>
  <ul class="log">{log_items}</ul>
  <div class="cap">boilerplate · fixed grounds · sections · citations = अपरिवर्तित (template/verified). प्रॉम्प्ट केवल: field values · reviewed-ground toggles · variant · अधिवक्ता-जोड़ा आधार (flagged)।</div>
</div>
"""

CSS = """
.tw{max-width:210mm;margin:0 auto 22px;font-family:system-ui,sans-serif;background:#fff;
  border:1px solid #d9d3c5;border-radius:10px;padding:16px 18px;box-shadow:0 6px 20px rgba(0,0,0,.07)}
.tw-row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:760px){.tw-row{grid-template-columns:1fr}}
.tw-lbl{font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:#a85e16;font-weight:700;margin-bottom:5px}
.bubble{background:#F4842E;color:#fff;border-radius:12px 12px 12px 3px;padding:11px 13px;font-size:14px;line-height:1.55}
.patch{background:#1a1814;color:#e7e3d8;border-radius:8px;padding:11px 13px;font-size:12px;line-height:1.5;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;margin:0;overflow:auto}
.patch{tab-size:2}
.log{margin:4px 0 0;padding-left:18px;font-size:13px;color:#2c6e34;line-height:1.7}
.log li{font-family:ui-monospace,monospace;font-size:12.5px}
.cap{margin-top:11px;font-size:12px;color:#6a655a;border-top:1px dashed #ddd6c6;padding-top:9px;line-height:1.5}
.sheet-lbl{max-width:210mm;margin:0 auto 6px;font-family:system-ui,sans-serif;font-size:12px;font-weight:700;
  letter-spacing:.05em;text-transform:uppercase}
.sheet-lbl.before{color:#9a8d6a}.sheet-lbl.after{color:#2c6e34}
"""

banner = "प्रॉम्प्ट-आधारित ट्वीक — natural language → structured patch → deterministic re-render (HC जमानत · reviewed: false)"
page = (
    '<!doctype html><html lang="hi"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<title>Headnote — प्रॉम्प्ट ट्वीक (proof)</title>'
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;700&display=swap" rel="stylesheet">'
    '<style>*{box-sizing:border-box}body{margin:0;background:#cdccc6;padding:24px 0}'
    + HEADER_CSS + CSS +
    '.rb{max-width:210mm;margin:0 auto 16px;font-family:system-ui,sans-serif;font-size:12.5px;'
    'line-height:1.5;color:#3a3730;background:#fdf6e3;border:1px solid #e3d9bd;padding:8px 12px;border-radius:6px}'
    '.doc-a4{margin-bottom:24px}</style></head><body>'
    + f'<div class="rb">{banner}</div>'
    + panel
    + '<div class="sheet-lbl before">पहले · before</div>'
    + f'<div class="doc-a4">{before_doc}</div>'
    + '<div class="sheet-lbl after">बाद में · after (प्रॉम्प्ट लागू)</div>'
    + f'<div class="doc-a4">{after_doc}</div>'
    + _FIT_SCRIPT +
    '</body></html>'
)

out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   ".preview_tmp", "reviews", "tweak.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(page)
print("wrote", out, len(page), "bytes")
