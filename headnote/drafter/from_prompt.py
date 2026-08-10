"""Prompt-first drafting — the "describe your matter → get a draft" front door.

One freeform prompt (Hindi / English / Hinglish) → a court-ready draft, the best we
can produce:

  1. CLASSIFY  — a cheap LLM call maps the prompt to a doc_type (+ court + bail_type)
     AND to the two axes that decide the document's SHAPE: who it is addressed to
     (forum_type) and what instrument it is. Those resolve to a FAMILY (doctypes.py).
  2. ROUTE:
       • a NON-COURT family (an application to a police station or an executive
         officer, a notice, a standalone affidavit, a deed) → the parts engine
         (author_parts.py). These documents have no cause-title, no opposing party
         and no prayer, so forcing them through the court renderer produced a
         document the advocate could not send. Reviewed canonical templates still
         win where one exists for the type.
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
import logging
import os

from headnote.drafter import author
from headnote.drafter import doctypes as DT

log = logging.getLogger("headnote.drafter")


def _finalize(result: dict) -> dict:
    """Add `page_hi` / `page_en` — the draft wrapped in a standalone A4 page (canonical
    header CSS + print CSS + Devanagari font) so the frontend can drop it straight into
    an iframe. The draft's own title becomes the page title (it is what the browser's
    print header shows).

    Also the single chokepoint for Draft DNA's FORMAT ENFORCEMENT: if the firing path
    stashed a `_style` (a loaded StyleProfile), the deterministic `apply_format` pass
    rewrites the boilerplate to the advocate's own tokens here — after render, before
    the page wrap — so every path (authored, canonical floor, skeleton) is covered in
    one place. `apply_format(html, None)` is the identity function, so no-DNA is a no-op.
    Mirror/reference results never set `_style` (reference beats DNA — §3b precedence)."""
    from headnote.drafter.templates._doc_header import doc_page
    style = result.pop("_style", None)
    if style:
        from headnote.drafter import style_profile as SP
        if result.get("html_hi"):
            result["html_hi"] = SP.apply_format(result["html_hi"], style, "hi")
        if result.get("html_en"):
            result["html_en"] = SP.apply_format(result["html_en"], style, "en")
    hi = (result.get("html_hi") or "").strip()
    en = (result.get("html_en") or "").strip()
    title = (result.get("title") or "").strip()
    result["page_hi"] = doc_page([hi], title=title) if hi else ""
    result["page_en"] = doc_page([en], title=title) if en else ""
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
CLASSIFY_SYSTEM = """You are the intake router for a pan-India litigation drafting tool (trial courts,
tribunals and High Courts across ALL Indian States and Union Territories). Read the advocate's description of
what they want to draft — it may be in Hindi, English or Hinglish — and classify it. Output ONLY valid JSON,
no prose:
{"doc_type": "<one key below>", "court": "magistrate"|"sessions"|"hc"|"family"|"civil"|"consumer"|"", "bail_type": "regular"|"anticipatory"|"", "forum_type": "<see FORUM below>", "instrument": "<see INSTRUMENT below>", "forum_name": "<the office/court the advocate named, verbatim; \"\" if none>", "language": "hi"|"en", "confidence": 0.0-1.0, "reason": "<short>"}

FORUM — WHO IS THIS DOCUMENT ADDRESSED TO? This decides the document's SHAPE and matters as much
as doc_type. A court filing has a cause-title, an opposing party and a prayer; a letter to an officer
has none of those. Getting this wrong produces a document the advocate cannot file or send.
  court          a judge — Magistrate, Sessions, District Judge, Family, High Court, Supreme Court
  tribunal       NCLT, DRT, MACT, Consumer Commission, CAT, appellate authorities
  police         a police officer — थाना प्रभारी / SHO / Inspector / SP / Commissioner
  executive      a revenue or executive officer — Collector, SDM, Tahsildar, RTO, municipal, excise
  registrar      Sub-Registrar, Registrar of Firms/Societies/Companies, university registrar
  institution    a bank, insurer, employer, school/university, utility company
  private_party  the other side directly (a notice, or a reply to their notice)
  none           addressed to nobody — a standalone affidavit, a deed, an agreement
DEFAULT TO "court". Choose another value ONLY on a clear signal — the advocate naming a थाना, an
officer, an office, or saying the document is to be SENT/SUBMITTED rather than filed.

INSTRUMENT — WHAT KIND OF DOCUMENT IS IT?
  petition | application | complaint | notice | reply | affidavit | deed | representation
  "deed" covers an agreement, sale deed, rent/lease agreement, partnership deed, MoU, power of
  attorney — anything executed BETWEEN parties rather than filed or sent.

