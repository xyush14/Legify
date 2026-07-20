"""Draft DNA — per-advocate drafting personalization.

The single source of truth for an advocate's stored *style* (their numbering
idiom, prayer/verification framing, signature block, a short human-readable
style description and 2–3 anonymised exemplars) and for how that style is
applied at draft time.

Design contract (docs/DRAFT_DNA_DESIGN.md):
  • FORMAT is ENFORCED — a deterministic post-render pass (`apply_format`)
    rewrites the boilerplate to the advocate's own tokens, on every path.
  • VOICE is STEERED — the style prose + exemplars go into the authoring prompt
    (`overlay_block` / `exemplar_block`); best-effort, LLM paths only.
  • FACTS are never learned or reused. DNA lives entirely on the *format* side
    of the two-source rule — never a fact source. The grounding guard in
    render_authored is untouched (source stays = the advocate's matter).

Regression safety (§7): every prompt slot DEFAULTS to today's exact literal, so
with no DNA (`style=None`) the assembled prompt and rendered HTML are byte-for-
byte identical to today. `apply_format(html, None)` is the identity function.

Storage: one `draft_style` jsonb column on public.user_profiles (extract-then-
discard — we persist only the distilled profile, never the uploaded files).
See migrations/010_draft_dna.sql.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger("headnote.drafter.style")


# ===========================================================================
# Defaults — the exact house-style literals these slots replace. Keeping them
# here (not inline in the prompt) makes style_profile the single source of
# truth: `_author_system(style=None)` fills the slots from FORMAT_DEFAULTS, so
# the default prompt is character-identical to the pre-refactor prompt.
# ===========================================================================
FORMAT_DEFAULTS = {
    "para_prefix":  "यह कि",
    "closer":       "यह कि, अन्य तर्क वक्त बहस मौखिक रुप से निवेदित किये जावेंगे।",
    "prayer_open":  "अतः श्रीमान न्यायालय से प्रार्थना है कि",
    "prayer_close": "… करने की कृपा करें।",
}

# The slots we expose to the authoring prompt (Mechanism 1). Kept to the four
# load-bearing, low-risk boilerplate literals — party labels/font are handled
# per-matter (JSON labels) or deterministically (apply_format), not in the prompt.
_PROMPT_SLOTS = ("para_prefix", "closer", "prayer_open", "prayer_close")

# How many exemplars we ever inject / store (cost + prompt-bloat cap).
_MAX_EXEMPLARS = 3


def _fmt(style: Optional[dict]) -> dict:
    """The `format` sub-dict of a StyleProfile, or {} — tolerant of shape."""
    if not isinstance(style, dict):
        return {}
    f = style.get("format")
    return f if isinstance(f, dict) else {}


def _slot(style: Optional[dict], key: str) -> str:
    """A format slot's value: the advocate's override when set + non-blank,
    else today's default literal."""
    v = (_fmt(style).get(key) or "").strip()
    return v or FORMAT_DEFAULTS[key]


# ===========================================================================
# Mechanism 1 — prompt parameterization (steers voice; authored path)
# ===========================================================================
def format_slots(style: Optional[dict]) -> dict:
    """The four prompt slots, filled from the profile or defaulted. With
    `style=None` this returns FORMAT_DEFAULTS verbatim → byte-identical prompt."""
    return {k: _slot(style, k) for k in _PROMPT_SLOTS}


def overlay_block(style: Optional[dict], lang: str = "hi") -> str:
    """A short, human-readable STYLE OVERLAY prepended to the system prompt when
    the advocate has DNA. Empty string with no style → the default prompt is
    untouched (we PREPEND, never leave a stray blank line, exactly like the
    CIVIL_NOTE / SPECIMEN injection). Prose only — no facts."""
    if not isinstance(style, dict):
        return ""
    prose = (style.get("style_prose") or "").strip()
    directives = [d for d in (style.get("directives") or []) if isinstance(d, dict)]
    if not prose and not directives:
        return ""
    lines = [
        "THIS ADVOCATE'S HOUSE STYLE (learned from their own filed drafts — match the "
        "register, ordering and phrasing; this steers VOICE only, never facts):",
    ]
    if prose:
        lines.append(f"• {prose}")
    for d in directives[:6]:
        k = str(d.get("key") or "").strip()
        v = str(d.get("value") or "").strip()
        if k and v:
            lines.append(f"• {k}: {v}")
    return "\n".join(lines) + "\n\n"


