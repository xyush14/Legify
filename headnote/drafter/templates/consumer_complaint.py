"""Consumer Complaint (उपभोक्ता परिवाद) — §35 Consumer Protection Act, 2019.

Filed before the District Commission (NOT a CPC plaint — a complaint, pleaded in
numbered paras). Para 1 MUST establish the complainant is a consumer (§2(7)):
goods/services for consideration, non-commercial. Then the transaction, the defect
/ deficiency (§2(11)) / unfair trade practice, the complaints and the OP's failure,
jurisdiction (§34(2)(d) — complainant's residence allowed), limitation (§69 — 2
years). Supporting affidavit is mandatory. Reliefs per §39.
"""
from __future__ import annotations

from headnote.drafter.templates import _civil as C
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Lucknow Development Authority v. M.K. Gupta (1994) 1 SCC 243",
     "point": "'service' construed widely; statutory bodies answerable; compensation for harassment", "verified": False},
]


def _facts(a, lang, H):
    hi = lang == "hi"
    en = not hi
    item = H.ph(C._val(a, "goods_or_service", en), "माल/सेवा" if hi else "goods/service")
    tdate = H.ph(a.get("transaction_date"), "दिनांक" if hi else "date")
    paid = H.ph(C._val(a, "amount_paid", en), "अदा राशि" if hi else "amount paid")
    defect = H.ph(C._val(a, "defect_deficiency", en), "दोष/सेवा में कमी" if hi else "defect/deficiency")
    comp = H.ph(a.get("complaint_date"), "दिनांक" if hi else "date")
    if hi:
        return [
            f'यह कि परिवादी उपभोक्ता संरक्षण अधिनियम, 2019 की धारा 2(7) के अन्तर्गत "उपभोक्ता" है, '
            f'क्योंकि उसने प्रतिफल देकर {item} अपने उपयोग हेतु (वाणिज्यिक प्रयोजन से नहीं) प्राप्त किया।',
            f'यह कि परिवादी ने दिनांक {tdate} को अनावेदक से उक्त {item} हेतु {paid} रुपये अदा किये, '
            f'जिसका बिल/रसीद परिवाद के साथ संलग्न है।',
            f'यह कि उक्त माल/सेवा में निम्नानुसार दोष/सेवा में कमी (धारा 2(11)) पाई गई ः— {defect}।',
            f'यह कि परिवादी ने दिनांक {comp} को अनावेदक से शिकायत कर दोष दूर करने/प्रतिपूर्ति की माँग '
            f'की, किन्तु अनावेदक ने कोई समुचित कार्यवाही नहीं की, जो सेवा में कमी है।',
            'यह कि यह माननीय आयोग को धारा 34(2)(d) के अन्तर्गत क्षेत्राधिकार प्राप्त है, क्योंकि परिवादी '
            'इस आयोग की अधिकारिता में निवास/कार्य करता है तथा अदा प्रतिफल आर्थिक सीमा के भीतर है।',
            'यह कि प्रस्तुत परिवाद वाद-कारण उत्पन्न होने की दिनांक से धारा 69 की 2 वर्ष की अवधि के '
            'भीतर, समय-सीमा में प्रस्तुत किया जा रहा है।',
        ]
    return [
        f'That the complainant is a "consumer" within Section 2(7) of the Consumer Protection Act, 2019, '
        f'having obtained {item} for consideration for personal use (not for any commercial purpose).',
        f'That on {tdate} the complainant paid Rs. {paid} to the opposite party for the said {item}, the '
        f'bill/receipt whereof is annexed to this complaint.',
        f'That the said goods/service suffer from the following defect / deficiency in service '
        f'(Section 2(11)):— {defect}.',
        f'That on {comp} the complainant complained to the opposite party seeking rectification/redress, '
        f'but the opposite party took no proper action, which amounts to deficiency in service.',
        'That this Hon\'ble Commission has jurisdiction under Section 34(2)(d), the complainant residing/'
        'working within its jurisdiction and the consideration paid being within its pecuniary limit.',
        'That the present complaint is being filed within the period of two years from the cause of '
        'action prescribed by Section 69.',
    ]


