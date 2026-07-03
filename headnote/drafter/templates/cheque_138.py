"""§138 Negotiable Instruments Act — cheque-dishonour COMPLAINT (परिवाद).

The first end-to-end test of the full system: the **canonical pixel-exact header**
(`_doc_header.render_header`) + the **point-wise body skeleton reproduced verbatim
from Vishnu ji's real filed §138 complaint** ("138 prigvate complent" / Tilak Singh
Rana) + **bilingual** (Hindi primary, English mirror). No LLM writes any text; only
the client variables fill in.

His verbatim para skeleton (the cause-of-action chain — it embodies the law):
  P1 relationship + legally-enforceable debt · P2 cheque given (no./bank/amount/date)
  · P3 presentation at payee's bank + dishonour (return memo + reason) · P4 demand
  notice (RPAD, pay-within-15-days) · P5 service / deemed receipt · P6 15-day default
  + cause of action · P7 legally-enforceable-debt recital (§139) · P8 mens rea / the
  §138 offence · [P8A §141 company + signatory — conditional] · P9 jurisdiction =
  payee's bank branch (§142(2): श्रवणाधिकार एवं विचारण क्षेत्राधिकार) · P10 no other
  complaint pending → PRAYER (cognizance + summon + max punishment + DOUBLE-the-cheque
  compensation) → signature → साक्ष्य सूची (witness list).

Companions (per application-frameworks.md): the §145 affidavit of evidence, the
document list, and the vakalatnama — noted at the foot. No case law in the body
(candidates in CITE_AT_HEARING, verified:false).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page
from headnote.drafter.templates import _fields as F


def _esc(s: Optional[str]) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ph(s: Optional[str], placeholder: str = "________") -> str:
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{placeholder}</span>'


# ---- candidate judgments (CITE-AT-HEARING only; never in the body) ----
CITE_AT_HEARING = [
    {"case": "Rangappa v. Sri Mohan (2010) 11 SCC 441",
     "point": "§139 presumption includes existence of a legally enforceable debt; rebuttable on preponderance.",
     "verified": False},
    {"case": "C.C. Alavi Haji v. Palapetty Muhammed (2007) 6 SCC 555",
     "point": "Deemed service of the demand notice (RPAD, correctly addressed) — answers 'notice not served'.",
     "verified": False},
    {"case": "Basalingappa v. Mudibasappa (2019) 5 SCC 418",
     "point": "How the drawer may rebut the §139 presumption.",
     "verified": False},
]


# =====================================================================  HINDI

def render_hi(a: dict) -> str:
    a = a or {}
    today = date.today()

    # ---- header fields ----
    hdr = render_header({
        "side_label": "",   # a complaint carries no "X की ओर से" side-line
        "court_name": a.get("court_name") or "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी, ............ (________)",
        "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "",
        "case_year": a.get("case_year") or str(today.year),
        "case_suffix": "परिवाद पत्र",
        "applicant_label": "अभियोगी",
        "applicant_desc": [
            f'{_ph(a.get("complainant_name"), "नाम")} पुत्र श्री {_ph(a.get("complainant_father"), "पिता")},',
            f'आयु— {_ph(a.get("complainant_age"), "..")} वर्ष, व्यवसाय— {_ph(a.get("complainant_occupation"), "व्यवसाय")},',
            f'निवासी— <u>{_ph(a.get("complainant_address"), "पता")}</u>',
        ],
        "respondent_label": "अभियुक्त",
        "respondent_desc": [
            f'{_ph(a.get("accused_name"), "नाम")} पुत्र श्री {_ph(a.get("accused_father"), "पिता")},',
            f'आयु— {_ph(a.get("accused_age"), "..")} वर्ष, व्यवसाय— {_ph(a.get("accused_occupation"), "व्यवसाय")},',
            f'निवासी— <u>{_ph(a.get("accused_address"), "पता")}</u>',
        ],
        "versus": "बनाम",
        "title_line": "परिवाद पत्र अन्तर्गत धारा 138 परक्राम्य लिखित अधिनियम",
    })

    # ---- variables ----
    rel = a.get("relationship") or "मित्रवत"
    txn = a.get("transaction_nature") or "की धान/सामग्री क्रय की थी"
    amt = _ph(a.get("amount"), "₹________")
    amtw = _ph(a.get("amount_words"), "________ रुपये")
    txn_date = _ph(a.get("transaction_date"), "..........")
    promise = a.get("promise_period") or ".........."
    cheque_no = _ph(a.get("cheque_no"), "________")
    acc_bank = _ph(a.get("accused_bank_branch"), "________ बैंक, ________ शाखा")
    cheque_date = _ph(a.get("cheque_date"), "..........")
    comp_bank = _ph(a.get("complainant_bank_branch"), "________ बैंक, ________ शाखा")
    dishon_date = _ph(a.get("dishonour_date"), "..........")
    dishon_reason = a.get("dishonour_reason") or "Funds Insufficient (खाते में अपर्याप्त राशि)"
    notice_date = _ph(a.get("notice_date"), "..........")
    notice_mode = a.get("notice_mode") or "रजिस्टर्ड ए.डी. डाक"
    known_date = _ph(a.get("notice_known_date"), "..........")
    expiry_date = _ph(a.get("expiry_date"), "..........")
    cause_date = _ph(a.get("cause_date"), "..........")
    svc = a.get("notice_service_narrative") or ""

    place = _ph(a.get("place"), "स्थान")
    fdate = _ph(a.get("filing_date"), today.strftime("%d/%m/%Y"))
    adv = a.get("advocate_name") or ""

    P = []  # the यहकि paragraphs (point-wise body)
    P.append(
        f'यहकि, अभियुक्त एवं अभियोगी एक-दूसरे से पूर्व से परिचित होकर उनके मध्य {_esc(rel)} '
        f'सम्बन्ध रहे हैं। अभियुक्त ने अभियोगी से दिनांक {txn_date} को {amt} ({amtw}) '
        f'{_esc(txn)}, जिसकी राशि अभियुक्त द्वारा {_esc(promise)} में अदा किये जाने का वादा '
        f'किया गया था।'
    )
    P.append(
        f'यहकि, अभियोगी द्वारा {_esc(promise)} में जब अभियुक्त से उक्त राशि की मांग की गई, '
        f'तो अभियुक्त ने राशि के भुगतान के दायित्व को स्वीकार करते हुये अपने खाते वाली '
        f'बैंक — {acc_bank} का चैक क्रमांक {cheque_no}, राशि {amt} ({amtw}), दिनांकित '
        f'{cheque_date}, स्वयं के हस्ताक्षर सहित इस आश्वासन के साथ अभियोगी को प्रदान किया '
        f'कि उक्त चैक को वैध अवधि में प्रस्तुत करने पर उसमें वर्णित राशि का भुगतान प्राप्त '
        f'हो जायेगा। अभियुक्त के विश्वास पर अभियोगी द्वारा उक्त चैक प्राप्त कर लिया गया।'
    )
    P.append(
        f'यहकि, अभियोगी द्वारा उक्त चैक क्रमांक {cheque_no}, राशि {amt}, दिनांकित {cheque_date}, '
        f'भुगतान हेतु अपनी बैंक — {comp_bank} में प्रस्तुत किया गया, किन्तु उक्त चैक का भुगतान '
        f'न होकर वह दिनांक {dishon_date} को मय रिटर्न मेमो, भुगतान न होने के कारण '
        f'"{_esc(dishon_reason)}" की टीप सहित, बिना भुगतान के अभियोगी को वापस प्राप्त हुआ।'
    )
    P.append(
        f'यहकि, उक्त चैक बिना भुगतान के वापस प्राप्त होने पर अभियोगी ने अपने अभिभाषक के '
        f'माध्यम से दिनांक {notice_date} को अभियुक्त के पते पर {_esc(notice_mode)} द्वारा इस '
        f'आशय का मांग-सूचना पत्र भेजा कि अभियुक्त सूचना प्राप्ति के 15 दिवस के भीतर चैक में '
        f'वर्णित राशि का भुगतान अभियोगी को करे।'
    )
    if svc.strip():
        P.append(f'यहकि, {_esc(svc)}')
    else:
        P.append(
            f'यहकि, उक्त मांग-सूचना पत्र की तामील/जानकारी अभियुक्त को दिनांक {known_date} को '
            f'हो गई।'
        )
    P.append(
        f'यहकि, अभियुक्त को सूचना पत्र की जानकारी दिनांक {known_date} को होने के कारण नोटिस '
        f'में वर्णित 15 दिवस की अवधि दिनांक {expiry_date} को पूर्ण हो चुकी है तथा दिनांक '
        f'{cause_date} से वाद-कारण उत्पन्न होकर आज दिनांक तक निरन्तर जारी है। अभियुक्त द्वारा '
        f'आज दिनांक तक चैक में वर्णित राशि का भुगतान अभियोगी को नहीं किया गया है।'
    )
    P.append(
        'यहकि, अभियुक्त द्वारा उक्त चैक अपने विधिक दायित्व के उन्मोचन (discharge of legally '
        'enforceable debt) हेतु अभियोगी को प्रदान किया गया था तथा उक्त चैक की राशि का भुगतान '
        'करने हेतु अभियुक्त विधिक रूप से उत्तरदायी है।'
    )
    P.append(
        'यहकि, अभियुक्त ने अभियोगी को अवैध हानि पहुँचाने एवं स्वयं को अवैध लाभ अर्जित करने के '
        'उद्देश्य से, यह जानते हुये कि उसके बैंक खाते में चैक के भुगतान योग्य पर्याप्त राशि '
        'नहीं है, छलपूर्वक उक्त चैक अभियोगी को प्रदान किया। अभियुक्त का उक्त कृत्य परक्राम्य '
        'लिखित अधिनियम की धारा 138 के अन्तर्गत दण्डनीय अपराध की श्रेणी में आता है।'
    )
    if a.get("is_company"):
        P.append(
            f'यहकि, अभियुक्त क्रमांक 1 {_ph(a.get("company_name"), "कम्पनी/फर्म")} एक कम्पनी/फर्म '
            f'है तथा अभियुक्त क्रमांक 2, उक्त कम्पनी के {_ph(a.get("signatory_role"), "हस्ताक्षरकर्ता/संचालक")} '
            f'होकर कम्पनी के दैनिक कार्य-संचालन हेतु उत्तरदायी होने के कारण परक्राम्य लिखित '
            f'अधिनियम की धारा 141 के अन्तर्गत उक्त अपराध हेतु संयुक्त एवं पृथक् रूप से उत्तरदायी हैं।'
        )
    P.append(
        f'यहकि, अभियोगी का बैंक खाता {comp_bank} में होने के कारण माननीय न्यायालय को प्रस्तुत '
        f'परिवाद का श्रवणाधिकार एवं विचारण क्षेत्राधिकार प्राप्त है तथा उक्त अपराध माननीय '
        f'न्यायालय के विचारण योग्य है।'
    )
    P.append(
        'यहकि, उक्त विवादित चैक के सम्बन्ध में अभियोगी द्वारा अभियुक्त के विरुद्ध भारतवर्ष '
        'के किसी भी अन्य न्यायालय में कोई परिवाद/अभियोग पत्र न तो प्रस्तुत किया गया है, न '
        'लंबित है और न ही विचाराधीन है।'
    )

    witnesses = a.get("witnesses") or [
        "अभियोगी स्वयं कथन करेगा।",
        "अभियोगी की बैंक से सम्बन्धित अधिकारी/कर्मचारी (मय रिकॉर्ड)।",
        "अभियुक्त की बैंक से सम्बन्धित अधिकारी।",
        "सूचना पत्र प्रेषक एवं रजिस्ट्री की डिलीवरी रिपोर्ट देने वाला सम्बन्धित डाक विभाग अधिकारी।",
        "अन्य साक्षी विचारण के दौरान माननीय न्यायालय की अनुमति से प्रस्तुत किये जावेंगे।",
    ]

    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">माननीय न्यायालय,</p>')
    out.append('<p class="cb-prelude">अभियोगी की ओर से परिवाद पत्र निम्न प्रकार प्रस्तुत है ः—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>')
    out.append(
        f'अतः माननीय न्यायालय से सादर निवेदन है कि अभियुक्त के विरुद्ध परक्राम्य लिखित '
        f'अधिनियम की धारा 138 के अन्तर्गत अपराध का संज्ञान लेकर अभियुक्त को तलब किया जावे, '
        f'तथा विचारणोपरान्त अभियुक्त को अधिकतम दण्ड से दण्डित किया जाकर अभियुक्त द्वारा '
        f'प्रदत्त चैक क्रमांक {cheque_no}, दिनांकित {cheque_date}, राशि {amt} ({amtw}) से '
        f'दुगुनी राशि क्षतिपूर्ति के रूप में अभियोगी को अभियुक्त से दिलाये जाने का आदेश '
        f'पारित करने की कृपा करें।'
    )
    out.append('</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>स्थान: {place}</div><div>दिनांक: {fdate}</div></div>')
    out.append('<div class="r"><div>प्रार्थी</div>')
    out.append(f'<div>{_ph(a.get("complainant_name"), "अभियोगी का नाम")} — अभियोगी</div>')
    if adv:
        out.append(f'<div style="margin-top:10pt">द्वारा अभिभाषक</div><div>({_esc(adv)})</div>')
    out.append('</div></div>')
    out.append('<div class="cb-block-label">साक्ष्य सूची</div>')
    out.append('<ol class="cb-witlist">')
    for w in witnesses:
        out.append(f'<li>{_esc(w)}</li>')
    out.append('</ol>')
    out.append(
        '<div class="cb-note">साथ संलग्न: (1) अभियोगी का साक्ष्य-शपथपत्र — धारा 145 परक्राम्य '
        'लिखित अधिनियम; (2) दस्तावेज सूची — मूल चैक, रिटर्न मेमो, मांग-सूचना पत्र, डाक रसीद/'
        'ट्रैकिंग, ऋण/लेन-देन सम्बन्धी दस्तावेज; (3) वकालतनामा।</div>')
    out.append('</div>')  # /.doc-body
    return "\n".join(out)


# ===================================================================  ENGLISH

def render_en(a: dict) -> str:
    a = dict(a or {})
    for _k in list(a):  # overlay any *_en value onto its base key → English-aware render
        if _k.endswith("_en") and a[_k] not in (None, ""):
            a[_k[:-3]] = a[_k]
    today = date.today()
    hdr = render_header({
        "side_label": "",
        "court_name": a.get("court_name_en") or a.get("court_name") or "Court of the Judicial Magistrate First Class, ............ (________)",
        "case_code": "Criminal Complaint Case",
        "case_number": a.get("case_number") or "",
        "case_year": a.get("case_year") or str(today.year),
        "applicant_label": "Complainant",
        "applicant_desc": [
            f'{_ph(a.get("complainant_name"), "name")}, S/o {_ph(a.get("complainant_father"), "father")},',
            f'aged {_ph(a.get("complainant_age"), "..")} yrs, occupation {_ph(a.get("complainant_occupation"), "occupation")},',
            f'R/o <u>{_ph(a.get("complainant_address"), "address")}</u>',
        ],
        "respondent_label": "Accused",
        "respondent_desc": [
            f'{_ph(a.get("accused_name"), "name")}, S/o {_ph(a.get("accused_father"), "father")},',
            f'aged {_ph(a.get("accused_age"), "..")} yrs, occupation {_ph(a.get("accused_occupation"), "occupation")},',
            f'R/o <u>{_ph(a.get("accused_address"), "address")}</u>',
        ],
        "versus": "Versus",
        "title_line": "COMPLAINT UNDER SECTION 138 OF THE NEGOTIABLE INSTRUMENTS ACT, 1881",
    })
    amt = _ph(a.get("amount"), "Rs. ________")
    cheque_no = _ph(a.get("cheque_no"), "________")
    cheque_date = _ph(a.get("cheque_date"), "..........")
    comp_bank = _ph(a.get("complainant_bank_branch"), "________ Bank, ________ Branch")
    acc_bank = _ph(a.get("accused_bank_branch"), "________ Bank, ________ Branch")
    dishon_date = _ph(a.get("dishonour_date"), "..........")
    dishon_reason = a.get("dishonour_reason") or "Funds Insufficient"
    notice_date = _ph(a.get("notice_date"), "..........")
    known_date = _ph(a.get("notice_known_date"), "..........")
    expiry_date = _ph(a.get("expiry_date"), "..........")
    cause_date = _ph(a.get("cause_date"), "..........")
    txn_date = _ph(a.get("transaction_date"), "..........")
    promise = _esc(a.get("promise_period") or "..........")

    P = []
    P.append(f'That the complainant and the accused were known to each other; the accused, on '
             f'{txn_date}, incurred a liability of {amt} towards the complainant '
             f'({_esc(a.get("transaction_nature_en") or "goods purchased / amount due")}), promising to pay by {promise}.')
    P.append(f'That, on demand, the accused — in acknowledgement of the said liability — issued from his '
             f'account at {acc_bank} cheque No. {cheque_no} for {amt}, dated {cheque_date}, duly signed, '
             f'with the assurance that it would be honoured on presentation within validity.')
    P.append(f'That the complainant presented the said cheque for payment through his bank, {comp_bank}, but '
             f'it was returned unpaid on {dishon_date} with the bank\'s return memo bearing the remark '
             f'"{_esc(dishon_reason)}".')
    P.append(f'That on the dishonour, the complainant, through counsel, issued a written demand notice on '
             f'{notice_date} by Registered A.D. post to the accused, calling upon him to pay the cheque '
             f'amount within 15 days of receipt.')
    if (a.get("notice_service_narrative_en") or "").strip():
        P.append(f'That {_esc(a.get("notice_service_narrative_en"))}')
    else:
        P.append(f'That the said demand notice was served on / came to the knowledge of the accused on {known_date}.')
    P.append(f'That the 15-day period expired on {expiry_date}, the cause of action arose on {cause_date} and '
             f'continues, and the accused has failed to pay the cheque amount to date.')
    P.append('That the said cheque was given by the accused in discharge of a legally enforceable debt/liability, '
             'for which the accused is legally liable.')
    P.append('That the accused, knowing that his account did not hold sufficient funds, fraudulently issued the '
             'cheque to cause wrongful loss to the complainant and wrongful gain to himself; the said act '
             'constitutes an offence punishable under Section 138 of the Negotiable Instruments Act, 1881.')
    if a.get("is_company"):
        P.append(f'That accused No. 1, {_ph(a.get("company_name"), "company/firm")}, is a company/firm and accused '
                 f'No. 2, being its {_ph(a.get("signatory_role"), "signatory/director")} responsible for the conduct '
                 f'of its business, is jointly and severally liable under Section 141 of the Act.')
    P.append(f'That as the complainant maintains his bank account at {comp_bank}, this Hon\'ble Court has '
             f'jurisdiction to try the complaint (Section 142(2) NI Act).')
    P.append('That no other complaint in respect of the said cheque has been filed by the complainant against the '
             'accused in any other court in India, nor is any such complaint pending.')

    witnesses_en = a.get("witnesses_en") or [
        "The complainant himself.",
        "The concerned officer/official of the complainant's bank (with record).",
        "The concerned officer of the accused's bank.",
        "The postal official who dispatched the notice and gave the delivery report.",
        "Such other witnesses as may be permitted during trial.",
    ]

    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>')
    out.append('<p class="cb-prelude">The complainant most respectfully submits as under:—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>')
    out.append(f'It is therefore most respectfully prayed that this Hon\'ble Court may be pleased to take '
               f'cognizance of the offence under Section 138 of the Negotiable Instruments Act, 1881, summon and '
               f'try the accused, award the maximum punishment, and direct the accused to pay the complainant '
               f'compensation of up to twice the cheque amount (cheque No. {cheque_no}, dated {cheque_date}, '
               f'{amt}).')
    out.append('</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Place: {_ph(a.get("place"), "place")}</div><div>Date: {_ph(a.get("filing_date"), today.strftime("%d/%m/%Y"))}</div></div>')
    out.append('<div class="r"><div>Complainant</div>')
    out.append(f'<div>{_ph(a.get("complainant_name"), "complainant")} — Complainant</div>')
    if a.get("advocate_name"):
        out.append(f'<div style="margin-top:10pt">Through Counsel</div><div>({_esc(a.get("advocate_name"))})</div>')
    out.append('</div></div>')
    out.append('<div class="cb-block-label">LIST OF WITNESSES</div>')
    out.append('<ol class="cb-witlist">')
    for w in witnesses_en:
        out.append(f'<li>{_esc(w)}</li>')
    out.append('</ol>')
    out.append('<div class="cb-note">Enclosed: (1) complainant\'s evidence affidavit u/S 145 NI Act; '
               '(2) list of documents — original cheque, return memo, demand notice, postal receipt/tracking, '
               'documents of the underlying debt; (3) vakalatnama.</div>')
    out.append('</div>')
    return "\n".join(out)


# =====================================================================  field schema
_TOGGLES = [
    F.toggle("is_company", "अभियुक्त कम्पनी/फर्म है (§141)", "Accused is a company/firm (§141)", default=False),
]


def field_spec() -> dict:
    """Input fields a lawyer fills for a §138 complaint (auto = derived, not typed)."""
    flds = [
        F.f("court_name", "न्यायालय का नाम", "Court name", required=True, section="court"),
        F.f("case_number", "केस क्रमांक", "Case no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("complainant_name", "अभियोगी का नाम", "Complainant name", F.NAME, True, "parties"),
        F.f("complainant_father", "पिता/पति का नाम", "Father/Husband", F.NAME, section="parties"),
        F.f("complainant_age", "आयु", "Age", F.NUMBER, section="parties"),
        F.f("complainant_occupation", "व्यवसाय", "Occupation", section="parties"),
        F.f("complainant_address", "पता", "Address", F.ADDRESS, True, "parties"),
        F.f("accused_name", "अभियुक्त का नाम", "Accused name", F.NAME, True, "parties"),
        F.f("accused_father", "पिता का नाम", "Father", F.NAME, section="parties"),
        F.f("accused_age", "आयु", "Age", F.NUMBER, section="parties"),
        F.f("accused_occupation", "व्यवसाय", "Occupation", section="parties"),
        F.f("accused_address", "पता", "Address", F.ADDRESS, True, "parties"),
        F.f("transaction_nature", "लेन-देन (क्या/किसलिए)", "Transaction (what/why)", section="crime",
            hint='जैसे "की धान क्रय की थी" / "की राशि उधार दी"'),
        F.f("amount", "राशि (₹)", "Amount (Rs.)", F.MONEY, True, "crime"),
        F.f("amount_words", "राशि (शब्दों में)", "Amount (in words)", section="crime"),
        F.f("transaction_date", "लेन-देन दिनांक", "Transaction date", F.DATE, section="crime"),
        F.f("promise_period", "भुगतान का वादा (कब)", "Promised payment by", section="crime"),
        F.f("cheque_no", "चैक क्रमांक", "Cheque no.", required=True, section="crime", ocr="cheque"),
        F.f("accused_bank_branch", "अभियुक्त की बैंक/शाखा", "Accused's bank/branch", section="crime", ocr="cheque"),
        F.f("cheque_date", "चैक दिनांक", "Cheque date", F.DATE, True, "crime", ocr="cheque"),
        F.f("complainant_bank_branch", "अभियोगी की बैंक/शाखा (क्षेत्राधिकार)", "Complainant's bank/branch (jurisdiction)", required=True, section="crime"),
        F.f("dishonour_date", "अनादर दिनांक", "Dishonour date", F.DATE, True, "crime", ocr="cheque"),
        F.f("dishonour_reason", "अनादर का कारण", "Return reason", section="crime", default="Funds Insufficient", ocr="cheque"),
        F.f("notice_date", "मांग-सूचना दिनांक", "Demand notice date", F.DATE, True, "crime"),
        F.f("notice_known_date", "सूचना तामील/ज्ञात दिनांक", "Notice served/known date", F.DATE, True, "crime"),
        F.f("expiry_date", "15-दिवस समाप्ति दिनांक", "15-day expiry date", F.DATE, section="crime", auto=True, hint="स्वतः: तामील + 15 दिन"),
        F.f("cause_date", "वाद-कारण दिनांक", "Cause-of-action date", F.DATE, section="crime", auto=True, hint="स्वतः"),
        F.f("notice_service_narrative", "तामील विवरण (यदि विवादित)", "Service narrative (if contested)", F.LONGTEXT, section="facts"),
        F.f("company_name", "कम्पनी/फर्म का नाम", "Company/firm name", section="grounds", depends="is_company"),
        F.f("signatory_role", "हस्ताक्षरकर्ता की भूमिका", "Signatory's role", section="grounds", depends="is_company"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("place", "स्थान", "Place", section="filing", default="ग्वालियर"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec("cheque_138", flds, _TOGGLES,
                        companions=["§145 साक्ष्य शपथपत्र", "दस्तावेज सूची (चैक/मेमो/नोटिस/रसीद)", "वकालतनामा"])


# =====================================================================  SAMPLE
# Genericised, illustrative example (NOT a real client) — modelled on the
# "Tilak Singh Rana" §138 complaint structure.
SAMPLE = {
    "court_name": "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी, ग्वालियर (म.प्र.)",
    "court_name_en": "Court of the Judicial Magistrate First Class, Gwalior (M.P.)",
    "case_number": "", "case_year": "2025",
    "complainant_name": "क ख", "complainant_name_en": "K. B.", "complainant_father": "____", "complainant_age": "35",
    "complainant_occupation": "कृषि", "complainant_occupation_en": "agriculture",
    "complainant_address": "ग्राम ____, मुरार, ग्वालियर (म.प्र.)", "complainant_address_en": "Village ____, Morar, Gwalior (M.P.)",
    "accused_name": "ग घ", "accused_name_en": "G. Gh.", "accused_father": "____", "accused_age": "42",
    "accused_occupation": "व्यापार", "accused_occupation_en": "business",
    "accused_address": "____, लश्कर, ग्वालियर (म.प्र.)", "accused_address_en": "____, Lashkar, Gwalior (M.P.)",
    "relationship": "मित्रवत", "relationship_en": "friendly", "transaction_nature": "की धान क्रय की थी",
    "transaction_nature_en": "purchased paddy",
    "amount": "₹1,12,080", "amount_words": "एक लाख बारह हजार अस्सी रुपये", "amount_words_en": "Rupees One Lakh Twelve Thousand Eighty",
    "transaction_date": "04.01.2025", "promise_period": "मार्च 2025", "promise_period_en": "March 2025",
    "cheque_no": "984612", "accused_bank_branch": "यस बैंक लिमिटेड, ____ शाखा, ग्वालियर",
    "accused_bank_branch_en": "Yes Bank Ltd., ____ Branch, Gwalior", "cheque_date": "05.02.2025",
    "complainant_bank_branch": "भारतीय स्टेट बैंक, अलापुर शाखा, ग्वालियर",
    "complainant_bank_branch_en": "State Bank of India, Alapur Branch, Gwalior",
    "dishonour_date": "04.04.2025", "dishonour_reason": "Funds Insufficient (खाते में अपर्याप्त राशि)",
    "dishonour_reason_en": "Funds Insufficient", "notice_date": "28.04.2025", "notice_known_date": "29.04.2025",
    "expiry_date": "14.05.2025", "cause_date": "15.05.2025",
    "place": "ग्वालियर", "place_en": "Gwalior", "filing_date": "__/05/2025", "advocate_name": "____",
}


# =====================================================================  review
def review_page_html(data: Optional[dict] = None) -> str:
    """Bilingual read-only review — Hindi sheet + English sheet on A4."""
    d = data if data is not None else SAMPLE
    banner = (
        '<b>समीक्षा — परिवाद पत्र अन्तर्गत धारा 138 परक्राम्य लिखित अधिनियम (cheque dishonour complaint)</b><br>'
        'नमूना (काल्पनिक) · संरचना विष्णु जी की वास्तविक §138 परिवाद फाइलिंग से अक्षरशः · canonical header + '
        'point-wise body · द्विभाषी (हिन्दी + English) · §139/§142(2) पालन · कोई AI-लिखित पाठ नहीं · '
        'समीक्षा हेतु प्रस्ताव (reviewed: false) · नीचे: हिन्दी प्रति, फिर अंग्रेजी प्रति।'
    )
    return doc_page([render_hi(d), render_en(d)], banner=banner)
