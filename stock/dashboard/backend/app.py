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
from fetchers.chip_total import fetch_chip_total
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