Forum examples, so the distinction is concrete:
  • "थाना कोतवाली में गाड़ी छुड़ाने का आवेदन" / "application to the police station"
        → forum_type "police", instrument "application"   (NOT a court filing)
  • "धारा 457 में सुपुर्दगी आवेदन" / "supurdgi application before the Magistrate"
        → forum_type "court", instrument "application"
  • "SDM को अतिक्रमण की शिकायत" → forum_type "executive", instrument "complaint"
  • "किरायानामा बनाना है" / "draft a rent agreement" → forum_type "none", instrument "deed"
  • "वसूली का नोटिस भेजना है" → forum_type "private_party", instrument "notice"
  • "बैंक को लोन सेटलमेंट का पत्र" → forum_type "institution", instrument "representation"

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
  authority_application  an application, representation or complaint addressed to an OFFICE rather than
                     a court — a police station, Collector/SDM/Tahsildar/RTO, a Registrar, a bank,
                     an employer, a university. Use this whenever the advocate is writing TO an
                     officer, even if a court could also be moved on the same facts.
  deed               a document executed BETWEEN parties — agreement, sale deed, rent/lease agreement,
                     partnership deed, MoU, power of attorney, gift deed, relinquishment
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
- Release of a seized vehicle / phone / goods: if it is to be moved BEFORE THE COURT → supurdgi,
  forum_type "court". If the advocate says the application goes TO THE THANA / to the police →
  authority_application, forum_type "police". Draft what the advocate asked for; do not silently
  convert a letter to an officer into a court application.
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
    """Map a freeform matter description to
    {doc_type, court, bail_type, forum_type, instrument, forum_name, family, language, confidence}.

    `family` (from doctypes.resolve_family) is what decides the document's SHAPE — a court
    cause-title, a letter to an officer, a notice, an affidavit or a deed. It defaults to
    the court filing, so a classifier that says nothing about the forum changes nothing.
    Falls back to a safe heuristic if the LLM is unavailable.
    """
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
    try:
        raw, _meta = _call_deepseek_or_groq(
            CLASSIFY_SYSTEM, matter.strip(), max_tokens=280, claude_model="claude-haiku-4-5", json_mode=True)
        out = parse_json_response(raw)
        dt = (out.get("doc_type") or "").strip()
        if dt not in _VOCAB:
            dt = _heuristic_type(matter)
        language = (out.get("language") or "").strip().lower()
        if language not in ("hi", "en"):
            language = _detect_lang(matter)
        forum, instrument = _resolve_shape_axes(out, matter, dt)
        return {
            "doc_type": dt,
            "court": (out.get("court") or "").strip(),
            "bail_type": (out.get("bail_type") or "").strip(),
            "forum_type": forum,
            "instrument": instrument,
            "forum_name": (out.get("forum_name") or "").strip(),
            "family": DT.resolve_family(forum, instrument),
            "language": language,
            "confidence": float(out.get("confidence") or 0.5),
            "reason": out.get("reason") or "",
        }
    except Exception:
        dt = _heuristic_type(matter)
        forum, instrument = _resolve_shape_axes({}, matter, dt)
        return {"doc_type": dt, "court": "", "bail_type": "",
                "forum_type": forum, "instrument": instrument, "forum_name": "",
                "family": DT.resolve_family(forum, instrument),
                "language": _detect_lang(matter),
                "confidence": 0.3, "reason": "heuristic (LLM unavailable)"}


# doc_type keys whose shape is settled regardless of what the model says about the
# forum — a vakalatnama is always a court document, a deed never is.
_TYPE_FORUM: dict[str, tuple[str, str]] = {
    "authority_application": ("executive", "application"),
    "deed":                  ("none", "deed"),
    "legal_notice":          ("private_party", "notice"),
    "general_affidavit":     ("none", "affidavit"),
}


# doc_type keys that can only ever be filed in a court. Used ONLY to settle a forum
# the classifier left blank — if the model explicitly says "police", we believe it and
# draft the letter the advocate asked for (with `_forum_mismatch_warning` saying what
# the court can also do). This guard exists so a missing field can never silently turn
# a bail application into a letter to the SHO.
_NON_COURT_CAPABLE = {"authority_application", "deed", "legal_notice",
                      "general_affidavit", "other_criminal", "other_civil"}


def _resolve_shape_axes(out: dict, matter: str, doc_type: str) -> tuple[str, str]:
    """(forum_type, instrument), validated. Unknown or absent values resolve to the
    court filing — the pre-existing behaviour — so this can only ever ADD shapes."""
    pinned = _TYPE_FORUM.get(doc_type)
    forum = (out.get("forum_type") or "").strip().lower()
    instrument = (out.get("instrument") or "").strip().lower()
    if forum not in DT.FORUM_TYPES:
        forum = ""
    if instrument not in DT.INSTRUMENTS:
        instrument = ""
    if not forum and doc_type not in _NON_COURT_CAPABLE and not pinned:
        # a court-only application whose forum the classifier didn't state
        return "court", instrument or "application"
    if not forum or not instrument:
        h_forum, h_instrument = _heuristic_shape(matter)
        forum = forum or (pinned[0] if pinned else h_forum)
        instrument = instrument or (pinned[1] if pinned else h_instrument)
    return forum or "court", instrument or "application"


