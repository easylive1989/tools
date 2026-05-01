# Stock Dashboard 警示季/年指標 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** YoY 警示擴展到季/年粒度。新 7 個 indicator_key(季 5、年 2),完整覆蓋基本面投資者最常看的 EPS YoY、營收 YoY、現金股利 YoY 等訊號。

**Architecture:** 沿用 P4 + MVP 既有 schema(condition / indicator_key 字串),僅擴展常數 set + engine routing + fetcher trigger 整合 + scheduler 拉取 + UI options。

**Tech Stack:** Python 3 / SQLite / FastAPI / pytest / 純 HTML+JS

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `stock/dashboard/backend/alerts.py` | Modify | 加 `QUARTERLY_INDICATOR_TYPES` / `YEARLY_INDICATOR_KEYS` constants + 2 個 helpers + check_alerts yoy routing 擴展 |
| `stock/dashboard/backend/fetchers/fundamentals_stock.py` | Modify | `fetch_stock_financial` 寫入後若新季觸發對應 quarterly indicator;`fetch_stock_dividend` 寫入後若新年觸發 yearly;`fetch_watchlist_stock_daily` 加 3 個 fetcher 呼叫 |
| `stock/dashboard/backend/app.py` | Modify | `STOCK_QUARTERLY_INDICATOR_KEYS` / `STOCK_YEARLY_INDICATOR_KEYS` / `STOCK_YOY_COMPATIBLE_KEYS` 常數;`create_alert` 交叉驗證更新 |
| `stock/dashboard/frontend/index.html` | Modify | indicator-key select 加 7 options;`STOCK_INDICATOR_LABELS` 加 7 個 labels |
| `stock/dashboard/tests/test_alerts.py` | Modify | helpers + routing 測試 |
| `stock/dashboard/tests/test_api.py` | Modify | API 驗證測試 |

---

## Task 1: 純函式 helpers `_get_stock_quarterly_yoy` + `_get_stock_yearly_yoy`

**Files:**
- Modify: `stock/dashboard/backend/alerts.py`
- Modify: `stock/dashboard/tests/test_alerts.py`

### Step 1.1: 寫純函式失敗測試

**File:** `stock/dashboard/tests/test_alerts.py`(append at end)

