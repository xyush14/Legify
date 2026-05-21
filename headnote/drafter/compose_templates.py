"""Template registry for the Smart Drafter (`/api/draft/compose`).

Each entry is pure data — fields the conductor collects + a `format_spec`
that the LLM uses to draft the final document. Adding a new template type
is just adding a new dict here and importing it in TEMPLATES.

References used in writing these specs (verified May 2026):
  - BNSS, 2023 (effective Jul 2024) section numbers
  - Supreme Court of India Mentioning Branch proforma
  - MP HC Notice No. 87/PR(J)/2022 on Mention Memo format
  - JuriGram, iPleaders, LegalKart, LawSathi format guides
  - State of Haryana v. Bhajan Lal (1992) — quashing categories

Conventions:
  - Field types: text | longtext | name | address | date | phone | section_list
  - Each field has label_en + label_hi for the conductor's questions.
  - format_spec is the SYSTEM prompt for the document-generation LLM call;
    it describes structure, statutes, vocab, paragraph ordering.
"""

from __future__ import annotations


# ============================================================================
# COMMON FIELD HELPERS — keep schemas DRY where multiple templates share fields
# ============================================================================

_ADVOCATE_FIELDS = [
    {"key": "advocate_name", "label_en": "Advocate name", "label_hi": "अधिवक्ता का नाम", "type": "name", "required": True, "section": "filing"},
    {"key": "place",         "label_en": "Place of filing","label_hi": "स्थान",          "type": "text", "required": True, "section": "filing"},
    {"key": "filing_date",   "label_en": "Filing date",   "label_hi": "दिनांक",         "type": "date", "required": True, "section": "filing"},
]

# Canonical section labels — every template's `sections` array references these
# by id. Frontend renders them as bail-style eyebrows ("अनुभाग 1") + titles.
SECTION_LABELS = {
    "court":     {"en": "Court & Application Type", "hi": "न्यायालय एवं आवेदन का प्रकार"},
    "parties":   {"en": "Parties",                  "hi": "पक्षकार"},
    "client":    {"en": "Client",                   "hi": "मुवक्किल"},
    "applicant": {"en": "Applicant",                "hi": "आवेदक"},
    "petitioner":{"en": "Petitioner",               "hi": "याचिकाकर्ता"},
    "respondent":{"en": "Respondent",               "hi": "विपक्षी / प्रतिवादी"},
    "advocate":  {"en": "Advocate",                 "hi": "अधिवक्ता"},
    "fir":       {"en": "The Crime / FIR",          "hi": "अपराध (FIR)"},
    "custody":   {"en": "Custody / Investigation",  "hi": "निरोध एवं विवेचना"},
    "matter":    {"en": "Matter Details",           "hi": "मामले का विवरण"},
    "order":     {"en": "Impugned Order",           "hi": "विवादित आदेश"},
    "marriage":  {"en": "Marriage & Family",        "hi": "विवाह एवं परिवार"},
    "income":    {"en": "Income & Maintenance",     "hi": "आय एवं भरण-पोषण"},
    "grounds":   {"en": "Grounds / Reasons",        "hi": "आधार / कारण"},
    "facts":     {"en": "Brief Facts",              "hi": "संक्षिप्त तथ्य"},
    "conviction":{"en": "Conviction Details",       "hi": "दोषसिद्धि विवरण"},
    "mention":   {"en": "Mentioning Details",       "hi": "मेंशन विवरण"},
    "filing":    {"en": "Filing / Signature",       "hi": "हस्ताक्षर"},
}


# ============================================================================
# TIER 1 — DAILY DRIVERS
# ============================================================================

# ---------------------------------------------------------------- Vakalatnama
VAKALATNAMA = {
    "id":         "vakalatnama",
    "name_en":    "Vakalatnama",
    "name_hi":    "वकालतनामा",
    "category":   "misc",
    "tier":       1,
    "description": "Authorisation for advocate to appear on behalf of the party. Required for every matter.",
    "fields": [
        {"key": "court_name",          "label_en": "Court name",                "label_hi": "न्यायालय का नाम",        "type": "text",      "required": True,  "hint": "e.g. 'Court of the Sessions Judge, Gwalior' or 'MP High Court, Gwalior Bench'", "section": "court"},
        {"key": "case_no",             "label_en": "Case / Crime number",       "label_hi": "केस / अपराध क्रमांक",   "type": "text",      "required": False, "hint": "If a case number is assigned", "section": "court"},
        {"key": "client_name",         "label_en": "Client (party) name",       "label_hi": "मुवक्किल का नाम",       "type": "name",      "required": True, "section": "client"},
        {"key": "client_father",       "label_en": "Client father's name",      "label_hi": "मुवक्किल के पिता का नाम", "type": "name",      "required": True, "section": "client"},
        {"key": "client_address",      "label_en": "Client address",            "label_hi": "मुवक्किल का पता",         "type": "address",   "required": True, "section": "client"},
        {"key": "party_role",          "label_en": "Party role",                "label_hi": "पक्षकार की भूमिका",        "type": "text",      "required": True,  "hint": "applicant / petitioner / respondent / accused / plaintiff", "section": "client"},
        {"key": "opposite_party",      "label_en": "Opposite party",            "label_hi": "विपक्षी पक्ष",            "type": "text",      "required": False, "hint": "e.g. 'State of MP' for criminal matters", "section": "client"},
        {"key": "advocate_name",       "label_en": "Advocate name",             "label_hi": "अधिवक्ता का नाम",         "type": "name",      "required": True, "section": "filing"},
        {"key": "advocate_enrollment", "label_en": "Bar Council enrolment no.", "label_hi": "बार काउंसिल पंजीयन क्रमांक","type": "text",      "required": False, "hint": "e.g. 'MP/1234/2018'", "section": "advocate"},
        {"key": "advocate_address",    "label_en": "Advocate chamber address",  "label_hi": "अधिवक्ता का पता",          "type": "address",   "required": True, "section": "filing"},
        {"key": "place",               "label_en": "Place of execution",        "label_hi": "स्थान",                    "type": "text",      "required": True, "section": "filing"},
        {"key": "date",                "label_en": "Date",                      "label_hi": "दिनांक",                    "type": "date",      "required": True, "section": "filing"},
    ],
    "format_spec": (
        "Generate a standard Indian Vakalatnama on behalf of the client, in the "
        "language requested. Structure:\n"
        "  1. Heading: 'VAKALATNAMA' / 'वकालतनामा' centered\n"
        "  2. 'IN THE COURT OF …' / 'न्यायालय …' line in caps\n"
        "  3. Case / Crime No. block (skip if none)\n"
        "  4. Parties: <Party Role> <Client Name>, s/o <Father>, r/o <Address>\n"
        "     Vs. <Opposite Party>\n"
        "  5. Standard appointment + authorisation paragraph (engage to appear, "
        "     plead, act, file documents, withdraw money, compromise as advised, etc.).\n"
        "  6. Acceptance line: 'Accepted, <Advocate Name>, Enrollment No. ___'\n"
        "  7. Signature blocks for client + advocate, with place + date.\n\n"
        "Use proper court Hindi if lang='hi' (vocabulary: माननीय न्यायालय, "
        "मुवक्किल, अधिवक्ता, हस्ताक्षर, etc.). Use formal English legal register "
        "if lang='en'. Do NOT add markdown — return plain text with line breaks."
    ),
    "example_prompts": [
        "मुझे ग्वालियर सेशन कोर्ट के लिए वकालतनामा चाहिए, मेरे मुवक्किल अनिल मोर्य के लिए",
        "Need a vakalatnama for my client Vivek Sharma in MP HC Gwalior bench",
    ],
}


