"""Translation engine for regional-language drafts.

Design goals
------------
* BEST QUALITY on court boilerplate: force the DEEP model (R1 reasoner via the
  existing router), inject the court-term glossary, and forbid drift on
  citations / section numbers / HTML structure. This runs OFFLINE once per
  string; the reviewed output is cached, so runtime pays nothing.
* SAFE runtime fact translation: the lawyer may type facts in English while the
  draft is in Marathi/Bengali/Gujarati. Proper nouns (names, police stations,
  places) are TRANSLITERATED into the target script; the surrounding prose is
  translated into formal court register; citations/sections/dates are preserved.

All model access goes through the existing `headnote.llm.router.route_call`
("translation" task) so provider routing, DeepSeek/Groq fallback and the cost
meter are inherited unchanged. `force_model="opus"` maps to DeepSeek-reasoner
(R1) under the production LLM_PROVIDER=deepseek config — i.e. the deep path.
"""
from __future__ import annotations

import logging
import re

from headnote.drafter.i18n import glossary as _glossary

log = logging.getLogger(__name__)

SUPPORTED_LANGS: dict[str, str] = {
    "mr": "Marathi",
    "bn": "Bengali",
    "gu": "Gujarati",
    # hi/en are the source languages the templates already render natively.
    "hi": "Hindi",
    "en": "English",
}

# State each regional language files in — used to anchor the court register.
_JURISDICTION = {
    "mr": "a Maharashtra District / High Court",
    "bn": "a West Bengal District / High Court",
    "gu": "a Gujarat District / High Court",
}

# Tokens the translator must NEVER alter. Statute short-forms in both scripts,
# the roman-digit section refs, and inline HTML placeholders.
_PRESERVE_NOTE = (
    "Keep these UNCHANGED (do not translate, do not transliterate): all HTML "
    "tags and attributes; section/crime/case numbers and every digit; dates; "
    "statute short-forms (IPC, BNS, CrPC, BNSS, NI Act, भा.द.वि., दं.प्र.सं., "
    "बी.एन.एस.एस.); and any case citation (party names + reporter + year)."
)


def _lang_name(code: str) -> str:
    name = SUPPORTED_LANGS.get(code)
    if not name:
        raise ValueError(f"Unsupported target language {code!r}. "
                         f"Known: {sorted(SUPPORTED_LANGS)}")
    return name


def _glossary_block(lang: str) -> str:
    lines = _glossary.glossary_lines(lang)
    if not lines:
        return ""
    body = "\n".join(lines)
    return (
        "\nCOURT-TERM GLOSSARY — use these exact renderings wherever the "
        "source term appears (they are the court-correct forms for this "
        f"jurisdiction; do not substitute synonyms):\n{body}\n"
    )


