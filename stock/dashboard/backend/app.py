import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import (
    init_db,
    get_latest_indicator,
    get_indicator_history,
    get_watched_tickers,
    get_latest_stock,
    add_watched_ticker,
    remove_watched_ticker,
    list_alerts,
    add_alert,
    delete_alert,
    set_alert_enabled,
    get_broker_daily_range,
    get_chip_daily_range,
    get_per_daily_range,
    get_revenue_monthly_range,
    get_financial_quarterly_range,
    get_dividend_history,
)
from fetchers.yfinance_fetcher import fetch_taiex, fetch_fx, fetch_all_stocks, fetch_stock_history
from fetchers.fear_greed import fetch_fear_greed
from fetchers.chip_total import fetch_chip_total
from fetchers.ndc import fetch_ndc
from fetchers.volume import fetch_tw_volume, fetch_us_volume
from fetchers.broker import fetch_broker_daily, to_finmind_id
from fetchers.chip_stock import fetch_stock_chip, to_finmind_id as chip_to_finmind_id
from fetchers.fundamentals_stock import (
    fetch_stock_per, fetch_stock_revenue,
    fetch_stock_financial, fetch_stock_dividend,
    to_finmind_id as fundamentals_to_finmind_id,
)

app = FastAPI(title="Stock Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://paul-learning.dev"],
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["*"],
)

RANGE_DELTAS: dict[str, timedelta] = {
    "1M": timedelta(days=30),
    "3M": timedelta(days=90),
    "6M": timedelta(days=180),
    "1Y": timedelta(days=365),
    "3Y": timedelta(days=1095),
}

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

INDICATOR_NAMES = [
    "taiex", "fx", "fear_greed",
    "margin_balance", "short_balance", "short_margin_ratio",
    "total_foreign_net", "total_trust_net", "total_dealer_net",
    "ndc", "tw_volume", "us_volume",
]


@app.on_event("startup")
def startup():
    init_db()
    try:
        from scheduler import start_scheduler
        start_scheduler()
    except ImportError:
        print("[app] scheduler not available yet")


@app.get("/api/dashboard")
def dashboard():
    result = {}
    for name in INDICATOR_NAMES:
        row = get_latest_indicator(name)
        if row:
            result[name] = {
                "value":     row["value"],
                "timestamp": row["timestamp"],
                "extra":     json.loads(row["extra_json"]) if row["extra_json"] else {},
            }
    return result


@app.get("/api/history/{indicator}")
def history(indicator: str, time_range: str = "3M"):
    if indicator not in INDICATOR_NAMES:
        raise HTTPException(status_code=404, detail="Unknown indicator")
    delta = RANGE_DELTAS.get(time_range, RANGE_DELTAS["3M"])
    since = datetime.now(timezone.utc).replace(tzinfo=None) - delta
    rows = get_indicator_history(indicator, since)
    return [{"timestamp": r["timestamp"], "value": r["value"]} for r in rows]


@app.get("/api/stocks")
def get_stocks():
    result = []
    for ticker in get_watched_tickers():
        row = get_latest_stock(ticker)
        if row:
            result.append({
                "ticker":     ticker,
                "name":       row["name"],
                "price":      row["price"],
                "change":     row["change"],
                "change_pct": row["change_pct"],
                "currency":   row["currency"],
                "timestamp":  row["timestamp"],
            })
        else:
            result.append({"ticker": ticker, "name": ticker, "price": None})
    return result


class AddStockRequest(BaseModel):
    ticker: str


@app.post("/api/stocks")
def add_stock(req: AddStockRequest):
    add_watched_ticker(req.ticker.upper())
    try:
        fetch_all_stocks()
    except Exception as e:
        print(f"[add_stock] Fetch error: {e}")
    return {"ok": True}


@app.delete("/api/stocks/{ticker}")
def delete_stock(ticker: str):
    remove_watched_ticker(ticker.upper())
    return {"ok": True}


