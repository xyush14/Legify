"""Prompt-first drafting — the "describe your matter → get a draft" front door.

One freeform prompt (Hindi / English / Hinglish) → a court-ready draft, the best we
can produce:

  1. CLASSIFY  — a cheap LLM call maps the prompt to a doc_type (+ court + bail_type).
  2. ROUTE:
       • a DETERMINISTIC type we have a template for (the moat — bail, anticipatory,
         discharge, revision, appeal, maintenance, dv, quashing, §138, vakalatnama,
         parivad) → extract the fields from the prompt and render the VERBATIM,
         zero-hallucination canonical template. Unfilled fields render as the usual
         placeholders for the advocate to complete in the editor.
       • anything else (a long-tail criminal application, ANY civil matter) → hand to
         the house-style LLM authoring engine (author.py), which writes in Vishnu ji's
         idiom under the verified-citation guard.

This reuses the proven pieces: prompt_tweak's validated PATCH machinery for field
extraction, the canonical template modules for the deterministic render, and author.py
for authoring. The frontend gets back `data` for canonical types so the existing editor
can pick up where the prompt left off.
"""
from __future__ import annotations

import json

from headnote.drafter import author


def _finalize(result: dict) -> dict:
    """Add `page_hi` / `page_en` — the draft wrapped in a standalone A4 page (canonical
    header CSS + Devanagari font) so the frontend can drop it straight into an iframe."""
    from headnote.drafter.templates._doc_header import doc_page
    hi = (result.get("html_hi") or "").strip()
    en = (result.get("html_en") or "").strip()
    result["page_hi"] = doc_page([hi]) if hi else ""
    result["page_en"] = doc_page([en]) if en else ""
    return result


def _editor_handoff(module_key: str, court: str, bail_type: str, data: dict) -> tuple[str, dict]:
    """Map a canonical draft → the universal editor's template id (+ FLAT fields) so the
    frontend can open the SAME draft in /draft/template/<id>, pre-filled. This is the
    inverse of template_adapter.to_data: grounds toggles flattened to top-level booleans,
    section-lists joined to comma strings, court/bail_type dropped (encoded in the id)."""
    from headnote.drafter import template_adapter as TA
    bt = bail_type or "regular"
    eid = next((k for k, (t, c, b) in TA.CANONICAL_MAP.items()
                if t == module_key and c == court and b == bt), None)
    if eid is None:  # court/variant didn't line up — fall back to any id for this module
        eid = next((k for k, (t, c, b) in TA.CANONICAL_MAP.items() if t == module_key), None)
    if eid is None:
        return "", {}
    flat: dict = {}
    for k, v in (data or {}).items():
        if k in ("grounds", "court", "bail_type"):
            continue
        if isinstance(v, list):
            flat[k] = ", ".join(str(x) for x in v)
        elif v not in (None, ""):
            flat[k] = v
    for gk, gv in (data.get("grounds") or {}).items():
        if gv:
            flat[gk] = True
    return eid, flat


