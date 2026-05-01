# Stock Dashboard 警示規則 Phase 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 擴展既有 alert 系統,加上「個股 daily 指標警示」(8 個 key)+「連 N 日警示」(streak above/below);加 scheduler 主動拉 watchlist 個股 daily 資料以確保警示能可靠觸發。

**Architecture:** `price_alerts` 表加 2 欄(`indicator_key` + `window_n`),沿用既有 `condition` 字串接受 4 種值(`above` / `below` / `streak_above` / `streak_below`),`target_type` 加 `stock_indicator`。`alerts.py` engine routing 按 (target_type, condition) 分支,純函式 `_check_streak` 跟 `_get_stock_indicator_history` 隔離可測試邏輯。Fetcher 觸發整合在 `chip_stock.py` / `fundamentals_stock.py` 寫入後逐 indicator 呼叫,只在「max date == today」時觸發避免 backfill spam。Scheduler 加 18:30 TST cron 對 watchlist 主動拉。

**Tech Stack:** Python 3 / SQLite / FastAPI / APScheduler / pytest / 純 HTML+JS / Discord webhook

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `stock/dashboard/backend/db.py` | Modify | `init_db()` 加 idempotent migration ALTER price_alerts;`add_alert` 簽名擴展(indicator_key、window_n);`get_active_alerts` SELECT 多回 2 欄 |
| `stock/dashboard/backend/alerts.py` | Modify | 加 `_check_streak`、`_get_stock_indicator_history`;`check_alerts` 加 routing(streak / stock_indicator);`_build_payload` 訊息 format 擴展 |
| `stock/dashboard/backend/fetchers/chip_stock.py` | Modify | `fetch_stock_chip` 寫入後對 5 個籌碼 indicator_key 各呼叫 `check_alerts`(只在 max date == today) |
| `stock/dashboard/backend/fetchers/fundamentals_stock.py` | Modify | `fetch_stock_per` 寫入後對 3 個估值 indicator_key 各呼叫(同模式);加 `fetch_watchlist_stock_daily` 函式 |
| `stock/dashboard/backend/scheduler.py` | Modify | 加 `watchlist_chip_per` daily cron job(18:30 TST) |
| `stock/dashboard/backend/app.py` | Modify | `AlertRequest` 加 indicator_key / window_n;`VALID_*` 擴展;`POST /api/alerts` 驗證 stock_indicator + streak_* |
| `stock/dashboard/frontend/index.html` | Modify | alert form HTML(target-type 加 option、condition 加 2 option、加 indicator_key 與 window_n 欄,動態顯示);JS `STOCK_INDICATOR_LABELS`、`alertTargetLabel` / 新 `alertConditionLabel` / `refreshTargetOptions` / `addAlert` 全部擴展 |
| `stock/dashboard/tests/test_alerts.py` | Modify | 加 streak 純函式測試 + stock_indicator routing 測試 |
| `stock/dashboard/tests/test_api.py` | Modify | 加 stock_indicator + streak_* alert POST 驗證測試 |

---

## Task 1: DB schema migration + alerts engine 純函式

**目標:** `price_alerts` 加 `indicator_key` / `window_n` 欄(idempotent migration),`db.add_alert` / `get_active_alerts` 對應更新,`alerts.py` 加兩個純函式 helper(streak 計算 + 個股 daily 歷史查詢)。

**Files:**
- Modify: `stock/dashboard/backend/db.py`、`stock/dashboard/backend/alerts.py`
- Modify: `stock/dashboard/tests/test_alerts.py`

### Step 1.1: 寫 streak 純函式失敗測試

**File:** `stock/dashboard/tests/test_alerts.py`(append at end)

```python
from alerts import _check_streak


def test_check_streak_above_all_pass():
    # 5 個值全部 >= threshold 200 → True
    assert _check_streak([220, 230, 210, 250, 200], 'streak_above', 200) is True


def test_check_streak_above_one_fails():
    # 一個值 < 200 → False
    assert _check_streak([220, 230, 199, 250, 200], 'streak_above', 200) is False


def test_check_streak_below_all_pass():
    assert _check_streak([90, 80, 70, 95, 100], 'streak_below', 100) is True


def test_check_streak_below_one_fails():
    assert _check_streak([90, 80, 70, 95, 101], 'streak_below', 100) is False


def test_check_streak_insufficient_values_returns_false():
    # 給的值少於預期(空、None mixed) → False
    assert _check_streak([], 'streak_above', 100) is False
    assert _check_streak([220, None, 230], 'streak_above', 200) is False


def test_check_streak_unknown_condition_returns_false():
    assert _check_streak([220, 230], 'above', 200) is False
```

### Step 1.2: Run test, verify fails

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py -v -k streak
```

Expected: 6 tests FAILED with `ImportError: cannot import name '_check_streak' from 'alerts'`

### Step 1.3: 實作 `_check_streak` in alerts.py

**File:** `stock/dashboard/backend/alerts.py`

In the existing module, after the `INDICATOR_UNITS` dict and before `_format_value`, add:

```python
def _check_streak(values: list, condition: str, threshold: float) -> bool:
    """檢查 values 是否全部達門檻(streak_above 全 >= threshold,streak_below 全 <= threshold)。

    values 中含 None 視為「資料不足」,直接 False(不允許部分)。
    給空 list 也 False。
    condition 不是 streak_above / streak_below 也 False。
    """
    if condition not in ('streak_above', 'streak_below'):
        return False
    if not values or any(v is None for v in values):
        return False
    if condition == 'streak_above':
        return all(v >= threshold for v in values)
    return all(v <= threshold for v in values)
```

### Step 1.4: Run test, verify pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py -v -k streak
```

Expected: 6 passed.

### Step 1.5: db.py — idempotent migration ALTER 加 2 欄

**File:** `stock/dashboard/backend/db.py`

In `init_db()`, AFTER the `executescript("""...""")` call (already inside `with get_connection() as conn:`),AND AFTER the existing `UPDATE indicator_snapshots SET indicator='margin_balance' ...` migration line,add:

```python
        # --- Phase 4 alert schema migration (idempotent) ---
        existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(price_alerts)").fetchall()}
        if "indicator_key" not in existing_cols:
            conn.execute("ALTER TABLE price_alerts ADD COLUMN indicator_key TEXT")
        if "window_n" not in existing_cols:
            conn.execute("ALTER TABLE price_alerts ADD COLUMN window_n INTEGER")
```

