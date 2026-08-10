"""Part-driven authoring and rendering for the NON-COURT document families.

`author.render_authored` renders exactly one shape — a court cause-title with
numbered "यह कि" grounds, a prayer and a सत्यापन. That shape is correct for a court
filing and wrong for everything else, which is why an application to a police station
came out as a court application. This module is the other renderer.

CONTRACT WITH THE COURT PATH
----------------------------
Nothing here runs for `doctypes.COURT_FILING`. `author.render_authored`,
`author.HOUSE_STYLE`, the canonical templates, the citation guards on the court path
and every existing test keep their exact behaviour. This module is only reached when
the classifier says the document is addressed somewhere other than a court.

WHAT IS SHARED, DELIBERATELY
----------------------------
The safety layer is NOT reimplemented — it is imported from `author`:
  * `_ground_index` / `_mark_grounding` / `_grounding_warnings` — every concrete fact
    is checked against the advocate's own brief and amber-flagged if it is not there.
  * `coverage_warnings` — the mirror duty: a fact the advocate GAVE must appear.
  * `_looks_script_corrupt` / `_strip_cjk` — CJK mojibake safety-net.
Zero-fabrication is a day-1 promise and does not get a second, weaker implementation.

Output shape matches `author.author_document` exactly, so `from_prompt._draft` can
use either interchangeably.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from headnote import config
from headnote.drafter import doctypes as DT
from headnote.drafter.author import (
    _ground_index,
    _grounding_warnings,
    _looks_script_corrupt,
    _mark_grounding,
    _strip_cjk,
    coverage_warnings,
)

log = logging.getLogger(__name__)


def _esc(s: Optional[str]) -> str:
    return "" if s is None else _strip_cjk(str(s)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _lines(v) -> list[str]:
    """Tolerate a model returning a string where the schema asked for a list."""
    if v is None:
        return []
    if isinstance(v, str):
        return [x.strip() for x in v.splitlines() if x.strip()]
    if isinstance(v, (list, tuple)):
        out: list[str] = []
        for item in v:
            if isinstance(item, dict):
                item = item.get("text") or item.get("line") or ""
            s = str(item or "").strip()
            if s:
                out.append(s)
        return out
    return [str(v).strip()] if str(v).strip() else []


# ===========================================================================
# 1) THE SHARED NON-NEGOTIABLES — same promises as the court path, restated for
#    a document that has no court in it.
# ===========================================================================

_UNIVERSAL_RULES = """
ZERO FABRICATION — THE ABSOLUTE RULE (identical to every other Headnote draft):
• Every concrete fact — a name, a relationship, a date, an amount, an FIR / file / receipt
  number, an address, a vehicle or article description, an event — MUST come from what the
  advocate actually gave you. If the advocate did not state it, it does not exist.
• For every value the structure needs but the advocate did not give, write "____". Never a
  guess, never a specimen name like "Ram Kumar", never a plausible date. A draft full of
  ____ is CORRECT and safe; an invented particular is a career-ending fabrication.
• USE THE WHOLE BRIEF — the mirror duty. Every fact the advocate DID give must appear at its
  proper place. Dropping a given fact is as serious as inventing one.
• Do NOT cite case law in this document. An application to an authority, a notice, an
  affidavit and a deed argue on facts and statute, not on judgments. If the advocate needs
  an authority, list it in "cite_at_hearing" — never in the body.
• When the input is thin, WRITE A THIN DOCUMENT. Do not pad it.

LANGUAGE AND SCRIPT:
• Write the ENTIRE document in {lang_name}. ONE SCRIPT THROUGHOUT — a name the advocate typed
  in Roman is transliterated into the target script, and an English fact fragment is rewritten
  in the target language. Dates, numbers, statute sections and reference numbers keep their
  given values exactly.
• Use the register that an actual office in that State would send. Respectful and plain for an
  authority; formal and firm for a notice. Never casual, never Hinglish, never "school essay".

JURISDICTION:
• Draft for the matter's OWN State and district. If the State, district, office or place is
  not stated, write ____ — NEVER default to Madhya Pradesh or any other State.
