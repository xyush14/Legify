"""Runtime LLM AUTHORING engine — the "draft anything from a prompt" path.

This is the NEW runtime authoring layer that complements the deterministic
canonical engine. The canonical engine (template_adapter / templates/*.py) mirrors
Vishnu ji's filed templates verbatim and writes ZERO free text — it is the moat and
always preferred where a type exists. But it only covers ~10–29 built types.

For everything else — a long-tail criminal application, a civil suit/petition, a
reply, any filing we have no template for — this module lets an LLM (DeepSeek at
runtime, never Claude — cost) AUTHOR the draft, but under the SAME discipline the
offline skill enforces, so the output reads like a senior advocate's filing and
NEVER fabricates law:

  1. FORMAT IS OURS, NOT THE MODEL'S. The model returns STRUCTURED CONTENT (party
     descriptors, numbered `यह कि …` paras, prayer, verification) as JSON; we render
     it into the canonical header + `cb-*` body — pixel-identical to a filed draft.
     The model cannot break the layout.
  2. ZERO FABRICATED CASE LAW (the existential rule — hallucinated citations are now
     judicial misconduct in India, SC 27-Feb-2026). The model may put a citation in
     the BODY only if it is on the per-type VERIFIED whitelist (real, pinpoint-checked
     in the skill's ledger). Everything else goes in a FLAGGED cite-at-hearing list —
     never the body. A regex guard (`_guard_citations`) catches leaks.
  3. SECTIONS CURRENT, KEYED TO FILING. BNSS-first, CrPC in brackets; the three LLM
     killers (§482/§528, §173/§193, §438) spelled out in the system prompt.
  4. LAW-MANDATED COMPANIONS surfaced (verification, affidavit, Rajnesh affidavit,
     §141 averment, etc.) as warnings the advocate (the gate) acts on.

Distilled from the headnote-legal-drafting skill references (court-formats.md,
application-frameworks.md, legal-frameworks.md) and the canonical bail renderer.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from headnote import config
from headnote.drafter.templates._doc_header import render_header, compose_court_name


# ===========================================================================
# 1) VERIFIED CITATION WHITELIST  — the ONLY authorities allowed in a body.
#    Real, pinpoint-checked (skill ledger). Keyed by matter family. The model
#    is handed only the slice relevant to the classified type; anything not on
#    the list it must route to cite-at-hearing (flagged), never the body.
# ===========================================================================
VERIFIED_CITATIONS: dict[str, list[dict]] = {
    "bail": [
        {"case": "Satender Kumar Antil v. CBI (2022) 10 SCC 51", "point": "bail categories A–D; bail is the rule"},
        {"case": "Sanjay Chandra v. CBI (2012) 1 SCC 40", "point": "bail secures attendance, is not punitive (Art. 21)"},
        {"case": "Prasanta Kumar Sarkar v. Ashis Chatterjee (2010) 14 SCC 496", "point": "the multi-factor bail checklist"},
        {"case": "P. Chidambaram v. ED (2019) 9 SCC 24", "point": "triple test — flight / tampering / influencing"},
        {"case": "Arnesh Kumar v. State of Bihar (2014) 8 SCC 273", "point": "arrest not automatic for ≤7-yr offences"},
        {"case": "Union of India v. K.A. Najeeb (2021) 3 SCC 713", "point": "Art. 21 trial-delay bail despite embargo"},
    ],
    "anticipatory_bail": [
        {"case": "Gurbaksh Singh Sibbia v. State of Punjab (1980) 2 SCC 565", "point": "anticipatory bail construed liberally"},
        {"case": "Sushila Aggarwal v. State (NCT Delhi) (2020) 5 SCC 1", "point": "not time-bound; continues till trial end"},
        {"case": "Arnesh Kumar v. State of Bihar (2014) 8 SCC 273", "point": "arrest not automatic for ≤7-yr offences"},
        {"case": "Satender Kumar Antil v. CBI (2022) 10 SCC 51", "point": "bail categories; cooperation"},
    ],
    "default_bail": [
        {"case": "Bikramjit Singh v. State of Punjab (2020) 12 SCC 327", "point": "default bail is an indefeasible fundamental right"},
        {"case": "Rakesh Kumar Paul v. State of Assam (2017) 15 SCC 67", "point": "pro-liberty computation of the 60/90-day clock"},
        {"case": "Uday Mohanlal Acharya v. State of Maharashtra (2001) 5 SCC 453", "point": "right must be availed before challan filed"},
    ],
    "maintenance": [
        {"case": "Rajnesh v. Neha (2021) 2 SCC 324", "point": "Affidavit of Assets & Liabilities mandatory; maintenance from date of application"},
        {"case": "Chaturbhuj v. Sita Bai (2008) 2 SCC 316", "point": "'unable to maintain herself' judged vs matrimonial standard"},
        {"case": "Bhuwan Mohan Singh v. Meena (2015) 6 SCC 353", "point": "able-bodied husband must earn; dignity of the wife"},
    ],
    "appeal": [
        {"case": "Chandrappa v. State of Karnataka (2007) 4 SCC 415", "point": "two reasonable views → the one favouring the accused"},
        {"case": "Sharad Birdhichand Sarda v. State of Maharashtra (1984) 4 SCC 116", "point": "the five panchsheel of circumstantial evidence"},
    ],
    "discharge": [
        {"case": "Union of India v. Prafulla Kumar Samal (1979) 3 SCC 4", "point": "grave suspicion test; no mini-trial at charge"},
        {"case": "Sajjan Kumar v. CBI (2010) 9 SCC 368", "point": "reaffirms the sift-and-weigh discharge test"},
        {"case": "Kahkashan Kausar v. State of Bihar (2022) 6 SCC 599", "point": "omnibus 498A allegations against relatives = no prima facie case"},
    ],
    "quashing": [
        {"case": "State of Haryana v. Bhajan Lal 1992 Supp (1) SCC 335", "point": "the seven categories for quashing; name the category"},
        {"case": "Gian Singh v. State of Punjab (2012) 10 SCC 303", "point": "quashing on genuine settlement of civil/matrimonial disputes"},
        {"case": "Parbatbhai Aahir v. State of Gujarat (2017) 9 SCC 641", "point": "settlement-quashing limits — not heinous/economic"},
    ],
    "revision": [
        {"case": "Amar Nath v. State of Haryana (1977) 4 SCC 137", "point": "intermediate (not interlocutory) orders are revisable"},
        {"case": "Madhu Limaye v. State of Maharashtra (1977) 4 SCC 551", "point": "framing/refusing charge is revisable"},
        {"case": "Amit Kapoor v. Ramesh Chander (2012) 9 SCC 460", "point": "the charge test on revision"},
    ],
    "cheque_138": [
        {"case": "C.C. Alavi Haji v. Palapetty Muhammed (2007) 6 SCC 555", "point": "deemed service of notice if correctly addressed + RPAD"},
        {"case": "Rangappa v. Sri Mohan (2010) 11 SCC 441", "point": "§139 presumption once signature admitted"},
        {"case": "Bridgestone India v. Inderpal Singh (2016) 2 SCC 75", "point": "jurisdiction = payee's bank branch (§142(2))"},
    ],
    "dv": [
        {"case": "Hiral Harsora v. Kusum Narottamdas Harsora (2016) 10 SCC 165", "point": "'adult male' struck down — female relatives can be respondents"},
        {"case": "Satish Chander Ahuja v. Sneha Ahuja (2021) 1 SCC 414", "point": "shared household — both limbs; can include in-laws' property"},
        {"case": "Prabha Tyagi v. Kamlesh Devi (2022) LiveLaw(SC) 474", "point": "right to reside not tied to actual residence; DIR not mandatory"},
    ],
    "divorce": [
        {"case": "Samar Ghosh v. Jaya Ghosh (2007) 4 SCC 511", "point": "illustrative instances of mental cruelty"},
    ],
}

# generic families carry NO body-eligible citations — long-tail / civil drafts
# argue on statute + facts; any authority the lawyer wants goes to cite-at-hearing.
# Civil types stay body-empty until Vishnu ji verifies a civil ledger (skill rule #2);
# their leading judgments live in the per-brief `cite_candidates` → cite_at_hearing only.
VERIFIED_CITATIONS["other_criminal"] = []
VERIFIED_CITATIONS["other_civil"] = []
for _t in ("recovery_suit", "injunction_suit", "specific_performance", "declaration_suit",
           "partition_suit", "eviction_suit", "written_statement", "consumer_complaint"):
    VERIFIED_CITATIONS[_t] = []


_NUM = re.compile(r"\d{1,4}")


def _cite_fingerprints(doc_family: str) -> set[tuple[str, str]]:
    """For each whitelisted citation, its (year, tail-number) fingerprint. This is
    SCRIPT-INDEPENDENT — a Hindi draft writes the case name in Devanagari but keeps the
    citation digits Western ('अर्नेश कुमार बनाम बिहार राज्य (2014) 8 एस.सी.सी. 273'), so
    matching on year+page recognises the same authority in either language."""
    fps: set[tuple[str, str]] = set()
    for c in VERIFIED_CITATIONS.get(doc_family, []):
        nums = _NUM.findall(c["case"])
        if not nums:
            continue
        year = next((n for n in nums if len(n) == 4 and n[:2] in ("19", "20")), nums[0])
        fps.add((year, nums[-1]))
    return fps


# ===========================================================================
# 2) PER-TYPE LEGAL BRIEF  — controlling test + para skeleton + companions.
#    Distilled from legal-frameworks.md / application-frameworks.md. Injected
#    into the system prompt so the model reasons from the RIGHT test and lays
#    the body out in the RIGHT order, in Vishnu's idiom.
# ===========================================================================
TYPE_BRIEFS: dict[str, dict] = {
    "bail": {
        "label_hi": "जमानत आवेदन पत्र", "label_en": "Bail Application",
        "court": "sessions", "case_code_hi": "प्रकरण क्रमांक", "case_code_en": "Criminal Case",
        "side_hi": "बन्दी की ओर से", "side_en": "On behalf of the Applicant",
        "section_hi": "धारा 483 बी.एन.एस.एस. (439 दं.प्र.सं.)",
        "brief": (
            "Regular bail. Classify (Antil A–D) first. The grounds section is the spine — each "
            "ground must neutralise one limb of the triple test (flight / tampering / influencing — "
            "Chidambaram) or one Sarkar factor. Plead: false implication, permanent resident (no "
            "flight/tampering), offence not death/life (forum competent), sole breadwinner if so, "
            "parity only with a role-equivalent co-accused, trial delay / long custody with the "
            "remand date. Disclose any prior rejected bail. Close with the oral-arguments line."
        ),
        "skeleton": [
            "recital: no other bail application pending or rejected (SC/HC/subordinate)",
            "F1: FIR/crime particulars (PS, district, crime no., sections, arrest date)",
            "[D]: prior magistrate/sessions bail rejected — if successive",
            "G: innocence / false implication",
            "[G]: sole breadwinner",
            "[G]: parity — role-equivalent co-accused already bailed",
            "G: offence not death/life — triable by this court",
            "G: permanent resident, no flight risk, no tampering",
            "[G]: trial delay / prolonged custody (give remand date)",
            "closer: अन्य तर्क वक्त बहस मौखिक रुप से निवेदित किये जावेंगे",
        ],
        "companions": ["शपथ पत्र (supporting affidavit + bail-disclosure block — Zeba Khan)", "vakalatnama"],
        "needs_verification": True, "needs_affidavit": True,
    },
    "anticipatory_bail": {
        "label_hi": "अग्रिम जमानत आवेदन पत्र", "label_en": "Anticipatory Bail Application",
        "court": "sessions", "case_code_hi": "प्रकरण क्रमांक", "case_code_en": "Criminal Case",
        "side_hi": "आवेदक की ओर से", "side_en": "On behalf of the Applicant",
        "section_hi": "धारा 482 बी.एन.एस.एस. (438 दं.प्र.सं.)",
        "brief": (
            "Anticipatory (pre-arrest) bail under BNSS §482 (NOT §438 — that is the revision band in "
            "BNSS; and §482 CrPC was quashing). Grounds pivot from custody to APPREHENSION OF ARREST + "
            "no custodial interrogation needed + full cooperation. Plead false/malicious implication, "
            "resident/no flight, and (if ≤7-yr offence) Arnesh Kumar + Antil. Prayer asks the court to "
            "call the case diary (मय कैफियत) and grant anticipatory bail on suitable security."
        ),
        "skeleton": [
            "recital: no other anticipatory application pending/rejected",
            "F1: FIR + reasonable apprehension of arrest",
            "G: false / malicious implication",
            "G: no custodial interrogation required; will cooperate with investigation",
            "[G]: parity / sole breadwinner",
            "G: permanent resident, no flight risk",
            "[G]: offence ≤7 yrs → Arnesh Kumar + Antil (verbatim, whitelisted)",
            "closer: oral arguments line",
        ],
        "companions": ["supporting affidavit (apprehension)", "vakalatnama"],
        "needs_verification": True, "needs_affidavit": True,
    },
    "maintenance": {
        "label_hi": "भरण-पोषण आवेदन पत्र", "label_en": "Maintenance Petition",
        "court": "family", "case_code_hi": "प्रकरण क्रमांक", "case_code_en": "Case",
        "side_hi": "आवेदिका की ओर से", "side_en": "On behalf of the Applicant",
        "section_hi": "धारा 144 बी.एन.एस.एस. (125 दं.प्र.सं.)",
        "brief": (
            "Maintenance under BNSS §144 (§125 CrPC). Rajnesh v. Neha is mandatory: plead the Affidavit "
            "of Assets & Liabilities as a companion, claim maintenance FROM THE DATE OF APPLICATION, and "
            "disclose any prior maintenance proceedings (amounts are set off, not stacked). Plead "
            "marriage, neglect/refusal to maintain, 'unable to maintain herself' vs the matrimonial "
            "standard, the husband's income & means, and the jurisdiction (where the wife resides)."
        ),
        "skeleton": [
            "F: marriage (Hindu rites, date/place)", "[F]: children",
            "F: dowry/cruelty/desertion narrative (case-specific)",
            "G: neglect / refusal to maintain (उपेक्षा)",
            "G: unable to maintain herself vs matrimonial standard",
            "G: husband's income & means; no other dependants",
            "G: quantum needed; jurisdiction (where wife resides)",
            "closer",
        ],
        "companions": ["Rajnesh Affidavit of Assets & Liabilities (urban/rural)", "interim-maintenance application", "vakalatnama"],
        "needs_verification": True, "needs_affidavit": True,
    },
    "appeal": {
        "label_hi": "आपराधिक अपील", "label_en": "Criminal Appeal",
        "court": "sessions", "case_code_hi": "आपराधिक अपील", "case_code_en": "Criminal Appeal",
        "side_hi": "अपीलार्थी की ओर से", "side_en": "On behalf of the Appellant",
        "section_hi": "धारा 415 बी.एन.एस.एस. (374 दं.प्र.सं.)",
        "brief": (
            "Appeal against conviction (BNSS §415 / §374 CrPC) — first appeal = full re-appreciation. "
            "Name the trial court, judge, case and sentence; 'no other appeal pending'. Grounds: faulty "
            "appreciation of evidence, material contradictions/improvements in PW testimony, benefit of "
            "doubt, issues not proved; for a circumstantial case reproduce the Sarda panchsheel. A "
            "SEPARATE §430/§389 suspension-of-sentence + bail-pending-appeal application is a companion."
        ),
        "skeleton": [
            "recital: no other appeal pending; certified copy of judgment annexed",
            "F: facts / questions for determination (प्रकरण के तथ्य)",
            "G: evidence mis-appreciated; benefit of doubt",
            "G: material contradictions/improvements in PW testimony",
            "[G]: circumstantial → Sarda panchsheel (whitelisted)",
            "G: issues not proved; clean image",
            "closer",
        ],
        "companions": ["separate §430/§389 suspension-of-sentence + bail-pending-appeal application", "certified copy of impugned judgment", "§5 condonation application if late", "vakalatnama"],
        "needs_verification": True, "needs_affidavit": False,
    },
    "discharge": {
        "label_hi": "उन्मोचन आवेदन पत्र", "label_en": "Discharge Application",
        "court": "sessions", "case_code_hi": "प्रकरण क्रमांक", "case_code_en": "Criminal Case",
        "side_hi": "आवेदक की ओर से", "side_en": "On behalf of the Applicant",
        "section_hi": "धारा 250 बी.एन.एस.एस. (227 दं.प्र.सं.)",
        "brief": (
            "Discharge — the test is GRAVE SUSPICION, not proof, and never a mini-trial (Prafulla Kumar "
            "Samal). Draft by showing the materials, TAKEN AT FACE VALUE, do not make out the INGREDIENTS "
            "of the offence — so grave suspicion is absent. NEVER argue credibility or contradictions "
            "(that is trial). For omnibus 498A allegations against relatives, plead Kahkashan Kausar."
        ),
        "skeleton": [
            "recital: stage — charge-sheet (§193) filed, matter fixed for charge",
            "F: prosecution case taken at face value",
            "G: ingredients of the offence not made out even at face value → grave suspicion absent",
            "[G]: omnibus 498A relatives — Kahkashan Kausar (whitelisted)",
            "closer",
        ],
        "companions": ["vakalatnama"],
        "needs_verification": True, "needs_affidavit": False,
    },
    "quashing": {
        "label_hi": "अन्तर्गत धारा 528 बी.एन.एस.एस.", "label_en": "Petition u/s 528 BNSS",
        "court": "hc", "case_code_hi": "एम.सी.आर.सी.", "case_code_en": "M.Cr.C.",
        "side_hi": "याचिकाकर्ता की ओर से", "side_en": "On behalf of the Petitioner",
        "section_hi": "धारा 528 बी.एन.एस.एस. (482 दं.प्र.सं.)",
        "brief": (
            "Quashing under BNSS §528 (the inherent power; §482 CrPC — NOT §482 BNSS, which is "
            "anticipatory bail). Used sparingly, no mini-trial. NAME the Bhajan Lal category invoked "
            "(commonly 1/3 ingredients not made out at face value, 5 absurd/improbable, 7 mala-fide/ "
            "counterblast) OR plead genuine settlement (Gian Singh / Parbatbhai — civil/matrimonial yes, "
            "heinous/economic no). Implead the complainant; annex the FIR; pray for interim stay."
        ),
        "skeleton": [
            "memo of parties (implead the complainant as Respondent 2)",
            "F: the impugned FIR / charge-sheet / proceeding + its stage",
            "G: the NAMED Bhajan Lal category (whitelisted) — or genuine settlement",
            "interim prayer: stay of investigation/trial",
            "closer",
        ],
        "companions": ["affidavit", "FIR copy annexure", "settlement affidavit (if settlement basis)", "vakalatnama (+ Adhivakta Kalyan Nidhi stamp)"],
        "needs_verification": True, "needs_affidavit": True,
    },
    "revision": {
        "label_hi": "आपराधिक पुनरीक्षण", "label_en": "Criminal Revision",
        "court": "sessions", "case_code_hi": "पुनरीक्षण", "case_code_en": "Criminal Revision",
        "side_hi": "पुनरीक्षणकर्ता की ओर से", "side_en": "On behalf of the Revisionist",
        "section_hi": "धारा 438 बी.एन.एस.एस. (397 दं.प्र.सं.)",
        "brief": (
            "Criminal revision — supervisory only (legality/propriety/correctness), NOT a re-appreciation "
            "of evidence. TWO threshold averments a draft must clear: (a) the impugned order is "
            "INTERMEDIATE, not purely interlocutory, hence revisable (Amar Nath / Madhu Limaye); (b) "
            "one-revision-only declaration. Grounds: perverse / no-evidence / misreading / jurisdictional "
            "error. Limitation 90 days. Big district sub-type: revision of §144/§125 maintenance orders."
        ),
        "skeleton": [
            "F: impugned order (court / date / decision)",
            "★ threshold: order is intermediate, NOT interlocutory → revisable; one-revision-only declaration",
            "G: perverse / no evidence / misreading / jurisdictional error",
            "closer",
        ],
        "companions": ["certified copy of impugned order", "§5 condonation if beyond 90 days", "vakalatnama"],
        "needs_verification": True, "needs_affidavit": False,
    },
    "cheque_138": {
        "label_hi": "आवेदन पत्र अन्तर्गत धारा 138 परक्राम्य लिखत अधिनियम", "label_en": "Application u/s 138 NI Act",
        "court": "magistrate", "case_code_hi": "प्रकरण क्रमांक", "case_code_en": "Criminal Case",
        "side_hi": "आवेदक की ओर से", "side_en": "On behalf of the Applicant",
        "section_hi": "धारा 138 परक्राम्य लिखत अधिनियम, 1881",
        "brief": (
            "§138 NI Act. The strict timeline IS the case: legally enforceable debt → cheque presented "
            "within 3 months → return memo → written demand notice within 30 days of the memo → drawer "
            "fails to pay within 15 days → offence complete day 16 → complaint within 1 month (§142). "
            "Jurisdiction = payee's bank branch (§142(2)). For a company cheque arraign the company AND "
            "the signatory under §141 (omitting the company is FATAL). Defence side attacks "
            "maintainability: notice not served/defective, premature/time-barred, no enforceable debt."
        ),
        "skeleton": [
            "F: relationship / legally enforceable debt",
            "F: cheque particulars; presentation within validity; dishonour (return memo)",
            "F: demand notice within 30 days; 15-day default → cause of action",
            "F: jurisdiction = payee's bank branch (§142(2))",
            "[F]: §141 company + signatory (if a company cheque)",
            "closer",
        ],
        "companions": ["§145 affidavit of evidence", "list of documents (cheque, return memo, notice, postal receipt)", "vakalatnama"],
        "needs_verification": True, "needs_affidavit": True,
    },
    "dv": {
        "label_hi": "आवेदन पत्र अन्तर्गत धारा 12 घरेलू हिंसा अधिनियम", "label_en": "Application u/s 12 PWDVA",
        "court": "magistrate", "case_code_hi": "प्रकरण क्रमांक", "case_code_en": "Case",
        "side_hi": "व्यथित की ओर से", "side_en": "On behalf of the Aggrieved Person",
        "section_hi": "धारा 12 घरेलू हिंसा से महिलाओं का संरक्षण अधिनियम, 2005",
        "brief": (
            "Domestic Violence §12 PWDVA — civil reliefs via the JMFC. Aggrieved person (व्यथित) is only a "
            "woman; respondents (प्रत्यर्थीगण) include female relatives (apply Harsora; plead each relative's "
            "SPECIFIC role). Plead §3 acts head-by-head WITH DATES (physical/sexual/verbal-emotional/"
            "ECONOMIC). Plead shared household — BOTH limbs (Ahuja). Reliefs as grounds: protection §18, "
            "residence §19, monetary §20 (Rajnesh affidavit, from date of application), custody §21, "
            "compensation §22, and ALWAYS plead interim/ex-parte relief §23 on affidavit."
        ),
        "skeleton": [
            "F: domestic relationship; §3 acts head-by-head with dates",
            "F: shared household — both limbs (resided there + respondent-owned/joint)",
            "G: §18 protection / §19 residence / §20 monetary / §21 custody / §22 compensation",
            "G: §23 interim/ex-parte relief on affidavit",
            "closer",
        ],
        "companions": ["Rajnesh Affidavit (for §20 monetary relief)", "supporting affidavit (§23)", "DIR (optional)", "vakalatnama"],
        "needs_verification": True, "needs_affidavit": True,
    },
    "default_bail": {
        "label_hi": "अनिवार्य जमानत आवेदन पत्र (धारा 187(3) बी.एन.एस.एस.)", "label_en": "Default / Statutory Bail Application",
        "court": "magistrate", "case_code_hi": "प्रकरण क्रमांक", "case_code_en": "Criminal Case",
        "side_hi": "बन्दी की ओर से", "side_en": "On behalf of the Applicant",
        "section_hi": "धारा 187(3) बी.एन.एस.एस. (167(2) दं.प्र.सं.)",
        "brief": (
            "Default/statutory bail under BNSS §187(3) (§167(2) CrPC) — MERITS-INDEPENDENT and "
            "time-critical. It accrues on the prosecution's FAILURE to file the charge-sheet within "
            "60 days (offence punishable up to 10 yrs) or 90 days (death/life/≥10 yrs) of the FIRST "
            "remand. The right is indefeasible (Bikramjit Singh) but must be EXERCISED BEFORE the "
            "challan is filed (Uday Mohanlal Acharya); computation is pro-liberty (Rakesh Kumar Paul). "
            "Plead the arithmetic exactly: arrest/remand date, days elapsed, no charge-sheet as on the "
            "filing date, and readiness to furnish bail. Gravity of the offence is IRRELEVANT — do not "
            "argue merits at all."
        ),
        "skeleton": [
            "F1: FIR/crime particulars + arrest date + FIRST remand date",
            "F: custody-days arithmetic — 60/90-day period expired on ____; charge-sheet NOT filed as on today",
            "G: indefeasible right to default bail accrued (whitelisted authorities)",
            "G: applicant is ready to furnish bail and abide by conditions",
            "closer: oral-arguments line",
        ],
        "companions": ["custody certificate / remand-date proof", "vakalatnama"],
        "needs_verification": True, "needs_affidavit": True,
    },
    "suspension_389": {
        "label_hi": "दण्डादेश निलंबन एवं जमानत आवेदन (धारा 430 बी.एन.एस.एस.)", "label_en": "Suspension of Sentence + Bail Pending Appeal",
        "court": "hc", "case_code_hi": "आपराधिक अपील", "case_code_en": "Criminal Appeal",
        "side_hi": "अपीलार्थी की ओर से", "side_en": "On behalf of the Appellant",
        "section_hi": "धारा 430 बी.एन.एस.एस. (389 दं.प्र.सं.)",
        "brief": (
            "Suspension of sentence + bail pending appeal under BNSS §430 (§389 CrPC). The bar is "
            "HIGHER than ordinary bail — the presumption of innocence is gone on conviction; the court "
            "looks for a FAIR CHANCE OF ACQUITTAL or something gross on the face of the record, and for "
            "heinous offences records detailed reasons. Plead: the conviction particulars (court, case, "
            "sections, sentence, date), the appeal already filed/admitted, the strongest appellate "
            "grounds in summary (why acquittal is fairly likely), custody suffered, and conduct. This is "
            "a SEPARATE application from the appeal memo itself."
        ),
        "skeleton": [
            "F: conviction + sentence particulars (trial court, case no., sections, sentence, date)",
            "F: appeal filed/admitted — particulars",
            "G: fair chance of acquittal — the strongest appellate grounds in summary",
            "G: custody already undergone; appeal will take time; conduct during trial",
            "G: applicant will abide by all conditions; permanent resident",
            "closer",
        ],
        "companions": ["certified copy of the impugned judgment", "vakalatnama"],
        "needs_verification": True, "needs_affidavit": True,
    },
    "divorce_13": {
        "label_hi": "विवाह विच्छेद याचिका (धारा 13 हि.वि.अ.)", "label_en": "Divorce Petition (S.13 HMA)",
        "court": "family", "case_code_hi": "वैवाहिक प्रकरण", "case_code_en": "Matrimonial Case",
        "side_hi": "याचिकाकर्ता की ओर से", "side_en": "On behalf of the Petitioner",
        "section_hi": "धारा 13 हिन्दू विवाह अधिनियम, 1955",
        "brief": (
            "Divorce under §13 HMA before the Family Court. Plead the marriage (date/place/rites), "
            "cohabitation and children, then the GROUND head-by-head with dated instances — cruelty "
            "(mental cruelty illustratives are in Samar Ghosh), desertion (2 yrs + animus deserendi), "
            "adultery, conversion, etc. IRRETRIEVABLE BREAKDOWN IS NOT A TRIAL-COURT GROUND — route the "
            "substance through cruelty/desertion. Jurisdiction per §19 HMA (marriage place / respondent "
            "residence / last resided together / petitioner-wife's residence)."
        ),
        "skeleton": [
            "F: marriage (date, place, rites); status & domicile of parties",
            "F: cohabitation, children (names/ages), where parties last resided together",
            "G: the §13 ground(s) head-by-head with dated instances",
            "F: no collusion / no condonation; no prior proceeding (or disclose it)",
            "G: jurisdiction (§19 HMA)",
            "closer",
        ],
        "companions": ["marriage proof (photographs/invitation/certificate)", "vakalatnama"],
        "needs_verification": True, "needs_affidavit": True,
    },
    "other_criminal": {
        "label_hi": "आवेदन पत्र", "label_en": "Criminal Application",
        "court": "sessions", "case_code_hi": "प्रकरण क्रमांक", "case_code_en": "Criminal Case",
        "side_hi": "आवेदक की ओर से", "side_en": "On behalf of the Applicant",
        "section_hi": "",
        "brief": (
            "A criminal application/petition for which we have no dedicated template. Identify the correct "
            "BNSS provision (NOT the spent CrPC number) and the relief sought, then lay the body out in "
            "Vishnu's idiom: a short factual recital, then numbered grounds, then the prayer. Keep the "
            "sections current (BNSS-first, CrPC in brackets) and key them to the FIR date if any. Do not "
            "invent facts or citations; leave unknown facts as ____ placeholders."
        ),
        "skeleton": [
            "F: brief facts / the matter giving rise to the application",
            "G: grounds in support of the relief (one ground per यह कि para)",
            "closer: oral-arguments line",
        ],
        "companions": ["vakalatnama"],
        "needs_verification": True, "needs_affidavit": False,
    },
    # ------------------------------------------------------------------
    # CIVIL FAMILY — per-suit briefs. Same discipline as the criminal set:
    # controlling test in the brief, mandatory plaint paras in the skeleton,
    # law-mandated companions surfaced. Leading judgments are OFFERED via
    # `cite_candidates` (cite_at_hearing only — the civil body whitelist is
    # empty until the advocate verifies a civil ledger).
    # ------------------------------------------------------------------
    "recovery_suit": {
        "label_hi": "धन वसूली वाद", "label_en": "Suit for Recovery of Money",
        "court": "civil", "case_code_hi": "व्यवहार वाद क्रमांक", "case_code_en": "Civil Suit",
        "side_hi": "वादी की ओर से", "side_en": "On behalf of the Plaintiff",
        "section_hi": "आदेश 7 नियम 1 सिविल प्रक्रिया संहिता, 1908",
        "brief": (
            "Money-recovery plaint. The transaction paras carry the case: WHAT was advanced (loan / goods "
            "supplied / services / advance), on WHICH dates, against WHICH documents (pronote, invoice, "
            "ledger, bank entries), and the demand + refusal. Give the arithmetic openly in one para: "
            "principal, agreed/claimed interest rate and period, total as on filing. Plead limitation "
            "(generally 3 years from the cause) and how the suit is within it; territorial jurisdiction "
            "under §20 CPC (defendant resides / cause of action arose); valuation = principal + accrued "
            "interest with ad-valorem court fee. Pray pendente-lite and future interest under §34 CPC. If "
            "the claim rests on a written contract or negotiable instrument, note that the summary "
            "procedure of Order XXXVII is available and say so in a warning."
        ),
        "skeleton": [
            "F: parties and their descriptions",
            "F: the dated transaction — what was advanced, against which documents",
            "F: demand and refusal/neglect to pay (dates; any demand notice)",
            "F: computation — principal + interest (rate, period) = total claimed",
            "F: cause of action — 'वाद कारण दिनांक ____ को … उत्पन्न हुआ' (date + place)",
            "F: jurisdiction (§20 CPC) — territorial + pecuniary",
            "F: मूल्यांकन एवं न्यायशुल्क — valuation and court fee paid",
            "F: limitation — period and why the suit is within it",
            "prayer: decree for the total, pendente-lite + future interest (§34 CPC), costs",
        ],
        "companions": ["list of documents (Order VII Rule 14) — pronote/invoices/bank statement/notice",
                       "court fee per valuation", "vakalatnama"],
        "cite_candidates": [
            {"case": "IDBI Trusteeship Services Ltd. v. Hubtown Ltd. (2017) 1 SCC 568",
             "point": "Order XXXVII leave-to-defend spectrum (only if drafted as a summary suit)"},
            {"case": "Mechelec Engineers & Manufacturers v. Basic Equipment Corpn. (1976) 4 SCC 687",
             "point": "classic leave-to-defend principles under Order XXXVII"},
        ],
        "needs_verification": True, "needs_affidavit": False,
    },
    "injunction_suit": {
        "label_hi": "स्थायी निषेधाज्ञा वाद", "label_en": "Suit for Permanent Injunction",
        "court": "civil", "case_code_hi": "व्यवहार वाद क्रमांक", "case_code_en": "Civil Suit",
        "side_hi": "वादी की ओर से", "side_en": "On behalf of the Plaintiff",
        "section_hi": "धारा 38 विनिर्दिष्ट अनुतोष अधिनियम, 1963",
        "brief": (
            "Permanent injunction under §38 Specific Relief Act. The spine: (1) the plaintiff's lawful "
            "possession/right over the suit property — a full वादग्रस्त संपत्ति description para with "
            "boundaries (चौहद्दी), khasra/survey/house number; (2) the defendant's SPECIFIC acts of "
            "interference with dates (threats, attempted dispossession, construction, obstruction); "
            "(3) why the injury is continuing and not compensable in money. Jurisdiction: §16 CPC — where "
            "the property is situate. Valuation commonly notional under §7(iv)(d) Court Fees Act with "
            "fixed fee. ALWAYS produce the companion temporary-injunction application under Order XXXIX "
            "Rules 1–2 read with §151 CPC pleading the triple test — prima facie case, balance of "
            "convenience, irreparable injury — on supporting affidavit."
        ),
        "skeleton": [
            "F: parties and their descriptions",
            "F: वादग्रस्त संपत्ति — full description with boundaries/khasra + plaintiff's possession/title basis",
            "F: defendant's acts of interference — specific, dated instances",
            "F: injury continuing; not compensable in money; no adequate alternative remedy",
            "F: cause of action (date of the latest interference) + jurisdiction (§16 CPC — situs)",
            "F: मूल्यांकन एवं न्यायशुल्क (§7(iv)(d) Court Fees Act) + limitation (continuing cause)",
            "prayer: permanent injunction restraining the specific acts + costs",
        ],
        "companions": ["Order XXXIX R.1–2 temporary-injunction application + supporting affidavit (triple test)",
                       "list of documents (Order VII Rule 14) — title/possession papers, site map/khasra",
                       "vakalatnama"],
        "cite_candidates": [
            {"case": "Dalpat Kumar v. Prahlad Singh (1992) 1 SCC 719",
             "point": "the temporary-injunction triple test — prima facie case, balance of convenience, irreparable injury"},
            {"case": "Wander Ltd. v. Antox India (P) Ltd. 1990 Supp SCC 727",
             "point": "discretionary injunction orders — scope of appellate interference"},
        ],
        "needs_verification": True, "needs_affidavit": False,
    },
    "specific_performance": {
        "label_hi": "विनिर्दिष्ट अनुपालन वाद", "label_en": "Suit for Specific Performance",
        "court": "civil", "case_code_hi": "व्यवहार वाद क्रमांक", "case_code_en": "Civil Suit",
        "side_hi": "वादी की ओर से", "side_en": "On behalf of the Plaintiff",
        "section_hi": "धारा 10 विनिर्दिष्ट अनुतोष अधिनियम, 1963",
        "brief": (
            "Specific performance of an agreement to sell (§10 SRA — after the 2018 amendment it is a "
            "statutory rule, no longer pure discretion). THE FATAL TRAP: §16(c) — the plaint MUST aver the "
            "plaintiff's CONTINUOUS readiness and willingness to perform, from the agreement date to the "
            "filing; omitting this averment is fatal. Plead: the agreement (date, property description, "
            "total consideration, earnest/part payment with receipts), the agreed time/manner of "
            "performance, the plaintiff's performance steps (payments, notices, presence before the "
            "sub-registrar if any), and the defendant's breach/refusal with dates. Limitation Art. 54: "
            "3 years from the date fixed for performance, or from refusal where no date is fixed. "
            "Ad-valorem court fee on the consideration. Pray in the alternative: refund of earnest with "
            "interest + damages/charge on the property. A companion Order XXXIX application to restrain "
            "alienation of the suit property is standard."
        ),
        "skeleton": [
            "F: parties and their descriptions",
            "F: the agreement — date, property (full description), consideration, earnest paid (receipts)",
            "F: agreed time/manner of performance; plaintiff's performance steps, dated",
            "F: §16(c) — plaintiff was and REMAINS ready & willing to perform (continuous averment)",
            "F: defendant's breach / refusal — dated instances; any legal notice",
            "F: cause of action + jurisdiction (§16 CPC — situs) + limitation (Art. 54)",
            "F: मूल्यांकन एवं न्यायशुल्क — ad valorem on the consideration",
            "prayer: (अ) specific performance + registration; (ब) alternative — refund of earnest + interest/damages; (स) costs",
        ],
        "companions": ["Order XXXIX application to restrain alienation + affidavit",
                       "list of documents (Order VII Rule 14) — agreement, receipts, notices",
                       "vakalatnama"],
        "cite_candidates": [
            {"case": "Kamal Kumar v. Premlata Joshi (2019) 3 SCC 704",
             "point": "the material questions a specific-performance plaintiff must plead and prove"},
            {"case": "Saradamani Kandappan v. S. Rajalakshmi (2011) 12 SCC 18",
             "point": "time/price-escalation and payment default in agreements to sell immovable property"},
        ],
        "needs_verification": True, "needs_affidavit": False,
    },
    "declaration_suit": {
        "label_hi": "घोषणा वाद", "label_en": "Suit for Declaration",
        "court": "civil", "case_code_hi": "व्यवहार वाद क्रमांक", "case_code_en": "Civil Suit",
        "side_hi": "वादी की ओर से", "side_en": "On behalf of the Plaintiff",
        "section_hi": "धारा 34 विनिर्दिष्ट अनुतोष अधिनियम, 1963",
        "brief": (
            "Declaration under §34 SRA of the plaintiff's legal character or right to property. Plead the "
            "plaintiff's title/right chain, then the defendant's DENIAL or the cloud cast on it (the "
            "instrument/mutation/claim) with dates — that denial is the cause of action. THE PROVISO "
            "TRAP: where further relief (possession, injunction, cancellation) is available, a bare "
            "declaration is barred — ALWAYS join the consequential relief the facts support. Limitation "
            "Art. 58: 3 years from when the right to sue first accrues. Valuation under §7(iv)(c) Court "
            "Fees Act (declaration with consequential relief). Jurisdiction §16 CPC for property."
        ),
        "skeleton": [
            "F: parties and their descriptions",
            "F: the plaintiff's title/right — the chain, with documents and dates",
            "F: वादग्रस्त संपत्ति description (if property) — boundaries/khasra",
            "F: the defendant's denial / the cloud (instrument, mutation, claim) — dated",
            "F: consequential relief needed (possession / injunction / cancellation) — §34 proviso satisfied",
            "F: cause of action + jurisdiction + limitation (Art. 58) + मूल्यांकन एवं न्यायशुल्क",
            "prayer: (अ) declaration; (ब) the consequential relief; (स) costs",
        ],
        "companions": ["list of documents (Order VII Rule 14) — title papers, revenue record",
                       "court fee per §7(iv)(c) valuation", "vakalatnama"],
        "cite_candidates": [
            {"case": "Anathula Sudhakar v. P. Buchi Reddy (2008) 4 SCC 594",
             "point": "when a suit needs declaration of title vs injunction simpliciter — the classic exposition"},
        ],
        "needs_verification": True, "needs_affidavit": False,
    },
    "partition_suit": {
        "label_hi": "बंटवारा वाद", "label_en": "Suit for Partition & Separate Possession",
        "court": "civil", "case_code_hi": "व्यवहार वाद क्रमांक", "case_code_en": "Civil Suit",
        "side_hi": "वादी की ओर से", "side_en": "On behalf of the Plaintiff",
        "section_hi": "आदेश 7 नियम 1 सिविल प्रक्रिया संहिता, 1908",
        "brief": (
            "Partition and separate possession of joint / ancestral property. Open with the वंशावली "
            "(genealogy) para establishing how the parties are co-sharers; then the SCHEDULE of joint "
            "properties (सूची अ/ब — each item fully described); then the plaintiff's share as a fraction "
            "WITH the basis (succession/coparcenary — daughters are equal coparceners); then the demand "
            "for partition and refusal (the cause of action). Court fee: FIXED if the plaintiff is in "
            "joint possession; AD VALOREM on the share if excluded from possession — plead possession "
            "status explicitly. Prayer follows the two-decree structure: preliminary decree declaring the "
            "share, then final decree by commissioner (Order XXVI) with mesne-profits enquiry if excluded."
        ),
        "skeleton": [
            "F: parties and their descriptions",
            "F: वंशावली — the family tree establishing co-ownership",
            "F: schedule of joint properties (सूची) — each fully described",
            "F: the plaintiff's share (fraction) + its legal basis; possession status (joint / excluded)",
            "F: demand for partition and refusal — dated (cause of action)",
            "F: jurisdiction (§16 CPC) + मूल्यांकन एवं न्यायशुल्क (fixed vs ad valorem per possession)",
            "prayer: (अ) preliminary decree declaring the share; (ब) final partition via commissioner + separate possession; (स) mesne profits; (द) costs",
        ],
        "companions": ["list of documents (Order VII Rule 14) — revenue record, mutation, family documents",
                       "vakalatnama"],
        "cite_candidates": [
            {"case": "Vineeta Sharma v. Rakesh Sharma (2020) 9 SCC 1",
             "point": "daughters are coparceners by birth — equal share (Hindu Succession, §6 as amended)"},
        ],
        "needs_verification": True, "needs_affidavit": False,
    },
    "eviction_suit": {
        "label_hi": "बेदखली एवं बकाया किराया वाद", "label_en": "Suit for Eviction & Arrears of Rent",
        "court": "civil", "case_code_hi": "व्यवहार वाद क्रमांक", "case_code_en": "Civil Suit",
        "side_hi": "वादी की ओर से", "side_en": "On behalf of the Plaintiff",
        "section_hi": "राज्य के लागू किरायेदारी/स्थान नियंत्रण अधिनियम की सुसंगत धारा",
        "brief": (
            "Landlord's eviction suit — governed by the RENT-CONTROL statute OF THE SUIT'S OWN STATE (this "
            "is a State subject, so use the correct State Act, not MP's by default): e.g. MP Accommodation "
            "Control Act 1961 §12(1), Maharashtra Rent Control Act 1999, Delhi Rent Act, West Bengal "
            "Premises Tenancy Act 1997, Tamil Nadu Tenancy Act 2017, Rajasthan Rent Control Act 2001, etc. "
            "Eviction lies ONLY on that Act's enumerated grounds, and the plaint must plead the EXACT "
            "clause(s). The common workhorses across these Acts: (1) ARREARS — tenant in arrears who failed "
            "to pay within the statutory period of a written demand notice (plead the notice, its service, "
            "the exact arrears computation, and any statutory deposit protection); and (2) BONA FIDE "
            "REQUIREMENT (residential/non-residential) — plead the landlord's genuine need AND that he has "
            "no other reasonably suitable accommodation of his own in the city. Plead the tenancy (start, "
            "monthly rent, premises description), the ground facts with dates, and any quit notice. If the "
            "State's Act / section is unknown, write ____ and flag it. Pray eviction + arrears + mesne "
            "profits/occupation charges till possession."
        ),
        "skeleton": [
            "F: parties; the premises — full description",
            "F: the tenancy — commencement, monthly rent, terms; rent last paid up to ____",
            "F: the §12(1) ground(s) — clause named, facts pleaded specifically with dates",
            "F: demand/quit notice — date, service, tenant's default (arrears computation)",
            "F: cause of action + jurisdiction + मूल्यांकन एवं न्यायशुल्क (annual rent basis)",
            "prayer: (अ) eviction & vacant possession; (ब) arrears of rent; (स) mesne profits till possession; (द) costs",
        ],
        "companions": ["demand/quit notice + service proof (registered post AD)",
                       "list of documents (Order VII Rule 14) — rent note/receipts, notice",
                       "vakalatnama"],
        "cite_candidates": [],
        "needs_verification": True, "needs_affidavit": False,
    },
    "written_statement": {
        "label_hi": "जवाबदावा (लिखित कथन)", "label_en": "Written Statement",
        "court": "civil", "case_code_hi": "व्यवहार वाद क्रमांक", "case_code_en": "Civil Suit",
        "side_hi": "प्रतिवादी की ओर से", "side_en": "On behalf of the Defendant",
        "section_hi": "आदेश 8 नियम 1 सिविल प्रक्रिया संहिता, 1908",
        "brief": (
            "Defendant's written statement under Order VIII. Structure is rigid: (1) प्रारंभिक आपत्तियां — "
            "preliminary objections (maintainability, limitation, jurisdiction, under-valuation/court fee, "
            "non-joinder/mis-joinder, no cause of action, §34 SRA bar — whichever the facts support); "
            "(2) परिच्छेदवार जवाब — a PARA-WISE reply to every plaint para, each specifically admitted or "
            "denied. THE TRAP: Order VIII Rules 3–5 — an evasive or general denial is DEEMED ADMISSION; "
            "deny each allegation specifically. (3) विशेष कथन — the defendant's own affirmative case; "
            "(4) set-off / counter-claim under Order VIII Rules 6/6A if the facts support one (it needs "
            "its own court fee). Verification per Order VI Rule 15. Timing: 30 days from summons, outer "
            "limit 90 days (Order VIII Rule 1) — warn if late."
        ),
        "skeleton": [
            "head: प्रारंभिक आपत्तियां (preliminary objections)",
            "G: each preliminary objection — one para each (limitation / jurisdiction / valuation / non-joinder / no cause of action)",
            "head: परिच्छेदवार जवाब (para-wise reply)",
            "F: reply to EACH plaint para in order — specific admission or specific denial (no evasive denials)",
            "head: विशेष कथन (special pleas)",
            "F: the defendant's affirmative facts, dated",
            "[G]: set-off / counter-claim (Order VIII R.6/6A) with its own valuation",
            "prayer: dismissal of the suit with costs (+ counter-claim decree if pleaded)",
        ],
        "companions": ["list of documents relied on by the defendant",
                       "court fee on counter-claim (if any)", "vakalatnama"],
        "cite_candidates": [
            {"case": "Balraj Taneja v. Sunil Madan (1999) 8 SCC 396",
             "point": "non-traverse / evasive denial in the written statement — consequences (O8 R3–5)"},
        ],
        "needs_verification": True, "needs_affidavit": False,
    },
    "consumer_complaint": {
        "label_hi": "उपभोक्ता परिवाद", "label_en": "Consumer Complaint",
        "court": "consumer", "case_code_hi": "उपभोक्ता परिवाद क्रमांक", "case_code_en": "Consumer Complaint",
        "side_hi": "परिवादी की ओर से", "side_en": "On behalf of the Complainant",
        "section_hi": "धारा 35 उपभोक्ता संरक्षण अधिनियम, 2019",
        "brief": (
            "Consumer complaint before the District Commission under §35 CPA 2019 (NOT a CPC plaint — a "
            "complaint, but pleaded in numbered paras). First para must establish the complainant IS a "
            "consumer (§2(7)): goods/services bought for consideration, not for a commercial purpose "
            "(livelihood/self-employment excepted). Then the transaction (what, when, from whom, amount "
            "paid — annex bill/receipt), then the defect in goods / deficiency in service (§2(11)) or "
            "unfair trade practice — specific, dated instances; then the complaints made to the opposite "
            "party and its failure. Jurisdiction: District Commission where the opposite party works/ "
            "resides OR where the COMPLAINANT resides/works (§34(2)(d)); pecuniary limit is reckoned on "
            "the CONSIDERATION PAID, not the compensation claimed. Limitation: 2 years from the cause "
            "(§69; condonation possible on sufficient cause). Reliefs per §39: refund/replacement, "
            "compensation for loss and harassment, litigation costs. Affidavit in support is mandatory."
        ),
        "skeleton": [
            "F: the complainant is a consumer (§2(7)) — consideration paid, personal (non-commercial) purpose",
            "F: the transaction — goods/service, date, amount paid, receipts/invoices",
            "F: defect / deficiency (§2(11)) / unfair trade practice — specific, dated",
            "F: complaints/notice to the opposite party and its failure or inaction",
            "F: jurisdiction — §34(2)(d) (complainant's residence allowed) + consideration within the pecuniary limit",
            "F: limitation — within 2 years (§69)",
            "prayer: (अ) refund/replacement/rectification; (ब) compensation for loss and mental agony; (स) litigation costs",
        ],
        "companions": ["supporting affidavit (mandatory)", "bills/receipts + correspondence annexures",
                       "prescribed complaint fee", "vakalatnama"],
        "cite_candidates": [
            {"case": "Lucknow Development Authority v. M.K. Gupta (1994) 1 SCC 243",
             "point": "'service' construed widely; statutory bodies answerable; compensation for harassment"},
        ],
        "needs_verification": True, "needs_affidavit": True,
    },
    "other_civil": {
        "label_hi": "वाद / आवेदन पत्र", "label_en": "Plaint / Application",
        "court": "civil", "case_code_hi": "व्यवहार वाद क्रमांक", "case_code_en": "Civil Suit",
        "side_hi": "वादी की ओर से", "side_en": "On behalf of the Plaintiff",
        "section_hi": "",
        "brief": (
            "A civil matter for which no specific brief exists (the specific civil types — recovery, "
            "injunction, specific performance, declaration, partition, eviction, written statement, "
            "consumer — have their own briefs; this is the true residual: probate/succession, misc. civil "
            "applications, execution, appointment of guardian, etc.). Lay it out as a plaint or "
            "application as the relief demands: parties, dated material facts, cause of action, "
            "jurisdiction & valuation with court fee, limitation, relief, and verification under Order VI "
            "Rule 15 CPC. Cite the correct CPC Order/Rule and substantive statute. Do not invent facts or "
            "case law."
        ),
        "skeleton": [
            "F: parties and their description",
            "F: material facts, numbered chronologically with dates",
            "F: cause of action + jurisdiction + मूल्यांकन एवं न्यायशुल्क",
            "F: limitation — period and why within it",
            "G: the plaintiff's entitlement in law",
            "prayer: the substantive relief + costs",
        ],
        "companions": ["court-fee per valuation", "list of documents (Order VII Rule 14)", "vakalatnama"],
        "needs_verification": True, "needs_affidavit": False,
    },
}


def brief_for(doc_type: str) -> dict:
    return TYPE_BRIEFS.get(doc_type) or TYPE_BRIEFS["other_criminal"]


_FAMILY_ALIAS = {"divorce_13": "divorce", "suspension_389": "appeal"}

# the civil doc_types — used to key the CPC drafting addendum and the civil fallback
CIVIL_TYPES = {"recovery_suit", "injunction_suit", "specific_performance", "declaration_suit",
               "partition_suit", "eviction_suit", "written_statement", "consumer_complaint",
               "other_civil"}


def family_for(doc_type: str) -> str:
    """Map a classifier doc_type to its citation-whitelist family."""
    doc_type = _FAMILY_ALIAS.get(doc_type, doc_type)
    return doc_type if doc_type in VERIFIED_CITATIONS else (
        "other_civil" if doc_type in CIVIL_TYPES else "other_criminal"
    )


# ===========================================================================
# 3) THE HOUSE-STYLE SYSTEM PROMPT  — format + idiom + structure + the guards.
# ===========================================================================
_SECTION_MAP_NOTE = (
    "BNSS↔CrPC — lead BNSS, CrPC in brackets, keyed to the FIR date (before 1-Jul-2024 → CrPC). "
    "THE THREE KILLERS an LLM gets wrong: (1) quashing = BNSS §528 (CrPC §482); BNSS §482 is "
    "ANTICIPATORY BAIL. (2) FIR = BNSS §173 (CrPC §154); charge-sheet = BNSS §193 (CrPC §173). "
    "(3) anticipatory = BNSS §482 (CrPC §438); BNSS §438 is in the revision band. "
    "Other: bail Sessions/HC §483 (439); Magistrate bail §480 (437); default bail §187 (167); "
    "maintenance §144 (125); discharge §250/§262 (227/239); appeal §415 (374); suspension §430 (389). "
    "Substantive offence follows the FIR's code (IPC→BNS: 302→103, 420→318, 376→64)."
)

HOUSE_STYLE = """You are the drafting engine of Headnote, drafting for a senior Indian litigation advocate.
Headnote is used by advocates ACROSS INDIA — every State and Union Territory, every trial court, tribunal and
High Court. You produce a COURT-READY litigation draft in that advocate's house style — it must be
indistinguishable from a document a senior advocate's office actually files IN THAT STATE'S courts. NOT a
generic, plain-English, "school application" letter. You write the SUBSTANCE (facts recital, the numbered
grounds, the prayer); the page layout is applied by Headnote, so you return STRUCTURED JSON only.

