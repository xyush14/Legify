"""Recorder / consultations — record a lawyer–client conversation, transcribe
it, and turn it into a structured legal work-product report (facts, issues,
next steps) that hands off to the drafter.

See headnote/consultations/storage.py (persistence) and report.py (the
transcript → structured-report engine). The HTTP surface is
headnote/api/consultations.py.
"""