### Step 1.6: db.py — `add_alert` 簽名擴展(向後相容)

**File:** `stock/dashboard/backend/db.py`

Locate `add_alert` (around L150). Replace its body with:

```python
def add_alert(target_type: str, target: str, condition: str, threshold: float,
              *, indicator_key: str | None = None, window_n: int | None = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO price_alerts "
            "(target_type, target, condition, threshold, indicator_key, window_n, "
            " enabled, created_at) "
            "VALUES (?,?,?,?,?,?,1,?)",
            (target_type, target, condition, threshold, indicator_key, window_n,
             datetime.now(timezone.utc).replace(tzinfo=None).isoformat()),
        )
        return cur.lastrowid
```

(既有 callers 沒帶 kwarg,自然 indicator_key=window_n=NULL — 向後相容。)

### Step 1.7: db.py — `get_active_alerts` SELECT * 自動帶新欄

`get_active_alerts` 已經用 `SELECT *`,新欄會自動帶過,不需改。

(快速確認:既有實作 `conn.execute("SELECT * FROM price_alerts WHERE target_type=? AND target=? AND enabled=1", ...)` 加新欄後 dict 會多 2 個 key,沒衝突。)

### Step 1.8: 寫 `_get_stock_indicator_history` 失敗測試

**File:** `stock/dashboard/tests/test_alerts.py`(append)

```python
import db
from alerts import _get_stock_indicator_history


def test_get_stock_indicator_history_per():
    db.init_db()
    db.save_per_daily_rows([
        {"ticker": "2330.TW", "date": "2026-04-28", "per": 30.0, "pbr": 9.0,  "dividend_yield": 1.5},
        {"ticker": "2330.TW", "date": "2026-04-29", "per": 31.0, "pbr": 9.5,  "dividend_yield": 1.4},
        {"ticker": "2330.TW", "date": "2026-04-30", "per": 32.0, "pbr": 10.0, "dividend_yield": 1.3},
    ])
    out = _get_stock_indicator_history("2330.TW", "per", n=3)
    assert out == [30.0, 31.0, 32.0]   # 舊→新

    out2 = _get_stock_indicator_history("2330.TW", "pbr", n=2)
    assert out2 == [9.5, 10.0]         # 取最近 2 個


def test_get_stock_indicator_history_chip_foreign_net():
    db.init_db()
    db.save_chip_daily_rows([
        {"ticker": "2330.TW", "date": "2026-04-29",
         "foreign_buy": 5_000_000, "foreign_sell": 3_000_000,
         "trust_buy": None, "trust_sell": None,
         "dealer_buy": None, "dealer_sell": None,
         "margin_balance": None, "short_balance": None},
        {"ticker": "2330.TW", "date": "2026-04-30",
         "foreign_buy": 6_000_000, "foreign_sell": 1_000_000,
         "trust_buy": None, "trust_sell": None,
         "dealer_buy": None, "dealer_sell": None,
         "margin_balance": None, "short_balance": None},
    ])
    # foreign_net = buy - sell;最近 2 日:2_000_000, 5_000_000
    assert _get_stock_indicator_history("2330.TW", "foreign_net", n=2) == [2_000_000, 5_000_000]


def test_get_stock_indicator_history_unknown_key_returns_empty():
    db.init_db()
    assert _get_stock_indicator_history("2330.TW", "unknown_key", n=5) == []
```

### Step 1.9: Run, verify fails

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py::test_get_stock_indicator_history_per -v
```

Expected: FAILED with `ImportError: cannot import name '_get_stock_indicator_history' from 'alerts'`

### Step 1.10: 實作 `_get_stock_indicator_history`

**File:** `stock/dashboard/backend/alerts.py`

After `_check_streak`, add:

```python
# --- 個股 daily 指標查詢路由 ---

# Phase 4 個股 daily 指標 → (table_helper, value-derive function)
# 取「最近 n 個有資料」的歷史值,順序 舊→新。

_PER_KEYS = {"per", "pbr", "dividend_yield"}
_CHIP_NET_KEYS = {"foreign_net", "trust_net", "dealer_net"}
_CHIP_BAL_KEYS = {"margin_balance", "short_balance"}

STOCK_INDICATOR_KEYS = _PER_KEYS | _CHIP_NET_KEYS | _CHIP_BAL_KEYS


def _get_stock_indicator_history(ticker: str, indicator_key: str, n: int) -> list[float]:
    """從 stock_per_daily / stock_chip_daily 取最近 n 個非 None 值,舊→新排序。"""
    if indicator_key not in STOCK_INDICATOR_KEYS:
        return []

    # since_date 撈足夠視窗:n 個交易日 + 假日 buffer。簡單抓 n*3 日曆天。
    from datetime import datetime, timedelta, timezone
    from db import get_per_daily_range, get_chip_daily_range
    since_date = (datetime.now(timezone.utc).date() - timedelta(days=n * 3 + 30)).isoformat()

    if indicator_key in _PER_KEYS:
        rows = get_per_daily_range(ticker, since_date)
        values = [r[indicator_key] for r in rows]
    elif indicator_key in _CHIP_NET_KEYS:
        rows = get_chip_daily_range(ticker, since_date)
        # foreign_net = foreign_buy - foreign_sell (and same for trust / dealer)
        bs_prefix = indicator_key[:-4]   # 'foreign_net' → 'foreign'
        values = []
        for r in rows:
            buy, sell = r[f"{bs_prefix}_buy"], r[f"{bs_prefix}_sell"]
            if buy is None or sell is None:
                values.append(None)
            else:
                values.append(buy - sell)
    else:  # margin_balance / short_balance
        rows = get_chip_daily_range(ticker, since_date)
        values = [r[indicator_key] for r in rows]

    # 過濾 None,取最近 n 個
    clean = [v for v in values if v is not None]
    return clean[-n:]
```

### Step 1.11: Run, verify pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py -v
```

Expected: 既有 alert tests + 6 streak + 3 history = pass(總 alerts test 至少 +9)。 5 pre-existing failures 不變。

### Step 1.12: Commit

