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
        {"key": "court_name",          "label_en": "Court name",                "label_hi": "न्यायालय का नाम",        "type": "text",      "required": True,  "hint": "e.g. 'Court of the Sessions Judge, Lucknow' or 'High Court of Delhi'", "section": "court"},
        {"key": "case_no",             "label_en": "Case / Crime number",       "label_hi": "केस / अपराध क्रमांक",   "type": "text",      "required": False, "hint": "If a case number is assigned", "section": "court"},
        {"key": "client_name",         "label_en": "Client (party) name",       "label_hi": "मुवक्किल का नाम",       "type": "name",      "required": True, "section": "client"},
        {"key": "client_father",       "label_en": "Client father's name",      "label_hi": "मुवक्किल के पिता का नाम", "type": "name",      "required": True, "section": "client"},
        {"key": "client_address",      "label_en": "Client address",            "label_hi": "मुवक्किल का पता",         "type": "address",   "required": True, "section": "client"},
        {"key": "party_role",          "label_en": "Party role",                "label_hi": "पक्षकार की भूमिका",        "type": "text",      "required": True,  "hint": "applicant / petitioner / respondent / accused / plaintiff", "section": "client"},
        {"key": "opposite_party",      "label_en": "Opposite party",            "label_hi": "विपक्षी पक्ष",            "type": "text",      "required": False, "hint": "e.g. 'State of Maharashtra' for criminal matters", "section": "client"},
        {"key": "advocate_name",       "label_en": "Advocate name",             "label_hi": "अधिवक्ता का नाम",         "type": "name",      "required": True, "section": "filing"},
        {"key": "advocate_enrollment", "label_en": "Bar Council enrolment no.", "label_hi": "बार काउंसिल पंजीयन क्रमांक","type": "text",      "required": False, "hint": "e.g. 'D/1234/2018'", "section": "advocate"},
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
        "OUTPUT IS HINDI (Devanagari) BY DEFAULT (English only if lang='en'). "
        "Use the standard Indian वकालतनामा wording: heading 'वकालतनामा' (centred); "
        "court line; party block '<party_role> <client> पुत्र श्री <father>, निवासी "
        "<address>' और 'बनाम <opposite_party>'; then the authorisation — 'मैं/हम "
        "उपरोक्त एतद् द्वारा अधिवक्ता <advocate> को अपना अधिवक्ता नियुक्त कर निम्न "
        "अधिकार प्रदान करता/करती हूँ:' covering — मेरी ओर से उपस्थित होना, पैरवी व "
        "बहस करना, आवेदन/दस्तावेज प्रस्तुत व वापस लेना, साक्ष्य देना व प्रतिपरीक्षा, "
        "राशि/दस्तावेज प्राप्त करना, समझौता/राजीनामा व आवेदन-वापसी (निर्देशानुसार), "
        "तथा आवश्यकता पर अन्य अधिवक्ता नियुक्त करना; अधिवक्ता के कृत्यों की "
        "जिम्मेदारी मुवक्किल की होगी; फिर 'स्वीकृत है — अधिवक्ता <advocate>, पंजीयन "
        "क्रमांक ___'; then client + advocate signatures with स्थान व दिनांक. "
        "Vocab: माननीय न्यायालय, मुवक्किल, अधिवक्ता, अधिकृत, हस्ताक्षर. "
        "Plain text — no markdown."
    ),
    "example_prompts": [
        "मुझे लखनऊ सेशन कोर्ट के लिए वकालतनामा चाहिए, मेरे मुवक्किल अनिल वर्मा के लिए",
        "Need a vakalatnama for my client Vivek Sharma in the Delhi High Court",
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
        {"key": "court_name",      "label_en": "Court",                       "label_hi": "न्यायालय",                "type": "text",  "required": True,  "hint": "e.g. 'Supreme Court of India' or 'High Court of Delhi'", "section": "court"},
        {"key": "case_no",         "label_en": "Case number",                 "label_hi": "केस क्रमांक",             "type": "text",  "required": True,  "hint": "e.g. 'Crl. Appeal 1234/2025' or 'WP(C) 567/2026'", "section": "court"},
        {"key": "case_title",      "label_en": "Case title (parties)",        "label_hi": "केस शीर्षक (पक्षकार)",    "type": "text",  "required": True,  "hint": "e.g. 'Vikesh Sharma vs State of Maharashtra'", "section": "court"},
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
        "Need to mention WP 567/2026 before the High Court — stay order is expiring tomorrow",
    ],
}


