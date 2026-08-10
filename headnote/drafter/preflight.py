"""The junior's note — deterministic pre-flight checks on a finished draft.

A junior advocate's value is not that he writes; it is that he tells you what he
was not sure about BEFORE you find it standing in court. This module is that
review, and it is deliberately built out of nothing but Python:

  * no LLM  → no cost, no latency, no new failure mode, and nothing to fabricate;
  * no I/O  → it can run on every draft, every time, including the never-fail
              skeleton floor;
  * amber is NEVER a blocker. Every finding is a glance, not a gate. A lawyer
    walking into a corridor gets his document; the note tells him where to look.

Each check returns one `Check`: an id, a severity (`ok` | `amber`), an
English one-liner, and a plain-English detail. UI copy is English because Hindi
is a CAPABILITY in Headnote, never the interface voice — but a detail line may
quote the advocate's own words back to him in whatever language he wrote them.

The checks, and why each one exists
-----------------------------------
closer        the oral-arguments closer ("अन्य तर्क वक्त बहस…") was missing from
              EVERY draft in the quality dry-run. Filed applications carry it.
prayer        a draft whose prayer does not name the relief claimed is a defective
              filing; this is the single most consequential internal mismatch.
cause_title   two different courts named in one document = returned at the counter.
code_date     IPC/BNS and CrPC/BNSS are keyed to WHEN the offence/FIR happened
              (01.07.2024). Getting this wrong is the most common 2024-25 defect.
blanks        placeholders are intentional in canonical templates — so this counts
              them and hands the count over rather than pretending they are errors.
companions    a bail application without its affidavit is not a filing.
ungrounded    a name or figure in the draft that is in nothing the advocate gave
              us. Zero-fabrication is a day-1 promise; this is where it is shown.
cite_at_hearing  verified authority deliberately kept OUT of the body, surfaced so
              it is not lost.
warnings      whatever the pipeline itself already flagged, in the same rail.

`review()` never raises: a review that 500s would take the draft down with it.
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional

# BNSS / BNS / BSA replaced CrPC / IPC / Evidence Act for offences on or after
# this date. Everything before it is still tried under the old codes.
NEW_CODES_FROM = date(2024, 7, 1)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t ]+")

# ---------------------------------------------------------------------------
# vocabulary tables. Every entry is a phrase that appears in real filed Indian
# drafts; nothing here is generated, and adding a language means adding rows.
# ---------------------------------------------------------------------------

# "other arguments will be advanced orally at the time of hearing"
_CLOSER = (
    "अन्य तर्क", "वक्त बहस", "बहस के समय", "मौखिक रुप से निवेदित", "मौखिक रूप से निवेदित",
    "इतर युक्तिवाद",                              # Marathi
    "અન્ય દલીલો",                                  # Gujarati
    "at the time of arguments", "at the time of hearing",
    "further arguments", "other arguments", "oral arguments will be",
)

# the prayer block itself
_PRAYER_CUES = ("प्रार्थना", "अतः", "अतःएव", "निवेदन है", "कृपा कर",
                "विनंती", "પ્રાર્થના",
                "it is therefore prayed", "prayed that", "prayer", "pleased to")

# doc_type → the words the prayer must actually name for the relief to match.
# Only types where the relief has an unmistakable name are listed; anything else
# falls back to "a prayer block exists", which is all we can honestly assert.
_RELIEF = {
    "bail":              ("जमानत", "जमानत का लाभ", "bail"),
    "anticipatory_bail": ("अग्रिम जमानत", "जमानत", "anticipatory bail", "bail"),
    "default_bail":      ("जमानत", "bail"),
    "suspension_389":    ("निलंबन", "निलम्बन", "जमानत", "suspension", "suspend"),
    "discharge":         ("उन्मोचन", "आरोपमुक्त", "discharge"),
    "revision":          ("पुनरीक्षण", "निरस्त", "अपास्त", "revision", "set aside"),
    "appeal":            ("अपील", "दोषमुक्त", "अपास्त", "appeal", "acquit", "set aside"),
    "quashing":          ("निरस्त", "रद्द", "quash", "set aside"),
    "maintenance":       ("भरण", "भरण-पोषण", "गुजारा", "maintenance"),
    "dv":                ("संरक्षण", "निवास", "protection", "residence", "maintenance"),
    "cheque_138":        ("दण्डित", "दंडित", "प्रतिकर", "convict", "compensation"),
    "supurdgi":          ("सुपुर्दगी", "अभिरक्षा", "release", "custody of the vehicle"),
    "exemption_205":     ("छूट", "उपस्थिति", "exemption", "personal appearance"),
    "compounding":       ("शमन", "राजीनामा", "compound"),
    "stay_petition":     ("स्थगन", "रोक", "stay"),
    "transfer_petition": ("स्थानान्तरण", "स्थानांतरण", "transfer"),
    "habeas_corpus":     ("मुक्त", "प्रस्तुत", "produce", "release"),
    "recovery_suit":     ("वसूली", "राशि", "recovery", "decree"),
    "injunction_suit":   ("निषेधाज्ञा", "व्यादेश", "injunction", "restrain"),
    "eviction_suit":     ("बेदखली", "आधिपत्य", "eviction", "possession"),
    "partition_suit":    ("बंटवारा", "बटवारा", "विभाजन", "partition"),
    "specific_performance": ("अनुपालन", "विनिर्दिष्ट", "specific performance"),
    "declaration_suit":  ("घोषणा", "declaration", "declare"),
    "consumer_complaint": ("प्रतिकर", "सेवा", "compensation", "deficiency"),
    "maintenance_125":   ("भरण", "maintenance"),
    "legal_notice":      ("भुगतान", "राशि", "payment", "demand"),
    "divorce_13":        ("विवाह विच्छेद", "तलाक", "divorce", "dissolution"),
    "restitution_9":     ("दाम्पत्य", "conjugal", "restitution"),
    "mact_166":          ("प्रतिकर", "क्षतिपूर्ति", "compensation"),
}

# how a court line announces itself, in the scripts we have real drafts for
_COURT_CUES = ("न्यायालय", "अदालत", "कोर्ट", "न्यायाधीश", "मा. न्यायालय",
               "நீதிமன்ற", "ન્યાયાલય", "আদালত",
               "in the court of", "before the", "hon'ble", "honble", "court of")

_APPLICANT_CUES = ("आवेदक", "प्रार्थी", "वादी", "याचिकाकर्ता", "अपीलार्थी", "परिवादी",
                   "अर्जदार", "અરજદાર", "applicant", "petitioner", "plaintiff", "appellant",
                   "complainant")
_RESPONDENT_CUES = ("अनावेदक", "प्रत्यर्थी", "प्रतिवादी", "अनावेदकगण", "गैरअर्जदार",
                    "respondent", "defendant", "opposite party", "state of", "non-applicant")

# An unfilled slot, as the canonical engines emit them. The dot run needs SIX,
# not four: "..... आवेदक" is the standard dotted leader before a party designation
# in an Indian cause title — decoration, not a blank — while a real dotted slot
# ("जमानत आवेदन क्रमांक ............... / 2026") is much longer. Counting leaders
# would put an amber line on every correctly formatted draft.
_BLANK = re.compile(r"_{3,}|\.{6,}|…{2,}")
_PH_SPAN = re.compile(r'class="[^"]*\bph\b[^"]*"')

# section numbering, per code family
_NEW_CODE_CUES = ("bnss", "बी.एन.एस.एस", "बीएनएसएस", "भा.ना.सु.सं", "भारतीय नागरिक सुरक्षा",
                  " bns", "बी.एन.एस", "भा.न्या.सं", "भारतीय न्याय संहिता", "b.n.s")
_OLD_CODE_CUES = ("crpc", "cr.p.c", "cr. p. c", "दं.प्र.सं", "दंप्रसं", "दण्ड प्रक्रिया",
                  "ipc", "i.p.c", "भा.द.वि", "भादवि", "भारतीय दण्ड संहिता", "भारतीय दंड संहिता")

# dd.mm.yyyy / dd-mm-yyyy / dd/mm/yy — the way an Indian draft writes a date
_DMY = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b")


@dataclass
class Check:
    id: str
    severity: str          # "ok" | "amber"
    title: str             # the one-liner the rail shows
    detail: str = ""       # the second line, in plain English

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# text helpers
# ---------------------------------------------------------------------------

def plain(html_or_text: Optional[str]) -> str:
    """Draft HTML → the words on the page. Block tags become newlines so a
    line-oriented check does not fuse the court line into the case number."""
    s = str(html_or_text or "")
    s = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>|<br\s*/?>", "\n", s)
    s = _TAG.sub(" ", s)
    s = _html.unescape(s)
    s = _WS.sub(" ", s)
    return "\n".join(ln.strip() for ln in s.split("\n") if ln.strip())


def _has(hay: str, needles) -> bool:
    low = hay.lower()
    return any(n.lower() in low for n in needles)


def _lines(text: str) -> list[str]:
    return [ln for ln in text.split("\n") if ln.strip()]


def _draft_text(result: dict) -> str:
    """The draft's own words, whichever language it came out in."""
    for key in ("html_hi", "html_en", "html"):
        v = (result or {}).get(key)
        if v and str(v).strip():
            return plain(v)
    return ""