```python
from alerts import _get_stock_quarterly_yoy, _get_stock_yearly_yoy


def test_get_stock_quarterly_yoy_eps_positive():
    db.save_financial_quarterly_rows([
        {"ticker": "2330.TW", "date": "2025-03-31", "report_type": "income", "type": "EPS",      "value": 10.0},
        {"ticker": "2330.TW", "date": "2026-03-31", "report_type": "income", "type": "EPS",      "value": 15.0},
        # 不相關 type / report_type 不應影響
        {"ticker": "2330.TW", "date": "2026-03-31", "report_type": "income", "type": "Revenue",  "value": 999_999},
        {"ticker": "2330.TW", "date": "2026-03-31", "report_type": "balance", "type": "TotalAssets", "value": 999_999},
    ])
    yoy = _get_stock_quarterly_yoy("2330.TW", "q_eps")
    # (15-10)/10*100 = 50.0
    assert yoy == pytest.approx(50.0, abs=0.01)


def test_get_stock_quarterly_yoy_operating_cf():
    db.save_financial_quarterly_rows([
        {"ticker": "2330.TW", "date": "2025-06-30", "report_type": "cash_flow",
         "type": "CashFlowsFromOperatingActivities", "value": 1_000_000_000},
        {"ticker": "2330.TW", "date": "2026-06-30", "report_type": "cash_flow",
         "type": "CashFlowsFromOperatingActivities", "value": 1_500_000_000},
    ])
    assert _get_stock_quarterly_yoy("2330.TW", "q_operating_cf") == pytest.approx(50.0, abs=0.01)


def test_get_stock_quarterly_yoy_missing_prev_returns_none():
    db.save_financial_quarterly_rows([
        {"ticker": "2330.TW", "date": "2026-03-31", "report_type": "income", "type": "EPS", "value": 15.0},
    ])
    assert _get_stock_quarterly_yoy("2330.TW", "q_eps") is None


def test_get_stock_quarterly_yoy_no_data_returns_none():
    assert _get_stock_quarterly_yoy("2330.TW", "q_eps") is None


def test_get_stock_quarterly_yoy_unknown_indicator_returns_none():
    db.save_financial_quarterly_rows([
        {"ticker": "2330.TW", "date": "2026-03-31", "report_type": "income", "type": "EPS", "value": 15.0},
    ])
    assert _get_stock_quarterly_yoy("2330.TW", "q_unknown") is None


def test_get_stock_yearly_yoy_cash_dividend_positive():
    # 114年=2025,113年=2024。每年 4 季合計
    rows = []
    for q in (1, 2, 3, 4):
        rows.append({
            "ticker": "2330.TW", "year": f"113年第{q}季",
            "cash_dividend": 2.5, "stock_dividend": 0.0,
            "cash_ex_date": None, "cash_payment_date": None, "announcement_date": None,
        })
        rows.append({
            "ticker": "2330.TW", "year": f"114年第{q}季",
            "cash_dividend": 4.0, "stock_dividend": 0.0,
            "cash_ex_date": None, "cash_payment_date": None, "announcement_date": None,
        })
    db.save_dividend_history_rows(rows)
    # 2024 合計 = 10, 2025 合計 = 16, YoY = 60.0
    assert _get_stock_yearly_yoy("2330.TW", "y_cash_dividend") == pytest.approx(60.0, abs=0.01)


def test_get_stock_yearly_yoy_stock_dividend():
    rows = [
        {"ticker": "2330.TW", "year": "113年第1季",
         "cash_dividend": 0.0, "stock_dividend": 1.0,
         "cash_ex_date": None, "cash_payment_date": None, "announcement_date": None},
        {"ticker": "2330.TW", "year": "114年第1季",
         "cash_dividend": 0.0, "stock_dividend": 2.0,
         "cash_ex_date": None, "cash_payment_date": None, "announcement_date": None},
    ]
    db.save_dividend_history_rows(rows)
    # 2024 stock=1, 2025 stock=2, YoY=100
    assert _get_stock_yearly_yoy("2330.TW", "y_stock_dividend") == pytest.approx(100.0, abs=0.01)


def test_get_stock_yearly_yoy_single_year_returns_none():
    rows = [
        {"ticker": "2330.TW", "year": "114年第1季",
         "cash_dividend": 4.0, "stock_dividend": 0.0,
         "cash_ex_date": None, "cash_payment_date": None, "announcement_date": None},
    ]
    db.save_dividend_history_rows(rows)
    # 只有 2025,沒去年 → None
    assert _get_stock_yearly_yoy("2330.TW", "y_cash_dividend") is None


def test_get_stock_yearly_yoy_no_data_returns_none():
    assert _get_stock_yearly_yoy("2330.TW", "y_cash_dividend") is None
```

### Step 1.2: Run, verify fails

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py -v -k "quarterly_yoy or yearly_yoy"
```

Expected: 9 FAILED.

### Step 1.3: 實作 helpers in alerts.py

**File:** `stock/dashboard/backend/alerts.py`

After existing `_get_stock_revenue_yoy`(or near top of YoY-related helpers區段), add:

```python
QUARTERLY_INDICATOR_TYPES = {
    "q_eps":              ("income",    "EPS"),
    "q_revenue":          ("income",    "Revenue"),
    "q_operating_income": ("income",    "OperatingIncome"),
    "q_net_income":       ("income",    "IncomeAfterTaxes"),
    "q_operating_cf":     ("cash_flow", "CashFlowsFromOperatingActivities"),
}
YEARLY_INDICATOR_KEYS = {"y_cash_dividend", "y_stock_dividend"}


