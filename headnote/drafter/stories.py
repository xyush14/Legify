"""
Story registry for the drafting engine.

Each Story:
  - has a stable string id ('friendly_cash_loan', 'bail_anticipatory', ...)
  - has bilingual display metadata (label + sub in en + hi)
  - declares its sections (the 6-card flow shape from the v3 prototype)
  - registers a render_en + render_hi function (template functions that
    take an answers dict and return HTML)
  - tracks a version so saved drafts can pin to the template version
    they were created with (avoids 'lawyer's saved draft changes when
    the template is fixed' surprise — see HEADNOTE_DRAFTING_HANDOFF.md
    §2.7 + earlier brainstorm)

Adding a story = adding a new module under templates/ + one entry here.
The list of 10 v0.1 stories matches the in-app drafting home tile grid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


# ----------------------------------------------------------- types

@dataclass
class Section:
    """One card in the drafter's 6-card flow."""
    id: str                             # 'parties', 'story', 'cheque', ...
    eyebrow: dict[str, str]             # {'en': 'SECTION 1', 'hi': 'अनुभाग 1'}
    title: dict[str, str]
    sub: dict[str, str]
    type: str                           # renderer the FE dispatches to
    scan: bool = False                  # if True, FE shows scan-to-prefill prompt


@dataclass
class Story:
    """A draft type — registered template."""
    id: str
    label: dict[str, str]
    sub: dict[str, str]
    icon: str                           # icon name, matches FE SVG keys
    sections: list[Section] = field(default_factory=list)
    # Render functions; signature is render(answers: dict) -> str (HTML).
    # When ready=False the renders are None and the FE shows 'coming soon'
    # in the tile + on the per-story page if the user manages to navigate.
    render_en: Optional[Callable[[dict], str]] = None
    render_hi: Optional[Callable[[dict], str]] = None
    template_version: int = 1
    ready: bool = False


# ----------------------------------------------------------- registry

_FRIENDLY_CASH_LOAN_SECTIONS = [
    Section("parties",
        eyebrow={"en": "SECTION 1", "hi": "अनुभाग 1"},
        title={"en": "The parties", "hi": "पक्षकार"},
        sub={"en": "Both sides — names, ages, addresses.",
             "hi": "दोनों पक्षों के नाम, आयु, पते।"},
        type="parties"),
    Section("story",
        eyebrow={"en": "SECTION 2", "hi": "अनुभाग 2"},
        title={"en": "The loan story", "hi": "ऋण की कहानी"},
        sub={"en": "Relationship, money lent, mode, witness, partial returns.",
             "hi": "संबंध, उधार, माध्यम, गवाह, आंशिक वापसी।"},
        type="friendly_story"),
    Section("cheque",
        eyebrow={"en": "SECTION 3", "hi": "अनुभाग 3"},
        title={"en": "The cheque", "hi": "चेक"},
        sub={"en": "Details from the cheque the accused gave.",
             "hi": "अभियुक्त द्वारा दिए गए चेक का विवरण।"},
        type="cheque", scan=True),
    Section("dishonour",
        eyebrow={"en": "SECTION 4", "hi": "अनुभाग 4"},
        title={"en": "The dishonour", "hi": "अनादर"},
        sub={"en": "From the bank return memo.",
             "hi": "बैंक के रिटर्न ज्ञापन से।"},
        type="dishonour", scan=True),
    Section("notice",
        eyebrow={"en": "SECTION 5", "hi": "अनुभाग 5"},
        title={"en": "The notice timeline", "hi": "नोटिस की समय-रेखा"},
        sub={"en": "Sent → received → 15-day expiry → cause of action.",
             "hi": "भेजा → प्राप्त → 15 दिन समाप्ति → वादकारण।"},
        type="notice"),
    Section("court",
        eyebrow={"en": "SECTION 6", "hi": "अनुभाग 6"},
        title={"en": "Court and filing", "hi": "न्यायालय एवं दाखिल"},
        sub={"en": "Final details before generating the draft.",
             "hi": "प्रारूप तैयार करने से पहले अंतिम विवरण।"},
        type="court"),
]


# Templates module loaded lazily so circular imports don't bite during
# bootstrap. The actual render functions live in
# headnote/drafter/templates/<story_id>.py — each module exports
# `render_en(answers) -> str` and `render_hi(answers) -> str`.
def _lazy_template(module_name: str, fn_name: str) -> Optional[Callable[[dict], str]]:
    def _loader(answers: dict) -> str:
        try:
            mod = __import__(
                f"headnote.drafter.templates.{module_name}",
                fromlist=[fn_name],
            )
            return getattr(mod, fn_name)(answers)
        except Exception as e:
            return f"<p>(template not yet ported: {module_name}.{fn_name} — {e})</p>"
    return _loader


