"""Send each lawyer their daily cause-list link over WhatsApp + email.

Morning: "here's today's list — print it, write next dates in court."
Evening: "back from court? upload the marked sheet so we settle your diary."

Both messages carry ONE tokenised link (headnote/cases/daily_links.py) to
/d/<token> — a no-login page that shows that date's list, prints it, and accepts
the marked-sheet upload. No PDF attachment needed (the page prints client-side).

Driven by POST /admin/cron/send-daily-causelist (external scheduler). dry_run
returns the recipient list without sending, so you can preview safely.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os

from headnote.cases import daily_links
from headnote.cases import storage as cases_storage
from headnote.cases import dateutil as case_dates
from headnote.entitlements import _supabase

log = logging.getLogger(__name__)

APP_BASE_URL = (os.environ.get("APP_BASE_URL") or "https://headnote.in").rstrip("/")
FROM_EMAIL = os.environ.get("WELCOME_FROM_EMAIL", "Headnote <hello@headnote.in>")
REPLY_TO = os.environ.get("WELCOME_REPLY_TO", "hello@headnote.in")


def _norm_phone(p: str) -> str:
    p = (p or "").strip().replace(" ", "").replace("-", "")
    if not p:
        return ""
    if p.startswith("+"):
        return p
    digits = "".join(ch for ch in p if ch.isdigit())
    if len(digits) == 10:            # bare Indian mobile → +91
        return "+91" + digits
    return "+" + digits


def _recipients(only_user_id=None):
    """[(user_id, phone, email, name)] for lawyers we can reach."""
    if only_user_id:
        rows = _supabase.select("user_profiles",
                                params={"id": f"eq.{only_user_id}", "select": "id,phone", "limit": "1"})
    else:
        rows = _supabase.select("user_profiles", params={"select": "id,phone", "limit": "2000"})
    out = []
    for r in rows:
        uid = r.get("id")
        if not uid:
            continue
        phone = _norm_phone(r.get("phone") or "")
        email, name = "", ""
        try:
            from headnote.email.renewal import _lookup_email
            email, name = _lookup_email(uid)
        except Exception:  # noqa: BLE001
            pass
        if phone or email:
            out.append((uid, phone, email, name))
    return out


def _day_count(user_id, date_iso: str) -> int:
    rows = cases_storage.list_cases(user_id=user_id, limit=500)
    return sum(1 for r in rows
               if case_dates.to_iso(r.get("next_hearing_date")) == date_iso)


def _copy(name: str, date_label: str, link: str):
    """One evening message: settle today + print tomorrow, from the same link."""
    hi = f" {name}" if name else ""
    wa = (f"🌙 Good evening{hi}. Time to settle your diary for {date_label} — upload the "
          f"cause list you marked in court, and print tomorrow's list to carry. Both here:\n{link}")
    subj = f"Settle today & print tomorrow — {date_label}"
    html = (f"<div style='font-family:Arial,sans-serif;max-width:520px;margin:0 auto;color:#1a1a1a'>"
            f"<p>Good evening{hi}. Settle your diary for {date_label} — upload the marked "
            f"cause list, and print tomorrow's list to carry to court.</p>"
            f"<p><a href='{link}' style='display:inline-block;background:#1a1a1a;color:#fff;"
            f"text-decoration:none;padding:12px 20px;border-radius:8px'>Open your court diary</a></p>"
            f"<p style='color:#888;font-size:12px'>headnote · your diary, self-updating</p></div>")
    return wa, subj, html


def _send_email(to: str, subject: str, html: str, text: str) -> bool:
    if not (to and os.environ.get("RESEND_API_KEY")):
        return False
    try:
        import resend
        resend.api_key = os.environ["RESEND_API_KEY"]
        resend.Emails.send({"from": FROM_EMAIL, "to": [to], "reply_to": REPLY_TO,
                            "subject": subject, "html": html, "text": text,
                            "tags": [{"name": "type", "value": "daily_causelist"}]})
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("daily causelist email to %s failed: %s", to, e)
        return False


def _send_whatsapp(to: str, body: str) -> bool:
    if not to:
        return False
    try:
        from headnote.whatsapp import client as wa
        wa.send_text(to, body)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("daily causelist whatsapp to %s failed: %s", to, e)
        return False


def _next_day(iso: str) -> str:
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return (_dt.date(y, m, d) + _dt.timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return iso


def send_daily_causelists(*, slot: str = "evening", dry_run: bool = False,
                          only_user_id=None, date_iso=None) -> dict:
    """One evening send per lawyer: settle today + print tomorrow, via one link.
    Messages every reachable lawyer who has cases TODAY (to settle) or TOMORROW (to
    print). `slot` is accepted for cron compatibility but the copy is unified."""
    settle_date = date_iso or case_dates.today_iso()
    prep_date = _next_day(settle_date)
    date_label = settle_date
    sent_wa = sent_email = skipped = 0
    preview = []
    for uid, phone, email, name in _recipients(only_user_id):
        c_today = _day_count(uid, settle_date)
        c_tomorrow = _day_count(uid, prep_date)
        if c_today == 0 and c_tomorrow == 0 and not only_user_id:
            skipped += 1
            continue                       # nothing to settle or print → don't nudge
        token = daily_links.make_token(uid, settle_date)   # page derives tomorrow
        link = f"{APP_BASE_URL}/d/{token}"
        wa_body, subj, html = _copy(name, date_label, link)
        if dry_run:
            preview.append({"user_id": uid, "phone": phone, "email": email,
                            "settle_today": c_today, "print_tomorrow": c_tomorrow, "link": link})
            continue
        if _send_whatsapp(phone, wa_body):
            sent_wa += 1
        if _send_email(email, subj, html, wa_body):
            sent_email += 1
    return {"ok": True, "date": settle_date, "prep_date": prep_date, "dry_run": dry_run,
            "whatsapp_sent": sent_wa, "email_sent": sent_email,
            "skipped_no_cases": skipped,
            **({"preview": preview} if dry_run else {})}
