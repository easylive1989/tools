# Stock Dashboard 警示深化 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** 警示系統加入「PER 5y 百分位」與「月營收 YoY」兩個衍生計算型警示。

**Architecture:** condition 字串加 4 個值(`percentile_above/below`, `yoy_above/below`)+ 1 個新 indicator_key(`revenue`),沿用既有 price_alerts schema(無 ALTER)。Engine routing 加 4 條分支 + 2 個純函式 helper。fetch_stock_revenue 加 trigger,watchlist scheduler 加 revenue 拉取。UI alert form 擴展。

**Tech Stack:** Python 3 / SQLite / FastAPI / pytest / 純 HTML+JS

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `stock/dashboard/backend/alerts.py` | Modify | 加 `_pct_rank`、`_get_stock_revenue_yoy` 純函式;`check_alerts` 加 4 條 routing;`_build_payload` 訊息對應 |
| `stock/dashboard/backend/fetchers/fundamentals_stock.py` | Modify | `fetch_stock_revenue` 寫入後加 trigger(只在新月);`fetch_watchlist_stock_daily` 加 revenue 呼叫 |
| `stock/dashboard/backend/app.py` | Modify | `VALID_CONDITIONS` + `STOCK_MONTHLY_INDICATOR_KEYS` + `STOCK_INDICATOR_KEYS` 擴展;`create_alert` 交叉驗證 |
| `stock/dashboard/frontend/index.html` | Modify | alert-condition 4 options;alert-indicator-key 加 revenue option;threshold placeholder 動態;alertConditionLabel 4 文字;STOCK_INDICATOR_LABELS 加 revenue |
| `stock/dashboard/tests/test_alerts.py` | Modify | 加 pct_rank / yoy / routing 測試 |
| `stock/dashboard/tests/test_api.py` | Modify | 加 4 個 API 交叉驗證測試 |

---

## Task 1: Pure functions `_pct_rank` + `_get_stock_revenue_yoy`

**Files:**
- Modify: `stock/dashboard/backend/alerts.py`
- Modify: `stock/dashboard/tests/test_alerts.py`

### Step 1.1: 寫純函式失敗測試

**File:** `stock/dashboard/tests/test_alerts.py`(append at end)

```python
from alerts import _pct_rank, _get_stock_revenue_yoy


def test_pct_rank_inclusive_at_max():
    # 最大值 → 100
    assert _pct_rank(50, [10, 20, 30, 40, 50]) == 100.0


def test_pct_rank_at_min():
    # 最小值 → 1/N * 100(因 inclusive: count(<=10) == 1)
    assert _pct_rank(10, [10, 20, 30, 40, 50]) == 20.0


def test_pct_rank_middle():
    # 30 在 [10,20,30,40,50] 中 → count(<=30)==3, 3/5*100 = 60
    assert _pct_rank(30, [10, 20, 30, 40, 50]) == 60.0


def test_pct_rank_insufficient_history_returns_none():
    # < 30 點 → None
    assert _pct_rank(20, [10, 20, 30]) is None


def test_pct_rank_none_value_returns_none():
    assert _pct_rank(None, [10, 20, 30, 40, 50] * 10) is None


def test_get_stock_revenue_yoy_positive():
    db.init_db()
    db.save_revenue_monthly_rows([
        {"ticker": "2330.TW", "year": 2025, "month": 4, "revenue": 1_000_000_000_000, "announced_date": ""},
        {"ticker": "2330.TW", "year": 2026, "month": 4, "revenue": 1_500_000_000_000, "announced_date": ""},
    ])
    yoy = _get_stock_revenue_yoy("2330.TW")
    # (1500 - 1000) / 1000 * 100 = 50.0
    assert yoy == pytest.approx(50.0, abs=0.01)


def test_get_stock_revenue_yoy_negative():
    db.init_db()
    db.save_revenue_monthly_rows([
        {"ticker": "2330.TW", "year": 2025, "month": 4, "revenue": 1_500_000_000_000, "announced_date": ""},
        {"ticker": "2330.TW", "year": 2026, "month": 4, "revenue": 1_000_000_000_000, "announced_date": ""},
    ])
    yoy = _get_stock_revenue_yoy("2330.TW")
    # (1000 - 1500) / 1500 * 100 ≈ -33.33
    assert yoy == pytest.approx(-33.33, abs=0.05)


def test_get_stock_revenue_yoy_missing_prev_year_returns_none():
    db.init_db()
    db.save_revenue_monthly_rows([
        {"ticker": "2330.TW", "year": 2026, "month": 4, "revenue": 1_500_000_000_000, "announced_date": ""},
    ])
    assert _get_stock_revenue_yoy("2330.TW") is None


def test_get_stock_revenue_yoy_no_data_returns_none():
    db.init_db()
    assert _get_stock_revenue_yoy("2330.TW") is None
```