# ---------------------------------------------------------------- Mention Memo
MENTION_MEMO = {
    "id":         "mention_memo",
    "name_en":    "Mention Memo (Urgent Listing)",
    "name_hi":    "मेंशन मेमो (अर्जेंट लिस्टिंग)",
    "category":   "procedural",
    "tier":       1,
    "description": "Oral mention before the bench requesting urgent listing of a pending matter.",
    "fields": [
        {"key": "court_name",      "label_en": "Court",                       "label_hi": "न्यायालय",                "type": "text",  "required": True,  "hint": "e.g. 'Supreme Court of India' or 'MP High Court, Gwalior Bench'", "section": "court"},
        {"key": "case_no",         "label_en": "Case number",                 "label_hi": "केस क्रमांक",             "type": "text",  "required": True,  "hint": "e.g. 'Crl. Appeal 1234/2025' or 'WP(C) 567/2026'", "section": "court"},
        {"key": "case_title",      "label_en": "Case title (parties)",        "label_hi": "केस शीर्षक (पक्षकार)",    "type": "text",  "required": True,  "hint": "e.g. 'Vikesh Sharma vs State of MP'", "section": "court"},
        {"key": "bench",           "label_en": "Bench / Court no.",           "label_hi": "बेंच / कोर्ट क्रमांक",     "type": "text",  "required": False, "hint": "e.g. 'Hon'ble Chief Justice's Bench' or 'Court No. 5'", "section": "court"},
        {"key": "mention_reason",  "label_en": "Reason for urgent mention",   "label_hi": "अर्जेंट मेंशन का कारण",    "type": "longtext", "required": True, "hint": "Why the matter needs urgent attention", "section": "mention"},
        {"key": "proposed_date",   "label_en": "Proposed listing date",       "label_hi": "प्रस्तावित सुनवाई दिनांक","type": "date",  "required": False, "section": "mention"},
        {"key": "advocate_name",   "label_en": "Advocate name",               "label_hi": "अधिवक्ता का नाम",         "type": "name",  "required": True, "section": "filing"},
        {"key": "advocate_enrollment", "label_en": "Bar Council enrolment no.","label_hi": "बार काउंसिल पंजीयन क्रमांक","type": "text", "required": False, "section": "advocate"},
        {"key": "advocate_for",    "label_en": "Appearing for",               "label_hi": "किस ओर से",               "type": "text",  "required": True, "hint": "e.g. 'Petitioner' or 'Respondent No. 1'", "section": "advocate"},
        {"key": "place",           "label_en": "Place",                       "label_hi": "स्थान",                    "type": "text",  "required": True, "section": "filing"},
        {"key": "filing_date",     "label_en": "Date",                        "label_hi": "दिनांक",                    "type": "date",  "required": True, "section": "filing"},
    ],
    "format_spec": (
        "Generate a Mention Memo in the format used before Indian High Courts "
        "and the Supreme Court for urgent oral mentioning. Structure:\n"
        "  1. Header: 'IN THE <COURT NAME>' (in caps)\n"
        "  2. Sub-header: '(MENTIONING BRANCH)' or '(URGENT MENTIONING)' if SC; "
        "     plain title otherwise\n"
        "  3. Case block: 'Case No. <case_no>' and 'In re: <case_title>'\n"
        "  4. Bench reference if specified: 'Before the Hon'ble Bench presided over by …'\n"
        "  5. Title: 'MEMO FOR MENTIONING' or 'MEMORANDUM OF URGENT MENTIONING' (centred, underlined)\n"
        "  6. Body in numbered paragraphs:\n"
        "     1. 'The undersigned advocate respectfully mentions the above matter "
        "        for urgent listing on <proposed_date if given, else 'an early date'>.'\n"
        "     2. The reason for urgent mention with specific factual basis (use <mention_reason>).\n"
        "     3. 'It is therefore most respectfully prayed that the said matter "
        "        may kindly be listed for hearing on <date / next working day> "
        "        before the appropriate Bench.'\n"
        "  7. Footer: 'Respectfully submitted,' followed by advocate signature block "
        "     showing name, enrollment no. (if given), and 'Counsel for the <advocate_for>'\n"
        "  8. Place + Date at the bottom-left.\n\n"
        "Tone: formal, deferential, concise (typically half a page). "
        "Hindi mode uses court-Hindi vocab: निवेदन, अति आवश्यक सुनवाई, "
        "अग्रिम लिस्टिंग, माननीय न्यायालय. Return plain text only — no markdown."
    ),
    "example_prompts": [
        "Crl appeal 1234/2025 ko urgent list karwana hai, accused was acquitted but state hasn't taken steps",
        "Need to mention WP 567/2026 before HC Gwalior — stay order is expiring tomorrow",
    ],
}


# ----------------------------------------------------------- Anticipatory Bail
ANTICIPATORY_BAIL = {
    "id":         "anticipatory_bail",
    "name_en":    "Anticipatory Bail (S.482 BNSS / S.438 CrPC)",
    "name_hi":    "अग्रिम जमानत आवेदन (धारा 482 BNSS / 438 दं.प्र.सं.)",
    "category":   "bail",
    "tier":       1,
    "description": "Pre-arrest bail application before Sessions / High Court.",
        "uploads": [
        {
            "id":            "fir_photo",
            "label_en":      "FIR Photo (all pages)",
            "label_hi":      "FIR की सभी पन्नों की फोटो",
            "sub_en":        "NCRB I.I.F.-I format · 1-8 pages · AI auto-fills FIR no, PS, sections, accused",
            "sub_hi":        "NCRB I.I.F.-I फॉर्मेट · 1-8 पन्ने · AI स्वतः FIR क्र., थाना, धाराएं, अभियुक्त भरेगा",
            "accept":        "image/*,application/pdf",
            "multiple":      True,
            "max_files":     8,
            "endpoint":      "/api/draft/ocr-fir",
            "fills_fields":  ["fir_number", "fir_date", "police_station", "district", "sections_str", "facts_narrative", "brief_facts_alleged"],
        }
    ],
    "fields": [
        {"key": "court_name",          "label_en": "Court",                       "label_hi": "न्यायालय",                "type": "text",     "required": True,  "hint": "Sessions / HC bench", "section": "court"},
        {"key": "applicant_name",      "label_en": "Applicant name",              "label_hi": "आवेदक का नाम",            "type": "name",     "required": True, "section": "applicant"},
        {"key": "applicant_father",    "label_en": "Father's name",               "label_hi": "पिता का नाम",             "type": "name",     "required": True, "section": "applicant"},
        {"key": "applicant_age",       "label_en": "Age",                         "label_hi": "आयु",                     "type": "text",     "required": False, "section": "applicant"},
        {"key": "applicant_occupation","label_en": "Occupation",                  "label_hi": "व्यवसाय",                 "type": "text",     "required": False, "section": "applicant"},
        {"key": "applicant_address",   "label_en": "Address",                     "label_hi": "पता",                     "type": "address",  "required": True, "section": "applicant"},
        {"key": "district",            "label_en": "District",                    "label_hi": "जिला",                    "type": "text",     "required": True, "section": "fir"},
        {"key": "state_name",          "label_en": "State",                       "label_hi": "राज्य",                   "type": "text",     "required": False, "section": "fir"},
        {"key": "fir_number",          "label_en": "FIR No.",                     "label_hi": "FIR क्रमांक",             "type": "text",     "required": True, "section": "fir"},
        {"key": "fir_date",            "label_en": "FIR date",                    "label_hi": "FIR दिनांक",              "type": "date",     "required": False, "section": "fir"},
        {"key": "police_station",      "label_en": "Police Station",              "label_hi": "पुलिस थाना",              "type": "text",     "required": True, "section": "fir"},
        {"key": "sections_str",        "label_en": "Sections invoked",            "label_hi": "धाराएं",                  "type": "section_list", "required": True, "hint": "e.g. '420 IPC, 406 IPC, 506 IPC'", "section": "fir"},
        {"key": "apprehension_reason", "label_en": "Reason for apprehension",     "label_hi": "गिरफ्तारी की आशंका का कारण","type": "longtext", "required": True, "hint": "Why the applicant fears arrest", "section": "grounds"},
        {"key": "facts_narrative",     "label_en": "Brief facts / defence",       "label_hi": "तथ्य व बचाव",             "type": "longtext", "required": True, "section": "grounds"},
        *_ADVOCATE_FIELDS,
    ],
    "format_spec": (
        "Generate a complete anticipatory bail application under Section 482 of "
        "the Bharatiya Nagarik Suraksha Sanhita, 2023 (or Section 438 CrPC for "
        "pre-Jul-2024 cases). Structure:\n"
        "  - Heading: Court name in formal style\n"
        "  - 'Application No. ___ of <year>' block (leave blank if none)\n"
        "  - Parties: Applicant (full S/o + R/o details) Vs. State of <State>\n"
        "  - 'APPLICATION UNDER SECTION 482 BNSS, 2023 FOR ANTICIPATORY BAIL'\n"
        "  - 'The humble applicant most respectfully submits as follows:—'\n"
        "  - Numbered paragraphs (1 to N) covering:\n"
        "      1. This is the FIRST anticipatory bail application of the applicant under §482 BNSS in this Honourable Court.\n"
        "      2. No similar application is pending or has been disposed of before this Hon'ble Court or before the Hon'ble Supreme Court of India.\n"
        "      3. Brief facts as alleged in the FIR (using <facts_narrative>).\n"
        "      4. The applicant has reasonable apprehension of arrest because… (using <apprehension_reason>).\n"
        "      5. Grounds for granting anticipatory bail (innocence, false implication, no flight risk, deep roots in society, cooperation with investigation, custodial interrogation not required — see *Arnesh Kumar v State of Bihar*, *Siddharam Mhetre*).\n"
        "      6. Applicant undertakes to cooperate with the investigation, not leave the country without leave of the Court, not influence witnesses, and abide by such conditions as the Hon'ble Court may impose.\n"
        "  - PRAYER: 'It is, therefore, most respectfully prayed that this Honourable Court may be pleased to grant anticipatory bail to the applicant in the event of his arrest in connection with FIR No. ___ / ___ registered at P.S. ___ under Sections ___ …'\n"
        "  - Signature blocks: Applicant + Through Counsel (name)\n"
        "  - Place + Date at bottom\n\n"
        "Use formal court Hindi (legal vocab: माननीय न्यायालय, आवेदक, सादर निवेदन, "
        "अग्रिम जमानत, सहयोग) if lang='hi'. Use formal Indian legal English if "
        "lang='en'. Return plain text — no markdown fences."
    ),
    "example_prompts": [
        "अग्रिम जमानत चाहिए, मुवक्किल विकेश शर्मा, धारा 420, FIR नंबर 95/2025, थाना मुरार",
        "Anticipatory bail for Anil Morya, S.420 IPC, FIR 95/2025 PS Murar Gwalior",
    ],
}


