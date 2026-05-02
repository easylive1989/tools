# Stock Dashboard BE-A: Core Infrastructure Design Spec

**Date**: 2026-05-02
**Phase**: BE-A (first sub-phase of Phase 2 — Backend Layered Refactor)
**Parent spec**: `docs/superpowers/specs/2026-05-02-stock-dashboard-conventions-design.md` §2.1, §4.2, §4.3, §4.4, §7 Phase 2
**Scope**: Add `backend/core/` package (`settings.py`, `logging.py`, `errors.py`) and route every existing `os.environ.get` callsite through `settings`. Initialise stdlib logging at app startup. Defines exception hierarchy for later phases to adopt.

## Goals

1. Centralise environment-variable reads in a single `pydantic-settings` model.
2. Provide a one-call logging setup that satisfies CONVENTIONS.md §4.2.
3. Define the exception hierarchy from CONVENTIONS.md §4.3 so BE-B / BE-C / Phase 4 can adopt it as they touch each layer.
4. Leave existing tests untouched (they continue to set `os.environ["DB_PATH"] = ":memory:"` before importing `db`).

## Non-Goals

- Do not replace `print(...)` with `logger.x(...)` calls. That cleanup happens in BE-B / BE-C / Phase 3 as each file is otherwise refactored.
- Do not change `raise RuntimeError` / `raise HTTPException` callers to use the new exception classes. The classes are defined here; adoption follows.
- Do not register a FastAPI exception handler for `StockDashboardError`. That belongs in BE-C once routes are split.
- Do not add `discord_ops_webhook_url` (Phase 4 AUTH).
- Do not move existing tests under `tests/{unit,integration,api}/` (out of scope; high-noise diff).

## Architecture

```
backend/
├── core/                       ← NEW (this spec)
│   ├── __init__.py             ← empty package marker
│   ├── settings.py             ← pydantic-settings singleton
│   ├── logging.py              ← setup_logging()
│   └── errors.py               ← exception hierarchy
├── app.py                      ← MODIFIED (startup hook calls setup_logging; CORS reads settings)
├── alerts.py                   ← MODIFIED (line 343 reads settings)
├── backfill.py                 ← MODIFIED (line 14 deleted)
├── db/__init__.py              ← MODIFIED (line 6 reads settings)
├── fetchers/
│   ├── chip_stock.py           ← MODIFIED (line 23)
│   ├── broker.py               ← MODIFIED (line 20)
│   ├── chip_total.py           ← MODIFIED (line 23)
│   └── fundamentals_stock.py   ← MODIFIED (line 28)
└── requirements.txt            ← MODIFIED (add pydantic-settings)
```

`tests/conftest.py` is **not** modified.

---

## 1. `backend/core/settings.py`

```python
"""Centralised configuration. Read once at import; no scattered os.environ.get."""
import os
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "..", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: str = os.path.join(
        os.path.dirname(__file__), "..", "stock_dashboard.db"
    )
    discord_stock_webhook_url: SecretStr | None = None
    finmind_token: SecretStr = SecretStr("")
    log_level: str = "INFO"
    cors_origins: list[str] = ["https://paul-learning.dev"]


settings = Settings()
```

Design notes:

- **Module-level singleton**: `settings = Settings()` runs at import time. Tests that set `os.environ["DB_PATH"] = ":memory:"` before any `from core.settings import settings` (or transitive `import db`) will see the override.
- **`SecretStr`** for `finmind_token` and `discord_stock_webhook_url`: prevents accidental leaks in `repr()` / structured logs. Callers use `.get_secret_value()` to access the raw string.
- **`extra="ignore"`**: tolerate other env vars (e.g. `VPS_HOST`, system-injected vars on the VPS) without failing validation.
- **`env_file` resolved relative to `core/settings.py`**: works from any cwd. Local dev: `backend/.env`. VPS: `/opt/stock-dashboard/backend/.env`.
- **Default `db_path` is the existing path**: matches the previous fallback in `db/__init__.py`.
- **Default `cors_origins`**: same as the previous hardcoded list in `app.py`.

## 2. `backend/core/logging.py`

```python
"""Logging setup. Call `setup_logging()` once at startup."""
import logging
from core.settings import settings


def setup_logging() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,  # override anything FastAPI / uvicorn already set
    )
    # Suppress noisy third-party loggers per CONVENTIONS.md §4.2.
    for noisy in ("urllib3", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
```

Design notes:

- **`force=True`**: uvicorn calls `logging.basicConfig` early; without `force` our config silently no-ops.
- **Triggered explicitly from `app.py` startup hook** (not as an import-time side-effect): testable and predictable.
- **Format string** matches CONVENTIONS.md §4.2 exactly.

## 3. `backend/core/errors.py`

```python
"""Exception hierarchy used across layers. See CONVENTIONS.md §4.3.

These classes are defined now but most adopters will arrive in BE-B / BE-C /
Phase 4 (AUTH-) as each layer is refactored.
"""


class StockDashboardError(Exception):
    """Base class for all in-app domain errors."""


class FetcherError(StockDashboardError):
    """Persistent failure fetching from an external data source."""


class FetcherParseError(FetcherError):
    """Response body did not match the expected shape."""


class RepositoryError(StockDashboardError):
    """SQL operation failed for an unrecoverable reason."""


class AlertEvaluationError(StockDashboardError):
    """Alert evaluator produced an unexpected result."""


class AuthError(StockDashboardError):
    """Authentication / authorisation failure (Phase 4 will adopt)."""
```

Design notes:

- **Pure definitions, no callers in BE-A**: spec §4.3's mapping (`RepositoryError → 500`, `FetcherError → 502`, `AuthError → 401`) requires a FastAPI exception handler, which lands in BE-C.
- Defining the hierarchy now (~15 lines) avoids forking it across multiple later phases.

## 4. Modified Callsites

### `backend/db/__init__.py:1-7`

```diff
 import sqlite3
-import os
 import threading
 from datetime import datetime, timedelta, timezone

-DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "stock_dashboard.db"))
+from core.settings import settings
+
+DB_PATH = settings.db_path
```

