"""
Native EN + HI templates for the Friendly Cash Loan §138 NI Act complaint.

This is a STUB. The full templates are 60+ lines of legal Hindi prose each
(see static/drafter.html lines 1118-1242 in the v3 prototype). Porting
them verbatim is the next session — requires sitting with the senior
advocate to validate each clause survives translation from JS f-strings
to Python f-strings unchanged.

For now: returns a structured placeholder showing the schema we'll fill.
This lets the API endpoints land + the FE integrate while we do the
careful template port one paragraph at a time.

To 'go live':
  1. Port friendlyCashLoanEN from static/drafter.html → render_en here
  2. Port friendlyCashLoanHI similarly → render_hi here
  3. In stories.py set STORIES['friendly_cash_loan'].ready = True
  4. Bump template_version = 2 (so saved drafts pin to v1 = stub
     and any drafts created post-go-live pin to v2 = real)
"""

from __future__ import annotations

from headnote.drafter.transliterate import xlit


def _tx(text: str, lang: str) -> str:
    """Transliterate a user-typed field, wrap in xlit span if changed.
    Same semantics as the JS prototype's tx() helper."""
    if not text:
        return ""
    rendered, was_xlit = xlit(text, lang)
    if was_xlit:
        return f'<span class="xlit">{rendered}</span>'
    return rendered


def _ph(en: str, hi: str, lang: str) -> str:
    return f'<span class="placeholder">{hi if lang == "hi" else en}</span>'


def render_en(a: dict) -> str:
    """English §138 NI Act complaint. STUB — the real template is being
    ported from the v3 prototype after a final lawyer review pass."""
    return _render_stub(a, "en")


def render_hi(a: dict) -> str:
    """Hindi §138 NI Act complaint. STUB — the real template is being
    ported from the v3 prototype after a final lawyer review pass."""
    return _render_stub(a, "hi")


def _render_stub(a: dict, lang: str) -> str:
    """Minimal placeholder showing the answers we collected. Lets the
    FE wire up the preview pane without waiting for the full template.

    Real template will replace this with the multi-paragraph complaint
    matching the v3 prototype output exactly."""
    items = []
    for k, v in (a or {}).items():
        if not v or k.startswith("__"):
            continue
        if isinstance(v, str):
            items.append(f"<li><b>{k}:</b> {_tx(v, lang)}</li>")
        else:
            items.append(f"<li><b>{k}:</b> {v}</li>")
    body = "<ul>" + "".join(items) + "</ul>" if items else "<p>(no answers yet)</p>"

    header = (
        "<div class='doc-head'>FRIENDLY CASH LOAN COMPLAINT (DRAFT PREVIEW · TEMPLATE NOT YET LIVE)</div>"
        if lang == "en"
        else "<div class='doc-head'>मित्रवत नकद ऋण परिवाद (प्रारूप पूर्वावलोकन · टेम्पलेट जल्द)</div>"
    )
    footer = (
        "<p><i>The full template — including all 8 paragraphs, "
        "evidence list, prayer, and verification — will be rendered here "
        "once the lawyer review pass is complete. The fields you fill in "
        "today are saved and will populate the real template automatically.</i></p>"
        if lang == "en"
        else "<p><i>पूर्ण प्रारूप — सभी 8 अनुच्छेद, साक्ष्य सूची, प्रार्थना, "
             "और सत्यापन सहित — अधिवक्ता समीक्षा पूर्ण होने पर यहाँ प्रदर्शित होगा। "
             "आज भरी गयी फ़ील्ड्स सहेज ली गयी हैं।</i></p>"
    )
    return header + body + footer
