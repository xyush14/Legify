"""Weekly partner snapshot email.

Triggered by `POST /admin/partners/send-weekly-emails` (manual or cron).
Renders one email per active partner with their week + lifetime numbers,
per-employee breakdown, and pending payout. Honors the "live earnings
dashboard, monthly payouts" promise in the distributor appointment pack —
without yet building a full partner-facing dashboard.

Design constraints (same as welcome.py):
  - Table-based layout (Gmail / Outlook strip flex/grid)
  - Inline CSS only
  - All absolute URLs
  - Plain-text fallback

Without RESEND_API_KEY this becomes a logged no-op.
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from headnote.entitlements import _supabase


log = logging.getLogger(__name__)

FROM_EMAIL   = os.environ.get("PARTNER_FROM_EMAIL", "Headnote Partners <hello@headnote.in>")
REPLY_TO     = os.environ.get("PARTNER_REPLY_TO",   "hello@headnote.in")
APP_BASE_URL = (os.environ.get("APP_BASE_URL") or "https://headnote.in").rstrip("/")


def _inr(n) -> str:
    """Indian-format integer rupees: 1,23,456."""
    try:
        return f"{int(round(float(n))):,}"
    except (TypeError, ValueError):
        return "0"


def _week_window() -> tuple[datetime, datetime]:
    """Returns (start, end) = (now - 7 days, now), both timezone-aware UTC."""
    end = datetime.now(timezone.utc)
    return end - timedelta(days=7), end


def _date_label(d: datetime) -> str:
    return d.strftime("%-d %b").lstrip("0") if hasattr(d, "strftime") else str(d)


def _aggregate(events: list[dict]) -> dict:
    """Sum events into {num_orders, gross_inr, commission_inr}."""
    agg = {"num_orders": 0, "gross_inr": 0, "commission_inr": 0}
    for ev in events:
        agg["num_orders"] += 1
        agg["gross_inr"] += int(float(ev.get("net_amount_inr") or 0))
        agg["commission_inr"] += int(float(ev.get("commission_inr") or 0))
    return agg


def _build_email_html(*, partner: dict, week_events: list[dict],
                      lifetime_events: list[dict], employees: list[dict]) -> str:
    """Render the partner weekly snapshot HTML."""
    name = partner.get("name") or "Partner"
    first = name.split()[0] if name else "Partner"
    start, end = _week_window()
    week_label = f"{_date_label(start)} – {_date_label(end)}"

    week     = _aggregate(week_events)
    lifetime = _aggregate(lifetime_events)
    pending = sum(
        int(float(e.get("commission_inr") or 0))
        for e in lifetime_events
        if (e.get("payout_status") or "").lower() == "pending"
    )

    # Per-employee breakdown for the lifetime window.
    by_emp: dict[str, dict] = defaultdict(lambda: {"num_orders": 0, "commission_inr": 0})
    for ev in lifetime_events:
        eid = ev.get("employee_id") or ""
        by_emp[eid]["num_orders"] += 1
        by_emp[eid]["commission_inr"] += int(float(ev.get("commission_inr") or 0))
    emp_lookup = {e["id"]: e for e in employees}

    rows = []
    for eid, m in sorted(by_emp.items(), key=lambda x: -x[1]["commission_inr"]):
        emp = emp_lookup.get(eid) if eid else None
        emp_name = emp.get("name") if emp else "Unassigned / partner code"
        rows.append((emp_name, m["num_orders"], m["commission_inr"]))

    employee_table = ""
    if rows:
        body_rows = "".join(
            f'<tr><td style="padding:8px 12px;border-bottom:1px solid #f0ebe0;font-size:13px;color:#0c0c0a;">{name}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #f0ebe0;font-size:13px;color:#525252;text-align:right;font-family:\'Geist Mono\',monospace;">{orders}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #f0ebe0;font-size:13px;color:#0c0c0a;text-align:right;font-family:\'Geist Mono\',monospace;font-weight:600;">₹{_inr(comm)}</td></tr>'
            for name, orders, comm in rows
        )
        employee_table = (
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            'style="background:#fff;border:1px solid #ececec;border-radius:10px;margin-top:8px;">'
            '<tr>'
            '<th style="padding:8px 12px;text-align:left;font-size:10px;font-family:\'Geist Mono\',monospace;text-transform:uppercase;letter-spacing:0.08em;color:#8c7549;background:#fafafa;border-bottom:1px solid #ececec;border-radius:10px 0 0 0;">Rep</th>'
            '<th style="padding:8px 12px;text-align:right;font-size:10px;font-family:\'Geist Mono\',monospace;text-transform:uppercase;letter-spacing:0.08em;color:#8c7549;background:#fafafa;border-bottom:1px solid #ececec;">Sales</th>'
            '<th style="padding:8px 12px;text-align:right;font-size:10px;font-family:\'Geist Mono\',monospace;text-transform:uppercase;letter-spacing:0.08em;color:#8c7549;background:#fafafa;border-bottom:1px solid #ececec;border-radius:0 10px 0 0;">Commission</th>'
            '</tr>' + body_rows + '</table>'
        )
    else:
        employee_table = (
            '<p style="margin:8px 0 0;font-size:13px;color:#8a8a8a;font-style:italic;">'
            "No sales attributed yet. Once your team's first code redemption hits, you'll see them here.</p>"
        )

    week_zero_msg = ""
    if week["num_orders"] == 0:
        week_zero_msg = (
            '<p style="margin:0 0 16px;font-size:14px;line-height:1.6;color:#525252;">'
            "No new sales this week. If your team needs anything from us (collateral, "
            "co-branded one-pagers, demo slots), reply to this email and we'll send it within a day.</p>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Headnote — Partner snapshot</title>
</head>
<body style="margin:0;padding:0;background:#fafafa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0c0c0a;">

<div style="display:none;max-height:0;overflow:hidden;color:transparent;opacity:0;">
  Your week at a glance — sales, commission, payouts.
</div>

<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#fafafa;padding:32px 16px;">
  <tr><td align="center">

    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width:600px;background:#ffffff;border-radius:16px;border:1px solid #ececec;box-shadow:0 6px 24px -8px rgba(0,0,0,0.06);">

      <!-- Header -->
      <tr><td style="padding:28px 36px 18px;border-bottom:1px solid #f0f0f0;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="font-family:Geist,system-ui,sans-serif;font-size:17px;font-weight:600;color:#0c0c0a;letter-spacing:-0.01em;">
              Headnote<span style="color:#c9a96e;">.</span>
            </td>
            <td align="right" style="font-family:'Geist Mono',monospace;font-size:11px;color:#8a8a8a;letter-spacing:0.08em;text-transform:uppercase;">
              Partner snapshot
            </td>
          </tr>
        </table>
      </td></tr>

      <!-- Hero -->
      <tr><td style="padding:32px 36px 16px;">
        <p style="margin:0 0 6px;font-family:'Geist Mono',monospace;font-size:11px;color:#8c7549;letter-spacing:0.14em;text-transform:uppercase;">{week_label}</p>
        <h1 style="margin:0 0 6px;font-family:Geist,system-ui,sans-serif;font-size:26px;line-height:1.15;font-weight:600;letter-spacing:-0.02em;color:#0c0c0a;">
          {first}, your week at Headnote.
        </h1>
        <p style="margin:0 0 14px;font-size:14px;color:#525252;line-height:1.55;">
          Numbers for <strong>{name}</strong>. Reply if anything looks off.
        </p>
      </td></tr>

      <!-- Hero metrics -->
      <tr><td style="padding:0 36px 8px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td valign="top" style="background:#fafafa;border:1px solid #ececec;border-radius:10px;padding:14px 16px;width:33%;">
              <p style="margin:0 0 2px;font-size:22px;font-weight:700;color:#0c0c0a;font-family:Geist,system-ui,sans-serif;letter-spacing:-0.01em;">{week["num_orders"]}</p>
              <p style="margin:0;font-family:'Geist Mono',monospace;font-size:10px;text-transform:uppercase;letter-spacing:0.08em;color:#8c7549;">Sales this week</p>
            </td>
            <td style="width:6px"></td>
            <td valign="top" style="background:#fafafa;border:1px solid #ececec;border-radius:10px;padding:14px 16px;width:33%;">
              <p style="margin:0 0 2px;font-size:22px;font-weight:700;color:#0c0c0a;font-family:Geist,system-ui,sans-serif;letter-spacing:-0.01em;">₹{_inr(week["commission_inr"])}</p>
              <p style="margin:0;font-family:'Geist Mono',monospace;font-size:10px;text-transform:uppercase;letter-spacing:0.08em;color:#8c7549;">Earned this week</p>
            </td>
            <td style="width:6px"></td>
            <td valign="top" style="background:#fafafa;border:1px solid #ececec;border-radius:10px;padding:14px 16px;width:33%;">
              <p style="margin:0 0 2px;font-size:22px;font-weight:700;color:#0c0c0a;font-family:Geist,system-ui,sans-serif;letter-spacing:-0.01em;">₹{_inr(pending)}</p>
              <p style="margin:0;font-family:'Geist Mono',monospace;font-size:10px;text-transform:uppercase;letter-spacing:0.08em;color:#8c7549;">Pending payout</p>
            </td>
          </tr>
        </table>
      </td></tr>

      <!-- Optional zero-message -->
      <tr><td style="padding:8px 36px 0;">{week_zero_msg}</td></tr>

      <!-- Employee leaderboard -->
      <tr><td style="padding:20px 36px 0;">
        <p style="margin:0 0 6px;font-family:'Geist Mono',monospace;font-size:11px;color:#8c7549;letter-spacing:0.12em;text-transform:uppercase;">Your team — lifetime</p>
        {employee_table}
      </td></tr>

      <!-- Lifetime totals -->
      <tr><td style="padding:20px 36px 0;">
        <p style="margin:0 0 6px;font-family:'Geist Mono',monospace;font-size:11px;color:#8c7549;letter-spacing:0.12em;text-transform:uppercase;">Lifetime totals</p>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#fafafa;border:1px solid #ececec;border-radius:10px;">
          <tr>
            <td style="padding:14px 16px;font-size:13.5px;color:#525252;line-height:1.5;">
              <span style="color:#0c0c0a;font-weight:600;">{lifetime["num_orders"]}</span> total sales ·
              <span style="color:#0c0c0a;font-weight:600;">₹{_inr(lifetime["gross_inr"])}</span> gross ·
              <span style="color:#0c0c0a;font-weight:600;">₹{_inr(lifetime["commission_inr"])}</span> total commission earned
              <br><span style="font-size:12px;color:#8a8a8a;">Your current rate: {float(partner.get("commission_pct") or 0):.0f}%</span>
            </td>
          </tr>
        </table>
      </td></tr>

      <!-- Note -->
      <tr><td style="padding:24px 36px;border-top:1px solid #f0f0f0;background:#fafafa;border-radius:0 0 16px 16px;margin-top:24px;">
        <p style="margin:0 0 8px;font-size:13.5px;line-height:1.6;color:#525252;">
          <strong style="color:#0c0c0a;">Payouts</strong> are settled monthly to the bank account on file. If anything looks wrong — missing sale, wrong commission %, a rep we haven't added — just reply.
        </p>
        <p style="margin:0;font-size:13px;color:#8a8a8a;">
          — Ayush, founder @ Headnote · Bhopal
        </p>
      </td></tr>

    </table>

    <!-- Footer -->
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width:600px;margin-top:18px;">
      <tr><td align="center" style="padding:8px 24px 24px;font-size:11px;color:#8a8a8a;line-height:1.6;">
        <p style="margin:0;">
          © 2026 Headnote Private Limited · Made in Bhopal, for Indian courts<br>
          You're receiving this as the authorized distributor contact for {name}.
        </p>
      </td></tr>
    </table>

  </td></tr>
</table>

</body></html>"""