# Zero-cost keyword floor for the two shape axes, used when the LLM is unavailable or
# returned nothing usable. Deliberately CONSERVATIVE, and it earns that adjective the
# hard way: a police station or an officer is named as a FACT in most criminal filings
# ("FIR 123/2025, thana Kotwali"), so merely spotting the word routed bail and
# discharge applications to the wrong shape. Two guards fix that:
#   1. a COURT VETO — a request naming court-only relief is a court filing, full stop;
#   2. ADDRESSING PHRASES, not office names — the office must be the thing written TO.
# A wrongly-shaped court filing is a worse failure than a court filing the advocate has
# to re-point, so anything ambiguous stays on the court path.

# relief only a judge can grant — seeing any of these ends the enquiry
_COURT_VETO = (
    "जमानत", "अग्रिम जमानत", "बेल", "bail", "उन्मोचन", "discharge", "आरोपमुक्त",
    "पुनरीक्षण", "revision", "अपील", "appeal", "निरस्त", "quash", "quashing",
    "वाद", "suit", "plaint", "याचिका", "petition", "writ", "रिट", "परिवाद",
    "भरण-पोषण", "भरण पोषण", "maintenance", "वकालतनामा", "vakalatnama",
    "जवाबदावा", "written statement", "charge sheet", "चार्जशीट", "आरोप पत्र",
    "trial", "विचारण", "sessions", "सत्र न्यायालय", "मजिस्ट्रेट", "magistrate",
    "high court", "उच्च न्यायालय", "supreme court", "सर्वोच्च न्यायालय",
)

# the office must be ADDRESSED, not merely mentioned. These are directional.
_POLICE_ADDRESSED = (
    "थाना प्रभारी को", "थाना प्रभारी महोदय", "थानाध्यक्ष को", "थाने को", "थाने में आवेदन",
    "पुलिस अधीक्षक को", "पुलिस को आवेदन", "पुलिस थाने में आवेदन", "आरक्षी केन्द्र को",
    "to the police", "to police station", "to the police station", "to the sho",
    "to sho", "to the station house officer", "to the superintendent of police",
    "police station ko", "thana prabhari ko", "thane me aavedan", "addressed to the police",
)
_EXEC_ADDRESSED = (
    "कलेक्टर को", "कलेक्टर महोदय", "एसडीएम को", "तहसीलदार को", "आरटीओ को",
    "नगर निगम को", "जिलाधिकारी को", "आबकारी", "अनुविभागीय अधिकारी को",
    "to the collector", "to collector", "to the sdm", "to the tahsildar",
    "to the rto", "to the municipal", "to the district magistrate",
    "collector ko", "sdm ko", "tahsildar ko",
)
_REGISTRAR_ADDRESSED = (
    "रजिस्ट्रार को", "उप पंजीयक को", "पंजीयक को",
    "to the registrar", "to registrar", "to the sub-registrar", "to the sub registrar",
)
_INSTITUTION_ADDRESSED = (
    "बैंक को", "बीमा कंपनी को", "नियोक्ता को", "विश्वविद्यालय को", "विद्यालय को",
    "to the bank", "to the insurance", "to the employer", "to the university",
    "to the principal", "bank ko",
)
_DEED_WORDS = ("किरायानामा", "इकरारनामा", "अनुबंध", "विलेख", "agreement", "rent agreement",
               "lease deed", "sale deed", "partnership deed", " mou", "power of attorney",
               "मुख्तारनामा", "दानपत्र", "gift deed", "बैनामा", "relinquishment deed")
_NOTICE_WORDS = ("नोटिस भेज", "legal notice", "demand notice", "विधिक सूचना", "सूचना पत्र भेज",
                 "notice bhejna", "नोटिस देना है")
_AFFIDAVIT_WORDS = ("शपथ पत्र", "शपथपत्र", "affidavit", "हलफनामा")


def _heuristic_shape(matter: str) -> tuple[str, str]:
    p = (matter or "").lower()

    def has(words) -> bool:
        return any(w in p for w in words)

    # a deed is a deed even in a matter that also mentions a court
    if has(_DEED_WORDS):
        return "none", "deed"
    if has(_NOTICE_WORDS):
        return "private_party", "notice"

    # court-only relief ends the enquiry — the office in the text is a fact, not an
    # addressee (this is what kept "bail application … thana kotwali" a court filing)
    if has(_COURT_VETO):
        return "court", "application"

    if has(_POLICE_ADDRESSED):
        return "police", "application"
    if has(_EXEC_ADDRESSED):
        return "executive", "application"
    if has(_REGISTRAR_ADDRESSED):
        return "registrar", "application"
    if has(_INSTITUTION_ADDRESSED):
        return "institution", "representation"

    if has(_AFFIDAVIT_WORDS):
        return "none", "affidavit"
    return "court", "application"


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
    # non-court shapes (see doctypes.py) — these have no court cause-title
    "authority_application", "deed",
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
    # "जामीन" (mr) / "જામીન" (gu) / "ஜாமீன்" (ta) / "জামিন" (bn) sit here too: this
    # ladder is the zero-cost path the instant skeleton uses, and a Pune or Chennai
    # advocate should not have to write in Hindi or English to get the right shape.
    if has("bail", "जमानत", "जामीन", "જામીન", "ஜாமீன்", "জামিন", "483", "480", "439", "437"):
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
    # ---- civil suits — now DETERMINISTIC (CPC plaints via the _civil engine) ----
    "recovery_suit":      ("recovery_suit", "civil", ""),
    "injunction_suit":    ("injunction_suit", "civil", ""),
    "specific_performance": ("specific_performance", "civil", ""),
    "declaration_suit":   ("declaration_suit", "civil", ""),
    "partition_suit":     ("partition_suit", "civil", ""),
    "eviction_suit":      ("eviction_suit", "civil", ""),
    "written_statement":  ("written_statement", "civil", ""),
    "consumer_complaint": ("consumer_complaint", "consumer", ""),
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
    # civil suits must stay in a civil forum (never a criminal-court guess)
    "recovery_suit": "civil", "injunction_suit": "civil", "specific_performance": "civil",
    "declaration_suit": "civil", "partition_suit": "civil", "eviction_suit": "civil",
    "written_statement": "civil", "consumer_complaint": "consumer",
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
    raw, _meta = _call_deepseek_or_groq(system, matter.strip(), max_tokens=900, claude_model="claude-haiku-4-5", json_mode=True)
    patch = validate_patch(parse_json_response(raw), spec)
    return apply_patch({}, patch, spec)


