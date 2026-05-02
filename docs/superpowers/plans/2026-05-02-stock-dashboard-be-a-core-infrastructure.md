# Stock Dashboard BE-A: Core Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `backend/core/` package (`settings.py`, `logging.py`, `errors.py`) and route every existing `os.environ.get` callsite through `settings`. Initialise stdlib logging at app startup. Define exception hierarchy (no callers in this phase).

**Architecture:** Centralised `pydantic-settings` singleton replaces scattered env reads. Stdlib `logging` configured once at startup with third-party noise suppression. Exception classes defined now, adopted in BE-B / BE-C / Phase 4.

**Tech Stack:** Python 3.12, pydantic 2.x, pydantic-settings 2.x, stdlib logging, pytest.

**Spec reference:** `docs/superpowers/specs/2026-05-02-stock-dashboard-be-a-design.md`.

---

## File Structure

**Created:**
- `stock/dashboard/backend/core/__init__.py` — empty package marker
- `stock/dashboard/backend/core/settings.py` — pydantic-settings singleton
- `stock/dashboard/backend/core/logging.py` — `setup_logging()` function
- `stock/dashboard/backend/core/errors.py` — exception hierarchy (no callers in BE-A)
- `stock/dashboard/tests/test_settings.py` — settings tests
- `stock/dashboard/tests/test_logging.py` — logging tests

**Modified:**
- `stock/dashboard/backend/requirements.txt` — add `pydantic-settings>=2.0.0`
- `stock/dashboard/backend/db/__init__.py` — line 6, remove `os` import
- `stock/dashboard/backend/backfill.py` — delete dead `DB_PATH` line
- `stock/dashboard/backend/alerts.py` — line 343, add settings import
- `stock/dashboard/backend/fetchers/chip_stock.py` — line 23, add settings import
- `stock/dashboard/backend/fetchers/broker.py` — line 20, add settings import
- `stock/dashboard/backend/fetchers/chip_total.py` — line 23, add settings import
- `stock/dashboard/backend/fetchers/fundamentals_stock.py` — line 28, add settings import
- `stock/dashboard/backend/app.py` — line 46 CORS, add `setup_logging()` to startup hook

**Unchanged (verified non-impact):**
- `stock/dashboard/tests/conftest.py` — autouse fixture continues to work because `os.environ["DB_PATH"] = ":memory:"` is set before `import db` triggers `core.settings` instantiation.

---

## Baseline

Before starting, verify the test suite reports `5 failed, 121 passed` with these specific failures (pre-existing, unrelated to this work — DO NOT FIX):

- `tests/test_brokers.py::test_brokers_endpoint_rejects_non_taiwan_ticker`
- `tests/test_brokers.py::test_brokers_endpoint_rejects_invalid_params`
- `tests/test_brokers.py::test_brokers_endpoint_returns_top5_by_net_buy`
- `tests/test_fetchers.py::test_fetch_ndc_saves_indicator`
- `tests/test_fetchers.py::test_fetch_fear_greed_saves_indicator`

After this phase, expected: `5 failed, 128 passed` (7 new tests added: 4 in `test_settings.py`, 3 in `test_logging.py`).

All commits use the `(BE-A-Tn)` step-id format per CONVENTIONS.md §5.1.

---

## Task Breakdown

### Task 1 (BE-A-T1): Add `pydantic-settings` dependency

**Files:**
- Modify: `stock/dashboard/backend/requirements.txt`

- [ ] **Step 1: Verify the baseline test suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 121 passed, 3 warnings` with the 5 baseline failures named in the section above. If different, stop and investigate.

- [ ] **Step 2: Add the dependency line**

Append a single line to `stock/dashboard/backend/requirements.txt`:

```
pydantic-settings>=2.0.0
```

The file should now end with that line as the last entry.

- [ ] **Step 3: Install locally**

```bash
python3 -m pip install -q 'pydantic-settings>=2.0.0'
python3 -c "import pydantic_settings; print(pydantic_settings.__version__)"
```

Expected: prints a version string starting with `2.`.

- [ ] **Step 4: Re-run the test suite to confirm nothing changed**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: same `5 failed, 121 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/requirements.txt && git commit -m "$(cat <<'EOF'
chore(stock-dashboard): add pydantic-settings dependency (BE-A-T1)