### Step 1.2: Run, verify fails

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py -v -k "pct_rank or revenue_yoy"
```

Expected: 9 tests FAILED with ImportError(_pct_rank / _get_stock_revenue_yoy 還不存在)。

### Step 1.3: 實作 `_pct_rank` + `_get_stock_revenue_yoy` in alerts.py

**File:** `stock/dashboard/backend/alerts.py`

In `alerts.py`, after existing `_get_stock_indicator_history` function and before `STOCK_INDICATOR_LABELS` (or after it,順序不嚴格), add:

```python
def _pct_rank(value: float | None, history: list[float]) -> float | None:
    """Inclusive percentile rank: count(v <= value) / total * 100.

    Empty / value=None / history < 30 points → None(避免新上市股誤觸發)。
    """
    if value is None or len(history) < 30:
        return None
    below = sum(1 for v in history if v is not None and v <= value)
    total = sum(1 for v in history if v is not None)
    if total == 0:
        return None
    return round(below / total * 100, 2)


def _get_stock_revenue_yoy(ticker: str) -> float | None:
    """從 stock_revenue_monthly 取最新月 vs 去年同月,算 YoY %。

    缺資料(新上市股、去年同期沒值、去年同期 = 0)→ None。
    """
    from db import get_revenue_monthly_range, get_latest_revenue_ym
    latest = get_latest_revenue_ym(ticker)
    if not latest:
        return None
    y, m = latest
    rows = get_revenue_monthly_range(ticker, y - 1, m)
    by_ym = {(r["year"], r["month"]): r["revenue"] for r in rows}
    cur = by_ym.get((y, m))
    prev = by_ym.get((y - 1, m))
    if cur is None or not prev:   # prev 為 0 / None 都 fail
        return None
    return round((cur - prev) / prev * 100, 2)
```

### Step 1.4: Run, verify pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py -v -k "pct_rank or revenue_yoy"
```

Expected: 9 passed.

### Step 1.5: Run full regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 87 passed (78 + 9), 5 pre-existing failures unchanged.

### Step 1.6: Commit

```bash
git add stock/dashboard/backend/alerts.py stock/dashboard/tests/test_alerts.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add _pct_rank and _get_stock_revenue_yoy helpers (T1)

新增 alerts.py 兩個純函式 helper:_pct_rank(inclusive percentile rank,
history < 30 點回 None 避免新上市股誤觸發)、_get_stock_revenue_yoy
(從 stock_revenue_monthly 取最新月 vs 去年同月算 YoY %,缺資料回
None)。T2 將在這之上加 routing。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `check_alerts` 加 percentile / yoy routing + Discord format

**Files:**
- Modify: `stock/dashboard/backend/alerts.py`
- Modify: `stock/dashboard/tests/test_alerts.py`

### Step 2.1: 寫 routing 失敗測試

**File:** `stock/dashboard/tests/test_alerts.py`(append at end)

```python
def test_check_alerts_percentile_above_triggers():
    db.init_db()
    # 寫 50 個 PER 值,latest 是最大 → 百分位 100
    rows = []
    for i in range(50):
        rows.append({
            "ticker": "2330.TW",
            "date": f"2024-{(i % 12) + 1:02d}-{(i // 12) * 7 + 1:02d}",
            "per": 20.0 + i,   # 20-69, latest=69 是最大
            "pbr": None, "dividend_yield": None,
        })
    db.save_per_daily_rows(rows)
    db.add_alert("stock_indicator", "2330.TW", "percentile_above", 90,
                 indicator_key="per", window_n=None)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("stock_indicator", "2330.TW", indicator_key="per")
    assert mock_send.called