# ----------------------------------------------------------- Quashing Petition
QUASHING_PETITION = {
    "id":         "quashing_petition",
    "name_en":    "Quashing Petition (S.528 BNSS / S.482 CrPC)",
    "name_hi":    "FIR निरस्तीकरण याचिका (धारा 528 BNSS / 482 दं.प्र.सं.)",
    "category":   "writ",
    "tier":       1,
    "description": "High Court petition to quash FIR / criminal proceedings by invoking inherent powers.",
        "uploads": [
        {
            "id":            "fir_photo",
            "label_en":      "FIR Photo (all pages)",
            "label_hi":      "FIR की सभी पन्नों की फोटो",
            "sub_en":        "NCRB I.I.F.-I format · 1-8 pages · AI auto-fills FIR no, PS, sections, accused",
            "sub_hi":        "NCRB I.I.F.-I फॉर्मेट · 1-8 पन्ने · AI स्वतः FIR क्र., थाना, धाराएं, अभियुक्त भरेगा",
            "accept":        "image/*,application/pdf",
            "multiple":      True,
            "max_files":     8,
            "endpoint":      "/api/draft/ocr-fir",
            "fills_fields":  ["fir_number", "fir_date", "police_station", "district", "sections_str", "facts_narrative", "brief_facts_alleged"],
        }
    ],
    "fields": [
        {"key": "court_name",        "label_en": "High Court",                 "label_hi": "उच्च न्यायालय",              "type": "text",     "required": True, "hint": "e.g. 'MP High Court, Gwalior Bench'", "section": "court"},
        {"key": "petitioner_name",   "label_en": "Petitioner name",            "label_hi": "याचिकाकर्ता का नाम",         "type": "name",     "required": True, "section": "petitioner"},
        {"key": "petitioner_father", "label_en": "Father's name",              "label_hi": "पिता का नाम",                "type": "name",     "required": True, "section": "petitioner"},
        {"key": "petitioner_age",    "label_en": "Age",                        "label_hi": "आयु",                         "type": "text",     "required": False, "section": "petitioner"},
        {"key": "petitioner_occupation","label_en": "Occupation",              "label_hi": "व्यवसाय",                     "type": "text",     "required": False, "section": "petitioner"},
        {"key": "petitioner_address","label_en": "Address",                    "label_hi": "पता",                         "type": "address",  "required": True, "section": "petitioner"},
        {"key": "fir_number",        "label_en": "FIR No.",                    "label_hi": "FIR क्रमांक",                 "type": "text",     "required": True, "section": "fir"},
        {"key": "fir_date",          "label_en": "FIR date",                   "label_hi": "FIR दिनांक",                  "type": "date",     "required": True, "section": "fir"},
        {"key": "police_station",    "label_en": "Police Station",             "label_hi": "पुलिस थाना",                  "type": "text",     "required": True, "section": "fir"},
        {"key": "district",          "label_en": "District",                   "label_hi": "जिला",                        "type": "text",     "required": True, "section": "fir"},
        {"key": "sections_str",      "label_en": "Sections in FIR",            "label_hi": "FIR की धाराएं",               "type": "section_list", "required": True, "section": "fir"},
        {"key": "complainant_name",  "label_en": "Complainant (Respondent 2)", "label_hi": "शिकायतकर्ता (विपक्षी क्र.2)","type": "name",     "required": False, "hint": "FIR complainant — usually impleaded as Respondent No. 2", "section": "respondent"},
        {"key": "brief_facts_alleged","label_en": "Allegations in FIR",        "label_hi": "FIR के आरोप",                 "type": "longtext", "required": True, "hint": "Verbatim or summarised allegations", "section": "grounds"},
        {"key": "grounds_for_quashing","label_en": "Grounds for quashing",     "label_hi": "निरस्तीकरण के आधार",          "type": "longtext", "required": True, "hint": "Why the FIR should be quashed (no offence made out / civil dispute given criminal colour / mala fide / settlement)", "section": "grounds"},
        {"key": "stage_of_proceedings","label_en": "Current stage",            "label_hi": "वर्तमान चरण",                  "type": "text",     "required": False, "hint": "e.g. 'Investigation pending', 'Charge-sheet filed', 'Cognizance taken'", "section": "grounds"},
        *_ADVOCATE_FIELDS,
    ],
    "format_spec": (
        "Generate a complete petition for quashing of FIR under Section 528 of "
        "the Bharatiya Nagarik Suraksha Sanhita, 2023 (or Section 482 CrPC for "
        "pre-Jul-2024 cases). Structure exactly:\n\n"
        "  1. HEADER (centred, caps): 'IN THE HIGH COURT OF <STATE> AT <BENCH>'\n"
        "  2. Case block: 'Miscellaneous Criminal Case No. ____ of <year>'\n"
        "  3. Cause title:\n"
        "       <Petitioner Name>, S/o <Father>, age ___, occupation ___,\n"
        "       R/o <Address>                                  ... PETITIONER\n"
        "                              VERSUS\n"
        "       1. State of <State> through Police Station <PS>\n"
        "       2. <Complainant>, S/o ___, R/o ___           ... RESPONDENTS\n"
        "       (Skip Respondent 2 if no complainant_name provided.)\n"
        "  4. Title (centred, underlined): 'PETITION UNDER SECTION 528 OF THE "
        "     BHARATIYA NAGARIK SURAKSHA SANHITA, 2023 (FORMERLY SECTION 482 "
        "     CrPC, 1973) FOR QUASHING OF FIR NO. <fir_number> DATED <fir_date> "
        "     REGISTERED AT P.S. <police_station>, DISTRICT <district> UNDER "
        "     SECTIONS <sections_str>'\n"
        "  5. 'MOST RESPECTFULLY SHEWETH:'\n"
        "  6. Numbered paragraphs:\n"
        "     1. Brief profile of the petitioner (name, occupation, residence, "
        "        clean antecedents).\n"
        "     2. Brief facts of the FIR using <brief_facts_alleged>.\n"
        "     3. Current stage of proceedings (using <stage_of_proceedings>).\n"
        "     4. Petitioner's version of facts / defence — establish why "
        "        prosecution is unsustainable.\n"
        "     5. Grounds for quashing — invoke Section 528 BNSS / 482 CrPC "
        "        inherent powers and the seven categories in *State of Haryana "
        "        v. Bhajan Lal* (1992 Supp (1) SCC 335). Reference grounds from "
        "        <grounds_for_quashing>. Typical heads:\n"
        "          (a) No prima facie offence even if allegations taken at face value\n"
        "          (b) Allegations don't constitute the offences alleged\n"
        "          (c) Inherent improbability / manifest falsity\n"
        "          (d) Essentially a civil dispute given criminal colour\n"
        "          (e) Mala fide / oblique motive\n"
        "          (f) Abuse of process of Court\n"
        "          (g) Continuation of proceedings would be unjust\n"
        "     6. No alternative efficacious remedy is available.\n"
        "  7. PRAYER (each clause numbered):\n"
        "        a) Quash the FIR No. ___ dated ___ and all consequential "
        "           proceedings arising therefrom.\n"
        "        b) Stay further investigation / proceedings during pendency.\n"
        "        c) Such other relief as this Hon'ble Court may deem fit.\n"
        "  8. Signature block: 'Through' <advocate_name>, Counsel for the Petitioner.\n"
        "  9. Place + Date at the bottom-left.\n"
        "  10. After the main body, add a 'VERIFICATION' paragraph: 'I, "
        "      <Petitioner>, do hereby verify that the contents of paras 1 to N "
        "      are true to my personal knowledge and the contents of paras X to "
        "      Y are based on legal advice received and believed to be true.'\n\n"
        "If lang='hi' write the entire document in formal Devanagari with court "
        "Hindi vocabulary: माननीय न्यायालय, याचिकाकर्ता, FIR निरस्तीकरण, "
        "अंतर्निहित अधिकार क्षेत्र. Return plain text only — no markdown."
    ),
    "example_prompts": [
        "MP HC Gwalior bench ke liye quashing chahiye, FIR 95/2025 PS Murar, S 420 IPC, civil dispute",
        "Need to quash FIR 234/2025 — false complaint by complainant, my client has settled",
    ],
}