# ---------------------------------------------------------------------------
# 1) Classifier — prompt → {doc_type, court, bail_type, confidence}.
# ---------------------------------------------------------------------------
CLASSIFY_SYSTEM = """You are the intake router for an Indian litigation drafting tool (Madhya Pradesh trial
courts + High Court). Read the advocate's description of what they want to draft — it may be in Hindi, English
or Hinglish — and classify it. Output ONLY valid JSON, no prose:
{"doc_type": "<one key below>", "court": "magistrate"|"sessions"|"hc"|"family"|"civil"|"consumer"|"", "bail_type": "regular"|"anticipatory"|"", "language": "hi"|"en", "confidence": 0.0-1.0, "reason": "<short>"}

"language" = the language the DRAFT should be written in, inferred from how the advocate wrote:
  • Devanagari (Hindi) text → "hi".
  • Hinglish — Hindi words typed in Latin/Roman script ("regular bail FIR 123 dhara 420 ka ekmatra kamane wala") → "hi".
    These lawyers want a HINDI court draft; the Roman typing is just input convenience.
  • Genuine English prose (an English sentence a court would accept as English) → "en".
  • If unsure, default to "hi" (this is an MP district-court tool).

doc_type keys (pick the SINGLE best fit):
  bail               regular bail after arrest/custody (BNSS §483/§480; CrPC §439/§437)
  anticipatory_bail  pre-arrest / apprehension of arrest (BNSS §482; CrPC §438; "अग्रिम")
  default_bail       statutory/default bail — charge-sheet/challan NOT filed in 60/90 days (BNSS §187(3); §167(2))
  suspension_389     suspend sentence + bail PENDING APPEAL after conviction (BNSS §430; §389)
  discharge          discharge from charge (BNSS §250/§262; §227/§239)
  revision           criminal revision against an order (BNSS §438-442; §397-401)
  appeal             appeal against conviction (BNSS §415; §374)
  quashing           quash an FIR / proceeding — HC inherent power (BNSS §528; §482 CrPC)
  maintenance        wife/child maintenance (BNSS §144; §125 CrPC); भरण-पोषण
  dv                 domestic violence reliefs (§12 PWDVA); व्यथित महिला
  cheque_138         cheque dishonour COMPLAINT by the payee (§138 NI Act)
  ni_138_dismiss     §138 cheque case DEFENCE (accused side) — notice-not-served / maintainability objection
  vakalatnama        vakalatnama / memo of appearance
  parivad            private complaint (परिवाद) before the Magistrate (BNSS §223; §200)
  complaint_156      police refusing to register FIR → direction to police (BNSS §175(3); §156(3))
  supurdgi           interim custody / release of a seized vehicle/property (सुपुर्दगी; BNSS §497/§503; §451/§457)
  exemption_205      dispense with personal attendance of the accused (BNSS §228; §205)
  compounding        compounding of offence on compromise / राजीनामा (BNSS §359; §320)
  recall_311         recall / re-examine a witness (BNSS §348; §311)
  statement_178      record a statement before the court (BNSS §178)
  production         summon/produce documents (BNSS §94; §91)
  production_warrant jail production warrant for an undertrial (BNSS §302; §267)
  reply              reply / जवाब to an application filed by the other side
  mention_memo       mention memo / urgent-listing request (HC)
  writ_petition      writ petition Art. 226/227 (not habeas)
  habeas_corpus      habeas corpus — illegal detention (Art. 226; बन्दी प्रत्यक्षीकरण)
  stay_petition      stay application (HC I.A.)
  transfer_petition  transfer a criminal case (BNSS §447; §407)
  mact_166           motor-accident compensation claim (§166 MV Act)
  divorce_13         divorce (§13 Hindu Marriage Act; विवाह विच्छेद / तलाक)
  restitution_9      restitution of conjugal rights (§9 HMA; दाम्पत्य पुनर्स्थापना)
  general_affidavit  a standalone affidavit (शपथ पत्र) is itself the ask
  legal_notice       a legal / demand notice to be SENT (not filed in court)
  recovery_suit      civil suit to RECOVER money owed — loan / goods supplied / services / advance (धन वसूली वाद)
  injunction_suit    civil suit for (permanent) injunction to restrain interference / dispossession / construction (§38 SRA; निषेधाज्ञा / व्यादेश)
  specific_performance  suit to enforce an agreement to sell / contract (§10 SRA; विनिर्दिष्ट अनुपालन; इकरारनामा)
  declaration_suit   suit for declaration of right / title / status (§34 SRA; घोषणा वाद)
  partition_suit     partition of joint / ancestral property + separate possession (बंटवारा वाद)
  eviction_suit      landlord's suit to evict a tenant / arrears of rent (MP Accommodation Control Act §12; बेदखली)
  written_statement  the DEFENDANT's written statement / जवाबदावा in reply to a plaint (Order VIII CPC)
  consumer_complaint consumer complaint — defective goods / deficient service (CPA 2019; उपभोक्ता परिवाद)
  other_criminal     any OTHER criminal application/petition with no specific key
  other_civil        any OTHER civil matter with no specific key above — probate, succession, execution, misc. civil application

Rules:
- PICK A SPECIFIC KEY ONLY ON A CLEAR SIGNAL. Many lawyer queries are research/analysis ("what are the
  precedents on X", evidence questions, trial strategy, sentencing law). For those, choose the application
  the lawyer would actually FILE in that situation if it is obvious; if several could fit or none clearly
  fits, use other_criminal (or other_civil). A weak thematic echo of a specific key is NOT enough.
- CLASSIFY THE CLIENT'S INTENT, NOT INCIDENTAL WORDS. "Recovery of a weapon" is not a recovery suit;
  a warrant being discussed is not bail; an affidavit mentioned in the facts is not general_affidavit
  (general_affidavit only when the affidavit ITSELF is the document to draft); a §156(3) direction being
  challenged is not complaint_156 (complaint_156 is for SEEKING that direction).
- Challenging the REJECTION of a discharge application → revision (the discharge stage is over).
- "anticipatory" / "pre-arrest" / "अग्रिम" / "गिरफ्तारी की आशंका" → anticipatory_bail, NOT bail.
- suspension_389 ONLY when the client is CONVICTED and wants bail / suspension of sentence PENDING APPEAL.
  Commuting, reducing or challenging the sentence itself → appeal. Sentencing-law research → other_criminal.
- revision ONLY when challenging a specific ORDER of a lower court (framing charge, refusing discharge,
  maintenance order, cognizance). Evidence-appreciation or trial-strategy questions are NOT revision.
- reply ONLY when responding to an application/petition the OTHER side has filed. Defence arguments at
  trial are NOT reply.
- recall_311 ONLY for recalling / re-examining a witness. Other witness-evidence questions → other_criminal.
- legal_notice ONLY when the client wants to SEND a notice. A notice being the subject-matter of an
  offence/case does not make the matter legal_notice.
- transfer_petition ONLY when seeking transfer of a CASE from one court to another.
- Charge-sheet/challan not filed + 60/90 days in custody → default_bail, NOT bail.
- quashing / "FIR रद्द" / "कार्यवाही निरस्त करने" → quashing, court=hc.
- maintenance / भरण-पोषण / monthly maintenance from husband → maintenance, court=family.
- §138 cheque matters: the PAYEE filing a complaint → cheque_138; if the client IS the accused/summoned
  (director, signatory, drawer — any defence posture) → ni_138_dismiss, never cheque_138.
- Police refusing/not registering the FIR → complaint_156, NOT parivad.
- Release of a seized vehicle / phone / goods → supurdgi.
- Civil: pick the SPECIFIC civil key when the relief is clear (recovery_suit / injunction_suit /
  specific_performance / declaration_suit / partition_suit / eviction_suit / written_statement /
  consumer_complaint); other_civil ONLY when none fits. A suit combining declaration AND injunction →
  key on the PRIMARY relief (title disputed → declaration_suit; pure possession protection → injunction_suit).
- written_statement ONLY when the client is the DEFENDANT answering a civil plaint; answering an
  application the other side filed in an ongoing case stays `reply`.
- eviction_suit is the LANDLORD's suit; a tenant defending eviction → written_statement.
- Criminal but no specific key fits → other_criminal.
- Civil suit keys → court "civil"; consumer_complaint → court "consumer". NEVER a criminal court
  (magistrate/sessions) for a civil suit.
- Set court only when clear from the text; otherwise "".
"""