Required by core/settings.py introduced in BE-A.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2 (BE-A-T2): `core/__init__.py` + `core/settings.py` with TDD

**Files:**
- Create: `stock/dashboard/backend/core/__init__.py`
- Create: `stock/dashboard/backend/core/settings.py`
- Create: `stock/dashboard/tests/test_settings.py`

- [ ] **Step 1: Create the empty package marker first**

```bash
mkdir -p /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/core
touch /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/core/__init__.py
```

(Empty file. The package needs to be importable before tests can reference it.)

- [ ] **Step 2: Write the failing tests**

Create `stock/dashboard/tests/test_settings.py` with this exact content:

```python
"""BE-A: settings.py tests."""
import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))


def test_settings_db_path_env_override(monkeypatch):
    """DB_PATH env var overrides the default."""
    monkeypatch.setenv("DB_PATH", ":memory:")
    import core.settings as settings_mod
    importlib.reload(settings_mod)
    assert settings_mod.settings.db_path == ":memory:"


def test_settings_secret_finmind_token_not_in_repr(monkeypatch):
    """SecretStr must not leak the token in repr/str."""
    monkeypatch.setenv("FINMIND_TOKEN", "super-secret")
    import core.settings as settings_mod
    importlib.reload(settings_mod)
    s = settings_mod.settings
    assert "super-secret" not in repr(s)
    assert "super-secret" not in str(s)
    assert s.finmind_token.get_secret_value() == "super-secret"


def test_settings_cors_origins_default():
    """Default CORS allows the production frontend."""
    import core.settings as settings_mod
    importlib.reload(settings_mod)
    assert "https://paul-learning.dev" in settings_mod.settings.cors_origins


def test_settings_log_level_default():
    """Default log level is INFO."""
    import core.settings as settings_mod
    importlib.reload(settings_mod)
    assert settings_mod.settings.log_level == "INFO"
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/test_settings.py -v 2>&1 | tail -15
```

Expected: FAIL with collection error `ModuleNotFoundError: No module named 'core.settings'` (or similar). The module file doesn't exist yet.

- [ ] **Step 4: Write `core/settings.py`**

Create `stock/dashboard/backend/core/settings.py` with this exact content:

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

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/test_settings.py -v 2>&1 | tail -15
```

Expected: 4 tests PASS.

- [ ] **Step 6: Run the full suite to confirm no regression**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 125 passed` (4 new passes from `test_settings.py`).

- [ ] **Step 7: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/core/__init__.py stock/dashboard/backend/core/settings.py stock/dashboard/tests/test_settings.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add core/settings.py with pydantic-settings (BE-A-T2)

Module-level singleton reading env vars once. SecretStr wraps tokens
to prevent accidental leaks in repr / structured logs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3 (BE-A-T3): `core/logging.py` with TDD

**Files:**
- Create: `stock/dashboard/backend/core/logging.py`
- Create: `stock/dashboard/tests/test_logging.py`

- [ ] **Step 1: Write the failing tests**

Create `stock/dashboard/tests/test_logging.py` with this exact content:

```python
"""BE-A: logging setup tests."""
import importlib
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))


def test_setup_logging_sets_root_to_info():
    from core.logging import setup_logging
    setup_logging()
    assert logging.getLogger().level == logging.INFO


def test_setup_logging_suppresses_third_party():
    from core.logging import setup_logging
    setup_logging()
    assert logging.getLogger("urllib3").level == logging.WARNING
    assert logging.getLogger("apscheduler").level == logging.WARNING


def test_setup_logging_respects_log_level_env(monkeypatch):
    """LOG_LEVEL=DEBUG raises the root logger to DEBUG."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    import core.settings as settings_mod
    importlib.reload(settings_mod)
    import core.logging as logging_mod
    importlib.reload(logging_mod)
    logging_mod.setup_logging()
    assert logging.getLogger().level == logging.DEBUG
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/test_logging.py -v 2>&1 | tail -15
```

