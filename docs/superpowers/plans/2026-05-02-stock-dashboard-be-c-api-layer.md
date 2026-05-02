# Stock Dashboard BE-C: API Layer + main.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `app.py` (697 lines, 18 endpoints) into 5 `api/routes/*.py` files + `api/schemas/{stocks,alerts}.py` + `api/_constants.py`. Rename `app.py` → `main.py` (FastAPI assembly only). Register a `StockDashboardError` exception handler scaffolding for future phases. Update systemd service + 4 test imports atomically in one commit.

**Architecture:** Each Tn (T3-T7) extracts one route group: copies endpoints to `routes/<group>.py` as an `APIRouter(prefix="/api", tags=[...])`, registers it on `app` via `include_router(...)`, and removes the original inline `@app.X` definitions. `app.py` stays the FastAPI source until T9 renames it to `main.py`. Tests use `from app import app` until T9, then `from main import app`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2.x, pytest. No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-02-stock-dashboard-be-c-design.md`.

---

## File Structure

**Created:**
- `stock/dashboard/backend/api/__init__.py` — empty
- `stock/dashboard/backend/api/_constants.py` — `RANGE_DELTAS` and `INDICATOR_NAMES`
- `stock/dashboard/backend/api/routes/__init__.py` — empty
- `stock/dashboard/backend/api/routes/indicators.py`
- `stock/dashboard/backend/api/routes/stocks.py`
- `stock/dashboard/backend/api/routes/fundamentals.py`
- `stock/dashboard/backend/api/routes/alerts.py`
- `stock/dashboard/backend/api/routes/news.py`
- `stock/dashboard/backend/api/schemas/__init__.py` — empty
- `stock/dashboard/backend/api/schemas/stocks.py` — `AddStockRequest`
- `stock/dashboard/backend/api/schemas/alerts.py` — `AlertRequest`, `AlertToggleRequest`

**Modified:**
- `stock/dashboard/backend/app.py` — progressively shrunk in T1-T8; deleted in T9
- `stock/dashboard/backend/main.py` — created in T9 (rename from app.py)
- `stock/dashboard/stock-dashboard.service` — `ExecStart` updated in T9
- `stock/dashboard/tests/test_api.py` — `from app import app` → `from main import app` (T9)
- `stock/dashboard/tests/test_brokers.py` — same (T9)
- `stock/dashboard/tests/test_chip.py` — same (T9)
- `stock/dashboard/tests/test_fundamentals.py` — same (T9)

**Unchanged:**
- `core/`, `db/`, `repositories/`, `services/`, `fetchers/`, `alerts.py`, `backfill.py`, `scheduler.py`
- `tests/conftest.py`, `tests/test_alerts.py`, `tests/test_db.py`, `tests/test_fetchers.py`, `tests/test_settings.py`, `tests/test_logging.py`, `tests/test_migration_runner.py`

---

## Baseline

Verify before starting: `5 failed, 128 passed` with these specific failures (DO NOT FIX):

- `tests/test_brokers.py::test_brokers_endpoint_rejects_non_taiwan_ticker`
- `tests/test_brokers.py::test_brokers_endpoint_rejects_invalid_params`
- `tests/test_brokers.py::test_brokers_endpoint_returns_top5_by_net_buy`
- `tests/test_fetchers.py::test_fetch_ndc_saves_indicator`
- `tests/test_fetchers.py::test_fetch_fear_greed_saves_indicator`

After this phase the count is unchanged: `5 failed, 128 passed`.

---

## Task Breakdown

### Task 1 (BE-C-T1): `api/` package + `_constants.py`

**Files:**
- Create: `stock/dashboard/backend/api/__init__.py` (empty)
- Create: `stock/dashboard/backend/api/_constants.py`
- Create: `stock/dashboard/backend/api/routes/__init__.py` (empty)
- Create: `stock/dashboard/backend/api/schemas/__init__.py` (empty)
- Modify: `stock/dashboard/backend/app.py` — replace inline `RANGE_DELTAS` and `INDICATOR_NAMES` with imports

- [ ] **Step 1: Verify baseline**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed, 3 warnings`. Same baseline.

- [ ] **Step 2: Create empty package markers**

```bash
mkdir -p /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/routes
mkdir -p /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/schemas
touch /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/__init__.py
touch /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/routes/__init__.py
touch /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/schemas/__init__.py
```

- [ ] **Step 3: Create `api/_constants.py`**

Write `stock/dashboard/backend/api/_constants.py` with this exact content:

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


INDICATOR_NAMES: list[str] = [
    "taiex", "fx", "fear_greed",
    "margin_balance", "short_balance", "short_margin_ratio",
    "total_foreign_net", "total_trust_net", "total_dealer_net",
    "ndc", "tw_volume", "us_volume",
]
```

- [ ] **Step 4: Update `app.py` to import from `api/_constants.py`**

In `stock/dashboard/backend/app.py`:

1. Delete the inline `RANGE_DELTAS` block (lines 51–57 of original):

```python
RANGE_DELTAS: dict[str, timedelta] = {
    "1M": timedelta(days=30),
    ...
}
```

2. Delete the inline `INDICATOR_NAMES` block (lines 70–75):

```python
INDICATOR_NAMES = [
    "taiex", "fx", "fear_greed",
    ...
]
```

3. After the existing `from core.settings import settings` line, add:

```python
from api._constants import RANGE_DELTAS, INDICATOR_NAMES
```

- [ ] **Step 5: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

- [ ] **Step 6: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/api/__init__.py stock/dashboard/backend/api/_constants.py stock/dashboard/backend/api/routes/__init__.py stock/dashboard/backend/api/schemas/__init__.py stock/dashboard/backend/app.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add api/ package + _constants.py (BE-C-T1)

api/{routes,schemas}/ packages set up. RANGE_DELTAS and
INDICATOR_NAMES extracted to api/_constants.py; app.py now imports
from there. Foundation for upcoming route extraction.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2 (BE-C-T2): Schemas

**Files:**
- Create: `stock/dashboard/backend/api/schemas/stocks.py`
- Create: `stock/dashboard/backend/api/schemas/alerts.py`
- Modify: `stock/dashboard/backend/app.py` — delete 3 inline classes, add imports

- [ ] **Step 1: Create `api/schemas/stocks.py`**

```python
"""Stock-related request/response schemas."""
from pydantic import BaseModel


class AddStockRequest(BaseModel):
    ticker: str
```

- [ ] **Step 2: Create `api/schemas/alerts.py`**

```python
"""Alert-related request/response schemas."""
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

- [ ] **Step 3: Update `app.py` — delete inline classes**

In `stock/dashboard/backend/app.py`:

