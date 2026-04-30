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
    db.save_indicator("margin_balance", 2341.0, json.dumps({"unit": "億元"}))
    db.save_indicator("ndc", 24.0, json.dumps({"light": "黃紅燈", "light_code": 4}))
    db.add_watched_ticker("0050.TW")
    db.save_stock_snapshot("0050.TW", 198.35, 1.15, 0.58, "TWD", "元大台灣50")


def test_dashboard_returns_all_indicators():
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    data = r.json()
    for key in ["taiex", "fx", "fear_greed", "margin_balance", "ndc"]:
        assert key in data
        assert "value" in data[key]
        assert "timestamp" in data[key]


def test_history_returns_list():
    r = client.get("/api/history/taiex?time_range=3M")
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


def test_stock_history_returns_data(monkeypatch):
    fake = {
        "ticker": "2330.TW",
        "name": "台積電",
        "currency": "TWD",
        "time_range": "3M",
        "dates": ["2026-01-02", "2026-01-03"],
        "candles": [
            {"open": 700, "high": 710, "low": 695, "close": 705, "volume": 12345},
            {"open": 705, "high": 715, "low": 700, "close": 710, "volume": 23456},
        ],
        "indicators": {
            "ma5": [None, None],
            "ma20": [None, None],
            "ma60": [None, None],
            "rsi14": [50.0, 60.0],
            "macd": [0.1, 0.2],
            "macd_signal": [0.05, 0.1],
            "macd_histogram": [0.05, 0.1],
        },
    }
    monkeypatch.setattr("app.fetch_stock_history", lambda ticker, time_range: fake)
    r = client.get("/api/stocks/2330.tw/history?time_range=3M")
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "2330.TW"
    assert len(data["candles"]) == 2
    assert "rsi14" in data["indicators"]


def test_stock_history_404_when_no_data(monkeypatch):
    monkeypatch.setattr("app.fetch_stock_history", lambda ticker, time_range: None)
    r = client.get("/api/stocks/UNKNOWN/history?time_range=3M")
    assert r.status_code == 404


def test_stock_history_rejects_invalid_range():
    r = client.get("/api/stocks/2330.TW/history?time_range=10Y")
    assert r.status_code == 400


def test_refresh_unknown_indicator_returns_404():
    r = client.post("/api/refresh/bogus")
    assert r.status_code == 404


def test_alert_endpoints_full_flow():
    r = client.post("/api/alerts", json={
        "target_type": "indicator",
        "target": "taiex",
        "condition": "above",
        "threshold": 22000,
    })
    assert r.status_code == 200
    aid = r.json()["id"]

    r = client.get("/api/alerts")
    assert r.status_code == 200
    items = r.json()
    assert any(a["id"] == aid and a["target"] == "taiex" for a in items)

    r = client.patch(f"/api/alerts/{aid}", json={"enabled": False})
    assert r.status_code == 200
    items = client.get("/api/alerts").json()
    assert next(a for a in items if a["id"] == aid)["enabled"] == 0

    r = client.delete(f"/api/alerts/{aid}")
    assert r.status_code == 200
    items = client.get("/api/alerts").json()
    assert all(a["id"] != aid for a in items)


def test_create_stock_alert_normalises_ticker():
    r = client.post("/api/alerts", json={
        "target_type": "stock",
        "target": "2330.tw",
        "condition": "below",
        "threshold": 800,
    })
    assert r.status_code == 200
    items = client.get("/api/alerts").json()
    aid = r.json()["id"]
    assert next(a for a in items if a["id"] == aid)["target"] == "2330.TW"


def test_create_alert_rejects_invalid_input():
    r = client.post("/api/alerts", json={
        "target_type": "weather", "target": "rain", "condition": "above", "threshold": 1,
    })
    assert r.status_code == 400

    r = client.post("/api/alerts", json={
        "target_type": "indicator", "target": "taiex", "condition": "sideways", "threshold": 1,
    })
    assert r.status_code == 400

    r = client.post("/api/alerts", json={
        "target_type": "indicator", "target": "unknown_ind", "condition": "above", "threshold": 1,
    })
    assert r.status_code == 400
