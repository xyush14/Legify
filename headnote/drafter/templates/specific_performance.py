"""Suit for Specific Performance (विनिर्दिष्ट अनुपालन वाद) — §10 Specific Relief Act.

THE FATAL TRAP is §16(c): the plaint MUST aver the plaintiff's CONTINUOUS
readiness and willingness to perform, from the agreement date to filing — the
engine hard-codes that averment as a dedicated para so it can never be omitted.
Limitation Art. 54. Alternative relief (refund of earnest + interest/damages) is
pleaded in the prayer. Companion: Order XXXIX application to restrain alienation.
"""
from __future__ import annotations

from headnote.drafter.templates import _civil as C
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Kamal Kumar v. Premlata Joshi (2019) 3 SCC 704",
     "point": "the material questions a specific-performance plaintiff must plead and prove", "verified": False},
    {"case": "Saradamani Kandappan v. S. Rajalakshmi (2011) 12 SCC 18",
     "point": "time / price-escalation and payment default in agreements to sell", "verified": False},
]


def _facts(a, lang, H):
    hi = lang == "hi"
    en = not hi
    adate = H.ph(a.get("agreement_date"), "दिनांक" if hi else "date")
    prop = H.ph(C._val(a, "property_description", en), "सम्पत्ति विवरण" if hi else "property description")
    cons = H.ph(C._val(a, "total_consideration", en), "कुल प्रतिफल" if hi else "consideration")
    earnest = H.ph(C._val(a, "earnest_paid", en), "बयाना राशि" if hi else "earnest")
    perf_date = H.ph(a.get("performance_date"), "नियत दिनांक" if hi else "the date fixed")
    breach = H.ph(a.get("refusal_date"), "दिनांक" if hi else "date")
    if hi:
        return [
            f'यह कि प्रतिवादी ने वादी के पक्ष में दिनांक {adate} को निम्नांकित सम्पत्ति के विक्रय हेतु '
            f'इकरारनामा (agreement to sell) निष्पादित किया ः— {prop}, कुल प्रतिफल {cons} रुपये में।',
            f'यह कि वादी ने उक्त इकरारनामे के अन्तर्गत बयाना/अग्रिम राशि {earnest} रुपये प्रतिवादी को '
            f'अदा की, जिसकी रसीद प्रतिवादी द्वारा दी गई।',
            f'यह कि इकरारनामे के अनुसार विक्रय-पत्र दिनांक {perf_date} को निष्पादित एवं पंजीकृत किया '
            f'जाना था।',
            'यह कि वादी इकरारनामे की दिनांक से आज पर्यन्त अपने भाग का सम्पूर्ण अनुपालन करने हेतु सदैव '
            'तैयार एवं तत्पर रहा है (धारा 16(ग) विनिर्दिष्ट अनुतोष अधिनियम) तथा शेष प्रतिफल अदा करने को '
            'आज भी तैयार है।',
            f'यह कि इसके विपरीत प्रतिवादी ने दिनांक {breach} को विक्रय-पत्र निष्पादित करने से इन्कार कर '
            f'इकरारनामे का उल्लंघन किया है।',
        ]
    return [
        f'That on {adate} the defendant executed an agreement to sell in favour of the plaintiff in '
        f'respect of the following property:— {prop}, for a total consideration of Rs. {cons}.',
        f'That the plaintiff paid earnest/part consideration of Rs. {earnest} to the defendant '
        f'thereunder, receipt whereof was acknowledged by the defendant.',
        f'That under the agreement the sale deed was to be executed and registered on {perf_date}.',
        'That the plaintiff has been, and continues to be, ready and willing to perform his part of the '
        'agreement from its date till date (Section 16(c) Specific Relief Act), and remains ready to pay '
        'the balance consideration.',
        f'That the defendant, on the contrary, has on {breach} refused to execute the sale deed and has '
        f'thereby breached the agreement.',
    ]