1. Find and delete `class AddStockRequest(BaseModel):` and its body (currently around lines 134–135).
2. Find and delete `class AlertRequest(BaseModel):` and its body (currently around lines 575–581).
3. Find and delete `class AlertToggleRequest(BaseModel):` and its body (currently around lines 584–585).

- [ ] **Step 4: Add imports near the top of `app.py`**

After the existing `from api._constants import RANGE_DELTAS, INDICATOR_NAMES` line (added in T1), add:

```python
from api.schemas.stocks import AddStockRequest
from api.schemas.alerts import AlertRequest, AlertToggleRequest
```

The `from pydantic import BaseModel` line at the top of `app.py` is no longer needed (no inline classes remain). Remove it.

- [ ] **Step 5: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

- [ ] **Step 6: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/api/schemas/stocks.py stock/dashboard/backend/api/schemas/alerts.py stock/dashboard/backend/app.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): extract api/schemas/{stocks,alerts}.py (BE-C-T2)

3 inline Pydantic models moved into api/schemas/. app.py imports
from new location; no longer needs `from pydantic import BaseModel`.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3 (BE-C-T3): `routes/indicators.py` (3 endpoints)

**Files:**
- Create: `stock/dashboard/backend/api/routes/indicators.py`
- Modify: `stock/dashboard/backend/app.py` — register router, delete 3 inline endpoints, move `FETCHERS` constant

- [ ] **Step 1: Create `api/routes/indicators.py`**

Write the following content. The `FETCHERS` dict moves here from `app.py` because only `refresh()` uses it.

```python
"""Indicator routes: dashboard, history, refresh."""
import json
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from api._constants import INDICATOR_NAMES, RANGE_DELTAS
from repositories.indicators import (
    get_indicator_history, get_latest_indicator,
)
from fetchers.yfinance_fetcher import fetch_taiex, fetch_fx, fetch_all_stocks
from fetchers.fear_greed import fetch_fear_greed
from fetchers.chip_total import fetch_chip_total
from fetchers.ndc import fetch_ndc
from fetchers.volume import fetch_tw_volume, fetch_us_volume

router = APIRouter(prefix="/api", tags=["indicators"])


FETCHERS: dict[str, Callable] = {
    "taiex":      fetch_taiex,
    "fx":         fetch_fx,
    "fear_greed": fetch_fear_greed,
    "chip_total": fetch_chip_total,
    "ndc":        fetch_ndc,
    "stocks":     fetch_all_stocks,
    "tw_volume":  fetch_tw_volume,
    "us_volume":  fetch_us_volume,
}


@router.get("/dashboard")
def dashboard():
    result = {}
    for name in INDICATOR_NAMES:
        row = get_latest_indicator(name)
        if row:
            result[name] = {
                "value":     row["value"],
                "timestamp": row["timestamp"],
                "extra":     json.loads(row["extra_json"]) if row["extra_json"] else {},
            }
    return result


@router.get("/history/{indicator}")
def history(indicator: str, time_range: str = "3M"):
    if indicator not in INDICATOR_NAMES:
        raise HTTPException(status_code=404, detail="Unknown indicator")
    delta = RANGE_DELTAS.get(time_range, RANGE_DELTAS["3M"])
    since = datetime.now(timezone.utc).replace(tzinfo=None) - delta
    rows = get_indicator_history(indicator, since)
    return [{"timestamp": r["timestamp"], "value": r["value"]} for r in rows]


@router.post("/refresh/{indicator}")
def refresh(indicator: str):
    fn = FETCHERS.get(indicator)
    if fn is None:
        raise HTTPException(status_code=404, detail="Unknown indicator")
    try:
        fn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}
```

- [ ] **Step 2: Update `app.py`**

In `stock/dashboard/backend/app.py`:

1. Delete the `FETCHERS` dict definition (currently lines 59–68).
2. Delete the `@app.get("/api/dashboard")` block (`def dashboard():` and body, lines 90–101).
3. Delete the `@app.get("/api/history/{indicator}")` block (lines 104–111).
4. Delete the `@app.post("/api/refresh/{indicator}")` block (lines 682–691).
5. Add import near the top: `from api.routes import indicators`.
6. After the CORS middleware block (after `app.add_middleware(CORSMiddleware, ...)`), add: `app.include_router(indicators.router)`.

After this task, `app.py` no longer references `FETCHERS`. The `from collections.abc import Callable` import at the top is now unused — remove it. Same for unused `import json` if no other route still uses it (verify).

The `from fetchers.yfinance_fetcher import fetch_taiex, fetch_fx, fetch_all_stocks` line at the top of `app.py` may still be needed if other routes use them (`fetch_all_stocks` is used in `add_stock`). Keep what's needed.

- [ ] **Step 3: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

- [ ] **Step 4: Smoke-check the endpoints register**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from app import app
paths = [r.path for r in app.routes]
for p in ['/api/dashboard', '/api/history/{indicator}', '/api/refresh/{indicator}']:
    assert p in paths, f'missing: {p}'
