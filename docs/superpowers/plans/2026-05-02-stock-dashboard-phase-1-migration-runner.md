# Stock Dashboard Phase 1 (MIGR-): DB Migration Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `init_db()`'s inline schema with a hand-rolled, version-tracked SQL migration runner. Existing call sites stay untouched; new schema changes from now on go through `db/migrations/NNNN_*.sql`.

**Architecture:**
- Convert `backend/db.py` → `backend/db/` Python package; existing functions live in `db/__init__.py` so every `from db import …` keeps working.
- Add `db/runner.py` (~50 LOC): tracks applied versions in a `schema_migrations` table, applies pending SQL files in order inside per-file transactions.
- Includes a **baseline** mechanism: on a VPS DB that already has the legacy schema but no `schema_migrations` table, mark all current migrations as applied without re-executing them. Safe upgrade path.
- `db.init_db()` becomes a thin shim that calls the runner. No caller changes in this phase.

**Tech Stack:** Python 3, sqlite3 (stdlib), pytest. No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-02-stock-dashboard-conventions-design.md` §2.4 + §7 Phase 1.

---

## File Structure

**Created:**
- `stock/dashboard/backend/db/__init__.py` — moved content from `backend/db.py` (no logic change other than swapping `init_db()` body in T7)
- `stock/dashboard/backend/db/runner.py` — migration runner (~50 LOC)
- `stock/dashboard/backend/db/migrations/0001_initial.sql` — current consolidated schema
- `stock/dashboard/tests/test_migration_runner.py` — runner unit tests

**Deleted:**
- `stock/dashboard/backend/db.py` — replaced by package

**Modified:**
- None of the existing call sites (`app.py`, `backfill.py`, `tests/conftest.py`, other test files) — `init_db()` still works.

**Out of scope (Phase 2+):**
- Migrating call sites away from `init_db()`.
- Splitting `db/__init__.py` into per-table repository files.
- Introducing `core/settings.py` (runner reads `DB_PATH` from env directly for now).

---

## Task Breakdown

Project prefix: `MIGR-`. All commits use `(MIGR-Tn)` step IDs per spec §5.1.

---

### Task 1 (MIGR-T1): Convert `backend/db.py` into a `db/` package

**Files:**
- Delete: `stock/dashboard/backend/db.py`
- Create: `stock/dashboard/backend/db/__init__.py` (verbatim copy of the deleted file's contents)

This is a pure restructuring step. No behavior changes. The existing test suite is the regression check.

- [ ] **Step 1: Verify the existing test suite is green before any changes**

```bash
cd stock/dashboard && python -m pytest tests/ -q
```

Expected: all tests pass. If anything is red here, stop — debug environment first.

- [ ] **Step 2: Move the file**

```bash
cd stock/dashboard/backend
mkdir -p db
git mv db.py db/__init__.py
```

- [ ] **Step 3: Run the full test suite to verify no import breakage**

```bash
cd stock/dashboard && python -m pytest tests/ -q
```

Expected: all tests pass. Imports like `import db` now resolve to `backend/db/__init__.py`.

- [ ] **Step 4: Commit**

```bash
git add stock/dashboard/backend/db/
git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): convert db.py to db/ package (MIGR-T1)

Pure move: db.py → db/__init__.py. No logic change. Lays the
groundwork for db/runner.py and db/migrations/ to live alongside.
EOF
)"
```

---

### Task 2 (MIGR-T2): Runner skeleton — create `schema_migrations` table

**Files:**
- Create: `stock/dashboard/backend/db/runner.py`
- Create: `stock/dashboard/tests/test_migration_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# stock/dashboard/tests/test_migration_runner.py
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd stock/dashboard && python -m pytest tests/test_migration_runner.py::test_runner_creates_schema_migrations_table -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'db.runner'` (or attribute error).

- [ ] **Step 3: Write minimal runner**

```python
# stock/dashboard/backend/db/runner.py
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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd stock/dashboard && python -m pytest tests/test_migration_runner.py::test_runner_creates_schema_migrations_table -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add stock/dashboard/backend/db/runner.py stock/dashboard/tests/test_migration_runner.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): runner creates schema_migrations table (MIGR-T2)

