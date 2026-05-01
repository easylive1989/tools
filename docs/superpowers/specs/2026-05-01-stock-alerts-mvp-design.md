# Stock Dashboard 警示深化 MVP 設計

**日期**: 2026-05-01
**狀態**: 已批准,待產實作計畫
**前置**: Phase 4(警示規則)+ Phase 4 follow-up 已上線。本 MVP 為警示能力深化的第一波 — 只覆蓋「PER 5y 百分位」+「月營收 YoY」兩個高頻使用情境。

## 背景

Phase 4 警示只支援 daily 指標的「raw 值 vs threshold」與「streak 連 N 個值」。但價值投資者真正常看的兩種訊號是:

1. **估值百分位**:目前 PER / PBR / 殖利率在 5 年區間的位置(高估或低估?)
2. **基本面 YoY**:月營收 YoY%(成長動能)

這兩個都需要「衍生計算」+「跨時間粒度」資料,Phase 4 schema 不支援。本案擴充。

## 範圍

### In scope

新增 4 個 condition 值 + 1 個新 indicator_key:

| Condition | 解讀 | 適用 indicator_key |
|---|---|---|
| `percentile_above` | 5y 百分位 > threshold(0-100) | per / pbr / dividend_yield(daily) |
| `percentile_below` | 5y 百分位 < threshold(0-100) | 同上 |
| `yoy_above` | YoY % > threshold(可正可負) | revenue(monthly) |
| `yoy_below` | YoY % < threshold | 同上 |

新 indicator_key: **`revenue`**(對應 `stock_revenue_monthly` 表的月營收)。

### Out of scope

- 季 / 年指標警示(EPS、毛利率、配發率…)留 backlog
- QoQ 警示、連 N 月 YoY 警示
- 跨指標複合條件(`PER < 20 且 EPS YoY > 30%`)

## DB schema

**不需 ALTER**。`condition` 欄位已是字串,接受新 4 種值。`indicator_key` 欄位也是字串,接受新 `revenue` 值。

## Backend

### Engine routing(`alerts.py`)

`check_alerts` 加 4 條新分支:

- `stock_indicator + percentile_above | percentile_below`:
  - 拉 5y daily 歷史 `_get_stock_indicator_history(target, indicator_key, n=1825)`
  - 算當前值百分位 `_pct_rank(latest, history)`(inclusive rank: `count(v <= latest) / total * 100`)
  - 比較 vs threshold
  - 只支援 daily indicator(per / pbr / dividend_yield)— 其他 indicator_key 跳過

- `stock_indicator + yoy_above | yoy_below`:
  - `_get_stock_revenue_yoy(target)` — 從 `stock_revenue_monthly` 拉最新月 + 去年同月,算 `(cur - prev) / prev * 100`
  - 比較 vs threshold
  - 只支援 monthly indicator(revenue)— 其他 indicator_key 跳過
  - 缺去年同期資料(新上市股)→ 回 None,不觸發

### 新純函式

- `_pct_rank(value, history) -> float | None`:百分位 0-100;history 不足 30 點回 None(避免新上市股誤觸發)
- `_get_stock_revenue_yoy(ticker) -> float | None`:回 YoY%,缺資料回 None

### Fetcher 觸發整合

- `fetch_stock_per` 既有 P4 trigger 已涵蓋(percentile alert 自動 ride)
- `fetch_stock_revenue` 加新 trigger:寫入後若 max(year, month) 比 DB 中 P4 之前最新月還新,呼叫 `check_alerts("stock_indicator", ticker, indicator_key="revenue")`
  - 「max 變動才觸發」guard 避免重複觸發(類似 P4 的「max date == today」)

### Scheduler 擴充

`fetch_watchlist_stock_daily` 加第三個 fetcher 呼叫:

```python
fetch_stock_chip(ticker)
fetch_stock_per(ticker)
fetch_stock_revenue(ticker)   # 新增
```

每日 18:30 跑,fetcher 內部 lazy 邏輯確保只在月份變動時打 FinMind。新增不影響現有兩個 fetcher 行為。

## API(`app.py`)

### 擴展常數