def _prayer(a, lang, H):
    hi = lang == "hi"
    earnest = H.ph(C._val(a, "earnest_paid", not hi), "बयाना राशि" if hi else "earnest")
    if hi:
        return [
            'प्रतिवादी को आदेशित किया जावे कि वह इकरारनामे का विनिर्दिष्ट अनुपालन करते हुए वादी के पक्ष '
            'में शेष प्रतिफल प्राप्त कर विक्रय-पत्र निष्पादित एवं पंजीकृत करे, व्यतिक्रम की दशा में '
            'न्यायालय के माध्यम से विक्रय-पत्र निष्पादित कराया जावे;',
            f'वैकल्पिक रूप से, यदि विनिर्दिष्ट अनुपालन सम्भव न हो तो बयाना राशि {earnest} रुपये ब्याज '
            f'सहित एवं क्षतिपूर्ति वादी को दिलाई जावे;',
        ]
    return [
        'a decree for specific performance directing the defendant to execute and register the sale '
        'deed in favour of the plaintiff on receipt of the balance consideration, and in default to have '
        'it executed through the Court;',
        f'in the alternative, if specific performance be refused, a decree for refund of the earnest of '
        f'Rs. {earnest} with interest and damages;',
    ]


CFG = {
    "key": "specific_performance", "label_hi": "विनिर्दिष्ट अनुपालन वाद", "label_en": "Suit for Specific Performance",
    "court": "civil",
    "title_hi": "विनिर्दिष्ट अनुपालन हेतु वाद-पत्र (धारा 10 विनिर्दिष्ट अनुतोष अधिनियम, 1963)",
    "title_en": "PLAINT FOR SPECIFIC PERFORMANCE (SECTION 10 SPECIFIC RELIEF ACT, 1963)",
    "p_label_hi": "वादी", "p_label_en": "Plaintiff", "d_label_hi": "प्रतिवादी", "d_label_en": "Defendant",
    "facts": _facts, "prayer": _prayer,
    "tail": lambda a, l, H: C.civil_tail(a, l, H, jurisdiction_hi="वादग्रस्त अचल सम्पत्ति (धारा 16 सी.पी.सी.)",
                                         jurisdiction_en="the suit immovable property (Section 16 CPC)"),
}


def render_hi(a): return C.render(a, "hi", CFG)
def render_en(a): return C.render(a, "en", CFG)


_EXTRA = [
    F.f("total_consideration", "कुल प्रतिफल (₹)", "Total consideration (Rs.)", F.MONEY, True, "facts"),
    F.f("earnest_paid", "बयाना/अग्रिम राशि (₹)", "Earnest/part payment (Rs.)", F.MONEY, section="facts"),
    F.f("performance_date", "अनुपालन हेतु नियत दिनांक", "Date fixed for performance", F.DATE, section="facts"),
    F.f("refusal_date", "इन्कार/उल्लंघन दिनांक", "Refusal/breach date", F.DATE, section="facts"),
]


def field_spec(court: str = "civil") -> dict:
    return C.spec(CFG, _EXTRA, property_desc=True, agreement=True,
                  companions=["आदेश 39 आवेदन — सम्पत्ति के अन्तरण पर रोक हेतु + शपथपत्र",
                              "दस्तावेज़ों की सूची (आदेश 7 नियम 14) — इकरारनामा, रसीदें, नोटिस", "वकालतनामा"])


SAMPLE = {
    "court": "civil", "court_city": "जबलपुर", "state_name": "म.प्र.", "suit_number": "____",
    "plaintiff_name": "____", "plaintiff_address": "____, जबलपुर (म.प्र.)",
    "defendant_name": "____", "defendant_address": "____, जबलपुर (म.प्र.)",
    "agreement_date": "____", "property_description": "मकान/भूखण्ड क्रमांक ____, स्थित ____, चौहद्दी सहित",
    "total_consideration": "____", "earnest_paid": "____", "performance_date": "____", "refusal_date": "____",
    "cause_of_action_date": "____", "cause_of_action_place": "जबलपुर",
    "valuation": "____", "court_fee": "____", "advocate_name": "____", "filing_date": "__/__/2026",
}


def review_page_html(data=None): return C.review_page_html(CFG, data if data is not None else SAMPLE)