@app.get("/api/stocks/{ticker}/brokers")
def stock_brokers(ticker: str, days: int = 20, top: int = 5):
    # 已停用：FinMind TaiwanStockTradingDailyReport 改為 Sponsor 限定 (見 README)。
    # 程式碼保留以便未來重啟功能。
    return {
        "ticker":      ticker.upper(),
        "days":        days,
        "as_of":       None,
        "ok":          False,
        "top_brokers": [],
    }


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


@app.get("/api/stocks/{ticker}/valuation")
def stock_valuation(ticker: str, years: int = 5):
    """個股估值快照:PER/PBR/殖利率最新值 + 5 年百分位 + 走勢。"""
    ticker = ticker.upper()
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if years < 1 or years > 10:
        raise HTTPException(status_code=400, detail="years must be 1..10")

    fetched = fetch_stock_per(ticker)
    since_date = (datetime.now(timezone.utc).date() - timedelta(days=years * 366)).isoformat()
    rows = get_per_daily_range(ticker, since_date)

    if not rows:
        return {"ticker": ticker, "years": years, "as_of": None, "ok": fetched,
                "latest": None, "range_5y": None, "rows": []}

    rows_sorted = sorted(rows, key=lambda r: r["date"])
    latest = rows_sorted[-1]

    def _stats(values: list[float]) -> dict:
        clean = [v for v in values if v is not None]
        if not clean:
            return {"min": None, "max": None, "avg": None}
        return {"min": min(clean), "max": max(clean),
                "avg": round(sum(clean) / len(clean), 4)}

    pers = [r["per"]            for r in rows_sorted if r["per"] is not None]
    pbrs = [r["pbr"]            for r in rows_sorted if r["pbr"] is not None]
    yds  = [r["dividend_yield"] for r in rows_sorted if r["dividend_yield"] is not None]

    if latest["per"] is not None and pers:
        below = sum(1 for v in pers if v <= latest["per"])
        per_percentile = round(below / len(pers) * 100, 2)
    else:
        per_percentile = None

    return {
        "ticker": ticker, "years": years,
        "as_of": latest["date"], "ok": True,
        "latest": {
            "per": latest["per"], "pbr": latest["pbr"],
            "dividend_yield": latest["dividend_yield"],
            "per_percentile_5y": per_percentile,
        },
        "range_5y": {"per": _stats(pers), "pbr": _stats(pbrs), "dividend_yield": _stats(yds)},
        "rows": rows_sorted,
    }