DRAFT FOR THE MATTER'S OWN STATE — never assume Madhya Pradesh (or any single State). Read the forum/State
from the matter and draft for THAT jurisdiction: its High Court and bench, its trial-court cause-title idiom,
and its State-specific statutes. If the State/court is not stated, leave the location blanks as ____ — do NOT
default to a State.

HOUSE STYLE — follow exactly:
• LANGUAGE: write in the language requested ({lang}). If Hindi, use formal Devanagari court register (NOT
  Hinglish, NOT casual Hindi) — natural for Hindi-belt forums (UP, MP, Bihar, Rajasthan, Chhattisgarh,
  Jharkhand, Uttarakhand, Haryana, HP, Delhi). If English, use formal Indian court English — the norm for
  most other High Courts and many State trial courts. Match the register a senior office in that State files.
  ONE SCRIPT THROUGHOUT: in a Hindi draft, names/places the advocate typed in Roman ("Ayush Shivhare s/o
  Vishnu, Gwalior") are TRANSLITERATED to Devanagari (आयुष शिवहरे पुत्र विष्णु, ग्वालियर) and English fact
  fragments are written as formal Hindi — never leave a Roman name inside a Hindi sentence. Likewise an
  English draft carries romanised names, not Devanagari. Dates/numbers keep their given values.
• PARTIES: a full descriptor block, not a bare name. Applicant = naam + पुत्र/पुत्री/पत्नी श्री <father/husband>
  + आयु + व्यवसाय + निवासी <address>, जिला <district> (<state>). Respondent for a State criminal matter =
  "<state> शासन द्वारा, पुलिस थाना <PS>, जिला <district>". Use the right party LABELS per matter:
  आवेदक/आवेदिका (applicant), प्रार्थी/प्रार्थिनी (petitioner in body), अनावेदक (non-applicant/State),
  व्यथित (DV aggrieved), प्रत्यर्थीगण (DV respondents), वादी/प्रतिवादी (civil plaintiff/defendant),
  अपीलार्थी (appellant), पुनरीक्षणकर्ता (revisionist).
• COURT NAME: compose the correct cause-title for the matter's OWN State and forum. Trial courts (any State):
  "न्यायालय माननीय सत्र न्यायाधीश महोदय, <नगर> (<राज्य>)", "…न्यायिक दण्डाधिकारी प्रथम श्रेणी…, <नगर> (<राज्य>)",
  "…प्रधान न्यायाधीश, कुटुम्ब न्यायालय, <नगर> (<राज्य>)"; in English "Court of the Sessions Judge, <city>
  (<State>)". HIGH COURT — use the RIGHT High Court for the State (there are 25). Map the State→HC, and the
  district→bench: Maharashtra/Goa→Bombay HC (benches Nagpur/Aurangabad/Panaji); UP→Allahabad HC (Lucknow
  bench); WB→Calcutta HC; TN/Puducherry→Madras HC (Madurai bench); Rajasthan→Rajasthan HC (Jaipur/Jodhpur);
  Punjab/Haryana/Chandigarh→Punjab & Haryana HC; Assam/Nagaland/Mizoram/Arunachal→Gauhati HC (Kohima/Aizawl/
  Itanagar); Karnataka→Karnataka HC (Dharwad/Kalaburagi); MP→MP HC (Indore/Gwalior/Jabalpur); Tripura→Tripura
  HC at Agartala; Kerala→Kerala HC; Gujarat→Gujarat HC; Delhi→Delhi HC; Telangana/AP, Bihar→Patna, Odisha→
  Orissa, J&K & Ladakh, HP, Uttarakhand, Jharkhand, Chhattisgarh, Sikkim, Manipur, Meghalaya — each its own HC.
  English HC form "In the High Court of <Name> at <Seat>". If you cannot tell the State, write ____ — NEVER
  write "Madhya Pradesh"/"मध्यप्रदेश" for a matter that is not from MP.
• BODY: every numbered paragraph BEGINS with "यह कि" (you may write "यहकि"). Facts first, then grounds —
  one discrete point per paragraph, in formal register, justified prose. After the last ground, ALWAYS add
  the closer: "यह कि, अन्य तर्क वक्त बहस मौखिक रुप से निवेदित किये जावेंगे।"
• PRAYER: open with "अतः श्रीमान न्यायालय से प्रार्थना है कि …" and end with "… करने की कृपा करें।"
• Use court idiom, not literal translation: मिथ्या आधारों पर आरोपी बनाया, न्यायिक अभिरक्षा में निरुद्ध,
  स्थायी निवासी, साक्ष्य को प्रभावित किये जाने की कोई संभावना नहीं, समानता के सिद्धान्त, युक्तियुक्त आशंका.

SECTIONS — {section_map}

ZERO FABRICATION — THE ABSOLUTE RULE:
• You must NOT invent ANY case citation. In India, citing a non-existent or mis-stated judgment is judicial
  misconduct. You may write a case citation in the BODY paragraphs ONLY if it is in the VERIFIED list below
  (these are real and pinpoint-checked) AND it genuinely fits the matter. Reproduce it exactly as listed.
• If you want to rely on any OTHER authority, do NOT put it in the body. Put a short, accurate, real reference
  in "cite_at_hearing" — and if you are not certain a judgment exists with that exact citation, DO NOT list it
  at all. An empty cite_at_hearing is correct and safe.
• FACTS — THE GROUNDING CONTRACT (as absolute as the citation rule):
  – Every concrete fact in the draft — a name, a relationship (wife/husband/son/father/heir/guarantor),
    a date, a money amount, an FIR/case/account number, an address, an event — MUST come from what the
    advocate actually gave you. If the advocate did not state it, it does not exist.
  – NEVER manufacture a fact pattern or a narrative to make the draft "look complete". Do not infer a
    relationship, invent a party, assume a reason for a loan, or supply a plausible date/amount. A draft
    that is mostly "____" blanks is CORRECT and safe; an invented story is a career-ending fabrication for
    the advocate and the exact failure that loses their trust.
  – For every fact the structure needs but the advocate did not give, write "____" — never a guess, never a
    placeholder name like "Ram Kumar" or a specimen date. List each such gap in "warnings" so the advocate
    knows what to fill.
  – USE THE WHOLE BRIEF — the mirror duty of the same contract: every fact the advocate DID give (each name,
    relationship, date, amount, FIR/case/account number, address, section, event) MUST appear in the draft at
    its proper place. DROPPING a given fact is as serious a failure as inventing one — the advocate wrote it
    because the court needs it. If a given fact fits nowhere in the skeleton, add a numbered fact para for it;
    never discard it.
  – When the input is thin, WRITE A THIN DRAFT (the skeleton with ____ blanks). Do not pad it with content.

VERIFIED CITATIONS YOU MAY USE IN THE BODY (only these; reproduce exactly; omit if not apposite):
{verified}

REAL AUTHORITIES YOU MAY OFFER IN cite_at_hearing ONLY (never the body — not yet body-verified;
offer only those genuinely apposite, reproduced exactly):
{candidates}

THE MATTER TYPE: {label}
CONTROLLING LAW & APPROACH: {brief}
BODY SKELETON (lay the paragraphs out in this order; [..] paras only if the facts support them):
{skeleton}

Return ONLY valid JSON (no markdown fence), in this exact shape:
{
  "lang": "hi" | "en",
  "court_level": "magistrate" | "cjm" | "sessions" | "principal_sessions" | "family" | "hc" | "civil" | "district_judge" | "consumer",
  "court_name": "<full cause-title in the chosen language; compose if user didn't give the city>",
  "case_code": "<एम.सी.आर.सी. / प्रकरण क्रमांक / आपराधिक अपील etc.>",
  "case_number": "", "case_year": "<YYYY or blank>",
  "side_label": "<बन्दी की ओर से / आवेदक की ओर से etc.; '' if none>",
  "title_line": "<the underlined title, e.g. 'जमानत आवेदन पत्र अन्तर्गत धारा 483 बी.एन.एस.एस. (439 दं.प्र.सं.)'>",
  "applicant_label": "<आवेदक/आवेदिका/प्रार्थी/व्यथित/वादी/अपीलार्थी>",
  "applicant_desc": ["<descriptor line 1>", "<line 2>", "..."],
  "respondent_label": "<अनावेदक/प्रत्यर्थी/प्रतिवादी>",
  "respondent_desc": ["<descriptor line(s)>"],
  "versus": "<बनाम / विरुद्ध>",
  "prelude": ["<recital/declaration paras BEFORE the salutation, each a full sentence; [] if none>"],
  "salutation": "<माननीय न्यायालय, / श्रीमान जी, / '' >",
  "paras": [ {"kind": "fact" | "ground" | "head", "text": "यह कि, …"} ],
  "prayer": "अतः श्रीमान न्यायालय से प्रार्थना है कि … करने की कृपा करें।",
  "needs_verification": true | false,
  "verification": "<सत्यापन text, or '' to use the default>",
  "needs_affidavit": true | false,
  "signatory_role": "<प्रार्थी / आवेदक / याचिकाकर्ता / वादी>",
  "cite_at_hearing": [ {"case": "<exact real citation>", "point": "<why>"} ],
  "companions": ["<law-mandated companion documents the advocate must also file>"],
  "warnings": ["<anything you could not complete, any ____ the lawyer must fill, any procedural gap>"]
}
Write the entire draft in the language requested ({lang}). Be thorough: a real filing has multiple fact paras
and several distinct grounds, each a complete, persuasive sentence in the advocate's register."""


def _verified_block(doc_family: str) -> str:
    cites = VERIFIED_CITATIONS.get(doc_family, [])
    if not cites:
        return ("(none for this matter type — argue on statute + facts; put any authority the lawyer "
                "wants in cite_at_hearing, and only if you are certain it really exists.)")
    return "\n".join(f"  • {c['case']} — {c['point']}" for c in cites)


def _candidates_block(b: dict) -> str:
    cands = b.get("cite_candidates") or []
    if not cands:
        return "  (none curated — list an authority only if you are certain it really exists.)"
    return "\n".join(f"  • {c['case']} — {c['point']}" for c in cands)


# CPC discipline for the civil family — appended to the system prompt so a civil draft
# reads like a plaint/WS, not a criminal application wearing civil labels.
_CIVIL_NOTE = """CIVIL DRAFTING ADDENDUM (this is a CIVIL matter — CPC discipline applies):
• Party labels: वादी/प्रतिवादी (suit), आवेदक/अनावेदक (misc. civil application), परिवादी/अनावेदकगण (consumer).
• CAUSE-TITLE for the suit's OWN State — a suit (Hindi-belt idiom): "न्यायालय माननीय व्यवहार न्यायाधीश महोदय
  वर्ग-____, <नगर> (<राज्य>)" (NOT "नागरिक न्यायाधीश"/"सिविल जज"); in English "Court of the Civil Judge,
  <Senior/Junior> Division, <city> (<State>)"; consumer: "जिला उपभोक्ता विवाद प्रतितोष आयोग, <नगर> (<राज्य>)" /
  "District Consumer Disputes Redressal Commission, <city> (<State>)". Use the matter's State, never MP by default.
• A PLAINT carries, as separate numbered paras: parties & descriptions · the dated transaction/title facts ·
  वादग्रस्त संपत्ति description for property suits (boundaries चौहद्दी, khasra/survey/house no.) · cause of
  action — "वाद कारण दिनांक ____ को ____ में उत्पन्न हुआ" naming date AND place · jurisdiction (territorial
  §16/§20 CPC + pecuniary) · मूल्यांकन एवं न्यायशुल्क (suit valuation and the court fee paid) · limitation —
  the period and why the suit is within it. Missing any of these gets the plaint returned under Order VII.
• PRAYER (सहायता) in lettered clauses: (अ) the main relief, (ब) consequential/alternative relief, (स) costs,
  (द) अन्य अनुतोष जो न्यायालय उचित समझे.
• Money claims: give the computation openly (principal, interest rate & period, total) and pray
  pendente-lite + future interest under §34 CPC.
• VERIFICATION per Order VI Rule 15 CPC — state which paras are from personal knowledge and which on
  record/legal advice and belief, with place and date.
• Sections: cite the CPC Order/Rule and the substantive Act precisely (Specific Relief Act 1963, T.P. Act
  1882, Consumer Protection Act 2019, Limitation Act 1963). For STATE-SPECIFIC subjects use the RIGHT State's
  Act, not MP's: rent control/eviction is a State statute — e.g. MP Accommodation Control Act 1961,
  Maharashtra Rent Control Act 1999, Delhi Rent Act 1995, West Bengal Premises Tenancy Act 1997, Tamil Nadu
  Regulation of Rights & Responsibilities of Landlords & Tenants Act 2017, Rajasthan Rent Control Act 2001,
  etc.; COURT FEES follow the applicable State Court-Fees Act. If unsure which State Act applies, write ____
  and flag it — do NOT default to the MP Act. BNSS/CrPC/BNS/IPC have NO place in a civil pleading.

"""


def _author_system(doc_type: str, lang: str, format_exemplar: str = "",
                   inject_skill: bool = True) -> str:
    b = brief_for(doc_type)
    fam = family_for(doc_type)
    skeleton = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(b.get("skeleton", [])))
    system = (HOUSE_STYLE
              .replace("{section_map}", _SECTION_MAP_NOTE)
              .replace("{verified}", _verified_block(fam))
              .replace("{candidates}", _candidates_block(b))
              .replace("{label}", f'{b["label_hi"]} ({b["label_en"]})')
              .replace("{brief}", b.get("brief", ""))
              .replace("{skeleton}", skeleton or "  (compose a sensible order: facts → grounds → prayer)")
              .replace("{lang}", "Hindi" if lang == "hi" else "English"))
    if doc_type in CIVIL_TYPES:
        system = system.replace("THE MATTER TYPE:", _CIVIL_NOTE + "THE MATTER TYPE:")
    if (format_exemplar or "").strip():
        # The canonical template, rendered blank, IS the prescribed format for this
        # application — the model writes the advocate's matter INTO this shape instead
        # of a schema-limited extraction throwing the matter's richness away.
        block = (
            "PRESCRIBED FORMAT — Headnote's reviewed, court-filed प्रारूप for exactly this application type "
            "(a BLANK specimen; ____ marks a placeholder). Your draft MUST come out in this shape: the same "
            "cause-title pattern, the same title line, the same recital order, the same standard sentences, "
            "the same prayer and verification framing. Write the advocate's facts INTO this shape, EXPAND the "
            "numbered paragraphs with the matter's own specifics (the specimen shows the floor, not the "
            "ceiling), and keep ____ wherever the advocate gave no value. The specimen carries NO facts — "
            "facts come ONLY from the matter.\n"
            "<SPECIMEN>\n" + format_exemplar.strip() + "\n</SPECIMEN>\n\n"
        )
        system = system.replace("THE MATTER TYPE:", block + "THE MATTER TYPE:")
    # Prepend the FULL drafting skill as a stable, cacheable reference prefix
    # (Drafter Quality Roadmap §4.2 — "half the quality gap"). Stable text first
    # so DeepSeek's prefix cache hits; the distilled operating prompt + per-matter
    # slice follow. Empty string when injection is disabled/unavailable.
    # inject_skill=False builds the SLIM prompt for the free-tier fallback retry:
    # the ~14K-token skill blows Groq's 12K-TPM limit, which silently killed the
    # whole fallback tier for authoring (413 on every call) whenever DeepSeek was down.
    if not inject_skill:
        return system
    from headnote.drafter.skill_context import full_skill_context
    skill = full_skill_context()
    return f"{skill}\n{system}" if skill else system


