"""Welcome email — fired once after a user completes onboarding.

Design constraints:
  - Table-based layout (Gmail / Outlook strip flex / grid).
  - Inline CSS only — most clients ignore <style> tags or strip them.
  - Single-column on mobile (max-width 600px).
  - All images via absolute URLs (https://headnote.in/...).
  - Plain-text fallback for spam-filter heuristics.

Resend docs: https://resend.com/docs/send-with-python
"""

from __future__ import annotations

import logging
import os
from typing import Optional


log = logging.getLogger(__name__)


# Brand
FROM_EMAIL   = os.environ.get("WELCOME_FROM_EMAIL", "Headnote <hello@headnote.in>")
REPLY_TO     = os.environ.get("WELCOME_REPLY_TO",   "hello@headnote.in")
APP_BASE_URL = (os.environ.get("APP_BASE_URL") or "https://headnote.in").rstrip("/")


def _build_html(name: str) -> str:
    """Render the welcome HTML. `name` is the user's first name."""
    first = (name or "there").split()[0] or "there"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Welcome to Headnote</title>
</head>
<body style="margin:0;padding:0;background:#fafafa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0a0a0a;">

<!-- Pre-header (hidden, shows in inbox preview) -->
<div style="display:none;max-height:0;overflow:hidden;color:transparent;opacity:0;">
  Verified case research, voice-first drafting, BNSS-mapped templates — all live on your account.
</div>

