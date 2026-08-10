#!/usr/bin/env python3
"""
notion_sync.py — compute the git commits not yet mirrored into the Notion Updates Log.

This powers the daily "Notion sync" task. It is deterministic and does NOT touch
Notion itself: the scheduled Claude agent reads `pending` output, creates the
Updates Log rows via the Notion MCP, then calls `mark <sha>` to advance the marker.
That split keeps the sync idempotent — a commit is never logged twice, and if a run
fails before marking, the next run simply retries (no data loss).

Usage:
    python scripts/notion_sync.py pending [--max N]   # JSON list of unsynced commits
    python scripts/notion_sync.py mark <sha>          # record <sha> as last synced
    python scripts/notion_sync.py state               # show the current marker

State is stored in .notion_sync_state.json at the repo root (gitignored).
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

STATE = Path(__file__).resolve().parent.parent / ".notion_sync_state.json"
DEFAULT_MAX = 25
FALLBACK_COUNT = 15  # if no marker exists yet, look back this many commits

# ASCII unit/record separators keep commit subjects/bodies parse-safe.
_US, _RS = "\x1f", "\x1e"
_FMT = f"%H{_US}%cI{_US}%s{_US}%b{_RS}"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True)


def _load_marker() -> str | None:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text()).get("last_sha")
        except Exception:
            return None
    return None


def pending(max_n: int) -> list[dict]:
    marker = _load_marker()
    if marker:
        out = _git("log", f"{marker}..HEAD", f"--pretty=format:{_FMT}")
    else:
        out = _git("log", f"-n{FALLBACK_COUNT}", f"--pretty=format:{_FMT}")

    commits: list[dict] = []
    for rec in out.split(_RS):
        rec = rec.strip()
        if not rec:
            continue
        parts = rec.split(_US)
        sha, date, subj = parts[0], parts[1], parts[2]
        body = parts[3].strip() if len(parts) > 3 else ""
        commits.append(
            {
                "sha": sha[:10],
                "full_sha": sha,
                "date": date[:10],
                "subject": subj,
                "body": body,
            }
        )
    return commits[:max_n]


def mark(sha: str) -> None:
    STATE.write_text(
        json.dumps(
            {
                "last_sha": sha,
                "marked_at": datetime.datetime.now().isoformat(timespec="seconds"),
            },
            indent=2,
        )
    )


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1

    cmd = args[0]
    if cmd == "pending":
        max_n = DEFAULT_MAX
        if "--max" in args:
            max_n = int(args[args.index("--max") + 1])
        print(json.dumps(pending(max_n), ensure_ascii=False, indent=2))
    elif cmd == "mark":
        if len(args) < 2:
            print("usage: notion_sync.py mark <sha>")
            return 1
        mark(args[1])
        print(f"marked {args[1]}")
    elif cmd == "state":
        print(json.dumps({"last_sha": _load_marker()}, indent=2))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
