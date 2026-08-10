"""Document Lens — read any document faithfully, in any language, as a PDF.

Two jobs an advocate has that are really one job: *"I cannot read this."*

  * the page is handwritten, faded, or photographed badly
  * the page is in a language he does not work in

Same pipeline; only the last step differs. Five stages, three of them free:

    1. prepare   deterministic image conditioning        free   documents/prepare.py
    2. read      one vision call over all pages          ~Rs 0.07/page
    3. verify    garbage guard + citation extraction     free   i18n/citations.py
    4. translate optional, behind the citation gate      ~Rs 0.07/page
    5. render    HTML -> the existing WeasyPrint PDF     free   api/pdf.py

Engine choice was measured, not assumed (scripts/ocr_bakeoff.py). On a real
handwritten UP gang chart, Gemini recovered 8 of 9 table rows and 20/25 facts
where Sarvam Document Intelligence recovered 0 rows and 4-14/25 across runs, at
~1/7th the cost and 3x the speed. Preparation matters regardless of engine: it
moved Gemini from 14/25 to 20/25 on that page.

Nothing here trusts the model with a citation. Every case number, section, date
and figure is extracted from the source and checked against the translation; a
translation that loses one is rejected and retried, then surfaced as a flag
rather than shown as if it were sound.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

from headnote.documents.prepare import looks_like_garbage, prepare
from headnote.drafter.i18n import citations as cite

log = logging.getLogger(__name__)

MAX_PAGES = 12
MAX_BYTES = 25 * 1024 * 1024

# Everything a phone or a chamber PC can produce. Anything not listed is still
# attempted as an image — a refusal to try is worse than a clean failure.
IMAGE_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif",
               "image/bmp", "image/tiff", "image/heic", "image/heif"}
DOC_EXT = {".doc", ".docx", ".odt", ".rtf", ".txt", ".md"}

LANGS = {"en": "English", "hi": "Hindi", "mr": "Marathi", "gu": "Gujarati",
         "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "kn": "Kannada",
         "ml": "Malayalam", "or": "Odia", "pa": "Punjabi", "as": "Assamese",
         "ur": "Urdu"}

_READ_PROMPT = (
    "Transcribe this document EXACTLY as written, in its original language and script.\n"
    "Rules:\n"
    "- Reproduce every case number, section, statute name, date, name and figure "
    "character for character. Never correct, renumber or modernise them.\n"
    "- Preserve structure. Render a ruled table as a Markdown table with one row "
    "per row of the original; keep headings and numbered paragraphs as they are.\n"
    "- Where the original is genuinely illegible write [illegible] at that point. "
    "Never guess a name, number or date.\n"
    "- Do not translate, summarise, explain or add anything.\n"
    "Output only the transcription."
)

_TRANSLATE_SYSTEM = (
    "You translate Indian legal documents for a practising advocate. In order:\n"
    "1. Reproduce every case number, section number, statute name, date and figure "
    "EXACTLY as in the source. Never renumber, reformat or convert them.\n"
    "2. Use the register of an Indian court filing, not conversational prose.\n"
    "3. Transliterate proper nouns; never translate a person's or place's name.\n"
    "4. Never state as completed an act the source describes only as attempted or "
    "intended.\n"
    "5. Preserve the layout: a table stays a table, a numbered list stays numbered.\n"
    "6. Do not add, omit, explain or summarise. Keep [illegible] markers as they are.\n"
    "Output only the translation."
)


@dataclass
class LensResult:
    text: str = ""
    lang: str = ""
    pages: int = 0
    source_kind: str = ""          # "image" | "pdf" | "office"
    flags: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    translated_from: str = ""

    def as_dict(self) -> dict:
        return {"text": self.text, "lang": self.lang, "pages": self.pages,
                "source_kind": self.source_kind, "flags": self.flags,
                "citations": self.citations, "translated_from": self.translated_from}


class LensError(RuntimeError):
    """Something the user can act on — the message is shown to them verbatim."""


# --- stage 1: intake ----------------------------------------------------------
def _register_heif() -> None:
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except Exception:  # noqa: BLE001 — HEIC just won't decode; caller reports it
        log.debug("pillow_heif unavailable", exc_info=True)


def office_text(data: bytes, filename: str) -> str:
    """Pull text straight out of a Word/text file — no OCR, no model, no cost.

    A .docx already contains its text. Rasterising it to images and reading it
    back with a vision model would be slower, cost money and lose accuracy.
    """
    low = filename.lower()
    if low.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace")
    if low.endswith(".docx"):
        import docx  # python-docx

        d = docx.Document(io.BytesIO(data))
        out = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    out.append(" | ".join(cells))
        return "\n".join(x for x in out if x is not None).strip()
    raise LensError(
        "Old .doc files (Word 97-2003) can't be read directly. "
        "Open it in Word and save as .docx or PDF, then upload again."
    )


def intake(data: bytes, filename: str, mime: str) -> tuple[list[tuple[bytes, str]], str]:
    """Normalise any upload to a list of prepared page images, or office text.

    Returns ``(pages, kind)``. For an office document ``pages`` is empty and the
    caller uses :func:`office_text` instead.
    """
    if not data:
        raise LensError("That file is empty.")
    if len(data) > MAX_BYTES:
        raise LensError(f"That file is larger than {MAX_BYTES // (1024 * 1024)} MB. "
                        "Upload the pages you need rather than the whole bundle.")

    low = (filename or "").lower()
    if low.endswith(tuple(DOC_EXT)):
        return [], "office"

    if mime == "application/pdf" or low.endswith(".pdf"):
        from headnote.drafter.ocr import _rasterize_pdfs

        pages = _rasterize_pdfs([(data, "application/pdf")], dpi=200, max_total=MAX_PAGES)
        if not pages:
            raise LensError("That PDF has no readable pages.")
        # A born-digital PDF rasterises clean; prepare() is for camera photos and
        # is a no-op-ish here, but scanned PDFs are photos in a wrapper and do
        # benefit. Cheap either way.
        return [(prepare(p, upscale=2), "image/jpeg") for p, _m in pages], "pdf"

    _register_heif()
    # prepare() deliberately never raises — it returns the original bytes so a
    # merely awkward photo still reaches OCR. That means it cannot be used to
    # detect an unopenable file, so check decodability explicitly first.
    # Without this, a .zip renamed .jpg sails through and the user is shown a
    # raw vendor 400 instead of being told what to upload.
    try:
        from PIL import Image

        Image.open(io.BytesIO(data)).verify()
    except Exception as exc:  # noqa: BLE001
        raise LensError("That file could not be opened as a document or an image. "
                        "PDF, JPG, PNG, HEIC, WEBP and DOCX all work.") from exc
    return [(prepare(data), "image/jpeg")], "image"


# --- stage 2 + 3: read and verify ---------------------------------------------
def read(data: bytes, filename: str, mime: str) -> LensResult:
    """Read one uploaded document into faithful text."""
    from headnote.integrations import gemini

    pages, kind = intake(data, filename, mime)
    res = LensResult(source_kind=kind)

    if kind == "office":
        res.text = office_text(data, filename)
        res.pages = 1
        if not res.text.strip():
            raise LensError("That document has no text in it.")
    else:
        if not gemini.enabled():
            raise LensError("Document reading is not configured on this server.")
        res.pages = len(pages)
        try:
            res.text = gemini.generate_text(_READ_PROMPT, images=pages, temperature=0.0)
        except Exception as exc:  # noqa: BLE001
            raise LensError(f"The document could not be read: {exc}") from exc

    bad = looks_like_garbage(res.text, pages=max(res.pages, 1))
    if bad:
        raise LensError(f"The reading came back unusable ({bad}). "
                        "A straighter, better-lit photo of the page usually fixes it.")

    res.citations = cite.extract(res.text)
    if "[illegible]" in res.text.lower():
        res.flags.append("Parts of the original could not be read and are marked "
                         "[illegible]. Check those against the paper copy.")
    return res


# --- stage 4: translate, behind the gate --------------------------------------
def translate(text: str, target: str, *, source_hint: str = "") -> LensResult:
    """Translate read text into `target`, refusing output that loses a citation.

    One retry with the failure named back to the model, because a dropped
    charge-sheet number is usually a lapse rather than an inability. If it fails
    twice the translation is still returned — with a flag saying exactly what is
    missing, so the advocate is told rather than quietly misled.
    """
    from headnote.integrations import gemini

    lang_name = LANGS.get(target, "")
    if not lang_name:
        raise LensError(f"{target!r} is not a language this can translate into.")
    if not text.strip():
        raise LensError("There is nothing to translate yet.")
    if not gemini.enabled():
        raise LensError("Translation is not configured on this server.")

    res = LensResult(lang=target, translated_from=source_hint)
    prompt = f"Translate the following document into {lang_name}:\n\n{text}"
    out, report = "", None
    for attempt in (1, 2):
        try:
            out = gemini.generate_text(prompt, system=_TRANSLATE_SYSTEM, temperature=0.1)
        except Exception as exc:  # noqa: BLE001
            raise LensError(f"The translation failed: {exc}") from exc
        report = cite.verify(text, out, target_lang=target)
        if report.ok:
            break
        if attempt == 1:
            log.info("lens: retrying translation — %s", report.reason())
            prompt = (f"Translate the following document into {lang_name}. Your previous "
                      f"attempt was rejected because it {report.reason()}. Reproduce every "
                      f"number and statute name exactly, and answer in {lang_name}.\n\n{text}")

    res.text = out
    res.citations = cite.extract(out)
    if report is not None and not report.ok:
        res.flags.append("Check against the original before relying on this: the "
                         f"translation {report.reason()}.")
    return res


# --- stage 5: render ----------------------------------------------------------
def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def to_html(res: LensResult, *, title: str, subtitle: str = "") -> str:
    """Headnote-branded HTML for the PDF renderer.

    Markdown tables are turned into real tables — a gang chart that arrives as a
    grid must leave as a grid, or the row a name belongs to stops being provable.
    """
    body: list[str] = []
    rows: list[list[str]] = []

    def flush() -> None:
        if not rows:
            return
        head, data = rows[0], [r for r in rows[1:] if not all(set(c) <= set("-: ") for c in r)]
        body.append("<table><thead><tr>"
                    + "".join(f"<th>{_esc(c)}</th>" for c in head)
                    + "</tr></thead><tbody>"
                    + "".join("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in r) + "</tr>"
                              for r in data)
                    + "</tbody></table>")
        rows.clear()

    for line in (res.text or "").splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and s.count("|") >= 3:
            rows.append([c.strip() for c in s.strip("|").split("|")])
            continue
        flush()
        if not s:
            continue
        if s.startswith("#"):
            body.append(f"<h2>{_esc(s.lstrip('# ').strip())}</h2>")
        else:
            body.append(f"<p>{_esc(s)}</p>")
    flush()

    flags = ""
    if res.flags:
        flags = ("<div class='flags'><h3>Check these against the original</h3><ol>"
                 + "".join(f"<li>{_esc(f)}</li>" for f in res.flags) + "</ol></div>")

    return f"""<div class="doc">