# ===========================================================================
# 4) CITATION GUARD  — strip/flag any body citation not on the whitelist.
# ===========================================================================
# citation-shaped tokens: "(2022) 10 SCC 51", "AIR 1960 SC 866", "2024 INSC 144",
# "2021 SCC OnLine SC 1002", and Devanagari "एस.सी.सी." / "आई.एन.एस.सी."
_CITE_TOKEN = re.compile(
    r"(\(?\d{4}\)?\s*\d*\s*(?:SCC(?:\s+OnLine)?|INSC|AIR|SCR|एस\.?सी\.?सी\.?|आई\.?एन\.?एस\.?सी\.?))",
    re.IGNORECASE,
)


# --- section-pair guard — the BNSS↔CrPC mirror of the citation guard. -------
# Function-map pairs from the skill (legal-frameworks.md §0). If an authored
# draft writes "धारा X BNSS (Y CrPC)" and (X → Y) contradicts this map, or uses
# a section number that cannot exist in the code it names (CrPC ends at §484,
# BNSS at §531), we flag it in warnings. Advocate is the gate — flag, not edit.
_BNSS_TO_CRPC = {
    "483": "439", "480": "437", "482": "438", "187": "167", "479": "436",
    "35": "41", "173": "154", "193": "173", "210": "190", "528": "482",
    "415": "374", "419": "378", "430": "389", "442": "401", "438": "397",
    "144": "125", "250": "227", "262": "239", "223": "200", "94": "91",
    "348": "311", "228": "205", "359": "320", "175": "156", "447": "407",
    "302": "267",
}
_BNSS_TOKEN = r"(?:बी\.?\s?एन\.?\s?एस\.?\s?एस\.?|भा\.?\s?ना\.?\s?सु\.?\s?सं\.?|B\.?N\.?S\.?S\.?)"
_CRPC_TOKEN = r"(?:दं\.?\s?प्र\.?\s?सं\.?|द\.?\s?प्र\.?\s?सं\.?|Cr\.?\s?P\.?\s?C\.?)"
_PAIR_RE = re.compile(
    r"(?:धारा|section|s\.)\s*(\d{1,3})(?:\(\d+\))?\s*" + _BNSS_TOKEN
    + r"[^()]{0,20}\(\s*(?:धारा|section|s\.)?\s*(\d{1,3})(?:\(\d+\))?\s*" + _CRPC_TOKEN,
    re.IGNORECASE,
)
_CRPC_NUM_RE = re.compile(r"(\d{3})(?:\(\d+\))?\s*" + _CRPC_TOKEN, re.IGNORECASE)
_BNSS_NUM_RE = re.compile(r"(\d{3})(?:\(\d+\))?\s*" + _BNSS_TOKEN, re.IGNORECASE)


