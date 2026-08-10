"""One door into drafting — the server half of the V2 `/draft` screen.

Draft had nineteen surfaces and four of them could start a bail application. The
reason the frontend grew that way is that the BACKEND had two doors: `/from-prompt`
(typed) and `/from-document` (uploaded). This module is the single door that
replaces them for the new screen — brief text, attachments each explicitly tagged
`facts` or `format`, an optional matter, a language — and the old endpoints stay
exactly as they are for the pages that still call them.

Three things live here, and all three are DETERMINISTIC and FREE (no model, no
quota, no network):

  instant_skeleton()  the court skeleton, rendered the moment he presses Draft, in
                      HIS captured page geometry and font. Today he watches an
                      empty screen for 5–15s; the never-fail floor already existed
                      as a hidden fallback, so showing it costs nothing and the
                      perceived wait goes to zero.

  questions_for()     at most ONE round, and only for what genuinely changes the
                      section, the cause-title or the grounds. A free-running chat
                      is where drafting tools die: every unanswered turn is an
                      abandoned draft. "Draft it anyway" is always available, and
                      anything skipped becomes an amber line, never a blocker.

  merge_brief()       the two-source rule, in one place: FACTS sources are folded
                      into the matter text and a FORMAT source is passed through
                      as `reference_text`. They are never conflated — a document
                      only becomes a format source when the advocate says so, and
                      an attached reference always beats the saved profile.

Language-neutral by construction: every word this module injects comes from
`dna_blocks.labels()`, which resolves payload → the reviewed court glossary →
English, and NEVER falls back to Hindi. A Madras filing carrying a Hindi सत्यापन
heading is a defective document.
"""
from __future__ import annotations

import re
from typing import Optional

from headnote.drafter import dna_blocks

# ---------------------------------------------------------------------------
# the instant skeleton
# ---------------------------------------------------------------------------

# How many placeholder grounds to draw. Enough that the page reads as a document
# rather than a stub, few enough that a real 4-ground draft does not shrink.
_SKELETON_GROUNDS = 3


def _blank(n: int = 12) -> str:
    return "_" * n


def classify_fast(brief: str) -> str:
    """doc_type from the brief with ZERO model calls, so the skeleton can be on
    screen before the network has finished thinking. Reuses the same keyword
    ladder the drafting pipeline falls back to, so the instant paper and the
    finished draft agree on what is being drafted."""
    from headnote.drafter.from_prompt import _heuristic_type
    return _heuristic_type(brief or "")


def detect_lang(brief: str, requested: str = "auto") -> str:
    """The language the DRAFTING ENGINE will author in. It is binary today (hi | en),
    because that is what `resolve_lang` and the type briefs support."""
    from headnote.drafter.from_prompt import resolve_lang
    return resolve_lang(requested or "auto", brief or "")


def script_lang(brief: str, requested: str = "auto") -> str:
    """The language the advocate is WORKING in — which is not the same question.

    `resolve_lang` collapses everything to hi | en, so routing labels through it
    would hand a Marathi or Gujarati advocate a Hindi सत्यापन heading, and hand a
    Tamil advocate Hindi as well. Both are defective documents. So an explicit
    language code from the caller is honoured as-is here and resolved by
    `dna_blocks.labels()`, which goes payload → reviewed court glossary → ENGLISH,
    and never Hindi. Only 'auto' falls back to the binary detector."""
    r = (requested or "").strip().lower()[:2]
    if r and r not in ("au", ""):
        return r
    return detect_lang(brief, "auto")


def layout_for(user_id: Optional[str], lang: str) -> tuple[dict, str]:
    """(template, how) — the advocate's own captured layout when he has one,
    otherwise the standard court format in a font his script can render.
    `how` is "own" | "standard", the same word `/api/draft/{id}/docx` reports in
    its `X-Headnote-Format` header, so the screen and the file never disagree."""
    from headnote.drafter import layout_template as LT
    tpl = None
    if user_id:
        try:
            from headnote.drafter import style_profile as SP
            tpl = SP.load_layout(user_id)
        except Exception:
            tpl = None
    if tpl and tpl.get("roles"):
        return tpl, "own"
    return LT.standard_template(LT.default_font_for(lang)), "standard"


