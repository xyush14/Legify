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
    "affidavit": Story(
        id="affidavit",
        label={"en": "Affidavit", "hi": "शपथपत्र"},
        sub={"en": "S.200 CrPC · supporting", "hi": "धारा 200 दंप्रसं"},
        icon="document", ready=False),
    "vakalatnama": Story(
        id="vakalatnama",
        label={"en": "Vakalatnama", "hi": "वकालतनामा"},
        sub={"en": "Authorisation to represent", "hi": "प्रतिनिधित्व प्राधिकार"},
        icon="user-check", ready=False),
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