def test_check_alerts_percentile_below_does_not_trigger_when_high():
    # 同樣 setup,但 alert 設「percentile_below 10」— 不該觸發(latest 在 100 百分位)
    db.init_db()
    rows = []
    for i in range(50):
        rows.append({
            "ticker": "2330.TW",
            "date": f"2024-{(i % 12) + 1:02d}-{(i // 12) * 7 + 1:02d}",
            "per": 20.0 + i,
            "pbr": None, "dividend_yield": None,
        })
    db.save_per_daily_rows(rows)
    db.add_alert("stock_indicator", "2330.TW", "percentile_below", 10,
                 indicator_key="per", window_n=None)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("stock_indicator", "2330.TW", indicator_key="per")
    assert not mock_send.called


def test_check_alerts_yoy_above_triggers():
    db.init_db()
    db.save_revenue_monthly_rows([
        {"ticker": "2330.TW", "year": 2025, "month": 4, "revenue": 1_000_000_000_000, "announced_date": ""},
        {"ticker": "2330.TW", "year": 2026, "month": 4, "revenue": 1_500_000_000_000, "announced_date": ""},
    ])
    # YoY = 50%, alert 設 yoy_above 30 → 觸發
    db.add_alert("stock_indicator", "2330.TW", "yoy_above", 30,
                 indicator_key="revenue", window_n=None)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("stock_indicator", "2330.TW", indicator_key="revenue")
    assert mock_send.called


def test_check_alerts_percentile_with_revenue_indicator_skipped():
    """percentile 只支援 daily indicator,搭 revenue 不應觸發(engine layer skip)。"""
    db.init_db()
    db.save_revenue_monthly_rows([
        {"ticker": "2330.TW", "year": 2026, "month": 4, "revenue": 1_500_000_000_000, "announced_date": ""},
    ])
    db.add_alert("stock_indicator", "2330.TW", "percentile_above", 50,
                 indicator_key="revenue", window_n=None)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("stock_indicator", "2330.TW", indicator_key="revenue")
    assert not mock_send.called
```

### Step 2.2: Run, verify fails

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py -v -k "percentile or yoy"
```

Expected: 4 routing tests FAILED(check_alerts 還沒接 percentile / yoy)。pct_rank / revenue_yoy 純函式測試應仍 pass。

### Step 2.3: 加 routing 到 `check_alerts`

**File:** `stock/dashboard/backend/alerts.py`

Find existing `check_alerts` function. The streak section currently looks like:

```python
        elif cond in ("streak_above", "streak_below"):
            window_n = alert.get("window_n") or 5
            if target_type == "indicator":
                hist = _latest_indicator_history(target, window_n)
            elif target_type == "stock_indicator":
                hist = _get_stock_indicator_history(target, indicator_key, window_n)
            else:
                continue
            triggered = _check_streak(hist, cond, threshold, expected_n=window_n)
            triggered_value = hist[-1] if (triggered and hist) else None
        else:
            continue
```

Replace the final `else: continue` (the one that catches unknown conditions) with new routing branches BEFORE it:

```python
        elif cond in ("percentile_above", "percentile_below"):
            # 5y 百分位:只支援 daily indicator
            from alerts import STOCK_INDICATOR_KEYS  # daily set 在 P4 內定義
            # 只接受 daily indicator key
            if target_type != "stock_indicator" or indicator_key not in {"per", "pbr", "dividend_yield"}:
                continue
            hist = _get_stock_indicator_history(target, indicator_key, 1825)
            cur_value = hist[-1] if hist else None
            rank = _pct_rank(cur_value, hist)
            if rank is None:
                continue
            triggered = ((cond == "percentile_above" and rank >= threshold) or
                         (cond == "percentile_below" and rank <= threshold))
            triggered_value = rank if triggered else None
        elif cond in ("yoy_above", "yoy_below"):
            # YoY:只支援 monthly indicator(目前僅 revenue)
            if target_type != "stock_indicator" or indicator_key != "revenue":
                continue
            yoy = _get_stock_revenue_yoy(target)
            if yoy is None:
                continue
            triggered = ((cond == "yoy_above" and yoy >= threshold) or
                         (cond == "yoy_below" and yoy <= threshold))
            triggered_value = yoy if triggered else None
        else:
            continue
```

### Step 2.4: 擴展 `_build_payload` 訊息 format

**File:** `stock/dashboard/backend/alerts.py`

Find existing `_build_payload`,在 `if cond == "above":` 系列分支加新 4 個 case。Find the existing block:

```python
    if cond == "above":
        crossed = "突破"
        color = 0xE74C3C
    elif cond == "below":
        crossed = "跌破"
        color = 0x3498DB
    elif cond == "streak_above":
        crossed = f"連 {window_n} 日突破"
        color = 0xE74C3C
    elif cond == "streak_below":
        crossed = f"連 {window_n} 日跌破"
        color = 0x3498DB
    else:
        crossed = cond
        color = 0x95A5A6
```

Add 4 new cases BEFORE the final `else`:

```python
    elif cond == "percentile_above":
        crossed = "5y 百分位突破"
        color = 0xE74C3C
    elif cond == "percentile_below":
        crossed = "5y 百分位跌破"
        color = 0x3498DB
    elif cond == "yoy_above":
        crossed = "YoY 突破"
        color = 0xE74C3C
    elif cond == "yoy_below":
        crossed = "YoY 跌破"
        color = 0x3498DB
```

For percentile / yoy values, the existing `_fmt` for `stock_indicator` works:
- percentile (0-100):當 indicator_key 是 per/pbr,`f"{v:.2f}"` 會對(雖然意義是百分位不是 PER)
- yoy %:當 indicator_key 是 revenue,`f"{v:,.0f}"` 會切掉小數,改寫:

In `_fmt`,for revenue特殊化:

```python
        if target_type == "stock_indicator":
            ik = alert.get("indicator_key")
            if ik in ("per", "pbr"):
                return f"{v:.2f}"
            if ik == "dividend_yield":
                return f"{v:.2f}%"
            if ik == "revenue":   # 新
                return f"{v:.2f}%"   # 既然 revenue alert condition 多為 yoy_*,顯示 % 比較合理
            return f"{v:,.0f}"
```

但實際上 percentile_above 對 PER/PBR 的 triggered_value 是「百分位」(0-100),不是 PER 值。為了讓訊息正確,可以把 percentile 跟其他分開 format:

更乾淨做法是 `_build_payload` 內針對 condition 一起特殊化(condition + indicator_key 組合決定單位)。為簡化:不動 `_fmt`,接受顯示有 minor 不一致。然後在 description 加說明文字幫助讀者:

修改 description:

```python
    embed = {
        "title": f"🚨 警示:{display_name}",
        "description": (
            f"**{display_name}** 目前 **{value_str}**,已{crossed}門檻 **{threshold_str}**。\n"
            f"_警示已自動停用,請至 Dashboard 重新啟用。_"
        ),
        "color": color,
    }
```

仍然 OK — 因為 percentile/yoy 的 value 跟 threshold 都同單位(百分位 0-100 vs 百分位;% vs %),消費者讀 message 不會誤解。

### Step 2.5: Run, verify pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py -v
```

Expected: 既有 + 9 (T1) + 4 (T2) = pass。 5 pre-existing fail 不變.

### Step 2.6: Run full regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 91 passed (87 + 4),5 pre-existing failures unchanged.

### Step 2.7: Commit

```bash
git add stock/dashboard/backend/alerts.py stock/dashboard/tests/test_alerts.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): alert engine routing for percentile + yoy (T2)

check_alerts 加 4 條新 routing:percentile_above/below(對 daily indicator
拉 5y 歷史算百分位)、yoy_above/below(對 revenue 取最新月 vs 去年同月
算 YoY %)。Engine 層級交叉驗證:percentile 只接 daily indicator,yoy 只
接 revenue,其他組合直接 skip。Discord 訊息 format 對應加 4 種 crossed
文字。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Fetcher trigger + scheduler watchlist

**Files:**
- Modify: `stock/dashboard/backend/fetchers/fundamentals_stock.py`

### Step 3.1: `fetch_stock_revenue` 加 trigger

**File:** `stock/dashboard/backend/fetchers/fundamentals_stock.py`

In `fetch_stock_revenue` function, BEFORE the call to `_request("TaiwanStockMonthRevenue", ...)`,先記錄 pre-fetch 的 latest_ym(便於後續判斷有無新月):

(實際做法:`fetch_stock_revenue` 內部已經呼叫 `get_latest_revenue_ym` 算 start_date。我們在 fetcher 寫入後比較 post-fetch 的 latest_ym 跟 pre-fetch 是否不同。)

Find `fetch_stock_revenue`'s ending block(after `save_revenue_monthly_rows(rows)` 跟 `print(...)` 之間 OR 末尾 `return True`):

