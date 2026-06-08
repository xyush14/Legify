"""Comp-access invite email — fired when an admin gifts someone a paid plan.

Trigger
-------
Admin hits POST /admin/access/invite with {email, name, role} → adds a row to
access_grants and calls send_access_invite() here. The recipient signs in via
Google at headnote.in → the entitlements layer auto-activates a real
subscription row for the role (monthly | yearly) and marks the grant consumed.

This email is NOT the standard welcome — that fires AFTER they sign up and
finish onboarding. This one is the "you've been invited, sign in to claim"
message that arrives BEFORE they've created an account.

Without RESEND_API_KEY set, every send becomes a logged no-op so local dev
and CI don't break.
"""

from __future__ import annotations

import logging
import os
from typing import Optional


log = logging.getLogger(__name__)


FROM_EMAIL   = os.environ.get("WELCOME_FROM_EMAIL", "Headnote <hello@headnote.in>")
REPLY_TO     = os.environ.get("WELCOME_REPLY_TO",   "hello@headnote.in")
APP_BASE_URL = (os.environ.get("APP_BASE_URL") or "https://headnote.in").rstrip("/")


_ROLE_COPY = {
    "monthly": ("Monthly",  "30 days", "30 days of unlimited research and drafting."),
    "yearly":  ("Yearly",   "365 days", "A full year of unlimited research and drafting."),
    "founder": ("Founder",  "perpetual", "Perpetual access — everything Headnote ships, no limits."),
    "partner": ("Partner",  "perpetual", "Perpetual access — everything Headnote ships, no limits."),
}


def _build_html(*, name: str, role: str, granted_by_note: str) -> str:
    first = (name or "there").split()[0] or "there"
    plan_title, duration, blurb = _ROLE_COPY.get(role, ("Headnote", "your access window", ""))
    note_block = ""
    if granted_by_note.strip():
        note_block = f"""
        <tr>
          <td style="padding:0 36px 8px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#fafafa;border:1px solid #ececec;border-radius:12px;">
              <tr>
                <td style="padding:16px 20px;">
                  <p style="margin:0 0 4px;font-family:'Geist Mono',ui-monospace,monospace;font-size:10px;color:#8c7549;letter-spacing:0.1em;text-transform:uppercase;">Note from the team</p>
                  <p style="margin:0;font-size:13.5px;line-height:1.55;color:#525252;white-space:pre-wrap;">{granted_by_note}</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Headnote {plan_title} is yours</title>
</head>
<body style="margin:0;padding:0;background:#fafafa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0a0a0a;">

<div style="display:none;max-height:0;overflow:hidden;color:transparent;opacity:0;">
  You've been gifted Headnote {plan_title} — {duration}, complimentary. Sign in to activate.
</div>

<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#fafafa;padding:32px 16px;">
  <tr>
    <td align="center">

      <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width:600px;background:#ffffff;border-radius:16px;border:1px solid #ececec;box-shadow:0 6px 24px -8px rgba(0,0,0,0.06);">

        <!-- Header -->
        <tr>
          <td style="padding:32px 36px 24px;border-bottom:1px solid #f0f0f0;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="vertical-align:middle;">
                  <img src="{APP_BASE_URL}/static/headnote-logo-email.png"
                       width="120" height="21" alt="Headnote"
                       style="display:block;border:0;outline:none;text-decoration:none;height:21px;width:120px;-ms-interpolation-mode:bicubic;" />
                </td>
                <td align="right" style="font-family:'Geist Mono',ui-monospace,monospace;font-size:11px;color:#8a8a8a;letter-spacing:0.08em;text-transform:uppercase;">
                  Invitation
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Hero -->
        <tr>
          <td style="padding:48px 36px 24px;">
            <p style="margin:0 0 12px;font-family:'Geist Mono',ui-monospace,monospace;font-size:11px;color:#8c7549;letter-spacing:0.14em;text-transform:uppercase;">Complimentary access · {duration}</p>
            <h1 style="margin:0 0 18px;font-family:Geist,system-ui,sans-serif;font-size:32px;line-height:1.1;font-weight:600;letter-spacing:-0.025em;color:#0a0a0a;">
              {first}, you've been gifted<br>
              <span style="color:#8c7549;">Headnote {plan_title}.</span>
            </h1>
            <p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:#525252;">
              {blurb} No card required, no trial mechanics — just full access from
              the moment you sign in.
            </p>
          </td>
        </tr>

        {note_block}

        <!-- Big CTA -->
        <tr>
          <td align="center" style="padding:24px 36px 12px;">
            <a href="{APP_BASE_URL}/app" style="display:inline-block;background:#0a0a0a;color:#ffffff;text-decoration:none;font-family:Geist,system-ui,sans-serif;font-size:15px;font-weight:600;padding:14px 32px;border-radius:10px;letter-spacing:0.01em;">
              Sign in to activate
            </a>
            <p style="margin:14px 0 0;font-size:12px;color:#8a8a8a;font-family:'Geist Mono',ui-monospace,monospace;">
              Sign in with Google using <span style="color:#0a0a0a;">this email address</span> — your access activates instantly.
            </p>
          </td>
        </tr>

        <!-- What's unlocked -->
        <tr>
          <td style="padding:20px 36px 32px;">
            <p style="margin:0 0 10px;font-family:'Geist Mono',ui-monospace,monospace;font-size:11px;color:#8c7549;letter-spacing:0.12em;text-transform:uppercase;">What's unlocked</p>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#fafafa;border:1px solid #ececec;border-radius:12px;">
              <tr>
                <td style="padding:18px 22px;font-size:13.5px;line-height:1.6;color:#525252;">
                  <strong style="color:#0a0a0a;">Research</strong> — verified case-law search with paragraph anchors.<br>
                  <strong style="color:#0a0a0a;">Drafting</strong> — photo of FIR → filled bail application in 12 sec.<br>
                  <strong style="color:#0a0a0a;">Voice</strong> — dictate Hindi/English, get court-ready prose.<br>
                  <strong style="color:#0a0a0a;">Smart Drafter</strong> — every template the codebase ships, no per-call cost.
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Reply prompt -->
        <tr>
          <td style="padding:24px 36px;border-top:1px solid #f0f0f0;background:#fafafa;border-radius:0 0 16px 16px;">
            <p style="margin:0;font-size:13.5px;line-height:1.6;color:#525252;">
              <strong style="color:#0a0a0a;">Reply to this email</strong> with any questions
              about how Headnote fits your practice. We read every reply.
            </p>
          </td>
        </tr>

      </table>

      <!-- Footer -->
      <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width:600px;margin-top:18px;">
        <tr>
          <td align="center" style="padding:8px 24px 24px;font-size:11px;color:#8a8a8a;line-height:1.6;">
            <p style="margin:0 0 6px;">
              <a href="{APP_BASE_URL}/terms"   style="color:#8a8a8a;text-decoration:none;margin:0 6px;">Terms</a> ·
              <a href="{APP_BASE_URL}/privacy" style="color:#8a8a8a;text-decoration:none;margin:0 6px;">Privacy</a> ·
              <a href="{APP_BASE_URL}/refund"  style="color:#8a8a8a;text-decoration:none;margin:0 6px;">Refund</a> ·
              <a href="{APP_BASE_URL}/contact" style="color:#8a8a8a;text-decoration:none;margin:0 6px;">Contact</a>
            </p>
            <p style="margin:0;">
              © 2026 Headnote Private Limited · Made in Bhopal, for Indian courts<br>
              Sent to <span style="color:#525252;">{{{{TO}}}}</span> because access was granted to this address.
            </p>
          </td>
        </tr>
      </table>

    </td>
  </tr>
</table>

</body>
</html>"""