"""


_SCHEMAS: dict[str, str] = {
    DT.AUTHORITY_APPLICATION: """{
  "lang": "hi" | "en" | "<the language code asked for>",
  "addressee": ["<line 1 — the officer's designation, e.g. 'थाना प्रभारी महोदय,'>",
                "<line 2 — the office, e.g. 'पुलिस थाना ____,'>",
                "<line 3 — place/district; add lines as needed>"],
  "subject": "<one sentence stating exactly what is sought>",
  "reference": "<FIR / file / receipt / prior-letter number and date; \\"\\" if none>",
  "salutation": "<महोदय, / Sir, / the correct form for the language>",
  "body": ["<paragraph 1 — who the applicant is and the background>",
           "<paragraph 2 — what happened, with the advocate's own particulars>",
           "<paragraph 3 — why the relief is sought and under what provision, if any>"],
  "request": "<the निवेदन — 'अतः आपसे निवेदन है कि …' / 'It is therefore requested that …'>",
  "applicant_name": "<the applicant's name, or ____>",
  "applicant_desc": ["<S/o-D/o-W/o, age, occupation>", "<full residence>"],
  "signed_by": "applicant" | "advocate",
  "enclosures": ["<annexure 1>", "<annexure 2>"],
  "companions": ["<any document the applicant must also submit>"],
  "cite_at_hearing": [],
  "warnings": ["<every ____ the advocate must fill; anything you could not complete>"]
}""",

    DT.NOTICE: """{
  "lang": "hi" | "en" | "<the language code asked for>",
  "sender_block": ["<advocate's name>", "<Advocate, <court>>", "<chamber address>", "<phone>"],
  "notice_date": "<date, or __/__/____>",
  "addressee": ["<name of the noticee>", "<full address lines>"],
  "subject": "<one sentence — what the notice is about>",
  "through_clause": "<'Under instructions from and on behalf of my client …' in the target language>",
  "paras": ["<numbered statement of facts, one point per paragraph>"],
  "demand": "<exactly what the noticee must do>",
  "time_limit": "<the period allowed, e.g. '15 दिवस' / '15 days'; ____ if not stated>",
  "consequence": "<what will follow on non-compliance>",
  "advocate_name": "<name, or ____>",
  "enclosures": [],
  "companions": [],
  "cite_at_hearing": [],
  "warnings": []
}""",

    DT.AFFIDAVIT: """{
  "lang": "hi" | "en" | "<the language code asked for>",
  "court_name": "<only if this affidavit is filed in a pending case; \\"\\" otherwise>",
  "case_no": "<only if filed in a pending case; \\"\\" otherwise>",
  "title_line": "<शपथ पत्र / AFFIDAVIT>",
  "deponent_block": "<'मैं, <नाम>, पुत्र श्री <पिता>, आयु ____ वर्ष, निवासी ____, शपथपूर्वक कथन करता/करती हूँ कि —' or the English equivalent>",
  "paras": ["<sworn paragraph 1>", "<sworn paragraph 2>"],
  "verification": "<the verification clause — which paras are on personal knowledge and which on record and belief>",
  "deponent_role": "<शपथकर्ता / Deponent>",
  "attestation": "<'सत्यापित एवं शपथित समक्ष ____' / 'Sworn before me' line; \\"\\" if not required>",
  "companions": [],
  "cite_at_hearing": [],
  "warnings": []
}""",

    DT.DEED: """{
  "lang": "hi" | "en" | "<the language code asked for>",
  "title_line": "<the deed's name, e.g. 'किरायानामा' / 'AGREEMENT TO SELL'>",
  "deed_date": "<date, or __/__/____>",
  "first_party": ["<name>", "<S/o, age, occupation>", "<residence>"],
  "second_party": ["<name>", "<S/o, age, occupation>", "<residence>"],
  "recitals": ["<WHEREAS … / जबकि … — one per paragraph>"],
  "operative": "<'NOW THIS DEED WITNESSETH …' / 'अतः यह विलेख साक्षी है कि …'>",
  "clauses": ["<numbered covenant 1>", "<numbered covenant 2>"],
  "schedule": ["<description of the property or subject-matter; [] if none>"],
  "witnesses": ["1. ____", "2. ____"],
  "companions": [],
  "cite_at_hearing": [],
  "warnings": []
}""",
}


_LANG_NAMES = {"hi": "Hindi", "en": "English", "mr": "Marathi", "gu": "Gujarati",
               "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "kn": "Kannada",
               "ml": "Malayalam", "pa": "Punjabi", "or": "Odia", "as": "Assamese"}


def build_system(family: str, lang: str = "hi", *, forum_name: str = "",
                 style: dict | None = None) -> str:
    """The system prompt for one non-court family: what the document IS, what it
    must NOT carry over from the court shape, its parts in order, and its schema."""
    lang_name = _LANG_NAMES.get((lang or "hi").lower(), "English")
    schema = _SCHEMAS.get(family) or _SCHEMAS[DT.AUTHORITY_APPLICATION]

    head = (
        "You are the drafting engine of Headnote, drafting for an Indian advocate. "
        "Headnote is used across every State and Union Territory.\n\n"
        "THIS DOCUMENT IS NOT A COURT FILING. Ignore every instinct to open with a court "
        "name, a case number, a cause-title or an applicant-versus-respondent block. Those "
        "belong to a pleading and would make this document wrong.\n\n"
        + DT.family_brief(family) + "\n\n"
        "PARTS, IN THIS ORDER:\n" + DT.parts_prompt(family, lang) + "\n"
    )
    if forum_name.strip():
        head += f"\nTHE ADDRESSEE THE ADVOCATE NAMED: {forum_name.strip()}\n"

    tail = (
        _UNIVERSAL_RULES.replace("{lang_name}", lang_name)
        + "\nReturn ONLY valid JSON (no markdown fence), in this exact shape:\n"
        + schema
        + f"\n\nWrite the entire document in {lang_name}."
    )

    system = head + tail

    # The advocate's Draft DNA steers register/vocabulary here exactly as it does on
    # the court path. Format is still enforced downstream by apply_format.
    try:
        from headnote.drafter import style_profile as SP
        overlay = SP.overlay_block(style, lang)
        if overlay:
            system = overlay + system
    except Exception:      # a style overlay must never be able to block a draft
        log.warning("style overlay failed on the parts path", exc_info=True)
    return system


# ===========================================================================
# 2) RENDER — payload → HTML, one branch per family
# ===========================================================================
# Only CSS classes that already exist in templates/_doc_header.HEADER_CSS are used
# (cb-prelude, cb-paras, cb-head, cb-prayer, cb-sig, cb-block-label, cb-witlist, ph,
# mark.fab), plus inline styles for the few left-aligned blocks the court format has
# no class for. That way the non-court families render correctly on every surface
# that already renders a draft, with no CSS to ship.

_L = DT.label

_LEADING_NUM = re.compile(r"^\s*\d+[.)]\s*")

_BLOCK_L = 'style="text-align:left;margin:0 0 3pt;line-height:1.5"'
_BLOCK_L_GAP = 'style="text-align:left;margin:0 0 10pt;line-height:1.5"'


def render_parts(payload: dict, family: str, lang: str = "hi", source: str = "") -> dict:
    """Payload → HTML for a non-court family. Pure and deterministic — no LLM.
    `source` is the advocate's own brief; every concrete fact is grounded against it."""
    p = payload or {}
    warnings = list(p.get("warnings") or [])
    gi = _ground_index(source)
    ung: list[str] = []

    def mk(text) -> str:
        return _mark_grounding(str(text), gi, ung)

    if family == DT.AUTHORITY_APPLICATION:
        html = _render_authority(p, lang, mk)
    elif family == DT.NOTICE:
        html = _render_notice(p, lang, mk)
    elif family == DT.AFFIDAVIT:
        html = _render_affidavit(p, lang, mk)
    elif family == DT.DEED:
        html = _render_deed(p, lang, mk)
    else:
        raise ValueError(f"render_parts called for a family it does not own: {family!r}")

    warnings.extend(_grounding_warnings(ung, lang))
    return {
        "html": html,
        "warnings": warnings,
        "cite_at_hearing": p.get("cite_at_hearing") or [],
        "companions": p.get("companions") or [],
        "needs_affidavit": bool(p.get("needs_affidavit")),
        "ungrounded": list(dict.fromkeys(ung)),
    }