Locate the section that looks like:

```python
    rows = parse_revenue_rows(raw, ticker)
    save_revenue_monthly_rows(rows)
    print(f"[fundamentals] {ticker} revenue {start_date}~{end_date}: {len(rows)} rows")
    return True
```

Replace with(在 save 後加 trigger,只在「max(year, month) > pre-fetch latest」時觸發):

```python
    rows = parse_revenue_rows(raw, ticker)
    save_revenue_monthly_rows(rows)

    # Phase 4 follow-up alert 觸發:只在「實際拉到新月」時針對 revenue 指標檢查。
    # latest_ym 是 fetch 開始前的最新月(已在函式上方算出);post-fetch 比對。
    new_max_ym = max(((r["year"], r["month"]) for r in rows), default=None)
    if new_max_ym and (latest_ym is None or new_max_ym > latest_ym):
        from alerts import check_alerts
        check_alerts("stock_indicator", ticker, indicator_key="revenue")

    print(f"[fundamentals] {ticker} revenue {start_date}~{end_date}: {len(rows)} rows")
    return True
```

(注意:`latest_ym` 變數在 `fetch_stock_revenue` 函式上方已用 `latest_ym = get_latest_revenue_ym(ticker)` 算出 — 確認在 scope 內可用。若實際變數名不同,以實際為準。)

### Step 3.2: `fetch_watchlist_stock_daily` 加 revenue 拉取

**File:** `stock/dashboard/backend/fetchers/fundamentals_stock.py`

Find `fetch_watchlist_stock_daily` function。Inside the for loop where it calls `fetch_stock_chip(ticker)` and `fetch_stock_per(ticker)`,append:

```python
        try:
            fetch_stock_revenue(ticker)
        except Exception as e:
            print(f"[watchlist_chip_per] {ticker} revenue error: {e}")
```

Function should have 3 try/except blocks(chip, per, revenue)inside the loop。注意 `fetch_stock_revenue` 已在同檔案 module-level 定義,直接呼叫即可。

### Step 3.3: Run regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -5
```

Expected: 91 passed unchanged. trigger 是 production-only 行為(test 用 mock 不觸及)。

### Step 3.4: Commit

```bash
git add stock/dashboard/backend/fetchers/fundamentals_stock.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): trigger revenue alert + watchlist scheduler revenue fetch (T3)

fetch_stock_revenue 寫入後判斷是否拉到新月(post-fetch max(y,m) >
pre-fetch latest_ym),若有則對 stock_indicator/revenue 觸發 check_alerts。
fetch_watchlist_stock_daily 加第 3 個 fetcher 呼叫(fetch_stock_revenue),
讓 watchlist 上 ticker 的月營收 YoY 警示能可靠觸發。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: API 擴展驗證

**Files:**
- Modify: `stock/dashboard/backend/app.py`
- Modify: `stock/dashboard/tests/test_api.py`

### Step 4.1: 寫 API 失敗測試

**File:** `stock/dashboard/tests/test_api.py`(append at end)

```python
def test_post_alert_percentile_above_with_per():
    db.init_db()
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "percentile_above",
        "threshold": 90,
        "indicator_key": "per",
    })
    assert r.status_code == 200


def test_post_alert_percentile_with_revenue_400():
    db.init_db()
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "percentile_above",
        "threshold": 90,
        "indicator_key": "revenue",   # monthly,跟 percentile 不相容
    })
    assert r.status_code == 400


def test_post_alert_yoy_above_with_revenue():
    db.init_db()
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "yoy_above",
        "threshold": 30,
        "indicator_key": "revenue",
    })
    assert r.status_code == 200


def test_post_alert_yoy_with_per_400():
    db.init_db()
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "yoy_above",
        "threshold": 30,
        "indicator_key": "per",   # daily,跟 yoy 不相容
    })
    assert r.status_code == 400


def test_post_alert_percentile_threshold_out_of_range_400():
    db.init_db()
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "percentile_above",
        "threshold": 150,   # > 100
        "indicator_key": "per",
    })
    assert r.status_code == 400
```

