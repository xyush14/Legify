"""Document ontology — WHAT KIND of document is this, and what parts does it have.

WHY THIS EXISTS
---------------
Until this module, Headnote could produce exactly ONE document shape:

    court name → case number → party A विरुद्ध party B → numbered "यह कि" paras
    → prayer → द्वारा अभिभाषक → सत्यापन

…for every request, because three things hardcoded it: the authored payload schema
(`author.HOUSE_STYLE`, whose fields are a cause-title and nothing else), the renderer
(`author.render_authored`), and a MANDATORY-TOP-SECTION instruction in `compose.py`
that said "open EVERY document with exactly these lines".

So an advocate asking for an *application to the police station* — which has no court,
no opposing party, no विरुद्ध and no prayer — got a court application. Not because the
model was weak, but because there was nowhere in the schema to put "सेवा में, थाना
प्रभारी" and no renderer that would emit it.

THE MODEL
---------
An advocate's document is defined by two facts, not by a template name:

    WHO is it addressed to  (forum_type)  ×  WHAT instrument is it  (instrument)
        → a FAMILY, which owns a PARTS GRAMMAR.

Parts are composable and ordered. A court filing has a cause-title and a prayer; an
application to an authority has सेवा में / विषय / संदर्भ and a निवेदन; a deed has
recitals and a schedule. None of them is a special case of another.

UNIVERSALITY (see memory → feedback_universal_not_one_user)
-----------------------------------------------------------
Labels resolve per language and NEVER fall back to Hindi — a Chennai or Kolkata
filing carrying a Devanagari heading is a defective document. Unpinned languages fall
back to ENGLISH, which is neutral and read everywhere. Regional cells below are marked
for advocate sign-off exactly like `i18n/glossary.py`: pin a cell only once a
practising advocate in that jurisdiction has confirmed it.

This module is PURE DATA + PURE FUNCTIONS. No LLM, no I/O, no rendering — so it is
cheap to test and safe to import anywhere.
"""
from __future__ import annotations

from typing import Iterable

# ===========================================================================
# 1) THE TWO AXES
# ===========================================================================

# WHO the document is addressed to.
FORUM_TYPES = (
    "court",          # any judicial forum — Magistrate, Sessions, HC, Family, Civil
    "tribunal",       # NCLT, DRT, MACT-as-tribunal, Consumer, CAT, Income-tax appellate
    "police",         # SHO / थाना प्रभारी / Superintendent of Police / Commissioner
    "executive",      # Collector, SDM, Tahsildar, RTO, municipal, excise, revenue
    "registrar",      # Sub-Registrar, Registrar of Societies/Firms/Companies, university
    "institution",    # bank, insurer, employer, school/university, utility, RERA desk
    "private_party",  # the other side directly — a notice, a reply to a notice
    "none",           # addressed to nobody — a standalone affidavit, a deed, an opinion
)

# WHAT legal instrument it is.
INSTRUMENTS = (
    "petition",        # writ, revision, appeal, quashing — a court is moved
    "application",     # आवेदन पत्र — moves a court OR requests an authority
    "complaint",       # परिवाद / FIR-complaint / consumer complaint
    "notice",          # legal notice, demand notice, §80 CPC, §138 NI
    "reply",           # जवाब / written statement / reply to a notice
    "affidavit",       # शपथ पत्र, standalone
    "deed",            # agreement, sale deed, partnership, MoU, power of attorney
    "representation",  # a written representation to an authority (no relief prayed)
)

# ===========================================================================
# 2) THE FAMILIES — each owns a parts grammar
# ===========================================================================

COURT_FILING = "court_filing"
AUTHORITY_APPLICATION = "authority_application"
NOTICE = "notice"
AFFIDAVIT = "affidavit"
DEED = "deed"

FAMILIES = (COURT_FILING, AUTHORITY_APPLICATION, NOTICE, AFFIDAVIT, DEED)