# ---------------------------------------------------------------------------
# 4) Orchestrate — the public entry point.
#
#    ONE INTENT: whatever the advocate gave → the correct document, in its
#    prescribed format, ALWAYS. The LLM authors every draft from the WHOLE input
#    (the old field-extraction→rigid-template primary silently discarded every
#    fact outside its schema — the #1 "it didn't read my prompt" complaint).
#    The canonical templates stay on as (a) the PRESCRIBED-FORMAT specimen shown
#    to the model, (b) the deterministic floor when the LLM chain is down, and
#    (c) the structured-editor handoff. Nothing in this module raises to the API.
# ---------------------------------------------------------------------------
def _strip_html(html: str) -> str:
    """Rendered template HTML → readable plain-text specimen for the prompt."""
    import re as _re
    t = html or ""
    t = _re.sub(r"<(?:br|/p|/li|/div|/h\d|/tr|/th|/td)[^>]*>", "\n", t, flags=_re.I)
    t = _re.sub(r"<li[^>]*>", "\n", t, flags=_re.I)
    t = _re.sub(r"<[^>]+>", "", t)
    t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"'))
    t = _re.sub(r"[ \t]+", " ", t)
    t = _re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def _format_exemplar(key: str, court: str, bail_type: str, lang: str) -> str:
    """The canonical template rendered BLANK → the prescribed-format specimen the
    authoring engine writes the matter INTO (templates as curriculum, not cage).
    Best-effort: '' on any failure — authoring still has the type brief + skeleton."""
    try:
        mod = _module(key)
        if mod is None:
            return ""
        data: dict = {}
        if court:
            data["court"] = court
        if bail_type:
            data["bail_type"] = bail_type
        if lang == "en" and hasattr(mod, "render_en"):
            html = mod.render_en(dict(data))
        else:
            html = mod.render_hi(dict(data))
        return _strip_html(html)[:7000]
    except Exception:
        return ""


def _canonical_result(dt: str, key: str, court: str, bail_type: str, matter: str,
                      lang: str, cls: dict, shared_warnings: list[str],
                      data: dict | None = None) -> dict:
    """The deterministic canonical render — the old primary, now the floor (and the
    DRAFTER_CANONICAL_FIRST escape hatch). Raises if the module/render fails; the
    caller decides the next rung. Pass `data` to skip the extraction LLM call."""
    mod = _module(key)
    spec = _spec(mod, key, court, bail_type)
    changelog: list[str] = []
    if data is None:
        data, changelog = extract_fields(spec, matter)
    data = dict(data)
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
    # honesty about what a rigid template can't hold: list the input facts it dropped
    warnings = list(shared_warnings)
    warnings.extend(author.coverage_warnings(matter, html_hi or html_en, lang))
    return {
        "ok": True, "mode": "canonical", "doc_type": dt, "court": court,
        "bail_type": bail_type, "lang": lang, "confidence": cls["confidence"],
        "editor_id": editor_id, "editor_fields": editor_fields,
        "html_hi": html_hi, "html_en": html_en,
        "data": data, "changelog": changelog,
        "cite_at_hearing": cite,
        "companions": spec.get("companions") or [],
        "warnings": warnings,
        "title": title,
        "reason": cls.get("reason", ""),
    }


