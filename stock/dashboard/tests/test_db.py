import pytest
import db

def test_init_creates_tables():
    db.init_db()
    conn = db.get_connection()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"indicator_snapshots", "watched_stocks", "stock_snapshots"} <= tables

def test_init_db_creates_schema_migrations_with_0001_applied():
    """init_db() now goes through the migration runner."""
    db.init_db()
    versions = [r[0] for r in db.get_connection().execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()]
    assert "0001" in versions

def test_init_db_baselines_existing_legacy_db():
    """Simulate the live VPS DB: it already has tables but no schema_migrations.
    init_db() must mark 0001 as applied without re-running it (which would error)
    and the existing data must remain intact."""
    # Build a fresh in-memory DB and pre-populate it with a legacy-shaped
    # indicator_snapshots table + one row, mimicking the VPS state.
    db.connection._memory_conn = None
    conn = db.get_connection()
    conn.execute(
        "CREATE TABLE indicator_snapshots ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  indicator TEXT NOT NULL,"
        "  timestamp TEXT NOT NULL,"
        "  value REAL NOT NULL,"
        "  extra_json TEXT"
        ")"
    )
    conn.execute(
        "INSERT INTO indicator_snapshots (indicator, timestamp, value) "
        "VALUES ('taiex', '2026-01-01T00:00:00', 17000.0)"
    )
    conn.commit()

    db.init_db()  # should baseline, not re-run

    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall()]
    assert "0001" in versions
    # Original row preserved.
    rows = conn.execute(
        "SELECT indicator, value FROM indicator_snapshots"
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [("taiex", 17000.0)]

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
    db.save_indicator("margin_balance", 2500.0)
    db.save_indicator("margin_balance", 2341.0)
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    rows = db.get_indicator_history("margin_balance", since)
    assert len(rows) == 2
    assert rows[-1]["value"] == 2341.0

def test_watched_stocks_crud():
    db.init_db()
    db.add_watched_ticker(1, "2330.TW")
    db.add_watched_ticker(1, "VOO")
    tickers = db.get_watched_tickers()
    assert "2330.TW" in tickers
    assert "VOO" in tickers
    db.remove_watched_ticker(1, "VOO")
    assert "VOO" not in db.get_watched_tickers()

def test_add_duplicate_ticker_is_idempotent():
    db.init_db()
    db.add_watched_ticker(1, "AAPL")
    db.add_watched_ticker(1, "AAPL")
    assert db.get_watched_tickers().count("AAPL") == 1

def test_save_and_get_stock_snapshot():
    db.init_db()
    db.add_watched_ticker(1, "0050.TW")
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


def test_remove_watched_ticker_disables_stock_indicator_alerts():
    """移除 watchlist ticker 應同時停用該 ticker 的 stock_indicator alerts(Phase 4 follow-up)。"""
    db.init_db()
    db.add_watched_ticker(1, "2330.TW")
    a1 = db.add_alert("stock_indicator", "2330.TW", "above", 30,
                      indicator_key="per", window_n=None)
    a2 = db.add_alert("indicator", "margin_balance", "above", 5000,
                      indicator_key=None, window_n=None)
    a3 = db.add_alert("stock_indicator", "2454.TW", "above", 50,
                      indicator_key="per", window_n=None)

    db.remove_watched_ticker(1, "2330.TW")

    alerts = {a["id"]: a for a in db.list_alerts()}
    assert alerts[a1]["enabled"] == 0
    assert alerts[a2]["enabled"] == 1
    assert alerts[a3]["enabled"] == 1


def test_remove_watched_ticker_does_not_affect_stock_price_alerts():
    """移除 ticker 不應該動到 'stock' (價格)類型 alerts — 跟 stock_indicator 分開處理。"""
    db.init_db()
    db.add_watched_ticker(1, "2330.TW")
    a1 = db.add_alert("stock", "2330.TW", "above", 1000)

    db.remove_watched_ticker(1, "2330.TW")

    alerts = {a["id"]: a for a in db.list_alerts()}
    assert alerts[a1]["enabled"] == 1
