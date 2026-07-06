"""Source-integrity verification for research precedent cards.

The situation pipeline attaches a `kanoon_doc_id` to each card and the UI badges
it "verified · Indian Kanoon". But attaching a doc id is NOT the same as
confirming the citation: the id may not resolve, or resolve to an unrelated
document, and the quoted "HELD" line may not appear in the judgment at all.
After the SC's 27 Feb 2026 ruling, showing a green "verified" badge on an
unconfirmed citation is exactly the kind of misrepresentation that gets a lawyer
into trouble.

This module does the confirmation the badge *claims* has happened, against the
live Indian Kanoon source (via the existing KanoonClient cache):

  A. RESOLVE + TITLE-MATCH — the doc id must resolve (docmeta), and the resolved
     document's title must actually be the cited case. Catches "id resolves but
     to the wrong document" (e.g. an id that maps to a Lokayukta Act page).

  B. QUOTE-IN-DOC — the card's verbatim court_quote / quotable_phrase must appear
     (near-verbatim) in the resolved judgment's own text — not just in whatever
     paragraph evidence we happened to fetch during retrieval.

  C. YEAR — the card's year must agree with the judgment's publish date.

Fail-closed: if the IK client is unavailable (no token, disabled, daily cap hit,
API down) or anything raises, the card is reported NOT verified. We never emit a
green badge we could not positively confirm.

The holding-vs-allegation check (does the "HELD" line recite a party's
allegation rather than the court's finding?) is pure text and lives in
`headnote.verify.held_reads_as_allegation` — it needs no network.

Cost: docmeta is ₹0.02, doc is ₹0.20, both cached forever. The full doc is only
fetched when the title matched (no point quote-checking a wrong document), and
retrieval has usually already cached it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from headnote import verify

# Two names refer to the same case when their distinctive tokens line up. We
# score on containment (does the shorter name's core sit inside the longer?)
# blended with Jaccard, so "Ram Niwas Bansal v. State of U.P." matches
# "Ram Niwas Bansal And Anr vs State Of U.P. And Ors" (shared surnames) but not
# "Rajasthan Lokayukta Sanchalan Act" (no shared distinctive tokens).
TITLE_MATCH_THRESHOLD = 0.5

# Party/boilerplate tokens that carry no identifying weight — dropped before
# comparison so two real titles aren't judged "matching" purely on "state of".
_TITLE_STOP = {
    "v", "vs", "versus", "and", "ors", "or", "anr", "another", "others",
    "state", "of", "the", "union", "india", "govt", "government", "through",
    "thru", "rep", "by", "ms", "mr", "smt", "sri", "shri", "in", "re",
    "petitioner", "respondent", "appellant", "etc", "no", "cri", "crl",
}


def _title_tokens(s: str) -> list[str]:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\b\d{4}\b", " ", s)  # drop years
    out = []
    for t in s.split():
        if not t or t in _TITLE_STOP or t.isdigit() or len(t) == 1:
            continue
        out.append(t)
    return out


def title_similarity(cited: str, resolved: str) -> float:
    """0..1 — how confidently `resolved` is the same case as `cited`.

    Containment-weighted so a distinctive surname overlap scores high even when
    one side carries extra "And Ors"/"State Of" padding, while genuinely
    different documents (no shared distinctive tokens) score near zero.
    """
    a = set(_title_tokens(cited))
    b = set(_title_tokens(resolved))
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    jacc = inter / len(a | b)
    contain = inter / min(len(a), len(b))
    return max(jacc, 0.5 * jacc + 0.5 * contain)


@dataclass
class SourceCheck:
    """Result of confirming one card's citation against the live IK source."""
    resolved: Optional[bool] = None          # doc id resolves? None = couldn't check
    title_match: Optional[bool] = None        # resolved doc IS the cited case?
    title_similarity: float = 0.0
    resolved_title: str = ""
    quote_present: Optional[bool] = None      # verbatim quote found in the doc?
    quote_similarity: float = 0.0
    year_match: Optional[bool] = None
    resolved_year: str = ""                    # authoritative year from publishdate
    flags: list[str] = field(default_factory=list)
    reason: str = ""                          # short human explanation for the UI

    def is_verified(self) -> bool:
        """Green badge ONLY when we positively confirmed all three: the doc
        resolves, it is the cited case, and the quote is present. `quote_present`
        is set True when there is no substantive quote to check (resolve + title
        is then sufficient for the quote dimension)."""
        return (
            self.resolved is True
            and self.title_match is True
            and self.quote_present is True
        )