def _last_resort(dt: str, lang: str, matter: str, warnings: list[str]) -> dict:
    """The absolute floor — pure Python, zero LLM, zero template imports beyond the
    in-module brief table. Produces the standard SHAPE of the application with the
    advocate's own input preserved verbatim as drafting notes, so a drafting request
    NEVER comes back as an error while the lawyer is mid-work. Cannot fail."""
    hi = lang != "en"
    try:
        b = author.brief_for(dt if dt in author.TYPE_BRIEFS else "other_criminal")
        title = b["label_hi"] if hi else b["label_en"]
    except Exception:
        title = "आवेदन पत्र" if hi else "Application"

    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    ph = '<span class="ph">____</span>'
    lead = "यह कि " if hi else "That "
    paras = "".join(f"<li>{lead}{ph} ।</li>" for _ in range(3))
    closer = "यह कि, अन्य तर्क वक्त बहस मौखिक रुप से निवेदित किये जावेंगे।" if hi else ""
    prayer = ("अतः श्रीमान न्यायालय से प्रार्थना है कि ____ करने की कृपा करें।" if hi
              else "It is therefore prayed that this Hon'ble Court may kindly ____.")
    notes = ""
    if (matter or "").strip():
        lbl = "आपके दिए तथ्य (ड्राफ्ट में यथास्थान जोड़ें)" if hi else "Your facts (add into the draft)"
        notes = (f'<div class="cb-block-label">{esc(lbl)}</div>'
                 f'<p class="cb-prelude">{esc(matter.strip())}</p>')
    html = (
        '<div class="cb-doc">'
        f'<p style="text-align:center;font-weight:bold">{"न्यायालय " if hi else "In the Court of "}{ph}</p>'
        f'<p style="text-align:center;font-weight:bold;text-decoration:underline">{esc(title)}</p>'
        '<div class="doc-body"><ol class="cb-paras">'
        + paras + (f"<li>{esc(closer)}</li>" if closer else "")
        + "</ol>"
        f'<div class="cb-prayer"><p>{esc(prayer)}</p></div>'
        + notes + "</div></div>")
    warn = list(warnings)
    warn.append(
        "AI ड्राफ्टिंग क्षणिक रूप से अनुपलब्ध रही — यह मानक ढाँचा है और आपके लिखे तथ्य नीचे सुरक्षित हैं; "
        "कुछ देर बाद पुनः प्रयास करें।"
        if hi else
        "AI drafting was temporarily unavailable — this is the standard shape and your facts are "
        "preserved below; please try again shortly.")
    return {
        "ok": True, "mode": "skeleton", "doc_type": dt, "court": "", "lang": lang,
        "confidence": 0.0,
        "html_hi": html if hi else "", "html_en": html if not hi else "",
        "cite_at_hearing": [], "companions": [], "warnings": warn,
        "title": title, "reason": "all drafting engines unavailable — standard shape returned",
    }


def draft_from_prompt(matter: str, lang: str = "auto", reference_text: str = "",
                      user_id: str | None = None) -> dict:
    """Freeform prompt (+ optional OCR'd case papers merged in, + optional style
    reference) → court-ready draft. Returns a unified result:
      {ok, mode: "authored"|"canonical"|"skeleton", doc_type, court, confidence,
       html_hi, html_en, data?, editor_id?, cite_at_hearing, companions, warnings,
       title, meta}

    Routing — ONE primary path, then a never-fail ladder:
      1. AUTHORED (primary, all types): the LLM drafts from the advocate's WHOLE
         input, with the matching canonical template (rendered blank) injected as
         the PRESCRIBED FORMAT. Reference uploaded → the mirror engine instead
         (reference = format, input = facts). All guards (citation whitelist,
         fact-grounding, section pairs, input coverage) apply.
      2. CANONICAL floor: LLM chain down → the deterministic template render.
      3. SKELETON floor: no template either → pure-python standard shape with the
         advocate's input preserved. This function NEVER raises.

    Set DRAFTER_CANONICAL_FIRST=1 to restore the old canonical-first routing.
    """
    matter = (matter or "").strip()
    reference_text = (reference_text or "").strip()
    if not matter and not reference_text:
        return {"ok": False, "error": "empty prompt"}
    try:
        return _draft(matter, lang, reference_text, user_id)
    except Exception:
        # the absolute backstop — a drafting request must never surface a stack trace
        log.exception("draft_from_prompt: unexpected failure — returning skeleton floor")
        rl = resolve_lang(lang, matter or reference_text)
        return _finalize(_last_resort("other_criminal", rl, matter, []))


# doc_types whose relief only a COURT can grant. When the advocate addresses one of
# these to an officer we still draft what they asked for — but we say so, the way a
# junior would. Silently converting the letter into a court application (what the
# engine used to do) is worse: the advocate files something they did not ask for.
_COURT_ONLY_RELIEF: dict[str, tuple[str, str]] = {
    "supurdgi": ("अंतरिम सुपुर्दगी का आदेश न्यायालय देता है (बी.एन.एस.एस. §497/§503) — थाना केवल "
                 "अभिरक्षा में रखता है। यह आवेदन थाने को संबोधित है; वाहन/माल की सुपुर्दगी के लिए "
                 "संबंधित मजिस्ट्रेट के समक्ष भी आवेदन देना होगा।",
                 "Interim custody of a seized article is ordered by the Magistrate (BNSS §497/§503); "
                 "the police only hold it. This application is addressed to the police station — a "
                 "separate application before the Magistrate will also be needed for release."),
    "complaint_156": ("पुलिस द्वारा एफ.आई.आर. दर्ज न करने पर निर्देश मजिस्ट्रेट देता है "
                      "(बी.एन.एस.एस. §175(3)) — यह पत्र थाने/पुलिस अधीक्षक को है, जो §173(4) की "
                      "पूर्व-शर्त पूरी करता है, स्वयं उपचार नहीं है।",
                      "A direction to register an FIR comes from the Magistrate (BNSS §175(3)). "
                      "This letter to the police/SP satisfies the precondition under §173(4); it is "
                      "not itself the remedy."),
    "bail": ("जमानत न्यायालय देता है, थाना नहीं। यह पत्र थाने को संबोधित है।",
             "Bail is granted by a court, not by a police station. This letter is addressed to the police."),
    "anticipatory_bail": ("अग्रिम जमानत सत्र न्यायालय/उच्च न्यायालय देता है, थाना नहीं।",
                          "Anticipatory bail is granted by the Sessions Court or High Court, not by the police."),
}