def _get_stock_quarterly_yoy(ticker: str, indicator_key: str) -> float | None:
    """從 stock_financial_quarterly 拉同一 (report_type, type) 序列,取最新季 vs 去年同季。

    缺資料 / 缺去年同季 / prev=0 → None。
    """
    if indicator_key not in QUARTERLY_INDICATOR_TYPES:
        return None
    report_type, type_name = QUARTERLY_INDICATOR_TYPES[indicator_key]

    from datetime import datetime, timezone
    from db import get_financial_quarterly_range
    # 拉近 3 年(足夠覆蓋去年同季 + buffer)
    since = (datetime.now(timezone.utc).date().replace(month=1, day=1)
             .replace(year=datetime.now(timezone.utc).year - 3)).isoformat()
    rows = get_financial_quarterly_range(ticker, report_type, since)
    same_type = [(r["date"], r["value"]) for r in rows
                 if r["type"] == type_name and r["value"] is not None]
    if not same_type:
        return None
    same_type.sort(key=lambda x: x[0])
    latest_date, latest_value = same_type[-1]

    # 去年同季 = same month-day, year - 1
    dt = datetime.strptime(latest_date, "%Y-%m-%d")
    target_prev_date = f"{dt.year - 1}-{dt.month:02d}-{dt.day:02d}"
    prev_value = next((v for d, v in same_type if d == target_prev_date), None)
    if prev_value is None or prev_value == 0:
        return None
    return round((latest_value - prev_value) / prev_value * 100, 2)


def _get_stock_yearly_yoy(ticker: str, indicator_key: str) -> float | None:
    """從 stock_dividend_history aggregate by 西元年(parse "114年第N季" → 2025),
    比較最新年 vs 去年。"""
    if indicator_key not in YEARLY_INDICATOR_KEYS:
        return None
    from db import get_dividend_history
    raw_rows = get_dividend_history(ticker)
    if not raw_rows:
        return None

    field = "cash_dividend" if indicator_key == "y_cash_dividend" else "stock_dividend"

    import re
    by_year: dict[int, float] = {}
    for r in raw_rows:
        m = re.match(r"^(\d{2,3})年", r.get("year") or "")
        if not m:
            continue
        ce_year = int(m.group(1)) + 1911
        v = r.get(field) or 0
        by_year[ce_year] = by_year.get(ce_year, 0) + v

    if len(by_year) < 2:
        return None
    sorted_years = sorted(by_year.keys())
    latest_year = sorted_years[-1]
    prev_year = latest_year - 1
    cur = by_year.get(latest_year)
    prev = by_year.get(prev_year)
    if cur is None or not prev:
        return None
    return round((cur - prev) / prev * 100, 2)
```

### Step 1.4: Run, verify pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py -v -k "quarterly_yoy or yearly_yoy"
```

Expected: 9 passed.

### Step 1.5: Run full regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 105 passed (96 + 9), 5 pre-existing fail unchanged.

### Step 1.6: Commit T1

```bash
git add stock/dashboard/backend/alerts.py stock/dashboard/tests/test_alerts.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add quarterly/yearly YoY helpers (Q-T1)

新增 alerts.py:
- QUARTERLY_INDICATOR_TYPES dict(5 個 q_* keys → (report_type, type))
- YEARLY_INDICATOR_KEYS set(y_cash_dividend / y_stock_dividend)
- _get_stock_quarterly_yoy:從 stock_financial_quarterly 取最新季 vs 去年
  同季 (date 字串同月日 year-1 比對)
- _get_stock_yearly_yoy:從 stock_dividend_history aggregate by 西元年
  (parse ROC 年),最新年 vs 去年合計比對

T2 將在這之上加 routing。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: check_alerts yoy routing 擴展

**Files:**
- Modify: `stock/dashboard/backend/alerts.py`
- Modify: `stock/dashboard/tests/test_alerts.py`

### Step 2.1: 寫 routing 失敗測試

**File:** `stock/dashboard/tests/test_alerts.py`(append at end)

```python
def test_check_alerts_yoy_quarterly_eps_triggers():
    db.save_financial_quarterly_rows([
        {"ticker": "2330.TW", "date": "2025-03-31", "report_type": "income", "type": "EPS", "value": 10.0},
        {"ticker": "2330.TW", "date": "2026-03-31", "report_type": "income", "type": "EPS", "value": 15.0},
    ])
    db.add_alert("stock_indicator", "2330.TW", "yoy_above", 30,
                 indicator_key="q_eps", window_n=None)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("stock_indicator", "2330.TW", indicator_key="q_eps")
    assert mock_send.called