def guard_sections(texts: list[str]) -> list[str]:
    """Scan authored text for BNSS↔CrPC pairing errors. Returns warning strings."""
    warnings: list[str] = []
    joined = "\n".join(t for t in texts if t)
    for m in _PAIR_RE.finditer(joined):
        bnss, crpc = m.group(1), m.group(2)
        want = _BNSS_TO_CRPC.get(bnss)
        if want and crpc != want:
            warnings.append(
                f"धारा-युग्म जाँचें: 'धारा {bnss} बी.एन.एस.एस. ({crpc} दं.प्र.सं.)' लिखा है — "
                f"मानचित्र अनुसार §{bnss} BNSS ↔ §{want} CrPC. (Section pair mismatch — verify.)")
    for m in _CRPC_NUM_RE.finditer(joined):
        if int(m.group(1)) > 484:
            warnings.append(
                f"'धारा {m.group(1)} दं.प्र.सं.' — CrPC में धारा 484 के बाद कोई धारा नहीं है; "
                f"संभवतः यह BNSS की धारा है। (CrPC ends at §484 — this is likely a BNSS number.)")
    for m in _BNSS_NUM_RE.finditer(joined):
        if int(m.group(1)) > 531:
            warnings.append(
                f"'धारा {m.group(1)} बी.एन.एस.एस.' — BNSS में धारा 531 के बाद कोई धारा नहीं है; जाँचें। "
                f"(BNSS ends at §531 — verify this section.)")
    return warnings


