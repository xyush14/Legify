"""Persistence for intake links and the pending-upload tray.

Dual backend, same contract as the rest of the app: Supabase Postgres when
configured (durable, cross-device), local SQLite otherwise so dev works with no
setup. Everything is scoped by user_id.

One ACTIVE link per matter — rotating revokes the old one, so a lawyer never has
two live links to the same file and cannot lose track of what is circulating.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

from headnote.config import KANOON_CACHE_PATH
from headnote import pgstore

_LINKS = "intake_links"
_UPLOADS = "intake_uploads"

PENDING, SAVED, DISCARDED = "pending", "saved", "discarded"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_token() -> str:
    """32 url-safe chars ≈ 190 bits. The whole URL is the secret, so it must not
    be guessable and must never be logged."""
    return secrets.token_urlsafe(24)


# ============================================================ SQLite backend

def _init(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS intake_links (
            id TEXT PRIMARY KEY, user_id TEXT, case_id TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE, label TEXT, expires_at TEXT,
            max_per_day INTEGER NOT NULL DEFAULT 20, revoked_at TEXT,
            created_at TEXT NOT NULL, last_used_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_il_token ON intake_links(token);
        CREATE INDEX IF NOT EXISTS idx_il_case  ON intake_links(user_id, case_id);

        CREATE TABLE IF NOT EXISTS intake_uploads (
            id TEXT PRIMARY KEY, user_id TEXT, case_id TEXT NOT NULL, link_id TEXT,
            filename TEXT, mime TEXT, size_bytes INTEGER, object_path TEXT,
            note TEXT, uploader_name TEXT, uploader_phone TEXT,
            status TEXT NOT NULL DEFAULT 'pending', document_id TEXT,
            created_at TEXT NOT NULL, reviewed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_iu_case ON intake_uploads(user_id, case_id, status);
    """)
    conn.commit()


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(KANOON_CACHE_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        _init(c)
        yield c
    finally:
        c.close()


def _row(r) -> Optional[dict]:
    return dict(r) if r else None


# ============================================================ links

def active_link(case_id: str, user_id: str) -> Optional[dict]:
    if pgstore.ready(_LINKS):
        rows = pgstore.listing(_LINKS, user_id=user_id, limit=1, case_id=case_id,
                               order="created_at.desc")
        rows = [r for r in rows if not r.get("revoked_at")]
        return rows[0] if rows else None
    with _conn() as c:
        return _row(c.execute(
            """SELECT * FROM intake_links
               WHERE user_id IS ? AND case_id = ? AND revoked_at IS NULL
               ORDER BY created_at DESC LIMIT 1""", (user_id, case_id)).fetchone())


def create_link(case_id: str, user_id: str, *, label: Optional[str] = None,
                expires_days: Optional[int] = None, max_per_day: int = 20) -> Optional[dict]:
    """Mint a link, revoking any existing active one for this matter."""
    revoke_active(case_id, user_id)
    token = new_token()
    exp = ((datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()
           if expires_days else None)
    if pgstore.ready(_LINKS):
        row = pgstore.insert(_LINKS, {
            "user_id": user_id, "case_id": case_id, "token": token, "label": label,
            "expires_at": exp, "max_per_day": max_per_day})
        if row:
            return row
    lid = uuid.uuid4().hex
    with _conn() as c:
        c.execute("""INSERT INTO intake_links
                     (id,user_id,case_id,token,label,expires_at,max_per_day,created_at)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (lid, user_id, case_id, token, label, exp, max_per_day, _now()))
        c.commit()
        return _row(c.execute("SELECT * FROM intake_links WHERE id=?", (lid,)).fetchone())


def revoke_active(case_id: str, user_id: str) -> int:
    link = active_link(case_id, user_id)
    if not link:
        return 0
    if pgstore.ready(_LINKS):
        pgstore.update(_LINKS, str(link["id"]), {"revoked_at": _now()}, user_id=user_id)
        return 1
    with _conn() as c:
        c.execute("UPDATE intake_links SET revoked_at=? WHERE id=? AND user_id IS ?",
                  (_now(), link["id"], user_id))
        c.commit()
    return 1


def link_by_token(token: str) -> Optional[dict]:
    """Public path: resolve a token with NO user scope (the token IS the auth)."""
    if not token or len(token) < 16:
        return None
    if pgstore.ready(_LINKS):
        from headnote.entitlements import _supabase
        rows = _supabase.select(_LINKS, params={"token": f"eq.{token}", "limit": "1"})
        if rows:
            return rows[0]
    with _conn() as c:
        return _row(c.execute("SELECT * FROM intake_links WHERE token=?", (token,)).fetchone())


def touch_link(link: dict) -> None:
    if pgstore.ready(_LINKS):
        pgstore.set_field(_LINKS, str(link["id"]), "last_used_at", _now())
        return
    with _conn() as c:
        c.execute("UPDATE intake_links SET last_used_at=? WHERE id=?", (_now(), link["id"]))
        c.commit()


# ============================================================ uploads

def add_upload(*, user_id: str, case_id: str, link_id: Optional[str],
               filename: str, mime: str, size_bytes: int, object_path: str,
               note: str = "", uploader_name: str = "",
               uploader_phone: str = "") -> Optional[dict]:
    common = {"user_id": user_id, "case_id": case_id, "link_id": link_id,
              "filename": filename, "mime": mime, "size_bytes": size_bytes,
              "object_path": object_path, "note": note or None,
              "uploader_name": uploader_name or None,
              "uploader_phone": uploader_phone or None, "status": PENDING}
    if pgstore.ready(_UPLOADS):
        row = pgstore.insert(_UPLOADS, common)
        if row:
            return row
    uid = uuid.uuid4().hex
    with _conn() as c:
        c.execute("""INSERT INTO intake_uploads
                     (id,user_id,case_id,link_id,filename,mime,size_bytes,object_path,
                      note,uploader_name,uploader_phone,status,created_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (uid, user_id, case_id, link_id, filename, mime, size_bytes,
                   object_path, note or None, uploader_name or None,
                   uploader_phone or None, PENDING, _now()))
        c.commit()
        return _row(c.execute("SELECT * FROM intake_uploads WHERE id=?", (uid,)).fetchone())


def list_uploads(user_id: str, *, case_id: Optional[str] = None,
                 status: str = PENDING, limit: int = 100) -> list[dict]:
    if pgstore.ready(_UPLOADS):
        rows = pgstore.listing(_UPLOADS, user_id=user_id, limit=limit, case_id=case_id,
                               order="created_at.desc")
        return [r for r in rows if not status or r.get("status") == status]
    q = "SELECT * FROM intake_uploads WHERE user_id IS ?"
    p: list = [user_id]
    if case_id:
        q += " AND case_id = ?"; p.append(case_id)
    if status:
        q += " AND status = ?"; p.append(status)
    q += " ORDER BY created_at DESC LIMIT ?"; p.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(q, tuple(p)).fetchall()]


def get_upload(upload_id: str, user_id: str) -> Optional[dict]:
    if pgstore.ready(_UPLOADS):
        return pgstore.get(_UPLOADS, upload_id, user_id=user_id)
    with _conn() as c:
        return _row(c.execute("SELECT * FROM intake_uploads WHERE id=? AND user_id IS ?",
                              (upload_id, user_id)).fetchone())


def set_status(upload_id: str, user_id: str, status: str,
               *, document_id: Optional[str] = None) -> Optional[dict]:
    patch = {"status": status, "reviewed_at": _now()}
    if document_id:
        patch["document_id"] = document_id
    if pgstore.ready(_UPLOADS):
        return pgstore.update(_UPLOADS, upload_id, patch, user_id=user_id)
    with _conn() as c:
        c.execute("""UPDATE intake_uploads SET status=?, reviewed_at=?, document_id=COALESCE(?,document_id)
                     WHERE id=? AND user_id IS ?""",
                  (status, _now(), document_id, upload_id, user_id))
        c.commit()
    return get_upload(upload_id, user_id)


def count_today(link_id: str, user_id: str) -> int:
    """Uploads through this link in the last 24h — the abuse brake."""
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    if pgstore.ready(_UPLOADS):
        from headnote.entitlements import _supabase
        rows = _supabase.select(_UPLOADS, params={
            "link_id": f"eq.{link_id}", "created_at": f"gte.{since}",
            "select": "id", "limit": "500"})
        return len(rows or [])
    with _conn() as c:
        r = c.execute("SELECT COUNT(*) FROM intake_uploads WHERE link_id=? AND created_at>=?",
                      (link_id, since)).fetchone()
        return int(r[0] if r else 0)


def pending_counts(user_id: str) -> dict[str, int]:
    """case_id → pending count, for the Home badge in one query."""
    out: dict[str, int] = {}
    for u in list_uploads(user_id, status=PENDING, limit=500):
        k = str(u.get("case_id"))
        out[k] = out.get(k, 0) + 1
    return out