#: The one family that predates this module. Its rendering path is byte-identical to
#: what shipped before — `author.render_authored` is untouched for it. Every guard,
#: template, canonical floor and Draft-DNA behaviour on the court path is unchanged.
LEGACY_FAMILY = COURT_FILING


# ===========================================================================
# 3) PARTS — the vocabulary a document is assembled from
# ===========================================================================
# A part is (key, requiredness). "req" = always emitted; "opt" = emitted when the
# payload carries it; "cond" = emitted only when a named flag on the payload is set.

PARTS: dict[str, tuple[tuple[str, str], ...]] = {
    # --- the existing court shape, described here for completeness. Rendering for
    #     this family still goes through author.render_authored, NOT the parts
    #     renderer — this entry documents the grammar and drives the prompt only.
    COURT_FILING: (
        ("side_label", "opt"),
        ("court", "req"),
        ("case_no", "opt"),
        ("parties", "req"),          # applicant / versus / respondent block
        ("title_line", "req"),
        ("prelude", "opt"),
        ("salutation", "opt"),
        ("body_numbered", "req"),    # the numbered "यह कि …" grounds
        ("prayer", "req"),
        ("signature", "req"),
        ("verification", "cond"),    # needs_verification
    ),

    # --- an application to a police station / Collector / RTO / Registrar / bank.
    #     NO court, NO opposing party, NO विरुद्ध, NO prayer-to-a-court, and the body
    #     is respectful prose, not numbered "यह कि" grounds.
    AUTHORITY_APPLICATION: (
        ("addressee", "req"),        # सेवा में, / To, — office, officer, place
        ("subject", "req"),          # विषय: — the one-line ask
        ("reference", "opt"),        # संदर्भ: — FIR no., file no., prior letter
        ("salutation", "req"),       # महोदय, / Sir,
        ("body_prose", "req"),       # narrative paragraphs, respectful register
        ("request", "req"),          # अतः आपसे निवेदन है कि …
        ("signature", "req"),        # applicant's own signature — NOT द्वारा अभिभाषक
        ("enclosures", "opt"),       # संलग्न: annexure list
    ),

    # --- a notice sent to the other side (or to the State under §80 CPC).
    NOTICE: (
        ("sender_block", "req"),     # advocate's letterhead / chamber address
        ("notice_date", "req"),
        ("addressee", "req"),
        ("subject", "req"),
        ("through_clause", "req"),   # "under instructions from my client …"
        ("body_numbered", "req"),    # numbered statement of facts
        ("demand", "req"),           # what is demanded, in what time
        ("consequence", "req"),      # what follows on non-compliance
        ("signature", "req"),        # advocate signs — this one IS the advocate
        ("enclosures", "opt"),
    ),

    # --- a standalone affidavit: a deponent block, sworn paras, verification.
    AFFIDAVIT: (
        ("court", "opt"),            # affidavits are often filed IN a case, often not
        ("case_no", "opt"),
        ("title_line", "req"),       # शपथ पत्र
        ("deponent_block", "req"),   # I, X s/o Y, aged, r/o …, do hereby solemnly affirm
        ("body_numbered", "req"),
        ("verification", "req"),     # always — an affidavit without one is a nullity
        ("signature", "req"),
        ("attestation", "opt"),      # before Oath Commissioner / Notary
    ),

    # --- a deed or agreement between parties.
    DEED: (
        ("title_line", "req"),
        ("deed_date", "req"),
        ("parties", "req"),          # first party / second party — NOT applicant/versus
        ("recitals", "req"),         # WHEREAS …
        ("operative_clause", "req"), # NOW THIS DEED WITNESSETH …
        ("clauses", "req"),          # numbered covenants
        ("schedule", "opt"),         # description of property
        ("signature", "req"),
        ("witnesses", "req"),        # a deed unwitnessed is a defective deed
    ),
}


# ===========================================================================
# 4) RESOLUTION — forum_type × instrument → family
# ===========================================================================