def _guard_citations(text: str, fingerprints: set[tuple[str, str]]) -> tuple[str, bool]:
    """Return (text, flagged). If a body paragraph contains a citation-shaped token
    (… SCC / INSC / AIR / एस.सी.सी. …) whose year+page does NOT match any whitelisted
    citation, flag it — the advocate is the gate, so we surface it loudly rather than
    silently delete. Biased to flag: a false flag merely asks for a verify; a missed
    fabrication is the unacceptable failure."""
    if not _CITE_TOKEN.search(text or ""):
        return text, False
    nums = set(_NUM.findall(text or ""))
    for year, tail in fingerprints:
        if year in nums and tail in nums:
            return text, False     # matches a verified authority — allowed
    return text, True              # citation-shaped but not on the whitelist → flag


# ===========================================================================
# 4b) FACT-GROUNDING GUARD  — the fact analog of the citation guard, and the
#     single most important trust control in the drafter. An LLM asked to fill a
#     rich draft structure from a THIN brief will invent a plausible fact pattern
#     (a demo once produced a "deceased wife" and "parents as defendants" that
#     existed nowhere in the lawyer's matter). The prompt says "never invent" —
#     but instruction alone is not enough, so EVERY generated draft is scanned
#     here: any concrete fact atom (a specific date, a money amount, or a
#     person-name/relationship) that cannot be traced back to what the advocate
#     actually gave is HIGHLIGHTED inline and surfaced loudly. We never silently
#     delete — the advocate is the gate — and we are biased to flag: a false flag
#     costs one glance, a missed fabrication costs the lawyer's licence. Empty
#     source ⇒ nothing is verifiable ⇒ every fact atom flags (correct: a draft
#     built from no facts is, by definition, unverifiable).
# ===========================================================================
_G_DATE = re.compile(r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b")
_G_MONEY = re.compile(r"(?:₹|रु\.?|रुपये|Rs\.?)\s*[\d,]+(?:\.\d+)?|\b\d[\d,]{2,}/\-")
# a name/relationship immediately after a descriptor marker — exactly where an
# invented party or relationship lives (S/o …, पुत्र …, पत्नी …, निवासी …, "namely X").
_G_NAME = re.compile(
    r"(?:S/o|D/o|W/o|पुत्र|पुत्री|पत्नी|पति|आत्मज|निवासी|नामक|नामतः|resident of|son of|"
    r"daughter of|wife of|widow of|husband of|namely|named)\s*[:\-–]?\s*"
    r"((?:श्री|श्रीमती|कुमारी|कु\.|स्व\.|स्वर्गीय|Late|Smt\.?|Sri|Shri|Mr\.?|Ms\.?)?\s*"
    r"[A-Za-zऀ-ॿ][^\s,।;.()]*(?:\s+[A-Za-zऀ-ॿ][^\s,।;.()]*){0,3})",
    re.IGNORECASE)
_G_HONORIFIC = re.compile(
    r"^(श्री|श्रीमती|कुमारी|कु\.|स्व\.|स्वर्गीय|late|smt\.?|sri|shri|mr\.?|ms\.?)\s*", re.IGNORECASE)
# generic role/relationship words that are NOT names — a capture that reduces to one
# of these (e.g. "wife of the plaintiff") is boilerplate, not a fabricated fact.
_G_ROLE_WORDS = {
    "the plaintiff", "plaintiff", "the defendant", "defendant", "the defendants", "defendants",
    "the applicant", "applicant", "the respondent", "respondent", "the petitioner", "petitioner",
    "the complainant", "complainant", "the accused", "the deponent", "deponent",
    "the corporation", "the bank", "the company", "the opposite party", "the said",
    "his", "her", "their", "his wife", "her husband", "his parents", "her parents",
    "their parents", "the family", "his family", "her family", "the deceased",
    "वादी", "प्रतिवादी", "प्रतिवादीगण", "आवेदक", "अनावेदक", "अनावेदकगण", "प्रार्थी",
    "याचिकाकर्ता", "परिवादी", "अभियुक्त", "बंदी", "उपरोक्त", "मृतक",
}


def _is_generic_role(name: str) -> bool:
    a = _G_HONORIFIC.sub("", re.sub(r"\s+", " ", name).casefold().strip(" .,-–")).strip()
    return (not a) or (a in _G_ROLE_WORDS) or a.startswith(("the ", "his ", "her ", "their "))


# Devanagari ↔ ASCII digits: the model often writes १०.०६.२०२४ for 10.06.2024 in a
# Hindi draft. Both guards must treat the two scripts as the SAME number, or a
# perfectly-grounded date false-flags as "invented" AND "missing" at once.
_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def _norm_digits(s: str) -> str:
    return (s or "").translate(_DEV_DIGITS)


# Phonetic skeleton for Devanagari name matching: transliteration is not unique
# (the machine writes शिव्हरे, the model शिवहरे; विश्नु vs विष्णु — same name).
# Dropping matras/halant and collapsing the sibilants gives both spellings the
# same skeleton, so a correctly-transliterated name grounds instead of flagging.
_DEVA_STRIP = set("ािीुूृॄेैोौॅॉंँः़्ऽ")
_DEVA_FOLD = str.maketrans({"श": "स", "ष": "स", "ण": "न", "ऋ": "र", "ळ": "ल",
                            # long/short independent vowels are transliteration noise
                            "आ": "अ", "ई": "इ", "ऊ": "उ", "ऐ": "ए", "औ": "ओ"})


def _deva_skeleton(s: str) -> str:
    s = _norm_digits(s or "")
    s = "".join(ch for ch in s if ch not in _DEVA_STRIP)
    return re.sub(r"\s+", " ", s.translate(_DEVA_FOLD)).casefold()


def _strip_honorifics(a: str) -> str:
    """Strip STACKED honorifics ('स्व. श्री कमलेश राणा' → 'कमलेश राणा')."""
    while True:
        b = _G_HONORIFIC.sub("", a).strip()
        if b == a:
            return a
        a = b


def _ed_le1(a: str, b: str) -> bool:
    """Edit distance ≤ 1 — absorbs the one-character spelling variance two valid
    transliterations of the same name routinely have (कंलेश vs कमलेश)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la > lb:
        a, b, la, lb = b, a, lb, la
    i = j = diff = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1; j += 1
            continue
        diff += 1
        if diff > 1:
            return False
        if la == lb:
            i += 1
        j += 1
    return diff + (lb - j) <= 1


def _ground_index(source: str) -> dict:
    """Pre-index the advocate's source text (their typed brief / OCR'd case papers)
    for O(1) grounding membership tests. The index also carries a TRANSLITERATED
    shadow of the source — a Hindi draft correctly writes the Roman-typed "Ayush
    Shivhare" as आयुष शिवहरे, and that must GROUND, not flag as invented (and the
    reverse for an English draft from a Devanagari brief)."""
    src = _norm_digits(source or "")
    text = re.sub(r"\s+", " ", src).casefold()
    try:
        from headnote.drafter.transliterate import en_to_hi, hi_to_en
        shadows = []
        if re.search(r"[A-Za-z]", src):
            # transliterate only NAME-SHAPED words (capitalized) — running English
            # ("sent", "dated") through the phonetic engine pollutes the shadow with
            # tokens that accidentally match real Devanagari words (सेंत ≈ सीता).
            names = re.findall(r"\b[A-Z][a-z]+\b", src)
            shadows.append(en_to_hi(" ".join(names) if names else src))
        if any("ऀ" <= ch <= "ॿ" for ch in src):
            shadows.append(hi_to_en(src))
        if shadows:
            text += " || " + re.sub(r"\s+", " ", " || ".join(shadows)).casefold()
    except Exception:
        pass
    skel = _deva_skeleton(text)
    return {"digits": re.sub(r"\D", "", src), "text": text, "skel": skel,
            "skel_tokens": set(re.split(r"[^\wऀ-ॿ]+", skel)) - {""}}


def _grounded(atom: str, kind: str, gi: dict) -> bool:
    """True if this fact atom traces to the source (or is a placeholder). A ____
    blank is never a fabrication."""
    if not atom or "_" in atom:
        return True
    if kind in ("date", "money"):
        d = re.sub(r"\D", "", _norm_digits(atom))
        return (not d) or (d in gi["digits"])
    a = re.sub(r"\s+", " ", atom).casefold().strip(" .,-–")
    if not a:
        return True
    a2 = _strip_honorifics(a)                 # match with or without honorifics (stacked too)
    if (a in gi["text"]) or (bool(a2) and a2 in gi["text"]):
        return True
    # cross-script leniency: a Devanagari name is the SAME name as its Roman-typed
    # source form if every word's phonetic skeleton matches a source token within
    # edit distance 1 (two valid transliterations rarely agree to the letter).
    if any("ऀ" <= ch <= "ॿ" for ch in a):
        toks = gi.get("skel_tokens") or set()
        words = [_deva_skeleton(w) for w in (a2 or a).split()]
        words = [w for w in words if len(w) >= 2]
        if words and toks:
            return all(any(_ed_le1(w, t) for t in toks if len(t) >= 2) for w in words)
    return False


def _mark_grounding(text: str, gi: dict, ung: list) -> str:
    """Escape `text` for HTML, wrapping every UNGROUNDED fact atom in
    <mark class="fab">. Appends the raw atoms to `ung` (caller aggregates them
    into a warning). Returns normal escaped text when nothing is ungrounded."""
    text = text or ""
    spans = []
    for m in _G_DATE.finditer(text):
        spans.append((m.start(), m.end(), "date", m.group(0)))
    for m in _G_MONEY.finditer(text):
        spans.append((m.start(), m.end(), "money", m.group(0)))
    for m in _G_NAME.finditer(text):
        if not _is_generic_role(m.group(1)):
            spans.append((m.start(1), m.end(1), "name", m.group(1)))
    bad = sorted((s, e, k, v) for (s, e, k, v) in spans if not _grounded(v, k, gi))
    picked, last = [], -1
    for s, e, k, v in bad:                     # drop overlaps, keep the earliest
        if s < last:
            continue
        picked.append((s, e, k, v))
        last = e
    if not picked:
        return _esc(text)
    tip = "इस विवरण को सत्यापित करें — आपके दिए इनपुट में यह नहीं मिला"
    buf, i = [], 0
    for s, e, k, v in picked:
        buf.append(_esc(text[i:s]))
        buf.append(f'<mark class="fab" title="{tip}">{_esc(text[s:e])}</mark>')
        ung.append(v.strip())
        i = e
    buf.append(_esc(text[i:]))
    return "".join(buf)


def _grounding_warnings(ung: list, lang: str) -> list[str]:
    """One aggregated, unmissable warning listing the ungrounded atoms."""
    uniq = list(dict.fromkeys(a for a in ung if a))
    if not uniq:
        return []
    shown = "; ".join(uniq[:12]) + (" …" if len(uniq) > 12 else "")
    if lang == "en":
        return [f"⚠ {len(uniq)} detail(s) in this draft are NOT in what you provided and may be "
                f"invented — verify or delete each before filing (highlighted in the draft): {shown}"]
    return [f"⚠ इस ड्राफ्ट के {len(uniq)} विवरण आपके दिए इनपुट में नहीं मिले और हो सकता है स्वतः जोड़े गए हों — "
            f"दाखिल करने से पूर्व प्रत्येक की पुष्टि करें या हटाएँ (ड्राफ्ट में हाइलाइट किए गए): {shown}"]


# ===========================================================================
# 4c) INPUT-COVERAGE GUARD — the mirror image of the grounding guard. Grounding
#     asks "is everything in the DRAFT traceable to the input?"; coverage asks
#     "did everything concrete in the INPUT make it into the draft?" — the
#     lawyer's actual complaint when a draft comes back generic is the second
#     one ("it didn't read what I wrote"). Deterministic, same atom regexes,
#     digit-normalised matching (so 05.01.2024 vs 5.1.2024 still counts).
# ===========================================================================
_C_CASE_NO = re.compile(r"\b\d{1,5}\s*/\s*(?:19|20)\d{2}\b")   # FIR/case no. — 123/2024


def coverage_warnings(matter: str, draft_text: str, lang: str = "hi") -> list[str]:
    """Return a warning listing concrete atoms (dates, amounts, FIR/case numbers)
    that the advocate GAVE but the draft does not carry. Pure/deterministic."""
    src = _norm_digits(matter or "")
    if not src.strip() or not (draft_text or "").strip():
        return []
    draft_digits = re.sub(r"\D", "", _norm_digits(draft_text))
    atoms: list[str] = []
    for rx in (_G_DATE, _G_MONEY, _C_CASE_NO):
        atoms.extend(m.group(0) for m in rx.finditer(src))
    missing, seen = [], set()
    for a in atoms:
        d = re.sub(r"\D", "", a)
        if not d or d in seen:
            continue
        seen.add(d)
        if d not in draft_digits:
            missing.append(a.strip())
    if not missing:
        return []
    shown = "; ".join(missing[:10]) + (" …" if len(missing) > 10 else "")
    if lang == "en":
        return [f"⚠ {len(missing)} detail(s) you provided did not make it into the draft — "
                f"add them where they belong before filing: {shown}"]
    return [f"⚠ आपके दिए {len(missing)} विवरण ड्राफ्ट में नहीं आए — दाखिल करने से पूर्व इन्हें "
            f"सही स्थान पर जोड़ें: {shown}"]


# ===========================================================================
# 5) RENDER  — structured content → canonical header + cb-* body (house format).
# ===========================================================================
def _esc(s: Optional[str]) -> str:
    # strip stray CJK (mojibake safety-net; never valid in an Indian court doc) then escape
    return "" if s is None else _strip_cjk(str(s)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_DEFAULT_VERIFICATION = (
    "सत्यापित किया जाता है कि उपरोक्त आवेदन पत्र की समस्त बातें मेरी व्यक्तिगत जानकारी एवं अभिलेख के "
    "आधार पर सत्य व सही हैं, जिसमें कुछ भी असत्य नहीं है और न ही कुछ छिपाया गया है।"
)
_DEFAULT_VERIFICATION_EN = (
    "It is verified that the contents of the above application are true and correct to my personal "
    "knowledge and the record; nothing material has been concealed."
)


def render_authored(p: dict, lang: str = "hi", source: str = "") -> dict:
    """Render an authored payload into house-format HTML. Returns
    {html, warnings, cite_at_hearing, companions, ungrounded}. Pure/deterministic —
    no LLM. `source` = the advocate's own input (typed brief / OCR'd case papers);
    every concrete fact in the draft is grounded against it (see the guard above)."""
    hi = lang != "en"
    p = p or {}
    warnings = list(p.get("warnings") or [])
    gi = _ground_index(source)
    ung: list[str] = []

    court_level = (p.get("court_level") or "").strip()
    _known_levels = ("magistrate", "cjm", "sessions", "principal_sessions", "family",
                     "civil", "district_judge", "consumer", "hc")
    if court_level not in _known_levels:
        # missing/unknown level → the brief's forum for a civil draft, sessions
        # otherwise (never a Sessions cause-title on the face of a plaint)
        if p.get("_doc_type") in CIVIL_TYPES:
            court_level = brief_for(p.get("_doc_type")).get("court") or "civil"
            if court_level not in _known_levels:
                court_level = "civil"
        else:
            court_level = "sessions"
    # The LLM composes court_name from the matter's own State. This fallback fires only
    # when it gave nothing — then leave the State/city BLANK (pan-India: never guess MP).
    court_name = (p.get("court_name") or "").strip() or compose_court_name(
        court_level, p.get("court_city") or "", p.get("state_name") or "",
        lang="hi" if hi else "en")

    hdr = render_header({
        "side_label": p.get("side_label") or "",
        "court_name": court_name,
        "case_code": p.get("case_code") or ("प्रकरण क्रमांक" if hi else "Case"),
        "case_number": p.get("case_number") or "",
        "case_year": p.get("case_year") or "",
        "applicant_label": p.get("applicant_label") or ("आवेदक" if hi else "Applicant"),
        "applicant_desc": [_mark_grounding(x, gi, ung) for x in (p.get("applicant_desc") or [])] or [_esc(p.get("applicant_label") or "")],
        "respondent_label": p.get("respondent_label") or ("अनावेदक" if hi else "Respondent"),
        "respondent_desc": [_mark_grounding(x, gi, ung) for x in (p.get("respondent_desc") or [])],
        "versus": p.get("versus") or ("बनाम" if hi else "Versus"),
        "title_line": p.get("title_line") or "",
    })

    out = [hdr, '<div class="doc-body">']
    for pre in (p.get("prelude") or []):
        if str(pre).strip():
            out.append(f'<p class="cb-prelude">{_mark_grounding(str(pre), gi, ung)}</p>')
    sal = (p.get("salutation") or "").strip()
    if sal:
        out.append(f'<p class="cb-prelude">{_esc(sal)}</p>')

    # numbered body — cb-head items don't advance the number (matches _doc_header CSS)
    fam_fps = _cite_fingerprints(family_for(p.get("_doc_type") or "other_criminal"))
    paras = p.get("paras") or []
    out.append('<ol class="cb-paras">')
    flagged_any = False
    for item in paras:
        if not isinstance(item, dict):
            item = {"kind": "ground", "text": str(item)}
        kind = item.get("kind") or "ground"
        text = (item.get("text") or "").strip()
        if not text:
            continue
        if kind == "head":
            out.append(f'<li class="cb-head">{_esc(text)}</li>')
            continue
        _t, cflag = _guard_citations(text, fam_fps)
        marked = _mark_grounding(text, gi, ung)
        if cflag:
            flagged_any = True
            out.append(f'<li>{marked} <span class="ph">[उद्धृत निर्णय — सत्यापन आवश्यक]</span></li>')
        else:
            out.append(f'<li>{marked}</li>')
    out.append('</ol>')
    if flagged_any:
        warnings.append("एक या अधिक आधारों में उद्धृत निर्णय श्वेतसूची में नहीं है — पीठासीन से सत्यापन के बिना "
                        "बहस में प्रयोग न करें। (An in-body citation is outside the verified list — verify before use.)")

    prayer = (p.get("prayer") or "").strip()
    if prayer:
        out.append(f'<div class="cb-prayer"><p>{_mark_grounding(prayer, gi, ung)}</p></div>')

    # section-pair guard — flag BNSS↔CrPC mismatches anywhere in the authored text
    _texts = [p.get("title_line") or "", prayer]
    _texts += [str(i.get("text") or "") if isinstance(i, dict) else str(i) for i in paras]
    warnings.extend(guard_sections(_texts))
    # a CIVIL pleading citing the criminal codes is itself a defect — flag it
    if p.get("_doc_type") in CIVIL_TYPES:
        _joined = "\n".join(t for t in _texts if t)
        if re.search(_BNSS_TOKEN, _joined) or re.search(_CRPC_TOKEN, _joined, re.IGNORECASE):
            warnings.append("व्यवहार (civil) प्रारूप में बी.एन.एस.एस./दं.प्र.सं. का उल्लेख मिला — "
                            "civil pleading में आपराधिक संहिता का स्थान नहीं है; जाँचें। "
                            "(A civil pleading cites BNSS/CrPC — verify and remove.)")

    # signature block
    role = p.get("signatory_role") or ("प्रार्थी" if hi else "Applicant")
    place_lbl, date_lbl = ("स्थान", "दिनांक") if hi else ("Place", "Date")
    through = "द्वारा अभिभाषक" if hi else "Through Counsel"
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>{place_lbl}: <span class="ph">________</span></div>'
               f'<div>{date_lbl}: <span class="ph">__/__/____</span></div></div>'
               f'<div class="r"><div>{_esc(role)}</div>'
               f'<div style="margin-top:10pt">{through}</div>'
               '<div>(<span class="ph">________</span>) — एडवोकेट</div></div></div>')

    # verification (सत्यापन) — appended where facts are sworn
    if p.get("needs_verification"):
        vlabel = "सत्यापन" if hi else "VERIFICATION"
        vtext = (p.get("verification") or "").strip() or (_DEFAULT_VERIFICATION if hi else _DEFAULT_VERIFICATION_EN)
        out.append(f'<div class="cb-block-label">{vlabel}</div>')
        out.append(f'<p class="cb-prelude">{_esc(vtext)}</p>')
        out.append(f'<div class="cb-sig"><div class="l"><div>{date_lbl}: <span class="ph">__/__/____</span></div></div>'
                   f'<div class="r"><div style="margin-top:14pt">{_esc(role)}</div></div></div>')

    out.append('</div>')
    warnings.extend(_grounding_warnings(ung, lang))
    return {
        "html": "\n".join(out),
        "warnings": warnings,
        "cite_at_hearing": p.get("cite_at_hearing") or [],
        "companions": p.get("companions") or [],
        "needs_affidavit": bool(p.get("needs_affidavit")),
        "ungrounded": list(dict.fromkeys(ung)),
    }


# ===========================================================================
# 6) AUTHOR  — prompt → structured payload (LLM) → guarded → rendered HTML.
# ===========================================================================
def _shape_payload(payload: dict, doc_type: str, b: dict, meta) -> dict:
    """Apply the invariant post-parse defaults every authored/revised payload needs:
    doc_type stamp, verification/affidavit defaults, and the law-mandated companions
    unioned in so the advocate never misses one."""
    payload["_doc_type"] = doc_type
    payload.setdefault("needs_verification", b.get("needs_verification", True))
    payload.setdefault("needs_affidavit", b.get("needs_affidavit", False))
    comps = list(payload.get("companions") or [])
    for c in b.get("companions", []):
        if c not in comps:
            comps.append(c)
    payload["companions"] = comps
    payload["_meta"] = meta
    return payload


# The advocate uploaded a FILED draft as a STYLE reference — we mirror its shape/voice,
# never its facts or its (unverified) citations. See extract_reference_skeleton().
REF_SKELETON_SYSTEM = """An Indian advocate has uploaded a FILED court document as a STYLE REFERENCE for a NEW
draft about a DIFFERENT matter. Your job is NOT to copy its facts — it is to capture its STRUCTURE, FORMAT and
VOICE so the new draft can be authored to look and read like it.