# ---------------------------------------------------------------- Writ Petition
WRIT_PETITION = {
    "id":         "writ_petition",
    "name_en":    "Writ Petition (Article 226)",
    "name_hi":    "रिट याचिका (अनुच्छेद 226)",
    "category":   "writ",
    "tier":       1,
    "description": "High Court writ — mandamus, certiorari, habeas corpus, prohibition, quo warranto.",
        "uploads": [
        {
            "id":            "order_photo",
            "label_en":      "Impugned Order (photo or PDF)",
            "label_hi":      "विवादित आदेश (फोटो या PDF)",
            "sub_en":        "Upload the order being challenged — AI will extract case no, court, date",
            "sub_hi":        "जिस आदेश को चुनौती दे रहे हैं उसे अपलोड करें",
            "accept":        "image/*,application/pdf",
            "multiple":      False,
            "max_files":     4,
            "endpoint":      None,
            "fills_fields":  [],
        }
    ],
    "fields": [
        {"key": "court_name",        "label_en": "High Court",                 "label_hi": "उच्च न्यायालय",              "type": "text",     "required": True, "section": "court"},
        {"key": "writ_type",         "label_en": "Type of writ",               "label_hi": "रिट का प्रकार",              "type": "text",     "required": True, "hint": "mandamus / certiorari / habeas corpus / prohibition / quo warranto", "section": "grounds"},
        {"key": "writ_category",     "label_en": "Civil or Criminal writ",     "label_hi": "सिविल या आपराधिक रिट",     "type": "text",     "required": False, "hint": "WP(C) = Civil, WP(Crl) = Criminal", "section": "grounds"},
        {"key": "petitioner_name",   "label_en": "Petitioner name",            "label_hi": "याचिकाकर्ता",                "type": "name",     "required": True, "section": "petitioner"},
        {"key": "petitioner_father", "label_en": "Father's name",              "label_hi": "पिता का नाम",                "type": "name",     "required": True, "section": "petitioner"},
        {"key": "petitioner_age",    "label_en": "Age",                        "label_hi": "आयु",                         "type": "text",     "required": False, "section": "petitioner"},
        {"key": "petitioner_occupation","label_en": "Occupation",              "label_hi": "व्यवसाय",                     "type": "text",     "required": False, "section": "petitioner"},
        {"key": "petitioner_address","label_en": "Address",                    "label_hi": "पता",                         "type": "address",  "required": True, "section": "petitioner"},
        {"key": "respondent_authority","label_en": "Respondent authority",     "label_hi": "विपक्षी प्राधिकारी",         "type": "longtext", "required": True, "hint": "e.g. 'State of MP through Principal Secretary, Home Dept; Superintendent of Police, Gwalior'", "section": "respondent"},
        {"key": "impugned_action",   "label_en": "Impugned action / order",    "label_hi": "विवादित कार्य / आदेश",        "type": "longtext", "required": True, "hint": "What is being challenged", "section": "order"},
        {"key": "subject_summary",   "label_en": "Subject in one line",        "label_hi": "विषय (एक पंक्ति में)",       "type": "text",     "required": True, "hint": "e.g. 'For quashing the arbitrary transfer order dated 01.03.2026'", "section": "grounds"},
        {"key": "facts_narrative",   "label_en": "Facts of the case",          "label_hi": "मामले के तथ्य",              "type": "longtext", "required": True, "section": "grounds"},
        {"key": "legal_violation",   "label_en": "Legal / fundamental rights violated", "label_hi": "उल्लंघित अधिकार",   "type": "longtext", "required": True, "hint": "Article 14, 19, 21 etc., or specific statutory rights", "section": "grounds"},
        {"key": "grounds_for_writ",  "label_en": "Grounds for the writ",       "label_hi": "रिट के आधार",                "type": "longtext", "required": True, "section": "grounds"},
        {"key": "relief_sought",     "label_en": "Specific relief sought",     "label_hi": "अभीप्सित अनुतोष",            "type": "longtext", "required": True, "section": "grounds"},
        {"key": "alternative_remedy_exhausted","label_en": "Alternative remedy exhausted?","label_hi": "वैकल्पिक उपचार समाप्त?","type": "text", "required": False, "hint": "Yes/No + brief explanation", "section": "grounds"},
        *_ADVOCATE_FIELDS,
    ],
    "format_spec": (
        "Generate a complete writ petition under Article 226 of the Constitution "
        "of India for an Indian High Court. Structure exactly:\n\n"
        "  1. HEADER: 'IN THE HIGH COURT OF <STATE> AT <BENCH>'\n"
        "  2. Case block: 'Writ Petition (<writ_category if given, else 'Civil'>) No. ____ of <year>'\n"
        "  3. 'IN THE MATTER OF:' line followed by\n"
        "       <Petitioner Name>, S/o <Father>, age ___, occupation ___,\n"
        "       R/o <Address>                                  ... PETITIONER\n"
        "                              VERSUS\n"
        "       <Respondent Authority — one entity per numbered line>\n"
        "                                                       ... RESPONDENTS\n"
        "  4. Title: 'PETITION UNDER ARTICLE 226 OF THE CONSTITUTION OF INDIA "
        "     SEEKING ISSUANCE OF A WRIT IN THE NATURE OF <writ_type> "
        "     <subject_summary>'\n"
        "  5. 'MOST RESPECTFULLY SHEWETH:'\n"
        "  6. SYNOPSIS (one paragraph, ~6 lines, capturing the gravamen)\n"
        "  7. LIST OF DATES & EVENTS (chronological, tabular feel — date on left, "
        "     event on right; derive from facts_narrative)\n"
        "  8. Numbered paragraphs:\n"
        "     1. Petitioner's profile.\n"
        "     2-N. Facts of the case (using <facts_narrative>).\n"
        "     N+1. The impugned action / order being challenged (using <impugned_action>).\n"
        "     N+2. Legal rights / fundamental rights violated (using <legal_violation>) — "
        "          cite specific Articles (14 — equality; 19 — freedoms; 21 — life "
        "          & liberty; 300A — property) or statutes as applicable.\n"
        "     N+3. Alternative remedy: state whether exhausted or unavailable / "
        "          inadequate (using <alternative_remedy_exhausted>); for criminal "
        "          writs, cite *Whirlpool Corp. v. Registrar of Trade Marks* "
        "          exceptions if remedy exists but inadequate.\n"
        "  9. GROUNDS (lettered A, B, C…): pinpoint each legal infirmity in the "
        "     impugned action; tie each ground to a constitutional or statutory "
        "     provision (using <grounds_for_writ>).\n"
        " 10. PRAYER:\n"
        "        a) Issue a writ of <writ_type> directing/quashing <relief_sought>.\n"
        "        b) Stay the operation of the impugned action during pendency.\n"
        "        c) Such other relief as this Hon'ble Court may deem fit.\n"
        " 11. Signature: 'Through' <advocate_name>, Counsel for the Petitioner.\n"
        " 12. Place + Date.\n"
        " 13. VERIFICATION paragraph (paras 1–N true to personal knowledge; "
        "     paras X–Y on legal advice).\n\n"
        "Tone: formal, Indian High Court legal English. If lang='hi' use "
        "formal Devanagari with vocabulary: माननीय उच्च न्यायालय, याचिकाकर्ता, "
        "विपक्षी, परमादेश रिट, मौलिक अधिकार, अनुच्छेद 226. Return plain text."
    ),
    "example_prompts": [
        "Writ for transfer order quashing — my client arbitrarily transferred to Bastar",
        "Habeas corpus petition — client illegally detained by Murar police for 5 days",
    ],
}


# ============================================================================
# TIER 2 — WEEKLY USE
# ============================================================================