STORIES: dict[str, Story] = {
    "friendly_cash_loan": Story(
        id="friendly_cash_loan",
        label={"en": "Friendly Cash Loan", "hi": "मित्रवत नकद ऋण"},
        sub={"en": "Known person · §138 NI Act", "hi": "परिचित व्यक्ति"},
        icon="handshake",
        sections=_FRIENDLY_CASH_LOAN_SECTIONS,
        render_en=_lazy_template("friendly_cash_loan", "render_en"),
        render_hi=_lazy_template("friendly_cash_loan", "render_hi"),
        template_version=1,
        ready=False,   # flip True once template module is fully ported + reviewed
    ),

    # The other nine — registered as stub stories so the API can list
    # them. ready=False means the per-story endpoints refuse to render
    # until the template module is ported.
    "business_goods": Story(
        id="business_goods",
        label={"en": "Goods Supplied / Business", "hi": "व्यापारिक लेन-देन"},
        sub={"en": "Invoice-based · §138 NI Act", "hi": "इनवॉइस आधारित"},
        icon="box", ready=False),
    "bail_application": Story(
        id="bail_application",
        label={"en": "Bail Application", "hi": "ज़मानत आवेदन"},
        sub={"en": "S.437 / S.438 / S.439 CrPC · live preview · FIR OCR",
             "hi": "धारा 437 / 438 / 439 दण्ड प्रकिया · लाइव पूर्वावलोकन · FIR स्कैन"},
        icon="lock",
        sections=[],  # custom UI lives at /draft/bail (not the generic 6-card flow)
        render_en=_lazy_template("bail_application", "render_en"),
        render_hi=_lazy_template("bail_application", "render_hi"),
        template_version=1,
        ready=True),
    "discharge_239": Story(
        id="discharge_239",
        label={"en": "Discharge (S.239 / 498A)", "hi": "उन्मोचन आवेदन (धारा 239)"},
        sub={"en": "S.239 CrPC / 262 BNSS · charge-sheet OCR · live preview",
             "hi": "धारा 239 दं.प्र.सं. · आरोप पत्र स्कैन · लाइव पूर्वावलोकन"},
        icon="shield",
        sections=[],  # custom UI lives at /draft/discharge (bail-style page)
        render_en=_lazy_template("discharge_239", "render_en"),
        render_hi=_lazy_template("discharge_239", "render_hi"),
        template_version=1,
        ready=True),

    # ---- Phase-2 deterministic builders — authored to the bail/discharge
    # standard, PENDING Vishnu ji's review. ready=False keeps them out of the
    # product picker; each is reviewable at /draft/<id>/review (the route imports
    # review_page_html directly, bypassing the ready gate). Flip ready=True per
    # type once he signs off.
    "anticipatory_bail": Story(
        id="anticipatory_bail",
        label={"en": "Anticipatory Bail (S.482 / S.438)", "hi": "अग्रिम जमानत (धारा 482)"},
        sub={"en": "Pre-arrest · Sessions / HC · apprehension grounds",
             "hi": "गिरफ्तारी-पूर्व · सत्र/उच्च न्यायालय · आशंका आधार"},
        icon="lock",
        sections=[],
        render_en=_lazy_template("anticipatory_bail", "render_en"),
        render_hi=_lazy_template("anticipatory_bail", "render_hi"),
        template_version=1,
        ready=False),
    "maintenance": Story(
        id="maintenance",
        label={"en": "Maintenance (S.144 / S.125)", "hi": "भरण-पोषण (धारा 144)"},
        sub={"en": "Family Court · wife / children · with verification",
             "hi": "कुटुम्ब न्यायालय · पत्नी/बच्चे · सत्यापन सहित"},
        icon="users",
        sections=[],
        render_en=_lazy_template("maintenance", "render_en"),
        render_hi=_lazy_template("maintenance", "render_hi"),
        template_version=1,
        ready=False),
    "appeal_conviction": Story(
        id="appeal_conviction",
        label={"en": "Appeal against Conviction (S.415 / S.374)", "hi": "दोषसिद्धि के विरुद्ध अपील (धारा 415)"},
        sub={"en": "Sessions / HC · canonical header · grounds of appeal · acquittal · bilingual",
             "hi": "सत्र/उच्च न्यायालय · मानक शीर्ष · अपील के आधार · दोषमुक्ति · द्विभाषी"},
        icon="scale",
        sections=[],
        render_en=_lazy_template("appeal", "render_en"),  # canonical-standard — supersedes appeal_conviction.py
        render_hi=_lazy_template("appeal", "render_hi"),
        template_version=2,
        ready=False),
    "cheque_138": Story(
        id="cheque_138",
        label={"en": "Cheque Bounce Complaint (S.138 NI Act)", "hi": "चेक बाउंस परिवाद (धारा 138)"},
        sub={"en": "JMFC · payee complaint · canonical header · bilingual",
             "hi": "न्या.दं. · परिवाद पत्र · मानक शीर्ष · द्विभाषी"},
        icon="file-text",
        sections=[],
        render_en=_lazy_template("cheque_138", "render_en"),
        render_hi=_lazy_template("cheque_138", "render_hi"),
        template_version=1,
        ready=False),  # first builder on the canonical header — /draft/cheque/review
    "bail": Story(
        id="bail",
        label={"en": "Bail — all courts (S.480 / 483 / 482)", "hi": "जमानत — सभी न्यायालय (धारा 480/483/482)"},
        sub={"en": "Magistrate / Sessions / HC + anticipatory · canonical header · bilingual",
             "hi": "मजिस्ट्रेट/सत्र/उच्च न्यायालय + अग्रिम · मानक शीर्ष · द्विभाषी"},
        icon="lock",
        sections=[],
        render_en=_lazy_template("bail", "render_en"),
        render_hi=_lazy_template("bail", "render_hi"),
        template_version=1,
        ready=False),  # unified, court-parameterized engine — /draft/bail/review
                       # (supersedes bail_regular.py: adds HC tables/Zeba-Khan + anticipatory + field schema)
    "discharge": Story(
        id="discharge",
        label={"en": "Discharge (S.262/250 · 239/227)", "hi": "उन्मोचन (धारा 262/250)"},
        sub={"en": "Magistrate/Sessions · grave-suspicion · canonical header · bilingual",
             "hi": "मजिस्ट्रेट/सत्र · प्रथम-दृष्टया · मानक शीर्ष · द्विभाषी"},
        icon="shield",
        sections=[],
        render_en=_lazy_template("discharge", "render_en"),
        render_hi=_lazy_template("discharge", "render_hi"),
        template_version=1,
        ready=False),  # canonical-header rebuild of discharge_239 — /draft/discharge/review
    "revision": Story(
        id="revision",
        label={"en": "Criminal Revision (S.438-442 · 397-401)", "hi": "पुनरीक्षण (धारा 438-442)"},
        sub={"en": "HC/Sessions · challenge a lower order · canonical header · bilingual",
             "hi": "उच्च/सत्र न्यायालय · अधीनस्थ आदेश को चुनौती · मानक शीर्ष · द्विभाषी"},
        icon="gavel",
        sections=[],
        render_en=_lazy_template("revision", "render_en"),
        render_hi=_lazy_template("revision", "render_hi"),
        template_version=1,
        ready=False),  # canonical-standard — /draft/revision/review
    "dv": Story(
        id="dv",
        label={"en": "Domestic Violence (S.12 PWDVA)", "hi": "घरेलू हिंसा (धारा 12)"},
        sub={"en": "JMFC · §17-22 reliefs · canonical header · bilingual",
             "hi": "न्या.दं. · §17-22 अनुतोष · मानक शीर्ष · द्विभाषी"},
        icon="shield",
        sections=[],
        render_en=_lazy_template("dv", "render_en"),
        render_hi=_lazy_template("dv", "render_hi"),
        template_version=1,
        ready=False),  # canonical-standard — /draft/dv/review
    "quashing": Story(
        id="quashing",
        label={"en": "Quashing (S.528 BNSS / S.482)", "hi": "अभिखण्डन याचिका (धारा 528)"},
        sub={"en": "High Court · compromise/abuse · canonical header · bilingual",
             "hi": "उच्च न्यायालय · राजीनामा/दुरुपयोग · मानक शीर्ष · द्विभाषी"},
        icon="x-circle",
        sections=[],
        render_en=_lazy_template("quashing", "render_en"),
        render_hi=_lazy_template("quashing", "render_hi"),
        template_version=1,
        ready=False),  # canonical-standard — /draft/quashing/review
    "parivad": Story(
        id="parivad",
        label={"en": "Private Complaint (S.223 BNSS / S.200)", "hi": "परिवाद पत्र (धारा 223)"},
        sub={"en": "JMFC · cognizance + summon · canonical header · bilingual",
             "hi": "न्या.दं. · संज्ञान + समन · मानक शीर्ष · द्विभाषी"},
        icon="file-text",
        sections=[],
        render_en=_lazy_template("parivad", "render_en"),
        render_hi=_lazy_template("parivad", "render_hi"),
        template_version=1,
        ready=False),  # canonical-standard — /draft/parivad/review

    "affidavit": Story(
        id="affidavit",
        label={"en": "Affidavit", "hi": "शपथपत्र"},
        sub={"en": "S.200 CrPC · supporting", "hi": "धारा 200 दंप्रसं"},
        icon="document", ready=False),
    "vakalatnama": Story(
        id="vakalatnama",
        label={"en": "Vakalatnama", "hi": "वकालतनामा"},
        sub={"en": "Authorisation to represent", "hi": "प्रतिनिधित्व प्राधिकार"},
        icon="user-check",
        sections=[],
        render_en=_lazy_template("vakalatnama", "render_en"),
        render_hi=_lazy_template("vakalatnama", "render_hi"),
        template_version=1,
        ready=False),  # proposal — /draft/vakalatnama/review for Vishnu sign-off
    "adjournment": Story(
        id="adjournment",
        label={"en": "Adjournment Application", "hi": "स्थगन आवेदन"},
        sub={"en": "Request next date", "hi": "अगली तारीख का अनुरोध"},
        icon="clock", ready=False),
    "mention_memo": Story(
        id="mention_memo",
        label={"en": "Mention Memo", "hi": "उल्लेख ज्ञापन"},
        sub={"en": "Court mention list entry", "hi": "न्यायालय उल्लेख सूची"},
        icon="message", ready=False),
    "delay_condonation": Story(
        id="delay_condonation",
        label={"en": "Delay Condonation", "hi": "विलंब क्षमापन"},
        sub={"en": "S.5 Limitation Act", "hi": "धारा 5 परिसीमा"},
        icon="hourglass", ready=False),
    "legal_notice": Story(
        id="legal_notice",
        label={"en": "Legal Notice", "hi": "विधिक नोटिस"},
        sub={"en": "Pre-litigation demand", "hi": "वाद-पूर्व माँग"},
        icon="mail", ready=False),
    "reply_notice": Story(
        id="reply_notice",
        label={"en": "Reply to Notice", "hi": "नोटिस का जवाब"},
        sub={"en": "Defensive response", "hi": "रक्षात्मक प्रत्युत्तर"},
        icon="reply", ready=False),
    "execution": Story(
        id="execution",
        label={"en": "Execution Application", "hi": "निष्पादन आवेदन"},
        sub={"en": "Decree · attachment · recovery",
             "hi": "डिक्री · संलग्नक · वसूली"},
        icon="gavel", ready=False),
}


