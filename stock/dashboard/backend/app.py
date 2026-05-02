import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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
from fetchers.broker import fetch_broker_daily
from fetchers.chip_stock import fetch_stock_chip, to_finmind_id as chip_to_finmind_id
from fetchers.fundamentals_stock import (
    fetch_stock_per, fetch_stock_revenue,
    fetch_stock_financial, fetch_stock_dividend,
    to_finmind_id as fundamentals_to_finmind_id,
)
from core.settings import settings
from api._constants import RANGE_DELTAS, INDICATOR_NAMES
from api.routes import indicators, stocks, fundamentals
from api.routes import alerts as alerts_routes

app = FastAPI(title="Stock Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["*"],
)

app.include_router(indicators.router)
app.include_router(stocks.router)
app.include_router(fundamentals.router)
app.include_router(alerts_routes.router)


@app.on_event("startup")
def startup():
    from core.logging import setup_logging
    setup_logging()
    init_db()
    try:
        from scheduler import start_scheduler
        start_scheduler()
    except ImportError:
        print("[app] scheduler not available yet")


@app.get("/api/news")
def get_news(limit: int = 15):
    from fetchers.news import get_cached_news
    return get_cached_news()[:limit]