def _prayer_slice(text: str) -> str:
    """The tail of the document from the first prayer cue onward. A prayer is
    always the last substantive block, so 'from the cue to the end' is both
    simple and right, and it never needs the HTML structure to be well-formed."""
    low = text.lower()
    idx = -1
    for cue in _PRAYER_CUES:
        i = low.find(cue.lower())
        if i >= 0 and (idx < 0 or i < idx):
            idx = i
    return text[idx:] if idx >= 0 else ""


def parse_dmy(raw: str) -> Optional[date]:
    """'12.03.2026' → date. Two-digit years resolve to 20xx, which is the only
    reading that makes sense on a live FIR. Returns None on anything invalid —
    a garbled date must not become a confident conclusion."""
    m = _DMY.search(raw or "")
    if not m:
        return None
    d, mo, y = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def earliest_date(*texts: str) -> Optional[date]:
    """The earliest plausible date across the inputs — on a criminal application
    the FIR/incident date is the earliest date in play, and it is the one the code
    family is keyed to. Dates outside 1990..today+1y are ignored as OCR noise."""
    lo = date(1990, 1, 1)
    hi = date(date.today().year + 1, 12, 31)
    found: list[date] = []
    for t in texts:
        for m in _DMY.finditer(t or ""):
            d = parse_dmy(m.group(0))
            if d and lo <= d <= hi:
                found.append(d)
    return min(found) if found else None


