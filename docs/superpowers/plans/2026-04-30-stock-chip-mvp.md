# Stock Dashboard 籌碼面 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 補上 4 個 FinMind 免費籌碼 dataset(整體 2 個 + 個股 2 個),涵蓋抓 → 存 → 顯示;替換現有 `margin.py`(避開 TWSE IP 封鎖風險),擴充總覽與個股頁籌碼面資訊。

**Architecture:** 整體層級用 `chip_total.py` 每日 cron 抓 FinMind 不帶 `data_id` 的全市場資料,寫入既有 `indicator_snapshots` 表(沿用既有 indicator pipeline)。個股層級用 `chip_stock.py` + 新表 `stock_chip_daily`,採 lazy fetch + cache(複用 `broker.py` 同模式)。警示規則層延後到第二階段。

**Tech Stack:** Python 3 / FastAPI / SQLite / APScheduler / requests / pytest / 純 HTML+JS 前端 / FinMind REST API v4

**Spec correction:** Spec 中 indicator key `margin_short_ratio`(原寫「融資使用率」)在實作中改為 `short_margin_ratio`(券資比 = 融券餘額 / 融資餘額 × 100)。整體市場 dataset 不含融資額度,無法算「使用率」;券資比是業界等同用途的指標。

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `stock/dashboard/backend/fetchers/margin.py` | **Delete** | 由 `chip_total.py` 取代,順帶不再需要 cloudscraper 抓 TWSE |
| `stock/dashboard/backend/fetchers/chip_total.py` | **Create** | 每日抓整體融資融券 + 整體三大法人,寫 6 個 indicator key |
| `stock/dashboard/backend/fetchers/chip_stock.py` | **Create** | 個股籌碼 lazy fetch + DB cache,複用 broker.py 模式 |
| `stock/dashboard/backend/db.py` | Modify | 加 `stock_chip_daily` table、`save_chip_daily_rows`、`get_chip_daily_range`、`get_latest_chip_date`;新增 `purge_old_data` 對 `stock_chip_daily` 的清理 |
| `stock/dashboard/backend/scheduler.py` | Modify | 移除 `margin` job,新增 `chip_total` job |
| `stock/dashboard/backend/app.py` | Modify | `INDICATOR_NAMES` 加 6 個 key、`FETCHERS` 加 `chip_total` 別名;新增 `/api/stocks/{ticker}/chip` endpoint |
| `stock/dashboard/backend/alerts.py` | Modify | `INDICATOR_LABELS` / `INDICATOR_UNITS` 加 6 個新 key 對應;移除舊 `margin` key |
| `stock/dashboard/backend/backfill.py` | Modify | 移除 `backfill_margin`,新增 `backfill_chip_total`;`__main__` 流程更新 |
| `stock/dashboard/frontend/index.html` | Modify | `margin` 卡片 key 改 `margin_balance`、新增 5 個指標卡片(融券餘額、券資比、外資/投信/自營淨買超) |
| `stock/dashboard/frontend/stock.html` | Modify | 在現有(已停用)券商卡下方新增「籌碼面」區塊(三大法人表 + 融資融券表) |
| `stock/dashboard/tests/test_chip.py` | **Create** | chip_total 解析、chip_stock 解析、`/chip` endpoint、DB helper 測試 |
| `stock/dashboard/backend/requirements.txt` | Modify | 移除 `cloudscraper>=1.2.71` 若 ndc.py 也已遷移(否則保留 — 確認後再決定) |

`requirements.txt` 處理在 Task 5 統一檢查(因為 `ndc.py` 跟 `backfill.py` 也在用 cloudscraper,刪除有風險,要看用量)。

---

## Task 1: 替換 margin.py — 整體融資融券

**目標**:用 FinMind 抓整體融資融券,以 3 個 indicator key 取代現有單一 `margin` key,既有歷史資料遷移到 `margin_balance`,index.html 卡片更新。

**Files:**
- Create: `stock/dashboard/backend/fetchers/chip_total.py`
- Create: `stock/dashboard/tests/test_chip.py`
- Modify: `stock/dashboard/backend/db.py`, `stock/dashboard/backend/scheduler.py`, `stock/dashboard/backend/app.py`, `stock/dashboard/backend/alerts.py`, `stock/dashboard/backend/backfill.py`, `stock/dashboard/frontend/index.html`
- Delete: `stock/dashboard/backend/fetchers/margin.py`

### Step 1.1: 寫第一個失敗測試(整體融資融券解析)

**File:** `stock/dashboard/tests/test_chip.py` (new)

- [ ] 建立檔案,內容:

```python
"""Chip fetcher tests."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import db
from app import app
from fetchers.chip_total import parse_total_margin

client = TestClient(app)


# Sample 來自 FinMind v4 GET /data?dataset=TaiwanStockTotalMarginPurchaseShortSale
# 一天 3 筆 row(MarginPurchase / MarginPurchaseMoney / ShortSale),長格式
SAMPLE_TOTAL_MARGIN = [
    {"name": "MarginPurchase",      "date": "2026-04-29",
     "TodayBalance": 8672780,        "YesBalance": 8677088,
     "buy": 353740, "sell": 349629, "Return": 8419},
    {"name": "ShortSale",            "date": "2026-04-29",
     "TodayBalance": 197420,         "YesBalance": 197613,
     "buy": 19169,  "sell": 20523,  "Return": 1547},
    {"name": "MarginPurchaseMoney", "date": "2026-04-29",
     "TodayBalance": 460963803000,   "YesBalance": 457112797000,
     "buy": 29073808000, "sell": 24578802000, "Return": 644000000},
]


def test_parse_total_margin_returns_three_indicators_per_day():
    out = parse_total_margin(SAMPLE_TOTAL_MARGIN)
    assert "2026-04-29" in out
    day = out["2026-04-29"]
    # margin_balance: MarginPurchaseMoney TodayBalance 換算億元
    assert day["margin_balance"] == pytest.approx(4609.638, rel=1e-3)
    # short_balance: ShortSale TodayBalance 千股(直接保留為「張」)
    assert day["short_balance"] == 197420
    # short_margin_ratio: 融券張 / 融資張 × 100
    assert day["short_margin_ratio"] == pytest.approx(2.276, rel=1e-2)
```

### Step 1.2: Run test to verify it fails

