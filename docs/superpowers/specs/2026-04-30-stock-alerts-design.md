# Stock Dashboard 警示規則 Phase 4 設計

**日期**: 2026-05-01
**狀態**: 已批准,待產實作計畫
**前置**: Phase 1 籌碼面、Phase 2 基本面 已完成上線。Phase 3 總體面 因 FinMind 把 `InterestRate` / `GovernmentBondsYield` 升為 Sponsor 限定而跳過。

## 背景

Phase 1 + 2 完成後,既有 alert 系統(`price_alerts` table、`check_alerts` engine、Discord 通知)只支援「整體 indicator 單值 above/below」與「個股價格 above/below」兩種型態。但已蒐集大量個股指標歷史(8 個 daily 欄位:估值 + 籌碼),沒有警示能力等於浪費。

Phase 4 補上**個股指標警示**(stock_indicator)+ **連 N 日警示**(streak),把警示功能補到「對個股投資真正實用」的程度。

## 範圍

### In scope

1. **個股指標警示** — 對 8 個 daily 個股欄位設警示:
   - **估值**(來源 `stock_per_daily`):per、pbr、dividend_yield
   - **籌碼**(來源 `stock_chip_daily`):foreign_net、trust_net、dealer_net、margin_balance、short_balance
2. **連 N 日警示**(streak above / below) — 對 daily 指標(整體 + 個股)都適用,N ∈ [2, 30],預設 5
3. **Scheduler 主動拉 watchlist 個股 daily fetch** — 每日 18:30 TST 對 `watched_stocks` 中所有台股 ticker 呼叫 `fetch_stock_chip` + `fetch_stock_per`,確保有警示的 ticker 每天有最新資料

### Out of scope

- **月/季/年指標警示**(月營收 YoY、EPS、毛利率、配發率…):觸發時機複雜、變動慢,且查個股頁就能看,push notification 邊際效益低。留 backlog。
- **跨指標複合條件**(`PER < 20 且 EPS YoY > 30%`):schema 複雜度顯著,留 backlog。
- **5y 百分位 / YoY 異常型警示**(例 PER 5y 百分位 > 95%):需要計算層級擴展,留 backlog。

## DB schema(擴展既有 `price_alerts`)

加 2 欄,沿用 `condition` 欄位接受 4 種值:

```sql
ALTER TABLE price_alerts ADD COLUMN indicator_key TEXT;  -- stock_indicator 必填,其他 NULL
ALTER TABLE price_alerts ADD COLUMN window_n INTEGER;    -- streak_* 必填,其他 NULL
```

- `target_type` 既有值 `{indicator, stock}` + 加 `stock_indicator`
- `condition` 既有值 `{above, below}` + 加 `{streak_above, streak_below}`
- `init_db()` 用 idempotent migration:`PRAGMA table_info(price_alerts)` 檢查缺欄 → 用 `ALTER TABLE` 加;已存在則 no-op

## Backend

### Alert engine 擴展(`alerts.py`)

```python
def check_alerts(target_type: str, target: str, value: float | None = None,
                 *, indicator_key: str | None = None) -> None:
    """
    Routing:
    - target_type='indicator', condition='above'/'below'
        → 既有單值比較(沿用)
    - target_type='indicator', condition='streak_above'/'streak_below'
        → 查 indicator_snapshots 最近 window_n 個值,全部達門檻才觸發
    - target_type='stock_indicator', condition='above'/'below'
        → 對 (target=ticker, indicator_key) 從對應 stock_*_daily 查最新值
    - target_type='stock_indicator', condition='streak_above'/'streak_below'
        → 對 (target=ticker, indicator_key) 查最近 window_n 個值
    - target_type='stock', condition='above'/'below'
        → 既有股價警示(沿用)
    """
```

新 helper `_check_streak(values, condition, threshold) -> bool`:純函式,單元測試容易。len(values) < window_n → False(資料不足不觸發)。

新 helper `_get_stock_indicator_history(ticker, indicator_key, n) -> list[float]`:依 indicator_key 路由到 `stock_per_daily` 或 `stock_chip_daily`,回傳最近 n 日值(舊→新排序)。