Skeleton run_migrations() that ensures the version-tracking table
exists. No file discovery or application yet.
EOF
)"
```

---

### Task 3 (MIGR-T3): Apply migration files in order, idempotently

**Files:**
- Modify: `stock/dashboard/backend/db/runner.py`
- Modify: `stock/dashboard/tests/test_migration_runner.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_migration_runner.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd stock/dashboard && python -m pytest tests/test_migration_runner.py -v
```

Expected: the three new tests FAIL (existing T2 test still passes).

- [ ] **Step 3: Implement file discovery + application**

Replace the body of `run_migrations` in `stock/dashboard/backend/db/runner.py`:

```python
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
            conn.execute("ROLLBACK")
            logger.error("migration_failed version=%s path=%s", version, path)
            raise
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, _now_iso()),
        )
        conn.commit()
        logger.info("migration_applied version=%s", version)
```

- [ ] **Step 4: Run the full migration runner test file**

```bash
cd stock/dashboard && python -m pytest tests/test_migration_runner.py -v
```

Expected: all four tests PASS.

- [ ] **Step 5: Commit**

```bash
git add stock/dashboard/backend/db/runner.py stock/dashboard/tests/test_migration_runner.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): apply migrations in order with version tracking (MIGR-T3)

Discovers NNNN_*.sql files, applies pending ones inside transactions,
records each version. Re-runs are idempotent.
EOF
)"
```

---

### Task 4 (MIGR-T4): Baseline mechanism for the existing VPS DB

The VPS already has the legacy schema. We must not re-create those tables and we must not error out. Instead, the runner detects "DB has known tables but no migration history" and stamps all current migrations as already applied.

**Files:**
- Modify: `stock/dashboard/backend/db/runner.py`
- Modify: `stock/dashboard/tests/test_migration_runner.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_migration_runner.py`:

```python
def test_runner_baselines_existing_db(tmp_path):
    """If the DB already has the legacy schema but no schema_migrations,
    mark all migrations as applied without running them."""
    conn = _fresh_conn()
    # Simulate an existing VPS DB by creating a known legacy table directly.
    conn.execute(
        "CREATE TABLE indicator_snapshots ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  indicator TEXT NOT NULL,"
        "  timestamp TEXT NOT NULL,"
        "  value REAL NOT NULL,"
        "  extra_json TEXT"
        ")"
    )
    conn.commit()

    # A migration that WOULD fail if executed (the table already exists).
    (tmp_path / "0001_initial.sql").write_text(
        "CREATE TABLE indicator_snapshots (x INTEGER);"
    )

    runner.run_migrations(conn, str(tmp_path))

    # Migration is recorded as applied, but was NOT executed
    # (otherwise the CREATE TABLE would have errored).
    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall()]
    assert versions == ["0001"]
    # Original schema preserved.
    cols = [r[1] for r in conn.execute(
        "PRAGMA table_info(indicator_snapshots)"
    ).fetchall()]
    assert "indicator" in cols and "x" not in cols


