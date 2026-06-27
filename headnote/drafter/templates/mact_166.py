"""Motor accident compensation claim — §166 Motor Vehicles Act, 1988 (MACT).

AUTHOR-tier (tribunal format; no Vishnu mirror — FLAG for review). Claimant(s) vs
driver / owner / insurer. reviewed:false. No case law in the body.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "National Insurance Co. v. Pranay Sethi (2017) 16 SCC 680", "point": "future-prospects / standardised compensation heads", "verified": False},
]


def _esc(s): return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def _ph(s, ph="________"): return _esc(s) if (s and str(s).strip()) else f'<span class="ph">{ph}</span>'
def _chunks(t): return [x.strip() for x in str(t or "").split("\n\n") if x.strip()]
def _ov(a):
    a = dict(a or {})
    for k in list(a):
        if k.endswith("_en") and a[k] not in (None, ""): a[k[:-3]] = a[k]
    return a


def _doc(a, hi):
    a = a if hi else _ov(a); g = a.get("grounds") or {}
    cn = a.get("court_name") or ("माननीय मोटर दुर्घटना दावा अधिकरण, ............ (म.प्र.)" if hi else "Motor Accidents Claims Tribunal, ............ (M.P.)")
    amt = _ph(a.get("claim_amount"), "____")
    hdr = render_header({
        "side_label": "", "court_name": cn, "case_code": (a.get("case_code") or ("दावा प्रकरण क्रमांक" if hi else "Claim Case No.")),
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": ("आवेदकगण/दावेदार" if hi else "Claimants"), "applicant_desc": [_ph(a.get("claimant_name"), "दावेदार का नाम" if hi else "claimant")],
        "respondent_label": ("अनावेदकगण" if hi else "Respondents"), "respondent_desc": [_ph(a.get("respondent_name"), "चालक/स्वामी/बीमा कम्पनी" if hi else "driver/owner/insurer")],
        "versus": ("बनाम" if hi else "Versus"),
        "title_line": ("दावा आवेदन अन्तर्गत धारा 166 मोटर यान अधिनियम, 1988" if hi else "CLAIM PETITION UNDER SECTION 166 OF THE MOTOR VEHICLES ACT, 1988"),
    })
    veh = _ph(a.get("vehicle_no"), "वाहन क्रमांक" if hi else "vehicle no.")
    P = []
    for ch in _chunks(a.get("facts_narrative")): P.append((f'यहकि, {_esc(ch)}' if hi else f'That {_esc(ch)}'))
    if not _chunks(a.get("facts_narrative")):
        P.append(('<span class="ph">[दुर्घटना का विवरण — दिनांक, स्थान, वाहन, चोट/मृत्यु, दावेदार का सम्बन्ध, '
                  'मृतक/घायल की आयु एवं आय — खाली पंक्ति से अलग पैरा]</span>' if hi else
                  '<span class="ph">[accident details — date, place, vehicle, injury/death, claimant relation, age & income]</span>'))
    if g.get("rash_negligent", True):
        P.append((f'यहकि, उक्त दुर्घटना अनावेदक चालक द्वारा वाहन {veh} को तेज गति एवं लापरवाहीपूर्वक चलाये जाने '
                  f'के कारण घटित हुई, जिसके लिये अनावेदक चालक एवं स्वामी उत्तरदायी हैं।' if hi else
                  f'That the accident occurred due to the rash and negligent driving of vehicle {veh} by the '
                  f'respondent driver, for which the driver and owner are liable.'))
    if g.get("insured", True):
        P.append(('यहकि, दुर्घटना दिनांक को उक्त वाहन अनावेदक बीमा कम्पनी के पास वैध रूप से बीमित था, अतः बीमा '
                  'कम्पनी प्रतिकर अदा करने हेतु संयुक्त एवं पृथक रूप से उत्तरदायी है।' if hi else
                  'That on the date of the accident the vehicle was validly insured with the respondent insurer, '
                  'which is jointly and severally liable to pay the compensation.'))
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append((f'यहकि, {_esc(cu)}' if hi else f'That {_esc(cu)}'))
    pray = (f'अतः माननीय अधिकरण से सादर निवेदन है कि दावेदारगण के पक्ष में रुपये {amt}/— का प्रतिकर ब्याज सहित '
            f'अनावेदकगण के विरुद्ध संयुक्त एवं पृथक रूप से दिलाये जाने की कृपा करें।' if hi else
            f'It is therefore most respectfully prayed that compensation of Rs. {amt}/- with interest be awarded '
            f'in favour of the claimants against the respondents, jointly and severally.')
    out = [hdr, '<div class="doc-body">', f'<p class="cb-prelude">{("माननीय अधिकरण," if hi else "MAY IT PLEASE THE TRIBUNAL,")}</p>',
           f'<p class="cb-prelude">{("दावेदारगण की ओर से दावा आवेदन निम्न प्रकार प्रस्तुत है ः—" if hi else "The claimants most respectfully submit as under:—")}</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>{pray}</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>{("दिनांक: " if hi else "Date: ")}{_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("claimant_name"), "दावेदार" if hi else "Claimant")}</div>'
               f'<div>— {("दावेदारगण" if hi else "Claimants")}</div><div style="margin-top:10pt">{("द्वारा अभिभाषक" if hi else "Through Counsel")}</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता" if hi else "advocate")})</div></div></div></div>')
    return "\n".join(out)


def render_hi(a: dict) -> str: return _doc(a or {}, True)
def render_en(a: dict) -> str: return _doc(a or {}, False)

_TOGGLES = [
    F.toggle("rash_negligent", "तेज/लापरवाह चालन — पैरा", "Rash/negligent driving — para", default=True),
    F.toggle("insured", "वाहन बीमित — बीमा कम्पनी उत्तरदायी", "Vehicle insured — insurer liable", default=True),
]


def field_spec(court: str = "") -> dict:
    flds = [
        F.f("court_name", "अधिकरण का नाम", "Tribunal name", required=True, section="court",
            hint="जैसे: मोटर दुर्घटना दावा अधिकरण, ____"),
        F.f("case_number", "दावा प्रकरण क्रमांक", "Claim case no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("claimant_name", "दावेदार का नाम", "Claimant name", F.NAME, True, "parties"),
        F.f("respondent_name", "अनावेदकगण (चालक/स्वामी/बीमा)", "Respondents (driver/owner/insurer)", F.NAME, True, "parties"),
        F.f("vehicle_no", "वाहन क्रमांक", "Vehicle no.", section="facts"),
        F.f("facts_narrative", "दुर्घटना का विवरण", "Accident details", F.LONGTEXT, True, "facts",
            hint="दिनांक/स्थान/वाहन/चोट-मृत्यु/सम्बन्ध/आयु-आय — खाली पंक्ति से अलग पैरा"),
        F.f("claim_amount", "दावा राशि (रु.)", "Claim amount (Rs.)", F.MONEY, section="facts"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec("mact_166", flds, _TOGGLES, companions=["affidavit", "vakalatnama", "FIR/charge-sheet, PM/MLC, vehicle docs"])


SAMPLE = {
    "court_name": "माननीय मोटर दुर्घटना दावा अधिकरण, ग्वालियर (म.प्र.)", "case_number": "____/2026",
    "claimant_name": "____ व अन्य", "respondent_name": "____ (चालक), ____ (स्वामी), ____ बीमा कम्पनी",
    "vehicle_no": "एम.पी.07 ____",
    "facts_narrative": (
        "दिनांक ____ को मृतक/घायल ____ अपने ____ से जा रहा था, तभी अनावेदक के वाहन ने तेज गति एवं लापरवाहीपूर्वक "
        "टक्कर मार दी, जिससे ____ को गम्भीर चोटें आईं/मृत्यु हो गई।\n\n"
        "मृतक/घायल आयु ____ वर्ष का होकर ____ रुपये मासिक अर्जित करता था; दावेदारगण उस पर आश्रित हैं।"
    ),
    "claim_amount": "____",
    "court_name_en": "Motor Accidents Claims Tribunal, Gwalior (M.P.)",
    "claimant_name_en": "____ & ors.", "respondent_name_en": "____ (driver), ____ (owner), ____ Insurance Co.",
    "vehicle_no_en": "MP-07-____",
    "facts_narrative_en": (
        "on ____ the deceased/injured ____ was travelling when the respondent's vehicle, driven rashly and "
        "negligently, struck them, causing grievous injury/death.\n\n"
        "the deceased/injured, aged ____ years, earned Rs. ____ per month; the claimants were dependent on them."
    ),
    "grounds": {"rash_negligent": True, "insured": True}, "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="MACT §166 दावा — समीक्षा · AUTHORED (अधिकरण प्रारूप; विष्णु जी समीक्षा आवश्यक) · द्विभाषी · reviewed: false")