Output ONLY valid JSON (no prose, no markdown fence):
{
  "doc_kind": "<what kind of application/petition/reply this is — Hindi + English>",
  "cause_title_style": "<how the court / cause-title line is laid out>",
  "title_line_style": "<the underlined title-line pattern, with the matter-specific bits blanked>",
  "party_block_style": "<how parties + their descriptor lines are formatted and labelled>",
  "section_order": ["<ordered list of the sections / headings / paragraph-groups as they appear>"],
  "para_conventions": "<opening word of each numbered para (e.g. 'यह कि'), numbering, register, sentence style>",
  "prayer_style": "<how the prayer opens and closes — the verbatim framing, specifics blanked>",
  "signoff_style": "<verification / affidavit / signatory-block conventions>",
  "tone": "<register + voice notes an author must match>",
  "dynamic_fields": ["<the kinds of matter-specific values that vary: names, dates, FIR no., sections, amounts, addresses>"]
}
Capture PATTERNS, never the specific facts of the reference. If it cites judgments, note THAT it relies on
authority and where — but DO NOT reproduce any citation (every citation must be re-verified downstream)."""


def extract_reference_skeleton(reference_text: str, lang: str = "hi") -> str:
    """Templatize pass: a filed reference draft → a compact, human-readable STRUCTURE spec
    the authoring prompt can mirror. Returns "" on any failure (caller degrades to a plain
    authored draft). Never surfaces the reference's facts or citations."""
    reference_text = (reference_text or "").strip()
    if not reference_text:
        return ""
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
    try:
        raw, _meta = _call_deepseek_or_groq(
            REF_SKELETON_SYSTEM, reference_text[:12000], max_tokens=1200,
            claude_model="claude-haiku-4-5", json_mode=True)
        spec = parse_json_response(raw)
    except Exception:
        return ""
    lines: list[str] = []

    def add(label, val):
        if not val:
            return
        if isinstance(val, list):
            val = "; ".join(str(x) for x in val if str(x).strip())
        if str(val).strip():
            lines.append(f"• {label}: {val}")
    add("Document kind", spec.get("doc_kind"))
    add("Cause-title layout", spec.get("cause_title_style"))
    add("Title-line pattern", spec.get("title_line_style"))
    add("Party block", spec.get("party_block_style"))
    add("Section order", spec.get("section_order"))
    add("Paragraph conventions", spec.get("para_conventions"))
    add("Prayer framing", spec.get("prayer_style"))
    add("Sign-off", spec.get("signoff_style"))
    add("Tone / register", spec.get("tone"))
    add("Dynamic fields that vary", spec.get("dynamic_fields"))
    return "\n".join(lines)


def _mirror_instruction(reference_skeleton: str) -> str:
    return (
        "\n\nMIRROR THIS STRUCTURE — the advocate uploaded a reference draft they want the output to match. "
        "Follow its section order, headings, paragraph conventions, cause-title, title-line, prayer and sign-off "
        "style, and match its tone and register as closely as you can. Fill it with THIS matter's facts (write "
        "____ for anything unknown — NEVER invent a fact, a party, a relationship or a narrative the matter does "
        "not state; a draft full of ____ is correct, an invented story is a defect). Do NOT copy the reference's "
        "own facts, and do NOT reproduce any citation from it — re-derive all content for this matter under the "
        "zero-fabrication rule.\n"
        "REFERENCE STRUCTURE TO MATCH:\n" + reference_skeleton
    )