def _sig_pair(lang: str, right_lines: list[str], *, with_place: bool = True) -> str:
    place, date = _L("place", lang), _L("date", lang)
    left = f'<div>{date}: <span class="ph">__/__/____</span></div>'
    if with_place:
        left = f'<div>{place}: <span class="ph">________</span></div>' + left
    right = "".join(f"<div>{_esc(x)}</div>" for x in right_lines if str(x).strip())
    return f'<div class="cb-sig"><div class="l">{left}</div><div class="r">{right}</div></div>'


def _render_authority(p: dict, lang: str, mk) -> str:
    """सेवा में → विषय → संदर्भ → महोदय → prose → निवेदन → applicant's signature → संलग्न.

    No court, no case number, no विरुद्ध, no prayer-to-a-court, no सत्यापन, and — unless
    the advocate is himself the applicant — no 'द्वारा अभिभाषक'.
    """
    out = ['<div class="cb-doc"><div class="doc-body">']

    # --- सेवा में / To,
    out.append(f'<p {_BLOCK_L}>{_esc(_L("to", lang))}</p>')
    addr = _lines(p.get("addressee")) or ["____"]
    for i, line in enumerate(addr):
        style = _BLOCK_L_GAP if i == len(addr) - 1 else _BLOCK_L
        out.append(f'<p {style}>{mk(line)}</p>')

    # --- विषय / Subject  (the one line the officer reads first)
    subject = str(p.get("subject") or "").strip()
    if subject:
        out.append(f'<p {_BLOCK_L_GAP}><strong>{_esc(_L("subject", lang))}:</strong> {mk(subject)}</p>')

    # --- संदर्भ / Reference
    ref = str(p.get("reference") or "").strip()
    if ref:
        out.append(f'<p {_BLOCK_L_GAP}><strong>{_esc(_L("reference", lang))}:</strong> {mk(ref)}</p>')

    # --- महोदय, / Sir,
    sal = str(p.get("salutation") or "").strip() or _L("sir", lang)
    out.append(f'<p {_BLOCK_L_GAP}>{_esc(sal)}</p>')

    # --- body: respectful PROSE, not numbered "यह कि" grounds
    body = _lines(p.get("body"))
    if not body:
        body = ["____"]
    for para in body:
        out.append(f'<p class="cb-prelude">{mk(para)}</p>')

    # --- निवेदन (never a court प्रार्थना)
    request = str(p.get("request") or "").strip()
    if not request:
        request = f'{_L("request_open", lang)} ____ ।'
    out.append(f'<div class="cb-prayer"><p>{mk(request)}</p></div>')

    # --- signature: the APPLICANT signs, over his own name
    signed_by = (p.get("signed_by") or "applicant").strip().lower()
    right = [_L("yours", lang)]
    name = str(p.get("applicant_name") or "").strip()
    right.append(name or "________")
    right.extend(_lines(p.get("applicant_desc")))
    right.append(_L("advocate", lang) if signed_by == "advocate" else _L("applicant", lang))
    out.append(_sig_pair(lang, right))

    # --- संलग्न / Enclosures
    encl = _lines(p.get("enclosures"))
    if encl:
        out.append('<p style="text-align:left;margin:14pt 0 3pt;line-height:1.5">'
                   f'<strong>{_esc(_L("enclosures", lang))}:</strong></p>')
        out.append('<ol class="cb-witlist">')
        for e in encl:
            out.append(f"<li>{mk(e)}</li>")
        out.append("</ol>")

    out.append("</div></div>")
    return "\n".join(out)


