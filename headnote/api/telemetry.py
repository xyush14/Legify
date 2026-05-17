"""Query telemetry recorder + aggregation queries.

Logs one row per /api/* call to a SQLite table in the same file as the
feedback database. Powers the /admin/telemetry endpoint that shows cost
breakdowns + escalation rates so you can verify the smart-routing is
actually saving money.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

from headnote import config


def init_telemetry_db() -> None:
    """Create the query_telemetry table if it doesn't exist. Same SQLite file
    as feedback. Best-effort — silently skips on read-only filesystems."""
    try:
        conn = sqlite3.connect(config.FEEDBACK_DB)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS query_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,                  -- ISO UTC timestamp
                task_type TEXT NOT NULL,           -- situation|digest|headnote|translate
                primary_model TEXT NOT NULL,
                escalated INTEGER NOT NULL DEFAULT 0,    -- 0/1
                total_cost_paise INTEGER NOT NULL DEFAULT 0,
                total_input_tokens INTEGER,
                total_output_tokens INTEGER,
                confidence INTEGER,                -- nullable
                latency_ms INTEGER NOT NULL,
                success INTEGER NOT NULL DEFAULT 1,
                user_id TEXT,
                notes TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON query_telemetry(ts);
            CREATE INDEX IF NOT EXISTS idx_telemetry_task ON query_telemetry(task_type);
        """)
        conn.commit()
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"[warn] query_telemetry init failed ({e}); recording will be a no-op.")


def record_query(
    *,
    task_type: str,
    primary_model: str,
    escalated: bool,
    total_cost_paise: int,
    latency_ms: int,
    confidence: Optional[int] = None,
    success: bool = True,
    total_input_tokens: Optional[int] = None,
    total_output_tokens: Optional[int] = None,
    user_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    """Insert one telemetry row. Silently swallows DB errors so a failed
    log never breaks the user-facing request."""
    try:
        conn = sqlite3.connect(config.FEEDBACK_DB)
        conn.execute(
            """INSERT INTO query_telemetry
                 (ts, task_type, primary_model, escalated, total_cost_paise,
                  total_input_tokens, total_output_tokens, confidence,
                  latency_ms, success, user_id, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                task_type, primary_model,
                1 if escalated else 0,
                int(total_cost_paise),
                total_input_tokens, total_output_tokens, confidence,
                int(latency_ms),
                1 if success else 0,
                user_id, notes,
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"[warn] telemetry record failed ({e}); continuing without log.")


# ----------------------------------------------------------------- aggregations

def get_summary(days: int = 7) -> dict:
    """Aggregate telemetry over the last `days` days. Returns the shape the
    /admin/telemetry endpoint serves."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    try:
        conn = sqlite3.connect(config.FEEDBACK_DB)
        conn.row_factory = sqlite3.Row
    except sqlite3.OperationalError as e:
        return {"error": f"telemetry DB unavailable: {e}"}

    try:
        total_row = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(total_cost_paise), 0) AS total_paise, "
            "COALESCE(SUM(success), 0) AS successes "
            "FROM query_telemetry WHERE ts >= ?",
            (cutoff,),
        ).fetchone()
        total_queries = int(total_row["n"] or 0)
        total_paise = int(total_row["total_paise"] or 0)
        successes = int(total_row["successes"] or 0)

        cost_by_model_rows = conn.execute(
            "SELECT primary_model, COALESCE(SUM(total_cost_paise), 0) AS paise, "
            "COUNT(*) AS n "
            "FROM query_telemetry WHERE ts >= ? GROUP BY primary_model",
            (cutoff,),
        ).fetchall()
        cost_by_model = {
            r["primary_model"]: {"paise": int(r["paise"]), "calls": int(r["n"])}
            for r in cost_by_model_rows
        }

        escalation_rows = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(escalated), 0) AS escalated "
            "FROM query_telemetry "
            "WHERE ts >= ? AND task_type IN ('situation', 'digest')",
            (cutoff,),
        ).fetchone()
        gen_calls = int(escalation_rows["n"] or 0)
        escalated_n = int(escalation_rows["escalated"] or 0)
        escalation_rate_pct = (
            round(100.0 * escalated_n / gen_calls, 2) if gen_calls > 0 else 0.0
        )

        confidence_rows = conn.execute(
            "SELECT task_type, AVG(confidence) AS avg_conf "
            "FROM query_telemetry "
            "WHERE ts >= ? AND confidence IS NOT NULL "
            "GROUP BY task_type",
            (cutoff,),
        ).fetchall()
        avg_confidence_by_task = {
            r["task_type"]: round(float(r["avg_conf"]), 2)
            for r in confidence_rows
            if r["avg_conf"] is not None
        }

        latency_row = conn.execute(
            "SELECT AVG(latency_ms) AS avg_ms FROM query_telemetry WHERE ts >= ?",
            (cutoff,),
        ).fetchone()
        avg_latency_ms = (
            round(float(latency_row["avg_ms"]), 0)
            if latency_row["avg_ms"] is not None else None
        )
    finally:
        conn.close()

    return {
        "window_days": days,
        "since_utc": cutoff,
        "total_queries": total_queries,
        "successful_queries": successes,
        "success_rate_pct": (round(100.0 * successes / total_queries, 2)
                             if total_queries > 0 else 0.0),
        "total_cost_paise": total_paise,
        "total_cost_inr": round(total_paise / 100, 2),
        "avg_cost_paise_per_call": (round(total_paise / total_queries, 1)
                                    if total_queries > 0 else 0.0),
        "cost_by_model": cost_by_model,
        "escalation_rate_pct": escalation_rate_pct,
        "avg_confidence_by_task": avg_confidence_by_task,
        "avg_latency_ms": avg_latency_ms,
    }