def _doc_paragraphs_as_evidence(doc, case_id: str) -> list["verify.EvidenceParagraph"]:
    """Parse a judgment's HTML into EvidenceParagraph units so we can reuse the
    tuned fuzzy matcher in verify._best_match for quote presence."""
    from headnote.kanoon.parser import parse_judgment

    parsed = parse_judgment(doc.doc_html, tid=getattr(doc, "tid", 0),
                            title_hint=getattr(doc, "title", ""))
    evs: list[verify.EvidenceParagraph] = []
    for p in parsed.paragraphs:
        if p.text:
            evs.append(verify.EvidenceParagraph(
                case_id=case_id, para_id=p.id, para_num=p.num, text=p.text,
            ))
    if not evs and (parsed.full_text or "").strip():
        evs.append(verify.EvidenceParagraph(
            case_id=case_id, para_id="", para_num=None, text=parsed.full_text,
        ))
    return evs


def verify_card_source(
    client,
    *,
    doc_id,
    cited_title: str,
    quotes: list[str] | None = None,
    year=None,
) -> SourceCheck:
    """Confirm one card's citation against Indian Kanoon. Never raises — any
    failure is reported as an unverified SourceCheck (fail-closed)."""
    chk = SourceCheck()
    quotes = [q for q in (quotes or []) if q and len(q.strip()) >= verify.MIN_QUOTE_CHARS]

    if client is None or not doc_id:
        chk.flags.append("source_unchecked")
        chk.reason = "citation source not checked — verify before use"
        return chk

    try:
        tid = int(str(doc_id).strip())
    except (TypeError, ValueError):
        chk.flags.append("source_unchecked")
        chk.reason = "citation has no valid Indian Kanoon id"
        return chk

    # --- A. resolve + title match (cheap docmeta, ₹0.02, cached forever)
    from headnote.kanoon.client import KanoonNotFound

    try:
        meta = client.get_docmeta(tid)
    except KanoonNotFound:
        chk.resolved = False
        chk.flags.append("unresolved")
        chk.reason = "Indian Kanoon doc id does not resolve to any document"
        return chk
    except Exception as e:  # noqa: BLE001 — auth / rate-limit / budget / network
        chk.flags.append("source_unchecked")
        chk.reason = f"could not reach Indian Kanoon to verify ({type(e).__name__})"
        return chk

    chk.resolved = True
    resolved_title = str((meta or {}).get("title") or "").strip()
    chk.resolved_title = resolved_title
    chk.title_similarity = title_similarity(cited_title, resolved_title)
    chk.title_match = chk.title_similarity >= TITLE_MATCH_THRESHOLD
    if not chk.title_match:
        chk.flags.append("title_mismatch")
        chk.reason = (
            f"doc id resolves to a different case"
            + (f" (‘{resolved_title[:70]}’)" if resolved_title else "")
        )

    # --- C. year, from the authoritative publishdate. When the doc IS the cited
    # case, its own publish year is ground truth — the caller corrects a wrong
    # LLM year to this rather than badging the wrong year as "verified".
    pub = str((meta or {}).get("publishdate") or "")
    m = re.search(r"(\d{4})", pub)
    if m:
        chk.resolved_year = m.group(1)
        if year:
            chk.year_match = str(year).strip() == m.group(1)

    # --- B. quote presence in the resolved judgment (only if it IS the case)
    if chk.title_match and quotes:
        try:
            doc = client.get_doc(tid)
            evs = _doc_paragraphs_as_evidence(doc, f"ik:{tid}")
            best = 0.0
            for q in quotes:
                ratio, _, _ = verify._best_match(q, evs)
                if ratio > best:
                    best = ratio
                if best >= verify.DEFAULT_VERBATIM_THRESHOLD:
                    break
            chk.quote_similarity = best
            chk.quote_present = best >= verify.DEFAULT_VERBATIM_THRESHOLD
            if not chk.quote_present:
                chk.flags.append("quote_unverified")
                if not chk.reason:
                    chk.reason = "the quoted line was not found in the judgment"
        except Exception as e:  # noqa: BLE001
            chk.quote_present = None
            chk.flags.append("quote_unchecked")
            if not chk.reason:
                chk.reason = f"could not verify the quote against the judgment ({type(e).__name__})"
    elif chk.title_match and not quotes:
        # Nothing verbatim was claimed — resolve + title is enough for this
        # dimension, so the quote check does not block the green badge.
        chk.quote_present = True

    return chk
