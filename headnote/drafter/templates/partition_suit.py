"""Suit for Partition & Separate Possession (बंटवारा वाद) — Order VII CPC.

Open with the वंशावली (genealogy) establishing co-ownership; then the SCHEDULE of
joint properties; then the plaintiff's share as a fraction WITH its basis
(succession/coparcenary — daughters are equal coparceners, Vineeta Sharma); then
the demand for partition and refusal (the cause of action). Two-decree prayer:
preliminary decree declaring the share → final decree by commissioner (Order XXVI).
"""
from __future__ import annotations

from headnote.drafter.templates import _civil as C
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Vineeta Sharma v. Rakesh Sharma (2020) 9 SCC 1",
     "point": "daughters are coparceners by birth — equal share (Hindu Succession Act §6 as amended)", "verified": False},
]


def _facts(a, lang, H):
    hi = lang == "hi"
    en = not hi
    geneology = H.ph(C._val(a, "genealogy", en), "वंशावली" if hi else "genealogy / family tree")
    prop = H.ph(C._val(a, "property_description", en), "संयुक्त सम्पत्ति की सूची" if hi else "schedule of joint properties")
    share = H.ph(C._val(a, "share_fraction", en), "अंश (भिन्न)" if hi else "share (fraction)")
    basis = H.ph(C._val(a, "share_basis", en), "अंश का आधार" if hi else "basis of the share")
    dem = H.ph(a.get("demand_date"), "दिनांक" if hi else "date")
    possession = (a.get("possession_status") or "joint")
    poss_hi = "संयुक्त आधिपत्य में" if possession == "joint" else "आधिपत्य से बहिष्कृत"
    poss_en = "in joint possession" if possession == "joint" else "excluded from possession"
    if hi:
        return [
            f'यह कि पक्षकारगण एक ही संयुक्त हिन्दू परिवार/सहदायिकी के सदस्य हैं, जिसकी वंशावली '
            f'निम्नानुसार है ः— {geneology}, जिसके आधार पर पक्षकारगण सह-अंशधारी (co-sharers) हैं।',
            f'यह कि निम्नांकित संयुक्त सम्पत्तियाँ बँटवारे योग्य हैं ः— {prop}।',
            f'यह कि उक्त संयुक्त सम्पत्ति में वादी का {share} अंश है, जो {basis} के आधार पर है; वादी '
            f'वर्तमान में उक्त सम्पत्ति में {poss_hi} है।',
            f'यह कि वादी ने दिनांक {dem} को प्रतिवादीगण से पृथक बँटवारे एवं आधिपत्य की माँग की, किन्तु '
            f'प्रतिवादीगण ने बँटवारा करने से इन्कार कर दिया, जो प्रस्तुत वाद का कारण है।',
        ]
    return [
        f'That the parties are members of one joint Hindu family / coparcenary, whose genealogy is as '
        f'under:— {geneology}, whereby the parties are co-sharers.',
        f'That the following joint properties are liable to partition:— {prop}.',
        f'That the plaintiff holds a {share} share in the said joint property by virtue of {basis}; the '
        f'plaintiff is presently {poss_en}.',
        f'That on {dem} the plaintiff demanded separate partition and possession from the defendants, '
        f'who refused to effect partition, which is the cause of action.',
    ]


def _prayer(a, lang, H):
    hi = lang == "hi"
    share = H.ph(C._val(a, "share_fraction", not hi), "अंश" if hi else "share")
    if hi:
        return [
            f'प्रारम्भिक डिक्री (preliminary decree) द्वारा यह घोषित किया जावे कि वादी उक्त संयुक्त '
            f'सम्पत्ति में {share} अंश का हकदार है;',
            'न्यायालय आयुक्त (Commissioner, आदेश 26 सी.पी.सी.) की नियुक्ति कर सम्पत्ति का वास्तविक '
            'बँटवारा कराते हुए वादी को उसके अंश का पृथक आधिपत्य दिलाया जावे;',
            'वादी को उसके अंश के अनुसार मध्यवर्ती लाभ (mesne profits) भी दिलाये जावें;',
        ]
    return [
        f'a preliminary decree declaring that the plaintiff is entitled to a {share} share in the said '
        f'joint property;',
        'appointment of a Commissioner (Order XXVI CPC) to effect actual partition and to deliver to the '
        'plaintiff separate possession of his share;',
        'mesne profits in respect of the plaintiff\'s share be also awarded;',
    ]