def _system_prompt(target_lang: str, *, mode: str) -> str:
    tgt = _lang_name(target_lang)
    where = _JURISDICTION.get(target_lang, f"a {tgt}-language court")
    base = (
        f"You are a senior Indian court draftsman. You translate litigation "
        f"text into {tgt} (Devanagari/native script) in the FORMAL court "
        f"register used in filed applications before {where} — never casual, "
        f"never colloquial, never transliterated Hinglish.\n"
        f"{_PRESERVE_NOTE}\n"
        f"{_glossary_block(target_lang)}"
    )
    if target_lang == "mr":
        # Hindi and Marathi share Devanagari, so models tend to leave Hindi
        # postpositions/connectors and Act names untranslated — producing a
        # Hindi-Marathi hybrid. Force full conversion.
        base += (
            "\nCRITICAL: The source is Hindi and Marathi shares its script, so it "
            "is tempting to leave Hindi words unchanged. Do NOT. Convert EVERY "
            "Hindi word into its Marathi equivalent — especially postpositions and "
            "connectors: द्वारा→यांनी, के/का/की→(चा/ची/चे), को→ला/स, से→पासून/वरून, "
            "में→मध्ये/त, के तहत→नुसार, अन्तर्गत→अन्वये, एवं→व, है→आहे, गया→गेला, "
            "किया→केला, हेतु→साठी. Translate Act names too: दहेज प्रतिषेध अधिनियम→हुंडा "
            "प्रतिबंध अधिनियम, घरेलू हिंसा→घरगुती हिंसाचार. The result must read as "
            "natural Marathi a Maharashtra advocate would file — ZERO Hindi words left."
        )
    if target_lang == "bn":
        # Bengali is a different script, so the risk is not leftover Hindi but
        # wrong legal register / anglicised terms. Anchor formal court Bengali.
        base += (
            "\nWrite in the FORMAL court Bengali (সাধু/formal register) used in "
            "West Bengal court filings — not spoken/colloquial Bengali. Use proper "
            "Bengali legal terms: section→ধারা, applicant→আবেদনকারী, accused→অভিযুক্ত, "
            "complainant→অভিযোগকারী, offence→অপরাধ, investigation→তদন্ত, "
            "charge-sheet→অভিযোগপত্র, prayer→প্রার্থনা, discharge→অব্যাহতি. Translate "
            "Act names into Bengali (e.g. Dowry Prohibition Act→যৌতুক নিষেধ আইন). "
            "Do NOT leave Hindi or English words in the body (statute short-forms and "
            "citations excepted). The applicant is the ACCUSED — never render them as "
            "the complainant."
        )
    if mode == "facts":
        base += (
            "\nThe input is a lawyer's FACTUAL NARRATIVE. TRANSLITERATE every "
            "proper noun — names of persons, police stations, villages, towns, "
            "courts — into the target script (do NOT translate them into a "
            "meaning). Translate only the surrounding description into formal "
            f"{tgt} legal prose."
        )
    else:  # boilerplate
        base += (
            "\nThe input is fixed court BOILERPLATE. Preserve its exact legal "
            "meaning and formality. Do not add, drop, soften or embellish any "
            "clause."
        )
    base += "\nOutput ONLY the translated text (same HTML structure if HTML was given). No preamble, no notes, no explanation."
    return base


def _clean(out: str) -> str:
    """Strip any stray fences/preamble a model might add despite instructions."""
    t = out.strip()
    if t.startswith("```"):
        t = "\n".join(t.split("\n")[1:])
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


# Translation backend, via I18N_MT_PROVIDER:
#   "sarvam"   — Sarvam AI, Indic-native + formal/legal mode (best output; paid, cheap)
#   "bhashini" — Govt. of India NMT (free)
#   "llm"      — DeepSeek/Claude via the router (instructable + glossary)
# Whatever is chosen, the LLM is the automatic fallback (I18N_MT_FALLBACK_LLM).
import os as _os


def _mt_provider() -> str:
    # Default = "llm": LLM + glossary beat raw NMT (Sarvam/Bhashini) head-to-head
    # on legal register + party roles (2026-07-03 bake-off). NMT stays available
    # via env for the cheap runtime-facts path or a future re-test.
    return _os.environ.get("I18N_MT_PROVIDER", "llm").strip().lower()


def _fallback_to_llm() -> bool:
    return _os.environ.get("I18N_MT_FALLBACK_LLM", "1").strip() not in ("0", "false", "no", "")


def _translate_via_llm(text: str, target_lang: str, source_lang: str,
                       mode: str, deep: bool) -> str:
    # Local import so importing the package never hard-requires the LLM stack.
    from headnote.llm.router import route_call
    src = _lang_name(source_lang)
    payload = {
        "system_prompt": _system_prompt(target_lang, mode=mode),
        "user_prompt": f"Translate this {src} text:\n\n{text}",
        "cache": True,
    }
    result = route_call("translation", payload,
                        force_model="opus" if deep else "haiku")
    return _clean(result.response)


