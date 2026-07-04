"""Cases — CNR-driven case folders that pre-fill the drafter.

A lawyer enters a CNR (the 16-character eCourts Case Number Record); we fetch
the case from a third-party eCourts API (``ecourts_client``), store a per-user
case record (``storage``), and let them generate a court draft pre-filled with
that case's parties / court / sections (``mapping``).

Strategic note (2026-06-24): the CNR→fetch→folder part is commoditised. The
differentiator is the LAST step — turning a fetched case into a one-click,
pre-filled bail / discharge draft on Headnote's own drafter. No CNR tracker
without a drafting engine can do that. See memory: project-cases-cnr.
"""
