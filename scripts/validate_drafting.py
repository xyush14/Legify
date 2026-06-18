#!/usr/bin/env python3
"""Structural validation for the Headnote drafting catalogue + generation
pipeline. Catches the template/format-spec inconsistencies that used to slip
through (empty specs, dangling dedupe redirects, malformed fields, a missing
mandatory header or output sanitizer).

Run:  python3 scripts/validate_drafting.py     # exit 0 = clean, 1 = errors
Safe to wire into CI (.github/workflows/tests.yml).
"""
from __future__ import annotations
import sys
from collections import Counter

sys.path.insert(0, ".")

errs: list[str] = []
warns: list[str] = []

from headnote.drafter.compose_templates import TEMPLATES  # noqa: E402

for tid, t in TEMPLATES.items():
    if t.get("id") and t["id"] != tid:
        errs.append(f"{tid}: 'id' field ({t['id']}) != registry key")
    redirect = (t.get("redirect_url") or "").strip()
    fs = (t.get("format_spec") or "").strip()
    if not redirect and len(fs) < 50:
        errs.append(f"{tid}: no redirect_url and format_spec is empty/trivial ({len(fs)} chars)")
    for i, fld in enumerate(t.get("fields", []) or []):
        if not isinstance(fld, dict) or "key" not in fld:
            errs.append(f"{tid}: field #{i} is malformed (missing 'key')")
    if redirect.startswith("/draft/template/"):
        target = redirect.split("/draft/template/")[1].split("?")[0].strip("/")
        if target not in TEMPLATES:
            errs.append(f"{tid}: redirect target '{target}' is not in the catalogue")

# ---- generation pipeline invariants ----
try:
    comp = open("headnote/drafter/compose.py", encoding="utf-8").read()
    if "MANDATORY TOP-SECTION" not in comp:
        errs.append("compose.py: the mandatory standard-header block is missing from the generator")
    if "_strip_llm_wrapping" not in comp:
        errs.append("compose.py: the output sanitizer (_strip_llm_wrapping) is missing")
except OSError as e:
    errs.append(f"compose.py unreadable: {e}")

# ---- skill spec present (local only; .claude/ is gitignored) ----
try:
    cf = open(".claude/skills/headnote-legal-drafting/references/court-formats.md", encoding="utf-8").read()
    if "Standard top-section" not in cf:
        warns.append("court-formats.md: the codified standard top-section is missing")
except OSError:
    warns.append("court-formats.md not present (expected in CI — skill is gitignored)")

q = Counter((t.get("quality") or "untagged") for t in TEMPLATES.values())
print(f"catalogue: {len(TEMPLATES)} templates   quality={dict(q)}")
print(f"errors={len(errs)}  warnings={len(warns)}")
for e in errs:
    print("  ERROR  ", e)
for w in warns:
    print("  warn   ", w)
print("OK — drafting catalogue is structurally sound." if not errs else "FAILED")
sys.exit(1 if errs else 0)
