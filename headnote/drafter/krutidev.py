"""Kruti Dev 010 → Unicode decoding, and a FONT-AWARE .docx text extractor.

Why this exists (the Draft DNA foundation, "Stage 0"):
    Most MP-district advocates file in the legacy **Kruti Dev 010** font. That
    font is NOT Unicode — it stores ordinary ASCII bytes that only *look* like
    Devanagari when rendered in the Kruti Dev typeface. Reading such a .docx
    with python-docx yields gibberish like ``;g fd`` which actually means
    ``यह कि``. If we feed that gibberish to the style analyst, Draft DNA learns
    nothing. So before we can learn an advocate's manner, we must recover REAL
    Unicode text from their real files.

The trap this module is built around:
    ``convert()`` must run ONLY on runs that are actually Kruti Dev. Running it
    on text that is already Unicode Devanagari (e.g. a Mangal .docx) CORRUPTS
    the correct text. So decoding is decided **per run, by the run's font** —
    never blanket over a whole document.

The 85-pair decode table below is the proven converter from
``scripts/kruti_to_unicode.py`` (kept as the offline CLI); this is its runtime
home so ingest can import it. Keep the two in sync if the table is edited.
"""
from __future__ import annotations

import io
import re

# ---------------------------------------------------------------------------
# Decode table — Kruti Dev 010 → Unicode. Order matters (longer sequences
# before the single chars they contain). Mirrors scripts/kruti_to_unicode.py.
# ---------------------------------------------------------------------------
PAIRS: list[tuple[str, str]] = [
    ("”", "'"), ("“", "'"), ("’", "'"), ("‘", "'"),
    (")", "द्ध"), (":", "रु"),
    ("Ø", "क्र"), ("æ", "क्र"), ("ø", "क्र"), ("=", "त्र"), ("Ý", "द्र"),
    ("™", "त्त"), ("¶", "फ़"),
    ("¼", "("), ("½", ")"), ("¡", "ँ"),
    ("vkS", "औ"), ("vks", "ओ"), ("vk", "आ"), ("bZ", "ई"), (",s", "ऐ"),
    ("{k", "क्ष"), ("'k", "श"), ('"k', "ष"), ("[k", "ख"), ("Fk", "थ"),
    ("Hk", "भ"), ("?k", "घ"), ("/k", "ध"), (".k", "ण"), ("ks", "ो"),
    ("kS", "ौ"),
    ("D", "क्"), ("X", "ग्"), ("P", "च्"), ("T", "ज्"), ("F", "थ्"),
    ("U", "न्"), ("I", "प्"), ("C", "ब्"), ("H", "भ्"), ("E", "म्"),
    ("Y", "ल्"), ("O", "व्"), ("L", "स्"), ("R", "त्"), ("'", "श्"),
    ('"', "ष्"), (".", "ण्"), ("[", "ख्"), ("/", "ध्"), ("{", "क्ष्"),
    ("?", "घ्"), ("J", "श्र"),
    ("d", "क"), ("x", "ग"), ("p", "च"), ("t", "ज"), ("V", "ट"),
    ("B", "ठ"), ("M", "ड"), ("<", "ढ"), ("r", "त"), ("n", "द"),
    ("u", "न"), ("i", "प"), ("Q", "फ"), ("c", "ब"), ("e", "म"),
    (";", "य"), ("j", "र"), ("y", "ल"), ("o", "व"), ("l", "स"),
    ("g", "ह"), ("N", "छ"), ("K", "ज्ञ"), (">", "झ"), ("z", "्र"),
    ("v", "अ"), ("b", "इ"), ("m", "उ"), ("Å", "ऊ"), (",", "ए"), ("_", "ऋ"),
    ("k", "ा"), ("h", "ी"), ("q", "ु"), ("w", "ू"), ("s", "े"),
    ("S", "ै"), ("`", "ृ"), ("a", "ं"), ("f", "ि"),
    ("W", "ँ"),
    ("~", "्"), ("A", "।"), ("|", "॥"), ("]", ","), ("@", "/"),
    ("}", "द्व"), ("%", "ः"), ("&", "—"),
]

_CONS = "कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहड़ढ़फ़ज़"
_MATRAS = "ािीुूृेैोौंःँ"
_IRE = re.compile("ि((?:[%s]्)*[%s])" % (_CONS, _CONS))
_ZRE = re.compile("([%s])([%s]*)Z" % (_CONS, _MATRAS))
_NRE = re.compile("ं([ािीुूृेैोौ])")