```bash
git add stock/dashboard/backend/db.py \
        stock/dashboard/backend/alerts.py \
        stock/dashboard/tests/test_alerts.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add alert schema migration and engine pure helpers (T1)

price_alerts 加 indicator_key / window_n 兩欄(idempotent migration via
PRAGMA table_info check + ALTER TABLE)。db.add_alert 簽名擴展為向後相容
的 kwargs。alerts.py 加 _check_streak(純函式判斷連 N 個值是否全部達門
檻)與 _get_stock_indicator_history(從 stock_per_daily / stock_chip_daily
路由查詢個股 daily 指標歷史值,順序舊→新),T2 將在這之上做 routing。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: alerts.py routing 重構 + Discord 訊息 format

**目標:** `check_alerts` 接受 `indicator_key` kwarg,按 `(target_type, condition)` 分支處理 4 個 routing 路徑,Discord `_build_payload` 訊息根據 condition / target_type 不同 format。

**Files:**
- Modify: `stock/dashboard/backend/alerts.py`
- Modify: `stock/dashboard/tests/test_alerts.py`

### Step 2.1: 寫 stock_indicator routing 失敗測試

**File:** `stock/dashboard/tests/test_alerts.py`(append)

```python
from unittest.mock import patch
from alerts import check_alerts


def test_check_alerts_stock_indicator_above_triggers():
    db.init_db()
    db.save_per_daily_rows([
        {"ticker": "2330.TW", "date": "2026-04-30", "per": 35.0, "pbr": 10.0, "dividend_yield": 1.0},
    ])
    db.add_alert("stock_indicator", "2330.TW", "above", 30.0,
                 indicator_key="per", window_n=None)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("stock_indicator", "2330.TW", indicator_key="per")
    assert mock_send.called
    args = mock_send.call_args
    payload = args[0][1]
    assert "2330.TW" in payload["embeds"][0]["title"] or "2330.TW" in payload["embeds"][0]["description"]


def test_check_alerts_stock_indicator_below_does_not_trigger_when_above():
    db.init_db()
    db.save_per_daily_rows([
        {"ticker": "2330.TW", "date": "2026-04-30", "per": 35.0, "pbr": 10.0, "dividend_yield": 1.0},
    ])
    db.add_alert("stock_indicator", "2330.TW", "below", 30.0,
                 indicator_key="per", window_n=None)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("stock_indicator", "2330.TW", indicator_key="per")
    assert not mock_send.called


def test_check_alerts_stock_indicator_streak_above_triggers():
    db.init_db()
    db.save_chip_daily_rows([
        {"ticker": "2330.TW", "date": f"2026-04-{day:02d}",
         "foreign_buy": 6_000_000, "foreign_sell": 1_000_000,  # net 5M each day
         "trust_buy": None, "trust_sell": None,
         "dealer_buy": None, "dealer_sell": None,
         "margin_balance": None, "short_balance": None}
        for day in (24, 25, 28, 29, 30)
    ])
    db.add_alert("stock_indicator", "2330.TW", "streak_above", 0,
                 indicator_key="foreign_net", window_n=5)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("stock_indicator", "2330.TW", indicator_key="foreign_net")
    assert mock_send.called


def test_check_alerts_indicator_streak_above_triggers():
    db.init_db()
    # 整體 indicator 連 3 日 >= 5000
    for d, v in [("2026-04-28T00:00:00", 5100),
                 ("2026-04-29T00:00:00", 5200),
                 ("2026-04-30T00:00:00", 5300)]:
        db.save_indicator("margin_balance", v, timestamp=__import__("datetime").datetime.fromisoformat(d))
    db.add_alert("indicator", "margin_balance", "streak_above", 5000,
                 indicator_key=None, window_n=3)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("indicator", "margin_balance", value=5300)
    assert mock_send.called
```

### Step 2.2: Run, verify failures

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py -v -k "check_alerts_stock_indicator or check_alerts_indicator_streak"
```

Expected: 4 tests FAILED(check_alerts 還沒接 stock_indicator / streak_*)。

### Step 2.3: 重構 `check_alerts` for routing

**File:** `stock/dashboard/backend/alerts.py`

Replace the existing `check_alerts` function entirely with:

```python
# 個股 indicator 顯示用中文 label
STOCK_INDICATOR_LABELS = {
    "per":              "PER",
    "pbr":              "PBR",
    "dividend_yield":   "殖利率",
    "foreign_net":      "外資淨買",
    "trust_net":        "投信淨買",
    "dealer_net":       "自營淨買",
    "margin_balance":   "融資餘額",
    "short_balance":    "融券餘額",
}


def _latest_indicator_history(indicator: str, n: int) -> list[float]:
    """取整體 indicator 最近 n 個值(舊→新)。"""
    from datetime import datetime, timedelta, timezone
    from db import get_indicator_history
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(n * 3, 30))
    rows = get_indicator_history(indicator, since)
    values = [r["value"] for r in rows if r["value"] is not None]
    return values[-n:]


def check_alerts(target_type: str, target: str, value: float | None = None,
                 *, indicator_key: str | None = None, display_name: str | None = None) -> None:
    """評估 alerts 並 notify。

    Routing by (target_type, condition):
    - target_type='indicator', condition='above'/'below'
        → 用 value 跟 threshold 比(沿用既有)
    - target_type='indicator', condition='streak_above'/'streak_below'
        → 用 _latest_indicator_history(target, alert.window_n) 跟 threshold 比
    - target_type='stock_indicator', condition='above'/'below'
        → 用 _get_stock_indicator_history(target, indicator_key, 1) 取最新值跟 threshold 比
    - target_type='stock_indicator', condition='streak_above'/'streak_below'
        → 用 _get_stock_indicator_history(target, indicator_key, alert.window_n) 跟 threshold 比
    - target_type='stock', condition='above'/'below'
        → 用 value 跟 threshold 比(沿用既有)

    觸發後 mark_alert_triggered 並送 Discord(沿用既有 logic)。
    """
    from db import get_active_alerts, mark_alert_triggered

    # 個股指標警示用 indicator_key 過濾出相關 alerts
    all_active = get_active_alerts(target_type, target)
    if target_type == "stock_indicator":
        active_alerts = [a for a in all_active if a.get("indicator_key") == indicator_key]
    else:
        active_alerts = all_active

    name = display_name or _alert_display_name(target_type, target, indicator_key)
    webhook = os.environ.get("DISCORD_STOCK_WEBHOOK_URL")

    for alert in active_alerts:
        threshold = alert["threshold"]
        cond = alert["condition"]
        triggered_value = None

        if cond in ("above", "below"):
            cur_value = value
            if target_type == "stock_indicator":
                # 取個股指標最新值
                hist = _get_stock_indicator_history(target, indicator_key, 1)
                cur_value = hist[-1] if hist else None
            if cur_value is None:
                continue
            triggered = ((cond == "above" and cur_value >= threshold) or
                         (cond == "below" and cur_value <= threshold))
            triggered_value = cur_value if triggered else None
        elif cond in ("streak_above", "streak_below"):
            window_n = alert.get("window_n") or 5
            if target_type == "indicator":
                hist = _latest_indicator_history(target, window_n)
            elif target_type == "stock_indicator":
                hist = _get_stock_indicator_history(target, indicator_key, window_n)
            else:
                continue   # streak 不適用於 stock 價格(沒有 history 表)
            triggered = _check_streak(hist, cond, threshold)
            triggered_value = hist[-1] if (triggered and hist) else None
        else:
            continue

        if not triggered:
            continue

        mark_alert_triggered(alert["id"], triggered_value)
        if not webhook:
            print(f"[alerts] webhook not set, skipping notification for alert {alert['id']}")
            continue
        try:
            send_to_discord(webhook, _build_payload(alert, triggered_value, name))
            print(f"[alerts] notified: {name} {cond} {threshold} (value={triggered_value})")
        except Exception as e:
            print(f"[alerts] discord error for alert {alert['id']}: {e}")


def _alert_display_name(target_type: str, target: str, indicator_key: str | None) -> str:
    if target_type == "indicator":
        return INDICATOR_LABELS.get(target, target)
    if target_type == "stock_indicator":
        ik_label = STOCK_INDICATOR_LABELS.get(indicator_key, indicator_key or "")
        return f"{target} {ik_label}"
    # stock
    return target
```