(`os` import removed because it's no longer used in this module.)

### `backend/backfill.py:13-14`

```diff
 import sqlite3, sys, os
-DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "stock_dashboard.db"))
```

`backfill.py` reads `DB_PATH` only to print it; the actual connection is via `db.get_connection()`. The local definition is dead.

### `backend/alerts.py:343`

```diff
-            webhook = os.environ.get("DISCORD_STOCK_WEBHOOK_URL")
+            webhook_secret = settings.discord_stock_webhook_url
+            webhook = webhook_secret.get_secret_value() if webhook_secret else None
```

(Add `from core.settings import settings` near the top.)

### `backend/fetchers/{chip_stock,broker,chip_total,fundamentals_stock}.py`

Each has the line `FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()` near the top. Replace with:

```python
from core.settings import settings
FINMIND_TOKEN = settings.finmind_token.get_secret_value().strip()
```

### `backend/app.py:46`

```diff
 app.add_middleware(
     CORSMiddleware,
-    allow_origins=["https://paul-learning.dev"],
+    allow_origins=settings.cors_origins,
     allow_methods=["GET", "POST", "DELETE", "PATCH"],
     allow_headers=["*"],
 )
```

(Add `from core.settings import settings` near the top.)

### `backend/app.py` startup hook

```diff
 @app.on_event("startup")
 def startup():
+    from core.logging import setup_logging
+    setup_logging()
     init_db()
     try:
         from scheduler import start_scheduler
         start_scheduler()
     except ImportError:
         print("[app] scheduler not available yet")
```

The `print` on the last line is intentionally retained; BE-C will replace it.

## 5. Tests

### New: `stock/dashboard/tests/test_settings.py`

(All existing tests live at `stock/dashboard/tests/test_*.py`. New tests follow the same convention.)

```python
"""BE-A: settings.py tests."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))


def test_settings_db_path_env_override(monkeypatch):
    """DB_PATH env var overrides the default."""
    monkeypatch.setenv("DB_PATH", ":memory:")
    # Re-import to pick up the env change.
    import importlib
    import core.settings as settings_mod
    importlib.reload(settings_mod)
    assert settings_mod.settings.db_path == ":memory:"


def test_settings_secret_finmind_token_not_in_repr(monkeypatch):
    """SecretStr must not leak the token in repr/str."""
    monkeypatch.setenv("FINMIND_TOKEN", "super-secret")
    import importlib
    import core.settings as settings_mod
    importlib.reload(settings_mod)
    s = settings_mod.settings
    assert "super-secret" not in repr(s)
    assert "super-secret" not in str(s)
    assert s.finmind_token.get_secret_value() == "super-secret"


def test_settings_cors_origins_default():
    """Default CORS allows the production frontend."""
    import core.settings as settings_mod
    assert "https://paul-learning.dev" in settings_mod.settings.cors_origins


def test_settings_log_level_default():
    """Default log level is INFO."""
    import core.settings as settings_mod
    assert settings_mod.settings.log_level == "INFO"
```

### New: `tests/test_logging.py`

```python
"""BE-A: logging setup tests."""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))


def test_setup_logging_sets_root_to_info():
    from core.logging import setup_logging
    setup_logging()
    assert logging.getLogger().level == logging.INFO


def test_setup_logging_suppresses_third_party(monkeypatch):
    from core.logging import setup_logging
    setup_logging()
    assert logging.getLogger("urllib3").level == logging.WARNING
    assert logging.getLogger("apscheduler").level == logging.WARNING


def test_setup_logging_respects_log_level_env(monkeypatch):
    """LOG_LEVEL=DEBUG raises the root logger to DEBUG."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    import importlib
    import core.settings as settings_mod
    importlib.reload(settings_mod)
    import core.logging as logging_mod
    importlib.reload(logging_mod)
    logging_mod.setup_logging()
    assert logging.getLogger().level == logging.DEBUG
```

### Existing tests

`tests/conftest.py`, `tests/test_db.py`, `tests/test_alerts.py`, `tests/test_fetchers.py`, etc. — **unchanged**. The autouse `reset_db` fixture continues to work because `os.environ["DB_PATH"] = ":memory:"` is set at module-import time before any `import db` triggers `core.settings` instantiation.

## 6. Migration Order (for the implementation plan)

1. Add `pydantic-settings` to `requirements.txt`. Install locally.
2. Create `backend/core/__init__.py` + `backend/core/settings.py`. Add `test_settings.py`. TDD: tests first, then file.
3. Create `backend/core/logging.py`. Add `test_logging.py`. TDD.
4. Create `backend/core/errors.py`. (No test — pure definitions.)
5. Replace `db/__init__.py` env read.
6. Delete dead `DB_PATH` line in `backfill.py`.
7. Replace `alerts.py` webhook env read.
8. Replace each `fetchers/*.py` token env read (4 files).
9. Replace `app.py` CORS origins; add `setup_logging()` call in startup hook.
10. Run full test suite: assert 5 baseline failures + all other tests pass + new tests pass.

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `pydantic-settings` not installed on VPS at deploy time | Deploy workflow already runs `pip install -q -r requirements.txt`; verify locally first; pin `>=2.0.0` |
| `SecretStr.get_secret_value()` forgotten by fetcher → token sent as `SecretStr(...)` repr to FinMind | Existing fetcher tests (`test_fetchers.py`) hit real fetcher functions and would catch a mangled token via assertion failures. Verify suite stays green. |
| Module-level `settings = Settings()` runs before tests have a chance to monkeypatch env | `tests/conftest.py` already sets env vars before imports. Test patterns using `monkeypatch.setenv` + `importlib.reload(core.settings)` handle the rest. |
| `setup_logging()` overrides uvicorn's access log formatting | `force=True` only resets root + named loggers. Uvicorn's named access loggers retain their own format. Verify by `journalctl -u stock-dashboard` after deploy. |
| Tests that previously read `db.DB_PATH` directly may rely on its precise resolution | Currently no test references `db.DB_PATH` directly (verified via `grep`). Module-level value is computed once from settings → identical to previous behaviour. |

## 8. Acceptance Criteria

- `grep -rn "os.environ\|os.getenv" stock/dashboard/backend/` returns **only the test conftest** (`tests/conftest.py:5`) and lines inside `core/settings.py` (none — pydantic-settings handles this).
- Full test suite: 5 baseline failures + all other tests pass + new `test_settings.py` and `test_logging.py` tests pass.
- `python3 -c "from core.settings import settings; print(settings.db_path)"` from `backend/` directory prints the expected default DB path.
- `requirements.txt` lists `pydantic-settings>=2.0.0`.
- Deploy to VPS succeeds; service starts; existing endpoints still respond.
- No `pydantic-settings` validation error in `journalctl -u stock-dashboard` post-deploy.

## 9. After This Phase

Next sub-phases (each its own brainstorm → spec → plan → implementation cycle):

- **BE-B**: Split `db/__init__.py` into `repositories/`. Split `alerts.py` into `services/{alert_engine, alert_notifier}.py`. Move `backfill.py` to `services/backfill.py`. Replace `print(...)` calls inside touched files with `logger.x(...)`. Adopt `FetcherError` / `RepositoryError` as appropriate.
- **BE-C**: Split `app.py` into `api/routes/*.py` + `api/schemas/*.py` + `api/dependencies.py` (without auth — that's Phase 4). Rename `app.py` → `main.py`. Register the FastAPI exception handler that maps `StockDashboardError` → HTTP responses.