def test_check_alerts_yoy_yearly_dividend_triggers():
    rows = [
        {"ticker": "2330.TW", "year": "113年第1季",
         "cash_dividend": 2.5, "stock_dividend": 0.0,
         "cash_ex_date": None, "cash_payment_date": None, "announcement_date": None},
        {"ticker": "2330.TW", "year": "114年第1季",
         "cash_dividend": 4.0, "stock_dividend": 0.0,
         "cash_ex_date": None, "cash_payment_date": None, "announcement_date": None},
    ]
    db.save_dividend_history_rows(rows)
    # 2024=2.5, 2025=4.0, YoY=60%
    db.add_alert("stock_indicator", "2330.TW", "yoy_above", 30,
                 indicator_key="y_cash_dividend", window_n=None)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("stock_indicator", "2330.TW", indicator_key="y_cash_dividend")
    assert mock_send.called
```

### Step 2.2: Run, verify fails

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py -v -k "yoy_quarterly_eps or yoy_yearly_dividend"
```

Expected: 2 FAILED.

### Step 2.3: 改 check_alerts yoy routing

**File:** `stock/dashboard/backend/alerts.py`

Find existing `check_alerts` yoy branch:

```python
        elif cond in ("yoy_above", "yoy_below"):
            # 只支援 monthly indicator(目前僅 revenue)
            if target_type != "stock_indicator" or indicator_key != "revenue":
                continue
            yoy = _get_stock_revenue_yoy(target)
            if yoy is None:
                continue
            triggered = ((cond == "yoy_above" and yoy >= threshold) or
                         (cond == "yoy_below" and yoy <= threshold))
            triggered_value = yoy if triggered else None
```

Replace with:

```python
        elif cond in ("yoy_above", "yoy_below"):
            # 支援 monthly(revenue)、quarterly(q_*)、yearly(y_*)
            if target_type != "stock_indicator":
                continue
            if indicator_key == "revenue":
                yoy = _get_stock_revenue_yoy(target)
            elif indicator_key in QUARTERLY_INDICATOR_TYPES:
                yoy = _get_stock_quarterly_yoy(target, indicator_key)
            elif indicator_key in YEARLY_INDICATOR_KEYS:
                yoy = _get_stock_yearly_yoy(target, indicator_key)
            else:
                continue
            if yoy is None:
                continue
            triggered = ((cond == "yoy_above" and yoy >= threshold) or
                         (cond == "yoy_below" and yoy <= threshold))
            triggered_value = yoy if triggered else None
```

### Step 2.4: Run, verify pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py -v
```

Expected: 既有 + T1 9 + T2 2 = pass。 5 pre-existing fail 不變.

### Step 2.5: Run full regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 107 passed (105 + 2), 5 pre-existing failures unchanged.

### Step 2.6: Commit T2

```bash
git add stock/dashboard/backend/alerts.py stock/dashboard/tests/test_alerts.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): alert engine yoy routing for quarterly/yearly (Q-T2)

check_alerts 的 yoy routing 從「只認 revenue」擴展為認 monthly(revenue)、
quarterly(QUARTERLY_INDICATOR_TYPES 5 個 q_* keys)、yearly
(YEARLY_INDICATOR_KEYS 2 個 y_* keys)。其他 indicator_key 仍 skip。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Fetcher trigger(financial + dividend)

**Files:**
- Modify: `stock/dashboard/backend/fetchers/fundamentals_stock.py`

### Step 3.1: `fetch_stock_financial` 加 trigger

**File:** `stock/dashboard/backend/fetchers/fundamentals_stock.py`

Find `fetch_stock_financial(ticker, report_type, ...)` function。It currently ends with:

```python
    rows = parse_financial_rows(raw, ticker, report_type)
    save_financial_quarterly_rows(rows)
    print(f"[fundamentals] {ticker} {report_type} {start_date}~{end_date}: {len(rows)} rows")
    return True
```

Need access to `latest`(pre-fetch latest_date)— check if function already calls `get_latest_financial_date(ticker, report_type)` early. If yes, reuse that variable. If variable name differs, adjust accordingly.