Expected: FAIL with collection error `ModuleNotFoundError: No module named 'core.logging'` (the module doesn't exist yet).

- [ ] **Step 3: Write `core/logging.py`**

Create `stock/dashboard/backend/core/logging.py` with this exact content:

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

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/test_logging.py -v 2>&1 | tail -15
```

Expected: 3 tests PASS.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed` (3 new passes from `test_logging.py`).

- [ ] **Step 6: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/core/logging.py stock/dashboard/tests/test_logging.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add core/logging.py with setup_logging() (BE-A-T3)

stdlib logging configured once at startup. force=True overrides
uvicorn's early basicConfig. urllib3 and apscheduler clamped to
WARNING per CONVENTIONS.md §4.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4 (BE-A-T4): `core/errors.py`

Pure type definitions. No tests (no behaviour to verify).

**Files:**
- Create: `stock/dashboard/backend/core/errors.py`

- [ ] **Step 1: Create the file**

Create `stock/dashboard/backend/core/errors.py` with this exact content:

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

- [ ] **Step 2: Verify importability**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from core.errors import (
    StockDashboardError, FetcherError, FetcherParseError,
    RepositoryError, AlertEvaluationError, AuthError,
)
assert issubclass(FetcherError, StockDashboardError)
assert issubclass(FetcherParseError, FetcherError)
assert issubclass(RepositoryError, StockDashboardError)
print('ok')
"
```

Expected: prints `ok`.

- [ ] **Step 3: Run the full suite to confirm no regression**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: same `5 failed, 128 passed` (no new tests).

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/core/errors.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add core/errors.py exception hierarchy (BE-A-T4)

Pure type definitions. No callers in BE-A. BE-B / BE-C / Phase 4
adopt as each layer is refactored.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5 (BE-A-T5): Replace env read in `db/__init__.py`

**Files:**
- Modify: `stock/dashboard/backend/db/__init__.py:1-7`

- [ ] **Step 1: Apply the change**

Edit `stock/dashboard/backend/db/__init__.py`. The current first 7 lines are:

```python
import sqlite3
import os
import threading
from datetime import datetime, timedelta, timezone

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "stock_dashboard.db"))
_memory_conn = None
```

Replace with:

```python
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from core.settings import settings

DB_PATH = settings.db_path
_memory_conn = None
```

(Removed `import os` — no longer used. Other `os.path.join` calls in this file? Confirm with `grep -n "os\." stock/dashboard/backend/db/__init__.py` after editing — should return zero matches. If any remain, restore the `import os` line.)

- [ ] **Step 2: Verify the os import is fully removable**

```bash
grep -n "os\." /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/db/__init__.py
```

Expected: zero matches. If any line uses `os.path...` etc., the `import os` line was needed — keep it.

- [ ] **Step 3: Run the full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed` — no change from the previous task. The autouse fixture in `conftest.py` still sets `os.environ["DB_PATH"] = ":memory:"` before `import db`, so `settings.db_path` resolves to `:memory:` for tests.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/db/__init__.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): db/__init__.py reads DB_PATH from settings (BE-A-T5)

Replaces direct os.environ.get with settings.db_path. Tests unchanged
(conftest.py still sets DB_PATH env var before import).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6 (BE-A-T6): Delete dead `DB_PATH` in `backfill.py`

**Files:**
- Modify: `stock/dashboard/backend/backfill.py:13-14`

- [ ] **Step 1: Confirm `DB_PATH` is dead**

```bash
grep -n "DB_PATH" /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/backfill.py
```

Expected: only a single match at line 14 (the definition). If there are other references, this task's premise is wrong — stop and report.

- [ ] **Step 2: Apply the change**

Edit `stock/dashboard/backend/backfill.py`. The current lines 13-14 are:

```python
import sqlite3, sys, os
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "stock_dashboard.db"))
```

Replace with (delete the second line and trim `os` from the imports if otherwise unused):

```python
import sqlite3, sys
```

Verify whether `os` is still needed elsewhere in `backfill.py`:

```bash
grep -n "os\." /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/backfill.py
```

If zero matches, removing `os` from the imports is safe (as shown above). If any matches remain, keep `import os`:

```python
import sqlite3, sys, os
```

