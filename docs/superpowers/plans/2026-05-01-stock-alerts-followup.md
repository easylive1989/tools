# Stock Dashboard 警示系統收尾 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 修補 Phase 4 final review 留下的兩個 backlog issues:`tw_volume`/`us_volume` alert trigger path、`remove_watched_ticker` 連動停用 stock_indicator alerts。

**Architecture:** 兩個獨立小修補。volume fetcher 加 check_alerts 一行;db.remove_watched_ticker 加 SQL UPDATE。

**Tech Stack:** Python 3 / SQLite / pytest

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `stock/dashboard/backend/fetchers/volume.py` | Modify | `fetch_tw_volume` / `fetch_us_volume` 寫入後加 `check_alerts` 呼叫 |
| `stock/dashboard/backend/db.py` | Modify | `remove_watched_ticker` 連動 disable stock_indicator alerts |
| `stock/dashboard/tests/test_fetchers.py` | Modify | volume 測試加 check_alerts assertion |
| `stock/dashboard/tests/test_db.py` | Modify | 加 watched ticker 移除連動 test |

---

## Task 1: volume.py 加 check_alerts trigger

**Files:**
- Modify: `stock/dashboard/backend/fetchers/volume.py`
- Modify: `stock/dashboard/tests/test_fetchers.py`

### Step 1.1: 看現有 volume.py 結構

```bash
cat stock/dashboard/backend/fetchers/volume.py
```

確認:
- 既有 import 是否含 `from alerts import check_alerts`(若沒則需加)
- `fetch_tw_volume` / `fetch_us_volume` 的 `save_indicator(...)` 呼叫位置

### Step 1.2: 寫 / 補 失敗測試

**File:** `stock/dashboard/tests/test_fetchers.py`(append 到既有 volume tests 之後,或修改既有 test_fetch_tw_volume_*)

加新 test 確認 check_alerts 在 save 後被呼叫:

```python
def test_fetch_tw_volume_calls_check_alerts():
    """確認 fetch_tw_volume 寫入後呼叫 check_alerts(Phase 4 follow-up)。"""
    db.init_db()
    sample = {"date": "20260501", "TradeValue": "500000000000"}  # 5000 億
    with patch("fetchers.volume.requests.get") as mock_get, \
         patch("fetchers.volume.check_alerts") as mock_check:
        mock_get.return_value.json.return_value = [sample]
        mock_get.return_value.raise_for_status = lambda: None
        from fetchers.volume import fetch_tw_volume
        fetch_tw_volume()
    mock_check.assert_called_once()
    args = mock_check.call_args[0]
    assert args[0] == "indicator"
    assert args[1] == "tw_volume"


def test_fetch_us_volume_calls_check_alerts():
    """確認 fetch_us_volume 寫入後呼叫 check_alerts(Phase 4 follow-up)。"""
    db.init_db()
    import pandas as pd
    fake_hist = pd.DataFrame(
        {"Volume": [1_000_000_000]},
        index=pd.to_datetime(["2026-05-01"]),
    )
    with patch("yfinance.Ticker") as mock_ticker, \
         patch("fetchers.volume.check_alerts") as mock_check:
        mock_ticker.return_value.history.return_value = fake_hist
        from fetchers.volume import fetch_us_volume
        fetch_us_volume()
    mock_check.assert_called_once()
    args = mock_check.call_args[0]
    assert args[0] == "indicator"
    assert args[1] == "us_volume"
```

> 注意:測試 patch path 用 `fetchers.volume.check_alerts`(by-reference semantics — 若 volume.py 用 `from alerts import check_alerts`,name 在 volume module namespace);若 `import alerts` 然後 `alerts.check_alerts(...)`,patch path 改 `alerts.check_alerts`。先看現有結構決定。

`patch` 跟 `db` 的 imports 在檔案上方應已有(既有 test_fetchers.py 慣例),若沒則加:

```python
from unittest.mock import patch
import db
```

### Step 1.3: Run, verify fail

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_fetchers.py -v -k "calls_check_alerts"
```

Expected: 2 tests FAILED(check_alerts 還沒接)。

### Step 1.4: 改 volume.py 加 trigger

**File:** `stock/dashboard/backend/fetchers/volume.py`

(a) 在 imports 區段確認有 `from alerts import check_alerts`;若沒,加:

```python
from alerts import check_alerts
```

(b) 在 `fetch_tw_volume()` 中,找到 `save_indicator("tw_volume", ...)` 行,IMMEDIATELY AFTER 加:

```python
    check_alerts("indicator", "tw_volume", value_yi)
