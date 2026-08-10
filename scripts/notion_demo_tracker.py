#!/usr/bin/env python3
"""
notion_demo_tracker.py — build the "Demo Follow-ups" live tracker in Notion.

Browserless: uses a Notion internal-integration token (no OAuth). One-time setup:
  1. Create an integration at notion.so/my-integrations, copy the secret (ntn_...).
  2. Add to .env:   NOTION_TOKEN=ntn_xxx
                    NOTION_PARENT_PAGE=<the page id/URL you shared with the integration>
  3. In Notion, open that page -> ... -> Connections -> add your integration.

Run:
    python scripts/notion_demo_tracker.py            # reads parent from .env
    python scripts/notion_demo_tracker.py <page_url> # or pass the page URL/id

It creates a database with a self-computing "Action" column (Missed / Due today /
Upcoming / Closed) and loads the demo users from the field diary. Idempotent-ish:
re-running creates a NEW database (delete the old one if you re-run).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
API = "https://api.notion.com/v1"
VERSION = "2022-06-28"


def _load_env() -> dict:
    env = dict(os.environ)
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


def _norm_page_id(raw: str) -> str:
    # Accept a full URL or a bare id; return a dashed uuid.
    m = re.search(r"([0-9a-fA-F]{32})", raw.replace("-", ""))
    if not m:
        raise SystemExit(f"Could not find a Notion page id in: {raw!r}")
    h = m.group(1).lower()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _api(token: str, method: str, path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Notion-Version", VERSION)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Notion API {e.code}: {e.read().decode()}")


ACTION_FORMULA = (
    'if(prop("Done"), "✅ Closed", '
    'if(empty(prop("Next Follow-up")), "⚪ Set a follow-up", '
    'if(prop("Next Follow-up") < now(), '
    '"\U0001f534 MISSED · overdue " + format(dateBetween(now(), prop("Next Follow-up"), "days")) + "d", '
    'if(formatDate(prop("Next Follow-up"), "YYYYMMDD") == formatDate(now(), "YYYYMMDD"), '
    '"\U0001f7e1 Due today · " + formatDate(prop("Next Follow-up"), "h:mm A"), '
    '"\U0001f7e2 Upcoming · in " + format(dateBetween(prop("Next Follow-up"), now(), "days")) + "d"))))'
)

STAGES = [
    ("New", "gray"), ("Contacted", "blue"), ("Demo scheduled", "yellow"),
    ("Demo done", "orange"), ("Converted", "green"),
    ("Not interested", "red"), ("No response", "brown"),
]

# name, phone, stage, log
ROWS = [
    ("Syeed Nadeem", "", "Demo done", "Prefers evening. Demo given."),
    ("Alok", "", "Contacted", "Link sent, then demo."),
    ("Ashish", "", "Contacted", "Available anytime. Call & schedule demo."),
    ("Rajendra", "", "No response", "Preferred ~2 PM. Not reachable last time; retry."),
    ("Ajay Singh", "8175882416", "No response", "Struck off in diary — verify number."),
    ("Prasidh", "9074006912", "Demo done", "Link sent, then demo done. Follow up to convert."),
    ("Ganesh", "9001077299", "Demo done", "Link sent, then demo done. Follow up to convert."),
    ("Prabhakar", "7905368719", "Contacted", "Link sent. Give demo."),
    ("Anand", "7081810422", "Converted", "Demo done, on monthly plan."),
    ("Vishwajeet", "9811533427", "New", "Preferred ~1 PM. Call & schedule demo."),
    ("Pawan", "9936649293", "New", "Call & schedule demo."),
    ("Ajay", "9468673474", "New", "Preferred ~11 AM. Call & schedule demo."),
]


def main() -> None:
    env = _load_env()
    token = env.get("NOTION_TOKEN")
    if not token:
        raise SystemExit("NOTION_TOKEN not found in .env")
    parent_raw = sys.argv[1] if len(sys.argv) > 1 else env.get("NOTION_PARENT_PAGE")
    if not parent_raw:
        raise SystemExit("Pass a page URL/id or set NOTION_PARENT_PAGE in .env")
    parent = _norm_page_id(parent_raw)

    db = _api(token, "POST", "/databases", {
        "parent": {"type": "page_id", "page_id": parent},
        "icon": {"type": "emoji", "emoji": "\U0001f4de"},
        "title": [{"type": "text", "text": {"content": "Demo Follow-ups"}}],
        "properties": {
            "Name": {"title": {}},
            "Phone": {"phone_number": {}},
            "Stage": {"select": {"options": [{"name": n, "color": c} for n, c in STAGES]}},
            "Next Follow-up": {"date": {}},
            "Last Contacted": {"date": {}},
            "Log": {"rich_text": {}},
            "Done": {"checkbox": {}},
            "Action": {"formula": {"expression": ACTION_FORMULA}},
        },
    })
    db_id = db["id"]
    print(f"Created database: {db.get('url', db_id)}")

    for name, phone, stage, log in ROWS:
        props = {
            "Name": {"title": [{"text": {"content": name}}]},
            "Stage": {"select": {"name": stage}},
            "Log": {"rich_text": [{"text": {"content": log}}]},
            "Done": {"checkbox": stage == "Converted"},
        }
        if phone:
            props["Phone"] = {"phone_number": phone}
        _api(token, "POST", "/pages", {"parent": {"database_id": db_id}, "properties": props})
        print(f"  + {name}")

    print("\nDone. Open the database in Notion, then add views:")
    print("  \U0001f534 Missed  ·  \U0001f7e1 Today  ·  \U0001f7e2 Upcoming  ·  \U0001f4cb Board by Stage")


if __name__ == "__main__":
    main()