def _prayer(a, lang, H):
    hi = lang == "hi"
    paid = H.ph(C._val(a, "amount_paid", not hi), "अदा राशि" if hi else "amount paid")
    if hi:
        return [
            f'अनावेदक को आदेशित किया जावे कि वह दोषपूर्ण माल बदले/मरम्मत करे अथवा अदा राशि {paid} रुपये '
            f'ब्याज सहित परिवादी को वापस करे;',
            'परिवादी को हुई हानि, मानसिक क्लेश एवं उत्पीड़न हेतु समुचित प्रतिकर (compensation) दिलाया जावे;',
        ]
    return [
        f'direct the opposite party to replace/rectify the defective goods or refund the amount of '
        f'Rs. {paid} with interest to the complainant;',
        'award adequate compensation to the complainant for the loss, mental agony and harassment '
        'suffered;',
    ]


CFG = {
    "key": "consumer_complaint", "label_hi": "उपभोक्ता परिवाद", "label_en": "Consumer Complaint", "court": "consumer",
    "case_code_hi": "उपभोक्ता परिवाद क्रमांक", "case_code_en": "Consumer Complaint No.",
    "title_hi": "परिवाद अन्तर्गत धारा 35 उपभोक्ता संरक्षण अधिनियम, 2019",
    "title_en": "COMPLAINT UNDER SECTION 35 OF THE CONSUMER PROTECTION ACT, 2019",
    "p_label_hi": "परिवादी", "p_label_en": "Complainant", "d_label_hi": "अनावेदक", "d_label_en": "Opposite Party",
    "lead_hi": "परिवादी उपरोक्त माननीय आयोग के समक्ष सादर निवेदन करता/करती है ः—",
    "lead_en": "The complainant most respectfully submits before this Hon'ble Commission as under:—",
    "facts": _facts, "prayer": _prayer, "tail": None, "needs_affidavit": True,
}


def render_hi(a): return C.render(a, "hi", CFG)
def render_en(a): return C.render(a, "en", CFG)


_EXTRA = [
    F.f("goods_or_service", "माल/सेवा का विवरण", "Goods/service", section="facts", required=True),
    F.f("transaction_date", "क्रय/सेवा दिनांक", "Transaction date", F.DATE, section="facts"),
    F.f("amount_paid", "अदा प्रतिफल (₹)", "Consideration paid (Rs.)", F.MONEY, True, "facts"),
    F.f("defect_deficiency", "दोष/सेवा में कमी", "Defect / deficiency", F.LONGTEXT, True, "facts"),
    F.f("complaint_date", "शिकायत दिनांक", "Complaint date", F.DATE, section="facts"),
]


def field_spec(court: str = "consumer") -> dict:
    return C.spec(CFG, _EXTRA,
                  companions=["समर्थन में शपथपत्र (अनिवार्य)", "बिल/रसीद एवं पत्राचार की प्रतियाँ",
                              "निर्धारित परिवाद शुल्क", "वकालतनामा"])


SAMPLE = {
    "court": "consumer", "court_city": "इन्दौर", "state_name": "म.प्र.", "suit_number": "____",
    "plaintiff_name": "____", "plaintiff_address": "____, इन्दौर (म.प्र.)",
    "defendant_name": "____ (कम्पनी/विक्रेता)", "defendant_address": "____",
    "goods_or_service": "____", "transaction_date": "____", "amount_paid": "____",
    "defect_deficiency": "____", "complaint_date": "____",
    "cause_of_action_date": "____", "cause_of_action_place": "इन्दौर",
    "valuation": "____", "court_fee": "____", "advocate_name": "____", "filing_date": "__/__/2026",
}


def review_page_html(data=None): return C.review_page_html(CFG, data if data is not None else SAMPLE)
