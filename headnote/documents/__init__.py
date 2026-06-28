"""Document Vault — OCR'd, searchable case documents.

Lawyers carry piles of scanned/handwritten paper: postmortem notes, FIRs,
affidavits, orders, medical-jurist reports. Headnote already OCRs these (the
Groq vision pipeline used for "draft from a document"); this module stops
throwing that transcription away — it persists each upload and makes the whole
pile searchable, by keyword AND by meaning (so OCR noise / paraphrase still
hits).
"""
