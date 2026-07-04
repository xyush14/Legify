"""Suit for Permanent Injunction (स्थायी निषेधाज्ञा वाद) — §38 Specific Relief Act.

Spine: (1) plaintiff's lawful possession/right over the suit property (full
description with boundaries), (2) the defendant's SPECIFIC dated acts of
interference, (3) why the injury is continuing and not compensable in money.
Jurisdiction = §16 CPC (situs). Always file the Order XXXIX Rules 1-2 temporary-
injunction application (triple test) — flagged as a companion.
"""
from __future__ import annotations

from headnote.drafter.templates import _civil as C
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Dalpat Kumar v. Prahlad Singh (1992) 1 SCC 719",
     "point": "temporary-injunction triple test — prima facie case, balance of convenience, irreparable injury", "verified": False},
    {"case": "Wander Ltd. v. Antox India (P) Ltd. 1990 Supp SCC 727",
     "point": "discretionary injunction — scope of appellate interference", "verified": False},
]


def _facts(a, lang, H):
    hi = lang == "hi"
    en = not hi
    prop = H.ph(C._val(a, "property_description", en), "वादग्रस्त सम्पत्ति का विवरण" if hi else "suit-property description")
    basis = H.ph(C._val(a, "possession_basis", en), "स्वामित्व/कब्जे का आधार" if hi else "basis of title/possession")
    acts = H.ph(C._val(a, "interference_acts", en), "हस्तक्षेप के कृत्य" if hi else "acts of interference")
    idate = H.ph(a.get("interference_date"), "दिनांक" if hi else "date")
    if hi:
        return [
            f'यह कि वादग्रस्त सम्पत्ति निम्नानुसार है ः— {prop}, जिस पर वादी का वैध स्वामित्व एवं '
            f'शान्तिपूर्ण आधिपत्य {basis} के आधार पर निरन्तर बना हुआ है।',
            f'यह कि प्रतिवादी ने दिनांक {idate} को तथा तत्पश्चात् वादी की उक्त सम्पत्ति में विधिविरुद्ध '
            f'रूप से हस्तक्षेप किया, यथा— {acts}।',
            'यह कि प्रतिवादी के उक्त कृत्यों से वादी को निरन्तर एवं अपूरणीय क्षति हो रही है, जिसकी '
            'प्रतिपूर्ति धनराशि द्वारा सम्भव नहीं है, तथा वादी के पास अन्य कोई पर्याप्त उपचार उपलब्ध नहीं है।',
        ]
    return [
        f'That the suit property is described as under:— {prop}, whereof the plaintiff is in lawful and '
        f'peaceful possession by virtue of {basis}.',
        f'That on {idate} and thereafter the defendant unlawfully interfered with the plaintiff\'s said '
        f'property, namely— {acts}.',
        'That by the said acts the plaintiff is suffering continuing and irreparable injury not '
        'compensable in money, and the plaintiff has no other adequate remedy.',
    ]


def _prayer(a, lang, H):
    hi = lang == "hi"
    acts = H.ph(C._val(a, "interference_acts", not hi), "उक्त हस्तक्षेप" if hi else "the said interference")
    if hi:
        return [
            f'प्रतिवादी, उसके कर्मचारी, अभिकर्ता एवं उसकी ओर से कार्य करने वालों के विरुद्ध स्थायी '
            f'निषेधाज्ञा (permanent injunction) की डिक्री पारित की जावे जिससे वे वादग्रस्त सम्पत्ति में '
            f'वादी के शान्तिपूर्ण आधिपत्य में {acts} अथवा किसी भी प्रकार का हस्तक्षेप न करें;',
        ]
    return [
        'a decree of permanent injunction against the defendant, his servants, agents and all persons '
        f'acting on his behalf, restraining them from {acts} or in any manner interfering with the '
        'plaintiff\'s peaceful possession of the suit property;',
    ]


CFG = {
    "key": "injunction_suit", "label_hi": "स्थायी निषेधाज्ञा वाद", "label_en": "Suit for Permanent Injunction",
    "court": "civil",
    "title_hi": "स्थायी निषेधाज्ञा हेतु वाद-पत्र (धारा 38 विनिर्दिष्ट अनुतोष अधिनियम, 1963)",
    "title_en": "PLAINT FOR PERMANENT INJUNCTION (SECTION 38 SPECIFIC RELIEF ACT, 1963)",
    "p_label_hi": "वादी", "p_label_en": "Plaintiff", "d_label_hi": "प्रतिवादी", "d_label_en": "Defendant",
    "facts": _facts, "prayer": _prayer,
    "tail": lambda a, l, H: C.civil_tail(a, l, H, jurisdiction_hi="वादग्रस्त अचल सम्पत्ति (धारा 16 सी.पी.सी.)",
                                         jurisdiction_en="the suit immovable property (Section 16 CPC)"),
}


def render_hi(a): return C.render(a, "hi", CFG)
def render_en(a): return C.render(a, "en", CFG)


_EXTRA = [
    F.f("possession_basis", "स्वामित्व/कब्जे का आधार", "Basis of title/possession", F.LONGTEXT, section="facts",
        hint="विक्रय-पत्र/नामांतरण/पैतृक/किरायेदारी"),
    F.f("interference_acts", "प्रतिवादी के हस्तक्षेप के कृत्य", "Defendant's acts of interference", F.LONGTEXT,
        True, "facts", hint="बेदखली का प्रयास/निर्माण/धमकी — तिथियों सहित"),
    F.f("interference_date", "हस्तक्षेप दिनांक", "Date of interference", F.DATE, section="facts"),
]


def field_spec(court: str = "civil") -> dict:
    return C.spec(CFG, _EXTRA, property_desc=True,
                  companions=["आदेश 39 नियम 1-2 अस्थायी निषेधाज्ञा आवेदन + शपथपत्र (त्रिविध परीक्षण)",
                              "दस्तावेज़ों की सूची (आदेश 7 नियम 14) — स्वत्व/कब्जा पत्र, नक्शा/खसरा", "वकालतनामा"])


SAMPLE = {
    "court": "civil", "court_city": "जयपुर", "state_name": "राजस्थान", "suit_number": "____",
    "plaintiff_name": "____", "plaintiff_address": "____, जयपुर (राजस्थान)",
    "defendant_name": "____", "defendant_address": "____, जयपुर (राजस्थान)",
    "property_description": "आराजी खसरा नं. ____, रकबा ____, स्थित ग्राम ____, चौहद्दी— उत्तर ____, दक्षिण ____, पूर्व ____, पश्चिम ____",
    "possession_basis": "पंजीकृत विक्रय-पत्र दिनांक ____ एवं राजस्व अभिलेख", "interference_acts": "बलपूर्वक बेदखली का प्रयास एवं अवैध निर्माण",
    "interference_date": "____", "cause_of_action_date": "____", "cause_of_action_place": "जयपुर",
    "valuation": "____", "court_fee": "____", "advocate_name": "____", "filing_date": "__/__/2026",
}


def review_page_html(data=None): return C.review_page_html(CFG, data if data is not None else SAMPLE)