Discord `_build_payload` 增加 streak / stock_indicator 訊息格式:
- 既有(沿用):`🚨 加權指數 目前 21458,已突破門檻 21000`
- 新 streak indicator:`🚨 外資淨買超 連 3 日突破 200 億(目前 234.5 億)`
- 新 stock_indicator above:`🚨 2330.TW PER 目前 32.23,已突破門檻 30`
- 新 stock_indicator streak:`🚨 2330.TW 外資淨買 連 5 日突破 0(目前 +12.3 萬張)`

### Fetcher 觸發整合

- `chip_stock.py` 的 `fetch_stock_chip` 寫入 `stock_chip_daily` 後,對該 ticker 的 5 個籌碼 indicator_key 各呼叫一次 `check_alerts('stock_indicator', ticker, indicator_key=key)`
- `fundamentals_stock.py` 的 `fetch_stock_per` 寫入 `stock_per_daily` 後,對該 ticker 的 3 個估值 indicator_key 各呼叫一次

**只在「最新一天有新資料」時觸發**(避免歷史回填時 spam):fetcher 寫入後比對「DB latest_date」與「該 ticker 寫入的 max date」,只有當寫入 max date == today 才呼叫 check_alerts。

### Scheduler 主動拉 watchlist

`scheduler.py` 新增 daily cron job:

```python
scheduler.add_job(
    fetch_watchlist_stock_daily,
    CronTrigger(hour=18, minute=30, timezone=TST),
    id="watchlist_chip_per",
    replace_existing=True,
)
```

`fetch_watchlist_stock_daily()`(放在 `fetchers/fundamentals_stock.py` 或 `fetchers/chip_stock.py` 末尾):
- 取 `get_watched_tickers()`
- 過濾出台股 ticker(`to_finmind_id` 非 None)
- 對每個 ticker 呼叫 `fetch_stock_chip(ticker)` + `fetch_stock_per(ticker)`
- 各 fetcher 自己的觸發整合會處理警示

> ⚠️ 設計變更:Phase 1+2 個股 fetcher 原為 lazy(個股頁打開才拉)。Phase 4 加 scheduler 主動拉,變成「lazy + scheduled 雙模式」。lazy 路徑保留(讓使用者打開冷門股 / 非 watchlist ticker 仍能立即看到資料);scheduler 確保 watchlist 上有警示的 ticker 每天有最新資料 → 警示能可靠觸發。

## API

| Endpoint | 變動 |
|---|---|
| `POST /api/alerts` | `AlertRequest` 加 `indicator_key: str | None`、`window_n: int | None`;`condition` 接受 4 值;`target_type` 接受 3 值 |
| `GET /api/alerts` | response 多 `indicator_key`、`window_n` 欄(沿用 row → dict 模式自然帶過) |
| `DELETE / PATCH /api/alerts/{id}` | 不變 |

### 新增驗證

`POST /api/alerts` 在 app.py:
- `target_type=stock_indicator` 時:
  - `indicator_key` 必填,且 ∈ {per, pbr, dividend_yield, foreign_net, trust_net, dealer_net, margin_balance, short_balance}
  - `target` 必須是台股 ticker(`.TW` / `.TWO`)
- `condition` 是 streak_* 時:`window_n` 必填,2 ≤ window_n ≤ 30
- 既有 `target_type=indicator` 規則:`target` 須在 `INDICATOR_NAMES`(沿用)
- 既有 `target_type=stock` 規則:`target` upper-case 即可(沿用)

## UI(`index.html` alert form 擴展)

既有表單 4 個欄位:`目標類型 / 目標 / 條件 / 門檻`。alert list 顯示已觸發 / 未觸發狀態。

### 表單變動

- 「目標類型」`<select id="alert-target-type">` 加 option `stock_indicator`「個股指標」
- 「目標」欄位 — 動態切換:
  - `target_type=indicator`:既有 indicator key 下拉
  - `target_type=stock`:沿用 ticker 文字輸入(既有)
  - `target_type=stock_indicator`:**雙欄** — ticker 文字輸入 + indicator_key 下拉(8 選 1,中文 label 對應)
