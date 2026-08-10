# Emergency backup of the volume-only user data — NO DEPLOY REQUIRED.
#
# Everything here runs against the code ALREADY on the server, so you can do it
# today without pushing anything. Supabase-backed data (logins, cases, hearing
# logs) is untouched by all of this — it lives off-host and needs no backup.
#
# ---------------------------------------------------------------------------
# STEP 1 — install the Railway CLI and connect (one time, on your Mac)
# ---------------------------------------------------------------------------
#   brew install railway
#   railway login
#   railway link          # pick the Headnote project + service
#
# ---------------------------------------------------------------------------
# STEP 2 — open a shell on the running server
# ---------------------------------------------------------------------------
#   railway ssh
#
# ---------------------------------------------------------------------------
# STEP 3 — paste this ENTIRE block into that shell, hit Enter
# ---------------------------------------------------------------------------
# It writes a small dump to /data/headnote_userdata.sqlite containing only the
# tables that exist nowhere else. It reads the live DBs read-only, so it cannot
# corrupt or slow down the running app.

python - <<'PYEOF'
import sqlite3, os
SRC = {
    "cache": os.environ.get("KANOON_CACHE_PATH", "/data/kanoon_cache.sqlite"),
    "feedback": os.environ.get("FEEDBACK_DB", "/data/feedback.db"),
}
TABLES = [
    ("cache", "drafts"),
    ("cache", "consultations"),
    ("cache", "documents"),
    ("cache", "document_pages"),
    ("cache", "document_chunks"),
    ("feedback", "access_grants"),
    ("feedback", "consumed_grants"),
]
OUT = "/data/headnote_userdata.sqlite"
if os.path.exists(OUT):
    os.remove(OUT)
out = sqlite3.connect(OUT)
total = 0
for key, table in TABLES:
    path = SRC[key]
    if not os.path.exists(path):
        print("  ! missing", path, "- skipping", table)
        continue
    # mode=ro: we never take a write lock on the live database.
    src = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    row = src.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not row or not row[0]:
        print("  - %s: absent" % table)
        src.close()
        continue
    out.execute(row[0])
    cols = [r[1] for r in src.execute("PRAGMA table_info(%s)" % table)]
    collist = ",".join('"%s"' % c for c in cols)
    ph = ",".join("?" * len(cols))
    cur = src.execute("SELECT %s FROM %s" % (collist, table))
    n = 0
    while True:
        # Batched so the document_pages image blobs never load all at once.
        rows = cur.fetchmany(200)
        if not rows:
            break
        out.executemany(
            "INSERT OR REPLACE INTO %s (%s) VALUES (%s)" % (table, collist, ph), rows
        )
        n += len(rows)
    out.commit()
    src.close()
    print("  OK %s: %d rows" % (table, n))
    total += n
out.commit()
out.execute("VACUUM")
out.close()
print("\nWrote %s  (%.1f MB, %d rows)" % (OUT, os.path.getsize(OUT) / 1048576.0, total))
PYEOF

# ---------------------------------------------------------------------------
# STEP 4 — type `exit` to leave the server, then pull the file to your Mac
# ---------------------------------------------------------------------------
#   railway volume files download /data/headnote_userdata.sqlite ./headnote_userdata.sqlite
#
# Keep that file somewhere safe (iCloud/Drive). It IS the backup.
#
# ---------------------------------------------------------------------------
# STEP 5 — restore onto whichever host you move to
# ---------------------------------------------------------------------------
#   python scripts/export_user_data.py --import-from headnote_userdata.sqlite
#
# Safe to run more than once: rows are replaced by primary key, never duplicated.
#
# ---------------------------------------------------------------------------
# What is deliberately NOT backed up, and why that is correct
# ---------------------------------------------------------------------------
#   Supabase (logins, cases, hearing_logs, wa_*) - lives off-host, migrates itself
#   IK cache / hf_judgments / embeddings / judgments.sqlite - rebuilds on boot
#
# Skipping the rebuildable data is what turns a 2.3 GB volume transfer into a
# download you can do over coffee.