def resolve_family(forum_type: str = "", instrument: str = "") -> str:
    """The one rule that decides a document's shape.

    Order matters: the INSTRUMENT wins where it is intrinsically shape-defining
    (a deed is a deed wherever it is addressed; an affidavit filed in court still
    has a deponent block, not a cause-title body). Otherwise the FORUM decides.

    Unknown/blank inputs fall back to the court filing, which is the pre-existing
    behaviour — so a classifier that says nothing changes nothing.
    """
    f = (forum_type or "").strip().lower()
    i = (instrument or "").strip().lower()

    # instrument-dominant shapes
    if i == "deed":
        return DEED
    if i == "affidavit":
        return AFFIDAVIT
    if i == "notice":
        return NOTICE

    # a document aimed at the other side directly is a notice even if the model
    # called it an "application" — there is no forum to move.
    if f == "private_party":
        return NOTICE

    # forum-dominant shapes
    if f in ("police", "executive", "registrar", "institution"):
        return AUTHORITY_APPLICATION
    if f in ("court", "tribunal"):
        return COURT_FILING
    if f == "none":
        # addressed to nobody and not a deed/affidavit/notice — a representation
        # with no forum is still an authority-style letter, not a court filing.
        return AUTHORITY_APPLICATION if i == "representation" else COURT_FILING

    return COURT_FILING


def is_court_family(family: str) -> bool:
    """True when the document keeps the pre-existing court rendering path."""
    return (family or COURT_FILING) == COURT_FILING


def parts_for(family: str) -> tuple[tuple[str, str], ...]:
    return PARTS.get(family or "", PARTS[COURT_FILING])


# ===========================================================================
# 5) LABELS — per language, English fallback, NEVER Hindi fallback
# ===========================================================================
# Discipline copied from i18n/glossary.py: a blank cell means "not yet confirmed by
# a practising advocate in that jurisdiction" and resolves to English. Do not fill a
# cell from a dictionary — fill it from a filed document or an advocate's sign-off.
#
#   hi — standard Hindi-belt administrative/court register. Confirmed.
#   en — formal Indian official English. Confirmed.
#   mr / gu / bn — DRAFTED, PENDING SIGN-OFF. Blank until then, so the draft says
#                  something neutral and correct rather than something Hindi and wrong.

