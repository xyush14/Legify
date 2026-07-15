"""
Persistence layer for the drafting engine.

drafts table lives in the same SQLite file as the IK cache + HF corpus
(KANOON_CACHE_PATH). This means: one Railway Volume covers everything,
backups are simple, and the existing /admin/import_corpus_from_url flow
implicitly covers drafts too once persistence ships.

Schema: minimal v1. user_id is denormalised from Supabase; we don't FK
to user_profiles because that's a Supabase-managed table and we don't
want SQLite ↔ Postgres coupling here. The user_id is whatever the
front-end passes as the bearer-validated identifier (Supabase user.id).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from headnote.config import KANOON_CACHE_PATH


def _init_schema(conn: sqlite3.Connection) -> None:
    """Idempotent: safe to call on every boot."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS drafts (
            id                TEXT PRIMARY KEY,
            user_id           TEXT,                           -- Supabase user.id or NULL (anon)
            story_id          TEXT NOT NULL,                  -- 'friendly_cash_loan' etc.
            template_version  INTEGER NOT NULL DEFAULT 1,     -- pinned at create-time
            lang              TEXT NOT NULL DEFAULT 'en',
            answers_json      TEXT NOT NULL,                  -- JSON-serialised flat dict
            title             TEXT,                           -- short label for the FE 'Drafts' list
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            exported_at       TEXT,
            exported_format   TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_drafts_user   ON drafts(user_id);
        CREATE INDEX IF NOT EXISTS idx_drafts_story  ON drafts(story_id);
        CREATE INDEX IF NOT EXISTS idx_drafts_updated ON drafts(updated_at DESC);
    """)
    # Additive migration: link a draft to a case folder (nullable). SQLite has no
    # ADD COLUMN IF NOT EXISTS, so guard on the live column set.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(drafts)")}
    if "case_id" not in cols:
        conn.execute("ALTER TABLE drafts ADD COLUMN case_id TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_drafts_case ON drafts(case_id)")
    conn.commit()


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(KANOON_CACHE_PATH, timeout=10)
    try:
        _init_schema(c)
        yield c
    finally:
        c.close()


def init_drafts_db() -> None:
    """Call once at app boot to ensure the drafts table exists."""
    with _conn() as _:
        pass


@dataclass
class Draft:
    id: str
    user_id: Optional[str]
    story_id: str
    template_version: int
    lang: str
    answers: dict
    title: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    exported_at: Optional[str] = None
    exported_format: Optional[str] = None
    case_id: Optional[str] = None

    @staticmethod
    def _row_to(d) -> "Draft":
        return Draft(
            id=d[0], user_id=d[1], story_id=d[2], template_version=d[3],
            lang=d[4], answers=json.loads(d[5] or "{}"),
            title=d[6], created_at=d[7], updated_at=d[8],
            exported_at=d[9], exported_format=d[10],
            case_id=d[11] if len(d) > 11 else None,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "story_id": self.story_id,
            "template_version": self.template_version,
            "lang": self.lang,
            "answers": self.answers,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "exported_at": self.exported_at,
            "exported_format": self.exported_format,
            "case_id": self.case_id,
        }


def create_draft(
    *,
    story_id: str,
    template_version: int,
    user_id: Optional[str] = None,
    lang: str = "en",
    answers: Optional[dict] = None,
    title: Optional[str] = None,
    case_id: Optional[str] = None,
) -> Draft:
    now = datetime.now(timezone.utc).isoformat()
    draft_id = uuid.uuid4().hex
    answers_json = json.dumps(answers or {}, ensure_ascii=False)
    with _conn() as c:
        c.execute(
            "INSERT INTO drafts (id, user_id, story_id, template_version, lang, answers_json, title, created_at, updated_at, case_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (draft_id, user_id, story_id, template_version, lang, answers_json, title, now, now, case_id),
        )
        c.commit()
    return Draft(
        id=draft_id, user_id=user_id, story_id=story_id,
        template_version=template_version, lang=lang,
        answers=answers or {}, title=title,
        created_at=now, updated_at=now, case_id=case_id,
    )


def get_draft(draft_id: str) -> Optional[Draft]:
    with _conn() as c:
        row = c.execute(
            "SELECT id, user_id, story_id, template_version, lang, answers_json, "
            "title, created_at, updated_at, exported_at, exported_format, case_id "
            "FROM drafts WHERE id = ?",
            (draft_id,),
        ).fetchone()
    return Draft._row_to(row) if row else None


def update_draft(
    draft_id: str,
    *,
    answers: Optional[dict] = None,
    lang: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[Draft]:
    """Patch one or more fields. Bumps updated_at; never silently
    overwrites template_version or story_id (those are immutable post-create)."""
    existing = get_draft(draft_id)
    if existing is None:
        return None

    new_answers = answers if answers is not None else existing.answers
    new_lang    = lang    if lang    is not None else existing.lang
    new_title   = title   if title   is not None else existing.title
    now = datetime.now(timezone.utc).isoformat()

    with _conn() as c:
        c.execute(
            "UPDATE drafts SET answers_json = ?, lang = ?, title = ?, updated_at = ? WHERE id = ?",
            (
                json.dumps(new_answers, ensure_ascii=False),
                new_lang, new_title, now, draft_id,
            ),
        )
        c.commit()

    existing.answers = new_answers
    existing.lang = new_lang
    existing.title = new_title
    existing.updated_at = now
    return existing


_SELECT_COLS = ("id, user_id, story_id, template_version, lang, answers_json, "
                "title, created_at, updated_at, exported_at, exported_format, case_id")


def list_drafts(*, user_id: Optional[str] = None, limit: int = 20,
                case_id: Optional[str] = None) -> list[Draft]:
    """Return the user's recent drafts (most-recently-updated first).
    Pass user_id=None to list anonymous drafts (development only).
    Pass case_id to return only drafts filed under that matter."""
    where = ["user_id IS NULL"] if user_id is None else ["user_id = ?"]
    params: list = [] if user_id is None else [user_id]
    if case_id is not None:
        where.append("case_id = ?")
        params.append(case_id)
    params.append(limit)
    with _conn() as c:
        rows = c.execute(
            f"SELECT {_SELECT_COLS} FROM drafts WHERE {' AND '.join(where)} "
            "ORDER BY updated_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    return [Draft._row_to(r) for r in rows]


def set_draft_case(draft_id: str, *, case_id: Optional[str], user_id: Optional[str]) -> bool:
    """Attach (or, with case_id=None, detach) a draft to a case folder.
    Ownership-scoped: only the owning user can re-file their draft."""
    with _conn() as c:
        cur = c.execute(
            "UPDATE drafts SET case_id = ? WHERE id = ? AND user_id IS ?",
            (case_id, draft_id, user_id),
        )
        c.commit()
    return cur.rowcount > 0


def delete_draft(draft_id: str) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
        c.commit()
    return cur.rowcount > 0