- [ ] 執行:

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_chip.py::test_parse_total_margin_returns_three_indicators_per_day -v
```

Expected: `FAILED` with `ImportError: cannot import name 'parse_total_margin' from 'fetchers.chip_total'` (檔案還不存在)

### Step 1.3: 建立 chip_total.py 含 parse_total_margin

**File:** `stock/dashboard/backend/fetchers/chip_total.py` (new)

- [ ] 建立檔案,內容:

```python
"""整體市場籌碼面 fetcher。

從 FinMind 抓:
- TaiwanStockTotalMarginPurchaseShortSale (整體融資融券)
- TaiwanStockTotalInstitutionalInvestors  (整體三大法人)  ← Task 2 加上

不帶 data_id,免費 quota 內每日 1-2 個 request 即可。
寫入 indicator_snapshots 沿用既有 indicator pipeline。
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator
from alerts import check_alerts

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()


def _request(dataset: str, start_date: str, end_date: str | None = None) -> list[dict]:
    params = {"dataset": dataset, "start_date": start_date}
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


def parse_total_margin(rows: list[dict]) -> dict[str, dict[str, float]]:
    """Long-format → {date: {margin_balance, short_balance, short_margin_ratio}}.

    rows 每筆有 name in {MarginPurchase, MarginPurchaseMoney, ShortSale}。
    margin_balance 取自 MarginPurchaseMoney.TodayBalance(元 → 億元),
    short_balance  取自 ShortSale.TodayBalance(張),
    short_margin_ratio = ShortSale.TodayBalance / MarginPurchase.TodayBalance × 100。
    """
    by_day: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        d = r.get("date")
        n = r.get("name")
        if not d or not n:
            continue
        by_day[d][n] = r

    result: dict[str, dict[str, float]] = {}
    for d, names in by_day.items():
        margin_money = names.get("MarginPurchaseMoney")
        margin_lots  = names.get("MarginPurchase")
        short        = names.get("ShortSale")
        if not (margin_money and margin_lots and short):
            continue
        margin_balance = round(float(margin_money["TodayBalance"]) / 1e8, 3)  # 元 → 億元
        short_balance = float(short["TodayBalance"])
        margin_lots_balance = float(margin_lots["TodayBalance"])
        ratio = round(short_balance / margin_lots_balance * 100, 3) if margin_lots_balance else 0
        result[d] = {
            "margin_balance":     margin_balance,
            "short_balance":      short_balance,
            "short_margin_ratio": ratio,
        }
    return result


def fetch_chip_total(start_date: str | None = None, end_date: str | None = None) -> None:
    """每日 cron 用:預設抓最近 5 天(涵蓋週末跳天),寫入 indicator_snapshots。

    Backfill 用:傳 start_date / end_date(YYYY-MM-DD)拉指定區間。
    """
    if not start_date:
        from datetime import timedelta
        start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

    # --- 整體融資融券 ---
    try:
        raw = _request("TaiwanStockTotalMarginPurchaseShortSale", start_date, end_date)
    except Exception as e:
        print(f"[chip_total] margin fetch error: {e}")
        return
    margin_by_day = parse_total_margin(raw)

    for d, vals in sorted(margin_by_day.items()):
        ts = datetime.strptime(d, "%Y-%m-%d")
        save_indicator("margin_balance",     vals["margin_balance"],
                       json.dumps({"unit": "億元", "date": d}), timestamp=ts)
        save_indicator("short_balance",      vals["short_balance"],
                       json.dumps({"unit": "張", "date": d}), timestamp=ts)
        save_indicator("short_margin_ratio", vals["short_margin_ratio"],
                       json.dumps({"unit": "%", "date": d}), timestamp=ts)
        # 用最新一天值觸發 alerts(只有 cron 模式;backfill 不該觸發 alert)
    if margin_by_day:
        latest = max(margin_by_day.keys())
        check_alerts("indicator", "margin_balance",     margin_by_day[latest]["margin_balance"])
        check_alerts("indicator", "short_balance",      margin_by_day[latest]["short_balance"])
        check_alerts("indicator", "short_margin_ratio", margin_by_day[latest]["short_margin_ratio"])
        print(f"[chip_total] margin {latest}: balance={margin_by_day[latest]['margin_balance']} 億, "
              f"short={margin_by_day[latest]['short_balance']:.0f} 張, "
              f"ratio={margin_by_day[latest]['short_margin_ratio']:.2f}%")
```

### Step 1.4: 確認測試通過

- [ ] 執行:

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_chip.py::test_parse_total_margin_returns_three_indicators_per_day -v
```

Expected: `1 passed`

### Step 1.5: db.py — indicator key 遷移(margin → margin_balance)

**File:** `stock/dashboard/backend/db.py`

- [ ] 在 `init_db()` 函式末尾(`conn.executescript(...)` 後),加上 idempotent migration:

```python
        # --- 既有歷史資料遷移:margin → margin_balance ---
        # 第一次部署 chip_total 後執行;之後每次 init_db 也安全(找不到就 no-op)。
        conn.execute(
            "UPDATE indicator_snapshots SET indicator='margin_balance' WHERE indicator='margin'"
        )
```

說明:`UPDATE` 在沒符合條件 row 時是 no-op,可重複呼叫。每次 process 啟動都跑一次,確保 key rename 一致。

### Step 1.6: scheduler.py — 換掉 margin job

**File:** `stock/dashboard/backend/scheduler.py`

- [ ] 修改 import 段(L7):

```python
- from fetchers.margin import fetch_margin
+ from fetchers.chip_total import fetch_chip_total
```

- [ ] 修改 cron 區段(L28),把:

```python
scheduler.add_job(fetch_margin,     CronTrigger(hour=18, minute=0, timezone=TST), id="margin",     replace_existing=True)
```

替換成:

```python
scheduler.add_job(fetch_chip_total, CronTrigger(hour=18, minute=0, timezone=TST), id="chip_total", replace_existing=True)
```

### Step 1.7: app.py — INDICATOR_NAMES + FETCHERS

**File:** `stock/dashboard/backend/app.py`

- [ ] 修改 import(L24):

```python
- from fetchers.margin import fetch_margin
+ from fetchers.chip_total import fetch_chip_total
```

- [ ] 修改 `FETCHERS`(L46):刪 `"margin": fetch_margin,`,加 `"chip_total": fetch_chip_total,`(用於手動 refresh endpoint)

```python
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
```

- [ ] 修改 `INDICATOR_NAMES`(L57):

```python
INDICATOR_NAMES = ["taiex", "fx", "fear_greed", "margin_balance", "short_balance",
                   "short_margin_ratio", "ndc", "tw_volume", "us_volume"]
```

### Step 1.8: alerts.py — labels / units 更新

**File:** `stock/dashboard/backend/alerts.py`

- [ ] 修改 `INDICATOR_LABELS`(L19),刪 `"margin"`,加新 keys:

```python
INDICATOR_LABELS = {
    "taiex":              "加權指數",
    "fx":                 "台幣兌美金",
    "fear_greed":         "恐懼與貪婪指數",
    "margin_balance":     "台股融資餘額",
    "short_balance":      "台股融券餘額",
    "short_margin_ratio": "台股券資比",
    "ndc":                "國發會景氣指標",
}
```

- [ ] 修改 `INDICATOR_UNITS`(L27),刪 `"margin"`,加新 keys:

```python
INDICATOR_UNITS = {
    "taiex":              "點",
    "fx":                 "TWD",
    "fear_greed":         "",
    "margin_balance":     "億元",
    "short_balance":      "張",
    "short_margin_ratio": "%",
    "ndc":                "分",
}
```

### Step 1.9: backfill.py — 移除 backfill_margin,加 backfill_chip_total

**File:** `stock/dashboard/backend/backfill.py`

- [ ] 刪除函式 `backfill_margin`(L192-207)。

- [ ] 在 `backfill_fear_greed` 函式之後新增:

```python
def backfill_chip_total(days: int = 365):
    """一次性從 FinMind 拉近 N 天的整體融資融券,寫入 indicator_snapshots。"""
    from datetime import timedelta
    from fetchers.chip_total import fetch_chip_total
    today = datetime.now()
    start = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    print(f"[backfill] chip_total {start} → {end} …")
    fetch_chip_total(start_date=start, end_date=end)
    print("  Done")
```

- [ ] 修改 `__main__`(L210)分支:

```python
if __name__ == "__main__":
    import sys as _sys
    init_db()
-   if len(_sys.argv) > 1 and _sys.argv[1] == "margin":
-       backfill_margin(int(_sys.argv[2]) if len(_sys.argv) > 2 else 365)
+   if len(_sys.argv) > 1 and _sys.argv[1] == "chip_total":
+       backfill_chip_total(int(_sys.argv[2]) if len(_sys.argv) > 2 else 365)
    elif len(_sys.argv) > 1 and _sys.argv[1] == "fear_greed":
        backfill_fear_greed()
    elif len(_sys.argv) > 1 and _sys.argv[1] == "volume":
        backfill_tw_volume()
        backfill_us_volume()
    else:
        backfill_taiex()
        backfill_fx()
        backfill_ndc()
        backfill_fear_greed()
        backfill_tw_volume()
        backfill_us_volume()
-       backfill_margin(365)
+       backfill_chip_total(365)
    print("[backfill] Done.")
```

### Step 1.10: index.html — margin 卡片改名 + 加 2 個新卡片

**File:** `stock/dashboard/frontend/index.html`

- [ ] 找到 L218-229 的 margin 卡片區塊,把所有 `margin` 改為 `margin_balance`(`onclick="refreshIndicator('margin')"` → `'margin_balance'`,`id="margin-value"` → `"margin_balance-value"` 等)。再在這張卡片後面緊接著加上 2 個新卡片(融券餘額、券資比),沿用既有 card 結構:

```html
<!-- 台股融券餘額 -->
<div class="card">
  <div class="card-header">
    <span class="card-label">台股融券餘額</span>
    <button class="refresh-btn" onclick="refreshIndicator('short_balance')">↻ 更新</button>
  </div>
  <div class="stat-row">
    <div class="card-value" id="short_balance-value">—</div>
    <span class="badge" id="short_balance-badge"></span>
  </div>
  <div class="chart-wrap"><canvas id="chart-short_balance"></canvas></div>
  <div class="card-sub" id="short_balance-sub"></div>
</div>

<!-- 台股券資比 -->
<div class="card">
  <div class="card-header">
    <span class="card-label">台股券資比</span>
    <button class="refresh-btn" onclick="refreshIndicator('short_margin_ratio')">↻ 更新</button>
  </div>
  <div class="stat-row">
    <div class="card-value" id="short_margin_ratio-value">—</div>
    <span class="badge" id="short_margin_ratio-badge"></span>
  </div>
  <div class="chart-wrap"><canvas id="chart-short_margin_ratio"></canvas></div>
  <div class="card-sub" id="short_margin_ratio-sub"></div>
</div>
```

- [ ] 修改 `loadDashboard()` 中既有的 margin 區塊(原 L416-419):

```javascript
// 從:
if (data.margin) {
  document.getElementById('margin-value').textContent = data.margin.value.toFixed(0) + ' 億';
  document.getElementById('margin-sub').textContent = '更新 ' + fmtDate(data.margin.timestamp);
}

// 改成:
if (data.margin_balance) {
  document.getElementById('margin_balance-value').textContent = data.margin_balance.value.toFixed(0) + ' 億';
  document.getElementById('margin_balance-sub').textContent = '更新 ' + fmtDate(data.margin_balance.timestamp);
}
if (data.short_balance) {
  // 千張更易讀
  document.getElementById('short_balance-value').textContent = (data.short_balance.value / 1000).toFixed(0) + ' 千張';
  document.getElementById('short_balance-sub').textContent = '更新 ' + fmtDate(data.short_balance.timestamp);
}
if (data.short_margin_ratio) {
  document.getElementById('short_margin_ratio-value').textContent = data.short_margin_ratio.value.toFixed(2) + ' %';
  document.getElementById('short_margin_ratio-sub').textContent = '更新 ' + fmtDate(data.short_margin_ratio.timestamp);
}
```

- [ ] 修改 `loadHistories()` 中既有 array / map(原 L470-472):

```javascript
// 從:
const indicators = ['taiex', 'tw_volume', 'us_volume', 'fear_greed', 'margin', 'ndc', 'fx'];
const units = { taiex: '點', fear_greed: '指數', margin: '億元', ndc: '分', fx: 'TWD', tw_volume: '億元', us_volume: '億股' };
const colors = { taiex: '#4ade80', fear_greed: '#fbbf24', margin: '#60a5fa', ndc: '#fbbf24', fx: '#a78bfa', tw_volume: '#f97316', us_volume: '#ec4899' };

// 改成:
const indicators = ['taiex', 'tw_volume', 'us_volume', 'fear_greed',
                    'margin_balance', 'short_balance', 'short_margin_ratio',
                    'ndc', 'fx'];
const units  = { taiex: '點', fear_greed: '指數', ndc: '分', fx: 'TWD',
                 tw_volume: '億元', us_volume: '億股',
                 margin_balance: '億元', short_balance: '張', short_margin_ratio: '%' };
const colors = { taiex: '#4ade80', fear_greed: '#fbbf24', ndc: '#fbbf24', fx: '#a78bfa',
                 tw_volume: '#f97316', us_volume: '#ec4899',
                 margin_balance: '#60a5fa', short_balance: '#fb923c', short_margin_ratio: '#a3a3a3' };
```

- [ ] 修改 alert section 的 `INDICATOR_LABELS`(原 L539-545):

```javascript
const INDICATOR_LABELS = {
  taiex:               '加權指數',
  fx:                  '台幣兌美金',
  fear_greed:          '恐懼與貪婪指數',
  margin_balance:      '台股融資餘額',
  short_balance:       '台股融券餘額',
  short_margin_ratio:  '台股券資比',
  ndc:                 '國發會景氣指標',
};
```

說明:index.html 是純 JS,無 build step,改完直接重整即可。

### Step 1.11: 刪除 margin.py

- [ ] 執行:

```bash
git rm stock/dashboard/backend/fetchers/margin.py
```

### Step 1.12: 跑全部 backend 測試確認無 regression

- [ ] 執行:

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v
```

Expected: 全部 pass(包含新增的 `test_parse_total_margin_returns_three_indicators_per_day`,以及既有 broker 等測試)。如果有 import error,通常是有檔案還在 import `fetchers.margin`,把那些 import 也清掉。

### Step 1.13: Commit

- [ ] 執行:

```bash
git add stock/dashboard/backend/fetchers/chip_total.py \
        stock/dashboard/backend/db.py \
        stock/dashboard/backend/scheduler.py \
        stock/dashboard/backend/app.py \
        stock/dashboard/backend/alerts.py \
        stock/dashboard/backend/backfill.py \
        stock/dashboard/frontend/index.html \
        stock/dashboard/tests/test_chip.py
git rm stock/dashboard/backend/fetchers/margin.py 2>/dev/null || true
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): replace margin.py with FinMind chip_total (T1)

新增 fetchers/chip_total.py 從 FinMind TaiwanStockTotalMarginPurchaseShortSale
抓整體融資融券,以 3 個 indicator key 取代既有單一 margin key:
margin_balance(融資餘額,億元)、short_balance(融券餘額,張)、
short_margin_ratio(券資比,%)。db.py 加 idempotent migration 把舊 margin
key 改名為 margin_balance 保留歷史。前端 index.html 對應更新並新增 2 張
卡片。順帶移除 cloudscraper 抓 TWSE 路徑的 IP 封鎖風險。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 整體三大法人

**目標**:在 `chip_total.py` 加上抓 `TaiwanStockTotalInstitutionalInvestors`,寫入 3 個新 indicator key,index.html 加 3 張卡片。

**Files:**
- Modify: `stock/dashboard/backend/fetchers/chip_total.py`, `stock/dashboard/backend/app.py`, `stock/dashboard/backend/alerts.py`, `stock/dashboard/frontend/index.html`, `stock/dashboard/tests/test_chip.py`

### Step 2.1: 寫第一個失敗測試(整體三大法人解析)

**File:** `stock/dashboard/tests/test_chip.py`(append)

- [ ] 在檔案末尾追加:

```python
from fetchers.chip_total import parse_total_institutional


# Sample 來自 FinMind v4 GET /data?dataset=TaiwanStockTotalInstitutionalInvestors
# 一天 6 筆 row,name 區分法人類別,單位是「元」
SAMPLE_TOTAL_INST = [
    {"name": "Foreign_Investor",   "date": "2026-04-29",
     "buy": 338372913624, "sell": 386520362349},
    {"name": "Foreign_Dealer_Self","date": "2026-04-29",
     "buy": 0,            "sell": 0},
    {"name": "Investment_Trust",   "date": "2026-04-29",
     "buy": 22631309887,  "sell": 20502983872},
    {"name": "Dealer_self",        "date": "2026-04-29",
     "buy": 4610504372,   "sell": 6343282634},
    {"name": "Dealer_Hedging",     "date": "2026-04-29",
     "buy": 25753523687,  "sell": 25619864056},
    {"name": "total",              "date": "2026-04-29",
     "buy": 391368251570, "sell": 438986492911},
]


def test_parse_total_institutional_returns_three_net_buys_per_day():
    out = parse_total_institutional(SAMPLE_TOTAL_INST)
    day = out["2026-04-29"]
    # 外資 = Foreign_Investor + Foreign_Dealer_Self;(338.37 - 386.52 + 0 - 0) 億 = -48.15
    assert day["total_foreign_net"] == pytest.approx(-481.474, rel=1e-2)
    # 投信:(22.63 - 20.50)億 ≈ 21.28 億
    assert day["total_trust_net"] == pytest.approx(21.283, rel=1e-2)
    # 自營商 = Dealer_self + Dealer_Hedging;((4.61 - 6.34) + (25.75 - 25.62))億 ≈ -15.99 億
    assert day["total_dealer_net"] == pytest.approx(-15.991, rel=1e-2)
```

### Step 2.2: 跑測試確認 fail

- [ ] 執行:

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_chip.py::test_parse_total_institutional_returns_three_net_buys_per_day -v
```

Expected: `FAILED` with `ImportError: cannot import name 'parse_total_institutional'`。

### Step 2.3: 在 chip_total.py 加 parse + fetch

**File:** `stock/dashboard/backend/fetchers/chip_total.py`

- [ ] 在 `parse_total_margin` 之後新增 `parse_total_institutional`:

```python
def parse_total_institutional(rows: list[dict]) -> dict[str, dict[str, float]]:
    """Long-format → {date: {total_foreign_net, total_trust_net, total_dealer_net}}.

    name 對應:
    - 外資  = Foreign_Investor + Foreign_Dealer_Self
    - 投信  = Investment_Trust
    - 自營商 = Dealer_self + Dealer_Hedging
    淨買超 = (buy - sell) 換算億元。
    """
    by_day: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        d, n = r.get("date"), r.get("name")
        if not d or not n:
            continue
        by_day[d][n] = r

    def _net(rec: dict | None) -> float:
        if not rec:
            return 0
        return float(rec.get("buy", 0) or 0) - float(rec.get("sell", 0) or 0)

    result: dict[str, dict[str, float]] = {}
    for d, names in by_day.items():
        foreign = _net(names.get("Foreign_Investor")) + _net(names.get("Foreign_Dealer_Self"))
        trust   = _net(names.get("Investment_Trust"))
        dealer  = _net(names.get("Dealer_self")) + _net(names.get("Dealer_Hedging"))
        result[d] = {
            "total_foreign_net": round(foreign / 1e8, 3),
            "total_trust_net":   round(trust   / 1e8, 3),
            "total_dealer_net":  round(dealer  / 1e8, 3),
        }
    return result
```

- [ ] 修改 `fetch_chip_total`,在融資融券寫入後追加抓三大法人。最終 `fetch_chip_total` 形如:

```python
def fetch_chip_total(start_date: str | None = None, end_date: str | None = None) -> None:
    if not start_date:
        from datetime import timedelta
        start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

    # --- 整體融資融券 ---
    try:
        raw = _request("TaiwanStockTotalMarginPurchaseShortSale", start_date, end_date)
    except Exception as e:
        print(f"[chip_total] margin fetch error: {e}")
    else:
        margin_by_day = parse_total_margin(raw)
        for d, vals in sorted(margin_by_day.items()):
            ts = datetime.strptime(d, "%Y-%m-%d")
            for key in ("margin_balance", "short_balance", "short_margin_ratio"):
                save_indicator(key, vals[key],
                               json.dumps({"date": d}), timestamp=ts)
        if margin_by_day:
            latest = max(margin_by_day.keys())
            for key in ("margin_balance", "short_balance", "short_margin_ratio"):
                check_alerts("indicator", key, margin_by_day[latest][key])
            print(f"[chip_total] margin {latest}: balance={margin_by_day[latest]['margin_balance']} 億, "
                  f"short={margin_by_day[latest]['short_balance']:.0f} 張, "
                  f"ratio={margin_by_day[latest]['short_margin_ratio']:.2f}%")

    # --- 整體三大法人 ---
    try:
        raw = _request("TaiwanStockTotalInstitutionalInvestors", start_date, end_date)
    except Exception as e:
        print(f"[chip_total] institutional fetch error: {e}")
        return
    inst_by_day = parse_total_institutional(raw)
    for d, vals in sorted(inst_by_day.items()):
        ts = datetime.strptime(d, "%Y-%m-%d")
        for key in ("total_foreign_net", "total_trust_net", "total_dealer_net"):
            save_indicator(key, vals[key],
                           json.dumps({"unit": "億元", "date": d}), timestamp=ts)
    if inst_by_day:
        latest = max(inst_by_day.keys())
        for key in ("total_foreign_net", "total_trust_net", "total_dealer_net"):
            check_alerts("indicator", key, inst_by_day[latest][key])
        print(f"[chip_total] inst {latest}: foreign={inst_by_day[latest]['total_foreign_net']} 億, "
              f"trust={inst_by_day[latest]['total_trust_net']} 億, "
              f"dealer={inst_by_day[latest]['total_dealer_net']} 億")
```

### Step 2.4: 跑測試確認 pass

- [ ] 執行:

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_chip.py -v
```

Expected: 兩個 chip parse 測試都 pass。

### Step 2.5: app.py 加 INDICATOR_NAMES

**File:** `stock/dashboard/backend/app.py`

- [ ] 修改 `INDICATOR_NAMES`(在 Task 1 已加 3 個 key 的版本上再加 3 個):

```python
INDICATOR_NAMES = [
    "taiex", "fx", "fear_greed",
    "margin_balance", "short_balance", "short_margin_ratio",
    "total_foreign_net", "total_trust_net", "total_dealer_net",
    "ndc", "tw_volume", "us_volume",
]
```

### Step 2.6: alerts.py 加新 labels / units

**File:** `stock/dashboard/backend/alerts.py`

- [ ] `INDICATOR_LABELS` 加:

```python
    "total_foreign_net": "外資淨買超",
    "total_trust_net":   "投信淨買超",
    "total_dealer_net":  "自營商淨買超",
```

- [ ] `INDICATOR_UNITS` 加:

```python
    "total_foreign_net": "億元",
    "total_trust_net":   "億元",
    "total_dealer_net":  "億元",
```

### Step 2.7: index.html 加 3 張法人卡片

**File:** `stock/dashboard/frontend/index.html`

- [ ] 在 Task 1 加的「券資比」卡片後緊接著加 3 張卡片(外資/投信/自營淨買超),沿用同款 card 結構,id 對應 `total_foreign_net` / `total_trust_net` / `total_dealer_net`。

```html
<!-- 外資淨買超 -->
<div class="card">
  <div class="card-header">
    <span class="card-label">外資淨買超</span>
    <button class="refresh-btn" onclick="refreshIndicator('total_foreign_net')">↻ 更新</button>
  </div>
  <div class="stat-row">
    <div class="card-value" id="total_foreign_net-value">—</div>
    <span class="badge" id="total_foreign_net-badge"></span>
  </div>
  <div class="chart-wrap"><canvas id="chart-total_foreign_net"></canvas></div>
  <div class="card-sub" id="total_foreign_net-sub"></div>
</div>

<!-- 投信淨買超 -->
<div class="card">
  <div class="card-header">
    <span class="card-label">投信淨買超</span>
    <button class="refresh-btn" onclick="refreshIndicator('total_trust_net')">↻ 更新</button>
  </div>
  <div class="stat-row">
    <div class="card-value" id="total_trust_net-value">—</div>
    <span class="badge" id="total_trust_net-badge"></span>
  </div>
  <div class="chart-wrap"><canvas id="chart-total_trust_net"></canvas></div>
  <div class="card-sub" id="total_trust_net-sub"></div>
</div>

<!-- 自營商淨買超 -->
<div class="card">
  <div class="card-header">
    <span class="card-label">自營商淨買超</span>
    <button class="refresh-btn" onclick="refreshIndicator('total_dealer_net')">↻ 更新</button>
  </div>
  <div class="stat-row">
    <div class="card-value" id="total_dealer_net-value">—</div>
    <span class="badge" id="total_dealer_net-badge"></span>
  </div>
  <div class="chart-wrap"><canvas id="chart-total_dealer_net"></canvas></div>
  <div class="card-sub" id="total_dealer_net-sub"></div>
</div>
```

- [ ] 在 `loadDashboard()` 中(Task 1 加的 short_margin_ratio 區塊之後),加 3 個 net 指標處理:

```javascript
for (const k of ['total_foreign_net', 'total_trust_net', 'total_dealer_net']) {
  if (data[k]) {
    const v = data[k].value;
    const el = document.getElementById(k + '-value');
    el.textContent = (v >= 0 ? '+' : '') + v.toFixed(2) + ' 億';
    el.className = 'card-value ' + (v >= 0 ? 'up' : 'down');
    document.getElementById(k + '-sub').textContent = '更新 ' + fmtDate(data[k].timestamp);
  }
}
```

- [ ] 在 `loadHistories()` 把 3 個新 key 加進 `indicators` / `units` / `colors`(Task 1 已加 3 個的版本上再加 3 個):

```javascript
const indicators = ['taiex', 'tw_volume', 'us_volume', 'fear_greed',
                    'margin_balance', 'short_balance', 'short_margin_ratio',
                    'total_foreign_net', 'total_trust_net', 'total_dealer_net',
                    'ndc', 'fx'];
const units  = { taiex: '點', fear_greed: '指數', ndc: '分', fx: 'TWD',
                 tw_volume: '億元', us_volume: '億股',
                 margin_balance: '億元', short_balance: '張', short_margin_ratio: '%',
                 total_foreign_net: '億元', total_trust_net: '億元', total_dealer_net: '億元' };
const colors = { taiex: '#4ade80', fear_greed: '#fbbf24', ndc: '#fbbf24', fx: '#a78bfa',
                 tw_volume: '#f97316', us_volume: '#ec4899',
                 margin_balance: '#60a5fa', short_balance: '#fb923c', short_margin_ratio: '#a3a3a3',
                 total_foreign_net: '#22d3ee', total_trust_net: '#a78bfa', total_dealer_net: '#facc15' };
```

- [ ] 把 3 個 net key 加進 `INDICATOR_LABELS`(在 Task 1 已更新的版本上再加 3 個):

```javascript
const INDICATOR_LABELS = {
  taiex:               '加權指數',
  fx:                  '台幣兌美金',
  fear_greed:          '恐懼與貪婪指數',
  margin_balance:      '台股融資餘額',
  short_balance:       '台股融券餘額',
  short_margin_ratio:  '台股券資比',
  total_foreign_net:   '外資淨買超',
  total_trust_net:     '投信淨買超',
  total_dealer_net:    '自營商淨買超',
  ndc:                 '國發會景氣指標',
};
```

### Step 2.8: 跑測試 + 手動 smoke

- [ ] 執行:

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v
# 手動驗證:啟動後端
DB_PATH=:memory: python -c "
import sys; sys.path.insert(0, '.')
from db import init_db, get_latest_indicator
from fetchers.chip_total import fetch_chip_total
init_db()
fetch_chip_total()
for k in ('margin_balance','short_balance','short_margin_ratio','total_foreign_net','total_trust_net','total_dealer_net'):
    print(k, get_latest_indicator(k))
"
```

Expected: 6 個 key 都應該印出 row(value, timestamp, ...)。如果 FinMind 暫時 down,測試也會失敗,改用 mock 驗。

### Step 2.9: Commit

- [ ] 執行:

```bash
git add stock/dashboard/backend/fetchers/chip_total.py \
        stock/dashboard/backend/app.py \
        stock/dashboard/backend/alerts.py \
        stock/dashboard/frontend/index.html \
        stock/dashboard/tests/test_chip.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add total institutional investors chip (T2)

在 chip_total.py 加抓 TaiwanStockTotalInstitutionalInvestors,寫入 3 個
indicator key:total_foreign_net、total_trust_net、total_dealer_net(全為
億元、可正可負的淨買超)。前端 index.html 加 3 張對應卡片。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 個股籌碼 backend(fetcher + DB + endpoint)

**目標**:新增個股版 fetcher 走 lazy fetch + cache,新表 `stock_chip_daily`,新 endpoint `/api/stocks/{ticker}/chip`。

**Files:**
- Create: `stock/dashboard/backend/fetchers/chip_stock.py`
- Modify: `stock/dashboard/backend/db.py`, `stock/dashboard/backend/app.py`, `stock/dashboard/tests/test_chip.py`

### Step 3.1: 寫個股 fetcher 失敗測試(parse + lazy 行為)

**File:** `stock/dashboard/tests/test_chip.py`(append)

- [ ] 追加:

```python
from fetchers.chip_stock import parse_stock_inst, parse_stock_margin, fetch_stock_chip


# 個股三大法人(長格式,name 區分)
SAMPLE_STOCK_INST = [
    {"date": "2026-04-29", "stock_id": "2330",
     "name": "Foreign_Investor",     "buy": 5_000_000, "sell": 3_000_000},
    {"date": "2026-04-29", "stock_id": "2330",
     "name": "Foreign_Dealer_Self",  "buy": 0,         "sell": 0},
    {"date": "2026-04-29", "stock_id": "2330",
     "name": "Investment_Trust",     "buy": 100_000,   "sell": 200_000},
    {"date": "2026-04-29", "stock_id": "2330",
     "name": "Dealer_self",          "buy": 50_000,    "sell": 80_000},
    {"date": "2026-04-29", "stock_id": "2330",
     "name": "Dealer_Hedging",       "buy": 30_000,    "sell": 20_000},
]


def test_parse_stock_inst_aggregates_to_three_net_lots():
    out = parse_stock_inst(SAMPLE_STOCK_INST, ticker="2330.TW")
    assert len(out) == 1
    row = out[0]
    assert row["ticker"] == "2330.TW"
    assert row["date"] == "2026-04-29"
    assert row["foreign_buy"]  == 5_000_000
    assert row["foreign_sell"] == 3_000_000
    assert row["trust_buy"]    == 100_000
    assert row["trust_sell"]   == 200_000
    assert row["dealer_buy"]   == 50_000 + 30_000
    assert row["dealer_sell"]  == 80_000 + 20_000


# 個股融資融券(寬格式 — 一天一筆)
SAMPLE_STOCK_MARGIN = [
    {"date": "2026-04-29", "stock_id": "2330",
     "MarginPurchaseTodayBalance": 12345,
     "ShortSaleTodayBalance": 678,
     "MarginPurchaseBuy": 100, "MarginPurchaseSell": 80,
     "ShortSaleBuy": 5, "ShortSaleSell": 7,
     "MarginPurchaseLimit": 0, "ShortSaleLimit": 0,
     "MarginPurchaseCashRepayment": 0, "ShortSaleCashRepayment": 0,
     "MarginPurchaseYesterdayBalance": 0, "ShortSaleYesterdayBalance": 0,
     "OffsetLoanAndShort": 0, "Note": ""},
]


def test_parse_stock_margin_extracts_balances():
    out = parse_stock_margin(SAMPLE_STOCK_MARGIN, ticker="2330.TW")
    assert len(out) == 1
    row = out[0]
    assert row["margin_balance"] == 12345
    assert row["short_balance"]  == 678
```

### Step 3.2: 跑測試確認 fail

- [ ] 執行:

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_chip.py -v
```

Expected: 兩個新 test fail with `ImportError`。

### Step 3.3: 建立 chip_stock.py

**File:** `stock/dashboard/backend/fetchers/chip_stock.py` (new)

- [ ] 建立檔案:

```python
"""個股籌碼 fetcher,lazy fetch + DB cache。