### Step 2.4: 擴展 `_build_payload` 支援 streak / stock_indicator

**File:** `stock/dashboard/backend/alerts.py`

Replace the existing `_build_payload` function with:

```python
def _build_payload(alert: dict, value: float | None, display_name: str) -> dict:
    cond = alert["condition"]
    threshold = alert["threshold"]
    window_n = alert.get("window_n")
    target_type = alert["target_type"]

    # 顯示用 unit / value 格式化(個股 indicator 沒對應 INDICATOR_UNITS,只 raw 數值)
    def _fmt(v: float) -> str:
        if v is None:
            return "—"
        if target_type == "indicator":
            return _format_value(target_type, alert["target"], v)
        if target_type == "stock_indicator":
            ik = alert.get("indicator_key")
            # PER/PBR 4 位小數,其餘整數比較好讀
            if ik in ("per", "pbr"):
                return f"{v:.2f}"
            if ik == "dividend_yield":
                return f"{v:.2f}%"
            return f"{v:,.0f}"
        # stock
        return f"{v:,.4f}" if v < 100 else f"{v:,.2f}"

    value_str = _fmt(value) if value is not None else "—"
    threshold_str = _fmt(threshold)

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

    embed = {
        "title": f"🚨 警示:{display_name}",
        "description": (
            f"**{display_name}** 目前 **{value_str}**,已{crossed}門檻 **{threshold_str}**。\n"
            f"_警示已自動停用,請至 Dashboard 重新啟用。_"
        ),
        "color": color,
    }
    return {"embeds": [embed]}
```

### Step 2.5: Run, verify all alert tests pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_alerts.py -v
```

Expected: 既有 alert tests + 4 new routing tests + 9 from T1 all pass. 5 pre-existing failures unchanged.

### Step 2.6: Commit

```bash
git add stock/dashboard/backend/alerts.py \
        stock/dashboard/tests/test_alerts.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): alert engine routing for streak + stock_indicator (T2)

check_alerts 重構為按 (target_type, condition) 分支 routing。新支援
streak_above / streak_below(查歷史 n 個值,全部達門檻才觸發),以及
stock_indicator(查 stock_per_daily / stock_chip_daily,foreign/trust/
dealer 的 net = buy - sell)。Discord _build_payload 訊息根據 condition
產生對應措辭(突破 / 跌破 / 連 N 日突破 / 連 N 日跌破)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Fetcher 觸發整合

**目標:** `chip_stock.py` / `fundamentals_stock.py`(per)在 lazy fetch 寫入後,對該 ticker 的對應 indicator_key 各呼叫 `check_alerts`,**只在「max date == today」**時呼叫(避免歷史 backfill spam)。

**Files:**
- Modify: `stock/dashboard/backend/fetchers/chip_stock.py`
- Modify: `stock/dashboard/backend/fetchers/fundamentals_stock.py`

### Step 3.1: chip_stock.py 觸發整合

**File:** `stock/dashboard/backend/fetchers/chip_stock.py`

In `fetch_stock_chip`, after the `save_chip_daily_rows(merged)` call near the end, BEFORE the `print(...)` and `return True`, add:

```python
    # Phase 4 alert 觸發:只在「最新一天有寫入」時針對 5 個籌碼指標檢查
    today_str = today.strftime("%Y-%m-%d")
    max_date = max((r["date"] for r in merged), default=None)
    if max_date == today_str:
        from alerts import check_alerts
        for key in ("foreign_net", "trust_net", "dealer_net",
                    "margin_balance", "short_balance"):
            check_alerts("stock_indicator", ticker, indicator_key=key)
```

(注意:`today` 變數在函式上面已用 `datetime.now(timezone.utc).astimezone().date()` 算出,可直接重用。)

### Step 3.2: fundamentals_stock.py — fetch_stock_per 觸發整合

**File:** `stock/dashboard/backend/fetchers/fundamentals_stock.py`

In `fetch_stock_per`, after `save_per_daily_rows(rows)` call, BEFORE the `print(...)` and `return True`, add:

```python
    # Phase 4 alert 觸發:只在「最新一天有寫入」時針對 3 個估值指標檢查
    today_str = today.strftime("%Y-%m-%d")
    max_date = max((r["date"] for r in rows), default=None)
    if max_date == today_str:
        from alerts import check_alerts
        for key in ("per", "pbr", "dividend_yield"):
            check_alerts("stock_indicator", ticker, indicator_key=key)
```