def exemplar_block(style: Optional[dict], doc_type: str = "", lang: str = "hi") -> str:
    """2–3 of the advocate's own paragraphs, appended to the USER prompt as
    few-shot 'this is how they wrote a similar ground'. Prefers exemplars whose
    doc_type matches; falls back to any. FORMAT/VOICE samples only — the model
    is told never to reuse their facts. Empty when no exemplars."""
    if not isinstance(style, dict):
        return ""
    ex = [e for e in (style.get("exemplars") or []) if isinstance(e, dict) and (e.get("text") or "").strip()]
    if not ex:
        return ""
    same = [e for e in ex if doc_type and e.get("doc_type") == doc_type]
    chosen = (same or ex)[:_MAX_EXEMPLARS]
    body = "\n".join(f"  — {(e.get('text') or '').strip()}" for e in chosen)
    return (
        "\n\nHOW THIS ADVOCATE PHRASES A PARAGRAPH (style samples from their own past "
        "drafts — imitate the CADENCE and REGISTER only; the facts here belong to other "
        "matters and MUST NOT appear in this draft):\n" + body
    )


# ===========================================================================
# Mechanism 2 — deterministic format normalizer (guarantees format; all paths)
# ===========================================================================
def apply_format(html: str, style: Optional[dict], lang: str = "hi") -> str:
    """Rewrite the rendered house boilerplate to the advocate's own tokens.

    Deterministic and total: with `style=None` (or a profile whose fields all
    equal the defaults) it returns `html` unchanged — that is the regression
    guarantee. Any internal error returns the original html (a draft must never
    break because personalization mis-fired). Runs on the authored-path markup
    (cb-paras / cb-prayer / cb-sig); on other markup the targeted replacements
    simply find nothing and no-op.
    """
    if not html or not isinstance(style, dict):
        return html
    try:
        return _apply_format(html, style, lang)
    except Exception:  # never let format personalization break a draft
        log.warning("apply_format failed — returning unmodified draft", exc_info=True)
        return html


# leading paragraph prefix inside a numbered <li> (authored renderer emits <li>यह कि …)
_LI_PREFIX = re.compile(r"(<li>\s*)(यह\s*कि,?\s*)")
# the cb-prayer block the authored renderer emits: <div class="cb-prayer"><p>…</p></div>
_PRAYER_BLOCK = re.compile(r'(<div class="cb-prayer"><p>)(.*?)(</p></div>)', re.S)


def _strip_ellipsis(s: str) -> str:
    """Drop a leading ellipsis placeholder ('… ' / '...') — FORMAT_DEFAULTS carry
    it for the PROMPT (where '…' marks 'the specific relief goes here'), but the
    ellipsis never appears in the RENDERED prayer, so the matcher works on the tail."""
    return re.sub(r"^[\s….]+", "", s or "").strip()


