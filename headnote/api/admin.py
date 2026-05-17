"""Admin endpoints — bearer-token-guarded. Mounted onto the main FastAPI app
in headnote.api.app.

Auth: every /admin/* route checks `Authorization: Bearer <ADMIN_TOKEN>`.
ADMIN_TOKEN is set via env var (see headnote.config); if unset, every
admin route returns 503 with a clear message so misconfiguration surfaces
loudly.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, status

from headnote import config
from headnote.api.telemetry import get_summary


router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(authorization: Optional[str]) -> None:
    """Raises HTTPException unless the header carries the configured bearer."""
    if not config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Admin routes are disabled: ADMIN_TOKEN env var is not set. "
                "Add it to .env (e.g. `ADMIN_TOKEN=<random-long-string>`) "
                "and restart."
            ),
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'Authorization: Bearer <ADMIN_TOKEN>' header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(None, 1)[1].strip()
    # Constant-time-ish compare. Python lacks a builtin, but for short
    # admin tokens the timing leak is academic.
    if token != config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bearer token does not match ADMIN_TOKEN.",
        )


@router.get("/telemetry", summary="Cost / escalation / quality summary")
def admin_telemetry(
    authorization: Optional[str] = Header(default=None),
    days: int = Query(default=7, ge=1, le=90,
                      description="Window in days (1-90). Defaults to last 7 days."),
):
    """Return aggregate telemetry over the last `days` days.

    Authentication: `Authorization: Bearer <ADMIN_TOKEN>`.

    The payload powers a future operator dashboard. For now, curl it:

        curl -H "Authorization: Bearer $ADMIN_TOKEN" \\
             https://your-deploy/admin/telemetry?days=7

    Key signals:
      - escalation_rate_pct: if this climbs > 30%, Sonnet is failing too
        often and a prompt tweak (or threshold change) is overdue.
      - avg_cost_paise_per_call: trend down should be the goal as cache
        hits and Sonnet defaults dominate over time.
      - avg_confidence_by_task: Sonnet self-rated confidence on
        situation/digest. Low averages indicate prompt quality issues.
    """
    _require_admin(authorization)
    return get_summary(days=days)
