"""Is this file ready for its next hearing?

Deterministic, explainable, and cheap: readiness is a function of two things we
already hold — what the COURT says the next hearing is for, and what ARTIFACTS
exist for the matter (drafts, documents, saved authorities). No model is
involved, so the answer is always reproducible and we can show the lawyer why.

Precedence:
  1. the lawyer's explicit tick        (prepared=True wins over everything)
  2. a manual status they set by hand  (override)
  3. the derived rule below

Nothing here writes; callers pass plain dicts.
"""

from __future__ import annotations

import re
from typing import Optional

# Purpose (as the COURT words it) → what "ready" means for that kind of hearing.
#
# District and High Court boards are very often in Hindi, so each category
# matches Devanagari as well as English. Getting this wrong is not cosmetic: an
# unmatched purpose used to fall through to "review", i.e. Headnote would tell a
# Hindi-board advocate it had no idea what the hearing was for when the court had
# said so plainly.
_CATEGORIES: list[tuple[str, str]] = [
    ("bail", r"bail|anticipatory|remand|जमानत|ज़मानत|अग्रिम\s*जमानत|रिमांड"),
    ("discharge", r"discharge|framing|charge|आरोप|उन्मोचन|विरचन|आरोप\s*विरचन"),
    ("evidence", r"evidence|cross|witness|exhibit|production|examination"
                 r"|साक्ष्य|गवाह|प्रतिपरीक्षण|बयान|परीक्षण|प्रदर्श"),
    ("reply", r"reply|objection|written statement|leave to defend|summons for judgment|jawab|ws\b"
              r"|जवाब|उत्तर|आपत्ति|लिखित\s*कथन"),
    ("arguments", r"argument|final hearing|submission|तर्क|बहस|अंतिम\s*तर्क|सुनवाई"),
]

LABELS = {
    "ready":    "Ready",
    "draft":    "Draft pending",
    "docs":     "Docs pending",
    "research": "Research pending",
    "args":     "Prepare arguments",
    "review":   "Review",
    "blocked":  "Blocked",
}


def category(purpose: Optional[str]) -> str:
    """Bucket the court's purpose line. Unknown/blank → 'review'."""
    p = (purpose or "").strip().lower()
    if not p:
        return "review"
    for name, pattern in _CATEGORIES:
        if re.search(pattern, p):
            return name
    return "review"


def _final(drafts: list[dict]) -> Optional[dict]:
    """A draft that is finished — ready to file, or already filed."""
    for d in drafts:
        if re.search(r"ready|filed|final", str(d.get("status") or ""), re.I):
            return d
    return None


def derive(matter: dict, *, drafts: list[dict] | None = None,
           documents: list[dict] | None = None,
           authorities: list[dict] | None = None) -> dict:
    """Return {state, why, manual} for one matter.

    `matter` is a case row; its prep block (purpose / prepared / assignee /
    override) is read from case_json["prep"] by the caller and passed through on
    the row as `prep`.
    """
    prep = matter.get("prep") or {}
    drafts = drafts or []
    documents = documents or []
    authorities = authorities or []

    if prep.get("prepared"):
        who = prep.get("assignee")
        return {"state": "ready",
                "why": "Marked prepared by you" + (f" · {who}" if who else ""),
                "manual": True}

    override = prep.get("override") or {}
    if override.get("state"):
        return {"state": override["state"],
                "why": override.get("why") or f"{LABELS.get(override['state'], 'Set')} — set by you",
                "manual": True}

    purpose = (prep.get("purpose") or "").strip()
    cat = category(purpose)

    if cat == "review":
        # Be honest about which of the two situations this is: the court has told
        # us nothing, or it has and we don't recognise the wording. The second
        # needs the lawyer to set it once, not a shrug.
        if purpose:
            return {"state": "review",
                    "why": f"Listed for “{purpose}” — tell me what to check for this",
                    "manual": False}
        return {"state": "review", "why": "No hearing purpose from the court yet", "manual": False}

    if cat == "evidence":
        if documents:
            return {"state": "ready", "why": "Exhibits and documents are on file", "manual": False}
        return {"state": "docs", "why": "Evidence documents not yet uploaded", "manual": False}

    if cat == "arguments":
        # Say WHICH half is missing. "Prepare arguments" told a lawyer nothing he
        # did not already know, and drafting vs research are different jobs —
        # often for different people in the chamber.
        if drafts and authorities:
            n = len(authorities)
            return {"state": "ready",
                    "why": f"Written notes and {n} authorit{'y' if n == 1 else 'ies'} on file",
                    "manual": False}
        if drafts:
            return {"state": "research",
                    "why": "Notes drafted — no authorities saved to this matter yet",
                    "manual": False}
        if authorities:
            n = len(authorities)
            return {"state": "draft",
                    "why": f"{n} authorit{'y' if n == 1 else 'ies'} saved — arguments not written yet",
                    "manual": False}
        return {"state": "research",
                "why": "Nothing prepared yet — no authorities, no written arguments",
                "manual": False}

    # bail / discharge / reply — all turn on whether the application is finished
    done = _final(drafts)
    if done:
        title = re.sub(r"\s+u/s.*$", "", str(done.get("title") or "The application"), flags=re.I)
        return {"state": "ready", "why": f"{title} is ready to file", "manual": False}

    if drafts:
        title = re.sub(r"\s+u/s.*$", "", str(drafts[0].get("title") or "A draft"), flags=re.I)
        return {"state": "draft", "why": f"{title} drafted, not finalised", "manual": False}

    what = {"bail": "bail application", "discharge": "discharge application",
            "reply": "reply"}.get(cat, cat)
    return {"state": "draft", "why": f"No {what} drafted yet", "manual": False}


def label(state: str) -> str:
    return LABELS.get(state, "Review")
