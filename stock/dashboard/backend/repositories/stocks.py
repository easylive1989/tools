"""Stock + watchlist repository."""
from datetime import datetime, timezone

from db.connection import get_connection


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
    """Remove ticker AND disable any stock_indicator alerts targeting it.

    The cross-table side effect (disabling alerts) is preserved verbatim from
    the pre-refactor implementation. Revisit in a later phase if desired.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM watched_stocks WHERE ticker=?", (ticker,))
        conn.execute(
            "UPDATE price_alerts SET enabled=0 "
            "WHERE target_type='stock_indicator' AND target=?",
            (ticker,)
        )