- [ ] **Step 3: Smoke-import**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "import backfill; print('ok')"
```

Expected: prints `ok`. (No import errors, no NameError.)

- [ ] **Step 4: Run the full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/backfill.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): remove dead DB_PATH from backfill.py (BE-A-T6)

backfill.py never used the local DB_PATH constant — connections go
through db.get_connection(). Removing avoids confusion with settings.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7 (BE-A-T7): Replace webhook env read in `alerts.py`

**Files:**
- Modify: `stock/dashboard/backend/alerts.py` (top imports + line 343)

- [ ] **Step 1: Add the settings import**

Find the import block near the top of `stock/dashboard/backend/alerts.py`. After the existing `from common.notify import send_to_discord` line, add:

```python
from core.settings import settings
```

- [ ] **Step 2: Replace the env read at line 343**

Find the line:

```python
            webhook = os.environ.get("DISCORD_STOCK_WEBHOOK_URL")
```

(One leading tab/spaces of indentation — preserve them.)

Replace with these two lines (same indentation):

```python
            webhook_secret = settings.discord_stock_webhook_url
            webhook = webhook_secret.get_secret_value() if webhook_secret else None
```

- [ ] **Step 3: Verify `os` is still imported (alerts.py uses `os.path` for sys.path bootstrap)**

```bash
grep -n "^import os\|os\." /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/alerts.py | head -10
```

Expected: `import os` remains, and other `os.path` / `os.environ` usages — leave them. Only the one `os.environ.get("DISCORD_STOCK_WEBHOOK_URL")` is replaced.

- [ ] **Step 4: Run the full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`. The `test_alerts.py` tests don't actually fire Discord notifications (they test pure logic / DB rows); the webhook path is exercised by integration only. If any new failure appears, suspect a missed `.get_secret_value()` call.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/alerts.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): alerts.py reads webhook from settings (BE-A-T7)

DISCORD_STOCK_WEBHOOK_URL now comes from settings as SecretStr;
.get_secret_value() unwraps for the HTTP call.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8 (BE-A-T8): Replace token env read in `fetchers/chip_stock.py`

**Files:**
- Modify: `stock/dashboard/backend/fetchers/chip_stock.py` (top imports + line 23)

- [ ] **Step 1: Add the settings import**

Open `stock/dashboard/backend/fetchers/chip_stock.py`. Look at lines 1–22 to understand the current top-of-file. After the existing imports, add (before the `FINMIND_TOKEN = ...` line):

```python
from core.settings import settings
```

- [ ] **Step 2: Replace the env read at line 23**

Find the line:

```python
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()
```

Replace with:

```python
FINMIND_TOKEN = settings.finmind_token.get_secret_value().strip()
```

- [ ] **Step 3: Confirm `os` is still needed (or removable)**

```bash
grep -n "os\." /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/fetchers/chip_stock.py
```

If zero matches, remove `import os` from the imports. Otherwise leave it.

- [ ] **Step 4: Smoke-import**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "import fetchers.chip_stock; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

- [ ] **Step 6: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/fetchers/chip_stock.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): chip_stock fetcher reads FINMIND_TOKEN from settings (BE-A-T8a)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9 (BE-A-T8b): Replace token env read in `fetchers/broker.py`

**Files:**
- Modify: `stock/dashboard/backend/fetchers/broker.py` (top imports + line 20)

- [ ] **Step 1: Apply the same pattern**

Open `stock/dashboard/backend/fetchers/broker.py`. Add after existing imports (before `FINMIND_TOKEN`):

```python
from core.settings import settings
```

Find:

```python
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()
```

Replace with:

```python
FINMIND_TOKEN = settings.finmind_token.get_secret_value().strip()
```

- [ ] **Step 2: Confirm `os` is still needed**

```bash
grep -n "os\." /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/fetchers/broker.py
```

If zero matches, remove `import os`. Otherwise keep.

- [ ] **Step 3: Smoke-import + full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "import fetchers.broker; print('ok')"
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `ok` and `5 failed, 128 passed`.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/fetchers/broker.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): broker fetcher reads FINMIND_TOKEN from settings (BE-A-T8b)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10 (BE-A-T8c): Replace token env read in `fetchers/chip_total.py`

**Files:**
- Modify: `stock/dashboard/backend/fetchers/chip_total.py` (top imports + line 23)

- [ ] **Step 1: Apply the same pattern**

Open `stock/dashboard/backend/fetchers/chip_total.py`. Add after existing imports (before `FINMIND_TOKEN`):

```python
from core.settings import settings
```