### Step 3.3: Run regression to confirm no test breaks

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 所有測試結果跟 T2 結束時相同(no regression)。Fetcher 觸發是 production-only 行為,test 用 mock 不會打到。

### Step 3.4: Commit

```bash
git add stock/dashboard/backend/fetchers/chip_stock.py \
        stock/dashboard/backend/fetchers/fundamentals_stock.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): trigger alert check after stock daily fetch (T3)

chip_stock.fetch_stock_chip 與 fundamentals_stock.fetch_stock_per 在寫入
後,當「max date == today」時對該 ticker 的對應個股 daily 指標(籌碼 5
個 + 估值 3 個)逐一呼叫 check_alerts。只在最新一天觸發,避免 backfill
歷史日期時 spam。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Scheduler watchlist 主動拉

**目標:** 新增 `fetch_watchlist_stock_daily` 函式拉 watchlist 中所有台股 ticker 的 chip + per 資料;scheduler.py 加每日 18:30 TST cron job。

**Files:**
- Modify: `stock/dashboard/backend/fetchers/fundamentals_stock.py`
- Modify: `stock/dashboard/backend/scheduler.py`

### Step 4.1: 寫 `fetch_watchlist_stock_daily` 函式

**File:** `stock/dashboard/backend/fetchers/fundamentals_stock.py`

At the end of the file, append:

```python
def fetch_watchlist_stock_daily() -> None:
    """Daily cron entry:對 watchlist 中所有台股 ticker 拉 chip_stock + PER。

    Lazy 路徑保留(個股頁打開時也拉);此函式確保 watchlist 上有警示的
    ticker 每天有最新資料,警示能可靠觸發。Watchlist 為空時 early return。
    """
    from db import get_watched_tickers
    from fetchers.chip_stock import fetch_stock_chip

    tickers = get_watched_tickers()
    tw_tickers = [t for t in tickers if to_finmind_id(t) is not None]
    if not tw_tickers:
        print("[watchlist_chip_per] watchlist 中無台股 ticker,skip")
        return

    print(f"[watchlist_chip_per] 拉 {len(tw_tickers)} 檔台股 chip + PER")
    for ticker in tw_tickers:
        try:
            fetch_stock_chip(ticker)
        except Exception as e:
            print(f"[watchlist_chip_per] {ticker} chip error: {e}")
        try:
            fetch_stock_per(ticker)
        except Exception as e:
            print(f"[watchlist_chip_per] {ticker} per error: {e}")
```

### Step 4.2: scheduler.py — 加 cron job

**File:** `stock/dashboard/backend/scheduler.py`

In the imports section at top of file, add:

```python
from fetchers.fundamentals_stock import fetch_watchlist_stock_daily
```

In `start_scheduler()`, after the existing `fetch_chip_total` job (around L28), add:

```python
    # Phase 4: watchlist 個股 daily 主動拉(chip + PER),確保警示能觸發
    scheduler.add_job(
        fetch_watchlist_stock_daily,
        CronTrigger(hour=18, minute=30, timezone=TST),
        id="watchlist_chip_per",
        replace_existing=True,
    )
```

### Step 4.3: 確認沒有 regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -5
```

Expected: 不變(scheduler import 不影響 test runtime)。

### Step 4.4: Commit

```bash
git add stock/dashboard/backend/fetchers/fundamentals_stock.py \
        stock/dashboard/backend/scheduler.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): watchlist daily chip + PER scheduler job (T4)

新增 fetch_watchlist_stock_daily 函式對 watchlist 中所有台股 ticker 各
呼叫 fetch_stock_chip + fetch_stock_per;每個 fetcher 內部失敗不擋住其
他 ticker。Scheduler 加 18:30 TST 每日 cron job(設計變更:個股 fetcher
從純 lazy 改為 lazy + scheduled 雙模式,確保 watchlist 上有警示的 ticker
每天有最新資料 → 警示能可靠觸發)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: API — POST /api/alerts 擴展驗證

**目標:** `AlertRequest` model 加 `indicator_key` / `window_n`;`POST /api/alerts` 驗證 stock_indicator + streak_*;`VALID_*` set 擴展。

**Files:**
- Modify: `stock/dashboard/backend/app.py`
- Modify: `stock/dashboard/tests/test_api.py`

### Step 5.1: 寫 API 失敗測試

**File:** `stock/dashboard/tests/test_api.py`(append at end)

```python
def test_post_alert_stock_indicator_per_above():
    db.init_db()
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "above",
        "threshold": 30,
        "indicator_key": "per",
    })
    assert r.status_code == 200
    body = r.json()
    assert "id" in body


def test_post_alert_stock_indicator_streak_below_with_window_n():
    db.init_db()
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "streak_below",
        "threshold": 25,
        "indicator_key": "per",
        "window_n": 5,
    })
    assert r.status_code == 200


def test_post_alert_stock_indicator_missing_indicator_key_400():
    db.init_db()
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "above",
        "threshold": 30,
    })
    assert r.status_code == 400


def test_post_alert_stock_indicator_unknown_indicator_key_400():
    db.init_db()
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "2330.TW",
        "condition": "above",
        "threshold": 30,
        "indicator_key": "unknown",
    })
    assert r.status_code == 400


def test_post_alert_stock_indicator_non_taiwan_ticker_400():
    db.init_db()
    r = client.post("/api/alerts", json={
        "target_type": "stock_indicator",
        "target": "AAPL",
        "condition": "above",
        "threshold": 30,
        "indicator_key": "per",
    })
    assert r.status_code == 400


def test_post_alert_streak_missing_window_n_400():
    db.init_db()
    r = client.post("/api/alerts", json={
        "target_type": "indicator",
        "target": "margin_balance",
        "condition": "streak_above",
        "threshold": 5000,
    })
    assert r.status_code == 400


def test_post_alert_streak_window_n_out_of_range_400():
    db.init_db()
    r = client.post("/api/alerts", json={
        "target_type": "indicator",
        "target": "margin_balance",
        "condition": "streak_above",
        "threshold": 5000,
        "window_n": 1,    # < 2
    })
    assert r.status_code == 400
    r2 = client.post("/api/alerts", json={
        "target_type": "indicator",
        "target": "margin_balance",
        "condition": "streak_above",
        "threshold": 5000,
        "window_n": 31,   # > 30
    })
    assert r2.status_code == 400