def _detect_lang(text: str) -> str:
    """Instant script heuristic used when the LLM can't decide: any Devanagari → 'hi',
    else 'en'. (The intent-aware call handles Hinglish; this is only the offline fallback.)"""
    return "hi" if any("ऀ" <= ch <= "ॿ" for ch in (text or "")) else "en"


def resolve_lang(requested: str, text: str, cls_language: str = "") -> str:
    """Resolve the draft language. An explicit 'hi'/'en' from the caller always wins; otherwise
    (requested 'auto' or blank) use the classifier's intent-aware call, then the script heuristic."""
    r = (requested or "").strip().lower()
    if r in ("hi", "en"):
        return r
    cl = (cls_language or "").strip().lower()
    if cl in ("hi", "en"):
        return cl
    return _detect_lang(text)


def classify(matter: str, lang: str = "hi") -> dict:
    """Map a freeform matter description to {doc_type, court, bail_type, language, confidence}.
    Falls back to a safe heuristic if the LLM is unavailable."""
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
    try:
        raw, _meta = _call_deepseek_or_groq(
            CLASSIFY_SYSTEM, matter.strip(), max_tokens=200, claude_model="claude-haiku-4-5")
        out = parse_json_response(raw)
        dt = (out.get("doc_type") or "").strip()
        if dt not in _VOCAB:
            dt = _heuristic_type(matter)
        language = (out.get("language") or "").strip().lower()
        if language not in ("hi", "en"):
            language = _detect_lang(matter)
        return {
            "doc_type": dt,
            "court": (out.get("court") or "").strip(),
            "bail_type": (out.get("bail_type") or "").strip(),
            "language": language,
            "confidence": float(out.get("confidence") or 0.5),
            "reason": out.get("reason") or "",
        }
    except Exception:
        return {"doc_type": _heuristic_type(matter), "court": "", "bail_type": "",
                "language": _detect_lang(matter),
                "confidence": 0.3, "reason": "heuristic (LLM unavailable)"}