def _build_text(*, name: str, role: str, granted_by_note: str) -> str:
    first = (name or "there").split()[0] or "there"
    plan_title, duration, blurb = _ROLE_COPY.get(role, ("Headnote", "your access window", ""))
    lines = [
        f"{first}, you've been gifted Headnote {plan_title}.",
        f"Complimentary access for {duration}.",
        "",
        blurb,
        "",
        f"Sign in to activate: {APP_BASE_URL}/app",
        "Use Google sign-in with the email this message arrived at.",
        "",
        "What's unlocked:",
        "  - Research — verified case-law search with paragraph anchors",
        "  - Drafting — photo of FIR -> filled bail application in 12 sec",
        "  - Voice — dictate Hindi/English, get court-ready prose",
        "  - Smart Drafter — every template the codebase ships, no per-call cost",
        "",
    ]
    if granted_by_note.strip():
        lines.extend(["NOTE FROM THE TEAM:", f"  {granted_by_note}", ""])
    lines.extend([
        "Reply to this email with any questions. We read every reply.",
        "",
        "---",
        f"Terms:   {APP_BASE_URL}/terms",
        f"Privacy: {APP_BASE_URL}/privacy",
        f"Refund:  {APP_BASE_URL}/refund",
        f"Contact: {APP_BASE_URL}/contact",
        "(c) 2026 Headnote Private Limited",
    ])
    return "\n".join(lines) + "\n"


def send_access_invite(
    *,
    to_email: str,
    name: Optional[str] = None,
    role: str = "monthly",
    note: str = "",
) -> bool:
    """Send the comp-access invite email. Returns True if Resend accepted the
    send, False on hard failure / missing config. Never raises."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        log.warning(
            "send_access_invite: RESEND_API_KEY not set — skipping email to %s (role=%s)",
            to_email, role,
        )
        return False
    if not to_email or "@" not in to_email:
        log.warning("send_access_invite: invalid recipient %r", to_email)
        return False
    if role not in _ROLE_COPY:
        log.warning("send_access_invite: unknown role %r; defaulting to monthly", role)
        role = "monthly"

    try:
        import resend
    except ImportError:
        log.error("send_access_invite: 'resend' package not installed")
        return False

    resend.api_key = api_key
    plan_title = _ROLE_COPY[role][0]
    subject = f"You've been gifted Headnote {plan_title} — sign in to activate"
    html = _build_html(name=name or "", role=role, granted_by_note=note or "").replace("{{TO}}", to_email)
    text = _build_text(name=name or "", role=role, granted_by_note=note or "")

    try:
        resend.Emails.send({
            "from":     FROM_EMAIL,
            "to":       [to_email],
            "reply_to": REPLY_TO,
            "subject":  subject,
            "html":     html,
            "text":     text,
            "tags": [
                {"name": "type",    "value": "access_invite"},
                {"name": "role",    "value": role},
                {"name": "version", "value": "v1"},
            ],
        })
        log.info("send_access_invite: sent to %s role=%s", to_email, role)
        return True
    except Exception as e:
        log.exception("send_access_invite: Resend send failed for %s: %s", to_email, e)
        return False
