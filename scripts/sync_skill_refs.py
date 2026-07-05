#!/usr/bin/env python3
"""Mirror the headnote-legal-drafting skill into the deployed package copy.

`.claude/skills/` is gitignored and does NOT ship to Railway, but the drafter
injects the full skill at runtime (headnote/drafter/skill_context.py). So the
skill reference markdown is mirrored into headnote/drafter/skill_refs/ (tracked).

Run this after editing the skill so the deployed drafter sees the update:

    python scripts/sync_skill_refs.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / ".claude" / "skills" / "headnote-legal-drafting"
DST = ROOT / "headnote" / "drafter" / "skill_refs"

FILES = [
    "SKILL.md",
    "references/court-formats.md",
    "references/legal-frameworks.md",
    "references/application-frameworks.md",
    "references/bail.md",
    "references/taxonomy.md",
]


def main() -> int:
    if not SRC.exists():
        print(f"! source skill dir not found: {SRC}", file=sys.stderr)
        return 1
    DST.mkdir(parents=True, exist_ok=True)
    n = 0
    for rel in FILES:
        src = SRC / rel
        if not src.exists():
            print(f"  skip (missing): {rel}")
            continue
        # Flatten references/*.md into the package dir (loader looks there).
        shutil.copy2(src, DST / Path(rel).name)
        n += 1
        print(f"  synced: {rel}")
    print(f"done — {n} file(s) → {DST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
