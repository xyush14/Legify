"""Suit for Recovery of Money (धन वसूली वाद) — Order VII CPC; §34 CPC interest.

Deterministic plaint via the shared civil engine. The transaction paras carry the
case: what was advanced, on which dates, against which documents, then demand +
refusal, then the arithmetic (principal + interest = total). Order XXXVII (summary
suit) is FLAGGED where the claim rests on a written contract / negotiable
instrument, but never assumed. No LLM — facts come from the advocate's fields.
"""
from __future__ import annotations

from headnote.drafter.templates import _civil as C
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "IDBI Trusteeship Services Ltd. v. Hubtown Ltd. (2017) 1 SCC 568",
     "point": "Order XXXVII leave-to-defend spectrum (only if drafted as a summary suit)", "verified": False},
    {"case": "Mechelec Engineers & Manufacturers v. Basic Equipment Corpn. (1976) 4 SCC 687",
     "point": "classic leave-to-defend principles under Order XXXVII", "verified": False},
]

_TXN_HI = {"loan": "उधार/ऋण के रूप में", "goods": "विक्रय किये गये माल के मूल्य स्वरूप",
           "services": "प्रदत्त सेवाओं के प्रतिफल स्वरूप", "advance": "अग्रिम राशि के रूप में"}
_TXN_EN = {"loan": "by way of a loan", "goods": "towards the price of goods sold and delivered",
           "services": "towards the consideration for services rendered", "advance": "by way of an advance"}


def _facts(a, lang, H):
    hi = lang == "hi"
    en = not hi
    txn = (a.get("transaction_type") or "loan")
    txn_txt = (_TXN_HI if hi else _TXN_EN).get(txn, _TXN_HI["loan"] if hi else _TXN_EN["loan"])
    amt = H.ph(C._val(a, "principal_amount", en), "मूल राशि" if hi else "principal")
    adv_date = H.ph(a.get("advance_date"), "दिनांक" if hi else "date")
    docs = H.ph(C._val(a, "documents", en), "दस्तावेज़" if hi else "documents")
    dem_date = H.ph(a.get("demand_date"), "दिनांक" if hi else "date")
    rate = H.ph(a.get("interest_rate"), "____")
    total = H.ph(C._val(a, "claim_amount", en), "कुल राशि" if hi else "total")
    if hi:
        return [
            f'यह कि वादी ने प्रतिवादी को दिनांक {adv_date} को {amt} रुपये की राशि {txn_txt} प्रदान की, '
            f'जिसका साक्ष्य {docs} से प्रकट होता है।',
            f'यह कि प्रतिवादी ने उक्त राशि नियत अवधि में लौटाने का वचन दिया था, किन्तु बार-बार मांग '
            f'किये जाने पर भी राशि अदा नहीं की।',
            f'यह कि वादी द्वारा दिनांक {dem_date} को प्रतिवादी को माँग/विधिक सूचना भेजी गई, फिर भी '
            f'प्रतिवादी ने राशि अदा करने में जानबूझकर व्यतिक्रम किया।',
            f'यह कि प्रतिवादी पर वादी की मूल राशि {amt} रुपये तथा उस पर {rate}% वार्षिक ब्याज सहित, '
            f'वाद प्रस्तुति दिनांक तक कुल {total} रुपये देय एवं शेष हैं।',
        ]
    return [
        f'That on {adv_date} the plaintiff advanced to the defendant a sum of Rs. {amt} {txn_txt}, '
        f'as is evident from {docs}.',
        'That the defendant undertook to repay the said sum within the stipulated period but, despite '
        'repeated demands, has failed and neglected to pay.',
        f'That the plaintiff, by demand/legal notice dated {dem_date}, called upon the defendant to pay, '
        f'yet the defendant has wilfully defaulted.',
        f'That there remains due and payable from the defendant to the plaintiff the principal sum of '
        f'Rs. {amt} together with interest at {rate}% per annum, aggregating to Rs. {total} as on the '
        f'date of the suit.',
    ]