def convert(s: str) -> str:
    """Decode a Kruti Dev 010 string to Unicode Devanagari."""
    if not s:
        return s
    for a, b in PAIRS:
        s = s.replace(a, b)
    s = _ZRE.sub(lambda m: "र्" + m.group(1) + m.group(2), s)
    s = _IRE.sub(r"\1ि", s)
    s = _NRE.sub(r"\1ं", s)
    return s


# ---------------------------------------------------------------------------
# Encode — Unicode Devanagari → Kruti Dev 010 (the inverse of convert()).
#
# Needed to OUTPUT drafts in the advocate's own Kruti Dev font. Built by
# inverting the decode PAIRS into one Unicode→KD map, applied with a SINGLE-PASS
# longest-match tokenizer — sequential str.replace would CASCADE (an inserted KD
# glyph like "/" is itself a Unicode key that a later pass would re-map). The
# three reorderings convert() applies are inverted first, in the order
# (short-i, anusvara, reph) — verified 100% round-trip on real filed drafts.
# ---------------------------------------------------------------------------
def _build_encode_map() -> dict:
    seen: dict[str, str] = {}
    for kd_glyph, uni in PAIRS:
        # skip the smart-quote normalisations (all map TO an apostrophe); keep
        # the FIRST kd glyph seen per Unicode (the standard KD010 key).
        if not uni or uni == "'" or uni in seen:
            continue
        seen[uni] = kd_glyph
    return seen


_ENCODE_MAP = _build_encode_map()
_ENCODE_MAXLEN = max((len(u) for u in _ENCODE_MAP), default=1)

_ENC_SHORT_I = re.compile("((?:[%s]्)*[%s])ि" % (_CONS, _CONS))   # ि after cluster → before
_ENC_ANUSVARA = re.compile("([ािीुूृेैोौ])ं")                     # matra+ं → ं+matra
_ENC_REPH = re.compile("र्([%s])([%s]*)" % (_CONS, _MATRAS))      # र्C(m) → C(m)Z


def to_krutidev(s: str) -> str:
    """Encode Unicode Devanagari to Kruti Dev 010 — the inverse of convert().
    Round-trips 100% on real filed drafts: convert(to_krutidev(x)) == x. Used
    to emit generated content in the advocate's own Kruti Dev font."""
    if not s:
        return s
    s = _ENC_SHORT_I.sub(r"ि\1", s)     # undo _IRE (short-i) — BEFORE anusvara
    s = _ENC_ANUSVARA.sub(r"ं\1", s)    # undo _NRE (anusvara)
    s = _ENC_REPH.sub(r"\1\2Z", s)      # undo _ZRE (reph)
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        hit = None
        for L in range(min(_ENCODE_MAXLEN, n - i), 0, -1):
            g = _ENCODE_MAP.get(s[i:i + L])
            if g is not None:
                hit = (L, g)
                break
        if hit:
            out.append(hit[1])
            i += hit[0]
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _compute_unsafe_chars() -> frozenset:
    """Characters that must NOT be placed in a Kruti Dev run.

    Derived from the mapping table itself (not hand-listed, so it stays correct
    if the table changes): a character is unsafe when the encoder leaves it
    unchanged (nothing to map it to) BUT the font reinterprets it — e.g. ASCII
    ':' would draw as 'रु' and 'IPC' as 'प्च्ब्'. Digits, spaces and hyphens are
    safe (they render as themselves, exactly as in real filed drafts).
    """
    import string
    candidates = string.printable[:95] + "—–ः।॥“”‘’…"
    return frozenset(c for c in candidates if to_krutidev(c) == c and convert(c) != c)


UNSAFE_IN_KRUTIDEV = _compute_unsafe_chars()


# ---------------------------------------------------------------------------
# Detection — is a given run Kruti Dev?
# ---------------------------------------------------------------------------
# Legacy Devanagari ASCII-mapped fonts. Matched case-insensitively as a prefix
# so "Kruti Dev 010", "KrutiDev010", "DevLys 010" etc. all resolve.
_KRUTIDEV_FONT_HINTS = ("kruti", "krutidev", "devlys", "dev lys", "richa", "agra")


def is_krutidev_font(font_name: str | None) -> bool:
    """True if a run's declared font is a known legacy ASCII-Devanagari font."""
    if not font_name:
        return False
    n = font_name.strip().lower()
    return any(h in n for h in _KRUTIDEV_FONT_HINTS)


