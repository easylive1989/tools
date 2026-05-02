# Stock Dashboard BE-B: Repositories + Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `db/__init__.py` into 5 `repositories/*.py` files + thin `db/connection.py`. Split `alerts.py` into `services/{alert_engine,alert_notifier}.py`. Move `backfill.py` body into `services/backfill.py` (CLI wrapper stays). Update test_alerts.py to use settings-based monkeypatch. Replace `print()` with stdlib logging in touched files.

**Architecture:** Strict one-way dependency: `db.connection → core.*`, `repositories/* → db.connection`, `services/* → repositories.* + core.*`. Backward compat via re-exports in `db/__init__.py` and `alerts.py` so existing call sites (`from db import save_indicator`, `import alerts as alerts_module`) keep working.

**Tech Stack:** Python 3.12, sqlite3, FastAPI (existing), pydantic-settings (BE-A), pytest. No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-02-stock-dashboard-be-b-design.md`.

---

## File Structure

**Created:**
- `stock/dashboard/backend/db/connection.py` — connection factory (~25 LOC)
- `stock/dashboard/backend/repositories/__init__.py` — empty package marker
- `stock/dashboard/backend/repositories/indicators.py` — 3 functions
- `stock/dashboard/backend/repositories/stocks.py` — 5 functions
- `stock/dashboard/backend/repositories/alerts.py` — 6 functions
- `stock/dashboard/backend/repositories/chip.py` — 6 functions
- `stock/dashboard/backend/repositories/fundamentals.py` — 12 functions
- `stock/dashboard/backend/services/__init__.py` — empty package marker
- `stock/dashboard/backend/services/alert_notifier.py` — Discord delivery (settings + logger)
- `stock/dashboard/backend/services/alert_engine.py` — evaluation logic + helpers (moved from alerts.py)
- `stock/dashboard/backend/services/backfill.py` — body of old backfill.py (with logger)

**Modified:**
- `stock/dashboard/backend/db/__init__.py` — drastically thinned to ~80 lines (re-exports + init_db + purge_old_data)
- `stock/dashboard/backend/alerts.py` — reduced to ~10-line thin re-export module
- `stock/dashboard/backend/backfill.py` — reduced to ~6-line thin CLI wrapper
- `stock/dashboard/tests/test_alerts.py` — ~17 monkeypatch sites updated to settings-based pattern

**Unchanged (verified non-impact):**
- `stock/dashboard/tests/conftest.py` — autouse `db.init_db()` continues to work via re-export
- `stock/dashboard/backend/scheduler.py` — its `from db import purge_old_data` still resolves
- `stock/dashboard/backend/app.py` — its `from db import …` re-export bridge keeps working
- `stock/dashboard/backend/fetchers/*` — untouched in BE-B (Phase 3 territory)
- `stock/dashboard/backend/core/*` — built in BE-A, no changes
- All other `tests/test_*.py` files — repositories are accessed via `from db import …` re-exports

---

## Baseline

Before starting, verify the test suite reports `5 failed, 128 passed` (baseline after BE-A merged) with these specific failures (pre-existing — DO NOT FIX):

- `tests/test_brokers.py::test_brokers_endpoint_rejects_non_taiwan_ticker`
- `tests/test_brokers.py::test_brokers_endpoint_rejects_invalid_params`
- `tests/test_brokers.py::test_brokers_endpoint_returns_top5_by_net_buy`
- `tests/test_fetchers.py::test_fetch_ndc_saves_indicator`
- `tests/test_fetchers.py::test_fetch_fear_greed_saves_indicator`

After this phase the count is unchanged: `5 failed, 128 passed`. BE-B is structural; no new tests are added.

All commits use `(BE-B-Tn)` step IDs per CONVENTIONS.md §5.1.

---

## Task Breakdown

### Task 1 (BE-B-T1): Extract `db/connection.py`

**Files:**
- Create: `stock/dashboard/backend/db/connection.py`
- Modify: `stock/dashboard/backend/db/__init__.py` (top-of-file imports — replace inline `get_connection` body with re-import from new module)

- [ ] **Step 1: Verify baseline**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed, 3 warnings`. If different, stop.

- [ ] **Step 2: Create `db/connection.py`**

Write `stock/dashboard/backend/db/connection.py` with this exact content:

```python
"""Connection factory + in-memory singleton for tests.

Kept dependency-free so repositories can import this without triggering
circular imports through db/__init__.py's re-exports.
"""
import sqlite3
import threading

from core.settings import settings

DB_PATH = settings.db_path
_memory_conn = None
_memory_lock = threading.Lock()


def get_connection() -> sqlite3.Connection:
    global _memory_conn
    if DB_PATH == ":memory:":
        with _memory_lock:
            if _memory_conn is None:
                _memory_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
                _memory_conn.row_factory = sqlite3.Row
        return _memory_conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
```

- [ ] **Step 3: Replace top of `db/__init__.py` with import from `db.connection`**

Open `stock/dashboard/backend/db/__init__.py`. The current first 14 lines are:

```python
import sqlite3
import os
import threading
from datetime import datetime, timedelta, timezone

from core.settings import settings

DB_PATH = settings.db_path
_memory_conn = None
_memory_lock = threading.Lock()

def get_connection() -> sqlite3.Connection:
    global _memory_conn
    if DB_PATH == ":memory:":
        ...
```

Replace through (and including) the entire `get_connection` function body with:

```python
import os
from datetime import datetime, timedelta, timezone

from db.connection import (
    get_connection, DB_PATH, _memory_conn, _memory_lock,
)
```

(`sqlite3` and `threading` are no longer used directly in `db/__init__.py` after the connection logic moves.)

Verify `db/__init__.py` lines after this change still has `init_db`, `save_indicator`, etc. unchanged starting at the next definition.

- [ ] **Step 4: Run the full test suite to verify no regression**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`. Same baseline. If a new failure appears, debug — likely a missed import or wrong line removed.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/db/connection.py stock/dashboard/backend/db/__init__.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): extract db/connection.py (BE-B-T1)

Connection factory and in-memory singleton moved to db/connection.py.
db/__init__.py re-imports the symbols so existing `from db import
get_connection` etc. keep working.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2 (BE-B-T2): `repositories/indicators.py` (3 functions)

**Files:**
- Create: `stock/dashboard/backend/repositories/__init__.py` (empty)
- Create: `stock/dashboard/backend/repositories/indicators.py`
- Modify: `stock/dashboard/backend/db/__init__.py` (delete the 3 indicator function bodies; add re-export at bottom)

- [ ] **Step 1: Create the package marker**

```bash
mkdir -p /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/repositories
touch /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/repositories/__init__.py
```

- [ ] **Step 2: Create `repositories/indicators.py`**

Write `stock/dashboard/backend/repositories/indicators.py` with this exact content:

```python
"""Indicator snapshot repository."""
from datetime import datetime, timezone

from db.connection import get_connection


def save_indicator(indicator: str, value: float, extra_json: str = None, timestamp: datetime = None):
    ts = (timestamp or datetime.now(timezone.utc).replace(tzinfo=None)).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO indicator_snapshots (indicator, timestamp, value, extra_json) VALUES (?,?,?,?)",
            (indicator, ts, value, extra_json),
        )


def get_latest_indicator(indicator: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM indicator_snapshots WHERE indicator=? ORDER BY timestamp DESC LIMIT 1",
            (indicator,),
        ).fetchone()
        return dict(row) if row else None


def get_indicator_history(indicator: str, since: datetime) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT timestamp, value, extra_json FROM indicator_snapshots "
            "WHERE indicator=? AND timestamp>=? ORDER BY timestamp",
            (indicator, since.isoformat()),
        ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 3: Delete the 3 function bodies from `db/__init__.py`**

Open `stock/dashboard/backend/db/__init__.py`. Find and **delete** these three function definitions (currently around lines 19-44 after T1; line numbers shift as you delete):

- `def save_indicator(...)` and its body
- `def get_latest_indicator(...)` and its body
- `def get_indicator_history(...)` and its body

- [ ] **Step 4: Add re-export block at the end of `db/__init__.py`**

If `db/__init__.py` already has a `# Re-exports` block (created in earlier T tasks), append the new line. Otherwise create the block at the very bottom of the file:

```python


# Re-exports for backward compatibility (BE-B).
from repositories.indicators import (  # noqa: E402,F401
    save_indicator, get_latest_indicator, get_indicator_history,
)
```

- [ ] **Step 5: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`. Baseline preserved.

- [ ] **Step 6: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/repositories/__init__.py stock/dashboard/backend/repositories/indicators.py stock/dashboard/backend/db/__init__.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): extract repositories/indicators.py (BE-B-T2)

3 functions moved from db/__init__.py to repositories/indicators.py.
db/__init__.py re-exports them for backward compat.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3 (BE-B-T3): `repositories/stocks.py` (5 functions)

**Files:**
- Create: `stock/dashboard/backend/repositories/stocks.py`
- Modify: `stock/dashboard/backend/db/__init__.py`

- [ ] **Step 1: Create `repositories/stocks.py`**

Write `stock/dashboard/backend/repositories/stocks.py` with this exact content:

```python
"""Stock + watchlist repository."""
from datetime import datetime, timezone

from db.connection import get_connection


def save_stock_snapshot(ticker: str, price: float, change: float, change_pct: float, currency: str, name: str = ""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO stock_snapshots (ticker, timestamp, price, change, change_pct, currency, name) "
            "VALUES (?,?,?,?,?,?,?)",
            (ticker, datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), price, change, change_pct, currency, name),
        )


def get_latest_stock(ticker: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM stock_snapshots WHERE ticker=? ORDER BY timestamp DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        return dict(row) if row else None


def get_watched_tickers() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT ticker FROM watched_stocks ORDER BY added_at").fetchall()
        return [r["ticker"] for r in rows]


def add_watched_ticker(ticker: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO watched_stocks (ticker, added_at) VALUES (?,?)",
            (ticker, datetime.now(timezone.utc).replace(tzinfo=None).isoformat()),
        )


def remove_watched_ticker(ticker: str):
    """Remove ticker AND disable any stock_indicator alerts targeting it.

    The cross-table side effect (disabling alerts) is preserved verbatim from
    the pre-refactor implementation. Revisit in a later phase if desired.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM watched_stocks WHERE ticker=?", (ticker,))
        conn.execute(
            "UPDATE price_alerts SET enabled=0 "
            "WHERE target_type='stock_indicator' AND target=?",
            (ticker,)
        )
```

- [ ] **Step 2: Delete the 5 function bodies from `db/__init__.py`**

Delete the function definitions for `save_stock_snapshot`, `get_latest_stock`, `get_watched_tickers`, `add_watched_ticker`, `remove_watched_ticker` from `db/__init__.py`.

- [ ] **Step 3: Add re-export to `db/__init__.py`**

Append (or extend the existing re-export block):

```python
from repositories.stocks import (  # noqa: E402,F401
    save_stock_snapshot, get_latest_stock, get_watched_tickers,
    add_watched_ticker, remove_watched_ticker,
)
```

- [ ] **Step 4: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/repositories/stocks.py stock/dashboard/backend/db/__init__.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): extract repositories/stocks.py (BE-B-T3)

5 functions moved from db/__init__.py. remove_watched_ticker keeps its
cross-table side effect (disables stock_indicator alerts) verbatim.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4 (BE-B-T4): `repositories/alerts.py` (6 functions)

**Files:**
- Create: `stock/dashboard/backend/repositories/alerts.py`
- Modify: `stock/dashboard/backend/db/__init__.py`

- [ ] **Step 1: Create `repositories/alerts.py`**

Write `stock/dashboard/backend/repositories/alerts.py` with this exact content:

```python
"""Price-alert repository."""
from datetime import datetime, timezone

from db.connection import get_connection


def list_alerts() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM price_alerts ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def add_alert(target_type: str, target: str, condition: str, threshold: float,
              *, indicator_key: str | None = None, window_n: int | None = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO price_alerts "
            "(target_type, target, condition, threshold, indicator_key, window_n, "
            " enabled, created_at) "
            "VALUES (?,?,?,?,?,?,1,?)",
            (target_type, target, condition, threshold, indicator_key, window_n,
             datetime.now(timezone.utc).replace(tzinfo=None).isoformat()),
        )
        return cur.lastrowid


def delete_alert(alert_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM price_alerts WHERE id=?", (alert_id,))


def set_alert_enabled(alert_id: int, enabled: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE price_alerts SET enabled=?, triggered_at=NULL, triggered_value=NULL "
            "WHERE id=?",
            (1 if enabled else 0, alert_id),
        )


def get_active_alerts(target_type: str, target: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM price_alerts WHERE target_type=? AND target=? AND enabled=1",
            (target_type, target),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_alert_triggered(alert_id: int, value: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE price_alerts SET enabled=0, triggered_at=?, triggered_value=? WHERE id=?",
            (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), value, alert_id),
        )
```

- [ ] **Step 2: Delete the 6 function bodies from `db/__init__.py`**

Delete `list_alerts`, `add_alert`, `delete_alert`, `set_alert_enabled`, `get_active_alerts`, `mark_alert_triggered`.

- [ ] **Step 3: Add re-export**

Append to the re-export block:

```python
from repositories.alerts import (  # noqa: E402,F401
    list_alerts, add_alert, delete_alert, set_alert_enabled,
    get_active_alerts, mark_alert_triggered,
)
```

- [ ] **Step 4: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/repositories/alerts.py stock/dashboard/backend/db/__init__.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): extract repositories/alerts.py (BE-B-T4)

6 functions moved from db/__init__.py. price_alerts CRUD now lives
in its own repository file.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5 (BE-B-T5): `repositories/chip.py` (6 functions: 3 broker + 3 chip)

**Files:**
- Create: `stock/dashboard/backend/repositories/chip.py`
- Modify: `stock/dashboard/backend/db/__init__.py`

- [ ] **Step 1: Create `repositories/chip.py`**

Write `stock/dashboard/backend/repositories/chip.py` with this exact content:

```python
"""Broker + chip per-day repository."""
from db.connection import get_connection


# --- Broker (per-trader-per-day) ---

def save_broker_daily_rows(rows: list[dict]) -> None:
    """Bulk upsert per-broker per-day aggregates.

    Each row needs: ticker, date, securities_trader_id, securities_trader,
    buy_volume, sell_volume, buy_amount, sell_amount.
    """
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_broker_daily "
            "(ticker, date, securities_trader_id, securities_trader, "
            " buy_volume, sell_volume, buy_amount, sell_amount) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, date, securities_trader_id) DO UPDATE SET "
            " securities_trader=excluded.securities_trader, "
            " buy_volume=excluded.buy_volume, "
            " sell_volume=excluded.sell_volume, "
            " buy_amount=excluded.buy_amount, "
            " sell_amount=excluded.sell_amount",
            [
                (
                    r["ticker"], r["date"], r["securities_trader_id"],
                    r.get("securities_trader") or "",
                    r.get("buy_volume", 0) or 0,
                    r.get("sell_volume", 0) or 0,
                    r.get("buy_amount", 0) or 0,
                    r.get("sell_amount", 0) or 0,
                )
                for r in rows
            ],
        )


def get_broker_daily_range(ticker: str, since_date: str) -> list[dict]:
    """Return per-broker daily aggregates for ticker on or after since_date (YYYY-MM-DD)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, securities_trader_id, securities_trader, "
            "       buy_volume, sell_volume, buy_amount, sell_amount "
            "FROM stock_broker_daily "
            "WHERE ticker=? AND date>=? "
            "ORDER BY date",
            (ticker, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_broker_date(ticker: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM stock_broker_daily WHERE ticker=?",
            (ticker,),
        ).fetchone()
        return row["d"] if row and row["d"] else None


# --- Chip (per-day aggregated) ---

def save_chip_daily_rows(rows: list[dict]) -> None:
    """Bulk upsert per-day stock chip rows."""
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_chip_daily "
            "(ticker, date, foreign_buy, foreign_sell, trust_buy, trust_sell, "
            " dealer_buy, dealer_sell, margin_balance, short_balance) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, date) DO UPDATE SET "
            " foreign_buy=COALESCE(excluded.foreign_buy, foreign_buy), "
            " foreign_sell=COALESCE(excluded.foreign_sell, foreign_sell), "
            " trust_buy=COALESCE(excluded.trust_buy, trust_buy), "
            " trust_sell=COALESCE(excluded.trust_sell, trust_sell), "
            " dealer_buy=COALESCE(excluded.dealer_buy, dealer_buy), "
            " dealer_sell=COALESCE(excluded.dealer_sell, dealer_sell), "
            " margin_balance=COALESCE(excluded.margin_balance, margin_balance), "
            " short_balance=COALESCE(excluded.short_balance, short_balance)",
            [
                (r["ticker"], r["date"],
                 r.get("foreign_buy"), r.get("foreign_sell"),
                 r.get("trust_buy"), r.get("trust_sell"),
                 r.get("dealer_buy"), r.get("dealer_sell"),
                 r.get("margin_balance"), r.get("short_balance"))
                for r in rows
            ],
        )


def get_chip_daily_range(ticker: str, since_date: str) -> list[dict]:
    """Per-day chip rows for ticker on or after since_date (YYYY-MM-DD)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, foreign_buy, foreign_sell, trust_buy, trust_sell, "
            "       dealer_buy, dealer_sell, margin_balance, short_balance "
            "FROM stock_chip_daily WHERE ticker=? AND date>=? ORDER BY date",
            (ticker, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_chip_date(ticker: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM stock_chip_daily WHERE ticker=?",
            (ticker,),
        ).fetchone()
        return row["d"] if row and row["d"] else None
```

- [ ] **Step 2: Delete the 6 function bodies from `db/__init__.py`**

Delete `save_broker_daily_rows`, `get_broker_daily_range`, `get_latest_broker_date`, `save_chip_daily_rows`, `get_chip_daily_range`, `get_latest_chip_date`.

- [ ] **Step 3: Add re-export**

Append:

```python
from repositories.chip import (  # noqa: E402,F401
    save_broker_daily_rows, get_broker_daily_range, get_latest_broker_date,
    save_chip_daily_rows, get_chip_daily_range, get_latest_chip_date,
)
```

- [ ] **Step 4: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/repositories/chip.py stock/dashboard/backend/db/__init__.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): extract repositories/chip.py (BE-B-T5)

6 functions moved from db/__init__.py: 3 broker + 3 chip per-day.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6 (BE-B-T6): `repositories/fundamentals.py` (12 functions)

**Files:**
- Create: `stock/dashboard/backend/repositories/fundamentals.py`
- Modify: `stock/dashboard/backend/db/__init__.py`

- [ ] **Step 1: Create `repositories/fundamentals.py`**

Write `stock/dashboard/backend/repositories/fundamentals.py` with this exact content:

```python
"""PER + Revenue + Financial + Dividend repository."""
import re

from db.connection import get_connection


# --- PER ---

def save_per_daily_rows(rows: list[dict]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_per_daily (ticker, date, per, pbr, dividend_yield) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(ticker, date) DO UPDATE SET "
            " per=excluded.per, pbr=excluded.pbr, dividend_yield=excluded.dividend_yield",
            [(r["ticker"], r["date"], r.get("per"), r.get("pbr"), r.get("dividend_yield"))
             for r in rows],
        )


def get_per_daily_range(ticker: str, since_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, per, pbr, dividend_yield FROM stock_per_daily "
            "WHERE ticker=? AND date>=? ORDER BY date",
            (ticker, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_per_date(ticker: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM stock_per_daily WHERE ticker=?",
            (ticker,),
        ).fetchone()
        return row["d"] if row and row["d"] else None


# --- Revenue ---

def save_revenue_monthly_rows(rows: list[dict]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_revenue_monthly "
            "(ticker, year, month, revenue, announced_date) VALUES (?,?,?,?,?) "
            "ON CONFLICT(ticker, year, month) DO UPDATE SET "
            " revenue=excluded.revenue, announced_date=excluded.announced_date",
            [(r["ticker"], r["year"], r["month"], r.get("revenue"), r.get("announced_date"))
             for r in rows],
        )


def get_revenue_monthly_range(ticker: str, since_year: int, since_month: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT year, month, revenue, announced_date FROM stock_revenue_monthly "
            "WHERE ticker=? AND (year * 12 + month) >= (? * 12 + ?) "
            "ORDER BY year, month",
            (ticker, since_year, since_month),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_revenue_ym(ticker: str) -> tuple[int, int] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT year, month FROM stock_revenue_monthly "
            "WHERE ticker=? ORDER BY year DESC, month DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        return (row["year"], row["month"]) if row else None


# --- Financial (income/balance/cash_flow) ---

def save_financial_quarterly_rows(rows: list[dict]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_financial_quarterly "
            "(ticker, date, report_type, type, value) VALUES (?,?,?,?,?) "
            "ON CONFLICT(ticker, date, report_type, type) DO UPDATE SET "
            " value=excluded.value",
            [(r["ticker"], r["date"], r["report_type"], r["type"], r.get("value"))
             for r in rows],
        )


def get_financial_quarterly_range(ticker: str, report_type: str, since_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, type, value FROM stock_financial_quarterly "
            "WHERE ticker=? AND report_type=? AND date>=? "
            "ORDER BY date, type",
            (ticker, report_type, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_financial_date(ticker: str, report_type: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM stock_financial_quarterly "
            "WHERE ticker=? AND report_type=?",
            (ticker, report_type),
        ).fetchone()
        return row["d"] if row and row["d"] else None


# --- Dividend ---

def save_dividend_history_rows(rows: list[dict]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_dividend_history "
            "(ticker, year, cash_dividend, stock_dividend, cash_ex_date, cash_payment_date, announcement_date) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, year) DO UPDATE SET "
            " cash_dividend=excluded.cash_dividend, "
            " stock_dividend=excluded.stock_dividend, "
            " cash_ex_date=excluded.cash_ex_date, "
            " cash_payment_date=excluded.cash_payment_date, "
            " announcement_date=excluded.announcement_date",
            [(r["ticker"], r["year"], r.get("cash_dividend"), r.get("stock_dividend"),
              r.get("cash_ex_date"), r.get("cash_payment_date"), r.get("announcement_date"))
             for r in rows],
        )


def get_dividend_history(ticker: str) -> list[dict]:
    """Return all dividend rows for ticker, sorted by ROC year + 季 numeric prefix."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT year, cash_dividend, stock_dividend, cash_ex_date, "
            "       cash_payment_date, announcement_date "
            "FROM stock_dividend_history WHERE ticker=?",
            (ticker,),
        ).fetchall()
    result = [dict(r) for r in rows]

    def _key(row: dict) -> tuple[int, int]:
        # 抓出「ROC 年」與「季」做自然排序;格式如 "114年第3季"
        y = row["year"] or ""
        ym = re.match(r"(\d+)", y)
        qm = re.search(r"第(\d+)", y)
        return (int(ym.group(1)) if ym else 0,
                int(qm.group(1)) if qm else 0)

    result.sort(key=_key)
    return result


def get_latest_dividend_announce_date(ticker: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(announcement_date) AS d FROM stock_dividend_history WHERE ticker=?",
            (ticker,),
        ).fetchone()
        return row["d"] if row and row["d"] else None
```

- [ ] **Step 2: Delete the 12 function bodies from `db/__init__.py`**

Delete all 12 functions: `save_per_daily_rows`, `get_per_daily_range`, `get_latest_per_date`, `save_revenue_monthly_rows`, `get_revenue_monthly_range`, `get_latest_revenue_ym`, `save_financial_quarterly_rows`, `get_financial_quarterly_range`, `get_latest_financial_date`, `save_dividend_history_rows`, `get_dividend_history`, `get_latest_dividend_announce_date`.

After this delete, `db/__init__.py` should no longer have any SQL function bodies — only `init_db`, `purge_old_data`, imports, and re-exports.

- [ ] **Step 3: Add re-export**

Append:

```python
from repositories.fundamentals import (  # noqa: E402,F401
    save_per_daily_rows, get_per_daily_range, get_latest_per_date,
    save_revenue_monthly_rows, get_revenue_monthly_range, get_latest_revenue_ym,
    save_financial_quarterly_rows, get_financial_quarterly_range, get_latest_financial_date,
    save_dividend_history_rows, get_dividend_history, get_latest_dividend_announce_date,
)
```

- [ ] **Step 4: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/repositories/fundamentals.py stock/dashboard/backend/db/__init__.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): extract repositories/fundamentals.py (BE-B-T6)

12 functions moved (PER 3 + Revenue 3 + Financial 3 + Dividend 3).
db/__init__.py is now SQL-free except for init_db + purge_old_data.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7 (BE-B-T7): Tidy `db/__init__.py`

**Files:**
- Modify: `stock/dashboard/backend/db/__init__.py`

This is a cleanup task. After T1-T6 the file should already be in good shape. T7 verifies the final structure and removes any inconsistencies.

- [ ] **Step 1: Read the current file and confirm structure**

```bash
wc -l /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/db/__init__.py
cat /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/db/__init__.py
```

Expected: ~80 lines, containing (in order):

1. Module docstring (optional, can add if missing)
2. `import os` and `from datetime import datetime, timedelta, timezone`
3. `from db.connection import get_connection, DB_PATH, _memory_conn, _memory_lock`
4. `def init_db():` (unchanged from BE-A)
5. `def purge_old_data(days: int = 1095):` (unchanged from pre-BE-B)
6. Re-export block: 5 `from repositories.X import (...)` statements

If the file matches this shape, no changes needed — proceed to commit (or skip if no diff).

- [ ] **Step 2: Replace the file with the canonical shape**

If the file deviates from the canonical shape (e.g. orphan imports, wrong ordering), replace it entirely with this content:

```python
"""Database package.

Public API kept stable via re-exports so call sites like
`from db import save_indicator` continue to work after the BE-B split.
"""
import os
from datetime import datetime, timedelta, timezone

from db.connection import (
    get_connection, DB_PATH, _memory_conn, _memory_lock,
)


def init_db():
    """Bring the database up to the latest schema by running migrations."""
    from db.runner import run_migrations
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    with get_connection() as conn:
        run_migrations(conn, migrations_dir)


def purge_old_data(days: int = 1095):
    """Delete data older than `days`. Cross-table maintenance run weekly by scheduler."""
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).isoformat()
    cutoff_date = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_connection() as conn:
        conn.execute("DELETE FROM indicator_snapshots WHERE timestamp<?", (cutoff,))
        conn.execute("DELETE FROM stock_snapshots WHERE timestamp<?", (cutoff,))
        conn.execute("DELETE FROM stock_broker_daily WHERE date<?", (cutoff_date,))
        conn.execute("DELETE FROM stock_chip_daily WHERE date<?", (cutoff_date,))
        conn.execute("DELETE FROM stock_per_daily WHERE date<?", (cutoff_date,))
        conn.execute(
            "DELETE FROM stock_revenue_monthly "
            "WHERE (year * 12 + month) < (? * 12 + ?)",
            (int(cutoff_date[:4]), int(cutoff_date[5:7]))
        )
        conn.execute("DELETE FROM stock_financial_quarterly WHERE date<?", (cutoff_date,))
        # dividend not purged (long history important).


# Re-exports for backward compatibility.
from repositories.indicators import (  # noqa: E402,F401
    save_indicator, get_latest_indicator, get_indicator_history,
)
from repositories.stocks import (  # noqa: E402,F401
    save_stock_snapshot, get_latest_stock, get_watched_tickers,
    add_watched_ticker, remove_watched_ticker,
)
from repositories.alerts import (  # noqa: E402,F401
    list_alerts, add_alert, delete_alert, set_alert_enabled,
    get_active_alerts, mark_alert_triggered,
)
from repositories.chip import (  # noqa: E402,F401
    save_broker_daily_rows, get_broker_daily_range, get_latest_broker_date,
    save_chip_daily_rows, get_chip_daily_range, get_latest_chip_date,
)
from repositories.fundamentals import (  # noqa: E402,F401
    save_per_daily_rows, get_per_daily_range, get_latest_per_date,
    save_revenue_monthly_rows, get_revenue_monthly_range, get_latest_revenue_ym,
    save_financial_quarterly_rows, get_financial_quarterly_range, get_latest_financial_date,
    save_dividend_history_rows, get_dividend_history, get_latest_dividend_announce_date,
)
```

- [ ] **Step 3: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

- [ ] **Step 4: Commit (skip if no diff)**

```bash
cd /Users/paulwu/Documents/Github/tools && git diff --quiet stock/dashboard/backend/db/__init__.py || (git add stock/dashboard/backend/db/__init__.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): tidy db/__init__.py final shape (BE-B-T7)

Canonical layout: imports, init_db, purge_old_data, then re-exports.
Verifies db/__init__.py is < 100 lines after the repository split.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)")
```

If `git diff --quiet` returned 0 (no diff), the file was already in canonical shape and no commit is created. That is fine; proceed to T8.

---

### Task 8 (BE-B-T8): Create `services/alert_notifier.py`

**Files:**
- Create: `stock/dashboard/backend/services/__init__.py` (empty)
- Create: `stock/dashboard/backend/services/alert_notifier.py`

- [ ] **Step 1: Create the package marker**

```bash
mkdir -p /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/services
touch /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/services/__init__.py
```

- [ ] **Step 2: Create `services/alert_notifier.py`**

Write `stock/dashboard/backend/services/alert_notifier.py` with this exact content:

```python
"""Discord notifier for triggered alerts. Reads webhook URL from settings."""
import logging
import os
import sys

# sys.path bootstrap to import common.notify (repo-root-relative)
_here = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    if os.path.isdir(os.path.join(_here, "common")):
        sys.path.insert(0, _here)
        break
    _here = os.path.dirname(_here)

from common.notify import send_to_discord
from core.settings import settings

logger = logging.getLogger(__name__)


def notify_triggered(payload: dict, *, alert_id: int) -> None:
    """Send a Discord embed for a triggered alert.

    Silent no-op if webhook is unset (test/dev mode); failures are logged
    but never propagate (Discord delivery is best-effort).
    """
    webhook_secret = settings.discord_stock_webhook_url
    webhook = webhook_secret.get_secret_value() if webhook_secret else None
    if not webhook:
        logger.info("alert_notify_skipped alert_id=%s reason=no_webhook", alert_id)
        return
    try:
        send_to_discord(webhook, payload)
        logger.info("alert_notified alert_id=%s", alert_id)
    except Exception as e:
        logger.warning("alert_notify_failed alert_id=%s error=%s", alert_id, e)
```

- [ ] **Step 3: Smoke-import**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "from services.alert_notifier import notify_triggered, send_to_discord, settings; print('ok')"
```

Expected: prints `ok`. If it errors with `ImportError: cannot import name 'common.notify'`, the sys.path bootstrap failed — verify the loop logic.

- [ ] **Step 4: Run full suite (no behavioural change yet)**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`. (alerts.py still calls `send_to_discord` directly with `os.environ.get`; this task hasn't wired notifier into alerts yet.)

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/services/__init__.py stock/dashboard/backend/services/alert_notifier.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add services/alert_notifier.py (BE-B-T8)

Discord notifier reads webhook from settings.discord_stock_webhook_url.
Logs alert_notified / alert_notify_skipped / alert_notify_failed.
Not yet wired in — T9 migrates alerts.py to call notify_triggered.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9 (BE-B-T9): Wire `alerts.py` to notifier + update test pattern

This is the most invasive task. It does three things together because they must land atomically (split commits would leave the suite red):

1. `alerts.py` calls `notify_triggered(payload, alert_id=...)` instead of inline `send_to_discord` + `os.environ.get`.
2. `alerts.py` re-exports `send_to_discord`, `settings`, `notify_triggered` so test patches reach the right object.
3. `tests/test_alerts.py` switches all 17 webhook patches and 3 `send_to_discord` patches to the new pattern.

**Files:**
- Modify: `stock/dashboard/backend/alerts.py` (substantial)
- Modify: `stock/dashboard/tests/test_alerts.py` (~17 webhook + ~3 send_to_discord sites)

- [ ] **Step 1: Modify `alerts.py` to call `notify_triggered`**

Locate in `stock/dashboard/backend/alerts.py` the block around the `os.environ.get("DISCORD_STOCK_WEBHOOK_URL")` line (search for that string). It is currently:

```python
    name = display_name or _alert_display_name(target_type, target, indicator_key)
    webhook = os.environ.get("DISCORD_STOCK_WEBHOOK_URL")

    for alert in active_alerts:
        ...
        if triggered:
            payload = _build_payload(alert, triggered_value, name)
            if not webhook:
                print(f"[alerts] webhook not set, skipping notification for alert {alert['id']}")
            else:
                try:
                    send_to_discord(webhook, payload)
                    print(f"[alerts] notified: {name} {cond} {threshold} (value={triggered_value})")
                except Exception as e:
                    print(f"[alerts] discord error for alert {alert['id']}: {e}")
            mark_alert_triggered(alert["id"], triggered_value)
```

Replace with:

```python
    name = display_name or _alert_display_name(target_type, target, indicator_key)

    for alert in active_alerts:
        ...
        if triggered:
            payload = _build_payload(alert, triggered_value, name)
            notify_triggered(payload, alert_id=alert["id"])
            mark_alert_triggered(alert["id"], triggered_value)
```

(The `...` is the unchanged evaluation logic — keep it verbatim.)

- [ ] **Step 2: Add the notifier import + settings re-export to `alerts.py` top**

Below the existing `from common.notify import send_to_discord` line in `alerts.py`, add:

```python
from services.alert_notifier import notify_triggered
from core.settings import settings  # re-exported so tests can monkeypatch alerts_module.settings
```

Keep `from common.notify import send_to_discord` so `alerts_module.send_to_discord` remains a valid (if no-longer-called-internally) reference for tests that patch it.

- [ ] **Step 3: Update `tests/test_alerts.py` — webhook patches**

Open `stock/dashboard/tests/test_alerts.py`. At the top, add or ensure these imports exist:

```python
from pydantic import SecretStr
from unittest.mock import patch  # may already be imported
```

Then update the 17 patch sites:

**Pattern A: 3× `monkeypatch.setenv` sites (lines 16, 34, 59 — line numbers approximate)**

Find:
```python
monkeypatch.setenv("DISCORD_STOCK_WEBHOOK_URL", "http://example.invalid/hook")
```

Replace with:
```python
monkeypatch.setattr(alerts_module.settings, "discord_stock_webhook_url",
                    SecretStr("http://example.invalid/hook"))
```

**Pattern B: 1× `monkeypatch.delenv` site (line ~46)**

Find:
```python
monkeypatch.delenv("DISCORD_STOCK_WEBHOOK_URL", raising=False)
```

Replace with:
```python
monkeypatch.setattr(alerts_module.settings, "discord_stock_webhook_url", None)
```

**Pattern C: 10× `with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": ...}):` sites (lines 151, 166, 183, 196, 279, 299, 312, 325, 425, 443)**

Find:
```python
with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
```

Replace each with:
```python
with patch.object(alerts_module.settings, "discord_stock_webhook_url",
                   SecretStr("https://example/x")):
```

(`patch.object` from `unittest.mock` works on instance attributes; settings is a pydantic BaseSettings instance which permits attribute assignment.)

- [ ] **Step 4: Update `tests/test_alerts.py` — `send_to_discord` patches**

Find the 3 occurrences of:
```python
monkeypatch.setattr(alerts_module, "send_to_discord", lambda url, payload: sent.append(payload))
```

(Lines ~15, 33, 58.)

Add an import at the top of `test_alerts.py` if not present:
```python
import services.alert_notifier as alert_notifier
```

Replace each `monkeypatch.setattr` line with:
```python
monkeypatch.setattr(alert_notifier, "send_to_discord", lambda url, payload: sent.append(payload))
```

(The runtime `send_to_discord` reference inside `notify_triggered` is `services.alert_notifier.send_to_discord`. The patch must target *that* attribute, not `alerts_module.send_to_discord`, for the swap to actually intercept the Discord call.)

- [ ] **Step 5: Run only the alerts tests first**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/test_alerts.py -v 2>&1 | tail -30
```

Expected: every alerts test passes. If any fails:
- Look at which patch site is missed
- Verify `alerts_module.settings` and `alerts_module.send_to_discord` reference what the test expects
- Verify `alert_notifier.send_to_discord` is the actual runtime reference

- [ ] **Step 6: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed` (baseline).

- [ ] **Step 7: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/alerts.py stock/dashboard/tests/test_alerts.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): wire alerts.py to alert_notifier + update tests (BE-B-T9)

alerts.py.check_alerts() now calls services.alert_notifier.notify_triggered
instead of doing the env-read + Discord-call + print inline. Test pattern
flips from os.environ monkeypatching to settings attribute patching;
send_to_discord patch target moves to services.alert_notifier.

Resolves BE-A T7 deferral: webhook routing now flows through settings.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10 (BE-B-T10): Extract `services/alert_engine.py` + reduce `alerts.py` to thin re-export

**Files:**
- Create: `stock/dashboard/backend/services/alert_engine.py`
- Modify: `stock/dashboard/backend/alerts.py` (drastically)

- [ ] **Step 1: Create `services/alert_engine.py`**

The full body of the current `alerts.py` (post-T9), minus the now-redundant Discord-related top-of-file imports (the `_here` bootstrap + `from common.notify import send_to_discord`), goes into `services/alert_engine.py`.

Specifically, the new file contains:

- Module docstring
- Imports: `import logging`, `from datetime import ...`, repositories imports (alerts, indicators, fundamentals, chip, stocks), `from services.alert_notifier import notify_triggered`
- `logger = logging.getLogger(__name__)`
- `INDICATOR_LABELS` constant
- `INDICATOR_UNITS` constant
- All 10 private helpers (`_check_streak`, `_get_stock_indicator_history`, `_pct_rank`, `_get_stock_revenue_yoy`, `_get_stock_quarterly_yoy`, `_get_stock_yearly_yoy`, `_format_value`, `_latest_indicator_history`, `_alert_display_name`, `_build_payload`)
- `def check_alerts(...)` (post-T9 form)

Write `stock/dashboard/backend/services/alert_engine.py`. Use the current `stock/dashboard/backend/alerts.py` content as the source — copy it, then remove:
- The `import os; import sys` lines (no longer needed for sys.path bootstrap; that bootstrap happens in `alert_notifier.py`)
- The `_here = ...; for _ in range(5): ...` bootstrap loop
- The `from common.notify import send_to_discord` line (notifier owns this)
- The `from core.settings import settings` line (notifier owns this)

Result imports at the top of `alert_engine.py`:

```python
"""Alert evaluation logic.

Pure functions over repository state; delivery is delegated to
services.alert_notifier.notify_triggered.

Note: there is also `repositories.alerts` (table CRUD). This module
operates on the alerts but is not a repository itself.
"""
import logging
from datetime import datetime, timedelta, timezone

from repositories.alerts import (
    get_active_alerts, mark_alert_triggered,
)
from repositories.indicators import get_latest_indicator, get_indicator_history
from repositories.fundamentals import (
    get_revenue_monthly_range, get_financial_quarterly_range,
    get_dividend_history,
)
from repositories.chip import get_chip_daily_range
from repositories.stocks import get_latest_stock
from services.alert_notifier import notify_triggered

logger = logging.getLogger(__name__)
```

(Adjust the imports above if the helpers actually use a different subset of repositories — confirm by grepping the current `alerts.py` for repository function calls.)

After the imports come `INDICATOR_LABELS`, `INDICATOR_UNITS`, all helpers, and `check_alerts` — copy verbatim from `alerts.py`. The imports inside the body that were `from db import …` can stay as-is during the copy because the re-exports still resolve; or you can update them now to direct repository imports. **Update them to direct repository imports** for clarity.

- [ ] **Step 2: Replace `alerts.py` with thin re-export**

Open `stock/dashboard/backend/alerts.py`. Replace the entire file with:

```python
"""DEPRECATED module path. Kept for backward compat with existing imports.

New code should import from services.alert_engine / services.alert_notifier.
"""
from services.alert_engine import (  # noqa: F401
    check_alerts, INDICATOR_LABELS, INDICATOR_UNITS,
)
from services.alert_notifier import (  # noqa: F401
    notify_triggered, send_to_discord,
)
from core.settings import settings  # noqa: F401
```

- [ ] **Step 3: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

If `test_alerts.py` fails with `AttributeError: module 'alerts' has no attribute X`:
- The test references something not re-exported. Add it to the alerts.py re-export list.

If a test fails with `monkeypatch.setattr` not affecting behaviour:
- Verify `alerts_module.settings is services.alert_notifier.settings is core.settings.settings` (same instance).
- Verify the test patches `alert_notifier.send_to_discord`, not `alerts_module.send_to_discord`.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/services/alert_engine.py stock/dashboard/backend/alerts.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): extract services/alert_engine.py (BE-B-T10)

alerts.py becomes a thin re-export module forwarding to
services.alert_engine and services.alert_notifier. Engine module
imports repositories directly (not through db re-exports).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11 (BE-B-T11): `services/backfill.py` + thin `backend/backfill.py` wrapper

**Files:**
- Create: `stock/dashboard/backend/services/backfill.py`
- Modify: `stock/dashboard/backend/backfill.py` (drastic shrink)

The original `backfill.py` body moves into `services/backfill.py`. Inside the new file every `print(...)` becomes a `logger.x(...)` call following the categorisation rule (info / warning / error). The module-level `if __name__ == "__main__":` block is wrapped in a `def main():` function so the wrapper can call it.

- [ ] **Step 1: Read the current backfill.py to inventory the prints**

```bash
grep -n "print(" /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/backfill.py
```

Each print falls into one of three categories:
- `[backfill] X from Y …` (start) → `logger.info`
- `Inserted N rows for X` (done count) → `logger.info`
- `[backfill] Done.` → `logger.info`
- `No data` / `No historical data` / `Cannot find CSRF token` → `logger.warning`
- (No try/except prints currently — but if any caught-exception print exists, use `logger.error`)

- [ ] **Step 2: Create `services/backfill.py`**

Write `stock/dashboard/backend/services/backfill.py` as the new home of backfill logic. Take the current `stock/dashboard/backend/backfill.py` content and apply these transformations:

1. Add at top: `import logging` and `logger = logging.getLogger(__name__)`.
2. Keep the `sys.path.insert(0, os.path.dirname(__file__))` bootstrap, but adjust the path because we're one directory deeper now:

```python
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

(That makes `from db import …` resolve from `backend/`.)

3. Replace every `print(f"[backfill] X")` with `logger.info("backfill_X ...", ...)` using grep-friendly tokens (e.g. `logger.info("backfill_yfinance_start indicator=%s ticker=%s", indicator, ticker_symbol)`).
4. Replace every `print("  No data")` (or similar) with `logger.warning("backfill_no_data indicator=%s", indicator)` (or context-appropriate name).
5. Wrap the existing `if __name__ == "__main__":` body into:

```python
def main():
    init_db()
    # ... (existing main loop body, with prints already replaced)


if __name__ == "__main__":
    main()
```

The full transformed content must be a single file — no truncation. Reference the original `backfill.py` line by line; keep all import statements, all helper function definitions, and the main block intact (only the prints transform).

If the function structure in `backfill.py` is unclear, here is the high-level skeleton it should match:

```python
"""Historical data backfill CLI."""
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bs4 import BeautifulSoup

from db import init_db, get_connection, save_indicator

logger = logging.getLogger(__name__)


def _ts(dt: datetime) -> str:
    ...


def _backfill_yf(indicator: str, ticker_symbol: str, period: str = "5y"):
    logger.info("backfill_yfinance_start indicator=%s ticker=%s", indicator, ticker_symbol)
    ...
    if df is None or df.empty:
        logger.warning("backfill_no_data indicator=%s", indicator)
        return 0
    ...
    logger.info("backfill_inserted indicator=%s rows=%d", indicator, inserted)
    return inserted


# ... (other backfill functions, similar pattern)


def main():
    init_db()
    _backfill_yf("taiex", "^TWII")
    _backfill_yf("fx", "TWD=X")
    _backfill_tw_volume()
    _backfill_us_volume()
    _backfill_ndc()
    _backfill_fear_greed()
    _backfill_chip_total()
    logger.info("backfill_done")


if __name__ == "__main__":
    from core.logging import setup_logging
    setup_logging()
    main()
```

(Use the actual function names and signatures from the existing `backfill.py`; the skeleton above is illustrative.)

- [ ] **Step 3: Replace `backend/backfill.py` with thin wrapper**

Open `stock/dashboard/backend/backfill.py`. Replace the entire file with:

```python
"""CLI entry point. Delegates to services.backfill.

Run from backend/ as: python backfill.py
"""
from services.backfill import main

if __name__ == "__main__":
    from core.logging import setup_logging
    setup_logging()
    main()
```

- [ ] **Step 4: Smoke-import**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "from services.backfill import main; print('ok')"
```

Expected: prints `ok`. If `ImportError`, the sys.path bootstrap inside `services/backfill.py` is wrong — verify the depth (`os.path.dirname(os.path.dirname(...))` should reach `backend/`).

- [ ] **Step 5: Smoke-run the wrapper (no actual backfill, just argv check)**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
import backfill
print('main =', backfill.main)
"
```

Expected: prints something like `main = <function main at 0x...>`. The function reference should resolve through the wrapper.

- [ ] **Step 6: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`. (No tests directly invoke backfill, so this verifies nothing else got broken.)

- [ ] **Step 7: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/services/backfill.py stock/dashboard/backend/backfill.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): move backfill to services + thin CLI wrapper (BE-B-T11)

backend/backfill.py becomes a 6-line wrapper that delegates to
services.backfill.main(). All print() calls inside services/backfill.py
replaced with stdlib logging. Existing `python backfill.py` invocation
still works.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12 (BE-B-T12): Final verification

**Files:**
- Inspect only.

- [ ] **Step 1: Verify the new structure**

```bash
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/repositories/
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/services/
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/db/
```

Expected:
- `repositories/`: `__init__.py`, `alerts.py`, `chip.py`, `fundamentals.py`, `indicators.py`, `stocks.py` (and `__pycache__/`).
- `services/`: `__init__.py`, `alert_engine.py`, `alert_notifier.py`, `backfill.py` (and `__pycache__/`).
- `db/`: `__init__.py`, `connection.py`, `runner.py`, `migrations/` (and `__pycache__/`).

- [ ] **Step 2: Verify file size targets**

```bash
wc -l /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/db/__init__.py /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/db/connection.py /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/alerts.py /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/backfill.py
```

Expected:
- `db/__init__.py` ≤ 100 lines (was 429 before BE-B)
- `db/connection.py` ≤ 30 lines
- `alerts.py` ≤ 15 lines
- `backfill.py` ≤ 10 lines

If any exceeds the target, inspect for forgotten code that should have been moved.

- [ ] **Step 3: Verify no `print(` remains in services/**

```bash
grep -rn "^[[:space:]]*print(" /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/services/
```

Expected: zero matches. (BE-B's print → logger sweep covers `services/alert_engine.py`, `services/alert_notifier.py`, `services/backfill.py`. Files outside `services/` may still have print — they're not in BE-B scope.)

- [ ] **Step 4: Verify backward compat — sample `from db import …` calls**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from db import save_indicator, get_latest_indicator, init_db, purge_old_data, get_connection
from db import save_stock_snapshot, list_alerts, save_chip_daily_rows, save_per_daily_rows
import alerts
print('alerts.check_alerts =', alerts.check_alerts.__module__)
print('alerts.send_to_discord =', alerts.send_to_discord)
print('alerts.settings =', type(alerts.settings).__name__)
print('alerts.notify_triggered =', alerts.notify_triggered.__module__)
print('ok')
"
```

Expected: prints
```
alerts.check_alerts = services.alert_engine
alerts.send_to_discord = <function send_to_discord at 0x...>
alerts.settings = Settings
alerts.notify_triggered = services.alert_notifier
ok
```

- [ ] **Step 5: Run the full test suite one final time**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed, 3 warnings`. The 5 failures are still the pre-existing baseline.

- [ ] **Step 6: Verify the branch log is clean**

```bash
cd /Users/paulwu/Documents/Github/tools && git log --oneline master..HEAD
```

Expected (in reverse chronological order):

```
… BE-B-T11
… BE-B-T10
… BE-B-T9
… BE-B-T8
… BE-B-T7  (skip if no diff)
… BE-B-T6
… BE-B-T5
… BE-B-T4
… BE-B-T3
… BE-B-T2
… BE-B-T1
```

(11 or 12 commits depending on whether T7 had a diff to commit.)

- [ ] **Step 7: No commit needed for verification**

This task is read-only verification. Nothing to commit.

---

## Spec Coverage Self-Check

| Spec section | Task |
|---|---|
| §1 Target structure (db/connection, repositories/, services/) | T1 (connection); T2-T6 (repositories); T8, T10, T11 (services) |
| §2 Repository mapping (5 files, 32 functions) | T2 (3) + T3 (5) + T4 (6) + T5 (6) + T6 (12) = 32 ✓ |
| §2 db/__init__.py ≤ 100 lines, init_db + purge_old_data + re-exports | T7 (canonical shape) + T12 step 2 (verification) |
| §3 services/alert_engine.py | T10 |
| §3 services/alert_notifier.py | T8 |
| §3 alerts.py thin re-export | T10 |
| §3 services/backfill.py + thin backend/backfill.py | T11 |
| §4 print → logger mapping (alert_notifier 3 sites; backfill ~15 sites) | T8 (notifier loggers); T11 (backfill loggers) |
| §5 Test pattern updates (~17 webhook + ~3 send_to_discord) | T9 |
| §6 Risks (re-export ordering, monkeypatch target, alerts naming) | T1 (one-way deps), T9 (patch targets), T10 (engine docstring) |
| §7 Migration order (T1–T13 in spec) | Plan tasks T1–T12 (spec T11 verification folded into T8/T10; spec T13 = plan T12) |
| §8 Acceptance criteria | T12 (all 5 verifications) |

All sections covered. Spec listed 13 tasks; plan uses 12 because spec T11 (verify print → logger) is naturally satisfied when T8 / T10 / T11 are written from the spec — no separate verification task needed.

---

## Execution Notes

- **Branch strategy**: per CONVENTIONS.md §5.3, large refactors get a feature branch. Recommended: `git checkout -b feat/be-b-services-repos` from master before T1, merge `--no-ff` after T12 passes. (Same pattern as MIGR / BE-A.)
- **Total tasks**: 12 (T1 through T12). 11 commits (T7 may be a no-op).
- **Estimated time**: 5–15 minutes per task; total ~1–2 hours. T9 is the largest (17+ test sites) — budget ~20 minutes.
- **No new dependencies**.
- **Each task ends green** with the suite reporting `5 failed, 128 passed`.

## Future-phase Notes (do not implement here)

- **BE-C** will rename `app.py` → `main.py`, split it into `api/routes/*.py`, `api/schemas/*.py`, `api/dependencies.py`. It will also register a FastAPI exception handler for `StockDashboardError`. After BE-C lands and consumers migrate to direct service imports, the thin `alerts.py` re-export module can be deleted.
- **Phase 3 (REG-)** will refactor fetchers to conform to `Fetcher` Protocol; introduce alert indicator registry. May replace `print(...)` in fetchers (out of BE-B scope per C1).
- **Phase 4 (AUTH-)** adds `discord_ops_webhook_url` to `Settings`; `services/alert_notifier.py` may grow a second notification channel for ops alerts.
