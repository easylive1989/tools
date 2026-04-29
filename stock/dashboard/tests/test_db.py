import pytest
import db

def test_init_creates_tables():
    db.init_db()
    conn = db.get_connection()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"indicator_snapshots", "watched_stocks", "stock_snapshots"} <= tables

def test_save_and_get_indicator():
    db.init_db()
    db.save_indicator("taiex", 21458.0, '{"change_pct": 0.58}')
    row = db.get_latest_indicator("taiex")
    assert row is not None
    assert row["value"] == 21458.0
    assert row["indicator"] == "taiex"

def test_get_indicator_returns_none_when_empty():
    db.init_db()
    assert db.get_latest_indicator("ndc") is None

def test_indicator_history_filtered_by_date():
    db.init_db()
    from datetime import datetime, timedelta, timezone
    db.save_indicator("margin", 2500.0)
    db.save_indicator("margin", 2341.0)
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    rows = db.get_indicator_history("margin", since)
    assert len(rows) == 2
    assert rows[-1]["value"] == 2341.0

def test_watched_stocks_crud():
    db.init_db()
    db.add_watched_ticker("2330.TW")
    db.add_watched_ticker("VOO")
    tickers = db.get_watched_tickers()
    assert "2330.TW" in tickers
    assert "VOO" in tickers
    db.remove_watched_ticker("VOO")
    assert "VOO" not in db.get_watched_tickers()

def test_add_duplicate_ticker_is_idempotent():
    db.init_db()
    db.add_watched_ticker("AAPL")
    db.add_watched_ticker("AAPL")
    assert db.get_watched_tickers().count("AAPL") == 1

def test_save_and_get_stock_snapshot():
    db.init_db()
    db.add_watched_ticker("0050.TW")
    db.save_stock_snapshot("0050.TW", 198.35, 1.15, 0.58, "TWD", "元大台灣50")
    row = db.get_latest_stock("0050.TW")
    assert row["price"] == 198.35
    assert row["name"] == "元大台灣50"


def test_alert_crud_and_lifecycle():
    db.init_db()
    aid = db.add_alert("indicator", "taiex", "above", 22000.0)
    assert aid > 0

    alerts = db.list_alerts()
    assert len(alerts) == 1
    assert alerts[0]["target"] == "taiex"
    assert alerts[0]["enabled"] == 1

    active = db.get_active_alerts("indicator", "taiex")
    assert len(active) == 1

    db.mark_alert_triggered(aid, 22150.5)
    after = db.list_alerts()[0]
    assert after["enabled"] == 0
    assert after["triggered_value"] == 22150.5
    assert after["triggered_at"] is not None
    assert db.get_active_alerts("indicator", "taiex") == []

    db.set_alert_enabled(aid, True)
    re_armed = db.list_alerts()[0]
    assert re_armed["enabled"] == 1
    assert re_armed["triggered_at"] is None

    db.delete_alert(aid)
    assert db.list_alerts() == []