def _apply_format(html: str, style: dict, lang: str) -> str:
    f = _fmt(style)
    hi = lang != "en"

    # ORDER MATTERS. The closer paragraph itself begins with the para prefix, so we
    # must swap the closer (and the prayer, and verification) — all exact/scoped
    # full-string matches — BEFORE the broad <li> prefix swap, or the prefix swap
    # would rewrite the closer's own opening words and break the exact match.

    # 1) closer line (the LLM writes it as the last ground para) — exact swap
    closer = (f.get("closer") or "").strip()
    if closer and closer != FORMAT_DEFAULTS["closer"]:
        html = html.replace(FORMAT_DEFAULTS["closer"], closer)

    # 2) prayer opener / closer — scoped to the cb-prayer block so the trailing
    #    "करने की कृपा करें।" can't collide with any body paragraph
    p_open = (f.get("prayer_open") or "").strip()
    p_close = (f.get("prayer_close") or "").strip()
    if (p_open and p_open != FORMAT_DEFAULTS["prayer_open"]) or \
       (p_close and p_close != FORMAT_DEFAULTS["prayer_close"]):
        html = _rewrite_prayer(html, p_open, p_close)

    # 3) verification (सत्यापन) — replace the default text with the advocate's own
    verification = (f.get("verification") or "").strip()
    if verification:
        from headnote.drafter.author import _DEFAULT_VERIFICATION, _DEFAULT_VERIFICATION_EN
        default_v = _DEFAULT_VERIFICATION if hi else _DEFAULT_VERIFICATION_EN
        html = html.replace(default_v, verification)

    # 4) advocate name in the signature block — the authored path leaves this a
    #    blank placeholder; the advocate's own name is standing info (format-side,
    #    not a client fact), so it is safe to fill from their DNA.
    block = [str(x).strip() for x in (f.get("advocate_block") or []) if str(x).strip()]
    if block:
        html = html.replace(
            '(<span class="ph">________</span>) — एडवोकेट',
            f'({_escape(block[0])}) — एडवोकेट',
        )

    # 5) paragraph prefix — LAST, and Hindi-only (English uses "That …"). Enforces
    #    the advocate's opener on every numbered para even if the LLM drifted to the
    #    default; also normalises the (now-custom) closer's opening words to match.
    prefix = (f.get("para_prefix") or "").strip()
    if hi and prefix and prefix != FORMAT_DEFAULTS["para_prefix"]:
        html = _LI_PREFIX.sub(lambda m: m.group(1) + prefix + " ", html)
    return html


def _rewrite_prayer(html: str, p_open: str, p_close: str) -> str:
    """Rewrite the prayer opener/closer inside the cb-prayer block only."""
    m = _PRAYER_BLOCK.search(html)
    if not m:
        return html
    inner = m.group(2)
    if p_open and p_open != FORMAT_DEFAULTS["prayer_open"]:
        inner = inner.replace(FORMAT_DEFAULTS["prayer_open"], p_open, 1)
    if p_close and p_close != FORMAT_DEFAULTS["prayer_close"]:
        dc, cc = _strip_ellipsis(FORMAT_DEFAULTS["prayer_close"]), _strip_ellipsis(p_close)
        idx = inner.rfind(dc) if dc else -1   # the prayer's TRAILING close
        if idx != -1:
            inner = inner[:idx] + cc + inner[idx + len(dc):]
    return html[:m.start()] + m.group(1) + inner + m.group(3) + html[m.end():]


def _escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ===========================================================================
# Extraction — uploaded drafts → a proposed StyleProfile (Phase 1)
# ===========================================================================
_ANALYST_SYSTEM = """You are a legal-drafting STYLE ANALYST for an Indian litigation tool. An advocate has
uploaded one or more of their OWN filed court drafts. Your job is to capture HOW THEY WRITE — their format,
framing and register — so future drafts can be produced in their exact style. You are NOT capturing the
facts of these drafts; ignore every specific name, date, amount, FIR/case number and address.

Study the drafts and return ONLY valid JSON (no prose, no markdown fence), in this exact shape:
{
  "format": {
    "para_prefix":  "<the exact opening words of each numbered paragraph, e.g. 'यह कि' / 'यहकि' / 'That'>",
    "closer":       "<the standard closing ground line before the prayer, verbatim; '' if none>",
    "prayer_open":  "<how the prayer OPENS, verbatim (the fixed words before the specific relief)>",
    "prayer_close": "<how the prayer CLOSES, verbatim>",
    "verification": "<their standard सत्यापन / verification sentence, verbatim, with any specific facts blanked to ____; '' if none>",
    "party_labels": {"applicant": "<आवेदक/प्रार्थी/वादी…>", "respondent": "<अनावेदक/प्रत्यर्थी/प्रतिवादी…>"},
    "font": "kruti_dev" | "devanagari" | "serif",
    "advocate_block": ["<advocate name as signed>", "<enrolment no. if shown>", "<bar council if shown>", "<chamber address if shown>"]
  },
  "style_prose": "<2-4 sentences an advocate could read and edit: their register, paragraph rhythm, ordering habits (e.g. parity-first in bail), phrasing tics. Plain description, no facts.>",
  "directives": [ {"key": "framing", "value": "<short rule, e.g. parity_first>"} ],
  "exemplars": [ {"doc_type": "<bail/discharge/plaint/… or ''>", "kind": "ground", "text": "<one representative numbered paragraph, VERBATIM in their words, but with every specific fact (names, dates, amounts, numbers, addresses) replaced by ____ >"} ]
}

Rules:
• Reproduce boilerplate (prefix, closer, prayer, verification) VERBATIM — it is the product.
• In exemplars and verification, BLANK every concrete fact to ____ — never carry a real name/date/amount forward.
• Give at most 3 exemplars, each a genuinely representative paragraph.
• If a field cannot be determined, use "" (or [] / a sensible default for font). Do not invent."""