CFG = {
    "key": "partition_suit", "label_hi": "बंटवारा वाद", "label_en": "Suit for Partition", "court": "civil",
    "title_hi": "बँटवारा एवं पृथक आधिपत्य हेतु वाद-पत्र (आदेश 7 नियम 1 सी.पी.सी.)",
    "title_en": "PLAINT FOR PARTITION & SEPARATE POSSESSION (ORDER VII RULE 1 CPC)",
    "p_label_hi": "वादी", "p_label_en": "Plaintiff", "d_label_hi": "प्रतिवादीगण", "d_label_en": "Defendants",
    "facts": _facts, "prayer": _prayer,
    "tail": lambda a, l, H: C.civil_tail(a, l, H, jurisdiction_hi="वादग्रस्त संयुक्त अचल सम्पत्ति (धारा 16 सी.पी.सी.)",
                                         jurisdiction_en="the joint immovable property (Section 16 CPC)"),
}


def render_hi(a): return C.render(a, "hi", CFG)
def render_en(a): return C.render(a, "en", CFG)


_EXTRA = [
    F.f("genealogy", "वंशावली (परिवार वृक्ष)", "Genealogy (family tree)", F.LONGTEXT, True, "facts",
        hint="पक्षकार किस प्रकार सह-अंशधारी हैं"),
    F.f("share_fraction", "वादी का अंश (भिन्न)", "Plaintiff's share (fraction)", section="facts", hint="जैसे 1/4"),
    F.f("share_basis", "अंश का आधार", "Basis of the share", section="facts", hint="उत्तराधिकार/सहदायिकी"),
    F.f("possession_status", "आधिपत्य की स्थिति", "Possession status", F.SELECT, section="facts", default="joint",
        options=[{"value": "joint", "label": "संयुक्त आधिपत्य (fixed fee)"},
                 {"value": "excluded", "label": "आधिपत्य से बहिष्कृत (ad valorem)"}]),
    F.f("demand_date", "बँटवारे की माँग दिनांक", "Date of demand for partition", F.DATE, section="facts"),
]


def field_spec(court: str = "civil") -> dict:
    return C.spec(CFG, _EXTRA, property_desc=True,
                  companions=["दस्तावेज़ों की सूची (आदेश 7 नियम 14) — राजस्व अभिलेख, नामांतरण, पारिवारिक दस्तावेज़",
                              "वकालतनामा"])


SAMPLE = {
    "court": "civil", "court_city": "ग्वालियर", "state_name": "म.प्र.", "suit_number": "____",
    "plaintiff_name": "____", "plaintiff_address": "____, ग्वालियर (म.प्र.)",
    "defendant_name": "____ आदि", "defendant_address": "____, ग्वालियर (म.प्र.)",
    "genealogy": "स्व. ____ के तीन पुत्र— ____, ____ एवं वादी; प्रत्येक शाखा सह-अंशधारी",
    "property_description": "कृषि भूमि खसरा नं. ____ एवं आवासीय मकान ____, चौहद्दी सहित",
    "share_fraction": "1/3", "share_basis": "पैतृक उत्तराधिकार", "possession_status": "joint", "demand_date": "____",
    "cause_of_action_date": "____", "cause_of_action_place": "ग्वालियर",
    "valuation": "____", "court_fee": "____", "advocate_name": "____", "filing_date": "__/__/2026",
}


def review_page_html(data=None): return C.review_page_html(CFG, data if data is not None else SAMPLE)