# The same relief, detected from what the advocate actually described rather than from
# the doc_type key. Found by running the real thing against production: for "थाना प्रभारी
# को … जब्त मोटरसाइकिल … सुपुर्दगी", the classifier correctly returns
# doc_type=`authority_application` (it IS a letter to an office), so keying the note on
# doc_type alone meant the note NEVER fired on the very case it was written for.
_RELIEF_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("supurdgi", ("सुपुर्दगी", "supurdgi", "supurdagi", "अंतरिम अभिरक्षा",
                  "जब्त वाहन", "जब्त मोटरसाइकिल", "जब्त गाड़ी", "गाड़ी छुड़ा", "वाहन छुड़ा",
                  "release of vehicle", "vehicle release", "seized vehicle",
                  "451", "457", "497", "503")),
    ("complaint_156", ("एफ.आई.आर. दर्ज नहीं", "एफआईआर दर्ज नहीं", "रिपोर्ट दर्ज नहीं",
                       "प्राथमिकी दर्ज नहीं", "फरियाद दर्ज नहीं", "दर्ज करने से मना",
                       "refusing to register", "refused to register", "not registering the fir",
                       "156(3)", "175(3)")),
    ("bail", ("जमानत", "bail")),
    ("anticipatory_bail", ("अग्रिम जमानत", "anticipatory bail", "गिरफ्तारी की आशंका")),
)


# "seizure of a thing" stated the long way round — the advocate rarely writes the word
# सुपुर्दगी; they describe what happened ("मोटरसाइकिल … जब्त की गई है").
_SEIZED = ("जब्त", "ज़ब्त", "seized", "seizure")
_SEIZABLE = ("वाहन", "मोटरसाइकिल", "गाड़ी", "कार", "ट्रक", "मोबाइल", "माल", "सामान",
             "vehicle", "motorcycle", "bike", "car", "truck", "mobile", "goods", "articles")


def _relief_from_text(matter: str) -> str:
    """Which court-only relief the advocate is actually asking for, read from their own
    words. Most specific first — 'अग्रिम जमानत' must beat 'जमानत'."""
    p = (matter or "").lower()
    signals = dict(_RELIEF_SIGNALS)
    for key in ("anticipatory_bail", "supurdgi", "complaint_156", "bail"):
        if any(w in p for w in signals[key]):
            return key
    if any(w in p for w in _SEIZED) and any(w in p for w in _SEIZABLE):
        return "supurdgi"
    return ""


def _forum_mismatch_warning(dt: str, family: str, lang: str, matter: str = "") -> str:
    """The junior's note when the requested relief needs a court but the document is
    addressed to an office. Keyed on the doc_type first, then on what the advocate
    described. Returns "" when there is nothing to say."""
    if family != DT.AUTHORITY_APPLICATION:
        return ""
    pair = _COURT_ONLY_RELIEF.get(dt) or _COURT_ONLY_RELIEF.get(_relief_from_text(matter))
    if not pair:
        return ""
    return pair[1] if lang == "en" else pair[0]


