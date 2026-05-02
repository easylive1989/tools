"""Hand-rolled SQL migration runner.

Applies forward-only `db/migrations/NNNN_*.sql` files in order, recording
applied versions in the `schema_migrations` table. See CONVENTIONS.md §2.4.
"""
import os
import sqlite3
from datetime import datetime, timezone


def run_migrations(conn: sqlite3.Connection, migrations_dir: str) -> None:
    """Apply any pending migrations, recording them in schema_migrations."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  version    TEXT PRIMARY KEY,"
        "  applied_at TEXT NOT NULL"
        ")"
    )
    conn.commit()