def test_runner_does_not_baseline_fresh_db(tmp_path):
    """Fresh DB (no known legacy tables) goes through the normal path."""
    (tmp_path / "0001_initial.sql").write_text(
        "CREATE TABLE indicator_snapshots (id INTEGER PRIMARY KEY, indicator TEXT);"
    )
    conn = _fresh_conn()
    runner.run_migrations(conn, str(tmp_path))

    cols = [r[1] for r in conn.execute(
        "PRAGMA table_info(indicator_snapshots)"
    ).fetchall()]
    assert cols == ["id", "indicator"]  # came from the migration
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd stock/dashboard && python -m pytest tests/test_migration_runner.py -v
```

Expected: `test_runner_baselines_existing_db` FAILS (the migration runs and `CREATE TABLE indicator_snapshots` errors). `test_runner_does_not_baseline_fresh_db` should already pass.

- [ ] **Step 3: Implement baseline detection**

Modify `stock/dashboard/backend/db/runner.py`:

Add a sentinel set near the top (after `_VERSION_RE`):

```python
# Tables known to exist in the pre-runner schema. If any of these are
# present in a DB that has no schema_migrations rows, we baseline the DB
# instead of re-running migrations.
_LEGACY_TABLES = frozenset({
    "indicator_snapshots",
    "watched_stocks",
    "stock_snapshots",
    "stock_broker_daily",
    "stock_chip_daily",
    "stock_per_daily",
    "stock_revenue_monthly",
    "stock_financial_quarterly",
    "stock_dividend_history",
    "price_alerts",
})
```

Add a helper function above `run_migrations`:

```python
def _is_legacy_db(conn: sqlite3.Connection) -> bool:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    existing = {r[0] for r in rows}
    return bool(existing & _LEGACY_TABLES)
```

Modify `run_migrations` to baseline when appropriate. The new body, after the `applied = {...}` line and before the migration loop:

```python
    if not applied and _is_legacy_db(conn):
        for version, _ in _discover(migrations_dir):
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, _now_iso()),
            )
        conn.commit()
        logger.info("migrations_baselined count=%d", len(_discover(migrations_dir)))
        return
```

The full `run_migrations` should now look like:

```python
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

    if not applied and _is_legacy_db(conn):
        for version, _ in _discover(migrations_dir):
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, _now_iso()),
            )
        conn.commit()
        logger.info("migrations_baselined count=%d", len(_discover(migrations_dir)))
        return

    for version, path in _discover(migrations_dir):
        if version in applied:
            continue
        with open(path, encoding="utf-8") as f:
            sql = f.read()
        try:
            conn.executescript("BEGIN; " + sql + "; COMMIT;")
        except sqlite3.Error:
            conn.execute("ROLLBACK")
            logger.error("migration_failed version=%s path=%s", version, path)
            raise
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, _now_iso()),
        )
        conn.commit()
        logger.info("migration_applied version=%s", version)
```

- [ ] **Step 4: Run the runner tests**

```bash
cd stock/dashboard && python -m pytest tests/test_migration_runner.py -v
```

Expected: all six tests PASS.

- [ ] **Step 5: Commit**

```bash
git add stock/dashboard/backend/db/runner.py stock/dashboard/tests/test_migration_runner.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): baseline existing DB without re-running migrations (MIGR-T4)

When a DB already has the legacy schema but no schema_migrations table,
stamp all known migrations as applied without executing them. Required
for safe upgrade of the live VPS database.
EOF
)"
```

---

### Task 5 (MIGR-T5): Fail-fast on bad migration with rollback

**Files:**
- Modify: `stock/dashboard/tests/test_migration_runner.py`

The implementation already rolls back inside `run_migrations` (T3). This task locks the behaviour with an explicit test.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_migration_runner.py`:

```python
def test_runner_rolls_back_on_bad_migration(tmp_path):
    """A SQL error must rollback the transaction and not record the version."""
    (tmp_path / "0001_good.sql").write_text(
        "CREATE TABLE good (id INTEGER);"
    )
    (tmp_path / "0002_bad.sql").write_text(
        "CREATE TABLE bad (id INTEGER);\n"
        "THIS IS NOT VALID SQL;"
    )
    conn = _fresh_conn()

    import pytest as _pytest
    with _pytest.raises(sqlite3.Error):
        runner.run_migrations(conn, str(tmp_path))

    versions = {r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall()}
    # 0001 succeeded and was recorded; 0002 must NOT be recorded.
    assert versions == {"0001"}
    # 'bad' table must not exist (rolled back).
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "good" in tables
    assert "bad" not in tables
```

