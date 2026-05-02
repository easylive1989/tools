# Stock Dashboard BE-B: Repositories + Services Design Spec

**Date**: 2026-05-02
**Phase**: BE-B (second sub-phase of Phase 2 — Backend Layered Refactor)
**Parent spec**: `docs/superpowers/specs/2026-05-02-stock-dashboard-conventions-design.md` §2.1, §7 Phase 2
**Predecessor**: BE-A (`docs/superpowers/specs/2026-05-02-stock-dashboard-be-a-design.md`) — added `core/` package
**Scope**:
- Split `db/__init__.py` (35 functions) into 5 `repositories/*.py` files + a thin `db/connection.py`
- Split `alerts.py` (412 lines) into `services/alert_engine.py` + `services/alert_notifier.py`
- Move `backfill.py` body into `services/backfill.py`; keep `backend/backfill.py` as thin CLI wrapper
- Replace `print(...)` with `logger.x(...)` inside the touched files (alerts + backfill)
- Update `tests/test_alerts.py` (~13 sites) to use `monkeypatch.setattr(alerts_module.settings, ...)` so the alerts notifier can read `settings.discord_stock_webhook_url` (resolves the BE-A T7 deferral)

## Goals

1. Establish the layered separation defined in CONVENTIONS.md §2.1: routes → services → repositories → db.
2. Make `alerts.py` two clear units: pure evaluation logic (engine) and Discord delivery (notifier).
3. Resolve the BE-A T7 webhook regression by moving notifier to settings + updating the test pattern.
4. Replace ad-hoc `print()` with structured logging inside the files we already touch.
5. Keep every existing call site working through re-exports — `from db import save_indicator`, `import alerts as alerts_module`, `python backfill.py` all continue to function.

## Non-Goals

- Do not touch `fetchers/*` (Phase 3 REG- territory).
- Do not touch `app.py` (BE-C territory).
- Do not adopt `RepositoryError` / `FetcherError` as new `raise` sites. The classes from `core/errors.py` stay defined-but-unused in BE-B; BE-C / Phase 3 adopt them.
- Do not migrate existing `tests/test_*.py` files into `tests/{unit,integration,api}/` subdirectories. Only new tests (if any) get placed in subdirs (per D3 decision).
- Do not change `scheduler.py`, `tests/conftest.py`, `core/*`, `db/runner.py`, `db/migrations/*`.
- Do not rewrite `remove_watched_ticker`'s cross-table side effect (it disables `stock_indicator` alerts for the removed ticker). The SQL moves into `repositories/stocks.py` verbatim; revisiting the design happens later.

---

## 1. Target File Structure

```
backend/
├── main.py / app.py            ← unchanged in BE-B (BE-C will rename)
├── scheduler.py                ← unchanged (imports `from db import ...` still resolve via re-exports)
├── core/                       ← unchanged (built in BE-A)
│   ├── __init__.py
│   ├── settings.py
│   ├── logging.py
│   └── errors.py
├── db/
│   ├── __init__.py             ← thinned: connection re-export + init_db + purge_old_data + repo re-exports
│   ├── connection.py           ← NEW: get_connection, DB_PATH, _memory_conn, _memory_lock
│   ├── runner.py               ← unchanged
│   └── migrations/
│       └── 0001_initial.sql
├── repositories/               ← NEW
│   ├── __init__.py             ← empty package marker
│   ├── indicators.py           ← 3 functions
│   ├── stocks.py               ← 5 functions
│   ├── alerts.py               ← 6 functions
│   ├── chip.py                 ← 6 functions
│   └── fundamentals.py         ← 12 functions
├── services/                   ← NEW
│   ├── __init__.py             ← empty package marker
│   ├── alert_engine.py         ← evaluation logic + helpers
│   ├── alert_notifier.py       ← Discord delivery, reads settings
│   └── backfill.py             ← migrated from backend/backfill.py
├── backfill.py                 ← thin wrapper: `from services.backfill import main; main()`
├── alerts.py                   ← thin re-export module (engine, notifier, send_to_discord, settings)
└── fetchers/                   ← unchanged

tests/
├── conftest.py                 ← unchanged
├── test_db.py                  ← unchanged
├── test_alerts.py              ← MODIFIED: ~13 monkeypatch sites updated
├── test_brokers.py / test_chip.py / test_api.py / ... ← unchanged
├── test_settings.py / test_logging.py
└── unit/                       ← NEW (only if BE-B adds new tests; otherwise empty/not created)
```

---

## 2. Repository Mapping (db/__init__.py → repositories/*)

### `repositories/indicators.py` (3)

`save_indicator`, `get_latest_indicator`, `get_indicator_history`

Imports `from db.connection import get_connection`.

### `repositories/stocks.py` (5)

`save_stock_snapshot`, `get_latest_stock`, `get_watched_tickers`, `add_watched_ticker`, `remove_watched_ticker`.

