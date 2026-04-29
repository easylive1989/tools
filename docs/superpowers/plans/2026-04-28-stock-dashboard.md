# Stock Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web dashboard at `paul-learning.dev/stock` showing Taiwan market indicators with historical charts, backed by a FastAPI service on `api.paul-learning.dev` that scrapes and caches data on a schedule.

**Architecture:** Static `index.html` on GitHub Pages calls a FastAPI backend on VPS. The backend uses APScheduler to fetch data from yfinance / TWSE / NDC / macromicro.me on different schedules and stores it in SQLite. The frontend polls the API every 60 s and renders charts with Chart.js.

**Tech Stack:** Python 3.11, FastAPI, APScheduler, SQLite, yfinance, requests, BeautifulSoup4, Chart.js (CDN), GitHub Actions, systemd.

---

## File Map

```
stock/dashboard/
├── backend/
│   ├── app.py                    # FastAPI app, CORS, routes, startup
│   ├── db.py                     # SQLite init, all CRUD helpers
│   ├── scheduler.py              # APScheduler job registration
│   ├── fetchers/
│   │   ├── __init__.py
│   │   ├── yfinance_fetcher.py   # taiex (^TWII), fx (TWD=X), watched stocks
│   │   ├── fear_greed.py         # macromicro.me scraper
│   │   ├── margin.py             # TWSE OpenAPI – margin balance
│   │   └── ndc.py                # NDC open data – composite indicator
│   └── requirements.txt
├── frontend/
│   └── index.html                # Single-page dashboard, Chart.js via CDN
├── stock-dashboard.service       # systemd unit file
├── deploy.sh                     # VPS deploy script
└── tests/
    ├── test_db.py
    ├── test_fetchers.py
    └── test_api.py
```

---

## Task 1: Scaffold

**Files:**
- Create: `stock/dashboard/backend/requirements.txt`
- Create: `stock/dashboard/backend/fetchers/__init__.py`
- Create: `stock/dashboard/tests/__init__.py`

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p stock/dashboard/backend/fetchers
mkdir -p stock/dashboard/frontend
mkdir -p stock/dashboard/tests
touch stock/dashboard/backend/fetchers/__init__.py
touch stock/dashboard/tests/__init__.py
```

- [ ] **Step 2: Write `requirements.txt`**

```
# stock/dashboard/backend/requirements.txt
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
apscheduler>=3.10.0
yfinance>=0.2.40
requests>=2.32.0
beautifulsoup4>=4.12.0
pytz>=2024.1
httpx>=0.27.0
pytest>=8.0.0
```

- [ ] **Step 3: Create virtualenv and install**

```bash
cd stock/dashboard/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 4: Commit**

```bash
git add stock/dashboard/
git commit -m "feat(stock-dashboard): scaffold directory structure"
```

---

## Task 2: Database layer

**Files:**
- Create: `stock/dashboard/backend/db.py`
- Create: `stock/dashboard/tests/test_db.py`

- [ ] **Step 1: Write failing tests**

