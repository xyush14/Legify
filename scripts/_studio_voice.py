"""Local-preview stand-in for the Smart-Drafter voice endpoints.

Spawned by .preview_tmp/server.js so `localhost:8099/static/draft-smart.html`
runs the REAL conversational conductor in a browser (real mic + browser TTS +
real Groq-backed AI) WITHOUT booting the full FastAPI app or Supabase auth.

Mirrors two prod endpoints (auth stripped — local only):
  GET  /api/draft/templates  → {"templates": [...]}        (mode="templates")
  POST /api/draft/compose    → conductor_step(...) result  (default)

Reads a JSON request on stdin, writes a JSON response on stdout. NOT imported
by the product; pure local dev aid.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    """Belt-and-suspenders .env loader (the conductor needs GROQ_API_KEY).

    config.py also calls load_dotenv(), but only if python-dotenv is installed
    in this venv — so parse .env ourselves to be safe. Never overwrites a value
    already in the environment.
    """
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def main() -> None:
    _load_env()
    try:
        body = json.loads(sys.stdin.read() or "{}")
    except Exception:
        body = {}

    from headnote.drafter.compose import conductor_step, list_templates_slim

    if body.get("mode") == "templates":
        sys.stdout.write(json.dumps({"templates": list_templates_slim()}, ensure_ascii=False))
        return

    doc_type = body.get("doc_type")
    if not doc_type:
        sys.stdout.write(json.dumps({"detail": "doc_type required"}))
        sys.exit(1)

    result = conductor_step(
        doc_type=doc_type,
        conversation=body.get("conversation") or [],
        collected=body.get("collected") or {},
        user_message=body.get("user_message"),
        lang=body.get("lang") or "hi",
        force_draft=bool(body.get("force_draft")),
    )
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