_VOCAB = {
    "bail", "anticipatory_bail", "default_bail", "suspension_389", "discharge",
    "revision", "appeal", "quashing", "maintenance", "dv", "cheque_138",
    "ni_138_dismiss", "vakalatnama", "parivad", "complaint_156", "supurdgi",
    "exemption_205", "compounding", "recall_311", "statement_178", "production",
    "production_warrant", "reply", "mention_memo", "writ_petition", "habeas_corpus",
    "stay_petition", "transfer_petition", "mact_166", "divorce_13", "restitution_9",
    "general_affidavit", "legal_notice",
    "recovery_suit", "injunction_suit", "specific_performance", "declaration_suit",
    "partition_suit", "eviction_suit", "written_statement", "consumer_complaint",
    "other_criminal", "other_civil",
}


def _heuristic_type(matter: str) -> str:
    p = (matter or "").lower()

    def has(*w):
        return any(x in p for x in w)
    # order matters: the specific overlays come BEFORE the generic families they overlap
    # (suspension/default bail before bail; habeas before writ; NI defence before cheque).
    if has("anticipatory", "pre-arrest", "अग्रिम", "गिरफ्तारी की आशंका", "गिरफ्तारी की आश"):
        return "anticipatory_bail"
    if has("suspension of sentence", "suspend sentence", "sentence suspend", "bail pending appeal",
           "अपील में जमानत", "दण्डादेश निलंबन", "सजा निलंबन", "389", "430 bnss"):
        return "suspension_389"
    if has("default bail", "statutory bail", "60 days", "90 days", "challan नहीं", "चालान नहीं",
           "charge sheet not filed", "chargesheet not filed", "187(3)", "167(2)"):
        return "default_bail"
    if has("quash", "fir रद्द", "कार्यवाही निरस्त", "528", "482 crpc"):
        return "quashing"
    if has("habeas", "बन्दी प्रत्यक्षीकरण", "बंदी प्रत्यक्षीकरण", "illegal detention", "अवैध निरोध"):
        return "habeas_corpus"
    # BEFORE the writ check — "written statement" contains the substring "writ"
    if has("written statement", "जवाबदावा", "जवाब दावा", "order 8", "order viii"):
        return "written_statement"
    if has("writ", "रिट", "226", "227 ") and not has("written"):
        return "writ_petition"
    if has("transfer", "स्थानान्तरण", "स्थानांतरण", "407", "447"):
        return "transfer_petition"
    if has("mention memo", "urgent listing", "स्मरण पत्र", "अविलम्ब सूची"):
        return "mention_memo"
    if has("stay", "स्थगन"):
        return "stay_petition"
    if has("सुपुर्दगी", "supurdgi", "supurdagi", "vehicle release", "गाड़ी छुड़", "वाहन मुक्त",
           "release of vehicle", "451", "457 ", "497 bnss", "503 bnss"):
        return "supurdgi"
    if has("exemption", "personal attendance", "उपस्थिति से छूट", "हाजिरी माफ", "205 ", "228 bnss"):
        return "exemption_205"
    if has("compound", "राजीनामा", "अपराध शमन", "320 ", "359 bnss"):
        return "compounding"
    if has("156(3)", "175(3)", "fir दर्ज नहीं", "police not registering", "थाने में रिपोर्ट दर्ज नहीं"):
        return "complaint_156"
    if has("recall witness", "re-examine", "पुनः परीक्षण", "311", "348 bnss"):
        return "recall_311"
    if has("production warrant", "उत्पादन वारंट", "267", "302 bnss"):
        return "production_warrant"
    if has("production of document", "summon document", "दस्तावेज तलब", "91 ", "94 bnss"):
        return "production"
    if has("maintenance", "भरण", "125", "144 bnss", "गुजारा"):
        return "maintenance"
    if has("domestic violence", "घरेलू हिंसा", "pwdva", "व्यथित"):
        return "dv"
    if has("divorce", "तलाक", "विवाह विच्छेद", "13 hma"):
        return "divorce_13"
    if has("restitution", "conjugal", "दाम्पत्य", "9 hma"):
        return "restitution_9"
    if has("motor accident", "mact", "दुर्घटना दावा", "166 mv", "accident claim"):
        return "mact_166"
    if has("notice not served", "notice defective", "138 defence", "138 quash", "चेक केस बचाव",
           "cheque case defence", "accused in cheque"):
        return "ni_138_dismiss"
    if has("cheque", "138", "चेक", "dishonour", "dishonor"):
        return "cheque_138"
    if has("discharge", "उन्मोचन", "227", "239", "250 bnss", "262"):
        return "discharge"
    if has("revision", "पुनरीक्षण", "397", "438 bnss"):
        return "revision"
    if has("appeal", "अपील", "conviction", "415", "374"):
        return "appeal"
    if has("vakalatnama", "वकालतनामा"):
        return "vakalatnama"
    if has("परिवाद", "private complaint"):
        return "parivad"
    if has("legal notice", "demand notice", "विधिक सूचना", "कानूनी नोटिस"):
        return "legal_notice"
    if has("affidavit", "शपथ पत्र", "शपथ-पत्र"):
        return "general_affidavit"
    if has("reply", "जवाब ", "जबाव"):
        return "reply"
    if has("bail", "जमानत", "483", "480", "439", "437"):
        return "bail"
    if has("specific performance", "विनिर्दिष्ट अनुपालन", "agreement to sell", "इकरारनामा", "बयनामा"):
        return "specific_performance"
    if has("partition", "बंटवारा", "बटवारा", "विभाजन वाद"):
        return "partition_suit"
    if has("eviction", "बेदखली", "बे-दखली", "किरायेदार", "tenant", "किराया बकाया", "arrears of rent"):
        return "eviction_suit"
    if has("consumer", "उपभोक्ता", "deficiency in service", "सेवा में कमी"):
        return "consumer_complaint"
    if has("declaration", "घोषणा", "declaratory"):
        return "declaration_suit"
    if has("injunction", "निषेधाज्ञा", "व्यादेश", "39 rule 1", "order 39", "order xxxix"):
        return "injunction_suit"
    if has("recovery of money", "money recovery", "वसूली", "loan recovery", "money suit",
           "recovery suit", "उधार वापस"):
        return "recovery_suit"
    if has("suit", "recovery", "वाद", "probate", "succession", "उत्तराधिकार"):
        return "other_civil"
    return "other_criminal"