Find:

```python
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()
```

Replace with:

```python
FINMIND_TOKEN = settings.finmind_token.get_secret_value().strip()
```

- [ ] **Step 2: Confirm `os` is still needed**

```bash
grep -n "os\." /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/fetchers/chip_total.py
```

If zero matches, remove `import os`. Otherwise keep.

- [ ] **Step 3: Smoke-import + full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "import fetchers.chip_total; print('ok')"
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `ok` and `5 failed, 128 passed`.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/fetchers/chip_total.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): chip_total fetcher reads FINMIND_TOKEN from settings (BE-A-T8c)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11 (BE-A-T8d): Replace token env read in `fetchers/fundamentals_stock.py`

**Files:**
- Modify: `stock/dashboard/backend/fetchers/fundamentals_stock.py` (top imports + line 28)

- [ ] **Step 1: Apply the same pattern**

Open `stock/dashboard/backend/fetchers/fundamentals_stock.py`. Add after existing imports (before `FINMIND_TOKEN`):

```python
from core.settings import settings
```

Find:

```python
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()
```

Replace with:

```python
FINMIND_TOKEN = settings.finmind_token.get_secret_value().strip()
```

- [ ] **Step 2: Confirm `os` is still needed**

```bash
grep -n "os\." /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/fetchers/fundamentals_stock.py
```

If zero matches, remove `import os`. Otherwise keep.

- [ ] **Step 3: Smoke-import + full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "import fetchers.fundamentals_stock; print('ok')"
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `ok` and `5 failed, 128 passed`.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/fetchers/fundamentals_stock.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): fundamentals_stock fetcher reads FINMIND_TOKEN from settings (BE-A-T8d)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12 (BE-A-T9): `app.py` CORS + startup logging

**Files:**
- Modify: `stock/dashboard/backend/app.py` (top imports, line 46 CORS, startup hook)

- [ ] **Step 1: Add the settings import near the top**

Find the import block near the top of `stock/dashboard/backend/app.py` (after the existing FastAPI imports). Add:

```python
from core.settings import settings
```

- [ ] **Step 2: Replace the hardcoded CORS list at line 46**

Find:

```python
    allow_origins=["https://paul-learning.dev"],
```

Replace with:

```python
    allow_origins=settings.cors_origins,
```

- [ ] **Step 3: Add `setup_logging()` to the startup hook**

Find the existing startup hook (around line 77):

```python
@app.on_event("startup")
def startup():
    init_db()
    try:
        from scheduler import start_scheduler
        start_scheduler()
    except ImportError:
        print("[app] scheduler not available yet")
```

Replace with:

```python
@app.on_event("startup")
def startup():
    from core.logging import setup_logging
    setup_logging()
    init_db()
    try:
        from scheduler import start_scheduler
        start_scheduler()
    except ImportError:
        print("[app] scheduler not available yet")
```

(The trailing `print` is intentionally retained; BE-C cleans it up.)

- [ ] **Step 4: Smoke-import**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "import app; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`. (The `test_api.py` tests use FastAPI's TestClient which goes through CORS middleware; settings-driven `cors_origins` should produce identical behaviour.)

- [ ] **Step 6: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/app.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): app.py uses settings + initialises logging (BE-A-T9)

CORS origins now come from settings.cors_origins (default unchanged).
Startup hook calls setup_logging() before init_db so subsequent log
output is properly formatted via journalctl.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13 (BE-A-T10): Phase final verification

**Files:**
- Inspect only.

- [ ] **Step 1: Verify no `os.environ` / `os.getenv` remains in backend code (excluding tests/conftest.py)**

```bash
grep -rn "os\.environ\|os\.getenv" /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/ 2>&1 | grep -v __pycache__
```

Expected: zero matches. If any line still reads env vars in `backend/`, address it before proceeding (it should have been covered by T5–T12).

`tests/conftest.py:5` (`os.environ["DB_PATH"] = ":memory:"`) is intentionally retained — that's the test harness, not application code.

- [ ] **Step 2: Verify the `core/` package has all four files**

```bash
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/core/
```

Expected: `__init__.py`, `errors.py`, `logging.py`, `settings.py` (and possibly `__pycache__/`).

