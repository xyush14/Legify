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
        "SLP against a High Court order in Cr.A. 234/2025 — appeal dismissed, conviction confirmed under S.302 IPC",
        "Special leave petition for my client whose anticipatory bail was rejected by Allahabad HC",
    ],
}


TRANSFER_PETITION_CRI = {
    "id":              "transfer_petition_cri",
    "name_en":         "Transfer Application (Criminal — §448 BNSS / §408 CrPC)",
    "name_hi":         "प्रकरण अंतरण आवेदन (धारा 448 BNSS / 408 दं.प्र.सं.)",
    "court":           "sessions",
    "court_label_en":  "Sessions Court",
    "court_label_hi":  "सत्र न्यायालय",
    "category":        "procedural",
    "tier":            2,
    "popularity":      2,
    "quality":         "v2-ref",
    "description":     "Application u/s 448 BNSS (408 CrPC) before the Principal District & Sessions Judge to transfer a criminal case from one court to another within the sessions division. Decoded verbatim from a real MP filing — आवेदक/अनावेदक(राज्य) caption, short single-ground यहकि para (e.g. presiding officer on long medical leave while accused is in continuous judicial custody), prayer to 'तलब कर ... किसी अन्य सक्षम न्यायालय द्वारा सुनवाई'. Forum variants of the SAME prayer (transfer chapter maps CrPC+40→BNSS): HC transfer within State = §407 CrPC / §447 BNSS; SC inter-State transfer = §406 CrPC / §446 BNSS.",
    "fields": [
        {"key": "petitioner_name",   "label_en": "Applicant (accused) name",       "label_hi": "आवेदक (अभियुक्त) का नाम",   "type": "name",     "required": True,  "section": "applicant"},
        {"key": "respondent_name",   "label_en": "Respondent (State via PS)",      "label_hi": "अनावेदक (राज्य द्वारा थाना)","type": "text",    "required": True,  "section": "respondent", "hint": "Default: <राज्य> शासन द्वारा पुलिस थाना <name>"},
        {"key": "case_no",           "label_en": "Case to be transferred (no.)",   "label_hi": "अंतरित करवाने वाला प्रकरण क्र.","type": "text", "required": True, "section": "matter"},
        {"key": "current_court",     "label_en": "Court to transfer FROM",         "label_hi": "किस न्यायालय से (वर्तमान)",   "type": "text",     "required": True,  "section": "matter", "hint": "Name + presiding officer, e.g. 'द्वितीय अपर सत्र न्यायाधीश (श्री ___)'"},
        {"key": "proposed_court",    "label_en": "Transferee court (optional)",    "label_hi": "प्रस्तावित न्यायालय (वैकल्पिक)","type": "text", "required": False, "section": "matter", "hint": "Leave blank → 'किसी अन्य सक्षम न्यायालय'"},
        {"key": "transfer_grounds",  "label_en": "Grounds for transfer",           "label_hi": "अंतरण के आधार",              "type": "longtext", "required": True,  "section": "grounds", "hint": "Presiding officer on long leave / apprehension of bias / accused in custody & trial stalled / safety / convenience"},
        {"key": "advocate_name",     "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",            "type": "name",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                           "label_hi": "दिनांक",                      "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "यह धारा 448 भा.ना.सु.सं./BNSS (408 दं.प्र.सं./CrPC) का प्रकरण अंतरण (transfer) आवेदन है, जो "
        "प्रधान जिला एवं सत्र न्यायाधीश के समक्ष प्रस्तुत होता है — असली MP फाइलिंग से verbatim decode "
        "किया गया। यह दस्तावेज़ छोटा व सीधा है (कोई शपथपत्र/सत्यापन भीतर नहीं)। हिन्दी में बिल्कुल इसी "
        "ढाँचे में लिखें:\n\n"
        "1. न्यायालय शीर्षक (केन्द्र में): 'न्यायालय माननीय प्रधान जिला एवं सत्र न्यायाधीश महोदय <जिला>'।\n"
        "2. प्रकरण पंक्ति: 'प्रकरण क्रमांक- ____ /<वर्ष>' (यह transfer आवेदन का क्रमांक है, अंतरित होने "
        "वाले मूल प्रकरण का नहीं)।\n"
        "3. पक्षकार खण्ड (आवेदक=अभियुक्त पहले):\n"
        "   '<petitioner_name> पुत्र श्री ____, निवासी- ____' .......... आवेदक\n"
        "   'बनाम'\n"
        "   '<respondent_name>' (जैसे '<राज्य> शासन द्वारा पुलिस थाना ____ जिला ____') .......... अनावेदक\n"
        "4. शीर्षक (केन्द्र, रेखांकित): 'आवेदन पत्र अन्तर्गत धारा 448 भा.ना.सु.सं.' (पुरानी संहिता में "
        "'धारा 408 दं.प्र.सं.')। शीर्षक में इससे अधिक न जोड़ें।\n"
        "5. सम्बोधन + आरम्भ: 'माननीय महोदय,' फिर 'प्रार्थी की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है :-'\n"
        "6. 'यहकि,' पैरा (प्राय: एक ही, संक्षिप्त — मूल प्रकरण का विवरण + अंतरण का आधार एक साथ):\n"
        "   प्रार्थी का प्रकरण [विशेष सत्र प्रकरण क्रमांक- <case_no>] '<current_court>' के न्यायालय में "
        "[दिनांक ____ को अभियुक्त परीक्षण/सुनवाई हेतु] नियत है; [यदि लागू हो: प्रार्थी उक्त प्रकरण में "
        "निरंतर न्यायिक अभिरक्षा में है]; फिर अंतरण का ठोस आधार <transfer_grounds> को बुनें (जैसे — उक्त "
        "न्यायालय के पीठासीन अधिकारी का स्वास्थ्य खराब होने से ऑपरेशन हुआ है व वे लम्बी छुट्टी पर हैं; "
        "अथवा पक्षपात की आशंका; अथवा सुनवाई में अनुचित विलम्ब); निष्कर्ष: 'इस कारण उपरोक्त प्रकरण "
        "<current_court> के न्यायालय से बुलाया जाकर किसी अन्य न्यायालय में अंतरित किया जाना न्याय संगत "
        "व आवश्यक है।'\n"
        "7. प्रार्थना (बिना 'प्रार्थना' शीर्षक के, सीधे 'अत:' से): 'अत: प्रार्थना है कि आवेदन पत्र "
        "स्वीकार कर प्रकरण क्रमांक- <case_no> उनमान [<respondent_name> बनाम <petitioner_name> आदि व अन्य] "
        "[नियत दिनांक ____ को] माननीय <current_court> के न्यायालय से तलब कर उपरोक्त प्रकरण की सुनवाई "
        "<proposed_court या 'किसी अन्य सक्षम न्यायालय'> द्वारा की जाने की कृपा करें।'\n"
        "8. हस्ताक्षर: 'दिनांक :- <filing_date>' दाहिनी ओर 'प्रार्थी' फिर '<petitioner_name> ---- आवेदक', "
        "फिर 'द्वारा अभिभाषक' और '<advocate_name> (एडवोकेट)'।\n"
        "(NOTE: यदि उच्च न्यायालय में राज्यांतर्गत अंतरण हो तो धारा 407 दं.प्र.सं./447 BNSS व 'माननीय "
        "उच्च न्यायालय' शीर्षक; अन्तर्राज्यीय अंतरण उच्चतम न्यायालय में धारा 406 दं.प्र.सं./446 BNSS — "
        "ढाँचा वही, केवल मंच व धारा बदलें।)\n\n"
        "ENGLISH MODE (only if lang=en): mirror the SAME structure in English — 'IN THE COURT OF THE "
        "PRINCIPAL DISTRICT & SESSIONS JUDGE, <district>' header; 'Case No. ___ / <year>'; "
        "applicant-first caption '<petitioner_name> S/o ___, R/o ___ …Applicant / Versus / "
        "<respondent_name> (State of <State> through P.S. ___) …Non-applicant'; centred underlined title "
        "'APPLICATION UNDER SECTION 448 BNSS (408 CrPC)'; 'To the Hon'ble Court,' + 'The following "
        "application is submitted on behalf of the applicant:-'; a short 'That,' paragraph stating the "
        "case number, the court where it is pending and the next date, that the applicant is in "
        "continuous judicial custody (if applicable), the concrete ground for transfer (from "
        "<transfer_grounds> — e.g. the presiding officer is on long medical leave, apprehension of "
        "bias, undue delay), and the conclusion that transferring the case to another competent court "
        "is just and necessary; prayer 'It is therefore prayed that the application be allowed, case "
        "no. <case_no> be called from the court of <current_court> and its hearing be entrusted to "
        "<proposed_court or 'any other competent court'>'; signature 'Applicant, through counsel "
        "<advocate_name>'. Plain text output, no markdown."
    ),
    "example_prompts": [
        "धारा 448 BNSS अंतरण — द्वितीय अपर सत्र न्यायाधीश के पीठासीन अधिकारी लम्बी मेडिकल छुट्टी पर, आरोपी न्यायिक अभिरक्षा में, प्रकरण किसी अन्य न्यायालय भेजा जाए",
        "सत्र न्यायाधीश से प्रकरण अंतरण आवेदन — विचारण न्यायाधीश के प्रति पक्षपात की आशंका, निष्पक्ष सुनवाई हेतु दूसरे न्यायालय में अंतरण",
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
        "1. Cause-title (centred, underlined), built from the court_name field: "
        "in Hindi 'माननीय उच्च न्यायालय <court_name>' — for an MP bench use the "
        "form 'माननीय उच्च न्यायालय मध्यप्रदेश खण्डपीठ <स्थान>'; in English 'IN "
        "THE HIGH COURT OF <court_name>'.\n"
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
        "Habeas corpus — my brother taken by the local police 3 days ago, no FIR, no production",
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
    "quality":         "v2-ref",
    "description":     "Application under S.389 CrPC (S.430 BNSS) to suspend execution of sentence pending appeal and release the convicted appellant on security. Format decoded verbatim from real High Court criminal-side filings — अपीलार्थी/प्रतिअपीलार्थी party blocks, ordinal successive-application title, 'दुखित होकर' prior-application recital, सी.आर.ए. case line.",
    "fields": [
        {"key": "court_name",       "label_en": "Court",                          "label_hi": "न्यायालय",                  "type": "text",     "required": True,  "section": "court", "hint": "Usually 'High Court, <bench>'"},
        {"key": "appeal_no",        "label_en": "Appeal number",                  "label_hi": "अपील क्रमांक",                "type": "text",     "required": True,  "section": "court", "hint": "e.g. Crl. Appeal No. ___ / 2026"},
        {"key": "appellant_name",   "label_en": "Appellant (convicted accused)",  "label_hi": "अपीलार्थी (दण्डित बन्दी)", "type": "name",     "required": True,  "section": "applicant"},
        {"key": "appellant_father", "label_en": "Father's name",                  "label_hi": "पिता का नाम",                "type": "name",     "required": True,  "section": "applicant"},
        {"key": "appellant_age",    "label_en": "Age",                            "label_hi": "आयु",                        "type": "text",     "required": False, "section": "applicant"},
        {"key": "current_jail",     "label_en": "Currently lodged at (jail)",     "label_hi": "वर्तमान निरोध स्थान (जेल)",   "type": "text",     "required": True,  "section": "applicant"},
        {"key": "trial_court",      "label_en": "Trial court whose conviction is challenged","label_hi": "विचारण न्यायालय (जिसके निर्णय को चुनौती)",   "type": "text", "required": True, "section": "matter"},
        {"key": "sections",         "label_en": "Sections of conviction",         "label_hi": "दण्डादेश की धाराएं",          "type": "text",     "required": True,  "section": "matter"},
        {"key": "sentence",         "label_en": "Sentence imposed",               "label_hi": "लगाया गया दण्ड",              "type": "text",     "required": True,  "section": "matter", "hint": "e.g. 7 years RI + ₹5,000 fine"},
        {"key": "sentence_date",    "label_en": "Date of judgment",               "label_hi": "निर्णय दिनांक",                "type": "date",     "required": True,  "section": "matter"},
        {"key": "grounds",          "label_en": "Grounds for suspension",         "label_hi": "निलंबन के आधार",              "type": "longtext", "required": True,  "section": "grounds", "hint": "Strong prima facie case in appeal / advanced age / medical / long custody / etc."},
        {"key": "advocate_name",    "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",             "type": "name",     "required": True,  "section": "filing"},
        {"key": "place",            "label_en": "Place",                          "label_hi": "स्थान",                       "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",      "label_en": "Date",                           "label_hi": "दिनांक",                       "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "यह §389 दं.प्र.सं. 1973 (अब धारा 430 भा.ना.सु.सं.) का आवेदन है — दण्डादेश का "
        "क्रियान्वयन अपील के निराकरण तक स्थगित कराकर दोषसिद्ध अपीलार्थी को उचित "
        "प्रतिभूति पर रिहा कराने हेतु, उच्च न्यायालय में लंबित दाण्डिक अपील के साथ। "
        "नीचे की संरचना वास्तविक न्यायालयीन filings से ली गई है — इसी क्रम व शब्दावली "
        "का कड़ाई से पालन करें।\n\n"
        "1. न्यायालय शीर्ष (केन्द्रित): 'माननीय उच्च न्यायालय <राज्य> खण्डपीठ "
        "<स्थान>' — court_name से।\n"
        "2. प्रकरण पंक्ति: 'सी.आर.ए. क्रमांक ____ / <वर्ष>' — appeal_no से।\n"
        "3. पक्षकार ब्लॉक (बहता हुआ गद्य, फॉर्म जैसा नहीं):\n"
        "   '<appellant_name> पुत्र <appellant_father>, आयु <appellant_age> वर्ष, "
        "निवासी ____, वर्तमान में <current_jail> में निरुद्ध ............ अपीलार्थी'\n"
        "   अगली पंक्ति केन्द्र में: 'वि0'\n"
        "   '<राज्य> शासन द्वारा पुलिस थाना ____ ............ प्रतिअपीलार्थी'\n"
        "4. शीर्षक (केन्द्रित — frontend स्वतः रेखांकित+बोल्ड करता है, कोई markup नहीं): "
        "'<क्रमसूचक> आवेदन पत्र अन्तर्गत धारा 389 दं.प्र.सं. 1973' — जहाँ <क्रमसूचक> = "
        "प्रथम/द्वितीय/तृतीय/चतुर्थ/पंचम/षष्टम् दर्शाता है कि अपीलार्थी की ओर से यह "
        "कौन-सा क्रमिक आवेदन है (यदि पहला है तो 'प्रथम')।\n"
        "5. प्रस्तावना पंक्ति: 'बन्दी/अपीलार्थी की ओर से आवेदन पत्र निम्न प्रकार "
        "प्रस्तुत है :-'\n"
        "6. क्रमांकित अनुच्छेद, प्रत्येक 'यहकि,' से प्रारम्भ:\n"
        "   (1) यह अपीलार्थी की ओर से <क्रमसूचक> आवेदन है; पूर्व आवेदन (यदि कोई) "
        "उनकी दिनांकों सहित — माननीय न्यायालय द्वारा 'बल न देने से निरस्त किये जाने "
        "से दुखित होकर' यह आवेदन प्रस्तुत किया जा रहा है। (यदि यह प्रथम आवेदन है तो: "
        "इसके पूर्व कोई आवेदन प्रस्तुत नहीं किया गया है।)\n"
        "   (2) इस सम्बन्ध में माननीय उच्चतम न्यायालय अथवा किसी अन्य न्यायालय में "
        "कोई आवेदन लंबित नहीं है।\n"
        "   (3) अपीलार्थी ने विचारण न्यायालय <trial_court> के दोषसिद्धि निर्णय के "
        "विरुद्ध पूर्ण सफलता की आशा से प्रस्तुत अपील की है तथा अधिरोपित अर्थदण्ड जमा "
        "कर दिया है।\n"
        "   (4) प्रकरण संक्षेप में — अभियोजन कथानक/घटना का संक्षिप्त विवरण।\n"
        "   (5) विचारण न्यायालय ने अपीलार्थी को धारा <sections> में दोषी सिद्ध मानते "
        "हुए दिनांक <sentence_date> को <sentence> से दण्डित किया।\n"
        "   (6 आगे) निलंबन के आधार (grounds field) — पृथक-पृथक अनुच्छेदों में: विचारण "
        "न्यायालय द्वारा साक्ष्य की अनदेखी, पक्षद्रोही साक्षी, चिकित्सीय विरोधाभास, "
        "अस्त्र की बरामदगी न होना आदि गम्भीर विधिक त्रुटियाँ; अपीलार्थी लगभग ____ से "
        "निरुद्ध है; अपील के शीघ्र निराकरण की सम्भावना नहीं; विचारण के दौरान जमानत पर "
        "रहते हुए कोई दुरुपयोग नहीं किया; स्थायी निवासी है, सम्पत्ति है, फरार होने की "
        "कोई आशंका नहीं; न्यायालय द्वारा अधिरोपित समस्त शर्तों का पालन करने को तैयार "
        "है।\n"
        "   (अन्तिम) 'यहकि, अन्य तर्क वक्त बहस मौखिक रूप से निवेदित किये जावेंगे।'\n"
        "7. प्रार्थना (बिना किसी 'PRAYER'/'प्रार्थना' शीर्षक के, सीधे अनुच्छेद रूप में): "
        "'अत: माननीय न्यायालय से विनम्र निवेदन है कि आवेदक अपीलार्थी का आवेदन पत्र "
        "स्वीकार किया जाकर विद्वान विचारण न्यायालय के निर्णय एवं दण्डाज्ञा दिनांक "
        "<sentence_date> का क्रियान्वयन अपील के अन्तिम निराकरण तक स्थगित किया जाकर "
        "आवेदक अपीलार्थी को अपील के अन्तिम निराकरण तक उचित प्रतिभूति पर उन्मुक्त किये "
        "जाने का आदेश पारित करने की कृपा करें।'\n"
        "8. हस्ताक्षर ब्लॉक (दायें): स्थान <place>, दिनांक <filing_date>; नीचे "
        "'-बन्दी/आवेदक अपीलार्थी' तथा अधिवक्ता <advocate_name>।\n"
        "नोट: शपथपत्र इस आवेदन के साथ संलग्न होता है पर वह एक पृथक दस्तावेज़ है — उसे "
        "इस आवेदन के मुख्य भाग में न जोड़ें।\n\n"
        "ENGLISH MODE (only if lang=en): mirror the exact same structure and order "
        "in formal Indian legal English — 'IN THE HIGH COURT OF MADHYA PRADESH, "
        "BENCH AT <place>'; 'Cr.A. No. ___ / <year>'; flowing appellant block "
        "ending '... Appellant', then 'Versus', then 'State of <State> through P.S. "
        "____ ... Respondent'; title '<ORDINAL> APPLICATION UNDER SECTION 389 "
        "CrPC, 1973'; 'That ...' numbered paragraphs covering the "
        "successive-application declaration with prior dates (or that this is the "
        "first application), no application pending in the Supreme Court or any "
        "other court, appeal preferred against conviction with fine deposited, "
        "brief facts, conviction & sentence particulars, then the grounds "
        "(evidence ignored, hostile witnesses, medical contradictions, no "
        "recovery, long custody, appeal unlikely to be heard soon, no misuse of "
        "bail during trial, permanent resident, ready to abide by conditions), "
        "closing 'That further arguments will be advanced orally at the time of "
        "hearing'; the prayer as a flowing paragraph (NO 'PRAYER' heading) to "
        "suspend execution of the judgment & sentence dated <sentence_date> till "
        "final disposal of the appeal and release the appellant on suitable "
        "security; signature '- Convict/Applicant Appellant' + advocate."
    ),
    "example_prompts": [
        "Suspension of sentence — client convicted to life + ₹2,000 fine u/s 302 IPC, appeal pending in HC, in custody ~6 years",
        "षष्टम् 389 आवेदन — पूर्व आवेदन निरस्त, अपील शीघ्र निराकृत होने की सम्भावना नहीं, अपीलार्थी स्थायी निवासी",
    ],
}


STAY_PETITION_HC = {
    "id":              "stay_petition_hc",
    "name_en":         "Stay / Interim Application (in HC Revision · §482)",
    "name_hi":         "अंतरिम स्थगन आवेदन (उच्च न्यायालय पुनरीक्षण / धारा 482)",
    "court":           "hc",
    "court_label_en":  "High Court",
    "court_label_hi":  "उच्च न्यायालय",
    "category":        "procedural",
    "tier":            2,
    "popularity":      3,
    "quality":         "v2-ref",
    "description":     "Interim application for अंतरिम स्थगन (stay) of the impugned order / further proceedings, riding on a pending HC criminal revision or §482 (528 BNSS) petition. Modeled on real High Court criminal-side idiom — 'माननीय उच्च न्यायालय <राज्य> खण्डपीठ <स्थान>' header, पुनरीक्षणकर्ता/प्रतिपुनरीक्षणकर्ता(राज्य) caption, purpose-line title naming the impugned order, 'प्रार्थी की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है' opening, यहकि paras, 'अत: ... स्थगित किये जाने की कृपा करें' prayer. Verified revision mapping: §397/401 CrPC = §438/442 BNSS. A stay is NOT a standalone suit — it is an I.A. inside the main matter.",
    "fields": [
        {"key": "court_name",      "label_en": "High Court + bench",             "label_hi": "उच्च न्यायालय + खण्डपीठ",   "type": "text",     "required": True,  "section": "court", "hint": "e.g. माननीय उच्च न्यायालय <राज्य> खण्डपीठ <स्थान>"},
        {"key": "main_petition_no","label_en": "Main revision / §482 case no.",  "label_hi": "मुख्य पुनरीक्षण / 482 प्रकरण क्र.","type": "text",  "required": True,  "section": "court"},
        {"key": "petitioner_name", "label_en": "Applicant (revisionist)",        "label_hi": "आवेदक (पुनरीक्षणकर्ता)",     "type": "name",     "required": True,  "section": "applicant"},
        {"key": "respondent_name", "label_en": "Respondent (State via PS)",      "label_hi": "अनावेदक (राज्य द्वारा थाना)","type": "text",    "required": True,  "section": "respondent", "hint": "Default: <राज्य> राज्य द्वारा आरक्षी केन्द्र <name>"},
        {"key": "impugned_order",  "label_en": "Impugned order (date + court)",  "label_hi": "विवादित आदेश (दिनांक + न्यायालय)","type": "text", "required": True,  "section": "matter", "hint": "e.g. आदेश दिनांक 29-10-2025, प्रथम अपर सत्र न्यायाधीश"},
        {"key": "what_to_stay",    "label_en": "What is sought to be stayed",    "label_hi": "किसका स्थगन चाहिए",        "type": "longtext", "required": True,  "section": "matter", "hint": "Execution of the impugned order / further trial-court proceedings / coercive action / further investigation"},
        {"key": "stay_grounds",    "label_en": "Grounds for stay",               "label_hi": "स्थगन के आधार",            "type": "longtext", "required": True,  "section": "grounds", "hint": "Prima facie case + irreparable injury if not stayed + balance of convenience; revision likely to succeed"},
        {"key": "advocate_name",   "label_en": "Advocate name",                  "label_hi": "अधिवक्ता का नाम",          "type": "name",     "required": True,  "section": "filing"},
        {"key": "filing_date",     "label_en": "Date",                           "label_hi": "दिनांक",                    "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "यह अंतरिम स्थगन (interim stay) हेतु आवेदन पत्र है, जो किसी लंबित उच्च न्यायालय आपराधिक "
        "पुनरीक्षण अथवा धारा 482 दं.प्र.सं. (528 भा.ना.सु.सं.) याचिका के साथ प्रस्तुत होता है — "
        "स्थगन कोई स्वतंत्र वाद नहीं, यह मुख्य प्रकरण के भीतर का I.A. है। इसे असली MP उच्च न्यायालय "
        "पुनरीक्षण की शैली में हिन्दी में लिखें:\n\n"
        "1. न्यायालय शीर्षक (केन्द्र में): 'माननीय उच्च न्यायालय <राज्य> खण्डपीठ <स्थान>' "
        "(<court_name> के अनुसार)।\n"
        "2. प्रकरण पंक्ति: मुख्य प्रकरण का क्रमांक — 'पुनरीक्षण याचिका क्रमांक- <main_petition_no>' "
        "(या 'विविध आपराधिक प्रकरण/M.Cr.C. क्रमांक- <main_petition_no>' यदि धारा 482 है)।\n"
        "3. पक्षकार खण्ड (पुनरीक्षण शैली):\n"
        "   'पुनरीक्षणकर्ता/आवेदक ----- <petitioner_name> पुत्र श्री ____, आयु- __ वर्ष, निवासी- ____'\n"
        "   'विरुद्ध'\n"
        "   'प्रतिपुनरीक्षणकर्ता/अनावेदक --- <respondent_name>' (जैसे '<राज्य> राज्य द्वारा आरक्षी केन्द्र "
        "____ जिला ____')।\n"
        "4. शीर्षक (purpose-line शैली, केन्द्र, रेखांकित): 'आवेदन पत्र वास्ते अंतरिम स्थगन — <impugned_order> "
        "[तथा <what_to_stay>] के स्थगन के सम्बन्ध में।' (विवादित आदेश/कार्यवाही का स्पष्ट उल्लेख करें; "
        "मुख्य मामला पुनरीक्षण हो तो धारा संदर्भ '438 एवं 442 भा.ना.सु.सं. (397 एवं 401 दं.प्र.सं.)' दे "
        "सकते हैं — सत्यापित mapping)।\n"
        "5. सम्बोधन + आरम्भ: 'माननीय महोदय,' फिर 'प्रार्थी की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है :-'\n"
        "6. 'यहकि,' से शुरू होने वाले क्रमांकित पैरा:\n"
        "   (1) प्रार्थी/पुनरीक्षणकर्ता की ओर से माननीय न्यायालय के समक्ष मुख्य पुनरीक्षण/धारा 482 याचिका "
        "क्रमांक- <main_petition_no> विचाराधीन/लंबित है;\n"
        "   (2) विवादित आदेश <impugned_order> का संक्षिप्त विवरण तथा वर्तमान में जो कार्यवाही/निष्पादन "
        "चल रहा है (<what_to_stay>) उसका उल्लेख;\n"
        "   (3) आधार पैरा — <stay_grounds> को बुनें: प्रथम दृष्ट्या प्रबल मामला (prima facie), यदि स्थगन "
        "न दिया गया तो प्रार्थी को अपूरणीय क्षति होगी (irreparable injury), तथा सुविधा का संतुलन "
        "(balance of convenience) प्रार्थी के पक्ष में है; मुख्य पुनरीक्षण के सफल होने की प्रबल "
        "सम्भावना है अतः उसके निराकरण तक यथास्थिति आवश्यक है;\n"
        "   (4) 'अन्य आधार वक्त बहस मौखिक रूप से निवेदित किये जावेंगे।'\n"
        "7. प्रार्थना (बिना 'प्रार्थना' शीर्षक के, सीधे 'अत:' से): 'अत: श्रीमान न्यायालय से निवेदन है कि "
        "मुख्य पुनरीक्षण/याचिका क्रमांक- <main_petition_no> के अन्तिम निराकरण तक विवादित आदेश "
        "<impugned_order> के निष्पादन / <what_to_stay> पर रोक लगाते हुए उसे स्थगित किये जाने की कृपा करें।' "
        "(अति-आवश्यक हो तो एकपक्षीय अंतरिम स्थगन की प्रार्थना भी जोड़ें।)\n"
        "8. हस्ताक्षर: 'दिनांक - <filing_date>' दाहिनी ओर 'प्रार्थी/पुनरीक्षणकर्ता', फिर 'द्वारा अभिभाषक' "
        "और '<advocate_name> (एडवोकेट)'।\n"
        "(NOTE: यदि शपथपत्र संलग्न हो तो वह पृथक दस्तावेज़ है — इस आवेदन के मुख्य भाग में न जोड़ें।)\n\n"
        "ENGLISH MODE (only if lang=en): mirror the SAME structure in English — 'IN THE HIGH COURT OF "
        "MADHYA PRADESH, BENCH AT <place>' header; main-matter case line 'Criminal Revision No. "
        "<main_petition_no>' (or 'M.Cr.C. No. <main_petition_no>' for §482); revisionist/respondent "
        "caption ('Revisionist/Applicant … Versus … State of <State> through P.S. ___ … Respondent'); a "
        "purpose-line title 'INTERLOCUTORY APPLICATION FOR INTERIM STAY of <impugned_order> / "
        "<what_to_stay>'; 'To the Hon'ble Court,' + 'The following application is submitted on behalf "
        "of the applicant:-'; 'That,'-numbered paragraphs (main revision/§482 petition is pending → "
        "the impugned order and the proceedings/execution sought to be stayed → grounds: prima facie "
        "case, irreparable injury if not stayed, balance of convenience, strong likelihood of success "
        "in the main revision → further grounds to be urged orally); prayer 'It is therefore prayed "
        "that, pending final disposal of <main_petition_no>, the execution of the impugned order "
        "<impugned_order> / <what_to_stay> be stayed' (add ex-parte ad-interim stay if urgent); "
        "signature 'Applicant / Revisionist, through counsel <advocate_name>'. Plain text output, no "
        "markdown."
    ),
    "example_prompts": [
        "अंतरिम स्थगन — प्रथम अपर सत्र न्यायाधीश के आदेश दिनांक 29-10-2025 के निष्पादन पर रोक, मुख्य पुनरीक्षण लंबित",
        "धारा 482 याचिका के साथ अंतरिम स्थगन — विचारण न्यायालय की आगे की कार्यवाही याचिका के निराकरण तक स्थगित की जाए",
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
# BNSS / 439 CrPC successive bail before a High Court):
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
        "Successive bail at the High Court after first bail withdrawn",
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
    "quality":         "v2-ref",
    "description":     "Criminal revision under §397/401 CrPC (§438/442 BNSS) before the Court of Session / High Court — structure decoded verbatim from real MP filings (पुनरीक्षणकर्ता/प्रतिपुनरीक्षणकर्ता idiom, 'दुखित होकर' impugned-order line, प्रकरण का संक्षिप्त विवरण then पुनरीक्षण याचिका के आधार, prayer to अपास्त the order).",
    "fields": [
        {"key": "court_name",        "label_en": "Court (Session / High Court)",  "label_hi": "न्यायालय (सत्र / उच्च)",    "type": "text",     "required": True,  "section": "court"},
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
        "यह आपराधिक पुनरीक्षण याचिका धारा 397/401 दं.प्र.सं. (438/442 भा.ना.सु.सं.) के अंतर्गत "
        "सत्र न्यायालय अथवा उच्च न्यायालय के समक्ष प्रस्तुत होती है। नीचे दी गई वास्तविक न्यायालयीन "
        "फाइलिंग संरचना का अक्षरशः पालन करें:\n\n"
        "शीर्ष (केन्द्र में):\n"
        "  <court_name> — सत्र हेतु 'न्यायालय माननीय सत्र न्यायाधीश <जिला>', उच्च न्यायालय हेतु "
        "'माननीय उच्च न्यायालय <राज्य> खण्डपीठ <स्थान>'\n"
        "  पुनरीक्षण याचिका क्रमांक- ______ /<वर्ष>\n\n"
        "पक्षकार (बायीं ओर पदनाम, दाहिनी ओर विवरण):\n"
        "  पुनरीक्षणकर्ता -----  <revisionist_name> पुत्र श्री <revisionist_father>, आयु- __ वर्ष, "
        "व्यवसाय- ___, निवासी- <revisionist_address>\n"
        "  केन्द्र में:  वि0रू0 (विरुद्ध)\n"
        "  प्रतिपुनरीक्षणकर्ता ---  <respondent_name> (पूर्ण विवरण सहित)\n\n"
        "विवादित-आदेश पंक्ति (शीर्षक के स्थान पर — यही इस दस्तावेज़ का 'title' है):\n"
        "  'प्रथम पुनरीक्षण याचिका अन्तर्गत धारा 397, 401 द0प्र0सं0/438, 442 भा0ना0सु0सं0 [सहपठित "
        "सम्बन्धित अधिनियम] विरुद्ध आदेश दिनांक <impugned_date> न्यायालय <magistrate_court> द्वारा "
        "प्रकरण क्रमांक- <impugned_case_no> में पारित आदेश से दुखित होकर।'\n\n"
        "प्रथम-पुनरीक्षण घोषणा (अनिवार्य):\n"
        "  'पुनरीक्षणकर्ता की ओर से यह प्रथम विविध पुनरीक्षण याचिका है। उक्त पुनरीक्षण याचिका के "
        "अतिरिक्त पुनरीक्षणकर्ता की ओर से अन्य कोई पुनरीक्षण याचिका माननीय उच्च न्यायालय अथवा "
        "माननीय उच्चतम न्यायालय में न ही विचाराधीन है, न ही निराकृत की गई है।'\n"
        "  'पुनरीक्षणकर्ता की ओर से पुनरीक्षण याचिका निम्न प्रकार प्रस्तुत है :-'\n\n"
        "प्रकरण का संक्षिप्त विवरण :- (विचारण न्यायालय में क्या हुआ, आदेश किस बारे में था — "
        "<impugned_summary> से 'यहकि,' अनुच्छेदों में संक्षेप; विवादित आदेश की प्रति एनेक्जर ए-1 "
        "बताएँ।)\n\n"
        "पुनरीक्षण याचिका के आधार:- (यह याचिका का हृदय है — <revision_grounds> से प्रत्येक आधार "
        "एक 'यहकि,' अनुच्छेद में):\n"
        "  • पहला आधार सदैव: 'यहकि, विचारण न्यायालय द्वारा पारित आदेश न्याय के विपरीत होने से "
        "अपास्त किये जाने योग्य है।'\n"
        "  • इसके बाद क्षेत्राधिकार-त्रुटि / विधि की त्रुटि / साक्ष्य की अनदेखी / एकपक्षीय विवेक / "
        "जल्दबाजी आदि आधार — तिथि व प्रदर्श/एनेक्जर संदर्भ सहित।\n"
        "  • अंतिम आधार सदैव: 'यहकि, अन्य आधार वक्त बहस रिकार्ड उपलब्ध होने पर मौखिक रूप से "
        "निवेदित किये जावेंगे।'\n\n"
        "प्रार्थना (कोई अलग 'PRAYER' शीर्षक नहीं) — सीधे:\n"
        "  'अत: माननीय न्यायालय से निवेदन है कि पुनरीक्षणकर्ता की ओर से प्रस्तुत पुनरीक्षण याचिका "
        "स्वीकार कर विचारण न्यायालय द्वारा प्रकरण क्रमांक- <impugned_case_no> में पारित आदेश दिनांक "
        "<impugned_date> को अपास्त करने की कृपा करें।'\n\n"
        "अंत में:\n"
        "  दिनांक :- <filing_date>                          प्रार्थी\n"
        "                                          <revisionist_name> - पुनरीक्षणकर्ता\n"
        "                                                   द्वारा अभिभाषक\n"
        "                                          <advocate_name> --- एडवोकेट\n\n"
        "महत्वपूर्ण: 'पुनरीक्षणकर्ता' व 'प्रतिपुनरीक्षणकर्ता' तथा निचली अदालत हेतु 'विचारण न्यायालय' "
        "शब्दों का ही प्रयोग करें। इण्डेक्स (अनुक्रमणिका) पृष्ठ पृथक होता है — इसे यहाँ न जोड़ें।\n\n"
        "ENGLISH MODE (only if lang=en): mirror the same structure — 'IN THE COURT OF SESSIONS JUDGE, "
        "<district>' or 'IN THE HIGH COURT OF MADHYA PRADESH, BENCH AT <place>', 'Criminal Revision No. "
        "___/<year>', Revisionist / Non-applicant blocks, the impugned-order line ('Being aggrieved by "
        "the order dated <date> passed by <court> in Case No. <no>…'), the first-revision declaration, "
        "'BRIEF FACTS OF THE CASE', 'GROUNDS' (numbered, the first being that the order is against law "
        "and liable to be set aside, the last reserving additional grounds at the time of arguments), "
        "and a prayer to set aside the impugned order. Use 'Revisionist', 'Non-applicant', 'trial "
        "court'."
    ),
    "example_prompts": [
        "Revision against JMFC order rejecting our discharge application",
        "Revision against family court maintenance order under §144 BNSS",
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
        "1. Cause-title (centred, bold), from the court_name field: in Hindi "
        "'न्यायालय माननीय सत्र न्यायाधीश महोदय, <court_name> (म.प्र.)'; in English "
        "'IN THE COURT OF THE SESSIONS JUDGE, <court_name>'.\n"
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
        "Trial court bail u/s 437 — accused in 379 IPC theft case at the local PS",
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
    "quality":         "v2-ref",
    "description":     "Application u/s 156(3) CrPC (175(3) BNSS) to the Magistrate when police refuses to register an FIR — structure decoded verbatim from real MP JMFC filings (आवेदक/आरोपी idiom, यहकि narrative built around the police-inaction sequence — थाना approached, registered-post applications, no action — title 'आवेदन पत्र अन्तर्गत धारा 156(3) दं.प्र.सं.', mandatory accompanying शपथपत्र).",
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
        "यह आवेदन धारा 156(3) दं.प्र.सं. (175(3) भा.ना.सु.सं.) के अंतर्गत न्यायिक दण्डाधिकारी प्रथम "
        "श्रेणी के समक्ष प्रस्तुत होता है, जिसमें पुलिस द्वारा प्रथम सूचना रिपोर्ट दर्ज न करने पर "
        "न्यायालय से थाने को FIR पंजीबद्ध करने का निर्देश माँगा जाता है। नीचे दी गई वास्तविक न्यायालयीन "
        "फाइलिंग संरचना का अक्षरशः पालन करें:\n\n"
        "शीर्ष (केन्द्र में):\n"
        "  न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी <court_name>\n"
        "  प्रकरण क्रमांक- ______ /<वर्ष> परिवाद पत्र\n\n"
        "पक्षकार-ब्लॉक (बहती पंक्तियों में):\n"
        "  <complainant_name> पुत्र श्री <complainant_father>, आयु- __ वर्ष, व्यवसाय- ___, निवासी- "
        "<complainant_address> (<राज्य>)\n"
        "  दाहिनी ओर:  --- आवेदक\n"
        "  केन्द्र में:  बनाम\n"
        "  <accused_names> में दिये प्रत्येक आरोपी का पूर्ण विवरण (पुत्र/आयु/व्यवसाय/निवासी); फिर "
        "दाहिनी ओर:  --- आरोपी\n\n"
        "शीर्षक (केन्द्र में):\n"
        "  आवेदन पत्र अन्तर्गत धारा 156(3) दं.प्र.सं.\n\n"
        "प्रस्तावना:\n"
        "  माननीय न्यायालय,\n"
        "  आवेदक की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है :-\n\n"
        "कथानक — प्रत्येक अनुच्छेद 'यहकि,' से प्रारम्भ हो; वास्तविक प्रवाह इस क्रम में:\n"
        "  • यहकि, आवेदक का परिचय व निवास।\n"
        "  • यहकि, घटना का विस्तृत विवरण — दिनांक <incident_date>, स्थान <incident_place>, आरोपी की "
        "भूमिका (<facts_narrative> से)।\n"
        "  • यहकि, उक्त कृत्य धारा <sections_invoked> से दण्डनीय संज्ञेय (व अजमानतीय) अपराध की श्रेणी "
        "में आता है।\n"
        "  • पुलिस-निष्क्रियता का क्रम (156(3) का विधिक आधार — अनिवार्य): यहकि, आवेदक थाना "
        "<police_station> गया व लिखित आवेदन दिया, किन्तु प्राप्ति/कार्यवाही नहीं हुई; पुनः रजिस्टर्ड "
        "डाक से आवेदन भेजे; पुलिस अधीक्षक/वरिष्ठ अधिकारी को भी आवेदन दिया (<police_refusal> से तिथियाँ "
        "सहित); आज दिनांक तक कोई कार्यवाही नहीं की गई।\n"
        "  • यहकि, साक्षीगण <witnesses> (यदि उपलब्ध हो)।\n"
        "  • यहकि, घटना-स्थल व पक्षकारों के निवास के आधार पर माननीय न्यायालय को श्रवणाधिकार प्राप्त है।\n"
        "  • यहकि, आवेदक द्वारा इस परिवाद के अतिरिक्त भारत वर्ष के किसी थाने/न्यायालय में अन्य कोई "
        "कार्यवाही न तो की गई है, न लंबित है।\n\n"
        "प्रार्थना (कोई अलग 'प्रार्थना/PRAYER' शीर्षक नहीं) — सीधे:\n"
        "  अत: श्रीमान जी से निवेदन है कि पुलिस थाना <police_station> को इस आशय का निर्देश देने की "
        "कृपा करें कि वह आरोपी के विरुद्ध धारा <sections_invoked> की प्रथम सूचना रिपोर्ट पंजीबद्ध कर "
        "अनुसंधान पश्चात् पुलिस रिपोर्ट प्रस्तुत करें।\n\n"
        "अंत में:\n"
        "  दिनांक :- <filing_date>                          प्रार्थी\n"
        "                                          <complainant_name> -- आवेदक\n"
        "                                                   द्वारा अभिभाषक\n"
        "                                          <advocate_name> -- एडवोकेट\n\n"
        "महत्वपूर्ण: 'आवेदक' (शिकायतकर्ता) व 'आरोपी' शब्दों का प्रयोग करें। 156(3) आवेदन के साथ "
        "शपथपत्र (Priyanka Srivastava निर्णय अनुसार अनिवार्य) संलग्न होता है — किन्तु वह पृथक भाग है, "
        "इसे यहाँ न जोड़ें।\n\n"
        "ENGLISH MODE (only if lang=en): mirror the same structure — 'IN THE COURT OF THE JUDICIAL "
        "MAGISTRATE FIRST CLASS, <district>', 'Complaint No. ___/<year>', complainant and accused "
        "blocks, title 'APPLICATION UNDER SECTION 156(3) Cr.P.C. (175(3) BNSS)', numbered 'That…' "
        "paragraphs in the same order with the police-inaction sequence (approached PS, written/"
        "registered-post applications, application to SP, no action taken) as the core, jurisdiction, "
        "and a prayer directing the police station to register the FIR and investigate. Use "
        "'complainant' and 'accused'."
    ),
    "example_prompts": [
        "थाना कोतवाली ने मेरी FIR दर्ज नहीं की 420, 406 IPC में, अब मजिस्ट्रेट कोर्ट जाना है",
        "Complaint u/s 156(3) — neighbours threatened with deadly weapons, police refused FIR",
    ],
}


PRODUCTION_WARRANT_91 = {
    "id":              "production_warrant_91",
    "name_en":         "Jail Production Warrant (Produce Accused from Custody)",
    "name_hi":         "जेल प्रोडक्शन वारंट आवेदन",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "procedural",
    "tier":            1,
    "popularity":      5,
    "quality":         "v2-ref",
    "description":     "Short application to produce an accused lodged in another jail / another case before the present court via a jail production warrant (पेशी वारंट), or for early hearing so he can appear from custody. Decoded verbatim from real MP filings — State-first अभियोगी/अभियुक्त caption, प्रार्थी voice, 'जेल प्रोडक्शन वारंट से तलब' / 'अभिलेखागार से तलब' idiom. NOTE: no §91 citation — that was a misnomer; §91 document-production is the separate production_documents_91_94 template.",
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
        "यह जेल प्रोडक्शन वारंट / पेशी वारंट हेतु एक संक्षिप्त प्रार्थना पत्र है — जब "
        "अभियुक्त किसी अन्य प्रकरण में दूसरी जेल/कारागार में निरुद्ध है और उसे वर्तमान "
        "प्रकरण में न्यायालय के समक्ष पेश कराना है। यह §91 दं.प्र.सं. (दस्तावेज़ तलबी) "
        "नहीं है — शीर्षक में कोई धारा-संख्या न लिखें। नीचे की संरचना वास्तविक MP "
        "filings से ली गई है — इसी क्रम व शब्दावली का कड़ाई से पालन करें।\n\n"
        "1. न्यायालय शीर्ष (केन्द्रित): court_name से — जैसे 'न्यायालय माननीय न्यायिक "
        "दण्डाधिकारी प्रथम श्रेणी <स्थान>' अथवा 'न्यायालय माननीय <क्रम> अपर सत्र "
        "न्यायाधीश महोदय <स्थान>'।\n"
        "2. प्रकरण पंक्ति: 'प्रकरण क्रमांक - <case_no>' (रजिस्टर-प्रकार सहित जैसे "
        "आर.सी.टी./एस.सी., यदि दिया हो)।\n"
        "3. पक्षकार ब्लॉक — राज्य पहले (दाण्डिक प्रकरण में अभियोजन प्रथम पक्ष):\n"
        "   '<राज्य> राज्य .......... अभियोगी'\n"
        "   केन्द्र में 'बनाम'\n"
        "   '<accused_name> [आदि] .......... अभियुक्त/अभियुक्तगण'\n"
        "4. शीर्षक — आवेदन का प्रयोजन-कथन (केन्द्रित, बिना किसी धारा-संख्या के): यदि "
        "अभियुक्त पहले से जेल में है व स्थाई वारंट पर स्वयं पेश होना चाहता है तो "
        "'आवेदन पत्र वास्ते शीघ्र सुनवाई।'; यदि उसे दूसरी जेल से तलब कराना है तो "
        "'आवेदन पत्र वास्ते जेल प्रोडक्शन वारंट से तलब किये जाने बावत्।' — purpose "
        "field के अनुसार उपयुक्त कथन चुनें।\n"
        "5. 'माननीय न्यायालय,' फिर 'प्रार्थी की ओर से प्रार्थना पत्र निम्न प्रकार "
        "प्रस्तुत है :-'\n"
        "6. क्रमांकित अनुच्छेद, प्रत्येक 'यहकि,' से प्रारम्भ:\n"
        "   (1) प्रार्थी का प्रकरण माननीय न्यायालय के समक्ष विचाराधीन है जिसमें दिनांक "
        "____ को प्रार्थी के विरुद्ध स्थाई/गिरफ्तारी वारंट जारी किया गया है।\n"
        "   (2) प्रार्थी वर्तमान में अन्य प्रकरण में <currently_at> में निरुद्ध है तथा "
        "उक्त प्रकरण में जेल प्रोडक्शन वारंट के माध्यम से न्यायालय के समक्ष उपस्थित होना "
        "चाहता है (अथवा उसी कारण नियत दिनांक को उपस्थित नहीं हो सका था)।\n"
        "   (3) उपरोक्त स्थिति में प्रार्थी को <currently_at> से जेल प्रोडक्शन वारंट "
        "द्वारा तलब किया जाकर/अभिरक्षा में लिया जाकर सुनवाई में लिया जाना न्यायोचित व "
        "न्याय संगत है।\n"
        "   (अन्तिम, यदि उपयुक्त) 'यहकि, शेष तर्क बहस के समय मौखिक रूप से निवेदित "
        "होंगे।'\n"
        "7. प्रार्थना (बिना किसी 'प्रार्थना'/'PRAYER' शीर्षक के, सीधे अनुच्छेद रूप में): "
        "'अत: श्रीमान न्यायालय से प्रार्थना है कि प्रार्थी की ओर से प्रस्तुत प्रार्थना "
        "पत्र स्वीकार कर <currently_at> से जेल प्रोडक्शन वारंट द्वारा प्रार्थी को तलब "
        "किया जाकर अभिरक्षा में लिये जाने (अथवा उक्त प्रकरण का अभिलेख अभिलेखागार से तलब "
        "कर आज दिनांक को सुनवाई में लिये जाने) का आदेश पारित करने की कृपा करें।'\n"
        "8. हस्ताक्षर ब्लॉक: 'दिनांक:- <filing_date>      प्रार्थी' फिर '<accused_name> "
        "पुत्र <accused_father>, आयु ___ वर्ष, निवासी ___ --- अभियुक्त' फिर 'द्वारा "
        "अभिभाषक <advocate_name>'।\n"
        "यह आवेदन आधे पृष्ठ का संक्षिप्त, यांत्रिक दस्तावेज़ है — कोई अतिरिक्त नाटकीयता "
        "नहीं।\n\n"
        "ENGLISH MODE (only if lang=en): mirror the same structure (a short, "
        "half-page application, NO section number in the title) — court header; "
        "'Case No. <case_no>'; State-first party block 'State of <State> ... Prosecution' "
        "/ 'Versus' / '<accused> ... Accused'; purpose-line title 'APPLICATION FOR "
        "EARLY HEARING' or 'APPLICATION TO SUMMON THE ACCUSED THROUGH JAIL PRODUCTION "
        "WARRANT'; 'That ...' paragraphs (a standing/arrest warrant was issued; the "
        "accused is presently lodged in <currently_at> in another case; he be summoned "
        "from that jail through a jail production warrant and taken into custody, or "
        "the record be called and the matter taken up today); a flowing prayer (NO "
        "'PRAYER' heading); signature 'Applicant' + accused particulars + 'through "
        "Advocate <advocate_name>'."
    ),
    "example_prompts": [
        "जेल प्रोडक्शन वारंट — मुवक्किल सेंट्रल जेल में अन्य प्रकरण में बंद, इस केस में पेशी हेतु तलब करना है",
        "Accused lodged in Mathura jail in another case; summon him here via jail production warrant and take into custody",
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
    "quality":         "v2-ref",
    "description":     "Application u/s 91 CrPC (94 BNSS) to call for / produce a document, CCTV footage, case diary, or other thing into the court record. Decoded verbatim from real MP filings — applicant-first आवेदक/अनावेदक caption, यहकि narrative, 'तलब किये जाने बावत्' purpose-line, prayer to तलब the item. Supporting शपथपत्र is a separate doc (general_affidavit).",
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
        "यह §91 दं.प्र.सं. / §94 भा.ना.सु.सं. का आवेदन है — किसी दस्तावेज़, सी.सी.टी.वी. "
        "फुटेज, केस डायरी अथवा अन्य वस्तु को न्यायालय के अभिलेख में तलब (call/produce) "
        "कराने हेतु। नीचे की संरचना वास्तविक MP filings से ली गई है — इसी क्रम व "
        "शब्दावली का कड़ाई से पालन करें।\n\n"
        "1. न्यायालय शीर्ष (केन्द्रित): court_name से — जैसे 'न्यायालय माननीय न्यायिक "
        "दण्डाधिकारी प्रथम श्रेणी <स्थान>' अथवा 'न्यायालय माननीय विशेष सत्र न्यायाधीश "
        "महोदय <(विशेष अधिनियम)> <स्थान>'।\n"
        "2. प्रकरण पंक्ति: 'प्रकरण क्रमांक- <case_no>'।\n"
        "3. पक्षकार ब्लॉक — आवेदक पहले (यह आवेदन आवेदक की ओर से है):\n"
        "   '<applicant_name> पुत्र/पुत्री श्री ____, आयु- ___ वर्ष, व्यवसाय- ____, "
        "निवासी- ____ .......... आवेदक/आवेदिका'\n"
        "   केन्द्र में 'बनाम'\n"
        "   '<राज्य> राज्य द्वारा पुलिस थाना ____ जिला ____ .......... अनावेदक'\n"
        "4. शीर्षक (केन्द्रित — कोई markup नहीं): या तो धारा-कथन 'आवेदन पत्र अन्तर्गत "
        "धारा 94 भा.ना.सु.सं. (91 दं.प्र.सं.)' अथवा प्रयोजन-कथन 'आवेदन पत्र वास्ते "
        "<वस्तु> तलब किये जाने बावत्।'\n"
        "5. 'माननीय न्यायालय,' (या 'माननीय महोदय,') फिर 'आवेदक/आवेदिका की ओर से आवेदन "
        "पत्र निम्न प्रकार प्रस्तुत है :-'\n"
        "6. क्रमांकित अनुच्छेद, प्रत्येक 'यहकि,' से प्रारम्भ — प्रकरण का संदर्भ; कौन-सा "
        "दस्तावेज़/फुटेज/केस-डायरी (documents_sought) किसके आधिपत्य में है (<custodian>, "
        "<custodian_address>); वह न्याय-निर्णय हेतु क्यों आवश्यक/प्रासंगिक है (relevance "
        "field); धारक उसे न्यायालयीन आदेश के बिना प्रस्तुत नहीं करेगा।\n"
        "7. प्रार्थना (बिना किसी 'प्रार्थना'/'PRAYER' शीर्षक के, सीधे अनुच्छेद रूप में): "
        "'अत: माननीय न्यायालय से निवेदन है कि <custodian> से <documents_sought> को तलब "
        "कर ... का आदेश पारित करने की कृपा करें।'\n"
        "8. हस्ताक्षर ब्लॉक: 'दिनांक:- <filing_date>      प्रार्थी/प्रार्थिनी' फिर "
        "'<applicant_name> - आवेदक/आवेदिका' फिर 'द्वारा अभिभाषक <advocate_name>'।\n"
        "नोट: इस आवेदन के समर्थन में शपथपत्र संलग्न होता है पर वह एक पृथक दस्तावेज़ है "
        "(general_affidavit) — इस आवेदन के मुख्य भाग में न जोड़ें।\n\n"
        "ENGLISH MODE (only if lang=en): mirror the same structure — court header; "
        "'Case No. <case_no>'; applicant-first party block '<applicant> ... Applicant' "
        "/ 'Versus' / 'State of <State> through P.S. ____ ... Non-applicant'; title "
        "'APPLICATION UNDER SECTION 94 BNSS (91 CrPC) TO CALL FOR <documents>'; 'That "
        "...' numbered paragraphs (case context; the documents/CCTV footage/case diary "
        "sought; that they are in the custody of <custodian> at <custodian_address>; "
        "their relevance to a just decision; the custodian will not produce them "
        "without a court order); a flowing prayer (NO 'PRAYER' heading) directing "
        "<custodian> to produce the listed documents/record; signature 'Applicant' + "
        "'through Advocate <advocate_name>'."
    ),
    "example_prompts": [
        "धारा 91 — पुलिस थाना से घटना के समय की सी.सी.टी.वी. फुटेज तलब कराना है, बचाव हेतु आवश्यक",
        "Call the case diary with the IO and bank statements from an SBI branch into the record in a 420 IPC case",
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
    "quality":         "v2-ref",
    "description":     "Application u/s 311 CrPC (348 BNSS) to summon / recall a material witness at the evidence stage — structure decoded verbatim from real MP filings (अभियोगी/अभियुक्तगण party block, प्रार्थी voice, यहकि paras: case fixed for evidence → witness material → bona fide, not for delay; title 'आवेदन पत्र अन्तर्गत धारा 311 दं.प्र.सं.').",
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
        "यह धारा 311 दं.प्र.सं. (348 भा.ना.सु.सं.) के अंतर्गत साक्षी को समन/पुनः बुलाकर साक्ष्य कराने "
        "हेतु एक संक्षिप्त आवेदन है। नीचे दी गई वास्तविक न्यायालयीन फाइलिंग संरचना का अक्षरशः पालन करें:\n\n"
        "शीर्ष (केन्द्र में):\n"
        "  न्यायालय माननीय <court_name> महोदय <जिला>  (सत्र हेतु '<क्रम> अपर सत्र न्यायाधीश', "
        "मजिस्ट्रेट हेतु 'न्यायिक दण्डाधिकारी प्रथम श्रेणी')\n"
        "  प्रकरण क्रमांक- <case_no> सत्रवाद/परिवाद\n\n"
        "पक्षकार-ब्लॉक (आपराधिक प्रकरण का मानक रूप):\n"
        "  <राज्य> शासन  ----  अभियोगी\n"
        "  केन्द्र में:  बनाम\n"
        "  <अभियुक्त का नाम> -----  अभियुक्तगण\n"
        "  (<applicant_role> के अनुसार आवेदन 'प्रार्थी' की ओर से होगा — अभियोजन हो तो शासन, बचाव हो "
        "तो अभियुक्त/आवेदक।)\n\n"
        "शीर्षक (केन्द्र में):\n"
        "  आवेदन पत्र अन्तर्गत धारा 311 दं.प्र.सं.\n\n"
        "प्रस्तावना:\n"
        "  माननीय महोदय,\n"
        "  प्रार्थी की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है :-\n\n"
        "कथानक — प्रत्येक अनुच्छेद 'यहकि,' से (वास्तविक, संक्षिप्त प्रवाह):\n"
        "  • यहकि, प्रार्थी का प्रकरण माननीय न्यायालय के समक्ष साक्ष्य हेतु नियत है।\n"
        "  • यहकि, साक्षी <witness_name> [निवासी <witness_address>] का परीक्षण आवश्यक है — कारण "
        "<necessity> (उदा. धारा 161 का कथन अभियोग पत्र में संलग्न है किन्तु ट्रायल प्रोग्राम में नाम "
        "त्रुटिवश रह गया / पुनः परीक्षण आवश्यक / दस्तावेज़ साबित कराना है)।\n"
        "  • यहकि, उक्त साक्षी प्रकरण का महत्वपूर्ण साक्षी है, जो <evidence_summary> बाबत् साक्ष्य "
        "देगा; प्रकरण के न्यायपूर्ण निराकरण हेतु उसकी साक्ष्य कराया जाना न्यायोचित व न्याय संगत है।\n"
        "  • यहकि, यह आवेदन सद्भावना पर आधारित है तथा विलम्ब हेतु नहीं, अत: स्वीकार किये जाने योग्य "
        "है।\n\n"
        "प्रार्थना (कोई अलग शीर्षक नहीं) — सीधे:\n"
        "  अत: श्रीमान जी से निवेदन है कि साक्षी <witness_name> की साक्ष्य कराये जाने हेतु आदेश पारित "
        "करने की कृपा करें।\n\n"
        "अंत में:\n"
        "  दिनांक :- <filing_date>                          प्रार्थी\n"
        "                                                   द्वारा अभिभाषक\n"
        "                                          <advocate_name> -- एडवोकेट\n\n"
        "ENGLISH MODE (only if lang=en): mirror the same short structure — court header + case number, "
        "'State of <State> … Prosecution / Versus / … Accused', title 'APPLICATION UNDER SECTION 311 "
        "Cr.P.C. (348 BNSS)', numbered 'That…' paragraphs (case fixed for evidence; the witness "
        "<witness_name> is material; what he/she will depose; the application is bona fide and not for "
        "delay — cf. Mohanlal Shamji Soni v. Union of India, (1991) 3 SCC), and a prayer to permit the "
        "witness's evidence. Use 'applicant/Prosecution/accused'."
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
    "quality":         "v2-ref",
    "description":     "Application u/s 320 CrPC (359 BNSS) for permission to compound an offence on the basis of a राजीनामा (compromise). Decoded verbatim from real MP filings — filed from the फरियादी side, 'समाज के प्रतिष्ठित लोगों द्वारा आपसी सहमति' recital, prayer for 'राजीनामा किये जाने की अनुमति', distinctive dual-signature block ('मुझे राजीनामा स्वीकार है' + accused). For non-compoundable offences it rides with a §482 HC quashing petition.",
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
        "यह राजीनामा (compromise) आवेदन पत्र है — असली MP फाइलिंग से verbatim decode किया गया। "
        "इसे फरियादी (complainant/शिकायतकर्ता) की ओर से प्रस्तुत किया जाता है, दोनों पक्षों की ओर से नहीं। "
        "बिल्कुल इसी ढाँचे में हिन्दी में लिखें:\n\n"
        "1. न्यायालय शीर्षक — केन्द्र में, जैसा <court_name> में दिया है "
        "(जैसे 'न्यायालय श्रीमान् मुख्य न्यायिक मजिस्ट्रेट महोदय, <स्थान>' या उच्च न्यायालय राजीनामे के साथ "
        "धारा 482 quashing के लिए हो तो 'उच्च न्यायालय <राज्य> खण्डपीठ <स्थान>')।\n"
        "2. प्रकरण पंक्ति — '<case_no>' तथा अपराध की धाराएँ '<sections>' (जैसे 'अपराध धारा 323, 294, 506 भा.द.वि.')।\n"
        "3. पक्षकार खण्ड (HC शैली, बहती हुई पंक्तियाँ) :\n"
        "   '<accused_name>' .......... आवेदक\n"
        "   'वि0)' (विरुद्ध)\n"
        "   '<राज्य> शासन व अन्य' .......... अनावेदकगण\n"
        "   (परिवादी <complainant_name> का नाम अनावेदक/फरियादी के रूप में पक्षकारों में रखें।)\n"
        "4. आरम्भिक पंक्ति : 'फरियादी की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है :-'\n"
        "5. शीर्षक — केन्द्र में, रेखांकित : 'आवेदन पत्र अन्तर्गत धारा 320 दं0 प्रक्रिया संहिता 1973' "
        "(यदि उपधारा लागू हो तो '320(2)')।\n"
        "6. 'यहकि,' से शुरू होने वाले क्रमांकित पैरा :\n"
        "   (1) उक्त प्रकरण फरियादी की रिपोर्ट पर पंजीबद्ध हुआ था / न्यायालय में विचाराधीन है;\n"
        "   (2) अब समाज के प्रतिष्ठित लोगों के बीच-बचाव/समझाइश से उभय पक्षों ने आपसी सहमति के आधार पर "
        "राजीनामा कर लिया है (<compromise_summary> के तथ्य यहाँ बुनें);\n"
        "   (3) फरियादी/पीड़ित पक्ष को आवेदक/अभियुक्त के विरुद्ध अब कोई शिकायत या आपत्ति शेष नहीं है, "
        "तथा वह स्वेच्छा से, बिना किसी दबाव या प्रलोभन के, राजीनामा कर रहा है (<voluntary_decl>);\n"
        "   (4) उभय पक्ष आपसी विवाद समाप्त कर शान्तिपूर्वक रहना चाहते हैं, अतः राजीनामा सद्भावना पर "
        "आधारित होकर स्वीकार योग्य है।\n"
        "7. प्रार्थना (बिना 'प्रार्थना' शीर्षक के, सीधे 'अतः' से) : माननीय न्यायालय से निवेदन है कि "
        "उभय पक्ष के मध्य हुए राजीनामे को स्वीकार कर राजीनामा किये जाने की अनुमति प्रदान करने की कृपा करें। "
        "(NOTE: prayer केवल 'राजीनामा किये जाने की अनुमति' की है — सीधे 'दोषमुक्त/उन्मोचित करें' मत लिखें; "
        "वह परिणाम न्यायालय राजीनामा स्वीकार होने पर स्वयं देता है।)\n"
        "8. विशिष्ट दोहरा-हस्ताक्षर खण्ड (यही इस दस्तावेज़ की पहचान है) — प्रार्थना के बाद यह पंक्ति : "
        "'मुझे उपरोक्त राजीनामा स्वीकार है।' फिर हस्ताक्षर :\n"
        "   1- (अभियोक्त्री/पीड़िता/परिवादी '<complainant_name>')\n"
        "   2- / 3- (अन्य फरियादीगण, यदि हों)\n"
        "   तदुपरान्त पृथक से अभियुक्त के हस्ताक्षर : '<accused_name> - अभियुक्त'\n"
        "   तथा 'अधिवक्ता <advocate_name>', स्थान '<place>', दिनांक '<filing_date>'।\n"
        "9. यदि अपराध असंज्ञेय/non-compoundable है (जैसे 376/POCSO/गम्भीर धाराएँ) तो यह राजीनामा अकेले "
        "मजिस्ट्रेट के समक्ष चलने योग्य नहीं — इसे उच्च न्यायालय में धारा 482 दं.प्र.सं. (528 BNSS) "
        "quashing याचिका के साथ संलग्न कर प्रस्तुत करें, यह आवेदन में स्पष्ट उल्लेख करें।\n\n"
        "ENGLISH MODE (only if lang=en): mirror the SAME structure in English — court header, case "
        "line with offence sections, applicant(=accused)/respondent(=State) party block, opening "
        "'The following application is submitted on behalf of the complainant:-', centred underlined "
        "title 'APPLICATION UNDER SECTION 320 CrPC 1973', 'That,'-numbered paragraphs (FIR/case "
        "registered → reputable members of society mediated → parties have compromised mutually of "
        "their own free will without coercion → complainant has no grievance left → compromise is "
        "bona fide and fit to be accepted), prayer ONLY to 'permit the compromise between the "
        "parties' (do NOT directly draft 'acquit/discharge'), then the same dual-endorsement block "
        "('I accept the above compromise.' signed by complainant/victim, then separately by the "
        "accused), advocate, place, date; and the same §482 HC-quashing note for non-compoundable "
        "offences. Plain text output, no markdown."
    ),
    "example_prompts": [
        "राजीनामा 323, 294, 506 भा.द.वि. में — मोहल्ले के बुजुर्गों की समझाइश से फरियादी और अभियुक्त में सुलह हो गई",
        "138 NI Act में राजीनामा आवेदन — अभियुक्त ने पूरी चेक राशि ब्याज सहित चुका दी, फरियादी को आपत्ति नहीं",
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
    "quality":         "v2-ref",
    "description":     "Application u/s 205 CrPC (228 BNSS) by an accused to be exempted from personal attendance and appear through counsel. Decoded verbatim from a real MP JMFC filing — state-first criminal caption (राज्य …अभियोगी / आरोपीगण), 'प्रार्थीगण/आरोपी की ओर से' opening, यहकि hardship narrative (age/illness/distance/dependant care), the key undertakings (अधिवक्ता प्रत्येक कार्यवाही हेतु तत्पर + 'जब भी आदेशित तब शब्दानुसार उपस्थित होंगे'), prayer 'व्यक्तिगत उपस्थिति माफ कर जरिये अभिभाषक उपस्थित मान्य'. No section number in the Hindi title beyond धारा 205 दं.प्र.सं.",
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
        "यह धारा 205 दं.प्र.सं. (228 भा.ना.सु.सं./BNSS) का व्यक्तिगत उपस्थिति से छूट हेतु आवेदन है — "
        "असली MP JMFC फाइलिंग से verbatim decode किया गया। हिन्दी में बिल्कुल इसी ढाँचे में लिखें:\n\n"
        "1. न्यायालय शीर्षक (केन्द्र में): 'न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी <स्थान>' "
        "(<court_name> के अनुसार)।\n"
        "2. प्रकरण पंक्ति: 'प्रकरण क्रमांक- <case_no>' (जैसे '129/2023 आर.सी.टी.')।\n"
        "3. पक्षकार खण्ड (criminal — राज्य पहले):\n"
        "   '<राज्य> राज्य' .......... अभियोगी\n"
        "   'बनाम'\n"
        "   '<accused_name> आदि' .......... आरोपीगण  (एक ही आरोपी हो तो 'आरोपी', एकवचन)\n"
        "4. शीर्षक (केन्द्र, रेखांकित): 'आवेदन पत्र अन्तर्गत धारा 205 दं.प्र.सं.' (BNSS में 'धारा 228 "
        "भा.ना.सु.सं.')। शीर्षक में इससे अधिक अंग्रेज़ी न जोड़ें।\n"
        "5. सम्बोधन + आरम्भ: 'माननीय महोदय,' फिर 'प्रार्थीगण/आरोपी की ओर से आवेदन पत्र निम्नानुसार "
        "प्रस्तुत है :-' (एक आरोपी हो तो 'प्रार्थी/आरोपी की ओर से')।\n"
        "6. 'यहकि,' से शुरू होने वाले क्रमांकित पैरा (असली क्रम):\n"
        "   (1) प्रार्थीगण के विरुद्ध उक्त प्रकरण विचाराधीन है जो [आज दिनांक को] साक्ष्य हेतु नियत है;\n"
        "   (2) कठिनाई का विस्तृत वर्णन — <hardship> को यहाँ बुनें (वृद्धावस्था/<accused_age>, गम्भीर "
        "बीमारी जैसे कैंसर/पैरालाइसिस, इलाजरत होना, आश्रित की 24-घंटे देखभाल, न्यायालय की दूरी "
        "जैसे दूरस्थ नगर से न्यायालय आना-जाना कठिन/जोखिमभरा); निष्कर्ष: 'ऐसी स्थिति में प्रार्थीगण को "
        "न्यायालय श्रीमान के समक्ष व्यक्तिगत उपस्थिति से उन्मुक्त किया जाना न्यायहित में आवश्यक है';\n"
        "   (3) UNDERTAKING-1: 'प्रार्थीगण के अधिवक्ता प्रत्येक कार्यवाही करने हेतु तत्पर हैं, प्रार्थीगण "
        "की अनुपस्थिति में न्यायालय द्वारा दिये जाने वाले आदेश का पालन नियत दिनांक को होता रहेगा';\n"
        "   (4) UNDERTAKING-2 (मुख्य): 'जब भी माननीय न्यायालय द्वारा प्रार्थीगण को व्यक्तिगत रूप से "
        "उपस्थित होने हेतु आदेशित किया जावेगा तब प्रार्थीगण द्वारा आदेश का पालन शब्दानुसार किया जावेगा';\n"
        "   (5) 'प्रस्तुत प्रार्थना पत्र सद्भावना पर आधारित होकर स्वीकार किये जाने योग्य है';\n"
        "   (6) 'उपरोक्त परिस्थिति और प्रकरण की प्रकृति को देखते हुये प्रार्थीगण को व्यक्तिगत उपस्थिति से "
        "[स्थाई रूप से] अभिमुक्ति प्रदान किया जाना न्याय संगत है'।\n"
        "7. प्रार्थना (बिना 'प्रार्थना' शीर्षक के, सीधे 'अत:' से): 'अत: श्रीमान जी से निवेदन है कि "
        "प्रार्थीगण के आवेदन पर सद्भावनापूर्वक विचार कर प्रार्थीगण की व्यक्तिगत उपस्थिति माफ कर जरिये "
        "अभिभाषक उपस्थित मान्य किये जाने का आदेश पारित करने की कृपा करें।'\n"
        "8. हस्ताक्षर: 'दिनांक- <filing_date>' दाहिनी ओर 'प्रार्थीगण' फिर सभी आरोपियों के नाम पंक्तिवार, "
        "'-- आरोपीगण', फिर 'द्वारा अभिभाषक' और '<advocate_name> - एडवोकेट'।\n\n"
        "ENGLISH MODE (only if lang=en): mirror the SAME structure in English — 'IN THE COURT OF THE "
        "JUDICIAL MAGISTRATE FIRST CLASS, <place>' header; 'Case No. <case_no>'; state-first caption "
        "'State of <State> …Prosecution / Versus / <accused_name> & ors …Accused'; centred underlined "
        "title 'APPLICATION UNDER SECTION 205 CrPC'; 'To the Hon'ble Court,' + 'The following "
        "application is submitted on behalf of the applicant-accused:-'; 'That,'-numbered paragraphs "
        "(case pending and fixed for evidence → detailed hardship from <hardship> → conclusion that "
        "exemption is necessary in the interest of justice → undertaking that counsel is ready for "
        "every proceeding and orders will be complied with in the applicant's absence → undertaking "
        "to appear in person whenever directed → application is bona fide → permanent exemption is "
        "just); prayer 'It is therefore prayed that the personal attendance of the applicant be "
        "exempted and appearance through counsel be permitted'; signature 'Applicant / Accused, "
        "through counsel <advocate_name>'. Plain text output, no markdown."
    ),
    "example_prompts": [
        "धारा 205 आवेदन — आरोपी 68 वर्ष का, कैंसर पीड़ित, पत्नी पैरालाइसिस से ग्रस्त, दूरस्थ नगर से न्यायालय आना असंभव",
        "धारा 205 — 138 NI Act प्रकरण, आरोपी बैंगलोर में व्यवसाय करता है, हर तारीख पर आना कठिन, जरिये अभिभाषक उपस्थिति की छूट चाहिए",
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
    "quality":         "v2-ref",
    "description":     "Application u/s 451/457 CrPC (497/503 BNSS) for interim custody (सुपुर्दगी) of a vehicle / property / jewellery seized by police and lying at the थाना, pending disposal. Decoded verbatim from real MP filings — applicant-first आवेदक/अनावेदक caption, 'सुपुर्दगी' case-line suffix, deterioration ground, Sundarbhai Ambalal Desai (AIR 2003 SC 638) authority, undertakings (no sale/alteration, produce on demand) — NOT a bail bond.",
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
        "यह §451/§457 दं.प्र.सं. (§497/§503 भा.ना.सु.सं.) का सुपुर्दगी आवेदन है — किसी "
        "अपराध में पुलिस द्वारा जप्त वाहन/संपत्ति/आभूषण को प्रकरण के निराकरण तक स्वामी "
        "को अंतरिम सुपुर्दगी पर दिलाने हेतु। नीचे की संरचना वास्तविक MP filings से ली "
        "गई है — इसी क्रम व शब्दावली का कड़ाई से पालन करें।\n\n"
        "1. न्यायालय शीर्ष (केन्द्रित): court_name से — जैसे 'न्यायालय माननीय न्यायिक "
        "दण्डाधिकारी प्रथम श्रेणी <स्थान>' अथवा 'न्यायालय माननीय विशेष न्यायाधीश महोदय "
        "<(विशेष अधिनियम)> <स्थान>'।\n"
        "2. प्रकरण पंक्ति: 'अपराध क्रमांक- <case_no_or_fir> सुपुर्दगी आवेदन' (case-line के "
        "अंत में 'सुपुर्दगी' अवश्य लिखें)।\n"
        "3. पक्षकार ब्लॉक — आवेदक पहले:\n"
        "   '<applicant_name> पुत्र/पत्नी श्री ____, आयु- ___ वर्ष, व्यवसाय- ____, "
        "निवासी- <applicant_address> .......... आवेदक/आवेदिका'\n"
        "   केन्द्र में 'बनाम'\n"
        "   '<राज्य> शासन द्वारा पुलिस थाना <police_station> जिला ____ .......... अनावेदक'\n"
        "4. शीर्षक (केन्द्रित — कोई markup नहीं): 'आवेदन पत्र अन्तर्गत धारा 451, 457 "
        "द0प्र0सं0' (यदि BNSS शैली अपेक्षित हो तो 'धारा 497, 503 भा0ना0सु0सं0')।\n"
        "5. 'माननीय महोदय,' फिर 'आवेदक/आवेदिका की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत "
        "है :-'\n"
        "6. क्रमांकित अनुच्छेद, प्रत्येक 'यहकि,' से प्रारम्भ:\n"
        "   (1) प्रार्थी <property_desc> का पंजीकृत/वैध स्वामी है (ownership_proof — आर.सी./"
        "विक्रय-पत्र/दस्तावेज़ प्रार्थी के पास मौजूद)।\n"
        "   (2) उक्त संपत्ति को पुलिस थाना <police_station> द्वारा अपराध क्रमांक "
        "<case_no_or_fir> अन्तर्गत धारा ____ में दिनांक <seizure_date> को जप्त कर थाने पर "
        "रखा गया है।\n"
        "   (3) प्रार्थी की उक्त अपराध में कोई संलिप्तता नहीं है / संपत्ति झूठा फंसाई गई है "
        "(प्रकरण के तथ्यानुसार)।\n"
        "   (4) जप्तशुदा संपत्ति थाने पर खुली अवस्था में पड़ी है जिसके दिन-प्रतिदिन खराब/"
        "नष्ट होने व साक्ष्यिक मूल्य समाप्त होने की पूर्ण संभावना है (वाहन मूल्यहीन हो "
        "जाएगा / आभूषण खुर्द-बुर्द हो सकते हैं)।\n"
        "   (5) माननीय सर्वोच्च न्यायालय द्वारा सुन्दरभाई अम्बालाल देसाई बनाम गुजरात राज्य, "
        "ए.आई.आर. 2003 एस.सी. 638 में प्रतिपादित सिद्धांतानुसार जप्तशुदा वाहन/संपत्ति "
        "प्रकरण के निराकरण तक स्वामी को सुपुर्दगी पर दी जा सकती है।\n"
        "   (6) सुपुर्दगी पर दिये जाने की दशा में प्रार्थी संपत्ति का विक्रय नहीं करेगा, न "
        "ही रंग-रूप में कोई परिवर्तन करेगा, तथा न्यायालय द्वारा तलब करने पर स्वयं के व्यय "
        "पर उसे प्रस्तुत करेगा एवं समस्त अधिरोपित शर्तों का अक्षरश: पालन करेगा।\n"
        "   (अन्तिम) 'यहकि, अन्य तर्क वक्त बहस मौखिक रूप से निवेदित किये जावेंगे।'\n"
        "7. प्रार्थना (बिना किसी 'प्रार्थना'/'PRAYER' शीर्षक के, सीधे अनुच्छेद रूप में): 'अत: "
        "श्रीमान न्यायालय से निवेदन है कि आवेदन स्वीकार कर [पुलिस थाना <police_station> से "
        "अपराध क्रमांक <case_no_or_fir> की केस डायरी मय कैफियत तलब कर] जप्तशुदा "
        "<property_desc> को प्रकरण के निराकरण तक प्रार्थी को सुपुर्दगी पर दिये जाने का आदेश "
        "पारित करने की कृपा करें।'\n"
        "8. हस्ताक्षर ब्लॉक: 'दिनांक:- <filing_date>      प्रार्थी' फिर '<applicant_name> -- "
        "आवेदक/आवेदिका' फिर 'द्वारा अभिभाषक <advocate_name>'।\n"
        "नोट: समर्थन में शपथपत्र पृथक दस्तावेज़ है (general_affidavit) — इसमें न जोड़ें। "
        "सुपुर्दगी प्रतिभूति/जमानत-बंध पर नहीं, बल्कि शर्तों/वचनबद्धता पर दी जाती है।\n\n"
        "ENGLISH MODE (only if lang=en): mirror the same structure — court header; "
        "'Crime No. <case_no_or_fir> — Supurdgi Application'; applicant-first party block "
        "'<applicant> ... Applicant' / 'Versus' / 'State of <State> through P.S. "
        "<police_station> ... Non-applicant'; title 'APPLICATION UNDER SECTION 451, 457 "
        "CrPC (497, 503 BNSS)'; 'That ...' numbered paragraphs (applicant is the registered "
        "owner of <property_desc> with valid documents <ownership_proof>; seized by "
        "<police_station> in Crime No. <case_no_or_fir> on <seizure_date>; no involvement / "
        "falsely implicated; the property lies open at the police station and is "
        "deteriorating / losing evidentiary value; per Sundarbhai Ambalal Desai v. State of "
        "Gujarat, AIR 2003 SC 638 seized property may be released on supurdgi to the owner "
        "pending trial; undertakings — will not sell or alter it, will produce it whenever "
        "the court directs, and will abide by all conditions); a flowing prayer (NO 'PRAYER' "
        "heading) to release the property on supurdgi pending disposal; signature "
        "'Applicant' + 'through Advocate <advocate_name>'. Supurdgi rests on "
        "undertakings/conditions, NOT on a bail-style bond + sureties."
    ),
    "example_prompts": [
        "सुपुर्दगी — 34(2) आबकारी में जप्त बुलेरो, मुवक्किल पंजीकृत स्वामी, वाहन थाने पर खराब हो रहा",
        "Release seized gold mangalsutra & earrings to the complainant-owner on supurdgi — lying in the malkhana",
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
    "quality":         "v2-ref",
    "description":     "Criminal complaint under §138 of the Negotiable Instruments Act for dishonour of cheque — structure decoded verbatim from real MP JMFC filings (अभियोगी/अभियुक्त idiom, full यहकि narrative, साक्ष्य सूची).",
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
        "Reproduce the EXACT structure of a real MP Judicial-Magistrate §138 परिवाद पत्र "
        "(decoded verbatim from the advocate's filings). In Hindi mode the whole document is "
        "Devanagari; refer to the complainant as 'अभियोगी' and the accused as 'अभियुक्त'. "
        "Do NOT write any English heading (no 'IN THE COURT OF', no 'COMPLAINT UNDER SECTION', "
        "no 'PRAYER'/'VERIFICATION'/'LIST OF DOCUMENTS'). Structure:\n"
        "1. Court header, centred: 'न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी <जिला>' "
        "   (from court_name; if blank use a blank line — never invent).\n"
        "2. Case line: 'प्रकरण क्रमांक- ________ /<वर्ष>            परिवाद पत्र'.\n"
        "3. Complainant block (flowing line, NOT label:value): "
        "'<अभियोगी का नाम> पुत्र <पिता>, आयु- ____ वर्ष, व्यवसाय- ________, निवासी- <पता> (<राज्य>)' "
        "   then on the right '----- अभियोगी'.\n"
        "4. Centred 'बनाम'.\n"
        "5. Accused block (flowing): '<अभियुक्त का नाम> पुत्र ________, निवासी- <अभियुक्त का पता> "
        "(<राज्य>)' then on the right '--- अभियुक्त'.\n"
        "6. Centred title: 'परिवाद पत्र अन्तर्गत धारा 138 परक्राम्य लिखित अधिनियम' "
        "   (no §142, no English — the frontend styles it bold/underlined).\n"
        "7. 'माननीय न्यायालय,' then 'अभियोगी की ओर से अभियोग पत्र निम्न प्रकार प्रस्तुत है :-'\n"
        "8. Numbered paragraphs, each opening 'यहकि,' — follow the real fact-flow:\n"
        "   (1) पक्षकारों के मध्य सम्बन्ध (पारिवारिक/मित्रवत/व्यावसायिक) तथा मूल लेन-देन — अभियुक्त ने "
        "       अभियोगी से <underlying_debt के अनुसार तिथि> को नगद <cheque_amount> (शब्दों में भी) "
        "       प्राप्त की व नियत तिथि पर लौटाने का वादा किया.\n"
        "   (2) मांग पर अभियुक्त ने भुगतान दायित्व स्वीकार करते हुये अपने खाते वाली बैंक <drawee_bank> "
        "       का चैक क्रमांक <cheque_no> राशि <cheque_amount> दिनांकित <cheque_date>, स्वयं के "
        "       हस्ताक्षरयुक्त, इस आश्वासन के साथ प्रदान किया कि वैध अवधि में प्रस्तुत करने पर भुगतान "
        "       प्राप्त हो जाएगा.\n"
        "   (3) अभियोगी ने उक्त चैक अपने खाते वाली बैंक ________ में दिनांक <deposit_date> को भुगतान "
        "       हेतु प्रस्तुत किया, परन्तु चैक बिना भुगतान के दिनांक <return_date> को, मय रिटर्न मेमो, "
        "       '<return_reason>' (अपर्याप्त निधि / खाता बन्द आदि) की टीप सहित वापिस प्राप्त हुआ.\n"
        "   (4) अनादरण पर अभियोगी ने अपने अभिभाषक के माध्यम से दिनांक <notice_date> को अभियुक्त के पते "
        "       पर रजिस्टर्ड ए.डी. से सूचना पत्र भेजा कि प्राप्ति के 15 दिवस के अन्दर चैक राशि का "
        "       भुगतान करे.\n"
        "   (5) सूचना पत्र अभियुक्त को दिनांक <notice_delivery> को प्राप्त/तामील हुआ "
        "       (यदि अभियुक्त ने तामील से बचने हेतु लौटवाया हो तो डाक टीप 'तलाश करने पर व्यक्ति नहीं मिला' "
        "       सहित विधिक रूप से तामील/deemed-service का उल्लेख करें); फिर भी भुगतान नहीं किया.\n"
        "   (6) वाद कारण: नोटिस की 15-दिवसीय अवधि <notice_delivery + 15 दिन> को पूर्ण हुई, अगले दिन से "
        "       वाद कारण उत्पन्न होकर आज दिनांक तक निरन्तर जारी है; अभियुक्त ने आज तक भुगतान नहीं किया.\n"
        "   (7) अभियुक्त ने उक्त चैक अपने विधिक दायित्वों के उन्मोचन में दिया था व भुगतान हेतु विधिक "
        "       रूप से उत्तरदायी है.\n"
        "   (8) अभियुक्त ने अवैध हानि पहुँचाने व स्वयं को अवैध लाभ के उद्देश्य से, यह जानते हुये कि खाते "
        "       में पर्याप्त राशि नहीं है (या चैक पर खाते से भिन्न हस्ताक्षर हैं), छलपूर्वक चैक दिया; उक्त "
        "       कृत्य निगोसियेबल इंस्ट्रूमेंट एक्ट की धारा 138 के तहत दण्डनीय अपराध की श्रेणी में आता है.\n"
        "   (9) क्षेत्राधिकार: अभियोगी का बैंक खाता <अभियोगी की प्रस्तुतकर्ता बैंक/शाखा — blank रखें यदि "
        "       उपलब्ध न हो> में होने के कारण श्रीमान न्यायालय को श्रवणाधिकार एवं विचारण क्षेत्राधिकार "
        "       प्राप्त है तथा उक्त अपराध श्रीमान न्यायालय के विचारण योग्य है.\n"
        "   (10) उक्त विवादित चैक के सम्बन्ध में अभियोगी ने अभियुक्त के विरुद्ध भारत वर्ष के किसी भी अन्य "
        "        न्यायालय में कोई अभियोग पत्र प्रस्तुत नहीं किया है, न लंबित है, न विचाराधीन है.\n"
        "9. Prayer — NO separate heading; begin 'अत: माननीय महोदय से निवेदन है कि' — अभियुक्त के विरुद्ध "
        "   धारा 138 निगोसियेबल इंस्ट्रूमेंट एक्ट के तहत अपराध का संज्ञान लेकर अभियुक्त को तलब कर, "
        "   सख्त से सख्त अधिकतम दण्ड से दण्डित करने तथा चैक क्रमांक <cheque_no> दिनांकित <cheque_date> "
        "   राशि <cheque_amount> से दुगनी राशि क्षतिपूर्ति के रूप में अभियोगी को अभियुक्त से दिलाये जाने "
        "   का आदेश पारित करने की कृपा करें.\n"
        "10. 'दिनांक:- <filing_date>' (बाएँ) तथा दाहिनी ओर 'प्रार्थी' / '<advocate_name>' / "
        "    '<अभियोगी का नाम> --- अभियोगी'.\n"
        "11. 'साक्ष्य सूची' heading, then witnesses, one per line: 'अभियोगी स्वयं कथन करेगा।' / "
        "    'अभियोगी की बैंक से सम्बन्धित अधिकारी/कर्मचारी मय रिकॉर्ड' / 'अभियुक्त की बैंक से सम्बन्धित "
        "    अधिकारी' / 'सूचना पत्र को पोस्ट करने वाला एवं रजिस्ट्री की डिलेवरी रिपोर्ट देने वाला सम्बन्धित "
        "    डाक विभाग अधिकारी' / 'अन्य साक्षी प्रकरण के विचारण के दौरान श्रीमान न्यायालय की अनुमति से "
        "    प्रस्तुत किये जावेंगे।'\n"
        "12. Repeat 'दिनांक:- <filing_date>' (बाएँ) तथा दाहिनी ओर 'प्रार्थी' / "
        "    '<अभियोगी का नाम> -- अभियोगी'.\n"
        "Note: the affidavit (शपथपत्र) is a SEPARATE document in real practice — do NOT append it here. "
        "Dates and amounts must be exact. Plain-text output only.\n"
        "ENGLISH MODE: produce the faithful English equivalent of this same structure — 'IN THE COURT "
        "OF THE JUDICIAL MAGISTRATE FIRST CLASS, <district>'; Complainant '... COMPLAINANT' / 'Versus' "
        "/ Accused '... ACCUSED'; title 'COMPLAINT UNDER SECTION 138 OF THE NEGOTIABLE INSTRUMENTS ACT, "
        "1881'; 'The complainant most respectfully submits as under:'; numbered 'That ...' paragraphs in "
        "the same order; 'LIST OF WITNESSES'; prayer to take cognizance, summon and try the accused, "
        "award maximum sentence and compensation of twice the cheque amount; date + 'Complainant' twice."
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
    "quality":         "v2-ref",
    "description":     "Application under §12 of the Protection of Women from Domestic Violence Act, 2005 — structure decoded verbatim from real MP JMFC filings (व्यथित/प्रत्यर्थीगण idiom, यहकि narrative, the five section-wise reliefs §17/§18/§19/§20/§22, पूर्व मुकदमेंबाजी का ब्योरा, §19(8) स्त्रीधन वापसी).",
    "fields": [
        {"key": "court_name",        "label_en": "Court (JMFC / district)",        "label_hi": "न्यायालय / जिला",          "type": "text",     "required": True,  "section": "court"},
        {"key": "aggrieved_name",    "label_en": "Aggrieved woman (व्यथिता)",       "label_hi": "व्यथिता (पीड़ित महिला)",     "type": "name",     "required": True,  "section": "applicant"},
        {"key": "aggrieved_father",  "label_en": "Father's name",                  "label_hi": "पिता का नाम",              "type": "name",     "required": True,  "section": "applicant"},
        {"key": "aggrieved_age",     "label_en": "Age",                            "label_hi": "आयु",                      "type": "text",     "required": False, "section": "applicant"},
        {"key": "aggrieved_address", "label_en": "Current address",                "label_hi": "वर्तमान पता",                "type": "address",  "required": True,  "section": "applicant"},
        {"key": "respondent_name",   "label_en": "Respondent(s) — husband + in-laws", "label_hi": "प्रत्यर्थीगण (पति व ससुरालीजन)", "type": "name",  "required": True,  "section": "respondent"},
        {"key": "respondent_relation","label_en": "Relationship with aggrieved",   "label_hi": "व्यथिता से संबंध",          "type": "text",     "required": True,  "section": "respondent"},
        {"key": "respondent_address","label_en": "Respondent address",             "label_hi": "प्रत्यर्थीगण का पता",        "type": "address",  "required": True,  "section": "respondent"},
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
        "यह आवेदन घरेलू हिंसा से महिलाओं का संरक्षण अधिनियम 2005 की धारा 12 के अंतर्गत "
        "न्यायिक दण्डाधिकारी प्रथम श्रेणी (JMFC) के समक्ष प्रस्तुत होता है। नीचे दी गई वास्तविक "
        "न्यायालयीन फाइलिंग संरचना का अक्षरशः पालन करें:\n\n"
        "शीर्ष (केन्द्र में):\n"
        "  न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी <court_name>\n"
        "  प्रकरण क्रमांक- ______ /<वर्ष> घरेलू हिंसा\n\n"
        "पक्षकार-ब्लॉक (बहती पंक्तियों में — कोई बुलेट/नम्बर नहीं):\n"
        "  श्रीमती <aggrieved_name> पत्नी श्री <पति का नाम> पुत्री श्री <aggrieved_father>, "
        "आयु- <aggrieved_age> वर्ष, व्यवसाय- गृहणी, निवासी- <aggrieved_address> (<राज्य>)\n"
        "  दाहिनी ओर:  --- व्यथित\n"
        "  केन्द्र में:  बनाम\n"
        "  प्रत्यर्थीगण प्रायः एक से अधिक होते हैं (पति + सास/ससुर/ननद/जेठ आदि)। <respondent_name> "
        "में दिये प्रत्येक व्यक्ति को क्रमांक देकर पृथक पंक्ति में लिखें: '<नाम> पुत्र/पत्नी श्री "
        "<...>, आयु- __ वर्ष, व्यवसाय- ___'; फिर साझा पता-पंक्ति 'निवासीगण- <respondent_address> "
        "(<राज्य>)'; फिर दाहिनी ओर '----- प्रत्यर्थीगण'। प्रत्यर्थी क्रमांक-01 सदैव पति होता है।\n\n"
        "शीर्षक (केन्द्र में):\n"
        "  आवेदन पत्र अन्तर्गत धारा 12 घरेलू हिंसा से महिलाओं का संरक्षण अधिनियम 2005\n\n"
        "प्रस्तावना:\n"
        "  माननीय न्यायालय,\n"
        "  व्यथित की ओर से आवेदन निम्न प्रकार प्रस्तुत है :-\n\n"
        "कथानक — प्रत्येक अनुच्छेद 'यहकि,' से प्रारम्भ हो; वास्तविक प्रवाह इस क्रम में:\n"
        "  • यहकि, व्यथित का विवाह प्रत्यर्थी क्रमांक-01 के साथ हिन्दू रीति-रिवाज से <marriage_date> "
        "को सम्पन्न हुआ।\n"
        "  • यहकि, विवाह में व्यथित के माता-पिता ने माँग अनुसार दहेज (गृहस्थी का सामान + सोने-चाँदी "
        "के जेवर + नगद) दिया।\n"
        "  • यहकि, विवाह के पश्चात् प्रत्यर्थीगण कम दहेज का ताना देकर अतिरिक्त दहेज की माँग करने लगे।\n"
        "  • यहकि, व्यथित द्वारा मायके में बताने पर समझाइश दी गई, किन्तु प्रताड़ना बढ़ती गई — विशिष्ट "
        "माँग (नगद राशि + वाहन) व धमकियाँ (<violence_narrative> से तिथिवार, विशिष्ट घटनाएँ भरें)।\n"
        "  • यहकि, प्रत्यर्थीगण ने मारपीट कर व्यथित को घर से निकाल दिया तथा उसका समस्त स्त्रीधन छीन "
        "लिया (तिथि सहित)।\n"
        "  • यहकि, व्यथित ने महिला थाना/पुलिस में शिकायत की, परामर्श कराया गया, एवं धारा 498ए आदि की "
        "प्रथम सूचना रिपोर्ट लेखबद्ध हुई (अपराध क्रमांक यदि ज्ञात हो)।\n"
        "  • यहकि, ससुरालीजन ने उपेक्षा कर भरण-पोषण की कोई व्यवस्था नहीं की (<shelter_status>)।\n"
        "  • यहकि, व्यथित की स्वयं की कोई आय नहीं है तथा वह असहाय स्थिति में मायके में निवासरत है।\n"
        "  • यहकि, प्रत्यर्थी क्रमांक-01 की आय <income_husband> है — भरण-पोषण की क्षमता दर्शाने हेतु।\n\n"
        "अनुतोष (DV आवेदन का केन्द्रीय भाग) — पंक्ति 'व्यथित, प्रत्यर्थीगण से निम्न प्रकार के अनुतोष "
        "प्राप्त करने की अधिकारणी है :-' के बाद प्रत्येक धारा का पृथक ब्लॉक लिखें (<reliefs_sought> से "
        "राशि/विवरण भरें):\n"
        "  धारा 17 के अनुसार अनुतोष :- शामिलाती कौटुम्बिक गृह में निवास का अधिकार।\n"
        "  धारा 18 के अनुसार संरक्षा आदेश :- घरेलू हिंसा से संरक्षण।\n"
        "  धारा 19 के अनुसार निवास का आदेश :- निवास हेतु प्रतिभूति व बंधपत्र।\n"
        "  धारा 20 के अनुसार मोद्रिक अनुतोष :- भरण-पोषण हेतु ₹______ मासिक।\n"
        "  धारा 22 के अनुसार प्रतिकर आदेश :- शारीरिक/मानसिक प्रताड़ना हेतु ₹______ क्षतिपूर्ति।\n\n"
        "पूर्व मुकदमेंबाजी का ब्योरा :- कोई पूर्व/लंबित प्रकरण (हि.वि.अधि. धारा 9/13, 498ए FIR आदि)।\n"
        "  • यहकि, धारा 19(8) के तहत प्रत्यर्थीगण के कब्जे से व्यथित का स्त्रीधन (जेवर + नगद) दिलाया जावे।\n"
        "  • वाद-कारण: अंतिम बार घर से निकाले जाने/साथ रखने से इंकार की तिथि से उत्पन्न होकर "
        "दिन-प्रतिदिन जारी है।\n"
        "  • क्षेत्राधिकार: व्यथित वर्तमान में जिस थाना-क्षेत्र में निवासरत है उसके आधार पर माननीय "
        "न्यायालय को श्रवणाधिकार व क्षेत्राधिकार प्राप्त है।\n\n"
        "प्रार्थना (कोई अलग 'PRAYER' शीर्षक नहीं) — सीधे:\n"
        "  अत: माननीय न्यायालय से निवेदन है कि व्यथित का आवेदन पत्र स्वीकार कर व्यथित को प्रत्यर्थीगण "
        "से आवेदन में चाही गई सहायता एवं अनुतोष दिलाया जाकर प्रत्यर्थीगण को व्यथित के साथ किये गये "
        "आपराधिक कृत्य के लिये दण्डित किये जाने का आदेश पारित करने की कृपा करें।\n\n"
        "अंत में:\n"
        "  दिनांक :- <filing_date>                          व्यथित\n"
        "                                                   <aggrieved_name>\n"
        "                                                   -- व्यथित\n"
        "  (<advocate_name> उपलब्ध हो तो अधिवक्ता-पंक्ति भी जोड़ें।)\n\n"
        "महत्वपूर्ण: केवल 'व्यथित' (पीड़ित महिला) तथा 'प्रत्यर्थीगण' (पति व ससुरालीजन) शब्दों का प्रयोग "
        "करें — 'आवेदिका/अनावेदक/अभियुक्त' का नहीं। शपथपत्र अलग दस्तावेज़ है — इसे यहाँ न जोड़ें।\n\n"
        "ENGLISH MODE (only if lang=en): mirror the very same structure — 'IN THE COURT OF THE "
        "JUDICIAL MAGISTRATE FIRST CLASS, <district>', 'Case No. ___/<year> (Domestic Violence)', "
        "aggrieved-person and numbered respondent(s) blocks, title 'APPLICATION UNDER SECTION 12 OF "
        "THE PROTECTION OF WOMEN FROM DOMESTIC VIOLENCE ACT, 2005', numbered 'That…' paragraphs in the "
        "same narrative order, the five section-wise reliefs (S.17 residence in shared household, S.18 "
        "protection order, S.19 residence order, S.20 monetary relief, S.22 compensation), "
        "prior-litigation details, S.19(8) return of stridhan, cause of action, jurisdiction, and a "
        "prayer beginning 'It is therefore most respectfully prayed…'. Use 'aggrieved person' and "
        "'respondent(s)'."
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
    "court_label_hi":  "कुटुम्ब न्यायालय",
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
        "1. Cause-title (centred, bold), from the court_name field: in Hindi "
        "render the MP family-court form 'न्यायालय माननीय प्रधान न्यायाधीश, "
        "कुटुम्ब न्यायालय, <court_name> (म.प्र.)'; in English 'IN THE FAMILY "
        "COURT OF <court_name>'.\n"
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
        "OUTPUT IS HINDI (Devanagari) BY DEFAULT (English only if lang='en'). "
        "Match the कुटुम्ब-न्यायालय family format: case line 'प्रकरण क्रमांक "
        "____/<वर्ष>'; petitioner as 'याचिकाकर्ता/याचिकाकर्ती' (full descriptor), "
        "'बनाम', spouse as 'अनावेदक/अनावेदिका'; title 'याचिका अन्तर्गत धारा 9 हिन्दू "
        "विवाह अधिनियम, 1955 (दाम्पत्य अधिकारों की पुनर्स्थापना हेतु)'; then "
        "'याचिकाकर्ता की ओर से याचिका निम्न प्रकार प्रस्तुत है :-' and 'यह कि' paras "
        "(हिन्दू रीति से विवाह, साथ निवास, अनावेदक/अनावेदिका का बिना उचित कारण अलग "
        "होना, मेल-मिलाप के प्रयास, याचिकाकर्ता का साथ रखने व भरण-पोषण को तत्पर "
        "होना); prayer for a 'दाम्पत्य अधिकारों की पुनर्स्थापना की डिक्री'; then "
        "'सत्यापन' + signature. Tone: civil, dignified. Plain text."
    ),
    "example_prompts": [
        "S.9 HMA — wife left for her parents' house 6 months ago, refusing to return",
        "Restitution petition for husband whose wife left without cause after 2 years of marriage",
    ],
}


HMA_13_DIVORCE = {
    "id":              "hma_13_divorce",
    "name_en":         "Divorce Petition (Hindu Marriage Act §13 / §13B)",
    "name_hi":         "विवाह विच्छेद याचिका (हिन्दू विवाह अधिनियम धारा 13 / 13B)",
    "court":           "family",
    "court_label_en":  "Family Court",
    "court_label_hi":  "कुटुम्ब न्यायालय",
    "category":        "family",
    "tier":            2,
    "popularity":      3,
    "quality":         "v2-ref",
    "description":     "Petition under §13 Hindu Marriage Act for विवाह विच्छेद (dissolution of marriage). Decoded verbatim from a real MP Family Court filing — कुटुम्ब न्यायालय header, full पत्नी/पुत्री identity party block, 'आवेदिका की ओर से आवेदन पत्र निम्नानुसार प्रस्तुत है', यहकि narrative of क्रूरता/दहेज, cause-of-action + 'दुरभि संधि नहीं' + न्याय शुल्क + क्षेत्राधिकार recitals, lettered prayer (डिग्री व जयपत्र: विवाह विच्छेद + स्त्रीधन वापसी + स्थाई निर्वाहिका + वाद व्यय), सत्यापन block. §13 = contested fault grounds (one spouse); §13B = mutual-consent JOINT petition. Advocate-appointment under §13 Family Courts Act is a SEPARATE doc.",
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
        "यह हिन्दू विवाह अधिनियम धारा 13 के अन्तर्गत विवाह विच्छेद (divorce) याचिका है — असली MP "
        "कुटुम्ब न्यायालय फाइलिंग से verbatim decode की गई। <petition_type> के अनुसार दो रूप हैं:\n"
        "  • धारा 13 (contested) — एक पक्ष दूसरे के विरुद्ध किसी आधार (क्रूरता/परित्याग/व्यभिचार आदि) पर। "
        "यही नीचे का मुख्य ढाँचा है।\n"
        "  • धारा 13B (mutual consent) — दोनों पति-पत्नी का संयुक्त आवेदन (कम से कम 1 वर्ष से अलग रह रहे "
        "हों); पक्षकार 'संयुक्त आवेदकगण', स्वेच्छा व आपसी सहमति पर ज़ोर, कोई दोषारोपण नहीं।\n\n"
        "हिन्दी में बिल्कुल इसी ढाँचे में लिखें:\n\n"
        "1. न्यायालय शीर्षक (केन्द्र में): 'न्यायालय माननीय प्रधान न्यायाधीश कुटुम्ब न्यायालय <जिला>' "
        "(<court_name> के अनुसार)।\n"
        "2. प्रकरण पंक्ति: 'प्रकरण क्रमांक - ______ हि.वि.अधि.' (<case_no> के अनुसार)।\n"
        "3. पक्षकार खण्ड (बहती हुई पूर्ण-परिचय पंक्तियाँ, संक्षिप्त नहीं):\n"
        "   'श्रीमती <petitioner_name> पत्नी श्री <respondent_name>, पुत्री श्री ____, आयु- __ वर्ष, "
        "व्यवसाय- ____, निवासी- ____, हाल निवासी- ____' .......... आवेदिका\n"
        "   'बनाम'\n"
        "   '<respondent_name> पुत्र श्री ____, आयु- __ वर्ष, व्यवसाय- ____, निवासी- ____' .......... अनावेदक\n"
        "   (यदि याचिकाकर्ता पति है तो भूमिकाएँ उलट दें — आवेदक / अनावेदिका; धारा 13B में दोनों "
        "'संयुक्त आवेदकगण'।)\n"
        "4. शीर्षक (केन्द्र, रेखांकित): 'आवेदन पत्र अन्तर्गत धारा 13 हिन्दू विवाह अधिनियम' "
        "(13B में: 'संयुक्त आवेदन पत्र अन्तर्गत धारा 13B हिन्दू विवाह अधिनियम')।\n"
        "5. सम्बोधन + आरम्भ: 'माननीय न्यायालय,' फिर 'आवेदिका की ओर से आवेदन पत्र निम्नानुसार प्रस्तुत है-'\n"
        "6. 'यहकि,' से शुरू होने वाले क्रमांकित पैरा (असली क्रम):\n"
        "   (1) आवेदिका का विवाह अनावेदक के साथ हिन्दू रीति-रिवाज अनुसार दिनांक <marriage_date> को "
        "<marriage_place> में सम्पन्न हुआ;\n"
        "   (2)-(अनेक) विवाह उपरान्त के तथ्य व आधार — <grounds> को विस्तृत यहकि पैरा में बुनें "
        "(दहेज मांग, मारपीट, शराब, क्रूरता, झूठी शिकायतें आदि — दिनांकवार घटनाएँ); संतान हो तो "
        "<children> का उल्लेख (नाम, आयु, वर्तमान में किसके पास);\n"
        "   • निष्कर्ष पैरा: अनावेदक का व्यवहार विवाह के बाद से क्रूरतापूर्ण रहा, इसी कारण आवेदिका को "
        "अनावेदक के विरुद्ध विवाह विच्छेद याचिका प्रस्तुत करना आवश्यक हुआ है;\n"
        "   • वाद कारण पैरा: <separation_date> को घर से निकालने/साथ रखने से इंकार से 'वाद कारण जारी "
        "होकर दिन-प्रतिदिन व्याप्त है';\n"
        "   • 'यहकि, आवेदिका व अनावेदक के मध्य कोई दुरभि संधि नहीं है।' (no collusion — अनिवार्य);\n"
        "   • 'यहकि, विवाह विच्छेद की डिग्री प्राप्त करने हेतु आवेदिका द्वारा निश्चित न्याय शुल्क के साथ "
        "आवेदन पत्र प्रस्तुत है।';\n"
        "   • क्षेत्राधिकार पैरा: विवाह जहाँ सम्पन्न हुआ / आवेदिका के वर्तमान निवास / अन्तिम बार साथ "
        "रखने से इंकार के आधार पर 'माननीय न्यायालय को आवेदन पत्र का श्रवणाधिकार व क्षेत्राधिकार प्राप्त है'।\n"
        "   (धारा 13B में, आधार-पैरा की जगह: दोनों पक्ष स्वेच्छा से, बिना दबाव, आपसी सहमति से अलग होना "
        "चाहते हैं; 1 वर्ष से पृथक रह रहे हैं; गुजारा/संतान अभिरक्षा/स्त्रीधन की आपसी settlement।)\n"
        "7. प्रार्थना (बिना 'प्रार्थना' शीर्षक के, सीधे 'अत:' से): 'अत: माननीय न्यायालय से प्रार्थना है कि "
        "आवेदिका के हित में अनावेदक के विरुद्ध निम्न आशय की डिग्री व जयपत्र प्रदान किया जावे।' फिर "
        "अक्षरांकित उप-प्रार्थनाएँ:\n"
        "   'अ-' विवाह दिनांक <marriage_date> को विच्छेदित कर विवाह विच्छेद की डिग्री प्रदान की जावे;\n"
        "   'ब-' आवेदिका को अनावेदक से उसका सम्पूर्ण स्त्रीधन व घर-गृहस्थी का सामान वापस दिलाया जावे;\n"
        "   'स-' आवेदिका को स्थाई निर्वाहिका (permanent alimony) के रूप में राशि दिलाई जावे;\n"
        "   'द-' वाद व्यय व अन्य न्यायोचित सहायता।\n"
        "   (पति-आवेदक हो तो स्त्रीधन/निर्वाहिका वाले खण्ड हटा दें; 13B में: संयुक्त सहमति से विवाह "
        "विच्छेद की डिग्री + तय settlement की पुष्टि।)\n"
        "8. हस्ताक्षर: 'दिनांक:- <filing_date>' दाहिनी ओर 'प्रार्थिनी / श्रीमती <petitioner_name> - "
        "आवेदिका' (अधिवक्ता <advocate_name>)।\n"
        "9. सत्यापन खण्ड: 'मैं श्रीमती <petitioner_name> ... शपथपूर्वक सत्यापित करती हूँ कि उपरोक्त "
        "आवेदन पत्र के पद क्रमांक- 1 लगायत <N> मय प्रार्थना (अ, ब, स, द) में वर्णित समस्त तथ्य मेरे निजी "
        "ज्ञान व जानकारी से सत्य व सही हैं, तथा कानूनी अंश मेरे अभिभाषक द्वारा दी गई जानकारी के आधार पर "
        "सत्य व सही हैं; कुछ भी असत्य नहीं है और न ही कुछ छिपाया गया है।' फिर 'दिनांक:- ____' तथा "
        "'हस्ताक्षर सत्यापनकर्ता'।\n"
        "(NOTE: अभिभाषक नियुक्ति हेतु धारा 13 कुटुम्ब न्यायालय अधिनियम का आवेदन एक अलग दस्तावेज़ है — "
        "इस याचिका में सम्मिलित न करें।)\n\n"
        "ENGLISH MODE (only if lang=en): mirror the SAME structure in English — 'IN THE COURT OF THE "
        "PRINCIPAL JUDGE, FAMILY COURT, <district>' header; 'H.M.A. Case No. ___ of <year>'; "
        "full-identity flowing party block (wife W/o, D/o, age, occupation, residence) marked "
        "'…APPLICANT' / 'Versus' / '…NON-APPLICANT'; centred underlined title 'APPLICATION UNDER "
        "SECTION 13 OF THE HINDU MARRIAGE ACT' (or 'JOINT APPLICATION UNDER SECTION 13B …' for "
        "mutual consent); 'To the Hon'ble Court,' + 'The following application is submitted on behalf "
        "of the applicant:-'; 'That,'-numbered paragraphs (marriage solemnised per Hindu rites on "
        "date/place → dated cruelty/dowry narrative + children → conclusion that cohabitation is "
        "impossible → cause of action accrued and continuing → no collusion between the parties → "
        "requisite court fee paid → jurisdiction); prayer opening 'It is therefore prayed that a "
        "decree and certificate be granted in favour of the applicant against the non-applicant to "
        "the following effect:-' with lettered sub-prayers (a) decree of divorce dissolving the "
        "marriage dated …, (b) return of all स्त्रीधन/dowry articles, (c) permanent alimony, "
        "(d) costs; signature 'Applicant'; then a Verification ('I … do hereby verify on oath that "
        "the contents of paragraphs 1 to N together with the prayer are true and correct to my "
        "personal knowledge …') + 'Signature of Deponent'. Plain text output, no markdown."
    ),
    "example_prompts": [
        "धारा 13 तलाक — पत्नी की ओर से पति के विरुद्ध, दहेज प्रताड़ना व क्रूरता, 13-11-2022 को घर से निकाला, स्त्रीधन व निर्वाहिका चाहिए",
        "धारा 13B आपसी सहमति तलाक — दोनों पति-पत्नी 14 माह से अलग, कोई संतान नहीं, गुजारा settlement तय",
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
    "quality":         "v2-ref",
    "description":     "Court शपथपत्र that accompanies an application (bail, record-call, signature-permission, etc.). Format decoded verbatim from real MP filings — court header + case line + short party block, 'शपथ पत्र' title, deponent identity list (नाम/पिता/आयु/व्यवसाय/निवासी), 'मैं शपथ पूर्वक सत्य कथन करता हूँ कि' oath, यहकि paras, then a सत्यापन block. NO stamp-paper line, NO notary attestation.",
    "fields": [
        {"key": "court_or_authority","label_en": "Court",                            "label_hi": "न्यायालय",     "type": "text",     "required": True,  "section": "court", "hint": "Court where the main application is filed, e.g. 'JMFC, <place>' / 'Sessions Judge, <place>'"},
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
        "यह एक शपथपत्र (sworn affidavit) है जैसा अदालतों में आवेदन के साथ "
        "संलग्न किया जाता है। नीचे की संरचना वास्तविक MP filings से ली गई है — इसी क्रम "
        "व शब्दावली का कड़ाई से पालन करें। महत्वपूर्ण: कोई 'गैर-न्यायिक स्टांप पेपर' "
        "पंक्ति नहीं, कोई 'समक्ष/BEFORE' पंक्ति नहीं, कोई नोटरी attestation ब्लॉक नहीं — "
        "यह एक न्यायालयीन शपथपत्र है।\n\n"
        "1. न्यायालय शीर्ष (केन्द्रित): court_or_authority से — जैसे 'न्यायालय माननीय "
        "न्यायिक दण्डाधिकारी प्रथम श्रेणी <स्थान>' अथवा 'न्यायालय माननीय प्रधान सत्र "
        "न्यायाधीश महोदय <स्थान>'।\n"
        "2. प्रकरण पंक्ति: 'प्रकरण क्रमांक ____ / <वर्ष>' (क्रमांक ज्ञात न हो तो रिक्त रेखा "
        "छोड़ें)।\n"
        "3. संक्षिप्त पक्षकार ब्लॉक (शपथपत्र में संक्षिप्त रहता है):\n"
        "   '<सम्बन्धित आवेदक का नाम> .......... आवेदक'\n"
        "   केन्द्र में 'वि0)'\n"
        "   '<राज्य> राज्य .......... अभियोगी'  (प्रकरण अनुसार)\n"
        "4. शीर्षक (केन्द्रित — frontend स्वतः रेखांकित+बोल्ड करता है, कोई markup नहीं): "
        "'शपथ पत्र'।\n"
        "5. शपथकर्ता परिचय — सूची रूप में, प्रत्येक अलग पंक्ति में '<लेबल> :- <मान>':\n"
        "   'नाम :- <deponent_name>'\n"
        "   'पिता का नाम :- <deponent_father>'\n"
        "   'आयु :- <deponent_age> वर्ष'\n"
        "   'व्यवसाय :- <deponent_occupation>'\n"
        "   'निवासी :- <deponent_address>'\n"
        "6. शपथ-वाक्य (परिचय के नीचे): 'मैं शपथ पूर्वक सत्य कथन करता/करती हूँ कि :-'\n"
        "7. क्रमांकित अनुच्छेद, प्रत्येक 'यहकि,' से प्रारम्भ — subject के आधार पर वे तथ्य "
        "जिनकी शपथ ली जा रही है (declarations field से)। जमानत-शपथपत्र की दशा में प्रथम "
        "अनुच्छेद यह घोषणा करता है कि शपथकर्ता उक्त प्रकरण में आवेदक/आरोपी है व समान आशय "
        "का कोई जमानत आवेदन उच्चतम/उच्च/अधीनस्थ न्यायालय में लंबित या निराकृत नहीं है; "
        "अन्तिम अनुच्छेद पैरवी हेतु नियुक्त अभिभाषक का उल्लेख कर सकता है।\n"
        "8. दिनांक + दायीं ओर हस्ताक्षर पंक्ति: 'दिनांक :- <filing_date>      हस्ताक्षर "
        "शपथकर्ता'।\n"
        "9. सत्यापन ब्लॉक — पृथक शीर्षक 'सत्यापन', फिर: 'मैं शपथकर्ता शपथपूर्वक सत्यापित "
        "करता/करती हूँ कि शपथपत्र के पद क्रमांक 1 लगायत <N> में दी गई जानकारी मेरे ज्ञान व "
        "विश्वास से सत्य व सही है जिसमें कुछ भी छुपाया नहीं गया है और न ही असत्य कथन किया "
        "गया है।' — फिर 'दिनांक :- <filing_date>      हस्ताक्षर सत्यापनकर्ता'।\n"
        "विषय (subject) केवल यह तय करने हेतु है कि कौन-से तथ्यों की शपथ ली जाए — इसे "
        "अलग 'विषय:/Re:' पंक्ति के रूप में न छापें।\n\n"
        "ENGLISH MODE (only if lang=en): mirror the same structure — court header "
        "(NO 'on stamp paper' line, NO notary block), 'Case No. ___ / <year>', short "
        "party block ending '... Applicant' / 'Versus' / 'State of <State> ... "
        "Prosecution'; title 'AFFIDAVIT'; deponent identity as a vertical list (Name / "
        "Father's name / Age / Occupation / Resident of); oath line 'I, the deponent, "
        "do hereby state on solemn affirmation that:'; numbered 'That ...' paragraphs "
        "of the sworn facts; 'Signature of Deponent' with date; then a 'VERIFICATION' "
        "heading and 'I, the deponent, verify on oath that the contents of paragraphs "
        "1 to <N> are true and correct to my knowledge and belief, nothing has been "
        "concealed and nothing false has been stated therein.'; 'Signature of "
        "Verifier' with date."
    ),
    "example_prompts": [
        "शपथपत्र — प्रथम जमानत आवेदन के साथ, शपथकर्ता आरोपी, समान आशय का कोई आवेदन लंबित नहीं",
        "Affidavit supporting a record-call application — deponent is the applicant, swears the documents are genuine",
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
        {"key": "advocate_court",    "label_en": "Practising court line",          "label_hi": "न्यायालय पंक्ति",            "type": "text",     "required": False, "section": "letterhead", "hint": "e.g. उच्च न्यायालय खण्डपीठ <स्थान>"},
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
        "(<advocate_court>, e.g. 'उच्च न्यायालय खण्डपीठ <स्थान>'); and 'मोबा- <advocate_mobile>'. "
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
        {"key": "court_name",        "label_en": "Court (JMFC / CJM + place)",     "label_hi": "न्यायालय (न्यायिक मजिस्ट्रेट + स्थान)", "type": "text", "required": True, "section": "court", "hint": "e.g. न्यायिक दण्डाधिकारी प्रथम श्रेणी, <स्थान>"},
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
        {"key": "court_name",        "label_en": "Court (where application is pending)", "label_hi": "न्यायालय (जहाँ आवेदन लंबित है)", "type": "text", "required": True, "section": "court", "hint": "e.g. न्यायिक दण्डाधिकारी प्रथम श्रेणी, <स्थान> / कुटुम्ब न्यायालय"},
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


# Wrapper — links to the dedicated §498A परिवाद complaint page. Deterministic,
# format-perfect bilingual (NO LLM for layout): the EN/हिं toggle is an instant
# client-side re-render and the cause-title sits in the right half of the page
# exactly as filed. Layout decoded verbatim from a real Gwalior JMFC filing.
COMPLAINT_498A = {
    "id":              "complaint_498a",
    "name_en":         "Complaint — Cruelty & Dowry (S.498A/377 IPC + DP Act)",
    "name_hi":         "परिवाद पत्र — क्रूरता व दहेज (धारा 498ए/377 भा.द.वि. + दहेज प्रतिषेध अधिनियम)",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "family",
    "tier":            1,
    "popularity":      5,
    "quality":         "v1-wrapper",
    "description":     (
        "Private complaint before a Judicial Magistrate First Class for matrimonial "
        "cruelty and dowry harassment (S.498A/377 IPC & 3/4 Dowry Prohibition Act). "
        "Opens the dedicated परिवाद drafter — deterministic, format-perfect bilingual "
        "(instant EN/हिं toggle, cause-title in the right half exactly as filed) with "
        "server-side PDF. Layout decoded verbatim from a real Gwalior JMFC filing."
    ),
    "redirect_url":    "/draft/complaint",
    "fields": [],
    "format_spec":     "",  # rendered client-side by /draft/complaint
    "example_prompts": [
        "498ए परिवाद पत्र — ससुराल वालों द्वारा दहेज हेतु क्रूरता, ग्वालियर JMFC में",
        "Section 498A complaint against husband and in-laws for dowry cruelty",
        "परिवाद पत्र धारा 498ए, 377 व 3/4 दहेज प्रतिषेध अधिनियम",
    ],
}


# ============================================================================
# AGGREGATE — used by compose_templates.py to merge into TEMPLATES dict
# ============================================================================

# -------------------------------------------------------------------------
# §138(b) NI Act — the ACCUSED's application to dismiss a cheque-bounce
# complaint where the statutory demand notice was never served / the postal
# proof is fabricated. (Distinct from NI_ACT_138, which is the complaint.)
# Decoded verbatim from the advocate's real JMFC-Gwalior filings
# (Sharif Khan 902/2025, HDFC 1674/2021, Lakshminarayan 478/2021) and
# rendered DETERMINISTICALLY in the browser — see buildNi138bDoc in
# static/draft-template.html. No LLM touches this document.
# -------------------------------------------------------------------------
NI_138B_DISMISS = {
    "id":              "ni_138b_dismiss",
    "name_en":         "§138(b) NI Act — Dismiss Complaint (notice not served)",
    "name_hi":         "धारा 138(ख) NI Act — परिवाद निरस्तीकरण आवेदन",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "commercial",
    "tier":            1,
    "popularity":      4,
    "quality":         "v2-ref",
    "engine":          "deterministic",
    "description":     "Accused's application under §138(b) NI Act to dismiss the cheque-bounce complaint where the statutory demand notice was never served / the postal proof is forged. Mirrored verbatim from real JMFC Gwalior filings; rendered instantly in-browser (no AI).",
    "fields": [
        {"key": "court_name",       "label_en": "Court / Bench",                       "label_hi": "न्यायालय / पीठ",                       "type": "text", "required": True,  "section": "court",   "hint": "e.g. माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी, ग्वालियर"},
        {"key": "case_no",          "label_en": "Case no. (प्रकरण क्रमांक)",            "label_hi": "प्रकरण क्रमांक",                        "type": "text", "required": True,  "section": "court",   "hint": "e.g. 902/2025"},
        {"key": "complainant_name", "label_en": "Complainant (परिवादी)",                "label_hi": "परिवादी",                              "type": "name", "required": True,  "section": "parties"},
        {"key": "accused_name",     "label_en": "Accused / Applicant (अभियुक्त)",       "label_hi": "अभियुक्त / प्रार्थी",                  "type": "name", "required": True,  "section": "parties"},
        {"key": "notice_date",      "label_en": "Notice date claimed by complainant",   "label_hi": "नोटिस/प्राप्ति दिनांक (परिवादी द्वारा दर्शित)","type": "text", "required": True, "section": "matter", "hint": "जैसा परिवादी ने दर्शाया — e.g. 12-01-2021"},
        {"key": "post_office",      "label_en": "Post office where item was received",  "label_hi": "डाकघर (जहाँ आइटम रिसीव हुआ)",          "type": "text", "required": True,  "section": "matter",  "hint": "e.g. अशोकनगर हैड ऑफिस / मोहना सब-ऑफिस"},
        {"key": "advocate_name",    "label_en": "Advocate(s)",                          "label_hi": "अधिवक्ता",                             "type": "text", "required": True,  "section": "filing",  "hint": "e.g. विष्णु शिवहरे, धारासिंह मीणा"},
        {"key": "filing_date",      "label_en": "Date",                                 "label_hi": "दिनांक",                               "type": "text", "required": True,  "section": "filing",  "hint": "e.g. 18/02/2026"},
    ],
    "format_spec": "Rendered deterministically client-side (ni_138b_dismiss) — no LLM. See buildNi138bDoc() in static/draft-template.html.",
}


# ============================================================================
# PROPOSED (quality="proposed") — v0 gap-fill from the courtbook coverage map.
# NOT YET advocate-reviewed and NOT anchored to a real filed petition, so the
# format is from standard practice, not from Vishnu ji's filings (skill rule 1).
# Goes live as a clearly-flagged v0 for testing; upgrade to a reviewed,
# filing-anchored template (like bail/discharge) before relying on it. Leading
# authorities are CANDIDATES for the cite-at-hearing list — verify before use,
# never baked into the draft body (skill rule 2). reviewed: false (skill rule 5).
# ============================================================================
MOTOR_ACCIDENT_CLAIM_166 = {
    "id":              "motor_accident_claim_166",
    "name_en":         "Motor Accident Claim (MACT — S.166 MV Act)",
    "name_hi":         "मोटर दुर्घटना दावा (धारा 166 मो.या.अ.)",
    "court":           "procedural",   # cross-court rail; a dedicated Tribunal rail is a follow-up
    "court_label_en":  "Common",
    "court_label_hi":  "सामान्य",
    "category":        "procedural",
    "tier":            2,
    "popularity":      4,
    "quality":         "proposed",     # v0 — pending advocate review (not filing-anchored)
    "description":     (
        "v0 PROPOSAL (pending advocate review — format not yet anchored to a real "
        "filed MACT petition). Claim petition before the Motor Accidents Claims "
        "Tribunal under S.166 MV Act, 1988, for compensation in a road-accident "
        "death or injury. Claimant(s) / legal representatives vs driver, owner and "
        "insurer; compensation built on the standard heads (loss of dependency × "
        "age-multiplier, future prospects, conventional heads). Sarla Verma / "
        "Pranay Sethi are flagged to cite at hearing — verify, do not bake in."
    ),
    "fields": [
        {"key": "tribunal",          "label_en": "Tribunal / Court",                "label_hi": "अधिकरण / न्यायालय",        "type": "text",     "required": True,  "section": "court", "hint": "e.g. 'मोटर दुर्घटना दावा अधिकरण, <स्थान>' / 'Motor Accidents Claims Tribunal, <place>'"},
        {"key": "claim_no",          "label_en": "Claim Case No. (if allotted)",    "label_hi": "दावा प्रकरण क्रमांक",       "type": "text",     "required": False, "section": "court"},
        {"key": "claim_nature",      "label_en": "Injury or death claim",           "label_hi": "चोट या मृत्यु का दावा",      "type": "text",     "required": True,  "section": "matter", "hint": "'injury' (victim alive) or 'death' (claim by legal heirs)"},
        {"key": "claimant_name",     "label_en": "Claimant(s) / legal heirs",       "label_hi": "आवेदकगण / विधिक उत्तराधिकारी", "type": "name",   "required": True,  "section": "applicant", "hint": "Injured person, or the dependents/LRs of the deceased — one per line"},
        {"key": "claimant_details",  "label_en": "Claimant parentage / age / occupation / residence", "label_hi": "आवेदक पिता / आयु / व्यवसाय / निवास", "type": "longtext", "required": True, "section": "applicant"},
        {"key": "deceased_name",     "label_en": "Deceased / victim name",          "label_hi": "मृतक / पीड़ित का नाम",       "type": "name",     "required": False, "section": "applicant", "hint": "For death claims: the deceased; relationship of each claimant"},
        {"key": "accident_datetime", "label_en": "Date & time of accident",         "label_hi": "दुर्घटना दिनांक व समय",       "type": "text",     "required": True,  "section": "facts"},
        {"key": "accident_place",    "label_en": "Place of accident",               "label_hi": "दुर्घटना स्थान",             "type": "text",     "required": True,  "section": "facts"},
        {"key": "accident_facts",    "label_en": "How the accident happened",       "label_hi": "दुर्घटना किस प्रकार हुई",     "type": "longtext", "required": True,  "section": "facts", "hint": "Manner of accident + rash/negligent driving by the offending driver"},
        {"key": "vehicle_number",    "label_en": "Offending vehicle no. (+ type)",  "label_hi": "दोषी वाहन क्रमांक (+ प्रकार)", "type": "text",   "required": True,  "section": "facts"},
        {"key": "fir_details",       "label_en": "FIR no. / police station",        "label_hi": "एफ.आई.आर. क्र. / थाना",      "type": "text",     "required": False, "section": "facts"},
        {"key": "injury_or_death",   "label_en": "Injuries / death + treatment",    "label_hi": "चोटें / मृत्यु एवं उपचार",    "type": "longtext", "required": True,  "section": "matter", "hint": "Nature of injuries, hospital/MLC, or fatality + post-mortem"},
        {"key": "victim_age",        "label_en": "Age of victim (for multiplier)",  "label_hi": "पीड़ित की आयु (गुणक हेतु)",   "type": "text",     "required": True,  "section": "matter"},
        {"key": "victim_income",     "label_en": "Income of victim (monthly/annual)", "label_hi": "पीड़ित की आय (मासिक/वार्षिक)", "type": "text",  "required": True,  "section": "matter", "hint": "With proof basis if any; drives loss-of-dependency"},
        {"key": "respondent_driver", "label_en": "Respondent 1 — driver",           "label_hi": "अनावेदक 1 — चालक",          "type": "name",     "required": False, "section": "respondent"},
        {"key": "respondent_owner",  "label_en": "Respondent 2 — owner",            "label_hi": "अनावेदक 2 — स्वामी",         "type": "name",     "required": True,  "section": "respondent"},
        {"key": "respondent_insurer","label_en": "Respondent 3 — insurer + policy", "label_hi": "अनावेदक 3 — बीमाकर्ता + पॉलिसी", "type": "longtext", "required": True, "section": "respondent"},
        {"key": "compensation_claimed","label_en": "Total compensation claimed (₹)", "label_hi": "कुल दावाकृत प्रतिकर (₹)",   "type": "text",     "required": True,  "section": "prayer"},
        {"key": "interest_rate",     "label_en": "Interest rate sought (%)",        "label_hi": "ब्याज दर (%)",               "type": "text",     "required": False, "section": "prayer", "hint": "Default ~6–9% p.a. from date of petition"},
        {"key": "advocate_name",     "label_en": "Advocate's name",                 "label_hi": "अधिवक्ता का नाम",            "type": "name",     "required": True,  "section": "filing"},
        {"key": "place",             "label_en": "Place",                           "label_hi": "स्थान",                     "type": "text",     "required": True,  "section": "filing"},
        {"key": "filing_date",       "label_en": "Date",                            "label_hi": "दिनांक",                     "type": "date",     "required": True,  "section": "filing"},
    ],
    "format_spec": (
        "Draft a claim petition under Section 166 of the Motor Vehicles Act, 1988 before the "
        "Motor Accidents Claims Tribunal. Output Hindi (Devanagari) by default; English mirror "
        "only if the user asks. Plain text, no markdown. Any unknown value → an underline blank "
        "(________). NOTE: this is a v0 structure from standard practice — keep idiom neutral; the "
        "exact court formatting will be replaced once anchored to a real filed petition.\n\n"
        "STRUCTURE (follow in order):\n"
        "1. HEADER (centred): 'मोटर दुर्घटना दावा अधिकरण <tribunal> के समक्ष' (EN: 'BEFORE THE MOTOR "
        "ACCIDENTS CLAIMS TRIBUNAL, <tribunal>').\n"
        "2. CASE LINE: 'दावा प्रकरण क्रमांक <claim_no> / <वर्ष>' (leave blank if not allotted).\n"
        "3. PARTIES: list each claimant from <claimant_name> with <claimant_details> ending "
        "'.......... आवेदक/आवेदकगण'; then centred 'विरुद्ध'; then respondents — '1. <respondent_driver> "
        "(चालक)', '2. <respondent_owner> (स्वामी)', '3. <respondent_insurer> (बीमाकर्ता)' ending "
        "'.......... अनावेदकगण'.\n"
        "4. TITLE: 'धारा 166 मोटर यान अधिनियम, 1988 के अंतर्गत प्रतिकर हेतु दावा आवेदन-पत्र' and the total "
        "claimed '(कुल ₹ <compensation_claimed>)'.\n"
        "5. JURISDICTION para: accident occurred within the Tribunal's territorial limits and/or the "
        "claimant resides / respondent resides within jurisdiction (S.166(2)).\n"
        "6. FACTS, numbered 'यह कि': (a) date/time <accident_datetime> and place <accident_place>; "
        "(b) manner of accident and that it was caused by the rash and negligent driving of vehicle "
        "<vehicle_number> by respondent no.1 (from <accident_facts>); (c) FIR particulars <fir_details>.\n"
        "7. INJURY/DEATH para: nature of injuries or the death, treatment / MLC / post-mortem (from "
        "<injury_or_death>); for death, the deceased <deceased_name> and each claimant's relationship "
        "and dependency.\n"
        "8. INCOME & DEPENDENCY: age <victim_age> and income <victim_income>; compute compensation on "
        "the SETTLED HEADS — loss of dependency (income, less personal-living deduction by family size, "
        "× the age-appropriate multiplier), future prospects, and the conventional heads (loss of "
        "estate, funeral expenses, loss of consortium) for death; or medical expenses, loss of earning, "
        "pain & suffering, special diet/attendant for injury. State these as the standard method; do NOT "
        "assert any specific case citation in the body.\n"
        "9. LIABILITY: respondent-driver negligent, respondent-owner vicariously liable, and respondent-"
        "insurer liable to indemnify under a valid policy.\n"
        "10. COMPUTATION: a head-wise list of the amounts totalling <compensation_claimed>.\n"
        "11. PRAYER: award of ₹<compensation_claimed> with interest @ <interest_rate>% p.a. from the date "
        "of the petition, plus costs, jointly and severally against the respondents.\n"
        "12. Then 'स्थान: <place>   दिनांक: <filing_date>' and a right-side 'आवेदकगण द्वारा अधिवक्ता "
        "<advocate_name>' signature line; followed by a verification ('सत्यापन') that the contents are "
        "true to knowledge, and a short list of documents relied upon (FIR, MLC/PM report, income proof, "
        "vehicle & policy particulars).\n\n"
        "ENGLISH MODE (lang=en): mirror the same structure with standard MACT English idiom — 'BEFORE THE "
        "MOTOR ACCIDENTS CLAIMS TRIBUNAL …', 'Claim Petition under Section 166 of the Motor Vehicles Act, "
        "1988', parties as Applicant(s) / Versus / Respondents (Driver, Owner, Insurer), the same numbered "
        "facts, dependency computation, liability, prayer, verification and document list."
    ),
    "example_prompts": [
        "मोटर दुर्घटना दावा — मृतक की पत्नी व बच्चों द्वारा, ट्रक से टक्कर, धारा 166 मो.या.अ.",
        "MACT claim under S.166 for grievous injury — rash driving by a bus, claim against owner and insurer",
    ],
}


# V2-native tiles — the forum variants the catalogue was missing. The canonical
# discharge/appeal engines already render both forums; these expose them as
# court-wise tiles so the magistrate §239 discharge (the common warrant-case one,
# Vishnu ji's "Arvind Sharma" filing) and the appeal-to-Sessions (against a
# Magistrate conviction) are reachable from the drafting home. Both redirect
# straight into the universal editor → template_adapter → canonical render.
DISCHARGE_APPLICATION_MAGISTRATE = {
    "id":              "discharge_application_magistrate",
    "name_en":         "Discharge — Magistrate (S.262 BNSS / 239 CrPC)",
    "name_hi":         "उन्मोचन — मजिस्ट्रेट (धारा 262 BNSS / 239 दं.प्र.सं.)",
    "court":           "magistrate",
    "court_label_en":  "Magistrate Court",
    "court_label_hi":  "मजिस्ट्रेट न्यायालय",
    "category":        "bail",
    "tier":            2,
    "popularity":      4,
    "quality":         "v2",
    "description":     "Discharge before the Magistrate in a warrant case on police report (S.262 BNSS / 239 CrPC) — no prima facie case made out. Canonical deterministic draft.",
    "redirect_url":    "/draft/template/discharge_magistrate",
    "fields":          [],
    "format_spec":     "",
    "example_prompts": [
        "मजिस्ट्रेट न्यायालय में धारा 239 दं.प्र.सं. के अंतर्गत उन्मोचन आवेदन",
        "Discharge before JMFC under S.239 CrPC — charge-sheet discloses no offence",
    ],
}


APPEAL_CONVICTION_SESSIONS = {
    "id":              "appeal_conviction_sessions",
    "name_en":         "Appeal against Conviction — Sessions (S.415 BNSS / 374 CrPC)",
    "name_hi":         "दोषसिद्धि अपील — सत्र न्यायालय (धारा 415 BNSS / 374 दं.प्र.सं.)",
    "court":           "sessions",
    "court_label_en":  "Sessions Court",
    "court_label_hi":  "सत्र न्यायालय",
    "category":        "appeal",
    "tier":            2,
    "popularity":      4,
    "quality":         "v2",
    "description":     "Criminal appeal to the Sessions Court against a Magistrate's conviction (S.415 BNSS / 374(3) CrPC) — grounds of appeal and acquittal prayer. Canonical deterministic draft.",
    "redirect_url":    "/draft/template/appeal_sessions",
    "fields":          [],
    "format_spec":     "",
    "example_prompts": [
        "मजिस्ट्रेट की दोषसिद्धि के विरुद्ध सत्र न्यायालय में आपराधिक अपील",
        "Appeal to Sessions Court against JMFC conviction under S.374 CrPC",
    ],
}


NEW_TEMPLATES_V2: dict[str, dict] = {
    DISCHARGE_APPLICATION_MAGISTRATE["id"]: DISCHARGE_APPLICATION_MAGISTRATE,
    APPEAL_CONVICTION_SESSIONS["id"]:       APPEAL_CONVICTION_SESSIONS,
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
    NI_138B_DISMISS["id"]:            NI_138B_DISMISS,
    DV_ACT_12["id"]:                  DV_ACT_12,
    HMA_9_RESTITUTION["id"]:          HMA_9_RESTITUTION,
    HMA_13_DIVORCE["id"]:             HMA_13_DIVORCE,
    GENERAL_AFFIDAVIT["id"]:          GENERAL_AFFIDAVIT,
    # v2-ref — decoded from real filings (close the biggest catalogue gaps)
    LEGAL_NOTICE["id"]:               LEGAL_NOTICE,
    PRIVATE_COMPLAINT_200["id"]:      PRIVATE_COMPLAINT_200,
    REPLY_APPLICATION["id"]:          REPLY_APPLICATION,
    COMPLAINT_498A["id"]:             COMPLAINT_498A,
    # proposed (v0, pending advocate review) — courtbook gap-fill
    MOTOR_ACCIDENT_CLAIM_166["id"]:   MOTOR_ACCIDENT_CLAIM_166,
}