# ---------------------------------------------------------------- Default Bail
DEFAULT_BAIL = {
    "id":         "default_bail",
    "name_en":    "Default Bail (S.187(3) BNSS / S.167(2) CrPC)",
    "name_hi":    "स्थिर जमानत (धारा 187(3) BNSS / 167(2) दं.प्र.सं.)",
    "category":   "bail",
    "tier":       2,
    "description": "Statutory right to bail when investigation exceeds 60 or 90 days without charge-sheet.",
        "uploads": [
        {
            "id":            "fir_photo",
            "label_en":      "FIR Photo (all pages)",
            "label_hi":      "FIR की सभी पन्नों की फोटो",
            "sub_en":        "NCRB I.I.F.-I format · 1-8 pages · AI auto-fills FIR no, PS, sections, accused",
            "sub_hi":        "NCRB I.I.F.-I फॉर्मेट · 1-8 पन्ने · AI स्वतः FIR क्र., थाना, धाराएं, अभियुक्त भरेगा",
            "accept":        "image/*,application/pdf",
            "multiple":      True,
            "max_files":     8,
            "endpoint":      "/api/draft/ocr-fir",
            "fills_fields":  ["fir_number", "fir_date", "police_station", "district", "sections_str", "facts_narrative", "brief_facts_alleged"],
        }
    ],
    "fields": [
        {"key": "court_name",        "label_en": "Court",                       "label_hi": "न्यायालय",                "type": "text",     "required": True,  "hint": "Court where charge-sheet was to be filed — Magistrate / Sessions", "section": "court"},
        {"key": "applicant_name",    "label_en": "Applicant name",              "label_hi": "आवेदक का नाम",            "type": "name",     "required": True, "section": "applicant"},
        {"key": "applicant_father",  "label_en": "Father's name",               "label_hi": "पिता का नाम",             "type": "name",     "required": True, "section": "applicant"},
        {"key": "applicant_address", "label_en": "Address",                     "label_hi": "पता",                     "type": "address",  "required": True, "section": "applicant"},
        {"key": "fir_number",        "label_en": "FIR No.",                     "label_hi": "FIR क्रमांक",             "type": "text",     "required": True, "section": "fir"},
        {"key": "police_station",    "label_en": "Police Station",              "label_hi": "पुलिस थाना",              "type": "text",     "required": True, "section": "fir"},
        {"key": "sections_str",      "label_en": "Sections invoked",            "label_hi": "धाराएं",                  "type": "section_list", "required": True, "section": "fir"},
        {"key": "arrest_date",       "label_en": "Date of arrest",              "label_hi": "गिरफ्तारी की दिनांक",     "type": "date",     "required": True, "hint": "Critical for 60/90 day computation", "section": "custody"},
        {"key": "remand_dates",      "label_en": "Remand dates",                "label_hi": "रिमांड की तिथियां",       "type": "longtext", "required": False, "hint": "Chronology of remand extensions", "section": "custody"},
        {"key": "current_jail",      "label_en": "Current jail",                "label_hi": "वर्तमान कारागार",         "type": "text",     "required": True, "section": "order"},
        {"key": "max_punishment",    "label_en": "Maximum punishment for offence","label_hi": "अधिकतम सज़ा",            "type": "text",     "required": True, "hint": "Determines whether 60 or 90 day period applies", "section": "custody"},
        {"key": "charge_sheet_filed","label_en": "Has charge-sheet been filed?", "label_hi": "क्या चार्जशीट दाखिल हुई?","type": "text",     "required": True, "hint": "No / Yes (date)", "section": "order"},
        *_ADVOCATE_FIELDS,
    ],
    "format_spec": (
        "Generate a default-bail application under Section 187(3) of the BNSS, "
        "2023 (formerly Section 167(2) CrPC). The defining feature of this "
        "application is its STATUTORY URGENCY — the right is indefeasible the "
        "moment the prescribed period (60 or 90 days) ends without a charge-"
        "sheet. Structure:\n\n"
        "  1. Header: Court name (where charge-sheet was due) in caps.\n"
        "  2. 'Application No. ____ of <year>'\n"
        "  3. Cause title:\n"
        "       <Applicant Name>, S/o <Father>, R/o <Address>     ... APPLICANT\n"
        "                              VERSUS\n"
        "       State of <State> through P.S. <Police Station>    ... RESPONDENT\n"
        "  4. Title (centred): 'APPLICATION UNDER SECTION 187(3) OF THE "
        "     BHARATIYA NAGARIK SURAKSHA SANHITA, 2023 (FORMERLY SECTION 167(2) "
        "     CrPC, 1973) FOR GRANT OF STATUTORY / DEFAULT BAIL'\n"
        "  5. 'MOST RESPECTFULLY SHEWETH:'\n"
        "  6. Numbered paragraphs:\n"
        "     1. The applicant has been in continuous judicial custody since "
        "        <arrest_date> in connection with FIR No. <fir_number> registered "
        "        at P.S. <police_station> under sections <sections_str>.\n"
        "     2. Computation of custody period: explicitly state the number of "
        "        days from arrest_date to the date of this application.\n"
        "     3. Applicable statutory period: state whether 60 or 90 days applies "
        "        based on <max_punishment> (90 days if punishable with death / life "
        "        / not less than 10 years; 60 days otherwise). Quote §187(3).\n"
        "     4. The statutory period has expired on <computed_date> and the "
        "        investigation agency has FAILED to file the charge-sheet within "
        "        the prescribed period (using <charge_sheet_filed>).\n"
        "     5. The applicant has an INDEFEASIBLE STATUTORY RIGHT to be released "
        "        on bail. Cite:\n"
        "          - *Sanjay Dutt v. State (II)*, (1994) 5 SCC 410\n"
        "          - *Uday Mohanlal Acharya v. State of Maharashtra*, (2001) 5 SCC 453\n"
        "          - *Rakesh Kumar Paul v. State of Assam*, (2017) 15 SCC 67\n"
        "          - *Bikramjit Singh v. Union of India*, (2020) 10 SCC 153\n"
        "     6. The applicant is prepared to furnish bail bond and sureties to "
        "        the satisfaction of this Hon'ble Court and undertakes to abide "
        "        by all conditions imposed.\n"
        "     7. The applicant has roots in society and there is no flight risk; "
        "        he undertakes not to influence witnesses or tamper with evidence.\n"
        "  7. PRAYER:\n"
        "       a) Release the applicant on default bail under §187(3) BNSS / "
        "          §167(2) CrPC in connection with FIR No. ___ at P.S. ___.\n"
        "       b) Such terms and conditions as this Hon'ble Court may deem fit.\n"
        "  8. Signature block: 'Through' <advocate_name>.\n"
        "  9. Place + Date.\n"
        " 10. VERIFICATION.\n\n"
        "CRITICAL: explicitly mention dates (arrest, computed cut-off, today) — "
        "the court will reject a vague default-bail plea. If lang='hi' use court "
        "Hindi: स्थिर/अनिवार्य जमानत, अंतर्निहित अधिकार, अधिकतम सज़ा, चार्जशीट. "
        "Return plain text."
    ),
    "example_prompts": [
        "Default bail for Ramesh Kumar, arrested 12.02.2026 in S.420 IPC, no chargesheet filed",
        "स्थिर जमानत चाहिए, मुवक्किल 70 दिन से जेल में, धारा 379, चार्जशीट दाखिल नहीं",
    ],
}


# ---------------------------------------------------------------- Discharge
DISCHARGE_APPLICATION = {
    "id":         "discharge_application",
    "name_en":    "Discharge Application (S.250 / 258 BNSS)",
    "name_hi":    "उन्मोचन आवेदन (धारा 250 / 258 BNSS)",
    "category":   "bail",
    "tier":       2,
    "description": "Pre-trial relief: discharge the accused for want of prima facie case.",
        "uploads": [
        {
            "id":            "fir_photo",
            "label_en":      "FIR Photo (all pages)",
            "label_hi":      "FIR की सभी पन्नों की फोटो",
            "sub_en":        "NCRB I.I.F.-I format · 1-8 pages · AI auto-fills FIR no, PS, sections, accused",
            "sub_hi":        "NCRB I.I.F.-I फॉर्मेट · 1-8 पन्ने · AI स्वतः FIR क्र., थाना, धाराएं, अभियुक्त भरेगा",
            "accept":        "image/*,application/pdf",
            "multiple":      True,
            "max_files":     8,
            "endpoint":      "/api/draft/ocr-fir",
            "fills_fields":  ["fir_number", "fir_date", "police_station", "district", "sections_str", "facts_narrative", "brief_facts_alleged"],
        }
    ],
    "fields": [
        {"key": "court_name",        "label_en": "Court",                        "label_hi": "न्यायालय",                "type": "text",     "required": True, "hint": "Sessions Court (§250) or Magistrate (§258)", "section": "court"},
        {"key": "applicant_name",    "label_en": "Applicant (accused) name",     "label_hi": "आवेदक का नाम",            "type": "name",     "required": True, "section": "applicant"},
        {"key": "applicant_father",  "label_en": "Father's name",                "label_hi": "पिता का नाम",             "type": "name",     "required": True, "section": "applicant"},
        {"key": "applicant_address", "label_en": "Address",                      "label_hi": "पता",                     "type": "address",  "required": True, "section": "applicant"},
        {"key": "case_no",           "label_en": "Sessions/Criminal case no.",   "label_hi": "सत्र/अपराधिक केस क्रमांक","type": "text",     "required": True, "section": "court"},
        {"key": "fir_number",        "label_en": "FIR no.",                      "label_hi": "FIR क्रमांक",             "type": "text",     "required": True, "section": "fir"},
        {"key": "police_station",    "label_en": "Police Station",               "label_hi": "पुलिस थाना",              "type": "text",     "required": True, "section": "fir"},
        {"key": "sections_str",      "label_en": "Sections",                     "label_hi": "धाराएं",                  "type": "section_list", "required": True, "section": "fir"},
        {"key": "charge_sheet_date", "label_en": "Charge-sheet date",            "label_hi": "चार्जशीट दिनांक",        "type": "date",     "required": False, "section": "order"},
        {"key": "discharge_grounds", "label_en": "Grounds for discharge",        "label_hi": "उन्मोचन के आधार",         "type": "longtext", "required": True, "hint": "Why no prima facie case is made out", "section": "grounds"},
        {"key": "facts_narrative",   "label_en": "Brief facts of the case",      "label_hi": "मामले के तथ्य",          "type": "longtext", "required": True, "section": "grounds"},
        *_ADVOCATE_FIELDS,
    ],
    "format_spec": (
        "Generate a discharge application under Section 250 of the BNSS "
        "(Sessions Court) or Section 258 BNSS (Magistrate) — Section 227 or "
        "239 CrPC respectively for pre-Jul-2024 cases. Structure:\n\n"
        "  1. Header (caps): Court name\n"
        "  2. Sessions/Criminal Case block\n"
        "  3. Cause title: State Vs. <Accused>\n"
        "  4. Title: 'APPLICATION UNDER SECTION 250 BNSS, 2023 (FORMERLY 227 "
        "     CrPC) FOR DISCHARGE OF THE ACCUSED'\n"
        "  5. 'MOST RESPECTFULLY SHEWETH:'\n"
        "  6. Numbered paragraphs:\n"
        "     1. Brief facts of prosecution (using <facts_narrative>).\n"
        "     2. Charge-sheet filed on <charge_sheet_date>, citing sections <sections_str>.\n"
        "     3. Material on record: even taking the charge-sheet at its face "
        "        value, no prima facie case is made out against the accused.\n"
        "     4. Grounds for discharge (using <discharge_grounds>): elaborate on "
        "        each ground with reference to specific paragraphs in the charge-"
        "        sheet, witness statements (S.180 BNSS / 161 CrPC), and documents.\n"
        "     5. Cite relevant precedents:\n"
        "          - *Union of India v. Prafulla Kumar Samal*, (1979) 3 SCC 4\n"
        "          - *State of Bihar v. Ramesh Singh*, (1977) 4 SCC 39\n"
        "          - *Sajjan Kumar v. CBI*, (2010) 9 SCC 368\n"
        "        on the standard at the discharge stage — court must sift the "
        "        evidence to see if a prima facie case exists, but must not "
        "        weigh as at trial.\n"
        "     6. Continuation of proceedings would amount to abuse of process.\n"
        "  7. PRAYER:\n"
        "       a) Discharge the accused-applicant from all the offences alleged.\n"
        "       b) Any other relief as deemed fit.\n"
        "  8. Signature: 'Through' <advocate_name>.\n"
        "  9. Place + Date.\n"
        " 10. VERIFICATION.\n\n"
        "Tone: factually meticulous, citation-grounded. If lang='hi' use vocab: "
        "उन्मोचन, प्रथम दृष्टया मामला, अभियोजन साक्ष्य. Return plain text."
    ),
    "example_prompts": [
        "Discharge application for Ramesh Pal in Sessions case 45/2026, S.302 IPC — no eye witness",
        "उन्मोचन आवेदन — मेरे मुवक्किल के विरुद्ध कोई प्रथम दृष्टया मामला नहीं बनता, चार्जशीट कमज़ोर है",
    ],
}