def _render_notice(p: dict, lang: str, mk) -> str:
    """Advocate's block → date → addressee → subject → on-instructions → numbered
    facts → demand → consequence → the ADVOCATE's signature."""
    out = ['<div class="cb-doc"><div class="doc-body">']

    sender = _lines(p.get("sender_block"))
    for line in sender:
        out.append(f'<p {_BLOCK_L}>{_esc(line)}</p>')
    if sender:
        out.append("<hr style='border:none;border-top:1px solid #333;margin:8pt 0 12pt'>")

    out.append(f'<div class="cb-block-label">{_esc(_L("legal_notice", lang))}</div>')

    date = str(p.get("notice_date") or "").strip() or "__/__/____"
    out.append(f'<p style="text-align:right;margin:0 0 12pt">{_esc(_L("date", lang))}: {mk(date)}</p>')

    out.append(f'<p {_BLOCK_L}>{_esc(_L("to", lang))}</p>')
    addr = _lines(p.get("addressee")) or ["____"]
    for i, line in enumerate(addr):
        out.append(f'<p {_BLOCK_L_GAP if i == len(addr) - 1 else _BLOCK_L}>{mk(line)}</p>')

    subject = str(p.get("subject") or "").strip()
    if subject:
        out.append(f'<p {_BLOCK_L_GAP}><strong>{_esc(_L("subject", lang))}:</strong> {mk(subject)}</p>')

    through = str(p.get("through_clause") or "").strip()
    if through:
        out.append(f'<p class="cb-prelude">{mk(through)}</p>')

    paras = _lines(p.get("paras"))
    if paras:
        out.append('<ol class="cb-paras">')
        for para in paras:
            out.append(f"<li>{mk(para)}</li>")
        out.append("</ol>")

    demand = str(p.get("demand") or "").strip()
    limit = str(p.get("time_limit") or "").strip()
    consequence = str(p.get("consequence") or "").strip()
    tail = " ".join(x for x in (demand, limit and f"({limit})", consequence) if x)
    if tail.strip():
        out.append(f'<div class="cb-prayer"><p>{mk(tail)}</p></div>')

    out.append(_sig_pair(lang, [str(p.get("advocate_name") or "________"),
                                _L("advocate", lang)]))
    out.append("</div></div>")
    return "\n".join(out)


