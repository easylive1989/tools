import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
os.environ["DB_PATH"] = ":memory:"

import pytest
import db
import json

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def seed_data():
    """Seed data after conftest.py's reset_db re-initialises the DB."""
    db.save_indicator("taiex", 21458.0, json.dumps({"change_pct": 0.58, "prev_close": 21334.0}))
    db.save_indicator("fx", 32.15, json.dumps({"change_pct": 0.12, "prev_close": 32.11}))
    db.save_indicator("fear_greed", 58.0, json.dumps({"label": "貪婪"}))
    db.save_indicator("margin", 2341.0, json.dumps({"unit": "億元"}))
    db.save_indicator("ndc", 24.0, json.dumps({"light": "黃紅燈", "light_code": 4}))
    db.add_watched_ticker("0050.TW")
    db.save_stock_snapshot("0050.TW", 198.35, 1.15, 0.58, "TWD", "元大台灣50")


def test_dashboard_returns_all_indicators():
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    data = r.json()
    for key in ["taiex", "fx", "fear_greed", "margin", "ndc"]:
        assert key in data
        assert "value" in data[key]
        assert "timestamp" in data[key]


def test_history_returns_list():
    r = client.get("/api/history/taiex?range=3M")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert rows[0]["value"] == 21458.0


def test_history_unknown_indicator_returns_404():
    r = client.get("/api/history/unknown")
    assert r.status_code == 404


def test_get_stocks_returns_watchlist():
    r = client.get("/api/stocks")
    assert r.status_code == 200
    stocks = r.json()
    tickers = [s["ticker"] for s in stocks]
    assert "0050.TW" in tickers


def test_add_and_delete_stock():
    r = client.post("/api/stocks", json={"ticker": "2330.tw"})
    assert r.status_code == 200
    tickers = db.get_watched_tickers()
    assert "2330.TW" in tickers  # normalized to uppercase

    r = client.delete("/api/stocks/2330.TW")
    assert r.status_code == 200
    assert "2330.TW" not in db.get_watched_tickers()


def test_refresh_unknown_indicator_returns_404():
    r = client.post("/api/refresh/bogus")
    assert r.status_code == 404
