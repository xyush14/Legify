# Resend email templates

Drop-in templates for the Resend dashboard. Plain HTML + plain-text twin
for every transactional mail Headnote sends.

The codebase already sends these via `headnote/email/*.py` using inline
HTML in the API call. These files exist so you can:

1. **Paste them into Resend's Broadcasts → Templates** for marketing
   broadcasts (Renewal-week campaign, "Section Finder is live" launches,
   etc.) that you author in the dashboard, not in code.
2. **Preview them in Resend's editor** to A/B subject lines and
   preview text without redeploying.
3. **Hand them to a designer / copywriter** for tweaks without them
   touching Python.

The code-side templates in `headnote/email/welcome.py` etc. remain the
source of truth for transactional sends fired from the app.

---

## welcome.html / welcome.txt — Welcome email

Fires when a user finishes onboarding. Triggered from
`POST /api/onboarding/welcome-email` ([onboarding.py:64](../../headnote/api/onboarding.py)).

| Field        | Value |
|--------------|-------|
| **From**     | `Headnote <hello@headnote.in>` |
| **Reply-To** | `hello@headnote.in` |
| **Subject**  | `Welcome to Headnote — three things to try first` |
| **Pre-header** (preview text) | `Verified case research, voice-first drafting, BNSS-mapped templates — live now.` |

**Merge variables**

| Variable | Source | Fallback |
|----------|--------|----------|
| `{{first_name}}` | `user_profiles.name` → first whitespace-split token; if blank, Google `full_name` claim | `there` |
| `{{email}}`      | Supabase `auth.users.email` | (recipient address itself) |

**Pasting into Resend Broadcasts**

1. Resend Dashboard → Broadcasts → Templates → New Template.
2. Name it `welcome-v1`.
3. Copy the contents of `welcome.html` into the HTML editor. The first
   `<!-- … -->` block at the top of the file is documentation — Resend's
   editor will keep it but it won't render.
4. Copy `welcome.txt` into the plain-text tab.
5. Resend uses `{{name_of_field}}` syntax that matches Audience contact
   fields. If your Audience uses different keys (`first_name` vs `name`),
   find-replace in the editor.

**Sending it programmatically (already wired)**

If you ever migrate from the inline HTML in `welcome.py` to Resend's
Template ID API, the swap is one call:

```python
resend.Emails.send({
    "from":     "Headnote <hello@headnote.in>",
    "to":       [to_email],
    "reply_to": "hello@headnote.in",
    "subject":  "Welcome to Headnote — three things to try first",
    "template_id": "tmpl_xxx",          # from Resend dashboard
    "template_data": {
        "first_name": name,
        "email":      to_email,
    },
})
```

Until then, treat these HTML/txt files as the spec and the inline Python
template in `headnote/email/welcome.py` as the live source.

---

## Design constraints (apply to every template)

- **Inline CSS only.** `<style>` tags are stripped by Gmail and Outlook.
- **Table-based layout.** `flex` / `grid` don't survive most email clients.
- **Max-width 600px**, mobile auto-collapses to single column.
- **Absolute URLs only** — `https://headnote.in/...`, never relative.
- **Deep-gold accent (`#8c7549`)** only on small labels and hover states.
  Never on body text.
- **Geist + Geist Mono** in font stacks, with `system-ui` fallback so we
  don't pay for webfont loading inside the email client (most strip them
  anyway).

When you add a new template, drop both `.html` and `.txt` here and
extend this README with a new section matching the welcome one above.