# ===========================================================================
# 6b) MIRROR — full-fidelity reference matching (the primary reference path).
#     The skeleton pass above compresses the reference to ~10 description lines
#     and then squeezes the output through the fixed MP house header — which is
#     why a Tripura-format plaint came back looking nothing like the upload.
#     Here the model sees the reference VERBATIM and returns the ENTIRE document
#     as typed layout blocks (recital-first cause-titles, party blocks with the
#     designation pinned right, lettered prayer sub-clauses, schedule/affidavit/
#     list-of-documents companion pages) that we render deterministically.
#     extract_reference_skeleton()+_mirror_instruction() stay as the fallback.
# ===========================================================================
_MIRROR_REF_CAP = 24000     # chars of OCR'd reference the model sees (≈ 15+ pages)

# shown when the model's output was cut off at the token limit (long Hindi documents
# are token-heavy) and we salvaged a partial draft — so a short draft is never passed
# off as complete. The advocate can tap Refine ("बाकी हिस्सा जोड़ो") to extend it.
_TRUNCATION_WARN = {
    "hi": "⚠ यह ड्राफ्ट लंबा होने के कारण बीच में कट गया है — नीचे का हिस्सा अधूरा है। "
          "पूरा करने के लिए Assistant में 'शेष ड्राफ्ट जोड़ो' लिखें या कम पृष्ठ अपलोड करें।",
    "en": "⚠ This draft was cut short because it ran long — the tail is incomplete. "
          "Tap Refine and ask to 'continue the rest of the draft', or upload fewer pages.",
}

MIRROR_SYSTEM = """You are the drafting engine of Headnote. An Indian advocate has uploaded a FILED court
document (the REFERENCE) and typed a brief for a NEW matter. Produce the NEW draft so the advocate's clerk
could not tell it apart from that office's own filing: SAME cause-title layout, SAME section order, SAME
headings, SAME boilerplate framing sentences, SAME paragraph voice and register, SAME language as the
reference, and EVERY companion section the reference carries (schedule of property, verification, affidavit,
list of documents — whatever is there), adapted to the new matter.

THE THREE-SOURCE RULE — what comes from where, in priority order. The advocate gave you a reference BECAUSE
they want a near-complete draft they lightly edit — NEVER return an empty skeleton of one-line shells.
This rule is UNIVERSAL — it governs EVERY kind of document (bail, anticipatory bail, discharge, revision,
appeal, writ, quashing, maintenance, DV, cheque, plaint/suit of any kind, written statement, reply/जबाव,
legal notice, affidavit, petition, application — whatever the reference is), in EVERY State/UT and forum,
in Hindi, English or any regional language. The examples below are illustrations of the principle, never a
restriction to one document type.

1. THE BRIEF (the advocate's typed matter + any attached case papers) is the PRIMARY source of THIS client's
   facts — names, relationships, dates, amounts, and the STORY / the point-by-point position. Write EVERY
   fact the brief gives into its proper place, in FULL. If the brief tells a story, the paragraphs must TELL
   THAT STORY at length in the reference's register — never compress a narrative the advocate gave into a
   one-line "____". Mirror the reference's ORDER and headings exactly.

2. THE REFERENCE supplies two things you MUST carry:
   (a) THE ADVOCATE'S OWN STANDING INFO — the letterhead: name, designation ("एडवोकेट"), court, office &
       residence ADDRESS, mobile, enrolment. This is the SAME advocate on every draft — it is NOT a client
       fact. Reproduce it VERBATIM, including the address and mobile number (name block left, address block
       right → the "columns" kind; separator lines → the "rule" kind). Do NOT blank it.
   (b) THE REUSABLE LEGAL SCAFFOLD — the framing sentences, the admit/deny paragraph shapes, the recital and
       prayer wording, the standard legal language and idiom. PRESERVE this scaffold richly so the output is
       a working draft, not a blank form.

3. CLIENT-SPECIFIC PARTICULARS the scaffold needs (a specific name, amount, date, or the substance of a
   point) that the BRIEF does NOT supply: keep the reference's own wording in place as a WORKING PLACEHOLDER
   (it is highlighted downstream for the advocate to confirm or replace) — do not blank a rich paragraph to
   "____". Only write ____ where there is genuinely nothing to carry. NEVER invent a net-new fact, party,
   date or figure that appears in NEITHER the brief NOR the reference.

Net effect: a rich brief → a rich, specific draft in the reference's format. A thin brief + a rich reference
→ the reference's FULL scaffold with its specifics carried and flagged for the advocate to swap. Either way
the advocate edits a near-complete draft — they never re-type the factual background from scratch.
• ONE SCRIPT THROUGHOUT: if the draft is Hindi, EVERYTHING is Devanagari — when the brief types names/
  places in Roman ("Ayush Shivhare s/o Vishnu"), TRANSLITERATE them (आयुष शिवहरे पुत्र विष्णु) and write
  English fact fragments as formal Hindi. Never leave a Roman name sitting inside a Hindi sentence.
  Digits stay as the reference writes them. Use ONLY Devanagari and Latin script — NEVER emit any Chinese,
  Japanese or Korean (CJK) character; there is no CJK in an Indian court document.
• PLAIN TEXT ONLY inside blocks — never markdown. No "##", no "**", no backticks. If the reference shows
  decorative marks (e.g. a title between // slashes //), reproduce those characters as text.
• PAGE BREAKS: use {"kind":"pagebreak"} ONLY where a NEW companion document begins (affidavit, list of
  documents). NEVER where the reference's physical page happens to end — the new draft reflows continuously
  and the printer decides the page boundaries.
• DO NOT INVENT NET-NEW facts — a name, party, date or figure present in NEITHER the brief NOR the reference.
  (Carrying the reference's own wording as a flagged placeholder is allowed and expected per rule 3; inventing
  a brand-new plausible value from nowhere is not.) In the OPENING RECITAL, prefer the brief's client/opposite
  party/notice-date; if the brief is silent, carry the reference's wording as a placeholder rather than
  guessing a fresh name.
• A PARA-WISE REPLY (जबाव सूचना पत्र / written statement) answers another document point by point. Reproduce
  the reference's admit/deny FRAMING for each point AND carry its substantive reasoning as the scaffold; where
  the brief gives this client's version of a point, write that version in full instead. Do not reduce a point
  the reference argues in a full paragraph down to a bare "____".
• STATUTES/SECTIONS: cite what the NEW matter actually needs (the reference shows the FORMAT of the recital,
  not the sections to copy). If unsure of a section number, write ____.
• CITATIONS: put NO case citation in the body. If authority helps, list only real judgments you are certain
  exist in "cite_at_hearing" — an empty list is correct and safe.

OUTPUT — ONLY valid JSON (no prose, no markdown fence):
{
 "title": "<short label for this draft>",
 "font": "serif" | "devanagari",
 "num_format": "<the reference's paragraph-number style with {n} as the number, e.g. '{n}.' or '({n})' or '{n}ए' — copy EXACTLY what the reference uses; omit for '{n}.'>",
 "num_digits": "arabic" | "devanagari",
 "item_letters": "latin" | "hindi",
 "blocks": [ …the ENTIRE document, top to bottom, one block per visual element… ],
 "cite_at_hearing": [{"case": "…", "point": "…"}],
 "companions": ["<documents to file alongside that you did NOT draft as blocks>"],
 "warnings": ["<anything the advocate must verify>"]
}
"font": "serif" for an English/Times-style reference; "devanagari" for a Hindi one.
"num_format"/"num_digits"/"item_letters": MIRROR the reference's own numbering idiom — if it numbers paras
"१." use devanagari digits; if its prayer sub-clauses run (अ) (ब) (स) use item_letters "hindi".

Block kinds (use EXACTLY these):
 {"kind":"columns","left":"विष्णु शिवहरे\\nएडवोकेट\\nउच्च न्यायालय खण्डपीठ ग्वालियर म.प्र.","right":"कार्यालय एवं निवास:- ____\\nमोबा. ____"}
                                                            → two-column letterhead row (name/designation left, address/phone right)
 {"kind":"rule","style":"double"}                            → full-width separator line; style "single" | "double" | "dashed"
 {"kind":"center","text":"…","bold":true,"underline":true}  → centred line (court name, case-number line)
 {"kind":"label","text":"IN THE MATTER OF:"}                → bold underlined left-margin label
 {"kind":"recital","text":"A PETITION UNDER …"}             → the indented bold justified block under a label
 {"kind":"party","lines":["Sri ____","S/o ____","Resident of: ____"],"designation":"… Plaintiff"}
                                                            → one party block; designation renders pinned to the right edge
 {"kind":"versus","text":"– Versus –"}                      → centred separator between party sides
 {"kind":"num","text":"That …"}                             → auto-numbered body para (1., 2., …) — do NOT write the number
 {"kind":"item","text":"Pass a decree …"}                   → auto-lettered sub-clause ((a), (b), …) — do NOT write the letter
 {"kind":"head","text":"PRAYER"}                            → centred bold underlined section heading
 {"kind":"text","text":"…"}                                 → plain justified paragraph
 {"kind":"right","text":"Deponent"}                         → right-aligned line
 {"kind":"sig","left":"Place: ____\\nDate: __/__/____","right":"Plaintiff\\nThrough Counsel\\n(____), Advocate"}
 {"kind":"table","headers":["Sl.","Document","Pages"],"rows":[["1","____",""]]}
 {"kind":"pagebreak"}                                       → next companion document (affidavit, list of documents)
                                                              starts on a fresh page; para numbering restarts"""


# markdown artifacts the model sometimes leaks into block text ("## विष्णु शिवहरे…",
# "**बनाम**") — a filed court paper has no markdown, so strip deterministically.
_MD_HEAD = re.compile(r"^\s*#{1,6}\s+")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")

# CJK / kana / hangul — a known failure mode where DeepSeek/Groq emit Chinese-looking
# glyphs instead of Devanagari on a Hindi task. NONE of these ever belong in an Indian
# court document, so we (a) detect a corrupt generation to force a retry, and (b) strip
# any stray survivors at render time.
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]")


def _strip_cjk(t: str) -> str:
    return _CJK_RE.sub("", t or "")


def _looks_script_corrupt(text: str) -> bool:
    """True when the output carries enough CJK that the model clearly drifted off
    Devanagari — the trigger to re-generate rather than show garbled 'Chinese' text."""
    return len(_CJK_RE.findall(text or "")) >= 5


def _demarkdown(t: str) -> str:
    t = _MD_HEAD.sub("", t or "")
    t = _MD_BOLD.sub(r"\1", t)
    return _strip_cjk(t.replace("```", "")).strip()


# a pagebreak is REAL only when a new companion document starts after it; a break
# followed by ordinary body flow is the reference's physical page boundary leaking
# through (prints as a near-empty first page — seen live).
_BREAK_OK_NEXT = {"center", "head", "label", "recital"}