<div class="masthead"><span class="brand">headnote.</span>
<span class="kicker">{_esc(subtitle or 'Document transcript')}</span></div>
<h1>{_esc(title)}</h1>
{''.join(body)}
{flags}
<div class="foot">Produced by Headnote from an uploaded document. Case numbers,
sections, dates and names are reproduced as they appear in the original; nothing
illegible has been guessed. A working copy for the advocate's reference, not a
certified translation.</div></div>
<style>
.doc{{font-size:10pt;line-height:1.62}}
.masthead{{display:flex;justify-content:space-between;align-items:baseline;
border-bottom:1.2px solid #0C0C0A;padding-bottom:6px;margin-bottom:14px}}
.brand{{font-weight:700;font-size:13pt;letter-spacing:-.02em}}
.kicker{{font-size:7pt;letter-spacing:.12em;text-transform:uppercase;color:#6B6B64}}
h1{{font-size:15pt;font-weight:700;margin:0 0 10px}}
h2{{font-size:11pt;font-weight:600;margin:14px 0 6px}}
p{{margin:0 0 8px;text-align:justify}}
table{{width:100%;border-collapse:collapse;margin:10px 0;font-size:8.6pt}}
th,td{{border:1px solid #DCDCD6;padding:4px 6px;text-align:left;vertical-align:top}}
th{{background:#F4F4F1;font-weight:600}}
.flags{{margin-top:16px;background:#FEF6E7;border-left:2px solid #B45309;padding:9px 12px}}
.flags h3{{font-size:7pt;letter-spacing:.12em;text-transform:uppercase;color:#B45309;margin:0 0 5px}}
.flags ol{{margin:0;padding-left:16px;font-size:8.4pt}}
.foot{{margin-top:16px;padding-top:8px;border-top:1px solid #DCDCD6;font-size:7.4pt;color:#6B6B64}}
</style>"""