def list_stories(lang: str = "en") -> list[dict]:
    """Serialisable summary of every story — used by GET /api/draft/stories
    to populate the FE tile grid + by clients enumerating draft types.

    Section/render details are deliberately omitted; callers wanting
    the full schema for a single story should hit GET /api/draft/story/<id>.
    """
    out: list[dict] = []
    for s in STORIES.values():
        out.append({
            "id": s.id,
            "label": s.label.get(lang, s.label.get("en", s.id)),
            "sub": s.sub.get(lang, s.sub.get("en", "")),
            "icon": s.icon,
            "ready": s.ready,
            "template_version": s.template_version,
            "section_count": len(s.sections),
        })
    return out


def get_story(story_id: str) -> Optional[Story]:
    return STORIES.get(story_id)


def render_story(story_id: str, lang: str, answers: dict) -> str:
    """Render a story to HTML in the requested lang. Returns a placeholder
    string when the template module hasn't been ported yet (ready=False)
    OR when the requested lang's renderer is None."""
    story = get_story(story_id)
    if story is None:
        return "<p>Unknown story id.</p>"
    if not story.ready:
        return (
            f"<p>Template for <b>{story.label.get('en', story.id)}</b> "
            f"is being built. We'll notify you the moment it goes live.</p>"
        )
    fn = story.render_hi if lang == "hi" else story.render_en
    if fn is None:
        return f"<p>{lang.upper()} render not registered for {story_id}.</p>"
    return fn(answers or {})