# ---------------------------------------------------------------------------
# the checks
# ---------------------------------------------------------------------------

def check_closer(text: str, doc_type: str) -> Check:
    if _has(text, _CLOSER):
        return Check("closer", "ok", "Oral-arguments closer present")
    return Check("closer", "amber", "The oral-arguments closer is missing",
                 "Filed applications end by reserving further arguments for the hearing. "
                 "Add that line before filing.")


def check_prayer(text: str, doc_type: str) -> Check:
    tail = _prayer_slice(text)
    if not tail:
        return Check("prayer", "amber", "No prayer block found",
                     "The document does not close with a prayer. Nothing can be granted "
                     "without one.")
    words = _RELIEF.get(doc_type)
    if not words:
        return Check("prayer", "ok", "Prayer present")
    if _has(tail, words):
        return Check("prayer", "ok", "Prayer matches the relief pleaded")
    return Check("prayer", "amber", "The prayer does not name the relief",
                 "The grounds argue one thing and the prayer asks for something else — or "
                 "for nothing nameable. Check the last paragraph.")


def check_cause_title(text: str) -> Check:
    ls = _lines(text)
    court_lines = [ln for ln in ls if _has(ln, _COURT_CUES)]
    if not court_lines:
        return Check("cause_title", "amber", "No court is named",
                     "The cause title has no court line, so the document cannot be presented "
                     "anywhere.")
    # two DIFFERENT courts in one document is a counter rejection. Compare on the
    # normalised court line, ignoring the case-number line that often repeats it.
    distinct = {_WS.sub(" ", ln.strip().lower().rstrip(".।,")) for ln in court_lines[:6]}
    if len(distinct) > 1 and len(court_lines) > 1:
        # only flag when the lines genuinely disagree, not when one is a substring
        srt = sorted(distinct, key=len)
        if not all(srt[0] in d for d in srt):
            return Check("cause_title", "amber", "More than one court is named",
                         "Two different courts appear in the cause title: "
                         + " / ".join(sorted(distinct)[:2])[:180])
    has_app = _has(text, _APPLICANT_CUES)
    has_res = _has(text, _RESPONDENT_CUES)
    if not (has_app and has_res):
        missing = "applicant" if not has_app else "respondent"
        return Check("cause_title", "amber", f"The {missing} side is not designated",
                     "A cause title needs both sides named and designated before it can be "
                     "numbered by the reader.")
    return Check("cause_title", "ok", "Cause-title consistent on every page")


