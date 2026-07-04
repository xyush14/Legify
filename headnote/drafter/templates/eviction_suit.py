"""Suit for Eviction & Arrears of Rent (बेदखली एवं बकाया किराया वाद).

Rent control is a STATE subject — the governing Act is state-specific (MP
Accommodation Control Act 1961 / Maharashtra Rent Control Act 1999 / Delhi Rent
Act / WB Premises Tenancy Act 1997 / TN Tenancy Act 2017 / Rajasthan Rent Control
Act 2001, …). The lawyer supplies the Act + the exact ground clause; the engine
never assumes MP. Plead tenancy, the ground with dates, and the quit/demand notice.
"""
from __future__ import annotations

from headnote.drafter.templates import _civil as C
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = []


def _facts(a, lang, H):
    hi = lang == "hi"
    en = not hi
    prem = H.ph(C._val(a, "property_description", en), "किरायेदारी परिसर" if hi else "tenanted premises")
    start = H.ph(a.get("tenancy_start"), "दिनांक" if hi else "date")
    rent = H.ph(C._val(a, "monthly_rent", en), "मासिक किराया" if hi else "monthly rent")
    act = H.ph(C._val(a, "rent_act", en), "राज्य किरायेदारी अधिनियम" if hi else "the State Rent Act")
    ground = H.ph(C._val(a, "eviction_ground", en), "बेदखली का आधार (धारा/खण्ड)" if hi else "the ground (section/clause)")
    notice = H.ph(a.get("notice_date"), "दिनांक" if hi else "date")
    arrears = H.ph(C._val(a, "arrears_amount", en), "बकाया किराया" if hi else "arrears")
    if hi:
        return [
            f'यह कि प्रतिवादी वादी का किरायेदार है तथा निम्नांकित परिसर— {prem} — दिनांक {start} से '
            f'{rent} रुपये मासिक किराये पर उसके आधिपत्य में है।',
            f'यह कि प्रतिवादी के विरुद्ध {act} के अन्तर्गत {ground} का आधार उपलब्ध है, जिसके तथ्य '
            f'सुस्पष्ट रूप से इस प्रकार हैं ः— प्रतिवादी दिनांक ____ से किराया अदा करने में व्यतिक्रमी '
            f'है तथा कुल {arrears} रुपये का बकाया किराया देय है।',
            f'यह कि वादी ने प्रतिवादी को दिनांक {notice} को माँग/बेदखली सूचना (quit notice) दी, जो '
            f'तामील होने के बावजूद प्रतिवादी ने न तो बकाया अदा किया और न ही परिसर रिक्त किया।',
        ]
    return [
        f'That the defendant is the plaintiff\'s tenant in respect of the following premises— {prem} — '
        f'since {start} at a monthly rent of Rs. {rent}.',
        f'That a ground of eviction under {act}, namely {ground}, is available against the defendant on '
        f'the following facts:— the defendant has been in default of rent since ____ and a sum of '
        f'Rs. {arrears} is due as arrears.',
        f'That the plaintiff served a demand/quit notice dated {notice} upon the defendant, who despite '
        f'service neither paid the arrears nor vacated the premises.',
    ]


def _prayer(a, lang, H):
    hi = lang == "hi"
    arrears = H.ph(C._val(a, "arrears_amount", not hi), "बकाया किराया" if hi else "arrears")
    if hi:
        return [
            'प्रतिवादी को उक्त परिसर से बेदखल कर उसका रिक्त एवं शान्तिपूर्ण आधिपत्य वादी को दिलाया जावे;',
            f'बकाया किराया {arrears} रुपये तथा परिसर रिक्त होने तक मध्यवर्ती लाभ/उपयोग-प्रभार वादी को '
            f'दिलाये जावें;',
        ]
    return [
        'a decree of eviction directing the defendant to hand over vacant and peaceful possession of the '
        'premises to the plaintiff;',
        f'a decree for arrears of rent of Rs. {arrears} and mesne profits / occupation charges till '
        f'possession is delivered;',
    ]


CFG = {
    "key": "eviction_suit", "label_hi": "बेदखली एवं बकाया किराया वाद", "label_en": "Suit for Eviction & Arrears of Rent",
    "court": "civil",
    "title_hi": "बेदखली एवं बकाया किराया हेतु वाद-पत्र (राज्य किरायेदारी/स्थान नियंत्रण अधिनियम)",
    "title_en": "PLAINT FOR EVICTION & ARREARS OF RENT (STATE RENT-CONTROL ACT)",
    "p_label_hi": "वादी (मकान-स्वामी)", "p_label_en": "Plaintiff (Landlord)",
    "d_label_hi": "प्रतिवादी (किरायेदार)", "d_label_en": "Defendant (Tenant)",
    "facts": _facts, "prayer": _prayer,
    "tail": lambda a, l, H: C.civil_tail(a, l, H, jurisdiction_hi="वादग्रस्त किरायेदारी परिसर (धारा 16 सी.पी.सी.)",
                                         jurisdiction_en="the tenanted premises (Section 16 CPC)"),
}


def render_hi(a): return C.render(a, "hi", CFG)
def render_en(a): return C.render(a, "en", CFG)


_EXTRA = [
    F.f("rent_act", "लागू किरायेदारी/स्थान नियंत्रण अधिनियम", "Applicable State Rent-Control Act", section="facts",
        hint="जैसे म.प्र. स्थान नियंत्रण अधिनियम 1961 / महाराष्ट्र रेंट कंट्रोल एक्ट 1999"),
    F.f("eviction_ground", "बेदखली का आधार (धारा/खण्ड + तथ्य)", "Ground of eviction (clause + facts)", F.LONGTEXT, True, "facts"),
    F.f("tenancy_start", "किरायेदारी प्रारम्भ दिनांक", "Tenancy start date", F.DATE, section="facts"),
    F.f("monthly_rent", "मासिक किराया (₹)", "Monthly rent (Rs.)", F.MONEY, section="facts"),
    F.f("arrears_amount", "बकाया किराया (₹)", "Arrears of rent (Rs.)", F.MONEY, section="facts"),
    F.f("notice_date", "माँग/बेदखली सूचना दिनांक", "Demand/quit-notice date", F.DATE, section="facts"),
]


def field_spec(court: str = "civil") -> dict:
    return C.spec(CFG, _EXTRA, property_desc=True,
                  companions=["माँग/बेदखली सूचना + तामील प्रमाण (पंजीकृत डाक ए.डी.)",
                              "दस्तावेज़ों की सूची (आदेश 7 नियम 14) — किरायानामा/रसीदें, सूचना", "वकालतनामा"])


SAMPLE = {
    "court": "civil", "court_city": "भोपाल", "state_name": "म.प्र.", "suit_number": "____",
    "plaintiff_name": "____", "plaintiff_address": "____, भोपाल (म.प्र.)",
    "defendant_name": "____", "defendant_address": "____, भोपाल (म.प्र.)",
    "property_description": "दुकान/मकान क्रमांक ____, स्थित ____, भोपाल", "rent_act": "म.प्र. स्थान नियंत्रण अधिनियम, 1961",
    "eviction_ground": "धारा 12(1)(अ) — किराया बकाया; तथा धारा 12(1)(च) — वास्तविक आवश्यकता",
    "tenancy_start": "____", "monthly_rent": "____", "arrears_amount": "____", "notice_date": "____",
    "cause_of_action_date": "____", "cause_of_action_place": "भोपाल",
    "valuation": "____", "court_fee": "____", "advocate_name": "____", "filing_date": "__/__/2026",
}


def review_page_html(data=None): return C.review_page_html(CFG, data if data is not None else SAMPLE)