```

### Step 5.2: Run, verify failures

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_api.py -v -k "stock_indicator or streak"
```

Expected: 7 tests FAILED(API 還沒接 stock_indicator 也沒驗證 window_n)。

### Step 5.3: app.py — extend AlertRequest + validation

**File:** `stock/dashboard/backend/app.py`

Replace the existing `AlertRequest`, `VALID_TARGET_TYPES`, `VALID_CONDITIONS` and `create_alert` function block with:

```python
class AlertRequest(BaseModel):
    target_type: str
    target: str
    condition: str
    threshold: float
    indicator_key: str | None = None
    window_n: int | None = None


class AlertToggleRequest(BaseModel):
    enabled: bool


VALID_TARGET_TYPES = {"indicator", "stock", "stock_indicator"}
VALID_CONDITIONS = {"above", "below", "streak_above", "streak_below"}
STOCK_DAILY_INDICATOR_KEYS = {
    "per", "pbr", "dividend_yield",
    "foreign_net", "trust_net", "dealer_net",
    "margin_balance", "short_balance",
}


@app.get("/api/alerts")
def get_alerts():
    return list_alerts()


@app.post("/api/alerts")
def create_alert(req: AlertRequest):
    if req.target_type not in VALID_TARGET_TYPES:
        raise HTTPException(status_code=400, detail="Invalid target_type")
    if req.condition not in VALID_CONDITIONS:
        raise HTTPException(status_code=400, detail="Invalid condition")

    # streak_* 必須帶 window_n,且範圍 2..30
    is_streak = req.condition.startswith("streak_")
    if is_streak:
        if req.window_n is None:
            raise HTTPException(status_code=400, detail="streak condition requires window_n")
        if req.window_n < 2 or req.window_n > 30:
            raise HTTPException(status_code=400, detail="window_n must be 2..30")

    if req.target_type == "indicator":
        if req.target not in INDICATOR_NAMES:
            raise HTTPException(status_code=400, detail="Unknown indicator")
        target = req.target
    elif req.target_type == "stock_indicator":
        if not req.indicator_key:
            raise HTTPException(status_code=400, detail="stock_indicator requires indicator_key")
        if req.indicator_key not in STOCK_DAILY_INDICATOR_KEYS:
            raise HTTPException(status_code=400, detail="Unknown indicator_key")
        if fundamentals_to_finmind_id(req.target) is None:
            raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) supported")
        target = req.target.upper()
    else:  # stock
        target = req.target.upper()

    alert_id = add_alert(req.target_type, target, req.condition, req.threshold,
                         indicator_key=req.indicator_key, window_n=req.window_n)
    return {"id": alert_id}
```

(注意:`fundamentals_to_finmind_id` 已 imported in app.py 從 Phase 2 開始。如果發現沒 import,從 `from fetchers.fundamentals_stock import ...` 那段補上。)

### Step 5.4: Run, verify pass

```bash
cd stock/dashboard/backend && python -m pytest ../tests/test_api.py -v -k "stock_indicator or streak"
```

Expected: 7 passed.

### Step 5.5: Run full regression

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 既有所有 + 7 new = 累計增加,5 pre-existing fail 不變。

### Step 5.6: Commit

```bash
git add stock/dashboard/backend/app.py \
        stock/dashboard/tests/test_api.py
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): API alert validation for stock_indicator and streak (T5)

AlertRequest 加 indicator_key / window_n optional 欄。POST /api/alerts 加
驗證:streak_* 必帶 window_n (2..30);stock_indicator 必帶 indicator_key
且須是 8 個 daily 指標之一,target 須為台股 ticker。VALID_TARGET_TYPES
/ VALID_CONDITIONS 對應擴展。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: UI 擴展 — alert form 動態欄位

**目標:** `index.html` alert form 加 stock_indicator target_type / streak_* condition / indicator_key 與 window_n 動態欄位;JS 處理新格式渲染。

**Files:**
- Modify: `stock/dashboard/frontend/index.html`

### Step 6.1: 修改 alert form HTML

**File:** `stock/dashboard/frontend/index.html`

Locate the existing `<div class="alert-form">` block (around L386-398). Replace with:

```html
  <div class="alert-form">
    <select id="alert-target-type">
      <option value="indicator">指標</option>
      <option value="stock">股票 / ETF</option>
      <option value="stock_indicator">個股指標</option>
    </select>
    <select id="alert-target"></select>
    <select id="alert-indicator-key" style="display:none">
      <option value="per">PER</option>
      <option value="pbr">PBR</option>
      <option value="dividend_yield">殖利率</option>
      <option value="foreign_net">外資淨買</option>
      <option value="trust_net">投信淨買</option>
      <option value="dealer_net">自營淨買</option>
      <option value="margin_balance">融資餘額</option>
      <option value="short_balance">融券餘額</option>
    </select>
    <select id="alert-condition">
      <option value="above">大於等於</option>
      <option value="below">小於等於</option>
      <option value="streak_above">連 N 日突破</option>
      <option value="streak_below">連 N 日跌破</option>
    </select>
    <input id="alert-window-n" type="number" min="2" max="30" placeholder="N 日" value="5" style="display:none">
    <input id="alert-threshold" type="number" step="any" placeholder="門檻數值">
    <button onclick="addAlert()">+ 新增警示</button>
  </div>
```

(新增的 `<select id="alert-indicator-key">` 跟 `<input id="alert-window-n">` 預設 `display:none`,JS 控制何時顯示。)

### Step 6.2: 加 STOCK_INDICATOR_LABELS + 修 alertTargetLabel + 加 alertConditionLabel

**File:** `stock/dashboard/frontend/index.html`

Locate the existing JS `INDICATOR_LABELS` const (around L637-648). After it, add `STOCK_INDICATOR_LABELS`:

```javascript
const STOCK_INDICATOR_LABELS = {
  per:              'PER',
  pbr:              'PBR',
  dividend_yield:   '殖利率',
  foreign_net:      '外資淨買',
  trust_net:        '投信淨買',
  dealer_net:       '自營淨買',
  margin_balance:   '融資餘額',
  short_balance:    '融券餘額',
};
```

Replace the existing `alertTargetLabel(a)` function (after STOCK_INDICATOR_LABELS) with:

```javascript
function alertTargetLabel(a) {
  if (a.target_type === 'indicator') return INDICATOR_LABELS[a.target] || a.target;
  if (a.target_type === 'stock_indicator') {
    const ikLabel = STOCK_INDICATOR_LABELS[a.indicator_key] || a.indicator_key || '';
    return `${a.target} ${ikLabel}`;
  }
  return a.target;   // stock
}