- [ ] **Step 2: Run the test**

```bash
cd stock/dashboard && python -m pytest tests/test_migration_runner.py::test_runner_rolls_back_on_bad_migration -v
```

Expected: PASS (the implementation from T3 already handles this). If it fails, debug and fix the runner before continuing.

- [ ] **Step 3: Commit**

```bash
git add stock/dashboard/tests/test_migration_runner.py
git commit -m "$(cat <<'EOF'
test(stock-dashboard): lock rollback-on-bad-migration behaviour (MIGR-T5)
EOF
)"
```

---

### Task 6 (MIGR-T6): Extract current schema into `0001_initial.sql`

**Files:**
- Create: `stock/dashboard/backend/db/migrations/0001_initial.sql`

The file is a consolidated snapshot of the current schema, including the `indicator_key` and `window_n` columns that were added by ad-hoc ALTERs. Legacy data fixes (e.g. the `margin → margin_balance` UPDATE) are intentionally excluded — fresh databases never had legacy values to fix, and the VPS DB has already had this UPDATE applied historically.

- [ ] **Step 1: Create the migration file**

Write the file with the following content:

```sql
-- 0001_initial.sql
-- Consolidated snapshot of the schema as of 2026-05-02.
-- For databases that already had this schema before the runner existed,
-- the runner's baseline mechanism marks this version as applied without
-- executing it (see db/runner.py).

CREATE TABLE indicator_snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator  TEXT    NOT NULL,
    timestamp  TEXT    NOT NULL,
    value      REAL    NOT NULL,
    extra_json TEXT
);
CREATE INDEX idx_ind_ts ON indicator_snapshots(indicator, timestamp);

CREATE TABLE watched_stocks (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker   TEXT NOT NULL UNIQUE,
    added_at TEXT NOT NULL
);

CREATE TABLE stock_snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker     TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    price      REAL NOT NULL,
    change     REAL,
    change_pct REAL,
    currency   TEXT,
    name       TEXT
);
CREATE INDEX idx_stock_ts ON stock_snapshots(ticker, timestamp);

CREATE TABLE stock_broker_daily (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker               TEXT NOT NULL,
    date                 TEXT NOT NULL,
    securities_trader_id TEXT NOT NULL,
    securities_trader    TEXT,
    buy_volume           REAL NOT NULL DEFAULT 0,
    sell_volume          REAL NOT NULL DEFAULT 0,
    buy_amount           REAL NOT NULL DEFAULT 0,
    sell_amount          REAL NOT NULL DEFAULT 0,
    UNIQUE(ticker, date, securities_trader_id)
);
CREATE INDEX idx_broker_ticker_date ON stock_broker_daily(ticker, date);

CREATE TABLE stock_chip_daily (
    ticker         TEXT NOT NULL,
    date           TEXT NOT NULL,
    foreign_buy    REAL,
    foreign_sell   REAL,
    trust_buy      REAL,
    trust_sell     REAL,
    dealer_buy     REAL,
    dealer_sell    REAL,
    margin_balance REAL,
    short_balance  REAL,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX idx_chip_ticker_date ON stock_chip_daily(ticker, date);

CREATE TABLE stock_per_daily (
    ticker         TEXT NOT NULL,
    date           TEXT NOT NULL,
    per            REAL,
    pbr            REAL,
    dividend_yield REAL,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX idx_per_ticker_date ON stock_per_daily(ticker, date);

CREATE TABLE stock_revenue_monthly (
    ticker         TEXT    NOT NULL,
    year           INTEGER NOT NULL,
    month          INTEGER NOT NULL,
    revenue        REAL,
    announced_date TEXT,
    PRIMARY KEY (ticker, year, month)
);
CREATE INDEX idx_revenue_ticker_ym ON stock_revenue_monthly(ticker, year, month);

CREATE TABLE stock_financial_quarterly (
    ticker      TEXT NOT NULL,
    date        TEXT NOT NULL,
    report_type TEXT NOT NULL,
    type        TEXT NOT NULL,
    value       REAL,
    PRIMARY KEY (ticker, date, report_type, type)
);
CREATE INDEX idx_financial_ticker_date ON stock_financial_quarterly(ticker, date, report_type);

CREATE TABLE stock_dividend_history (
    ticker            TEXT NOT NULL,
    year              TEXT NOT NULL,
    cash_dividend     REAL,
    stock_dividend    REAL,
    cash_ex_date      TEXT,
    cash_payment_date TEXT,
    announcement_date TEXT,
    PRIMARY KEY (ticker, year)
);
CREATE INDEX idx_dividend_ticker ON stock_dividend_history(ticker);

CREATE TABLE price_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type     TEXT NOT NULL,
    target          TEXT NOT NULL,
    condition       TEXT NOT NULL,
    threshold       REAL NOT NULL,
    enabled         INTEGER NOT NULL DEFAULT 1,
    triggered_at    TEXT,
    triggered_value REAL,
    created_at      TEXT NOT NULL,
    indicator_key   TEXT,
    window_n        INTEGER
);
CREATE INDEX idx_alert_target ON price_alerts(target_type, target, enabled);
```