```python
# stock/dashboard/tests/test_db.py
import os, sys, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
os.environ["DB_PATH"] = ":memory:"

import db

def test_init_creates_tables():
    db.init_db()
    conn = db.get_connection()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"indicator_snapshots", "watched_stocks", "stock_snapshots"} <= tables

def test_save_and_get_indicator():
    db.init_db()
    db.save_indicator("taiex", 21458.0, '{"change_pct": 0.58}')
    row = db.get_latest_indicator("taiex")
    assert row is not None
    assert row["value"] == 21458.0
    assert row["indicator"] == "taiex"

def test_get_indicator_returns_none_when_empty():
    db.init_db()
    assert db.get_latest_indicator("ndc") is None

def test_indicator_history_filtered_by_date():
    db.init_db()
    from datetime import datetime, timedelta
    db.save_indicator("margin", 2500.0)
    db.save_indicator("margin", 2341.0)
    since = datetime.utcnow() - timedelta(minutes=1)
    rows = db.get_indicator_history("margin", since)
    assert len(rows) == 2
    assert rows[-1]["value"] == 2341.0

def test_watched_stocks_crud():
    db.init_db()
    db.add_watched_ticker("2330.TW")
    db.add_watched_ticker("VOO")
    tickers = db.get_watched_tickers()
    assert "2330.TW" in tickers
    assert "VOO" in tickers
    db.remove_watched_ticker("VOO")
    assert "VOO" not in db.get_watched_tickers()

def test_add_duplicate_ticker_is_idempotent():
    db.init_db()
    db.add_watched_ticker("AAPL")
    db.add_watched_ticker("AAPL")
    assert db.get_watched_tickers().count("AAPL") == 1

def test_save_and_get_stock_snapshot():
    db.init_db()
    db.add_watched_ticker("0050.TW")
    db.save_stock_snapshot("0050.TW", 198.35, 1.15, 0.58, "TWD", "元大台灣50")
    row = db.get_latest_stock("0050.TW")
    assert row["price"] == 198.35
    assert row["name"] == "元大台灣50"
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd stock/dashboard
source backend/.venv/bin/activate
python -m pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Implement `db.py`**

```python
# stock/dashboard/backend/db.py
import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "stock_dashboard.db"))

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS indicator_snapshots (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                indicator TEXT    NOT NULL,
                timestamp TEXT    NOT NULL,
                value     REAL    NOT NULL,
                extra_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_ind_ts
                ON indicator_snapshots(indicator, timestamp);

            CREATE TABLE IF NOT EXISTS watched_stocks (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker   TEXT NOT NULL UNIQUE,
                added_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stock_snapshots (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker     TEXT NOT NULL,
                timestamp  TEXT NOT NULL,
                price      REAL NOT NULL,
                change     REAL,
                change_pct REAL,
                currency   TEXT,
                name       TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_stock_ts
                ON stock_snapshots(ticker, timestamp);
        """)

def save_indicator(indicator: str, value: float, extra_json: str = None):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO indicator_snapshots (indicator, timestamp, value, extra_json) VALUES (?,?,?,?)",
            (indicator, datetime.utcnow().isoformat(), value, extra_json),
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

def save_stock_snapshot(ticker: str, price: float, change: float, change_pct: float, currency: str, name: str = ""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO stock_snapshots (ticker, timestamp, price, change, change_pct, currency, name) "
            "VALUES (?,?,?,?,?,?,?)",
            (ticker, datetime.utcnow().isoformat(), price, change, change_pct, currency, name),
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
            (ticker, datetime.utcnow().isoformat()),
        )

def remove_watched_ticker(ticker: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM watched_stocks WHERE ticker=?", (ticker,))

def purge_old_data(days: int = 1095):
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        conn.execute("DELETE FROM indicator_snapshots WHERE timestamp<?", (cutoff,))
        conn.execute("DELETE FROM stock_snapshots WHERE timestamp<?", (cutoff,))
```

- [ ] **Step 4: Run tests — expect pass**

```bash
python -m pytest tests/test_db.py -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add stock/dashboard/backend/db.py stock/dashboard/tests/test_db.py
git commit -m "feat(stock-dashboard): add SQLite database layer"
```

---

## Task 3: yfinance fetcher

**Files:**
- Create: `stock/dashboard/backend/fetchers/yfinance_fetcher.py`
- Create: `stock/dashboard/tests/test_fetchers.py`

- [ ] **Step 1: Write failing tests**

```python
# stock/dashboard/tests/test_fetchers.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
os.environ["DB_PATH"] = ":memory:"

import db
db.init_db()

from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
import json

def make_hist(prices):
    idx = pd.date_range("2026-01-01", periods=len(prices), freq="D")
    return pd.DataFrame({"Close": prices, "Open": prices, "High": prices, "Low": prices, "Volume": [0]*len(prices)}, index=idx)

def test_fetch_taiex_saves_indicator():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_hist([21334.0, 21458.0])
    mock_ticker.history_metadata = {"currency": "TWD"}

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_taiex
        fetch_taiex()

    row = db.get_latest_indicator("taiex")
    assert row is not None
    assert row["value"] == 21458.0
    extra = json.loads(row["extra_json"])
    assert abs(extra["change_pct"] - 0.58) < 0.1
    assert extra["prev_close"] == 21334.0

def test_fetch_fx_saves_indicator():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_hist([32.11, 32.15])
    mock_ticker.history_metadata = {"currency": "USD"}

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_fx
        fetch_fx()

    row = db.get_latest_indicator("fx")
    assert row is not None
    assert abs(row["value"] - 32.15) < 0.01

def test_fetch_all_stocks_saves_snapshots():
    db.add_watched_ticker("0050.TW")
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_hist([197.20, 198.35])
    mock_ticker.history_metadata = {"currency": "TWD"}
    mock_ticker.info = {"shortName": "元大台灣50"}

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_all_stocks
        fetch_all_stocks()

    row = db.get_latest_stock("0050.TW")
    assert row is not None
    assert abs(row["price"] - 198.35) < 0.01
    assert row["currency"] == "TWD"

def test_fetch_taiex_skips_on_empty_history():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_taiex
        fetch_taiex()  # should not raise
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest tests/test_fetchers.py -v
```

Expected: `ModuleNotFoundError: No module named 'fetchers.yfinance_fetcher'`

- [ ] **Step 3: Implement `fetchers/yfinance_fetcher.py`**

```python
# stock/dashboard/backend/fetchers/yfinance_fetcher.py
import json
import yfinance as yf
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator, save_stock_snapshot, get_watched_tickers

def _fetch_price(ticker_symbol: str) -> dict | None:
    stock = yf.Ticker(ticker_symbol)
    hist = stock.history(period="5d")
    if hist.empty:
        return None
    latest = hist.iloc[-1]
    prev = hist.iloc[-2] if len(hist) >= 2 else latest
    price = float(latest["Close"])
    prev_close = float(prev["Close"])
    change = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0
    currency = ""
    try:
        currency = stock.history_metadata.get("currency", "")
    except Exception:
        pass
    return {"price": price, "prev_close": prev_close, "change": change,
            "change_pct": round(change_pct, 2), "currency": currency}

def fetch_taiex():
    data = _fetch_price("^TWII")
    if not data:
        return
    save_indicator("taiex", data["price"], json.dumps({
        "change_pct": data["change_pct"],
        "prev_close": round(data["prev_close"], 2),
    }))

def fetch_fx():
    data = _fetch_price("TWD=X")
    if not data:
        return
    save_indicator("fx", round(data["price"], 4), json.dumps({
        "change_pct": data["change_pct"],
        "prev_close": round(data["prev_close"], 4),
    }))

def fetch_all_stocks():
    tickers = get_watched_tickers()
    for ticker in tickers:
        try:
            data = _fetch_price(ticker)
            if not data:
                continue
            name = ticker
            try:
                info = yf.Ticker(ticker).info
                name = info.get("shortName") or info.get("longName") or ticker
            except Exception:
                pass
            save_stock_snapshot(
                ticker, round(data["price"], 4),
                round(data["change"], 4), data["change_pct"],
                data["currency"], name,
            )
        except Exception as e:
            print(f"[yfinance] Error fetching {ticker}: {e}")
```

- [ ] **Step 4: Run — expect pass**

```bash
python -m pytest tests/test_fetchers.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add stock/dashboard/backend/fetchers/yfinance_fetcher.py stock/dashboard/tests/test_fetchers.py
git commit -m "feat(stock-dashboard): add yfinance fetcher for TAIEX, FX, stocks"
```

---

## Task 4: TWSE margin fetcher

**Files:**
- Modify: `stock/dashboard/tests/test_fetchers.py`
- Create: `stock/dashboard/backend/fetchers/margin.py`

The TWSE OpenAPI endpoint for daily margin trading totals:
`https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN`

Returns a JSON array where each element is a security. Sum field `融資金額小計` across all entries to get the total margin balance in thousands of TWD. Divide by 100000 to get 億元.

- [ ] **Step 1: Verify API response in terminal**

```bash
curl -s "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN" | python3 -c "
import json,sys
data = json.load(sys.stdin)
print('Keys:', list(data[0].keys()) if data else 'empty')
print('First row:', json.dumps(data[0], ensure_ascii=False, indent=2) if data else 'none')
"
```

Identify the field name for margin balance (expect `融資金額小計` or `融資餘額`). If the field name differs, update `margin.py` accordingly.

- [ ] **Step 2: Add test to `test_fetchers.py`**

```python
def test_fetch_margin_saves_indicator():
    fake_response = [
        {"融資金額小計": "5000000"},
        {"融資金額小計": "3000000"},
    ]
    with patch("fetchers.margin.requests.get") as mock_get:
        mock_get.return_value.json.return_value = fake_response
        mock_get.return_value.raise_for_status = MagicMock()
        from fetchers.margin import fetch_margin
        fetch_margin()
    row = db.get_latest_indicator("margin")
    assert row is not None
    # (5000000 + 3000000) * 1000 / 1e8 = 80 億
    assert abs(row["value"] - 80.0) < 1.0

def test_fetch_margin_handles_empty_response():
    with patch("fetchers.margin.requests.get") as mock_get:
        mock_get.return_value.json.return_value = []
        mock_get.return_value.raise_for_status = MagicMock()
        from fetchers.margin import fetch_margin
        fetch_margin()  # should not raise
```

- [ ] **Step 3: Run — expect failure**

```bash
python -m pytest tests/test_fetchers.py::test_fetch_margin_saves_indicator -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Implement `fetchers/margin.py`**

```python
# stock/dashboard/backend/fetchers/margin.py
import json, requests
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN"
# Field names as returned by TWSE API (verify with curl in Step 1)
BALANCE_FIELD = "融資金額小計"

def fetch_margin():
    resp = requests.get(TWSE_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        print("[margin] Empty response from TWSE")
        return
    total_thousands = sum(
        int(row.get(BALANCE_FIELD, "0").replace(",", ""))
        for row in data
        if row.get(BALANCE_FIELD)
    )
    # TWSE reports in thousands of TWD → convert to 億元 (100 million)
    total_yi = total_thousands * 1000 / 1e8
    save_indicator("margin", round(total_yi, 2), json.dumps({
        "unit": "億元",
    }))
```

- [ ] **Step 5: Run — expect pass**

```bash
python -m pytest tests/test_fetchers.py -v -k "margin"
```

Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add stock/dashboard/backend/fetchers/margin.py stock/dashboard/tests/test_fetchers.py
git commit -m "feat(stock-dashboard): add TWSE margin balance fetcher"
```

---

## Task 5: NDC indicator fetcher

**Files:**
- Modify: `stock/dashboard/tests/test_fetchers.py`
- Create: `stock/dashboard/backend/fetchers/ndc.py`

NDC publishes the composite indicator score monthly. Use their open data CSV endpoint:
`https://index.ndc.gov.tw/n/zh_tw/download/eco/cycle`

The CSV contains columns for year/month and the composite score (景氣綜合判斷分數). Score ranges: ≤9 blue, 10–16 yellow-blue, 17–23 green, 24–31 yellow-red, ≥32 red.

- [ ] **Step 1: Discover the actual CSV format**

```bash
curl -sL "https://index.ndc.gov.tw/n/zh_tw/download/eco/cycle" -o /tmp/ndc_sample.csv
head -5 /tmp/ndc_sample.csv
```

If the URL returns HTML instead of CSV, open https://index.ndc.gov.tw/n/zh_tw/data/eco in a browser, open DevTools → Network, look for XHR/fetch requests returning JSON/CSV with score data, and update `NDC_URL` and parsing logic in `ndc.py` to match.

- [ ] **Step 2: Add test to `test_fetchers.py`**

```python
def test_fetch_ndc_saves_indicator():
    fake_csv = "年月,景氣綜合判斷分數\n115年02月,24\n115年01月,23\n"
    with patch("fetchers.ndc.requests.get") as mock_get:
        mock_get.return_value.text = fake_csv
        mock_get.return_value.raise_for_status = MagicMock()
        from fetchers.ndc import fetch_ndc
        fetch_ndc()
    row = db.get_latest_indicator("ndc")
    assert row is not None
    assert row["value"] == 24.0
    extra = json.loads(row["extra_json"])
    assert extra["light"] == "黃燈"
```

- [ ] **Step 3: Run — expect failure**

```bash
python -m pytest tests/test_fetchers.py::test_fetch_ndc_saves_indicator -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Implement `fetchers/ndc.py`**

```python
# stock/dashboard/backend/fetchers/ndc.py
import csv, io, json, requests
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator

NDC_URL = "https://index.ndc.gov.tw/n/zh_tw/download/eco/cycle"
SCORE_COL = "景氣綜合判斷分數"
DATE_COL = "年月"

def _score_to_light(score: int) -> tuple[str, int]:
    if score <= 9:   return "藍燈", 1
    if score <= 16:  return "黃藍燈", 2
    if score <= 23:  return "綠燈", 3
    if score <= 31:  return "黃紅燈", 4
    return "紅燈", 5

def fetch_ndc():
    resp = requests.get(NDC_URL, timeout=20)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    rows = [r for r in reader if r.get(SCORE_COL, "").strip()]
    if not rows:
        print("[ndc] No data rows found")
        return
    latest = rows[0]  # assume newest first; reverse if needed
    score = int(latest[SCORE_COL].strip())
    light, light_code = _score_to_light(score)
    save_indicator("ndc", float(score), json.dumps({
        "light": light,
        "light_code": light_code,
        "period": latest.get(DATE_COL, ""),
    }))
```

- [ ] **Step 5: Run — expect pass**

```bash
python -m pytest tests/test_fetchers.py -v -k "ndc"
```

Expected: 1 passed

- [ ] **Step 6: Smoke-test against live NDC API**

```bash
cd stock/dashboard/backend
python3 -c "from fetchers.ndc import fetch_ndc; fetch_ndc(); import db; print(db.get_latest_indicator('ndc'))"
```

If parsing fails, check column names with the curl output from Step 1 and adjust `SCORE_COL`, `DATE_COL`, or the row-sorting order in `ndc.py`.

- [ ] **Step 7: Commit**

```bash
git add stock/dashboard/backend/fetchers/ndc.py stock/dashboard/tests/test_fetchers.py
git commit -m "feat(stock-dashboard): add NDC composite indicator fetcher"
```

---

## Task 6: Fear & Greed fetcher

**Files:**
- Modify: `stock/dashboard/tests/test_fetchers.py`
- Create: `stock/dashboard/backend/fetchers/fear_greed.py`

macromicro.me loads chart data via their internal API. Discover the endpoint from browser DevTools.

- [ ] **Step 1: Discover the API endpoint**

1. Open https://www.macromicro.me/collections/46/tw-stock-relative/128747/taiwan-mm-fear-and-greed-index-vs-taiex in Chrome.
2. Open DevTools → Network → filter by `Fetch/XHR`.
3. Reload the page. Look for a request that returns JSON with a `value` or `data` array containing the fear/greed numbers.
4. Note the URL, any required headers (`Referer`, `Cookie`, etc.), and the JSON structure.
5. Try the URL with curl:

```bash
curl -s "https://api.macromicro.me/charts/128747" \
  -H "Referer: https://www.macromicro.me/" \
  | python3 -m json.tool | head -50
```

Update `FEAR_GREED_URL` and parsing in Step 4 to match what you find.

- [ ] **Step 2: Add test to `test_fetchers.py`**

```python
def test_fetch_fear_greed_saves_indicator():
    # Adjust this fake response to match the actual API structure found in Step 1
    fake_json = {"data": [[1745000000, 58], [1744000000, 52]]}
    with patch("fetchers.fear_greed.requests.get") as mock_get:
        mock_get.return_value.json.return_value = fake_json
        mock_get.return_value.raise_for_status = MagicMock()
        from fetchers.fear_greed import fetch_fear_greed
        fetch_fear_greed()
    row = db.get_latest_indicator("fear_greed")
    assert row is not None
    assert row["value"] == 58.0
    extra = json.loads(row["extra_json"])
    assert "label" in extra
```

- [ ] **Step 3: Run — expect failure**

```bash
python -m pytest tests/test_fetchers.py::test_fetch_fear_greed_saves_indicator -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Implement `fetchers/fear_greed.py`**

```python
# stock/dashboard/backend/fetchers/fear_greed.py
import json, requests
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator

# Update these after completing Step 1 discovery
FEAR_GREED_URL = "https://api.macromicro.me/charts/128747"
HEADERS = {"Referer": "https://www.macromicro.me/"}

def _value_to_label(v: float) -> str:
    if v < 25:  return "極度恐懼"
    if v < 45:  return "恐懼"
    if v < 55:  return "中立"
    if v < 75:  return "貪婪"
    return "極度貪婪"

def fetch_fear_greed():
    resp = requests.get(FEAR_GREED_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    # Expected: {"data": [[timestamp_ms, value], ...]} — newest last or first
    # Adjust indexing based on actual response structure
    series = payload.get("data", [])
    if not series:
        print("[fear_greed] Empty data from macromicro.me")
        return
    # Take the latest entry (try last element first, then first)
    latest_entry = series[-1] if isinstance(series[-1], (list, tuple)) else series[0]
    value = float(latest_entry[1])
    save_indicator("fear_greed", value, json.dumps({"label": _value_to_label(value)}))
```

- [ ] **Step 5: Run — expect pass**

```bash
python -m pytest tests/test_fetchers.py -v -k "fear_greed"
```

Expected: 1 passed

- [ ] **Step 6: Smoke-test against live API**

```bash
cd stock/dashboard/backend
python3 -c "from fetchers.fear_greed import fetch_fear_greed; fetch_fear_greed(); import db; print(db.get_latest_indicator('fear_greed'))"
```

If parsing fails, adjust `series` extraction and `latest_entry` indexing to match the actual response.

- [ ] **Step 7: Commit**

```bash
git add stock/dashboard/backend/fetchers/fear_greed.py stock/dashboard/tests/test_fetchers.py
git commit -m "feat(stock-dashboard): add MM fear & greed fetcher"
```

---

## Task 7: FastAPI app + API endpoints

**Files:**
- Create: `stock/dashboard/backend/app.py`
- Create: `stock/dashboard/tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

```python
# stock/dashboard/tests/test_api.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
os.environ["DB_PATH"] = ":memory:"

import db
db.init_db()
import json
from datetime import datetime

from fastapi.testclient import TestClient

# Seed data before importing app so startup doesn't clobber memory DB
db.save_indicator("taiex",  21458.0, json.dumps({"change_pct": 0.58, "prev_close": 21334.0}))
db.save_indicator("fx",     32.15,   json.dumps({"change_pct": 0.12, "prev_close": 32.11}))
db.save_indicator("fear_greed", 58.0, json.dumps({"label": "貪婪"}))
db.save_indicator("margin", 2341.0,  json.dumps({"unit": "億元"}))
db.save_indicator("ndc",    24.0,    json.dumps({"light": "黃燈", "light_code": 4}))
db.add_watched_ticker("0050.TW")
db.save_stock_snapshot("0050.TW", 198.35, 1.15, 0.58, "TWD", "元大台灣50")

from app import app
client = TestClient(app)

def test_dashboard_returns_all_indicators():
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    data = r.json()
    for key in ["taiex", "fx", "fear_greed", "margin", "ndc"]:
        assert key in data
        assert "value" in data[key]
        assert "timestamp" in data[key]

def test_history_returns_list():
    r = client.get("/api/history/taiex?range=3M")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert rows[0]["value"] == 21458.0

def test_history_unknown_indicator_returns_404():
    r = client.get("/api/history/unknown")
    assert r.status_code == 404

def test_get_stocks_returns_watchlist():
    r = client.get("/api/stocks")
    assert r.status_code == 200
    stocks = r.json()
    tickers = [s["ticker"] for s in stocks]
    assert "0050.TW" in tickers

def test_add_and_delete_stock():
    r = client.post("/api/stocks", json={"ticker": "2330.tw"})
    assert r.status_code == 200
    tickers = db.get_watched_tickers()
    assert "2330.TW" in tickers  # normalized to uppercase

    r = client.delete("/api/stocks/2330.TW")
    assert r.status_code == 200
    assert "2330.TW" not in db.get_watched_tickers()

def test_refresh_known_indicator_succeeds():
    from unittest.mock import patch
    with patch("app.FETCHERS") as mock_fetchers:
        mock_fetchers.__contains__ = lambda self, k: k == "taiex"
        mock_fetchers.__getitem__ = lambda self, k: (lambda: None)
        r = client.post("/api/refresh/taiex")
        assert r.status_code == 200

def test_refresh_unknown_indicator_returns_404():
    r = client.post("/api/refresh/bogus")
    assert r.status_code == 404
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest tests/test_api.py -v
```

Expected: `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Implement `app.py`**

```python
# stock/dashboard/backend/app.py
import json
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import (
    init_db, get_latest_indicator, get_indicator_history,
    get_watched_tickers, get_latest_stock,
    add_watched_ticker, remove_watched_ticker,
)
from fetchers.yfinance_fetcher import fetch_taiex, fetch_fx, fetch_all_stocks
from fetchers.fear_greed import fetch_fear_greed
from fetchers.margin import fetch_margin
from fetchers.ndc import fetch_ndc

app = FastAPI(title="Stock Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://paul-learning.dev"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

RANGE_DELTAS: dict[str, timedelta] = {
    "1M":  timedelta(days=30),
    "3M":  timedelta(days=90),
    "6M":  timedelta(days=180),
    "1Y":  timedelta(days=365),
    "3Y":  timedelta(days=1095),
}

FETCHERS: dict[str, callable] = {
    "taiex":      fetch_taiex,
    "fx":         fetch_fx,
    "fear_greed": fetch_fear_greed,
    "margin":     fetch_margin,
    "ndc":        fetch_ndc,
    "stocks":     fetch_all_stocks,
}

INDICATOR_NAMES = ["taiex", "fx", "fear_greed", "margin", "ndc"]

@app.on_event("startup")
def startup():
    init_db()
    from scheduler import start_scheduler
    start_scheduler()

@app.get("/api/dashboard")
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

@app.get("/api/history/{indicator}")
def history(indicator: str, range: str = "3M"):
    if indicator not in INDICATOR_NAMES:
        raise HTTPException(status_code=404, detail="Unknown indicator")
    delta = RANGE_DELTAS.get(range, RANGE_DELTAS["3M"])
    since = datetime.utcnow() - delta
    rows = get_indicator_history(indicator, since)
    return [{"timestamp": r["timestamp"], "value": r["value"]} for r in rows]

@app.get("/api/stocks")
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

class AddStockRequest(BaseModel):
    ticker: str

@app.post("/api/stocks")
def add_stock(req: AddStockRequest):
    add_watched_ticker(req.ticker.upper())
    try:
        fetch_all_stocks()
    except Exception as e:
        print(f"[add_stock] Fetch error: {e}")
    return {"ok": True}

@app.delete("/api/stocks/{ticker}")
def delete_stock(ticker: str):
    remove_watched_ticker(ticker.upper())
    return {"ok": True}

@app.post("/api/refresh/{indicator}")
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

- [ ] **Step 4: Run — expect pass**

```bash
python -m pytest tests/test_api.py -v
```

Expected: 7 passed

- [ ] **Step 5: Smoke-test locally**

```bash
cd stock/dashboard/backend
uvicorn app:app --reload --port 8001
# in another terminal:
curl http://localhost:8001/api/dashboard | python3 -m json.tool
```

- [ ] **Step 6: Commit**

```bash
git add stock/dashboard/backend/app.py stock/dashboard/tests/test_api.py
git commit -m "feat(stock-dashboard): add FastAPI app with all API endpoints"
```

---

## Task 8: Scheduler

**Files:**
- Create: `stock/dashboard/backend/scheduler.py`

- [ ] **Step 1: Implement `scheduler.py`**

```python
# stock/dashboard/backend/scheduler.py
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from fetchers.yfinance_fetcher import fetch_taiex, fetch_fx, fetch_all_stocks
from fetchers.fear_greed import fetch_fear_greed
from fetchers.margin import fetch_margin
from fetchers.ndc import fetch_ndc
from db import purge_old_data

TST = pytz.timezone("Asia/Taipei")

def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=TST)

    # Every 15 minutes — yfinance returns stale data outside market hours so
    # over-fetching is harmless and simplifies the schedule
    scheduler.add_job(fetch_taiex,      "interval", minutes=15, id="taiex",  replace_existing=True)
    scheduler.add_job(fetch_fx,         "interval", minutes=15, id="fx",     replace_existing=True)
    scheduler.add_job(fetch_all_stocks, "interval", minutes=15, id="stocks", replace_existing=True)

    # Daily 08:00 TST
    scheduler.add_job(fetch_fear_greed, CronTrigger(hour=8,  minute=0, timezone=TST), id="fear_greed", replace_existing=True)

    # Daily 18:00 TST (after TWSE settlement)
    scheduler.add_job(fetch_margin,     CronTrigger(hour=18, minute=0, timezone=TST), id="margin",     replace_existing=True)

    # Monthly on the 1st at 09:00 TST
    scheduler.add_job(fetch_ndc,        CronTrigger(day=1,  hour=9,  minute=0, timezone=TST), id="ndc", replace_existing=True)

    # Weekly cleanup of data older than 3 years
    scheduler.add_job(purge_old_data,   CronTrigger(day_of_week="sun", hour=0, timezone=TST), id="cleanup", replace_existing=True)

    scheduler.start()
    return scheduler
```

- [ ] **Step 2: Verify scheduler starts with the app**

```bash
cd stock/dashboard/backend
uvicorn app:app --port 8001
# should start without errors; logs will show APScheduler starting
```

- [ ] **Step 3: Commit**

```bash
git add stock/dashboard/backend/scheduler.py
git commit -m "feat(stock-dashboard): add APScheduler job definitions"
```

---

## Task 9: Frontend

**Files:**
- Create: `stock/dashboard/frontend/index.html`

- [ ] **Step 1: Create `index.html`**

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>市場總覽</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1117; color: #e2e8f0; padding: 20px; font-size: 14px; }
.top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.top-bar h1 { font-size: 18px; font-weight: 700; color: #fff; }
.update-time { font-size: 12px; color: #94a3b8; }
.range-bar { display: flex; align-items: center; gap: 6px; margin-bottom: 14px; }
.range-label { font-size: 12px; color: #94a3b8; margin-right: 4px; }
.range-btn { background: transparent; border: 1px solid #2d3348; border-radius: 5px; color: #94a3b8; font-size: 13px; padding: 4px 14px; cursor: pointer; }
.range-btn.active { background: #3b82f6; border-color: #3b82f6; color: #fff; font-weight: 600; }
.grid-indicators { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 14px; }
.card { background: #1e2130; border: 1px solid #2d3348; border-radius: 10px; padding: 16px; }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.card-label { font-size: 13px; color: #cbd5e1; text-transform: uppercase; letter-spacing: .05em; }
.card-value { font-size: 34px; font-weight: 700; color: #fff; }
.card-sub { font-size: 13px; color: #94a3b8; margin-top: 8px; }
.refresh-btn { background: transparent; border: 1px solid #2d3348; border-radius: 5px; color: #94a3b8; font-size: 13px; padding: 3px 8px; cursor: pointer; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 13px; font-weight: 600; }
.badge-up   { background: rgba(74,222,128,.15); color: #4ade80; }
.badge-down { background: rgba(248,113,.15); color: #f87171; }
.badge-neutral { background: rgba(251,191,36,.15); color: #fbbf24; }
.stat-row { display: flex; align-items: flex-end; gap: 10px; margin-bottom: 12px; }
.up { color: #4ade80; } .down { color: #f87171; } .neutral { color: #fbbf24; }
.chart-wrap { position: relative; height: 100px; }
.gauge-track { height: 6px; border-radius: 4px; background: linear-gradient(to right, #f87171, #fbbf24 50%, #4ade80); position: relative; margin: 0 0 4px; }
.gauge-marker { position: absolute; top: -5px; width: 14px; height: 14px; border-radius: 50%; background: #fff; border: 2px solid #0f1117; transform: translateX(-50%); transition: left .3s; }
.gauge-labels { display: flex; justify-content: space-between; font-size: 12px; color: #94a3b8; margin-bottom: 8px; }
.ndc-inner { display: grid; grid-template-columns: auto 1fr; gap: 20px; align-items: start; }
.ndc-lights { display: flex; gap: 6px; margin: 6px 0 4px; }
.light { width: 12px; height: 12px; border-radius: 50%; background: #2d3348; }
.light.on-blue   { background: #60a5fa; box-shadow: 0 0 6px #60a5fa; }
.light.on-yelblue{ background: #34d399; box-shadow: 0 0 6px #34d399; }
.light.on-green  { background: #4ade80; box-shadow: 0 0 6px #4ade80; }
.light.on-yellred{ background: #fbbf24; box-shadow: 0 0 6px #fbbf24; }
.light.on-red    { background: #f87171; box-shadow: 0 0 6px #f87171; }
.stock-table { width: 100%; border-collapse: collapse; margin-top: 8px; }
.stock-table th { font-size: 11px; color: #94a3b8; text-transform: uppercase; padding: 5px 8px; border-bottom: 1px solid #2d3348; text-align: left; }
.stock-table td { padding: 7px 8px; border-bottom: 1px solid #1a1f2e; font-size: 13px; }
.stock-table tr:last-child td { border-bottom: none; }
.ticker { font-weight: 600; color: #60a5fa; }
.r { text-align: right; }
.add-row { display: flex; gap: 8px; margin-top: 12px; }
.add-input { flex: 1; background: #0f1117; border: 1px solid #2d3348; border-radius: 6px; padding: 7px 10px; color: #e2e8f0; font-size: 13px; }
.add-input::placeholder { color: #94a3b8; }
.add-btn { background: #3b82f6; color: #fff; border: none; border-radius: 6px; padding: 7px 14px; font-size: 13px; cursor: pointer; }
.del-btn { background: transparent; border: 1px solid #2d3348; border-radius: 4px; padding: 3px 7px; font-size: 11px; color: #94a3b8; cursor: pointer; }
.section-title { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: .05em; }
@media (max-width: 900px) { .grid-indicators { grid-template-columns: 1fr 1fr; } }
@media (max-width: 600px) { .grid-indicators { grid-template-columns: 1fr; } }
</style>
</head>
<body>

<div class="top-bar">
  <h1>📊 市場總覽</h1>
  <span class="update-time" id="update-time">載入中…</span>
</div>

<div class="range-bar">
  <span class="range-label">時間區間：</span>
  <button class="range-btn" data-range="1M">1 個月</button>
  <button class="range-btn active" data-range="3M">3 個月</button>
  <button class="range-btn" data-range="6M">6 個月</button>
  <button class="range-btn" data-range="1Y">1 年</button>
  <button class="range-btn" data-range="3Y">3 年</button>
</div>

<div class="grid-indicators">

  <!-- 加權指數 -->
  <div class="card">
    <div class="card-header">
      <span class="card-label">加權指數</span>
      <button class="refresh-btn" onclick="refreshIndicator('taiex')">↻ 更新</button>
    </div>
    <div class="stat-row">
      <div class="card-value" id="taiex-value">—</div>
      <span class="badge" id="taiex-badge"></span>
    </div>
    <div class="chart-wrap"><canvas id="chart-taiex"></canvas></div>
    <div class="card-sub" id="taiex-sub"></div>
  </div>

  <!-- MM 恐懼與貪婪 -->
  <div class="card">
    <div class="card-header">
      <span class="card-label">MM 恐懼與貪婪指數</span>
      <button class="refresh-btn" onclick="refreshIndicator('fear_greed')">↻ 更新</button>
    </div>
    <div class="stat-row">
      <div class="card-value" id="fg-value">—</div>
      <span class="badge" id="fg-badge"></span>
    </div>
    <div class="gauge-track"><div class="gauge-marker" id="fg-marker" style="left:50%"></div></div>
    <div class="gauge-labels"><span>恐懼</span><span>貪婪</span></div>
    <div class="chart-wrap"><canvas id="chart-fear_greed"></canvas></div>
    <div class="card-sub" id="fg-sub"></div>
  </div>

  <!-- 台股融資餘額 -->
  <div class="card">
    <div class="card-header">
      <span class="card-label">台股融資餘額</span>
      <button class="refresh-btn" onclick="refreshIndicator('margin')">↻ 更新</button>
    </div>
    <div class="stat-row">
      <div class="card-value" id="margin-value">—</div>
      <span class="badge" id="margin-badge"></span>
    </div>
    <div class="chart-wrap"><canvas id="chart-margin"></canvas></div>
    <div class="card-sub" id="margin-sub"></div>
  </div>

  <!-- 國發會景氣指標 -->
  <div class="card">
    <div class="card-header">
      <span class="card-label">國發會景氣指標</span>
      <button class="refresh-btn" onclick="refreshIndicator('ndc')">↻ 更新</button>
    </div>
    <div class="ndc-inner">
      <div>
        <div style="font-size:13px;color:#94a3b8;margin-bottom:4px">景氣燈號</div>
        <div class="stat-row" style="margin-bottom:6px">
          <div class="card-value" id="ndc-value">—</div>
          <span class="badge" id="ndc-badge"></span>
        </div>
        <div class="ndc-lights">
          <div class="light" id="ndc-l1"></div>
          <div class="light" id="ndc-l2"></div>
          <div class="light" id="ndc-l3"></div>
          <div class="light" id="ndc-l4"></div>
          <div class="light" id="ndc-l5"></div>
        </div>
        <div style="font-size:10px;color:#94a3b8;margin-top:2px">藍│黃藍│綠│黃紅│紅</div>
        <div class="card-sub" id="ndc-sub" style="margin-top:8px"></div>
      </div>
      <div>
        <div style="font-size:13px;color:#94a3b8;margin-bottom:4px">分數走勢</div>
        <div class="chart-wrap"><canvas id="chart-ndc"></canvas></div>
      </div>
    </div>
  </div>

  <!-- 台幣兌美金 -->
  <div class="card">
    <div class="card-header">
      <span class="card-label">台幣兌美金</span>
      <button class="refresh-btn" onclick="refreshIndicator('fx')">↻ 更新</button>
    </div>
    <div class="stat-row">
      <div class="card-value" id="fx-value">—</div>
      <span class="badge" id="fx-badge"></span>
    </div>
    <div class="chart-wrap"><canvas id="chart-fx"></canvas></div>
    <div class="card-sub" id="fx-sub"></div>
  </div>

</div>

<!-- 自選股 -->
<div class="card">
  <div class="section-title">自選股票 / ETF / 虛擬幣</div>
  <table class="stock-table">
    <thead><tr>
      <th>代號</th><th>名稱</th>
      <th class="r">價格</th><th class="r">漲跌</th><th class="r">漲跌幅</th><th></th>
    </tr></thead>
    <tbody id="stock-tbody"></tbody>
  </table>
  <div class="add-row">
    <input class="add-input" id="add-ticker-input" placeholder="輸入代號，例如 2317.TW、AAPL、ETH-USD…">
    <button class="add-btn" onclick="addStock()">+ 新增</button>
  </div>
</div>

<script>
const API_BASE = 'https://api.paul-learning.dev';
let currentRange = '3M';
const charts = {};

// ── Chart helpers ──────────────────────────────────────────────────────────
const CHART_DEFAULTS = {
  type: 'line',
  options: {
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#1a1f2e', borderColor: '#3b82f6', borderWidth: 1,
        titleColor: '#94a3b8', bodyColor: '#e2e8f0',
        callbacks: { title: items => items[0].label }
      }
    },
    scales: {
      x: { grid: { color: '#2d3348' }, ticks: { color: '#94a3b8', maxTicksLimit: 4 } },
      y: { grid: { color: '#2d3348' }, ticks: { color: '#94a3b8' } }
    }
  }
};

function makeChart(id, color, yLabel) {
  const ctx = document.getElementById('chart-' + id).getContext('2d');
  charts[id] = new Chart(ctx, {
    ...JSON.parse(JSON.stringify(CHART_DEFAULTS)),
    data: {
      labels: [],
      datasets: [{
        data: [], borderColor: color,
        backgroundColor: color + '20', fill: true,
        tension: 0.3, pointRadius: 0, pointHoverRadius: 5,
        borderWidth: 2,
      }]
    }
  });
  charts[id].options.scales.y.title = { display: true, text: yLabel, color: '#94a3b8' };
  charts[id].options.scales.x.title = { display: true, text: '日期', color: '#94a3b8' };
  return charts[id];
}

function updateChart(id, rows) {
  const c = charts[id];
  if (!c) return;
  c.data.labels = rows.map(r => r.timestamp.slice(0, 10));
  c.data.datasets[0].data = rows.map(r => r.value);
  c.update('none');
}

// ── Badge helpers ──────────────────────────────────────────────────────────
function setBadge(el, changePct) {
  if (changePct == null) { el.textContent = ''; return; }
  const up = changePct >= 0;
  el.textContent = (up ? '▲ +' : '▼ ') + changePct.toFixed(2) + '%';
  el.className = 'badge ' + (up ? 'badge-up' : 'badge-down');
}

function fmtDate(iso) {
  return iso ? iso.slice(0, 10) : '';
}

// ── Dashboard update ───────────────────────────────────────────────────────
async function loadDashboard() {
  const data = await fetch(API_BASE + '/api/dashboard').then(r => r.json());

  // TAIEX
  if (data.taiex) {
    document.getElementById('taiex-value').textContent = data.taiex.value.toLocaleString();
    setBadge(document.getElementById('taiex-badge'), data.taiex.extra?.change_pct);
    document.getElementById('taiex-sub').textContent =
      '前收 ' + (data.taiex.extra?.prev_close?.toLocaleString() ?? '—') +
      ' · 更新 ' + fmtDate(data.taiex.timestamp);
  }

  // Fear & Greed
  if (data.fear_greed) {
    const v = data.fear_greed.value;
    document.getElementById('fg-value').textContent = v;
    document.getElementById('fg-value').className = 'card-value ' + fgClass(v);
    const badge = document.getElementById('fg-badge');
    badge.textContent = data.fear_greed.extra?.label ?? '';
    badge.className = 'badge badge-neutral';
    document.getElementById('fg-marker').style.left = v + '%';
    document.getElementById('fg-sub').textContent = '更新 ' + fmtDate(data.fear_greed.timestamp);
  }

  // Margin
  if (data.margin) {
    document.getElementById('margin-value').textContent = data.margin.value.toFixed(0) + ' 億';
    document.getElementById('margin-sub').textContent = '更新 ' + fmtDate(data.margin.timestamp);
  }

  // NDC
  if (data.ndc) {
    const score = data.ndc.value;
    const light = data.ndc.extra?.light ?? '';
    const code  = data.ndc.extra?.light_code ?? 0;
    document.getElementById('ndc-value').textContent = score + ' 分';
    const b = document.getElementById('ndc-badge');
    b.textContent = light;
    b.className = 'badge badge-neutral';
    ['on-blue','on-yelblue','on-green','on-yellred','on-red'].forEach((cls, i) => {
      const el = document.getElementById('ndc-l' + (i+1));
      el.className = 'light' + (code === i+1 ? ' ' + cls : '');
    });
    document.getElementById('ndc-sub').textContent =
      (data.ndc.extra?.period ?? '') + ' · 每月更新';
  }

  // FX
  if (data.fx) {
    document.getElementById('fx-value').textContent = data.fx.value.toFixed(2);
    setBadge(document.getElementById('fx-badge'), data.fx.extra?.change_pct);
    document.getElementById('fx-sub').textContent =
      '前收 ' + (data.fx.extra?.prev_close ?? '—') +
      ' · 更新 ' + fmtDate(data.fx.timestamp);
  }

  document.getElementById('update-time').textContent =
    '上次更新：' + new Date().toLocaleTimeString('zh-TW');
}

function fgClass(v) {
  if (v < 45) return 'down';
  if (v > 55) return 'up';
  return 'neutral';
}

async function loadHistories() {
  const indicators = ['taiex', 'fear_greed', 'margin', 'ndc', 'fx'];
  const units = { taiex: '點', fear_greed: '指數', margin: '億元', ndc: '分', fx: 'TWD' };
  const colors = { taiex: '#4ade80', fear_greed: '#fbbf24', margin: '#60a5fa', ndc: '#fbbf24', fx: '#a78bfa' };

  for (const ind of indicators) {
    if (!charts[ind]) makeChart(ind, colors[ind], units[ind]);
    const rows = await fetch(API_BASE + '/api/history/' + ind + '?range=' + currentRange).then(r => r.json());
    updateChart(ind, rows);
  }
}

// ── Stock watchlist ────────────────────────────────────────────────────────
async function loadStocks() {
  const stocks = await fetch(API_BASE + '/api/stocks').then(r => r.json());
  const tbody = document.getElementById('stock-tbody');
  tbody.innerHTML = '';
  for (const s of stocks) {
    const up = (s.change_pct ?? 0) >= 0;
    const cls = up ? 'up' : 'down';
    const arrow = up ? '▲' : '▼';
    tbody.insertAdjacentHTML('beforeend', `
      <tr>
        <td><span class="ticker">${s.ticker}</span></td>
        <td>${s.name ?? ''}</td>
        <td class="r">${s.price != null ? s.price.toLocaleString() + ' ' + (s.currency ?? '') : '—'}</td>
        <td class="r ${cls}">${s.change != null ? arrow + ' ' + Math.abs(s.change).toFixed(2) : '—'}</td>
        <td class="r ${cls}">${s.change_pct != null ? (up?'+':'') + s.change_pct.toFixed(2) + '%' : '—'}</td>
        <td><button class="del-btn" onclick="deleteStock('${s.ticker}')">✕</button></td>
      </tr>`);
  }
}

async function addStock() {
  const input = document.getElementById('add-ticker-input');
  const ticker = input.value.trim();
  if (!ticker) return;
  await fetch(API_BASE + '/api/stocks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticker }),
  });
  input.value = '';
  loadStocks();
}

async function deleteStock(ticker) {
  await fetch(API_BASE + '/api/stocks/' + encodeURIComponent(ticker), { method: 'DELETE' });
  loadStocks();
}

// ── Manual refresh ─────────────────────────────────────────────────────────
async function refreshIndicator(indicator) {
  await fetch(API_BASE + '/api/refresh/' + indicator, { method: 'POST' });
  loadDashboard();
  loadHistories();
}

// ── Range selector ─────────────────────────────────────────────────────────
document.querySelectorAll('.range-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentRange = btn.dataset.range;
    loadHistories();
  });
});

// ── Add stock on Enter ─────────────────────────────────────────────────────
document.getElementById('add-ticker-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') addStock();
});

// ── Bootstrap ─────────────────────────────────────────────────────────────
(async () => {
  await loadDashboard();
  await loadHistories();
  await loadStocks();
  setInterval(async () => {
    await loadDashboard();
    await loadStocks();
  }, 60_000);
})();
</script>
</body>
</html>
```

- [ ] **Step 2: Test the frontend against local backend**

```bash
# Start backend with CORS also allowing localhost for local testing
cd stock/dashboard/backend
uvicorn app:app --port 8001

# In app.py temporarily add "http://localhost:8001" to allow_origins, or use:
# Open stock/dashboard/frontend/index.html in browser with local server:
python3 -m http.server 9000 --directory stock/dashboard/frontend
# Open http://localhost:9000 — check that charts render and data loads
```

Verify: all 5 indicator cards show values, charts render, range buttons change chart data, stock add/delete works.

- [ ] **Step 3: Commit**

```bash
git add stock/dashboard/frontend/index.html
git commit -m "feat(stock-dashboard): add frontend dashboard (index.html)"
```

---

## Task 10: Backend deployment

**Files:**
- Create: `stock/dashboard/stock-dashboard.service`
- Create: `stock/dashboard/deploy.sh`

- [ ] **Step 1: Create systemd service file**

```ini
# stock/dashboard/stock-dashboard.service
[Unit]
Description=Stock Dashboard API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/stock-dashboard/backend
ExecStart=/opt/stock-dashboard/backend/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
Environment=DB_PATH=/opt/stock-dashboard/backend/stock_dashboard.db

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create `deploy.sh`**

```bash
#!/usr/bin/env bash
# stock/dashboard/deploy.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")"   # repo root

VPS=root@$VPS_HOST
REMOTE=/opt/stock-dashboard

echo "==> Syncing code to VPS..."
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='stock_dashboard.db' \
  stock/dashboard/backend/ $VPS:$REMOTE/backend/

echo "==> Installing dependencies..."
ssh $VPS "
  cd $REMOTE/backend
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
"

echo "==> Installing systemd service..."
ssh $VPS "
  cp $REMOTE/backend/../stock-dashboard.service /etc/systemd/system/stock-dashboard.service 2>/dev/null || true
  systemctl daemon-reload
  systemctl enable stock-dashboard
  systemctl restart stock-dashboard
  systemctl status stock-dashboard --no-pager
"

echo "==> Done. API live at https://api.paul-learning.dev"
```

- [ ] **Step 3: Copy service file and deploy**

```bash
cp stock/dashboard/stock-dashboard.service stock/dashboard/backend/../stock-dashboard.service
chmod +x stock/dashboard/deploy.sh
bash stock/dashboard/deploy.sh
```

- [ ] **Step 4: Verify backend is live**

```bash
curl https://api.paul-learning.dev/api/dashboard | python3 -m json.tool
```

Expected: JSON with keys `taiex`, `fx`, `fear_greed`, `margin`, `ndc` (some may be empty on first deploy until scheduler runs; trigger manually):

```bash
curl -X POST https://api.paul-learning.dev/api/refresh/taiex
curl -X POST https://api.paul-learning.dev/api/refresh/fx
curl https://api.paul-learning.dev/api/dashboard | python3 -m json.tool
```

- [ ] **Step 5: Commit**

```bash
git add stock/dashboard/stock-dashboard.service stock/dashboard/deploy.sh
git commit -m "feat(stock-dashboard): add VPS deploy script and systemd service"
```

---

## Task 11: GitHub Actions — frontend deployment

**Files:**
- Create: `.github/workflows/deploy-stock-dashboard.yml`

- [ ] **Step 1: Create workflow**

```yaml
# .github/workflows/deploy-stock-dashboard.yml
name: Deploy Stock Dashboard to GitHub Pages

on:
  push:
    branches: [master]
    paths:
      - 'stock/dashboard/frontend/**'
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Assemble site
        run: |
          # Merge with travel app output (already built separately)
          mkdir -p _site/stock
          cp stock/dashboard/frontend/index.html _site/stock/index.html

      - name: Build travel app
        working-directory: travel/2026_austria_czechia
        run: npm ci && npm run build

      - name: Add travel app to site
        run: |
          mkdir -p _site/travel/2026_austria_czechia
          cp -r travel/2026_austria_czechia/dist/. _site/travel/2026_austria_czechia/

      - uses: actions/configure-pages@v4

      - uses: actions/upload-pages-artifact@v3
        with:
          path: '_site'

      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Update existing `deploy-pages.yml` to also include the stock dashboard**

The existing `deploy-pages.yml` only watches `travel/**`. The new workflow covers both. Disable the old one to avoid conflicts:

```bash
mv .github/workflows/deploy-pages.yml .github/workflows/deploy-pages.yml.disabled
```

- [ ] **Step 3: Push and verify**

```bash
git add .github/workflows/deploy-stock-dashboard.yml
git add .github/workflows/deploy-pages.yml.disabled
git commit -m "feat(stock-dashboard): add GitHub Actions deployment workflow"
git push origin master
```

Open `https://github.com/<your-repo>/actions` and confirm the workflow runs successfully.

Then visit **https://paul-learning.dev/stock** — the dashboard should load and show live data.

- [ ] **Step 4: Seed initial watchlist**

```bash
curl -X POST https://api.paul-learning.dev/api/stocks -H "Content-Type: application/json" -d '{"ticker":"0050.TW"}'
curl -X POST https://api.paul-learning.dev/api/stocks -H "Content-Type: application/json" -d '{"ticker":"2330.TW"}'
curl -X POST https://api.paul-learning.dev/api/stocks -H "Content-Type: application/json" -d '{"ticker":"VOO"}'
```

---

## Self-Review Notes

- **Spec coverage:** All 6 API endpoints implemented (Task 7). All 5 data sources with fetchers (Tasks 3–6). Scheduler (Task 8). Frontend with Chart.js, range selector, tooltip, stock CRUD (Task 9). Systemd + deploy script (Task 10). GitHub Actions (Task 11). ✓
- **Data retention / purge:** `purge_old_data` in scheduler weekly job. ✓
- **CORS:** `allow_origins=["https://paul-learning.dev"]` in `app.py`. ✓
- **NDC / fear_greed discovery steps:** Tasks 5 & 6 include explicit "smoke-test against live API" steps and instructions to adjust parsing if the response format differs. ✓
- **Type consistency:** `save_stock_snapshot` signature matches across `db.py`, `yfinance_fetcher.py`, and test calls. ✓