def translate_segment(
    text: str,
    target_lang: str,
    *,
    source_lang: str = "hi",
    mode: str = "boilerplate",
    deep: bool = True,
) -> str:
    """Translate a single string/segment.

    Backend is Bhashini by default (see _mt_provider); it masks preserved tokens
    (citations / section numbers / statute short-forms) itself. `mode`/`deep`
    only apply to the LLM path — Bhashini is plain NMT.
    Returns the input unchanged if blank or target == source.
    """
    if not text or not text.strip() or target_lang == source_lang:
        return text
    _lang_name(target_lang)  # validates

    provider = _mt_provider()
    if provider == "sarvam":
        from headnote.drafter.i18n import sarvam
        try:
            return sarvam.translate(text, source_lang, target_lang)
        except sarvam.SarvamError as e:
            if not _fallback_to_llm():
                raise
            log.warning("[i18n] Sarvam failed, falling back to LLM: %s", str(e)[:160])
    elif provider == "bhashini":
        from headnote.drafter.i18n import bhashini
        try:
            return bhashini.translate(text, source_lang, target_lang)
        except bhashini.BhashiniError as e:
            if not _fallback_to_llm():
                raise
            log.warning("[i18n] Bhashini failed, falling back to LLM: %s", str(e)[:160])

    return _translate_via_llm(text, target_lang, source_lang, mode, deep)


# Match a rendered-template block: everything between the outer <div ...> and
# the final </div>. We translate the inner text nodes only, leaving tags intact
# by handing the whole HTML to the model with a preserve-tags instruction.
def translate_document_html(
    html: str,
    target_lang: str,
    *,
    source_lang: str = "hi",
    deep: bool = True,
) -> str:
    """Whole-document path: translate a rendered Hindi/English draft's visible
    text into `target_lang`, preserving every HTML tag and the preserved-token
    set. Use for the fast prototype / preview; the production path prefers the
    cached per-string boilerplate + runtime fact translation for determinism.
    """
    if not html or not html.strip() or target_lang == source_lang:
        return html
    return translate_segment(
        html, target_lang,
        source_lang=source_lang, mode="boilerplate", deep=deep,
    )


def translate_batch(
    texts: list[str],
    target_lang: str,
    *,
    source_lang: str = "hi",
    mode: str = "boilerplate",
    deep: bool = False,
) -> list[str]:
    """Translate many segments in ONE LLM call — essential for regionalizing a
    whole uncached document without firing N sequential requests. Returns a list
    aligned to `texts`; any segment that can't be matched back falls to its
    original (never dropped). NMT backends don't batch, so they loop per item.
    """
    items = [t for t in texts if t and t.strip()]
    if not items or target_lang == source_lang:
        return list(texts)
    _lang_name(target_lang)

    provider = _mt_provider()
    # NMT engines have no batch API — translate item by item (they're fast).
    if provider in ("sarvam", "bhashini"):
        return [translate_segment(t, target_lang, source_lang=source_lang, mode=mode)
                for t in texts]

    # LLM: one call, numbered in / numbered out.
    from headnote.llm.router import route_call
    src = _lang_name(source_lang)
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(items))
    sys_prompt = _system_prompt(target_lang, mode=mode) + (
        "\n\nYou are given a NUMBERED list of segments. Translate EACH one and "
        "return the SAME numbering, one per line, as `<n>. <translation>` — same "
        "count, same order, nothing else."
    )
    result = route_call("translation",
                        {"system_prompt": sys_prompt,
                         "user_prompt": f"Translate each {src} segment:\n\n{numbered}",
                         "cache": True},
                        force_model="opus" if deep else "haiku")
    # Parse "<n>. <text>" lines back into a map.
    out_map: dict[int, str] = {}
    for line in _clean(result.response).splitlines():
        m = re.match(r"\s*(\d+)\.\s*(.+)$", line)
        if m:
            out_map[int(m.group(1))] = m.group(2).strip()
    translated = {items[i]: out_map[i + 1] for i in range(len(items)) if (i + 1) in out_map}
    return [translated.get(t, t) for t in texts]


def translate_facts(
    text: str,
    target_lang: str,
    *,
    source_lang: str = "en",
    deep: bool = False,
) -> str:
    """Runtime path: translate the lawyer's factual narrative (default from
    English) into the draft's regional language, transliterating proper nouns.
    Defaults to the fast model — facts are lower-stakes than boilerplate and
    this runs in the request path.
    """
    return translate_segment(
        text, target_lang,
        source_lang=source_lang, mode="facts", deep=deep,
    )
