# Stock Dashboard 基本面 Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 補上 6 個 FinMind 免費基本面 dataset(PER/PBR/殖利率、月營收、損益表、資產負債表、現金流量表、股利),個股頁加 6 張 c 版完整深度 cards,涵蓋抓 → 存 → API 衍生計算 → UI 顯示。

**Architecture:** 沿用 Phase 1 籌碼面的「lazy fetch + DB cache + 卡片式 UI」模式。新增單一 `fundamentals_stock.py` fetcher 模組(含 4 個 fetcher 函式)、4 張新 DB 表(per_daily / revenue_monthly / financial_quarterly / dividend_history)、4 個 REST endpoint(`/valuation`, `/revenue`, `/financial`, `/dividend`)、6 張獨立 UI cards。財報三表合併存 `stock_financial_quarterly`(以 `report_type` 欄區分,因為 type 命名衝突)。衍生指標(YoY、毛利率、配發率、5y 百分位等)在 API 層計算,不存進 DB。

**Tech Stack:** Python 3 / FastAPI / SQLite / requests / Chart.js / pytest / FinMind REST API v4

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `stock/dashboard/backend/fetchers/fundamentals_stock.py` | **Create** | 4 個 fetcher 函式 + 4 個 parse 函式 + 共用 `_request` / `to_finmind_id` / lazy fetch 框架 |
| `stock/dashboard/backend/db.py` | Modify | 加 4 張新表(`stock_per_daily` / `stock_revenue_monthly` / `stock_financial_quarterly` / `stock_dividend_history`)+ 對應 helpers + `purge_old_data` 擴充 |
| `stock/dashboard/backend/app.py` | Modify | 加 4 個 endpoint(`/valuation` / `/revenue` / `/financial` / `/dividend`)+ 衍生計算 helper functions |
| `stock/dashboard/frontend/stock.html` | Modify | 加 6 張獨立 cards(估值快照 / 月營收 / 損益 / 資產負債 / 現金流 / 股利)+ 對應 JS load 函式 + Chart.js 渲染 |
| `stock/dashboard/tests/test_fundamentals.py` | **Create** | parse 函式 unit tests + endpoint integration tests(mock fetch)|

---

## Task 1: DB schema + parse 函式骨架

**目標:** 建立 4 張新表 + db helpers + `fundamentals_stock.py` 共用骨架(`_request` / `to_finmind_id`)+ 4 個 parse 函式(純函式,容易單元測試)。

**Files:**
- Create: `stock/dashboard/backend/fetchers/fundamentals_stock.py`
- Create: `stock/dashboard/tests/test_fundamentals.py`
- Modify: `stock/dashboard/backend/db.py`

### Step 1.1: db.py 加 4 張新表

**File:** `stock/dashboard/backend/db.py`

- [ ] 在 `init_db()` 函式的 `executescript("""...""")` 字串內,在現有 `stock_chip_daily` 區塊之後,加入 4 張新表:

```sql
            CREATE TABLE IF NOT EXISTS stock_per_daily (
                ticker         TEXT NOT NULL,
                date           TEXT NOT NULL,
                per            REAL,
                pbr            REAL,
                dividend_yield REAL,
                PRIMARY KEY (ticker, date)
            );
            CREATE INDEX IF NOT EXISTS idx_per_ticker_date
                ON stock_per_daily(ticker, date);

            CREATE TABLE IF NOT EXISTS stock_revenue_monthly (
                ticker         TEXT    NOT NULL,
                year           INTEGER NOT NULL,
                month          INTEGER NOT NULL,
                revenue        REAL,
                announced_date TEXT,
                PRIMARY KEY (ticker, year, month)
            );
            CREATE INDEX IF NOT EXISTS idx_revenue_ticker_ym
                ON stock_revenue_monthly(ticker, year, month);

            CREATE TABLE IF NOT EXISTS stock_financial_quarterly (
                ticker      TEXT NOT NULL,
                date        TEXT NOT NULL,
                report_type TEXT NOT NULL,
                type        TEXT NOT NULL,
                value       REAL,
                PRIMARY KEY (ticker, date, report_type, type)
            );
            CREATE INDEX IF NOT EXISTS idx_financial_ticker_date
                ON stock_financial_quarterly(ticker, date, report_type);

            CREATE TABLE IF NOT EXISTS stock_dividend_history (
                ticker             TEXT NOT NULL,
                year               TEXT NOT NULL,
                cash_dividend      REAL,
                stock_dividend     REAL,
                cash_ex_date       TEXT,
                cash_payment_date  TEXT,
                announcement_date  TEXT,
                PRIMARY KEY (ticker, year)
            );
            CREATE INDEX IF NOT EXISTS idx_dividend_ticker
                ON stock_dividend_history(ticker);
```

- [ ] 在 `purge_old_data` 函式內,加上對 4 張新表的清理:

```python
        conn.execute("DELETE FROM stock_per_daily WHERE date<?", (cutoff_date,))
        conn.execute(
            "DELETE FROM stock_revenue_monthly "
            "WHERE (year * 12 + month) < (? * 12 + ?)",
            (int(cutoff_date[:4]), int(cutoff_date[5:7]))
        )
        conn.execute("DELETE FROM stock_financial_quarterly WHERE date<?", (cutoff_date,))
        # dividend 不 purge(歷史很長很重要)
```

### Step 1.2: db.py 加 helpers

**File:** `stock/dashboard/backend/db.py`(在 `get_latest_chip_date` 之後新增)

```python
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
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT year, cash_dividend, stock_dividend, cash_ex_date, "
            "       cash_payment_date, announcement_date "
            "FROM stock_dividend_history WHERE ticker=? ORDER BY year",
            (ticker,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_dividend_announce_date(ticker: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(announcement_date) AS d FROM stock_dividend_history WHERE ticker=?",
            (ticker,),
        ).fetchone()
        return row["d"] if row and row["d"] else None
```

### Step 1.3: 寫 4 個 parse 失敗測試

**File:** `stock/dashboard/tests/test_fundamentals.py` (new)

```python
"""Fundamentals fetcher tests."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import db
from app import app
from fetchers.fundamentals_stock import (
    parse_per_rows, parse_revenue_rows,
    parse_financial_rows, parse_dividend_rows,
)

client = TestClient(app)


# === PER ===
SAMPLE_PER = [
    {"date": "2026-04-29", "stock_id": "2330",
     "dividend_yield": 1.01, "PER": 32.91, "PBR": 10.43},
    {"date": "2026-04-30", "stock_id": "2330",
     "dividend_yield": 1.03, "PER": 32.23, "PBR": 10.22},
]


def test_parse_per_rows_extracts_three_columns():
    out = parse_per_rows(SAMPLE_PER, ticker="2330.TW")
    assert len(out) == 2
    assert out[0] == {
        "ticker": "2330.TW", "date": "2026-04-29",
        "per": 32.91, "pbr": 10.43, "dividend_yield": 1.01,
    }
    assert out[1]["per"] == 32.23


# === Revenue ===
SAMPLE_REVENUE = [
    {"date": "2026-03-01", "stock_id": "2330",
     "revenue": 317656613000, "revenue_year": 2026, "revenue_month": 2,
     "create_time": "2026-04-21"},
    {"date": "2026-04-01", "stock_id": "2330",
     "revenue": 415191699000, "revenue_year": 2026, "revenue_month": 3,
     "create_time": "2026-04-21"},
]


def test_parse_revenue_rows_extracts_year_month_value():
    out = parse_revenue_rows(SAMPLE_REVENUE, ticker="2330.TW")
    assert len(out) == 2
    first = out[0]
    assert first["ticker"]         == "2330.TW"
    assert first["year"]           == 2026
    assert first["month"]          == 2
    assert first["revenue"]        == 317656613000
    assert first["announced_date"] == "2026-04-21"


# === Financial (one parser handles all three statements via report_type) ===
SAMPLE_INCOME = [
    {"date": "2026-03-31", "stock_id": "2330", "type": "EPS",         "value": 13.98, "origin_name": "EPS"},
    {"date": "2026-03-31", "stock_id": "2330", "type": "Revenue",     "value": 8392000000000, "origin_name": "營業收入"},
    {"date": "2026-03-31", "stock_id": "2330", "type": "GrossProfit", "value": 4123000000000, "origin_name": "毛利"},
]


def test_parse_financial_rows_long_format_with_report_type():
    out = parse_financial_rows(SAMPLE_INCOME, ticker="2330.TW", report_type="income")
    assert len(out) == 3
    assert all(r["ticker"] == "2330.TW" for r in out)
    assert all(r["report_type"] == "income" for r in out)
    assert all(r["date"] == "2026-03-31" for r in out)
    types = {r["type"]: r["value"] for r in out}
    assert types["EPS"] == 13.98
    assert types["Revenue"] == 8392000000000


# === Dividend ===
SAMPLE_DIVIDEND = [
    {"date": "2025-12-17", "stock_id": "2330", "year": "114年第2季",
     "CashEarningsDistribution": 5.00001118, "StockEarningsDistribution": 0.0,
     "CashExDividendTradingDate": "2025-12-11",
     "CashDividendPaymentDate": "2026-01-08",
     "AnnouncementDate": "2025-11-26"},
    {"date": "2026-03-23", "stock_id": "2330", "year": "114年第3季",
     "CashEarningsDistribution": 6.00003573, "StockEarningsDistribution": 0.0,
     "CashExDividendTradingDate": "2026-03-17",
     "CashDividendPaymentDate": "2026-04-09",
     "AnnouncementDate": "2026-03-02"},
]


def test_parse_dividend_rows_picks_relevant_columns():
    out = parse_dividend_rows(SAMPLE_DIVIDEND, ticker="2330.TW")
    assert len(out) == 2
    first = out[0]
    assert first["ticker"]            == "2330.TW"
    assert first["year"]              == "114年第2季"
    assert first["cash_dividend"]     == pytest.approx(5.00001118)
    assert first["stock_dividend"]    == 0.0
    assert first["cash_ex_date"]      == "2025-12-11"
    assert first["cash_payment_date"] == "2026-01-08"
    assert first["announcement_date"] == "2025-11-26"
```

