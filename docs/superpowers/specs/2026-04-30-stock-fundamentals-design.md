# Stock Dashboard 基本面 Phase 2 設計

**日期**: 2026-04-30
**狀態**: 已批准,待產實作計畫
**前置**: Phase 1 籌碼面 (`docs/superpowers/specs/2026-04-30-stock-chip-mvp-design.md`) 已完成上線

## 背景

Phase 1 籌碼面已上線,接下來補基本面 — 這是個股投資決策的核心面向(估值、營收、財報、股利)。FinMind 的基本面 dataset 全部免費(個股查詢免 quota 升級),非常適合直接接入。

設計目標延續既有風格:lazy fetch + DB cache、卡片式 UI、API 層做衍生計算、4 個 dataset 分散到獨立表/endpoint/card。但因財報三表(損益、資產負債、現金流量)各自欄位繁雜,每張 card 採完整深度(c 版),並把財報拆為 3 個獨立 cards,共 **6 張 cards**。

## 範圍

### In scope

6 個 FinMind dataset(全部免費 with `data_id`):

| Dataset | 內容 | 更新頻率 |
|---|---|---|
| `TaiwanStockPER` | PER / PBR / 殖利率 | 每日 |
| `TaiwanStockMonthRevenue` | 月營收 | 每月 |
| `TaiwanStockFinancialStatements` | 損益表(綜合損益)| 每季 |
| `TaiwanStockBalanceSheet` | 資產負債表 | 每季 |
| `TaiwanStockCashFlowsStatement` | 現金流量表 | 每季 |
| `TaiwanStockDividend` | 股利政策 | 不定期 |

行為:抓 → 存 → API 衍生計算 → UI 顯示。每張 card 完整深度(歷史走勢 chart、衍生指標、年度匯總等)。

### Out of scope

- **警示規則層**:沿用 Phase 1 決定,警示 engine / UI / Discord 訊息格式延後到獨立 phase
- 個股新聞、研究報告類 dataset
- 整體市場版本(基本面 dataset 都是個股級)
- Phase 3 總體面(央行利率、美國國債殖利率)

## UI 設計(`stock.html`)

6 張獨立 cards,並列在現有「籌碼面」card 之後。順序:估值 → 營收 → 損益 → 資產負債 → 現金流 → 股利。每張 card 預設 `display:none`,只在 `.TW`/`.TWO` ticker 顯示,各自 lazy fetch。fetch 失敗各自 graceful fail,不影響其他 card。

| Card | 內容(c 版完整深度) |
|---|---|
| **估值快照** | 最新 PER/PBR/殖利率 stat row(含「5 年區間百分位」標示);近 5 年 PER/PBR/殖利率 3 條走勢 chart |
| **月營收** | 最新月營收 + YoY%;近 36 個月 bar chart(YoY 染色)+ 12MA 疊加 line;YTD 累計 vs 去年同期 stat block |
| **損益表** | 近 12 季表(EPS / 營收 / 毛利 / 營業利益 / 稅後淨利 / 毛利率 % / 營益率 % / 淨利率 %)+ EPS 季度趨勢 line chart + TTM 年度匯總 stat block(最近 4 季合計 vs 前 4 季合計) |
| **資產負債表** | 近 12 季表(總資產 / 流動資產 / 現金 / 總負債 / 流動負債 / 長期負債 / 股東權益)+ 比率(流動比 / 速動比 / 負債比 / 權益比)+ 總資產 vs 股東權益 趨勢 chart |
| **現金流量表** | 近 12 季表(營業 CF / 投資 CF / 融資 CF / 自由現金流 = 營業 CF + 投資 CF)+ 三大現金流 stacked bar + 自由現金流 line chart |
| **股利歷史** | 近 10 年表(每西元年合計:現金股利 = 該年所有季度現金股利 sum / 股票股利同 / 殖利率 / 配發率 / 最近一次除權息日)+ 歷年現金 / 股票股利 stacked bar chart + 平均殖利率 / 平均配發率 stat block |

## Backend

### Fetcher

單一 `fetchers/fundamentals_stock.py` 模組(類似 `chip_stock.py` 的「個股 lazy fetch」模式),包含:

```
to_finmind_id()           # 沿用既有 helper 邏輯
_request(dataset, ...)     # 共用 FinMind v4 GET 包裝,帶 Bearer token
parse_per_rows()
parse_revenue_rows()
parse_financial_rows()    # 三表共用 long-format parser(差別只在 report_type)
parse_dividend_rows()

fetch_stock_per(ticker, lookback_days=1825)        # 5 年
fetch_stock_revenue(ticker, months=36)             # 3 年
fetch_stock_financial(ticker, report_type, quarters=12)
                          # report_type ∈ {'income', 'balance', 'cash_flow'}
                          # 對應 FinMind 三個 dataset
fetch_stock_dividend(ticker, years=10)             # 10 年
```

每個 fetcher 採 lazy fetch + DB cache 模式:看 DB 最新日期/月份/季度 → 過期才打 FinMind 拉 delta → 寫入 DB。失敗 log + return False,不擋住其他 card。

### DB(4 張新表)

```sql
CREATE TABLE stock_per_daily (
    ticker         TEXT NOT NULL,
    date           TEXT NOT NULL,
    per            REAL,
    pbr            REAL,
    dividend_yield REAL,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX idx_per_ticker_date ON stock_per_daily(ticker, date);

CREATE TABLE stock_revenue_monthly (
    ticker         TEXT    NOT NULL,
    year           INTEGER NOT NULL,
    month          INTEGER NOT NULL,
    revenue        REAL,                 -- 元
    announced_date TEXT,
    PRIMARY KEY (ticker, year, month)
);
CREATE INDEX idx_revenue_ticker_ym ON stock_revenue_monthly(ticker, year, month);

CREATE TABLE stock_financial_quarterly (
    ticker      TEXT NOT NULL,
    date        TEXT NOT NULL,           -- 季結算日 e.g. 2026-03-31
    report_type TEXT NOT NULL,           -- 'income' | 'balance' | 'cash_flow'
    type        TEXT NOT NULL,           -- 各表內細部指標,e.g. 'EPS', 'CashAndCashEquivalents'
    value       REAL,
    PRIMARY KEY (ticker, date, report_type, type)
);
CREATE INDEX idx_financial_ticker_date ON stock_financial_quarterly(ticker, date, report_type);

CREATE TABLE stock_dividend_history (
    ticker             TEXT NOT NULL,
    year               TEXT NOT NULL,    -- e.g. "114年第3季"
    cash_dividend      REAL,
    stock_dividend     REAL,
    cash_ex_date       TEXT,
    cash_payment_date  TEXT,
    announcement_date  TEXT,
    PRIMARY KEY (ticker, year)
);
CREATE INDEX idx_dividend_ticker ON stock_dividend_history(ticker);
```

**設計重點**:`stock_financial_quarterly` 用 `report_type` 欄區分三表 — 因為三表的 `type` 命名有衝突(例:`AccountsPayable` 在資產負債表是「應付帳款餘額」,在現金流量表是「應付帳款變動」)。長格式 + 三表合一表方便共用 query/parser/upsert,只是 PK 多一個欄位。

### Backend 衍生計算(API 層)

| 資料 | 衍生指標 |
|---|---|
| 估值 | 5 年 PER 百分位、5 年 PER/PBR/殖利率 min/max/avg |
| 月營收 | YoY%、12 個月移動平均、YTD 累計 vs 去年同期 |
| 損益 | 毛利率 / 營益率 / 淨利率、季度 EPS YoY/QoQ、年度匯總(本年 vs 去年) |
| 資產負債 | 流動比 = 流動資產/流動負債、速動比、負債比、權益比 |
| 現金流量 | 自由現金流 = 營業 CF + 投資 CF、三大 CF 占比 |
| 股利 | 該年合計(現金/股票股利分別 sum across 該西元年所有季度);殖利率 = 該年現金股利合計 ÷ 該年期間平均收盤價(從 `stock_snapshots` 取該年所有交易日收盤價 avg,缺資料 fallback 用最近一次除權息日前一日收盤價);配發率 = 該年現金股利合計 ÷ 該年 EPS 合計(EPS 從 `stock_financial_quarterly` 取 `report_type='income'` & `type='EPS'` 的 4 季 sum);平均殖利率/配發率 = 近 10 年算數平均 |

衍生指標**不存進 DB**(原始資料保持單一真相源),由 API 層在每次請求時計算。

## API endpoints