def _render_affidavit(p: dict, lang: str, mk) -> str:
    """Deponent's own declaration → sworn paras → verification → attestation.
    A cause-title heads it only when the affidavit is filed in a pending case."""
    out = ['<div class="cb-doc"><div class="doc-body">']

    court = str(p.get("court_name") or "").strip()
    if court:
        out.append(f'<p style="text-align:center;font-weight:700;margin:0 0 6pt">{mk(court)}</p>')
        case_no = str(p.get("case_no") or "").strip()
        if case_no:
            out.append(f'<p style="text-align:center;margin:0 0 12pt">{mk(case_no)}</p>')

    title = str(p.get("title_line") or "").strip() or _L("affidavit", lang)
    out.append(f'<div class="cb-block-label">{_esc(title)}</div>')

    deponent = str(p.get("deponent_block") or "").strip()
    if deponent:
        out.append(f'<p class="cb-prelude">{mk(deponent)}</p>')

    paras = _lines(p.get("paras")) or ["____"]
    out.append('<ol class="cb-paras">')
    for para in paras:
        out.append(f"<li>{mk(para)}</li>")
    out.append("</ol>")

    role = str(p.get("deponent_role") or "").strip() or _L("deponent", lang)
    out.append(_sig_pair(lang, [role]))

    verification = str(p.get("verification") or "").strip()
    if verification:
        out.append(f'<div class="cb-block-label">{_esc(_L("verification", lang))}</div>')
        out.append(f'<p class="cb-prelude">{mk(verification)}</p>')
        out.append(_sig_pair(lang, [role], with_place=False))

    attestation = str(p.get("attestation") or "").strip()
    if attestation:
        out.append(f'<p class="cb-prelude" style="margin-top:16pt">{mk(attestation)}</p>')

    out.append("</div></div>")
    return "\n".join(out)