複用 broker.py 同模式:
- 從 watchlist ticker 解析 FinMind data_id(去 .TW / .TWO 後綴)
- 從 DB 取 latest cached date,僅補 delta 區間
- 預設首次拉 60 個交易日(用日曆日 90 天概抓涵蓋週末假日)

寫入新表 stock_chip_daily(ticker, date, foreign_buy, foreign_sell,
trust_buy, trust_sell, dealer_buy, dealer_sell, margin_balance,
short_balance)。API 層計算 *_net = buy - sell。
"""
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_chip_daily_rows, get_latest_chip_date

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()

# 預設首次拉 90 個日曆天 ≒ 60 個交易日(涵蓋週末假日)
DEFAULT_LOOKBACK_DAYS = 90


def to_finmind_id(ticker: str) -> str | None:
    """Reuse 同 broker.py 邏輯:把 watchlist ticker 轉成 FinMind 純數字代碼。"""
    t = (ticker or "").upper().strip()
    if t.endswith(".TW"):
        return t[:-3]
    if t.endswith(".TWO"):
        return t[:-4]
    if t.isdigit():
        return t
    return None


def _request(dataset: str, stock_id: str, start_date: str, end_date: str) -> list[dict]:
    params = {
        "dataset":    dataset,
        "data_id":    stock_id,
        "start_date": start_date,
        "end_date":   end_date,
    }
    headers = {}
    if FINMIND_TOKEN:
        headers["Authorization"] = f"Bearer {FINMIND_TOKEN}"
    r = requests.get(FINMIND_URL, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") not in (200, None):
        raise RuntimeError(f"FinMind {dataset} error: {payload.get('msg') or payload}")
    return payload.get("data") or []


def parse_stock_inst(rows: list[dict], ticker: str) -> list[dict]:
    """Long-format 個股三大法人 → per-day record。"""
    by_day: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        d, n = r.get("date"), r.get("name")
        if not d or not n:
            continue
        by_day[d][n] = r

    def _bs(rec: dict | None) -> tuple[float, float]:
        if not rec:
            return 0, 0
        return float(rec.get("buy", 0) or 0), float(rec.get("sell", 0) or 0)

    out: list[dict] = []
    for d, names in by_day.items():
        f_b, f_s = _bs(names.get("Foreign_Investor"))
        fd_b, fd_s = _bs(names.get("Foreign_Dealer_Self"))
        t_b, t_s = _bs(names.get("Investment_Trust"))
        ds_b, ds_s = _bs(names.get("Dealer_self"))
        dh_b, dh_s = _bs(names.get("Dealer_Hedging"))
        out.append({
            "ticker": ticker,
            "date":   d,
            "foreign_buy":  f_b + fd_b,
            "foreign_sell": f_s + fd_s,
            "trust_buy":    t_b,
            "trust_sell":   t_s,
            "dealer_buy":   ds_b + dh_b,
            "dealer_sell":  ds_s + dh_s,
            "margin_balance": None,
            "short_balance":  None,
        })
    return out


def parse_stock_margin(rows: list[dict], ticker: str) -> list[dict]:
    """Wide-format 個股融資融券 → per-day record(只取 *TodayBalance 欄)。"""
    out: list[dict] = []
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        out.append({
            "ticker": ticker,
            "date":   d,
            "foreign_buy":  None,
            "foreign_sell": None,
            "trust_buy":    None,
            "trust_sell":   None,
            "dealer_buy":   None,
            "dealer_sell":  None,
            "margin_balance": float(r.get("MarginPurchaseTodayBalance") or 0),
            "short_balance":  float(r.get("ShortSaleTodayBalance") or 0),
        })
    return out


def _merge(rows_a: list[dict], rows_b: list[dict]) -> list[dict]:
    """Merge two per-day records lists by (ticker, date). 後者覆蓋前者非空欄位。"""
    by_key: dict[tuple[str, str], dict] = {}
    for r in rows_a + rows_b:
        k = (r["ticker"], r["date"])
        existing = by_key.get(k, {})
        merged = {**existing, **{k_: v for k_, v in r.items() if v is not None}}
        # 確保 schema 完整
        for f in ("foreign_buy","foreign_sell","trust_buy","trust_sell",
                  "dealer_buy","dealer_sell","margin_balance","short_balance"):
            merged.setdefault(f, None)
        merged["ticker"] = r["ticker"]
        merged["date"]   = r["date"]
        by_key[k] = merged
    return sorted(by_key.values(), key=lambda x: x["date"])


def fetch_stock_chip(ticker: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> bool:
    """Lazy fetch + DB cache,失敗回 False(不擋住其他指標)。"""
    stock_id = to_finmind_id(ticker)
    if stock_id is None:
        return False

    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest = get_latest_chip_date(ticker)
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
        inst_raw = _request("TaiwanStockInstitutionalInvestorsBuySell", stock_id, start_date, end_date)
        margin_raw = _request("TaiwanStockMarginPurchaseShortSale", stock_id, start_date, end_date)
    except Exception as e:
        print(f"[chip_stock] {ticker} fetch error: {e}")
        return False

    inst_rows   = parse_stock_inst(inst_raw, ticker)
    margin_rows = parse_stock_margin(margin_raw, ticker)
    merged = _merge(inst_rows, margin_rows)
    if not merged:
        return True
    save_chip_daily_rows(merged)
    print(f"[chip_stock] {ticker} {start_date}~{end_date}: {len(merged)} chip-day rows")
    return True
```

### Step 3.4: db.py 加新 table + helpers

**File:** `stock/dashboard/backend/db.py`

- [ ] `init_db()` 中 `executescript` 字串內(在 `stock_broker_daily` 區塊之後),加新 table:

```python
            CREATE TABLE IF NOT EXISTS stock_chip_daily (
                ticker         TEXT NOT NULL,
                date           TEXT NOT NULL,
                foreign_buy    REAL,
                foreign_sell   REAL,
                trust_buy      REAL,
                trust_sell     REAL,
                dealer_buy     REAL,
                dealer_sell    REAL,
                margin_balance REAL,
                short_balance  REAL,
                PRIMARY KEY (ticker, date)
            );
            CREATE INDEX IF NOT EXISTS idx_chip_ticker_date
                ON stock_chip_daily(ticker, date);
```

- [ ] 在 `get_latest_broker_date` 之後新增 3 個 helpers:

```python
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

- [ ] `purge_old_data` 加一行清理新表:

```python
        conn.execute("DELETE FROM stock_chip_daily WHERE date<?", (cutoff_date,))
```

### Step 3.5: 跑 parse 測試確認 pass

- [ ] 執行:

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_chip.py -v
```

Expected: 4 個 chip 測試都 pass。

### Step 3.6: 寫 endpoint 整合測試

**File:** `stock/dashboard/tests/test_chip.py`(append)

- [ ] 追加:

```python
def _seed_chip_rows(ticker: str, days_data: list[dict]) -> None:
    """Helper:直接塞 chip rows 進 DB(略過 fetch)。"""
    rows = []
    for d in days_data:
        rows.append({
            "ticker": ticker, "date": d["date"],
            "foreign_buy":  d.get("foreign_buy"),  "foreign_sell": d.get("foreign_sell"),
            "trust_buy":    d.get("trust_buy"),    "trust_sell":   d.get("trust_sell"),
            "dealer_buy":   d.get("dealer_buy"),   "dealer_sell":  d.get("dealer_sell"),
            "margin_balance": d.get("margin_balance"),
            "short_balance":  d.get("short_balance"),
        })
    db.save_chip_daily_rows(rows)


def test_chip_endpoint_returns_net_values():
    db.init_db()
    _seed_chip_rows("2330.TW", [
        {"date": "2026-04-29",
         "foreign_buy": 5_000_000, "foreign_sell": 3_000_000,
         "trust_buy": 100_000, "trust_sell": 200_000,
         "dealer_buy": 80_000, "dealer_sell": 100_000,
         "margin_balance": 12345, "short_balance": 678},
    ])
    # patch fetch 不要打網路
    with patch("fetchers.chip_stock.fetch_stock_chip", return_value=True):
        r = client.get("/api/stocks/2330.TW/chip?days=20")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "2330.TW"
    assert body["ok"] is True
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["foreign_net"] == 2_000_000
    assert row["trust_net"]   == -100_000
    assert row["dealer_net"]  == -20_000
    assert row["margin_balance"] == 12345
    assert row["short_balance"]  == 678


def test_chip_endpoint_rejects_non_taiwan_ticker():
    r = client.get("/api/stocks/AAPL/chip")
    assert r.status_code == 400
```

### Step 3.7: 跑 endpoint 測試確認 fail(endpoint 還沒做)

- [ ] 執行:

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_chip.py::test_chip_endpoint_returns_net_values -v
```

Expected: `FAILED` with 404 or function not implemented.

### Step 3.8: app.py 加 endpoint

**File:** `stock/dashboard/backend/app.py`

- [ ] 修改 import 段加:

```python
from db import (
    ...
    get_chip_daily_range,
)
from fetchers.chip_stock import fetch_stock_chip, to_finmind_id as chip_to_finmind_id
```

(把 `to_finmind_id` 別名以避免跟 broker 那個衝突;broker.py 也 export 同名,但兩個都做相同事所以實作會一樣)

- [ ] 在 `stock_brokers` 之後加新 endpoint:

```python
@app.get("/api/stocks/{ticker}/chip")
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
```

### Step 3.9: 跑全部測試

- [ ] 執行:

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v
```

Expected: 全部 pass(包含 endpoint 測試 + 既有 broker、alerts、api、db、fetchers 測試)。

### Step 3.10: Commit

- [ ] 執行:

```bash
git add stock/dashboard/backend/fetchers/chip_stock.py \
        stock/dashboard/backend/db.py \
        stock/dashboard/backend/app.py \
        stock/dashboard/tests/test_chip.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add per-stock chip backend (T3)

新增 fetchers/chip_stock.py(個股三大法人 + 融資融券)、stock_chip_daily
DB table、相關 db helpers,以及 GET /api/stocks/{ticker}/chip endpoint。
採 lazy fetch + cache,複用既有 broker.py 模式:首次拉 60 個交易日,後續
只補 delta。API 層回 foreign_net / trust_net / dealer_net(由 buy-sell
即時計算)、margin_balance、short_balance。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 個股籌碼 UI

**目標**:`stock.html` 加籌碼面區塊,呼叫 `/api/stocks/{ticker}/chip` 並顯示三大法人 + 融資融券表。

**Files:**
- Modify: `stock/dashboard/frontend/stock.html`

### Step 4.1: 加 CSS

**File:** `stock/dashboard/frontend/stock.html`

- [ ] 在 `.broker-table` 系列 CSS(L35 附近)之後加類似的 chip 表格樣式:

```css
.chip-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.chip-table th, .chip-table td { padding: 8px 6px; text-align: right; border-bottom: 1px solid #2d3348; }
.chip-table th { color: #94a3b8; font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
.chip-table td.chip-date, .chip-table th.chip-date { text-align: left; color: #e2e8f0; }
.chip-table tbody tr:last-child td { border-bottom: none; }
.chip-empty { color: #94a3b8; font-size: 13px; padding: 8px 0; }
.chip-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 720px) { .chip-grid { grid-template-columns: 1fr; } }
.chip-pos { color: #4ade80; }
.chip-neg { color: #f87171; }
```

### Step 4.2: 加 HTML 區塊

- [ ] 在現有(已停用)`<div id="broker-card">` 之後緊接著加籌碼卡:

```html
<div class="card" id="chip-card" style="display:none">
  <div class="card-header">
    <span class="card-label">籌碼面</span>
    <span class="card-hint" id="chip-hint">近 20 個交易日</span>
  </div>
  <div class="chip-grid">
    <div>
      <div class="card-sub" style="margin-bottom:6px;">三大法人(張)</div>
      <div id="chip-inst-body"></div>
    </div>
    <div>
      <div class="card-sub" style="margin-bottom:6px;">融資融券(張)</div>
      <div id="chip-margin-body"></div>
    </div>
  </div>
</div>
```

### Step 4.3: 加 JS 載入函式

- [ ] 在 `loadBrokers()` 函式定義位置(stock.html L337 附近)後加:

```javascript
async function loadChip() {
  const card = document.getElementById('chip-card');
  if (!card) return;
  // 限 .TW / .TWO ticker
  if (!/\.TW(O)?$/i.test(TICKER)) {
    card.style.display = 'none';
    return;
  }
  card.style.display = '';
  const instBody = document.getElementById('chip-inst-body');
  const marginBody = document.getElementById('chip-margin-body');
  instBody.innerHTML = '<div class="chip-empty">載入中…</div>';
  marginBody.innerHTML = '<div class="chip-empty">載入中…</div>';

  try {
    const r = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(TICKER)}/chip?days=20`);
    if (!r.ok) {
      instBody.innerHTML = `<div class="chip-empty">無法載入(${r.status})</div>`;
      marginBody.innerHTML = '';
      return;
    }
    const data = await r.json();
    if (!data.rows || !data.rows.length) {
      instBody.innerHTML = '<div class="chip-empty">尚無資料(資料來源:FinMind,盤後更新)。</div>';
      marginBody.innerHTML = '';
      return;
    }
    const fmtNet = v => {
      if (v === null || v === undefined) return '—';
      const cls = v > 0 ? 'chip-pos' : (v < 0 ? 'chip-neg' : '');
      const s = (v >= 0 ? '+' : '') + Math.round(v).toLocaleString();
      return `<span class="${cls}">${s}</span>`;
    };
    const fmtBal = v => v === null || v === undefined ? '—' : Math.round(v).toLocaleString();

    // 倒序顯示(最近的在最上面)
    const rev = [...data.rows].reverse();
    instBody.innerHTML = `
      <table class="chip-table">
        <thead><tr><th class="chip-date">日期</th><th>外資</th><th>投信</th><th>自營</th></tr></thead>
        <tbody>
          ${rev.map(r => `
            <tr>
              <td class="chip-date">${r.date.slice(5)}</td>
              <td>${fmtNet(r.foreign_net)}</td>
              <td>${fmtNet(r.trust_net)}</td>
              <td>${fmtNet(r.dealer_net)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>`;
    marginBody.innerHTML = `
      <table class="chip-table">
        <thead><tr><th class="chip-date">日期</th><th>融資餘額</th><th>融券餘額</th></tr></thead>
        <tbody>
          ${rev.map(r => `
            <tr>
              <td class="chip-date">${r.date.slice(5)}</td>
              <td>${fmtBal(r.margin_balance)}</td>
              <td>${fmtBal(r.short_balance)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>`;
  } catch (e) {
    instBody.innerHTML = `<div class="chip-empty">載入失敗:${e.message}</div>`;
    marginBody.innerHTML = '';
  }
}
```

- [ ] 在 `loadDetail()` 函式末尾(已知位置 L408-417,Task 1 之前的版本曾有 `loadBrokers()` 呼叫)加上 `loadChip()` 呼叫,放在 `makeMacdChart` 之後:

```javascript
    makeMacdChart(data.dates, data.indicators);
    loadChip();
  } catch (e) {
```

### Step 4.4: 手動驗證 UI

- [ ] 啟動本機服務:

```bash
# Terminal A
cd stock/dashboard/backend && python -m uvicorn app:app --reload --port 8000
# Terminal B(servn 前端)
cd stock/dashboard/frontend && python -m http.server 8080
```

- [ ] 瀏覽器開 `http://localhost:8080/stock.html?ticker=2330.TW`
- [ ] 確認:
  - 「籌碼面」卡片出現
  - 兩張表都有資料(首次會等 5-10 秒 lazy fetch)
  - 數字有正負色(綠/紅)
  - 切換不同股票(`?ticker=2454.TW`)資料能更新
  - 美股 ticker(`?ticker=AAPL`)時卡片自動隱藏

### Step 4.5: Commit

- [ ] 執行:

```bash
git add stock/dashboard/frontend/stock.html
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add per-stock chip section to stock detail (T4)

stock.html 加籌碼面區塊,顯示近 20 個交易日的三大法人淨買賣(張)與融資
融券餘額(張),雙欄並排。淨值帶正負色。資料 lazy fetch 自 /api/stocks/
{ticker}/chip,非台股 ticker 自動隱藏卡片。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Deploy + Backfill 驗證

**目標**:把 T1-T4 推上 master 觸發部署,VPS 跑一次 backfill 拉 1 年整體歷史資料,驗證生產環境 endpoints 正常。

### Step 5.1: 確認本機所有測試通過

- [ ] 執行:

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v
```

Expected: 全部 pass。如有 fail,回到 T1-T4 對應 task 修復。

### Step 5.2: Push 到 master

- [ ] 執行:

```bash
git push origin master
```

兩個 workflow 會被觸發:
- Deploy Stock Dashboard Backend(rsync VPS + 重啟 systemd)
- Deploy Stock Dashboard to GitHub Pages(前端)

### Step 5.3: 等部署完成

- [ ] 執行:

```bash
gh run watch $(gh run list --workflow=deploy-stock-dashboard-backend.yml --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
gh run watch $(gh run list --workflow=deploy-stock-dashboard.yml         --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
```

Expected: 兩個都 success。

### Step 5.4: VPS 跑 backfill 拉整體歷史 1 年

- [ ] 執行:

```bash
ssh root@178.104.240.236 "cd /opt/stock-dashboard/backend && .venv/bin/python backfill.py chip_total 365"
```

Expected: log 印出 `[chip_total] margin <date>: ...` 跟 `[chip_total] inst <date>: ...`,沒 fetch error。整個過程約 < 30 秒(只 2 個 FinMind requests)。

### Step 5.5: 驗證生產 API

- [ ] 執行:

```bash
echo '--- /api/dashboard 含新 keys ---'
curl -s 'https://api.paul-learning.dev/api/dashboard' | jq '. | {margin_balance, short_balance, short_margin_ratio, total_foreign_net, total_trust_net, total_dealer_net} | with_entries(.value |= .value)'

echo '--- /api/history/margin_balance 1Y ---'
curl -s 'https://api.paul-learning.dev/api/history/margin_balance?time_range=1Y' | jq 'length'

echo '--- /api/stocks/2330.TW/chip days=20 ---'
curl -s 'https://api.paul-learning.dev/api/stocks/2330.TW/chip?days=20' | jq '{ok, as_of, count: (.rows | length), sample: .rows[-1]}'
```

Expected:
- 6 個新 indicator key 都回非 null 數值
- history endpoint 回非空 array(backfill 1 年資料應有 ~250 筆)
- chip endpoint `ok: true`、`count` 在 15-20 之間(20 個交易日減去最近假日)

### Step 5.6: 驗證 UI

- [ ] 瀏覽器開 `https://paul-learning.dev`
- [ ] 確認:
  - 總覽頁有 6 張新卡片(融資餘額、融券餘額、券資比、外資/投信/自營淨買超)
  - 卡片都有數值,點 ↻ 更新有反應
  - 點任一卡片可進歷史圖
- [ ] 開 `https://paul-learning.dev/stock.html?ticker=2330.TW`
- [ ] 確認「籌碼面」區塊出現,有資料

### Step 5.7: 留意「VPS .env 沒被 deploy 沖掉」

- [ ] 執行:

```bash
ssh root@178.104.240.236 "awk -F= '{print \$1}' /opt/stock-dashboard/backend/.env"
```

Expected: 應有 `DISCORD_STOCK_WEBHOOK_URL` 跟 `FINMIND_TOKEN`。在 T5 再次部署後(由 GitHub Action 重寫 .env),`FINMIND_TOKEN` 應該還在(因為已經在 GitHub Secrets 中,workflow 會寫入)。

### Step 5.8(optional): 移除 cloudscraper 依賴

只在確認 `ndc.py` 與 `backfill.py` 都不再需要 cloudscraper 時做,否則跳過此 step。

- [ ] 執行:

```bash
grep -rn cloudscraper stock/dashboard/backend/
```

如果還有非 `margin.py` 的引用(預期 `ndc.py` 跟 `backfill.py` 內 `backfill_ndc` 仍會用),保留 `cloudscraper`。否則:

- [ ] 修改 `stock/dashboard/backend/requirements.txt`,移除 `cloudscraper>=1.2.71`。
- [ ] commit + push。

### Step 5.9: 完成 commit(只在做了 5.8 才需要)

- [ ] 執行:

```bash
git add stock/dashboard/backend/requirements.txt
git commit -m "chore(stock-dashboard): drop cloudscraper after margin.py removal"
git push
```

---

## 完成後狀態

- 6 個新 indicator key 在 `indicator_snapshots`
- 1 個新表 `stock_chip_daily`
- 既有 `margin` 歷史已 rename 為 `margin_balance`,沒丟資料
- 總覽 dashboard 多 6 張籌碼卡
- 個股頁多「籌碼面」區塊
- `cloudscraper` / TWSE IP 封鎖風險解除(若 5.8 完成)
- 警示規則層尚未實裝(`check_alerts` 對新 key 已在呼叫,但 alert UI 不認識新 key,`/api/alerts` POST 過去會通過,但無對應 label,UI 顯示是 raw key) — 第二階段處理

## 風險與緩解(備忘)

- **FinMind 改 dataset 為 Sponsor**:仿券商分點停用模式 — fetcher 短路、UI 隱藏卡片、保留程式碼
- **FinMind quota 600/hr**:T1+T2 cron 每天 2 requests;個股 lazy 每用戶看一檔 2 requests,合理流量遠低於 600/hr
- **Schema 變動**:fetcher 中 `parse_*` 都是 defensive(missing key 跳過),失敗 log 不擋住其他指標