def _draft_non_court(family: str, dt: str, det, key: str, court: str, bail_type: str,
                     matter: str, lang: str, cls: dict, shared_warnings: list[str],
                     style: dict | None) -> dict:
    """Route a non-court document. Ladder, in order of how much advocate review is
    behind each rung:

      1. A REVIEWED canonical template for this exact type (legal_notice,
         general_affidavit, vakalatnama). An advocate has signed these off, so they
         beat anything generated — this is the one family where canonical goes first.
      2. The parts engine (author_parts) — authored into this family's own grammar.
      3. The parts FLOOR — deterministic, zero-LLM, and still the right shape. Never
         `_last_resort`, which emits a court skeleton and would reintroduce the bug.

    Never raises: the floor is pure Python.
    """
    from headnote.drafter import author_parts as AP

    warnings = list(shared_warnings)

    def _wrap(result: dict, reason: str) -> dict:
        # The junior's note is decided AFTER drafting, on the brief PLUS the document's
        # own subject line. Deciding it beforehand missed the real case in production:
        # the advocate wrote "मोटरसाइकिल … जब्त की गई है" and never used the word
        # सुपुर्दगी — the engine did, in the subject it composed. The subject is the
        # document's own statement of the relief, so it is the better signal.
        result.setdefault("warnings", [])
        note = _forum_mismatch_warning(
            dt, family, lang, f'{matter} {result.get("title") or ""}')
        result["warnings"] = warnings + ([note] if note else []) + list(result["warnings"])
        result.update({
            "court": "",
            "family": family,
            "confidence": cls.get("confidence", 0.5),
            "html_hi": result.get("html", "") if lang != "en" else "",
            "html_en": result.get("html", "") if lang == "en" else "",
            "reason": reason,
            "classified_as": dt,
            "forum_type": cls.get("forum_type", ""),
            "instrument": cls.get("instrument", ""),
            "_style": style,
        })
        return result

    # 1) advocate-reviewed template for this exact type
    if det:
        try:
            reviewed = _canonical_result(dt, key, court, bail_type, matter, lang, cls, warnings)
            reviewed["family"] = family
            reviewed["_style"] = style
            return reviewed
        except Exception:
            log.exception("canonical render failed for non-court type=%s — authoring instead", dt)

    # 2) authored into this family's parts grammar
    try:
        result = AP.author_parts_document(matter, family, lang, doc_type=dt,
                                          forum_name=cls.get("forum_name", ""),
                                          style=style)
        return _wrap(result, f"drafted as a {family.replace('_', ' ')}")
    except Exception:
        log.exception("parts authoring failed for family=%s — falling to the parts floor", family)

    # 3) the floor — correct shape, the advocate's own words kept verbatim
    result = AP.floor_document(family, lang, matter)
    return _wrap(result, "drafting engines unavailable — the correct blank shape was returned")