# ---------------------------------------------------------------------------
# 2) Deterministic routing — classifier type → canonical template module.
#    EVERY type with a reviewed canonical template routes here (the moat) —
#    the LLM authoring path is only for the true long tail.
# ---------------------------------------------------------------------------
# doc_type → (module_key, default_court, bail_type)
_DETERMINISTIC = {
    "bail":               ("bail", "sessions", "regular"),
    "anticipatory_bail":  ("bail", "sessions", "anticipatory"),
    "default_bail":       ("default_bail", "magistrate", ""),
    "suspension_389":     ("suspension_389", "hc", ""),
    "discharge":          ("discharge", "sessions", ""),
    "revision":           ("revision", "sessions", ""),
    "appeal":             ("appeal", "sessions", ""),
    "maintenance":        ("maintenance", "family", ""),
    "dv":                 ("dv", "magistrate", ""),
    "quashing":           ("quashing", "hc", ""),
    "cheque_138":         ("cheque", "magistrate", ""),   # module key per CANONICAL_MAP (bundle aliases cheque→cheque_138)
    "ni_138_dismiss":     ("ni_138_dismiss", "magistrate", ""),
    "vakalatnama":        ("vakalatnama", "sessions", ""),
    "parivad":            ("parivad", "magistrate", ""),
    "complaint_156":      ("complaint_156", "magistrate", ""),
    "supurdgi":           ("supurdgi", "magistrate", ""),
    "exemption_205":      ("exemption_205", "magistrate", ""),
    "compounding":        ("compounding", "magistrate", ""),
    "recall_311":         ("recall_311", "sessions", ""),
    "statement_178":      ("statement_178", "magistrate", ""),
    "production":         ("production", "magistrate", ""),
    "production_warrant": ("production_warrant", "magistrate", ""),
    "reply":              ("reply", "magistrate", ""),
    "mention_memo":       ("mention_memo", "hc", ""),
    "writ_petition":      ("writ_petition", "hc", ""),
    "habeas_corpus":      ("habeas_corpus", "hc", ""),
    "stay_petition":      ("stay_petition", "hc", ""),
    "transfer_petition":  ("transfer_petition", "hc", ""),
    "mact_166":           ("mact_166", "", ""),
    "divorce_13":         ("divorce_13", "family", ""),
    "restitution_9":      ("restitution_9", "family", ""),
    "general_affidavit":  ("general_affidavit", "", ""),
    "legal_notice":       ("legal_notice", "", ""),
}

