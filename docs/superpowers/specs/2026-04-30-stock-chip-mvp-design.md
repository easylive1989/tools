# Stock Dashboard 籌碼面 MVP 設計

**日期**: 2026-04-30
**狀態**: 已批准,待產實作計畫

## 背景

Stock Dashboard 目前資料源以 yfinance 為主,加上 TWSE CSV(`margin.py`,有 IP 封鎖風險)、CNN F&G、自家 NDC fetcher。

FinMind 經盤點後免費可用 52 個 dataset(完全免費 32 個 + 個股查詢免費 / 全市場批次需付費 20 個)。本案先補「籌碼面」,屬於日更新、與既有資料整合度高、可直接擴充現有 dashboard 的內容。

券商分點功能(`TaiwanStockTradingDailyReport`)因 FinMind 改為 Sponsor 限定,已於 2026-04-30 commits `fb44ee0`、`cbd5acf` 停用,程式碼保留待未來重啟,不在本案範圍。

## 範圍

### In scope

新增 / 替換以下 4 個 FinMind dataset(全部免費):

| Dataset | 用途 | 層級 |
|---|---|---|
| `TaiwanStockTotalMarginPurchaseShortSale` | 整體融資融券 | 替換現有 `margin.py` |
| `TaiwanStockTotalInstitutionalInvestors` | 整體三大法人 | 全新 |
| `TaiwanStockMarginPurchaseShortSale` | 個股融資融券 | 全新 |
| `TaiwanStockInstitutionalInvestorsBuySell` | 個股三大法人 | 全新 |

行為層面只到「抓 → 存 → 顯示」。

### Out of scope

- **警示規則層**:`check_alerts` 在新 indicator save 時會呼叫一次,但不擴充 alert engine、不新增 alert 規則型別、不改 alert UI。第二階段獨立 task。
- 其他三大資料面:基本面(PER/PBR、月營收、財報、股利)、總體面(央行利率、美國國債殖利率)。後續批次再做。
- 重啟券商分點功能。

## 設計

### Backend

#### Fetchers

```
backend/fetchers/
├── chip_total.py    (新增) — 整體融資融券 + 整體三大法人
├── chip_stock.py    (新增) — 個股籌碼,lazy fetch + DB cache
├── margin.py        (刪除) — 連同 cloudscraper 依賴
└── (其他既有 fetchers 不動)
```

- `chip_total.py`:每日 18:00 cron 觸發,呼叫 FinMind 兩個 dataset(不帶 `data_id`,免費 quota 內 2 requests/day),寫入 `indicator_snapshots`。
- `chip_stock.py`:lazy fetch + DB cache,複用 `broker.py` 同模式 — 使用者打 endpoint 時才拉,DB 已有最新就略過,缺資料才補 delta。

#### DB schema

`indicator_snapshots`(現有通用表)新增 indicator keys:

| Key | 說明 | 單位 |
|---|---|---|
| `margin_balance` | 整體融資餘額 | 億元 |
| `short_balance` | 整體融券餘額 | 仟股 |
| `margin_short_ratio` | 融資使用率 | % |
| `total_foreign_net` | 整體外資淨買超 | 億元 |
| `total_trust_net` | 整體投信淨買超 | 億元 |
| `total_dealer_net` | 整體自營淨買超 | 億元 |

(現有 `margin` key 在 T1 改名為 `margin_balance`,既有歷史資料保留 — 詳見 T1。)

新表 `stock_chip_daily`:

```sql
CREATE TABLE IF NOT EXISTS stock_chip_daily (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    foreign_buy REAL,
    foreign_sell REAL,
    trust_buy REAL,
    trust_sell REAL,
    dealer_buy REAL,
    dealer_sell REAL,
    margin_balance REAL,    -- 融資餘額(張)
    short_balance REAL,     -- 融券餘額(張)
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_chip_ticker_date
  ON stock_chip_daily(ticker, date);
```

#### Scheduler

`scheduler.py` 變動:

```diff
- scheduler.add_job(fetch_margin, CronTrigger(hour=18, minute=0, ...), id="margin", ...)
+ scheduler.add_job(fetch_chip_total, CronTrigger(hour=18, minute=0, ...), id="chip_total", ...)
```

個股版不掛 scheduler(lazy fetch 模式)。

#### Backfill

- **整體層級**:`chip_total.py` 第一次執行時偵測 DB 中對應 indicator key 為空,自動拉 1 年歷史寫入(FinMind 整體不帶 `data_id` 一次取一段時間,1 個 request 即可)。不需要額外手動指令。
- **個股層級**:`chip_stock.py` lazy fetch — 首次拉 60 個交易日寫入 `stock_chip_daily`,之後僅補 delta(從 DB 最新日期 +1 抓到今天)。前端預設只顯示最近 20 個交易日,DB 多存的 40 天作為 cache buffer。

### API