# ----------------------------------------------------------- Anticipatory Bail
ANTICIPATORY_BAIL = {
    "id":         "anticipatory_bail",
    # DEDUPE: the polished bail canvas (FIR-OCR + live preview) handles §438
    # anticipatory bail far better than this v1 form. Auto-redirect there.
    "redirect_url": "/draft/bail?court=hc&section=438",
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
        "अग्रिम जमानत चाहिए, मुवक्किल विकेश शर्मा, धारा 420, FIR नंबर 95/2025, थाना कोतवाली",
        "Anticipatory bail for Anil Verma, S.420 IPC, FIR 95/2025 PS Sadar",
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
        {"key": "court_name",        "label_en": "High Court",                 "label_hi": "उच्च न्यायालय",              "type": "text",     "required": True, "hint": "e.g. 'High Court of Delhi'", "section": "court"},
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
        "OUTPUT IS HINDI (Devanagari) BY DEFAULT — this is filed in the MP High "
        "Court in Hindi; produce English only if lang='en'. Match Vishnu Ji's real "
        "§482 filing: case line 'एम.सी.आर.सी. ____/<वर्ष>'; section phrased "
        "'धारा 528 भा.ना.सु.सं. (482 दं.प्र.सं.)'; title 'याचिका अन्तर्गत धारा 528 "
        "भा.ना.सु.सं. (482 दं.प्र.सं.) मय शपथपत्र'; grounds open with 'यह कि' and "
        "invoke the Bhajan Lal categories; prayer to quash the FIR. After the "
        "petition add a SEPARATE 'शपथ पत्र' (name/पिता/आयु/व्यवसाय/निवासी block, then "
        "'यह कि' truth clauses, then 'सत्यापन' + signature), then a short 'इंडेक्स' "
        "listing the petition (मय शपथपत्र) and the FIR copy as एनेक्जर ए-1. Court "
        "Hindi: माननीय न्यायालय, याचिकाकर्ता, निरस्तीकरण, अंतर्निहित अधिकार. "
        "Plain text only — no markdown."
    ),
    "example_prompts": [
        "High Court ke liye quashing chahiye, FIR 95/2025 PS Sadar, S 420 IPC, civil dispute",
        "Need to quash FIR 234/2025 — false complaint by complainant, my client has settled",
    ],
}