# ---------------------------------------------------------------- Maintenance
MAINTENANCE = {
    "id":         "maintenance",
    "name_en":    "Maintenance Petition (S.144 BNSS / S.125 CrPC)",
    "name_hi":    "भरण-पोषण याचिका (धारा 144 BNSS / 125 दं.प्र.सं.)",
    "category":   "family",
    "tier":       2,
    "description": "Maintenance for wife / children / parents unable to maintain themselves.",
    "fields": [
        {"key": "court_name",        "label_en": "Court",                       "label_hi": "न्यायालय",                "type": "text",     "required": True, "hint": "Family Court or JM First Class with jurisdiction", "section": "court"},
        {"key": "petitioner_name",   "label_en": "Petitioner name",             "label_hi": "याचिकाकर्ता का नाम",      "type": "name",     "required": True, "hint": "Wife / child / parent claiming maintenance", "section": "petitioner"},
        {"key": "petitioner_father", "label_en": "Petitioner father's name",    "label_hi": "पिता का नाम",             "type": "name",     "required": False, "section": "petitioner"},
        {"key": "petitioner_address","label_en": "Petitioner address",          "label_hi": "याचिकाकर्ता का पता",     "type": "address",  "required": True, "section": "petitioner"},
        {"key": "petitioner_age",    "label_en": "Petitioner age",              "label_hi": "आयु",                     "type": "text",     "required": False, "section": "petitioner"},
        {"key": "respondent_name",   "label_en": "Respondent (husband) name",   "label_hi": "विपक्षी (पति) का नाम",     "type": "name",     "required": True, "section": "respondent"},
        {"key": "respondent_father", "label_en": "Respondent father's name",    "label_hi": "विपक्षी के पिता का नाम",  "type": "name",     "required": False, "section": "respondent"},
        {"key": "respondent_address","label_en": "Respondent address",          "label_hi": "विपक्षी का पता",          "type": "address",  "required": True, "section": "respondent"},
        {"key": "marriage_date",     "label_en": "Date of marriage",            "label_hi": "विवाह की दिनांक",         "type": "date",     "required": False, "section": "marriage"},
        {"key": "marriage_place",    "label_en": "Place of marriage",           "label_hi": "विवाह स्थल",              "type": "text",     "required": False, "section": "marriage"},
        {"key": "separation_date",   "label_en": "Date of separation",          "label_hi": "अलगाव की दिनांक",         "type": "date",     "required": False, "section": "marriage"},
        {"key": "children_details",  "label_en": "Children (if any)",           "label_hi": "बच्चे (यदि कोई हों)",    "type": "longtext", "required": False, "hint": "Names, ages, who has custody", "section": "marriage"},
        {"key": "respondent_income", "label_en": "Respondent's monthly income", "label_hi": "विपक्षी की मासिक आय",     "type": "text",     "required": True, "section": "respondent"},
        {"key": "petitioner_income", "label_en": "Petitioner's income (if any)","label_hi": "याचिकाकर्ता की आय",       "type": "text",     "required": False, "section": "petitioner"},
        {"key": "grounds_for_claim", "label_en": "Grounds for maintenance claim","label_hi": "भरण-पोषण के आधार",       "type": "longtext", "required": True, "hint": "cruelty / desertion / neglect / refusal to maintain", "section": "grounds"},
        {"key": "amount_sought",     "label_en": "Monthly maintenance sought (₹)","label_hi": "मासिक भरण-पोषण की मांग (₹)","type": "text", "required": True, "section": "income"},
        *_ADVOCATE_FIELDS,
    ],
    "format_spec": (
        "Generate a maintenance petition under Section 144 of the BNSS, 2023 "
        "(formerly Section 125 CrPC, 1973). Structure:\n\n"
        "  1. Header: 'IN THE FAMILY COURT AT <PLACE>' or 'IN THE COURT OF "
        "     CHIEF JUDICIAL MAGISTRATE AT <PLACE>'\n"
        "  2. 'Misc. Criminal Case (Maint.) No. ____ of <year>'\n"
        "  3. Cause title:\n"
        "       <Petitioner Name>, W/o or D/o <Father/Husband>, age ___,\n"
        "       R/o <Address>                                  ... PETITIONER\n"
        "                              VERSUS\n"
        "       <Respondent Name>, S/o ___, R/o ___           ... RESPONDENT\n"
        "  4. Title: 'PETITION UNDER SECTION 144 OF THE BNSS, 2023 (FORMERLY "
        "     SECTION 125 CrPC, 1973) FOR MAINTENANCE'\n"
        "  5. 'MOST RESPECTFULLY SHEWETH:'\n"
        "  6. Numbered paragraphs:\n"
        "     1. The petitioner is the legally wedded wife (or minor child / "
        "        dependent parent) of the respondent.\n"
        "     2. Marriage: date <marriage_date>, place <marriage_place> "
        "        (omit if not provided).\n"
        "     3. Children: <children_details> (omit if none).\n"
        "     4. Separation date / circumstances leading to separation "
        "        (using <separation_date> and <grounds_for_claim>).\n"
        "     5. Grounds for maintenance — specific instances of cruelty, "
        "        desertion, neglect, or refusal to maintain. Use <grounds_for_claim>.\n"
        "     6. Respondent's income: <respondent_income>. Mention sources of "
        "        income (salary, business, agricultural, rental).\n"
        "     7. Petitioner's income (or lack thereof): <petitioner_income>. "
        "        State explicitly the inability to maintain herself / themselves.\n"
        "     8. Standard of living during cohabitation — to claim maintenance "
        "        consistent with that standard.\n"
        "     9. Cite the standard for maintenance under S.144 BNSS — see "
        "        *Rajnesh v. Neha*, (2021) 2 SCC 324 (uniform format affidavit "
        "        of assets & liabilities; criteria for quantum).\n"
        "  7. PRAYER:\n"
        "       a) Direct the respondent to pay ₹<amount_sought> per month as "
        "          maintenance to the petitioner.\n"
        "       b) Direct payment of arrears from the date of application.\n"
        "       c) Cost of litigation.\n"
        "       d) Such other relief as this Hon'ble Court may deem fit.\n"
        "  8. Signature: 'Through' <advocate_name>.\n"
        "  9. Place + Date.\n"
        " 10. VERIFICATION.\n\n"
        "If lang='hi': use vocab भरण-पोषण, क्रूरता, उपेक्षा, परित्याग, "
        "अनुरक्षण. Return plain text."
    ),
    "example_prompts": [
        "Maintenance petition for my client wife Sunita Sharma vs husband Vikesh — ₹15000/month",
        "मेरी मुवक्किल को पति ने 2 साल से छोड़ दिया है, भरण-पोषण याचिका चाहिए",
    ],
}