### Step 1.4: Run tests, verify all 4 fail with ImportError

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_fundamentals.py -v
```

Expected: 4 tests FAILED with `ImportError: cannot import name 'parse_per_rows' from 'fetchers.fundamentals_stock'`(模組還不存在).

### Step 1.5: Create fundamentals_stock.py with shared helpers + 4 parse functions

**File:** `stock/dashboard/backend/fetchers/fundamentals_stock.py` (new)

```python
"""個股基本面 fetcher,lazy fetch + DB cache。

從 FinMind 抓 6 個 dataset(全部免費 with data_id):
- TaiwanStockPER (每日 PER/PBR/殖利率) → stock_per_daily
- TaiwanStockMonthRevenue (每月營收) → stock_revenue_monthly
- TaiwanStockFinancialStatements (損益表,每季) → stock_financial_quarterly (report_type='income')
- TaiwanStockBalanceSheet (資產負債表,每季) → stock_financial_quarterly (report_type='balance')
- TaiwanStockCashFlowsStatement (現金流量表,每季) → stock_financial_quarterly (report_type='cash_flow')
- TaiwanStockDividend (股利) → stock_dividend_history

複用 chip_stock.py 模式:lazy fetch + DB cache,失敗 log + return False。
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import (
    save_per_daily_rows, get_latest_per_date,
    save_revenue_monthly_rows, get_latest_revenue_ym,
    save_financial_quarterly_rows, get_latest_financial_date,
    save_dividend_history_rows, get_latest_dividend_announce_date,
)

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()

# 對應 spec 範圍
DEFAULT_PER_LOOKBACK_DAYS = 1825      # 5 年
DEFAULT_REVENUE_LOOKBACK_MONTHS = 36  # 3 年
DEFAULT_FINANCIAL_LOOKBACK_QUARTERS = 12  # 3 年(12 季)
DEFAULT_DIVIDEND_LOOKBACK_YEARS = 10  # 10 年

# Phase 2 三表名 → FinMind dataset name
FINANCIAL_DATASET = {
    "income":    "TaiwanStockFinancialStatements",
    "balance":   "TaiwanStockBalanceSheet",
    "cash_flow": "TaiwanStockCashFlowsStatement",
}


def to_finmind_id(ticker: str) -> str | None:
    """把 watchlist ticker 轉成 FinMind 純數字代碼,非台股回 None。複用 broker.py 邏輯。"""
    t = (ticker or "").upper().strip()
    if t.endswith(".TW"):
        return t[:-3]
    if t.endswith(".TWO"):
        return t[:-4]
    if t.isdigit():
        return t
    return None


def _request(dataset: str, stock_id: str, start_date: str, end_date: str | None = None) -> list[dict]:
    params = {"dataset": dataset, "data_id": stock_id, "start_date": start_date}
    if end_date:
        params["end_date"] = end_date
    headers = {}
    if FINMIND_TOKEN:
        headers["Authorization"] = f"Bearer {FINMIND_TOKEN}"
    r = requests.get(FINMIND_URL, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") not in (200, None):
        raise RuntimeError(f"FinMind {dataset} error: {payload.get('msg') or payload}")
    return payload.get("data") or []


# === Parsers (pure functions, easy to unit-test) ===

def parse_per_rows(rows: list[dict], ticker: str) -> list[dict]:
    """TaiwanStockPER → list of {ticker, date, per, pbr, dividend_yield}."""
    out: list[dict] = []
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        out.append({
            "ticker":         ticker,
            "date":           d,
            "per":            float(r["PER"]) if r.get("PER") is not None else None,
            "pbr":            float(r["PBR"]) if r.get("PBR") is not None else None,
            "dividend_yield": float(r["dividend_yield"]) if r.get("dividend_yield") is not None else None,
        })
    return out


def parse_revenue_rows(rows: list[dict], ticker: str) -> list[dict]:
    """TaiwanStockMonthRevenue → list of {ticker, year, month, revenue, announced_date}."""
    out: list[dict] = []
    for r in rows:
        y, m = r.get("revenue_year"), r.get("revenue_month")
        if y is None or m is None:
            continue
        out.append({
            "ticker":         ticker,
            "year":           int(y),
            "month":          int(m),
            "revenue":        float(r["revenue"]) if r.get("revenue") is not None else None,
            "announced_date": r.get("create_time") or "",
        })
    return out


def parse_financial_rows(rows: list[dict], ticker: str, report_type: str) -> list[dict]:
    """三表共用 long-format parser。

    rows 形如 {date, stock_id, type, value, origin_name},直接展開為 DB 列。
    """
    out: list[dict] = []
    for r in rows:
        d, t = r.get("date"), r.get("type")
        if not d or not t:
            continue
        out.append({
            "ticker":      ticker,
            "date":        d,
            "report_type": report_type,
            "type":        t,
            "value":       float(r["value"]) if r.get("value") is not None else None,
        })
    return out


def parse_dividend_rows(rows: list[dict], ticker: str) -> list[dict]:
    """TaiwanStockDividend → list of {ticker, year, cash_dividend, stock_dividend,
    cash_ex_date, cash_payment_date, announcement_date}."""
    out: list[dict] = []
    for r in rows:
        y = r.get("year")
        if not y:
            continue
        out.append({
            "ticker":            ticker,
            "year":              y,
            "cash_dividend":     float(r["CashEarningsDistribution"])  if r.get("CashEarningsDistribution")  is not None else None,
            "stock_dividend":    float(r["StockEarningsDistribution"]) if r.get("StockEarningsDistribution") is not None else None,
            "cash_ex_date":      r.get("CashExDividendTradingDate") or None,
            "cash_payment_date": r.get("CashDividendPaymentDate") or None,
            "announcement_date": r.get("AnnouncementDate") or None,
        })
    return out


# === Fetchers (Task 2 will add the 4 fetch_* functions below) ===
```

註:Task 2 會在文件底部加 `fetch_stock_per` / `fetch_stock_revenue` / `fetch_stock_financial` / `fetch_stock_dividend` 4 個 fetcher。

### Step 1.6: Run tests, verify all 4 pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_fundamentals.py -v
```

Expected: 4 passed.

### Step 1.7: Run full backend regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 既有 42 + 5 pre-existing fail + 4 new pass = 47 passed, 5 failed (pre-existing 不變).

### Step 1.8: Commit

```bash
git add stock/dashboard/backend/db.py \
        stock/dashboard/backend/fetchers/fundamentals_stock.py \
        stock/dashboard/tests/test_fundamentals.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add fundamentals DB schema and parsers (T1)

新增 4 張 DB 表(stock_per_daily / stock_revenue_monthly /
stock_financial_quarterly / stock_dividend_history),對應 db helpers,以及
fetchers/fundamentals_stock.py 骨架(_request、to_finmind_id、4 個 pure
parse 函式)。三表合一 stock_financial_quarterly 用 report_type 欄區分。
T2 將在這之上加 4 個 fetcher 函式與 4 個 API endpoint。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Fetchers + API endpoints + 衍生計算

**目標:** 在 `fundamentals_stock.py` 加 4 個 fetcher 函式(lazy fetch + cache),在 `app.py` 加 4 個 endpoint,衍生計算(YoY、毛利率、配發率、5y 百分位、TTM 等)在 endpoint 層計算。

**Files:**
- Modify: `stock/dashboard/backend/fetchers/fundamentals_stock.py`(append fetchers)
- Modify: `stock/dashboard/backend/app.py`
- Modify: `stock/dashboard/tests/test_fundamentals.py`(append endpoint tests)

### Step 2.1: 寫 endpoint 失敗測試

**File:** `stock/dashboard/tests/test_fundamentals.py`(append)

```python
def _seed_per(ticker: str, rows: list[dict]) -> None:
    db.save_per_daily_rows([{
        "ticker": ticker, "date": r["date"],
        "per": r.get("per"), "pbr": r.get("pbr"),
        "dividend_yield": r.get("dividend_yield"),
    } for r in rows])


def _seed_revenue(ticker: str, rows: list[dict]) -> None:
    db.save_revenue_monthly_rows([{
        "ticker": ticker, "year": r["year"], "month": r["month"],
        "revenue": r.get("revenue"), "announced_date": r.get("announced_date", ""),
    } for r in rows])


def _seed_financial(ticker: str, report_type: str, rows: list[dict]) -> None:
    db.save_financial_quarterly_rows([{
        "ticker": ticker, "date": r["date"],
        "report_type": report_type, "type": r["type"], "value": r.get("value"),
    } for r in rows])


def _seed_dividend(ticker: str, rows: list[dict]) -> None:
    db.save_dividend_history_rows([{
        "ticker": ticker, "year": r["year"],
        "cash_dividend": r.get("cash_dividend"),
        "stock_dividend": r.get("stock_dividend"),
        "cash_ex_date": r.get("cash_ex_date"),
        "cash_payment_date": r.get("cash_payment_date"),
        "announcement_date": r.get("announcement_date"),
    } for r in rows])


def test_valuation_endpoint_returns_latest_and_5y_range():
    db.init_db()
    _seed_per("2330.TW", [
        {"date": "2024-01-02", "per": 20.0, "pbr": 5.0,  "dividend_yield": 2.5},
        {"date": "2024-06-30", "per": 25.0, "pbr": 6.0,  "dividend_yield": 2.0},
        {"date": "2025-06-30", "per": 30.0, "pbr": 8.0,  "dividend_yield": 1.5},
        {"date": "2026-04-30", "per": 32.0, "pbr": 10.0, "dividend_yield": 1.0},
    ])
    with patch("app.fetch_stock_per", return_value=True):
        r = client.get("/api/stocks/2330.TW/valuation?years=5")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "2330.TW"
    assert body["ok"] is True
    assert body["latest"]["per"] == 32.0
    assert body["latest"]["pbr"] == 10.0
    # PER 範圍 [20, 32];32 是最大,百分位 100
    assert body["latest"]["per_percentile_5y"] == pytest.approx(100.0, abs=0.01)
    assert body["range_5y"]["per"]["min"] == 20.0
    assert body["range_5y"]["per"]["max"] == 32.0
    assert len(body["rows"]) == 4


def test_revenue_endpoint_yoy_and_ytd():
    db.init_db()
    _seed_revenue("2330.TW", [
        # 2025 YTD: Jan + Feb = 1000 + 1100 = 2100
        {"year": 2025, "month": 1, "revenue": 1000_000_000_000},
        {"year": 2025, "month": 2, "revenue": 1100_000_000_000},
        {"year": 2025, "month": 3, "revenue": 1200_000_000_000},
        # 2026 YTD: Jan + Feb = 1500 + 1600 = 3100; YoY = 47.6%
        {"year": 2026, "month": 1, "revenue": 1500_000_000_000},
        {"year": 2026, "month": 2, "revenue": 1600_000_000_000},
    ])
    with patch("app.fetch_stock_revenue", return_value=True):
        r = client.get("/api/stocks/2330.TW/revenue?months=12")
    body = r.json()
    assert body["latest"]["year"] == 2026
    assert body["latest"]["month"] == 2
    # YoY: (1600 - 1100) / 1100 = 45.45%
    assert body["latest"]["yoy_pct"] == pytest.approx(45.45, abs=0.05)
    # YTD 2026 (Jan+Feb) = 3100;去年同期 (Jan+Feb 2025) = 2100;YoY = 47.62%
    assert body["ytd"]["accumulated"] == 3100_000_000_000
    assert body["ytd"]["last_year_accumulated"] == 2100_000_000_000
    assert body["ytd"]["yoy_pct"] == pytest.approx(47.62, abs=0.05)


def test_financial_income_endpoint_returns_quarterly_with_ratios():
    db.init_db()
    _seed_financial("2330.TW", "income", [
        {"date": "2026-03-31", "type": "Revenue",         "value": 1000.0},
        {"date": "2026-03-31", "type": "GrossProfit",     "value": 600.0},
        {"date": "2026-03-31", "type": "OperatingIncome", "value": 400.0},
        {"date": "2026-03-31", "type": "IncomeAfterTaxes","value": 300.0},
        {"date": "2026-03-31", "type": "EPS",             "value": 12.5},
    ])
    with patch("app.fetch_stock_financial", return_value=True):
        r = client.get("/api/stocks/2330.TW/financial?statement=income&quarters=4")
    body = r.json()
    assert body["ok"] is True
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["date"] == "2026-03-31"
    assert row["revenue"] == 1000.0
    assert row["gross_profit"] == 600.0
    assert row["eps"] == 12.5
    assert row["gross_margin_pct"]     == pytest.approx(60.0)
    assert row["operating_margin_pct"] == pytest.approx(40.0)
    assert row["net_margin_pct"]       == pytest.approx(30.0)


def test_financial_balance_endpoint_returns_ratios():
    db.init_db()
    _seed_financial("2330.TW", "balance", [
        {"date": "2026-03-31", "type": "TotalAssets",       "value": 5000.0},
        {"date": "2026-03-31", "type": "CurrentAssets",     "value": 2000.0},
        {"date": "2026-03-31", "type": "Liabilities",       "value": 2500.0},
        {"date": "2026-03-31", "type": "CurrentLiabilities","value": 1000.0},
        {"date": "2026-03-31", "type": "EquityAttributableToOwnersOfParent",
         "value": 2500.0},
    ])
    with patch("app.fetch_stock_financial", return_value=True):
        r = client.get("/api/stocks/2330.TW/financial?statement=balance&quarters=4")
    body = r.json()
    row = body["rows"][0]
    assert row["total_assets"]      == 5000.0
    assert row["total_liabilities"] == 2500.0
    assert row["equity"]            == 2500.0
    assert row["current_ratio"]     == pytest.approx(2.0)        # 2000 / 1000
    assert row["debt_ratio_pct"]    == pytest.approx(50.0)       # 2500 / 5000 × 100
    assert row["equity_ratio_pct"]  == pytest.approx(50.0)


def test_financial_cashflow_endpoint_returns_fcf():
    db.init_db()
    _seed_financial("2330.TW", "cash_flow", [
        {"date": "2026-03-31", "type": "CashFlowsFromOperatingActivities",     "value": 800.0},
        {"date": "2026-03-31", "type": "CashProvidedByInvestingActivities",    "value": -300.0},
        {"date": "2026-03-31", "type": "CashFlowsProvidedFromFinancingActivities", "value": -200.0},
    ])
    with patch("app.fetch_stock_financial", return_value=True):
        r = client.get("/api/stocks/2330.TW/financial?statement=cashflow&quarters=4")
    body = r.json()
    row = body["rows"][0]
    assert row["operating_cf"]   == 800.0
    assert row["investing_cf"]   == -300.0
    assert row["financing_cf"]   == -200.0
    assert row["free_cash_flow"] == 500.0  # 800 + (-300)


def test_dividend_endpoint_aggregates_by_calendar_year():
    db.init_db()
    # 兩季屬於 114年(2025),分別 5 + 6 元現金股利
    _seed_dividend("2330.TW", [
        {"year": "114年第2季", "cash_dividend": 5.0, "stock_dividend": 0.0,
         "cash_ex_date": "2025-12-11", "cash_payment_date": "2026-01-08",
         "announcement_date": "2025-11-26"},
        {"year": "114年第3季", "cash_dividend": 6.0, "stock_dividend": 0.0,
         "cash_ex_date": "2026-03-17", "cash_payment_date": "2026-04-09",
         "announcement_date": "2026-03-02"},
    ])
    # 也需要 EPS 資料才能算配發率
    _seed_financial("2330.TW", "income", [
        # 2025 全年 EPS 加總 = 50
        {"date": "2025-03-31", "type": "EPS", "value": 12.0},
        {"date": "2025-06-30", "type": "EPS", "value": 12.5},
        {"date": "2025-09-30", "type": "EPS", "value": 12.5},
        {"date": "2025-12-31", "type": "EPS", "value": 13.0},
    ])
    with patch("app.fetch_stock_dividend", return_value=True):
        r = client.get("/api/stocks/2330.TW/dividend?years=10")
    body = r.json()
    assert body["ok"] is True
    # 應有一年 (2025)
    rows_by_year = {row["year"]: row for row in body["rows"]}
    row = rows_by_year[2025]
    assert row["cash_dividend"]     == 11.0   # 5 + 6
    assert row["stock_dividend"]    == 0.0
    # 配發率 = 11 / 50 = 22.0%
    assert row["payout_ratio_pct"]  == pytest.approx(22.0)


def test_valuation_rejects_non_taiwan_ticker():
    r = client.get("/api/stocks/AAPL/valuation")
    assert r.status_code == 400
```

### Step 2.2: Run, verify all endpoint tests fail

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_fundamentals.py -v
```

Expected: 7 endpoint tests fail with 404 / not implemented;4 parse tests still pass.

### Step 2.3: Append fetchers to fundamentals_stock.py

**File:** `stock/dashboard/backend/fetchers/fundamentals_stock.py`(append after parsers)

```python
# === Fetchers (lazy fetch + DB cache) ===

def fetch_stock_per(ticker: str, lookback_days: int = DEFAULT_PER_LOOKBACK_DAYS) -> bool:
    stock_id = to_finmind_id(ticker)
    if stock_id is None:
        return False

    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest = get_latest_per_date(ticker)
    if latest:
        latest_date = datetime.strptime(latest, "%Y-%m-%d").date()
        if (today - latest_date).days <= 0:
            return True
        start = latest_date + timedelta(days=1)
    else:
        start = today - timedelta(days=lookback_days)
    start_date = start.strftime("%Y-%m-%d")
    if start_date > end_date:
        return True

    try:
        raw = _request("TaiwanStockPER", stock_id, start_date, end_date)
    except Exception as e:
        print(f"[fundamentals] {ticker} PER fetch error: {e}")
        return False

    rows = parse_per_rows(raw, ticker)
    save_per_daily_rows(rows)
    print(f"[fundamentals] {ticker} PER {start_date}~{end_date}: {len(rows)} rows")
    return True


def fetch_stock_revenue(ticker: str, months: int = DEFAULT_REVENUE_LOOKBACK_MONTHS) -> bool:
    stock_id = to_finmind_id(ticker)
    if stock_id is None:
        return False

    today = datetime.now(timezone.utc).astimezone().date()
    latest_ym = get_latest_revenue_ym(ticker)
    if latest_ym:
        # 從 latest_ym 後一個月開始拉
        y, m = latest_ym
        start = datetime(y, m, 1) + timedelta(days=32)
        start = start.replace(day=1)
        # 若 start > today,代表 DB 已最新
        if start.date() > today:
            return True
    else:
        start = today.replace(day=1) - timedelta(days=months * 31)
        start = start.replace(day=1)
    start_date = start.strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    try:
        raw = _request("TaiwanStockMonthRevenue", stock_id, start_date, end_date)
    except Exception as e:
        print(f"[fundamentals] {ticker} revenue fetch error: {e}")
        return False

    rows = parse_revenue_rows(raw, ticker)
    save_revenue_monthly_rows(rows)
    print(f"[fundamentals] {ticker} revenue {start_date}~{end_date}: {len(rows)} rows")
    return True


def fetch_stock_financial(ticker: str, report_type: str,
                          quarters: int = DEFAULT_FINANCIAL_LOOKBACK_QUARTERS) -> bool:
    """fetch 一個 statement (income/balance/cash_flow) 的資料。"""
    stock_id = to_finmind_id(ticker)
    if stock_id is None:
        return False
    dataset = FINANCIAL_DATASET.get(report_type)
    if dataset is None:
        return False

    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest = get_latest_financial_date(ticker, report_type)
    if latest:
        latest_date = datetime.strptime(latest, "%Y-%m-%d").date()
        # 至少 90 天才有可能有新季度
        if (today - latest_date).days < 90:
            return True
        start = latest_date + timedelta(days=1)
    else:
        # 一季 ~ 90 天,quarters * 100 略寬鬆
        start = today - timedelta(days=quarters * 100)
    start_date = start.strftime("%Y-%m-%d")
    if start_date > end_date:
        return True

    try:
        raw = _request(dataset, stock_id, start_date, end_date)
    except Exception as e:
        print(f"[fundamentals] {ticker} financial({report_type}) fetch error: {e}")
        return False

    rows = parse_financial_rows(raw, ticker, report_type)
    save_financial_quarterly_rows(rows)
    print(f"[fundamentals] {ticker} {report_type} {start_date}~{end_date}: {len(rows)} rows")
    return True


def fetch_stock_dividend(ticker: str, years: int = DEFAULT_DIVIDEND_LOOKBACK_YEARS) -> bool:
    stock_id = to_finmind_id(ticker)
    if stock_id is None:
        return False

    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest_announce = get_latest_dividend_announce_date(ticker)
    if latest_announce:
        # 從上次 announcement 後一天開始補拉(輕量 — 股利更新不頻繁)
        latest_date = datetime.strptime(latest_announce, "%Y-%m-%d").date()
        start = latest_date + timedelta(days=1)
        # 但若距今 < 30 天,假設還沒有新的,直接 return
        if (today - latest_date).days < 30:
            return True
    else:
        start = today - timedelta(days=years * 366)
    start_date = start.strftime("%Y-%m-%d")
    if start_date > end_date:
        return True

    try:
        raw = _request("TaiwanStockDividend", stock_id, start_date, end_date)
    except Exception as e:
        print(f"[fundamentals] {ticker} dividend fetch error: {e}")
        return False

    rows = parse_dividend_rows(raw, ticker)
    save_dividend_history_rows(rows)
    print(f"[fundamentals] {ticker} dividend {start_date}~{end_date}: {len(rows)} rows")
    return True
```

### Step 2.4: app.py — add 4 endpoints + derived calc helpers

**File:** `stock/dashboard/backend/app.py`

- [ ] 加入 imports(放在現有 import 區塊):

```python
from db import (
    ...,
    get_per_daily_range,
    get_revenue_monthly_range,
    get_financial_quarterly_range,
    get_dividend_history,
)
from fetchers.fundamentals_stock import (
    fetch_stock_per, fetch_stock_revenue,
    fetch_stock_financial, fetch_stock_dividend,
    to_finmind_id as fundamentals_to_finmind_id,
)
```

- [ ] 在現有 `stock_chip` endpoint 之後新增以下 4 個 endpoint:

```python
@app.get("/api/stocks/{ticker}/valuation")
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

    # PER 5y 百分位:目前值在歷史中的位置(0=最低,100=最高)
    if latest["per"] is not None and pers:
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


@app.get("/api/stocks/{ticker}/revenue")
def stock_revenue(ticker: str, months: int = 36):
    """個股月營收 + YoY + 12MA + YTD vs 去年同期。"""
    ticker = ticker.upper()
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if months < 1 or months > 60:
        raise HTTPException(status_code=400, detail="months must be 1..60")

    fetched = fetch_stock_revenue(ticker)

    today = datetime.now(timezone.utc).date()
    # 為了能算 YoY (要拿前一年同月)+ 12MA (前 11 個月),多撈 14 個月當 buffer
    fetch_back_months = months + 14
    since_year = today.year - (fetch_back_months // 12) - 1
    since_month = ((today.month - (fetch_back_months % 12) - 1) % 12) + 1
    rows = get_revenue_monthly_range(ticker, since_year, since_month)

    if not rows:
        return {"ticker": ticker, "months": months, "ok": fetched,
                "latest": None, "ytd": None, "rows": []}

    # 建 (year, month) → revenue 索引
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

    # YTD: 本年 1 月到 latest.month 累計;去年同期累計
    ytd_cur = sum(by_ym[(latest["year"], m)]
                  for m in range(1, latest["month"] + 1)
                  if (latest["year"], m) in by_ym)
    ytd_prev = sum(by_ym[(latest["year"] - 1, m)]
                   for m in range(1, latest["month"] + 1)
                   if (latest["year"] - 1, m) in by_ym)
    ytd_yoy = round((ytd_cur - ytd_prev) / ytd_prev * 100, 2) if ytd_prev else None

    return {
        "ticker": ticker, "months": months, "ok": True,
        "latest": latest,
        "ytd": {"accumulated": ytd_cur,
                "last_year_accumulated": ytd_prev,
                "yoy_pct": ytd_yoy},
        "rows": last_n,
    }


# 三表名 → wide-row builder (將 long format rows 同 date 聚合為 wide row + 衍生比率)
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
    eq    = types.get("EquityAttributableToOwnersOfParent") or types.get("Equity")
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
    ocf = (types.get("CashFlowsFromOperatingActivities")
           or types.get("NetCashInflowFromOperatingActivities"))
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


@app.get("/api/stocks/{ticker}/financial")
def stock_financial(ticker: str, statement: str = "income", quarters: int = 12):
    """個股財報(三表三選一)。statement ∈ {income, balance, cashflow}。"""
    ticker = ticker.upper()
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if statement not in _FINANCIAL_BUILDER:
        raise HTTPException(status_code=400, detail="statement must be income | balance | cashflow")
    if quarters < 1 or quarters > 20:
        raise HTTPException(status_code=400, detail="quarters must be 1..20")

    # statement → 對應 fetcher 的 report_type(cashflow 在 fetcher 內叫 cash_flow)
    report_type = "cash_flow" if statement == "cashflow" else statement
    fetched = fetch_stock_financial(ticker, report_type)

    since_date = (datetime.now(timezone.utc).date() - timedelta(days=quarters * 100)).isoformat()
    long_rows = get_financial_quarterly_range(ticker, report_type, since_date)

    if not long_rows:
        return {"ticker": ticker, "statement": statement, "quarters": quarters,
                "ok": fetched, "rows": [], "annual_summary": None}

    # long format → 按 date 聚合 type → wide row
    by_date: dict[str, dict[str, float]] = {}
    for r in long_rows:
        by_date.setdefault(r["date"], {})[r["type"]] = r["value"]

    builder = _FINANCIAL_BUILDER[statement]
    wide_rows = sorted([builder(d, types) for d, types in by_date.items()],
                       key=lambda r: r["date"])
    last_n = wide_rows[-quarters:]

    annual_summary = None
    if statement == "income" and len(wide_rows) >= 8:
        # TTM (最近 4 季合計) vs 前 4 季合計
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
    """股利資料按 announcement_date / cash_ex_date 推斷西元年,合計現金/股票股利。"""
    import re
    by_year: dict[int, dict] = {}
    for r in rows:
        # year 字串如 "114年第3季" → ROC 114 = 西元 2025
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
        # 取最近一次除權息日 / 發放日
        ex = r.get("cash_ex_date")
        if ex and (bucket["cash_ex_date"] is None or ex > bucket["cash_ex_date"]):
            bucket["cash_ex_date"] = ex
            bucket["cash_payment_date"] = r.get("cash_payment_date")
    return by_year


def _annual_eps_sum(ticker: str, year: int) -> float | None:
    """回傳該西元年 4 季 EPS 合計;有任一季缺則回 None。"""
    rows = get_financial_quarterly_range(ticker, "income", f"{year}-01-01")
    eps_by_date: dict[str, float] = {}
    for r in rows:
        if r["type"] == "EPS" and r["date"].startswith(str(year)):
            eps_by_date[r["date"]] = r["value"]
    if not eps_by_date:
        return None
    return round(sum(eps_by_date.values()), 4)


@app.get("/api/stocks/{ticker}/dividend")
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

    # 算配發率(該年現金股利合計 / 該年 EPS 合計);殖利率留 null(需要當年均價,目前不存)
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
            "dividend_yield_pct": None,  # 未實作:需要該年均價
        })

    # summary:平均殖利率 / 平均配發率 (skip null)
    payouts = [r["payout_ratio_pct"] for r in rows_with_ratio if r["payout_ratio_pct"] is not None]
    summary = {
        "avg_payout_ratio_pct": round(sum(payouts) / len(payouts), 2) if payouts else None,
        "avg_dividend_yield_pct": None,
    }

    return {"ticker": ticker, "years": years, "ok": True,
            "summary": summary, "rows": rows_with_ratio}
```

### Step 2.5: Run all tests, verify pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_fundamentals.py -v
```

Expected: 11 passed (4 parse + 7 endpoint).

### Step 2.6: Run full backend regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 既有 47 passed → 47 passed,5 pre-existing fail 不變.

### Step 2.7: Commit

```bash
git add stock/dashboard/backend/fetchers/fundamentals_stock.py \
        stock/dashboard/backend/app.py \
        stock/dashboard/tests/test_fundamentals.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add fundamentals fetchers and 4 API endpoints (T2)

新增 4 個 fetcher 函式(fetch_stock_per/revenue/financial/dividend),lazy
fetch + DB cache + delta 邏輯。新增 4 個 endpoint:/valuation(含 5y 百分位)、
/revenue(YoY + 12MA + YTD)、/financial(三表 statement 三選一,含毛利率/
流動比/自由現金流等衍生比率)、/dividend(按西元年合計、配發率)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: UI 估值快照 card

**目標:** 在 stock.html 加估值快照 card,呼叫 `/valuation`,顯示最新 PER/PBR/殖利率 + 5y 百分位 + 3 條走勢 chart。

**Files:**
- Modify: `stock/dashboard/frontend/stock.html`

### Step 3.1: 加 CSS

**File:** `stock/dashboard/frontend/stock.html`

在 `.chip-*` CSS 之後(找 `.chip-neg` 即可定位),加上 fundamentals 共用 + 估值專用 CSS:

```css
.fund-stat-row { display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 12px; }
.fund-stat { display: flex; flex-direction: column; gap: 2px; min-width: 110px; }
.fund-stat .label { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: .04em; }
.fund-stat .value { font-size: 18px; font-weight: 600; color: #e2e8f0; }
.fund-stat .sub   { font-size: 11px; color: #94a3b8; }
.fund-empty { color: #94a3b8; font-size: 13px; padding: 8px 0; }
.fund-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.fund-table th, .fund-table td { padding: 6px 8px; text-align: right; border-bottom: 1px solid #2d3348; }
.fund-table th { color: #94a3b8; font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
.fund-table td.fund-label, .fund-table th.fund-label { text-align: left; color: #e2e8f0; }
.fund-table tbody tr:last-child td { border-bottom: none; }
.fund-pos { color: #4ade80; }
.fund-neg { color: #f87171; }
```

### Step 3.2: 加 HTML(估值快照 card)

緊接在 `<div id="chip-card">` 之後(找 chip-card 結束的 `</div>` 後 一行):

```html
<div class="card" id="valuation-card" style="display:none">
  <div class="card-header">
    <span class="card-label">估值快照</span>
    <span class="card-hint" id="valuation-hint">PER / PBR / 殖利率 · 近 5 年</span>
  </div>
  <div id="valuation-stats" class="fund-stat-row"></div>
  <div class="chart-wrap short"><canvas id="chart-valuation"></canvas></div>
</div>
```

### Step 3.3: 加 JS — loadValuation

在 `loadChip()` 函式之後加上:

```javascript
let valuationChart = null;

async function loadValuation() {
  const card = document.getElementById('valuation-card');
  if (!card) return;
  if (!isTwTicker(TICKER)) { card.style.display = 'none'; return; }
  card.style.display = '';
  const stats = document.getElementById('valuation-stats');
  stats.innerHTML = '<div class="fund-empty">載入中…</div>';

  try {
    const r = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(TICKER)}/valuation?years=5`);
    if (!r.ok) {
      stats.innerHTML = `<div class="fund-empty">無法載入估值 (${r.status})</div>`;
      return;
    }
    const data = await r.json();
    if (!data.latest || !data.rows || !data.rows.length) {
      stats.innerHTML = '<div class="fund-empty">尚無估值資料</div>';
      return;
    }

    const fmtN = (v, d=2) => v === null || v === undefined ? '—' : Number(v).toFixed(d);

    const hint = document.getElementById('valuation-hint');
    if (hint && data.as_of) hint.textContent = `PER / PBR / 殖利率 · 近 5 年 (至 ${data.as_of})`;

    const range = data.range_5y || {};
    stats.innerHTML = `
      <div class="fund-stat">
        <span class="label">PER</span>
        <span class="value">${fmtN(data.latest.per)}</span>
        <span class="sub">5 年區間 ${fmtN(range.per?.min)} – ${fmtN(range.per?.max)}<br>百分位 ${fmtN(data.latest.per_percentile_5y, 1)}%</span>
      </div>
      <div class="fund-stat">
        <span class="label">PBR</span>
        <span class="value">${fmtN(data.latest.pbr)}</span>
        <span class="sub">5 年區間 ${fmtN(range.pbr?.min)} – ${fmtN(range.pbr?.max)}<br>平均 ${fmtN(range.pbr?.avg)}</span>
      </div>
      <div class="fund-stat">
        <span class="label">現金殖利率</span>
        <span class="value">${fmtN(data.latest.dividend_yield)}%</span>
        <span class="sub">5 年平均 ${fmtN(range.dividend_yield?.avg)}%</span>
      </div>
    `;

    // chart: 3 條 line 共一張(left axis = PER/PBR,right axis = 殖利率)
    const labels = data.rows.map(r => r.date);
    const perData = data.rows.map(r => r.per);
    const pbrData = data.rows.map(r => r.pbr);
    const ydData  = data.rows.map(r => r.dividend_yield);
    const ctx = document.getElementById('chart-valuation').getContext('2d');
    if (valuationChart) valuationChart.destroy();
    valuationChart = new Chart(ctx, {
      type: 'line',
      data: { labels, datasets: [
        { label: 'PER',     data: perData, borderColor: '#60a5fa', borderWidth: 1.5, pointRadius: 0, yAxisID: 'y' },
        { label: 'PBR',     data: pbrData, borderColor: '#a78bfa', borderWidth: 1.5, pointRadius: 0, yAxisID: 'y' },
        { label: '殖利率%', data: ydData,  borderColor: '#4ade80', borderWidth: 1.5, pointRadius: 0, yAxisID: 'y1' },
      ]},
      options: {
        ...COMMON_OPTS,
        scales: {
          x: { ...COMMON_OPTS.scales.x, ticks: { ...COMMON_OPTS.scales.x.ticks, maxTicksLimit: 6 } },
          y:  { ...COMMON_OPTS.scales.y, position: 'left',  title: { display: true, text: 'PER / PBR', color: '#94a3b8' } },
          y1: { ...COMMON_OPTS.scales.y, position: 'right', title: { display: true, text: '殖利率 %',  color: '#94a3b8' },
                grid: { drawOnChartArea: false } },
        },
      },
    });
  } catch (e) {
    stats.innerHTML = `<div class="fund-empty">載入失敗:${e.message}</div>`;
  }
}
```

- [ ] 在 `loadDetail()` 函式末尾(`loadChip();` 那行下方)加 `loadValuation();`:

```javascript
makeMacdChart(data.dates, data.indicators);
loadChip();
loadValuation();
} catch (e) {
```

### Step 3.4: 手動 grep 驗證

```bash
grep -n "valuation-card\|loadValuation\|chart-valuation" stock/dashboard/frontend/stock.html
```

Expected: 看到 HTML / JS / canvas 各自定義。

### Step 3.5: 跑後端測試確認沒 regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -5
```

Expected: 47 passed,5 pre-existing fail 不變.

### Step 3.6: Commit

```bash
git add stock/dashboard/frontend/stock.html
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add valuation card to stock detail (T3)

stock.html 新增「估值快照」card:最新 PER/PBR/殖利率 stat row(含 5y
百分位)+ 近 5 年 3 條走勢 chart(PER/PBR 共左軸、殖利率右軸)。lazy
fetch from /valuation,非台股 ticker 自動隱藏。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: UI 月營收 card

**目標:** 月營收 card,顯示最新月 + YoY,近 36 個月 bar(YoY 染色)+ 12MA 疊加 + YTD vs 去年同期 stat。

**Files:**
- Modify: `stock/dashboard/frontend/stock.html`

### Step 4.1: 加 HTML

緊接在 `<div id="valuation-card">` 後:

```html
<div class="card" id="revenue-card" style="display:none">
  <div class="card-header">
    <span class="card-label">月營收</span>
    <span class="card-hint" id="revenue-hint">近 36 個月</span>
  </div>
  <div id="revenue-stats" class="fund-stat-row"></div>
  <div class="chart-wrap short"><canvas id="chart-revenue"></canvas></div>
</div>
```

### Step 4.2: 加 JS — loadRevenue

在 `loadValuation()` 之後:

```javascript
let revenueChart = null;

async function loadRevenue() {
  const card = document.getElementById('revenue-card');
  if (!card) return;
  if (!isTwTicker(TICKER)) { card.style.display = 'none'; return; }
  card.style.display = '';
  const stats = document.getElementById('revenue-stats');
  stats.innerHTML = '<div class="fund-empty">載入中…</div>';

  try {
    const r = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(TICKER)}/revenue?months=36`);
    if (!r.ok) {
      stats.innerHTML = `<div class="fund-empty">無法載入月營收 (${r.status})</div>`;
      return;
    }
    const data = await r.json();
    if (!data.latest || !data.rows || !data.rows.length) {
      stats.innerHTML = '<div class="fund-empty">尚無月營收資料</div>';
      return;
    }

    const fmtYi = v => v === null || v === undefined ? '—' : (v / 1e8).toLocaleString(undefined, {maximumFractionDigits: 0}) + ' 億';
    const fmtPctSigned = v => {
      if (v === null || v === undefined) return '—';
      const cls = v > 0 ? 'fund-pos' : (v < 0 ? 'fund-neg' : '');
      return `<span class="${cls}">${(v >= 0 ? '+' : '')}${Number(v).toFixed(2)}%</span>`;
    };

    const latest = data.latest;
    const ytd = data.ytd || {};
    stats.innerHTML = `
      <div class="fund-stat">
        <span class="label">最新月</span>
        <span class="value">${latest.year}/${String(latest.month).padStart(2,'0')}</span>
        <span class="sub">營收 ${fmtYi(latest.revenue)}</span>
      </div>
      <div class="fund-stat">
        <span class="label">YoY</span>
        <span class="value">${fmtPctSigned(latest.yoy_pct)}</span>
        <span class="sub">12MA ${fmtYi(latest.ma12)}</span>
      </div>
      <div class="fund-stat">
        <span class="label">YTD 累計</span>
        <span class="value">${fmtYi(ytd.accumulated)}</span>
        <span class="sub">去年同期 ${fmtYi(ytd.last_year_accumulated)}<br>YoY ${fmtPctSigned(ytd.yoy_pct)}</span>
      </div>
    `;

    const labels = data.rows.map(r => `${String(r.year).slice(2)}/${String(r.month).padStart(2,'0')}`);
    const revYi  = data.rows.map(r => r.revenue !== null ? r.revenue / 1e8 : null);
    const ma12Yi = data.rows.map(r => r.ma12    !== null ? r.ma12    / 1e8 : null);
    const colors = data.rows.map(r => r.yoy_pct === null ? '#475569' : (r.yoy_pct >= 0 ? '#4ade80' : '#f87171'));

    const ctx = document.getElementById('chart-revenue').getContext('2d');
    if (revenueChart) revenueChart.destroy();
    revenueChart = new Chart(ctx, {
      data: {
        labels,
        datasets: [
          { type: 'bar',  label: '月營收(億)', data: revYi,  backgroundColor: colors, borderWidth: 0, yAxisID: 'y' },
          { type: 'line', label: '12MA(億)',   data: ma12Yi, borderColor: '#fbbf24', borderWidth: 1.5, pointRadius: 0, yAxisID: 'y' },
        ],
      },
      options: {
        ...COMMON_OPTS,
        scales: {
          x: { ...COMMON_OPTS.scales.x, ticks: { ...COMMON_OPTS.scales.x.ticks, maxTicksLimit: 12 } },
          y: { ...COMMON_OPTS.scales.y, title: { display: true, text: '億元', color: '#94a3b8' } },
        },
      },
    });
  } catch (e) {
    stats.innerHTML = `<div class="fund-empty">載入失敗:${e.message}</div>`;
  }
}
```

- [ ] 在 `loadDetail()` 加 `loadRevenue();`(在 `loadValuation();` 下方):

```javascript
loadValuation();
loadRevenue();
```

### Step 4.3: Commit

```bash
git add stock/dashboard/frontend/stock.html
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add monthly revenue card to stock detail (T4)

stock.html 新增「月營收」card:最新月 + YoY + YTD 累計對比去年同期 stat
row;近 36 個月 bar chart(YoY 正負染色)+ 12 個月移動平均 line 疊加。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: UI 損益表 card

**目標:** 12 季表(EPS / 營收 / 毛利 / 營業利益 / 稅後淨利 / 三大利率)+ EPS 季度 chart + TTM 年度匯總 stat。

**Files:**
- Modify: `stock/dashboard/frontend/stock.html`

### Step 5.1: 加 HTML

在 `revenue-card` 後:

```html
<div class="card" id="income-card" style="display:none">
  <div class="card-header">
    <span class="card-label">損益表</span>
    <span class="card-hint" id="income-hint">近 12 季</span>
  </div>
  <div id="income-summary" class="fund-stat-row"></div>
  <div class="chart-wrap short"><canvas id="chart-eps"></canvas></div>
  <div id="income-table-wrap" style="margin-top:12px; overflow-x:auto"></div>
</div>
```

### Step 5.2: 加 JS — loadIncome

```javascript
let epsChart = null;

async function loadIncome() {
  const card = document.getElementById('income-card');
  if (!card) return;
  if (!isTwTicker(TICKER)) { card.style.display = 'none'; return; }
  card.style.display = '';
  const summary = document.getElementById('income-summary');
  const tableWrap = document.getElementById('income-table-wrap');
  summary.innerHTML = '<div class="fund-empty">載入中…</div>';
  tableWrap.innerHTML = '';

  try {
    const r = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(TICKER)}/financial?statement=income&quarters=12`);
    if (!r.ok) {
      summary.innerHTML = `<div class="fund-empty">無法載入損益表 (${r.status})</div>`;
      return;
    }
    const data = await r.json();
    if (!data.rows || !data.rows.length) {
      summary.innerHTML = '<div class="fund-empty">尚無損益資料</div>';
      return;
    }

    const fmtYi = v => v === null || v === undefined ? '—' : (v / 1e8).toLocaleString(undefined, {maximumFractionDigits: 0});
    const fmtN = (v, d=2) => v === null || v === undefined ? '—' : Number(v).toFixed(d);
    const fmtPctSigned = v => {
      if (v === null || v === undefined) return '—';
      const cls = v > 0 ? 'fund-pos' : (v < 0 ? 'fund-neg' : '');
      return `<span class="${cls}">${(v >= 0 ? '+' : '')}${Number(v).toFixed(2)}%</span>`;
    };

    const ann = data.annual_summary;
    if (ann) {
      summary.innerHTML = `
        <div class="fund-stat">
          <span class="label">最近 4 季 EPS</span>
          <span class="value">${fmtN(ann.current_4q.eps)}</span>
          <span class="sub">前 4 季 ${fmtN(ann.previous_4q.eps)} · YoY ${fmtPctSigned(ann.eps_yoy_pct)}</span>
        </div>
        <div class="fund-stat">
          <span class="label">最近 4 季營收</span>
          <span class="value">${fmtYi(ann.current_4q.revenue)} 億</span>
          <span class="sub">前 4 季 ${fmtYi(ann.previous_4q.revenue)} 億 · YoY ${fmtPctSigned(ann.revenue_yoy_pct)}</span>
        </div>
      `;
    } else {
      summary.innerHTML = '<div class="fund-empty">資料不足以計算 4 季匯總</div>';
    }

    // 表格(倒序最新在上)
    const rev = [...data.rows].reverse();
    tableWrap.innerHTML = `
      <table class="fund-table">
        <thead><tr>
          <th class="fund-label">季別</th>
          <th>EPS</th><th>營收(億)</th><th>毛利(億)</th><th>營益(億)</th><th>淨利(億)</th>
          <th>毛利率</th><th>營益率</th><th>淨利率</th>
        </tr></thead>
        <tbody>
          ${rev.map(r => `
            <tr>
              <td class="fund-label">${r.date}</td>
              <td>${fmtN(r.eps)}</td>
              <td>${fmtYi(r.revenue)}</td>
              <td>${fmtYi(r.gross_profit)}</td>
              <td>${fmtYi(r.operating_income)}</td>
              <td>${fmtYi(r.net_income)}</td>
              <td>${fmtN(r.gross_margin_pct)}%</td>
              <td>${fmtN(r.operating_margin_pct)}%</td>
              <td>${fmtN(r.net_margin_pct)}%</td>
            </tr>
          `).join('')}
        </tbody>
      </table>`;

    const labels = data.rows.map(r => r.date);
    const epsData = data.rows.map(r => r.eps);
    const ctx = document.getElementById('chart-eps').getContext('2d');
    if (epsChart) epsChart.destroy();
    epsChart = new Chart(ctx, {
      type: 'line',
      data: { labels, datasets: [
        { label: 'EPS', data: epsData, borderColor: '#60a5fa', backgroundColor: '#60a5fa', borderWidth: 1.5, pointRadius: 2 },
      ]},
      options: {
        ...COMMON_OPTS,
        scales: {
          x: { ...COMMON_OPTS.scales.x, ticks: { ...COMMON_OPTS.scales.x.ticks, maxTicksLimit: 6 } },
          y: { ...COMMON_OPTS.scales.y, title: { display: true, text: 'EPS (元)', color: '#94a3b8' } },
        },
      },
    });
  } catch (e) {
    summary.innerHTML = `<div class="fund-empty">載入失敗:${e.message}</div>`;
  }
}
```

- [ ] 在 `loadDetail()` 加 `loadIncome();`(在 `loadRevenue();` 下方)

### Step 5.3: Commit

```bash
git add stock/dashboard/frontend/stock.html
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add income statement card to stock detail (T5)

stock.html 新增「損益表」card:近 12 季表(EPS/營收/毛利/營業利益/淨利/
毛利率/營益率/淨利率)+ EPS 季度 line chart + TTM 年度匯總 stat block
(最近 4 季 vs 前 4 季 YoY)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: UI 資產負債表 card

**目標:** 12 季表(資產 / 負債 / 權益細項)+ 比率 + 總資產 vs 股東權益趨勢 chart。

**Files:**
- Modify: `stock/dashboard/frontend/stock.html`

### Step 6.1: 加 HTML

在 `income-card` 後:

```html
<div class="card" id="balance-card" style="display:none">
  <div class="card-header">
    <span class="card-label">資產負債表</span>
    <span class="card-hint" id="balance-hint">近 12 季</span>
  </div>
  <div id="balance-summary" class="fund-stat-row"></div>
  <div class="chart-wrap short"><canvas id="chart-balance"></canvas></div>
  <div id="balance-table-wrap" style="margin-top:12px; overflow-x:auto"></div>
</div>
```

### Step 6.2: 加 JS — loadBalance

```javascript
let balanceChart = null;

async function loadBalance() {
  const card = document.getElementById('balance-card');
  if (!card) return;
  if (!isTwTicker(TICKER)) { card.style.display = 'none'; return; }
  card.style.display = '';
  const summary = document.getElementById('balance-summary');
  const tableWrap = document.getElementById('balance-table-wrap');
  summary.innerHTML = '<div class="fund-empty">載入中…</div>';
  tableWrap.innerHTML = '';

  try {
    const r = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(TICKER)}/financial?statement=balance&quarters=12`);
    if (!r.ok) {
      summary.innerHTML = `<div class="fund-empty">無法載入資產負債 (${r.status})</div>`;
      return;
    }
    const data = await r.json();
    if (!data.rows || !data.rows.length) {
      summary.innerHTML = '<div class="fund-empty">尚無資產負債資料</div>';
      return;
    }

    const fmtYi = v => v === null || v === undefined ? '—' : (v / 1e8).toLocaleString(undefined, {maximumFractionDigits: 0});
    const fmtN = (v, d=2) => v === null || v === undefined ? '—' : Number(v).toFixed(d);

    const latest = data.rows[data.rows.length - 1];
    summary.innerHTML = `
      <div class="fund-stat">
        <span class="label">總資產(${latest.date})</span>
        <span class="value">${fmtYi(latest.total_assets)} 億</span>
        <span class="sub">現金 ${fmtYi(latest.cash)} 億</span>
      </div>
      <div class="fund-stat">
        <span class="label">流動 / 速動 比</span>
        <span class="value">${fmtN(latest.current_ratio)}</span>
        <span class="sub">流動資產 ${fmtYi(latest.current_assets)} 億 / 流動負債 ${fmtYi(latest.current_liabilities)} 億</span>
      </div>
      <div class="fund-stat">
        <span class="label">負債比 / 權益比</span>
        <span class="value">${fmtN(latest.debt_ratio_pct)}% / ${fmtN(latest.equity_ratio_pct)}%</span>
        <span class="sub">總負債 ${fmtYi(latest.total_liabilities)} 億 · 股東權益 ${fmtYi(latest.equity)} 億</span>
      </div>
    `;

    const rev = [...data.rows].reverse();
    tableWrap.innerHTML = `
      <table class="fund-table">
        <thead><tr>
          <th class="fund-label">季別</th>
          <th>總資產(億)</th><th>流動資產(億)</th><th>現金(億)</th>
          <th>總負債(億)</th><th>流動負債(億)</th><th>長期負債(億)</th>
          <th>股東權益(億)</th>
          <th>流動比</th><th>負債比</th>
        </tr></thead>
        <tbody>
          ${rev.map(r => `
            <tr>
              <td class="fund-label">${r.date}</td>
              <td>${fmtYi(r.total_assets)}</td>
              <td>${fmtYi(r.current_assets)}</td>
              <td>${fmtYi(r.cash)}</td>
              <td>${fmtYi(r.total_liabilities)}</td>
              <td>${fmtYi(r.current_liabilities)}</td>
              <td>${fmtYi(r.long_term_liabilities)}</td>
              <td>${fmtYi(r.equity)}</td>
              <td>${fmtN(r.current_ratio)}</td>
              <td>${fmtN(r.debt_ratio_pct)}%</td>
            </tr>
          `).join('')}
        </tbody>
      </table>`;

    const labels = data.rows.map(r => r.date);
    const taData = data.rows.map(r => r.total_assets !== null ? r.total_assets / 1e8 : null);
    const eqData = data.rows.map(r => r.equity       !== null ? r.equity       / 1e8 : null);
    const ctx = document.getElementById('chart-balance').getContext('2d');
    if (balanceChart) balanceChart.destroy();
    balanceChart = new Chart(ctx, {
      type: 'line',
      data: { labels, datasets: [
        { label: '總資產(億)',   data: taData, borderColor: '#60a5fa', borderWidth: 1.5, pointRadius: 0, yAxisID: 'y' },
        { label: '股東權益(億)', data: eqData, borderColor: '#4ade80', borderWidth: 1.5, pointRadius: 0, yAxisID: 'y' },
      ]},
      options: {
        ...COMMON_OPTS,
        scales: {
          x: { ...COMMON_OPTS.scales.x, ticks: { ...COMMON_OPTS.scales.x.ticks, maxTicksLimit: 6 } },
          y: { ...COMMON_OPTS.scales.y, title: { display: true, text: '億元', color: '#94a3b8' } },
        },
      },
    });
  } catch (e) {
    summary.innerHTML = `<div class="fund-empty">載入失敗:${e.message}</div>`;
  }
}
```

- [ ] `loadDetail()` 加 `loadBalance();`(`loadIncome();` 下方)

### Step 6.3: Commit

```bash
git add stock/dashboard/frontend/stock.html
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add balance sheet card to stock detail (T6)

stock.html 新增「資產負債表」card:近 12 季表(總資產/流動/現金/總負債/
流動負債/長期負債/股東權益,加流動比、負債比)+ 總資產 vs 股東權益趨勢
line chart + 最新季比率 stat block。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: UI 現金流量表 card

**目標:** 12 季表(營業/投資/融資/自由 CF)+ 三大現金流 stacked bar + 自由現金流 line。

**Files:**
- Modify: `stock/dashboard/frontend/stock.html`

### Step 7.1: 加 HTML

在 `balance-card` 後:

```html
<div class="card" id="cashflow-card" style="display:none">
  <div class="card-header">
    <span class="card-label">現金流量表</span>
    <span class="card-hint" id="cashflow-hint">近 12 季</span>
  </div>
  <div id="cashflow-summary" class="fund-stat-row"></div>
  <div class="chart-wrap short"><canvas id="chart-cashflow"></canvas></div>
  <div id="cashflow-table-wrap" style="margin-top:12px; overflow-x:auto"></div>
</div>
```

### Step 7.2: 加 JS — loadCashflow

```javascript
let cashflowChart = null;

async function loadCashflow() {
  const card = document.getElementById('cashflow-card');
  if (!card) return;
  if (!isTwTicker(TICKER)) { card.style.display = 'none'; return; }
  card.style.display = '';
  const summary = document.getElementById('cashflow-summary');
  const tableWrap = document.getElementById('cashflow-table-wrap');
  summary.innerHTML = '<div class="fund-empty">載入中…</div>';
  tableWrap.innerHTML = '';

  try {
    const r = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(TICKER)}/financial?statement=cashflow&quarters=12`);
    if (!r.ok) {
      summary.innerHTML = `<div class="fund-empty">無法載入現金流量 (${r.status})</div>`;
      return;
    }
    const data = await r.json();
    if (!data.rows || !data.rows.length) {
      summary.innerHTML = '<div class="fund-empty">尚無現金流量資料</div>';
      return;
    }

    const fmtYi = v => v === null || v === undefined ? '—' : (v / 1e8).toLocaleString(undefined, {maximumFractionDigits: 0});

    const latest = data.rows[data.rows.length - 1];
    summary.innerHTML = `
      <div class="fund-stat">
        <span class="label">營業 CF</span>
        <span class="value">${fmtYi(latest.operating_cf)} 億</span>
      </div>
      <div class="fund-stat">
        <span class="label">投資 CF</span>
        <span class="value">${fmtYi(latest.investing_cf)} 億</span>
      </div>
      <div class="fund-stat">
        <span class="label">融資 CF</span>
        <span class="value">${fmtYi(latest.financing_cf)} 億</span>
      </div>
      <div class="fund-stat">
        <span class="label">自由現金流</span>
        <span class="value">${fmtYi(latest.free_cash_flow)} 億</span>
        <span class="sub">營業 + 投資</span>
      </div>
    `;

    const rev = [...data.rows].reverse();
    tableWrap.innerHTML = `
      <table class="fund-table">
        <thead><tr>
          <th class="fund-label">季別</th>
          <th>營業 CF(億)</th><th>投資 CF(億)</th><th>融資 CF(億)</th>
          <th>自由 CF(億)</th>
        </tr></thead>
        <tbody>
          ${rev.map(r => `
            <tr>
              <td class="fund-label">${r.date}</td>
              <td>${fmtYi(r.operating_cf)}</td>
              <td>${fmtYi(r.investing_cf)}</td>
              <td>${fmtYi(r.financing_cf)}</td>
              <td>${fmtYi(r.free_cash_flow)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>`;

    const labels = data.rows.map(r => r.date);
    const ocf = data.rows.map(r => r.operating_cf  !== null ? r.operating_cf  / 1e8 : null);
    const icf = data.rows.map(r => r.investing_cf  !== null ? r.investing_cf  / 1e8 : null);
    const fcf = data.rows.map(r => r.financing_cf  !== null ? r.financing_cf  / 1e8 : null);
    const free = data.rows.map(r => r.free_cash_flow !== null ? r.free_cash_flow / 1e8 : null);
    const ctx = document.getElementById('chart-cashflow').getContext('2d');
    if (cashflowChart) cashflowChart.destroy();
    cashflowChart = new Chart(ctx, {
      data: {
        labels,
        datasets: [
          { type: 'bar',  label: '營業 CF', data: ocf,  backgroundColor: '#4ade80', stack: 'cf' },
          { type: 'bar',  label: '投資 CF', data: icf,  backgroundColor: '#f87171', stack: 'cf' },
          { type: 'bar',  label: '融資 CF', data: fcf,  backgroundColor: '#a78bfa', stack: 'cf' },
          { type: 'line', label: '自由 CF', data: free, borderColor: '#fbbf24', borderWidth: 1.5, pointRadius: 2 },
        ],
      },
      options: {
        ...COMMON_OPTS,
        scales: {
          x: { ...COMMON_OPTS.scales.x, ticks: { ...COMMON_OPTS.scales.x.ticks, maxTicksLimit: 6 }, stacked: true },
          y: { ...COMMON_OPTS.scales.y, title: { display: true, text: '億元', color: '#94a3b8' }, stacked: true },
        },
      },
    });
  } catch (e) {
    summary.innerHTML = `<div class="fund-empty">載入失敗:${e.message}</div>`;
  }
}
```

- [ ] `loadDetail()` 加 `loadCashflow();`(`loadBalance();` 下方)

### Step 7.3: Commit

```bash
git add stock/dashboard/frontend/stock.html
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add cash flow card to stock detail (T7)

stock.html 新增「現金流量表」card:近 12 季表(營業/投資/融資 CF + 自由
現金流)+ 三大現金流 stacked bar + 自由現金流 line(疊加)+ 最新季 stat
block。自由現金流 = 營業 CF + 投資 CF。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: UI 股利歷史 card

**目標:** 10 年表 + 歷年現金/股票股利 stacked bar + 平均配發率/殖利率 stat。

**Files:**
- Modify: `stock/dashboard/frontend/stock.html`

### Step 8.1: 加 HTML

在 `cashflow-card` 後:

```html
<div class="card" id="dividend-card" style="display:none">
  <div class="card-header">
    <span class="card-label">股利歷史</span>
    <span class="card-hint" id="dividend-hint">近 10 年</span>
  </div>
  <div id="dividend-summary" class="fund-stat-row"></div>
  <div class="chart-wrap short"><canvas id="chart-dividend"></canvas></div>
  <div id="dividend-table-wrap" style="margin-top:12px; overflow-x:auto"></div>
</div>
```

### Step 8.2: 加 JS — loadDividend

```javascript
let dividendChart = null;

async function loadDividend() {
  const card = document.getElementById('dividend-card');
  if (!card) return;
  if (!isTwTicker(TICKER)) { card.style.display = 'none'; return; }
  card.style.display = '';
  const summary = document.getElementById('dividend-summary');
  const tableWrap = document.getElementById('dividend-table-wrap');
  summary.innerHTML = '<div class="fund-empty">載入中…</div>';
  tableWrap.innerHTML = '';

  try {
    const r = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(TICKER)}/dividend?years=10`);
    if (!r.ok) {
      summary.innerHTML = `<div class="fund-empty">無法載入股利 (${r.status})</div>`;
      return;
    }
    const data = await r.json();
    if (!data.rows || !data.rows.length) {
      summary.innerHTML = '<div class="fund-empty">尚無股利資料</div>';
      return;
    }

    const fmtN = (v, d=2) => v === null || v === undefined ? '—' : Number(v).toFixed(d);

    const sm = data.summary || {};
    summary.innerHTML = `
      <div class="fund-stat">
        <span class="label">平均配發率</span>
        <span class="value">${fmtN(sm.avg_payout_ratio_pct)}%</span>
        <span class="sub">近 10 年現金股利 / EPS 平均</span>
      </div>
      <div class="fund-stat">
        <span class="label">平均殖利率</span>
        <span class="value">${sm.avg_dividend_yield_pct === null ? '—' : fmtN(sm.avg_dividend_yield_pct) + '%'}</span>
        <span class="sub">${sm.avg_dividend_yield_pct === null ? '需歷史均價,目前未計' : '近 10 年平均'}</span>
      </div>
    `;

    const rev = [...data.rows].reverse();
    tableWrap.innerHTML = `
      <table class="fund-table">
        <thead><tr>
          <th class="fund-label">年份</th>
          <th>現金股利</th><th>股票股利</th>
          <th>配發率</th><th>殖利率</th><th>除權息日</th>
        </tr></thead>
        <tbody>
          ${rev.map(r => `
            <tr>
              <td class="fund-label">${r.year}</td>
              <td>${fmtN(r.cash_dividend)}</td>
              <td>${fmtN(r.stock_dividend)}</td>
              <td>${fmtN(r.payout_ratio_pct)}${r.payout_ratio_pct !== null ? '%' : ''}</td>
              <td>${r.dividend_yield_pct === null ? '—' : fmtN(r.dividend_yield_pct) + '%'}</td>
              <td>${r.cash_ex_date ?? '—'}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>`;

    const labels = data.rows.map(r => String(r.year));
    const cash = data.rows.map(r => r.cash_dividend);
    const stk  = data.rows.map(r => r.stock_dividend);
    const ctx = document.getElementById('chart-dividend').getContext('2d');
    if (dividendChart) dividendChart.destroy();
    dividendChart = new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets: [
        { label: '現金股利', data: cash, backgroundColor: '#4ade80', stack: 'd' },
        { label: '股票股利', data: stk,  backgroundColor: '#a78bfa', stack: 'd' },
      ]},
      options: {
        ...COMMON_OPTS,
        scales: {
          x: { ...COMMON_OPTS.scales.x, stacked: true },
          y: { ...COMMON_OPTS.scales.y, title: { display: true, text: '元 / 股', color: '#94a3b8' }, stacked: true },
        },
      },
    });
  } catch (e) {
    summary.innerHTML = `<div class="fund-empty">載入失敗:${e.message}</div>`;
  }
}
```

- [ ] `loadDetail()` 加 `loadDividend();`(`loadCashflow();` 下方)

### Step 8.3: Commit

```bash
git add stock/dashboard/frontend/stock.html
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add dividend history card to stock detail (T8)

stock.html 新增「股利歷史」card:近 10 年表(每西元年合計現金/股票股利、
配發率、除權息日)+ 歷年現金/股票股利 stacked bar chart + 平均配發率
stat block。殖利率欄位暫顯 — (需歷史均價尚未實作)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Deploy + 驗證

**目標:** push 到 master 觸發部署、ssh VPS 確認服務正常、curl 驗證 4 個 endpoint、提示手動 UI 抽看。

### Step 9.1: 確認本機所有測試通過

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 47 passed,5 pre-existing failures unchanged. 如有新增 fail,STOP 報告 BLOCKED.

### Step 9.2: Push

```bash
git push origin master
```

### Step 9.3: Watch deploys

```bash
gh run watch $(gh run list --workflow=deploy-stock-dashboard-backend.yml --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
gh run watch $(gh run list --workflow=deploy-stock-dashboard.yml         --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
```

Expected: 兩個 workflow 都成功(各約 20-30s)。

### Step 9.4: 驗證 4 個 endpoint

```bash
echo '--- /valuation ---'
curl -s 'https://api.paul-learning.dev/api/stocks/2330.TW/valuation?years=5' | jq '{ok, as_of, latest, range_5y_per: .range_5y.per, count: (.rows | length)}'

echo '--- /revenue ---'
curl -s 'https://api.paul-learning.dev/api/stocks/2330.TW/revenue?months=12' | jq '{ok, latest, ytd, count: (.rows | length)}'

echo '--- /financial?statement=income ---'
curl -s 'https://api.paul-learning.dev/api/stocks/2330.TW/financial?statement=income&quarters=4' | jq '{ok, annual_summary, sample: .rows[-1]}'

echo '--- /financial?statement=balance ---'
curl -s 'https://api.paul-learning.dev/api/stocks/2330.TW/financial?statement=balance&quarters=4' | jq '{ok, sample: .rows[-1]}'

echo '--- /financial?statement=cashflow ---'
curl -s 'https://api.paul-learning.dev/api/stocks/2330.TW/financial?statement=cashflow&quarters=4' | jq '{ok, sample: .rows[-1]}'

echo '--- /dividend ---'
curl -s 'https://api.paul-learning.dev/api/stocks/2330.TW/dividend?years=10' | jq '{ok, summary, count: (.rows | length), sample: .rows[-1]}'
```

Expected:
- valuation:`ok: true`,`latest.per` / `latest.pbr` / `latest.dividend_yield` 都非 null,`per_percentile_5y` 是 0-100 數字,`count` ~250-1250(視首次 fetch 範圍)
- revenue:`ok: true`,`latest.year/month/revenue` 非 null,`ytd.accumulated` 非 null
- financial(income):`ok: true`,`annual_summary` 非 null(若有 8 季資料),`sample.eps`、`sample.gross_margin_pct` 非 null
- financial(balance):`sample.total_assets`、`current_ratio`、`debt_ratio_pct` 非 null
- financial(cashflow):`sample.operating_cf`、`free_cash_flow` 非 null
- dividend:`ok: true`,`rows` 多個年份,`sample.cash_dividend` 非 null

### Step 9.5: 手動 UI 抽看(由執行者交還給使用者)

執行者沒瀏覽器,標註此項給使用者手動驗證:
- `https://paul-learning.dev/stock.html?ticker=2330.TW` — 確認 6 張新 cards 都有資料、chart 都渲染
- 切換到非台股 ticker(如 AAPL)— 6 張新 cards 應該都隱藏

### Step 9.6: VPS .env sanity check

```bash
ssh root@${VPS_HOST} "awk -F= '{print \$1}' /opt/stock-dashboard/backend/.env"
```

Expected: 顯示 `DISCORD_STOCK_WEBHOOK_URL`、`FINMIND_TOKEN` — 沒被沖掉。

> 注意:`${VPS_HOST}` 需替換為實際 VPS 位址(由執行者所在環境的 env var 提供;不要 inline 進 commit message 或 doc)。

### Step 9.7: 報告

執行者最終報告含:
- 本機測試結果
- Push commit SHA
- 兩個 workflow 的成功狀態
- 6 個 curl 命令的 JSON 輸出(verbatim)
- VPS .env keys
- 手動 UI 驗證提示給使用者

---

## 完成後狀態

- 4 張新 DB 表(`stock_per_daily` / `stock_revenue_monthly` / `stock_financial_quarterly` / `stock_dividend_history`)
- 1 個新 fetcher 模組(`fundamentals_stock.py`)含 4 個 fetcher
- 4 個新 API endpoint(`/valuation` / `/revenue` / `/financial` / `/dividend`)
- 6 張新 UI cards(估值快照 / 月營收 / 損益 / 資產負債 / 現金流 / 股利)
- 6 個新 chart(estaluation 3 軸 / revenue bar+line / EPS line / balance line / cashflow stacked+line / dividend stacked bar)
- 11 個新測試(4 parse + 7 endpoint)
- 警示規則層尚未實作(Phase 1 同決定)

## 風險與緩解(備忘)

- **FinMind dataset 改 Sponsor 等級**:仿券商分點下架模式。fetcher 短路、UI 隱藏 card、保留程式碼。
- **6 張 card 同時 lazy fetch**:首次開個股頁打 6 次 FinMind(~6 秒)。各 card 各自 graceful fail,單一 fail 不擋其他。實際 quota 壓力低。
- **三表 type 命名衝突**:DB 加 `report_type` 欄區分(已採)。
- **EPS 為 0 / 缺 EPS 的配發率**:API 層回 None,前端顯示 `—`。
- **股利「年份」對應 EPS**:用西元年合計現金股利 ÷ 西元年合計 EPS。`_aggregate_dividend_by_calendar_year` 從 ROC 年解析。`_annual_eps_sum` 取該西元年所有日期(`{year}-...`)的 EPS。
- **殖利率(dividend_yield_pct in /dividend)目前留 None**:需要該年均價,Phase 2 不實作(`stock_snapshots` 沒儲存歷史日均;之後可加 sub-task)。`/valuation` 的 `dividend_yield` 是 FinMind PER dataset 提供的「滾動殖利率」,不一樣。
- **速動比(Quick Ratio)未實作**:Spec 列「流動比 / 速動比 / 負債比 / 權益比」4 個比率,plan 只做 3 個。原因:速動比 = (流動資產 − 存貨) / 流動負債,需要 FinMind 端「Inventories」type 字串,未事先實測確認,先 backlog。其餘 3 個比率覆蓋核心償債能力判斷。需求出現再加。