# ---------------------------------------------------------------- Writ Petition
# Structure mirrors the MP HC Article 226 writ standard (Rule 25 of the MP HC
# Rules, 2008): Declaration → Particulars → Other-proceedings → Remedies →
# Delay → Facts (5.x) → Grounds (6.x) → Relief (a,b,c) → Interim Relief →
# Documents → Caveat → Signature → Affidavit + Verification + List of Documents.
# Reference: Sandeep Bairagi v. State (MP HC writ challenging an SDO order
# under Section 129(5) of the MP Land Revenue Code).
WRIT_PETITION = {
    "id":         "writ_petition",
    "name_en":    "Writ Petition (Article 226)",
    "name_hi":    "रिट याचिका (अनुच्छेद 226)",
    "category":   "writ",
    "tier":       1,
    "description": "High Court writ — mandamus, certiorari, habeas corpus, prohibition, quo warranto.",
    "uploads": [
        {
            "id":            "impugned_order",
            "label_en":      "Impugned Order (photo or PDF)",
            "label_hi":      "विवादित आदेश (फोटो या PDF)",
            "sub_en":        "Upload the order being challenged · 1-8 pages · AI auto-fills authority, case no, date, subject",
            "sub_hi":        "जिस आदेश को चुनौती दे रहे हैं उसे अपलोड करें · 1-8 पन्ने · AI स्वतः प्राधिकारी, केस क्र., दिनांक भरेगा",
            "accept":        "image/*,application/pdf",
            "multiple":      True,
            "max_files":     8,
            "endpoint":      "/api/draft/ocr-impugned-order",
            "fills_fields":  [
                "impugned_authority", "impugned_case_no", "impugned_order_date",
                "impugned_passed_by", "petitioner_name", "petitioner_father",
                "petitioner_address", "subject_summary", "operative_direction",
                "respondent_authority", "statutes_invoked", "earlier_proceeding_ref",
                "place_district",
            ],
        }
    ],
    "fields": [
        # ---- Court & writ identity ----
        {"key": "court_name",         "label_en": "High Court",                  "label_hi": "उच्च न्यायालय",                 "type": "text",     "required": True,  "hint": "e.g. 'High Court of Delhi' or 'High Court of Judicature at Bombay'", "section": "court"},
        {"key": "bench_location",     "label_en": "Bench location",              "label_hi": "खण्डपीठ",                       "type": "text",     "required": False, "hint": "e.g. 'Lucknow Bench' / 'Aurangabad Bench' — if the High Court has one", "section": "court"},
        {"key": "writ_type",          "label_en": "Type of writ",                "label_hi": "रिट का प्रकार",                 "type": "text",     "required": True,  "hint": "mandamus / certiorari / habeas corpus / prohibition / quo warranto", "section": "court"},
        {"key": "writ_category",      "label_en": "Civil or Criminal writ",      "label_hi": "सिविल या आपराधिक रिट",        "type": "text",     "required": False, "hint": "WP(C) = Civil, WP(Crl) = Criminal", "section": "court"},
        {"key": "subject_summary",    "label_en": "Subject of writ (one line)",  "label_hi": "विषय (एक पंक्ति)",              "type": "text",     "required": True,  "hint": "e.g. 'For quashing the SDO order dated 31.03.2026 under §129(5) MPLRC'", "section": "court"},

        # ---- Petitioner (aggrieved party) ----
        {"key": "petitioner_name",    "label_en": "Petitioner name",             "label_hi": "याचिकाकर्ता",                   "type": "name",     "required": True, "section": "petitioner"},
        {"key": "petitioner_father",  "label_en": "Father's / husband's name",   "label_hi": "पिता / पति का नाम",             "type": "name",     "required": True, "section": "petitioner"},
        {"key": "petitioner_age",     "label_en": "Age",                         "label_hi": "आयु",                            "type": "text",     "required": False, "section": "petitioner"},
        {"key": "petitioner_occupation","label_en": "Occupation",                "label_hi": "व्यवसाय",                        "type": "text",     "required": False, "section": "petitioner"},
        {"key": "petitioner_address", "label_en": "Address",                     "label_hi": "पता",                            "type": "address",  "required": True, "section": "petitioner"},

        # ---- Respondents ----
        {"key": "respondent_authority","label_en": "Respondents (one per line, numbered)", "label_hi": "विपक्षी प्राधिकारी (एक प्रति पंक्ति, क्रमांकित)", "type": "longtext", "required": True, "hint": "e.g.\n1. State of MP, through Principal Secretary, Revenue Department, Vallabh Bhawan, Bhopal\n2. Collector, Vidisha\n3. Sub-Divisional Officer (Revenue), Vidisha", "section": "respondent"},

        # ---- Para 1 — Particulars of the impugned order(s) (Rule 25(2)(a) MP HC Rules) ----
        {"key": "impugned_authority", "label_en": "Authority that passed the order","label_hi": "आदेश पारित करने वाला प्राधिकारी","type": "text", "required": True, "hint": "e.g. 'Sub-Divisional Officer, Vidisha'", "section": "order"},
        {"key": "impugned_case_no",   "label_en": "Case / reference number",     "label_hi": "केस / संदर्भ क्रमांक",          "type": "text",     "required": True, "hint": "e.g. '144/B-121/2025-26'", "section": "order"},
        {"key": "impugned_order_date","label_en": "Order date",                  "label_hi": "आदेश की दिनांक",                "type": "date",     "required": True, "section": "order"},
        {"key": "impugned_passed_by", "label_en": "Officer who signed",          "label_hi": "हस्ताक्षरकर्ता अधिकारी",         "type": "text",     "required": False, "section": "order"},
        {"key": "operative_direction","label_en": "Operative direction of the order","label_hi": "आदेश का प्रवर्तनीय भाग",     "type": "longtext", "required": True, "hint": "1-3 sentences — exactly what the order directs", "section": "order"},
        {"key": "earlier_proceeding_ref","label_en": "Earlier order (if this is an appeal/revision)","label_hi": "पूर्व आदेश (यदि यह अपील/पुनरीक्षण है)","type": "longtext", "required": False, "hint": "Case no + date + authority of the earlier order — so the writ can challenge both", "section": "order"},
        {"key": "statutes_invoked",   "label_en": "Statutes invoked in the order","label_hi": "प्रयुक्त धाराएँ",                "type": "text",     "required": False, "hint": "e.g. '§129(5) MP Land Revenue Code'", "section": "order"},
        {"key": "place_district",     "label_en": "Place / district of the authority", "label_hi": "स्थान / जिला",          "type": "text",     "required": False, "section": "order"},

        # ---- Paras 2-4 — declarations required by Rule 25 ----
        {"key": "other_proceedings",  "label_en": "Other proceedings on this matter?", "label_hi": "क्या इसी मामले में अन्य कार्यवाही?", "type": "longtext", "required": False, "hint": "If yes — court + case no + status. If none, leave blank (template inserts standard declaration).", "section": "grounds"},
        {"key": "remedies_exhausted", "label_en": "Statutory remedies exhausted",   "label_hi": "वैधानिक उपचार समाप्त",          "type": "longtext", "required": True,  "hint": "Which appeals/revisions were filed (or why an alternative remedy is inadequate / unavailable)", "section": "grounds"},
        {"key": "delay_explanation",  "label_en": "Delay (if any) and explanation", "label_hi": "विलम्ब (यदि कोई हो)",          "type": "longtext", "required": False, "hint": "If filed beyond 90 days from cause of action, explain", "section": "grounds"},

        # ---- Para 5 — Facts ----
        {"key": "facts_narrative",    "label_en": "Facts (chronological — will be auto-numbered 5.1, 5.2, …)", "label_hi": "तथ्य (कालक्रम अनुसार — 5.1, 5.2 ... स्वतः क्रमांकित होंगे)", "type": "longtext", "required": True, "section": "grounds"},

        # ---- Para 6 — Grounds ----
        {"key": "grounds_for_writ",   "label_en": "Grounds (each on its own line — will be auto-numbered 6.1, 6.2, …)", "label_hi": "आधार (हर एक नई पंक्ति में — 6.1, 6.2 ... स्वतः क्रमांकित होंगे)", "type": "longtext", "required": True, "hint": "Statutory infirmity, violation of natural justice, jurisdictional error, breach of Article 14/19/21/300A — one ground per line.", "section": "grounds"},

        # ---- Para 7 — Relief ----
        {"key": "relief_sought",      "label_en": "Reliefs prayed (a, b, c …)",   "label_hi": "प्रार्थित अनुतोष (अ, ब, स …)", "type": "longtext", "required": True, "section": "grounds"},

        # ---- Para 8 — Interim relief ----
        {"key": "interim_relief",     "label_en": "Interim relief sought",        "label_hi": "अंतरिम अनुतोष",                  "type": "longtext", "required": False, "hint": "e.g. 'Stay the operation of the impugned order pending hearing'", "section": "grounds"},

        # ---- Para 9-10 — Documents + Caveat ----
        {"key": "list_of_documents",  "label_en": "List of documents / annexures",  "label_hi": "दस्तावेजों की सूची / अनुलग्नक", "type": "longtext", "required": True,  "hint": "One per line — e.g.\nP-1: Impugned order dated 31.03.2026\nP-2: Tehsildar order dated 20.06.2025\nP-3: Revenue records", "section": "grounds"},
        {"key": "caveat_filed",       "label_en": "Has the respondent filed a caveat?", "label_hi": "क्या विपक्षी ने केवेट दाखिल किया है?", "type": "text", "required": False, "hint": "Yes / No", "section": "grounds"},

        # ---- Affidavit deponent (Rule 25(3) — verification by affidavit) ----
        {"key": "affidavit_deponent", "label_en": "Affidavit deponent",           "label_hi": "शपथ-पत्र का प्रस्तुतकर्ता",     "type": "name",     "required": False, "hint": "Usually the petitioner. Leave blank to default to petitioner.", "section": "grounds"},

        *_ADVOCATE_FIELDS,
    ],
    "format_spec": (
        "Generate a complete WRIT PETITION under Article 226 of the Constitution "
        "of India for the High Court named by the user — structured per that "
        "High Court's writ rules. Use the court name and bench exactly as "
        "provided.\n\n"
        "Output FIVE sections in order, separated by clear page-break lines:\n\n"
        "════════ PAGE 1 — THE PETITION ════════\n\n"
        "  HEADER (left-aligned, bold caps):\n"
        "    IN THE <court_name>\n"
        "    (PRINCIPAL SEAT / BENCH AT <bench_location>)\n"
        "    WRIT PETITION (<writ_category or 'C'>) NO. _____ OF <year of filing_date>\n\n"
        "  CAUSE TITLE (two-column):\n"
        "    IN THE MATTER OF:\n"
        "    <petitioner_name>, S/o <petitioner_father>, aged about <petitioner_age> "
        "    years, occupation <petitioner_occupation>, R/o <petitioner_address>\n"
        "                                            ... PETITIONER\n"
        "                          VERSUS\n"
        "    <respondent_authority — render each numbered line on its own row>\n"
        "                                            ... RESPONDENTS\n\n"
        "  TITLE (centred, caps):\n"
        "    PETITION UNDER ARTICLE 226 OF THE CONSTITUTION OF INDIA SEEKING "
        "    ISSUANCE OF A WRIT IN THE NATURE OF <writ_type> <subject_summary>\n\n"
        "  'MAY IT PLEASE YOUR LORDSHIPS:' (then a single-line 'The Petitioner "
        "  above-named most respectfully begs to submit as under:').\n\n"
        "  DECLARATION (verbatim, as required by the High Court's writ rules):\n"
        "    'The Petitioner has not filed any other Writ Petition before this "
        "    Hon'ble Court or any other High Court of the country or Hon'ble Supreme "
        "    Court of India on the same subject matter, except as disclosed in "
        "    Paragraph 2 below.'\n\n"
        "  NUMBERED PARAGRAPHS:\n\n"
        "    1. PARTICULARS OF THE IMPUGNED ORDER\n"
        "       (a) Date of impugned order ........... <impugned_order_date>\n"
        "       (b) Case / Reference No. ............ <impugned_case_no>\n"
        "       (c) Passed by ........................ <impugned_passed_by> "
        "           (<impugned_authority>)\n"
        "       (d) Statute invoked .................. <statutes_invoked>\n"
        "       (e) Subject matter ................... <operative_direction>\n"
        "       (Annexure P-1: certified copy of the impugned order.)\n"
        "       If <earlier_proceeding_ref> is filled, add sub-paragraph 1A with the "
        "       earlier order's particulars (date, case no, authority) AND clarify "
        "       that the present writ challenges BOTH the impugned order and the "
        "       said earlier order. Add Annexure P-2 for the earlier order.\n\n"
        "    2. That the Petitioner has NOT filed any other Writ Petition / "
        "       proceeding on the same subject before this Court, any other High "
        "       Court, or the Supreme Court. [If <other_proceedings> is non-empty, "
        "       replace this paragraph with a candid disclosure of the other "
        "       proceedings.]\n\n"
        "    3. STATUTORY REMEDIES — that the Petitioner has exhausted the "
        "       statutory remedies available under the relevant statute, OR that "
        "       the alternative remedy is inadequate / illusory / not efficacious "
        "       in the facts of the present case. Use <remedies_exhausted> verbatim "
        "       expanded into formal court prose; where the remedy exists but is "
        "       inadequate, cite *Whirlpool Corporation v. Registrar of Trade "
        "       Marks*, (1998) 8 SCC 1 (writ maintainable despite alternative "
        "       remedy when (i) fundamental rights are violated, (ii) natural "
        "       justice is breached, (iii) action is wholly without jurisdiction).\n\n"
        "    4. DELAY — that there is no delay in approaching this Hon'ble Court. "
        "       [If <delay_explanation> is non-empty, expand it into a formal "
        "       explanation of the cause of action date and the reasons for any "
        "       delay; cite *Tilokchand Motichand v. H. B. Munshi*, (1969) 1 SCC 110 "
        "       only if relevant.]\n\n"
        "    5. FACTS OF THE CASE — expand <facts_narrative> into chronological "
        "       sub-paragraphs 5.1, 5.2, 5.3 … (one fact / event per sub-paragraph; "
        "       at least 5 sub-paragraphs; end with the impugned order and the "
        "       Petitioner's grievance against it). Each sub-paragraph begins 'That'.\n\n"
        "    6. GROUNDS — expand <grounds_for_writ> into lettered/numbered "
        "       sub-paragraphs 6.1, 6.2, 6.3 …. Each ground must tie to a "
        "       constitutional or statutory provision. Cover (where applicable):\n"
        "       - Jurisdictional error / want of authority\n"
        "       - Violation of natural justice (audi alteram partem, bias)\n"
        "       - Article 14 — arbitrariness, non-application of mind\n"
        "       - Article 19 / 21 / 300A — substantive infirmity\n"
        "       - Misreading / non-consideration of material on record\n"
        "       - Mala fides / colourable exercise of power\n"
        "       Each ground begins 'BECAUSE' (or 'क्योंकि' in Hindi).\n\n"
        "    7. RELIEF / PRAYER — expand <relief_sought> into lettered prayers:\n"
        "       (a) Issue a writ in the nature of <writ_type>, or any other "
        "           appropriate writ, order or direction, quashing / setting aside "
        "           the impugned order dated <impugned_order_date> passed by "
        "           <impugned_authority> in Case No. <impugned_case_no>.\n"
        "       (b) Direct the Respondents to <substantive direction derived from "
        "           <relief_sought>>.\n"
        "       (c) Award costs of the petition to the Petitioner.\n"
        "       (d) Pass such other and further orders as this Hon'ble Court may "
        "           deem fit in the facts and circumstances of the case.\n\n"
        "    8. INTERIM RELIEF — render <interim_relief> if non-empty, else a "
        "       standard line: 'During the pendency of the present writ petition, "
        "       the operation, execution and implementation of the impugned order "
        "       dated <impugned_order_date> may kindly be stayed in the interest "
        "       of justice.'\n\n"
        "    9. DOCUMENTS — that the documents annexed to this petition (listed "
        "       separately on the List of Documents page) are true copies of "
        "       their originals; the Petitioner reserves liberty to file additional "
        "       documents.\n\n"
        "   10. CAVEAT — 'No caveat has been received by the Petitioner.' "
        "       [If <caveat_filed> is 'Yes', invert to 'A caveat has been received "
        "       and a copy of this petition has been served on the caveator.']\n\n"
        "  SIGNATURE BLOCK (right-aligned):\n"
        "    Place: <place>\n"
        "    Date:  <filing_date>\n"
        "                                                    PETITIONER\n"
        "                                          Through, <advocate_name>\n"
        "                                          Counsel for the Petitioner\n\n"
        "════════ PAGE 2 — AFFIDAVIT ════════\n\n"
        "  Title: AFFIDAVIT (centred, bold caps).\n"
        "  Body: 'I, <affidavit_deponent or petitioner_name>, S/o <petitioner_father>, "
        "  aged about <petitioner_age> years, R/o <petitioner_address>, do hereby "
        "  solemnly affirm and declare on oath as under:\n"
        "  1. That I am the Petitioner in the present writ petition and am fully "
        "     conversant with the facts and circumstances of the case and am "
        "     competent to swear this affidavit.\n"
        "  2. That the contents of paragraphs 1 to 10 of the accompanying writ "
        "     petition have been read over to me, are true to my personal knowledge "
        "     and the documents annexed thereto are true copies of their originals.'\n\n"
        "  DEPONENT signature block (right) + VERIFICATION:\n"
        "    'Verified at <place> on this ___ day of <month> <year> that the "
        "    contents of the above affidavit are true and correct to the best of "
        "    my knowledge; no part of it is false and nothing material has been "
        "    concealed therefrom.'\n"
        "                                                       DEPONENT\n\n"
        "════════ PAGE 3 — LIST OF DOCUMENTS ════════\n\n"
        "  Title: LIST OF DOCUMENTS (centred, bold caps) + the same court / W.P. "
        "  No. header from page 1.\n"
        "  Tabular layout, three columns: S.No. | Description | Annexure / Pages.\n"
        "  Populate from <list_of_documents> — one entry per line; if a line "
        "  begins with 'P-N:' use that as the annexure label, else auto-number "
        "  P-1, P-2, P-3. Always include row 1: 'Writ Petition with Affidavit'.\n\n"
        "  Footer:\n"
        "    Place: <place>\n"
        "    Date:  <filing_date>\n"
        "                                          Through, <advocate_name>\n"
        "                                          Counsel for the Petitioner\n\n"
        "TONE & LANGUAGE RULES\n"
        "=====================\n"
        "- Formal Indian High Court legal English.\n"
        "- If lang='hi', render the ENTIRE document in formal Devanagari court "
        "  Hindi (माननीय उच्च न्यायालय, याचिकाकर्ता, विपक्षी, अनुच्छेद 226, "
        "  परमादेश रिट, उत्प्रेषण रिट, मौलिक अधिकार, आदेश दिनांकित, अंतरिम राहत, "
        "  शपथ-पत्र, सत्यापन). Names of parties / authorities / places stay in "
        "  the SAME SCRIPT they were entered in; do NOT auto-transliterate.\n"
        "- Statute citations ('Section 129(5) MP Land Revenue Code', 'Article 14 "
        "  of the Constitution') stay in the original Roman form even in a Hindi "
        "  draft — that is the courtroom convention.\n"
        "- Number every paragraph; sub-number where indicated (5.1, 6.2 etc.).\n"
        "- Return PLAIN TEXT (no markdown fences, no asterisks for emphasis). "
        "  Use the literal string '════════ PAGE N — TITLE ════════' on its own "
        "  line to mark each page break so the renderer can paginate."
    ),
    "example_prompts": [
        "Writ challenging SDO Vidisha order dated 31.03.2026 under §129(5) MPLRC",
        "Writ for arbitrary transfer order quashing — client transferred to Bastar with mala fides",
        "Habeas corpus petition — client illegally detained by the local police for 5 days",
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
    "name_en":    "Discharge — Sessions (S.250 BNSS / 227 CrPC)",
    "name_hi":    "उन्मोचन — सत्र न्यायालय (धारा 250 BNSS / 227 दं.प्र.सं.)",
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
        "OUTPUT IS HINDI (Devanagari) BY DEFAULT (English only if lang='en'). "
        "Match Vishnu Ji's real family-court §125 filing: cause-title 'न्यायालय "
        "माननीय प्रधान न्यायाधीश महोदय, कुटुम्ब न्यायालय <स्थान>'; case line "
        "'प्रकरण क्रमांक ____/<वर्ष> मु.फौ.'; applicants as 'आवेदकगण' (पत्नी + each "
        "child with आयु, नाबालिग सरपरस्त माँ); 'बनाम'; husband as 'अनावेदक'; title "
        "'आवेदन पत्र अन्तर्गत धारा 144 भा.ना.सु.सं. (125 दं.प्र.सं.)'; then "
        "'आवेदकगण की ओर से आवेदन निम्न प्रकार प्रस्तुत है :-' and 'यह कि' paras: "
        "विवाह, दहेज, क्रूरता/प्रताड़ना, घर से निकाला जाना, अनावेदक की आय व साधन, "
        "मांगी गई मासिक भरण-पोषण राशि, क्षेत्राधिकार. Prayer to grant the monthly "
        "भरण-पोषण; then a 'सत्यापन' block signed by the आवेदिका. Vocab: भरण-पोषण, "
        "क्रूरता, उपेक्षा, परित्याग, अनुरक्षण. Plain text."
    ),
    "example_prompts": [
        "Maintenance petition for my client wife Sunita Sharma vs husband Vikesh — ₹15000/month",
        "मेरी मुवक्किल को पति ने 2 साल से छोड़ दिया है, भरण-पोषण याचिका चाहिए",
    ],
}