def analyze_style(texts: list[str], lang: str = "hi") -> dict:
    """OCR'd text of 2–3 of the advocate's filed drafts → a proposed StyleProfile
    (unconfirmed). One LLM analyst pass (a stronger model — this is one-time),
    reinforced by a cheap regex heuristic for the paragraph prefix (the single
    most reliable signal). Never raises: returns a defaulted profile on failure
    so the UI can still show something to confirm/edit.

    IMPORTANT: the caller extracts-then-discards — only the returned profile is
    persisted, never `texts`.
    """
    joined = "\n\n---\n\n".join(t.strip() for t in texts if (t or "").strip())
    joined = joined[:24000]  # cap — one-time call, but keep it bounded
    profile = _empty_profile()
    if not joined:
        return profile

    # LLM analyst pass
    try:
        from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
        from headnote import config
        raw, _meta = _call_deepseek_or_groq(
            _ANALYST_SYSTEM,
            f"THE ADVOCATE'S DRAFTS:\n{joined}\n\nAnalyse the style and return the JSON.",
            max_tokens=4000,
            claude_model=config.DRAFTER_AUTHOR_MODEL,
            json_mode=True,
        )
        parsed = parse_json_response(raw)
        if isinstance(parsed, dict):
            profile = _merge_profile(profile, parsed)
    except Exception:
        log.warning("analyze_style LLM pass failed — falling back to heuristics", exc_info=True)

    # Heuristic reinforcement — the paragraph prefix is the most reliable signal
    heur_prefix = _detect_para_prefix(joined)
    if heur_prefix and not (profile["format"].get("para_prefix") or "").strip():
        profile["format"]["para_prefix"] = heur_prefix

    profile["source_meta"] = {
        "n_drafts": sum(1 for t in texts if (t or "").strip()),
        "confidence": {},
    }
    return profile


def _detect_para_prefix(text: str) -> str:
    """The most common numbered-paragraph opener in the advocate's drafts."""
    if re.search(r"यह\s*कि", text):
        # normalise to the spaced canonical form the renderer uses
        return "यह कि"
    if re.search(r"\bThat\b", text):
        return "That"
    return ""


def _empty_profile() -> dict:
    return {
        "format": {
            "para_prefix": "", "closer": "", "prayer_open": "", "prayer_close": "",
            "verification": "", "party_labels": {}, "font": "devanagari",
            "advocate_block": [],
        },
        "style_prose": "",
        "directives": [],
        "exemplars": [],
        "source_meta": {},
    }


