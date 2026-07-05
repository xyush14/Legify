"""Full drafting-skill injection for the authoring engine.

The authoring system prompt (`HOUSE_STYLE` in author.py) is a *distilled* slice of
the `headnote-legal-drafting` skill — enough to shape output, but it leaves the deep
knowledge (the per-type grounds libraries, the legal tests each application must
satisfy, the BNSS↔CrPC maps, the Kruti-Dev court-format rules) on the shelf.

Per the Drafter Quality Roadmap (§4.2), injecting the ENTIRE skill as a stable,
cached prefix is "half the quality gap". This module loads the skill reference
markdown once and returns it as one string, framed as authoritative reference
knowledge. Placed FIRST in the system prompt, it becomes a byte-identical prefix
across every draft, so DeepSeek's automatic context-cache reads it at ~$0.07/M —
near-free on repeat drafts.

DEPLOYMENT NOTE: `.claude/skills/` is gitignored and does NOT ship to Railway, so
the skill files are mirrored into `headnote/drafter/skill_refs/` (tracked, deployed).
Re-sync after editing the skill with `python scripts/sync_skill_refs.py`.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

# Toggle: set DRAFTER_INJECT_SKILL=0 to fall back to the distilled prompt only
# (e.g. to isolate a regression or shave first-call latency in a demo).
_INJECT = os.environ.get("DRAFTER_INJECT_SKILL", "1").strip().lower() not in ("0", "false", "no", "")

# Deployed copy inside the package (primary), then the live skill dir (local dev).
_PKG_REFS = Path(__file__).parent / "skill_refs"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_LIVE_REFS = _REPO_ROOT / ".claude" / "skills" / "headnote-legal-drafting"

# Load order = pedagogical order: what the engine IS, then format, then the law,
# then per-application specs, then the bail grounds library (the bar), then taxonomy.
_FILES = [
    ("SKILL.md", None),
    ("court-formats.md", "references"),
    ("legal-frameworks.md", "references"),
    ("application-frameworks.md", "references"),
    ("bail.md", "references"),
    ("taxonomy.md", "references"),
]

_PREAMBLE = """=== HEADNOTE LEGAL-DRAFTING SKILL — AUTHORITATIVE REFERENCE ===
This is your complete drafting knowledge base: court-format rules, the grounds
libraries (the numbered "यह कि …" arguments), the legal tests and leading judgments
each application must satisfy, and the BNSS↔CrPC / BNS↔IPC section maps. Use it as
the CONTROLLING authority for HOW to draft — format, structure, which ground
neutralises which limb of a test, correct sections, register.

Two hard rules on how to USE this reference:
  1. It teaches FORMAT, STRUCTURE, GROUNDS REASONING and LAW — never facts. Any
     example names, dates, amounts or citations inside it are illustrative only and
     MUST NOT appear in the draft unless the advocate's own brief supplies them.
  2. Where it conflicts with the operating instructions further below, the specific
     operating instructions and the verified-citation list govern.
"""

_POSTAMBLE = "\n=== END OF SKILL REFERENCE — operating instructions follow ===\n"


def _read(name: str, sub: str | None) -> str:
    """Read one skill file from the deployed copy, falling back to the live dir."""
    for base in (_PKG_REFS, _LIVE_REFS):
        p = (base / sub / name) if sub else (base / name)
        try:
            return p.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, OSError):
            continue
    return ""


@lru_cache(maxsize=1)
def full_skill_context() -> str:
    """The entire skill as one stable string, or "" if injection is off / files
    are unavailable. Cached for the process lifetime so it is byte-identical on
    every call (required for the DeepSeek prefix cache to hit)."""
    if not _INJECT:
        log.info("[drafter] skill injection DISABLED (DRAFTER_INJECT_SKILL=0)")
        return ""
    parts: list[str] = []
    for name, sub in _FILES:
        body = _read(name, sub)
        if body:
            parts.append(f"\n----- {name} -----\n{body}")
    if not parts:
        log.warning("[drafter] skill injection ON but NO skill files found "
                    "(looked in %s and %s) — drafting from the distilled prompt only. "
                    "Run: python scripts/sync_skill_refs.py", _PKG_REFS, _LIVE_REFS)
        return ""
    out = _PREAMBLE + "".join(parts) + _POSTAMBLE
    log.info("[drafter] full skill injected: %d files, ~%dK tokens (cached prefix)",
             len(parts), len(out) // 4000)
    return out


def skill_available() -> bool:
    """True when the skill files were found and injection is enabled — for a
    one-time startup log so a silent no-op in prod is visible."""
    return bool(full_skill_context())