print('ok')
"
```

Expected: prints `ok`.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/api/routes/indicators.py stock/dashboard/backend/app.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): extract routes/indicators.py (BE-C-T3)

3 endpoints (dashboard, history, refresh) moved into api/routes/
indicators.py with APIRouter. FETCHERS dict relocates to the same
file. app.py registers the router and drops the inline definitions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4 (BE-C-T4): `routes/stocks.py` (6 endpoints)

**Files:**
- Create: `stock/dashboard/backend/api/routes/stocks.py`
- Modify: `stock/dashboard/backend/app.py` — register router, delete 6 inline endpoints

- [ ] **Step 1: Create `api/routes/stocks.py`**

```python
"""Stock + watchlist routes."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from api._constants import RANGE_DELTAS
from api.schemas.stocks import AddStockRequest
from repositories.chip import get_broker_daily_range, get_chip_daily_range
from repositories.stocks import (
    add_watched_ticker, get_latest_stock, get_watched_tickers, remove_watched_ticker,
)
from fetchers.yfinance_fetcher import fetch_all_stocks, fetch_stock_history
from fetchers.chip_stock import fetch_stock_chip, to_finmind_id as chip_to_finmind_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["stocks"])


@router.get("/stocks")
def get_stocks():
    result = []
    for ticker in get_watched_tickers():
        row = get_latest_stock(ticker)
        if row:
            result.append({
                "ticker":     ticker,
                "name":       row["name"],
                "price":      row["price"],
                "change":     row["change"],
                "change_pct": row["change_pct"],
                "currency":   row["currency"],
                "timestamp":  row["timestamp"],
            })
        else:
            result.append({"ticker": ticker, "name": ticker, "price": None})
    return result


@router.post("/stocks")
def add_stock(req: AddStockRequest):
    add_watched_ticker(req.ticker.upper())
    try:
        fetch_all_stocks()
    except Exception as e:
        logger.warning("add_stock_fetch_error error=%s", e)
    return {"ok": True}


@router.delete("/stocks/{ticker}")
def delete_stock(ticker: str):
    remove_watched_ticker(ticker.upper())
    return {"ok": True}


@router.get("/stocks/{ticker}/brokers")
def stock_brokers(ticker: str, days: int = 20, top: int = 5):
    # 已停用：FinMind TaiwanStockTradingDailyReport 改為 Sponsor 限定 (見 README)。
    # 程式碼保留以便未來重啟功能。
    return {
        "ticker":      ticker.upper(),
        "days":        days,
        "as_of":       None,
        "ok":          False,
        "top_brokers": [],
    }


@router.get("/stocks/{ticker}/chip")
def stock_chip(ticker: str, days: int = 20):
    """個股籌碼:近 N 個交易日的三大法人淨買賣 + 融資融券餘額。

    Lazy fetch + DB cache。輸出每筆 row 含:
    foreign_net / trust_net / dealer_net(buy-sell)、margin_balance、short_balance。
    """
    ticker = ticker.upper()
    if chip_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days must be 1..90")

    fetched = fetch_stock_chip(ticker)
    since_date = (datetime.now(timezone.utc).date() - timedelta(days=int(days * 1.6) + 5)).isoformat()
    rows = get_chip_daily_range(ticker, since_date)

    if not rows:
        return {
            "ticker": ticker, "days": days, "as_of": None,
            "ok": fetched, "rows": [],
        }

    distinct_dates = sorted({r["date"] for r in rows})
    window_dates = distinct_dates[-days:]
    window_set = set(window_dates)

    def _net(b, s) -> float | None:
        if b is None and s is None:
            return None
        return (b or 0) - (s or 0)

    out_rows = []
    for r in rows:
        if r["date"] not in window_set:
            continue
        out_rows.append({
            "date":           r["date"],
            "foreign_net":    _net(r["foreign_buy"], r["foreign_sell"]),
            "trust_net":      _net(r["trust_buy"], r["trust_sell"]),
            "dealer_net":     _net(r["dealer_buy"], r["dealer_sell"]),
            "margin_balance": r["margin_balance"],
            "short_balance":  r["short_balance"],
        })

    return {
        "ticker": ticker, "days": days,
        "as_of": window_dates[-1] if window_dates else None,
        "ok": True, "rows": out_rows,
    }


@router.get("/stocks/{ticker}/history")
def stock_history(ticker: str, time_range: str = "3M"):
    if time_range not in RANGE_DELTAS:
        raise HTTPException(status_code=400, detail="Unknown time_range")
    try:
        data = fetch_stock_history(ticker.upper(), time_range)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")
    if data is None:
        raise HTTPException(status_code=404, detail="No history available")
    return data
```

Note: `add_stock`'s old `print(f"[add_stock] Fetch error: {e}")` is replaced with `logger.warning(...)` (per CONVENTIONS.md §4.2).

`get_broker_daily_range` is imported but the brokers endpoint doesn't actually use it (short-circuited). Keep the import as a placeholder for when the feature is restored — or remove it. **Remove it** for cleanness; can re-add in a future task.

Actually, simpler: delete the unused `get_broker_daily_range` import. The final import block becomes:

```python
from repositories.chip import get_chip_daily_range
```

- [ ] **Step 2: Update `app.py`**

In `stock/dashboard/backend/app.py`:

1. Delete the `@app.get("/api/stocks")` block (`def get_stocks():`).
2. Delete the `@app.post("/api/stocks")` block (`def add_stock(req: AddStockRequest):`).
3. Delete the `@app.delete("/api/stocks/{ticker}")` block (`def delete_stock(ticker: str):`).
4. Delete the `@app.get("/api/stocks/{ticker}/brokers")` block (`def stock_brokers(...)`).
5. Delete the `@app.get("/api/stocks/{ticker}/chip")` block (`def stock_chip(...)`).
6. Delete the `@app.get("/api/stocks/{ticker}/history")` block (`def stock_history(...)`).
7. Add import: `from api.routes import stocks` (next to the existing `from api.routes import indicators`).
8. Add `app.include_router(stocks.router)` after the existing `indicators` include.
9. Trim the `app.py` top-of-file imports of anything no longer used by remaining routes:
   - `fetch_stock_history` — remove if no other route uses it
   - `chip_to_finmind_id` — remove
   - `get_chip_daily_range` — remove from the `from db import (...)` block
   - `get_broker_daily_range` — remove from the `from db import (...)` block
   - `get_watched_tickers`, `get_latest_stock`, `add_watched_ticker`, `remove_watched_ticker` — remove from the `from db import (...)` block

Don't aggressively trim everything in T4; the suite verifies correctness. Just delete obviously orphaned imports. T8 will do a final cleanup pass.

- [ ] **Step 3: Run full suite + smoke-check endpoints**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from app import app
paths = [r.path for r in app.routes]
expected = ['/api/stocks', '/api/stocks/{ticker}', '/api/stocks/{ticker}/brokers',
            '/api/stocks/{ticker}/chip', '/api/stocks/{ticker}/history']
for p in expected:
    assert p in paths, f'missing: {p}'
print('ok')
"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/api/routes/stocks.py stock/dashboard/backend/app.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): extract routes/stocks.py (BE-C-T4)

6 endpoints (watchlist CRUD + brokers + chip + history) moved into
api/routes/stocks.py. The print in add_stock's exception handler
becomes logger.warning per CONVENTIONS.md §4.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5 (BE-C-T5): `routes/fundamentals.py` (4 endpoints + 5 helpers)

**Files:**
- Create: `stock/dashboard/backend/api/routes/fundamentals.py`
- Modify: `stock/dashboard/backend/app.py` — delete 4 inline endpoints + 5 inline helpers + `_FINANCIAL_BUILDER` dict

- [ ] **Step 1: Create `api/routes/fundamentals.py`**

This is the largest route file (~250 lines). Write the following content:

```python
"""Stock fundamentals routes: valuation, revenue, financial, dividend."""
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from repositories.fundamentals import (
    get_dividend_history, get_financial_quarterly_range,
    get_per_daily_range, get_revenue_monthly_range,
)
from fetchers.fundamentals_stock import (
    fetch_stock_dividend, fetch_stock_financial, fetch_stock_per, fetch_stock_revenue,
    to_finmind_id as fundamentals_to_finmind_id,
)

router = APIRouter(prefix="/api", tags=["fundamentals"])


@router.get("/stocks/{ticker}/valuation")
def stock_valuation(ticker: str, years: int = 5):
    """個股估值快照:PER/PBR/殖利率最新值 + 5 年百分位 + 走勢。"""
    ticker = ticker.upper()
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if years < 1 or years > 10:
        raise HTTPException(status_code=400, detail="years must be 1..10")

    fetched = fetch_stock_per(ticker)
    since_date = (datetime.now(timezone.utc).date() - timedelta(days=years * 366)).isoformat()
    rows = get_per_daily_range(ticker, since_date)

    if not rows:
        return {"ticker": ticker, "years": years, "as_of": None, "ok": fetched,
                "latest": None, "range_5y": None, "rows": []}

    rows_sorted = sorted(rows, key=lambda r: r["date"])
    latest = rows_sorted[-1]

    def _stats(values: list[float]) -> dict:
        clean = [v for v in values if v is not None]
        if not clean:
            return {"min": None, "max": None, "avg": None}
        return {"min": min(clean), "max": max(clean),
                "avg": round(sum(clean) / len(clean), 4)}

    pers = [r["per"]            for r in rows_sorted if r["per"] is not None]
    pbrs = [r["pbr"]            for r in rows_sorted if r["pbr"] is not None]
    yds  = [r["dividend_yield"] for r in rows_sorted if r["dividend_yield"] is not None]

    if latest["per"] is not None and pers:
        # Inclusive percentile rank: P(X <= current_per) × 100。
        # 若 latest 為歷史最高值 → 100;若為最低 → ~ (1/N)×100。
        below = sum(1 for v in pers if v <= latest["per"])
        per_percentile = round(below / len(pers) * 100, 2)
    else:
        per_percentile = None

    return {
        "ticker": ticker, "years": years,
        "as_of": latest["date"], "ok": True,
        "latest": {
            "per": latest["per"], "pbr": latest["pbr"],
            "dividend_yield": latest["dividend_yield"],
            "per_percentile_5y": per_percentile,
        },
        "range_5y": {"per": _stats(pers), "pbr": _stats(pbrs), "dividend_yield": _stats(yds)},
        "rows": rows_sorted,
    }


@router.get("/stocks/{ticker}/revenue")
def stock_revenue(ticker: str, months: int = 36):
    """個股月營收 + YoY + 12MA + YTD vs 去年同期。"""
    ticker = ticker.upper()
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if months < 1 or months > 60:
        raise HTTPException(status_code=400, detail="months must be 1..60")

    fetched = fetch_stock_revenue(ticker)

    today = datetime.now(timezone.utc).date()
    fetch_back_months = months + 14
    since_year = today.year - (fetch_back_months // 12) - 1
    since_month = ((today.month - (fetch_back_months % 12) - 1) % 12) + 1
    rows = get_revenue_monthly_range(ticker, since_year, since_month)

    if not rows:
        return {"ticker": ticker, "months": months, "ok": fetched,
                "latest": None, "ytd": None, "rows": []}

    by_ym = {(r["year"], r["month"]): r["revenue"] for r in rows}

    def _yoy(year: int, month: int) -> float | None:
        cur = by_ym.get((year, month))
        prev = by_ym.get((year - 1, month))
        if cur is None or not prev:
            return None
        return round((cur - prev) / prev * 100, 2)

    def _ma12(year: int, month: int) -> float | None:
        vals = []
        y, m = year, month
        for _ in range(12):
            v = by_ym.get((y, m))
            if v is None:
                return None
            vals.append(v)
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return round(sum(vals) / 12, 0)

    enriched = [{
        "year":    r["year"],
        "month":   r["month"],
        "revenue": r["revenue"],
        "yoy_pct": _yoy(r["year"], r["month"]),
        "ma12":    _ma12(r["year"], r["month"]),
    } for r in rows]

    enriched_sorted = sorted(enriched, key=lambda r: (r["year"], r["month"]))
    last_n = enriched_sorted[-months:]
    latest = enriched_sorted[-1]

    def _ytd_sum(year: int, last_month: int) -> float | None:
        """Return sum 1..last_month for year; None if any month missing."""
        vals = []
        for m in range(1, last_month + 1):
            v = by_ym.get((year, m))
            if v is None:
                return None
            vals.append(v)
        return sum(vals)

    ytd_cur  = _ytd_sum(latest["year"],     latest["month"])
    ytd_prev = _ytd_sum(latest["year"] - 1, latest["month"])
    ytd_yoy = (round((ytd_cur - ytd_prev) / ytd_prev * 100, 2)
               if (ytd_cur is not None and ytd_prev) else None)

    return {
        "ticker": ticker, "months": months, "ok": True,
        "latest": latest,
        "ytd": {"accumulated": ytd_cur,
                "last_year_accumulated": ytd_prev,
                "yoy_pct": ytd_yoy},
        "rows": last_n,
    }


def _build_income_row(date: str, types: dict[str, float]) -> dict:
    rev   = types.get("Revenue")
    gp    = types.get("GrossProfit")
    op    = types.get("OperatingIncome")
    nit   = types.get("IncomeAfterTaxes")
    eps   = types.get("EPS")
    def _pct(num, den):
        return round(num / den * 100, 2) if num is not None and den else None
    return {
        "date":                  date,
        "revenue":               rev,
        "gross_profit":          gp,
        "operating_income":      op,
        "net_income":            nit,
        "eps":                   eps,
        "gross_margin_pct":      _pct(gp,  rev),
        "operating_margin_pct":  _pct(op,  rev),
        "net_margin_pct":        _pct(nit, rev),
    }


def _build_balance_row(date: str, types: dict[str, float]) -> dict:
    ta    = types.get("TotalAssets")
    ca    = types.get("CurrentAssets")
    cash  = types.get("CashAndCashEquivalents")
    tl    = types.get("Liabilities")
    cl    = types.get("CurrentLiabilities")
    ncl   = types.get("NoncurrentLiabilities")
    eq    = types.get("EquityAttributableToOwnersOfParent")
    if eq is None:
        eq = types.get("Equity")
    def _ratio(num, den):
        return round(num / den, 4) if num is not None and den else None
    def _pct(num, den):
        return round(num / den * 100, 2) if num is not None and den else None
    return {
        "date":                date,
        "total_assets":        ta,
        "current_assets":      ca,
        "cash":                cash,
        "total_liabilities":   tl,
        "current_liabilities": cl,
        "long_term_liabilities": ncl,
        "equity":              eq,
        "current_ratio":       _ratio(ca, cl),
        "debt_ratio_pct":      _pct(tl, ta),
        "equity_ratio_pct":    _pct(eq, ta),
    }


def _build_cashflow_row(date: str, types: dict[str, float]) -> dict:
    ocf = types.get("CashFlowsFromOperatingActivities")
    if ocf is None:
        ocf = types.get("NetCashInflowFromOperatingActivities")
    icf = types.get("CashProvidedByInvestingActivities")
    fcf = types.get("CashFlowsProvidedFromFinancingActivities")
    free_cf = (ocf + icf) if (ocf is not None and icf is not None) else None
    return {
        "date":           date,
        "operating_cf":   ocf,
        "investing_cf":   icf,
        "financing_cf":   fcf,
        "free_cash_flow": free_cf,
    }


_FINANCIAL_BUILDER = {
    "income":   _build_income_row,
    "balance":  _build_balance_row,
    "cashflow": _build_cashflow_row,
}


@router.get("/stocks/{ticker}/financial")
def stock_financial(ticker: str, statement: str = "income", quarters: int = 12):
    """個股財報(三表三選一)。statement ∈ {income, balance, cashflow}。"""
    ticker = ticker.upper()
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if statement not in _FINANCIAL_BUILDER:
        raise HTTPException(status_code=400, detail="statement must be income | balance | cashflow")
    if quarters < 1 or quarters > 20:
        raise HTTPException(status_code=400, detail="quarters must be 1..20")

    report_type = "cash_flow" if statement == "cashflow" else statement
    fetched = fetch_stock_financial(ticker, report_type)

    since_date = (datetime.now(timezone.utc).date() - timedelta(days=quarters * 100)).isoformat()
    long_rows = get_financial_quarterly_range(ticker, report_type, since_date)

    if not long_rows:
        return {"ticker": ticker, "statement": statement, "quarters": quarters,
                "ok": fetched, "rows": [], "annual_summary": None}

    by_date: dict[str, dict[str, float]] = {}
    for r in long_rows:
        by_date.setdefault(r["date"], {})[r["type"]] = r["value"]

    builder = _FINANCIAL_BUILDER[statement]
    wide_rows = sorted([builder(d, types) for d, types in by_date.items()],
                       key=lambda r: r["date"])
    last_n = wide_rows[-quarters:]

    annual_summary = None
    if statement == "income" and len(wide_rows) >= 8:
        last4 = wide_rows[-4:]
        prev4 = wide_rows[-8:-4]
        def _sum(rows: list[dict], key: str) -> float | None:
            vals = [r.get(key) for r in rows if r.get(key) is not None]
            return sum(vals) if vals else None
        cur_eps = _sum(last4, "eps");      prev_eps = _sum(prev4, "eps")
        cur_rev = _sum(last4, "revenue");  prev_rev = _sum(prev4, "revenue")
        annual_summary = {
            "current_4q":  {"eps": cur_eps,  "revenue": cur_rev},
            "previous_4q": {"eps": prev_eps, "revenue": prev_rev},
            "eps_yoy_pct":     round((cur_eps - prev_eps) / prev_eps * 100, 2) if (cur_eps is not None and prev_eps) else None,
            "revenue_yoy_pct": round((cur_rev - prev_rev) / prev_rev * 100, 2) if (cur_rev is not None and prev_rev) else None,
        }

    return {
        "ticker": ticker, "statement": statement, "quarters": quarters,
        "ok": True, "rows": last_n,
        "annual_summary": annual_summary,
    }


def _aggregate_dividend_by_calendar_year(rows: list[dict]) -> dict[int, dict]:
    """股利資料按 ROC 年(year 字串前綴 e.g. "114年第3季")推斷西元年,合計現金/股票股利。"""
    by_year: dict[int, dict] = {}
    for r in rows:
        y_str = r.get("year") or ""
        m = re.match(r"^(\d{2,3})年", y_str)
        if not m:
            continue
        roc_year = int(m.group(1))
        ce_year = roc_year + 1911
        bucket = by_year.setdefault(ce_year, {
            "year": ce_year, "cash_dividend": 0.0, "stock_dividend": 0.0,
            "cash_ex_date": None, "cash_payment_date": None,
        })
        bucket["cash_dividend"]  += float(r.get("cash_dividend")  or 0)
        bucket["stock_dividend"] += float(r.get("stock_dividend") or 0)
        ex = r.get("cash_ex_date")
        if ex and (bucket["cash_ex_date"] is None or ex > bucket["cash_ex_date"]):
            bucket["cash_ex_date"] = ex
            bucket["cash_payment_date"] = r.get("cash_payment_date")
    return by_year


def _annual_eps_sum(ticker: str, year: int) -> float | None:
    """回傳該西元年 EPS 合計(可能是 partial-year — 例:當年只發了 Q1+Q2 報表)。
    若 DB 中該年完全沒 EPS 資料,回 None;否則回現有季度 EPS 加總(可能 < 4 季)。
    呼叫方需注意此值在年中可能不是完整年度 EPS。
    """
    rows = get_financial_quarterly_range(ticker, "income", f"{year}-01-01")
    eps_by_date: dict[str, float] = {}
    for r in rows:
        if r["type"] == "EPS" and r["date"].startswith(str(year)):
            eps_by_date[r["date"]] = r["value"]
    if not eps_by_date:
        return None
    return round(sum(eps_by_date.values()), 4)


@router.get("/stocks/{ticker}/dividend")
def stock_dividend(ticker: str, years: int = 10):
    """個股股利歷史:按西元年合計現金/股票股利,加配發率。"""
    ticker = ticker.upper()
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if years < 1 or years > 30:
        raise HTTPException(status_code=400, detail="years must be 1..30")

    fetched = fetch_stock_dividend(ticker)
    raw_rows = get_dividend_history(ticker)

    if not raw_rows:
        return {"ticker": ticker, "years": years, "ok": fetched,
                "summary": None, "rows": []}

    by_year = _aggregate_dividend_by_calendar_year(raw_rows)

    rows_with_ratio = []
    cutoff_year = datetime.now(timezone.utc).year - years
    for ce_year, b in sorted(by_year.items()):
        if ce_year < cutoff_year:
            continue
        eps_sum = _annual_eps_sum(ticker, ce_year)
        payout = (round(b["cash_dividend"] / eps_sum * 100, 2)
                  if eps_sum and eps_sum != 0 else None)
        rows_with_ratio.append({
            "year":             ce_year,
            "cash_dividend":    round(b["cash_dividend"], 4),
            "stock_dividend":   round(b["stock_dividend"], 4),
            "cash_ex_date":     b["cash_ex_date"],
            "cash_payment_date":b["cash_payment_date"],
            "payout_ratio_pct": payout,
            "dividend_yield_pct": None,
        })

    payouts = [r["payout_ratio_pct"] for r in rows_with_ratio if r["payout_ratio_pct"] is not None]
    summary = {
        "avg_payout_ratio_pct": round(sum(payouts) / len(payouts), 2) if payouts else None,
        "avg_dividend_yield_pct": None,
    }

    return {"ticker": ticker, "years": years, "ok": True,
            "summary": summary, "rows": rows_with_ratio}
```

- [ ] **Step 2: Update `app.py`**

In `stock/dashboard/backend/app.py`:

1. Delete the `@app.get("/api/stocks/{ticker}/valuation")` block.
2. Delete the `@app.get("/api/stocks/{ticker}/revenue")` block.
3. Delete the 5 helpers: `_build_income_row`, `_build_balance_row`, `_build_cashflow_row`, `_aggregate_dividend_by_calendar_year`, `_annual_eps_sum`.
4. Delete the `_FINANCIAL_BUILDER` dict.
5. Delete the `@app.get("/api/stocks/{ticker}/financial")` block.
6. Delete the `@app.get("/api/stocks/{ticker}/dividend")` block.
7. Add import: `from api.routes import fundamentals` (with the existing route imports).
8. Add `app.include_router(fundamentals.router)` after the `stocks` include.
9. Trim now-orphaned imports in `app.py`:
   - `import re` — remove if no other endpoint uses it (alerts route uses it but it's still in app.py for now; check after deleting helpers; if `re` no longer appears outside imports, remove)
   - `fetch_stock_per`, `fetch_stock_revenue`, `fetch_stock_financial`, `fetch_stock_dividend`, `fundamentals_to_finmind_id` — remove from app.py imports
   - `get_per_daily_range`, `get_revenue_monthly_range`, `get_financial_quarterly_range`, `get_dividend_history` — remove from `from db import (...)` block in app.py

- [ ] **Step 3: Run full suite + smoke**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from app import app
paths = [r.path for r in app.routes]
expected = ['/api/stocks/{ticker}/valuation', '/api/stocks/{ticker}/revenue',
            '/api/stocks/{ticker}/financial', '/api/stocks/{ticker}/dividend']
for p in expected:
    assert p in paths, f'missing: {p}'
print('ok')
"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/api/routes/fundamentals.py stock/dashboard/backend/app.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): extract routes/fundamentals.py (BE-C-T5)

4 endpoints (valuation, revenue, financial, dividend) and their 5
private view helpers + _FINANCIAL_BUILDER dispatch dict moved into
api/routes/fundamentals.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6 (BE-C-T6): `routes/alerts.py` (4 endpoints)

**Files:**
- Create: `stock/dashboard/backend/api/routes/alerts.py`
- Modify: `stock/dashboard/backend/app.py`

- [ ] **Step 1: Create `api/routes/alerts.py`**

```python
"""Alert routes: list, create, delete, toggle."""
from fastapi import APIRouter, HTTPException

from api._constants import INDICATOR_NAMES
from api.schemas.alerts import AlertRequest, AlertToggleRequest
from repositories.alerts import (
    add_alert, delete_alert, list_alerts, set_alert_enabled,
)
from fetchers.fundamentals_stock import to_finmind_id as fundamentals_to_finmind_id

router = APIRouter(prefix="/api", tags=["alerts"])


VALID_TARGET_TYPES = {"indicator", "stock", "stock_indicator"}
VALID_CONDITIONS = {
    "above", "below",
    "streak_above", "streak_below",
    "percentile_above", "percentile_below",
    "yoy_above", "yoy_below",
}
STOCK_DAILY_INDICATOR_KEYS = {
    "per", "pbr", "dividend_yield",
    "foreign_net", "trust_net", "dealer_net",
    "margin_balance", "short_balance",
}
STOCK_MONTHLY_INDICATOR_KEYS = {"revenue"}
STOCK_QUARTERLY_INDICATOR_KEYS = {
    "q_eps", "q_revenue", "q_operating_income",
    "q_net_income", "q_operating_cf",
}
STOCK_YEARLY_INDICATOR_KEYS = {"y_cash_dividend", "y_stock_dividend"}
STOCK_YOY_COMPATIBLE_KEYS = (
    STOCK_MONTHLY_INDICATOR_KEYS
    | STOCK_QUARTERLY_INDICATOR_KEYS
    | STOCK_YEARLY_INDICATOR_KEYS
)
STOCK_INDICATOR_KEYS = STOCK_DAILY_INDICATOR_KEYS | STOCK_YOY_COMPATIBLE_KEYS
PERCENTILE_DAILY_KEYS = {"per", "pbr", "dividend_yield"}


@router.get("/alerts")
def get_alerts():
    return list_alerts()


@router.post("/alerts")
def create_alert(req: AlertRequest):
    if req.target_type not in VALID_TARGET_TYPES:
        raise HTTPException(status_code=400, detail="Invalid target_type")
    if req.condition not in VALID_CONDITIONS:
        raise HTTPException(status_code=400, detail="Invalid condition")

    is_streak = req.condition.startswith("streak_")
    if is_streak:
        if req.window_n is None:
            raise HTTPException(status_code=400, detail="streak condition requires window_n")
        if req.window_n < 2 or req.window_n > 30:
            raise HTTPException(status_code=400, detail="window_n must be 2..30")

    is_percentile = req.condition.startswith("percentile_")
    is_yoy = req.condition.startswith("yoy_")
    if is_percentile and (req.threshold < 0 or req.threshold > 100):
        raise HTTPException(status_code=400, detail="percentile threshold must be 0..100")

    if req.target_type == "indicator":
        if req.target not in INDICATOR_NAMES:
            raise HTTPException(status_code=400, detail="Unknown indicator")
        target = req.target
    elif req.target_type == "stock_indicator":
        if not req.indicator_key:
            raise HTTPException(status_code=400, detail="stock_indicator requires indicator_key")
        if req.indicator_key not in STOCK_INDICATOR_KEYS:
            raise HTTPException(status_code=400, detail="Unknown indicator_key")
        if fundamentals_to_finmind_id(req.target) is None:
            raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) supported")
        # 交叉驗證:percentile 只支援 daily;yoy 只支援 monthly
        if is_percentile and req.indicator_key not in PERCENTILE_DAILY_KEYS:
            raise HTTPException(
                status_code=400,
                detail="percentile condition requires daily indicator (per/pbr/dividend_yield)"
            )
        if is_yoy and req.indicator_key not in STOCK_YOY_COMPATIBLE_KEYS:
            raise HTTPException(
                status_code=400,
                detail="yoy condition requires monthly/quarterly/yearly indicator"
            )
        target = req.target.upper()
    else:  # stock
        target = req.target.upper()

    alert_id = add_alert(req.target_type, target, req.condition, req.threshold,
                         indicator_key=req.indicator_key, window_n=req.window_n)
    return {"id": alert_id}


@router.delete("/alerts/{alert_id}")
def remove_alert(alert_id: int):
    delete_alert(alert_id)
    return {"ok": True}


@router.patch("/alerts/{alert_id}")
def toggle_alert(alert_id: int, req: AlertToggleRequest):
    set_alert_enabled(alert_id, req.enabled)
    return {"ok": True}
```

- [ ] **Step 2: Update `app.py`**

In `stock/dashboard/backend/app.py`:

1. Delete the 8 module-level constants (`VALID_TARGET_TYPES`, `VALID_CONDITIONS`, `STOCK_DAILY_INDICATOR_KEYS`, `STOCK_MONTHLY_INDICATOR_KEYS`, `STOCK_QUARTERLY_INDICATOR_KEYS`, `STOCK_YEARLY_INDICATOR_KEYS`, `STOCK_YOY_COMPATIBLE_KEYS`, `STOCK_INDICATOR_KEYS`, `PERCENTILE_DAILY_KEYS`).
2. Delete the 4 alert endpoint blocks (`get_alerts`, `create_alert`, `remove_alert`, `toggle_alert`).
3. Add import: `from api.routes import alerts as alerts_routes` (alias to avoid colliding with `backend/alerts.py` thin re-export module).

   **Important:** The existing `backend/alerts.py` (BE-B thin re-export) is in scope; without aliasing, `from api.routes import alerts` would shadow it. Use `as alerts_routes` here.

4. Add `app.include_router(alerts_routes.router)` after the `fundamentals` include.
5. Trim orphan imports:
   - `from api.schemas.alerts import AlertRequest, AlertToggleRequest` — remove from app.py
   - `list_alerts, add_alert, delete_alert, set_alert_enabled` — remove from `from db import (...)` block in app.py
   - `fundamentals_to_finmind_id` — remove if no other route in app.py uses it (only fundamentals routes did, all extracted in T5; but stock_chip in T4 used `chip_to_finmind_id` not `fundamentals_to_finmind_id`. Confirm and remove)

- [ ] **Step 3: Run full suite + smoke**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from app import app
paths = [r.path for r in app.routes]
expected = ['/api/alerts', '/api/alerts/{alert_id}']
for p in expected:
    assert p in paths, f'missing: {p}'
print('ok')
"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/api/routes/alerts.py stock/dashboard/backend/app.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): extract routes/alerts.py (BE-C-T6)

4 alert endpoints + alert validation constants (VALID_TARGET_TYPES
etc.) moved into api/routes/alerts.py. Imports aliased as
alerts_routes in app.py to avoid clashing with backend/alerts.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7 (BE-C-T7): `routes/news.py` (1 endpoint)

**Files:**
- Create: `stock/dashboard/backend/api/routes/news.py`
- Modify: `stock/dashboard/backend/app.py`

- [ ] **Step 1: Create `api/routes/news.py`**

```python
"""News feed routes."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["news"])


