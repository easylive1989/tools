"""Fundamentals fetcher tests."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import db
from app import app
from fetchers.fundamentals_stock import (
    parse_per_rows, parse_revenue_rows,
    parse_financial_rows, parse_dividend_rows,
)

client = TestClient(app)


# === PER ===
SAMPLE_PER = [
    {"date": "2026-04-29", "stock_id": "2330",
     "dividend_yield": 1.01, "PER": 32.91, "PBR": 10.43},
    {"date": "2026-04-30", "stock_id": "2330",
     "dividend_yield": 1.03, "PER": 32.23, "PBR": 10.22},
]


def test_parse_per_rows_extracts_three_columns():
    out = parse_per_rows(SAMPLE_PER, ticker="2330.TW")
    assert len(out) == 2
    assert out[0] == {
        "ticker": "2330.TW", "date": "2026-04-29",
        "per": 32.91, "pbr": 10.43, "dividend_yield": 1.01,
    }
    assert out[1]["per"] == 32.23


# === Revenue ===
SAMPLE_REVENUE = [
    {"date": "2026-03-01", "stock_id": "2330",
     "revenue": 317656613000, "revenue_year": 2026, "revenue_month": 2,
     "create_time": "2026-04-21"},
    {"date": "2026-04-01", "stock_id": "2330",
     "revenue": 415191699000, "revenue_year": 2026, "revenue_month": 3,
     "create_time": "2026-04-21"},
]


def test_parse_revenue_rows_extracts_year_month_value():
    out = parse_revenue_rows(SAMPLE_REVENUE, ticker="2330.TW")
    assert len(out) == 2
    first = out[0]
    assert first["ticker"]         == "2330.TW"
    assert first["year"]           == 2026
    assert first["month"]          == 2
    assert first["revenue"]        == 317656613000
    assert first["announced_date"] == "2026-04-21"


# === Financial (one parser handles all three statements via report_type) ===
SAMPLE_INCOME = [
    {"date": "2026-03-31", "stock_id": "2330", "type": "EPS",         "value": 13.98, "origin_name": "EPS"},
    {"date": "2026-03-31", "stock_id": "2330", "type": "Revenue",     "value": 8392000000000, "origin_name": "營業收入"},
    {"date": "2026-03-31", "stock_id": "2330", "type": "GrossProfit", "value": 4123000000000, "origin_name": "毛利"},
]


def test_parse_financial_rows_long_format_with_report_type():
    out = parse_financial_rows(SAMPLE_INCOME, ticker="2330.TW", report_type="income")
    assert len(out) == 3
    assert all(r["ticker"] == "2330.TW" for r in out)
    assert all(r["report_type"] == "income" for r in out)
    assert all(r["date"] == "2026-03-31" for r in out)
    types = {r["type"]: r["value"] for r in out}
    assert types["EPS"] == 13.98
    assert types["Revenue"] == 8392000000000


# === Dividend ===
SAMPLE_DIVIDEND = [
    {"date": "2025-12-17", "stock_id": "2330", "year": "114年第2季",
     "CashEarningsDistribution": 5.00001118, "StockEarningsDistribution": 0.0,
     "CashExDividendTradingDate": "2025-12-11",
     "CashDividendPaymentDate": "2026-01-08",
     "AnnouncementDate": "2025-11-26"},
    {"date": "2026-03-23", "stock_id": "2330", "year": "114年第3季",
     "CashEarningsDistribution": 6.00003573, "StockEarningsDistribution": 0.0,
     "CashExDividendTradingDate": "2026-03-17",
     "CashDividendPaymentDate": "2026-04-09",
     "AnnouncementDate": "2026-03-02"},
]


def test_parse_dividend_rows_picks_relevant_columns():
    out = parse_dividend_rows(SAMPLE_DIVIDEND, ticker="2330.TW")
    assert len(out) == 2
    first = out[0]
    assert first["ticker"]            == "2330.TW"
    assert first["year"]              == "114年第2季"
    assert first["cash_dividend"]     == pytest.approx(5.00001118)
    assert first["stock_dividend"]    == 0.0
    assert first["cash_ex_date"]      == "2025-12-11"
    assert first["cash_payment_date"] == "2026-01-08"
    assert first["announcement_date"] == "2025-11-26"
