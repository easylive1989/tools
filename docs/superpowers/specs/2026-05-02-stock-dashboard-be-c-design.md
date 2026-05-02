# Stock Dashboard BE-C: API Layer + main.py Design Spec

**Date**: 2026-05-02
**Phase**: BE-C (third sub-phase of Phase 2 — Backend Layered Refactor)
**Parent spec**: `docs/superpowers/specs/2026-05-02-stock-dashboard-conventions-design.md` §2.1, §4.3, §7 Phase 2
**Predecessors**: BE-A (`core/`), BE-B (`repositories/`, `services/`)
**Scope**:
- Split `app.py` (697 lines, 18 endpoints) into 5 `api/routes/*.py` files
- Extract 3 inline Pydantic models into `api/schemas/{stocks.py, alerts.py}`
- Move `RANGE_DELTAS` constant into `api/_constants.py`
- Rename `app.py` → `main.py` (FastAPI assembly only, ≤ 60 lines)
- Register a FastAPI exception handler that maps `StockDashboardError` subclasses to HTTP responses (scaffolding for Phase 3 fetcher errors)
- Replace the lone `print("[app] scheduler not available yet")` with `logger.warning(...)`
- Update `stock-dashboard.service` `ExecStart` from `app:app` to `main:app`
- Update 4 `tests/test_*.py` files: `from app import app` → `from main import app`

## Goals

1. Match the layered structure defined in CONVENTIONS.md §2.1: routes layer is FastAPI surface only, never SQL or external HTTP, never business logic.
2. Make `main.py` a thin FastAPI assembly file (~50–60 lines): instantiate, configure CORS, mount routers, register exception handler, define startup hook.
3. Split route definitions by resource so each file has one clear responsibility.
4. Set up the `StockDashboardError → HTTP` mapping so Phase 3 (fetcher errors) and Phase 4 (auth errors) work out-of-the-box without further FastAPI changes.

## Non-Goals

- Do not introduce `api/dependencies.py`. Phase 4 creates it when `verify_token` lands.
- Do not migrate route inputs to use Pydantic where they currently take query / path params. Existing signatures stay (e.g. `def stock_chip(ticker: str, days: int = 20):`).
- Do not raise `FetcherError` / `RepositoryError` / `AuthError` from any caller. The handler is registered but no production code raises domain errors yet — adoption follows in Phase 3 / Phase 4.
- Do not refactor `remove_watched_ticker`'s cross-table side effect. It stays in `repositories/stocks.py`.
- Do not delete the `db/__init__.py` re-export block. `scheduler.py`, `services/backfill.py`, fetchers, and existing tests still import through `db`.
- Do not move existing tests into `tests/{unit,integration,api}/` subdirectories.

---

## 1. Target File Structure

```
backend/
├── main.py                     ← NEW: FastAPI assembly (renamed from app.py)
├── api/                        ← NEW
│   ├── __init__.py             ← empty package marker
│   ├── _constants.py           ← RANGE_DELTAS shared constant
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── indicators.py       ← /api/dashboard, /api/history/{indicator}, /api/refresh/{indicator}
│   │   ├── stocks.py           ← /api/stocks (CRUD), /api/stocks/{ticker}/{brokers,chip,history}
│   │   ├── fundamentals.py     ← /api/stocks/{ticker}/{valuation,revenue,financial,dividend} + 5 helpers
│   │   ├── alerts.py           ← /api/alerts (CRUD)
│   │   └── news.py             ← /api/news
│   └── schemas/
│       ├── __init__.py
│       ├── stocks.py           ← AddStockRequest
│       └── alerts.py           ← AlertRequest, AlertToggleRequest
├── core/                       ← unchanged (BE-A)
├── db/                         ← unchanged (BE-B)
├── repositories/               ← unchanged (BE-B)
├── services/                   ← unchanged (BE-B)
├── alerts.py                   ← unchanged (BE-B thin re-export)
├── backfill.py                 ← unchanged (BE-B thin wrapper)
├── scheduler.py                ← unchanged
├── fetchers/                   ← unchanged
└── (no app.py — deleted in T9)

stock-dashboard.service         ← MODIFIED: ExecStart `app:app` → `main:app`

tests/
├── test_api.py                 ← MODIFIED: from app import app → from main import app
├── test_brokers.py             ← same
├── test_chip.py                ← same
├── test_fundamentals.py        ← same
└── (others unchanged)
```

---

## 2. Endpoint → Router Mapping

### `routes/indicators.py` (3 endpoints)

| Method | Path | Function |
|---|---|---|
| GET | `/api/dashboard` | `dashboard()` |
| GET | `/api/history/{indicator}` | `history(indicator: str, time_range: str = "3M")` |
| POST | `/api/refresh/{indicator}` | `refresh(indicator: str)` |