@router.get("/news")
def get_news(limit: int = 15):
    from fetchers.news import get_cached_news
    return get_cached_news()[:limit]
```

(Keeps the lazy `from fetchers.news import get_cached_news` style from the original — defers the heavy fetcher import.)

- [ ] **Step 2: Update `app.py`**

In `stock/dashboard/backend/app.py`:

1. Delete the `@app.get("/api/news")` block (`def get_news(limit: int = 15):`).
2. Add import: `from api.routes import news`.
3. Add `app.include_router(news.router)` after the `alerts_routes` include.

- [ ] **Step 3: Run full suite + smoke**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from app import app
paths = [r.path for r in app.routes]
assert '/api/news' in paths
print('ok')
"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/api/routes/news.py stock/dashboard/backend/app.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): extract routes/news.py (BE-C-T7)

Final route extraction. app.py no longer defines any inline endpoints.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8 (BE-C-T8): Add exception handler + replace last `print` + verify shape

**Files:**
- Modify: `stock/dashboard/backend/app.py`

After T1-T7, `app.py` has only: imports, `app = FastAPI(...)`, CORS middleware, 5 `app.include_router(...)`, and the `@app.on_event("startup")` hook with a `print` for the scheduler import error. T8 adds the exception handler and converts the print to a logger call.

- [ ] **Step 1: Final `app.py` content**

Replace the entire `stock/dashboard/backend/app.py` file with this canonical content:

```python
"""Stock Dashboard FastAPI application."""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import indicators, stocks, fundamentals, news
from api.routes import alerts as alerts_routes
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
app.include_router(alerts_routes.router)
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