<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#fafafa;padding:32px 16px;">
  <tr>
    <td align="center">

      <!-- ===== Outer card ===== -->
      <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width:600px;background:#ffffff;border-radius:16px;border:1px solid #ececec;box-shadow:0 6px 24px -8px rgba(0,0,0,0.06);">

        <!-- Header band -->
        <tr>
          <td style="padding:32px 36px 24px;border-bottom:1px solid #f0f0f0;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="font-family:Geist,system-ui,sans-serif;font-size:18px;font-weight:600;color:#0a0a0a;letter-spacing:-0.01em;">
                  Headnote<span style="color:#c9a96e;">.</span>
                </td>
                <td align="right" style="font-family:'Geist Mono',monospace;font-size:11px;color:#8a8a8a;letter-spacing:0.08em;text-transform:uppercase;">
                  v0.4 · live
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Hero -->
        <tr>
          <td style="padding:48px 36px 24px;">
            <p style="margin:0 0 12px;font-family:'Geist Mono',monospace;font-size:11px;color:#8c7549;letter-spacing:0.14em;text-transform:uppercase;">Welcome aboard</p>
            <h1 style="margin:0 0 18px;font-family:Geist,system-ui,sans-serif;font-size:32px;line-height:1.1;font-weight:600;letter-spacing:-0.025em;color:#0a0a0a;">
              {first}, you're in.<br>
              <span style="color:#8c7549;">Let's win your next matter.</span>
            </h1>
            <p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:#525252;">
              Headnote is now active on your account. Below are three things worth
              opening in your first session — each takes under a minute.
            </p>
          </td>
        </tr>

        <!-- Feature 1: Research -->
        <tr>
          <td style="padding:8px 36px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#fafafa;border:1px solid #ececec;border-radius:12px;padding:0;">
              <tr>
                <td style="padding:20px 22px;">
                  <p style="margin:0 0 6px;font-family:'Geist Mono',monospace;font-size:10px;color:#8c7549;letter-spacing:0.1em;text-transform:uppercase;">01 · Research</p>
                  <h2 style="margin:0 0 8px;font-family:Geist,system-ui,sans-serif;font-size:18px;font-weight:600;color:#0a0a0a;letter-spacing:-0.015em;">
                    The precedent your opponent didn't find.
                  </h2>
                  <p style="margin:0 0 12px;font-size:13.5px;line-height:1.55;color:#525252;">
                    Type a situation. Get 3–5 verified authorities — every case ID,
                    paragraph anchor, and quoted phrase checked against the source
                    judgment. No hallucinations.
                  </p>
                  <a href="{APP_BASE_URL}/app" style="display:inline-block;font-family:'Geist Mono',monospace;font-size:12px;font-weight:500;color:#0a0a0a;text-decoration:none;border:1px solid #0a0a0a;padding:7px 14px;border-radius:6px;">
                    Try a search →
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Feature 2: Drafting -->
        <tr>
          <td style="padding:12px 36px 0;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#fafafa;border:1px solid #ececec;border-radius:12px;">
              <tr>
                <td style="padding:20px 22px;">
                  <p style="margin:0 0 6px;font-family:'Geist Mono',monospace;font-size:10px;color:#8c7549;letter-spacing:0.1em;text-transform:uppercase;">02 · Drafting</p>
                  <h2 style="margin:0 0 8px;font-family:Geist,system-ui,sans-serif;font-size:18px;font-weight:600;color:#0a0a0a;letter-spacing:-0.015em;">
                    Photo of FIR → filled bail application.
                  </h2>
                  <p style="margin:0 0 12px;font-size:13.5px;line-height:1.55;color:#525252;">
                    Snap any NCRB I.I.F.-I FIR on your phone. Accused, sections, PS,
                    narrative — auto-extracted in 6–12 seconds, in Hindi or English.
                    Then one click to a print-ready PDF.
                  </p>
                  <a href="{APP_BASE_URL}/draft/bail" style="display:inline-block;font-family:'Geist Mono',monospace;font-size:12px;font-weight:500;color:#0a0a0a;text-decoration:none;border:1px solid #0a0a0a;padding:7px 14px;border-radius:6px;">
                    Open bail drafter →
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Feature 3: Voice -->
        <tr>
          <td style="padding:12px 36px 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#fafafa;border:1px solid #ececec;border-radius:12px;">
              <tr>
                <td style="padding:20px 22px;">
                  <p style="margin:0 0 6px;font-family:'Geist Mono',monospace;font-size:10px;color:#8c7549;letter-spacing:0.1em;text-transform:uppercase;">03 · Voice</p>
                  <h2 style="margin:0 0 8px;font-family:Geist,system-ui,sans-serif;font-size:18px;font-weight:600;color:#0a0a0a;letter-spacing:-0.015em;">
                    Dictate the facts. File the application.
                  </h2>
                  <p style="margin:0 0 12px;font-size:13.5px;line-height:1.55;color:#525252;">
                    Tap the mic on any long-text field. Speak Hindi, English, or the
                    mix lawyers actually speak. Headnote turns it into court-ready
                    prose in 4 seconds.
                  </p>
                  <a href="{APP_BASE_URL}/draft/smart" style="display:inline-block;font-family:'Geist Mono',monospace;font-size:12px;font-weight:500;color:#0a0a0a;text-decoration:none;border:1px solid #0a0a0a;padding:7px 14px;border-radius:6px;">
                    Try Smart Drafter →
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Big CTA -->
        <tr>
          <td align="center" style="padding:0 36px 40px;">
            <a href="{APP_BASE_URL}/app" style="display:inline-block;background:#0a0a0a;color:#ffffff;text-decoration:none;font-family:Geist,system-ui,sans-serif;font-size:15px;font-weight:600;padding:14px 32px;border-radius:10px;letter-spacing:0.01em;">
              Open Headnote
            </a>
            <p style="margin:14px 0 0;font-size:12px;color:#8a8a8a;font-family:'Geist Mono',monospace;">
              You're on the <span style="color:#0a0a0a;">Demo plan</span> — 3 days, no card required.
            </p>
          </td>
        </tr>

        <!-- Founder note -->
        <tr>
          <td style="padding:24px 36px;border-top:1px solid #f0f0f0;background:#fafafa;border-radius:0 0 16px 16px;">
            <p style="margin:0 0 8px;font-size:13.5px;line-height:1.6;color:#525252;">
              <strong style="color:#0a0a0a;">Reply to this email</strong> if something's broken or
              missing. It lands on the founder's phone, not a ticket queue.
            </p>
            <p style="margin:0;font-size:13px;color:#8a8a8a;">
              — Ayush, founder @ Headnote · Bhopal
            </p>
          </td>
        </tr>

      </table>

      <!-- ===== Footer ===== -->
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
              Sent to <span style="color:#525252;">{{TO}}</span> because you signed up at headnote.in.
            </p>
          </td>
        </tr>
      </table>

    </td>
  </tr>