Module-level constants used here only:
- `INDICATOR_NAMES: list[str]`
- `FETCHERS: dict[str, Callable]` (fetcher dispatch)

Imports needed (representative):
```python
from api._constants import RANGE_DELTAS
from repositories.indicators import get_latest_indicator, get_indicator_history
from fetchers.yfinance_fetcher import fetch_taiex, fetch_fx, fetch_all_stocks
from fetchers.fear_greed import fetch_fear_greed
from fetchers.chip_total import fetch_chip_total
from fetchers.ndc import fetch_ndc
from fetchers.volume import fetch_tw_volume, fetch_us_volume
```

### `routes/stocks.py` (6 endpoints)

| Method | Path | Function |
|---|---|---|
| GET | `/api/stocks` | `get_stocks()` |
| POST | `/api/stocks` | `add_stock(req: AddStockRequest)` |
| DELETE | `/api/stocks/{ticker}` | `delete_stock(ticker)` |
| GET | `/api/stocks/{ticker}/brokers` | `stock_brokers(ticker, days=20, top=5)` |
| GET | `/api/stocks/{ticker}/chip` | `stock_chip(ticker, days=20)` |
| GET | `/api/stocks/{ticker}/history` | `stock_history(ticker, time_range="3M")` |

Imports:
```python
from api._constants import RANGE_DELTAS
from api.schemas.stocks import AddStockRequest
from repositories.stocks import (
    get_watched_tickers, get_latest_stock,
    add_watched_ticker, remove_watched_ticker,
)
from repositories.chip import get_broker_daily_range, get_chip_daily_range
from fetchers.yfinance_fetcher import fetch_stock_history
```

### `routes/fundamentals.py` (4 endpoints + 5 private helpers)

| Method | Path | Function |
|---|---|---|
| GET | `/api/stocks/{ticker}/valuation` | `stock_valuation(ticker, years=5)` |
| GET | `/api/stocks/{ticker}/revenue` | `stock_revenue(ticker, months=36)` |
| GET | `/api/stocks/{ticker}/financial` | `stock_financial(ticker, statement="income", quarters=12)` |
| GET | `/api/stocks/{ticker}/dividend` | `stock_dividend(ticker, years=10)` |

Private helpers (file-local, underscore prefix):
- `_build_income_row(date, types) -> dict`
- `_build_balance_row(date, types) -> dict`
- `_build_cashflow_row(date, types) -> dict`
- `_aggregate_dividend_by_calendar_year(rows) -> dict[int, dict]`
- `_annual_eps_sum(ticker, year) -> float | None`

Imports:
```python
from repositories.fundamentals import (
    get_per_daily_range, get_revenue_monthly_range,
    get_financial_quarterly_range, get_dividend_history,
)
from fetchers.fundamentals_stock import (
    fetch_stock_per, fetch_stock_revenue,
    fetch_stock_financial, fetch_stock_dividend,
    to_finmind_id as fundamentals_to_finmind_id,
)
```

Estimated file size: ~250 lines (4 endpoints x ~30 lines + 5 helpers x ~20 lines).

### `routes/alerts.py` (4 endpoints)

| Method | Path | Function |
|---|---|---|
| GET | `/api/alerts` | `get_alerts()` |
| POST | `/api/alerts` | `create_alert(req: AlertRequest)` |
| DELETE | `/api/alerts/{alert_id}` | `remove_alert(alert_id)` |
| PATCH | `/api/alerts/{alert_id}` | `toggle_alert(alert_id, req: AlertToggleRequest)` |

Imports:
```python
from api.schemas.alerts import AlertRequest, AlertToggleRequest
from repositories.alerts import (
    list_alerts, add_alert, delete_alert, set_alert_enabled,
)
```

### `routes/news.py` (1 endpoint)

| Method | Path | Function |
|---|---|---|
| GET | `/api/news` | `get_news(limit=15)` |

Imports:
```python
from fetchers.news import fetch_news
```

### Common Router Pattern

Every `routes/*.py` opens with:

```python
"""<Resource> routes."""
import logging
from fastapi import APIRouter, HTTPException
# ... other imports ...

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["<resource>"])
```

Endpoints decorated with `@router.get(...)` etc. (not `@app.get(...)`).

---

## 3. Schemas

### `api/schemas/stocks.py`

```python
from pydantic import BaseModel


class AddStockRequest(BaseModel):
    ticker: str
```

### `api/schemas/alerts.py`

```python
from pydantic import BaseModel


class AlertRequest(BaseModel):
    target_type: str
    target: str
    condition: str
    threshold: float
    indicator_key: str | None = None
    window_n: int | None = None


class AlertToggleRequest(BaseModel):
    enabled: bool
```

(Field types match the current inline definitions in `app.py`.)

---