- [ ] **Step 2: Verify file size**

```bash
wc -l /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/app.py
```

Expected: ≤ 60 lines.

- [ ] **Step 3: Run full suite + smoke**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from app import app
print('routes:', sorted({r.path for r in app.routes if r.path.startswith('/api')}))
print('startup_handlers:', len(app.router.on_startup))
print('exception_handlers count:', len(app.exception_handlers))
print('ok')
"
```

Expected output: roughly 17 distinct `/api/...` paths (FastAPI deduplicates), 1 startup handler, exception_handlers includes the StockDashboardError handler.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/app.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add exception handler + canonical app.py shape (BE-C-T8)

app.py now ≤ 60 lines: FastAPI assembly, CORS, 5 routers, exception
handler mapping StockDashboardError → HTTP, startup hook with logger
(replaces the last surviving print "[app] scheduler not available
yet"). Exception handler is scaffolding — Phase 3 fetcher errors and
Phase 4 auth errors will surface through it automatically.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9 (BE-C-T9): Rename `app.py` → `main.py` + update tests + update systemd

**Files:**
- Rename: `stock/dashboard/backend/app.py` → `stock/dashboard/backend/main.py`
- Modify: `stock/dashboard/tests/test_api.py` (1 line)
- Modify: `stock/dashboard/tests/test_brokers.py` (1 line)
- Modify: `stock/dashboard/tests/test_chip.py` (1 line)
- Modify: `stock/dashboard/tests/test_fundamentals.py` (1 line)
- Modify: `stock/dashboard/stock-dashboard.service` (1 line)

- [ ] **Step 1: Rename the file**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && git mv app.py main.py
```