# ---------------------------------------------------------------- Revision
REVISION_PETITION = {
    "id":         "revision_petition",
    "name_en":    "Criminal Revision (S.438 BNSS / S.397 CrPC)",
    "name_hi":    "आपराधिक पुनरीक्षण (धारा 438 BNSS / 397 दं.प्र.सं.)",
    "category":   "appeal",
    "tier":       2,
    "description": "Revision against magistrate / inferior court order — questions of legality, jurisdiction.",
        "uploads": [
        {
            "id":            "order_photo",
            "label_en":      "Impugned Order (photo or PDF)",
            "label_hi":      "विवादित आदेश (फोटो या PDF)",
            "sub_en":        "Upload the order being challenged — AI will extract case no, court, date",
            "sub_hi":        "जिस आदेश को चुनौती दे रहे हैं उसे अपलोड करें",
            "accept":        "image/*,application/pdf",
            "multiple":      False,
            "max_files":     4,
            "endpoint":      None,
            "fills_fields":  [],
        }
    ],
    "fields": [
        {"key": "court_name",          "label_en": "Revisional Court",              "label_hi": "पुनरीक्षण न्यायालय",          "type": "text",     "required": True, "hint": "Sessions Court (HC's order: HC). Revision lies to the next-higher court.", "section": "court"},
        {"key": "revisionist_name",    "label_en": "Revisionist name",              "label_hi": "पुनरीक्षणकर्ता का नाम",       "type": "name",     "required": True, "section": "petitioner"},
        {"key": "revisionist_father",  "label_en": "Father's name",                 "label_hi": "पिता का नाम",                 "type": "name",     "required": True, "section": "petitioner"},
        {"key": "revisionist_address", "label_en": "Address",                       "label_hi": "पता",                          "type": "address",  "required": True, "section": "petitioner"},
        {"key": "respondent_name",     "label_en": "Respondent",                    "label_hi": "विपक्षी",                     "type": "text",     "required": True, "hint": "Usually 'State' or the opposite party", "section": "respondent"},
        {"key": "impugned_court",      "label_en": "Court that passed impugned order","label_hi": "विवादित आदेश पारित न्यायालय","type": "text",    "required": True, "section": "order"},
        {"key": "impugned_case_no",    "label_en": "Case no. in impugned court",    "label_hi": "विवादित न्यायालय का केस क्रमांक","type": "text", "required": True, "section": "order"},
        {"key": "impugned_order_date", "label_en": "Date of impugned order",        "label_hi": "विवादित आदेश की दिनांक",      "type": "date",     "required": True, "section": "order"},
        {"key": "summary_of_order",    "label_en": "Summary of the impugned order", "label_hi": "विवादित आदेश का सार",          "type": "longtext", "required": True, "section": "order"},
        {"key": "grounds_for_revision","label_en": "Grounds for revision",          "label_hi": "पुनरीक्षण के आधार",            "type": "longtext", "required": True, "hint": "Illegality / impropriety / jurisdictional error", "section": "grounds"},
        *_ADVOCATE_FIELDS,
    ],
    "format_spec": (
        "Generate a criminal revision petition under Section 438 of the BNSS, "
        "2023 (formerly Section 397 read with 401 CrPC). Note: revision lies "
        "on a question of LEGALITY / propriety / jurisdiction — NOT on a "
        "reappreciation of evidence as in an appeal. Structure:\n\n"
        "  1. Header (caps): Court name (Sessions or HC depending on the "
        "     impugned court).\n"
        "  2. 'Criminal Revision No. ____ of <year>'\n"
        "  3. Cause title:\n"
        "       <Revisionist Name>, S/o <Father>, R/o <Address>  ... REVISIONIST\n"
        "                              VERSUS\n"
        "       <Respondent>                                      ... RESPONDENT\n"
        "  4. Title: 'PETITION UNDER SECTION 438 OF THE BNSS, 2023 (FORMERLY "
        "     SECTION 397 CrPC, 1973) FOR CRIMINAL REVISION OF THE ORDER "
        "     DATED <impugned_order_date> PASSED BY <impugned_court> IN CASE "
        "     NO. <impugned_case_no>'\n"
        "  5. 'MOST RESPECTFULLY SHEWETH:'\n"
        "  6. Numbered paragraphs:\n"
        "     1. Brief facts and procedural history leading to the impugned order.\n"
        "     2. Summary of the impugned order (using <summary_of_order>) — "
        "        attach a certified copy.\n"
        "     3. The present revision is being filed WITHIN the 90-day "
        "        limitation prescribed under the Limitation Act, 1963 read with "
        "        the BNSS. (If beyond, mention condonation of delay under §5 of "
        "        the Limitation Act, with reasons.)\n"
        "     4. The revisional jurisdiction is invoked on the following grounds "
        "        (using <grounds_for_revision>):\n"
        "        (a) Patent illegality / error apparent on the face of the record\n"
        "        (b) Jurisdictional error — the impugned court acted without / in "
        "            excess of jurisdiction\n"
        "        (c) Manifest impropriety in exercise of discretion\n"
        "        (d) Misreading / non-consideration of material evidence\n"
        "     5. Cite *Amar Nath v. State of Haryana*, (1977) 4 SCC 137 and "
        "        *State of Orissa v. Debendra Nath Padhi*, (2005) 1 SCC 568 "
        "        on the scope of revisional jurisdiction.\n"
        "     6. The impugned order has caused grave miscarriage of justice and "
        "        requires interference.\n"
        "  7. PRAYER:\n"
        "       a) Set aside / quash the impugned order dated <date> in case "
        "          no. <case_no>.\n"
        "       b) Stay further proceedings before the impugned court during "
        "          pendency of this revision.\n"
        "       c) Such other relief as deemed fit.\n"
        "  8. Signature: 'Through' <advocate_name>.\n"
        "  9. Place + Date.\n"
        " 10. VERIFICATION.\n\n"
        "If lang='hi' use vocab: पुनरीक्षण, क्षेत्राधिकार, अवैधता, "
        "विवेकाधिकार का दुरुपयोग. Return plain text."
    ),
    "example_prompts": [
        "Revision against JM Class 1 Gwalior's order dt 10.01.2026 dismissing my discharge plea",
        "Sessions Court ne maintenance kharij kiya — revision file karna hai",
    ],
}


# ---------------------------------------------------------------- Reply to Bail
REPLY_TO_BAIL = {
    "id":         "reply_to_bail",
    "name_en":    "Reply to Bail Application (Counter Affidavit)",
    "name_hi":    "जमानत आवेदन पर प्रत्युत्तर (प्रत्यावेदन)",
    "category":   "bail",
    "tier":       2,
    "description": "Counter affidavit filed by prosecution/complainant opposing the bail application.",
        "uploads": [
        {
            "id":            "fir_photo",
            "label_en":      "FIR Photo (all pages)",
            "label_hi":      "FIR की सभी पन्नों की फोटो",
            "sub_en":        "NCRB I.I.F.-I format · 1-8 pages · AI auto-fills FIR no, PS, sections, accused",
            "sub_hi":        "NCRB I.I.F.-I फॉर्मेट · 1-8 पन्ने · AI स्वतः FIR क्र., थाना, धाराएं, अभियुक्त भरेगा",
            "accept":        "image/*,application/pdf",
            "multiple":      True,
            "max_files":     8,
            "endpoint":      "/api/draft/ocr-fir",
            "fills_fields":  ["fir_number", "fir_date", "police_station", "district", "sections_str", "facts_narrative", "brief_facts_alleged"],
        }
    ],
    "fields": [
        {"key": "court_name",            "label_en": "Court",                       "label_hi": "न्यायालय",                "type": "text",     "required": True, "section": "court"},
        {"key": "bail_application_no",   "label_en": "Bail Application No.",        "label_hi": "जमानत आवेदन क्रमांक",     "type": "text",     "required": True, "section": "mention"},
        {"key": "bail_application_date", "label_en": "Date of bail application",    "label_hi": "जमानत आवेदन की दिनांक",   "type": "date",     "required": False, "section": "mention"},
        {"key": "accused_name",          "label_en": "Accused (bail applicant)",    "label_hi": "अभियुक्त (जमानत आवेदक)",  "type": "name",     "required": True, "section": "respondent"},
        {"key": "fir_number",            "label_en": "FIR No.",                     "label_hi": "FIR क्रमांक",             "type": "text",     "required": True, "section": "fir"},
        {"key": "police_station",        "label_en": "Police Station",              "label_hi": "पुलिस थाना",              "type": "text",     "required": True, "section": "fir"},
        {"key": "sections_str",          "label_en": "Sections",                    "label_hi": "धाराएं",                  "type": "section_list", "required": True, "section": "fir"},
        {"key": "deponent_name",         "label_en": "Deponent's name",             "label_hi": "शपथकर्ता का नाम",         "type": "name",     "required": True, "hint": "Usually I.O. / S.P. / complainant", "section": "respondent"},
        {"key": "deponent_designation",  "label_en": "Deponent's designation",      "label_hi": "शपथकर्ता का पद",          "type": "text",     "required": True, "section": "respondent"},
        {"key": "grounds_for_opposing",  "label_en": "Grounds for opposing bail",   "label_hi": "जमानत का विरोध करने के आधार","type": "longtext", "required": True, "hint": "Gravity, evidence, flight risk, witness tampering, prior record", "section": "grounds"},
        {"key": "investigation_status",  "label_en": "Status of investigation",     "label_hi": "जांच की स्थिति",          "type": "longtext", "required": False, "hint": "What's collected so far, what's pending", "section": "mention"},
        {"key": "filing_party",          "label_en": "Filing on behalf of",         "label_hi": "किस ओर से दाखिल",         "type": "text",     "required": True, "hint": "Prosecution / Complainant / Both", "section": "respondent"},
        *_ADVOCATE_FIELDS,
    ],
    "format_spec": (
        "Generate a counter affidavit (reply) opposing a bail application. "
        "Structure:\n\n"
        "  1. Header: Court name in caps.\n"
        "  2. 'In re: Bail Application No. <bail_application_no> of <year>'\n"
        "  3. Cause title: '<Accused Name> ... Applicant\\nVERSUS\\nState of <State> "
        "     ... Respondent'\n"
        "  4. Title: 'COUNTER AFFIDAVIT / REPLY ON BEHALF OF THE "
        "     <filing_party> TO BAIL APPLICATION NO. <bail_application_no>'\n"
        "  5. Affidavit lead-in: 'I, <deponent_name>, <deponent_designation>, "
        "     do hereby solemnly affirm and state on oath as follows:—'\n"
        "  6. Numbered paragraphs:\n"
        "     1. I am the deponent and well-acquainted with the facts of the "
        "        case, having investigated the matter / suffered the offence "
        "        in person.\n"
        "     2. I have perused the bail application dated <bail_application_date> "
        "        filed by the accused and I am filing this counter to oppose "
        "        the said application and bring relevant facts on record.\n"
        "     3. The accused is involved in FIR No. <fir_number> at P.S. "
        "        <police_station> under sections <sections_str>. The offences "
        "        are grave and the evidence collected so far establishes a "
        "        prima facie case (using <investigation_status>).\n"
        "     4. Para-wise reply: each paragraph of the bail application is "
        "        addressed; correct facts are placed on record where the "
        "        applicant has suppressed or misstated.\n"
        "     5. Grounds for opposing bail (using <grounds_for_opposing>) — "
        "        cover all applicable heads:\n"
        "        (a) Gravity of the offence and likely sentence on conviction\n"
        "        (b) Strength of evidence on record\n"
        "        (c) Reasonable apprehension of evidence tampering / witness "
        "            intimidation\n"
        "        (d) Flight risk / no fixed roots in society\n"
        "        (e) Likelihood of repeating the offence\n"
        "        (f) Prior criminal antecedents (if any)\n"
        "     6. Cite *State of UP v. Amarmani Tripathi*, (2005) 8 SCC 21 and "
        "        *P. Chidambaram v. Directorate of Enforcement*, (2019) on the "
        "        principles guiding bail; *Anil Kumar Yadav v. State (NCT Delhi)*, "
        "        (2018) 12 SCC 129 on relevant considerations.\n"
        "  7. PRAYER: 'It is therefore most respectfully prayed that this "
        "     Hon'ble Court may be pleased to reject / dismiss the bail "
        "     application No. <bail_application_no> filed by the accused.'\n"
        "  8. Signature: Deponent + Through Counsel <advocate_name>.\n"
        "  9. Verification: 'Verified at <place> on this <date> that the "
        "     contents of paras 1 to N are true to my personal knowledge based "
        "     on the case diary / records / information received in official "
        "     capacity and nothing material has been concealed.'\n\n"
        "If lang='hi' use vocab: प्रत्यावेदन, शपथपत्र, अभियुक्त, गंभीरता, "
        "साक्ष्य के साथ छेड़छाड़, फरारी का संदेह. Return plain text."
    ),
    "example_prompts": [
        "Reply to bail application no 234/2026 — accused tried to threaten witness yesterday",
        "Counter to anticipatory bail — accused has 3 prior FIRs in similar cases",
    ],
}