Find the early call (likely `latest = get_latest_financial_date(ticker, report_type)`). Replace the ending block with:

```python
    rows = parse_financial_rows(raw, ticker, report_type)
    save_financial_quarterly_rows(rows)

    # Phase 4 alert 觸發:只在拉到新季時針對對應 quarterly indicator 檢查
    new_max_date = max((r["date"] for r in rows), default=None)
    if new_max_date and (latest is None or new_max_date > latest):
        from alerts import check_alerts
        # report_type → 對應的 q_* indicator_key 集合
        triggered_keys: list[str] = []
        if report_type == "income":
            triggered_keys = ["q_eps", "q_revenue", "q_operating_income", "q_net_income"]
        elif report_type == "cash_flow":
            triggered_keys = ["q_operating_cf"]
        # balance 不觸發(範圍外)
        for key in triggered_keys:
            check_alerts("stock_indicator", ticker, indicator_key=key)

    print(f"[fundamentals] {ticker} {report_type} {start_date}~{end_date}: {len(rows)} rows")
    return True
```

(注意:variable name 確認 — 若 fetcher 內既有變數叫 `latest_date` 而非 `latest`,以實際為準。)

### Step 3.2: `fetch_stock_dividend` 加 trigger

**File:** Same file.

Find `fetch_stock_dividend(ticker, ...)` function。It currently ends with:

```python
    rows = parse_dividend_rows(raw, ticker)
    save_dividend_history_rows(rows)
    print(f"[fundamentals] {ticker} dividend {start_date}~{end_date}: {len(rows)} rows")
    return True
```

For dividend trigger,我們要比對「最新西元年」是否變動。pre-fetch 從 `get_dividend_history` 算 max 西元年;post-fetch 從 `rows` 算 max 西元年(parse "XX年第N季")。

Replace the ending with:

```python
    rows = parse_dividend_rows(raw, ticker)
    save_dividend_history_rows(rows)

    # Phase 4 alert 觸發:只在拉到新西元年才觸發 yearly indicator
    import re
    def _max_ce_year(items):
        years = []
        for r in items:
            m = re.match(r"^(\d{2,3})年", r.get("year") or "")
            if m:
                years.append(int(m.group(1)) + 1911)
        return max(years, default=None)

    pre_year = _max_ce_year(pre_dividend_history)
    new_year = _max_ce_year(rows)
    if new_year and (pre_year is None or new_year > pre_year):
        from alerts import check_alerts
        for key in ("y_cash_dividend", "y_stock_dividend"):
            check_alerts("stock_indicator", ticker, indicator_key=key)

    print(f"[fundamentals] {ticker} dividend {start_date}~{end_date}: {len(rows)} rows")
    return True
```

This requires `pre_dividend_history` — captured BEFORE the fetcher reads new data. Find function early section that has `latest_announce = get_latest_dividend_announce_date(ticker)`. After that line, add:

```python
    from db import get_dividend_history
    pre_dividend_history = get_dividend_history(ticker)
```

(If lazy import 不便,top-of-file `from db import ...` 可加 `get_dividend_history`,看既有 import style。)

### Step 3.3: Run regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -5
```

Expected: 107 passed unchanged. trigger 是 production-only 行為。

### Step 3.4: Commit T3

```bash
git add stock/dashboard/backend/fetchers/fundamentals_stock.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): fetcher trigger for quarterly/yearly alerts (Q-T3)

fetch_stock_financial 寫入後若 max(date) > pre-fetch latest 則對應觸發
quarterly indicator(income → q_eps/q_revenue/q_operating_income/
q_net_income;cash_flow → q_operating_cf;balance 不觸發)。
fetch_stock_dividend 寫入後若 aggregate 出新西元年則觸發 y_cash_dividend
/ y_stock_dividend。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Scheduler watchlist 加拉取

**Files:**
- Modify: `stock/dashboard/backend/fetchers/fundamentals_stock.py`

### Step 4.1: 修 `fetch_watchlist_stock_daily`

**File:** Same file.

Find `fetch_watchlist_stock_daily()` function。It currently has 3 try/except blocks(chip / per / revenue).

Append 3 more try/except blocks inside the for loop:

```python
        try:
            fetch_stock_financial(ticker, "income")
        except Exception as e:
            print(f"[watchlist_chip_per] {ticker} income error: {e}")
        try:
            fetch_stock_financial(ticker, "cash_flow")
        except Exception as e:
            print(f"[watchlist_chip_per] {ticker} cash_flow error: {e}")
        try:
            fetch_stock_dividend(ticker)
        except Exception as e:
            print(f"[watchlist_chip_per] {ticker} dividend error: {e}")
```

### Step 4.2: Run regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -5
```

Expected: 107 passed unchanged.

### Step 4.3: Commit T4

```bash
git add stock/dashboard/backend/fetchers/fundamentals_stock.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): watchlist scheduler add quarterly + yearly fetchers (Q-T4)

fetch_watchlist_stock_daily 加 3 個 fetcher 呼叫(income / cash_flow /
dividend)讓 watchlist ticker 的季財報跟年股利資料每天主動更新,確保
quarterly/yearly YoY 警示能可靠觸發。各 fetcher 內部 lazy guard 確保
資料未變動時不打 FinMind。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: API 擴展驗證

**Files:**
- Modify: `stock/dashboard/backend/app.py`
- Modify: `stock/dashboard/tests/test_api.py`

### Step 5.1: 寫 API 失敗測試

**File:** `stock/dashboard/tests/test_api.py`(append at end)

```python
def test_post_alert_yoy_with_q_eps():
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "yoy_above",
        "threshold": 30,
        "indicator_key": "q_eps",
    })
    assert r.status_code == 200


def test_post_alert_yoy_with_y_cash_dividend():
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "yoy_above",
        "threshold": 20,
        "indicator_key": "y_cash_dividend",
    })
    assert r.status_code == 200


def test_post_alert_yoy_with_unknown_q_key_400():
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "yoy_above",
        "threshold": 30,
        "indicator_key": "q_unknown_field",
    })
    assert r.status_code == 400


def test_post_alert_percentile_with_q_eps_400():
    """percentile 仍只支援 daily,搭 q_eps 應 400。"""
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "percentile_above",
        "threshold": 90,
        "indicator_key": "q_eps",
    })
    assert r.status_code == 400


def test_post_alert_yoy_with_per_still_400():
    """yoy + daily indicator 仍應 400(沿用既有規則)。"""
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "yoy_above",
        "threshold": 30,
        "indicator_key": "per",
    })
    assert r.status_code == 400
```

### Step 5.2: Run, verify some fail

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_api.py -v -k "q_eps or y_cash_dividend or yoy_with_per_still"
```

Expected:
- `test_post_alert_yoy_with_q_eps` FAIL(STOCK_INDICATOR_KEYS 不認 q_eps)
- `test_post_alert_yoy_with_y_cash_dividend` FAIL(同)
- `test_post_alert_yoy_with_unknown_q_key_400` PASS(unknown 自然拒絕)
- `test_post_alert_percentile_with_q_eps_400` 既有 reject:indicator_key 不在 STOCK_INDICATOR_KEYS,400 — pass(但語意不對:目前因為「unknown」拒絕,而不是「percentile + non-daily」拒絕。修了 STOCK_INDICATOR_KEYS 後仍應 400 因為 cross-validation 拒絕)
- `test_post_alert_yoy_with_per_still_400` PASS(沿用既有規則,still 400)

### Step 5.3: app.py — extend constants and validation

**File:** `stock/dashboard/backend/app.py`

Locate existing constants(MVP T4 加的):

```python
VALID_CONDITIONS = {
    "above", "below",
    "streak_above", "streak_below",
    "percentile_above", "percentile_below",
    "yoy_above", "yoy_below",
}
STOCK_DAILY_INDICATOR_KEYS = {...}
STOCK_MONTHLY_INDICATOR_KEYS = {"revenue"}
STOCK_INDICATOR_KEYS = STOCK_DAILY_INDICATOR_KEYS | STOCK_MONTHLY_INDICATOR_KEYS
PERCENTILE_DAILY_KEYS = {"per", "pbr", "dividend_yield"}
```

Replace the constants block with:

```python
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
```

Find existing yoy validation in `create_alert`:

```python
        if is_yoy and req.indicator_key not in STOCK_MONTHLY_INDICATOR_KEYS:
            raise HTTPException(
                status_code=400,
                detail="yoy condition requires monthly indicator (revenue)"
            )