- [ ] **Step 2: Update test imports**

In each of the 4 test files, replace `from app import app` with `from main import app`:

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/tests
sed -i.bak 's/^from app import app/from main import app/' test_api.py test_brokers.py test_chip.py test_fundamentals.py
rm -f test_api.py.bak test_brokers.py.bak test_chip.py.bak test_fundamentals.py.bak
```

(macOS `sed -i.bak` requires the `.bak` suffix; the `rm -f` cleanup deletes the backups. On Linux you can use `sed -i ''`.)

Verify:

```bash
grep -n "^from app import app\|^from main import app" /Users/paulwu/Documents/Github/tools/stock/dashboard/tests/test_*.py
```

Expected: 4 lines, all `from main import app`. No `from app import app` remains.

- [ ] **Step 3: Update systemd service file**

Edit `stock/dashboard/stock-dashboard.service` line 9:

Old:
```
ExecStart=/opt/stock-dashboard/backend/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```

New:
```
ExecStart=/opt/stock-dashboard/backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

- [ ] **Step 4: Smoke import**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "from main import app; print('routes:', len([r for r in app.routes if r.path.startswith('/api')]))"
```

Expected: prints something like `routes: 18` (FastAPI route count includes method variants — exact number may differ; non-zero means OK).

- [ ] **Step 5: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`.

