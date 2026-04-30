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
)
from fetchers.yfinance_fetcher import fetch_taiex, fetch_fx, fetch_all_stocks, fetch_stock_history
from fetchers.fear_greed import fetch_fear_greed
from fetchers.margin import fetch_margin
from fetchers.ndc import fetch_ndc
from fetchers.volume import fetch_tw_volume, fetch_us_volume
from fetchers.broker import fetch_broker_daily, to_finmind_id

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
    "margin":     fetch_margin,
    "ndc":        fetch_ndc,
    "stocks":     fetch_all_stocks,
    "tw_volume":  fetch_tw_volume,
    "us_volume":  fetch_us_volume,
}

INDICATOR_NAMES = ["taiex", "fx", "fear_greed", "margin", "ndc", "tw_volume", "us_volume"]


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
    """前 N 大買超券商，含持續買入天數與買進均價。

    days: 統計期間（交易日數，會以日曆天 1.5 倍換算 fetch 視窗）
    top:  回傳前幾大買超券商
    """
    ticker = ticker.upper()
    if to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if days < 1 or days > 60:
        raise HTTPException(status_code=400, detail="days must be 1..60")
    if top < 1 or top > 20:
        raise HTTPException(status_code=400, detail="top must be 1..20")

    fetched = fetch_broker_daily(ticker)
    # 用日曆日換算合理 fetch 視窗 (約 1.5 倍交易日數)
    since_date = (datetime.now(timezone.utc).date() - timedelta(days=int(days * 1.6) + 5)).isoformat()
    rows = get_broker_daily_range(ticker, since_date)
    if not rows:
        return {
            "ticker":    ticker,
            "days":      days,
            "as_of":     None,
            "ok":        fetched,
            "top_brokers": [],
        }

    # 篩到「最近 N 個出現過的交易日」
    distinct_dates = sorted({r["date"] for r in rows})
    window_dates = distinct_dates[-days:]
    window_set = set(window_dates)
    rows_in_window = [r for r in rows if r["date"] in window_set]

    # 聚合每個券商
    by_broker: dict[str, dict] = {}
    for r in rows_in_window:
        bid = r["securities_trader_id"]
        agg = by_broker.setdefault(bid, {
            "id": bid,
            "name": r["securities_trader"] or bid,
            "buy_volume": 0.0,
            "sell_volume": 0.0,
            "buy_amount": 0.0,
            "daily_net": {},
        })
        if not agg["name"] and r["securities_trader"]:
            agg["name"] = r["securities_trader"]
        agg["buy_volume"] += r["buy_volume"] or 0
        agg["sell_volume"] += r["sell_volume"] or 0
        agg["buy_amount"] += r["buy_amount"] or 0
        agg["daily_net"][r["date"]] = (r["buy_volume"] or 0) - (r["sell_volume"] or 0)

    # 排序：依淨買超量
    ranked = sorted(
        by_broker.values(),
        key=lambda b: b["buy_volume"] - b["sell_volume"],
        reverse=True,
    )[:top]

    # 每家計算持續買入天數（從最新交易日往前數）
    result = []
    reversed_dates = list(reversed(window_dates))
    for b in ranked:
        net_buy = b["buy_volume"] - b["sell_volume"]
        avg_buy_price = (b["buy_amount"] / b["buy_volume"]) if b["buy_volume"] > 0 else None
        streak = 0
        for d in reversed_dates:
            daily = b["daily_net"].get(d, 0)
            if daily > 0:
                streak += 1
            else:
                break
        result.append({
            "id":                  b["id"],
            "name":                b["name"],
            "net_buy_volume":      round(net_buy, 2),
            "buy_volume":          round(b["buy_volume"], 2),
            "sell_volume":         round(b["sell_volume"], 2),
            "avg_buy_price":       round(avg_buy_price, 4) if avg_buy_price is not None else None,
            "consecutive_buy_days": streak,
        })

    return {
        "ticker":      ticker,
        "days":        days,
        "as_of":       window_dates[-1] if window_dates else None,
        "ok":          True,
        "top_brokers": result,
    }


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