- 「條件」`<select id="alert-condition">` 加 2 個 options:`streak_above`「連 N 日突破」、`streak_below`「連 N 日跌破」
- 條件選 streak_* 後,顯示新欄位 `window_n`「N 日」(數字輸入,預設 5,範圍 2-30)
- 提交時組合 `AlertRequest` payload(includes indicator_key / window_n 當且僅當需要)

### Alert list 顯示新格式

JS `alertTargetLabel(a)` 擴展:
- `stock_indicator`:`{ticker} {INDICATOR_LABEL_ZH[indicator_key]}`(例:`2330.TW PER`)
- 既有 `indicator` / `stock`:沿用

`alertConditionLabel(a)` 新函式:
- `above`/`below`:既有顯示「突破」/「跌破」(沿用)
- `streak_above`:`連 ${window_n} 日突破`
- `streak_below`:`連 ${window_n} 日跌破`

新增 8 個 stock indicator 中文 label map:
```js
const STOCK_INDICATOR_LABELS = {
  per: 'PER', pbr: 'PBR', dividend_yield: '殖利率',
  foreign_net: '外資淨買', trust_net: '投信淨買', dealer_net: '自營淨買',
  margin_balance: '融資餘額', short_balance: '融券餘額',
};
```

## 實作 task 切割

每個 task 獨立 commit、可獨立 deploy:

| # | Task | 範圍 | 規模 |
|---|---|---|---|
| **T1** | DB schema migration + db helpers + alerts engine 純函式(`_check_streak`、`_get_stock_indicator_history`)+ 對應 unit test | 資料層 + engine 純函式 | 小 |
| **T2** | alerts.py routing 重構:接受 indicator_key kwarg、streak / stock_indicator 路徑 + Discord 訊息 format 適應 | 後端 engine | 中 |
| **T3** | Fetcher 觸發整合:chip_stock + fundamentals_stock(per)寫入後呼叫 check_alerts(只在最新日)| 觸發整合 | 小 |
| **T4** | Scheduler:`fetch_watchlist_stock_daily` 函式 + 18:30 TST cron job | 排程 | 小 |
| **T5** | API:`POST /api/alerts` 擴展驗證、AlertRequest model 加欄、response 自然擴展 | API | 小 |
| **T6** | UI:alert form 動態欄位、4 種 condition、3 種 target_type、列表顯示新格式 | 前端 | 中 |
| **T7** | Deploy + 驗證(設個 alert 試 Discord 收到)| 部署 + e2e | 小 |

T1 → T2 → T3 順序固定。T4 / T5 / T6 可平行(都依賴 T2 的 routing)。T7 最後。

整體規模約 Phase 1 等級(7 個 task,但每個都小;比 Phase 2 的 9 個 UI-heavy task 小)。

## 風險與緩解

| 風險 | 緩解 |
|---|---|
| Scheduler 拉 watchlist 時 quota 暴增 | 每 ticker 2 個 FinMind requests,100 ticker = 200/day,FinMind quota 600/hr 內 |
| 個股 fetcher backfill / migration 寫入歷史日期觸發 alert spam | check_alerts 只在「fetcher 寫入的 max date == today」才呼叫 |
| Streak 遇歷史資料節假日缺漏 | `_get_stock_indicator_history` 取「最近 N 個有資料的點」(skip 節假日),不要求連續日曆日 |
| FinMind 把 `stock_per_daily` 等 dataset 升 Sponsor | Phase 4 不增加新 FinMind dataset(都是 Phase 1+2 已用的),風險已分散 |
| Watchlist 為空時 scheduler job 空跑 | `fetch_watchlist_stock_daily` 早 return 即可 |
| 既有 alert(沒 indicator_key / window_n)在 routing 時碰到 None 欄位 | DB ALTER 加欄預設 NULL,既有 alert 條件自然走「indicator + above/below」舊路徑;routing 在 streak / stock_indicator 分支才讀新欄 |

## 後續階段(backlog)

- 月/季指標警示(月營收 YoY、EPS、毛利率、配發率)
- 跨指標複合條件(AND / OR)
- 5y 百分位 / YoY 異常型警示
- alert 觸發後的 silence window(避免短時間重複觸發)