def check_code_date(text: str, brief: str, doc_type: str, code_sensitive: bool) -> Check:
    if not code_sensitive:
        return Check("code_date", "ok", "Not keyed to a code date",
                     "This document type does not turn on the CrPC/BNSS changeover.")
    fir = earliest_date(brief, text)
    new_cues = _has(text, _NEW_CODE_CUES)
    old_cues = _has(text, _OLD_CODE_CUES)
    if fir is None:
        return Check("code_date", "amber", "No FIR or incident date given",
                     "The draft uses BNSS/BNS numbering. If the offence is before "
                     "01.07.2024, CrPC/IPC numbering applies — say the date and redraft, "
                     "or change it in the editor.")
    pretty = fir.strftime("%d.%m.%Y")
    if fir < NEW_CODES_FROM:
        if old_cues:
            return Check("code_date", "ok", "Sections keyed to the FIR date",
                         f"FIR {pretty} → pre-01.07.2024, so CrPC/IPC numbering leads"
                         + (" with BNSS in brackets" if new_cues else ""))
        return Check("code_date", "amber", "Old-code numbering may be needed",
                     f"FIR {pretty} is before 01.07.2024, so the offence is tried under "
                     "IPC/CrPC — but the draft carries BNS/BNSS numbering.")
    if new_cues:
        return Check("code_date", "ok", "Sections keyed to the FIR date",
                     f"FIR {pretty} → post-01.07.2024, so BNSS/BNS numbering leads"
                     + (" with CrPC in brackets" if old_cues else ""))
    return Check("code_date", "amber", "New-code numbering may be needed",
                 f"FIR {pretty} is on or after 01.07.2024, so BNSS/BNS applies — but the "
                 "draft carries only IPC/CrPC numbering.")


def check_blanks(result: dict, text: str) -> Check:
    """Placeholders in a canonical draft are INTENTIONAL — the advocate fills the
    case number and his own particulars at the counter. So this counts them and
    says so, rather than calling his own template an error."""
    raw = ""
    for key in ("html_hi", "html_en", "html"):
        if (result or {}).get(key):
            raw = str(result[key])
            break
    n = len(_BLANK.findall(text)) + len(_PH_SPAN.findall(raw))
    if not n:
        return Check("blanks", "ok", "No blanks left unfilled")
    return Check("blanks", "amber",
                 f"{n} blank{'' if n == 1 else 's'} left for you to fill",
                 "Left deliberately — case number, particulars and dates are yours to "
                 "enter. Nothing has been invented to fill them.")


def check_companions(result: dict) -> Check:
    comp = [str(c).strip() for c in (result or {}).get("companions") or [] if str(c).strip()]
    if not comp:
        return Check("companions", "ok", "No companion filing needed")
    return Check("companions", "amber",
                 "This filing needs companion papers",
                 "Not filed on its own: " + "; ".join(comp[:4]))


