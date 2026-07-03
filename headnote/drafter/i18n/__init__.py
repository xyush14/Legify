"""Regional-language translation for Headnote drafts (Marathi / Bengali / Gujarati).

Two surfaces (see engine.py):
  * BOILERPLATE — the fixed court language in the templates. Translated ONCE,
    offline, with the deep model + legal glossary, then reviewed by a
    jurisdiction advocate and cached in verified strings files. Deterministic
    and zero-runtime-cost thereafter; keeps the "verbatim filed" moat intact.
  * FACTS — the lawyer's case-specific narrative (typed EN/HI), translated at
    render time into the target language. Proper nouns are transliterated, not
    translated; citations / section numbers / dates are preserved verbatim.
"""
from headnote.drafter.i18n.engine import (  # noqa: F401
    SUPPORTED_LANGS,
    translate_segment,
    translate_document_html,
    translate_facts,
)
from headnote.drafter.i18n.render import regionalize, is_regional  # noqa: F401