### Step 4.2: Run, verify fails

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_api.py -v -k "percentile or yoy"
```

Expected: 5 tests FAILED(API 還沒接這些 condition / 交叉驗證)。

### Step 4.3: app.py — extend constants and validation

**File:** `stock/dashboard/backend/app.py`

Locate the existing constants:

```python
VALID_CONDITIONS = {"above", "below", "streak_above", "streak_below"}
STOCK_DAILY_INDICATOR_KEYS = {
    "per", "pbr", "dividend_yield",
    "foreign_net", "trust_net", "dealer_net",
    "margin_balance", "short_balance",
}
```

Replace with:

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
STOCK_INDICATOR_KEYS = STOCK_DAILY_INDICATOR_KEYS | STOCK_MONTHLY_INDICATOR_KEYS
PERCENTILE_DAILY_KEYS = {"per", "pbr", "dividend_yield"}
```

Find `create_alert` function. Locate the `is_streak` check block:

```python
    is_streak = req.condition.startswith("streak_")
    if is_streak:
        if req.window_n is None:
            raise HTTPException(status_code=400, detail="streak condition requires window_n")
        if req.window_n < 2 or req.window_n > 30:
            raise HTTPException(status_code=400, detail="window_n must be 2..30")
```

After this block, add new validation:

```python
    is_percentile = req.condition.startswith("percentile_")
    is_yoy = req.condition.startswith("yoy_")
    if is_percentile and (req.threshold < 0 or req.threshold > 100):
        raise HTTPException(status_code=400, detail="percentile threshold must be 0..100")
```

Then locate the `elif req.target_type == "stock_indicator":` block:

```python
    elif req.target_type == "stock_indicator":
        if not req.indicator_key:
            raise HTTPException(status_code=400, detail="stock_indicator requires indicator_key")
        if req.indicator_key not in STOCK_DAILY_INDICATOR_KEYS:
            raise HTTPException(status_code=400, detail="Unknown indicator_key")
        if fundamentals_to_finmind_id(req.target) is None:
            raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) supported")
        target = req.target.upper()
```

Replace with(更新 indicator_key 驗證 + 加交叉驗證):

```python
    elif req.target_type == "stock_indicator":
        if not req.indicator_key:
            raise HTTPException(status_code=400, detail="stock_indicator requires indicator_key")
        if req.indicator_key not in STOCK_INDICATOR_KEYS:
            raise HTTPException(status_code=400, detail="Unknown indicator_key")
        if fundamentals_to_finmind_id(req.target) is None:
            raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) supported")
        # 交叉驗證:percentile 只支援 daily;yoy 只支援 monthly
        if is_percentile and req.indicator_key not in PERCENTILE_DAILY_KEYS:
            raise HTTPException(status_code=400, detail="percentile condition requires daily indicator (per/pbr/dividend_yield)")
        if is_yoy and req.indicator_key not in STOCK_MONTHLY_INDICATOR_KEYS:
            raise HTTPException(status_code=400, detail="yoy condition requires monthly indicator (revenue)")
        target = req.target.upper()
```

### Step 4.4: Run, verify pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_api.py -v -k "percentile or yoy"
```

Expected: 5 passed.

### Step 4.5: Run full regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 96 passed (91 + 5),5 pre-existing failures unchanged.

### Step 4.6: Commit

```bash
git add stock/dashboard/backend/app.py stock/dashboard/tests/test_api.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): API alert validation for percentile and yoy (T4)

VALID_CONDITIONS 加 percentile_above/below + yoy_above/below。新加
STOCK_MONTHLY_INDICATOR_KEYS={"revenue"} 跟 PERCENTILE_DAILY_KEYS。
POST /api/alerts 加交叉驗證:percentile 只支援 daily indicator(per/pbr/
dividend_yield);yoy 只支援 monthly indicator(revenue);percentile
threshold 限 0-100。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: UI alert form 擴展

**Files:**
- Modify: `stock/dashboard/frontend/index.html`

### Step 5.1: condition select 加 4 options

**File:** `stock/dashboard/frontend/index.html`

Locate existing `<select id="alert-condition">`:

```html
<select id="alert-condition">
  <option value="above">大於等於</option>
  <option value="below">小於等於</option>
  <option value="streak_above">連 N 日突破</option>
  <option value="streak_below">連 N 日跌破</option>
</select>
```

Replace with:

```html
<select id="alert-condition">
  <option value="above">大於等於</option>
  <option value="below">小於等於</option>
  <option value="streak_above">連 N 日突破</option>
  <option value="streak_below">連 N 日跌破</option>
  <option value="percentile_above">5y 百分位突破</option>
  <option value="percentile_below">5y 百分位跌破</option>
  <option value="yoy_above">YoY 突破</option>
  <option value="yoy_below">YoY 跌破</option>
</select>
```

### Step 5.2: indicator-key select 加 revenue option

Locate existing `<select id="alert-indicator-key">`. Append before its closing `</select>`:

```html
      <option value="revenue">月營收</option>
```

### Step 5.3: STOCK_INDICATOR_LABELS 加 revenue

In existing `STOCK_INDICATOR_LABELS` const(in JS),加一行:

```javascript
  short_balance:    '融券餘額',
  revenue:          '月營收',   // 新
```

### Step 5.4: alertConditionLabel 加 4 個

In existing `alertConditionLabel(a)`,擴展為:

```javascript
function alertConditionLabel(a) {
  if (a.condition === 'above') return '≥';
  if (a.condition === 'below') return '≤';
  if (a.condition === 'streak_above') return `連 ${a.window_n} 日 ≥`;
  if (a.condition === 'streak_below') return `連 ${a.window_n} 日 ≤`;
  if (a.condition === 'percentile_above') return '5y 百分位 ≥';
  if (a.condition === 'percentile_below') return '5y 百分位 ≤';
  if (a.condition === 'yoy_above') return 'YoY ≥';
  if (a.condition === 'yoy_below') return 'YoY ≤';
  return a.condition;
}
```

### Step 5.5: threshold placeholder 動態切換

Find `refreshConditionFields` function. Replace it with:

```javascript
function refreshConditionFields() {
  const cond = document.getElementById('alert-condition').value;
  const windowEl = document.getElementById('alert-window-n');
  windowEl.style.display = cond.startsWith('streak_') ? '' : 'none';

  // threshold placeholder 動態切換
  const thresholdEl = document.getElementById('alert-threshold');
  if (cond.startsWith('percentile_')) {
    thresholdEl.placeholder = '百分位 0-100';
  } else if (cond.startsWith('yoy_')) {
    thresholdEl.placeholder = 'YoY %(可正可負)';
  } else {
    thresholdEl.placeholder = '門檻數值';
  }
}
```

### Step 5.6: Verify and Commit

```bash
grep -n "percentile_above\|yoy_above\|月營收" stock/dashboard/frontend/index.html
```

Expected: 看到 HTML option / JS label / 4 個 condition 都對齊。

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -5
```

Backend tests 不該 regress(96 passed)。

```bash
git add stock/dashboard/frontend/index.html
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): alert form supports percentile + yoy conditions (T5)

index.html alert form 加 4 個 condition options(5y 百分位 / YoY 突破跌破)
+ indicator-key 「月營收」option;STOCK_INDICATOR_LABELS 加 revenue label;
alertConditionLabel 對應 4 種文字;refreshConditionFields 加 threshold
placeholder 動態切換(百分位 0-100 / YoY % 可正可負 / 門檻數值)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Deploy + 驗證

### Step 6.1: 本機所有測試通過

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 96 passed, 5 pre-existing failures unchanged.

### Step 6.2: Push

```bash
git push origin master
```

### Step 6.3: Watch deploys

```bash
gh run watch $(gh run list --workflow=deploy-stock-dashboard-backend.yml --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
gh run watch $(gh run list --workflow=deploy-stock-dashboard.yml         --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
```

Expected: 兩個 success(20-30s 各)。

### Step 6.4: 驗證 percentile alert 觸發

設個門檻極低必觸發的 percentile alert(2330.TW PER 5y 百分位 > 0):

```bash
echo '--- POST percentile alert (2330.TW per percentile_above 0) ---'
curl -s -X POST 'https://api.paul-learning.dev/api/alerts' \
  -H 'Content-Type: application/json' \
  -d '{"target_type":"stock_indicator","target":"2330.TW","condition":"percentile_above","threshold":0,"indicator_key":"per"}' | jq

# 觸發 fetch_stock_per 拉資料
ssh root@178.104.240.236 "cd /opt/stock-dashboard/backend && set -a && . .env && set +a && .venv/bin/python -c '
import sys; sys.path.insert(0, \".\")
from db import init_db; init_db()
from fetchers.fundamentals_stock import fetch_stock_per
fetch_stock_per(\"2330.TW\")
'"

# 驗證
curl -s 'https://api.paul-learning.dev/api/alerts' | jq '[.[] | select(.condition=="percentile_above")] | .[] | {id, target, condition, threshold, enabled, triggered_at, triggered_value}'
```