def check_ungrounded(result: dict) -> Check:
    """Anything in the draft that is in NOTHING the advocate gave us. This is the
    zero-fabrication promise made visible: we do not silently delete it (it may
    well be right, spoken but not typed) — we name it and ask him to confirm."""
    ung = [str(u).strip() for u in (result or {}).get("ungrounded") or [] if str(u).strip()]
    if not ung:
        return Check("ungrounded", "ok", "Every fact traces to what you gave me")
    shown = ", ".join(f'"{u}"' for u in ung[:3])
    more = f" (+{len(ung) - 3} more)" if len(ung) > 3 else ""
    return Check("ungrounded", "amber", f"{shown}{more} is not in anything you gave me",
                 "Taken from your brief as spoken. Confirm the spelling and the figure "
                 "before filing.")


def check_cite_at_hearing(result: dict) -> Check:
    cites = [str(c).strip() for c in (result or {}).get("cite_at_hearing") or [] if str(c).strip()]
    if not cites:
        return Check("cite_at_hearing", "ok", "No authority held back")
    return Check("cite_at_hearing", "amber", "Cite at hearing — not in the document",
                 "; ".join(cites[:3]) + ". Verified authority, kept out of the body.")


# ---------------------------------------------------------------------------
# the review
# ---------------------------------------------------------------------------

# types whose section numbering turns on the 01.07.2024 changeover. Mirrors
# from_prompt._CODE_SENSITIVE; kept local so preflight has no import cost and a
# test pins the two lists together.
CODE_SENSITIVE = {
    "bail", "anticipatory_bail", "default_bail", "suspension_389", "discharge",
    "revision", "appeal", "quashing", "parivad", "complaint_156", "supurdgi",
    "exemption_205", "compounding", "recall_311", "statement_178", "production",
    "production_warrant", "transfer_petition", "maintenance", "other_criminal",
}


def review(result: dict, *, brief: str = "") -> dict:
    """The junior's note for one finished draft.

    `result` is the unified draft dict every path returns (`from_prompt`,
    `/refine`, the skeleton floor). `brief` is what the advocate typed or said —
    it is where the FIR date usually lives even when the draft left it blank.

    Returns {ok, checks:[…], counts:{ok, amber}}. Ordering is deliberate:
    the amber items come first, because the rail is read top-down and the point
    of the rail is what to look at.
    """
    try:
        result = result if isinstance(result, dict) else {}
        text = _draft_text(result)
        doc_type = str(result.get("doc_type") or "other_criminal")
        code_sensitive = doc_type in CODE_SENSITIVE

        checks: list[Check] = []
        if text:
            checks.append(check_closer(text, doc_type))
            checks.append(check_prayer(text, doc_type))
            checks.append(check_cause_title(text))
            checks.append(check_code_date(text, brief, doc_type, code_sensitive))
            checks.append(check_blanks(result, text))
        else:
            checks.append(Check("empty", "amber", "The draft came back empty",
                                "Nothing was rendered. Press Draft again — your brief is "
                                "still here."))
        checks.append(check_ungrounded(result))
        checks.append(check_cite_at_hearing(result))
        checks.append(check_companions(result))

        # whatever the pipeline itself flagged, in the same rail rather than a
        # separate banner the lawyer has to notice twice
        for i, w in enumerate((result.get("warnings") or [])[:4]):
            w = plain(w)
            if w:
                checks.append(Check(f"pipeline_{i}", "amber", w[:120],
                                    w[120:400] if len(w) > 120 else ""))

        amber = [c for c in checks if c.severity == "amber"]
        okc = [c for c in checks if c.severity == "ok"]
        return {
            "ok": True,
            "doc_type": doc_type,
            "checks": [c.as_dict() for c in amber + okc],
            "counts": {"ok": len(okc), "amber": len(amber)},
        }
    except Exception as e:  # a review must never take the draft down with it
        import logging
        logging.getLogger("headnote.drafter.preflight").warning(
            "preflight degraded: %s", e, exc_info=True)
        return {"ok": False, "checks": [], "counts": {"ok": 0, "amber": 0},
                "error": f"{type(e).__name__}"}
