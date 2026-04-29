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
)
from fetchers.yfinance_fetcher import fetch_taiex, fetch_fx, fetch_all_stocks
from fetchers.fear_greed import fetch_fear_greed
from fetchers.margin import fetch_margin
from fetchers.ndc import fetch_ndc

app = FastAPI(title="Stock Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://paul-learning.dev"],
    allow_methods=["GET", "POST", "DELETE"],
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
}

INDICATOR_NAMES = ["taiex", "fx", "fear_greed", "margin", "ndc"]


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