| Endpoint | 參數 | 回應重點 |
|---|---|---|
| `GET /api/stocks/{ticker}/valuation` | `years=5` | `{ok, as_of, latest:{per,pbr,dividend_yield,per_percentile_5y}, range_5y:{...}, rows:[...]}` |
| `GET /api/stocks/{ticker}/revenue` | `months=36` | `{ok, latest:{...,yoy_pct}, ytd:{accumulated, last_year_accumulated, yoy_pct}, rows:[...含 ma12]}` |
| `GET /api/stocks/{ticker}/financial` | `statement=income\|balance\|cashflow`, `quarters=12` | 視 statement 不同欄位 + 衍生比率 + (僅 income)`annual_summary` |
| `GET /api/stocks/{ticker}/dividend` | `years=10` | `{ok, summary:{avg_dividend_yield, avg_payout_ratio}, rows:[...]}` |

`/financial` 一個 endpoint 帶 `statement` query param 三選一,後端共用查詢/計算骨架,只在 statement-specific 衍生計算分支處理。

## 實作 task 切割

每個 task 獨立 commit,可獨立 deploy:

| # | Task | 範圍 | 風險 |
|---|---|---|---|
| **T1** | DB 4 張新表 + db helpers(`save_*`/`get_*_range`/`get_latest_*_date`)+ `fundamentals_stock.py` 骨架(`to_finmind_id`、`_request`、4 個 parse 函式)| 資料層 | 低 |
| **T2** | 4 個 fetcher 函式 + 4 個 API endpoint + 衍生計算(per 百分位、YoY、財報比率、配發率等)| 後端 + API,衍生計算密度高 | 中 |
| **T3** | UI:估值快照 card(stat row + 百分位 + 5 年 3 條走勢 chart)| 前端 + chart | 中 |
| **T4** | UI:月營收 card(36M bar 染色 + 12MA + YTD)| 前端 + chart + YTD | 中 |
| **T5** | UI:損益表 card(12 季表 + EPS chart + 年度匯總)| 前端 + 表 + chart + 比率 | 中 |
| **T6** | UI:資產負債表 card(12 季表 + 比率 + 總資產 vs 股東權益 chart)| 前端 + 表 + chart | 中 |
| **T7** | UI:現金流量表 card(12 季表 + stacked bar + FCF line)| 前端 + 表 + stacked + FCF | 中 |
| **T8** | UI:股利歷史 card(10 年表 + stacked bar + 平均 stat)| 前端 + 表 + chart | 中 |
| **T9** | Deploy + 驗證 | 部署 + 線上 curl 驗證 + 手動 UI 抽看 | 低 |

T1 → T2 順序固定。T3-T8 可平行(都依賴 T2 的 endpoint)。T9 在所有完成後跑。

整體規模約 Phase 1 的 **2 倍**(因為 6 張 c 版深度 cards、3 個財報 statement 各自展開)。

## 風險與緩解

| 風險 | 緩解 |
|---|---|
| FinMind dataset 改成 Sponsor 等級(像券商分點)| 仿券商分點下架模式 — fetcher 短路、UI 隱藏 card、保留程式碼 |
| FinMind 600/hr quota:第一次開個股頁要打 6 次 FinMind | 每張 card 各自 lazy fetch,首次打 6 次後續零次,實際 quota 壓力低 |
| 三表 type 命名衝突 | DB 加 `report_type` 欄區分(已採) |
| 財報資料 long-format → wide-format 轉換錯位 | parser 在轉換時用 type 名 whitelisted 對應到目標欄位,缺欄回 None |
| 衍生計算邊界(EPS 為 0、營收為 0 時的比率)| API 層加防呆:除數為 0 → 回 None,前端顯示 `—` |
| 配發率「該年 EPS」對應跨年股利的歸屬 | 用「股利 year 對應的當年 EPS 加總」,若 EPS 為 0 或無資料 → 回 None |

## 後續階段

- **Phase 3 總體面**:央行利率(`InterestRate`)、美國國債殖利率(`GovernmentBondsYield`)— Phase 2 完成後啟動
- **警示規則層**:獨立 spec,等基本面/總體面累積足夠歷史資料後再做
- **資產負債表 / 現金流量表的更多衍生指標**(例 ROE、ROA、自由現金流殖利率)— 視使用後反饋再加
