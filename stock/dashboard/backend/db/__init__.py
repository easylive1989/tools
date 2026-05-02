import sqlite3
import os
import threading
from datetime import datetime, timedelta, timezone

from core.settings import settings

DB_PATH = settings.db_path
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
    """Bring the database up to the latest schema by running migrations."""
    from db.runner import run_migrations
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    with get_connection() as conn:
        run_migrations(conn, migrations_dir)

def save_indicator(indicator: str, value: float, extra_json: str = None, timestamp: datetime = None):
    ts = (timestamp or datetime.now(timezone.utc).replace(tzinfo=None)).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO indicator_snapshots (indicator, timestamp, value, extra_json) VALUES (?,?,?,?)",
            (indicator, ts, value, extra_json),
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
        # Phase 4 follow-up:同時停用該 ticker 的 stock_indicator alerts(避免 stale)
        conn.execute(
            "UPDATE price_alerts SET enabled=0 "
            "WHERE target_type='stock_indicator' AND target=?",
            (ticker,)
        )

def list_alerts() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM price_alerts ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def add_alert(target_type: str, target: str, condition: str, threshold: float,
              *, indicator_key: str | None = None, window_n: int | None = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO price_alerts "
            "(target_type, target, condition, threshold, indicator_key, window_n, "
            " enabled, created_at) "
            "VALUES (?,?,?,?,?,?,1,?)",
            (target_type, target, condition, threshold, indicator_key, window_n,
             datetime.now(timezone.utc).replace(tzinfo=None).isoformat()),
        )
        return cur.lastrowid


def delete_alert(alert_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM price_alerts WHERE id=?", (alert_id,))


def set_alert_enabled(alert_id: int, enabled: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE price_alerts SET enabled=?, triggered_at=NULL, triggered_value=NULL "
            "WHERE id=?",
            (1 if enabled else 0, alert_id),
        )


def get_active_alerts(target_type: str, target: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM price_alerts WHERE target_type=? AND target=? AND enabled=1",
            (target_type, target),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_alert_triggered(alert_id: int, value: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE price_alerts SET enabled=0, triggered_at=?, triggered_value=? WHERE id=?",
            (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), value, alert_id),
        )


def save_broker_daily_rows(rows: list[dict]) -> None:
    """Bulk upsert per-broker per-day aggregates.

    Each row needs: ticker, date, securities_trader_id, securities_trader,
    buy_volume, sell_volume, buy_amount, sell_amount.
    """
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_broker_daily "
            "(ticker, date, securities_trader_id, securities_trader, "
            " buy_volume, sell_volume, buy_amount, sell_amount) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, date, securities_trader_id) DO UPDATE SET "
            " securities_trader=excluded.securities_trader, "
            " buy_volume=excluded.buy_volume, "
            " sell_volume=excluded.sell_volume, "
            " buy_amount=excluded.buy_amount, "
            " sell_amount=excluded.sell_amount",
            [
                (
                    r["ticker"], r["date"], r["securities_trader_id"],
                    r.get("securities_trader") or "",
                    r.get("buy_volume", 0) or 0,
                    r.get("sell_volume", 0) or 0,
                    r.get("buy_amount", 0) or 0,
                    r.get("sell_amount", 0) or 0,
                )
                for r in rows
            ],
        )