# single-forum types — the classifier's court guess must not override these
_FORCE_COURT = {
    "cheque_138": "magistrate", "ni_138_dismiss": "magistrate", "quashing": "hc",
    "maintenance": "family", "divorce_13": "family", "restitution_9": "family",
    "writ_petition": "hc", "habeas_corpus": "hc", "stay_petition": "hc",
    "transfer_petition": "hc", "mention_memo": "hc", "suspension_389": "hc",
    "supurdgi": "magistrate", "exemption_205": "magistrate", "compounding": "magistrate",
    "complaint_156": "magistrate", "statement_178": "magistrate",
    "production_warrant": "magistrate", "dv": "magistrate", "parivad": "magistrate",
}


def _module(key: str):
    """Resolve a canonical template module via the shared bundle registry —
    one source of truth, so a newly built template auto-routes from a prompt."""
    from headnote.drafter.bundle import module_for
    try:
        return module_for(key)
    except ImportError:
        return None


def _spec(mod, key: str, court: str, bail_type: str) -> dict:
    """field_spec with whatever arity the module exposes (mirrors template_adapter)."""
    import inspect
    n = len(inspect.signature(mod.field_spec).parameters)
    if n >= 2:
        return mod.field_spec(court, bail_type)
    if n == 1:
        return mod.field_spec(court)
    return mod.field_spec()


# ---------------------------------------------------------------------------
# 2b) FIR-date / code gate — the skill's gating question ("FIR date?").
#     BNSS applies to FIRs on/after 1-Jul-2024; older matters stay CrPC. When a
#     criminal-procedure prompt gives neither a date nor an explicit code cue,
#     say so loudly instead of silently defaulting.
# ---------------------------------------------------------------------------
_CODE_SENSITIVE = {
    "bail", "anticipatory_bail", "default_bail", "suspension_389", "discharge",
    "revision", "appeal", "quashing", "parivad", "complaint_156", "supurdgi",
    "exemption_205", "compounding", "recall_311", "statement_178", "production",
    "production_warrant", "transfer_petition", "maintenance", "other_criminal",
}
_DATEISH = None  # compiled lazily

_CIVIL_FORUMS = ("civil", "district_judge", "consumer")


def _authored_court(author_type: str, cls: dict) -> str:
    """The court handed to the authoring engine. A civil matter never takes the
    classifier's criminal-forum guess (its enum is criminal-leaning) — the brief's
    civil forum wins; a genuine civil-forum guess passes through."""
    guess = (cls.get("court") or "").strip()
    if author_type in author.CIVIL_TYPES and guess not in _CIVIL_FORUMS:
        return author.brief_for(author_type).get("court") or "civil"
    return guess or (author.brief_for(author_type).get("court") or "")