```python
VALID_CONDITIONS = {
    "above", "below",
    "streak_above", "streak_below",
    "percentile_above", "percentile_below",   # 新
    "yoy_above", "yoy_below",                  # 新
}

STOCK_DAILY_INDICATOR_KEYS = {  # P4 既有,不變
    "per", "pbr", "dividend_yield",
    "foreign_net", "trust_net", "dealer_net",
    "margin_balance", "short_balance",
}
STOCK_MONTHLY_INDICATOR_KEYS = {"revenue"}    # 新
STOCK_INDICATOR_KEYS = STOCK_DAILY_INDICATOR_KEYS | STOCK_MONTHLY_INDICATOR_KEYS
```

### POST 驗證新交叉規則

- `percentile_*` condition 必須搭 daily indicator_key(否則 400)
- `yoy_*` condition 必須搭 monthly indicator_key(否則 400)
- 既有 above/below/streak_* 維持原驗證

threshold 範圍驗證(輕):
- `percentile_*`:0-100
- `yoy_*`:不限,可正可負(YoY 可大幅漲跌)

## UI(`index.html` alert form)

- `<select id="alert-condition">` 加 4 option(`5y 百分位 突破 / 跌破`、`YoY % 突破 / 跌破`)
- `<select id="alert-indicator-key">` 加 `<option value="revenue">月營收</option>`(放在 daily 8 個之後)
- `<input id="alert-threshold">` placeholder 動態切換:
  - `above`/`below`:既有「門檻數值」
  - `streak_*`:「門檻數值」
  - `percentile_*`:「百分位 0-100」
  - `yoy_*`:「YoY % (可正可負)」
- `alertConditionLabel`:加 4 種文字
  - `percentile_above` → `5y百分位 ≥`
  - `percentile_below` → `5y百分位 ≤`
  - `yoy_above` → `YoY ≥`
  - `yoy_below` → `YoY ≤`
- `STOCK_INDICATOR_LABELS` 加 `revenue: '月營收'`

## Tests

- `test_alerts.py`:
  - `test_pct_rank_*`(empty / insufficient / inclusive rank 100 / rank 50)
  - `test_get_stock_revenue_yoy_*`(missing / negative / positive)
  - `test_check_alerts_stock_indicator_percentile_above_triggers`
  - `test_check_alerts_stock_indicator_yoy_above_triggers`
  - `test_check_alerts_percentile_only_for_daily_keys`(yoy_above + per 拒絕觸發)
- `test_api.py`:
  - `test_post_alert_percentile_with_per`(成功)
  - `test_post_alert_percentile_with_revenue_400`(交叉驗證拒絕)
  - `test_post_alert_yoy_with_revenue`(成功)
  - `test_post_alert_yoy_with_per_400`

## Tasks

| # | Task | 範圍 | 規模 |
|---|---|---|---|
| **T1** | 新純函式 `_pct_rank` + `_get_stock_revenue_yoy` + 單元測試 | engine | 小 |
| **T2** | `check_alerts` 加 4 條 routing(percentile / yoy)+ Discord 訊息 format 對應 + 整合測試 | engine | 中 |
| **T3** | `fetch_stock_revenue` trigger 整合(寫入後若新月則 check_alerts);scheduler `fetch_watchlist_stock_daily` 加 revenue | fetcher + scheduler | 小 |
| **T4** | API:VALID_CONDITIONS / STOCK_MONTHLY_INDICATOR_KEYS / 交叉驗證 + 4 個 API 測試 | API | 小 |
| **T5** | UI:condition options / indicator_key option / threshold placeholder 動態 / label / STOCK_INDICATOR_LABELS | 前端 | 中 |
| **T6** | Deploy + e2e 驗證(建 percentile + yoy 各 1 個 alert,觀察 Discord 通知)| 部署 | 小 |

6 個 task。T1→T2 順序固定;T3 / T4 / T5 可平行(都依賴 T2);T6 最後。

## 風險

| 風險 | 緩解 |
|---|---|
| 新上市股 5y 歷史不足 → percentile 誤觸發 | `_pct_rank` history < 30 點回 None |
| 新上市股缺去年同月 → YoY 誤觸發 | `_get_stock_revenue_yoy` missing 回 None |
| Scheduler 加第三個 fetcher → quota 壓力 | 100 ticker × 3 = 300 req/day,FinMind 600/hr 內 |
| 月營收 fetcher 寫入時實際月份沒變動仍呼叫 check_alerts | 用「fetcher 寫入的 max(y,m) > pre-fetch 的 latest_ym」guard |

## 後續(backlog)

- 季指標 percentile / YoY(EPS、毛利率)
- 年指標 YoY(配發率)
- 連 N 月 YoY 警示
- 跨指標複合條件
