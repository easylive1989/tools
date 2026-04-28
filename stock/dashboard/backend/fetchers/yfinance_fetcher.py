import json
import yfinance as yf
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator, save_stock_snapshot, get_watched_tickers


def _fetch_price(ticker_symbol: str) -> dict | None:
    """Fetch price data for a ticker symbol."""
    stock = yf.Ticker(ticker_symbol)
    hist = stock.history(period="5d")
    if hist.empty:
        return None
    latest = hist.iloc[-1]
    prev = hist.iloc[-2] if len(hist) >= 2 else latest
    price = float(latest["Close"])
    prev_close = float(prev["Close"])
    change = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0
    currency = ""
    try:
        currency = stock.history_metadata.get("currency", "")
    except Exception:
        pass
    return {
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": round(change_pct, 2),
        "currency": currency,
    }


def fetch_taiex():
    """Fetch Taiwan stock exchange index (^TWII)."""
    data = _fetch_price("^TWII")
    if not data:
        return
    save_indicator(
        "taiex",
        data["price"],
        json.dumps({
            "change_pct": data["change_pct"],
            "prev_close": round(data["prev_close"], 2),
        }),
    )


def fetch_fx():
    """Fetch TWD/USD exchange rate."""
    data = _fetch_price("TWD=X")
    if not data:
        return
    save_indicator(
        "fx",
        round(data["price"], 4),
        json.dumps({
            "change_pct": data["change_pct"],
            "prev_close": round(data["prev_close"], 4),
        }),
    )


def fetch_all_stocks():
    """Fetch all watched stocks."""
    tickers = get_watched_tickers()
    for ticker in tickers:
        try:
            data = _fetch_price(ticker)
            if not data:
                continue
            name = ticker
            try:
                info = yf.Ticker(ticker).info
                name = info.get("shortName") or info.get("longName") or ticker
            except Exception:
                pass
            save_stock_snapshot(
                ticker,
                round(data["price"], 4),
                round(data["change"], 4),
                data["change_pct"],
                data["currency"],
                name,
            )
        except Exception as e:
            print(f"[yfinance] Error fetching {ticker}: {e}")
