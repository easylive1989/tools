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


def test_runner_applies_pending_migration(tmp_path):
    (tmp_path / "0001_create_widgets.sql").write_text(
        "CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT);"
    )
    conn = _fresh_conn()
    runner.run_migrations(conn, str(tmp_path))

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "widgets" in tables

    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()]
    assert versions == ["0001"]


def test_runner_skips_already_applied_migrations(tmp_path):
    (tmp_path / "0001_create_widgets.sql").write_text(
        "CREATE TABLE widgets (id INTEGER PRIMARY KEY);"
    )
    conn = _fresh_conn()
    runner.run_migrations(conn, str(tmp_path))
    runner.run_migrations(conn, str(tmp_path))  # second call must be a no-op

    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall()]
    assert versions == ["0001"]


def test_runner_applies_multiple_migrations_in_order(tmp_path):
    (tmp_path / "0002_add_color.sql").write_text(
        "ALTER TABLE widgets ADD COLUMN color TEXT;"
    )
    (tmp_path / "0001_create_widgets.sql").write_text(
        "CREATE TABLE widgets (id INTEGER PRIMARY KEY);"
    )
    conn = _fresh_conn()
    runner.run_migrations(conn, str(tmp_path))

    cols = [r[1] for r in conn.execute("PRAGMA table_info(widgets)").fetchall()]
    assert "color" in cols
    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()]
    assert versions == ["0001", "0002"]
