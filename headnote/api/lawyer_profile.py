"""GET / PATCH /api/lawyer-profile — bar-association persona stored on the user.

What's stored
-------------
Per-advocate fields used to auto-fill every draft's signature block and the
court-default field. Stored as extra columns on public.user_profiles (see
`docs/migrations/` for the alter-table SQL).

| Column            | Example                                       |
| ----------------- | --------------------------------------------- |
| advocate_name     | "Vishnu Shivhare"                             |
| enrolment_number  | "D/2349/2010"                                 |
| bar_council       | "Bar Council of Delhi"                        |
| chamber_address   | "Chamber No. 47, High Court Premises"         |
| home_court        | "High Court of Delhi"                         |

The phone + email already live in user_profiles from onboarding.

Why a separate router
---------------------
Keeps the auth-required endpoints cleanly grouped + lets future fields
(signature image URL, AOR number for SC, etc.) be added without touching
the onboarding flow.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from headnote.entitlements import CurrentUser, get_current_user
from headnote.entitlements import _supabase


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lawyer-profile", tags=["lawyer-profile"])


# Columns we read/write. Adding a new persona field? Add it here + run the
# Supabase migration. No other code changes needed — the format_spec
# substitution machinery (compose.py) reads the dict generically.
_PERSONA_COLS = (
    "advocate_name",
    "enrolment_number",
    "bar_council",
    "chamber_address",
    "home_court",
)


class LawyerProfile(BaseModel):
    """All fields optional — a brand-new user has none of them set."""
    advocate_name:    Optional[str] = Field(None, max_length=120)
    enrolment_number: Optional[str] = Field(None, max_length=60)
    bar_council:      Optional[str] = Field(None, max_length=120)
    chamber_address:  Optional[str] = Field(None, max_length=400)
    home_court:       Optional[str] = Field(None, max_length=120)


def _read_profile(user_id: str) -> dict:
    """Read the persona row for this user. Returns dict with the 5 fields
    (None for unset). Returns all-None dict if no row exists."""
    try:
        rows = _supabase.select(
            "user_profiles",
            params={
                "id":     f"eq.{user_id}",
                "select": ",".join(_PERSONA_COLS),
                "limit":  "1",
            },
        )
    except Exception as e:
        log.warning("lawyer_profile read failed for %.8s: %s", user_id, e)
        rows = []
    base = {col: None for col in _PERSONA_COLS}
    if rows:
        base.update({k: v for k, v in rows[0].items() if k in _PERSONA_COLS})
    return base


@router.get("", summary="Read the signed-in lawyer's persona")
def get_lawyer_profile(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Returns whatever persona fields the user has saved. Missing fields
    come back as null — the FE shows empty inputs to be filled.

    Also returns `phone` and `email` for convenience (already on the user)
    so the settings page can render a full profile preview without two
    separate fetches.
    """
    profile = _read_profile(user.id)
    return {
        **profile,
        "phone": (user.raw_claims or {}).get("phone") or None,
        "email": user.email or "",
        # `complete` is a derived flag the FE uses to decide whether to
        # show the "Complete your bar profile" nudge on the drafting home.
        "complete": all(profile.get(k) for k in ("advocate_name", "enrolment_number")),
    }


@router.patch("", summary="Update the signed-in lawyer's persona")
def patch_lawyer_profile(
    body: LawyerProfile,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Upserts the provided fields. Only non-None fields are written —
    sending {} is a no-op. Returns the updated profile.

    Whitespace-only strings are treated as null (so a field can be cleared
    by sending "  ")."""
    payload: dict = {}
    for col in _PERSONA_COLS:
        val = getattr(body, col, None)
        if val is None:
            continue
        v = (val or "").strip()
        payload[col] = v if v else None
    if not payload:
        return _read_profile(user.id)

    try:
        _supabase.update(
            "user_profiles",
            payload,
            params={"id": f"eq.{user.id}"},
        )
    except Exception as e:
        log.exception("lawyer_profile update failed for %.8s", user.id)
        raise HTTPException(status_code=502, detail=f"could not save profile: {e}")

    return _read_profile(user.id)