```

(注意:`value_yi` 是既有變數名,從 grep volume.py 的 `save_indicator("tw_volume", value_yi, ...)` 查得;若實際變數名不同,用實際值代入。)

(c) 在 `fetch_us_volume()` 中,同樣 save_indicator 後加:

```python
    check_alerts("indicator", "us_volume", value_yi)
```

### Step 1.5: Run, verify pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_fetchers.py -v -k "tw_volume or us_volume"
```

Expected: 既有 + 2 new = pass。

### Step 1.6: Run full regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 76 passed (74 + 2),5 pre-existing failures unchanged.

### Step 1.7: Commit

```bash
git add stock/dashboard/backend/fetchers/volume.py \
        stock/dashboard/tests/test_fetchers.py
git commit -m "$(cat <<'EOF'
fix(stock-dashboard): trigger check_alerts for tw_volume / us_volume (T1)

Phase 4 final review 指出 INDICATOR_NAMES 含 tw_volume/us_volume,API 可
建 alert 但 volume fetcher 沒呼叫 check_alerts,alert 永不觸發 silent
failure。fetch_tw_volume / fetch_us_volume 在 save_indicator 後加上
check_alerts("indicator", key, value) 補齊 trigger path。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: remove_watched_ticker 連動 disable alerts

**Files:**
- Modify: `stock/dashboard/backend/db.py`
- Modify: `stock/dashboard/tests/test_db.py`

### Step 2.1: 寫失敗測試

**File:** `stock/dashboard/tests/test_db.py`(append at end)

```python
def test_remove_watched_ticker_disables_stock_indicator_alerts():
    """移除 watchlist ticker 應同時停用該 ticker 的 stock_indicator alerts(Phase 4 follow-up)。"""
    db.init_db()
    db.add_watched_ticker("2330.TW")
    # 為 2330.TW 建 stock_indicator alert + 一個無關的 indicator alert + 一個其他 ticker 的 stock_indicator alert
    a1 = db.add_alert("stock_indicator", "2330.TW", "above", 30,
                      indicator_key="per", window_n=None)
    a2 = db.add_alert("indicator", "margin_balance", "above", 5000,
                      indicator_key=None, window_n=None)
    a3 = db.add_alert("stock_indicator", "2454.TW", "above", 50,
                      indicator_key="per", window_n=None)

    db.remove_watched_ticker("2330.TW")

    alerts = {a["id"]: a for a in db.list_alerts()}
    # 2330.TW 的 stock_indicator alert 應 disable
    assert alerts[a1]["enabled"] == 0
    # 整體 indicator alert 不受影響
    assert alerts[a2]["enabled"] == 1
    # 其他 ticker 的 stock_indicator alert 不受影響
    assert alerts[a3]["enabled"] == 1


def test_remove_watched_ticker_does_not_affect_stock_price_alerts():
    """移除 ticker 不應該動到 'stock' (價格)類型 alerts — 跟 stock_indicator 分開處理。"""
    db.init_db()
    db.add_watched_ticker("2330.TW")
    a1 = db.add_alert("stock", "2330.TW", "above", 1000)

    db.remove_watched_ticker("2330.TW")

    alerts = {a["id"]: a for a in db.list_alerts()}
    # stock 類型不該被連動(僅 stock_indicator 連動)
    assert alerts[a1]["enabled"] == 1
```

### Step 2.2: Run, verify fail

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_db.py -v -k "remove_watched_ticker"
```

Expected: `test_remove_watched_ticker_disables_stock_indicator_alerts` FAIL(目前 remove 沒連動)。`test_remove_watched_ticker_does_not_affect_stock_price_alerts` 應 pass(目前 remove 完全不動 alert)。

### Step 2.3: 改 db.py — remove_watched_ticker 加連動

**File:** `stock/dashboard/backend/db.py`

Find existing `remove_watched_ticker`:

```python
def remove_watched_ticker(ticker: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM watched_stocks WHERE ticker=?", (ticker,))
```

Replace with:

```python
def remove_watched_ticker(ticker: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM watched_stocks WHERE ticker=?", (ticker,))
        # Phase 4 follow-up:同時停用該 ticker 的 stock_indicator alerts(避免 stale)
        conn.execute(
            "UPDATE price_alerts SET enabled=0 "
            "WHERE target_type='stock_indicator' AND target=?",
            (ticker,)
        )
```