- [ ] **Step 2: Verify the file is syntactically valid**

```bash
cd stock/dashboard/backend && python -c "
import sqlite3
conn = sqlite3.connect(':memory:')
with open('db/migrations/0001_initial.sql') as f:
    conn.executescript(f.read())
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\")]
print(tables)
"
```

Expected output (order independent): all 10 tables — `indicator_snapshots, price_alerts, stock_broker_daily, stock_chip_daily, stock_dividend_history, stock_financial_quarterly, stock_per_daily, stock_revenue_monthly, stock_snapshots, watched_stocks`.

- [ ] **Step 3: Commit**

```bash
git add stock/dashboard/backend/db/migrations/0001_initial.sql
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add 0001_initial.sql with consolidated schema (MIGR-T6)

Snapshot of the schema as of today, including indicator_key and
window_n columns. Legacy data fixes intentionally excluded.
EOF
)"
```

---

### Task 7 (MIGR-T7): Wire runner into `db.init_db()`

**Files:**
- Modify: `stock/dashboard/backend/db/__init__.py`

Replace the inline schema in `init_db()` with a call to the runner. Existing call sites stay unchanged.

- [ ] **Step 1: Write a failing test first**

Append to `tests/test_db.py` (above the existing tests):

```python
def test_init_db_creates_schema_migrations_with_0001_applied():
    """init_db() now goes through the migration runner."""
    db.init_db()
    versions = [r[0] for r in db.get_connection().execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()]
    assert versions == ["0001"]
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd stock/dashboard && python -m pytest tests/test_db.py::test_init_db_creates_schema_migrations_with_0001_applied -v
```

Expected: FAIL — `schema_migrations` table does not exist (init_db still uses the inline executescript).

- [ ] **Step 3: Replace `init_db()` body**

In `stock/dashboard/backend/db/__init__.py`, replace the existing `init_db` function (currently lines ~23–156, the function with the long `executescript` and the legacy UPDATE / ALTER block) with:

```python
def init_db():
    """Bring the database up to the latest schema by running migrations."""
    from db.runner import run_migrations
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    with get_connection() as conn:
        run_migrations(conn, migrations_dir)
```

