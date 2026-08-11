"""Hearing reminders to the lawyer's own clients.

The product has asked for this consent since the Matters diary shipped — the
client's mobile box on the matters screen is labelled "for reminders" and there
is a tickbox reading "client consents to hearing reminders" — and until now
nothing in the codebase ever read either field. This package is the other half
of that promise.

Three modules:
  copy.py     the exact words, built from the matter's own fields. No model.
  storage.py  the send log — proof of what went out, and the double-send guard.
  service.py  who is due, and the one-tap batch send.

Two rules run through all of it:

  * A reminder is never composed by a language model. A client who is told the
    wrong hearing date turns up on the wrong day and blames his advocate, and
    no amount of "usually correct" is worth that. Every value in the message is
    a field off the matter; the sentences around them are fixed strings.

  * Nothing is sent without consent, and nothing is skipped silently. A matter
    that cannot be reminded is REPORTED with the reason (no number, no consent,
    already sent) so the lawyer can act on it, rather than quietly falling out
    of the list and leaving him to believe his client was told.
"""
