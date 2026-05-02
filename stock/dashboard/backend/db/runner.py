"""Hand-rolled SQL migration runner.

Applies forward-only `db/migrations/NNNN_*.sql` files in order, recording
applied versions in the `schema_migrations` table. See CONVENTIONS.md §2.4.
"""
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^(\d{4})_.+\.sql$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _discover(migrations_dir: str) -> list[tuple[str, str]]:
    """Return [(version, full_path), ...] sorted by version."""
    if not os.path.isdir(migrations_dir):
        return []
    entries = []
    for name in os.listdir(migrations_dir):
        m = _VERSION_RE.match(name)
        if m:
            entries.append((m.group(1), os.path.join(migrations_dir, name)))
    entries.sort(key=lambda e: e[0])
    return entries


def run_migrations(conn: sqlite3.Connection, migrations_dir: str) -> None:
    """Apply any pending migrations, recording them in schema_migrations."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  version    TEXT PRIMARY KEY,"
        "  applied_at TEXT NOT NULL"
        ")"
    )
    conn.commit()

    applied = {
        r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }

    for version, path in _discover(migrations_dir):
        if version in applied:
            continue
        with open(path, encoding="utf-8") as f:
            sql = f.read()
        try:
            conn.executescript("BEGIN; " + sql + "; COMMIT;")
        except sqlite3.Error:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            logger.error("migration_failed version=%s path=%s", version, path)
            raise
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, _now_iso()),
        )
        conn.commit()
        logger.info("migration_applied version=%s", version)