```

Replace with:

```python
        if is_yoy and req.indicator_key not in STOCK_YOY_COMPATIBLE_KEYS:
            raise HTTPException(
                status_code=400,
                detail="yoy condition requires monthly/quarterly/yearly indicator"
            )
```

### Step 5.4: Run, verify pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_api.py -v -k "q_eps or y_cash_dividend or yoy_with_per_still or unknown_q_key or percentile_with_q_eps"
```

Expected: 5 passed.

### Step 5.5: Run full regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 112 passed (107 + 5), 5 pre-existing failures unchanged.

### Step 5.6: Commit T5

```bash
git add stock/dashboard/backend/app.py stock/dashboard/tests/test_api.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): API alert validation for quarterly/yearly indicators (Q-T5)

新加 STOCK_QUARTERLY_INDICATOR_KEYS(5 個 q_*)、STOCK_YEARLY_INDICATOR_KEYS
(2 個 y_*)、STOCK_YOY_COMPATIBLE_KEYS(monthly+quarterly+yearly)。
yoy condition 驗證從「只認 monthly」改為「認 yoy compatible(monthly /
quarterly / yearly)」。percentile 仍只認 daily,維持現狀。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: UI alert form 加 7 個 indicator_key options

**Files:**
- Modify: `stock/dashboard/frontend/index.html`

### Step 6.1: indicator-key select 加 7 options

**File:** `stock/dashboard/frontend/index.html`

Locate existing `<select id="alert-indicator-key">`(MVP T5 加 revenue 後的版本)。Find `<option value="revenue">月營收</option>` line. After it, append 7 lines:

```html
      <option value="q_eps">季 EPS</option>
      <option value="q_revenue">季營收</option>
      <option value="q_operating_income">季營業利益</option>
      <option value="q_net_income">季稅後淨利</option>
      <option value="q_operating_cf">季營業 CF</option>
      <option value="y_cash_dividend">年現金股利</option>
      <option value="y_stock_dividend">年股票股利</option>
```

### Step 6.2: STOCK_INDICATOR_LABELS 加 7 labels

Locate existing `STOCK_INDICATOR_LABELS` JS const. After `revenue: '月營收',`(MVP-T5 加的),add:

```javascript
  q_eps:              '季 EPS',
  q_revenue:          '季營收',
  q_operating_income: '季營業利益',
  q_net_income:       '季稅後淨利',
  q_operating_cf:     '季營業 CF',
  y_cash_dividend:    '年現金股利',
  y_stock_dividend:   '年股票股利',
```

### Step 6.3: Verify and Commit

```bash
grep -n "q_eps\|q_revenue\|y_cash_dividend\|y_stock_dividend" stock/dashboard/frontend/index.html
```

Expected: HTML option + JS label 都找到。

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -5
```

Backend 不該 regress(112 passed)。

