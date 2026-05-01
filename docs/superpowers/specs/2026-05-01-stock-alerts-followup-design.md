# Stock Dashboard 警示系統收尾(Phase 4 Follow-up)設計

**日期**: 2026-05-01
**狀態**: 已批准,待產實作計畫
**前置**: Phase 4(警示規則)已上線。本文件處理 Phase 4 final review 留下的兩個 minor backlog issues。

## 背景

Phase 4 final review 指出兩個 design-level 議題:

1. **`tw_volume` / `us_volume` alert dead zone**:`INDICATOR_NAMES` 含這兩個 key,使用者透過 API 可建立 alert,但 `fetchers/volume.py` 沒呼叫 `check_alerts`,alert 永不觸發。silent failure。

2. **Watchlist 移除 ticker 時 stock_indicator alert stale**:`remove_watched_ticker(ticker)` 只刪 `watched_stocks`,該 ticker 的 stock_indicator alert 留在 DB,但 scheduler 不再拉新資料 → alert 失效或誤觸發。

兩個都不影響核心功能,但屬於正確性 / 一致性問題,屬「P4 收尾」範疇。

## 範圍

### In scope

1. **volume fetcher 加 check_alerts 觸發**:
   - `fetch_tw_volume()` 寫入後呼叫 `check_alerts("indicator", "tw_volume", value)`
   - `fetch_us_volume()` 同樣
2. **`remove_watched_ticker` 連動停用 stock_indicator alerts**:
   - 移除 ticker 時 SQL `UPDATE price_alerts SET enabled=0 WHERE target_type='stock_indicator' AND target=?`
   - 不刪除 alert,保留 audit trail。UI 上 alert 仍可見、顯示「已停用」,user 可手動重新啟用(若 ticker 重新加回 watchlist 後想恢復警示)

### Out of scope

- Phase 4 final review 提到的其他 design 議題(例如 watchlist removed ticker 的 ticker-not-in-watchlist UI flag)
- 月/季/年指標警示能力(留 backlog)

## Backend

### `fetchers/volume.py` — 加 check_alerts trigger

兩個函式各加一行(在 `save_indicator(...)` 後):

```python
# fetch_tw_volume:
save_indicator("tw_volume", value_yi, json.dumps({...}))
check_alerts("indicator", "tw_volume", value_yi)   # 新增

# fetch_us_volume:
save_indicator("us_volume", value_yi, json.dumps({...}))
check_alerts("indicator", "us_volume", value_yi)   # 新增
```

需要 `from alerts import check_alerts`(若 volume.py 還沒 import)。

### `db.py` — `remove_watched_ticker` 加連動

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

## Tests

- `test_fetchers.py`:`test_fetch_tw_volume_*` / `test_fetch_us_volume_*` 加上 `check_alerts` 被呼叫的 assertion(若既有 test 已 mock save_indicator,順便確認 check_alerts 也 mock 並 assert called)
- `test_db.py`:加 `test_remove_watched_ticker_disables_stock_indicator_alerts`:setup 一個 stock_indicator alert,呼叫 remove,驗證 alert.enabled = 0;同時驗證 indicator/stock 類型 alert 不受影響

## Tasks

| # | Task | 範圍 | 規模 |
|---|---|---|---|
| **T1** | volume.py 加 check_alerts + test | 後端 | 小 |
| **T2** | db.remove_watched_ticker 加連動 + test | 後端 | 小 |
| **T3** | Deploy + 驗證(curl 設個 tw_volume alert + remove 一個 watched ticker) | 部署 | 小 |

3 個 task。T1 / T2 可並行(都不互相依賴)。T3 最後。

## 風險

| 風險 | 緩解 |
|---|---|
| volume.py 加 check_alerts 後 backfill / 歷史重抓觸發 alert spam | volume fetcher 都是 cron job 每天跑,沒 backfill 路徑;`backfill.py` 中的 `backfill_tw_volume` / `backfill_us_volume` 直接寫 DB(不走 fetcher),不會觸發 alert |
| `remove_watched_ticker` 改動影響既有 caller | 既有 caller 只 `delete_stock` endpoint(app.py:130);本改動不改 signature,行為延伸(多停用 alerts),向後相容 |
| 既有 `test_remove_watched_ticker` 是否有 | 預期沒(P0~P4 沒覆蓋這個 helper),新增 test 即可 |

## 後續

無新 backlog。本案結束後 stock dashboard 警示系統視為完整。