function alertConditionLabel(a) {
  if (a.condition === 'above') return '≥';
  if (a.condition === 'below') return '≤';
  if (a.condition === 'streak_above') return `連 ${a.window_n} 日 ≥`;
  if (a.condition === 'streak_below') return `連 ${a.window_n} 日 ≤`;
  return a.condition;
}
```

### Step 6.3: 改 loadAlerts 渲染使用新 label 函式

**File:** `stock/dashboard/frontend/index.html`

In existing `loadAlerts()` function, find the line:

```javascript
    const condText = a.condition === 'above' ? '≥' : '≤';
```

Replace with:

```javascript
    const condText = alertConditionLabel(a);
```

(其餘 list rendering 不變,因為 `${condText}` 已涵蓋 streak 文字。)

### Step 6.4: 修 refreshTargetOptions 處理 stock_indicator + 動態 indicator_key/window_n 顯示

**File:** `stock/dashboard/frontend/index.html`

Replace the existing `refreshTargetOptions` function with:

```javascript
async function refreshTargetOptions() {
  const type = document.getElementById('alert-target-type').value;
  const targetSelect = document.getElementById('alert-target');
  const indKeyEl = document.getElementById('alert-indicator-key');
  targetSelect.innerHTML = '';

  // indicator_key 只在 stock_indicator 時顯示
  indKeyEl.style.display = (type === 'stock_indicator') ? '' : 'none';

  if (type === 'indicator') {
    Object.entries(INDICATOR_LABELS).forEach(([k, label]) => {
      const opt = document.createElement('option');
      opt.value = k;
      opt.textContent = label;
      targetSelect.appendChild(opt);
    });
    return;
  }

  // stock 與 stock_indicator 都列 watchlist 中的 ticker
  const stocks = await fetch(API_BASE + '/api/stocks').then(r => r.json()).catch(() => []);
  if (!stocks.length) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = '（請先在自選股新增）';
    targetSelect.appendChild(opt);
    return;
  }
  for (const s of stocks) {
    const opt = document.createElement('option');
    opt.value = s.ticker;
    opt.textContent = s.name ? `${s.ticker} · ${s.name}` : s.ticker;
    targetSelect.appendChild(opt);
  }
}

function refreshConditionFields() {
  const cond = document.getElementById('alert-condition').value;
  const windowEl = document.getElementById('alert-window-n');
  windowEl.style.display = cond.startsWith('streak_') ? '' : 'none';
}
```

In the existing event listener registration (search for `alert-target-type` `addEventListener`,around L758),add a second listener for condition change. Replace the existing single line with:

```javascript
document.getElementById('alert-target-type').addEventListener('change', refreshTargetOptions);
document.getElementById('alert-condition').addEventListener('change', refreshConditionFields);
```

In the bottom IIFE bootstrap (around L775+),find `await refreshTargetOptions();` and immediately after add:

```javascript
  refreshConditionFields();
```

### Step 6.5: 修 addAlert 帶 indicator_key + window_n

**File:** `stock/dashboard/frontend/index.html`

Replace the existing `addAlert()` function with:

```javascript
async function addAlert() {
  const target_type = document.getElementById('alert-target-type').value;
  const target = document.getElementById('alert-target').value;
  const condition = document.getElementById('alert-condition').value;
  const thresholdRaw = document.getElementById('alert-threshold').value;
  if (!target || thresholdRaw === '') {
    alert('請選擇目標並輸入門檻數值');
    return;
  }
  const payload = { target_type, target, condition, threshold: Number(thresholdRaw) };

  if (target_type === 'stock_indicator') {
    payload.indicator_key = document.getElementById('alert-indicator-key').value;
  }
  if (condition.startsWith('streak_')) {
    const wn = document.getElementById('alert-window-n').value;
    if (wn === '') {
      alert('streak 警示需輸入 N 日');
      return;
    }
    payload.window_n = Number(wn);
  }

  const r = await fetch(API_BASE + '/api/alerts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    alert('建立失敗:' + (err.detail || r.status));
    return;
  }
  document.getElementById('alert-threshold').value = '';
  loadAlerts();
}
```

### Step 6.6: CSS — alert-form grid template column 從 5 欄改 7 欄

**File:** `stock/dashboard/frontend/index.html`

Locate the existing CSS rule (around L60):

```css
.alert-form { display: grid; grid-template-columns: 1.4fr 1.6fr 1fr 1fr auto; gap: 8px; margin-top: 12px; }
```

Replace with(支援 7 欄 — 多 1 個 indicator-key select 跟 1 個 window-n input):

```css
.alert-form { display: grid; grid-template-columns: 1.2fr 1.4fr 1.2fr 1fr 0.6fr 1fr auto; gap: 8px; margin-top: 12px; }
```

(對應元素順序:target-type / target / indicator-key / condition / window-n / threshold / button。即使 indicator-key / window-n `display:none`,grid 行為也合理,因為 hidden 元素不佔 grid track。)

待 720px 以下 media query(around L73)維持 fallback 自動換行,沒 issue。

### Step 6.7: 手動 grep 驗證 + Commit

```bash
grep -n "alert-indicator-key\|alert-window-n\|STOCK_INDICATOR_LABELS\|alertConditionLabel\|refreshConditionFields" stock/dashboard/frontend/index.html
```

Expected: 各看到 HTML 定義 + JS 引用。

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -5
```

Backend tests 不該因前端變動 regress。