`remove_watched_ticker` keeps its cross-table side effect (disables `stock_indicator` alerts for the removed ticker). This is a known smell to revisit later — out of scope for BE-B.

### `repositories/alerts.py` (6)

`list_alerts`, `add_alert`, `delete_alert`, `set_alert_enabled`, `get_active_alerts`, `mark_alert_triggered`.

### `repositories/chip.py` (6)

Broker (3) + chip (3) merged in one file (same chip domain):
- `save_broker_daily_rows`, `get_broker_daily_range`, `get_latest_broker_date`
- `save_chip_daily_rows`, `get_chip_daily_range`, `get_latest_chip_date`

### `repositories/fundamentals.py` (12)

PER (3) + Revenue (3) + Financial (3) + Dividend (3):
- `save_per_daily_rows`, `get_per_daily_range`, `get_latest_per_date`
- `save_revenue_monthly_rows`, `get_revenue_monthly_range`, `get_latest_revenue_ym`
- `save_financial_quarterly_rows`, `get_financial_quarterly_range`, `get_latest_financial_date`
- `save_dividend_history_rows`, `get_dividend_history`, `get_latest_dividend_announce_date`

The inline `import re` + `_key()` sort helper inside `get_dividend_history` stay private to that file.

### Stays in `db/__init__.py`

- `import` block (sqlite3, threading, datetime, etc.)
- `init_db()` — runner shim, unchanged
- `purge_old_data()` — cross-table maintenance, kept here per A1 decision
- Re-export block at the bottom: `from repositories.indicators import *` (explicit list, not `*`)
- Re-export of connection symbols: `from db.connection import get_connection, DB_PATH, _memory_conn, _memory_lock`

### `db/connection.py` (NEW)

```python
"""Connection factory + in-memory singleton for tests.

Keep this small and dependency-free so repositories can import it without
triggering circular imports through db/__init__.py's re-exports.
"""
import os
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

### Final `db/__init__.py` shape

```python
"""Database package.

Public API kept stable via re-exports so call sites like
`from db import save_indicator` continue to work after the BE-B split.
"""
import os

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
    from datetime import datetime, timedelta, timezone
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
            (int(cutoff_date[:4]), int(cutoff_date[5:7])),
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

`from datetime import` lives inside `purge_old_data` rather than module top to keep the imports list short. Alternative: move it to module top — either is acceptable.

---

## 3. Services

### `services/alert_engine.py`

Body of the current `alerts.py` minus the Discord delivery call:

- All `_helper` functions (`_check_streak`, `_get_stock_indicator_history`, `_pct_rank`, `_get_stock_revenue_yoy`, `_get_stock_quarterly_yoy`, `_get_stock_yearly_yoy`, `_format_value`, `_latest_indicator_history`, `_alert_display_name`, `_build_payload`)
- `INDICATOR_LABELS` and `INDICATOR_UNITS` constants
- `check_alerts(...)` function

`check_alerts` replaces the inline `os.environ.get(DISCORD_STOCK_WEBHOOK_URL)` + `send_to_discord(...)` + `print(...)` block with a single `notify_triggered(payload, alert_id=alert["id"])` call.

Imports come from `repositories.*` (not `db.*`) — direct paths, not re-exports.

`logger = logging.getLogger(__name__)` at module top.

### `services/alert_notifier.py`

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

### `alerts.py` (thin re-export)

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

`send_to_discord` is re-exported because some tests do
`monkeypatch.setattr(alerts_module, "send_to_discord", lambda url, payload: ...)`. To make that monkeypatch effective, the `alert_notifier.notify_triggered` body must reference the name through the *module* (so the patched attribute on `alerts_module` is visible). See risk §6.

`settings` is re-exported so tests can do `monkeypatch.setattr(alerts_module.settings, "discord_stock_webhook_url", SecretStr("..."))`.

### `services/backfill.py` + `backend/backfill.py` thin wrapper

`services/backfill.py`: full body of the current `backend/backfill.py`, with two changes:
1. All `print(...)` calls become `logger.info(...)` / `logger.warning(...)` / `logger.error(...)` based on context (see §4).
2. The `if __name__ == "__main__":` block moves into a `def main():` function so the wrapper can call it.

`backend/backfill.py` (~6 lines):

```python
"""CLI entry point. Delegates to services.backfill.

Run from backend/ as: python backfill.py
"""
from services.backfill import main

if __name__ == "__main__":
    main()
```

Existing invocation `python backfill.py` from `backend/` directory continues to work.

---

## 4. `print()` → Logger Mapping

### `services/alert_notifier.py` (3 sites moved from `alerts.py`)