### Step 2.4: Run, verify both tests pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_db.py -v -k "remove_watched_ticker"
```

Expected: 2 passed.

### Step 2.5: Run full regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 78 passed (76 + 2),5 pre-existing failures unchanged.

### Step 2.6: Commit

```bash
git add stock/dashboard/backend/db.py stock/dashboard/tests/test_db.py
git commit -m "$(cat <<'EOF'
fix(stock-dashboard): disable stock_indicator alerts on watched ticker removal (T2)

remove_watched_ticker 同時對 price_alerts 中對應 ticker 的 stock_indicator
alerts 設 enabled=0,避免 ticker 移出 watchlist 後 alert 變 stale(scheduler
不再拉新資料)。整體 indicator alert 跟 stock 價格 alert 不受影響。alert
不刪除,保留 audit trail,user 可手動重新啟用。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Deploy + 驗證

### Step 3.1: 確認本機所有測試通過

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 78 passed, 5 pre-existing failures unchanged.

### Step 3.2: Push

```bash
git push origin master
```

### Step 3.3: Watch deploys

```bash
gh run watch $(gh run list --workflow=deploy-stock-dashboard-backend.yml --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
```

(只 backend 會觸發 deploy 因為前端沒改)

Expected: success in ~20-30s.

### Step 3.4: 驗證 tw_volume alert 觸發

```bash
echo '--- POST tw_volume alert (門檻極低必觸發) ---'
curl -s -X POST 'https://api.paul-learning.dev/api/alerts' \
  -H 'Content-Type: application/json' \
  -d '{"target_type":"indicator","target":"tw_volume","condition":"above","threshold":1}' | jq

# 手動觸發 fetch_tw_volume
ssh root@${VPS_HOST} "cd /opt/stock-dashboard/backend && set -a && . .env && set +a && .venv/bin/python -c '
import sys; sys.path.insert(0, \".\")
from db import init_db; init_db()
from fetchers.volume import fetch_tw_volume
fetch_tw_volume()
'"
```

Expected: log 印出 `[alerts] notified: 台股成交金額 ...`(或類似 — INDICATOR_LABELS 中 tw_volume 沒有 中文 label,會 fallback 到 'tw_volume')。Discord 收到通知。

驗證 alert 被 disable:

```bash
curl -s 'https://api.paul-learning.dev/api/alerts' | jq '[.[] | select(.target=="tw_volume")] | .[] | {id, target, enabled, triggered_at, triggered_value}'
```

Expected: `enabled: 0`、`triggered_at` 非 null。

### Step 3.5: 驗證 watched ticker 移除連動

```bash
# 假設 watchlist 已有 2330.TW;先確認
curl -s 'https://api.paul-learning.dev/api/stocks' | jq '.[] | select(.ticker=="2330.TW") | .ticker'

# 為 2330.TW 加 stock_indicator alert(實際門檻不重要,測 disable 連動)
curl -s -X POST 'https://api.paul-learning.dev/api/alerts' \
  -H 'Content-Type: application/json' \
  -d '{"target_type":"stock_indicator","target":"2330.TW","condition":"above","threshold":99999,"indicator_key":"per"}' | jq

# 從 watchlist 移除 2330.TW
curl -s -X DELETE 'https://api.paul-learning.dev/api/stocks/2330.TW' | jq

# 確認剛才建的 alert enabled=0
curl -s 'https://api.paul-learning.dev/api/alerts' | jq '[.[] | select(.target=="2330.TW" and .target_type=="stock_indicator")] | .[] | {id, target, indicator_key, enabled}'
```

Expected: alert.enabled = 0(連動成功)。其他 alert(整體 indicator / 別檔 ticker)不受影響。

### Step 3.6: 把 2330.TW 加回 watchlist(復原 production state)

```bash
curl -s -X POST 'https://api.paul-learning.dev/api/stocks' \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"2330.TW"}' | jq
```

(若 user 原本 watchlist 沒有 2330.TW,跳過此步並 user 自行調整。)

### Step 3.7: 報告

最終報告:
- 本機測試結果(76+2 = 78 passed)
- Push commit SHA
- Workflow success
- POST tw_volume alert + 手動觸發後的驗證
- Watched ticker 移除連動測試
- VPS 狀態
- 提示使用者:測試 alert 已 disable,手動 DELETE 或保留作 audit