def _build_email_text(*, partner: dict, week_events: list[dict],
                      lifetime_events: list[dict], employees: list[dict]) -> str:
    """Plain-text fallback. Same numbers, no chrome."""
    name = partner.get("name") or "Partner"
    first = name.split()[0] if name else "Partner"
    start, end = _week_window()
    week_label = f"{_date_label(start)} - {_date_label(end)}"

    week = _aggregate(week_events)
    lifetime = _aggregate(lifetime_events)
    pending = sum(
        int(float(e.get("commission_inr") or 0))
        for e in lifetime_events
        if (e.get("payout_status") or "").lower() == "pending"
    )

    lines = [
        f"{first}, your week at Headnote.",
        f"Numbers for {name} ({week_label})",
        "",
        f"THIS WEEK: {week['num_orders']} sales · ₹{_inr(week['commission_inr'])} earned",
        f"PENDING PAYOUT: ₹{_inr(pending)}",
        "",
        "LIFETIME:",
        f"  {lifetime['num_orders']} total sales",
        f"  ₹{_inr(lifetime['gross_inr'])} gross",
        f"  ₹{_inr(lifetime['commission_inr'])} commission earned",
        f"  Rate: {float(partner.get('commission_pct') or 0):.0f}%",
        "",
        "Payouts settle monthly. Reply if anything looks off.",
        "",
        "— Ayush, founder @ Headnote · Bhopal",
    ]
    return "\n".join(lines) + "\n"