## 4. Constants

### `api/_constants.py`

```python
"""Shared constants used by multiple route modules."""
from datetime import timedelta


RANGE_DELTAS: dict[str, timedelta] = {
    "1M": timedelta(days=30),
    "3M": timedelta(days=90),
    "6M": timedelta(days=180),
    "1Y": timedelta(days=365),
    "3Y": timedelta(days=1095),
}
```

Used by `routes/indicators.py` (`history` endpoint) and `routes/stocks.py` (`stock_history` endpoint). Other modules don't import it.

`INDICATOR_NAMES` and `FETCHERS` are private to `routes/indicators.py` and stay there.

---

## 5. `main.py`

Final shape (~50–60 lines):

```python
"""Stock Dashboard FastAPI application."""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import indicators, stocks, fundamentals, alerts, news
from core.errors import (
    AuthError, FetcherError, RepositoryError, StockDashboardError,
)
from core.settings import settings

logger = logging.getLogger(__name__)

app = FastAPI(title="Stock Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["*"],
)

app.include_router(indicators.router)
app.include_router(stocks.router)
app.include_router(fundamentals.router)
app.include_router(alerts.router)
app.include_router(news.router)


_ERROR_TO_STATUS: list[tuple[type[StockDashboardError], int]] = [
    (AuthError, 401),
    (FetcherError, 502),
    (RepositoryError, 500),
]


@app.exception_handler(StockDashboardError)
async def stock_dashboard_error_handler(request: Request, exc: StockDashboardError):
    status = 500
    for cls, code in _ERROR_TO_STATUS:
        if isinstance(exc, cls):
            status = code
            break
    detail = (
        "資料來源暫時無法取得"
        if isinstance(exc, FetcherError)
        else (str(exc) or exc.__class__.__name__)
    )
    logger.warning("api_domain_error class=%s status=%d", exc.__class__.__name__, status)
    return JSONResponse(status_code=status, content={"detail": detail})


@app.on_event("startup")
def startup():
    from core.logging import setup_logging
    setup_logging()
    from db import init_db
    init_db()
    try:
        from scheduler import start_scheduler
        start_scheduler()
    except ImportError:
        logger.warning("scheduler_not_available")
```

Notes:

- **Module-level `app = FastAPI(...)`** (no factory pattern). Single deployment, no environment variants — keep simple.
- **Exception handler matches subclasses by isinstance** — `@app.exception_handler(StockDashboardError)` is FastAPI's built-in dispatch; subclass instances trigger this handler. `_ERROR_TO_STATUS` order matters (most specific first) but currently all subclasses are siblings under `StockDashboardError`, so any single check finds the match.
- **`detail = "資料來源暫時無法取得"`** for `FetcherError`: matches CONVENTIONS.md §4.3's user-facing message.
- **Imports inside `startup()`** for `setup_logging`, `init_db`, `start_scheduler`: deferred imports avoid bootstrapping side effects at module load (kept consistent with existing `app.py`).
- **`logger.warning("scheduler_not_available")`** replaces the last surviving `print` in app.py / main.py.

---

## 6. Migration Order (Implementation Plan Tasks)

10 tasks (BE-C-T1 through BE-C-T10), each ending in a green test suite and a commit. All commits use `(BE-C-Tn)` step IDs.

| # | Task |
|---|---|
| T1 | `api/__init__.py`, `api/routes/__init__.py`, `api/schemas/__init__.py`, `api/_constants.py` (RANGE_DELTAS); update `app.py` to import RANGE_DELTAS from new location |
| T2 | `api/schemas/{stocks.py, alerts.py}`; `app.py` imports from these instead of defining inline (delete `class AddStockRequest`, `class AlertRequest`, `class AlertToggleRequest`) |
| T3 | `routes/indicators.py` (3 endpoints); `app.py` adds `app.include_router(indicators.router)` and removes the 3 inline `@app.get/@app.post` definitions |
| T4 | `routes/stocks.py` (6 endpoints); same pattern |
| T5 | `routes/fundamentals.py` (4 endpoints + 5 helpers); same pattern |
| T6 | `routes/alerts.py` (4 endpoints); same pattern |
| T7 | `routes/news.py` (1 endpoint); same pattern |
| T8 | Add exception handler to `app.py`; replace `print("[app] scheduler not available yet")` with `logger.warning("scheduler_not_available")`; verify final shape |
| T9 | Rename `app.py` → `main.py`; update `tests/test_{api,brokers,chip,fundamentals}.py` imports; update `stock-dashboard.service` `ExecStart` (`app:app` → `main:app`) |
| T10 | Final verification (no commit) |

T1–T8: app.py remains the FastAPI source. Tests continue to use `from app import app`.
T9: rename + service file + tests in one commit so deploy switches atomically.
T10: read-only verification; runs the full suite, inspects file sizes, confirms branch log.

