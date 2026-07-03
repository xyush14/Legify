"""Regionalize a rendered Hindi draft into Marathi / Bengali / Gujarati.

Strategy (see the package docstring): render the Hindi document exactly as the
canonical template already does, then walk its visible text nodes and:
  * substitute any node found in the verified cache (deterministic, filing-grade
    once an advocate flips v=true);
  * for a miss (typically a client-typed fact), runtime-translate it if the LLM
    is reachable, else leave the Hindi untouched so nothing is silently dropped.

No per-language render functions, no template refactor: adding a language is a
JSON file, and the advocate feedback loop is pure data.
"""
from __future__ import annotations

import logging
import re

from headnote.drafter.i18n import cache as _cache

log = logging.getLogger(__name__)

_REGIONAL = {"mr", "bn", "gu"}

# A visible text node = text sitting directly between two tags. We deliberately
# skip nodes that are pure punctuation / dotted placeholders.
_NODE_RX = re.compile(r">([^<>]+)<")
_SKIP_RX = re.compile(r"^[.…\s:—/()]+$")


def _worth_translating(src: str) -> bool:
    """A cache MISS is only sent to the LLM when it looks like substantive
    client prose — not an unfilled placeholder, a bracketed AI hint, or a short
    label. Boilerplate/labels live in the cache; a short miss is almost always
    an empty field, so translating it just burns a call to echo Hindi back."""
    s = src.strip()
    if s.startswith("[") or s.startswith("("):     # AI-hint / placeholder text
        return False
    if len(s) < 20:                                # labels, single words, dots
        return False
    return " " in s                                # real prose has spaces


def is_regional(lang: str) -> bool:
    return lang in _REGIONAL


def _visible_nodes(html: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _NODE_RX.finditer(html):
        s = m.group(1).strip()
        if not s or s in seen or _SKIP_RX.match(s):
            continue
        seen.add(s)
        out.append(s)
    return out


def _replace_node(html: str, src: str, tgt: str) -> str:
    """Replace `src` only where it is a full text node (bounded by > and <),
    preserving the original surrounding whitespace. Substring matches inside a
    longer node are never touched."""
    pat = re.compile(r"(>)(\s*)" + re.escape(src) + r"(\s*)(<)")
    return pat.sub(lambda m: f"{m.group(1)}{m.group(2)}{tgt}{m.group(3)}{m.group(4)}", html)


def regionalize(html: str, lang: str, *, translate_missing: bool = True) -> tuple[str, dict]:
    """Return (regionalized_html, report).

    report = {lang, nodes, hit, translated, missed, verified} — `verified` is
    True only if every substituted node came from an advocate-verified entry.
    """
    report = {"lang": lang, "nodes": 0, "hit": 0, "translated": 0,
              "missed": 0, "verified": True}
    if lang not in _REGIONAL or not html:
        return html, report

    nodes = _visible_nodes(html)
    report["nodes"] = len(nodes)

    # Pass 1 — substitute everything in the verified cache (deterministic, free).
    misses: list[str] = []
    for src in nodes:
        hit = _cache.lookup(src, lang)
        if hit is not None:
            tgt, verified = hit
            if tgt and tgt != src:
                html = _replace_node(html, src, tgt)
            report["hit"] += 1
            report["verified"] = report["verified"] and verified
        elif translate_missing and _worth_translating(src):
            misses.append(src)
        else:
            report["missed"] += 1

    # Pass 2 — translate all remaining prose in ONE batched LLM call (a whole
    # uncached document is ~dozens of nodes; sequential calls would be unusably
    # slow). Any node here is machine output, so the doc is not "verified".
    if misses:
        report["verified"] = False
        try:
            from headnote.drafter.i18n.engine import translate_batch
            outs = translate_batch(misses, lang, source_lang="hi", mode="boilerplate")
            for src, tgt in zip(misses, outs):
                if tgt and tgt != src:
                    html = _replace_node(html, src, tgt)
                    report["translated"] += 1
                else:
                    report["missed"] += 1
        except Exception as e:  # LLM unreachable / no key — degrade gracefully
            log.warning("[i18n] batch translate failed (%s): %s", lang, str(e)[:120])
            report["missed"] += len(misses)

    return html, report