def render_mirrored(p: dict, doc_type: str, source: str = "") -> dict:
    """Deterministic renderer for a mirror payload's typed blocks → mr-* HTML.
    Runs the same guards as the house render: citation whitelist, BNSS↔CrPC
    pairing, civil-code check, AND fact grounding against `source` (the advocate's
    typed brief — NOT the reference, whose facts are another client's case). Pure —
    no LLM."""
    p = p or {}
    warnings = [str(w) for w in (p.get("warnings") or []) if str(w).strip()]
    fam_fps = _cite_fingerprints(family_for(doc_type or "other_criminal"))
    gi = _ground_index(source)
    ung: list[str] = []
    root_cls = "mr-doc" + (" mr-serif" if (p.get("font") or "").strip().lower() == "serif" else "")
    out = [f'<div class="{root_cls}">']
    texts: list[str] = []       # everything the section/civil guards should scan
    num = 0                     # auto para number — resets on pagebreak
    item_i = 0                  # auto sub-clause letter — resets on any other kind
    flagged_any = False

    # numbering idiom mirrored from the reference: "1." vs "१." vs "1ए" vs "(1)";
    # prayer sub-clauses (a)(b) vs (अ)(ब). Sanitised — a bad format falls back.
    num_format = str(p.get("num_format") or "{n}.").strip()
    if "{n}" not in num_format or len(num_format) > 8:
        num_format = "{n}."
    deva_nums = (p.get("num_digits") or "").strip().lower() == "devanagari"
    _HINDI_LETTERS = ["अ", "ब", "स", "द", "इ", "फ", "ग", "ह", "ज", "क", "ल", "म"]

    def _num_marker(n: int) -> str:
        s = str(n)
        if deva_nums:
            s = s.translate(str.maketrans("0123456789", "०१२३४५६७८९"))
        return num_format.replace("{n}", s)

    def _item_marker(i: int) -> str:
        if (p.get("item_letters") or "").strip().lower() == "hindi":
            return _HINDI_LETTERS[i - 1] if i <= len(_HINDI_LETTERS) else str(i)
        return chr(96 + i) if i <= 26 else str(i)

    def fmt(t: str) -> str:
        """citation guard + escape — for boilerplate blocks (court name, headings)."""
        nonlocal flagged_any
        t2, flagged = _guard_citations(t, fam_fps)
        texts.append(t2)
        h = _esc(t2)
        if flagged:
            flagged_any = True
            h += ' <span class="ph">[उद्धृत निर्णय — सत्यापन आवश्यक]</span>'
        return h

    def fmtg(t: str) -> str:
        """citation guard + FACT GROUNDING + escape — for fact-bearing blocks
        (party descriptors, numbered paras, prayer items, recitals, body text)."""
        nonlocal flagged_any
        t2, flagged = _guard_citations(t, fam_fps)
        texts.append(t2)
        h = _mark_grounding(t2, gi, ung)
        if flagged:
            flagged_any = True
            h += ' <span class="ph">[उद्धृत निर्णय — सत्यापन आवश्यक]</span>'
        return h

    blocks = [(b if isinstance(b, dict) else {"kind": "text", "text": str(b)})
              for b in (p.get("blocks") or [])]
    for bi, b in enumerate(blocks):
        kind = (b.get("kind") or "text").strip().lower()
        text = _demarkdown(str(b.get("text") or ""))
        if kind != "item":
            item_i = 0
        if kind == "pagebreak":
            nxt = next(((x.get("kind") or "text").strip().lower()
                        for x in blocks[bi + 1:] if isinstance(x, dict)), "")
            if nxt not in _BREAK_OK_NEXT:
                continue    # reference page-boundary artifact — the draft reflows
            num = 0
            out.append('<div class="mr-break"></div>')
            continue
        if kind == "rule":
            style = (b.get("style") or "single").strip().lower()
            style = style if style in ("single", "double", "dashed") else "single"
            out.append(f'<div class="mr-rule mr-rule-{style}"></div>')
            continue
        if kind == "columns":
            # the advocate's letterhead (name / address / mobile) — their OWN standing
            # info, NOT a client fact: use fmt (no fact-grounding) so it renders verbatim
            # and is never amber-flagged.
            left = _demarkdown(str(b.get("left") or ""))
            right = _demarkdown(str(b.get("right") or ""))
            if not left and not right:
                continue
            out.append(f'<div class="mr-cols"><div class="l">{fmt(left)}</div>'
                       f'<div class="r">{fmt(right)}</div></div>')
            continue
        if kind == "party":
            lines = [_demarkdown(str(x)) for x in (b.get("lines") or []) if str(x).strip()]
            desig = _demarkdown(str(b.get("designation") or ""))
            if not lines and not desig:
                continue
            body = "<br>".join(fmtg(x) for x in lines)
            if desig:
                body += f'<div class="mr-desig">{_esc(desig)}</div>'
            out.append(f'<div class="mr-party">{body}</div>')
            continue
        if kind == "sig":
            left = _demarkdown(str(b.get("left") or ""))
            right = _demarkdown(str(b.get("right") or ""))
            if not left and not right:
                continue
            out.append(f'<div class="mr-sig"><div class="l">{_esc(left)}</div>'
                       f'<div class="r">{_esc(right)}</div></div>')
            continue
        if kind == "table":
            headers = [str(h).strip() for h in (b.get("headers") or [])]
            rows = [r if isinstance(r, list) else [r] for r in (b.get("rows") or [])]
            if not headers and not rows:
                continue
            texts.extend(str(c) for r in rows for c in r)
            thead = ("<tr>" + "".join(f"<th>{_esc(h)}</th>" for h in headers) + "</tr>") if headers else ""
            tbody = "".join("<tr>" + "".join(f"<td>{_esc(str(c))}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f'<table class="mr-table">{thead}{tbody}</table>')
            continue
        if not text:
            continue
        if kind == "num":
            num += 1
            out.append(f'<div class="mr-num"><span class="n">{_esc(_num_marker(num))}</span>{fmtg(text)}</div>')
        elif kind == "item":
            item_i += 1
            out.append(f'<div class="mr-item"><span class="n">({_esc(_item_marker(item_i))})</span>{fmtg(text)}</div>')
        elif kind == "center":
            cls = "mr-center" + (" mr-b" if b.get("bold") else "") + (" mr-u" if b.get("underline") else "")
            out.append(f'<div class="{cls}">{fmt(text)}</div>')
        elif kind == "label":
            out.append(f'<div class="mr-label">{fmt(text)}</div>')
        elif kind == "recital":
            out.append(f'<div class="mr-recital">{fmtg(text)}</div>')
        elif kind == "versus":
            out.append(f'<div class="mr-versus">{fmt(text)}</div>')
        elif kind == "head":
            out.append(f'<div class="mr-head">{fmt(text)}</div>')
        elif kind == "right":
            out.append(f'<div class="mr-right">{fmt(text)}</div>')
        else:
            out.append(f'<div class="mr-text">{fmtg(text)}</div>')
    out.append('</div>')

    if flagged_any:
        warnings.append("एक या अधिक पैरा में उद्धृत निर्णय श्वेतसूची में नहीं है — सत्यापन के बिना प्रयोग न करें। "
                        "(An in-body citation is outside the verified list — verify before use.)")
    warnings.extend(guard_sections(texts))
    if doc_type in CIVIL_TYPES:
        joined = "\n".join(texts)
        if re.search(_BNSS_TOKEN, joined) or re.search(_CRPC_TOKEN, joined, re.IGNORECASE):
            warnings.append("व्यवहार (civil) प्रारूप में बी.एन.एस.एस./दं.प्र.सं. का उल्लेख मिला — "
                            "civil pleading में आपराधिक संहिता का स्थान नहीं है; जाँचें। "
                            "(A civil pleading cites BNSS/CrPC — verify and remove.)")
    warnings.extend(_grounding_warnings(ung, "en" if not source or _looks_en(source) else "hi"))
    return {"html": "\n".join(out), "warnings": warnings, "ungrounded": list(dict.fromkeys(ung))}


def _looks_en(s: str) -> bool:
    """Heuristic: a source with no Devanagari is treated as English for warning copy."""
    return not any("ऀ" <= ch <= "ॿ" for ch in (s or ""))


def _mirror_result(payload: dict, rendered: dict, doc_type: str, lang: str, meta) -> dict:
    return {
        "ok": True,
        "mode": "authored",
        "doc_type": doc_type,
        "lang": lang,
        "html": rendered["html"],
        "cite_at_hearing": payload.get("cite_at_hearing") or [],
        "companions": [str(c) for c in (payload.get("companions") or []) if str(c).strip()],
        "needs_affidavit": False,   # a mirrored reference carries its own affidavit page when it has one
        "warnings": rendered["warnings"],
        "ungrounded": rendered.get("ungrounded") or [],
        "title": (payload.get("title") or "").strip() or brief_for(doc_type)["label_hi"],
        "meta": meta,
    }


_MIRROR_MAX_CONT = 4        # continuation rounds — enough for a ~15-page filing
_MIRROR_MAX_BLOCKS = 500     # hard stop so a repeating model can't loop forever


def _block_sig(b: dict) -> str:
    """A short identity for a block — used to drop a continuation's accidental repeat
    of the last block already produced."""
    if not isinstance(b, dict):
        return str(b)[:80]
    return (str(b.get("kind") or "") + "|" +
            (str(b.get("text") or "") or " ".join(str(x) for x in (b.get("lines") or [])) or
             str(b.get("left") or "") + str(b.get("right") or ""))[:80])


def _mirror_continue(reference_text: str, matter: str, blocks_so_far: list, lang: str):
    """One continuation call: the model resumes the SAME document after the blocks it
    already produced and returns ONLY the remaining blocks. Returns (more_blocks, truncated)."""
    import json as _json
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
    tail = blocks_so_far[-3:]
    anchor = _json.dumps(tail, ensure_ascii=False)
    user = (
        "REFERENCE (structure/format ONLY):\n" + (reference_text or "").strip()[:_MIRROR_REF_CAP] + "\n\n"
        "THE NEW MATTER (the ONLY source of facts; ____ where silent):\n"
        + ((matter or "").strip() or "(no brief typed)") + "\n\n"
        f"CONTINUATION TASK: you have ALREADY produced {len(blocks_so_far)} blocks of this document; the LAST "
        f"few were:\n{anchor}\n\n"
        "Continue the SAME document from IMMEDIATELY AFTER that last block. Output ONLY the REMAINING blocks "
        'as JSON {"blocks":[ … ]}, in the same schema, same language/register. Do NOT repeat any block shown '
        'above. If the document is already complete (prayer, signature and verification all done), return '
        '{"blocks":[]}.'
    )
    raw, _meta = _call_deepseek_or_groq(MIRROR_SYSTEM, user, max_tokens=16000,
                                        claude_model=config.DRAFTER_AUTHOR_MODEL, json_mode=True)
    if _looks_script_corrupt(raw):
        return [], False
    payload = parse_json_response(raw)
    more = payload.get("blocks")
    more = more if isinstance(more, list) else []
    # drop a leading repeat of the last block we already have
    if more and blocks_so_far and _block_sig(more[0]) == _block_sig(blocks_so_far[-1]):
        more = more[1:]
    return more, bool(payload.get("_truncated"))


def mirror_document(matter: str, reference_text: str, doc_type: str, lang: str = "hi") -> dict:
    """Primary reference path: the advocate's brief + the VERBATIM reference →
    typed layout blocks → deterministic render. Raises on LLM/parse failure or a
    too-thin payload — the caller falls back to the skeleton+authored path.

    ANY-LENGTH: a long document overflows one model call, so if the first pass is
    truncated we keep asking the model to CONTINUE (append the remaining blocks)
    until it finishes or we hit the round cap — the advocate gets the WHOLE draft."""
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
    user = (
        "REFERENCE (the filed document to mirror — structure/format/boilerplate ONLY, its facts are "
        f"another client's case):\n{(reference_text or '').strip()[:_MIRROR_REF_CAP]}\n\n"
        "THE NEW MATTER (the advocate's brief — the ONLY source of facts; ____ where it is silent):\n"
        f"{(matter or '').strip() or '(no brief typed — every matter-specific value becomes ____)'}\n\n"
        f"Draft now, as JSON per the schema, in {'Hindi' if lang == 'hi' else 'English'} "
        "(match the reference's language/register)."
    )
    raw, meta = _call_deepseek_or_groq(MIRROR_SYSTEM, user, max_tokens=16000, claude_model=config.DRAFTER_AUTHOR_MODEL, json_mode=True)
    if _looks_script_corrupt(raw):
        # model drifted into CJK garbage — bail so the caller re-generates via a clean path
        raise ValueError("mirror output script-corrupt (CJK) — re-generating")
    payload = parse_json_response(raw)
    blocks = payload.get("blocks")
    if not isinstance(blocks, list) or len(blocks) < 4:
        raise ValueError("mirror payload too thin — falling back to the skeleton path")

    # continuation loop — stitch the rest of a long document
    truncated = bool(payload.get("_truncated"))
    rounds = 0
    while truncated and rounds < _MIRROR_MAX_CONT and len(blocks) < _MIRROR_MAX_BLOCKS:
        rounds += 1
        try:
            more, truncated = _mirror_continue(reference_text, matter, blocks, lang)
        except Exception:
            break
        if not more:
            truncated = False
            break
        blocks.extend(more)
    payload["blocks"] = blocks

    # ground facts against the advocate's brief ONLY — the reference is another
    # client's case, so its facts must NEVER count as verification for this draft.
    rendered = render_mirrored(payload, doc_type, source=matter)
    # …and the mirror duty: everything concrete the advocate GAVE must be in the draft
    rendered["warnings"].extend(coverage_warnings(matter, rendered["html"], lang))
    if truncated:   # still cut off after the continuation rounds — be honest
        rendered["warnings"].insert(0, _TRUNCATION_WARN[lang if lang == "en" else "hi"])
    return _mirror_result(payload, rendered, doc_type, lang, meta)


def revise_mirrored(prior_html: str, instruction: str, doc_type: str = "other_criminal",
                    lang: str = "hi") -> dict:
    """Instruction-based refine of a MIRRORED draft. Re-emitting through the house
    renderer would throw away the matched reference format, so the revision goes back
    through the block engine: current draft (its markup encodes the layout) + the
    change request → the full revised block document."""
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
    user = (
        "REVISION TASK — the advocate already has the draft below (it was matched to their uploaded "
        "reference; its HTML classes encode the block layout) and wants changes made to it.\n\n"
        f"CURRENT DRAFT:\n{(prior_html or '').strip()[:_MIRROR_REF_CAP]}\n\n"
        f"REQUESTED CHANGES:\n{(instruction or '').strip()}\n\n"
        "Reproduce the ENTIRE draft as JSON blocks per the schema, preserving its structure, formatting "
        "and every part the advocate did not ask to change; apply only the requested changes. The current "
        "draft plus the instruction are the ONLY sources of facts — ____ stays ____ unless the instruction "
        f"fills it. Write in {'Hindi' if lang == 'hi' else 'English'}."
    )
    raw, meta = _call_deepseek_or_groq(MIRROR_SYSTEM, user, max_tokens=16000, claude_model=config.DRAFTER_AUTHOR_MODEL, json_mode=True)
    payload = parse_json_response(raw)
    if not isinstance(payload.get("blocks"), list) or len(payload["blocks"]) < 4:
        raise ValueError("mirror revision payload too thin")
    # the accepted prior draft + the new instruction are the facts of record here
    rendered = render_mirrored(payload, doc_type, source=(prior_html or "") + "\n" + (instruction or ""))
    result = _mirror_result(payload, rendered, doc_type, lang, meta)
    result["mirrored"] = True
    return result


def author_payload(matter: str, doc_type: str, lang: str = "hi", *, court: str = "",
                   reference_skeleton: str = "", format_exemplar: str = "") -> dict:
    """Call the runtime LLM (DeepSeek → Groq; never Claude) and return the parsed,
    schema-shaped payload. Raises on LLM/parse failure (caller decides fallback).
    If `reference_skeleton` is given, the draft is authored to MIRROR that structure/voice.
    If `format_exemplar` is given (the canonical template rendered blank), the draft is
    authored INTO that prescribed format — templates as curriculum, not cage."""
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
    system = _author_system(doc_type, lang, format_exemplar=format_exemplar)
    b = brief_for(doc_type)
    user = (
        f"MATTER (the advocate's instructions / facts — use ONLY these facts):\n{matter.strip()}\n\n"
        f"Court level (use if sensible, else infer): {court or b.get('court')}\n"
        f"Draft the {b['label_en']} now, in {'Hindi' if lang == 'hi' else 'English'}, as JSON per the schema."
    )
    if reference_skeleton:
        user += _mirror_instruction(reference_skeleton)
    # Authoring routes through DRAFTER_AUTHOR_MODEL (default Sonnet→DeepSeek R1) so the
    # grounds are reasoned, not merely assembled. Set env to claude-haiku-4-5 for V3.
    try:
        raw, meta = _call_deepseek_or_groq(system, user, max_tokens=9000, claude_model=config.DRAFTER_AUTHOR_MODEL, json_mode=True)
        if _looks_script_corrupt(raw):
            raise ValueError("author output script-corrupt (CJK) — re-generating")
        payload = parse_json_response(raw)
    except Exception:
        # SLIM RETRY — covers failure classes: (a) the ~14K-token skill prefix 413s the
        # free-tier fallback (Groq 12K TPM); (b) broken/truncated JSON; (c) the model
        # drifted into CJK glyphs instead of Devanagari. A fresh roll usually lands; a
        # skill-less authored draft beats no draft; every guard still applies.
        slim = _author_system(doc_type, lang, format_exemplar=format_exemplar, inject_skill=False)
        raw, meta = _call_deepseek_or_groq(slim, user, max_tokens=9000, claude_model=config.DRAFTER_AUTHOR_MODEL, json_mode=True)
        payload = parse_json_response(raw)
    return _shape_payload(payload, doc_type, b, meta)


def author_document(matter: str, doc_type: str, lang: str = "hi", *, court: str = "",
                    reference_skeleton: str = "", format_exemplar: str = "") -> dict:
    """End-to-end authoring: prompt → house-style court-ready HTML + flagged extras.
    Returns {ok, mode, doc_type, html, cite_at_hearing, companions, warnings, meta}."""
    payload = author_payload(matter, doc_type, lang, court=court,
                             reference_skeleton=reference_skeleton, format_exemplar=format_exemplar)
    # ground every fact in the output against the advocate's own brief (the matter)
    rendered = render_authored(payload, lang, source=matter)
    # …and the mirror duty: everything concrete the advocate GAVE must be in the draft
    rendered["warnings"].extend(coverage_warnings(matter, rendered["html"], lang))
    if payload.get("_truncated"):
        rendered["warnings"].insert(0, _TRUNCATION_WARN["en" if lang == "en" else "hi"])
    return {
        "ok": True,
        "mode": "authored",
        "doc_type": doc_type,
        "lang": lang,
        "html": rendered["html"],
        "cite_at_hearing": rendered["cite_at_hearing"],
        "companions": rendered["companions"],
        "needs_affidavit": rendered["needs_affidavit"],
        "warnings": rendered["warnings"],
        "ungrounded": rendered.get("ungrounded") or [],
        "title": payload.get("title_line") or brief_for(doc_type)["label_hi"],
        "meta": payload.get("_meta"),
    }


def revise_document(prior_text: str, instruction: str, doc_type: str = "other_criminal",
                    lang: str = "hi", *, court: str = "") -> dict:
    """Instruction-based refine of an already-authored draft: the advocate's CURRENT draft
    + a change request → the FULL revised draft, still under house-style + zero-fabrication.
    This is the edit path for authored (non-canonical) drafts, which have no structured fields."""
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
    system = _author_system(doc_type, lang)
    b = brief_for(doc_type)
    user = (
        "REVISION TASK — the advocate already has the draft below and wants changes made to it.\n\n"
        f"CURRENT DRAFT:\n{(prior_text or '').strip()}\n\n"
        f"REQUESTED CHANGES:\n{(instruction or '').strip()}\n\n"
        f"Return the FULL revised draft as JSON per the schema, in {'Hindi' if lang == 'hi' else 'English'}. "
        "Preserve everything the advocate did NOT ask to change; apply only the requested changes. "
        "Keep the house style and the zero-fabrication rules in force."
    )
    try:
        raw, meta = _call_deepseek_or_groq(system, user, max_tokens=9000, claude_model=config.DRAFTER_AUTHOR_MODEL, json_mode=True)
        payload = _shape_payload(parse_json_response(raw), doc_type, b, meta)
    except Exception:
        # slim retry (see author_payload) — keep the edit path alive on the free tier
        # and re-roll on broken/truncated JSON
        slim = _author_system(doc_type, lang, inject_skill=False)
        raw, meta = _call_deepseek_or_groq(slim, user, max_tokens=9000, claude_model=config.DRAFTER_AUTHOR_MODEL, json_mode=True)
        payload = _shape_payload(parse_json_response(raw), doc_type, b, meta)
    # a refine's facts of record = the accepted prior draft + the new instruction
    rendered = render_authored(payload, lang, source=(prior_text or "") + "\n" + (instruction or ""))
    return {
        "ok": True,
        "mode": "authored",
        "doc_type": doc_type,
        "lang": lang,
        "html": rendered["html"],
        "cite_at_hearing": rendered["cite_at_hearing"],
        "companions": rendered["companions"],
        "needs_affidavit": rendered["needs_affidavit"],
        "warnings": rendered["warnings"],
        "ungrounded": rendered.get("ungrounded") or [],
        "title": payload.get("title_line") or brief_for(doc_type)["label_hi"],
        "meta": payload.get("_meta"),
    }
