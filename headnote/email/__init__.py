"""Transactional email — Resend-backed.

Public surface:
    send_welcome(to_email, name)        -> bool   (welcome.py)
    send_assist_request(...)            -> bool   (assist.py)

Without RESEND_API_KEY set, every send becomes a logged no-op so local
dev and CI don't break. Production must set the env var.
"""

from headnote.email.welcome import send_welcome  # noqa: F401
from headnote.email.assist  import send_assist_request  # noqa: F401