def instant_skeleton(brief: str, *, lang: str = "auto", user_id: Optional[str] = None,
                     answers: Optional[dict] = None) -> dict:
    """The paper, before the model has written a word.

    Returns the same role-tagged block shape `dna_blocks.from_authored` produces
    and `layout_template.render_into_layout` consumes, plus the page geometry and
    per-role formats — so the browser can draw HIS page to scale and the .docx
    later comes out of the same blocks. Never raises."""
    from headnote.drafter import author, layout_template as LT

    answers = answers or {}
    draft_lang = detect_lang(brief, lang)      # what the engine will author in (hi|en)
    slang = script_lang(brief, lang)           # what HE works in (hi|en|mr|gu|bn|ta|…)
    doc_type = classify_fast(brief)
    L = dna_blocks.labels(slang)
    try:
        b = author.brief_for(doc_type)
    except Exception:
        b = {}
    # The type briefs carry reviewed Hindi and English wording only. For any other
    # language the honest answer is ENGLISH, never Hindi: a Chennai or Pune filing
    # carrying a Hindi statutory heading is defective. The moment a Tamil or Marathi
    # advocate signs off that vocabulary, this row turns with no code change.
    hi = slang == "hi"
    title = (b.get("label_hi") if hi else b.get("label_en")) or "Application"
    section = b.get("section_hi") if hi else ""
    case_code = (b.get("case_code_hi") if hi else b.get("case_code_en")) or ""
    side = (b.get("side_hi") if hi else b.get("side_en")) or ""

    # The court line is either his own answer or a blank he can SEE. Never a guess:
    # a court is never inferred from a device location or a probable default
    # (see feedback_court_location) — a wrong court on the cause title is fatal.
    court_line = str(answers.get("court") or "").strip() or _blank(34)

    blocks: list[list] = []

    def add(role: str, text: str) -> None:
        if text and str(text).strip():
            blocks.append([role, str(text).strip()])

    add("side_label", side)
    add("court", court_line)
    add("caseno", f"{case_code}– {_blank(10)} / {_blank(4)}".strip())
    add("applicant", f'{L["applicant"]} ——')
    add("applicant", _blank(38))
    add("versus", L["versus"])
    add("respondent", f'{L["respondent"]} ——')
    add("respondent", _blank(38))
    add("section_heading", section or title)
    for _ in range(_SKELETON_GROUNDS):
        add("ground", _blank(56))
    add("prayer", _blank(56))
    add("dateline", f'{L["place"]}: {_blank(10)}')
    add("dateline", f'{L["date"]}: __/__/____')
    add("sig_party", L["applicant"])
    add("sig_by", L["through"])
    add("advocate", f'({_blank(8)}) — {L["advocate"]}')

    tpl, how = layout_for(user_id, slang)
    page = dict(tpl.get("page") or {})
    return {
        "ok": True,
        "doc_type": doc_type,
        "title": title,
        "lang": draft_lang,
        "script_lang": slang,
        "format": how,                       # "own" | "standard"
        "font": LT.template_primary_font(tpl),
        "size": LT.template_primary_size(tpl),
        "page": page,
        "roles": tpl.get("roles") or {},
        "blocks": blocks,
        "n_drafts": tpl.get("n_drafts"),
    }


# ---------------------------------------------------------------------------
# the one round of questions
# ---------------------------------------------------------------------------

# Only two kinds of question earn a place, because only these change the DOCUMENT:
#   court            → changes the cause title AND, for bail, the section
#   first/successive → changes the mandatory disclosure recital and the grounds
# His address does not earn one. Neither does anything we can leave as a blank he
# can see on the page.
_BAIL_FAMILY = {"bail", "anticipatory_bail", "default_bail", "suspension_389"}

_COURT_IN_BRIEF = (
    "न्यायालय", "अदालत", "कोर्ट", "सत्र", "मजिस्ट्रेट", "जे.एम.एफ.सी", "जेएमएफसी",
    "उच्च न्यायालय", "हाईकोर्ट", "cjm", "jmfc", "sessions", "magistrate",
    "high court", "supreme court", "district judge", "tribunal", "family court",
    "न्यायाधीश", "कुटुम्ब न्यायालय", "श्रम न्यायालय",
)
_SUCCESSIVE_IN_BRIEF = (
    "पूर्व में खारिज", "पहले खारिज", "निरस्त हो चुक", "खारिज हो चुक", "द्वितीय जमानत",
    "successive", "second bail", "rejected earlier", "previously rejected",
    "first bail", "प्रथम जमानत", "पहला आवेदन", "कोई जमानत आवेदन प्रस्तुत नहीं",
)

_COURT_OPTIONS_CRIMINAL = ("Sessions Court", "Magistrate / JMFC", "High Court")
_COURT_OPTIONS_CIVIL = ("Civil Court", "District Judge", "High Court")


def questions_for(brief: str, *, lang: str = "auto", doc_type: str = "",
                  answers: Optional[dict] = None) -> dict:
    """At most one round, at most two questions, always skippable.

    Deterministic: a question is asked only when the brief does not already answer
    it. Returns {questions: […], skippable: true}; an empty list means draft now
    and ask nothing."""
    from headnote.drafter import author

    answers = answers or {}
    text = (brief or "").lower()
    dt = doc_type or classify_fast(brief)
    civil = dt in getattr(author, "CIVIL_TYPES", set())
    qs: list[dict] = []

    if "court" not in answers and not any(c.lower() in text for c in _COURT_IN_BRIEF):
        opts = _COURT_OPTIONS_CIVIL if civil else _COURT_OPTIONS_CRIMINAL
        qs.append({
            "id": "court",
            "label": "Which court is this going to?",
            "why": "It sets the cause title, and for bail it sets the section.",
            "options": [{"value": o, "label": o} for o in opts]
                       + [{"value": "", "label": "Other…", "free": True}],
        })

    if (dt in _BAIL_FAMILY and "bail_stage" not in answers
            and not any(c.lower() in text for c in _SUCCESSIVE_IN_BRIEF)):
        qs.append({
            "id": "bail_stage",
            "label": "First bail application, or a successive one?",
            "why": "A successive application must disclose the earlier rejection.",
            "options": [
                {"value": "first", "label": "First"},
                {"value": "successive", "label": "Successive — rejected before"},
            ],
        })

    return {"ok": True, "doc_type": dt, "questions": qs[:2], "skippable": True}


