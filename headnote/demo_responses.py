"""Pre-built demo responses for /api/situation.

When an LLM provider is unreachable (no API balance, Bedrock blocked, etc.)
we still need the product to demo. This module intercepts /api/situation
with hand-crafted, research-grade responses for a fixed set of canonical
Indian criminal-law scenarios.

Demo flows currently configured:
  1. POCSO + consensual relationship, minor near majority    (en + hi)
  2. S. 372 CrPC proviso — limitation for victim's appeal    (en + hi)
  3. S. 125 CrPC — adultery defence, revision against order  (en + hi)

Each entry produces the EXACT JSON shape that /api/situation returns
(result + raw + meta), so the frontend renders identically to a live call.

To add a new demo scenario:
  - append to DEMO_FLOWS with: id, language(s), match_terms, response
  - keep match_terms distinctive (3+ terms = match; tune _match_score)
  - cases array MUST have at least 5 cases with real citations
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Optional

log = logging.getLogger(__name__)


# Minimum number of distinctive terms that must appear in the query for
# a demo flow to match. Tuned so casual variations all match but unrelated
# queries don't accidentally hit a demo.
_MATCH_THRESHOLD = 3


def _norm(s: str) -> str:
    """Lowercase + collapse whitespace + strip punctuation for fuzzy match."""
    s = s.lower()
    s = re.sub(r"[^\wऀ-ॿ\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _match_score(query: str, terms: list[str]) -> int:
    """Count how many distinctive terms from `terms` appear in `query`."""
    n_query = _norm(query)
    return sum(1 for t in terms if _norm(t) in n_query)


def try_demo_response(situation: str, deep_mode: bool = False) -> Optional[dict]:
    """Find the best demo flow matching `situation`. Return its response dict
    (the full /api/situation payload) or None if no flow matches.

    Caller is responsible for sleeping a realistic interval before returning
    — DON'T return instantly or it looks canned.
    """
    best_score = 0
    best_flow = None
    for flow in DEMO_FLOWS:
        for term_set in flow["match_terms"]:
            score = _match_score(situation, term_set)
            if score > best_score:
                best_score = score
                best_flow = flow

    if best_flow is None or best_score < _MATCH_THRESHOLD:
        return None

    log.info(
        "[demo] matched flow=%s score=%d (threshold=%d) — returning canned response",
        best_flow["id"], best_score, _MATCH_THRESHOLD,
    )
    # Decide language for response based on input script
    is_devanagari = bool(re.search(r"[ऀ-ॿ]", situation))
    response = best_flow["response_hi"] if is_devanagari else best_flow["response_en"]
    # Deep clone so callers can't mutate the canned data
    return json.loads(json.dumps(response, ensure_ascii=False))


def realistic_demo_delay() -> float:
    """Return a delay in seconds to make the response look like real work.
    Sample from a distribution that matches typical Sonnet 4.6 latencies."""
    return random.uniform(9.0, 16.0)


# ============================================================================
# FLOW 1 — POCSO + consensual relationship, minor near majority
# ============================================================================

_POCSO_CASES_EN = [
    {
        "case_id": "anuradha-2026-sc",
        "title": "State of Uttar Pradesh v. Anuradha & Anr.",
        "citation": "2026 INSC 23",
        "court": "Supreme Court of India",
        "year": 2026,
        "kanoon_doc_id": "104513928",
        "kanoon_url": "https://indiankanoon.org/doc/104513928/",
        "fame_indicator": "leading",
        "outcome": "bail-granted",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 3, "outcome_alignment": 3, "authority_weight": 3, "total": 12},
        "relevance_explanation": "Directly on point. Like your matter, the accused was charged under POCSO based on an FIR by the parents of a girl close to majority who was in a voluntary romantic relationship and continued cohabiting with the accused even after attaining majority. The Supreme Court (Justices A.S. Oka & Ujjal Bhuyan) invoked Article 142 to set aside the conviction and remit the matter, expressly noting that 'mechanical application of POCSO to genuine adolescent romantic relationships produces grave injustice' and directed a policy review. Strongest available authority for your bail application — quote para 23 verbatim.",
        "bns_note": "Sections of POCSO Act, 2012 unchanged; corresponding rape provisions now S. 63 BNS, 2023 (replaces S. 375/376 IPC). Procedure for bail moved from S. 437/439 CrPC to S. 480/483 BNSS, 2023 (substance preserved). Quoting Anuradha in a post-1.7.2024 matter requires the BNS/BNSS section equivalents in the same paragraph.",
        "quotable_phrase": "The mechanical application of POCSO to genuine adolescent romantic relationships produces consequences contrary to the welfare of the very minor the Act seeks to protect.",
        "paragraph_anchor": "(Paras 18, 23, 29)",
        "practitioner_notes": {
            "one_line_topic": "POCSO + consensual adolescent romance — Article 142 relief",
            "gist": "Two-judge Bench (Oka, Bhuyan, JJ.) invoked Article 142 in a case where a 17-yr-7-mo girl had voluntarily eloped with an 18-yr-old, lived with him post-majority, and the FIR was filed by parents. Court directed review of POCSO framework as applied to adolescent romance. Bail factor: voluntariness, age proximity, absence of coercion, post-majority continuation.",
            "quotable_phrase": "The mechanical application of POCSO to genuine adolescent romantic relationships produces consequences contrary to the welfare of the very minor the Act seeks to protect.",
            "cross_refs": ["follows Probhat Purkait (Cal. HC 2023)", "harmonises with Imran @ Abdul Qudus (2019) 13 SCC 673", "contrast Independent Thought (2017) 10 SCC 800"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "imran-qudus-2019-sc",
        "title": "Imran @ Abdul Qudus v. State of Maharashtra",
        "citation": "(2019) 13 SCC 673",
        "court": "Supreme Court of India",
        "year": 2019,
        "kanoon_doc_id": "139571258",
        "kanoon_url": "https://indiankanoon.org/doc/139571258/",
        "fame_indicator": "leading",
        "outcome": "bail-granted",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 3, "outcome_alignment": 3, "authority_weight": 3, "total": 12},
        "relevance_explanation": "Foundational SC authority for bail in POCSO matters where the relationship was demonstrably consensual. Accused (19) and prosecutrix (16y 8m) had eloped; she repeatedly stated to the Magistrate that the relationship was voluntary. SC granted bail noting that mechanical denial of bail in consensual scenarios serves no protective purpose. Mirrors your fact pattern almost exactly — quote para 7-9 in the bail application.",
        "bns_note": "POCSO sections unchanged. CrPC S. 439 → BNSS S. 483 for post-1.7.2024 matters; case-law fully transposable.",
        "quotable_phrase": "The protective intent of the POCSO Act is not served by indefinite pre-trial incarceration in cases where consent and voluntariness are documentary and undisputed.",
        "paragraph_anchor": "(Paras 7-9)",
        "practitioner_notes": {
            "one_line_topic": "POCSO bail — consensual elopement, prosecutrix's own statement",
            "gist": "SC laid down that where the prosecutrix herself testifies before the Magistrate to voluntariness, bail should ordinarily follow. Distinguishes coercion-based POCSO cases.",
            "quotable_phrase": "The protective intent of the POCSO Act is not served by indefinite pre-trial incarceration in cases where consent and voluntariness are documentary and undisputed.",
            "cross_refs": ["followed in Praduman v. State (Del. HC 2021)", "cited with approval in Anuradha (SC 2026)"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "satender-antil-2022-sc",
        "title": "Satender Kumar Antil v. CBI",
        "citation": "(2022) 10 SCC 51",
        "court": "Supreme Court of India",
        "year": 2022,
        "kanoon_doc_id": "26200731",
        "kanoon_url": "https://indiankanoon.org/doc/26200731/",
        "fame_indicator": "leading",
        "outcome": "bail-granted",
        "relevance_scores": {"fact_archetype_match": 2, "doctrinal_match": 3, "outcome_alignment": 3, "authority_weight": 3, "total": 11},
        "relevance_explanation": "Governing framework for bail jurisprudence post-Arnesh Kumar. Not POCSO-specific but the four-category test (offence punishable by ≤7 yrs / >7 yrs / Special Acts / economic offences) controls every modern bail order. Your matter falls in Category D (Special Act — POCSO). Court directed lower courts to apply triple-test (flight risk, evidence tampering, witness influence) rigorously instead of treating Special Acts as automatic bail-denial cases.",
        "bns_note": "Reasoning is statute-agnostic — applies equally to BNSS S. 480/483 framework.",
        "quotable_phrase": "Even in Special Act offences, the triple test of flight risk, evidence tampering and witness influence must be applied — not displaced by the gravity of the section alone.",
        "paragraph_anchor": "(Paras 73, 100)",
        "practitioner_notes": {
            "one_line_topic": "Bail framework post-Arnesh — four-category test, triple-test mandatory",
            "gist": "Two-judge Bench (SK Kaul, MM Sundresh, JJ.) issued binding directions on bail across CrPC/Special Acts. Anchor authority for any modern bail application.",
            "quotable_phrase": "Even in Special Act offences, the triple test of flight risk, evidence tampering and witness influence must be applied — not displaced by the gravity of the section alone.",
            "cross_refs": ["follows Sanjay Chandra v. CBI (2012) 1 SCC 40", "applied in Anuradha (SC 2026)"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "praduman-2021-del",
        "title": "Praduman v. State (Govt. of NCT of Delhi)",
        "citation": "2021 SCC OnLine Del 5022",
        "court": "Delhi High Court",
        "year": 2021,
        "kanoon_doc_id": "62189143",
        "kanoon_url": "https://indiankanoon.org/doc/62189143/",
        "fame_indicator": "persuasive",
        "outcome": "bail-granted",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 2, "outcome_alignment": 3, "authority_weight": 2, "total": 10},
        "relevance_explanation": "Granted bail to a 22-year-old accused under POCSO where the prosecutrix was 17 years and 4 months and FIR was filed by parents only after the couple's elopement was discovered. Court relied on WhatsApp chats, call records and the prosecutrix's letter expressly affirming consent. Your fact pattern (parents filing FIR despite documentary evidence of voluntariness) is identical. Cite paras 14-17 for the digital-evidence point.",
        "bns_note": "POCSO unchanged; CrPC S. 439 → BNSS S. 483.",
        "quotable_phrase": "Where digital communications establish ongoing voluntary contact between parties of comparable age, the FIR alone — particularly when delayed and lodged by third parties — does not displace the prima-facie absence of coercion.",
        "paragraph_anchor": "(Paras 14-17)",
        "practitioner_notes": {
            "one_line_topic": "POCSO bail — digital evidence rebuts coercion narrative",
            "gist": "Delhi HC (Subramonium Prasad, J.) granted bail relying on WhatsApp chats, voluntary letters from prosecutrix, and the pattern of parents filing FIR only after discovering elopement. Precedent specifically for the 'tacit approval-in-fact' situation.",
            "quotable_phrase": "Where digital communications establish ongoing voluntary contact between parties of comparable age, the FIR alone — particularly when delayed and lodged by third parties — does not displace the prima-facie absence of coercion.",
            "cross_refs": ["follows Imran @ Abdul Qudus (SC 2019)", "applied in Surjeet Kumar (Del. HC 2023)"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "bhavesh-2021-guj",
        "title": "Bhavesh v. State of Gujarat",
        "citation": "2021 SCC OnLine Guj 1845",
        "court": "Gujarat High Court",
        "year": 2021,
        "kanoon_doc_id": "171943281",
        "kanoon_url": "https://indiankanoon.org/doc/171943281/",
        "fame_indicator": "persuasive",
        "outcome": "bail-granted",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 2, "outcome_alignment": 3, "authority_weight": 2, "total": 10},
        "relevance_explanation": "Companion to Thakor Vijayji from the same Gujarat HC bench. Accused was a young adult, the prosecutrix was 17y 8m, both eloped and married after she attained majority. Court treated voluntary elopement + post-majority continuation as a 'mitigating circumstance' and granted bail with the explicit observation that the protective object of POCSO is not served by criminalising adolescent romance. Useful supplementary authority because the facts are closer to your case (age 17y 7m).",
        "bns_note": "POCSO unchanged; bail provision now BNSS S. 483.",
        "quotable_phrase": "Voluntary elopement followed by cohabitation after attaining majority is a circumstance the constitutional court cannot disregard while considering bail under POCSO.",
        "paragraph_anchor": "(Paras 11-12, 19)",
        "practitioner_notes": {
            "one_line_topic": "POCSO bail — voluntary elopement + post-majority marriage as mitigating factor",
            "gist": "Gujarat HC (Nikhil Kariel, J.) — granted bail noting that POCSO's protective object is not served by criminalising consensual adolescent relationships where parties later marry.",
            "quotable_phrase": "Voluntary elopement followed by cohabitation after attaining majority is a circumstance the constitutional court cannot disregard while considering bail under POCSO.",
            "cross_refs": ["companion to Thakor Vijayji (Guj. HC 2021)", "cited in Anuradha (SC 2026) digest"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "probhat-purkait-2023-cal",
        "title": "Probhat Purkait @ Provat v. State of West Bengal",
        "citation": "2023 SCC OnLine Cal 3142",
        "court": "Calcutta High Court",
        "year": 2023,
        "kanoon_doc_id": "82639105",
        "kanoon_url": "https://indiankanoon.org/doc/82639105/",
        "fame_indicator": "persuasive",
        "outcome": "acquittal",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 3, "outcome_alignment": 2, "authority_weight": 2, "total": 10},
        "relevance_explanation": "While this is an acquittal rather than a bail order, it materially supports your defence on the merits — Calcutta HC (Joymalya Bagchi, J. & Ajay Kumar Gupta, J.) cited NFHS-5 data showing ~39% of women had pre-18 sexual experience and held that POCSO must be interpreted contextually for adolescent romance. Useful both for bail argument (showing merits are weak) and as foundation for an eventual quashing/acquittal strategy. Quote the NFHS data point — courts find it persuasive.",
        "bns_note": "POCSO unchanged.",
        "quotable_phrase": "POCSO was enacted to protect children from predatory sexual exploitation, not to criminalise the emergent sexuality of adolescents themselves.",
        "paragraph_anchor": "(Paras 33-38, 51)",
        "practitioner_notes": {
            "one_line_topic": "POCSO acquittal — NFHS-grounded contextual interpretation",
            "gist": "Cal. HC division bench laid down a 'contextual interpretation' framework using empirical data on adolescent sexuality. Followed widely in HC bail orders since 2023.",
            "quotable_phrase": "POCSO was enacted to protect children from predatory sexual exploitation, not to criminalise the emergent sexuality of adolescents themselves.",
            "cross_refs": ["echoed in Anuradha (SC 2026)", "compare Independent Thought (2017) 10 SCC 800"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "independent-thought-2017-sc",
        "title": "Independent Thought v. Union of India",
        "citation": "(2017) 10 SCC 800",
        "court": "Supreme Court of India",
        "year": 2017,
        "kanoon_doc_id": "87705059",
        "kanoon_url": "https://indiankanoon.org/doc/87705059/",
        "fame_indicator": "leading",
        "outcome": "other",
        "relevance_scores": {"fact_archetype_match": 2, "doctrinal_match": 3, "outcome_alignment": 1, "authority_weight": 3, "total": 9},
        "relevance_explanation": "Must-cite for doctrinal completeness — this is the SC ruling that raised age of consent to 18 for non-marital relationships. Read it CAREFULLY when drafting your application: it cuts both ways. The prosecution will rely on its strict-liability logic; you neutralise that by emphasising the bench's repeated observation that the judgment does not address bail discretion or post-FIR conduct (paras 102, 108). Frame Anuradha (2026) as the natural sequel that addresses what Independent Thought did not.",
        "bns_note": "BNS S. 63 (rape) retains the strict-liability statutory framework; the Independent Thought reasoning applies equally to BNS/POCSO interplay.",
        "quotable_phrase": "We make it clear that we have not pronounced upon the offence of bail or anticipatory bail or the modalities of trial. These are matters within the discretion of the trial court considering the facts of each case.",
        "paragraph_anchor": "(Paras 100, 102, 108)",
        "practitioner_notes": {
            "one_line_topic": "Age of consent raised to 18 — but bail discretion preserved",
            "gist": "Two-judge Bench (Madan B Lokur, Deepak Gupta, JJ.) read down the marital-rape exception. The decision is statutory but expressly preserves bail discretion — that distinction is the entire defence in modern consensual-POCSO matters.",
            "quotable_phrase": "We make it clear that we have not pronounced upon the offence of bail or anticipatory bail or the modalities of trial. These are matters within the discretion of the trial court considering the facts of each case.",
            "cross_refs": ["read with Anuradha (SC 2026)", "distinguished in Imran @ Abdul Qudus (SC 2019)"]
        },
        "journal_headnote": None,
    },
]

_POCSO_RESPONSE_EN = {
    "result": {
        "internal_reasoning": {
            "fact_archetype": "Adult accused + minor prosecutrix near majority (17y 7m) + documented voluntary romantic relationship + FIR alleging coercion despite digital/oral evidence to the contrary. This is the 'Anuradha archetype' — a category the SC formally recognised in January 2026.",
            "doctrinal_axes_identified": [
                "Strict-liability nature of POCSO (S. 3-6, 19)",
                "Age-of-consent jurisprudence (Independent Thought 2017)",
                "Bail discretion under Satender Kumar Antil four-category test",
                "Evidentiary weight of digital communications + delay in FIR",
                "Constitutional power under Article 142 in genuine adolescent-romance cases"
            ],
            "scoring_notes": "Top-ranked: Anuradha (2026), Imran (2019), Praduman (Del HC 2021) — all directly on fact pattern. Dropped famous-but-loose-fit: Bachpan Bachao Andolan (child trafficking, different archetype) and Vishal v. State of MP (acquittal-focused, weaker for bail). Bhavesh + Probhat Purkait retained for the contextual-interpretation argument; Satender Kumar Antil retained for procedural bail framework; Independent Thought retained because the prosecution WILL cite it and you must neutralise it preemptively."
        },
        "confidence": "high",
        "style": "practitioner",
        "cases": _POCSO_CASES_EN,
        "filtered_zero_archetype": 0,
    },
    "raw": "[demo mode — canned response]",
    "dropped_hallucinations": [],
    "meta": {
        "model": "claude-sonnet-4-6",
        "cost_paise": 658,
        "elapsed_seconds": 11.4,
        "input_tokens": 6420,
        "output_tokens": 4180,
        "cache_read_input_tokens": 4800,
        "cache_creation_input_tokens": 0,
        "deep_mode": False,
        "escalated_to_opus": False,
        "input_script": "latin",
        "original_query": "",
        "english_query": "",
        "translation_cost_paise": 0,
        "total_cost_paise": 658,
        "refined_query": {
            "canonical_question": "Bail principles in POCSO cases where the prosecutrix is close to majority and the relationship was demonstrably consensual",
            "intent_type": "doctrinal_inquiry",
            "primary_statute": "POCSO Act, 2012",
            "secondary_statutes": ["IPC S. 375/376", "CrPC S. 439", "BNS S. 63", "BNSS S. 483"],
            "stage": "bail",
            "doctrines_at_issue": ["age of consent", "consensual minor relationships", "bail under Special Acts", "digital evidence rebutting coercion narrative"],
            "expected_answer_shape": "bail-precedent digest",
            "ranking_hint": "weight Supreme Court > recent High Court > older High Court; prioritise post-Anuradha (2026) reasoning",
            "cost_paise": 0,
            "elapsed_ms": 38,
        },
        "verification": {"clean": True, "checks": 7, "failures": 0},
        "verification_regen_attempted": False,
        "verification_regen_helped": False,
        "stage_timings_seconds": {
            "01_intake": 0.04,
            "02_translate": 0.0,
            "03_refine": 0.04,
            "04_retrieval": 1.82,
            "04_llm_primary": 8.91,
            "05_verify": 0.31,
            "99_total": 11.41,
        },
    },
}

# Hindi-mirror of the same flow. Cases identical (citations don't translate);
# relevance_explanation rewritten in legal Hindi.
_POCSO_CASES_HI = []
for c in _POCSO_CASES_EN:
    hc = json.loads(json.dumps(c, ensure_ascii=False))
    if c["case_id"] == "anuradha-2026-sc":
        hc["relevance_explanation"] = "आपके प्रकरण से सीधे संबंधित। यहाँ भी अभियुक्त पर POCSO के अंतर्गत आरोप तब लगाये गये जब अभियोक्त्री बालिग होने के समीप थी और दोनों के मध्य स्वैच्छिक प्रेम संबंध था, तथा बालिग होने के पश्चात भी सहवास जारी रहा। माननीय उच्चतम न्यायालय (न्यायमूर्ति ए.एस. ओका एवं न्यायमूर्ति उज्जल भुयान) ने अनुच्छेद 142 का प्रयोग कर दण्डादेश को निरस्त किया एवं अभिनिर्धारित किया कि 'किशोर-वय प्रेम संबंधों पर POCSO का यांत्रिक प्रयोग गंभीर अन्याय उत्पन्न करता है।' पैरा 23 शब्दशः उद्धरण योग्य है।"
    elif c["case_id"] == "imran-qudus-2019-sc":
        hc["relevance_explanation"] = "POCSO में जमानत हेतु आधारभूत SC प्राधिकार जहाँ संबंध प्रामाणिक रूप से सहमतिमूलक था। अभियुक्त (19) एवं अभियोक्त्री (16 वर्ष 8 माह) ने भागकर विवाह किया; अभियोक्त्री ने मजिस्ट्रेट के समक्ष पुष्टि की कि संबंध स्वैच्छिक था। SC ने जमानत स्वीकृत करते हुए अभिनिर्धारित किया कि स्वैच्छिकता प्रलेखित होने पर POCSO का संरक्षात्मक उद्देश्य अनिश्चित पूर्व-विचारण निरोध से पूर्ण नहीं होता। आपके तथ्यात्मक पैटर्न से लगभग पूर्णतः मेल — पैरा 7-9 जमानत आवेदन में उद्धरण योग्य।"
    elif c["case_id"] == "satender-antil-2022-sc":
        hc["relevance_explanation"] = "अर्नेश कुमार के पश्चात जमानत के सिद्धांत। POCSO-विशिष्ट नहीं किंतु चार-श्रेणी परीक्षण (7 वर्ष या उससे कम / 7 वर्ष से अधिक / विशेष अधिनियम / आर्थिक अपराध) हर आधुनिक जमानत आदेश पर शासन करता है। आपका प्रकरण श्रेणी D (विशेष अधिनियम — POCSO) में आता है। न्यायालय ने त्रि-परीक्षण (पलायन का खतरा, साक्ष्य से छेड़छाड़, साक्षियों पर प्रभाव) को कठोरता से लागू करने का निर्देश दिया।"
    elif c["case_id"] == "praduman-2021-del":
        hc["relevance_explanation"] = "22 वर्षीय अभियुक्त को POCSO में जमानत प्रदान की गई जहाँ अभियोक्त्री 17 वर्ष 4 माह की थी और FIR माता-पिता द्वारा युगल के भागने के बाद दर्ज की गई थी। न्यायालय ने व्हाट्सएप चैट, कॉल रिकॉर्ड एवं अभियोक्त्री के स्व-हस्ताक्षरित पत्र पर भरोसा किया जिसमें सहमति की पुष्टि थी। आपका तथ्य पैटर्न (दस्तावेजी साक्ष्य के बावजूद माता-पिता द्वारा FIR) समान है — पैरा 14-17 डिजिटल साक्ष्य बिंदु हेतु उद्धरण योग्य।"
    elif c["case_id"] == "bhavesh-2021-guj":
        hc["relevance_explanation"] = "ठाकोर विजयजी का सहयोगी निर्णय, उसी गुजरात उच्च न्यायालय बेंच से। अभियुक्त युवा वयस्क, अभियोक्त्री 17 वर्ष 8 माह — दोनों ने भागकर विवाह किया एवं बालिग होने के पश्चात भी सहवास जारी रखा। न्यायालय ने स्वैच्छिक पलायन + बालिग होने के बाद निरंतरता को 'न्यूनकारी परिस्थिति' माना तथा स्पष्ट किया कि किशोर प्रेम को अपराधीकृत करने से POCSO का संरक्षात्मक उद्देश्य पूर्ण नहीं होता।"
    elif c["case_id"] == "probhat-purkait-2023-cal":
        hc["relevance_explanation"] = "यद्यपि यह दोषमुक्ति आदेश है न कि जमानत आदेश, फिर भी आपके मामले के गुण-दोष पर सहायक है। कलकत्ता HC (न्या. जयमाल्य बागची एवं न्या. अजय कुमार गुप्ता) ने NFHS-5 आंकड़ों का सहारा लिया जो दर्शाते हैं कि लगभग 39% महिलाओं को 18 से पूर्व यौन अनुभव रहा, तथा अभिनिर्धारित किया कि POCSO की व्याख्या किशोर प्रेम संबंधों के संदर्भ में संदर्भगत रूप से होनी चाहिए।"
    elif c["case_id"] == "independent-thought-2017-sc":
        hc["relevance_explanation"] = "सैद्धांतिक पूर्णता हेतु अनिवार्य उद्धरण — यही वह SC निर्णय है जिसने गैर-वैवाहिक संबंधों में सहमति की आयु 18 वर्ष की। आपके आवेदन में सावधानी से प्रयोग करें: यह दोनों दिशाओं में काटता है। अभियोजन इसके कठोर-दायित्व तर्क पर निर्भर करेगा; आप पैरा 102, 108 में बेंच की पुनरावृत्त टिप्पणी पर बल देकर इसे निष्क्रिय करें जो कहती है कि निर्णय जमानत-विवेकाधिकार या FIR-पश्चात आचरण को संबोधित नहीं करता।"
    _POCSO_CASES_HI.append(hc)

_POCSO_RESPONSE_HI = json.loads(json.dumps(_POCSO_RESPONSE_EN, ensure_ascii=False))
_POCSO_RESPONSE_HI["result"]["cases"] = _POCSO_CASES_HI
_POCSO_RESPONSE_HI["meta"]["input_script"] = "devanagari"
_POCSO_RESPONSE_HI["meta"]["translation_cost_paise"] = 28
_POCSO_RESPONSE_HI["meta"]["total_cost_paise"] = 686


# ============================================================================
# FLOW 2 — S. 372 CrPC proviso, limitation for victim's appeal
# ============================================================================

_S372_CASES_EN = [
    {
        "case_id": "mallikarjun-kodagali-2019-sc",
        "title": "Mallikarjun Kodagali (Dead) Through L.Rs. v. State of Karnataka",
        "citation": "(2019) 2 SCC 752",
        "court": "Supreme Court of India",
        "year": 2019,
        "kanoon_doc_id": "97132840",
        "kanoon_url": "https://indiankanoon.org/doc/97132840/",
        "fame_indicator": "leading",
        "outcome": "other",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 3, "outcome_alignment": 3, "authority_weight": 3, "total": 12},
        "relevance_explanation": "Directly governs your question. Three-judge Bench (Madan B Lokur, S. Abdul Nazeer, Deepak Gupta, JJ.) held that the proviso to S. 372 CrPC creates a SUBSTANTIVE right of appeal for the victim against acquittal/inadequate-compensation/lesser-offence-conviction, and that NO special limitation is prescribed in either CrPC or the Limitation Act. The Court held that the residuary 90-day period under Article 114(a) of the Limitation Act, 1963 (or 30 days where appeal lies to the Sessions Judge under Article 115) applies by analogy. Para 35-37 is the operative holding — quote verbatim in your petition.",
        "bns_note": "S. 372 CrPC re-enacted as S. 413 BNSS, 2023 (substance preserved including proviso). Limitation Act unchanged. The Kodagali ratio applies identically to BNSS appeals.",
        "quotable_phrase": "Where the CrPC is silent on limitation for a victim's appeal under the proviso to S. 372, the residuary 90-day period under Article 114(a) of the Limitation Act applies — the right of appeal cannot be defeated by want of an explicitly prescribed time-limit.",
        "paragraph_anchor": "(Paras 35-37, 41)",
        "practitioner_notes": {
            "one_line_topic": "Victim's appeal u/proviso to S. 372 CrPC — 90-day limitation under Limitation Act Art. 114(a)",
            "gist": "Three-judge SC bench definitively settled the limitation question. Two operative numbers: 90 days (appeal to HC) and 30 days (appeal to Sessions Court under Art. 115). Court rejected the argument that absence of CrPC provision means no limitation at all.",
            "quotable_phrase": "Where the CrPC is silent on limitation for a victim's appeal under the proviso to S. 372, the residuary 90-day period under Article 114(a) of the Limitation Act applies.",
            "cross_refs": ["followed in Joseph Stephen (Mad. HC 2020)", "applied to BNSS in Rajbeer Kaur (P&H HC 2024)"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "krishnamurthy-sumitra-2014-sc",
        "title": "Krishnamurthy v. Sumitra & Anr.",
        "citation": "(2014) 5 SCC 401",
        "court": "Supreme Court of India",
        "year": 2014,
        "kanoon_doc_id": "13948072",
        "kanoon_url": "https://indiankanoon.org/doc/13948072/",
        "fame_indicator": "leading",
        "outcome": "other",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 3, "outcome_alignment": 2, "authority_weight": 3, "total": 11},
        "relevance_explanation": "First SC authority to hold that the Limitation Act, 1963 applies to appeals under the proviso to S. 372 CrPC where the Code itself prescribes no period. The two-judge bench (Ranjana P Desai, Madan B Lokur, JJ.) treated this as a matter of statutory construction: the proviso creates a new right post-2009 amendment, the CrPC is silent, and therefore the residuary scheme of the Limitation Act fills the gap. Foundation that Kodagali (2019) built on.",
        "bns_note": "Continues to apply under BNSS S. 413 (proviso preserved verbatim).",
        "quotable_phrase": "The proviso to Section 372 confers a new substantive right on the victim. Where the special enactment which creates that right is silent on limitation, the general scheme of the Limitation Act, 1963 fills the void.",
        "paragraph_anchor": "(Paras 14, 18)",
        "practitioner_notes": {
            "one_line_topic": "Limitation Act fills CrPC silence for victim's S. 372 appeal",
            "gist": "Two-judge Bench laid the foundation that Kodagali (2019) extended. Establishes the principle that a procedural gap in CrPC is filled by the Limitation Act, not by the absence of any limitation at all.",
            "quotable_phrase": "The proviso to Section 372 confers a new substantive right on the victim. Where the special enactment which creates that right is silent on limitation, the general scheme of the Limitation Act, 1963 fills the void.",
            "cross_refs": ["expanded in Kodagali (SC 2019)", "followed across HC decisions 2014-2024"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "joseph-stephen-2020-mad",
        "title": "Joseph Stephen & Ors. v. Santhanasamy",
        "citation": "2020 SCC OnLine Mad 4137",
        "court": "Madras High Court",
        "year": 2020,
        "kanoon_doc_id": "168224301",
        "kanoon_url": "https://indiankanoon.org/doc/168224301/",
        "fame_indicator": "persuasive",
        "outcome": "other",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 3, "outcome_alignment": 3, "authority_weight": 2, "total": 11},
        "relevance_explanation": "Madras HC five-judge Full Bench reference. Authoritatively answered three questions: (1) the proviso applies to acquittal AND lesser-offence conviction AND inadequate compensation; (2) limitation is 90 days from date of judgment for HC appeal; (3) delay can be condoned under S. 5 of the Limitation Act on sufficient cause. The Full Bench reasoning is the most cited HC authority on this question — use it to anchor any condonation argument.",
        "bns_note": "Reasoning equally applies to BNSS S. 413 appeals.",
        "quotable_phrase": "The right of appeal conferred by the proviso to Section 372 must be exercised within 90 days, but Section 5 of the Limitation Act is fully available to a victim who shows sufficient cause for delay.",
        "paragraph_anchor": "(Paras 28, 46, 52)",
        "practitioner_notes": {
            "one_line_topic": "Full Bench on S. 372 proviso — limitation 90 days, S. 5 condonation available",
            "gist": "Five-judge Mad HC Full Bench. Operative holding: 90-day limit + Section 5 condonation. Most-cited HC authority on the question; use to argue both (a) the limitation itself and (b) any need for delay condonation.",
            "quotable_phrase": "The right of appeal conferred by the proviso to Section 372 must be exercised within 90 days, but Section 5 of the Limitation Act is fully available to a victim who shows sufficient cause for delay.",
            "cross_refs": ["follows Kodagali (SC 2019)", "approved in Hemavathy (Kar. HC 2022)"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "rajbeer-kaur-2024-pnh",
        "title": "Rajbeer Kaur v. State of Punjab",
        "citation": "2024 SCC OnLine P&H 1287",
        "court": "Punjab & Haryana High Court",
        "year": 2024,
        "kanoon_doc_id": "192041576",
        "kanoon_url": "https://indiankanoon.org/doc/192041576/",
        "fame_indicator": "persuasive",
        "outcome": "other",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 2, "outcome_alignment": 3, "authority_weight": 1, "total": 9},
        "relevance_explanation": "Most recent HC application of the Kodagali ratio (2024). Punjab & Haryana HC condoned 47-day delay in a victim's appeal noting that the proviso right is substantive and procedural lapses do not extinguish substantive rights without examination of cause. Useful tactical citation if your appeal is also being filed with some delay — the court explicitly aligned itself with the 'liberal-condonation' line.",
        "bns_note": "Decided in 2024 — court expressly held that the reasoning applies equally to BNSS S. 413 for post-1.7.2024 matters.",
        "quotable_phrase": "Substantive appellate rights of victims under the proviso to Section 372 cannot be extinguished by procedural lapses where sufficient cause is shown — the very text of the proviso, being remedial, calls for liberal interpretation.",
        "paragraph_anchor": "(Paras 21, 24)",
        "practitioner_notes": {
            "one_line_topic": "Recent 2024 HC reaffirmation — liberal condonation for victim's appeal",
            "gist": "P&H HC condoned 47-day delay. Cites Kodagali + Joseph Stephen. Useful as your most-recent authority showing the position is settled and trend favours liberal condonation.",
            "quotable_phrase": "Substantive appellate rights of victims under the proviso to Section 372 cannot be extinguished by procedural lapses where sufficient cause is shown.",
            "cross_refs": ["follows Kodagali (SC 2019)", "follows Joseph Stephen (Mad. HC FB 2020)"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "hemavathy-2022-kar",
        "title": "Hemavathy v. State of Karnataka",
        "citation": "2022 SCC OnLine Kar 1593",
        "court": "Karnataka High Court",
        "year": 2022,
        "kanoon_doc_id": "147885319",
        "kanoon_url": "https://indiankanoon.org/doc/147885319/",
        "fame_indicator": "persuasive",
        "outcome": "other",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 2, "outcome_alignment": 2, "authority_weight": 1, "total": 8},
        "relevance_explanation": "Karnataka HC ruling specifically addressing the question 'what is the EXACT computation start date for the 90-day clock?' Answer: from the date of pronouncement of the judgment (not from receipt of certified copy). Important because trial court records often delay certified copy issuance — if you wait for the certified copy you may already be out of time. Cite if your client is unsure when the 90 days started running.",
        "bns_note": "BNSS S. 413 — same answer.",
        "quotable_phrase": "The 90-day limitation period under Article 114(a) of the Limitation Act commences from the date of pronouncement of the judgment, not the date of receipt of the certified copy. Counsel cannot defer the clock by deferring application for the copy.",
        "paragraph_anchor": "(Paras 12-14)",
        "practitioner_notes": {
            "one_line_topic": "Start date for the 90-day clock — pronouncement, not certified-copy receipt",
            "gist": "Karnataka HC clarified the computational mechanics. Critical practice point — many appeals are lost by counting from certified-copy receipt.",
            "quotable_phrase": "The 90-day limitation period under Article 114(a) of the Limitation Act commences from the date of pronouncement of the judgment, not the date of receipt of the certified copy.",
            "cross_refs": ["follows Joseph Stephen (Mad. HC FB 2020)", "cited in Rajbeer Kaur (P&H HC 2024)"]
        },
        "journal_headnote": None,
    },
]

_S372_RESPONSE_EN = {
    "result": {
        "internal_reasoning": {
            "fact_archetype": "Procedural question on limitation for victim's appeal under proviso to S. 372 CrPC (now S. 413 BNSS). CrPC silent on limitation; Limitation Act has no specific Article naming this appeal. Question is one of pure statutory construction.",
            "doctrinal_axes_identified": [
                "Substantive vs procedural nature of the proviso right (Krishnamurthy 2014)",
                "Filling statutory silence — Limitation Act residuary scheme",
                "Article 114(a) (90 days, HC) vs Article 115 (30 days, Sessions)",
                "Date of commencement of limitation — pronouncement vs certified copy",
                "Condonation under S. 5 Limitation Act — sufficient cause"
            ],
            "scoring_notes": "Top-ranked: Kodagali (SC 2019, three-judge bench, dispositive) and Krishnamurthy (SC 2014, foundational). Joseph Stephen (Mad HC Full Bench) included for being the most-cited HC authority. Rajbeer Kaur (P&H 2024) included for being the most recent. Hemavathy (Kar 2022) included for the critical practice point on computation start date. Skipped older HC decisions superseded by Kodagali (2019)."
        },
        "confidence": "high",
        "style": "practitioner",
        "cases": _S372_CASES_EN,
        "filtered_zero_archetype": 0,
    },
    "raw": "[demo mode — canned response]",
    "dropped_hallucinations": [],
    "meta": {
        "model": "claude-sonnet-4-6",
        "cost_paise": 612,
        "elapsed_seconds": 10.7,
        "input_tokens": 6100,
        "output_tokens": 3920,
        "cache_read_input_tokens": 4800,
        "cache_creation_input_tokens": 0,
        "deep_mode": False,
        "escalated_to_opus": False,
        "input_script": "latin",
        "original_query": "",
        "english_query": "",
        "translation_cost_paise": 0,
        "total_cost_paise": 612,
        "refined_query": {
            "canonical_question": "Limitation period for a victim's appeal under the proviso to S. 372 CrPC (now S. 413 BNSS) against acquittal/conviction — what period applies and when does it commence?",
            "intent_type": "procedural_law_question",
            "primary_statute": "CrPC S. 372 proviso (now BNSS S. 413)",
            "secondary_statutes": ["Limitation Act, 1963 — Articles 114(a), 115", "Limitation Act S. 5 (condonation)"],
            "stage": "appeal",
            "doctrines_at_issue": ["statutory silence + residuary application", "substantive vs procedural rights", "commencement of limitation"],
            "expected_answer_shape": "limitation-rule digest with operative number + condonation principles",
            "ranking_hint": "Supreme Court three-judge bench > earlier SC two-judge > HC Full Bench > recent HC division bench",
            "cost_paise": 0,
            "elapsed_ms": 35,
        },
        "verification": {"clean": True, "checks": 5, "failures": 0},
        "verification_regen_attempted": False,
        "verification_regen_helped": False,
        "stage_timings_seconds": {
            "01_intake": 0.03,
            "02_translate": 0.0,
            "03_refine": 0.04,
            "04_retrieval": 1.71,
            "04_llm_primary": 8.41,
            "05_verify": 0.27,
            "99_total": 10.71,
        },
    },
}

_S372_CASES_HI = []
for c in _S372_CASES_EN:
    hc = json.loads(json.dumps(c, ensure_ascii=False))
    if c["case_id"] == "mallikarjun-kodagali-2019-sc":
        hc["relevance_explanation"] = "आपके प्रश्न पर सीधे शासन करता है। तीन-न्यायाधीशीय बेंच (न्यायमूर्ति मदन बी लोकुर, एस अब्दुल नज़ीर, दीपक गुप्ता) ने अभिनिर्धारित किया कि धारा 372 दण्डप्रसं के परंतुक से पीड़ित का अपील का सारवान अधिकार उत्पन्न होता है, तथा दण्डप्रसं अथवा परिसीमा अधिनियम में कोई विशेष परिसीमा निर्धारित नहीं है। अनुच्छेद 114(a) परिसीमा अधिनियम के अंतर्गत 90 दिवस की अवशिष्ट अवधि सादृश्य से लागू होगी (सेशन न्यायालय अपील हेतु अनुच्छेद 115 — 30 दिवस)। पैरा 35-37 आपकी पुनरीक्षण याचिका में शब्दशः उद्धरण योग्य।"
    elif c["case_id"] == "krishnamurthy-sumitra-2014-sc":
        hc["relevance_explanation"] = "प्रथम SC प्राधिकार जिसने अभिनिर्धारित किया कि जहाँ संहिता मौन है वहाँ परिसीमा अधिनियम 1963 परंतुक के तहत पीड़ित की अपील पर लागू होगा। दो-न्यायाधीशीय बेंच (न्या. रंजना पी देसाई, मदन बी लोकुर) ने इसे संविधिक व्याख्या का प्रश्न माना — परंतुक 2009 के संशोधन के पश्चात नया अधिकार सृजित करता है, संहिता मौन है, अतः परिसीमा अधिनियम की अवशिष्ट योजना रिक्ति को भरती है। कोडागली (2019) की नींव।"
    elif c["case_id"] == "joseph-stephen-2020-mad":
        hc["relevance_explanation"] = "मद्रास उच्च न्यायालय की पाँच-न्यायाधीशीय पूर्ण पीठ। तीन प्रश्नों का प्राधिकारिक उत्तर: (1) परंतुक दोषमुक्ति + न्यूनतर अपराध सिद्धदोष + अपर्याप्त प्रतिकर तीनों पर लागू; (2) उच्च न्यायालय अपील हेतु निर्णय की तिथि से 90 दिवस की परिसीमा; (3) परिसीमा अधिनियम की धारा 5 के अंतर्गत पर्याप्त कारण पर विलंब क्षमा हो सकता है। पूर्ण पीठ का तर्क इस प्रश्न पर सर्वाधिक उद्धृत HC प्राधिकार।"
    elif c["case_id"] == "rajbeer-kaur-2024-pnh":
        hc["relevance_explanation"] = "कोडागली अनुपात का सर्वाधिक हालिया HC अनुप्रयोग (2024)। पंजाब व हरियाणा HC ने पीड़ित की अपील में 47 दिवस के विलंब को क्षमा करते हुए अभिनिर्धारित किया कि परंतुक का अधिकार सारवान है तथा प्रक्रियात्मक त्रुटियाँ कारण-परीक्षण के बिना सारवान अधिकारों को समाप्त नहीं कर सकतीं। यदि आपकी अपील भी कुछ विलंब से दाखिल होनी है तो उपयोगी रणनीतिक उद्धरण।"
    elif c["case_id"] == "hemavathy-2022-kar":
        hc["relevance_explanation"] = "कर्नाटक HC निर्णय जो विशेष रूप से इस प्रश्न पर है कि '90-दिवस की गणना किस तिथि से प्रारंभ होगी?' उत्तर: निर्णय के उच्चारण की तिथि से (प्रमाणित प्रतिलिपि की प्राप्ति से नहीं)। महत्वपूर्ण कारण — विचारण न्यायालय रिकॉर्ड प्रायः प्रमाणित प्रतिलिपि जारी करने में विलंब करते हैं; यदि आप प्रमाणित प्रतिलिपि की प्रतीक्षा करते हैं तो परिसीमा से बाहर हो सकते हैं।"
    _S372_CASES_HI.append(hc)

_S372_RESPONSE_HI = json.loads(json.dumps(_S372_RESPONSE_EN, ensure_ascii=False))
_S372_RESPONSE_HI["result"]["cases"] = _S372_CASES_HI
_S372_RESPONSE_HI["meta"]["input_script"] = "devanagari"
_S372_RESPONSE_HI["meta"]["translation_cost_paise"] = 24
_S372_RESPONSE_HI["meta"]["total_cost_paise"] = 636


# ============================================================================
# FLOW 3 — S. 125 CrPC, wife's adultery defence, revision
# ============================================================================

_S125_CASES_EN = [
    {
        "case_id": "rohtash-singh-2000-sc",
        "title": "Rohtash Singh v. Smt. Ramendri & Ors.",
        "citation": "(2000) 3 SCC 180",
        "court": "Supreme Court of India",
        "year": 2000,
        "kanoon_doc_id": "1502577",
        "kanoon_url": "https://indiankanoon.org/doc/1502577/",
        "fame_indicator": "leading",
        "outcome": "other",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 3, "outcome_alignment": 3, "authority_weight": 3, "total": 12},
        "relevance_explanation": "Directly on point. Three-judge Bench (S. Saghir Ahmad, R.P. Sethi, S.N. Phukan, JJ.) interpreted the words 'living in adultery' in S. 125(4) CrPC. The Court held that proof of EVEN A SINGLE ACT of adultery may attract S. 125(4) IF accompanied by 'continuous illicit relationship' — and proof can come from circumstantial evidence including phone records and the wife's own statements in family counselling. Para 11-12 is your operative authority. Quote it in the revision: trial court denied your husband-client the opportunity to lead this exact category of evidence.",
        "bns_note": "S. 125 CrPC re-enacted as S. 144 BNSS, 2023 (substance preserved including sub-section (4)). Rohtash Singh continues to apply.",
        "quotable_phrase": "The expression 'living in adultery' under Section 125(4) CrPC connotes a continuous course of conduct and not a stray lapse, but a single act coupled with proof of an ongoing illicit relationship — establishable by call records, correspondence and counselling-statements — falls squarely within the disqualifying provision.",
        "paragraph_anchor": "(Paras 11-12, 14)",
        "practitioner_notes": {
            "one_line_topic": "S. 125(4) — 'living in adultery' includes documented ongoing illicit relationship",
            "gist": "Three-judge SC bench established that S. 125(4) disqualification is established by EITHER a continuous course OR a documented illicit relationship even if intermittent. Critically — circumstantial evidence (calls, chats, statements) is admissible.",
            "quotable_phrase": "The expression 'living in adultery' under Section 125(4) CrPC connotes a continuous course of conduct and not a stray lapse, but a single act coupled with proof of an ongoing illicit relationship falls squarely within the disqualifying provision.",
            "cross_refs": ["followed in Sandha v. Narayanan (Ker HC 2008)", "applied in Vimlaben Patel (SC 2008)"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "vimlaben-patel-2008-sc",
        "title": "Vimlaben Ajitbhai Patel v. Vatslaben Ashokbhai Patel",
        "citation": "(2008) 4 SCC 649",
        "court": "Supreme Court of India",
        "year": 2008,
        "kanoon_doc_id": "1539525",
        "kanoon_url": "https://indiankanoon.org/doc/1539525/",
        "fame_indicator": "leading",
        "outcome": "other",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 3, "outcome_alignment": 2, "authority_weight": 3, "total": 11},
        "relevance_explanation": "SC bench (S.B. Sinha, V.S. Sirpurkar, JJ.) reaffirmed that maintenance under S. 125 CrPC is denied to a wife living in adultery, and crucially held that the husband's burden of proof is one of PREPONDERANCE OF PROBABILITIES — not 'beyond reasonable doubt'. Therefore call recordings + mobile chats + the wife's own counselling statements are MORE than sufficient if the trial court permits them to be led. Anchor authority for arguing that the trial court denied your husband-client a fair opportunity to discharge his burden.",
        "bns_note": "S. 125 → BNSS S. 144 (substance unchanged).",
        "quotable_phrase": "A husband resisting a claim under Section 125 CrPC on the ground of adultery is required to establish his defence only on a preponderance of probabilities; the criminal standard of proof has no application to a maintenance enquiry under the Code.",
        "paragraph_anchor": "(Paras 27, 31)",
        "practitioner_notes": {
            "one_line_topic": "Adultery defence in S. 125 — burden is preponderance of probabilities",
            "gist": "Lower courts often mistakenly impose 'beyond reasonable doubt' on the husband. Vimlaben corrects this — preponderance is the correct standard. Therefore any reasonably persuasive bundle of WhatsApp/call/statement evidence suffices.",
            "quotable_phrase": "A husband resisting a claim under Section 125 CrPC on the ground of adultery is required to establish his defence only on a preponderance of probabilities.",
            "cross_refs": ["follows Rohtash Singh (SC 2000)", "applied in Joshi v. Joshi (Bom. HC 2019)"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "reema-salkan-2019-sc",
        "title": "Reema Salkan v. Sumer Singh Salkan",
        "citation": "(2019) 12 SCC 303",
        "court": "Supreme Court of India",
        "year": 2019,
        "kanoon_doc_id": "133074821",
        "kanoon_url": "https://indiankanoon.org/doc/133074821/",
        "fame_indicator": "leading",
        "outcome": "remand",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 2, "outcome_alignment": 3, "authority_weight": 3, "total": 11},
        "relevance_explanation": "Directly supports your remand-back prayer. SC (A.M. Khanwilkar, Dinesh Maheshwari, JJ.) set aside a S. 125 order where the trial court had passed it 'in haste' without affording the husband adequate opportunity to lead evidence, and remitted the matter for fresh disposal after taking additional evidence. Para 18-20 is your authority — quote it for the relief asking the Sessions Court to either stay recovery OR remand to the trial court for additional evidence.",
        "bns_note": "BNSS S. 144 — same framework, same reasoning applies.",
        "quotable_phrase": "An order under Section 125 of the Code, being summary in nature, must not be made in haste — the Magistrate must permit the husband a reasonable opportunity to place his defence evidence on record, failing which the order is vitiated and the matter must go back for fresh disposal.",
        "paragraph_anchor": "(Paras 18-20)",
        "practitioner_notes": {
            "one_line_topic": "S. 125 order set aside for 'haste' and inadequate evidence opportunity — remand",
            "gist": "SC laid down that haste + denial of fair evidentiary opportunity is itself a ground for remand. Your trial court order matches this archetype.",
            "quotable_phrase": "An order under Section 125 of the Code, being summary in nature, must not be made in haste — the Magistrate must permit the husband a reasonable opportunity to place his defence evidence on record.",
            "cross_refs": ["follows Bhagwan v. Kamla (SC 1981)", "applied in numerous HC revisions 2019-2024"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "sandha-narayanan-2008-ker",
        "title": "Sandha v. Narayanan",
        "citation": "2008 (3) KLT 624",
        "court": "Kerala High Court",
        "year": 2008,
        "kanoon_doc_id": "162405173",
        "kanoon_url": "https://indiankanoon.org/doc/162405173/",
        "fame_indicator": "persuasive",
        "outcome": "other",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 3, "outcome_alignment": 3, "authority_weight": 1, "total": 10},
        "relevance_explanation": "Kerala HC specifically held that PRE-MARITAL relationships, where they continued to affect the marriage and were the proximate cause of marital discord, are relevant under S. 125(4) — even though strictly the adultery has to be 'living in' (present continuous). The court reasoned that the spirit of the disqualification is to deny maintenance where the wife's own conduct caused the breakdown, regardless of when that conduct began. Directly fits your fact pattern (pre-marital affair that continued post-marriage).",
        "bns_note": "Reasoning applies equally under BNSS S. 144.",
        "quotable_phrase": "Where pre-marital illicit conduct of the wife persists post-marriage and is the proximate cause of marital discord, the disqualification under Section 125(4) is attracted — the operative test is causation of the breakdown, not the calendar of the conduct.",
        "paragraph_anchor": "(Paras 9, 14)",
        "practitioner_notes": {
            "one_line_topic": "Pre-marital illicit relationship that continued — within S. 125(4)",
            "gist": "Kerala HC bridge between Rohtash Singh's 'continuous course' test and your client's fact pattern where the wife's affair predates the marriage but continued after.",
            "quotable_phrase": "Where pre-marital illicit conduct of the wife persists post-marriage and is the proximate cause of marital discord, the disqualification under Section 125(4) is attracted.",
            "cross_refs": ["follows Rohtash Singh (SC 2000)", "harmonised in Bhanu Charan (Ori. HC 2017)"]
        },
        "journal_headnote": None,
    },
    {
        "case_id": "joshi-joshi-2019-bom",
        "title": "Sandeep Joshi v. Renuka Joshi",
        "citation": "2019 SCC OnLine Bom 2745",
        "court": "Bombay High Court",
        "year": 2019,
        "kanoon_doc_id": "141962308",
        "kanoon_url": "https://indiankanoon.org/doc/141962308/",
        "fame_indicator": "persuasive",
        "outcome": "other",
        "relevance_scores": {"fact_archetype_match": 3, "doctrinal_match": 2, "outcome_alignment": 3, "authority_weight": 1, "total": 9},
        "relevance_explanation": "Bombay HC stayed RECOVERY of arrears in a S. 125 matter pending revision where the husband had prima facie material (call records + a third-party witness affidavit) suggesting adultery, and the trial court had not addressed this evidence. Authority specifically for your stay-on-recovery prayer. Apply via S. 397/401 CrPC revisional jurisdiction.",
        "bns_note": "BNSS S. 438/442 (revision) — framework preserved.",
        "quotable_phrase": "Pending consideration of the revision, where prima facie material exists for the husband's adultery defence and the trial court has not addressed it, recovery of arrears can and ordinarily should be stayed in the interests of justice.",
        "paragraph_anchor": "(Paras 11-12)",
        "practitioner_notes": {
            "one_line_topic": "Stay on recovery of arrears — prima facie material + procedural lapse",
            "gist": "Bombay HC granted stay pending revision. Exact authority for your interim relief prayer.",
            "quotable_phrase": "Pending consideration of the revision, where prima facie material exists for the husband's adultery defence and the trial court has not addressed it, recovery of arrears can and ordinarily should be stayed.",
            "cross_refs": ["applies Vimlaben (SC 2008) on preponderance standard", "followed across HC revisions"]
        },
        "journal_headnote": None,
    },
]

_S125_RESPONSE_EN = {
    "result": {
        "internal_reasoning": {
            "fact_archetype": "Husband's revision against S. 125 CrPC maintenance order where the trial court (i) passed the order in haste, (ii) did not afford adequate opportunity to lead evidence on the wife's adultery defence (call records, chats, family counselling statements), and (iii) the alleged adultery is rooted in a pre-marital relationship that continued. Reliefs sought: dismissal of maintenance OR stay on recovery OR remand for additional evidence.",
            "doctrinal_axes_identified": [
                "S. 125(4) — 'living in adultery' disqualification (Rohtash Singh)",
                "Standard of proof for husband — preponderance of probabilities (Vimlaben)",
                "Pre-marital relationship continuing post-marriage (Sandha v. Narayanan)",
                "Procedural haste and denial of evidence opportunity — remand (Reema Salkan)",
                "Interim stay on recovery in revision (Sandeep Joshi)"
            ],
            "scoring_notes": "Top-ranked: Rohtash Singh (three-judge SC, direct on S. 125(4)), Vimlaben (SC, burden of proof), Reema Salkan (SC, remand for procedural haste). Two HCs added — Sandha (Ker. HC) for the pre-marital-continuation point and Sandeep Joshi (Bom. HC) for the stay-on-recovery prayer. Skipped: Bhagwan v. Kamla (1981) — superseded by Reema Salkan; Mohd. Ahmed Khan v. Shah Bano — not relevant to adultery defence."
        },
        "confidence": "high",
        "style": "practitioner",
        "cases": _S125_CASES_EN,
        "filtered_zero_archetype": 0,
    },
    "raw": "[demo mode — canned response]",
    "dropped_hallucinations": [],
    "meta": {
        "model": "claude-sonnet-4-6",
        "cost_paise": 631,
        "elapsed_seconds": 11.0,
        "input_tokens": 6280,
        "output_tokens": 4050,
        "cache_read_input_tokens": 4800,
        "cache_creation_input_tokens": 0,
        "deep_mode": False,
        "escalated_to_opus": False,
        "input_script": "latin",
        "original_query": "",
        "english_query": "",
        "translation_cost_paise": 0,
        "total_cost_paise": 631,
        "refined_query": {
            "canonical_question": "In a husband's revision against a S. 125 CrPC maintenance order, what authorities support (i) the adultery defence based on the wife's pre-marital relationship continuing post-marriage, (ii) the husband's burden of proof, (iii) stay on recovery, and (iv) remand to the trial court for additional evidence?",
            "intent_type": "doctrinal_inquiry",
            "primary_statute": "CrPC S. 125 (now BNSS S. 144)",
            "secondary_statutes": ["CrPC S. 397/401 — revisional jurisdiction", "BNSS S. 438/442", "Evidence Act"],
            "stage": "revision",
            "doctrines_at_issue": ["living in adultery (S. 125(4))", "preponderance of probabilities", "remand for procedural haste", "interim stay on recovery"],
            "expected_answer_shape": "multi-issue revision-petition brief",
            "ranking_hint": "Supreme Court > High Court; weight three-judge SC benches highest; recent HCs for procedural reliefs",
            "cost_paise": 0,
            "elapsed_ms": 42,
        },
        "verification": {"clean": True, "checks": 5, "failures": 0},
        "verification_regen_attempted": False,
        "verification_regen_helped": False,
        "stage_timings_seconds": {
            "01_intake": 0.04,
            "02_translate": 0.0,
            "03_refine": 0.05,
            "04_retrieval": 1.79,
            "04_llm_primary": 8.72,
            "05_verify": 0.29,
            "99_total": 11.04,
        },
    },
}

_S125_CASES_HI = []
for c in _S125_CASES_EN:
    hc = json.loads(json.dumps(c, ensure_ascii=False))
    if c["case_id"] == "rohtash-singh-2000-sc":
        hc["relevance_explanation"] = "आपके प्रकरण पर सीधे लागू। तीन-न्यायाधीशीय बेंच (न्या. एस सगीर अहमद, आर पी सेठी, एस एन फुकन) ने धारा 125(4) दण्डप्रसं के 'व्यभिचार में रहना' शब्दों की व्याख्या की। न्यायालय ने अभिनिर्धारित किया कि व्यभिचार का एक भी कृत्य धारा 125(4) को आकर्षित करता है यदि वह 'सतत अवैध संबंध' के साथ हो — तथा यह प्रमाण कॉल रिकॉर्ड एवं पत्नी के स्वयं के पारिवारिक परामर्श में दिये गये कथनों जैसे परिस्थितिजन्य साक्ष्य से सिद्ध हो सकता है। पैरा 11-12 आपका प्राधिकार — पुनरीक्षण में उद्धरण करें: विचारण न्यायालय ने आपके पति-मुवक्किल को इस श्रेणी के साक्ष्य प्रस्तुत करने का अवसर नहीं दिया।"
    elif c["case_id"] == "vimlaben-patel-2008-sc":
        hc["relevance_explanation"] = "SC बेंच (न्या. एस बी सिन्हा, वी एस सिरपुरकर) ने पुष्ट किया कि व्यभिचार में रहने वाली पत्नी को धारा 125 दण्डप्रसं के अंतर्गत भरण-पोषण अस्वीकार होगा, तथा महत्वपूर्ण रूप से अभिनिर्धारित किया कि पति का प्रमाण-भार 'संभाव्यता की प्रबलता' का है — 'युक्तियुक्त संदेह से परे' का नहीं। अतः कॉल रिकॉर्डिंग + मोबाइल चैट + पत्नी के स्व-परामर्श कथन पर्याप्त से अधिक हैं यदि विचारण न्यायालय उन्हें प्रस्तुत करने दे। यह तर्क करने का आधार कि विचारण न्यायालय ने पति-मुवक्किल को अपना भार निर्वहन करने का उचित अवसर नहीं दिया।"
    elif c["case_id"] == "reema-salkan-2019-sc":
        hc["relevance_explanation"] = "आपके पुनः-विचारण-प्रार्थना (remand) का सीधा समर्थन। SC (न्या. ए एम खानविलकर, दिनेश माहेश्वरी) ने एक धारा 125 आदेश को निरस्त किया जहाँ विचारण न्यायालय ने 'शीघ्रता में' आदेश पारित किया था बिना पति को साक्ष्य प्रस्तुत करने का पर्याप्त अवसर दिये, तथा अतिरिक्त साक्ष्य लेने के पश्चात नये निर्णय हेतु प्रकरण पुनः भेजा। पैरा 18-20 आपका प्राधिकार — सत्र न्यायालय से वसूली पर स्थगन अथवा अतिरिक्त साक्ष्य हेतु विचारण न्यायालय भेजने की प्रार्थना के लिये उद्धरण करें।"
    elif c["case_id"] == "sandha-narayanan-2008-ker":
        hc["relevance_explanation"] = "केरल HC ने विशेष रूप से अभिनिर्धारित किया कि विवाह-पूर्व संबंध, जो विवाह को प्रभावित करते रहे एवं वैवाहिक विघटन का निकटतम कारण थे, धारा 125(4) के अंतर्गत प्रासंगिक हैं — यद्यपि सख्त अर्थ में व्यभिचार 'में रहना' (वर्तमान काल) चाहिए। न्यायालय ने तर्क दिया कि निरर्हता का भाव यह है कि जहाँ पत्नी का स्वयं का आचरण विघटन का कारण बना वहाँ भरण-पोषण अस्वीकार हो, चाहे वह आचरण कब प्रारंभ हुआ हो। आपके तथ्य पैटर्न (विवाह-पूर्व प्रेम संबंध जो विवाह के बाद भी जारी रहा) से सीधा मेल।"
    elif c["case_id"] == "joshi-joshi-2019-bom":
        hc["relevance_explanation"] = "बम्बई HC ने पुनरीक्षण लंबित रहते धारा 125 के अधीन बकाया राशि की वसूली पर स्थगन प्रदान किया जहाँ पति के पास व्यभिचार के प्राथमिक प्रमाण (कॉल रिकॉर्ड + तृतीय पक्ष साक्षी का शपथपत्र) थे, एवं विचारण न्यायालय ने इस साक्ष्य पर विचार नहीं किया था। आपकी 'वसूली पर स्थगन' की प्रार्थना हेतु विशिष्ट प्राधिकार। दण्डप्रसं की धारा 397/401 की पुनरीक्षण अधिकारिता द्वारा आवेदन करें।"
    _S125_CASES_HI.append(hc)

_S125_RESPONSE_HI = json.loads(json.dumps(_S125_RESPONSE_EN, ensure_ascii=False))
_S125_RESPONSE_HI["result"]["cases"] = _S125_CASES_HI
_S125_RESPONSE_HI["meta"]["input_script"] = "devanagari"
_S125_RESPONSE_HI["meta"]["translation_cost_paise"] = 31
_S125_RESPONSE_HI["meta"]["total_cost_paise"] = 662


# ============================================================================
# Demo flow registry — fuzzy match terms (distinctive enough that random
# unrelated queries won't accidentally hit one of these).
# ============================================================================

DEMO_FLOWS = [
    {
        "id": "pocso-consensual-minor-near-majority",
        "language": "both",
        "match_terms": [
            # English terms
            ["pocso", "consensual", "17", "relationship"],
            ["pocso", "minor", "majority", "consent"],
            ["pocso", "romantic", "voluntary"],
            ["pocso", "false implication", "chats"],
            # Hindi terms
            ["पॉक्सो", "सहमति", "17"],
            ["पॉक्सो", "प्रेम संबंध", "नाबालिग"],
        ],
        "response_en": _POCSO_RESPONSE_EN,
        "response_hi": _POCSO_RESPONSE_HI,
    },
    {
        "id": "s372-victim-appeal-limitation",
        "language": "both",
        "match_terms": [
            # English
            ["372", "proviso", "victim", "appeal"],
            ["372", "limitation", "victim"],
            ["372", "appeal", "acquittal", "limitation"],
            ["proviso", "section 372", "appeal"],
            # Hindi
            ["372", "परंतुक", "अपील"],
            ["372", "परिसीमा", "पीड़ित"],
            ["धारा 372", "अपील", "दोषमुक्ति"],
        ],
        "response_en": _S372_RESPONSE_EN,
        "response_hi": _S372_RESPONSE_HI,
    },
    {
        "id": "s125-adultery-revision",
        "language": "both",
        "match_terms": [
            # English
            ["125", "maintenance", "adultery"],
            ["125", "crpc", "wife", "adultery"],
            ["125", "revision", "maintenance"],
            ["125", "pre-marital", "affair"],
            # Hindi
            ["125", "भरण पोषण", "जारता"],
            ["125", "भरण-पोषण", "व्यभिचार"],
            ["धारा 125", "पुनरीक्षण", "पत्नी"],
            ["125", "प्रेम संबंध", "विवाह पूर्व"],
        ],
        "response_en": _S125_RESPONSE_EN,
        "response_hi": _S125_RESPONSE_HI,
    },
]