_LABELS: dict[str, dict[str, str]] = {
    # --- authority application ---
    "to":            {"hi": "सेवा में,",     "en": "To,",            "mr": "सेवेत,",   "gu": "સેવામાં,", "bn": ""},
    "subject":       {"hi": "विषय",          "en": "Subject",        "mr": "विषय",     "gu": "વિષય",    "bn": "বিষয়"},
    "reference":     {"hi": "संदर्भ",        "en": "Reference",      "mr": "संदर्भ",   "gu": "સંદર્ભ",  "bn": ""},
    "sir":           {"hi": "महोदय,",        "en": "Sir,",           "mr": "महोदय,",   "gu": "સાહેબ,",  "bn": "মহোদয়,"},
    "request_open":  {"hi": "अतः आपसे निवेदन है कि", "en": "It is therefore requested that",
                      "mr": "तरी आपणास विनंती आहे की", "gu": "તેથી આપને વિનંતી છે કે", "bn": ""},
    "enclosures":    {"hi": "संलग्न",        "en": "Enclosures",     "mr": "सोबत",     "gu": "સામેલ",   "bn": "সংযুক্তি"},
    "applicant":     {"hi": "आवेदक",         "en": "Applicant",      "mr": "अर्जदार",  "gu": "અરજદાર",  "bn": "আবেদনকারী"},
    "yours":         {"hi": "भवदीय,",        "en": "Yours faithfully,", "mr": "आपला विश्वासू,", "gu": "આપનો વિશ્વાસુ,", "bn": ""},

    # --- shared ---
    "place":         {"hi": "स्थान",         "en": "Place",          "mr": "स्थळ",     "gu": "સ્થળ",    "bn": "স্থান"},
    "date":          {"hi": "दिनांक",        "en": "Date",           "mr": "दिनांक",   "gu": "તારીખ",   "bn": "তারিখ"},

    # --- notice ---
    "legal_notice":  {"hi": "विधिक सूचना पत्र", "en": "LEGAL NOTICE", "mr": "कायदेशीर नोटीस", "gu": "કાનૂની નોટિસ", "bn": ""},
    "advocate":      {"hi": "एडवोकेट",       "en": "Advocate",       "mr": "अधिवक्ता", "gu": "એડવોકેટ", "bn": "আইনজীবী"},

    # --- affidavit ---
    "affidavit":     {"hi": "शपथ पत्र",      "en": "AFFIDAVIT",      "mr": "प्रतिज्ञापत्र", "gu": "સોગંદનામું", "bn": "হলফনামা"},
    "deponent":      {"hi": "शपथकर्ता",      "en": "Deponent",       "mr": "प्रतिज्ञापक", "gu": "સોગંદ લેનાર", "bn": ""},
    "verification":  {"hi": "सत्यापन",       "en": "VERIFICATION",   "mr": "सत्यापन",  "gu": "સત્યાપન", "bn": "সত্যপাঠ"},

    # --- deed ---
    "witnesses":     {"hi": "साक्षीगण",      "en": "WITNESSES",      "mr": "साक्षीदार", "gu": "સાક્ષીઓ", "bn": ""},
    "schedule":      {"hi": "अनुसूची",       "en": "SCHEDULE",       "mr": "अनुसूची",  "gu": "અનુસૂચિ", "bn": ""},
    "first_party":   {"hi": "प्रथम पक्ष",    "en": "First Party",    "mr": "प्रथम पक्ष", "gu": "પ્રથમ પક્ષ", "bn": ""},
    "second_party":  {"hi": "द्वितीय पक्ष",  "en": "Second Party",   "mr": "द्वितीय पक्ष", "gu": "દ્વિતીય પક્ષ", "bn": ""},
}


def label(key: str, lang: str = "en") -> str:
    """The court-correct label for `key` in `lang`.

    Falls back to ENGLISH — never to Hindi. A Marathi or Tamil document carrying a
    Devanagari-Hindi heading is wrong in a way an English heading is not.
    """
    row = _LABELS.get(key)
    if not row:
        return ""
    lg = (lang or "en").strip().lower()
    return (row.get(lg) or "").strip() or row.get("en", "")


def label_coverage(lang: str) -> tuple[int, int]:
    """(pinned, total) — how much of the label set is advocate-ready for `lang`.
    Mirrors i18n.glossary.coverage so the two can be reported together."""
    total = len(_LABELS)
    pinned = sum(1 for row in _LABELS.values() if (row.get(lang) or "").strip())
    return pinned, total


# ===========================================================================
# 6) PROMPT SURFACE — the grammar, described to the model
# ===========================================================================
# One paragraph per family, telling the model what this document IS and — as
# importantly — what it must NOT carry over from the court shape. The negatives are
# load-bearing: the model has 41 court templates' worth of prior in its context, and
# without an explicit prohibition it reaches for विरुद्ध and प्रार्थना every time.