Notes:
- Delete the legacy `UPDATE indicator_snapshots SET indicator='margin_balance' WHERE indicator='margin'` block — it's already been applied to the VPS DB and is unnecessary on fresh DBs.
- Delete the `PRAGMA table_info(price_alerts)` + ALTER TABLE block — `0001_initial.sql` already creates the columns.
- Keep all other functions in `db/__init__.py` unchanged.
- The `import` is local to avoid circular import risk if anything in `db.runner` ever needs `db` symbols (currently it doesn't, but cheap insurance).

- [ ] **Step 4: Run the new test plus the full suite**

```bash
cd stock/dashboard && python -m pytest tests/ -q
```

Expected: all tests PASS, including the new T7 test and every pre-existing test (`test_db.py`, `test_alerts.py`, `test_api.py`, `test_brokers.py`, `test_chip.py`, `test_fetchers.py`, `test_fundamentals.py`, `test_migration_runner.py`).

If any pre-existing test fails, the most likely cause is a column or index that wasn't carried over to `0001_initial.sql`. Diff the file against the original `executescript` block and fix.

- [ ] **Step 5: Commit**

```bash
git add stock/dashboard/backend/db/__init__.py stock/dashboard/tests/test_db.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): init_db() now runs through migration runner (MIGR-T7)

Replaces the inline executescript and ad-hoc ALTERs with a single
run_migrations() call. Existing callers (app.py startup, backfill.py,
test fixtures) are unchanged — init_db() is a thin shim now.

Fresh DBs apply 0001_initial.sql; legacy DBs (the live VPS) hit the
runner's baseline path and are stamped without re-execution.
EOF
)"
```

---

### Task 8 (MIGR-T8): VPS-baseline integration test

Lock down the upgrade-of-live-VPS path with an end-to-end test using the real `db.init_db()` entry point and a pre-populated DB.

**Files:**
- Modify: `stock/dashboard/tests/test_db.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_db.py`:

```python
def test_init_db_baselines_existing_legacy_db(monkeypatch):
    """Simulate the live VPS DB: it already has tables but no schema_migrations.
    init_db() must mark 0001 as applied without re-running it (which would error)
    and the existing data must remain intact."""
    # Build a fresh in-memory DB and pre-populate it with a legacy-shaped
    # indicator_snapshots table + one row, mimicking the VPS state.
    db._memory_conn = None
    conn = db.get_connection()
    conn.execute(
        "CREATE TABLE indicator_snapshots ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  indicator TEXT NOT NULL,"
        "  timestamp TEXT NOT NULL,"
        "  value REAL NOT NULL,"
        "  extra_json TEXT"
        ")"
    )
    conn.execute(
        "INSERT INTO indicator_snapshots (indicator, timestamp, value) "
        "VALUES ('taiex', '2026-01-01T00:00:00', 17000.0)"
    )
    conn.commit()

    db.init_db()  # should baseline, not re-run

    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall()]
    assert versions == ["0001"]
    # Original row preserved.
    rows = conn.execute(
        "SELECT indicator, value FROM indicator_snapshots"
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [("taiex", 17000.0)]
```

Note: the existing `reset_db` autouse fixture in `conftest.py` runs *before* each test (sets `_memory_conn = None`, calls `init_db()`). For this test we need the legacy table to exist *before* `init_db()` runs, so the test re-resets `_memory_conn = None` then builds the legacy state itself before calling `init_db()`. The `monkeypatch` parameter is included for future-proofing even though the current implementation doesn't need it.

- [ ] **Step 2: Run the test**

```bash
cd stock/dashboard && python -m pytest tests/test_db.py::test_init_db_baselines_existing_legacy_db -v
```

Expected: PASS. If it fails, the baseline detection in `runner.py` is not triggering — most likely the `_LEGACY_TABLES` set is missing the table this test creates, or the `applied` check is wrong.

- [ ] **Step 3: Run the entire test suite for safety**

```bash
cd stock/dashboard && python -m pytest tests/ -q
```

Expected: every test passes.

- [ ] **Step 4: Commit**

```bash
git add stock/dashboard/tests/test_db.py
git commit -m "$(cat <<'EOF'
test(stock-dashboard): lock VPS-baseline upgrade path (MIGR-T8)

End-to-end test using db.init_db() against a pre-populated legacy DB,
asserting baseline marks 0001 as applied without touching existing rows.
EOF
)"
```

---

### Task 9 (MIGR-T9): Phase final polish

**Files:**
- Inspect: `stock/dashboard/backend/db/__init__.py`, `stock/dashboard/backend/db/runner.py`, `stock/dashboard/tests/test_migration_runner.py`, `stock/dashboard/README.md`

- [ ] **Step 1: Re-read the diff for the whole phase**

```bash
git log --oneline master..HEAD
git diff master...HEAD -- stock/dashboard/backend/db/ stock/dashboard/tests/
```

Look for: dead imports, lingering references to legacy code paths, test functions that became redundant after the change.

- [ ] **Step 2: Confirm no `from db import init_db` site silently broke**

```bash
grep -rn "init_db" stock/dashboard/
```

Expected: `init_db` still appears in `db/__init__.py` (definition), `app.py:79`, `backfill.py:206`, `tests/conftest.py:15`, and various `tests/test_*.py`. None of those need to change in this phase — the shim preserves them.

- [ ] **Step 3: Run the full test suite one final time**

```bash
cd stock/dashboard && python -m pytest tests/ -v
```

Expected: every test PASS.

- [ ] **Step 4: Add a short note to README about the migration model**

Append to `stock/dashboard/README.md`:

```markdown
## DB Migrations

Schema is now managed by `backend/db/runner.py`. To add a schema change:

1. Create `backend/db/migrations/NNNN_<snake_name>.sql` (next number, 4 digits).
2. The runner picks it up on the next `init_db()` call (i.e. on next
   service restart). Already-applied versions are recorded in
   `schema_migrations`.
3. Forward-only: never edit a migration that has been pushed to master;
   write a follow-up migration instead.

The live VPS DB was migrated in via the runner's baseline mechanism
(see `MIGR-T4`): it had the legacy schema before the runner existed,
so `0001_initial.sql` is marked applied without being re-executed.
```

- [ ] **Step 5: Commit**

```bash
git add stock/dashboard/README.md
git commit -m "$(cat <<'EOF'
docs(stock-dashboard): document migration runner workflow (MIGR-T9)

Phase MIGR final polish — adds a Migrations section to the dashboard
README explaining how to add schema changes going forward.
EOF
)"
```

---

## Spec Coverage Self-Check

Cross-reference each Phase 1 bullet from the spec (`§7 Phase 1 — MIGR-`) to the tasks above:

| Spec requirement | Task |
|---|---|
| Build `db/runner.py` (~50 LOC) | T2 (skeleton), T3 (apply), T4 (baseline), T5 (rollback test) |
| Extract current schema as `db/migrations/0001_initial.sql` | T6 |
| `init_db()` retired (replaced with shim per Phase 1 scope) | T7 |
| Tests use the runner via fixture | T7 (existing fixture now flows through runner) + T8 (new VPS-baseline test) |
| No other layer changes | Verified in T9 step 2 (`grep init_db` shows callers unchanged) |
| Forward-only, file naming `NNNN_<snake>.sql` | Enforced by `_VERSION_RE` regex in T3 |
| Already-applied versions skipped | T3 |
| Failure aborts startup (raises) | T3 + T5 |

All items covered.

## Future-phase Notes (do not implement here)

- Phase 2 will replace `init_db()` shim by calling `run_migrations()` directly from `main.py` startup, deleting the shim.
- Phase 2 will also introduce `core/settings.py`, at which point the runner can read `DB_PATH` via `settings` rather than relying on `db.get_connection()`.
- The `MIGRATIONS_DIR` path resolution in `db/__init__.py` uses `__file__`, so it works under any deployment layout.

---

## Execution Notes

- Total tasks: **9** (T1–T9). Each task ends with a passing test suite and a commit.
- Estimated time per task: 5–15 minutes.
- All commits use the `(MIGR-Tn)` step-id format per CONVENTIONS.md §5.1.
- No new Python dependencies are introduced.
- The plan is independent of the rest of the conventions adoption; it ships a runnable, deployable system at every commit boundary.
