"""23 additional templates — Phase 4 of the v2 drafting reorganisation.

Court taxonomy:
  SC          → 3 templates (placeholders, no references yet)
  HC          → 3 NEW (existing HC templates tuned separately in v1 file)
  Sessions   → 4 NEW
  Magistrate → 9 NEW
  Family     → 3 NEW (maintenance already in v1)
  Procedural → 1 NEW (vakalatnama, mention_memo already in v1)

Each template's format_spec is v1 quality — written from general knowledge
of Indian court formats. They produce structurally complete drafts but
will be retuned using Vishnu ji's reference filings (after the Kruti Dev
converter is built and we can decode the actual filings).

Wrapper templates (regular_bail_sessions, anticipatory_bail_sessions,
trial_bail_437) have a `redirect_url` field — the universal drafter
auto-navigates there on load, so the user lands on the polished bail
page UX (/draft/bail) instead of the generic form drafter.

Each dict carries court / court_label_en / court_label_hi / popularity
DIRECTLY (no central _COURT_METADATA lookup needed for these). The v1
templates still use the lookup table; both styles coexist.
"""

from __future__ import annotations


# ============================================================================
# SUPREME COURT (3) — placeholders, refine when refs available
# ============================================================================

SLP_CRIMINAL = {
    "id":              "slp_criminal",
    "name_en":         "Special Leave Petition (Criminal)",
    "name_hi":         "विशेष अनुमति याचिका (दण्ड)",
    "court":           "sc",
    "court_label_en":  "Supreme Court",
    "court_label_hi":  "उच्चतम न्यायालय",
    "category":        "appeal",
    "tier":            2,
    "popularity":      4,
    "quality":         "v1-ai",
    "description":     "SLP under Article 136 against a final order of the High Court in a criminal matter.",
    "fields": [
        {"key": "court_name",       "label_en": "Court",                          "label_hi": "न्यायालय",                 "type": "text",     "required": True,  "section": "court", "hint": "'Supreme Court of India'"},
        {"key": "petitioner_name",  "label_en": "Petitioner name",                "label_hi": "याचिकाकर्ता का नाम",        "type": "name",     "required": True,  "section": "applicant"},
        {"key": "respondent_name",  "label_en": "Respondent (State / opp party)", "label_hi": "प्रतिवादी",                 "type": "text",     "required": True,  "section": "respondent"},
        {"key": "impugned_court",   "label_en": "High Court whose order is challenged", "label_hi": "विवादित आदेश का न्यायालय", "type": "text", "required": True, "section": "order"},
        {"key": "impugned_case_no", "label_en": "High Court case number",         "label_hi": "उच्च न्यायालय का प्रकरण क्रमांक","type": "text", "required": True, "section": "order"},
        {"key": "impugned_date",    "label_en": "Date of impugned order",         "label_hi": "विवादित आदेश का दिनांक",     "type": "date",     "required": True,  "section": "order"},
        {"key": "facts_narrative",  "label_en": "Brief facts",                    "label_hi": "संक्षिप्त तथ्य",            "type": "longtext", "required": True,  "section": "facts"},
        {"key": "questions_of_law", "label_en": "Substantial questions of law",   "label_hi": "विधि के सारवान प्रश्न",     "type": "longtext", "required": True,  "section": "grounds"},
        {"key": "grounds_narrative","label_en": "Grounds for grant of leave",     "label_hi": "अनुमति प्रदान करने के आधार",  "type": "longtext", "required": True,  "section": "grounds"},
        {"key": "prayer",           "label_en": "Prayer",                         "label_hi": "प्रार्थना",                  "type": "longtext", "required": True,  "section": "prayer"},
        {"key": "advocate_name",    "label_en": "Advocate on Record name",        "label_hi": "अधिवक्ता का नाम",           "type": "name",     "required": True,  "section": "filing"},
        {"key": "advocate_enrollment", "label_en": "AOR / enrolment no.",         "label_hi": "बार पंजीयन क्रमांक",          "type": "text",     "required": False, "section": "filing"},
        {"key": "place",            "label_en": "Place",                          "label_hi": "स्थान",                     "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",      "label_en": "Date",                           "label_hi": "दिनांक",                     "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a Special Leave Petition (Criminal) under Article 136 of the Constitution. Structure:\n"
        "1. Header: 'IN THE SUPREME COURT OF INDIA' (centred, caps, underlined). "
        "Sub-line: 'CRIMINAL APPELLATE JURISDICTION'.\n"
        "2. Case no. block: 'Special Leave Petition (Crl.) No. ____ of ____'\n"
        "3. Petitioner / Respondent block in standard SC format with full address & father's name.\n"
        "4. Title: 'PETITION UNDER ARTICLE 136 OF THE CONSTITUTION OF INDIA' (centred, underlined, bold).\n"
        "5. 'To, The Hon'ble The Chief Justice and His Companion Justices of the Supreme Court of India.'\n"
        "6. 'The humble petition of the petitioner above-named most respectfully showeth:'\n"
        "7. Numbered paras (1, 2, 3...) covering: (a) brief facts; (b) procedural history below "
        "(trial court → HC); (c) impugned HC order with citation; (d) reasons HC erred.\n"
        "8. 'QUESTIONS OF LAW' section — numbered substantial questions for SC consideration.\n"
        "9. 'GROUNDS' section — A, B, C, D... — each ground 1-3 sentences. Cite SC authorities.\n"
        "10. 'PRAYER': 'It is most respectfully prayed that this Hon'ble Court may be pleased to: "
        "(a) grant leave to appeal against the impugned order ... ; (b) ... ; (c) pass such other "
        "and further orders as this Hon'ble Court may deem fit and proper.'\n"
        "11. 'AND FOR THIS ACT OF KINDNESS, the petitioner as in duty bound shall ever pray.'\n"
        "12. Signed by Advocate-on-Record + petitioner. Place + Date at bottom-left.\n\n"
        "Use formal English (SC matters are filed in English). Reserve Hindi for the verification "
        "if user prefers. Plain text output, no markdown."
    ),
    "example_prompts": [
        "SLP against MP HC order in Cr.A. 234/2025 — appeal dismissed, conviction confirmed under S.302 IPC",
        "Special leave petition for my client whose anticipatory bail was rejected by Allahabad HC",
    ],
}


TRANSFER_PETITION_CRI = {
    "id":              "transfer_petition_cri",
    "name_en":         "Transfer Petition (Criminal)",
    "name_hi":         "स्थानांतरण याचिका (दण्ड)",
    "court":           "sc",
    "court_label_en":  "Supreme Court",
    "court_label_hi":  "उच्चतम न्यायालय",
    "category":        "procedural",
    "tier":            2,
    "popularity":      2,
    "quality":         "v1-ai",
    "description":     "Petition under S.448 BNSS / S.406 CrPC seeking transfer of a criminal case from one State to another.",
    "fields": [
        {"key": "petitioner_name",   "label_en": "Petitioner name",                "label_hi": "याचिकाकर्ता",              "type": "name",     "required": True,  "section": "applicant"},
        {"key": "respondent_name",   "label_en": "Respondent",                     "label_hi": "प्रतिवादी",                "type": "text",     "required": True,  "section": "respondent"},
        {"key": "case_no",           "label_en": "Case to be transferred (no.)",   "label_hi": "स्थानांतरित करवाने वाला प्रकरण","type": "text", "required": True, "section": "matter"},
        {"key": "current_court",     "label_en": "Current court / state",          "label_hi": "वर्तमान न्यायालय / राज्य",   "type": "text",     "required": True,  "section": "matter"},
        {"key": "proposed_court",    "label_en": "Proposed transferee court / state","label_hi": "प्रस्तावित न्यायालय / राज्य","type": "text", "required": True, "section": "matter"},
        {"key": "transfer_grounds",  "label_en": "Grounds for transfer",           "label_hi": "स्थानांतरण के आधार",         "type": "longtext", "required": True,  "section": "grounds", "hint": "Threat to safety / hardship / fair trial concerns"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",            "type": "name",     "required": True,  "section": "filing"},
        {"key": "place",             "label_en": "Place",                          "label_hi": "स्थान",                      "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                      "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a Transfer Petition (Criminal) under S.448 BNSS / S.406 CrPC for SC filing. Structure:\n"
        "1. 'IN THE SUPREME COURT OF INDIA — CRIMINAL ORIGINAL JURISDICTION' header.\n"
        "2. 'Transfer Petition (Crl.) No. ____ of ____' case block.\n"
        "3. Petitioner / Respondent block.\n"
        "4. Title: 'PETITION UNDER S.448 BNSS / S.406 CrPC FOR TRANSFER OF CRIMINAL CASE' (centred, underlined).\n"
        "5. Numbered paras: (a) details of the case sought to be transferred (no., court, state); "
        "(b) procedural history; (c) specific grounds: threat to petitioner's safety, inconvenience to "
        "witnesses, distance, language barrier, apprehension of unfair trial, etc.; (d) why proposed "
        "court is appropriate.\n"
        "6. 'PRAYER': transfer case from X court / State to Y court / State.\n"
        "7. Signed by advocate + petitioner. Place + Date.\n"
        "Tone: formal English, deferential. Plain text output."
    ),
    "example_prompts": [
        "Transfer petition to move 376 IPC case from district court Lucknow to Delhi due to safety threats",
        "Need transfer petition — wife filed 498A in Pune, husband works in Bangalore",
    ],
}


REVIEW_PETITION_SC = {
    "id":              "review_petition_sc",
    "name_en":         "Review Petition (Supreme Court)",
    "name_hi":         "पुनरीक्षण याचिका (उच्चतम न्यायालय)",
    "court":           "sc",
    "court_label_en":  "Supreme Court",
    "court_label_hi":  "उच्चतम न्यायालय",
    "category":        "appeal",
    "tier":            2,
    "popularity":      2,
    "quality":         "v1-ai",
    "description":     "Review Petition under Article 137 of the Constitution against a final SC order/judgment.",
    "fields": [
        {"key": "petitioner_name",   "label_en": "Petitioner",                     "label_hi": "याचिकाकर्ता",              "type": "name",     "required": True,  "section": "applicant"},
        {"key": "respondent_name",   "label_en": "Respondent",                     "label_hi": "प्रतिवादी",                "type": "text",     "required": True,  "section": "respondent"},
        {"key": "impugned_order_no", "label_en": "SC order/judgment number",       "label_hi": "उच्चतम न्यायालय का आदेश क्रमांक","type":"text","required": True, "section": "order"},
        {"key": "impugned_date",     "label_en": "Date of order under review",     "label_hi": "विवादित आदेश का दिनांक",      "type": "date",     "required": True,  "section": "order"},
        {"key": "error_grounds",     "label_en": "Errors apparent on record",      "label_hi": "अभिलेख में स्पष्ट त्रुटियां",  "type": "longtext", "required": True,  "section": "grounds"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",            "type": "name",     "required": True,  "section": "filing"},
        {"key": "place",             "label_en": "Place",                          "label_hi": "स्थान",                      "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                      "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a Review Petition under Article 137 of the Constitution for SC filing. Structure:\n"
        "1. 'IN THE SUPREME COURT OF INDIA — CRIMINAL APPELLATE JURISDICTION (REVIEW)' header.\n"
        "2. 'Review Petition (Crl.) No. ____ of ____ IN <original case no>' block.\n"
        "3. Parties block matching the original case.\n"
        "4. Title: 'PETITION UNDER ARTICLE 137 OF THE CONSTITUTION OF INDIA SEEKING REVIEW OF "
        "ORDER DATED <date>' (centred, underlined).\n"
        "5. Numbered paras: (a) brief outline of the original matter; (b) the impugned SC order "
        "with date and bench; (c) specific errors apparent on the face of the record (NOT a re-argument "
        "— stick to errors); (d) new important matter or evidence discovered (if any).\n"
        "6. 'PRAYER': review and set aside / modify the SC order dated X.\n"
        "Tone: very formal — SC review is a high bar; phrasing must show the petitioner respects "
        "finality and only invokes review for clear errors. Plain text output."
    ),
    "example_prompts": [
        "Review of SC order dated 12.03.2025 in Crl.A. 1245/2024 — Court overlooked critical evidence",
        "SC review petition where the order didn't consider our cited Constitution Bench judgment",
    ],
}


# ============================================================================
# HIGH COURT (3 NEW)
# ============================================================================

HABEAS_CORPUS_226 = {
    "id":              "habeas_corpus_226",
    "name_en":         "Habeas Corpus Petition (Art. 226)",
    "name_hi":         "बंदी प्रत्यक्षीकरण याचिका (अनुच्छेद 226)",
    "court":           "hc",
    "court_label_en":  "High Court",
    "court_label_hi":  "उच्च न्यायालय",
    "category":        "writ",
    "tier":            1,
    "popularity":      4,
    "quality":         "v1-ai",
    "description":     "Writ of habeas corpus — challenges illegal detention. Filed before the High Court of the State where the detained person is held.",
    "fields": [
        {"key": "court_name",        "label_en": "High Court",                     "label_hi": "उच्च न्यायालय",            "type": "text",     "required": True,  "section": "court"},
        {"key": "petitioner_name",   "label_en": "Petitioner (next friend)",       "label_hi": "याचिकाकर्ता",               "type": "name",     "required": True,  "section": "applicant", "hint": "Family member / friend filing on behalf of the detenue"},
        {"key": "petitioner_relation","label_en": "Relationship with detenue",     "label_hi": "बंदी से संबंध",              "type": "text",     "required": True,  "section": "applicant"},
        {"key": "detenue_name",      "label_en": "Detained person",                "label_hi": "बंदी (निरुद्ध व्यक्ति)",       "type": "name",     "required": True,  "section": "detenue"},
        {"key": "detenue_age",       "label_en": "Detenue age",                    "label_hi": "बंदी की आयु",                "type": "text",     "required": False, "section": "detenue"},
        {"key": "detenue_address",   "label_en": "Detenue ordinary address",       "label_hi": "बंदी का सामान्य पता",         "type": "address",  "required": True,  "section": "detenue"},
        {"key": "detained_by",       "label_en": "Detaining authority (PS / jail)","label_hi": "निरोध करने वाला (थाना/जेल)",   "type": "text",     "required": True,  "section": "detention"},
        {"key": "detention_date",    "label_en": "Date of detention",              "label_hi": "निरोध दिनांक",                "type": "date",     "required": True,  "section": "detention"},
        {"key": "circumstances",     "label_en": "Circumstances of detention",     "label_hi": "निरोध की परिस्थितियां",       "type": "longtext", "required": True,  "section": "facts"},
        {"key": "illegality_grounds","label_en": "Why detention is illegal",       "label_hi": "निरोध अवैध क्यों है",          "type": "longtext", "required": True,  "section": "grounds", "hint": "No FIR / No production / Beyond 24 hours / No warrant / etc."},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "place",             "label_en": "Place",                          "label_hi": "स्थान",                       "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                       "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a Habeas Corpus Petition under Article 226 of the Constitution. Structure (Hindi or English per lang):\n"
        "1. Header: 'माननीय उच्च न्यायालय <state>, <bench>' / 'IN THE HON'BLE HIGH COURT OF <state>, <bench>' centred, underlined.\n"
        "2. Case block: 'W.P. (Crl.) No. ____ / <year>' / 'रिट याचिका (दण्ड) क्र. ____ / <वर्ष>'.\n"
        "3. Petitioner block: '<petitioner_name>, <relation> of the detenue, r/o <address>'.\n"
        "4. Respondents: State + detaining authority (PS / Jail Superintendent).\n"
        "5. Title: 'PETITION UNDER ARTICLE 226 OF THE CONSTITUTION OF INDIA SEEKING ISSUANCE OF "
        "WRIT OF HABEAS CORPUS' centred, underlined, bold.\n"
        "6. 'Most respectfully showeth:'\n"
        "7. Numbered paras: (i) who detenue is + relationship; (ii) the detention — when, where, by whom; "
        "(iii) circumstances — any FIR, was detenue produced before magistrate within 24 hours, what "
        "section invoked; (iv) illegality — Article 22 violation, no judicial authorisation, etc.; "
        "(v) urgency — life and liberty at stake.\n"
        "8. 'PRAYER': (a) writ of habeas corpus directing respondents to produce the detenue before "
        "this Hon'ble Court; (b) release of the detenue forthwith if detention is found illegal; "
        "(c) cost; (d) such other reliefs.\n"
        "9. 'AND for this act of kindness, the petitioner as in duty bound shall ever pray.'\n"
        "10. Verification: 'I, <petitioner>, do hereby solemnly affirm and declare that the contents "
        "of this petition are true to my knowledge.'\n"
        "11. Signed by petitioner + advocate. Place + Date.\n"
        "Tone: urgent + formal — habeas matters get same-day listing. Plain text output."
    ),
    "example_prompts": [
        "Habeas corpus — my brother taken by Murar police 3 days ago, no FIR, no production",
        "बंदी प्रत्यक्षीकरण — मेरे पति को थाना मक्सी ने 5 दिन से बिठा रखा है, कोई FIR नहीं",
    ],
}


SUSPENSION_OF_SENTENCE = {
    "id":              "suspension_of_sentence",
    "name_en":         "Suspension of Sentence (S.430 BNSS / 389 CrPC)",
    "name_hi":         "दण्डादेश के निलंबन हेतु आवेदन",
    "court":           "hc",
    "court_label_en":  "High Court",
    "court_label_hi":  "उच्च न्यायालय",
    "category":        "bail",
    "tier":            1,
    "popularity":      4,
    "quality":         "v1-ai",
    "description":     "Application under S.430 BNSS / 389 CrPC to suspend execution of sentence pending appeal, and grant bail to the convicted appellant.",
    "fields": [
        {"key": "court_name",       "label_en": "Court",                          "label_hi": "न्यायालय",                  "type": "text",     "required": True,  "section": "court", "hint": "Usually 'MP HC <bench>'"},
        {"key": "appeal_no",        "label_en": "Appeal number",                  "label_hi": "अपील क्रमांक",                "type": "text",     "required": True,  "section": "court", "hint": "e.g. Crl. Appeal No. ___ / 2026"},
        {"key": "appellant_name",   "label_en": "Appellant (convicted accused)",  "label_hi": "अपीलकर्ता (दण्डित अभियुक्त)", "type": "name",     "required": True,  "section": "applicant"},
        {"key": "appellant_father", "label_en": "Father's name",                  "label_hi": "पिता का नाम",                "type": "name",     "required": True,  "section": "applicant"},
        {"key": "appellant_age",    "label_en": "Age",                            "label_hi": "आयु",                        "type": "text",     "required": False, "section": "applicant"},
        {"key": "current_jail",     "label_en": "Currently lodged at (jail)",     "label_hi": "वर्तमान निरोध स्थान (जेल)",   "type": "text",     "required": True,  "section": "applicant"},
        {"key": "trial_court",      "label_en": "Trial court whose conviction is challenged","label_hi": "विचारण न्यायालय",   "type": "text", "required": True, "section": "matter"},
        {"key": "sections",         "label_en": "Sections of conviction",         "label_hi": "दण्डादेश की धाराएं",          "type": "text",     "required": True,  "section": "matter"},
        {"key": "sentence",         "label_en": "Sentence imposed",               "label_hi": "लगाया गया दण्ड",              "type": "text",     "required": True,  "section": "matter", "hint": "e.g. 7 years RI + ₹5,000 fine"},
        {"key": "sentence_date",    "label_en": "Date of judgment",               "label_hi": "निर्णय दिनांक",                "type": "date",     "required": True,  "section": "matter"},
        {"key": "grounds",          "label_en": "Grounds for suspension",         "label_hi": "निलंबन के आधार",              "type": "longtext", "required": True,  "section": "grounds", "hint": "Strong prima facie case in appeal / advanced age / medical / long custody / etc."},
        {"key": "advocate_name",    "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "place",            "label_en": "Place",                          "label_hi": "स्थान",                       "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",      "label_en": "Date",                           "label_hi": "दिनांक",                       "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate an Application for Suspension of Sentence under S.430 BNSS / 389 CrPC, filed in the "
        "criminal appeal pending before the High Court. Structure:\n"
        "1. Court header centred + underlined.\n"
        "2. 'IA No. ____ IN Criminal Appeal No. <appeal_no>' block.\n"
        "3. Appellant block: name, s/o father, age, currently lodged at <jail>.\n"
        "4. 'Versus' centred.\n"
        "5. 'State of <state>' as respondent.\n"
        "6. Title: 'APPLICATION UNDER S.430 BNSS / 389 CrPC FOR SUSPENSION OF SENTENCE AND GRANT OF "
        "BAIL DURING PENDENCY OF APPEAL' centred, underlined, bold.\n"
        "7. Numbered paras: (1) the appeal is admitted/pending; (2) appellant was convicted by trial "
        "court for <sections>, sentenced to <sentence> on <sentence_date>; (3) appeal has been preferred "
        "against conviction; (4) grounds why sentence should be suspended (use <grounds> field); "
        "(5) appellant has no other criminal antecedents (if true); (6) appellant undertakes to abide by "
        "all conditions imposed.\n"
        "8. 'PRAYER': (a) suspend execution of sentence dated <date>; (b) release appellant on bail "
        "on furnishing personal bond + sureties; (c) such other reliefs.\n"
        "9. Verification + signature + place + date.\n"
        "Tone: formal, focused on appeal-merits + appellant's track record. Plain text output."
    ),
    "example_prompts": [
        "Suspension of sentence — client convicted 7 years u/s 304-II IPC, appeal admitted last week, has been in jail 14 months",
        "Sentence suspension after Sessions Court conviction in 376 IPC — appeal pending in HC",
    ],
}


STAY_PETITION_HC = {
    "id":              "stay_petition_hc",
    "name_en":         "Stay Petition (Interim Order)",
    "name_hi":         "स्थगन आवेदन (अंतरिम)",
    "court":           "hc",
    "court_label_en":  "High Court",
    "court_label_hi":  "उच्च न्यायालय",
    "category":        "procedural",
    "tier":            2,
    "popularity":      3,
    "quality":         "v1-ai",
    "description":     "Interim application seeking stay of proceedings / execution of order / further investigation in a pending criminal matter before the High Court.",
    "fields": [
        {"key": "court_name",      "label_en": "Court",                          "label_hi": "न्यायालय",                "type": "text",     "required": True,  "section": "court"},
        {"key": "main_petition_no","label_en": "Main petition / case no.",      "label_hi": "मुख्य प्रकरण क्रमांक",       "type": "text",     "required": True,  "section": "court"},
        {"key": "petitioner_name", "label_en": "Petitioner / Applicant",         "label_hi": "याचिकाकर्ता",             "type": "name",     "required": True,  "section": "applicant"},
        {"key": "respondent_name", "label_en": "Respondent",                     "label_hi": "प्रतिवादी",               "type": "text",     "required": True,  "section": "respondent"},
        {"key": "what_to_stay",    "label_en": "What is sought to be stayed",    "label_hi": "किसका स्थगन चाहिए",        "type": "longtext", "required": True,  "section": "matter", "hint": "Trial court proceedings / coercive action / execution of impugned order / further investigation"},
        {"key": "stay_grounds",    "label_en": "Grounds for stay",               "label_hi": "स्थगन के आधार",            "type": "longtext", "required": True,  "section": "grounds", "hint": "Irreparable injury / prima facie case / balance of convenience"},
        {"key": "advocate_name",   "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",          "type": "name",     "required": True,  "section": "filing"},
        {"key": "place",           "label_en": "Place",                          "label_hi": "स्थान",                    "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",     "label_en": "Date",                           "label_hi": "दिनांक",                    "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate an Interim Application for stay, filed alongside or in a pending main petition. Structure:\n"
        "1. Court header centred + underlined.\n"
        "2. 'IA No. ____ IN <main_petition_no>' block.\n"
        "3. Parties matching main petition.\n"
        "4. Title: 'INTERIM APPLICATION FOR STAY OF PROCEEDINGS / EXECUTION / COERCIVE ACTION' centred, underlined.\n"
        "5. Numbered paras: (1) the main petition is pending before this Court; (2) what is sought to be stayed "
        "(use <what_to_stay>); (3) grounds — three classical limbs: prima facie case, balance of convenience, "
        "irreparable injury (use <stay_grounds>); (4) urgency.\n"
        "6. 'PRAYER': (a) stay <what_to_stay> till disposal of main petition; (b) ex-parte ad-interim "
        "stay if appropriate; (c) such other reliefs.\n"
        "7. Verification + signature + place + date.\n"
        "Tone: focused, urgent. Cite the three classical stay grounds explicitly. Plain text."
    ),
    "example_prompts": [
        "Stay of trial court proceedings during pending quashing petition before HC",
        "Interim stay of further investigation in FIR 95/2025 till main quashing petition is decided",
    ],
}


# ============================================================================
# SESSIONS COURT (4 NEW)
# ============================================================================

# Wrapper — links to the standalone bail page UX.
REGULAR_BAIL_SESSIONS = {
    "id":              "regular_bail_sessions",
    "name_en":         "Regular Bail (Sessions Court)",
    "name_hi":         "नियमित जमानत (सत्र न्यायालय)",
    "court":           "sessions",
    "court_label_en":  "Sessions Court",
    "court_label_hi":  "सत्र न्यायालय",
    "category":        "bail",
    "tier":            1,
    "popularity":      5,
    "quality":         "v1-wrapper",
    "description":     "Regular bail application before Sessions Court (S.483 BNSS / 439 CrPC). Opens the polished bail drafter with FIR-OCR and live preview.",
    "redirect_url":    "/draft/bail?court=sessions&section=439",
    "fields": [],
    "format_spec":     "",  # rendered by /draft/bail
    "example_prompts": [
        "नियमित जमानत आवेदन सत्र न्यायालय में, धारा 420, 406 IPC के लिए",
        "Regular bail at Sessions Court for accused in 376 IPC matter",
    ],
}


# Wrapper — links to the standalone bail page UX for High Court bail.
# Follows the structure of the reference PDF (Rashmi Kanjar / Section 483
# BNSS / 439 CrPC successive bail before MP HC Gwalior Bench):
#   • Index page with annexure list
#   • Front page: parties + prior bail history table + crime details table
#     + criminal record table
#   • Body paragraphs (1-8) with sub-tables for co-accused, cross-case,
#     prior bail history
#   • Brief facts (5.1 - 5.3) and grounds (6.1 - 6.8)
#   • Affidavit page (memo of appearance)
#   • Exemption application (optional, for filing without certified copy)
REGULAR_BAIL_HC = {
    "id":              "regular_bail_hc",
    "name_en":         "Regular Bail (High Court — S.483 BNSS / 439 CrPC)",
    "name_hi":         "नियमित जमानत (उच्च न्यायालय — धारा 483 BNSS / 439 दं.प्र.सं.)",
    "court":           "hc",
    "court_label_en":  "High Court",
    "court_label_hi":  "उच्च न्यायालय",
    "category":        "bail",
    "tier":            1,
    "popularity":      5,
    "quality":         "v1-wrapper",
    "description":     (
        "Regular bail application before High Court (S.483 BNSS / 439 CrPC). "
        "First or successive bail after Sessions Court rejection. Includes "
        "prior bail history, co-accused parity table, FIR-OCR, affidavit, "
        "and exemption-from-certified-copy application."
    ),
    "redirect_url":    "/draft/bail?court=hc&section=439",
    "fields": [],
    "format_spec":     "",  # rendered by /draft/bail with section=439
    "example_prompts": [
        "उच्च न्यायालय में द्वितीय जमानत आवेदन — सत्र न्यायालय से निरस्त, धारा 302/34 IPC",
        "High Court bail under 439 CrPC after Sessions Court rejection in 376 IPC matter",
        "Successive bail at MP HC Gwalior bench after first bail withdrawn",
    ],
}


# Wrapper — links to the standalone bail page UX, anticipatory variant.
ANTICIPATORY_BAIL_SESSIONS = {
    "id":              "anticipatory_bail_sessions",
    "name_en":         "Anticipatory Bail (Sessions Court)",
    "name_hi":         "अग्रिम जमानत (सत्र न्यायालय)",
    "court":           "sessions",
    "court_label_en":  "Sessions Court",
    "court_label_hi":  "सत्र न्यायालय",
    "category":        "bail",
    "tier":            1,
    "popularity":      5,
    "quality":         "v1-wrapper",
    "description":     "Anticipatory bail before Sessions Court (S.482 BNSS / 438 CrPC). Pre-arrest, before FIR turns into custody.",
    "redirect_url":    "/draft/bail?court=sessions&section=438",
    "fields": [],
    "format_spec":     "",
    "example_prompts": [
        "अग्रिम जमानत सत्र न्यायालय में, धारा 420 IPC में FIR दर्ज है",
        "Anticipatory bail at Sessions Court — apprehension of arrest in dowry case",
    ],
}


CRIMINAL_REVISION_SESSIONS = {
    "id":              "criminal_revision_sessions",
    "name_en":         "Criminal Revision (Sessions Court)",
    "name_hi":         "आपराधिक पुनरीक्षण (सत्र न्यायालय)",
    "court":           "sessions",
    "court_label_en":  "Sessions Court",
    "court_label_hi":  "सत्र न्यायालय",
    "category":        "appeal",
    "tier":            2,
    "popularity":      3,
    "quality":         "v1-ai",
    "description":     "Criminal revision under S.438 BNSS / 397 CrPC before Sessions Court — against an order of the Magistrate.",
    "fields": [
        {"key": "court_name",        "label_en": "Sessions Court",                "label_hi": "सत्र न्यायालय",            "type": "text",     "required": True,  "section": "court"},
        {"key": "revisionist_name",  "label_en": "Revisionist (applicant)",       "label_hi": "पुनरीक्षणकर्ता",            "type": "name",     "required": True,  "section": "applicant"},
        {"key": "revisionist_father","label_en": "Father's name",                  "label_hi": "पिता का नाम",              "type": "name",     "required": True,  "section": "applicant"},
        {"key": "revisionist_address","label_en": "Address",                      "label_hi": "पता",                       "type": "address",  "required": True,  "section": "applicant"},
        {"key": "respondent_name",   "label_en": "Non-applicant / Respondent",    "label_hi": "अनावेदक / प्रतिवादी",        "type": "text",     "required": True,  "section": "respondent"},
        {"key": "magistrate_court",  "label_en": "Magistrate court whose order is challenged","label_hi": "विवादित आदेश का न्यायालय","type":"text","required":True,"section": "order"},
        {"key": "impugned_case_no",  "label_en": "Case number below",             "label_hi": "अधीनस्थ न्यायालय का प्रकरण क्र.","type": "text", "required": True, "section": "order"},
        {"key": "impugned_date",     "label_en": "Date of impugned order",        "label_hi": "विवादित आदेश का दिनांक",      "type": "date",     "required": True,  "section": "order"},
        {"key": "impugned_summary",  "label_en": "What the order said",           "label_hi": "आदेश का सारांश",              "type": "longtext", "required": True,  "section": "facts"},
        {"key": "revision_grounds",  "label_en": "Grounds of revision",           "label_hi": "पुनरीक्षण के आधार",           "type": "longtext", "required": True,  "section": "grounds", "hint": "Jurisdictional error / illegality / impropriety"},
        {"key": "advocate_name",     "label_en": "Advocate name",                 "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "place",             "label_en": "Place",                         "label_hi": "स्थान",                        "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                          "label_hi": "दिनांक",                        "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a Criminal Revision Petition under S.438 BNSS / 397 CrPC before Sessions Court. Structure:\n"
        "1. 'IN THE COURT OF SESSIONS JUDGE, <district>' centred + underlined.\n"
        "2. 'Criminal Revision No. ____ of <year>' case block.\n"
        "3. Revisionist block (name, s/o, address).\n"
        "4. 'Versus' centred.\n"
        "5. Respondent block.\n"
        "6. Title: 'PETITION UNDER S.438 BNSS / 397 CrPC FOR REVISION OF ORDER DATED <date> "
        "PASSED BY <magistrate_court>' centred, underlined.\n"
        "7. Numbered paras: (1) brief background; (2) impugned order summary (use <impugned_summary>); "
        "(3) grounds — focus on jurisdictional error, perversity, illegality, propriety (use <revision_grounds>); "
        "(4) why the order causes injustice.\n"
        "8. 'PRAYER': (a) set aside the order dated <date>; (b) pass such fresh order as deemed fit; "
        "(c) costs; (d) other reliefs.\n"
        "9. Verification + signature + place + date.\n"
        "Plain text output."
    ),
    "example_prompts": [
        "Revision against JMFC order rejecting our discharge application",
        "Revision against magistrate's order taking cognizance",
    ],
}


REPLY_TO_BAIL_SESSIONS = {
    "id":              "reply_to_bail_sessions",
    "name_en":         "Reply to Bail (Counter, Sessions)",
    "name_hi":         "जमानत आवेदन पर प्रत्युत्तर (सत्र न्यायालय)",
    "court":           "sessions",
    "court_label_en":  "Sessions Court",
    "court_label_hi":  "सत्र न्यायालय",
    "category":        "bail",
    "tier":            2,
    "popularity":      3,
    "quality":         "v1-ai",
    "description":     "Counter-affidavit by the prosecution / complainant opposing a bail application pending before Sessions Court.",
    "fields": [
        {"key": "court_name",        "label_en": "Court",                          "label_hi": "न्यायालय",                "type": "text",     "required": True,  "section": "court"},
        {"key": "bail_app_no",       "label_en": "Bail application number",        "label_hi": "जमानत आवेदन क्रमांक",       "type": "text",     "required": True,  "section": "court"},
        {"key": "case_title",        "label_en": "Case title",                     "label_hi": "केस शीर्षक",               "type": "text",     "required": True,  "section": "court"},
        {"key": "respondent_name",   "label_en": "Respondent (filing counter)",    "label_hi": "अनावेदक",                  "type": "text",     "required": True,  "section": "respondent"},
        {"key": "accused_name",      "label_en": "Accused (applicant)",            "label_hi": "अभियुक्त (आवेदक)",          "type": "name",     "required": True,  "section": "applicant"},
        {"key": "objections",        "label_en": "Para-wise objections to bail",   "label_hi": "जमानत के विरुद्ध आपत्तियां",  "type": "longtext", "required": True,  "section": "grounds", "hint": "Tampering / flight risk / criminal antecedents / seriousness / witness threat"},
        {"key": "advocate_name",     "label_en": "Advocate / APP name",            "label_hi": "अधिवक्ता / APP का नाम",     "type": "name",     "required": True,  "section": "filing"},
        {"key": "place",             "label_en": "Place",                          "label_hi": "स्थान",                     "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                     "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a Counter / Reply to bail application opposing release of the accused. Structure:\n"
        "1. Court header.\n"
        "2. 'IN <bail_app_no>' block + case title.\n"
        "3. Respondent (State / complainant) submits.\n"
        "4. Title: 'REPLY ON BEHALF OF THE NON-APPLICANT TO THE BAIL APPLICATION OF THE ACCUSED' "
        "centred, underlined.\n"
        "5. Para 1: 'The contents of the bail application are false and misleading and are denied to "
        "the extent they are inconsistent with the version of the prosecution as set out below.'\n"
        "6. Numbered paras 2 onwards — para-wise denial + counter-narrative. Cover (use <objections>): "
        "(a) seriousness of offence; (b) criminal antecedents (list prior FIRs); (c) likelihood of "
        "tampering with evidence / witnesses; (d) flight risk; (e) investigation stage; (f) recoveries "
        "yet to be made.\n"
        "7. 'PRAYER': bail application be dismissed; if granted, stringent conditions including "
        "passport surrender, weekly police station appearance, prohibition on contacting witnesses.\n"
        "8. Verification by IO / complainant. Signature + place + date.\n"
        "Tone: prosecutorial, fact-driven, focuses on the four classical bail-opposing limbs.\n"
        "Plain text output."
    ),
    "example_prompts": [
        "Counter to bail in 376 IPC — accused has 2 prior similar FIRs",
        "Reply opposing bail in NDPS commercial quantity case",
    ],
}


# ============================================================================
# MAGISTRATE COURT / JMFC (9 NEW)
# ============================================================================

# Wrapper — opens the polished bail page UX with JMFC / trial defaults.
TRIAL_BAIL_437 = {
    "id":              "trial_bail_437",
    "name_en":         "Trial Court Bail (S.480 BNSS / 437 CrPC)",
    "name_hi":         "विचारण न्यायालय जमानत (धारा 480 BNSS / 437 दं.प्र.सं.)",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "bail",
    "tier":            1,
    "popularity":      5,
    "quality":         "v1-wrapper",
    "description":     "First-stage bail before the Judicial Magistrate. Use for offences cognisable but bailable, or non-bailable matters where the magistrate has jurisdiction.",
    "redirect_url":    "/draft/bail?court=jmfc&section=437",
    "fields": [],
    "format_spec":     "",
    "example_prompts": [
        "Trial court bail u/s 437 — accused in 379 IPC theft case at PS Murar",
        "जमानत JMFC में, धारा 323, 504 IPC",
    ],
}


COMPLAINT_156_3 = {
    "id":              "complaint_156_3",
    "name_en":         "Complaint for FIR Registration (S.175(3) BNSS / 156(3) CrPC)",
    "name_hi":         "FIR दर्ज कराने हेतु परिवाद (धारा 175(3) BNSS / 156(3) दं.प्र.सं.)",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "procedural",
    "tier":            1,
    "popularity":      4,
    "quality":         "v1-ai",
    "description":     "Complaint to the Magistrate when police refuses to register an FIR. Magistrate can direct PS to register and investigate.",
    "fields": [
        {"key": "court_name",        "label_en": "Court (JMFC / CJM)",             "label_hi": "न्यायालय (न्यायिक मजिस्ट्रेट)","type":"text","required": True, "section": "court"},
        {"key": "complainant_name",  "label_en": "Complainant",                    "label_hi": "परिवादी",                  "type": "name",     "required": True,  "section": "applicant"},
        {"key": "complainant_father","label_en": "Father's name",                  "label_hi": "पिता का नाम",              "type": "name",     "required": True,  "section": "applicant"},
        {"key": "complainant_address","label_en": "Address",                       "label_hi": "पता",                       "type": "address",  "required": True,  "section": "applicant"},
        {"key": "accused_names",     "label_en": "Accused (names + roles)",        "label_hi": "अभियुक्त (नाम + भूमिका)",    "type": "longtext", "required": True,  "section": "respondent"},
        {"key": "police_station",    "label_en": "Police Station concerned",       "label_hi": "संबंधित थाना",               "type": "text",     "required": True,  "section": "facts"},
        {"key": "incident_date",     "label_en": "Date of incident",               "label_hi": "घटना दिनांक",                "type": "date",     "required": True,  "section": "facts"},
        {"key": "incident_place",    "label_en": "Place of incident",              "label_hi": "घटना स्थल",                  "type": "text",     "required": True,  "section": "facts"},
        {"key": "facts_narrative",   "label_en": "Detailed facts of the offence",  "label_hi": "अपराध की विस्तृत तथ्य",      "type": "longtext", "required": True,  "section": "facts"},
        {"key": "sections_invoked",  "label_en": "Sections of law (BNS/IPC)",      "label_hi": "लागू धाराएं",                "type": "text",     "required": True,  "section": "facts"},
        {"key": "police_refusal",    "label_en": "What happened at the PS",        "label_hi": "थाने में क्या हुआ",           "type": "longtext", "required": True,  "section": "grounds", "hint": "Date of approach, refusal to register, written complaint to SP if any"},
        {"key": "witnesses",         "label_en": "Witnesses (name + address)",     "label_hi": "साक्षी (नाम + पता)",          "type": "longtext", "required": False, "section": "facts"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "place",             "label_en": "Place",                          "label_hi": "स्थान",                       "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                       "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a S.175(3) BNSS / 156(3) CrPC complaint to the Magistrate seeking direction to "
        "register an FIR. Structure (Hindi preferred, English if asked):\n"
        "1. 'न्यायिक मजिस्ट्रेट प्रथम श्रेणी, <district>' / 'IN THE COURT OF THE JMFC, <district>' centred.\n"
        "2. 'परिवाद क्रमांक ____ / <वर्ष>' / 'Complaint No. ____ of ____' block.\n"
        "3. परिवादी (complainant) block: name, father, address.\n"
        "4. 'बनाम' / 'Versus' centred.\n"
        "5. अभियुक्तगण (accused) block — all accused with parental/role info.\n"
        "6. Title: 'धारा 175(3) भा.ना.सु.सं. / 156(3) दं.प्र.सं. अन्तर्गत परिवाद - प्रथम सूचना रिपोर्ट दर्ज "
        "कराने हेतु' centred + underlined.\n"
        "7. 'महामहोदय, परिवादी निवेदन करता है कि:' opening line.\n"
        "8. Numbered paras: (1) परिवादी का परिचय; (2) घटना का विस्तृत विवरण — दिनांक, स्थान, समय, अभियुक्तों "
        "की भूमिका; (3) चोट / नुकसान / क्षति; (4) साक्षीगण; (5) लागू धाराएं (use <sections_invoked>); "
        "(6) थाने में जाकर रिपोर्ट दर्ज कराने का प्रयास — पुलिस ने मना किया / FIR दर्ज नहीं की; "
        "(7) SP / DSP को लिखित आवेदन (तारीख); (8) अब तक कोई कार्रवाई नहीं; (9) माननीय न्यायालय से "
        "हस्तक्षेप की अपेक्षा है।\n"
        "9. 'प्रार्थना' (Prayer): (a) थाना <ps> को निर्देश दिया जावे कि लागू धाराओं में FIR दर्ज करे; "
        "(b) विवेचना उच्च अधिकारी से कराई जावे; (c) ऐसी अन्य राहत जो न्यायालय उचित समझे।\n"
        "10. Verification + signature of complainant + advocate + place + date.\n"
        "Tone: factual, chronological, names everything specific. Plain text."
    ),
    "example_prompts": [
        "थाना मुरार ने मेरी FIR दर्ज नहीं की 420, 406 IPC में, अब मजिस्ट्रेट कोर्ट जाना है",
        "Complaint u/s 156(3) — neighbours threatened with deadly weapons, police refused FIR",
    ],
}


PRODUCTION_WARRANT_91 = {
    "id":              "production_warrant_91",
    "name_en":         "Production Warrant (S.94 BNSS / 91 CrPC)",
    "name_hi":         "हाजिर वारंट (धारा 94 BNSS / 91 दं.प्र.सं.)",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "procedural",
    "tier":            1,
    "popularity":      5,
    "quality":         "v1-ai",
    "description":     "Application to bring the accused (lodged in another jail / case) to the present court for proceedings.",
    "fields": [
        {"key": "court_name",        "label_en": "Court",                          "label_hi": "न्यायालय",                  "type": "text",     "required": True,  "section": "court"},
        {"key": "case_no",           "label_en": "Case number",                    "label_hi": "प्रकरण क्रमांक",              "type": "text",     "required": True,  "section": "court"},
        {"key": "accused_name",      "label_en": "Accused name",                   "label_hi": "अभियुक्त का नाम",            "type": "name",     "required": True,  "section": "accused"},
        {"key": "accused_father",    "label_en": "Father's name",                  "label_hi": "पिता का नाम",                "type": "name",     "required": False, "section": "accused"},
        {"key": "currently_at",      "label_en": "Currently lodged at (jail name)","label_hi": "वर्तमान निरोध स्थान (जेल)",   "type": "text",     "required": True,  "section": "matter"},
        {"key": "hearing_date",      "label_en": "Hearing date",                   "label_hi": "सुनवाई दिनांक",               "type": "date",     "required": True,  "section": "matter"},
        {"key": "purpose",           "label_en": "Purpose of production",          "label_hi": "प्रस्तुति का प्रयोजन",         "type": "text",     "required": True,  "section": "matter", "hint": "Recording statement / framing of charge / examination / arguments"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                       "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a short Production Warrant application — procedural, half-page. Structure:\n"
        "1. Court header.\n"
        "2. 'IN <case_no>' block.\n"
        "3. State of <state> Vs <accused_name>.\n"
        "4. Title: 'आवेदन धारा 94 BNSS / 91 दं.प्र.सं. अन्तर्गत' / 'APPLICATION UNDER S.94 BNSS / 91 CrPC' "
        "centred + underlined.\n"
        "5. Two-three short paras: (1) accused is presently lodged at <currently_at> in some other "
        "matter; (2) presence required before this Court on <hearing_date> for <purpose>; (3) request "
        "Court to issue production warrant to Superintendent of <currently_at> directing production.\n"
        "6. 'प्रार्थना' / 'PRAYER': production warrant be issued.\n"
        "7. Signature of advocate + place + date.\n"
        "Tone: short, mechanical, no theatre. Plain text."
    ),
    "example_prompts": [
        "Production warrant — accused Rajesh Singh lodged in Gwalior Central Jail, needed for statement on 12.07",
        "हाजिर वारंट — मेरा मुवक्किल भिंड जेल में बंद है, मुख्य परिवाद में पेशी चाहिए",
    ],
}


PRODUCTION_DOCUMENTS_91_94 = {
    "id":              "production_documents_91_94",
    "name_en":         "Production of Documents (S.94 BNSS / 91 CrPC)",
    "name_hi":         "दस्तावेज़ प्रस्तुति आवेदन (धारा 94 BNSS / 91 दं.प्र.सं.)",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "procedural",
    "tier":            2,
    "popularity":      3,
    "quality":         "v1-ai",
    "description":     "Application seeking court direction to a third party (bank / hospital / company) to produce documents relevant to the case.",
    "fields": [
        {"key": "court_name",        "label_en": "Court",                          "label_hi": "न्यायालय",                "type": "text",     "required": True,  "section": "court"},
        {"key": "case_no",           "label_en": "Case number",                    "label_hi": "प्रकरण क्रमांक",            "type": "text",     "required": True,  "section": "court"},
        {"key": "applicant_name",    "label_en": "Applicant",                      "label_hi": "आवेदक",                    "type": "name",     "required": True,  "section": "applicant"},
        {"key": "custodian",         "label_en": "Custodian of documents",         "label_hi": "दस्तावेज़ धारक",             "type": "text",     "required": True,  "section": "matter", "hint": "Bank / hospital / company / authority"},
        {"key": "custodian_address", "label_en": "Custodian address",              "label_hi": "धारक का पता",              "type": "address",  "required": True,  "section": "matter"},
        {"key": "documents_sought",  "label_en": "Documents needed",               "label_hi": "आवश्यक दस्तावेज़",          "type": "longtext", "required": True,  "section": "matter"},
        {"key": "relevance",         "label_en": "Relevance to the case",          "label_hi": "केस में प्रासंगिकता",        "type": "longtext", "required": True,  "section": "grounds"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",           "type": "name",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                     "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a S.94 BNSS / 91 CrPC application to produce documents. Structure:\n"
        "1. Court header + case number.\n"
        "2. Parties.\n"
        "3. Title: 'APPLICATION UNDER S.94 BNSS / 91 CrPC FOR PRODUCTION OF DOCUMENTS'.\n"
        "4. Numbered paras: (1) case is pending; (2) certain documents in custody of <custodian> at "
        "<custodian_address> are necessary for just decision — list them (use <documents_sought>); "
        "(3) relevance — how each document supports applicant's case (use <relevance>); "
        "(4) custodian unlikely to produce without court order.\n"
        "5. 'PRAYER': direct <custodian> to produce listed documents on next hearing.\n"
        "6. Signature + place + date.\n"
        "Plain text output."
    ),
    "example_prompts": [
        "Application to call bank statements of accused from SBI Murar branch in 420 IPC case",
        "Production of CCTV footage from hotel where alleged offence took place",
    ],
}


EXAMINATION_311 = {
    "id":              "examination_311",
    "name_en":         "Examination of Witness (S.348 BNSS / 311 CrPC)",
    "name_hi":         "साक्षी परीक्षण आवेदन (धारा 348 BNSS / 311 दं.प्र.सं.)",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "procedural",
    "tier":            2,
    "popularity":      3,
    "quality":         "v1-ai",
    "description":     "Application to summon and examine an additional witness (or re-call a previously examined witness) at any stage of inquiry / trial.",
    "fields": [
        {"key": "court_name",        "label_en": "Court",                          "label_hi": "न्यायालय",                "type": "text",     "required": True,  "section": "court"},
        {"key": "case_no",           "label_en": "Case number",                    "label_hi": "प्रकरण क्रमांक",            "type": "text",     "required": True,  "section": "court"},
        {"key": "applicant_role",    "label_en": "Applicant role",                 "label_hi": "आवेदक की भूमिका",          "type": "text",     "required": True,  "section": "applicant", "hint": "Defence / Prosecution / Complainant"},
        {"key": "applicant_name",    "label_en": "Applicant name",                 "label_hi": "आवेदक का नाम",              "type": "name",     "required": True,  "section": "applicant"},
        {"key": "witness_name",      "label_en": "Witness to be examined",         "label_hi": "जिस साक्षी का परीक्षण चाहिए","type": "name",     "required": True,  "section": "matter"},
        {"key": "witness_address",   "label_en": "Witness address",                "label_hi": "साक्षी का पता",              "type": "address",  "required": True,  "section": "matter"},
        {"key": "evidence_summary",  "label_en": "What the witness will depose to","label_hi": "साक्षी क्या साक्ष्य देगा",    "type": "longtext", "required": True,  "section": "matter"},
        {"key": "necessity",         "label_en": "Why necessary now",              "label_hi": "अभी क्यों आवश्यक",            "type": "longtext", "required": True,  "section": "grounds"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                       "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a S.348 BNSS / 311 CrPC application to examine an additional witness. Structure:\n"
        "1. Court header + case number.\n"
        "2. Parties.\n"
        "3. Title: 'APPLICATION UNDER S.348 BNSS / 311 CrPC FOR SUMMONING AND EXAMINATION OF "
        "ADDITIONAL WITNESS' centred + underlined.\n"
        "4. Numbered paras: (1) case stage; (2) the witness <witness_name> r/o <witness_address> "
        "is material to the just decision of the case; (3) what he/she will depose (use "
        "<evidence_summary>); (4) why this evidence is essential and could not be brought earlier "
        "(use <necessity>); (5) the application is not for delay but for a just decision.\n"
        "5. 'PRAYER': summon <witness_name> and permit examination at the cost of applicant.\n"
        "6. Signature + place + date.\n"
        "Plain text output. Cite Mohanlal Shamji Soni v. Union (1991) on need for just decision."
    ),
    "example_prompts": [
        "311 application to call the doctor who examined the victim — missed in original list",
        "Re-call PW-3 for cross — material contradictions discovered",
    ],
}


COMPROMISE_320 = {
    "id":              "compromise_320",
    "name_en":         "Compromise / Rajinama (S.359 BNSS / 320 CrPC)",
    "name_hi":         "राजीनामा (धारा 359 BNSS / 320 दं.प्र.सं.)",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "procedural",
    "tier":            1,
    "popularity":      4,
    "quality":         "v1-ai",
    "description":     "Joint application by complainant and accused to compound the offence and seek closure. Available for compoundable offences listed in S.320 CrPC / S.359 BNSS.",
    "fields": [
        {"key": "court_name",        "label_en": "Court",                          "label_hi": "न्यायालय",                "type": "text",     "required": True,  "section": "court"},
        {"key": "case_no",           "label_en": "Case number",                    "label_hi": "प्रकरण क्रमांक",            "type": "text",     "required": True,  "section": "court"},
        {"key": "complainant_name",  "label_en": "Complainant",                    "label_hi": "परिवादी",                  "type": "name",     "required": True,  "section": "parties"},
        {"key": "accused_name",      "label_en": "Accused",                        "label_hi": "अभियुक्त",                  "type": "name",     "required": True,  "section": "parties"},
        {"key": "sections",          "label_en": "Sections involved",              "label_hi": "लागू धाराएं",                "type": "text",     "required": True,  "section": "parties"},
        {"key": "compromise_summary","label_en": "Terms of compromise",            "label_hi": "राजीनामे की शर्तें",          "type": "longtext", "required": True,  "section": "matter"},
        {"key": "voluntary_decl",    "label_en": "Voluntariness declaration",      "label_hi": "स्वेच्छा की घोषणा",          "type": "longtext", "required": False, "section": "matter", "hint": "Default: 'parties have settled mutually without any coercion or pressure'"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "place",             "label_en": "Place",                          "label_hi": "स्थान",                       "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                       "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a Compromise / Rajinama application under S.359 BNSS / 320 CrPC. Structure:\n"
        "1. Court header + case number.\n"
        "2. Parties — both complainant AND accused are joint applicants.\n"
        "3. Title: 'राजीनामा आवेदन धारा 359 BNSS / 320 दं.प्र.सं. अन्तर्गत' / 'COMPROMISE PETITION "
        "UNDER S.359 BNSS / 320 CrPC' centred + underlined.\n"
        "4. Numbered paras: (1) parties to the case; (2) the offence is compoundable under S.320 (1) "
        "/ S.320 (2) (specify which sub-section); (3) parties have voluntarily settled the matter — "
        "describe terms (use <compromise_summary>); (4) there is no pressure or coercion; "
        "(5) parties wish to bury the dispute.\n"
        "5. 'PRAYER': (a) accept the compromise; (b) acquit / discharge the accused under "
        "S.320 / S.359 BNSS; (c) close the proceedings.\n"
        "6. Signature of BOTH complainant + accused + their advocates.\n"
        "7. Verification by both parties separately.\n"
        "Tone: balanced, dignified. Plain text output."
    ),
    "example_prompts": [
        "Rajinama between Sharma and Verma in 323, 504 IPC — money repaid, dispute settled",
        "Compromise application in 138 NI Act — accused paid the full cheque amount + interest",
    ],
}


DISPENSE_ATTENDANCE_205 = {
    "id":              "dispense_attendance_205",
    "name_en":         "Dispense with Personal Attendance (S.228 BNSS / 205 CrPC)",
    "name_hi":         "व्यक्तिगत उपस्थिति से छूट हेतु आवेदन (धारा 228 BNSS / 205 दं.प्र.सं.)",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "procedural",
    "tier":            2,
    "popularity":      3,
    "quality":         "v1-ai",
    "description":     "Application by an accused (typically in non-serious / summons cases) to be permitted to appear through an advocate instead of in person.",
    "fields": [
        {"key": "court_name",        "label_en": "Court",                          "label_hi": "न्यायालय",                "type": "text",     "required": True,  "section": "court"},
        {"key": "case_no",           "label_en": "Case number",                    "label_hi": "प्रकरण क्रमांक",            "type": "text",     "required": True,  "section": "court"},
        {"key": "accused_name",      "label_en": "Accused name",                   "label_hi": "अभियुक्त का नाम",            "type": "name",     "required": True,  "section": "applicant"},
        {"key": "accused_age",       "label_en": "Age + occupation",               "label_hi": "आयु + व्यवसाय",              "type": "text",     "required": False, "section": "applicant"},
        {"key": "accused_address",   "label_en": "Address",                        "label_hi": "पता",                       "type": "address",  "required": True,  "section": "applicant"},
        {"key": "sections",          "label_en": "Sections (offence type)",       "label_hi": "लागू धाराएं",                "type": "text",     "required": True,  "section": "matter"},
        {"key": "hardship",          "label_en": "Hardship / reason",              "label_hi": "कठिनाई / कारण",              "type": "longtext", "required": True,  "section": "grounds", "hint": "Distance / illness / advanced age / employment requirements"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                       "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a S.228 BNSS / 205 CrPC application to dispense with personal appearance. Structure:\n"
        "1. Court header + case number + parties.\n"
        "2. Title: 'APPLICATION UNDER S.228 BNSS / 205 CrPC FOR EXEMPTION FROM PERSONAL ATTENDANCE'.\n"
        "3. Numbered paras: (1) summons issued; (2) offence is bailable / summons-triable / minor; "
        "(3) accused is willing to be represented by counsel for all proceedings; (4) hardship "
        "(use <hardship> field); (5) accused undertakes to appear when required.\n"
        "4. 'PRAYER': dispense with personal attendance under S.228 BNSS / 205 CrPC.\n"
        "5. Signature + place + date.\n"
        "Plain text output."
    ),
    "example_prompts": [
        "S.205 application — client is 78 years old, lives in Mumbai, case in Gwalior — health issues",
        "Dispense with attendance in NI Act 138 case, accused runs business in Bangalore",
    ],
}


SUPURDGI_451_457 = {
    "id":              "supurdgi_451_457",
    "name_en":         "Property Custody (Supurdgi) (S.497 / 503 BNSS / 451 / 457 CrPC)",
    "name_hi":         "सुपुर्दगी आवेदन (धारा 497/503 BNSS / 451/457 दं.प्र.सं.)",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "procedural",
    "tier":            2,
    "popularity":      4,
    "quality":         "v1-ai",
    "description":     "Application for interim custody (supurdgi) of a vehicle / property seized by police and lying in malkhana, pending disposal of the case.",
    "fields": [
        {"key": "court_name",        "label_en": "Court",                          "label_hi": "न्यायालय",                "type": "text",     "required": True,  "section": "court"},
        {"key": "case_no_or_fir",    "label_en": "Case / FIR number",              "label_hi": "प्रकरण / FIR क्रमांक",       "type": "text",     "required": True,  "section": "court"},
        {"key": "applicant_name",    "label_en": "Applicant (registered owner)",   "label_hi": "आवेदक (पंजीकृत स्वामी)",     "type": "name",     "required": True,  "section": "applicant"},
        {"key": "applicant_address", "label_en": "Address",                        "label_hi": "पता",                       "type": "address",  "required": True,  "section": "applicant"},
        {"key": "property_desc",     "label_en": "Property description",           "label_hi": "संपत्ति का विवरण",            "type": "longtext", "required": True,  "section": "matter", "hint": "Vehicle: make/model/registration; gold: weight; cash: amount"},
        {"key": "ownership_proof",   "label_en": "Ownership proof available",      "label_hi": "स्वामित्व का प्रमाण",         "type": "longtext", "required": True,  "section": "matter", "hint": "RC / sale deed / bank statement"},
        {"key": "seizure_date",      "label_en": "Date of seizure",                "label_hi": "जब्ती दिनांक",                "type": "date",     "required": True,  "section": "matter"},
        {"key": "police_station",    "label_en": "PS where seized",                "label_hi": "जब्त करने वाला थाना",         "type": "text",     "required": True,  "section": "matter"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                       "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a Supurdgi application for interim release of seized property. Structure:\n"
        "1. Court header + case/FIR number.\n"
        "2. Applicant block + address + 'owner' status.\n"
        "3. State of <state> as non-applicant.\n"
        "4. Title: 'सुपुर्दगी आवेदन धारा 497/503 BNSS / 451/457 दं.प्र.सं.' / 'APPLICATION FOR "
        "INTERIM CUSTODY UNDER S.497 / 503 BNSS / 451 / 457 CrPC' centred + underlined.\n"
        "5. Numbered paras: (1) applicant is registered owner of <property_desc>; (2) the property "
        "was seized on <seizure_date> by <police_station> in connection with <case_no_or_fir>; "
        "(3) ownership proofs — RC / sale deed (use <ownership_proof>); (4) prolonged custody in "
        "malkhana causes depreciation / deterioration; (5) Sunderbhai Ambalal Desai v. State of Gujarat "
        "(2002) settles right to interim custody; (6) applicant undertakes to produce property when "
        "directed + not alienate.\n"
        "6. 'PRAYER': release <property_desc> on supurdgi to applicant on furnishing bond + sureties.\n"
        "7. Signature + place + date.\n"
        "Plain text output."
    ),
    "example_prompts": [
        "Supurdgi of motorcycle seized in 379 IPC theft case — I'm the registered owner",
        "Release of seized truck — Rs 15 lakh value, depreciating in police custody for 8 months",
    ],
}


NI_ACT_138 = {
    "id":              "ni_act_138",
    "name_en":         "NI Act §138 — Cheque Bounce Complaint",
    "name_hi":         "चेक बाउंस परिवाद (NI Act 138)",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "commercial",
    "tier":            1,
    "popularity":      5,
    "quality":         "v1-ai",
    "description":     "Criminal complaint under §138 of the Negotiable Instruments Act for dishonour of cheque. Filed in the Magistrate / Commercial Court.",
    "fields": [
        {"key": "court_name",        "label_en": "Court",                          "label_hi": "न्यायालय",                "type": "text",     "required": True,  "section": "court", "hint": "JMFC / Special NI Act court / Commercial court"},
        {"key": "complainant_name",  "label_en": "Complainant",                    "label_hi": "परिवादी",                  "type": "name",     "required": True,  "section": "applicant"},
        {"key": "complainant_father","label_en": "Father / Authorised signatory","label_hi": "पिता / प्राधिकृत हस्ताक्षरकर्ता","type":"name","required": False,"section": "applicant"},
        {"key": "complainant_address","label_en": "Complainant address / business","label_hi": "परिवादी का पता / व्यवसाय",  "type": "address",  "required": True,  "section": "applicant"},
        {"key": "accused_name",      "label_en": "Accused (drawer of cheque)",     "label_hi": "अभियुक्त (चेक देने वाला)",     "type": "name",     "required": True,  "section": "respondent"},
        {"key": "accused_address",   "label_en": "Accused address",                "label_hi": "अभियुक्त का पता",             "type": "address",  "required": True,  "section": "respondent"},
        {"key": "cheque_no",         "label_en": "Cheque number",                  "label_hi": "चेक क्रमांक",                "type": "text",     "required": True,  "section": "cheque"},
        {"key": "cheque_amount",     "label_en": "Cheque amount (₹)",              "label_hi": "चेक राशि (₹)",                "type": "text",     "required": True,  "section": "cheque"},
        {"key": "cheque_date",       "label_en": "Cheque date",                    "label_hi": "चेक दिनांक",                  "type": "date",     "required": True,  "section": "cheque"},
        {"key": "drawee_bank",       "label_en": "Drawee bank + branch",           "label_hi": "जमाकर्ता बैंक + शाखा",         "type": "text",     "required": True,  "section": "cheque"},
        {"key": "deposit_date",      "label_en": "Date deposited for clearance",   "label_hi": "क्लीयरिंग में जमा करने का दिनांक","type": "date", "required": True, "section": "cheque"},
        {"key": "return_date",       "label_en": "Date cheque was returned",       "label_hi": "चेक वापसी दिनांक",             "type": "date",     "required": True,  "section": "cheque"},
        {"key": "return_reason",     "label_en": "Reason for return",              "label_hi": "वापसी का कारण",                "type": "text",     "required": True,  "section": "cheque", "hint": "Insufficient funds / Account closed / Signature mismatch / Payment stopped"},
        {"key": "notice_date",       "label_en": "Date of statutory notice (15 days)","label_hi": "वैधानिक नोटिस का दिनांक",  "type": "date",     "required": True,  "section": "notice"},
        {"key": "notice_delivery",   "label_en": "Notice delivery date",           "label_hi": "नोटिस तामील का दिनांक",        "type": "date",     "required": True,  "section": "notice"},
        {"key": "underlying_debt",   "label_en": "What the cheque was for",        "label_hi": "चेक किस कर्ज़ के लिए था",       "type": "longtext", "required": True,  "section": "facts", "hint": "Loan / goods supplied / services rendered — must be a legally enforceable debt"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "place",             "label_en": "Place",                          "label_hi": "स्थान",                       "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                       "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a S.138 NI Act criminal complaint. Critical: get the timeline right — cheque "
        "presentation within 3 months of date; bank return; notice within 30 days of return; "
        "complaint within 30 days after 15-day notice period expires. Structure:\n"
        "1. Court header — 'IN THE COURT OF JMFC <district>' OR Special NI Act court if applicable.\n"
        "2. Case block: 'Complaint Case No. ____ of <year>' / 'परिवाद क्रमांक ____'.\n"
        "3. Complainant block: name / business / authorised signatory; address.\n"
        "4. 'Versus' centred.\n"
        "5. Accused block: name + address.\n"
        "6. Title: 'COMPLAINT UNDER SECTION 138 READ WITH SECTION 142 OF THE NEGOTIABLE INSTRUMENTS "
        "ACT, 1881' centred + underlined + bold.\n"
        "7. 'The above-named complainant most respectfully submits as follows:'\n"
        "8. Numbered paras:\n"
        "   (1) Complainant is engaged in <business> at <address>.\n"
        "   (2) Accused is well-known to the complainant and resides at <accused_address>.\n"
        "   (3) The accused was liable to pay the complainant <cheque_amount> being <underlying_debt> "
        "       — a legally enforceable debt/liability.\n"
        "   (4) Towards discharge of the said liability, the accused issued cheque no. <cheque_no> "
        "       dated <cheque_date> for <cheque_amount> drawn on <drawee_bank>.\n"
        "   (5) Complainant presented the said cheque for collection on <deposit_date> through "
        "       <his/her> banker.\n"
        "   (6) The cheque was returned unpaid on <return_date> with the endorsement <return_reason>. "
        "       The return memo is filed as Annex A-1.\n"
        "   (7) Complainant issued a statutory legal notice dated <notice_date> to the accused calling "
        "       upon him to pay the cheque amount within 15 days. Notice delivered on <notice_delivery>. "
        "       Notice + postal proof at Annex A-2.\n"
        "   (8) Despite receipt, the accused failed and neglected to make payment within 15 days.\n"
        "   (9) The accused has thereby committed an offence punishable under S.138 NI Act.\n"
        "   (10) Cause of action arose on the expiry of 15 days from the notice date i.e. <date>; "
        "       this complaint is filed within 30 days thereof, hence within limitation under S.142.\n"
        "9. 'LIST OF DOCUMENTS': original cheque, return memo, statutory notice, postal proof, "
        "   ledger / invoice / loan note evidencing the underlying liability.\n"
        "10. 'LIST OF WITNESSES': complainant, banker (if needed).\n"
        "11. 'PRAYER': (a) take cognizance under S.138 NI Act read with S.142; (b) summon the accused "
        "    and try him in accordance with law; (c) on conviction, sentence him to imprisonment up "
        "    to 2 years and / or fine up to twice the cheque amount; (d) award compensation under "
        "    S.357 CrPC / S.395 BNSS to make good the cheque amount with interest.\n"
        "12. Verification: 'I, <complainant>, do hereby verify that the contents of this complaint "
        "    are true to my personal knowledge.' + signature + place + date.\n"
        "13. Below: 'Through Advocate: <advocate_name>, <enrolment_no>'.\n"
        "Tone: methodical, dates and amounts precise — judges throw out complaints with timeline "
        "errors. Plain text output."
    ),
    "example_prompts": [
        "Cheque bounce — Rs 5 lakh cheque from Mukesh Sharma, returned 'insufficient funds' on 12.03.2026",
        "138 NI Act complaint — wholesale dealer's cheque bounced, notice already sent",
    ],
}


# ============================================================================
# FAMILY COURT (3 NEW)
# ============================================================================

DV_ACT_12 = {
    "id":              "dv_act_12",
    "name_en":         "Domestic Violence Act §12 Application",
    "name_hi":         "घरेलू हिंसा अधिनियम धारा 12 आवेदन",
    "court":           "family",
    "court_label_en":  "Family Court",
    "court_label_hi":  "परिवार न्यायालय",
    "category":        "family",
    "tier":            1,
    "popularity":      5,
    "quality":         "v1-ai",
    "description":     "Application under §12 of the Protection of Women from Domestic Violence Act, 2005 — seeking protection / residence / monetary / custody / compensation orders.",
    "fields": [
        {"key": "court_name",        "label_en": "Court (JMFC / Family)",          "label_hi": "न्यायालय",                "type": "text",     "required": True,  "section": "court"},
        {"key": "aggrieved_name",    "label_en": "Aggrieved person (woman)",       "label_hi": "पीड़िता",                  "type": "name",     "required": True,  "section": "applicant"},
        {"key": "aggrieved_father",  "label_en": "Father's name",                  "label_hi": "पिता का नाम",              "type": "name",     "required": True,  "section": "applicant"},
        {"key": "aggrieved_age",     "label_en": "Age",                            "label_hi": "आयु",                      "type": "text",     "required": False, "section": "applicant"},
        {"key": "aggrieved_address", "label_en": "Current address",                "label_hi": "वर्तमान पता",                "type": "address",  "required": True,  "section": "applicant"},
        {"key": "respondent_name",   "label_en": "Respondent (husband / in-laws)", "label_hi": "अनावेदक",                  "type": "name",     "required": True,  "section": "respondent"},
        {"key": "respondent_relation","label_en": "Relationship with aggrieved",   "label_hi": "पीड़िता से संबंध",          "type": "text",     "required": True,  "section": "respondent"},
        {"key": "respondent_address","label_en": "Respondent address",             "label_hi": "अनावेदक का पता",            "type": "address",  "required": True,  "section": "respondent"},
        {"key": "marriage_date",     "label_en": "Marriage date",                  "label_hi": "विवाह दिनांक",               "type": "date",     "required": False, "section": "marriage"},
        {"key": "violence_narrative","label_en": "Acts of domestic violence",      "label_hi": "घरेलू हिंसा का विवरण",        "type": "longtext", "required": True,  "section": "facts", "hint": "Specific incidents — dates, places, what was done"},
        {"key": "shelter_status",    "label_en": "Where is aggrieved staying now", "label_hi": "वर्तमान आश्रय",              "type": "longtext", "required": True,  "section": "facts"},
        {"key": "income_husband",    "label_en": "Husband's income / employment", "label_hi": "पति की आय / व्यवसाय",        "type": "text",     "required": False, "section": "income"},
        {"key": "reliefs_sought",    "label_en": "Reliefs needed",                 "label_hi": "चाहित राहत",                 "type": "longtext", "required": True,  "section": "prayer", "hint": "Protection / Residence / Monetary (₹) / Custody / Compensation — list all"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "place",             "label_en": "Place",                          "label_hi": "स्थान",                       "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                       "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a S.12 PWDVA application — typically filed by the woman through a Protection Officer "
        "or directly. Structure:\n"
        "1. Court header — 'IN THE COURT OF JMFC, <district>' or 'FAMILY COURT, <district>' centred + underlined.\n"
        "2. Case block: 'Application No. ____ of <year>' / 'D.V. क्रमांक ____'.\n"
        "3. Aggrieved person (आवेदिका) block: name, father's name, age, present address.\n"
        "4. 'Versus' centred.\n"
        "5. Respondent block: name, relation (husband / father-in-law / etc), address.\n"
        "6. Title: 'APPLICATION UNDER SECTION 12 OF THE PROTECTION OF WOMEN FROM DOMESTIC VIOLENCE "
        "ACT, 2005' centred + underlined.\n"
        "7. 'The applicant, an aggrieved person within the meaning of S.2(a) of the said Act, most "
        "respectfully submits as follows:'\n"
        "8. Numbered paras:\n"
        "   (1) Applicant's identity + father's name + age + present address.\n"
        "   (2) Respondent's identity + relationship + address.\n"
        "   (3) Marriage / domestic relationship — date, place, manner.\n"
        "   (4) The shared household — where the applicant lived with respondent.\n"
        "   (5) Acts of domestic violence — dated, specific, narrated chronologically (use <violence_narrative>). "
        "       Include physical, sexual, verbal, emotional, economic abuse as applicable per S.3 of the Act.\n"
        "   (6) Current circumstances — shelter status, financial position, dependent children if any.\n"
        "   (7) Respondent's means — income, property, employment.\n"
        "   (8) Reliefs sought — must specify which reliefs under which section (S.18 protection, "
        "       S.19 residence, S.20 monetary, S.21 custody, S.22 compensation).\n"
        "9. 'PRAYER': itemised list of reliefs (use <reliefs_sought>):\n"
        "   (a) Protection order under S.18 — restrain respondent from committing acts of DV;\n"
        "   (b) Residence order under S.19 — secure shared household OR alternate accommodation;\n"
        "   (c) Monetary relief under S.20 — ₹___/month for applicant + ₹___/month per child;\n"
        "   (d) Custody under S.21 of minor child(ren) — if applicable;\n"
        "   (e) Compensation under S.22 — ₹___ for injuries / mental agony;\n"
        "   (f) Such other reliefs.\n"
        "10. Verification + applicant signature + advocate signature + place + date.\n"
        "Tone: dignified, narrative — DV applications are factual life-stories. Avoid emotional "
        "language but be specific about every incident. Hindi mode uses standard family-court "
        "vocabulary: आवेदिका, अनावेदक, संरक्षण आदेश, निवास आदेश, आर्थिक राहत, संरक्षण, क्षतिपूर्ति. Plain text."
    ),
    "example_prompts": [
        "DV application for my client — husband + in-laws assaulting and demanding dowry, she's been thrown out",
        "घरेलू हिंसा आवेदन — पति ने मारपीट की, गहने छीने, घर से निकाला",
    ],
}


HMA_9_RESTITUTION = {
    "id":              "hma_9_restitution",
    "name_en":         "Restitution of Conjugal Rights (HMA §9)",
    "name_hi":         "वैवाहिक अधिकारों की पुनर्स्थापना याचिका (HMA धारा 9)",
    "court":           "family",
    "court_label_en":  "Family Court",
    "court_label_hi":  "परिवार न्यायालय",
    "category":        "family",
    "tier":            2,
    "popularity":      2,
    "quality":         "v1-ai",
    "description":     "Petition under §9 of the Hindu Marriage Act seeking the spouse's return to the matrimonial home.",
    "fields": [
        {"key": "court_name",        "label_en": "Family Court",                   "label_hi": "परिवार न्यायालय",          "type": "text",     "required": True,  "section": "court"},
        {"key": "petitioner_name",   "label_en": "Petitioner",                     "label_hi": "याचिकाकर्ता",              "type": "name",     "required": True,  "section": "applicant"},
        {"key": "respondent_name",   "label_en": "Respondent spouse",              "label_hi": "अनावेदक/अनावेदिका",         "type": "name",     "required": True,  "section": "respondent"},
        {"key": "marriage_date",     "label_en": "Marriage date",                  "label_hi": "विवाह दिनांक",               "type": "date",     "required": True,  "section": "marriage"},
        {"key": "marriage_place",    "label_en": "Marriage place",                 "label_hi": "विवाह स्थल",                 "type": "text",     "required": True,  "section": "marriage"},
        {"key": "separation_date",   "label_en": "Date of separation",             "label_hi": "अलगाव दिनांक",               "type": "date",     "required": True,  "section": "facts"},
        {"key": "facts_narrative",   "label_en": "Reasons for separation",         "label_hi": "अलगाव के कारण",              "type": "longtext", "required": True,  "section": "facts"},
        {"key": "reconciliation_efforts","label_en": "Efforts at reconciliation",  "label_hi": "मेल-मिलाप के प्रयास",         "type": "longtext", "required": False, "section": "facts"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                       "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a HMA S.9 petition for restitution. Structure:\n"
        "1. 'IN THE FAMILY COURT, <district>' header.\n"
        "2. 'H.M.A. Petition No. ____ of <year>' case block.\n"
        "3. Petitioner / Respondent blocks.\n"
        "4. Title: 'PETITION UNDER S.9 OF THE HINDU MARRIAGE ACT, 1955 FOR RESTITUTION OF "
        "CONJUGAL RIGHTS' centred + underlined.\n"
        "5. Numbered paras: (1) parties are Hindu, married under Hindu rites on <date> at <place>; "
        "(2) they lived together from <date> to <date>; (3) respondent left the matrimonial home on "
        "<separation_date>; (4) reasons for separation as per petitioner (use <facts_narrative>); "
        "(5) efforts at reconciliation; (6) petitioner is willing and able to receive and maintain "
        "respondent.\n"
        "6. 'PRAYER': order respondent to return to the matrimonial home and resume conjugal life.\n"
        "7. Verification + signature + date.\n"
        "Tone: civil, dignified. Plain text output."
    ),
    "example_prompts": [
        "S.9 HMA — wife left for her parents' house 6 months ago, refusing to return",
        "Restitution petition for husband whose wife left without cause after 2 years of marriage",
    ],
}


HMA_13_DIVORCE = {
    "id":              "hma_13_divorce",
    "name_en":         "Divorce Petition (HMA §13(A) / §13(B))",
    "name_hi":         "तलाक की याचिका (HMA धारा 13(A) / 13(B))",
    "court":           "family",
    "court_label_en":  "Family Court",
    "court_label_hi":  "परिवार न्यायालय",
    "category":        "family",
    "tier":            2,
    "popularity":      3,
    "quality":         "v1-ai",
    "description":     "Petition under §13 of the Hindu Marriage Act for dissolution of marriage. §13(A) — contested grounds; §13(B) — mutual consent (joint petition).",
    "fields": [
        {"key": "court_name",        "label_en": "Family Court",                   "label_hi": "परिवार न्यायालय",          "type": "text",     "required": True,  "section": "court"},
        {"key": "petition_type",     "label_en": "Type of petition",               "label_hi": "याचिका का प्रकार",          "type": "text",     "required": True,  "section": "court", "hint": "Contested (S.13(A)) / Mutual consent (S.13(B))"},
        {"key": "petitioner_name",   "label_en": "Petitioner",                     "label_hi": "याचिकाकर्ता/याचिकाकर्ती",     "type": "name",     "required": True,  "section": "applicant"},
        {"key": "respondent_name",   "label_en": "Respondent",                     "label_hi": "अनावेदक/अनावेदिका",         "type": "name",     "required": True,  "section": "respondent"},
        {"key": "marriage_date",     "label_en": "Marriage date",                  "label_hi": "विवाह दिनांक",               "type": "date",     "required": True,  "section": "marriage"},
        {"key": "marriage_place",    "label_en": "Marriage place",                 "label_hi": "विवाह स्थल",                 "type": "text",     "required": True,  "section": "marriage"},
        {"key": "separation_date",   "label_en": "Date of separation",             "label_hi": "अलगाव दिनांक",               "type": "date",     "required": True,  "section": "facts"},
        {"key": "grounds",           "label_en": "Grounds for divorce",            "label_hi": "तलाक के आधार",              "type": "longtext", "required": True,  "section": "grounds", "hint": "Cruelty / Adultery / Desertion / Conversion / Mental disorder — or 'irretrievable breakdown' for mutual consent"},
        {"key": "children",          "label_en": "Children (names + ages)",        "label_hi": "संतान (नाम + आयु)",          "type": "longtext", "required": False, "section": "marriage"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                       "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a HMA S.13 divorce petition. Two flavours based on <petition_type>:\n"
        "A) S.13(A) — contested by one spouse against the other on a ground.\n"
        "B) S.13(B) — JOINT petition by both spouses on mutual consent (must have lived apart ≥ 1 year).\n\n"
        "Structure (common):\n"
        "1. 'IN THE FAMILY COURT, <district>' header.\n"
        "2. 'H.M.A. Petition No. ____ of <year>' case block.\n"
        "3. Parties block — for S.13(B) both are joint petitioners.\n"
        "4. Title: 'PETITION UNDER S.13(A) FOR DISSOLUTION OF MARRIAGE' / 'JOINT PETITION UNDER "
        "S.13(B) FOR DISSOLUTION OF MARRIAGE BY MUTUAL CONSENT' centred + underlined.\n"
        "5. Numbered paras:\n"
        "   (1) Both parties are Hindu, marriage on <marriage_date> at <marriage_place> per Hindu rites.\n"
        "   (2) Lived together / where & when.\n"
        "   (3) Children (use <children> field).\n"
        "   (4) Separation: parties separated on <separation_date>, have lived apart since.\n"
        "   (5) Grounds (use <grounds>). For 13(A): cite specific cruelty / adultery / desertion "
        "       incidents with dates. For 13(B): state mutual consent + irretrievable breakdown + "
        "       statutory 1-year separation requirement met.\n"
        "   (6) Settlement of issues — maintenance, custody, alimony (in 13(B), give settlement).\n"
        "6. 'PRAYER': decree of divorce dissolving the marriage; ancillary reliefs (custody, alimony).\n"
        "7. Verification by both parties (for 13(B)) or by petitioner (for 13(A)) + signatures + date.\n"
        "Tone: civil, careful. For mutual consent, emphasise voluntariness. Plain text output."
    ),
    "example_prompts": [
        "Mutual consent divorce — both spouses agree, separated 14 months, no children",
        "Contested divorce on cruelty grounds — wife filing against husband, dowry harassment",
    ],
}


# ============================================================================
# PROCEDURAL — cross-court (1 NEW; vakalatnama + mention_memo in v1 file)
# ============================================================================

GENERAL_AFFIDAVIT = {
    "id":              "general_affidavit",
    "name_en":         "General Affidavit",
    "name_hi":         "शपथ पत्र (सामान्य)",
    "court":           "procedural",
    "court_label_en":  "Common",
    "court_label_hi":  "सामान्य",
    "category":        "procedural",
    "tier":            1,
    "popularity":      5,
    "quality":         "v1-ai",
    "description":     "General-purpose sworn affidavit usable for any court or authority. Substitutable subject (identity / residence / no-criminal-record / supporting a petition / etc.).",
    "fields": [
        {"key": "court_or_authority","label_en": "Court / Authority",               "label_hi": "न्यायालय / प्राधिकारी",     "type": "text",     "required": True,  "section": "court", "hint": "e.g. 'JMFC Gwalior' or 'SDM Bhopal'"},
        {"key": "deponent_name",     "label_en": "Deponent (you / your client)",   "label_hi": "शपथकर्ता",                 "type": "name",     "required": True,  "section": "applicant"},
        {"key": "deponent_father",   "label_en": "Father's / Husband's name",      "label_hi": "पिता / पति का नाम",        "type": "name",     "required": True,  "section": "applicant"},
        {"key": "deponent_age",      "label_en": "Age",                            "label_hi": "आयु",                       "type": "text",     "required": True,  "section": "applicant"},
        {"key": "deponent_occupation","label_en": "Occupation",                    "label_hi": "व्यवसाय",                   "type": "text",     "required": False, "section": "applicant"},
        {"key": "deponent_address",  "label_en": "Address",                        "label_hi": "पता",                       "type": "address",  "required": True,  "section": "applicant"},
        {"key": "subject",           "label_en": "Subject of affidavit",           "label_hi": "विषय",                     "type": "text",     "required": True,  "section": "matter", "hint": "What you are swearing to"},
        {"key": "declarations",      "label_en": "Numbered declarations",          "label_hi": "क्रमबद्ध कथन",              "type": "longtext", "required": True,  "section": "matter", "hint": "Each fact you swear is true, on a new line"},
        {"key": "place",             "label_en": "Place",                          "label_hi": "स्थान",                     "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                     "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a generic affidavit — usable for any court / SDM / collector / passport / employer "
        "/ bank. Structure:\n"
        "1. Top right corner: '(On Non-Judicial Stamp Paper of appropriate value)' / "
        "'(उपयुक्त मूल्य के गैर-न्यायिक स्टांप पेपर पर)'.\n"
        "2. 'BEFORE <court_or_authority>' / 'समक्ष <court_or_authority>' centred.\n"
        "3. Title: 'AFFIDAVIT' / 'शपथ पत्र' centred + underlined + bold.\n"
        "4. Re: line — subject of the affidavit.\n"
        "5. Opening: 'I, <deponent_name>, S/o / W/o <deponent_father>, aged about <age> years, "
        "by occupation <occupation>, resident of <deponent_address>, do hereby solemnly affirm and "
        "declare on oath as under:' / 'मैं, <deponent_name>, पुत्र/पत्नी श्री <deponent_father>, उम्र "
        "लगभग <age> वर्ष, व्यवसाय <occupation>, निवासी <deponent_address>, शपथपूर्वक सत्य कथन करता/करती "
        "हूँ कि:'.\n"
        "6. Numbered declarations (use <declarations> field) — each para 1-3 sentences, factual.\n"
        "7. 'VERIFICATION': 'I, the deponent above-named, do hereby verify that the contents of "
        "paragraphs 1 to <N> of this affidavit are true to my personal knowledge, that no part of "
        "it is false, and nothing material has been concealed therefrom.' / 'मैं, उपरोक्त नामित "
        "शपथकर्ता, सत्यापित करता/करती हूँ कि इस शपथ पत्र की कंडिका 1 से <N> तक की सभी बातें मेरी "
        "व्यक्तिगत जानकारी से सत्य हैं, इसका कोई भी अंश असत्य नहीं है और कोई भी महत्वपूर्ण बात छिपाई "
        "नहीं गई है।'\n"
        "8. Signature line for deponent + place + date.\n"
        "9. Notary attestation block at the bottom: 'सत्यापित — Notary, <place>'.\n"
        "Tone: formal, sworn-statement style. Plain text output."
    ),
    "example_prompts": [
        "Affidavit declaring no-criminal-record for passport renewal",
        "Identity affidavit for opening minor bank account — guardian's declaration",
    ],
}


# ============================================================================
# REFERENCE-GRADE (v2-ref) — structures decoded verbatim from real filings
# (advocate's actual .docx drafts). These three close the biggest catalogue
# gaps: Notice (~89 filings), Private Complaint (~48), Reply/Jawab (~40).
# ============================================================================

# ── 1. LEGAL NOTICE (सूचना पत्र) — pre-litigation demand notice ───────────────
# Sent by the advocate on the client's instructions, by Registered A.D., before
# any suit. Covers §138 NI Act cheque-demand, HMA §9 restitution demand, money
# recovery, and general legal/demand notices. Cross-court → "procedural" rail.
LEGAL_NOTICE = {
    "id":              "legal_notice",
    "name_en":         "Legal Notice (Demand Notice)",
    "name_hi":         "सूचना पत्र (विधिक नोटिस)",
    "court":           "procedural",
    "court_label_en":  "Common",
    "court_label_hi":  "सामान्य",
    "category":        "procedural",
    "tier":            1,
    "popularity":      5,
    "quality":         "v2-ref",
    "description":     "Pre-litigation demand notice sent by the advocate, by Registered A.D., on the client's instructions — §138 cheque-bounce demand, HMA §9 restitution, recovery of money, or any general legal demand. Gives the addressee 15 days to comply before suit.",
    "fields": [
        {"key": "advocate_name",     "label_en": "Sending advocate's name",        "label_hi": "प्रेषक अधिवक्ता का नाम",    "type": "name",     "required": True,  "section": "letterhead"},
        {"key": "advocate_address",  "label_en": "Advocate office / residence",    "label_hi": "अधिवक्ता कार्यालय / निवास",  "type": "address",  "required": True,  "section": "letterhead"},
        {"key": "advocate_court",    "label_en": "Practising court line",          "label_hi": "न्यायालय पंक्ति",            "type": "text",     "required": False, "section": "letterhead", "hint": "e.g. उच्च न्यायालय खण्डपीठ ग्वालियर म.प्र."},
        {"key": "advocate_mobile",   "label_en": "Advocate mobile",                "label_hi": "अधिवक्ता मोबाइल",            "type": "text",     "required": False, "section": "letterhead"},
        {"key": "notice_type",       "label_en": "Type of notice",                 "label_hi": "नोटिस का प्रकार",            "type": "text",     "required": True,  "section": "facts", "hint": "138 cheque bounce / HMA §9 restitution / money recovery / general demand"},
        {"key": "noticee_name",      "label_en": "Noticee (addressee)",            "label_hi": "नोटिसी (बनाम)",             "type": "name",     "required": True,  "section": "respondent"},
        {"key": "noticee_details",   "label_en": "Noticee parentage / age / residence", "label_hi": "नोटिसी पिता / आयु / निवास", "type": "longtext", "required": True, "section": "respondent"},
        {"key": "client_name",       "label_en": "Client (पक्षकार)",               "label_hi": "पक्षकार का नाम",             "type": "name",     "required": True,  "section": "applicant"},
        {"key": "client_details",    "label_en": "Client parentage / age / occupation / residence", "label_hi": "पक्षकार पिता / आयु / व्यवसाय / निवास", "type": "longtext", "required": True, "section": "applicant"},
        {"key": "facts_narrative",   "label_en": "What happened (the grievance)",  "label_hi": "क्या हुआ (शिकायत का आधार)",   "type": "longtext", "required": True,  "section": "facts", "hint": "For 138: loan amount, date, cheque no., bank, deposit & return dates, return reason. For HMA-9: marriage date, desertion, what is demanded back."},
        {"key": "demand",            "label_en": "What is demanded",               "label_hi": "क्या माँगा जा रहा है",        "type": "longtext", "required": True,  "section": "prayer", "hint": "Pay ₹X / return wife & jewellery / restore possession etc."},
        {"key": "compliance_days",   "label_en": "Days to comply",                 "label_hi": "पालन हेतु दिवस",             "type": "text",     "required": False, "section": "prayer", "hint": "Default 15"},
        {"key": "notice_cost",       "label_en": "Notice cost (₹, optional)",      "label_hi": "नोटिस व्यय (₹, वैकल्पिक)",   "type": "text",     "required": False, "section": "prayer"},
        {"key": "copy_to",           "label_en": "Copies marked to (नोट)",         "label_hi": "प्रतिलिपि (नोट)",            "type": "longtext", "required": False, "section": "filing", "hint": "e.g. महिला थाना / SP — for matrimonial notices"},
        {"key": "notice_date",       "label_en": "Date of notice",                 "label_hi": "नोटिस दिनांक",               "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a Hindi सूचना पत्र (legal demand notice) in the exact letter format Indian advocates "
        "use. Output Hindi (Devanagari) by default; add an English mirror only if the user asks. "
        "Plain text, no markdown. Structure — follow precisely:\n"
        "1. LETTERHEAD (top): advocate name on the left with 'एडवोकेट' beneath it; on the right the "
        "office/residence address (<advocate_address>); a line for the practising court "
        "(<advocate_court>, e.g. 'उच्च न्यायालय खण्डपीठ ग्वालियर म.प्र.'); and 'मोबा- <advocate_mobile>'. "
        "Then a full-width separator line of dashes '-----------------------------------------------------'.\n"
        "2. TITLE (centred): '// सूचना पत्र मय रजिस्टर्ड ए.डी. //'.\n"
        "3. ADDRESSEE: 'बनाम:- <noticee_name> <noticee_details>' (parentage, age, full residence).\n"
        "4. OPENING: 'मैं अपने पक्षकार <client_name> <client_details> द्वारा दी गई जानकारी एवं उनके "
        "निर्देशानुसार आप नोटिसी को निम्न आशय का सूचना पत्र प्रेषित कर रहा हूँ :-'.\n"
        "5. BODY — numbered fact paragraphs, EACH beginning 'यह कि' — build the cause from "
        "<facts_narrative> in chronological order. For a §138 cheque notice the chain MUST be: "
        "(a) relationship / liability; (b) loan or debt amount & date; (c) accused issued cheque no. ___ "
        "dated ___ for ₹___ drawn on <bank>; (d) cheque presented on ___; (e) returned unpaid on ___ "
        "with memo 'अपर्याप्त निधि' (insufficient funds) via the client's bank; (f) 'इस प्रकार से आप "
        "नोटिसी का उक्त कृत्य धारा 138 परक्राम्य लिखत अधिनियम के तहत दण्डनीय अपराध की श्रेणी में आता है।' "
        "For an HMA §9 / matrimonial notice: marriage facts, cohabitation, desertion/cause, demand to "
        "return and resume cohabitation.\n"
        "6. DEMAND PARAGRAPH (begins 'अत:'): 'अत: ज़रिये सूचना पत्र आप नोटिसी को सूचित किया जाता है कि "
        "आप सूचना पत्र प्राप्ति के <compliance_days, default 15> दिवस के अन्दर मेरे पक्षकार को <demand> "
        "[for 138 add: व ₹<notice_cost> नोटिस व्यय पृथक से] अदा कर / पूर्ण कर रसीद प्राप्त करें अन्यथा "
        "वाद गुजरने मियाद आप नोटिसी के विरुद्ध सक्षम न्यायालय में वैधानिक कार्यवाही करने के लिए विवश होना "
        "पड़ेगा जिसमें होने वाले समस्त हर्जे-खर्चे के लिए आप नोटिसी स्वयं उत्तरदायी होंगे। सूचित हों।'\n"
        "7. CLOSING: left 'दिनांक:- <notice_date>'; right (signature block) 'प्रेषक' then advocate "
        "name and 'एडवोकेट'.\n"
        "8. If <copy_to> given, append 'नोट :-' footnote listing the offices a copy is endorsed to.\n"
        "Tone: firm, formal, single-letter (NOT a court petition — no court header, no 'माननीय "
        "न्यायालय'). Numbers, dates, cheque & bank details must be exact."
    ),
    "example_prompts": [
        "138 नोटिस — संजीव शिवहरे का ₹14 लाख का चेक बाउंस हुआ, अपर्याप्त निधि",
        "HMA धारा 9 नोटिस — पत्नी की वापसी व जेवरात की माँग",
        "Money-recovery notice — friend took ₹2 lakh hand-loan, refusing to repay",
    ],
}


# ── 2. PRIVATE COMPLAINT (परिवाद पत्र — §223 BNSS / 200 CrPC, direct) ─────────
# The DIRECT route: Magistrate takes cognizance, records the complainant's
# statement (§200 CrPC / §223 BNSS) and issues process (§204 / §227). Distinct
# from complaint_156_3 (which only asks the Magistrate to DIRECT the police to
# register an FIR). Used where 156(3) is unavailable — e.g. accused are the
# police themselves — or the complainant wishes to lead evidence directly.
PRIVATE_COMPLAINT_200 = {
    "id":              "private_complaint_200",
    "name_en":         "Private Complaint — Direct (S.223 BNSS / 200 CrPC)",
    "name_hi":         "परिवाद पत्र — प्रत्यक्ष (धारा 223 BNSS / 200 दं.प्र.सं.)",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "procedural",
    "tier":            1,
    "popularity":      4,
    "quality":         "v2-ref",
    "description":     "Direct private complaint where the Magistrate takes cognizance, records the complainant's statement (S.200 CrPC / S.223 BNSS) and summons the accused — used when 156(3) won't work (e.g. accused are police) or the complainant will lead evidence. Carries a sworn affidavit (शपथपत्र).",
    "fields": [
        {"key": "court_name",        "label_en": "Court (JMFC / CJM + place)",     "label_hi": "न्यायालय (न्यायिक मजिस्ट्रेट + स्थान)", "type": "text", "required": True, "section": "court", "hint": "e.g. न्यायिक दण्डाधिकारी प्रथम श्रेणी, ग्वालियर"},
        {"key": "complainant_name",  "label_en": "Complainant (परिवादी)",          "label_hi": "परिवादी का नाम",            "type": "name",     "required": True,  "section": "applicant"},
        {"key": "complainant_father","label_en": "Father's name",                  "label_hi": "पिता का नाम",               "type": "name",     "required": True,  "section": "applicant"},
        {"key": "complainant_address","label_en": "Complainant address + age",     "label_hi": "परिवादी का पता + आयु",       "type": "address",  "required": True,  "section": "applicant"},
        {"key": "accused_names",     "label_en": "Accused (names, roles, address)", "label_hi": "आरोपीगण (नाम, भूमिका, पता)", "type": "longtext", "required": True,  "section": "respondent", "hint": "One per line; include 'नामालूम' if parentage unknown"},
        {"key": "offence_sections",  "label_en": "Offence sections (BNS / IPC)",   "label_hi": "अपराध की धाराएं (BNS/IPC)",  "type": "text",     "required": True,  "section": "facts", "hint": "Substantive offences, e.g. 342, 327, 323, 324, 504, 506बी, 34 भा.द.वि."},
        {"key": "incident_date",     "label_en": "Date of incident",               "label_hi": "घटना दिनांक",                "type": "date",     "required": True,  "section": "facts"},
        {"key": "incident_place",    "label_en": "Place / police-station area",    "label_hi": "घटना स्थल / थाना क्षेत्र",   "type": "text",     "required": True,  "section": "facts"},
        {"key": "facts_narrative",   "label_en": "Detailed facts (the full story)","label_hi": "विस्तृत तथ्य (पूरी घटना)",    "type": "longtext", "required": True,  "section": "facts"},
        {"key": "police_approach",   "label_en": "Approach to police / authorities","label_hi": "पुलिस / अधिकारियों से संपर्क", "type": "longtext", "required": False, "section": "grounds", "hint": "Dates of complaints to PS, SP, SDOP, CM cell, Human Rights Commission and their inaction"},
        {"key": "witnesses",         "label_en": "Witnesses (name + address)",     "label_hi": "साक्षीगण (नाम + पता)",        "type": "longtext", "required": False, "section": "facts"},
        {"key": "relief_compensation","label_en": "Compensation / relief sought",  "label_hi": "प्रतिकर / अनुतोष",           "type": "longtext", "required": False, "section": "prayer"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                      "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a Hindi परिवाद पत्र (direct private complaint) in the exact court format. Output "
        "Hindi (Devanagari); add English only if asked. Plain text, no markdown. Map IPC sections to "
        "their BNS equivalents if the user gives BNS. Procedural section: §200 CrPC → §223 BNSS "
        "(examination of complainant), §204 → §227 (issue of process). Structure:\n"
        "1. COURT HEADER (centred): 'न्यायालय माननीय <court_name> महोदय'.\n"
        "2. CASE BLOCK: 'प्रकरण क्रमांक       /<वर्ष>          परिवाद पत्र'.\n"
        "3. COMPLAINANT: '<complainant_name> पुत्र/पुत्री श्री <complainant_father>, आयु- __ वर्ष, "
        "निवासी- <complainant_address>' then right-aligned '--- परिवादी'.\n"
        "4. 'बनाम' (centred).\n"
        "5. ACCUSED: each from <accused_names> with parentage/role + residence; then right-aligned "
        "'--- आरोपी' (or '--- आरोपीगण' if more than one).\n"
        "6. TITLE (centred): 'परिवाद पत्र अन्तर्गत धारा <offence_sections>' — the SUBSTANTIVE offence "
        "sections (NOT 156(3); this is the direct route).\n"
        "7. 'माननीय न्यायालय,' then 'परिवादी की ओर से परिवाद पत्र निम्न प्रकार प्रस्तुत है :-'.\n"
        "8. BODY — numbered paragraphs EACH beginning 'यह कि': (1) complainant's standing / good "
        "repute; (2..n) the incident in full chronological detail from <facts_narrative> — date, time, "
        "place, each accused's specific role, injuries/loss; then (if <police_approach> given) approach "
        "to the police and their refusal, written applications to SP/SDOP/CM cell/Human Rights "
        "Commission with dates and continued inaction; then 'यह कि परिवादी के विरुद्ध प्रथम दृष्टया धारा "
        "<offence_sections> का अपराध बनता है।'; then jurisdiction 'यह कि घटना स्थल पुलिस थाना "
        "<incident_place> के क्षेत्राधिकार में होने से माननीय न्यायालय को परिवाद का श्रवणाधिकार एवं "
        "क्षेत्राधिकार प्राप्त है।'; then 'यह कि परिवादी द्वारा उक्त घटना के सम्बन्ध में भारत वर्ष के किसी भी "
        "थाने या न्यायालय में आज दिनांक तक इस परिवाद के अलावा अन्य कोई कार्यवाही नहीं की है न ही कोई प्रकरण "
        "लंबित है।'.\n"
        "9. PRAYER (begins 'अत:'): 'अत: श्रीमान जी से निवेदन है कि परिवादी का परिवाद पत्र स्वीकार कर "
        "आरोपीगण के विरुद्ध धारा <offence_sections> के तहत अपराध पंजीबद्ध कर एवं आरोपीगण को समन/शक्ति "
        "पत्र से तलब कर अधिकतम दण्ड से दण्डित कर परिवादी को <relief_compensation, e.g. प्रतिकर> दिलाने का "
        "आदेश पारित करने की कृपा करें।'.\n"
        "10. 'दिनांक:- <filing_date>' (left) and 'परिवादी / प्रार्थी' + complainant name (right).\n"
        "11. 'साक्षीगण :-' — numbered list from <witnesses> (if given).\n"
        "12. AFFIDAVIT (शपथपत्र) BLOCK at the end: repeat the court header + case-number + short parties "
        "('<complainant> --- परिवादी / बनाम / <accused> --- आरोपी'); heading 'शपथपत्र'; a "
        "नाम/पिता/आयु/व्यवसाय/निवासी key-value block of the deponent; 'मैं उक्त शपथकर्ता शपथपूर्वक सत्य "
        "कथन करता/करती हूँ कि:-'; numbered 'यह कि' paragraphs swearing the complaint's contents are "
        "true to personal knowledge; then verification + deponent signature + date.\n"
        "Tone: factual, chronological, names everything specific."
    ),
    "example_prompts": [
        "थाना सुभाषपुरा के पुलिसवालों ने मेरे मुवक्किल को अवैध हिरासत में पीटा — 342, 323, 324 में परिवाद",
        "Direct private complaint — defamation 356 BNS, complainant will lead evidence",
        "परिवाद 200 — पुलिस ने FIR नहीं ली, अब सीधे कोर्ट से समन चाहते हैं",
    ],
}


# ── 3. REPLY / COUNTER TO APPLICATION (जबाव) — general para-wise reply ────────
# Filed by the non-applicant (अनावेदक) answering ANY application para-by-para:
# maintenance (§125 CrPC / §144 BNSS), domestic violence (§12 DV Act), a claim
# petition, §311 recall, etc. Distinct from reply_to_bail_sessions (which is the
# prosecution's bail-opposing counter only). Cross-court → "procedural" rail.
REPLY_APPLICATION = {
    "id":              "reply_application",
    "name_en":         "Reply / Counter to Application (Jawab)",
    "name_hi":         "जबाव / प्रत्युत्तर (आवेदन पर)",
    "court":           "procedural",
    "court_label_en":  "Common",
    "court_label_hi":  "सामान्य",
    "category":        "procedural",
    "tier":            1,
    "popularity":      4,
    "quality":         "v2-ref",
    "description":     "Para-wise reply (जबाव) by the non-applicant to any pending application — maintenance (§125 CrPC / §144 BNSS), domestic violence (§12 DV Act), a claim petition, §311 recall, etc. Admits/denies each numbered paragraph and adds a 'विशेष निवेदन' affirmative defence.",
    "fields": [
        {"key": "court_name",        "label_en": "Court (where application is pending)", "label_hi": "न्यायालय (जहाँ आवेदन लंबित है)", "type": "text", "required": True, "section": "court", "hint": "e.g. न्यायिक दण्डाधिकारी प्रथम श्रेणी, ग्वालियर / कुटुम्ब न्यायालय"},
        {"key": "case_no",           "label_en": "Case / application number",      "label_hi": "प्रकरण क्रमांक",             "type": "text",     "required": True,  "section": "court"},
        {"key": "application_section","label_en": "Application section + Act",      "label_hi": "आवेदन की धारा + अधिनियम",     "type": "text",     "required": True,  "section": "court", "hint": "e.g. 125 दं.प्र.सं. (144 BNSS) / धारा 12 घरेलू हिंसा अधिनियम"},
        {"key": "applicant_name",    "label_en": "Applicant (आवेदक / आवेदकगण)",    "label_hi": "आवेदक का नाम",              "type": "name",     "required": True,  "section": "applicant"},
        {"key": "respondent_name",   "label_en": "Respondent filing reply (अनावेदक)", "label_hi": "अनावेदक (जबाव देने वाला)",  "type": "name",     "required": True,  "section": "respondent"},
        {"key": "original_paras",    "label_en": "The application's numbered allegations", "label_hi": "आवेदन की क्रमांकित कण्डिकाएं", "type": "longtext", "required": True, "section": "facts", "hint": "Paste/summarise the original application para-by-para (पद क्रमांक 1, 2, 3 …) so each can be answered"},
        {"key": "defence_narrative", "label_en": "Respondent's version (admit / deny each para)", "label_hi": "अनावेदक का पक्ष (हर पद पर स्वीकार/अस्वीकार)", "type": "longtext", "required": True, "section": "grounds", "hint": "Which paras are admitted, which denied, and the counter-facts"},
        {"key": "special_submissions","label_en": "Special submissions (विशेष निवेदन)", "label_hi": "विशेष निवेदन",            "type": "longtext", "required": False, "section": "grounds", "hint": "Affirmative defence — e.g. already paying maintenance in another case, willing to keep applicant, applicant left voluntarily"},
        {"key": "advocate_name",     "label_en": "Advocate name(s)",               "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                      "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Generate a Hindi जबाव (para-wise reply / counter) to a pending application. Output Hindi "
        "(Devanagari); add English only if asked. Plain text, no markdown. Map CrPC→BNSS if user gives "
        "BNSS (e.g. §125 CrPC → §144 BNSS). Structure:\n"
        "1. COURT HEADER (centred): 'न्यायालय माननीय <court_name>'.\n"
        "2. 'प्रकरण क्रमांक- <case_no>'.\n"
        "3. APPLICANT: '<applicant_name> आदि' then right-aligned '- आवेदकगण' (or '- आवेदक' if single).\n"
        "4. 'बनाम' (centred).\n"
        "5. RESPONDENT: '<respondent_name>' then right-aligned '-- अनावेदक'.\n"
        "6. TITLE (centred): 'जबाव आवेदन पत्र अन्तर्गत धारा <application_section>'.\n"
        "7. 'माननीय महोदय,' then 'अनावेदक की ओर से जबाव निम्न प्रकार प्रस्तुत है :-'.\n"
        "8. BODY — numbered paragraphs EACH beginning 'यह कि' and addressing the corresponding "
        "'पद क्रमांक- <N>' of the application (use <original_paras> for the numbering and "
        "<defence_narrative> for the stance). Use the authentic register:\n"
        "   • admit: 'पद क्रमांक- <N> में वर्णित तथ्य सही लिखा होने से स्वीकार है परन्तु <qualification>।'\n"
        "   • deny: 'पद क्रमांक- <N> में वर्णित समस्त तथ्य मिथ्या व असत्य होने से पूरी तरह से अस्वीकार है। "
        "<counter-narrative>।'\n"
        "   • legal/no-reply: 'पद क्रमांक- <N> कानून का विषय होने से जबाव की आवश्यकता नहीं।'\n"
        "   • the prayer para of the application: 'प्रार्थना मिथ्या होने से स्वीकार नहीं है।'\n"
        "   Reply to EVERY numbered para of the application in order; never leave a para unanswered.\n"
        "9. 'विशेष निवेदन :-' — additional 'यह कि' paragraphs of affirmative defence from "
        "<special_submissions> (e.g. maintenance already ordered in another case, respondent willing "
        "to keep the applicant, applicant left voluntarily with her belongings, respondent's actual "
        "income/means).\n"
        "10. PRAYER (begins 'अत:'): 'अत: निवेदन है कि अनावेदक का जबाव स्वीकार कर आवेदकगण द्वारा "
        "प्रस्तुत आवेदन निरस्त करने की कृपा करें।'.\n"
        "11. CLOSING: 'दिनांक:- <filing_date>' (left); right side 'प्रार्थी' + respondent name + "
        "'-- अनावेदक', then 'द्वारा अभिभाषक' + advocate name(s) + 'एडवोकेट'.\n"
        "Tone: measured, point-by-point, denies the applicant's narrative while asserting the "
        "respondent's own version. Mirror the application's paragraph count exactly."
    ),
    "example_prompts": [
        "125 का जबाव — पत्नी खुद मायके चली गई, अनावेदक रखने को तैयार, आय ₹5000/माह",
        "Reply to §12 DV application — deny all allegations, no dowry demand, willing to cohabit",
        "जबाव — claim petition में हर पद का खण्डन करना है",
    ],
}


# ============================================================================
# AGGREGATE — used by compose_templates.py to merge into TEMPLATES dict
# ============================================================================

NEW_TEMPLATES_V2: dict[str, dict] = {
    SLP_CRIMINAL["id"]:               SLP_CRIMINAL,
    TRANSFER_PETITION_CRI["id"]:      TRANSFER_PETITION_CRI,
    REVIEW_PETITION_SC["id"]:         REVIEW_PETITION_SC,
    HABEAS_CORPUS_226["id"]:          HABEAS_CORPUS_226,
    SUSPENSION_OF_SENTENCE["id"]:     SUSPENSION_OF_SENTENCE,
    STAY_PETITION_HC["id"]:           STAY_PETITION_HC,
    REGULAR_BAIL_SESSIONS["id"]:      REGULAR_BAIL_SESSIONS,
    REGULAR_BAIL_HC["id"]:            REGULAR_BAIL_HC,
    ANTICIPATORY_BAIL_SESSIONS["id"]: ANTICIPATORY_BAIL_SESSIONS,
    CRIMINAL_REVISION_SESSIONS["id"]: CRIMINAL_REVISION_SESSIONS,
    REPLY_TO_BAIL_SESSIONS["id"]:     REPLY_TO_BAIL_SESSIONS,
    TRIAL_BAIL_437["id"]:             TRIAL_BAIL_437,
    COMPLAINT_156_3["id"]:            COMPLAINT_156_3,
    PRODUCTION_WARRANT_91["id"]:      PRODUCTION_WARRANT_91,
    PRODUCTION_DOCUMENTS_91_94["id"]: PRODUCTION_DOCUMENTS_91_94,
    EXAMINATION_311["id"]:            EXAMINATION_311,
    COMPROMISE_320["id"]:             COMPROMISE_320,
    DISPENSE_ATTENDANCE_205["id"]:    DISPENSE_ATTENDANCE_205,
    SUPURDGI_451_457["id"]:           SUPURDGI_451_457,
    NI_ACT_138["id"]:                 NI_ACT_138,
    DV_ACT_12["id"]:                  DV_ACT_12,
    HMA_9_RESTITUTION["id"]:          HMA_9_RESTITUTION,
    HMA_13_DIVORCE["id"]:             HMA_13_DIVORCE,
    GENERAL_AFFIDAVIT["id"]:          GENERAL_AFFIDAVIT,
    # v2-ref — decoded from real filings (close the biggest catalogue gaps)
    LEGAL_NOTICE["id"]:               LEGAL_NOTICE,
    PRIVATE_COMPLAINT_200["id"]:      PRIVATE_COMPLAINT_200,
    REPLY_APPLICATION["id"]:          REPLY_APPLICATION,
}