def _render_deed(p: dict, lang: str, mk) -> str:
    """Title → date → first/second party → recitals → operative → clauses →
    schedule → signatures → WITNESSES. Never applicant/respondent, never विरुद्ध."""
    out = ['<div class="cb-doc"><div class="doc-body">']

    title = str(p.get("title_line") or "").strip() or "____"
    out.append(f'<div class="cb-block-label">{_esc(title)}</div>')

    date = str(p.get("deed_date") or "").strip() or "__/__/____"
    out.append(f'<p class="cb-prelude">{_esc(_L("date", lang))}: {mk(date)}</p>')

    for key, lbl in (("first_party", "first_party"), ("second_party", "second_party")):
        desc = _lines(p.get(key))
        if desc:
            out.append(f'<p {_BLOCK_L}><strong>{_esc(_L(lbl, lang))}:</strong></p>')
            for i, line in enumerate(desc):
                out.append(f'<p {_BLOCK_L_GAP if i == len(desc) - 1 else _BLOCK_L}>{mk(line)}</p>')

    for recital in _lines(p.get("recitals")):
        out.append(f'<p class="cb-prelude">{mk(recital)}</p>')

    operative = str(p.get("operative") or "").strip()
    if operative:
        out.append(f'<p class="cb-prelude" style="font-weight:600">{mk(operative)}</p>')

    clauses = _lines(p.get("clauses")) or ["____"]
    out.append('<ol class="cb-paras">')
    for clause in clauses:
        out.append(f"<li>{mk(clause)}</li>")
    out.append("</ol>")

    schedule = _lines(p.get("schedule"))
    if schedule:
        out.append(f'<div class="cb-block-label">{_esc(_L("schedule", lang))}</div>')
        for line in schedule:
            out.append(f'<p class="cb-prelude">{mk(line)}</p>')

    out.append('<div class="cb-sig" style="margin-top:24pt">'
               f'<div class="l"><div>{_esc(_L("first_party", lang))}</div>'
               '<div><span class="ph">________</span></div></div>'
               f'<div class="r"><div>{_esc(_L("second_party", lang))}</div>'
               '<div><span class="ph">________</span></div></div></div>')

    # a deed without witnesses is a defective deed — always emitted
    out.append(f'<div class="cb-block-label">{_esc(_L("witnesses", lang))}</div>')
    out.append('<ol class="cb-witlist">')
    for w in (_lines(p.get("witnesses")) or ["____", "____"]):
        # the <ol> supplies the number — strip one the model may have written in
        out.append("<li>" + _esc(_LEADING_NUM.sub("", w)) + "</li>")
    out.append("</ol>")

    out.append("</div></div>")
    return "\n".join(out)


# ===========================================================================
# 3) DRAFT DNA BLOCKS — the same document as role-tagged text, so the advocate's
#    own captured layout renders the .docx (Canvas and .docx must be one document)
# ===========================================================================
# Roles reuse `layout_template.ROLES` wherever the semantics genuinely match, so a
# captured template's own formatting still applies. The six that have no court
# equivalent (addressee, subject, reference, salutation, enclosures, witness) are
# added to `layout_template.standard_template` as RENDER base formats only — the
# CAPTURE vocabulary is untouched, so reading an advocate's .docx is unchanged.