| Old `print` | New |
|---|---|
| `print(f"[alerts] webhook not set, skipping notification for alert {alert['id']}")` | `logger.info("alert_notify_skipped alert_id=%s reason=no_webhook", alert_id)` |
| `print(f"[alerts] notified: {name} {cond} {threshold} (value={triggered_value})")` | `logger.info("alert_notified alert_id=%s", alert_id)` (caller-rich context lives in payload) |
| `print(f"[alerts] discord error for alert {alert['id']}: {e}")` | `logger.warning("alert_notify_failed alert_id=%s error=%s", alert_id, e)` |

### `services/backfill.py` (~15 sites)

Pattern:
- Start/done messages → `logger.info`
- "no data" / "cannot find token" → `logger.warning`
- Caught exceptions inside backfill loop → `logger.error`

Examples:

| Old | New |
|---|---|
| `print(f"[backfill] {indicator} from yfinance {ticker_symbol} …")` | `logger.info("backfill_yfinance_start indicator=%s ticker=%s", indicator, ticker_symbol)` |
| `print(f"  No data")` | `logger.warning("backfill_no_data indicator=%s", indicator)` |
| `print(f"  Inserted {inserted} rows for {indicator}")` | `logger.info("backfill_inserted indicator=%s rows=%d", indicator, inserted)` |
| `print("  Cannot find CSRF token")` | `logger.warning("backfill_ndc_csrf_not_found")` |
| `print("[backfill] Done.")` | `logger.info("backfill_done")` |

The exact mapping for each `print` is locked into the implementation plan; the spec defines the categorisation rule (info / warning / error).

---

## 5. Test Pattern Updates (`tests/test_alerts.py`)

### Old patterns

```python
# Pattern A: monkeypatch.setenv (3 sites)
monkeypatch.setenv("DISCORD_STOCK_WEBHOOK_URL", "http://example.invalid/hook")

# Pattern B: patch.dict("os.environ", ...) (10+ sites)
with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
    ...

# Pattern C: monkeypatch.delenv (1 site)
monkeypatch.delenv("DISCORD_STOCK_WEBHOOK_URL", raising=False)
```

### New patterns

```python
from pydantic import SecretStr

# Pattern A → setattr on alerts_module.settings
monkeypatch.setattr(alerts_module.settings, "discord_stock_webhook_url",
                    SecretStr("http://example.invalid/hook"))

# Pattern B → unittest.mock.patch.object on settings instance
from unittest.mock import patch
with patch.object(alerts_module.settings, "discord_stock_webhook_url",
                   SecretStr("https://example/x")):
    ...

# Pattern C → setattr to None (mirrors "no webhook")
monkeypatch.setattr(alerts_module.settings, "discord_stock_webhook_url", None)
```

### Additional test fix: monkeypatch target for `send_to_discord`

Currently:
```python
monkeypatch.setattr(alerts_module, "send_to_discord", lambda url, payload: sent.append(payload))
```

After refactor, the actual `send_to_discord` reference used at runtime lives in `services.alert_notifier`. For the patch to take effect on the running notifier, tests should do **both** (defensive):

```python
import services.alert_notifier as alert_notifier
monkeypatch.setattr(alert_notifier, "send_to_discord", lambda url, payload: sent.append(payload))
```

