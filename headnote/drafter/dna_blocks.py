"""Draft DNA — the seam between the drafting brain and the advocate's own layout.

Draft DNA can reproduce an advocate's exact page geometry, indents and font
(`layout_template.render_into_layout`), but it consumes **role-tagged blocks**,
while the authoring engine produced only HTML. That mismatch is why DNA was
unreachable from drafting. This module closes it.

The conversion is deterministic and works off the AUTHORED PAYLOAD — the typed
dict the drafting brain returns (`author.author_payload`) — not off the rendered
HTML. That matters for three reasons:

  • the payload is already structured (court_name, applicant_desc, paras[…],
    prayer, …), so there is nothing to parse and nothing to guess;
  • its text is RAW. The HTML render escapes entities and injects grounding
    markers (`<span class="ung">`) and citation flags; none of that must ever
    reach a .docx the advocate files;
  • no LLM is involved, so this adds no cost, no latency and no failure mode.

Block order here MUST track `author.render_authored` / `render_header`, so the
.docx and the on-screen draft are the same document. When you change the order of
one, change the other.

Scope: the AUTHORED path only — which is where nearly all traffic goes since
routing flipped to authored-primary (2026-07-06). Deliberately NOT handled:
  • mirrored drafts — an attached reference outranks the saved profile, so a
    mirrored draft must keep the reference's format, not the advocate's profile.
    Rendering those into the reference's own captured geometry is the next step.
  • canonical templates — they already have a native .docx path
    (`/api/draft/render-docx`).
"""
from __future__ import annotations

import html as _html
import re

# roles are defined by layout_template.ROLES — kept in sync by test
_TAG = re.compile(r"<[^>]+>")

# ---------------------------------------------------------------------------
# Labels for the blocks WE inject (the ones the drafting brain doesn't author):
# place/date line, "through counsel", the advocate line, the attestation heading.
#
# These must never default to Hindi. Headnote is for every Indian advocate, and a
# Marathi or Tamil filing carrying a Hindi सत्यापन heading is a defective document.
# Resolution order, per label:
#   1. the payload, when the drafting brain supplied it (it authored in-language)
#   2. the reviewed court glossary (headnote.drafter.i18n.glossary) for hi/mr/bn/gu
#   3. English — deliberately, NOT Hindi: for a language we cannot render correctly,
#      English is neutral and every Indian advocate reads it; Hindi would be wrong.
# ---------------------------------------------------------------------------
_EN = {"place": "Place", "date": "Date", "through": "Through Counsel",
       "advocate": "Advocate", "verification": "VERIFICATION",
       "applicant": "Applicant", "respondent": "Respondent", "versus": "Versus"}

# the Hindi court term each label maps to — the glossary's key
_HI = {"place": "स्थान", "date": "दिनांक", "through": "द्वारा अभिभाषक",
       "advocate": "एडवोकेट", "verification": "सत्यापन",
       "applicant": "आवेदक", "respondent": "अनावेदक", "versus": "विरुद्ध"}


def labels(lang: str) -> dict:
    """The injected-block vocabulary for `lang`. Falls back to English, never Hindi."""
    code = (lang or "en").strip().lower()[:2]
    if code == "hi":
        return dict(_HI)
    if code == "en":
        return dict(_EN)
    try:
        from headnote.drafter.i18n import glossary as _g
        terms = _g.TERMS
    except Exception:
        return dict(_EN)
    out = {}
    for key, hi_term in _HI.items():
        pinned = ((terms.get(hi_term) or {}).get(code) or "").strip()
        # an unpinned cell means no advocate has confirmed that word in this
        # language — emit English rather than guess, and never emit Hindi
        out[key] = pinned or _EN[key]
    return out


def _plain(s) -> str:
    """Descriptor lines may carry markup (`<u>…</u>` for underlined place-values)
    and HTML entities. A .docx wants neither."""
    if s is None:
        return ""
    return _html.unescape(_TAG.sub("", str(s))).strip()


def _case_line(p: dict) -> str:
    """Mirror `_doc_header.render_header`'s case line: "<code>– <no> / <year> [suffix]"."""
    code = _plain(p.get("case_code"))
    no = _plain(p.get("case_number")) or "      "
    year = _plain(p.get("case_year"))
    line = f"{code}– {no} / {year}".strip()
    suffix = _plain(p.get("case_suffix"))
    return f"{line} {suffix}".strip() if suffix else line


def from_authored(p: dict, lang: str = "hi", *, number_grounds: bool = True) -> list[tuple]:
    """Authored payload → [(role, text), …] for `layout_template.render_into_layout`.

    `number_grounds` prefixes the numbered body paragraphs ("1. ", "2. "…) to match
    the `<ol>` the HTML render emits. Word list-numbering is not part of a captured
    role format, so without this the numbers would simply be lost.

    Language-neutral: every word we inject comes from `labels(lang)`, and every word
    of substance comes from the payload the drafting brain authored in the advocate's
    own language. Works for hi/en/mr/bn/gu today and for any language the brain can
    draft in, without a code change.
    """
    p = p or {}
    L = labels(lang)
    out: list[tuple] = []

    def add(role: str, text) -> None:
        t = _plain(text)
        if t:
            out.append((role, t))

    # ---- header (order per render_header) ----
    add("side_label", p.get("side_label"))
    add("court", p.get("court_name"))
    add("caseno", _case_line(p))

    # party blocks: the designation line, then each descriptor line, each in the
    # advocate's captured cause-title format
    add("applicant", f'{_plain(p.get("applicant_label")) or L["applicant"]} ——')
    for line in (p.get("applicant_desc") or []):
        add("applicant", line)
    add("versus", p.get("versus") or L["versus"])
    add("respondent", f'{_plain(p.get("respondent_label")) or L["respondent"]} ——')
    for line in (p.get("respondent_desc") or []):
        add("respondent", line)
    add("section_heading", p.get("title_line"))

    # ---- body ----
    for pre in (p.get("prelude") or []):
        add("intro", pre)
    add("intro", p.get("salutation"))

    n = 0
    for item in (p.get("paras") or []):
        if not isinstance(item, dict):
            item = {"kind": "ground", "text": item}
        text = _plain(item.get("text"))
        if not text:
            continue
        # a heading inside the body does not advance the number (matches render_authored)
        if (item.get("kind") or "ground") == "head":
            add("ground_head", text)
            continue
        n += 1
        add("ground", f"{n}. {text}" if number_grounds else text)

    add("prayer", p.get("prayer"))

    # ---- signature block ----
    add("dateline", f'{_plain(p.get("place_label")) or L["place"]}: ________')
    add("dateline", f'{_plain(p.get("date_label")) or L["date"]}: __/__/____')
    role = _plain(p.get("signatory_role")) or L["applicant"]
    add("sig_party", role)
    add("sig_by", _plain(p.get("through_label")) or L["through"])
    add("advocate", f'(________) — {_plain(p.get("advocate_label")) or L["advocate"]}')

    # ---- the attestation block, where facts are sworn ----
    if p.get("needs_verification"):
        add("section_heading", _plain(p.get("verification_label")) or L["verification"])
        add("intro", p.get("verification"))
        add("dateline", f'{_plain(p.get("date_label")) or L["date"]}: __/__/____')
        add("sig_party", role)

    return out


def is_empty(blocks) -> bool:
    """A block list with no body is not worth rendering into a .docx."""
    return not any(r in ("ground", "prayer") for r, _ in (blocks or []))