FAMILY_BRIEFS: dict[str, str] = {
    AUTHORITY_APPLICATION: (
        "This is an APPLICATION TO AN AUTHORITY — a police station (थाना प्रभारी / SHO / "
        "Superintendent), a revenue or executive officer (Collector, SDM, Tahsildar, RTO), a "
        "Registrar, or an institution (bank, insurer, employer, university). It is NOT a court "
        "filing and must not look like one.\n"
        "  • It opens 'सेवा में,' / 'To,' with the OFFICE, the officer's designation and the place — "
        "never a court cause-title.\n"
        "  • It carries a विषय (Subject) line stating the ask in one sentence, and a संदर्भ "
        "(Reference) line when there is a prior FIR / file / letter number to cite.\n"
        "  • THERE IS NO OPPOSING PARTY. Do NOT write विरुद्ध / बनाम / Versus. Do NOT write an "
        "applicant-vs-respondent block. There is one applicant and one addressee.\n"
        "  • THERE IS NO CASE NUMBER and no court. Do not invent either.\n"
        "  • The body is respectful continuous PROSE in short numbered or unnumbered paragraphs — "
        "NOT the court's numbered 'यह कि …' grounds. Facts, then what is sought, then why.\n"
        "  • It closes with a निवेदन (request), not a court प्रार्थना: 'अतः आपसे निवेदन है कि …'. "
        "Never 'अतः श्रीमान न्यायालय से प्रार्थना है'.\n"
        "  • THE APPLICANT signs it, over their own name. Do NOT add 'द्वारा अभिभाषक' or an "
        "advocate signature line unless the advocate is expressly the one applying.\n"
        "  • NO सत्यापन / verification block — that belongs to a pleading. If the authority "
        "requires a sworn statement, list an affidavit under संलग्न instead.\n"
        "  • List annexures under संलग्न when the applicant said documents accompany it."
    ),
    NOTICE: (
        "This is a NOTICE sent to the other side (or, under §80 CPC, to the State) — not a filing. "
        "It is written by the ADVOCATE, in the first person, on instructions.\n"
        "  • It opens with the advocate's chamber block and the date, then the addressee.\n"
        "  • It states 'under instructions from and on behalf of my client …'.\n"
        "  • Facts are set out in NUMBERED paragraphs (this family does keep numbering).\n"
        "  • It ends with a clear DEMAND, a TIME LIMIT, and the CONSEQUENCE of non-compliance.\n"
        "  • THE ADVOCATE signs it. There is no court, no cause-title, no prayer, no सत्यापन."
    ),
    AFFIDAVIT: (
        "This is a STANDALONE AFFIDAVIT. It opens with the deponent's own declaration — "
        "'I, <name>, S/o <father>, aged <age>, R/o <address>, do hereby solemnly affirm and state "
        "on oath …' — NOT a cause-title with an opposing party. Where it is filed in a pending "
        "case, the court and case number may head it, but there is still no विरुद्ध block and no "
        "prayer. Sworn paragraphs, then the verification, then the deponent's signature and the "
        "attestation before the Oath Commissioner / Notary."
    ),
    DEED: (
        "This is a DEED / AGREEMENT between parties — there is no court and no adversary.\n"
        "  • Parties are FIRST PARTY and SECOND PARTY (with full descriptors), never "
        "applicant/respondent and never विरुद्ध.\n"
        "  • It carries RECITALS ('WHEREAS …' / 'जबकि …') establishing the background, then the "
        "operative clause ('NOW THIS DEED WITNESSETH …' / 'अतः यह विलेख साक्षी है कि …'), then "
        "numbered covenants.\n"
        "  • Property or subject-matter is described in a SCHEDULE.\n"
        "  • It closes with the parties' signatures AND witnesses. No prayer, no सत्यापन."
    ),
}


def family_brief(family: str) -> str:
    """The instruction block describing this family to the drafting model.
    Empty for the court family — that path keeps its existing prompt untouched."""
    return FAMILY_BRIEFS.get(family or "", "")


def parts_prompt(family: str, lang: str = "en") -> str:
    """The parts grammar, rendered for the model: which parts, in what order, and
    which are optional. Keeps the model from inventing a section order of its own."""
    rows: list[str] = []
    for key, req in parts_for(family):
        mark = {"req": "required", "opt": "optional", "cond": "conditional"}.get(req, req)
        rows.append(f"  {len(rows) + 1}. {key} ({mark})")
    return "\n".join(rows)


def all_part_keys() -> Iterable[str]:
    """Every part key across every family — used by the renderer and the DNA block
    mapper so a part can never be emitted that the layout engine cannot place."""
    seen: list[str] = []
    for spec in PARTS.values():
        for key, _ in spec:
            if key not in seen:
                seen.append(key)
    return seen
