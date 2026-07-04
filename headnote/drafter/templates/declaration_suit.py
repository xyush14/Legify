"""Suit for Declaration (घोषणा वाद) — §34 Specific Relief Act.

Plead the plaintiff's title/right chain, then the defendant's DENIAL / the cloud
cast on it (with dates) — that denial is the cause of action. THE PROVISO TRAP:
where further relief (possession/injunction/cancellation) is available, a bare
declaration is barred — so consequential relief is pleaded as a dedicated para +
prayer clause. Limitation Art. 58.
"""
from __future__ import annotations

from headnote.drafter.templates import _civil as C
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Anathula Sudhakar v. P. Buchi Reddy (2008) 4 SCC 594",
     "point": "when a suit needs declaration of title vs injunction simpliciter — the classic exposition", "verified": False},
]


def _facts(a, lang, H):
    hi = lang == "hi"
    en = not hi
    right = H.ph(C._val(a, "right_claimed", en), "अधिकार/स्वत्व" if hi else "right/title")
    chain = H.ph(C._val(a, "title_chain", en), "स्वत्व की श्रृंखला" if hi else "chain of title")
    denial = H.ph(C._val(a, "denial_acts", en), "प्रतिवादी का इन्कार/बादल" if hi else "the defendant's denial/cloud")
    ddate = H.ph(a.get("denial_date"), "दिनांक" if hi else "date")
    conseq = H.ph(C._val(a, "consequential_relief", en), "आनुषंगिक अनुतोष" if hi else "consequential relief")
    if hi:
        return [
            f'यह कि वादी {right} का विधिपूर्ण स्वामी/अधिकारी है, जो {chain} से सिद्ध होता है।',
            f'यह कि प्रतिवादी ने दिनांक {ddate} को वादी के उक्त अधिकार/स्वत्व को अस्वीकार करते हुए '
            f'उस पर बादल (cloud) उत्पन्न किया, यथा— {denial}, जो प्रस्तुत वाद का कारण है।',
            f'यह कि वादी के अधिकार की घोषणा के साथ-साथ आनुषंगिक अनुतोष— {conseq} — आवश्यक है, अतः '
            f'धारा 34 के परन्तुक की बाधा उपस्थित नहीं होती।',
        ]
    return [
        f'That the plaintiff is the lawful owner/holder of {right}, as established by {chain}.',
        f'That on {ddate} the defendant denied the plaintiff\'s said right/title and cast a cloud upon '
        f'it, namely— {denial}, which constitutes the cause of action.',
        f'That along with a declaration of the plaintiff\'s right, consequential relief— {conseq} — is '
        f'necessary, and hence the bar of the proviso to Section 34 is not attracted.',
    ]


def _prayer(a, lang, H):
    hi = lang == "hi"
    right = H.ph(C._val(a, "right_claimed", not hi), "उक्त अधिकार/स्वत्व" if hi else "the said right/title")
    conseq = H.ph(C._val(a, "consequential_relief", not hi), "आनुषंगिक अनुतोष" if hi else "the consequential relief")
    if hi:
        return [
            f'वादी के पक्ष में यह घोषणा (declaration) की जावे कि वादी {right} का विधिपूर्ण स्वामी/अधिकारी है;',
            f'तदनुसार आनुषंगिक अनुतोष— {conseq} — भी वादी को प्रदान किया जावे;',
        ]
    return [
        f'a decree declaring that the plaintiff is the lawful owner/holder of {right};',
        f'the consequential relief of {conseq} be also granted to the plaintiff accordingly;',
    ]


CFG = {
    "key": "declaration_suit", "label_hi": "घोषणा वाद", "label_en": "Suit for Declaration", "court": "civil",
    "title_hi": "घोषणा एवं आनुषंगिक अनुतोष हेतु वाद-पत्र (धारा 34 विनिर्दिष्ट अनुतोष अधिनियम, 1963)",
    "title_en": "PLAINT FOR DECLARATION (SECTION 34 SPECIFIC RELIEF ACT, 1963)",
    "p_label_hi": "वादी", "p_label_en": "Plaintiff", "d_label_hi": "प्रतिवादी", "d_label_en": "Defendant",
    "facts": _facts, "prayer": _prayer,
}


def render_hi(a): return C.render(a, "hi", CFG)
def render_en(a): return C.render(a, "en", CFG)


_EXTRA = [
    F.f("right_claimed", "जिस अधिकार/स्वत्व की घोषणा चाहिए", "Right/title to be declared", F.LONGTEXT, True, "facts"),
    F.f("title_chain", "स्वत्व की श्रृंखला (दस्तावेज़/तिथि)", "Chain of title (documents/dates)", F.LONGTEXT, section="facts"),
    F.f("denial_acts", "प्रतिवादी का इन्कार/बादल", "Defendant's denial / cloud", F.LONGTEXT, True, "facts"),
    F.f("denial_date", "इन्कार दिनांक", "Date of denial", F.DATE, section="facts"),
    F.f("consequential_relief", "आवश्यक आनुषंगिक अनुतोष", "Consequential relief needed", section="facts",
        hint="कब्ज़ा / निषेधाज्ञा / विलेख निरस्तीकरण"),
]


def field_spec(court: str = "civil") -> dict:
    return C.spec(CFG, _EXTRA, property_desc=True,
                  companions=["दस्तावेज़ों की सूची (आदेश 7 नियम 14) — स्वत्व पत्र, राजस्व अभिलेख",
                              "मूल्यांकनानुसार न्यायशुल्क (धारा 7(iv)(c))", "वकालतनामा"])


SAMPLE = {
    "court": "civil", "court_city": "इन्दौर", "state_name": "म.प्र.", "suit_number": "____",
    "plaintiff_name": "____", "plaintiff_address": "____, इन्दौर (म.प्र.)",
    "defendant_name": "____", "defendant_address": "____, इन्दौर (म.प्र.)",
    "right_claimed": "आराजी खसरा नं. ____ का स्वामित्व", "title_chain": "पंजीकृत विक्रय-पत्र दिनांक ____ एवं नामांतरण",
    "denial_acts": "प्रतिवादी द्वारा फर्जी नामांतरण के आधार पर स्वत्व का दावा", "denial_date": "____",
    "consequential_relief": "स्थायी निषेधाज्ञा", "cause_of_action_date": "____", "cause_of_action_place": "इन्दौर",
    "valuation": "____", "court_fee": "____", "advocate_name": "____", "filing_date": "__/__/2026",
}


def review_page_html(data=None): return C.review_page_html(CFG, data if data is not None else SAMPLE)