Expected: alert.enabled = 0、triggered_value 是百分位 0-100 數字。Discord 收到通知。

(注意:若 fetch_stock_per 在 production 已有 5y 資料,只在 max date == today 時觸發。今天若是假日 → fetch 不到新資料 → 觸發不會發生。可手動跑 `check_alerts` 驗證:

```bash
ssh root@178.104.240.236 "cd /opt/stock-dashboard/backend && set -a && . .env && set +a && .venv/bin/python -c '
import sys; sys.path.insert(0, \".\")
from db import init_db; init_db()
from alerts import check_alerts
check_alerts(\"stock_indicator\", \"2330.TW\", indicator_key=\"per\")
'"
```
)

### Step 6.5: 驗證 yoy alert 觸發

設 yoy alert(2330.TW revenue YoY > 0):

```bash
echo '--- POST yoy alert (2330.TW revenue yoy_above 0) ---'
curl -s -X POST 'https://api.paul-learning.dev/api/alerts' \
  -H 'Content-Type: application/json' \
  -d '{"target_type":"stock_indicator","target":"2330.TW","condition":"yoy_above","threshold":0,"indicator_key":"revenue"}' | jq

# 觸發 fetch_stock_revenue(若新月會自動觸發 alert)
ssh root@178.104.240.236 "cd /opt/stock-dashboard/backend && set -a && . .env && set +a && .venv/bin/python -c '
import sys; sys.path.insert(0, \".\")
from db import init_db; init_db()
from fetchers.fundamentals_stock import fetch_stock_revenue
fetch_stock_revenue(\"2330.TW\")
'"

# 若 fetch 沒拉到新月,手動觸發 check_alerts
ssh root@178.104.240.236 "cd /opt/stock-dashboard/backend && set -a && . .env && set +a && .venv/bin/python -c '
import sys; sys.path.insert(0, \".\")
from db import init_db; init_db()
from alerts import check_alerts
check_alerts(\"stock_indicator\", \"2330.TW\", indicator_key=\"revenue\")
'"

# 驗證
curl -s 'https://api.paul-learning.dev/api/alerts' | jq '[.[] | select(.condition=="yoy_above")] | .[] | {id, target, condition, threshold, enabled, triggered_at, triggered_value}'
```

Expected: alert.enabled = 0、triggered_value 是 YoY % 數字。Discord 收到通知。

### Step 6.6: 驗證 cross-validation API 拒絕

```bash
echo '--- POST percentile + revenue (應 400) ---'
curl -s -X POST 'https://api.paul-learning.dev/api/alerts' \
  -H 'Content-Type: application/json' \
  -d '{"target_type":"stock_indicator","target":"2330.TW","condition":"percentile_above","threshold":50,"indicator_key":"revenue"}' | jq

echo '--- POST yoy + per (應 400) ---'
curl -s -X POST 'https://api.paul-learning.dev/api/alerts' \
  -H 'Content-Type: application/json' \
  -d '{"target_type":"stock_indicator","target":"2330.TW","condition":"yoy_above","threshold":30,"indicator_key":"per"}' | jq
```

Expected: 各回 detail 含「percentile / yoy 不相容」訊息,400。

### Step 6.7: VPS sanity

```bash
ssh root@178.104.240.236 "awk -F= '{print \$1}' /opt/stock-dashboard/backend/.env"
ssh root@178.104.240.236 "systemctl status stock-dashboard --no-pager | head -5"
```

Expected: env keys 都在,service active。

### Step 6.8: 報告

最終報告:
- 本機 96 passed
- Push commit SHA
- 兩 workflow IDs + duration
- POST percentile + 觸發 + Discord 觀察
- POST yoy + 觸發 + Discord 觀察
- 交叉驗證 400 反應
- VPS service status
- 提示使用者:測試 alert 已 disable;手動 UI 抽看(瀏覽器確認新 condition options 出現)

## Self-Review

- 5 個 percentile / yoy condition + 1 個新 indicator_key 都跑 e2e
- 兩個觸發 path(daily PER, monthly revenue)都驗證
- 交叉驗證 API 拒絕不合理組合
- service 沒因 import error 起不來