def _code_gate_warning(matter: str, doc_type: str, lang: str) -> str:
    """Return a warning string when the BNSS/CrPC choice could not be anchored."""
    global _DATEISH
    import re as _re
    if doc_type not in _CODE_SENSITIVE:
        return ""
    if _DATEISH is None:
        _DATEISH = _re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|20[12]\d|19[89]\d")
    p = (matter or "").lower()
    code_cues = ("crpc", "cr.p.c", "दं.प्र.सं", "दंप्रसं", "bnss", "बी.एन.एस.एस",
                 "भा.ना.सु.सं", "ipc", "भा.द.वि", "भादवि", " bns", "बी.एन.एस")
    if _DATEISH.search(p) or any(c in p for c in code_cues):
        return ""
    if lang == "en":
        return ("No FIR/case date or code given — drafted with BNSS (2023) numbering. "
                "If the FIR predates 01.07.2024, CrPC numbering applies — switch it in the editor.")
    return ("FIR/प्रकरण की दिनांक नहीं दी गई — ड्राफ्ट BNSS (2023) क्रमांकन में है। "
            "FIR दिनांक 01.07.2024 से पूर्व की हो तो दं.प्र.सं. क्रमांकन लागू होगा — संपादक में बदल लें।")


# ---------------------------------------------------------------------------
# 3) One-shot field extraction (origination) — prompt → validated field values.
# ---------------------------------------------------------------------------
EXTRACT_SYSTEM = """You extract structured field VALUES from an Indian advocate's description of a matter, to
PRE-FILL a court-draft form. Output ONLY valid JSON:
{"set": {<field_key>: <value>}, "toggles": {<toggle_key>: true}, "variant": {<variant_key>: <value>}}

Rules:
- Use ONLY field_key / toggle_key / variant_key that appear in the SCHEMA below.
- Extract EVERY value the description gives: names, father/husband name, age, occupation, address, district,
  police station, FIR/crime number, case number, year, sections, dates (arrest/order/filing), amounts.
- For a "section_list" field, return an array of the section strings as given.
- Turn a toggle ON only if the description clearly supports that ground.
- DO NOT invent values. Omit any field the description doesn't mention — a blank renders as a placeholder.
- Keep values in the language the advocate used (Hindi stays Hindi).
SCHEMA: {schema}
"""


def extract_fields(spec: dict, matter: str) -> tuple[dict, list[str]]:
    """Prompt → validated PATCH → applied onto empty data. Reuses prompt_tweak's
    key-checked apply/validate so nothing outside the spec is ever set."""
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
    from headnote.drafter.prompt_tweak import validate_patch, apply_patch
    schema = {
        "fields": [{"key": f["key"], "type": f.get("type"), "label": (f.get("label") or {}).get("en")}
                   for f in spec.get("fields", [])],
        "toggles": [{"key": t["key"], "label": (t.get("label") or {}).get("en")} for t in spec.get("toggles", [])],
        "variants": spec.get("variants", {}),
    }
    system = EXTRACT_SYSTEM.replace("{schema}", json.dumps(schema, ensure_ascii=False))
    raw, _meta = _call_deepseek_or_groq(system, matter.strip(), max_tokens=900, claude_model="claude-haiku-4-5")
    patch = validate_patch(parse_json_response(raw), spec)
    return apply_patch({}, patch, spec)