def _draft(matter: str, lang: str, reference_text: str, user_id: str | None = None) -> dict:
    requested_lang = lang
    cls = classify(matter or reference_text, lang)
    dt = cls["doc_type"]
    # Auto-detect the draft language from the advocate's input (intent-aware), unless the
    # caller pinned 'hi'/'en'. Everything downstream renders/authors in this resolved lang.
    lang = resolve_lang(lang, matter or reference_text, cls.get("language"))
    extra_warnings: list[str] = []

    # --- style-reference path — mirror the uploaded draft's shape/voice (authored) ---
    if reference_text:
        author_type = dt if dt in author.TYPE_BRIEFS else (
            "other_civil" if dt == "other_civil" else "other_criminal")
        a_court = _authored_court(author_type, cls)
        # The reference IS the format — so its language governs the draft (an English
        # filed plaint must come back English even off a Hinglish brief). An explicit
        # hi/en from the caller still wins inside resolve_lang.
        m_lang = resolve_lang(requested_lang, reference_text)
        result = None
        try:
            # primary: full-fidelity mirror — model sees the reference verbatim,
            # returns the whole document as layout blocks (author.mirror_document)
            result = author.mirror_document(matter, reference_text, author_type, m_lang)
            lang = m_lang
            result["mirror_ok"] = True
        except Exception:
            result = None
        if result is None:
            # fallback: the older skeleton pass + house-style authoring
            try:
                skeleton = author.extract_reference_skeleton(reference_text, lang)
                result = author.author_document(
                    matter, author_type, lang, court=a_court,
                    reference_skeleton=skeleton)
                result["mirror_ok"] = bool(skeleton)
                if not skeleton:
                    result.setdefault("warnings", []).insert(
                        0, "Could not read the reference clearly — drafted in the standard house style instead.")
            except Exception:
                result = None
        if result is not None:
            result.update({
                "court": a_court,
                "confidence": cls["confidence"],
                "html_hi": result["html"] if lang != "en" else "",
                "html_en": result["html"] if lang == "en" else "",
                "reason": "mirrored your reference draft",
                "classified_as": dt,
                "mirrored": True,
            })
            return _finalize(result)
        # reference path fully down → draft WITHOUT the reference rather than fail
        extra_warnings.append(
            "रेफरेंस दस्तावेज़ लागू नहीं हो सका — ड्राफ्ट मानक प्रारूप में बना है।"
            if lang != "en" else
            "Could not apply the reference document — drafted in the standard format instead.")
        reference_text = ""
        if not matter:
            return _finalize(_last_resort(dt, lang, matter, extra_warnings))

    # Draft DNA — load the advocate's saved StyleProfile now that the reference path
    # has resolved. Precedence (§3b): an attached reference beats DNA, and the mirror
    # branch above returns early, so we only reach here with NO active reference —
    # DNA legitimately applies (incl. when a reference was attached but failed to
    # apply). `load_style` returns None for anon / no-profile → the untouched path.
    from headnote.drafter import style_profile as _SP
    style = _SP.load_style(user_id) if user_id else None

    # warnings every path shares: the FIR-date/code gate + low classifier confidence
    shared_warnings: list[str] = list(extra_warnings)
    gate = _code_gate_warning(matter, dt, lang)
    if gate:
        shared_warnings.append(gate)
    if cls["confidence"] < 0.55:
        shared_warnings.append(
            "Application type inferred with low confidence — verify the type is right."
            if lang == "en" else
            "आवेदन का प्रकार कम विश्वास के साथ अनुमानित है — प्रकार की पुष्टि कर लें।")

    det = _DETERMINISTIC.get(dt)
    key = bail_type = ""
    court = ""
    if det:
        key, def_court, bail_type = det
        court = _FORCE_COURT.get(dt) or cls.get("court") or def_court

    # --- NON-COURT SHAPES: an application to a police station or an executive
    # officer, a notice, a standalone affidavit, a deed. These have no cause-title,
    # no opposing party and no prayer-to-a-court, so they cannot go through the court
    # renderer — that is exactly how "application to the police station" used to come
    # back as a court application. A reference upload keeps the mirror path (the
    # uploaded document IS the format, whatever family it belongs to).
    family = cls.get("family") or DT.COURT_FILING
    if not DT.is_court_family(family) and not reference_text:
        return _finalize(_draft_non_court(
            family, dt, det, key, court, bail_type, matter, lang, cls,
            shared_warnings, style))

    # escape hatch: one env var restores the old canonical-first routing exactly
    if det and os.environ.get("DRAFTER_CANONICAL_FIRST", "").strip().lower() in ("1", "true", "yes", "on"):
        try:
            _cr = _canonical_result(dt, key, court, bail_type, matter, lang, cls, shared_warnings)
            _cr["_style"] = style
            return _finalize(_cr)
        except Exception as e:
            cls["reason"] = f"canonical render failed ({type(e).__name__}); authored instead"

    # --- PRIMARY: the LLM authors from the WHOLE input, prescribed format in front ---
    # Field extraction runs in a parallel thread as a best-effort side product (the
    # structured-editor handoff + the canonical floor's data) — never on the critical
    # path, never a reason to drop input facts from the draft itself.
    extract_fut = None
    if det:
        try:
            mod = _module(key)
            spec = _spec(mod, key, court, bail_type)
            import concurrent.futures as _cf
            _pool = _cf.ThreadPoolExecutor(max_workers=1)
            extract_fut = _pool.submit(extract_fields, spec, matter)
            _pool.shutdown(wait=False)
        except Exception:
            extract_fut = None

    author_type = dt if dt in author.TYPE_BRIEFS else (
        "other_civil" if dt == "other_civil" else "other_criminal")
    a_court = court or _authored_court(author_type, cls)
    exemplar = _format_exemplar(key, court, bail_type, lang) if det else ""

    result = None
    try:
        result = author.author_document(matter, author_type, lang, court=a_court,
                                        format_exemplar=exemplar, style=style)
    except Exception:
        log.exception("authoring path failed for doc_type=%s — falling to canonical floor", dt)
        result = None

    if result is not None:
        result.update({
            "doc_type": dt,
            "court": a_court,
            "bail_type": bail_type or "",
            "confidence": cls["confidence"],
            "html_hi": result["html"] if lang != "en" else "",
            "html_en": result["html"] if lang == "en" else "",
            "reason": cls.get("reason", ""),
            "classified_as": dt,
        })
        if det:
            # union the template's reviewed hearing authorities into the authored ones
            try:
                mod = _module(key)
                cites = result.setdefault("cite_at_hearing", [])
                for c in (getattr(mod, "CITE_AT_HEARING", []) or []):
                    if c not in cites:
                        cites.append(c)
            except Exception:
                pass
            # structured-editor handoff, if the parallel extraction landed
            if extract_fut is not None:
                try:
                    data, _ = extract_fut.result(timeout=25)
                    data = dict(data)
                    if court:
                        data["court"] = court
                    if bail_type:
                        data["bail_type"] = bail_type
                    eid, efields = _editor_handoff(key, court, bail_type, data)
                    if eid:
                        result["editor_id"], result["editor_fields"] = eid, efields
                        result["data"] = data
                except Exception:
                    pass
        result["warnings"] = shared_warnings + list(result.get("warnings") or [])
        result["_style"] = style
        return _finalize(result)

    # --- FLOOR 1: LLM chain down → the deterministic canonical template render ---
    if det:
        try:
            data: dict = {}
            if extract_fut is not None:
                try:
                    data, _ = extract_fut.result(timeout=25)
                except Exception:
                    data = {}
            floor = _canonical_result(dt, key, court, bail_type, matter, lang, cls,
                                      shared_warnings, data=data)
            floor["warnings"] = list(floor.get("warnings") or []) + [
                "AI ड्राफ्टिंग क्षणिक रूप से अनुपलब्ध रही — यह मानक (canonical) प्रारूप है; रिक्त स्थान संपादक में भर लें।"
                if lang != "en" else
                "AI drafting was temporarily unavailable — this is the standard canonical format; "
                "fill the blanks in the editor."]
            floor["_style"] = style
            return _finalize(floor)
        except Exception:
            log.exception("canonical floor failed for doc_type=%s — returning skeleton", dt)

    # --- FLOOR 2: pure-python standard shape (cannot fail) ---
    _lr = _last_resort(dt, lang, matter, shared_warnings)
    _lr["_style"] = style
    return _finalize(_lr)
