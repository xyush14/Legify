"""Partner & referral-code admin endpoints.

All routes are bearer-token-guarded (Authorization: Bearer ADMIN_TOKEN) so they
can be hit from /static/admin-partners.html with the same auth flow as
/static/admin-assist.html.

Surface:
  GET    /admin/partners/list                         list partners + aggregated metrics
  POST   /admin/partners/list                         create a partner (distributor)
  GET    /admin/partners/by-id/{partner_id}           one partner's detail (employees + codes + recent events)
  PATCH  /admin/partners/by-id/{partner_id}           update partner (commission_pct, status, contact, etc.)

  POST   /admin/partners/by-id/{partner_id}/employees add an employee under a partner
  PATCH  /admin/partners/employees/{employee_id}      update an employee

  GET    /admin/partners/codes/all                    list ALL referral codes (incl. publications) with metrics
  POST   /admin/partners/codes                        issue a code (kind=distributor or publication)
  PATCH  /admin/partners/codes/{code}                 toggle active / change discount / expire / notes

  GET    /admin/partners/events                       recent referral_events ledger
  POST   /admin/partners/events/{event_id}/mark-paid  mark a commission as paid out
  POST   /admin/partners/send-weekly-emails           render + send the weekly snapshot to all active partners (or one via ?partner_id=)

Why `/by-id/`: FastAPI matches routes in declaration order, so a literal
`/events` declared after `/{partner_id}` would never fire. Nesting the
partner-by-id routes under `/by-id/` avoids any ambiguity.

Auth: every route checks `Authorization: Bearer <ADMIN_TOKEN>`. Falls through
to admin_v2's dual-auth pattern would also work, but bearer-only keeps the FE
dashboard self-contained (no Supabase JWT plumbing needed for this surface).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from headnote import config
from headnote.entitlements import _supabase
from headnote.payments import referrals


log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/partners", tags=["admin", "partners"])


# ---------------------------------------------------------------- auth

def _require_admin(authorization: Optional[str]) -> None:
    """Same bearer-token gate as admin.py — see that module for rationale."""
    if not config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin routes disabled: ADMIN_TOKEN env var is not set.",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'Authorization: Bearer <ADMIN_TOKEN>' header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(None, 1)[1].strip()
    if token != config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bearer token does not match ADMIN_TOKEN.",
        )


# ---------------------------------------------------------------- models

class PartnerIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    territory: Optional[str] = None
    commission_pct: float = Field(10.0, ge=0, le=100)
    notes: Optional[str] = None


class PartnerPatch(BaseModel):
    name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    territory: Optional[str] = None
    commission_pct: Optional[float] = Field(None, ge=0, le=100)
    status: Optional[str] = Field(None, pattern="^(active|paused|terminated)$")
    notes: Optional[str] = None


class EmployeeIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class EmployeePatch(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|inactive)$")
    notes: Optional[str] = None


class CodeIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    kind: str = Field(..., pattern="^(distributor|publication)$")
    partner_id: Optional[str] = None       # required when kind=distributor
    employee_id: Optional[str] = None      # optional under a distributor
    publication_name: Optional[str] = None # required when kind=publication
    discount_pct: float = Field(0.0, ge=0, le=100)
    applies_to: str = Field("first_order", pattern="^(first_order|all_orders)$")
    expires_at: Optional[str] = None       # ISO timestamp
    notes: Optional[str] = None


class CodePatch(BaseModel):
    active: Optional[bool] = None
    discount_pct: Optional[float] = Field(None, ge=0, le=100)
    applies_to: Optional[str] = Field(None, pattern="^(first_order|all_orders)$")
    employee_id: Optional[str] = None
    expires_at: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------- aggregation

def _aggregate_partner_metrics() -> dict[str, dict]:
    """Pull every partner_employees / referral_codes / referral_events /
    referral_attributions row once and group by partner_id in Python.

    Cheap given the order of magnitude (< 100 partners, < few-thousand events).
    Returns a dict keyed by partner_id with sub-dicts of metrics.
    """
    events = _supabase.select(
        "referral_events",
        params={"select": "partner_id,net_amount_inr,commission_inr,payout_status,created_at"},
    )
    attributions = _supabase.select(
        "referral_attributions",
        params={"select": "partner_id"},
    )
    codes = _supabase.select(
        "referral_codes",
        params={"select": "partner_id,kind"},
    )
    employees = _supabase.select(
        "partner_employees",
        params={"select": "partner_id,status"},
    )

    metrics: dict[str, dict] = defaultdict(lambda: {
        "num_employees":         0,
        "num_active_employees":  0,
        "num_codes":             0,
        "num_attributions":      0,
        "num_paid_orders":       0,
        "gross_inr":             0,        # sum net_amount across paid orders
        "commission_total_inr":  0,
        "commission_pending_inr": 0,
        "commission_paid_inr":   0,
        "last_event_at":         None,
    })

    for e in employees:
        pid = e.get("partner_id")
        if not pid: continue
        m = metrics[pid]
        m["num_employees"] += 1
        if e.get("status") == "active":
            m["num_active_employees"] += 1

    for c in codes:
        pid = c.get("partner_id")
        if not pid: continue
        metrics[pid]["num_codes"] += 1

    for a in attributions:
        pid = a.get("partner_id")
        if not pid: continue
        metrics[pid]["num_attributions"] += 1

    for ev in events:
        pid = ev.get("partner_id")
        if not pid: continue
        m = metrics[pid]
        m["num_paid_orders"] += 1
        m["gross_inr"] += int(float(ev.get("net_amount_inr") or 0))
        ci = int(float(ev.get("commission_inr") or 0))
        m["commission_total_inr"] += ci
        if ev.get("payout_status") == "paid":
            m["commission_paid_inr"] += ci
        else:
            # pending and reversed both count as not-yet-paid for the dashboard;
            # we surface payout_status on the detail page if you need to drill in.
            m["commission_pending_inr"] += ci
        created_at = ev.get("created_at")
        if created_at and (m["last_event_at"] is None or created_at > m["last_event_at"]):
            m["last_event_at"] = created_at

    return metrics


# ---------------------------------------------------------------- partners

@router.get("/list", summary="List partners with aggregated metrics")
def list_partners(authorization: Optional[str] = Header(default=None)) -> dict:
    _require_admin(authorization)
    rows = _supabase.select(
        "partners",
        params={"select": "*", "order": "created_at.desc"},
    )
    metrics = _aggregate_partner_metrics()
    for p in rows:
        m = metrics.get(p["id"], {})
        p["metrics"] = {
            "num_employees":          m.get("num_employees", 0),
            "num_active_employees":   m.get("num_active_employees", 0),
            "num_codes":              m.get("num_codes", 0),
            "num_attributions":       m.get("num_attributions", 0),
            "num_paid_orders":        m.get("num_paid_orders", 0),
            "gross_inr":              m.get("gross_inr", 0),
            "commission_total_inr":   m.get("commission_total_inr", 0),
            "commission_pending_inr": m.get("commission_pending_inr", 0),
            "commission_paid_inr":    m.get("commission_paid_inr", 0),
            "last_event_at":          m.get("last_event_at"),
        }
    return {"partners": rows, "count": len(rows)}


@router.post("/list", summary="Create a partner (distributor)")
def create_partner(
    body: PartnerIn,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require_admin(authorization)
    payload = body.model_dump(exclude_none=True)
    payload["status"] = "active"
    try:
        rows = _supabase.upsert("partners", payload)
    except Exception as e:
        log.exception("partner create failed")
        raise HTTPException(status_code=500, detail=f"create failed: {e}")
    if not rows:
        raise HTTPException(status_code=500, detail="No row returned")
    return rows[0]


@router.get("/by-id/{partner_id}", summary="One partner's detail page payload")
def get_partner(
    partner_id: str,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require_admin(authorization)
    partners = _supabase.select(
        "partners",
        params={"id": f"eq.{partner_id}", "select": "*", "limit": "1"},
    )
    if not partners:
        raise HTTPException(status_code=404, detail="Partner not found")

    employees = _supabase.select(
        "partner_employees",
        params={"partner_id": f"eq.{partner_id}", "select": "*", "order": "created_at.desc"},
    )
    codes = _supabase.select(
        "referral_codes",
        params={"partner_id": f"eq.{partner_id}", "select": "*", "order": "created_at.desc"},
    )
    events = _supabase.select(
        "referral_events",
        params={
            "partner_id": f"eq.{partner_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": "200",
        },
    )

    # Per-employee aggregation for the detail page leaderboard.
    by_emp: dict[str, dict] = defaultdict(lambda: {
        "num_paid_orders": 0, "gross_inr": 0,
        "commission_inr": 0, "last_event_at": None,
    })
    for ev in events:
        eid = ev.get("employee_id") or "_no_employee_"
        m = by_emp[eid]
        m["num_paid_orders"] += 1
        m["gross_inr"] += int(float(ev.get("net_amount_inr") or 0))
        m["commission_inr"] += int(float(ev.get("commission_inr") or 0))
        ca = ev.get("created_at")
        if ca and (m["last_event_at"] is None or ca > m["last_event_at"]):
            m["last_event_at"] = ca

    for e in employees:
        e["metrics"] = by_emp.get(e["id"], {
            "num_paid_orders": 0, "gross_inr": 0,
            "commission_inr": 0, "last_event_at": None,
        })

    return {
        "partner":   partners[0],
        "employees": employees,
        "codes":     codes,
        "events":    events,
        "unassigned_metrics": by_emp.get("_no_employee_", {}),
    }


@router.patch("/by-id/{partner_id}", summary="Update a partner")
def update_partner(
    partner_id: str,
    body: PartnerPatch,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require_admin(authorization)
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    rows = _supabase.update("partners", payload, params={"id": f"eq.{partner_id}"})
    if not rows:
        raise HTTPException(status_code=404, detail="Partner not found")
    return rows[0]


# ---------------------------------------------------------------- employees

@router.post("/by-id/{partner_id}/employees", summary="Add an employee under a partner")
def add_employee(
    partner_id: str,
    body: EmployeeIn,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require_admin(authorization)
    payload = body.model_dump(exclude_none=True)
    payload["partner_id"] = partner_id
    payload["status"] = "active"
    rows = _supabase.upsert("partner_employees", payload)
    if not rows:
        raise HTTPException(status_code=500, detail="No row returned")
    return rows[0]


@router.patch("/employees/{employee_id}", summary="Update an employee")
def update_employee(
    employee_id: str,
    body: EmployeePatch,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require_admin(authorization)
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    rows = _supabase.update("partner_employees", payload, params={"id": f"eq.{employee_id}"})
    if not rows:
        raise HTTPException(status_code=404, detail="Employee not found")
    return rows[0]


# ---------------------------------------------------------------- codes

@router.get("/codes/all", summary="List all referral codes with usage metrics")
def list_codes(authorization: Optional[str] = Header(default=None)) -> dict:
    """Paths the FE uses: /admin/partners/codes/all (not /codes — that would
    clash with FastAPI matching /{partner_id})."""
    _require_admin(authorization)
    rows = _supabase.select(
        "referral_codes",
        params={
            "select": (
                "code,kind,partner_id,employee_id,publication_name,"
                "discount_pct,applies_to,active,expires_at,notes,created_at,"
                "partners(name),partner_employees(name)"
            ),
            "order": "created_at.desc",
        },
    )
    # Aggregate redemptions per code.
    events = _supabase.select(
        "referral_events",
        params={"select": "code,net_amount_inr,commission_inr"},
    )
    by_code: dict[str, dict] = defaultdict(lambda: {
        "num_paid_orders": 0, "gross_inr": 0, "commission_inr": 0,
    })
    for ev in events:
        c = ev.get("code")
        if not c: continue
        m = by_code[c]
        m["num_paid_orders"] += 1
        m["gross_inr"] += int(float(ev.get("net_amount_inr") or 0))
        m["commission_inr"] += int(float(ev.get("commission_inr") or 0))
    for r in rows:
        r["metrics"] = by_code.get(r["code"], {
            "num_paid_orders": 0, "gross_inr": 0, "commission_inr": 0,
        })
    return {"codes": rows, "count": len(rows)}


@router.post("/codes", summary="Issue a new referral code")
def issue_code(
    body: CodeIn,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require_admin(authorization)
    code = referrals.canonical(body.code)
    if not code:
        raise HTTPException(status_code=400, detail="Empty code")

    if body.kind == "distributor" and not body.partner_id:
        raise HTTPException(status_code=400, detail="partner_id required when kind=distributor")
    if body.kind == "publication" and not body.publication_name:
        raise HTTPException(status_code=400, detail="publication_name required when kind=publication")

    payload: dict[str, Any] = {
        "code":             code,
        "kind":             body.kind,
        "discount_pct":     body.discount_pct,
        "applies_to":       body.applies_to,
        "active":           True,
    }
    if body.kind == "distributor":
        payload["partner_id"] = body.partner_id
        if body.employee_id:
            payload["employee_id"] = body.employee_id
    else:
        payload["publication_name"] = body.publication_name
    if body.expires_at:
        payload["expires_at"] = body.expires_at
    if body.notes:
        payload["notes"] = body.notes

    try:
        rows = _supabase.upsert("referral_codes", payload)
    except Exception as e:
        log.exception("code issue failed")
        raise HTTPException(status_code=500, detail=f"create failed: {e}")
    if not rows:
        raise HTTPException(status_code=500, detail="No row returned")
    return rows[0]


@router.patch("/codes/{code}", summary="Update a referral code")
def update_code(
    code: str,
    body: CodePatch,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _require_admin(authorization)
    canon = referrals.canonical(code)
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    rows = _supabase.update("referral_codes", payload, params={"code": f"eq.{canon}"})
    if not rows:
        raise HTTPException(status_code=404, detail="Code not found")
    return rows[0]


# ---------------------------------------------------------------- events

@router.get("/events", summary="Recent referral_events ledger")
def list_events(
    authorization: Optional[str] = Header(default=None),
    limit: int = Query(100, ge=1, le=1000),
    partner_id: Optional[str] = Query(None),
    payout_status: Optional[str] = Query(None, pattern="^(pending|paid|reversed|none)$"),
) -> dict:
    _require_admin(authorization)
    params: dict[str, str] = {
        "select": (
            "*,partners(name),partner_employees(name)"
        ),
        "order":  "created_at.desc",
        "limit":  str(limit),
    }
    if partner_id:
        params["partner_id"] = f"eq.{partner_id}"
    if payout_status:
        params["payout_status"] = f"eq.{payout_status}"
    rows = _supabase.select("referral_events", params=params)
    return {"events": rows, "count": len(rows)}


@router.post("/send-weekly-emails", summary="Send the weekly snapshot email to active partners")
def send_weekly_emails(
    authorization: Optional[str] = Header(default=None),
    partner_id: Optional[str] = Query(None, description="If set, send only to this one partner (useful for testing)"),
) -> dict:
    """Renders + sends one weekly snapshot email per active partner. Returns
    a small JSON summary so a cron job can log/alert on degraded sends.

    Wire to a scheduler (Railway cron / GitHub Actions / external uptime
    monitor) calling this with the ADMIN_TOKEN once a week. Idempotency is
    deliberately NOT enforced here — calling twice in a day will send twice.
    The cron schedule owns that, not the endpoint.
    """
    _require_admin(authorization)
    from headnote.email.partner_weekly import send_all
    return send_all(partner_id=partner_id)


@router.post("/events/{event_id}/mark-paid", summary="Mark a commission as paid out")
def mark_event_paid(
    event_id: int,
    payout_id: str = Body(..., embed=True),
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """`payout_id` is your bank-transfer reference / UPI txn id. Stored verbatim
    so you can reconcile against your bank statement later."""
    _require_admin(authorization)
    from datetime import datetime, timezone
    rows = _supabase.update(
        "referral_events",
        {
            "payout_status": "paid",
            "payout_id":     payout_id,
            "payout_at":     datetime.now(timezone.utc).isoformat(),
        },
        params={"id": f"eq.{event_id}"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Event not found")
    return rows[0]