# ---------------------------------------------------------------- Appeal
APPEAL_CONVICTION = {
    "id":         "appeal_conviction",
    "name_en":    "Appeal against Conviction (S.415/419 BNSS / S.374 CrPC)",
    "name_hi":    "दोषसिद्धि के विरुद्ध अपील (धारा 415/419 BNSS / 374 दं.प्र.सं.)",
    "category":   "appeal",
    "tier":       2,
    "description": "Appeal by a convicted accused before the Sessions / High Court / Supreme Court.",
        "uploads": [
        {
            "id":            "order_photo",
            "label_en":      "Impugned Order (photo or PDF)",
            "label_hi":      "विवादित आदेश (फोटो या PDF)",
            "sub_en":        "Upload the order being challenged — AI will extract case no, court, date",
            "sub_hi":        "जिस आदेश को चुनौती दे रहे हैं उसे अपलोड करें",
            "accept":        "image/*,application/pdf",
            "multiple":      False,
            "max_files":     4,
            "endpoint":      None,
            "fills_fields":  [],
        }
    ],
    "fields": [
        {"key": "court_name",        "label_en": "Appellate court",                 "label_hi": "अपीलीय न्यायालय",         "type": "text",     "required": True, "hint": "Sessions (for Mag convictions); HC (for Sessions convictions); SC (for HC convictions)", "section": "court"},
        {"key": "appellant_name",    "label_en": "Appellant (convict) name",        "label_hi": "अपीलार्थी का नाम",        "type": "name",     "required": True, "section": "petitioner"},
        {"key": "appellant_father",  "label_en": "Father's name",                   "label_hi": "पिता का नाम",             "type": "name",     "required": True, "section": "petitioner"},
        {"key": "appellant_address", "label_en": "Address",                         "label_hi": "पता",                     "type": "address",  "required": True, "section": "petitioner"},
        {"key": "convicting_court",  "label_en": "Convicting court (trial court)",  "label_hi": "दोषसिद्ध करने वाला न्यायालय","type": "text",    "required": True, "section": "order"},
        {"key": "trial_case_no",     "label_en": "Trial case number",               "label_hi": "विचारण केस क्रमांक",      "type": "text",     "required": True, "section": "order"},
        {"key": "conviction_date",   "label_en": "Date of conviction judgment",     "label_hi": "दोषसिद्धि की दिनांक",     "type": "date",     "required": True, "section": "order"},
        {"key": "sections_convicted","label_en": "Sections convicted under",        "label_hi": "जिन धाराओं में दोषसिद्धि","type": "section_list", "required": True, "section": "order"},
        {"key": "sentence_passed",   "label_en": "Sentence",                        "label_hi": "सज़ा",                    "type": "text",     "required": True, "hint": "e.g. '7 years RI + ₹50,000 fine'", "section": "order"},
        {"key": "current_jail",      "label_en": "Current jail (if in custody)",    "label_hi": "वर्तमान कारागार",         "type": "text",     "required": False, "section": "order"},
        {"key": "grounds_for_appeal","label_en": "Grounds of appeal",               "label_hi": "अपील के आधार",            "type": "longtext", "required": True, "hint": "Errors of law / fact / appreciation of evidence", "section": "grounds"},
        {"key": "facts_narrative",   "label_en": "Brief facts of prosecution case", "label_hi": "अभियोजन के संक्षिप्त तथ्य","type": "longtext", "required": True, "section": "grounds"},
        *_ADVOCATE_FIELDS,
    ],
    "format_spec": (
        "Generate an appeal against conviction under Section 415 / 419 of the "
        "BNSS, 2023 (formerly Section 374 CrPC). Structure:\n\n"
        "  1. Header: Appellate court name in caps.\n"
        "  2. 'Criminal Appeal No. ____ of <year>'\n"
        "  3. Cause title:\n"
        "       <Appellant Name>, S/o <Father>, R/o <Address>,\n"
        "       presently lodged at <current_jail if given>     ... APPELLANT\n"
        "                              VERSUS\n"
        "       State of <State>                                 ... RESPONDENT\n"
        "  4. Title: 'APPEAL UNDER SECTION 415 BNSS, 2023 (FORMERLY SECTION 374 "
        "     CrPC, 1973) AGAINST THE JUDGMENT AND ORDER OF CONVICTION DATED "
        "     <conviction_date> PASSED BY <convicting_court> IN CASE NO. "
        "     <trial_case_no>, CONVICTING THE APPELLANT UNDER SECTIONS "
        "     <sections_convicted> AND SENTENCING HIM TO <sentence_passed>'\n"
        "  5. 'MOST RESPECTFULLY SHEWETH:'\n"
        "  6. Numbered paragraphs:\n"
        "     1. Profile of the appellant; clean antecedents (if applicable).\n"
        "     2. Brief facts of prosecution (using <facts_narrative>).\n"
        "     3. Trial: list of charges framed, witnesses examined, documents "
        "        exhibited, defence taken.\n"
        "     4. The impugned judgment dated <conviction_date> convicted the "
        "        appellant under <sections_convicted> and imposed <sentence_passed>.\n"
        "     5. The appellant being aggrieved by the impugned judgment, "
        "        prefers this appeal within the prescribed limitation.\n"
        "     6. GROUNDS OF APPEAL (each as a numbered ground, A, B, C…) — "
        "        using <grounds_for_appeal>. Cover applicable heads:\n"
        "        A. The learned trial court erred in appreciating the "
        "           prosecution evidence; benefit of doubt not extended.\n"
        "        B. Material contradictions / improvements in PW statements "
        "           ignored.\n"
        "        C. Recovery / forensic evidence not legally proved.\n"
        "        D. Defence witnesses / documents not duly considered.\n"
        "        E. Sentence is excessive / disproportionate to the offence "
        "           and the appellant's role.\n"
        "        F. Mandatory presumptions / standards (e.g. proof beyond "
        "           reasonable doubt) not applied.\n"
        "     7. Cite *Sharad Birdhichand Sarda v. State of Maharashtra*, (1984) "
        "        4 SCC 116 (circumstantial evidence) or other apex-court "
        "        decisions relevant to the grounds.\n"
        "  7. PRAYER:\n"
        "       a) Set aside the impugned judgment dated <conviction_date> "
        "          and acquit the appellant.\n"
        "       b) In the alternative, reduce the sentence to the period "
        "          already undergone.\n"
        "       c) Suspend the sentence and release the appellant on bail "
        "          during pendency of the appeal.\n"
        "       d) Such other relief as deemed fit.\n"
        "  8. Signature: 'Through' <advocate_name>.\n"
        "  9. Place + Date.\n"
        " 10. VERIFICATION.\n\n"
        "Tone: precise, evidence-anchored. If lang='hi' use vocab: अपील, "
        "दोषसिद्धि, सज़ा, अपीलार्थी, सत्र न्यायालय. Return plain text."
    ),
    "example_prompts": [
        "Appeal against Sessions court conviction in 302 IPC — eye witnesses contradicted themselves",
        "मेरे मुवक्किल को 7 साल की सज़ा हुई है, सत्र न्यायालय का फैसला अपील में चुनौती देनी है",
    ],
}


# ============================================================================
# REGISTRY
# ============================================================================

TEMPLATES: dict[str, dict] = {
    # Tier 1 — daily
    VAKALATNAMA["id"]:        VAKALATNAMA,
    MENTION_MEMO["id"]:       MENTION_MEMO,
    ANTICIPATORY_BAIL["id"]:  ANTICIPATORY_BAIL,
    QUASHING_PETITION["id"]:  QUASHING_PETITION,
    WRIT_PETITION["id"]:      WRIT_PETITION,
    # Tier 2 — weekly
    DEFAULT_BAIL["id"]:       DEFAULT_BAIL,
    DISCHARGE_APPLICATION["id"]: DISCHARGE_APPLICATION,
    MAINTENANCE["id"]:        MAINTENANCE,
    REVISION_PETITION["id"]:  REVISION_PETITION,
    REPLY_TO_BAIL["id"]:      REPLY_TO_BAIL,
    APPEAL_CONVICTION["id"]:  APPEAL_CONVICTION,
}


def list_templates_slim() -> list[dict]:
    """Slim metadata for the FE picker."""
    return [
        {"id": t["id"], "name_en": t["name_en"], "name_hi": t["name_hi"],
         "category": t.get("category"), "tier": t.get("tier"),
         "description": t.get("description"),
         "example_prompts": t.get("example_prompts", [])}
        for t in TEMPLATES.values()
    ]


def get_template(doc_type: str) -> dict | None:
    return TEMPLATES.get(doc_type)