```bash
git add stock/dashboard/frontend/index.html
git commit -m "$(cat <<'EOF'
feat(stock-dashboard): alert form supports stock_indicator + streak (T6)

index.html alert form 加「個股指標」target type、indicator_key 8 選 1
下拉、「連 N 日突破/跌破」condition、N 日數字輸入,動態顯示對應欄位。
JS 加 STOCK_INDICATOR_LABELS、alertConditionLabel、refreshConditionFields,
loadAlerts 渲染含 streak 文字。CSS grid template 從 5 欄擴 7 欄。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Deploy + 驗證

**目標:** push 觸發 workflow 部署、curl 設一個 alert 並驗證警示能透過 Discord 觸發、確認 scheduler job 註冊。

### Step 7.1: 確認本機所有測試通過

```bash
cd stock/dashboard/backend && python -m pytest ../tests/ -v 2>&1 | tail -10
```

Expected: 較 Phase 2 完成時的 53 passed 多出 ~16-20 個(streak 6 + history 3 + routing 4 + API 7 = 20 個新 test),5 pre-existing failures 不變。

### Step 7.2: Push

```bash
git push origin master
```

### Step 7.3: Watch deploys

```bash
gh run watch $(gh run list --workflow=deploy-stock-dashboard-backend.yml --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
gh run watch $(gh run list --workflow=deploy-stock-dashboard.yml         --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
```

Expected: 兩個 workflow success(各約 20-30s)。

### Step 7.4: 驗證 alert API 能接受新 payload

```bash
echo '--- POST stock_indicator alert ---'
curl -s -X POST 'https://api.paul-learning.dev/api/alerts' \
  -H 'Content-Type: application/json' \
  -d '{"target_type":"stock_indicator","target":"2330.TW","condition":"below","threshold":1000,"indicator_key":"per"}' | jq

echo '--- POST streak alert ---'
curl -s -X POST 'https://api.paul-learning.dev/api/alerts' \
  -H 'Content-Type: application/json' \
  -d '{"target_type":"indicator","target":"margin_balance","condition":"streak_above","threshold":100,"window_n":3}' | jq

echo '--- GET alerts (verify both stored) ---'
curl -s 'https://api.paul-learning.dev/api/alerts' | jq '[.[] | select(.target_type=="stock_indicator" or .condition | startswith("streak_"))]'
```

Expected: 兩個 POST 各回 `{"id": N}`;GET 回 array 含這兩個 alert 完整欄(target_type / condition / indicator_key / window_n)。

### Step 7.5: 驗證 alert 觸發機制(用門檻已被超過的測試)

剛剛建立的兩個 alert 門檻都極低(per < 1000 必觸發、margin_balance 連 3 日 ≥ 100 億必觸發)。下次 fetcher 跑 / scheduler 跑就會觸發 Discord 通知。

立刻手動觸發 chip_total fetch 來測試 streak alert(整體指標路徑):

```bash
ssh root@${VPS_HOST} "cd /opt/stock-dashboard/backend && .venv/bin/python -c '
import sys; sys.path.insert(0, \".\")
from db import init_db
init_db()
from fetchers.chip_total import fetch_chip_total
fetch_chip_total()
'"
```

Expected: 應該看到 print log;Discord 應該收到「margin_balance 連 3 日突破 100」訊息(因為 margin_balance 一定 > 100 億)。

確認 alert 已被自動 disable:

```bash
curl -s 'https://api.paul-learning.dev/api/alerts' | jq '[.[] | select(.condition=="streak_above")]'
```

Expected: `enabled: 0`,且 `triggered_at` 有值。

### Step 7.6: 用 watchlist scheduler 驗證 stock_indicator alert

stock_indicator alert 需要 fetch_stock_per 在最新一天時觸發。可手動跑 fetch_watchlist_stock_daily 測試:

```bash
ssh root@${VPS_HOST} "cd /opt/stock-dashboard/backend && .venv/bin/python -c '
import sys; sys.path.insert(0, \".\")
from db import init_db
init_db()
from fetchers.fundamentals_stock import fetch_watchlist_stock_daily
fetch_watchlist_stock_daily()
'"
```

Expected: log 顯示 watchlist 中每檔 ticker 拉 chip + per;若 watchlist 中有 2330.TW,fetch_stock_per 寫入後會對 stock_indicator(per below 1000)觸發 alert,Discord 收到「2330.TW PER 目前 X.XX,已跌破門檻 1000」。

### Step 7.7: VPS .env sanity

```bash
ssh root@${VPS_HOST} "awk -F= '{print \$1}' /opt/stock-dashboard/backend/.env"
```

Expected: `DISCORD_STOCK_WEBHOOK_URL`、`FINMIND_TOKEN` 都在。

### Step 7.8: 清理測試 alert(user-action)

兩個測試 alert 已 triggered → enabled=0,可以保留(user 已知用途)或手動 DELETE:

```bash
curl -s -X DELETE 'https://api.paul-learning.dev/api/alerts/<id>'
```

### Step 7.9: 報告

執行者最終報告:
- 本機測試結果
- Push commit SHA
- 兩個 workflow 的成功狀態
- 測試 alert POST + GET 的 verbatim 結果
- 手動觸發 fetcher 的 log 摘要
- Discord 收到的訊息(如可從 webhook 觀察 / 截圖佐證)
- VPS .env keys
- 手動 UI 驗證提示給使用者(alert form 應顯示新 options;新 alert 應該以新 label 格式列出)

---

## 完成後狀態

- `price_alerts` 表加 `indicator_key`、`window_n` 欄(idempotent migration)
- `alerts.py` 支援 4 種 condition × 3 種 target_type 的 routing(共有意義組合 7 種)
- 8 個 daily 個股指標(估值 3 + 籌碼 5)可警示
- 連 N 日警示對 daily 個股 + 整體 indicator 都適用
- Scheduler 每天 18:30 TST 主動拉 watchlist 個股 chip + per
- Phase 1+2 已部署的 fetcher 觸發整合好了
- 警示規則層完整實裝(Phase 1+2 的「out-of-scope」全補上)

## 風險與緩解(備忘)

- **fetcher 觸發 spam**:`max date == today` guard 確保 backfill 寫入歷史日期不會 spam
- **Streak 遇假日**:`_get_stock_indicator_history` 取「最近 n 個有資料的點」(過濾 None,不要求連續日曆日)
- **Watchlist 為空**:`fetch_watchlist_stock_daily` 早 return 跟 log
- **Watchlist 變大時 quota**:每 ticker 2 個 FinMind requests,100 ticker = 200/day,FinMind 600/hr 配額遠夠
- **既有 alert(沒 indicator_key/window_n)的 routing 安全**:DB ALTER 加欄預設 NULL,既有 alert 走 `(indicator/stock, above/below)` 舊路徑,routing 在 streak / stock_indicator 分支才讀新欄