- [ ] **Step 3: Sanity-check settings from a fresh interpreter**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from core.settings import settings
print('db_path =', settings.db_path)
print('log_level =', settings.log_level)
print('cors_origins =', settings.cors_origins)
print('finmind set =', bool(settings.finmind_token.get_secret_value()))
print('discord set =', settings.discord_stock_webhook_url is not None)
"
```

Expected: prints values from `.env` or defaults. The boolean fields print `True` or `False` — they reveal nothing sensitive.

- [ ] **Step 4: Run the full test suite one final time**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed, 3 warnings`. The 5 failures are still the pre-existing baseline.

- [ ] **Step 5: Verify the branch log is clean**

```bash
cd /Users/paulwu/Documents/Github/tools && git log --oneline master..HEAD
```

Expected (12 commits, in reverse chronological order ending at the BE-A-T1 commit):

```
… BE-A-T9
… BE-A-T8d
… BE-A-T8c
… BE-A-T8b
… BE-A-T8a
… BE-A-T7
… BE-A-T6
… BE-A-T5
… BE-A-T4
… BE-A-T3
… BE-A-T2
… BE-A-T1
```

(If using a feature branch — see Execution Notes — `master..HEAD` shows commits ahead of master.)

If the log doesn't match, investigate. There should be no extra commits and no missing tasks.

- [ ] **Step 6: No commit needed for verification**

This task is read-only verification. Nothing to commit.

---

## Spec Coverage Self-Check

Cross-reference each section of the BE-A spec to the tasks above:

| Spec section | Task |
|---|---|
| §1 `core/settings.py` | T2 |
| §2 `core/logging.py` | T3 |
| §3 `core/errors.py` | T4 |
| §4 `db/__init__.py` callsite | T5 |
| §4 `backfill.py` dead-code removal | T6 |
| §4 `alerts.py` callsite | T7 |
| §4 `fetchers/chip_stock.py` | T8 |
| §4 `fetchers/broker.py` | T9 |
| §4 `fetchers/chip_total.py` | T10 |
| §4 `fetchers/fundamentals_stock.py` | T11 |
| §4 `app.py` CORS | T12 |
| §4 `app.py` startup hook (`setup_logging()`) | T12 |
| §5 Tests (`test_settings.py`, `test_logging.py`) | T2, T3 |
| §6 Migration order (10 steps) | T1–T13 (mapped 1:1) |
| §7 Risks: deps install verified | T1 |
| §7 Risks: `SecretStr.get_secret_value()` consistently called | T7–T11 each call it |
| §8 Acceptance: zero `os.environ` in backend | T13 step 1 |
| §8 Acceptance: 128 tests pass | T13 step 4 |
| §8 Acceptance: settings importable | T13 step 3 |

All sections covered.

---

## Execution Notes

- **Branch strategy**: per CONVENTIONS.md §5.3, large refactors get a feature branch. Recommended: `git checkout -b feat/be-a-core-infra` from master before starting T1, then merge `--no-ff` after T13 passes. (Following the same pattern as Phase 1's `feat/migr-phase-1` branch.)
- **Total tasks**: 13 (T1 through T13, with T8 split into T8a–T8d for one-fetcher-per-commit clarity). Each task ends green with a single commit.
- **Estimated time**: 2–5 minutes per task; ~30–45 minutes total once familiar with the codebase.
- **No new dependencies beyond `pydantic-settings>=2.0.0`** — already standard in the FastAPI ecosystem.
- **Tests verify behaviour**, not implementation: `test_settings_secret_finmind_token_not_in_repr` would catch any future refactor that switches away from `SecretStr` and starts leaking the token.

## Future-phase Notes (do not implement here)

- **BE-B** will replace remaining `print(...)` calls inside `alerts.py`, `backfill.py`, and the fetchers as those modules are split into `services/` / `repositories/`. It will also adopt `RepositoryError` / `FetcherError` from `core/errors.py`.
- **BE-C** will rename `app.py` → `main.py`, register a FastAPI exception handler that maps `StockDashboardError` subclasses to HTTP responses, and replace the trailing `print("[app] scheduler not available yet")` with `logger.warning(...)`.
- **Phase 4 (AUTH-)** will add `discord_ops_webhook_url` to `Settings`, populated from the corresponding GitHub Secret + VPS `.env`.