def send_one(partner_id: str) -> bool:
    """Send the weekly snapshot to ONE partner. Returns True on success,
    False on no recipient / no API key / send failure.

    Reads everything fresh from Supabase — no caller-passed state.
    """
    partners = _supabase.select(
        "partners",
        params={"id": f"eq.{partner_id}", "select": "*", "limit": "1"},
    )
    if not partners:
        log.warning("partner_weekly: partner %s not found", partner_id)
        return False
    partner = partners[0]
    if partner.get("status") != "active":
        log.info("partner_weekly: skip non-active partner %s (%s)", partner_id, partner.get("status"))
        return False

    to_email = (partner.get("contact_email") or "").strip()
    if not to_email or "@" not in to_email:
        log.warning("partner_weekly: partner %s has no contact_email; skipping", partner_id)
        return False

    employees = _supabase.select(
        "partner_employees",
        params={"partner_id": f"eq.{partner_id}", "select": "id,name,email,status"},
    )

    start, _ = _week_window()
    week_events = _supabase.select(
        "referral_events",
        params={
            "partner_id":  f"eq.{partner_id}",
            "created_at":  f"gte.{start.isoformat()}",
            "select":      "*",
        },
    )
    lifetime_events = _supabase.select(
        "referral_events",
        params={
            "partner_id":  f"eq.{partner_id}",
            "select":      "*",
            "order":       "created_at.desc",
            "limit":       "1000",
        },
    )

    html = _build_email_html(
        partner=partner, week_events=week_events,
        lifetime_events=lifetime_events, employees=employees,
    )
    text = _build_email_text(
        partner=partner, week_events=week_events,
        lifetime_events=lifetime_events, employees=employees,
    )

    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        log.warning("partner_weekly: RESEND_API_KEY not set; would have sent to %s", to_email)
        return False

    try:
        import resend
    except ImportError:
        log.error("partner_weekly: 'resend' package not installed")
        return False

    resend.api_key = api_key
    subject = f"Headnote — your week ({(partner.get('name') or 'Partner').split()[0]})"
    try:
        resend.Emails.send({
            "from":     FROM_EMAIL,
            "to":       [to_email],
            "reply_to": REPLY_TO,
            "subject":  subject,
            "html":     html,
            "text":     text,
            "tags": [
                {"name": "type",    "value": "partner_weekly"},
                {"name": "partner", "value": partner.get("id", "")[:24]},
            ],
        })
        log.info("partner_weekly: sent to %s for partner %s", to_email, partner.get("name"))
        return True
    except Exception as e:
        log.exception("partner_weekly: Resend send failed for %s: %s", to_email, e)
        return False


def send_all(partner_id: Optional[str] = None) -> dict:
    """Send the weekly snapshot to all active partners (or just one if
    `partner_id` is given). Returns a summary dict — never raises."""
    if partner_id:
        ok = send_one(partner_id)
        return {"attempted": 1, "sent": int(ok), "skipped": int(not ok)}

    partners = _supabase.select(
        "partners",
        params={"status": "eq.active", "select": "id"},
    )
    sent = skipped = 0
    for p in partners:
        try:
            if send_one(p["id"]):
                sent += 1
            else:
                skipped += 1
        except Exception:
            log.exception("partner_weekly: unexpected failure for partner %s", p.get("id"))
            skipped += 1
    return {"attempted": len(partners), "sent": sent, "skipped": skipped}