def _prayer(a, lang, H):
    hi = lang == "hi"
    total = H.ph(C._val(a, "claim_amount", not hi), "कुल राशि" if hi else "total")
    if hi:
        return [
            f'प्रतिवादी के विरुद्ध एवं वादी के पक्ष में {total} रुपये की राशि की डिक्री पारित की जावे;',
            'उक्त राशि पर वाद-प्रस्तुति से वसूली दिनांक तक वादकालीन एवं भावी ब्याज (धारा 34 सी.पी.सी.) '
            'दिलाया जावे;',
        ]
    return [
        f'a decree for Rs. {total} in favour of the plaintiff and against the defendant;',
        'pendente-lite and future interest on the said sum from the date of suit till realisation under '
        'Section 34 CPC;',
    ]


CFG = {
    "key": "recovery_suit", "label_hi": "धन वसूली वाद", "label_en": "Suit for Recovery of Money",
    "court": "civil", "section_hi": "आदेश 7 नियम 1 सी.पी.सी.", "section_en": "Order VII Rule 1 CPC",
    "title_hi": "धन वसूली हेतु वाद-पत्र (आदेश 7 नियम 1 सी.पी.सी.)",
    "title_en": "PLAINT FOR RECOVERY OF MONEY (ORDER VII RULE 1 CPC)",
    "p_label_hi": "वादी", "p_label_en": "Plaintiff", "d_label_hi": "प्रतिवादी", "d_label_en": "Defendant",
    "facts": _facts, "prayer": _prayer,
}


def render_hi(a: dict) -> str:
    return C.render(a, "hi", CFG)


def render_en(a: dict) -> str:
    return C.render(a, "en", CFG)


_EXTRA = [
    F.f("transaction_type", "लेन-देन का प्रकार", "Transaction type", F.SELECT, section="facts",
        default="loan", options=[
            {"value": "loan", "label": "ऋण / उधार (loan)"},
            {"value": "goods", "label": "माल का मूल्य (goods sold)"},
            {"value": "services", "label": "सेवाओं का प्रतिफल (services)"},
            {"value": "advance", "label": "अग्रिम राशि (advance)"}]),
    F.f("principal_amount", "मूल राशि (₹)", "Principal amount (Rs.)", F.MONEY, True, "facts"),
    F.f("advance_date", "राशि प्रदान दिनांक", "Date advanced", F.DATE, section="facts"),
    F.f("documents", "आधार दस्तावेज़ (प्रोनोट/बिल/खाता)", "Supporting documents", section="facts",
        hint="pronote / invoice / ledger / bank entry"),
    F.f("demand_date", "माँग/नोटिस दिनांक", "Demand/notice date", F.DATE, section="facts"),
    F.f("interest_rate", "ब्याज दर (% वार्षिक)", "Interest rate (% p.a.)", F.NUMBER, section="facts"),
]


def field_spec(court: str = "civil") -> dict:
    return C.spec(CFG, _EXTRA, amount=True,
                  companions=["दस्तावेज़ों की सूची (आदेश 7 नियम 14) — प्रोनोट/बिल/बैंक विवरण/नोटिस",
                              "मूल्यांकनानुसार न्यायशुल्क", "वकालतनामा"])


SAMPLE = {
    "court": "civil", "court_city": "इन्दौर", "state_name": "म.प्र.",
    "suit_number": "____",
    "plaintiff_name": "____", "plaintiff_address": "____, इन्दौर (म.प्र.)",
    "defendant_name": "____", "defendant_address": "____, इन्दौर (म.प्र.)",
    "transaction_type": "loan", "principal_amount": "2,85,000", "advance_date": "16/07/2018",
    "documents": "प्रतिवादी द्वारा निष्पादित वचन-पत्र (प्रोनोट) एवं बैंक अंतरण विवरण",
    "demand_date": "22/10/2025", "interest_rate": "12", "claim_amount": "5,00,000",
    "cause_of_action_date": "22/10/2025", "cause_of_action_place": "इन्दौर",
    "valuation": "5,00,000", "court_fee": "____", "advocate_name": "____", "filing_date": "__/__/2026",
}


def review_page_html(data=None):
    return C.review_page_html(CFG, data if data is not None else SAMPLE)
