import json
import math
import yfinance as yf
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator, save_stock_snapshot, get_watched_tickers


def _is_valid(v) -> bool:
    return v is not None and not math.isnan(v)


def _fetch_price(ticker_obj) -> dict | None:
    """Fetch price data for a Ticker instance.

    yfinance 對某些台股盤前可能回傳 NaN，所以從最新往前找第一筆有效的 Close。
    """
    # 拉長一點區間以便處理連假/停牌
    hist = ticker_obj.history(period="10d")
    if hist.empty:
        return None
    closes = [float(c) for c in hist["Close"].tolist()]
    valid = [c for c in closes if _is_valid(c)]
    if len(valid) < 1:
        return None
    price = valid[-1]
    prev_close = valid[-2] if len(valid) >= 2 else price
    change = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0
    currency = ""
    try:
        currency = ticker_obj.history_metadata.get("currency", "")
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
    data = _fetch_price(yf.Ticker("^TWII"))
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
    data = _fetch_price(yf.Ticker("TWD=X"))
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
            stock = yf.Ticker(ticker)
            data = _fetch_price(stock)
            if not data:
                continue
            name = ticker
            try:
                info = stock.info
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