---

## 7. Backward Compatibility

- `from db import …` continues to work for `scheduler.py`, `services/backfill.py`, fetchers, and tests. The re-export block in `db/__init__.py` (added in BE-B) is preserved.
- `import alerts as alerts_module` continues to work for `tests/test_alerts.py`. The thin re-export module `backend/alerts.py` (BE-B) is unchanged.
- `python backfill.py` from `backend/` continues to work via the BE-B thin wrapper.
- All existing endpoint URLs and request/response shapes are byte-for-byte unchanged.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Renaming `app.py` to `main.py` while VPS service still expects `app:app` causes deploy failure | T9 packages: rename + service file + 4 test imports in ONE commit. Deploy executes them together. Local `python3 -c "from main import app; print(app)"` smoke check before commit. |
| FastAPI route duplicate registration if a Tn adds `app.include_router` but forgets to delete the inline `@app.get` | Each Tn explicitly enumerates the inline definitions to remove. Suite catches duplicates indirectly: pytest fails on `RuntimeError` if a duplicate path conflicts. |
| `RANGE_DELTAS` reference missed when migrating to `_constants.py` | T1 ends with `grep -rn "RANGE_DELTAS" backend/` showing only `_constants.py` (definition) and the importing modules. |
| `routes/fundamentals.py` ~250 lines feels large | Accepted: helpers are pure view-shape transformations, splitting them into a separate file would obscure the per-endpoint flow. CONVENTIONS.md §brainstorm prefers cohesion over size when concerns are tightly coupled. |
| Routes start importing from `repositories.X` directly while `db/__init__.py` re-export still exists, creating two import paths | Accepted as transitional. New code (BE-C routes) uses `repositories.X`; old callers (scheduler, fetchers, tests) keep `from db import …`. Re-exports stay until the last caller migrates (post-Phase 3). |
| `StockDashboardError` exception handler registered but no production raise site → looks like dead code | Documented as scaffolding. Adopted in Phase 3 (fetchers raise FetcherError) and Phase 4 (auth raises AuthError). Optionally add a tiny unit test in T8 that posts a fake request through TestClient and a stub raising `FetcherError` to verify the 502 mapping — non-essential but cheap insurance. |
| `tests/test_api.py` (and 3 others) import `from app import app`; T9 changes that to `from main import app`. If T9 misses one, that test fails to collect | T9 step explicitly lists 4 files; final grep `^from app import\\|^import app` returns zero hits in `tests/`. |
| Deploy workflow filters changes to specific paths; service file changes outside `stock/dashboard/backend/**` may not trigger | `stock-dashboard.service` is in `stock/dashboard/` (not under `backend/`). Verify the workflow's path filter includes `stock/dashboard/stock-dashboard.service`. (Confirmed: existing workflow already triggers on `stock/dashboard/stock-dashboard.service`.) |

---

## 9. Acceptance Criteria

- `api/routes/` contains exactly 5 files (`indicators.py`, `stocks.py`, `fundamentals.py`, `alerts.py`, `news.py`) plus `__init__.py`.
- `api/schemas/` contains exactly 2 files (`stocks.py`, `alerts.py`) plus `__init__.py`.
- `api/_constants.py` defines `RANGE_DELTAS` and is the only definition.
- `backend/main.py` exists, ≤ 60 lines, contains `FastAPI(...)` instantiation, CORS middleware, 5 `include_router(...)` calls, exception handler for `StockDashboardError`, and the startup hook.
- `backend/app.py` does not exist.
- `stock-dashboard.service` `ExecStart` line ends with `main:app …`.
- `grep -rn "^from app\|^import app" tests/` returns zero matches.
- Full test suite: 5 baseline failures (unchanged) + every other test passes. Total `5 failed, 128 passed`.
- VPS deploy succeeds; `systemctl is-active stock-dashboard` returns `active`; `journalctl -u stock-dashboard -n 20` shows clean startup; `curl http://127.0.0.1:8000/api/dashboard` (run on VPS) returns 200 with JSON body.

---

## 10. After This Phase

- **Phase 3 (REG-)**: refactor fetchers to conform to `Fetcher` Protocol; introduce alert indicator registry. Fetchers will start raising `FetcherError`, which the BE-C exception handler then maps to HTTP 502 automatically.
- **Phase 4 (AUTH-)**: add `api/dependencies.py` with `verify_token`; add `discord_ops_webhook_url` to settings; protect endpoints with `Depends(verify_token)`. AuthError will map to HTTP 401 via the BE-C exception handler.
- **After Phase 5 (FE-)**: with the React frontend live, consider deleting the `db/__init__.py` re-export block and the thin `alerts.py` re-export module if all callers have migrated to direct imports.
