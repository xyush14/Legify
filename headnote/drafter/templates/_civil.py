"""Shared deterministic CIVIL PLAINT engine (CPC Order VII structure).

Every Indian civil plaint shares ONE skeleton — cause-title, parties, the
type-specific facts, cause of action, jurisdiction, valuation & court-fee,
limitation, a lettered PRAYER (सहायता), and verification (Order VI Rule 15).
Each suit module (recovery / injunction / specific-performance / declaration /
partition / eviction / consumer / written-statement) supplies ONLY its statute,
its fact paragraphs and its prayer clauses; this engine assembles the rest,
bilingual, DETERMINISTICALLY — no LLM writes a word, so nothing is fabricated:
facts come from the advocate's fields and any blank renders as a ____ placeholder.
The cause-title is pan-India via compose_court_name (State → the right forum).

A suit CFG is a dict:
  key, label_hi, label_en, court ("civil"|"consumer"|"district_judge"),
  section_hi, section_en           # statute line under the title
  title_hi, title_en               # e.g. "धन वसूली हेतु वाद-पत्र"
  p_label_hi/p_label_en            # plaintiff-side label (वादी / परिवादी / प्रतिवादी-for-WS)
  d_label_hi/d_label_en            # defendant-side label (प्रतिवादी / अनावेदकगण)
  facts(a, lang, H) -> [str]       # the type-specific numbered paras
  tail(a, lang, H) -> [str] | None # standard CPC tail; use civil_tail for plaints
  prayer(a, lang, H) -> [str]      # the substantive relief clauses (costs+residual auto-added)
  needs_affidavit (bool)           # consumer complaints etc.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

_HI_LETTERS = ["अ", "ब", "स", "द", "इ", "ई", "उ", "ऊ", "ए", "ऐ"]


# --------------------------------------------------------------- helpers (H)
def esc(s: Optional[str]) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ph(s: Optional[str], p: str = "________") -> str:
    if s is not None and str(s).strip():
        return esc(s)
    return f'<span class="ph">{p}</span>'


def secs(sections, sep=" एवं ") -> str:
    if isinstance(sections, (list, tuple)):
        return sep.join(esc(x) for x in sections if str(x).strip()) or "________"
    return esc(sections) if sections and str(sections).strip() else "________"


class _H:
    esc = staticmethod(esc)
    ph = staticmethod(ph)
    secs = staticmethod(secs)


H = _H()


def _val(a, key, en=False):
    """Prefer *_en value on the English render, fall back to the entered value."""
    if en:
        v = a.get(key + "_en")
        if v is not None and str(v).strip():
            return v
    return a.get(key)


# --------------------------------------------------------------- court + parties
def _court_level(a, cfg):
    return a.get("court") or cfg.get("court") or "civil"


def _court_name(a, cfg, lang):
    hi = lang == "hi"
    key = "court_name" if hi else "court_name_en"
    if a.get(key):
        return a[key]
    if a.get("court_name"):
        return a["court_name"]
    return compose_court_name(_court_level(a, cfg), a.get("court_city") or "",
                              _val(a, "state_name", not hi) or "", lang=lang)


def _party_desc(name, father, addr, hi):
    """Two/three-line party descriptor for the cause-title (blanks → placeholders)."""
    lines = [ph(name, "नाम" if hi else "name")]
    rel = (father or "").strip()
    if rel:
        lines.append(esc(rel))
    lbl = "निवासी— " if hi else "R/o "
    lines.append(lbl + ph(addr, "पता" if hi else "address"))
    return lines


# --------------------------------------------------------------- the standard CPC tail
def civil_tail(a, lang, _H_, *, jurisdiction_hi="वाद-हेतुक एवं वादग्रस्त विषय-वस्तु",
               jurisdiction_en="the cause of action and the subject-matter of the suit"):
    """CoA · jurisdiction · valuation & court-fee · limitation — the four paras
    every plaint must carry (Order VII Rules 1, 10-11; §§15-20 CPC)."""
    hi = lang == "hi"
    coa_date = ph(a.get("cause_of_action_date"), "दिनांक" if hi else "date")
    coa_place = ph(_val(a, "cause_of_action_place", not hi), "स्थान" if hi else "place")
    val = ph(_val(a, "valuation", not hi), "________")
    fee = ph(_val(a, "court_fee", not hi), "________")
    if hi:
        return [
            f'यह कि प्रस्तुत वाद का कारण दिनांक {coa_date} को {coa_place} में उत्पन्न हुआ तथा '
            f'निरन्तर बना हुआ है; सम्पूर्ण वाद-हेतुक इस माननीय न्यायालय की प्रादेशिक अधिकारिता के '
            f'अन्तर्गत उत्पन्न हुआ है।',
            f'यह कि {jurisdiction_hi} इस माननीय न्यायालय की प्रादेशिक एवं आर्थिक अधिकारिता के '
            f'अन्तर्गत आता है, अतः यह न्यायालय प्रस्तुत वाद की सुनवाई एवं विनिश्चय हेतु सक्षम है।',
            f'यह कि प्रस्तुत वाद का मूल्यांकन अधिकारिता एवं न्यायशुल्क हेतु {val} रुपये किया जाकर '
            f'उस पर देय न्यायशुल्क {fee} रुपये अदा किया गया है।',
            'यह कि प्रस्तुत वाद परिसीमा अधिनियम, 1963 द्वारा निर्धारित अवधि के भीतर, समय-सीमा में '
            'संस्थित किया जा रहा है।',
        ]
    return [
        f'That the cause of action for the present suit first arose on {coa_date} at {coa_place} and '
        f'continues to subsist; the entire cause of action has arisen within the territorial '
        f'jurisdiction of this Hon\'ble Court.',
        f'That {jurisdiction_en} falls within the territorial and pecuniary jurisdiction of this '
        f'Hon\'ble Court, which is therefore competent to try and determine the present suit.',
        f'That the suit has been valued for the purposes of jurisdiction and court fee at Rs. {val}, '
        f'on which the requisite court fee of Rs. {fee} has been paid.',
        'That the present suit is being instituted well within the period of limitation prescribed '
        'by the Limitation Act, 1963.',
    ]


# --------------------------------------------------------------- verification + signature
def _verification(a, lang, plabel):
    hi = lang == "hi"
    d = ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))
    place = ph(_val(a, "cause_of_action_place", not hi), "स्थान" if hi else "place")
    if hi:
        return (
            f'सत्यापित किया जाता है कि प्रस्तुत वाद-पत्र की कण्डिका 1 लगायत ____ के कथन मेरी व्यक्तिगत '
            f'जानकारी एवं अभिलेख के आधार पर सत्य एवं सही हैं तथा शेष कण्डिकाएँ विधिक सलाह पर आधारित हैं '
            f'जिन्हें मैं सत्य मानता/मानती हूँ; इनमें कुछ भी असत्य नहीं है और न ही कुछ छिपाया गया है। '
            f'आज दिनांक {d} को {place} पर सत्यापित किया गया।')
    return (
        f'Verified that the contents of paragraphs 1 to ____ of the plaint are true and correct to my '
        f'personal knowledge and the record, and the remaining paragraphs are based on legal advice '
        f'which I believe to be true; nothing material has been concealed. Verified at {place} on '
        f'this {d}.')


# --------------------------------------------------------------- the engine
def render(a: dict, lang: str, cfg: dict) -> str:
    a = a or {}
    hi = lang == "hi"
    court_name = _court_name(a, cfg, lang)
    p_label = cfg["p_label_hi"] if hi else cfg["p_label_en"]
    d_label = cfg["d_label_hi"] if hi else cfg["d_label_en"]

    p_desc = _party_desc(_val(a, "plaintiff_name", not hi), _val(a, "plaintiff_father", not hi),
                         _val(a, "plaintiff_address", not hi), hi)
    d_desc = _party_desc(_val(a, "defendant_name", not hi), _val(a, "defendant_father", not hi),
                         _val(a, "defendant_address", not hi), hi)

    case_code = cfg.get("case_code_hi" if hi else "case_code_en") or ("व्यवहार वाद क्रमांक" if hi else "Civil Suit No.")
    hdr = render_header({
        "side_label": "",
        "court_name": court_name,
        "case_code": case_code,
        "case_number": a.get("suit_number") or "",
        "case_year": a.get("suit_year") or str(date.today().year),
        "applicant_label": p_label, "applicant_desc": p_desc,
        "respondent_label": d_label, "respondent_desc": d_desc,
        "versus": "बनाम" if hi else "Versus",
        "title_line": (cfg["title_hi"] if hi else cfg["title_en"]),
    })

    # body paragraphs
    P = list(cfg["facts"](a, lang, H) or [])
    tail = cfg.get("tail", civil_tail)
    if tail:
        P += list(tail(a, lang, H) or [])
    for cu in (_val(a, "custom_grounds", not hi) or a.get("custom_grounds") or []):
        if str(cu).strip():
            P.append((f'यह कि {esc(cu)}' if hi else f'That {esc(cu)}'))

    out = [hdr, '<div class="doc-body">']
    lead = cfg.get("lead_hi" if hi else "lead_en")
    if lead is None:
        lead = (f'{p_label} उपरोक्त इस माननीय न्यायालय के समक्ष सादर निवेदन करता/करती है ः—'
                if hi else f'The {p_label} above-named most respectfully submits as under:—')
    out.append(f'<p class="cb-prelude">{lead}</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        if isinstance(p, dict) and p.get("head"):     # non-numbered section heading
            out.append(f'<li class="cb-head">{esc(p["head"])}</li>')
        else:
            out.append(f'<li>{p}</li>')
    out.append('</ol>')

    # prayer — substantive clauses from cfg + standard costs & residual relief
    clauses = list(cfg["prayer"](a, lang, H) or [])
    clauses.append('वाद-व्यय (costs) वादी को प्रतिवादी से दिलाया जावे;' if hi
                   else 'the costs of the suit be awarded to the plaintiff;')
    clauses.append('अन्य कोई भी अनुतोष जो माननीय न्यायालय उचित एवं न्यायसंगत समझे, वह भी प्रदान किया जावे।' if hi
                   else 'any other relief that this Hon\'ble Court deems just and proper be also granted.')
    letters = _HI_LETTERS if hi else [chr(97 + i) for i in range(len(clauses))]
    open_line = ('अतः माननीय न्यायालय से सादर प्रार्थना है कि—' if hi
                 else 'It is, therefore, most respectfully prayed that this Hon\'ble Court may be pleased to grant:')
    out.append('<div class="cb-prayer"><p>' + open_line + '</p><ol class="cb-relief-list" '
               'style="list-style:none;padding-left:0;margin:6pt 0 0">')
    for i, cl in enumerate(clauses):
        lt = letters[i] if i < len(letters) else str(i + 1)
        out.append(f'<li style="margin:0 0 6pt;padding-left:26pt;text-indent:-26pt">({lt}) {cl}</li>')
    out.append('</ol></div>')

    # verification (Order VI Rule 15)
    out.append(f'<div class="cb-block-label">{"सत्यापन" if hi else "VERIFICATION"}</div>')
    out.append(f'<p class="cb-prelude">{_verification(a, lang, p_label)}</p>')

    # signature — signed by the FILER (plaintiff for a plaint; defendant for a WS)
    signer = cfg.get("signer_hi" if hi else "signer_en") or p_label
    d = ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))
    place = ph(_val(a, "cause_of_action_place", not hi), "स्थान" if hi else "Place")
    adv = ph(_val(a, "advocate_name", not hi), "अधिवक्ता" if hi else "advocate")
    if hi:
        out.append('<div class="cb-sig"><div class="l">'
                   f'<div>स्थान: {place}</div><div>दिनांक: {d}</div></div>'
                   f'<div class="r"><div>{signer}</div>'
                   f'<div style="margin-top:10pt">द्वारा अधिवक्ता</div>'
                   f'<div>({adv}) — एडवोकेट</div></div></div>')
    else:
        out.append('<div class="cb-sig"><div class="l">'
                   f'<div>Place: {place}</div><div>Date: {d}</div></div>'
                   f'<div class="r"><div>{signer}</div>'
                   f'<div style="margin-top:10pt">Through Counsel</div>'
                   f'<div>({adv}) — Advocate</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# --------------------------------------------------------------- shared field schema
def common_fields(*, property_desc=False, amount=False, agreement=False):
    """The fields every civil plaint needs; suit modules add their own on top."""
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court",
            hint="राज्य + जिला → सही न्यायालय/उच्च न्यायालय"),
        F.f("state_name", "राज्य", "State", section="court", hint="मामले का राज्य"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", section="court", auto=True),
        F.f("suit_number", "वाद क्रमांक", "Suit no.", section="court"),
        F.f("suit_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("plaintiff_name", "वादी का नाम", "Plaintiff name", F.NAME, True, "parties"),
        F.f("plaintiff_father", "पिता/पति का नाम", "Father/Husband name", section="parties"),
        F.f("plaintiff_address", "वादी का पता", "Plaintiff address", F.ADDRESS, section="parties"),
        F.f("defendant_name", "प्रतिवादी का नाम", "Defendant name", F.NAME, True, "parties"),
        F.f("defendant_father", "प्रतिवादी पिता/पति", "Defendant father/husband", section="parties"),
        F.f("defendant_address", "प्रतिवादी का पता", "Defendant address", F.ADDRESS, section="parties"),
    ]
    if property_desc:
        flds.append(F.f("property_description", "वादग्रस्त सम्पत्ति का विवरण (चौहद्दी सहित)",
                        "Suit-property description (with boundaries)", F.LONGTEXT, section="facts",
                        hint="खसरा/सर्वे/मकान नं. + चौहद्दी"))
    if amount:
        flds.append(F.f("claim_amount", "दावा राशि (₹)", "Claim amount (Rs.)", F.MONEY, section="facts"))
    if agreement:
        flds.append(F.f("agreement_date", "अनुबंध/इकरारनामा दिनांक", "Agreement date", F.DATE, section="facts"))
    return flds


def tail_fields():
    """Cause-of-action / jurisdiction / valuation / limitation + filing fields."""
    return [
        F.f("cause_of_action_date", "वाद-कारण दिनांक", "Cause-of-action date", F.DATE, section="facts"),
        F.f("cause_of_action_place", "वाद-कारण स्थान", "Cause-of-action place", section="facts"),
        F.f("valuation", "वाद मूल्यांकन (₹)", "Suit valuation (Rs.)", F.MONEY, section="facts"),
        F.f("court_fee", "अदा न्यायशुल्क (₹)", "Court fee paid (Rs.)", F.MONEY, section="facts"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]


def spec(cfg, extra_fields, toggles=None, *, property_desc=False, amount=False, agreement=False,
         companions=None):
    flds = common_fields(property_desc=property_desc, amount=amount, agreement=agreement)
    flds += list(extra_fields or [])
    flds += tail_fields()
    flds.append(F.custom_grounds())
    return F.build_spec(cfg["key"], flds, toggles or [],
                        variants={"court": [cfg.get("court", "civil")]},
                        companions=companions or [])


def review_page_html(cfg, sample):
    return doc_page([render(sample, "hi", cfg), render(sample, "en", cfg)],
                    banner=f'{cfg["label_hi"]} ({cfg["label_en"]}) — deterministic civil plaint · '
                           f'द्विभाषी · CPC Order VII · reviewed: false')