def blocks_from_parts(payload: dict, family: str, lang: str = "hi") -> list[tuple]:
    p = payload or {}
    out: list[tuple] = []

    def add(role: str, text) -> None:
        s = str(text or "").strip()
        if s:
            out.append((role, s))

    if family == DT.AUTHORITY_APPLICATION:
        add("addressee", _L("to", lang))
        for line in _lines(p.get("addressee")):
            add("addressee", line)
        if str(p.get("subject") or "").strip():
            add("subject", f'{_L("subject", lang)}: {p["subject"]}')
        if str(p.get("reference") or "").strip():
            add("reference", f'{_L("reference", lang)}: {p["reference"]}')
        add("salutation", p.get("salutation") or _L("sir", lang))
        for para in _lines(p.get("body")):
            add("intro", para)
        add("prayer", p.get("request"))
        add("dateline", f'{_L("place", lang)}: ________    {_L("date", lang)}: __/__/____')
        add("sig_party", _L("yours", lang))
        add("advocate", p.get("applicant_name") or "________")
        for line in _lines(p.get("applicant_desc")):
            add("advocate", line)
        signed_by = (p.get("signed_by") or "applicant").strip().lower()
        add("sig_by", _L("advocate", lang) if signed_by == "advocate" else _L("applicant", lang))
        encl = _lines(p.get("enclosures"))
        if encl:
            add("enclosures", f'{_L("enclosures", lang)}:')
            for i, e in enumerate(encl, 1):
                add("enclosures", f"{i}. {e}")

    elif family == DT.NOTICE:
        for line in _lines(p.get("sender_block")):
            add("addressee", line)
        add("section_heading", _L("legal_notice", lang))
        add("dateline", f'{_L("date", lang)}: {p.get("notice_date") or "__/__/____"}')
        add("addressee", _L("to", lang))
        for line in _lines(p.get("addressee")):
            add("addressee", line)
        if str(p.get("subject") or "").strip():
            add("subject", f'{_L("subject", lang)}: {p["subject"]}')
        add("intro", p.get("through_clause"))
        for i, para in enumerate(_lines(p.get("paras")), 1):
            add("ground", f"{i}. {para}")
        tail = " ".join(x for x in (str(p.get("demand") or ""), str(p.get("time_limit") or ""),
                                    str(p.get("consequence") or "")) if x.strip())
        add("prayer", tail)
        add("sig_party", p.get("advocate_name") or "________")
        add("sig_by", _L("advocate", lang))

    elif family == DT.AFFIDAVIT:
        add("court", p.get("court_name"))
        add("caseno", p.get("case_no"))
        add("section_heading", p.get("title_line") or _L("affidavit", lang))
        add("intro", p.get("deponent_block"))
        for i, para in enumerate(_lines(p.get("paras")), 1):
            add("ground", f"{i}. {para}")
        role = p.get("deponent_role") or _L("deponent", lang)
        add("dateline", f'{_L("place", lang)}: ________    {_L("date", lang)}: __/__/____')
        add("sig_party", role)
        if str(p.get("verification") or "").strip():
            add("section_heading", _L("verification", lang))
            add("intro", p.get("verification"))
            add("sig_party", role)
        add("intro", p.get("attestation"))

    elif family == DT.DEED:
        add("section_heading", p.get("title_line"))
        add("dateline", f'{_L("date", lang)}: {p.get("deed_date") or "__/__/____"}')
        for key, lbl in (("first_party", "first_party"), ("second_party", "second_party")):
            desc = _lines(p.get(key))
            if desc:
                add("applicant", f'{_L(lbl, lang)}:')
                for line in desc:
                    add("applicant", line)
        for recital in _lines(p.get("recitals")):
            add("intro", recital)
        add("intro", p.get("operative"))
        for i, clause in enumerate(_lines(p.get("clauses")), 1):
            add("ground", f"{i}. {clause}")
        schedule = _lines(p.get("schedule"))
        if schedule:
            add("section_heading", _L("schedule", lang))
            for line in schedule:
                add("intro", line)
        add("sig_party", f'{_L("first_party", lang)}  ________')
        add("sig_party", f'{_L("second_party", lang)}  ________')
        add("section_heading", _L("witnesses", lang))
        for w in (_lines(p.get("witnesses")) or ["____", "____"]):
            add("witness", w)

    return out


# ===========================================================================
# 4) THE FLOOR — a deterministic, zero-LLM document per family.
# ===========================================================================
# `from_prompt._last_resort` emits a COURT skeleton (न्यायालय ____ / यह कि ____ /
# प्रार्थना). Falling back to that for a police-station application would reproduce
# the exact bug this module exists to fix, so each family gets its own floor.

def floor_payload(family: str, lang: str, matter: str = "") -> dict:
    """The correct empty shape for this family, with the advocate's own words kept
    verbatim as drafting notes. Zero LLM — this must work when everything is down."""
    note = (matter or "").strip()
    if family == DT.AUTHORITY_APPLICATION:
        return {
            "addressee": ["____", "____"],
            "subject": "____",
            "reference": "",
            "salutation": _L("sir", lang),
            "body": [note] if note else ["____"],
            "request": f'{_L("request_open", lang)} ____ ।',
            "applicant_name": "____",
            "applicant_desc": [],
            "signed_by": "applicant",
            "enclosures": [],
            "warnings": [],
        }
    if family == DT.NOTICE:
        return {
            "sender_block": ["____"], "notice_date": "__/__/____",
            "addressee": ["____"], "subject": "____", "through_clause": "____",
            "paras": [note] if note else ["____"], "demand": "____",
            "time_limit": "____", "consequence": "____", "advocate_name": "____",
            "warnings": [],
        }
    if family == DT.AFFIDAVIT:
        return {
            "title_line": _L("affidavit", lang), "deponent_block": "____",
            "paras": [note] if note else ["____"], "verification": "____",
            "deponent_role": _L("deponent", lang), "warnings": [],
        }
    if family == DT.DEED:
        return {
            "title_line": "____", "deed_date": "__/__/____",
            "first_party": ["____"], "second_party": ["____"],
            "recitals": [note] if note else ["____"], "operative": "____",
            "clauses": ["____"], "witnesses": ["____", "____"], "warnings": [],
        }
    raise ValueError(f"no floor for family {family!r}")


