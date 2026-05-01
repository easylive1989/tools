"""個股基本面 fetcher,lazy fetch + DB cache。

從 FinMind 抓 6 個 dataset(全部免費 with data_id):
- TaiwanStockPER (每日 PER/PBR/殖利率) → stock_per_daily
- TaiwanStockMonthRevenue (每月營收) → stock_revenue_monthly
- TaiwanStockFinancialStatements (損益表,每季) → stock_financial_quarterly (report_type='income')
- TaiwanStockBalanceSheet (資產負債表,每季) → stock_financial_quarterly (report_type='balance')
- TaiwanStockCashFlowsStatement (現金流量表,每季) → stock_financial_quarterly (report_type='cash_flow')
- TaiwanStockDividend (股利) → stock_dividend_history

複用 chip_stock.py 模式:lazy fetch + DB cache,失敗 log + return False。
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import (
    save_per_daily_rows, get_latest_per_date,
    save_revenue_monthly_rows, get_latest_revenue_ym,
    save_financial_quarterly_rows, get_latest_financial_date,
    save_dividend_history_rows, get_latest_dividend_announce_date,
)

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()

# 對應 spec 範圍
DEFAULT_PER_LOOKBACK_DAYS = 1825      # 5 年
DEFAULT_REVENUE_LOOKBACK_MONTHS = 36  # 3 年
DEFAULT_FINANCIAL_LOOKBACK_QUARTERS = 12  # 3 年(12 季)
DEFAULT_DIVIDEND_LOOKBACK_YEARS = 10  # 10 年

# Phase 2 三表名 → FinMind dataset name
FINANCIAL_DATASET = {
    "income":    "TaiwanStockFinancialStatements",
    "balance":   "TaiwanStockBalanceSheet",
    "cash_flow": "TaiwanStockCashFlowsStatement",
}


def to_finmind_id(ticker: str) -> str | None:
    """把 watchlist ticker 轉成 FinMind 純數字代碼,非台股回 None。複用 broker.py 邏輯。"""
    t = (ticker or "").upper().strip()
    if t.endswith(".TW"):
        return t[:-3]
    if t.endswith(".TWO"):
        return t[:-4]
    if t.isdigit():
        return t
    return None


def _request(dataset: str, stock_id: str, start_date: str, end_date: str | None = None) -> list[dict]:
    params = {"dataset": dataset, "data_id": stock_id, "start_date": start_date}
    if end_date:
        params["end_date"] = end_date
    headers = {}
    if FINMIND_TOKEN:
        headers["Authorization"] = f"Bearer {FINMIND_TOKEN}"
    r = requests.get(FINMIND_URL, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") not in (200, None):
        raise RuntimeError(f"FinMind {dataset} error: {payload.get('msg') or payload}")
    return payload.get("data") or []


# === Parsers (pure functions, easy to unit-test) ===

def parse_per_rows(rows: list[dict], ticker: str) -> list[dict]:
    """TaiwanStockPER → list of {ticker, date, per, pbr, dividend_yield}."""
    out: list[dict] = []
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        out.append({
            "ticker":         ticker,
            "date":           d,
            "per":            float(r["PER"]) if r.get("PER") is not None else None,
            "pbr":            float(r["PBR"]) if r.get("PBR") is not None else None,
            "dividend_yield": float(r["dividend_yield"]) if r.get("dividend_yield") is not None else None,
        })
    return out


def parse_revenue_rows(rows: list[dict], ticker: str) -> list[dict]:
    """TaiwanStockMonthRevenue → list of {ticker, year, month, revenue, announced_date}."""
    out: list[dict] = []
    for r in rows:
        y, m = r.get("revenue_year"), r.get("revenue_month")
        if y is None or m is None:
            continue
        out.append({
            "ticker":         ticker,
            "year":           int(y),
            "month":          int(m),
            "revenue":        float(r["revenue"]) if r.get("revenue") is not None else None,
            "announced_date": r.get("create_time") or "",
        })
    return out


def parse_financial_rows(rows: list[dict], ticker: str, report_type: str) -> list[dict]:
    """三表共用 long-format parser。

    rows 形如 {date, stock_id, type, value, origin_name},直接展開為 DB 列。
    """
    out: list[dict] = []
    for r in rows:
        d, t = r.get("date"), r.get("type")
        if not d or not t:
            continue
        out.append({
            "ticker":      ticker,
            "date":        d,
            "report_type": report_type,
            "type":        t,
            "value":       float(r["value"]) if r.get("value") is not None else None,
        })
    return out


def parse_dividend_rows(rows: list[dict], ticker: str) -> list[dict]:
    """TaiwanStockDividend → list of {ticker, year, cash_dividend, stock_dividend,
    cash_ex_date, cash_payment_date, announcement_date}."""
    out: list[dict] = []
    for r in rows:
        y = r.get("year")
        if not y:
            continue
        out.append({
            "ticker":            ticker,
            "year":              y,
            "cash_dividend":     float(r["CashEarningsDistribution"])  if r.get("CashEarningsDistribution")  is not None else None,
            "stock_dividend":    float(r["StockEarningsDistribution"]) if r.get("StockEarningsDistribution") is not None else None,
            "cash_ex_date":      r.get("CashExDividendTradingDate") or None,
            "cash_payment_date": r.get("CashDividendPaymentDate") or None,
            "announcement_date": r.get("AnnouncementDate") or None,
        })
    return out


# === Fetchers (Task 2 will add the 4 fetch_* functions below) ===