def _merge_profile(base: dict, parsed: dict) -> dict:
    """Fold an LLM-parsed profile onto the empty skeleton, defensively — the LLM
    may omit or misshape fields."""
    pf = parsed.get("format") if isinstance(parsed.get("format"), dict) else {}
    for k in ("para_prefix", "closer", "prayer_open", "prayer_close", "verification", "font"):
        v = pf.get(k)
        if isinstance(v, str) and v.strip():
            base["format"][k] = v.strip()
    if isinstance(pf.get("party_labels"), dict):
        base["format"]["party_labels"] = {str(a): str(b) for a, b in pf["party_labels"].items() if b}
    if isinstance(pf.get("advocate_block"), list):
        base["format"]["advocate_block"] = [str(x).strip() for x in pf["advocate_block"] if str(x).strip()][:4]
    if isinstance(parsed.get("style_prose"), str):
        base["style_prose"] = parsed["style_prose"].strip()[:800]
    if isinstance(parsed.get("directives"), list):
        base["directives"] = [
            {"key": str(d.get("key") or "").strip(), "value": str(d.get("value") or "").strip()}
            for d in parsed["directives"] if isinstance(d, dict) and d.get("key") and d.get("value")
        ][:8]
    if isinstance(parsed.get("exemplars"), list):
        base["exemplars"] = [
            {"doc_type": str(e.get("doc_type") or "").strip(),
             "kind": str(e.get("kind") or "ground").strip(),
             "text": str(e.get("text") or "").strip()}
            for e in parsed["exemplars"] if isinstance(e, dict) and (e.get("text") or "").strip()
        ][:_MAX_EXEMPLARS]
    return base


def sanitize_profile(profile: dict) -> dict:
    """Normalise a profile coming FROM the client (the confirm/edit UI) before we
    persist it — clamp shapes and lengths, drop junk. Tolerant: unknown keys are
    ignored, missing keys defaulted."""
    if not isinstance(profile, dict):
        return _empty_profile()
    out = _empty_profile()
    out = _merge_profile(out, profile)  # reuses the same defensive folding
    # source_meta passes through if present + sane
    sm = profile.get("source_meta")
    if isinstance(sm, dict):
        out["source_meta"] = {k: sm[k] for k in ("n_drafts", "extracted_at", "confidence") if k in sm}
    return out


# ===========================================================================
# Persistence — one jsonb column on user_profiles (Supabase)
# ===========================================================================
def load_style(user_id: Optional[str]) -> Optional[dict]:
    """Return the advocate's saved StyleProfile, or None if unset / anon / on any
    read error. None is the untouched status-quo path — callers treat it as
    'no personalization'."""
    if not user_id:
        return None
    try:
        from headnote.entitlements import _supabase
        rows = _supabase.select(
            "user_profiles",
            params={"id": f"eq.{user_id}", "select": "draft_style", "limit": "1"},
        )
    except Exception as e:
        log.warning("load_style read failed for %.8s: %s", user_id, e)
        return None
    if not rows:
        return None
    ds = rows[0].get("draft_style")
    if not isinstance(ds, dict):
        return None
    # a profile with nothing meaningful in it is the same as no profile
    if not _is_meaningful(ds):
        return None
    return ds


def save_style(user_id: str, profile: Optional[dict]) -> Optional[dict]:
    """Persist (or clear, when profile is None) the StyleProfile. Returns what was
    stored. Raises on a hard DB error so the API surfaces a 502."""
    from headnote.entitlements import _supabase
    payload = {"draft_style": sanitize_profile(profile) if profile is not None else None}
    _supabase.update("user_profiles", payload, params={"id": f"eq.{user_id}"})
    return payload["draft_style"]


def _is_meaningful(style: dict) -> bool:
    """True if the profile actually diverges from the house default — i.e. there
    is something to apply. A profile of all-defaults/empties is treated as None so
    it never engages the (regression-sensitive) personalization path needlessly."""
    f = _fmt(style)
    for k in _PROMPT_SLOTS:
        v = (f.get(k) or "").strip()
        if v and v != FORMAT_DEFAULTS[k]:
            return True
    if (f.get("verification") or "").strip():
        return True
    if [x for x in (f.get("advocate_block") or []) if str(x).strip()]:
        return True
    if (style.get("style_prose") or "").strip():
        return True
    if [d for d in (style.get("directives") or []) if isinstance(d, dict) and d.get("value")]:
        return True
    if [e for e in (style.get("exemplars") or []) if isinstance(e, dict) and (e.get("text") or "").strip()]:
        return True
    return False
