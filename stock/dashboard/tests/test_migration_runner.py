import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
os.environ.setdefault("DB_PATH", ":memory:")

from db import runner


def _fresh_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_runner_creates_schema_migrations_table(tmp_path):
    conn = _fresh_conn()
    runner.run_migrations(conn, str(tmp_path))  # empty migrations dir

    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchall()
    assert len(rows) == 1