# ===========================================================================
# 5) END-TO-END
# ===========================================================================

def author_parts_document(matter: str, family: str, lang: str = "hi", *,
                          doc_type: str = "", forum_name: str = "",
                          style: dict | None = None) -> dict:
    """prompt → payload (LLM) → grounded → HTML + DNA blocks.

    Same return shape as `author.author_document`, so `from_prompt` treats the two
    interchangeably. Raises on LLM/parse failure; the caller falls back to
    `floor_payload` for THIS family — never to the court skeleton.
    """
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response

    system = build_system(family, lang, forum_name=forum_name, style=style)
    user = (
        "THE MATTER (the advocate's instructions and facts — the ONLY source of facts; "
        f"write ____ wherever it is silent):\n{(matter or '').strip() or '(nothing typed)'}\n\n"
        f"Draft the document now, as JSON per the schema, in "
        f"{_LANG_NAMES.get((lang or 'hi').lower(), 'English')}."
    )
    try:
        raw, meta = _call_deepseek_or_groq(system, user, max_tokens=9000,
                                           claude_model=config.DRAFTER_AUTHOR_MODEL,
                                           json_mode=True)
        if _looks_script_corrupt(raw):
            raise ValueError("parts output script-corrupt (CJK) — re-generating")
        payload = parse_json_response(raw)
    except Exception:
        # Same slim retry as the court path: the fallback tier 413s on a long prompt,
        # and a fresh roll usually lands. Every guard below still applies.
        log.warning("parts authoring first pass failed; retrying slim", exc_info=True)
        slim = build_system(family, lang, forum_name=forum_name)
        raw, meta = _call_deepseek_or_groq(slim, user, max_tokens=9000,
                                           claude_model=config.DRAFTER_AUTHOR_MODEL,
                                           json_mode=True)
        payload = parse_json_response(raw)

    if not isinstance(payload, dict):
        raise ValueError("parts payload is not an object")

    rendered = render_parts(payload, family, lang, source=matter)
    # the mirror duty — everything concrete the advocate GAVE must be in the draft
    rendered["warnings"].extend(coverage_warnings(matter, rendered["html"], lang))

    return {
        "ok": True,
        "mode": "authored",
        "family": family,
        "doc_type": doc_type or family,
        "lang": lang,
        "html": rendered["html"],
        "cite_at_hearing": rendered["cite_at_hearing"],
        "companions": rendered["companions"],
        "needs_affidavit": rendered["needs_affidavit"],
        "warnings": rendered["warnings"],
        "ungrounded": rendered.get("ungrounded") or [],
        "title": str(payload.get("subject") or payload.get("title_line") or "").strip(),
        "meta": meta if isinstance(meta, dict) else None,
        "blocks": blocks_from_parts(payload, family, lang),
    }


def floor_document(family: str, lang: str, matter: str = "") -> dict:
    """The never-fail floor for a non-court family — correct shape, no LLM."""
    payload = floor_payload(family, lang, matter)
    rendered = render_parts(payload, family, lang, source=matter)
    return {
        "ok": True,
        "mode": "skeleton",
        "family": family,
        "doc_type": family,
        "lang": lang,
        "html": rendered["html"],
        "cite_at_hearing": [],
        "companions": [],
        "needs_affidavit": False,
        "warnings": rendered["warnings"],
        "ungrounded": [],
        "title": "",
        "meta": None,
        "blocks": blocks_from_parts(payload, family, lang),
    }
