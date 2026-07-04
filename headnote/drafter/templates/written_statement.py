"""Written Statement (जवाबदावा / लिखित कथन) — Order VIII CPC.

The DEFENDANT's reply to a plaint. Rigid structure: (1) प्रारंभिक आपत्तियां —
preliminary objections; (2) परिच्छेदवार जवाब — a PARA-WISE reply to every plaint
para (Order VIII Rules 3-5: an evasive/general denial is DEEMED ADMISSION — deny
each allegation specifically); (3) विशेष कथन — the defendant's affirmative case.
Prayer: dismissal with costs. Filed & signed by the DEFENDANT. Verification O6 R15.
"""
from __future__ import annotations

from headnote.drafter.templates import _civil as C
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Balraj Taneja v. Sunil Madan (1999) 8 SCC 396",
     "point": "non-traverse / evasive denial in the written statement — consequences (O8 R3-5)", "verified": False},
]


def _lines(v):
    return [x.strip() for x in str(v or "").replace("\r", "").split("\n") if x.strip()]


def _blocks(v):
    return [x.strip() for x in str(v or "").split("\n\n") if x.strip()]


def _facts(a, lang, H):
    hi = lang == "hi"
    en = not hi
    P = []
    # 1) preliminary objections
    P.append({"head": "प्रारंभिक आपत्तियां" if hi else "PRELIMINARY OBJECTIONS"})
    objs = _lines(C._val(a, "prelim_objections", en))
    if objs:
        for o in objs:
            P.append((f'यह कि {H.esc(o)}' if hi else f'That {H.esc(o)}'))
    else:
        P.append(H.ph(None, "[परिसीमा/अधिकारिता/मूल्यांकन/कुसंयोजन/वाद-हेतुक का अभाव — प्रत्येक पृथक कण्डिका]"
                      if hi else "[limitation / jurisdiction / valuation / misjoinder / no cause of action]"))
    # 2) para-wise reply
    P.append({"head": "परिच्छेदवार जवाब" if hi else "PARA-WISE REPLY"})
    reply = _blocks(C._val(a, "para_wise_reply", en))
    if reply:
        for r in reply:
            P.append(H.esc(r))
    else:
        P.append(H.ph(None, "[वाद की प्रत्येक कण्डिका का क्रमवार उत्तर — विशिष्ट स्वीकार/अस्वीकार; कोई "
                      "टालमटोल इन्कार नहीं (आदेश 8 नियम 3-5)]" if hi else
                      "[a specific admission or denial of each plaint paragraph in order — no evasive "
                      "denials (Order VIII Rules 3-5)]"))
    # 3) special pleas (defendant's affirmative case)
    P.append({"head": "विशेष कथन" if hi else "SPECIAL PLEAS"})
    special = _blocks(C._val(a, "special_pleas", en))
    if special:
        for s in special:
            P.append((f'यह कि {H.esc(s)}' if hi else f'That {H.esc(s)}'))
    else:
        P.append(H.ph(None, "[प्रतिवादी का सकारात्मक पक्ष — तिथियों सहित]" if hi
                      else "[the defendant's affirmative facts, with dates]"))
    return P


def _prayer(a, lang, H):
    hi = lang == "hi"
    if hi:
        return ['वादी का वाद सव्यय निरस्त किया जावे;']
    return ['the plaintiff\'s suit be dismissed with costs;']


CFG = {
    "key": "written_statement", "label_hi": "जवाबदावा (लिखित कथन)", "label_en": "Written Statement", "court": "civil",
    "title_hi": "जवाबदावा / लिखित कथन (आदेश 8 नियम 1 सी.पी.सी.)",
    "title_en": "WRITTEN STATEMENT (ORDER VIII RULE 1 CPC)",
    "p_label_hi": "वादी", "p_label_en": "Plaintiff", "d_label_hi": "प्रतिवादी", "d_label_en": "Defendant",
    "signer_hi": "प्रतिवादी", "signer_en": "Defendant",
    "lead_hi": "प्रतिवादी उपरोक्त वादी के वाद के उत्तर में सादर निवेदन करता/करती है ः—",
    "lead_en": "The defendant, in reply to the plaintiff's suit, most respectfully submits as under:—",
    "facts": _facts, "prayer": _prayer, "tail": None,
}


def render_hi(a): return C.render(a, "hi", CFG)
def render_en(a): return C.render(a, "en", CFG)


_EXTRA = [
    F.f("prelim_objections", "प्रारंभिक आपत्तियां (प्रति पंक्ति एक)", "Preliminary objections (one per line)",
        F.LONGTEXT, section="facts", hint="परिसीमा / अधिकारिता / मूल्यांकन / कुसंयोजन / वाद-हेतुक का अभाव"),
    F.f("para_wise_reply", "परिच्छेदवार जवाब (प्रति उत्तर खाली पंक्ति से अलग)", "Para-wise reply (blank line between)",
        F.LONGTEXT, section="facts", hint="वाद की प्रत्येक कण्डिका का विशिष्ट स्वीकार/अस्वीकार"),
    F.f("special_pleas", "विशेष कथन (खाली पंक्ति से अलग)", "Special pleas (blank line between)",
        F.LONGTEXT, section="facts", hint="प्रतिवादी का सकारात्मक पक्ष"),
]


def field_spec(court: str = "civil") -> dict:
    return C.spec(CFG, _EXTRA,
                  companions=["प्रतिवादी द्वारा भरोसा किये दस्तावेज़ों की सूची",
                              "प्रतिदावा हो तो उस पर पृथक न्यायशुल्क (आदेश 8 नियम 6अ)", "वकालतनामा"])


SAMPLE = {
    "court": "civil", "court_city": "इन्दौर", "state_name": "म.प्र.", "suit_number": "____",
    "plaintiff_name": "____", "plaintiff_address": "____, इन्दौर (म.प्र.)",
    "defendant_name": "____", "defendant_address": "____, इन्दौर (म.प्र.)",
    "prelim_objections": ("प्रस्तुत वाद परिसीमा अवधि से बाधित है।\n"
                          "वाद का मूल्यांकन एवं न्यायशुल्क त्रुटिपूर्ण है।\n"
                          "वाद में कोई वाद-हेतुक उत्पन्न नहीं होता।"),
    "para_wise_reply": ("वाद की कण्डिका 1 स्वीकार है।\n\nकण्डिका 2 के कथन असत्य होने से अस्वीकार हैं।"),
    "special_pleas": "प्रतिवादी ने विवादित राशि पूर्व में ही अदा कर दी थी, जिसकी रसीद संलग्न है।",
    "cause_of_action_place": "इन्दौर", "advocate_name": "____", "filing_date": "__/__/2026",
}


def review_page_html(data=None): return C.review_page_html(CFG, data if data is not None else SAMPLE)
