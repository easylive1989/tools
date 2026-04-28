from unittest.mock import patch, MagicMock
import pandas as pd
import json

# conftest.py already sets DB_PATH=:memory: and calls db.init_db()
import db


def make_hist(prices):
    idx = pd.date_range("2026-01-01", periods=len(prices), freq="D")
    return pd.DataFrame({
        "Close": prices,
        "Open": prices,
        "High": prices,
        "Low": prices,
        "Volume": [0] * len(prices)
    }, index=idx)


def test_fetch_taiex_saves_indicator():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_hist([21334.0, 21458.0])
    mock_ticker.history_metadata = {"currency": "TWD"}

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_taiex
        fetch_taiex()

    row = db.get_latest_indicator("taiex")
    assert row is not None
    assert row["value"] == 21458.0
    extra = json.loads(row["extra_json"])
    assert abs(extra["change_pct"] - 0.58) < 0.1
    assert extra["prev_close"] == 21334.0


def test_fetch_fx_saves_indicator():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_hist([32.11, 32.15])
    mock_ticker.history_metadata = {"currency": "USD"}

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_fx
        fetch_fx()

    row = db.get_latest_indicator("fx")
    assert row is not None
    assert abs(row["value"] - 32.15) < 0.01


def test_fetch_all_stocks_saves_snapshots():
    db.add_watched_ticker("0050.TW")
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_hist([197.20, 198.35])
    mock_ticker.history_metadata = {"currency": "TWD"}
    mock_ticker.info = {"shortName": "元大台灣50"}

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_all_stocks
        fetch_all_stocks()

    row = db.get_latest_stock("0050.TW")
    assert row is not None
    assert abs(row["price"] - 198.35) < 0.01
    assert row["currency"] == "TWD"


def test_fetch_taiex_skips_on_empty_history():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_taiex
        fetch_taiex()  # should not raise