# ---------------------------------------------------------------------------
# the two-source rule
# ---------------------------------------------------------------------------

def merge_brief(brief: str, *, facts_texts: Optional[list[str]] = None,
                matter_context: str = "", answers: Optional[dict] = None,
                lang: str = "hi") -> str:
    """The matter text handed to the drafting engine.

    Every source is LABELLED in the merged text, so the engine (and the
    fact-grounding guard behind it) can tell the advocate's own words from a
    document's OCR from his stored matter data. A FORMAT reference is deliberately
    NOT merged here — it travels separately as `reference_text`, because mixing a
    reference's facts into a draft is exactly the fabrication we promise never to
    do."""
    hi = (lang or "hi") != "en"
    parts: list[str] = []
    if (brief or "").strip():
        parts.append(brief.strip())

    for i, t in enumerate(facts_texts or []):
        t = (t or "").strip()
        if not t:
            continue
        lbl = ("संलग्न दस्तावेज़ से तथ्य" if hi else "Facts from the attached document")
        if len(facts_texts or []) > 1:
            lbl = f"{lbl} {i + 1}"
        parts.append(f"{lbl}:\n{t}")

    if (matter_context or "").strip():
        parts.append(matter_context.strip())

    ans = _answer_lines(answers or {}, hi)
    if ans:
        parts.append(ans)
    return "\n\n".join(parts).strip()


def _answer_lines(answers: dict, hi: bool) -> str:
    """The one round's answers, as facts the engine can use. Only keys we asked
    for are echoed — an unexpected key from a client is ignored rather than
    smuggled into the draft."""
    out: list[str] = []
    court = str(answers.get("court") or "").strip()
    if court:
        out.append(("न्यायालय: " if hi else "Court: ") + court)
    stage = str(answers.get("bail_stage") or "").strip().lower()
    if stage == "first":
        out.append("This is the FIRST bail application; no earlier bail application has been "
                   "filed or rejected." if not hi else
                   "यह प्रथम जमानत आवेदन है; इससे पूर्व कोई जमानत आवेदन प्रस्तुत/निरस्त नहीं हुआ है।")
    elif stage == "successive":
        out.append("This is a SUCCESSIVE bail application; an earlier bail application was "
                   "rejected and that must be disclosed." if not hi else
                   "यह द्वितीय/उत्तरवर्ती जमानत आवेदन है; पूर्व आवेदन निरस्त हुआ था, जिसका "
                   "प्रकटन आवश्यक है।")
    if not out:
        return ""
    head = "आवेदन का विवरण" if hi else "Application details"
    return f"{head}:\n" + "\n".join(out)


def matter_context(matter_id: Optional[str], user_id: Optional[str]) -> str:
    """The advocate's OWN stored matter, folded in as labelled facts.

    Only fields actually on the row are used — nothing is inferred, and a matter
    that is not his (or does not exist) is a silent no-op rather than an error
    that costs him his draft."""
    if not (matter_id and user_id):
        return ""
    try:
        from headnote.cases import storage as cases_storage
        row = cases_storage.get_case(matter_id, user_id=user_id)
    except Exception:
        row = None
    if not row:
        return ""
    cj = row.get("case_json") or {}
    bits: list[str] = []
    client = (cj.get("client") or {}).get("name")
    if client:
        bits.append(f"Client / party: {client}")
    if row.get("case_title"):
        bits.append(f"Case title: {row['case_title']}")
    num = row.get("case_number")
    if num:
        bits.append("Case no.: " + str(num) + (f"/{row['case_year']}" if row.get("case_year") else ""))
    if row.get("court_name"):
        bits.append(f"Court: {row['court_name']}")
    secs = cj.get("sections") or []
    if secs:
        acts = cj.get("acts") or []
        bits.append("Sections: " + ", ".join(str(s) for s in secs)
                    + (f" ({'; '.join(str(a) for a in acts)})" if acts else ""))
    if row.get("stage"):
        bits.append(f"Stage: {row['stage']}")
    if not bits:
        return ""
    return "[From this matter's file in Headnote]\n" + "\n".join(bits)


# ---------------------------------------------------------------------------
# titles for the recent-drafts shelf
# ---------------------------------------------------------------------------
_TITLE_TRIM = re.compile(r"\s+")


def short_title(brief: str, fallback: str = "Draft", limit: int = 64) -> str:
    t = _TITLE_TRIM.sub(" ", (brief or "").strip())
    if not t:
        return fallback
    return (t[: limit - 1] + "…") if len(t) > limit else t
