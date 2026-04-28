import sqlite3
import os
import threading
from datetime import datetime, timedelta, timezone

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "stock_dashboard.db"))
_memory_conn = None
_memory_lock = threading.Lock()

def get_connection() -> sqlite3.Connection:
    global _memory_conn
    if DB_PATH == ":memory:":
        with _memory_lock:
            if _memory_conn is None:
                _memory_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
                _memory_conn.row_factory = sqlite3.Row
        return _memory_conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS indicator_snapshots (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                indicator TEXT    NOT NULL,
                timestamp TEXT    NOT NULL,
                value     REAL    NOT NULL,
                extra_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_ind_ts
                ON indicator_snapshots(indicator, timestamp);

            CREATE TABLE IF NOT EXISTS watched_stocks (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker   TEXT NOT NULL UNIQUE,
                added_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stock_snapshots (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker     TEXT NOT NULL,
                timestamp  TEXT NOT NULL,
                price      REAL NOT NULL,
                change     REAL,
                change_pct REAL,
                currency   TEXT,
                name       TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_stock_ts
                ON stock_snapshots(ticker, timestamp);
        """)

def save_indicator(indicator: str, value: float, extra_json: str = None):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO indicator_snapshots (indicator, timestamp, value, extra_json) VALUES (?,?,?,?)",
            (indicator, datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), value, extra_json),
        )

def get_latest_indicator(indicator: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM indicator_snapshots WHERE indicator=? ORDER BY timestamp DESC LIMIT 1",
            (indicator,),
        ).fetchone()
        return dict(row) if row else None

def get_indicator_history(indicator: str, since: datetime) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT timestamp, value, extra_json FROM indicator_snapshots "
            "WHERE indicator=? AND timestamp>=? ORDER BY timestamp",
            (indicator, since.isoformat()),
        ).fetchall()
        return [dict(r) for r in rows]

def save_stock_snapshot(ticker: str, price: float, change: float, change_pct: float, currency: str, name: str = ""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO stock_snapshots (ticker, timestamp, price, change, change_pct, currency, name) "
            "VALUES (?,?,?,?,?,?,?)",
            (ticker, datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), price, change, change_pct, currency, name),
        )

def get_latest_stock(ticker: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM stock_snapshots WHERE ticker=? ORDER BY timestamp DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        return dict(row) if row else None

def get_watched_tickers() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT ticker FROM watched_stocks ORDER BY added_at").fetchall()
        return [r["ticker"] for r in rows]

def add_watched_ticker(ticker: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO watched_stocks (ticker, added_at) VALUES (?,?)",
            (ticker, datetime.now(timezone.utc).replace(tzinfo=None).isoformat()),
        )

def remove_watched_ticker(ticker: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM watched_stocks WHERE ticker=?", (ticker,))

def purge_old_data(days: int = 1095):
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        conn.execute("DELETE FROM indicator_snapshots WHERE timestamp<?", (cutoff,))
        conn.execute("DELETE FROM stock_snapshots WHERE timestamp<?", (cutoff,))