</table>

</body>
</html>"""


def _build_text(name: str) -> str:
    """Plain-text fallback. Some spam filters look for this; some clients
    show it instead of HTML (text-only mail readers, accessibility tools)."""
    first = (name or "there").split()[0] or "there"
    return (
        f"{first}, you're in.\n"
        f"Let's win your next matter.\n\n"
        f"Headnote is now active on your account. Three things worth trying first:\n\n"
        f"1. RESEARCH — the precedent your opponent didn't find.\n"
        f"   Type a situation, get 3-5 verified authorities. Every cite checked.\n"
        f"   → {APP_BASE_URL}/app\n\n"
        f"2. DRAFTING — photo of FIR -> filled bail application.\n"
        f"   NCRB I.I.F.-I extracted in 6-12 seconds. Hindi or English.\n"
        f"   → {APP_BASE_URL}/draft/bail\n\n"
        f"3. VOICE — dictate the facts, file the application.\n"
        f"   Tap the mic, speak Hindi/English/the mix lawyers actually speak.\n"
        f"   → {APP_BASE_URL}/draft/smart\n\n"
        f"Open Headnote:\n{APP_BASE_URL}/app\n\n"
        f"You're on the Demo plan — 3 days, no card required.\n\n"
        f"Reply to this email if something's broken or missing. It lands on\n"
        f"the founder's phone, not a ticket queue.\n\n"
        f"— Ayush, founder @ Headnote · Bhopal\n\n"
        f"---\n"
        f"Terms:   {APP_BASE_URL}/terms\n"
        f"Privacy: {APP_BASE_URL}/privacy\n"
        f"Refund:  {APP_BASE_URL}/refund\n"
        f"Contact: {APP_BASE_URL}/contact\n"
        f"© 2026 Headnote Private Limited · Made in Bhopal\n"
    )


def send_welcome(to_email: str, name: Optional[str] = None) -> bool:
    """Send the welcome email. Idempotency is enforced by the caller (the
    /api/onboarding/welcome-email endpoint checks user_profiles.welcome_sent).

    Returns True if the send succeeded (or was attempted), False on hard
    failure / missing config. Never raises — email failures must not block
    the user's onboarding flow.
    """
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        log.warning(
            "send_welcome: RESEND_API_KEY not set — skipping email to %s. "
            "Set the env var on Railway to enable transactional email.",
            to_email,
        )
        return False
    if not to_email or "@" not in to_email:
        log.warning("send_welcome: invalid recipient %r — skipping", to_email)
        return False

    try:
        import resend
    except ImportError:
        log.error("send_welcome: 'resend' package not installed — add to requirements.txt")
        return False

    resend.api_key = api_key
    html = _build_html(name or "").replace("{{TO}}", to_email)
    text = _build_text(name or "")

    try:
        resend.Emails.send({
            "from":     FROM_EMAIL,
            "to":       [to_email],
            "reply_to": REPLY_TO,
            "subject":  "Welcome to Headnote — three things to try first",
            "html":     html,
            "text":     text,
            "tags": [
                {"name": "type",     "value": "welcome"},
                {"name": "version",  "value": "v1"},
            ],
        })
        log.info("send_welcome: sent to %s (name=%s)", to_email, name or "?")
        return True
    except Exception as e:
        # Never raise — email failure must not block onboarding.
        log.exception("send_welcome: Resend API call failed for %s: %s", to_email, e)
        return False