- [ ] **Step 6: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/main.py stock/dashboard/tests/test_api.py stock/dashboard/tests/test_brokers.py stock/dashboard/tests/test_chip.py stock/dashboard/tests/test_fundamentals.py stock/dashboard/stock-dashboard.service && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): rename app.py → main.py + update deploy + tests (BE-C-T9)

- backend/app.py → backend/main.py (git mv preserves history)
- 4 tests/test_*.py: from app import app → from main import app
- stock-dashboard.service: ExecStart uvicorn app:app → main:app

Atomic switch: deploy + tests + import path all flip in one commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Note: `git mv` should record the file as a rename in `git show --stat`. Verify with:

```bash
git show --stat HEAD | head -10
```

Expected: shows `stock/dashboard/backend/{app.py => main.py}` (rename), other files modified.

---

### Task 10 (BE-C-T10): Final verification

**Files:**
- Inspect only.

- [ ] **Step 1: File structure check**

```bash
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/routes/
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/schemas/
[ -f /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/main.py ] && echo "main.py: YES"
[ -f /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/app.py ] && echo "app.py: STILL EXISTS (BAD)" || echo "app.py: gone (good)"
```

Expected:
- `api/`: `__init__.py`, `_constants.py`, `routes/`, `schemas/` (and `__pycache__/`)
- `api/routes/`: `__init__.py`, `alerts.py`, `fundamentals.py`, `indicators.py`, `news.py`, `stocks.py`
- `api/schemas/`: `__init__.py`, `alerts.py`, `stocks.py`
- `main.py: YES`, `app.py: gone (good)`

