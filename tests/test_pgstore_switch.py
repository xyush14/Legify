"""The Postgres child-table switch must stay OFF by default.

Why this test exists
--------------------
drafts / consultations / documents read from Postgres OR SQLite, never both:

    if pgstore.ready(_PG):
        return [...postgres...]
    ...sqlite...

Migration 012 creates those Postgres tables EMPTY, and this repo has no
SQLite→Postgres backfill. So the moment `ready()` returns True, every draft,
document and recording an existing user already has stops being read — the rows
are still on disk, but nothing looks at them. That is silent, total, and hits
paying users on the surface they use most.

The guard is one env var defaulted off. This test is the tripwire for anyone
who changes that default without doing the backfill first.
"""

from __future__ import annotations

import importlib

import pytest

from headnote import config, pgstore


def test_pg_child_tables_defaults_to_off():
    """If this fails, a deploy is about to hide every user's existing work."""
    fresh = importlib.reload(config)
    assert fresh.PG_CHILD_TABLES is False, (
        "PG_CHILD_TABLES must default to OFF until the SQLite rows are "
        "backfilled into Postgres — see headnote/config.py"
    )


def test_enabled_is_false_while_the_switch_is_off(monkeypatch):
    monkeypatch.setattr(config, "PG_CHILD_TABLES", False)
    assert pgstore.enabled() is False


def test_every_child_table_falls_back_to_sqlite_while_off(monkeypatch):
    monkeypatch.setattr(config, "PG_CHILD_TABLES", False)
    for table in ("drafts", "consultations", "documents", "intake_links"):
        assert pgstore.ready(table) is False, f"{table} would read from Postgres"


def test_switch_is_the_only_thing_gating_it(monkeypatch):
    """Flipping it on must genuinely re-enable the durable path, so the switch
    is a real toggle and not a permanent disable we forget to undo."""
    monkeypatch.setattr(config, "PG_CHILD_TABLES", True)
    monkeypatch.setattr(pgstore._supabase, "_enabled", lambda: True)
    assert pgstore.enabled() is True