(The existing `monkeypatch.setattr(alerts_module, "send_to_discord", ...)` line can stay as a no-op for backward compat, or be removed — implementation plan picks one.)

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Re-export chain creates circular imports | Strict one-way order: `db/connection.py` → `core/*` only; `repositories/*` → `db.connection` only; `services/*` → `repositories.*` and `core.*` only; `db/__init__.py` re-exports happen at the **bottom** (after `init_db` / `purge_old_data` so they don't depend on imports being set up). |
| `tests/conftest.py` autouse `db.init_db()` breaks | `init_db` stays in `db/__init__.py` (just re-exports new internals). conftest unchanged. |
| `monkeypatch.setattr(alerts_module, "send_to_discord", ...)` no longer intercepts because the runtime call site is `services.alert_notifier.send_to_discord` | Test plan switches monkeypatch target to `alert_notifier` module. ~3 sites in `test_alerts.py`. |
| Tests assert log content like `"[alerts] webhook not set..."` (capsys / caplog) | Audit `test_alerts.py` for capsys/caplog assertions on the literal `[alerts]` strings; update or remove those assertions during T9. (Best effort confirmation: most existing tests assert via `sent == []`, not stdout.) |
| `services/backfill.py` is no longer at `backend/backfill.py` so `python backfill.py` from a fresh checkout fails | Thin wrapper at `backend/backfill.py` preserves the entry point. README / deploy docs don't reference the path explicitly, so no doc updates required. |
| `purge_old_data` stays in `db/__init__.py` but uses `get_connection` — works because `db/__init__.py` re-imports it from `db.connection` at the top | Verified by ordering: connection re-import on line 1 of body, `purge_old_data` defined after. |
| `services/alert_engine.py` imports `repositories.alerts` — name collision risk with the public `alerts.py` thin re-export | None at runtime: `import alerts` resolves to `backend/alerts.py`, while `import repositories.alerts` is a different name. But code reading might confuse a maintainer — the spec calls this out so the implementer adds a brief comment in `alert_engine.py`. |
| `alerts_module.settings` reference works only if `alerts.py` re-exports `settings` from `core.settings` — and tests need to monkeypatch the **same instance** that `alert_notifier` reads | Both modules import from `core.settings.settings` (the same module-level singleton instance). `alerts_module.settings is core.settings.settings` is True, so monkeypatch on either reaches the same object. Tests target `alerts_module.settings` for ergonomic shortness. |

---

## 7. Migration Order

13 tasks (BE-B-T1 through BE-B-T13), each ending in a green test suite and a single commit. All commits use `(BE-B-Tn)` step IDs per CONVENTIONS.md §5.1.

| # | Task |
|---|---|
| T1 | Create `db/connection.py`; `db/__init__.py` re-imports symbols |
| T2 | `repositories/__init__.py` + `repositories/indicators.py` (3) + re-export |
| T3 | `repositories/stocks.py` (5) + re-export |
| T4 | `repositories/alerts.py` (6) + re-export |
| T5 | `repositories/chip.py` (6) + re-export |
| T6 | `repositories/fundamentals.py` (12) + re-export |
| T7 | Remove the now-orphaned SQL function bodies from `db/__init__.py` (only re-exports + init_db + purge_old_data + import block remain) |
| T8 | Create `services/__init__.py` + `services/alert_notifier.py` (settings + logger) |
| T9 | Update `tests/test_alerts.py`: ~13 webhook monkeypatch sites + ~3 send_to_discord sites; convert `alerts.py` to thin re-export module |
| T10 | Create `services/alert_engine.py` from old `alerts.py` body; reduce `alerts.py` to its final thin re-export form |
| T11 | Replace `print` with `logger` inside `services/alert_engine.py` (none) and `services/alert_notifier.py` (3 — already done in T8 if implemented from spec) — this task is verification-only if T8 wrote the loggers correctly |
| T12 | Create `services/backfill.py` (move + print → logger); reduce `backend/backfill.py` to thin wrapper |
| T13 | Final verification: `grep -rn "^from db import" backend/`, full suite, branch log inspection |

T11 may collapse into a no-op once T8 / T10 are written from this spec. The implementation plan can either keep T11 as an explicit verification-only task or delete it.

---

## 8. Acceptance Criteria

- `repositories/` contains exactly 5 files (`indicators.py`, `stocks.py`, `alerts.py`, `chip.py`, `fundamentals.py`) totalling 32 functions (3 + 5 + 6 + 6 + 12).
- `services/` contains exactly 3 files (`alert_engine.py`, `alert_notifier.py`, `backfill.py`).
- `db/connection.py` exists and is < 30 lines.
- `db/__init__.py` is < 100 lines (down from ~430), containing only: imports, `init_db()`, `purge_old_data()`, repository re-export block.
- `backend/backfill.py` is ≤ 10 lines (thin wrapper).
- `backend/alerts.py` is ≤ 15 lines (thin re-export).
- All existing `from db import X` call sites still work (sample: `app.py`, `scheduler.py`, every test file).
- `import alerts as alerts_module` continues to work; `alerts_module.check_alerts`, `alerts_module.send_to_discord`, `alerts_module.settings` all accessible.
- `python backfill.py` (run from `backend/`) starts and prints log lines (now via stdlib logging).
- Full test suite: 5 baseline failures (unchanged) + every other test passes. Total pass count ≥ 128 (BE-A baseline) — test refactor doesn't add or remove tests.
- `grep -rn "^[[:space:]]*print(" backend/services/` returns zero matches (logger fully adopted in services).
- `journalctl -u stock-dashboard -n 50` post-deploy shows correctly formatted log lines from `services.alert_notifier` and `services.backfill` namespaces.

---

## 9. After This Phase

- **BE-C** (next sub-phase): split `app.py` into `api/routes/*.py` + `api/schemas/*.py` + `api/dependencies.py`; rename `app.py` → `main.py`; register a FastAPI exception handler for `StockDashboardError`. The thin `alerts.py` re-export becomes unnecessary if BE-C consumers migrate to direct `services.alert_engine` imports — at that point we can consider deleting it.
- **Phase 3 (REG-)**: refactor fetchers to conform to `Fetcher` Protocol; introduce alert indicator registry. May replace `print(...)` in fetchers (out of BE-B scope per C1).
- **Phase 4 (AUTH-)**: add `discord_ops_webhook_url` to `Settings`. Touches `core/settings.py` only; `services/alert_notifier.py` may grow a second notification channel for ops alerts.
