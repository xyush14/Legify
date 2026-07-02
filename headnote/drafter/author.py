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
VERIFIED_CITATIONS["other_criminal"] = []
VERIFIED_CITATIONS["other_civil"] = []


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
    "other_civil": {
        "label_hi": "वाद / आवेदन पत्र", "label_en": "Plaint / Application",
        "court": "civil", "case_code_hi": "व्यवहार वाद क्रमांक", "case_code_en": "Civil Suit",
        "side_hi": "वादी की ओर से", "side_en": "On behalf of the Plaintiff",
        "section_hi": "",
        "brief": (
            "A civil matter (suit, petition, application) for which we have no dedicated template — e.g. a "
            "suit for recovery / declaration / injunction / specific performance / partition, a written "
            "statement, or an interlocutory application (Order 39 temporary injunction, etc.). Lay it out "
            "as a plaint where appropriate: parties, jurisdiction & valuation, cause of action with "
            "material facts numbered, the relief/prayer, and the verification under Order VI Rule 15 CPC. "
            "Cite the correct CPC Order/Rule and substantive statute. Do not invent facts or case law."
        ),
        "skeleton": [
            "F: parties and their description",
            "F: jurisdiction and valuation (पक्षकार / क्षेत्राधिकार / मूल्यांकन)",
            "F: cause of action — material facts, numbered chronologically",
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


def family_for(doc_type: str) -> str:
    """Map a classifier doc_type to its citation-whitelist family."""
    doc_type = _FAMILY_ALIAS.get(doc_type, doc_type)
    return doc_type if doc_type in VERIFIED_CITATIONS else (
        "other_civil" if doc_type == "other_civil" else "other_criminal"
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

HOUSE_STYLE = """You are the drafting engine of Headnote, drafting for a senior Indian trial-court advocate
in Madhya Pradesh. You produce a COURT-READY litigation draft in that advocate's house style — it must be
indistinguishable from a document a senior advocate's office actually files. NOT a generic, plain-English,
"school application" letter. You write the SUBSTANCE (facts recital, the numbered grounds, the prayer); the
page layout is applied by Headnote, so you return STRUCTURED JSON only.

HOUSE STYLE — follow exactly:
• Default language is Hindi in formal court register (Devanagari), unless asked for English. This is the
  language of an MP district/High-Court filing — NOT Hinglish, NOT casual Hindi.
• PARTIES: a full descriptor block, not a bare name. Applicant = naam + पुत्र/पुत्री/पत्नी श्री <father/husband>
  + आयु + व्यवसाय + निवासी <address>, जिला <district> (<state>). Respondent for a State criminal matter =
  "<state> शासन द्वारा, पुलिस थाना <PS>, जिला <district>". Use the right party LABELS per matter:
  आवेदक/आवेदिका (applicant), प्रार्थी/प्रार्थिनी (petitioner in body), अनावेदक (non-applicant/State),
  व्यथित (DV aggrieved), प्रत्यर्थीगण (DV respondents), वादी/प्रतिवादी (civil plaintiff/defendant),
  अपीलार्थी (appellant), पुनरीक्षणकर्ता (revisionist).
• COURT NAME: compose the correct cause-title — e.g. "न्यायालय माननीय सत्र न्यायाधीश महोदय, <नगर> (म.प्र.)",
  "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, <नगर> (म.प्र.)", "माननीय उच्च न्यायालय मध्यप्रदेश
  खण्डपीठ <bench>", "न्यायालय माननीय प्रधान न्यायाधीश महोदय, कुटुम्ब न्यायालय, <नगर> (म.प्र.)".
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
• Do NOT invent FACTS either. Use only what the user gave. For any unknown but needed fact (a name, date, FIR
  number, amount), write a blank "____" in the text — never guess. It is better to leave ____ than to fabricate.

VERIFIED CITATIONS YOU MAY USE IN THE BODY (only these; reproduce exactly; omit if not apposite):
{verified}

THE MATTER TYPE: {label}
CONTROLLING LAW & APPROACH: {brief}
BODY SKELETON (lay the paragraphs out in this order; [..] paras only if the facts support them):
{skeleton}

Return ONLY valid JSON (no markdown fence), in this exact shape:
{
  "lang": "hi" | "en",
  "court_level": "magistrate" | "cjm" | "sessions" | "principal_sessions" | "family" | "hc" | "civil",
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


def _author_system(doc_type: str, lang: str) -> str:
    b = brief_for(doc_type)
    fam = family_for(doc_type)
    skeleton = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(b.get("skeleton", [])))
    return (HOUSE_STYLE
            .replace("{section_map}", _SECTION_MAP_NOTE)
            .replace("{verified}", _verified_block(fam))
            .replace("{label}", f'{b["label_hi"]} ({b["label_en"]})')
            .replace("{brief}", b.get("brief", ""))
            .replace("{skeleton}", skeleton or "  (compose a sensible order: facts → grounds → prayer)")
            .replace("{lang}", "Hindi" if lang == "hi" else "English"))


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
# 5) RENDER  — structured content → canonical header + cb-* body (house format).
# ===========================================================================
def _esc(s: Optional[str]) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_DEFAULT_VERIFICATION = (
    "सत्यापित किया जाता है कि उपरोक्त आवेदन पत्र की समस्त बातें मेरी व्यक्तिगत जानकारी एवं अभिलेख के "
    "आधार पर सत्य व सही हैं, जिसमें कुछ भी असत्य नहीं है और न ही कुछ छिपाया गया है।"
)
_DEFAULT_VERIFICATION_EN = (
    "It is verified that the contents of the above application are true and correct to my personal "
    "knowledge and the record; nothing material has been concealed."
)


def render_authored(p: dict, lang: str = "hi") -> dict:
    """Render an authored payload into house-format HTML. Returns
    {html, warnings, cite_at_hearing, companions}. Pure/deterministic — no LLM."""
    hi = lang != "en"
    p = p or {}
    warnings = list(p.get("warnings") or [])

    court_level = (p.get("court_level") or "sessions").strip()
    court_name = (p.get("court_name") or "").strip() or compose_court_name(
        court_level if court_level in ("magistrate", "cjm", "sessions", "principal_sessions", "family", "hc") else "sessions",
        "", "म.प्र." if hi else "M.P.", lang="hi" if hi else "en")

    hdr = render_header({
        "side_label": p.get("side_label") or "",
        "court_name": court_name,
        "case_code": p.get("case_code") or ("प्रकरण क्रमांक" if hi else "Case"),
        "case_number": p.get("case_number") or "",
        "case_year": p.get("case_year") or "",
        "applicant_label": p.get("applicant_label") or ("आवेदक" if hi else "Applicant"),
        "applicant_desc": [_esc(x) for x in (p.get("applicant_desc") or [])] or [_esc(p.get("applicant_label") or "")],
        "respondent_label": p.get("respondent_label") or ("अनावेदक" if hi else "Respondent"),
        "respondent_desc": [_esc(x) for x in (p.get("respondent_desc") or [])],
        "versus": p.get("versus") or ("बनाम" if hi else "Versus"),
        "title_line": p.get("title_line") or "",
    })

    out = [hdr, '<div class="doc-body">']
    for pre in (p.get("prelude") or []):
        if str(pre).strip():
            out.append(f'<p class="cb-prelude">{_esc(pre)}</p>')
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
        text, flagged = _guard_citations(text, fam_fps)
        if flagged:
            flagged_any = True
            out.append(f'<li>{_esc(text)} <span class="ph">[उद्धृत निर्णय — सत्यापन आवश्यक]</span></li>')
        else:
            out.append(f'<li>{_esc(text)}</li>')
    out.append('</ol>')
    if flagged_any:
        warnings.append("एक या अधिक आधारों में उद्धृत निर्णय श्वेतसूची में नहीं है — पीठासीन से सत्यापन के बिना "
                        "बहस में प्रयोग न करें। (An in-body citation is outside the verified list — verify before use.)")

    prayer = (p.get("prayer") or "").strip()
    if prayer:
        out.append(f'<div class="cb-prayer"><p>{_esc(prayer)}</p></div>')

    # section-pair guard — flag BNSS↔CrPC mismatches anywhere in the authored text
    _texts = [p.get("title_line") or "", prayer]
    _texts += [str(i.get("text") or "") if isinstance(i, dict) else str(i) for i in paras]
    warnings.extend(guard_sections(_texts))

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
    return {
        "html": "\n".join(out),
        "warnings": warnings,
        "cite_at_hearing": p.get("cite_at_hearing") or [],
        "companions": p.get("companions") or [],
        "needs_affidavit": bool(p.get("needs_affidavit")),
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
            claude_model="claude-haiku-4-5")
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
        "____ for anything unknown). Do NOT copy the reference's own facts, and do NOT reproduce any citation from "
        "it — re-derive all content for this matter under the zero-fabrication rule.\n"
        "REFERENCE STRUCTURE TO MATCH:\n" + reference_skeleton
    )


def author_payload(matter: str, doc_type: str, lang: str = "hi", *, court: str = "",
                   reference_skeleton: str = "") -> dict:
    """Call the runtime LLM (DeepSeek → Groq; never Claude) and return the parsed,
    schema-shaped payload. Raises on LLM/parse failure (caller decides fallback).
    If `reference_skeleton` is given, the draft is authored to MIRROR that structure/voice."""
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
    system = _author_system(doc_type, lang)
    b = brief_for(doc_type)
    user = (
        f"MATTER (the advocate's instructions / facts — use ONLY these facts):\n{matter.strip()}\n\n"
        f"Court level (use if sensible, else infer): {court or b.get('court')}\n"
        f"Draft the {b['label_en']} now, in {'Hindi' if lang == 'hi' else 'English'}, as JSON per the schema."
    )
    if reference_skeleton:
        user += _mirror_instruction(reference_skeleton)
    # V3 (deepseek-chat) = fast structured assembly; the heavy reasoning is in the prompt.
    raw, meta = _call_deepseek_or_groq(system, user, max_tokens=4000, claude_model="claude-haiku-4-5")
    payload = parse_json_response(raw)
    return _shape_payload(payload, doc_type, b, meta)


def author_document(matter: str, doc_type: str, lang: str = "hi", *, court: str = "",
                    reference_skeleton: str = "") -> dict:
    """End-to-end authoring: prompt → house-style court-ready HTML + flagged extras.
    Returns {ok, mode, doc_type, html, cite_at_hearing, companions, warnings, meta}."""
    payload = author_payload(matter, doc_type, lang, court=court, reference_skeleton=reference_skeleton)
    rendered = render_authored(payload, lang)
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
    raw, meta = _call_deepseek_or_groq(system, user, max_tokens=4000, claude_model="claude-haiku-4-5")
    payload = _shape_payload(parse_json_response(raw), doc_type, b, meta)
    rendered = render_authored(payload, lang)
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
        "title": payload.get("title_line") or brief_for(doc_type)["label_hi"],
        "meta": payload.get("_meta"),
    }