| Endpoint | 變動 | 說明 |
|---|---|---|
| `/api/dashboard` | 改 | `INDICATOR_NAMES` 加上 6 個新 key,自動包含於回應 |
| `/api/history/{indicator}` | 不改 | 自動支援新 keys(只看 indicator name) |
| `/api/stocks/{ticker}/chip?days=20` | **新增** | 個股籌碼,lazy fetch + cache。回應 schema 參照 `/brokers` 慣例 |

DB 存原始 `*_buy` / `*_sell`(便於未來計算成交比重、賣壓等衍生指標),API 層計算 `*_net = buy - sell` 回傳給前端,前端不接觸原始 buy/sell。

`/api/stocks/{ticker}/chip` 回應 sketch:

```json
{
  "ticker": "2330.TW",
  "days": 20,
  "as_of": "2026-04-29",
  "ok": true,
  "rows": [
    {
      "date": "2026-04-29",
      "foreign_net": 12345,
      "trust_net": -678,
      "dealer_net": 90,
      "margin_balance": 45678,
      "short_balance": 1234
    }
  ]
}
```

### Frontend

#### `index.html`(總覽 dashboard)

- 既有的 `margin` 卡片改名「融資餘額」(資料 key 從 `margin` 換為 `margin_balance`)
- 新增 5 個卡片:融券餘額、融資使用率、外資淨買超、投信淨買超、自營淨買超
- 點任一卡片進歷史圖,沿用既有 `history` 模式

#### `stock.html`(個股詳細頁)

- 在現有(已停用)券商卡下方新增「籌碼面」區塊
- 區塊內容:
  - 「三大法人」表(近 20 個交易日,每列:date、外資淨、投信淨、自營淨)
  - 「融資融券」表(近 20 個交易日,每列:date、融資餘額、融券餘額)
- 表格樣式沿用現有設計風格(`.broker-table` 風格類似)
- 載入流程:`stock.html` 載入時呼叫 `loadChip()`,首次會 lazy fetch ~10 秒,之後從 DB cache

## 實作 task 切割

每個 task 獨立 commit、可獨立 deploy:

| # | Task | 範圍 | 風險 |
|---|---|---|---|
| **T1** | 替換 margin.py(整體融資融券) | 新增 `chip_total.py` 抓整體融資融券,寫入 `margin_balance` / `short_balance` / `margin_short_ratio` 三個 indicator key,刪除 `margin.py`,scheduler 換 job,`INDICATOR_NAMES` 加 3 個新 key,既有 `margin` 卡片 key 改為 `margin_balance` 並新增「融券餘額」「融資使用率」2 個卡片 | 中 — 替換既有功能,要做歷史資料遷移 |
| **T2** | 整體三大法人 | 在 `chip_total.py` 加第二個 dataset 抓取,新增 `total_foreign_net` / `total_trust_net` / `total_dealer_net` 三個 indicator key,`index.html` 加 3 個卡片 | 低 — 純新增 |
| **T3** | 個股籌碼 backend | 新增 `chip_stock.py` + `stock_chip_daily` 表 + db.py 函式 + `/api/stocks/{ticker}/chip` endpoint | 中 — 新表 + lazy fetch 邏輯 |
| **T4** | 個股籌碼 UI | `stock.html` 加籌碼區塊 + JS 載入邏輯 | 低 — 前端 |
| **T5** | 部署 + backfill | commit/push 觸發部署,整體歷史 1 年 backfill | 低 — 部署驗證 |

T1 → T2 順序固定(T1 先替換 margin,T2 才能在同一 fetcher 加東西)。
T3 ↔ T4 可並行,但建議 T3 先做才能驗證 endpoint。
T5 可在 T1 / T2 / T3+T4 任一完成時各自部署。

## 風險與緩解

| 風險 | 緩解 |
|---|---|
| 既有 `margin` 歷史資料(`indicator_snapshots` 中)被 T1 改名打斷 | T1 一次性 SQL `UPDATE name='margin_balance' WHERE name='margin'`,保留歷史 |
| FinMind quota 600/hr,個股 lazy fetch 高流量時可能爆 | 第一階段沒警示,觸發頻率低(=user 點開頁面),60 days × N 開頁,實際請求量遠低於 600/hr |
| FinMind 未來把「整體三大法人 / 融資融券」也改 Sponsor 等級 | 與券商分點下架同模式處理 — fetcher 短路、UI 隱藏卡片、保留程式碼 |
| FinMind 欄位 schema 變動 | 在 fetcher 做 defensive parsing(missing key 跳過該筆),失敗不擋住其他指標 |

## 後續階段

- **第二階段(警示規則)**:擴充 alert engine 支援「indicator 數值警示」(例:外資淨買超 > X 億)、「indicator 連 N 日警示」(例:融資使用率連 5 日 > 90%)、「stock chip 連 N 日警示」(例:某 ticker 外資連 N 日買超)。需新 alert schema + UI + Discord 通知格式。
- **第三階段(基本面)**:PER/PBR、月營收、財報三表、股利。
- **第四階段(總體面)**:央行利率、美國國債殖利率。