@app.get("/api/stocks/{ticker}/revenue")
def stock_revenue(ticker: str, months: int = 36):
    """個股月營收 + YoY + 12MA + YTD vs 去年同期。"""
    ticker = ticker.upper()
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if months < 1 or months > 60:
        raise HTTPException(status_code=400, detail="months must be 1..60")

    fetched = fetch_stock_revenue(ticker)

    today = datetime.now(timezone.utc).date()
    fetch_back_months = months + 14
    since_year = today.year - (fetch_back_months // 12) - 1
    since_month = ((today.month - (fetch_back_months % 12) - 1) % 12) + 1
    rows = get_revenue_monthly_range(ticker, since_year, since_month)

    if not rows:
        return {"ticker": ticker, "months": months, "ok": fetched,
                "latest": None, "ytd": None, "rows": []}

    by_ym = {(r["year"], r["month"]): r["revenue"] for r in rows}

    def _yoy(year: int, month: int) -> float | None:
        cur = by_ym.get((year, month))
        prev = by_ym.get((year - 1, month))
        if cur is None or not prev:
            return None
        return round((cur - prev) / prev * 100, 2)

    def _ma12(year: int, month: int) -> float | None:
        vals = []
        y, m = year, month
        for _ in range(12):
            v = by_ym.get((y, m))
            if v is None:
                return None
            vals.append(v)
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return round(sum(vals) / 12, 0)

    enriched = [{
        "year":    r["year"],
        "month":   r["month"],
        "revenue": r["revenue"],
        "yoy_pct": _yoy(r["year"], r["month"]),
        "ma12":    _ma12(r["year"], r["month"]),
    } for r in rows]

    enriched_sorted = sorted(enriched, key=lambda r: (r["year"], r["month"]))
    last_n = enriched_sorted[-months:]
    latest = enriched_sorted[-1]

    ytd_cur = sum(by_ym[(latest["year"], m)]
                  for m in range(1, latest["month"] + 1)
                  if (latest["year"], m) in by_ym)
    ytd_prev = sum(by_ym[(latest["year"] - 1, m)]
                   for m in range(1, latest["month"] + 1)
                   if (latest["year"] - 1, m) in by_ym)
    ytd_yoy = round((ytd_cur - ytd_prev) / ytd_prev * 100, 2) if ytd_prev else None

    return {
        "ticker": ticker, "months": months, "ok": True,
        "latest": latest,
        "ytd": {"accumulated": ytd_cur,
                "last_year_accumulated": ytd_prev,
                "yoy_pct": ytd_yoy},
        "rows": last_n,
    }


def _build_income_row(date: str, types: dict[str, float]) -> dict:
    rev   = types.get("Revenue")
    gp    = types.get("GrossProfit")
    op    = types.get("OperatingIncome")
    nit   = types.get("IncomeAfterTaxes")
    eps   = types.get("EPS")
    def _pct(num, den):
        return round(num / den * 100, 2) if num is not None and den else None
    return {
        "date":                  date,
        "revenue":               rev,
        "gross_profit":          gp,
        "operating_income":      op,
        "net_income":            nit,
        "eps":                   eps,
        "gross_margin_pct":      _pct(gp,  rev),
        "operating_margin_pct":  _pct(op,  rev),
        "net_margin_pct":        _pct(nit, rev),
    }


def _build_balance_row(date: str, types: dict[str, float]) -> dict:
    ta    = types.get("TotalAssets")
    ca    = types.get("CurrentAssets")
    cash  = types.get("CashAndCashEquivalents")
    tl    = types.get("Liabilities")
    cl    = types.get("CurrentLiabilities")
    ncl   = types.get("NoncurrentLiabilities")
    eq    = types.get("EquityAttributableToOwnersOfParent") or types.get("Equity")
    def _ratio(num, den):
        return round(num / den, 4) if num is not None and den else None
    def _pct(num, den):
        return round(num / den * 100, 2) if num is not None and den else None
    return {
        "date":                date,
        "total_assets":        ta,
        "current_assets":      ca,
        "cash":                cash,
        "total_liabilities":   tl,
        "current_liabilities": cl,
        "long_term_liabilities": ncl,
        "equity":              eq,
        "current_ratio":       _ratio(ca, cl),
        "debt_ratio_pct":      _pct(tl, ta),
        "equity_ratio_pct":    _pct(eq, ta),
    }


def _build_cashflow_row(date: str, types: dict[str, float]) -> dict:
    ocf = (types.get("CashFlowsFromOperatingActivities")
           or types.get("NetCashInflowFromOperatingActivities"))
    icf = types.get("CashProvidedByInvestingActivities")
    fcf = types.get("CashFlowsProvidedFromFinancingActivities")
    free_cf = (ocf + icf) if (ocf is not None and icf is not None) else None
    return {
        "date":           date,
        "operating_cf":   ocf,
        "investing_cf":   icf,
        "financing_cf":   fcf,
        "free_cash_flow": free_cf,
    }


_FINANCIAL_BUILDER = {
    "income":   _build_income_row,
    "balance":  _build_balance_row,
    "cashflow": _build_cashflow_row,
}


@app.get("/api/stocks/{ticker}/financial")
def stock_financial(ticker: str, statement: str = "income", quarters: int = 12):
    """個股財報(三表三選一)。statement ∈ {income, balance, cashflow}。"""
    ticker = ticker.upper()
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if statement not in _FINANCIAL_BUILDER:
        raise HTTPException(status_code=400, detail="statement must be income | balance | cashflow")
    if quarters < 1 or quarters > 20:
        raise HTTPException(status_code=400, detail="quarters must be 1..20")

    report_type = "cash_flow" if statement == "cashflow" else statement
    fetched = fetch_stock_financial(ticker, report_type)

    since_date = (datetime.now(timezone.utc).date() - timedelta(days=quarters * 100)).isoformat()
    long_rows = get_financial_quarterly_range(ticker, report_type, since_date)

    if not long_rows:
        return {"ticker": ticker, "statement": statement, "quarters": quarters,
                "ok": fetched, "rows": [], "annual_summary": None}

    by_date: dict[str, dict[str, float]] = {}
    for r in long_rows:
        by_date.setdefault(r["date"], {})[r["type"]] = r["value"]

    builder = _FINANCIAL_BUILDER[statement]
    wide_rows = sorted([builder(d, types) for d, types in by_date.items()],
                       key=lambda r: r["date"])
    last_n = wide_rows[-quarters:]

    annual_summary = None
    if statement == "income" and len(wide_rows) >= 8:
        last4 = wide_rows[-4:]
        prev4 = wide_rows[-8:-4]
        def _sum(rows: list[dict], key: str) -> float | None:
            vals = [r.get(key) for r in rows if r.get(key) is not None]
            return sum(vals) if vals else None
        cur_eps = _sum(last4, "eps");      prev_eps = _sum(prev4, "eps")
        cur_rev = _sum(last4, "revenue");  prev_rev = _sum(prev4, "revenue")
        annual_summary = {
            "current_4q":  {"eps": cur_eps,  "revenue": cur_rev},
            "previous_4q": {"eps": prev_eps, "revenue": prev_rev},
            "eps_yoy_pct":     round((cur_eps - prev_eps) / prev_eps * 100, 2) if (cur_eps is not None and prev_eps) else None,
            "revenue_yoy_pct": round((cur_rev - prev_rev) / prev_rev * 100, 2) if (cur_rev is not None and prev_rev) else None,
        }

    return {
        "ticker": ticker, "statement": statement, "quarters": quarters,
        "ok": True, "rows": last_n,
        "annual_summary": annual_summary,
    }


def _aggregate_dividend_by_calendar_year(rows: list[dict]) -> dict[int, dict]:
    """股利資料按 ROC 年(year 字串前綴 e.g. "114年第3季")推斷西元年,合計現金/股票股利。"""
    import re
    by_year: dict[int, dict] = {}
    for r in rows:
        y_str = r.get("year") or ""
        m = re.match(r"^(\d{2,3})年", y_str)
        if not m:
            continue
        roc_year = int(m.group(1))
        ce_year = roc_year + 1911
        bucket = by_year.setdefault(ce_year, {
            "year": ce_year, "cash_dividend": 0.0, "stock_dividend": 0.0,
            "cash_ex_date": None, "cash_payment_date": None,
        })
        bucket["cash_dividend"]  += float(r.get("cash_dividend")  or 0)
        bucket["stock_dividend"] += float(r.get("stock_dividend") or 0)
        ex = r.get("cash_ex_date")
        if ex and (bucket["cash_ex_date"] is None or ex > bucket["cash_ex_date"]):
            bucket["cash_ex_date"] = ex
            bucket["cash_payment_date"] = r.get("cash_payment_date")
    return by_year


def _annual_eps_sum(ticker: str, year: int) -> float | None:
    """回傳該西元年 4 季 EPS 合計;有任一季缺則回 None。實際上有任 EPS 資料即合計。"""
    rows = get_financial_quarterly_range(ticker, "income", f"{year}-01-01")
    eps_by_date: dict[str, float] = {}
    for r in rows:
        if r["type"] == "EPS" and r["date"].startswith(str(year)):
            eps_by_date[r["date"]] = r["value"]
    if not eps_by_date:
        return None
    return round(sum(eps_by_date.values()), 4)


@app.get("/api/stocks/{ticker}/dividend")
def stock_dividend(ticker: str, years: int = 10):
    """個股股利歷史:按西元年合計現金/股票股利,加配發率。"""
    ticker = ticker.upper()
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if years < 1 or years > 30:
        raise HTTPException(status_code=400, detail="years must be 1..30")

    fetched = fetch_stock_dividend(ticker)
    raw_rows = get_dividend_history(ticker)

    if not raw_rows:
        return {"ticker": ticker, "years": years, "ok": fetched,
                "summary": None, "rows": []}

    by_year = _aggregate_dividend_by_calendar_year(raw_rows)

    rows_with_ratio = []
    cutoff_year = datetime.now(timezone.utc).year - years
    for ce_year, b in sorted(by_year.items()):
        if ce_year < cutoff_year:
            continue
        eps_sum = _annual_eps_sum(ticker, ce_year)
        payout = (round(b["cash_dividend"] / eps_sum * 100, 2)
                  if eps_sum and eps_sum != 0 else None)
        rows_with_ratio.append({
            "year":             ce_year,
            "cash_dividend":    round(b["cash_dividend"], 4),
            "stock_dividend":   round(b["stock_dividend"], 4),
            "cash_ex_date":     b["cash_ex_date"],
            "cash_payment_date":b["cash_payment_date"],
            "payout_ratio_pct": payout,
            "dividend_yield_pct": None,
        })

    payouts = [r["payout_ratio_pct"] for r in rows_with_ratio if r["payout_ratio_pct"] is not None]
    summary = {
        "avg_payout_ratio_pct": round(sum(payouts) / len(payouts), 2) if payouts else None,
        "avg_dividend_yield_pct": None,
    }

    return {"ticker": ticker, "years": years, "ok": True,
            "summary": summary, "rows": rows_with_ratio}


@app.get("/api/stocks/{ticker}/history")
def stock_history(ticker: str, time_range: str = "3M"):
    if time_range not in RANGE_DELTAS:
        raise HTTPException(status_code=400, detail="Unknown time_range")
    try:
        data = fetch_stock_history(ticker.upper(), time_range)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")
    if data is None:
        raise HTTPException(status_code=404, detail="No history available")
    return data


class AlertRequest(BaseModel):
    target_type: str
    target: str
    condition: str
    threshold: float


class AlertToggleRequest(BaseModel):
    enabled: bool


VALID_TARGET_TYPES = {"indicator", "stock"}
VALID_CONDITIONS = {"above", "below"}


@app.get("/api/alerts")
def get_alerts():
    return list_alerts()


@app.post("/api/alerts")
def create_alert(req: AlertRequest):
    if req.target_type not in VALID_TARGET_TYPES:
        raise HTTPException(status_code=400, detail="Invalid target_type")
    if req.condition not in VALID_CONDITIONS:
        raise HTTPException(status_code=400, detail="Invalid condition")
    if req.target_type == "indicator" and req.target not in INDICATOR_NAMES:
        raise HTTPException(status_code=400, detail="Unknown indicator")
    target = req.target.upper() if req.target_type == "stock" else req.target
    alert_id = add_alert(req.target_type, target, req.condition, req.threshold)
    return {"id": alert_id}


@app.delete("/api/alerts/{alert_id}")
def remove_alert(alert_id: int):
    delete_alert(alert_id)
    return {"ok": True}


@app.patch("/api/alerts/{alert_id}")
def toggle_alert(alert_id: int, req: AlertToggleRequest):
    set_alert_enabled(alert_id, req.enabled)
    return {"ok": True}


@app.post("/api/refresh/{indicator}")
def refresh(indicator: str):
    fn = FETCHERS.get(indicator)
    if fn is None:
        raise HTTPException(status_code=404, detail="Unknown indicator")
    try:
        fn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}


@app.get("/api/news")
def get_news(limit: int = 15):
    from fetchers.news import get_cached_news
    return get_cached_news()[:limit]
