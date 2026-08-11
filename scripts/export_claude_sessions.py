#!/usr/bin/env python3
"""Export Claude Code session transcripts to plain Markdown.

Claude Code stores every session as JSON Lines on this machine, under
`~/.claude/projects/<slugified-project-path>/<session-uuid>.jsonl`. That format
is Claude-specific: no other tool (Codex, Cursor, Gemini CLI, a plain text
editor) can read it usefully. This script converts each transcript into one
Markdown file plus an INDEX, so the history survives Claude Code itself.

It is READ-ONLY with respect to ~/.claude — it never writes or deletes there.

Usage
-----
    python3 scripts/export_claude_sessions.py                    # this project
    python3 scripts/export_claude_sessions.py --all-projects     # every project
    python3 scripts/export_claude_sessions.py --out ~/somewhere
    python3 scripts/export_claude_sessions.py --thinking         # keep reasoning

Output
------
    <out>/INDEX.md                       one row per session, newest first
    <out>/sessions/YYYY-MM-DD--slug--<id8>.md

WARNING: transcripts contain whatever was on screen during the session —
API keys read from .env, client documents, personal emails. The export is as
sensitive as the sessions were. Keep it OUT of any public repository.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

HOME = Path.home()
PROJECTS = HOME / ".claude" / "projects"

# Injected by the harness, not typed by the human — noise in a readable export.
SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
COMMAND_WRAPPER = re.compile(r"<(command-name|command-message|command-args|local-command-[a-z]+)>.*?</\1>", re.DOTALL)


def slug(text: str, limit: int = 60) -> str:
    text = re.sub(r"\s+", "-", text.strip().lower())
    text = re.sub(r"[^a-z0-9\-]", "", text)
    return re.sub(r"-+", "-", text).strip("-")[:limit] or "untitled"


def clean(text: str) -> str:
    text = SYSTEM_REMINDER.sub("", text)
    text = COMMAND_WRAPPER.sub("", text)
    return text.strip()


def blocks_of(message: dict) -> list:
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content if isinstance(content, list) else []


def tool_line(block: dict) -> str:
    """One-line summary of a tool call. The full input would drown the prose."""
    name = block.get("name", "tool")
    inp = block.get("input") or {}
    for key in ("file_path", "path", "command", "pattern", "url", "prompt", "query", "skill"):
        val = inp.get(key)
        if isinstance(val, str) and val.strip():
            one = " ".join(val.split())
            return f"`{name}` — {one[:160]}{'…' if len(one) > 160 else ''}"
    return f"`{name}`"


def read_session(path: Path) -> dict | None:
    rows = []
    with path.open(errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        return None

    meta = {
        "id": path.stem,
        "title": None,
        "first_prompt": None,
        "started": None,
        "ended": None,
        "branch": None,
        "cwd": None,
        "version": None,
        "entrypoint": None,
        "bytes": path.stat().st_size,
        "human_turns": 0,
        "tool_calls": 0,
    }
    parts: list[str] = []

    for row in rows:
        stamp = row.get("timestamp")
        if stamp:
            meta["started"] = meta["started"] or stamp
            meta["ended"] = stamp
        for field in ("gitBranch", "cwd", "version", "entrypoint"):
            if row.get(field) and not meta[field.lower() if field != "gitBranch" else "branch"]:
                meta["branch" if field == "gitBranch" else field.lower()] = row[field]
        if row.get("type") == "ai-title" and row.get("aiTitle"):
            meta["title"] = row["aiTitle"]

        kind = row.get("type")
        if kind not in ("user", "assistant"):
            continue
        if row.get("isSidechain"):
            continue  # subagent chatter, not the conversation
        message = row.get("message")
        if not isinstance(message, dict):
            continue

        when = (stamp or "")[11:16]

        if kind == "user":
            text = "\n\n".join(
                clean(b.get("text", "")) for b in blocks_of(message) if b.get("type") == "text"
            ).strip()
            images = sum(1 for b in blocks_of(message) if b.get("type") == "image")
            if not text and images:
                text = f"_({images} image(s) pasted)_"
            if not text:
                continue  # pure tool_result turn
            meta["human_turns"] += 1
            meta["first_prompt"] = meta["first_prompt"] or " ".join(text.split())[:200]
            parts.append(f"### 🧑 Ayush · {when}\n\n{text}\n")
            continue

        chunks = []
        for block in blocks_of(message):
            btype = block.get("type")
            if btype == "text" and block.get("text", "").strip():
                chunks.append(clean(block["text"]))
            elif btype == "thinking" and KEEP_THINKING and block.get("thinking", "").strip():
                chunks.append("<details><summary>reasoning</summary>\n\n"
                              + block["thinking"].strip() + "\n\n</details>")
            elif btype == "tool_use":
                meta["tool_calls"] += 1
                chunks.append("→ " + tool_line(block))
        body = "\n\n".join(c for c in chunks if c).strip()
        if body:
            parts.append(f"### 🤖 Claude · {when}\n\n{body}\n")

    meta["body"] = "\n".join(parts)
    return meta


def write_session(meta: dict, out_dir: Path) -> Path:
    day = (meta["started"] or "0000-00-00")[:10]
    name = f"{day}--{slug(meta['title'] or meta['first_prompt'] or 'untitled')}--{meta['id'][:8]}.md"
    dest = out_dir / name
    header = [
        f"# {meta['title'] or (meta['first_prompt'] or 'Untitled session')[:80]}",
        "",
        f"- **Session id:** `{meta['id']}`",
        f"- **When:** {meta['started']} → {meta['ended']}",
        f"- **Branch:** `{meta['branch'] or '—'}`",
        f"- **Project:** `{meta['cwd'] or '—'}`",
        f"- **Claude Code:** {meta['version'] or '—'} ({meta['entrypoint'] or '—'})",
        f"- **Turns:** {meta['human_turns']} human · {meta['tool_calls']} tool calls",
        "",
        "---",
        "",
    ]
    dest.write_text("\n".join(header) + meta["body"], encoding="utf-8")
    return dest


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}GB"


def main() -> None:
    global KEEP_THINKING
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HOME / "Documents" / "Headnote-AI-Archive"),
                    help="destination folder (default: ~/Documents/Headnote-AI-Archive)")
    ap.add_argument("--project", default=None,
                    help="project path to export (default: current working directory)")
    ap.add_argument("--all-projects", action="store_true", help="export every project Claude has seen")
    ap.add_argument("--thinking", action="store_true", help="include Claude's reasoning blocks")
    args = ap.parse_args()
    KEEP_THINKING = args.thinking

    if not PROJECTS.exists():
        raise SystemExit(f"No Claude Code history found at {PROJECTS}")

    if args.all_projects:
        dirs = [d for d in PROJECTS.iterdir() if d.is_dir()]
    else:
        target = Path(args.project or Path.cwd()).resolve()
        # Claude slugifies the absolute path: every non-alphanumeric run becomes "-"
        wanted = re.sub(r"[^A-Za-z0-9]+", "-", str(target))
        dirs = [d for d in PROJECTS.iterdir() if d.is_dir() and d.name == wanted]
        if not dirs:
            raise SystemExit(f"No history for {target}\nLooked for: {PROJECTS / wanted}\n"
                             f"Available:\n  " + "\n  ".join(p.name for p in PROJECTS.iterdir() if p.is_dir()))

    out = Path(args.out).expanduser()
    sessions_dir = out / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    exported = []
    for d in dirs:
        for jsonl in sorted(d.glob("*.jsonl")):
            meta = read_session(jsonl)
            if not meta or not meta["body"].strip():
                continue
            dest = write_session(meta, sessions_dir)
            meta["file"] = dest.name
            exported.append(meta)

    exported.sort(key=lambda m: m["started"] or "", reverse=True)

    lines = [
        "# Claude Code session archive — Headnote",
        "",
        f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
        f"**{len(exported)} sessions** · "
        f"{human_bytes(sum(m['bytes'] for m in exported))} of raw transcript",
        "",
        "Plain Markdown, newest first. Readable by any tool or human — no Claude Code required.",
        "",
        "| Date | Session | Turns | File |",
        "|---|---|---|---|",
    ]
    for m in exported:
        title = (m["title"] or m["first_prompt"] or "untitled").replace("|", "/")[:90]
        lines.append(f"| {(m['started'] or '')[:10]} | {title} | {m['human_turns']} | "
                     f"[md](sessions/{m['file']}) |")
    (out / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"{len(exported)} sessions → {sessions_dir}")
    print(f"index → {out / 'INDEX.md'}")


if __name__ == "__main__":
    KEEP_THINKING = False
    main()
