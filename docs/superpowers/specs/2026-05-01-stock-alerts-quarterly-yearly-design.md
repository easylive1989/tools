# Stock Dashboard 警示季/年指標 設計

**日期**: 2026-05-01
**狀態**: 已批准,待產實作計畫
**前置**: Phase 4 + P4 follow-up + 警示深化 MVP(monthly YoY + 5y percentile)已上線。本案延伸 YoY 警示到季/年指標。

## 背景

警示深化 MVP 加了 monthly YoY(對 revenue 一個 indicator)。本案繼續擴展到季/年粒度,涵蓋基本面投資者最常看的訊號:EPS YoY、季營收 YoY、營業現金流 YoY、年現金股利 YoY。

衍生比率(margin / payout ratio)留 backlog,本案只做 raw 數值 YoY。

## 範圍

### In scope:7 個新 indicator_key

用 `q_` / `y_` prefix 避免跟 monthly `revenue` 衝突:

| Indicator Key | 來源(report_type, type)/ 表 | 解讀 |
|---|---|---|
| `q_eps` | `stock_financial_quarterly` (income, EPS) | 季 EPS |
| `q_revenue` | (income, Revenue) | 季營收 |
| `q_operating_income` | (income, OperatingIncome) | 季營業利益 |
| `q_net_income` | (income, IncomeAfterTaxes) | 季稅後淨利 |
| `q_operating_cf` | (cash_flow, CashFlowsFromOperatingActivities) | 季營業 CF |
| `y_cash_dividend` | `stock_dividend_history` aggregate by 西元年 | 年現金股利合計 |
| `y_stock_dividend` | 同 | 年股票股利合計 |

支援 `yoy_above` / `yoy_below` 兩個 condition(MVP 既有)。

### Out of scope

- 衍生比率 YoY(毛利率、淨利率、配發率)
- 連 N 季/年 YoY 警示
- balance sheet 指標警示(總資產、負債等較少看 YoY)
- QoQ 警示

## DB schema

**不需 ALTER**。沿用 P4 + MVP schema(condition / indicator_key 都是字串)。

## Backend

### `alerts.py` 新增

#### Constants

```python
QUARTERLY_INDICATOR_TYPES = {
    "q_eps":              ("income",    "EPS"),
    "q_revenue":          ("income",    "Revenue"),
    "q_operating_income": ("income",    "OperatingIncome"),
    "q_net_income":       ("income",    "IncomeAfterTaxes"),
    "q_operating_cf":     ("cash_flow", "CashFlowsFromOperatingActivities"),
}
YEARLY_INDICATOR_KEYS = {"y_cash_dividend", "y_stock_dividend"}
```

#### Helpers

```python
def _get_stock_quarterly_yoy(ticker, indicator_key) -> float | None
    # 1. lookup (report_type, type) from QUARTERLY_INDICATOR_TYPES
    # 2. get_financial_quarterly_range(ticker, report_type, since=今年-3年-01-01)
    # 3. filter rows where r["type"] == type_name AND r["value"] is not None
    # 4. sort by date,取 latest
    # 5. compute target_prev_date = latest_date.year-1 + 同 month-day(季結算日)
    # 6. find prev value;缺則 None;否則 round((cur-prev)/prev*100, 2)


def _get_stock_yearly_yoy(ticker, indicator_key) -> float | None
    # 1. get_dividend_history(ticker)
    # 2. parse "114年第N季" → ROC year+1911 = 西元年
    # 3. aggregate by 西元年(cash_dividend or stock_dividend by 視 indicator_key)
    # 4. 找最新西元年 vs 去年,缺則 None
```

#### check_alerts routing 擴展

`yoy_above/below` 分支從「只認 revenue」改為 multi-granularity:

```python
elif cond in ("yoy_above", "yoy_below"):
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
    triggered = ...
```

### Fetcher trigger 整合

- `fetch_stock_financial(ticker, report_type)` 寫入後:
  - 比對 `new_max_date = max(r["date"] for r in rows)` vs pre-fetch `latest = get_latest_financial_date(ticker, report_type)`
  - 若新季,對該 report_type 對應的 quarterly indicator 觸發 check_alerts:
    - `report_type == "income"` → q_eps / q_revenue / q_operating_income / q_net_income
    - `report_type == "cash_flow"` → q_operating_cf
    - `report_type == "balance"` → 無觸發(範圍外)
- `fetch_stock_dividend(ticker)` 寫入後:
  - aggregate 出最新西元年 vs pre-fetch 最新年(從 `get_dividend_history` 算)
  - 若新年,對 y_cash_dividend、y_stock_dividend 觸發

### Scheduler 擴充

`fetch_watchlist_stock_daily` 加 3 個 fetcher 呼叫:

```python
fetch_stock_chip(ticker)
fetch_stock_per(ticker)
fetch_stock_revenue(ticker)
fetch_stock_financial(ticker, "income")      # 新
fetch_stock_financial(ticker, "cash_flow")   # 新
fetch_stock_dividend(ticker)                  # 新
```

(balance 不拉,因為範圍內無 balance indicator,且 quota 不必要消耗。實際上 watchlist 100 ticker × 6 fetcher × lazy guard ≈ 季/年 90% 為 cache hit,quota 充裕。)

## API(`app.py`)

### 擴展常數

```python
STOCK_QUARTERLY_INDICATOR_KEYS = {
    "q_eps", "q_revenue", "q_operating_income",
    "q_net_income", "q_operating_cf",
}
STOCK_YEARLY_INDICATOR_KEYS = {"y_cash_dividend", "y_stock_dividend"}

# YoY 相容範圍 = monthly + quarterly + yearly
STOCK_YOY_COMPATIBLE_KEYS = (
    STOCK_MONTHLY_INDICATOR_KEYS    # {"revenue"}
    | STOCK_QUARTERLY_INDICATOR_KEYS
    | STOCK_YEARLY_INDICATOR_KEYS
)
STOCK_INDICATOR_KEYS = STOCK_DAILY_INDICATOR_KEYS | STOCK_YOY_COMPATIBLE_KEYS
```

### 交叉驗證更新

```python
if is_yoy and req.indicator_key not in STOCK_YOY_COMPATIBLE_KEYS:
    raise HTTPException(400, "yoy condition requires monthly/quarterly/yearly indicator")
```

(原本驗證:`indicator_key not in STOCK_MONTHLY_INDICATOR_KEYS` → 改為 `not in STOCK_YOY_COMPATIBLE_KEYS`。)

`percentile_*` 仍只支援 daily,不變。

## UI

`index.html` alert form 的 `<select id="alert-indicator-key">` 加 7 個 options(放在 monthly `revenue` 之後):

```html
<option value="q_eps">季 EPS</option>
<option value="q_revenue">季營收</option>
<option value="q_operating_income">季營業利益</option>
<option value="q_net_income">季稅後淨利</option>
<option value="q_operating_cf">季營業 CF</option>
<option value="y_cash_dividend">年現金股利</option>
<option value="y_stock_dividend">年股票股利</option>
```

`STOCK_INDICATOR_LABELS` 對應加 7 個 labels。

## Tests

- `test_alerts.py`:
  - `test_get_stock_quarterly_yoy_*`(positive / negative / missing prev / no data / wrong indicator_key)
  - `test_get_stock_yearly_yoy_*`(positive / no data / single year / negative)
  - `test_check_alerts_yoy_quarterly_eps_triggers`
  - `test_check_alerts_yoy_yearly_dividend_triggers`
- `test_api.py`:
  - `test_post_alert_yoy_with_q_eps`(成功)
  - `test_post_alert_yoy_with_y_cash_dividend`(成功)
  - `test_post_alert_yoy_with_unknown_q_key_400`
  - `test_post_alert_percentile_with_q_eps_400`(percentile 仍只 daily)

## Tasks

| # | Task | 範圍 | 規模 |
|---|---|---|---|
| **T1** | 2 個新 helpers + 純函式測試 | engine | 小-中 |
| **T2** | check_alerts yoy routing 擴展 + routing 測試 | engine | 小 |
| **T3** | Fetcher trigger(financial income+cashflow + dividend)| fetcher | 中 |
| **T4** | Scheduler watchlist 加 3 個拉取 | scheduler | 小 |
| **T5** | API 驗證擴展 + API 測試 | API | 小 |
| **T6** | UI 加 7 個 indicator_key option + label | 前端 | 小 |
| **T7** | Deploy + e2e 驗證(q_eps + y_cash_dividend 各 1 alert)| 部署 | 小 |

7 task。T1 → T2 順序固定。T3 / T4 / T5 / T6 可平行。T7 最後。

## 風險

| 風險 | 緩解 |
|---|---|
| 季資料缺去年同季 | `_get_stock_quarterly_yoy` 找不到 prev 回 None |
| 年資料缺去年 | 同上對 yearly |
| Watchlist scheduler 從 3 → 6 fetcher × 100 ticker = 600 req/day,FinMind 600/hr 邊緣 | fetcher lazy guard 確保 cache hit 不打 API;季/年資料變動極少,實際 ~10% 才打 |
| FinMind type 字串改名(`IncomeAfterTaxes` 等)| QUARTERLY_INDICATOR_TYPES 集中管理,改一處即可 |
| 季 fetcher 寫入時若 batch 含舊+新季,觸發過多 | 用「new_max_date > pre-fetch latest」guard 只在實際拉到新季時觸發 |

## 後續(backlog)

- 衍生比率 YoY(毛利率、淨利率、配發率)
- balance sheet YoY(總資產、流動比)
- 連 N 季/年 YoY 警示
- 跨指標複合條件