# When the font is unknown (e.g. a PDF text layer with no font metadata), fall
# back to a content heuristic: Kruti-Dev gibberish is Latin-heavy with the
# tell-tale ASCII-Devanagari punctuation the encoding relies on, and carries
# essentially no real Devanagari codepoints.
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_KRUTI_TELLS = re.compile(r"[;\[\]{}<>~^`|]")


def looks_like_krutidev(text: str) -> bool:
    """Heuristic for text whose font is unknown. Conservative: only True when
    the text has real Latin content, almost no Devanagari, AND the Kruti-Dev
    tell-tale punctuation density is high — so plain English is NOT flagged."""
    if not text:
        return False
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 8:
        return False
    deva = len(_DEVANAGARI.findall(text))
    if deva > len(text) * 0.10:          # already substantially Devanagari → not KD
        return False
    latin = sum(1 for c in letters if "a" <= c.lower() <= "z")
    if latin < len(letters) * 0.6:       # not Latin-dominant → not KD gibberish
        return False
    tells = len(_KRUTI_TELLS.findall(text))
    return tells >= max(2, len(text) // 40)


# ---------------------------------------------------------------------------
# Font-aware .docx extraction — decode ONLY the Kruti Dev runs.
# ---------------------------------------------------------------------------
def _run_font(run) -> str | None:
    """The run's effective font name, reading both the high-level property and
    the raw rFonts (ascii/cs/hAnsi) so we catch Devanagari-only 'cs' fonts."""
    try:
        name = run.font.name
        if name:
            return name
    except Exception:
        pass
    try:
        rpr = run._element.rPr
        if rpr is not None:
            rfonts = rpr.rFonts
            if rfonts is not None:
                for attr in ("ascii", "cs", "hAnsi"):
                    v = rfonts.get(
                        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}" + attr
                    )
                    if v:
                        return v
    except Exception:
        pass
    return None


def _decode_paragraph(paragraph) -> str:
    """Rebuild a paragraph's text, decoding runs whose font is Kruti Dev.

    CRITICAL: Word splits a paragraph into runs at arbitrary points — often in
    the MIDDLE of a multi-byte Kruti Dev sequence (e.g. "le{" | "k" for क्ष).
    Decoding each run alone would break those sequences and produce artefacts,
    so we CONCATENATE consecutive Kruti runs and decode the joined text as one.
    Non-Kruti (Unicode/English) runs flush the buffer and pass through intact,
    so mixed-font paragraphs are still handled without corruption.
    """
    out: list[str] = []
    kbuf: list[str] = []

    def flush():
        if kbuf:
            out.append(convert("".join(kbuf)))
            kbuf.clear()

    # A paragraph that has ANY explicitly Kruti-Dev run is a Kruti Dev paragraph;
    # runs without font metadata inside it INHERIT that font. Without this, Word
    # splitting a word into "le{" + "k" (second run font-less, too short for the
    # content heuristic) would break the multi-byte sequence and reintroduce the
    # mojibake artefact.
    para_is_kd = any(is_krutidev_font(_run_font(r)) for r in paragraph.runs if r.text)

    any_run = False
    for run in paragraph.runs:
        t = run.text
        if not t:
            continue
        any_run = True
        font = _run_font(run)
        if is_krutidev_font(font) or (font is None and (para_is_kd or looks_like_krutidev(t))):
            kbuf.append(t)
        else:
            flush()
            out.append(t)
    flush()
    if not any_run and paragraph.text:
        # no run objects (rare) — decide on the whole-paragraph text
        return convert(paragraph.text) if looks_like_krutidev(paragraph.text) else paragraph.text
    return "".join(out)


def extract_docx_fontaware(data: bytes | str) -> str:
    """Read a .docx into Unicode text, decoding only the Kruti Dev runs and
    leaving Unicode (Mangal/Nirmala/etc.) runs untouched. `data` is raw bytes
    or a path. Paragraphs and table cells are returned in document order.

    This is the drop-in replacement for the font-blind text pull in
    office._extract_docx for the Draft DNA ingest path.
    """
    from docx import Document

    doc = Document(io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data)
    lines: list[str] = []
    for para in doc.paragraphs:
        lines.append(_decode_paragraph(para))
    for table in doc.tables:
        for row in table.rows:
            cells = [_decode_paragraph_in_cell(c) for c in row.cells]
            joined = " | ".join(x for x in cells if x.strip())
            if joined.strip():
                lines.append(joined)
    return "\n".join(l for l in lines if l is not None)


def _decode_paragraph_in_cell(cell) -> str:
    return "\n".join(_decode_paragraph(p) for p in cell.paragraphs)