def get_broker_daily_range(ticker: str, since_date: str) -> list[dict]:
    """Return per-broker daily aggregates for ticker on or after since_date (YYYY-MM-DD)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, securities_trader_id, securities_trader, "
            "       buy_volume, sell_volume, buy_amount, sell_amount "
            "FROM stock_broker_daily "
            "WHERE ticker=? AND date>=? "
            "ORDER BY date",
            (ticker, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_broker_date(ticker: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM stock_broker_daily WHERE ticker=?",
            (ticker,),
        ).fetchone()
        return row["d"] if row and row["d"] else None


def save_chip_daily_rows(rows: list[dict]) -> None:
    """Bulk upsert per-day stock chip rows."""
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_chip_daily "
            "(ticker, date, foreign_buy, foreign_sell, trust_buy, trust_sell, "
            " dealer_buy, dealer_sell, margin_balance, short_balance) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, date) DO UPDATE SET "
            " foreign_buy=COALESCE(excluded.foreign_buy, foreign_buy), "
            " foreign_sell=COALESCE(excluded.foreign_sell, foreign_sell), "
            " trust_buy=COALESCE(excluded.trust_buy, trust_buy), "
            " trust_sell=COALESCE(excluded.trust_sell, trust_sell), "
            " dealer_buy=COALESCE(excluded.dealer_buy, dealer_buy), "
            " dealer_sell=COALESCE(excluded.dealer_sell, dealer_sell), "
            " margin_balance=COALESCE(excluded.margin_balance, margin_balance), "
            " short_balance=COALESCE(excluded.short_balance, short_balance)",
            [
                (r["ticker"], r["date"],
                 r.get("foreign_buy"), r.get("foreign_sell"),
                 r.get("trust_buy"), r.get("trust_sell"),
                 r.get("dealer_buy"), r.get("dealer_sell"),
                 r.get("margin_balance"), r.get("short_balance"))
                for r in rows
            ],
        )


def get_chip_daily_range(ticker: str, since_date: str) -> list[dict]:
    """Per-day chip rows for ticker on or after since_date (YYYY-MM-DD)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, foreign_buy, foreign_sell, trust_buy, trust_sell, "
            "       dealer_buy, dealer_sell, margin_balance, short_balance "
            "FROM stock_chip_daily WHERE ticker=? AND date>=? ORDER BY date",
            (ticker, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_chip_date(ticker: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM stock_chip_daily WHERE ticker=?",
            (ticker,),
        ).fetchone()
        return row["d"] if row and row["d"] else None


# --- PER ---
def save_per_daily_rows(rows: list[dict]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_per_daily (ticker, date, per, pbr, dividend_yield) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(ticker, date) DO UPDATE SET "
            " per=excluded.per, pbr=excluded.pbr, dividend_yield=excluded.dividend_yield",
            [(r["ticker"], r["date"], r.get("per"), r.get("pbr"), r.get("dividend_yield"))
             for r in rows],
        )


def get_per_daily_range(ticker: str, since_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, per, pbr, dividend_yield FROM stock_per_daily "
            "WHERE ticker=? AND date>=? ORDER BY date",
            (ticker, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_per_date(ticker: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM stock_per_daily WHERE ticker=?",
            (ticker,),
        ).fetchone()
        return row["d"] if row and row["d"] else None


# --- Revenue ---
def save_revenue_monthly_rows(rows: list[dict]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_revenue_monthly "
            "(ticker, year, month, revenue, announced_date) VALUES (?,?,?,?,?) "
            "ON CONFLICT(ticker, year, month) DO UPDATE SET "
            " revenue=excluded.revenue, announced_date=excluded.announced_date",
            [(r["ticker"], r["year"], r["month"], r.get("revenue"), r.get("announced_date"))
             for r in rows],
        )


def get_revenue_monthly_range(ticker: str, since_year: int, since_month: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT year, month, revenue, announced_date FROM stock_revenue_monthly "
            "WHERE ticker=? AND (year * 12 + month) >= (? * 12 + ?) "
            "ORDER BY year, month",
            (ticker, since_year, since_month),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_revenue_ym(ticker: str) -> tuple[int, int] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT year, month FROM stock_revenue_monthly "
            "WHERE ticker=? ORDER BY year DESC, month DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        return (row["year"], row["month"]) if row else None


# --- Financial (income/balance/cash_flow) ---
def save_financial_quarterly_rows(rows: list[dict]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_financial_quarterly "
            "(ticker, date, report_type, type, value) VALUES (?,?,?,?,?) "
            "ON CONFLICT(ticker, date, report_type, type) DO UPDATE SET "
            " value=excluded.value",
            [(r["ticker"], r["date"], r["report_type"], r["type"], r.get("value"))
             for r in rows],
        )


def get_financial_quarterly_range(ticker: str, report_type: str, since_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, type, value FROM stock_financial_quarterly "
            "WHERE ticker=? AND report_type=? AND date>=? "
            "ORDER BY date, type",
            (ticker, report_type, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_financial_date(ticker: str, report_type: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM stock_financial_quarterly "
            "WHERE ticker=? AND report_type=?",
            (ticker, report_type),
        ).fetchone()
        return row["d"] if row and row["d"] else None


# --- Dividend ---
def save_dividend_history_rows(rows: list[dict]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_dividend_history "
            "(ticker, year, cash_dividend, stock_dividend, cash_ex_date, cash_payment_date, announcement_date) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, year) DO UPDATE SET "
            " cash_dividend=excluded.cash_dividend, "
            " stock_dividend=excluded.stock_dividend, "
            " cash_ex_date=excluded.cash_ex_date, "
            " cash_payment_date=excluded.cash_payment_date, "
            " announcement_date=excluded.announcement_date",
            [(r["ticker"], r["year"], r.get("cash_dividend"), r.get("stock_dividend"),
              r.get("cash_ex_date"), r.get("cash_payment_date"), r.get("announcement_date"))
             for r in rows],
        )


def get_dividend_history(ticker: str) -> list[dict]:
    """Return all dividend rows for ticker, sorted by ROC year + 季 numeric prefix."""
    import re
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT year, cash_dividend, stock_dividend, cash_ex_date, "
            "       cash_payment_date, announcement_date "
            "FROM stock_dividend_history WHERE ticker=?",
            (ticker,),
        ).fetchall()
    result = [dict(r) for r in rows]

    def _key(row: dict) -> tuple[int, int]:
        # 抓出「ROC 年」與「季」做自然排序;格式如 "114年第3季"
        y = row["year"] or ""
        ym = re.match(r"(\d+)", y)
        qm = re.search(r"第(\d+)", y)
        return (int(ym.group(1)) if ym else 0,
                int(qm.group(1)) if qm else 0)

    result.sort(key=_key)
    return result


def get_latest_dividend_announce_date(ticker: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(announcement_date) AS d FROM stock_dividend_history WHERE ticker=?",
            (ticker,),
        ).fetchone()
        return row["d"] if row and row["d"] else None


def purge_old_data(days: int = 1095):
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).isoformat()
    cutoff_date = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_connection() as conn:
        conn.execute("DELETE FROM indicator_snapshots WHERE timestamp<?", (cutoff,))
        conn.execute("DELETE FROM stock_snapshots WHERE timestamp<?", (cutoff,))
        conn.execute("DELETE FROM stock_broker_daily WHERE date<?", (cutoff_date,))
        conn.execute("DELETE FROM stock_chip_daily WHERE date<?", (cutoff_date,))
        conn.execute("DELETE FROM stock_per_daily WHERE date<?", (cutoff_date,))
        conn.execute(
            "DELETE FROM stock_revenue_monthly "
            "WHERE (year * 12 + month) < (? * 12 + ?)",
            (int(cutoff_date[:4]), int(cutoff_date[5:7]))
        )
        conn.execute("DELETE FROM stock_financial_quarterly WHERE date<?", (cutoff_date,))
        # dividend 不 purge(歷史很長很重要)