- [ ] **Step 2: Size check**

```bash
wc -l /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/main.py /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/_constants.py /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/schemas/*.py /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/routes/*.py
```

Expected:
- `main.py` ≤ 60 lines
- `_constants.py` ~25 lines
- `schemas/stocks.py` ~5 lines, `schemas/alerts.py` ~15 lines
- `routes/indicators.py` ~80 lines, `routes/stocks.py` ~110 lines, `routes/fundamentals.py` ~250 lines, `routes/alerts.py` ~110 lines, `routes/news.py` ~10 lines

- [ ] **Step 3: No `from app import` left in repo**

```bash
grep -rn "^from app import\|^import app$" /Users/paulwu/Documents/Github/tools/stock/dashboard/ 2>/dev/null | grep -v __pycache__
```

Expected: zero matches.

- [ ] **Step 4: Service file points to main:app**

```bash
grep "ExecStart" /Users/paulwu/Documents/Github/tools/stock/dashboard/stock-dashboard.service
```

Expected: line ends with `main:app --host 127.0.0.1 --port 8000`.

- [ ] **Step 5: Routes register on `main.app`**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from main import app
paths = sorted({r.path for r in app.routes if r.path.startswith('/api')})
print('count:', len(paths))
for p in paths:
    print(' ', p)
"
```

Expected: 17 distinct `/api/...` paths printed (the 18 endpoints share some paths between methods, e.g. POST and GET on `/api/stocks`).

- [ ] **Step 6: Full suite final run**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed, 3 warnings`.

- [ ] **Step 7: Branch log inspection**

```bash
cd /Users/paulwu/Documents/Github/tools && git log --oneline master..HEAD
```

Expected (in reverse chronological order):

```
… BE-C-T9
… BE-C-T8
… BE-C-T7
… BE-C-T6
… BE-C-T5
… BE-C-T4
… BE-C-T3
… BE-C-T2
… BE-C-T1
```

(9 commits if T1-T9 all produced commits.)

- [ ] **Step 8: No commit needed**

This task is read-only verification. Nothing to commit.

---

## Spec Coverage Self-Check

| Spec section | Task |
|---|---|
| §1 Target file structure | T1 (api/), T2 (schemas/), T3-T7 (routes/), T9 (main.py) |
| §2 Endpoint → router mapping (5 routers) | T3 (indicators), T4 (stocks), T5 (fundamentals), T6 (alerts), T7 (news) |
| §3 Schemas (AddStockRequest, AlertRequest, AlertToggleRequest) | T2 |
| §4 Constants (RANGE_DELTAS, INDICATOR_NAMES) | T1 |
| §5 main.py exception handler + startup logger | T8 (added on app.py) + T9 (rename) |
| §6 Migration order (10 tasks) | T1–T10 (mapped 1:1) |
| §7 Backward compat (`from db import …`, `import alerts as alerts_module`, `python backfill.py`) | Untouched throughout BE-C |
| §8 Risks (rename, route duplicates, etc.) | T9 atomic commit; per-task `app.include_router` + delete inline; T1 grep verification |
| §9 Acceptance: `api/routes/` 5 files + `api/schemas/` 2 files + `main.py` ≤ 60 lines + `app.py` gone | T10 |

All sections covered.

---

## Execution Notes

- **Branch strategy**: per CONVENTIONS.md §5.3, large refactors get a feature branch. Recommended: `git checkout -b feat/be-c-api-layer` from master before T1, merge `--no-ff` after T10 passes. (Same pattern as MIGR / BE-A / BE-B.)
- **Total tasks**: 10 (T1-T10). 9 commits (T10 is verification, no commit).
- **Estimated time**: 5-15 minutes per task; ~1.5-2 hours total. T5 (fundamentals) is the largest at ~250 lines copied — budget 20 minutes for careful copy + verify.
- **No new dependencies**.
- **Each task ends green** with the suite reporting `5 failed, 128 passed`.
- **Deploy timing**: after T10 verification + merge to master + push. The deploy workflow re-syncs `backend/`, including the new `api/` package and the deleted `app.py`. The `stock-dashboard.service` change triggers the workflow's path filter (verified — `stock/dashboard/stock-dashboard.service` is in the `paths:` list). systemd restart picks up the new `main:app` ExecStart.

## Future-phase Notes (do not implement here)

- **Phase 3 (REG-)** will refactor fetchers to conform to `Fetcher` Protocol; introduce alert indicator registry. Fetchers will start raising `FetcherError`, which the BE-C exception handler then maps to HTTP 502 automatically.
- **Phase 4 (AUTH-)** will add `api/dependencies.py` with `verify_token`; protect endpoints with `Depends(verify_token)`. AuthError will map to HTTP 401 via the BE-C exception handler.
- **After Phase 5 (FE-)**: with the React frontend live, consider deleting the `db/__init__.py` re-export block and the thin `alerts.py` re-export module if all callers have migrated to direct imports.