```bash
git add stock/dashboard/frontend/index.html
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): alert form indicator_key adds quarterly + yearly (Q-T6)

index.html alert form 的 indicator-key select 加 7 個 options(5 個 q_* 季
指標 + 2 個 y_* 年指標)。STOCK_INDICATOR_LABELS 對應加 7 個中文 labels。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Deploy + 驗證

### Step 7.1: 確認本機所有測試通過

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 112 passed, 5 pre-existing failures unchanged.

### Step 7.2: Push

```bash
git push origin master
```

### Step 7.3: Watch deploys

```bash
gh run watch $(gh run list --workflow=deploy-stock-dashboard-backend.yml --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
gh run watch $(gh run list --workflow=deploy-stock-dashboard.yml         --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
```

Expected: 兩個 success.

### Step 7.4: 驗證 q_eps alert 觸發

設個門檻極低必觸發的 q_eps alert(2330.TW EPS YoY > -100):

```bash
echo '--- POST q_eps yoy alert ---'
curl -s -X POST 'https://api.paul-learning.dev/api/alerts' \
  -H 'Content-Type: application/json' \
  -d '{"target_type":"stock_indicator","target":"2330.TW","condition":"yoy_above","threshold":-100,"indicator_key":"q_eps"}' | jq

# 手動觸發 check_alerts(用 DB 既有資料)
ssh root@178.104.240.236 "cd /opt/stock-dashboard/backend && set -a && . .env && set +a && .venv/bin/python -c '
import sys; sys.path.insert(0, \".\")
from db import init_db; init_db()
from alerts import check_alerts
check_alerts(\"stock_indicator\", \"2330.TW\", indicator_key=\"q_eps\")
'"
```

Expected: log `[alerts] notified: 2330.TW 季 EPS yoy_above -100.0 (value=...)`. Discord 收到通知。

驗證:

```bash
curl -s 'https://api.paul-learning.dev/api/alerts' | jq '[.[] | select(.indicator_key=="q_eps")] | .[] | {id, target, indicator_key, threshold, enabled, triggered_at, triggered_value}'
```

Expected: enabled=0,triggered_value 是 EPS YoY% 數字。

### Step 7.5: 驗證 y_cash_dividend alert 觸發

```bash
echo '--- POST y_cash_dividend yoy alert ---'
curl -s -X POST 'https://api.paul-learning.dev/api/alerts' \
  -H 'Content-Type: application/json' \
  -d '{"target_type":"stock_indicator","target":"2330.TW","condition":"yoy_above","threshold":-100,"indicator_key":"y_cash_dividend"}' | jq

ssh root@178.104.240.236 "cd /opt/stock-dashboard/backend && set -a && . .env && set +a && .venv/bin/python -c '
import sys; sys.path.insert(0, \".\")
from db import init_db; init_db()
from alerts import check_alerts
check_alerts(\"stock_indicator\", \"2330.TW\", indicator_key=\"y_cash_dividend\")
'"
```

Expected: log + Discord 收到「2330.TW 年現金股利 yoy_above -100.0 (value=...)」。

(若 production DB 中 y_cash_dividend 只有 1 年資料 → return None, 不觸發。實際情況看 production DB 累積。)

### Step 7.6: 驗證 cross-validation API 拒絕

```bash
echo '--- POST yoy + per (應 400)---'
curl -s -o /tmp/p1.json -w '%{http_code}\n' -X POST 'https://api.paul-learning.dev/api/alerts' \
  -H 'Content-Type: application/json' \
  -d '{"target_type":"stock_indicator","target":"2330.TW","condition":"yoy_above","threshold":30,"indicator_key":"per"}'
cat /tmp/p1.json | jq

echo '--- POST percentile + q_eps (應 400)---'
curl -s -o /tmp/p2.json -w '%{http_code}\n' -X POST 'https://api.paul-learning.dev/api/alerts' \
  -H 'Content-Type: application/json' \
  -d '{"target_type":"stock_indicator","target":"2330.TW","condition":"percentile_above","threshold":90,"indicator_key":"q_eps"}'
cat /tmp/p2.json | jq
```

Expected: 各回 HTTP 400 + detail 訊息。

### Step 7.7: VPS sanity

```bash
ssh root@178.104.240.236 "awk -F= '{print \$1}' /opt/stock-dashboard/backend/.env"
ssh root@178.104.240.236 "systemctl status stock-dashboard --no-pager | head -5"
```

Expected: env keys 都在,service active。

### Step 7.8: 報告

最終報告含:
- 本機測試結果(112 passed)
- Push commit SHA
- 兩 workflow IDs + duration
- POST q_eps + 觸發 + Discord 觀察(predicted)
- POST y_cash_dividend + 觸發 + Discord 觀察
- 兩個 cross-validation 400 reject
- VPS service status
- 提示使用者:測試 alert 已 disable;手動 UI 抽看(瀏覽器確認新 7 個 indicator_key options 出現)

## Self-Review

- 7 個新 indicator_key 都能 POST 成功
- 季 / 年 YoY 計算正確(test 已驗證 setup)
- API 拒絕 yoy+daily / percentile+non-daily
- VPS 沒因 import error 起不來