# ---------------------------------------------------------------- Revision
REVISION_PETITION = {
    "id":         "revision_petition",
    # DEDUPE: superseded by the real-filing v2 `criminal_revision_sessions`
    # (covers Sessions + HC). Auto-redirect to avoid a weaker duplicate.
    "redirect_url": "/draft/template/criminal_revision_sessions",
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
        "Revision against JM Class 1's order dt 10.01.2026 dismissing my discharge plea",
        "Sessions Court ne maintenance kharij kiya — revision file karna hai",
    ],
}


# ---------------------------------------------------------------- Reply to Bail
REPLY_TO_BAIL = {
    "id":         "reply_to_bail",
    # DEDUPE: consolidated into `reply_to_bail_sessions` (canonical cause-title
    # fixed). Auto-redirect to avoid a duplicate reply-to-bail entry.
    "redirect_url": "/draft/template/reply_to_bail_sessions",
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
    "name_en":    "Appeal against Conviction — High Court (S.415 BNSS / 374 CrPC)",
    "name_hi":    "दोषसिद्धि अपील — उच्च न्यायालय (धारा 415 BNSS / 374 दं.प्र.सं.)",
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
        "OUTPUT IS HINDI (Devanagari) BY DEFAULT (English only if lang='en'). "
        "Match Vishnu Ji's real आपराधिक अपील: 'आपराधिक अपील क्रमांक ____/<वर्ष>'; "
        "'अपीलार्थी' (with full descriptor), 'विरुद्ध', 'प्रतिअपीलार्थी म.प्र. शासन "
        "द्वारा आरक्षी केंद्र ____'; title 'आपराधिक अपील अन्तर्गत धारा 415 "
        "भा.ना.सु.सं. (374(2) दं.प्र.सं.) विरुद्ध निर्णय दिनांक ____ न्यायालय ____ "
        "द्वारा सत्र प्रकरण क्रमांक ____ में अपीलार्थी को धारा ____ में दोषसिद्ध कर "
        "दण्डित किया गया'; line 'अपीलार्थी की ओर से यह प्रथम आपराधिक अपील है'; then "
        "'प्रकरण का संक्षिप्त विवरण :-' (यह कि paras), the विचारणीय प्रश्न, then "
        "'अपील के आधार :-' as 'यह कि' grounds attacking the judgment (अविश्वसनीय "
        "साक्षी, विरोधाभास, चिकित्सीय साक्ष्य का असमर्थन, सन्देह का लाभ). Prayer: "
        "'अपील स्वीकार कर निर्णय अपास्त कर अपीलार्थी की दोषमुक्ति का निर्णय पारित "
        "करें'. Vocab: अपील, दोषसिद्धि, अपीलार्थी, अपास्त, दोषमुक्ति. Plain text."
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

# Merge in the 23 v2 templates (SC / HC additions / Sessions / Magistrate /
# Family / additional Procedural). Each v2 template already carries its
# court / court_label_en / court_label_hi / popularity fields directly,
# so _enrich_with_court_metadata() does NOT need to mutate them.
try:
    from headnote.drafter.compose_templates_v2 import NEW_TEMPLATES_V2
    TEMPLATES.update(NEW_TEMPLATES_V2)
except Exception as _e:  # pragma: no cover — defensive
    import logging as _logging
    _logging.getLogger(__name__).warning("v2 templates import failed: %s", _e)


# ----------------------------------------------------------------------------
# Court taxonomy (v2 — drafting home reorganisation).
# Maps each template id to the court tier where it's typically filed.
# Source: analysis of Vishnu ji's filing library + Headnote v2 plan.
# Consumed by /api/draft/courts to render court-grouped tile lists.
# ----------------------------------------------------------------------------

# Display labels per court. Order is the order shown on the drafting home.
COURT_LABELS: dict[str, dict[str, str]] = {
    "sc":         {"en": "Supreme Court",     "hi": "उच्चतम न्यायालय"},
    "hc":         {"en": "High Court",        "hi": "उच्च न्यायालय"},
    "sessions":   {"en": "Sessions Court",    "hi": "सत्र न्यायालय"},
    "magistrate": {"en": "Magistrate Court",  "hi": "मजिस्ट्रेट न्यायालय"},
    "family":     {"en": "Family Court",      "hi": "परिवार न्यायालय"},
    "procedural": {"en": "Common",            "hi": "सामान्य"},  # cross-court rail
}
COURT_ORDER: list[str] = ["sc", "hc", "sessions", "magistrate", "family", "procedural"]

# Per-template (court, popularity 1-5). Popularity sorts the within-court
# template list — higher = more prominent on the court drill-down page.
_COURT_METADATA: dict[str, tuple[str, int]] = {
    "vakalatnama":           ("procedural", 5),
    "mention_memo":          ("procedural", 4),
    "anticipatory_bail":     ("hc",         5),
    "quashing_petition":     ("hc",         5),
    "writ_petition":         ("hc",         3),
    "default_bail":          ("sessions",   3),
    "discharge_application": ("sessions",   4),
    "maintenance":           ("family",     5),
    "revision_petition":     ("hc",         3),
    "reply_to_bail":         ("hc",         3),
    "appeal_conviction":     ("hc",         4),
}


def _enrich_with_court_metadata() -> None:
    """Inject court / court_label_en / court_label_hi / popularity into each
    template dict so the FE can group templates by court without inferring
    from the id. Idempotent — safe to call multiple times."""
    for tpl_id, (court, popularity) in _COURT_METADATA.items():
        tpl = TEMPLATES.get(tpl_id)
        if not tpl:
            continue
        tpl["court"]          = court
        tpl["court_label_en"] = COURT_LABELS[court]["en"]
        tpl["court_label_hi"] = COURT_LABELS[court]["hi"]
        tpl["popularity"]     = popularity


# Apply enrichment immediately so callers see the populated fields.
_enrich_with_court_metadata()


# Kept in the registry (direct URL still resolves) but hidden from the public
# picker grid: Supreme Court AOR-only filings, irrelevant to the district /
# sessions / High Court practice Headnote serves.
_HIDDEN_FROM_PICKER = {"slp_criminal", "review_petition_sc"}


# Canonical V2 engine: these catalogue types are now served by the reviewed,
# deterministic per-court templates (headnote/drafter/templates/*) behind the
# universal editor (/draft/template/<id> → template_adapter). Pointing the tile
# here swaps the old LLM/wrapper path for the V2 bundle without touching the UI.
_V2_EDITOR = {
    "regular_bail_hc":            "bail_hc",
    "regular_bail_sessions":      "bail_sessions",
    "trial_bail_437":             "bail_magistrate",
    "anticipatory_bail_sessions": "anticipatory_bail",
    "anticipatory_bail":          "anticipatory_bail_hc",
    "quashing_petition":          "quashing",
    "revision_petition":          "revision_hc",
    "criminal_revision_sessions": "revision_sessions",
    "appeal_conviction":          "appeal_hc",
    "discharge_application":      "discharge_sessions",
    "maintenance":                "maintenance",
    "dv_act_12":                  "dv",
    "ni_act_138":                 "cheque_138",
    "private_complaint_200":      "parivad",
    "vakalatnama":                "vakalatnama",
}


def _redirect_for(t: dict) -> str | None:
    """V2 canonical tiles point at /draft/template/<canonical id>; everything
    else keeps its existing wrapper redirect (or none → default template URL)."""
    if t["id"] in _V2_EDITOR:
        return "/draft/template/" + _V2_EDITOR[t["id"]]
    return t.get("redirect_url")


def list_templates_slim() -> list[dict]:
    """Slim metadata for the FE picker. Now includes court grouping fields,
    redirect_url (for wrapper templates), and quality tag (v1-ai etc)."""
    return [
        {
            "id":              t["id"],
            "name_en":         t["name_en"],
            "name_hi":         t["name_hi"],
            "category":        t.get("category"),
            "tier":            t.get("tier"),
            "court":           t.get("court", "procedural"),
            "court_label_en":  t.get("court_label_en", "Common"),
            "court_label_hi":  t.get("court_label_hi", "सामान्य"),
            "popularity":      t.get("popularity", 1),
            "redirect_url":    _redirect_for(t),  # V2 canonical tiles → /draft/template/<id>; else wrapper
            "quality":         t.get("quality", "v1"),  # v1-ai / v1-wrapper / tuned
            "description":     t.get("description"),
            "example_prompts": t.get("example_prompts", []),
        }
        for t in TEMPLATES.values()
        if t["id"] not in _HIDDEN_FROM_PICKER
    ]


def list_templates_by_court() -> list[dict]:
    """Return templates grouped by court, in the canonical display order.
    Used by GET /api/draft/courts to render the drafting home grid.

    Returns a list of court groups:
        [{"id": "sc",  "label_en": "Supreme Court", "label_hi": "...",
          "count": 0, "templates": []},
         {"id": "hc",  "label_en": "High Court",    ..., "templates": [...]},
         ...]

    Within each group, templates are sorted by popularity desc, then by
    name_en asc.
    """
    slim = list_templates_slim()
    groups: list[dict] = []
    for court_id in COURT_ORDER:
        members = [t for t in slim if t["court"] == court_id]
        members.sort(key=lambda t: (-t["popularity"], t["name_en"].lower()))
        groups.append({
            "id":       court_id,
            "label_en": COURT_LABELS[court_id]["en"],
            "label_hi": COURT_LABELS[court_id]["hi"],
            "count":    len(members),
            "templates": members,
        })
    return groups


def get_template(doc_type: str) -> dict | None:
    return TEMPLATES.get(doc_type)