# ---------------------------------------------------------------------------
# 4) Orchestrate — the public entry point.
# ---------------------------------------------------------------------------
def draft_from_prompt(matter: str, lang: str = "auto", reference_text: str = "") -> dict:
    """Freeform prompt → best-effort court-ready draft. Returns a unified result:
      {ok, mode: "canonical"|"authored", doc_type, court, confidence, html_hi,
       html_en, data?, cite_at_hearing, companions, warnings, title, meta}

    If `reference_text` is given, the advocate uploaded a FILED draft as a STYLE
    reference: we author the draft to MIRROR that document's structure, headings, tone
    and formatting (the user's facts fill the dynamic slots). The explicit "match THIS
    document" intent wins over the canonical templates, so a reference always routes to
    the house-style authoring engine (which keeps the verified-citation guard).
    """
    matter = (matter or "").strip()
    reference_text = (reference_text or "").strip()
    if not matter and not reference_text:
        return {"ok": False, "error": "empty prompt"}

    cls = classify(matter or reference_text, lang)
    dt = cls["doc_type"]
    # Auto-detect the draft language from the advocate's input (intent-aware), unless the
    # caller pinned 'hi'/'en'. Everything downstream renders/authors in this resolved lang.
    lang = resolve_lang(lang, matter or reference_text, cls.get("language"))

    # --- style-reference path — mirror the uploaded draft's shape/voice (authored) ---
    if reference_text:
        skeleton = author.extract_reference_skeleton(reference_text, lang)
        author_type = dt if dt in author.TYPE_BRIEFS else (
            "other_civil" if dt == "other_civil" else "other_criminal")
        a_court = _authored_court(author_type, cls)
        result = author.author_document(
            matter, author_type, lang, court=a_court,
            reference_skeleton=skeleton)
        result.update({
            "court": a_court,
            "confidence": cls["confidence"],
            "html_hi": result["html"] if lang != "en" else "",
            "html_en": result["html"] if lang == "en" else "",
            "reason": "mirrored your reference draft",
            "classified_as": dt,
            "mirrored": True,
            "mirror_ok": bool(skeleton),
        })
        if not skeleton:
            result.setdefault("warnings", []).insert(
                0, "Could not read the reference clearly — drafted in the standard house style instead.")
        return _finalize(result)

    # warnings every path shares: the FIR-date/code gate + low classifier confidence
    shared_warnings: list[str] = []
    gate = _code_gate_warning(matter, dt, lang)
    if gate:
        shared_warnings.append(gate)
    if cls["confidence"] < 0.55:
        shared_warnings.append(
            "Application type inferred with low confidence — verify the type is right."
            if lang == "en" else
            "आवेदन का प्रकार कम विश्वास के साथ अनुमानित है — प्रकार की पुष्टि कर लें।")

    # --- deterministic (canonical template) path — the moat ---
    if dt in _DETERMINISTIC:
        key, def_court, bail_type = _DETERMINISTIC[dt]
        court = _FORCE_COURT.get(dt) or cls.get("court") or def_court
        try:
            mod = _module(key)
            spec = _spec(mod, key, court, bail_type)
            data, log = extract_fields(spec, matter)
            if court:
                data["court"] = court
            if bail_type:
                data["bail_type"] = bail_type
            html_hi = mod.render_hi(data)
            html_en = mod.render_en(data) if hasattr(mod, "render_en") else ""
            cite = list(getattr(mod, "CITE_AT_HEARING", []) or [])
            editor_id, editor_fields = _editor_handoff(key, court, bail_type, data)
            from headnote.drafter.template_adapter import LABELS as _TA_LABELS
            lab = _TA_LABELS.get(editor_id) or {}
            title = lab.get("hi") or author.brief_for(
                dt if dt in author.TYPE_BRIEFS else "other_criminal")["label_hi"]
            return _finalize({
                "ok": True, "mode": "canonical", "doc_type": dt, "court": court,
                "bail_type": bail_type, "lang": lang, "confidence": cls["confidence"],
                "editor_id": editor_id, "editor_fields": editor_fields,
                "html_hi": html_hi, "html_en": html_en,
                "data": data, "changelog": log,
                "cite_at_hearing": cite,
                "companions": spec.get("companions") or [],
                "warnings": list(shared_warnings),
                "title": title,
                "reason": cls.get("reason", ""),
            })
        except Exception as e:  # canonical path failed → fall through to authoring
            cls["reason"] = f"canonical render failed ({type(e).__name__}); authored instead"

    # --- authored (house-style LLM) path — long tail + civil + anything else ---
    author_type = dt if dt in author.TYPE_BRIEFS else (
        "other_civil" if dt == "other_civil" else "other_criminal")
    a_court = _authored_court(author_type, cls)
    result = author.author_document(matter, author_type, lang, court=a_court)
    result.update({
        "court": a_court,
        "confidence": cls["confidence"],
        "html_hi": result["html"] if lang != "en" else "",
        "html_en": result["html"] if lang == "en" else "",
        "reason": cls.get("reason", ""),
        "classified_as": dt,
    })
    result["warnings"] = shared_warnings + list(result.get("warnings") or [])
    return _finalize(result)
