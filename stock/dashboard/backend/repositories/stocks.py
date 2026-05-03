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


def get_watched_tickers(user_id: int | None = None) -> list[str]:
    """Watched tickers.

    Pass `user_id` to scope to one user (used by API routes).
    Pass `None` for the global DISTINCT union (used by scheduled fetchers
    that prefetch every ticker any user is watching).
    """
    with get_connection() as conn:
        if user_id is None:
            rows = conn.execute(
                "SELECT DISTINCT ticker FROM watched_stocks ORDER BY ticker"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT ticker FROM watched_stocks WHERE user_id=? ORDER BY added_at",
                (user_id,),
            ).fetchall()
        return [r["ticker"] for r in rows]


def add_watched_ticker(user_id: int, ticker: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO watched_stocks (user_id, ticker, added_at) VALUES (?,?,?)",
            (user_id, ticker, datetime.now(timezone.utc).replace(tzinfo=None).isoformat()),
        )


def remove_watched_ticker(user_id: int, ticker: str):
    """Remove ticker (for this user) AND disable any of this user's
    stock_indicator alerts targeting it.

    The cross-table side effect (disabling alerts) is preserved from the
    pre-USER implementation but now scoped to the user — a different
    user's alerts on the same ticker stay enabled.
    """
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM watched_stocks WHERE user_id=? AND ticker=?",
            (user_id, ticker),
        )
        conn.execute(
            "UPDATE price_alerts SET enabled=0 "
            "WHERE user_id=? AND target_type='stock_indicator' AND target=?",
            (user_id, ticker),
        )
