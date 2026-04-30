"""Chip fetcher tests."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import db
from app import app
from fetchers.chip_total import parse_total_margin, parse_total_institutional

client = TestClient(app)


# Sample 來自 FinMind v4 GET /data?dataset=TaiwanStockTotalMarginPurchaseShortSale
# 一天 3 筆 row(MarginPurchase / MarginPurchaseMoney / ShortSale),長格式
SAMPLE_TOTAL_MARGIN = [
    {"name": "MarginPurchase",      "date": "2026-04-29",
     "TodayBalance": 8672780,        "YesBalance": 8677088,
     "buy": 353740, "sell": 349629, "Return": 8419},
    {"name": "ShortSale",            "date": "2026-04-29",
     "TodayBalance": 197420,         "YesBalance": 197613,
     "buy": 19169,  "sell": 20523,  "Return": 1547},
    {"name": "MarginPurchaseMoney", "date": "2026-04-29",
     "TodayBalance": 460963803000,   "YesBalance": 457112797000,
     "buy": 29073808000, "sell": 24578802000, "Return": 644000000},
]


def test_parse_total_margin_returns_three_indicators_per_day():
    out = parse_total_margin(SAMPLE_TOTAL_MARGIN)
    assert "2026-04-29" in out
    day = out["2026-04-29"]
    # margin_balance: MarginPurchaseMoney TodayBalance 換算億元
    assert day["margin_balance"] == pytest.approx(4609.638, rel=1e-3)
    # short_balance: ShortSale TodayBalance 千股(直接保留為「張」)
    assert day["short_balance"] == 197420
    # short_margin_ratio: 融券張 / 融資張 × 100
    assert day["short_margin_ratio"] == pytest.approx(2.276, rel=1e-2)


# Sample 來自 FinMind v4 GET /data?dataset=TaiwanStockTotalInstitutionalInvestors
# 一天 6 筆 row,name 區分法人類別,單位是「元」
SAMPLE_TOTAL_INST = [
    {"name": "Foreign_Investor",   "date": "2026-04-29",
     "buy": 338372913624, "sell": 386520362349},
    {"name": "Foreign_Dealer_Self","date": "2026-04-29",
     "buy": 0,            "sell": 0},
    {"name": "Investment_Trust",   "date": "2026-04-29",
     "buy": 22631309887,  "sell": 20502983872},
    {"name": "Dealer_self",        "date": "2026-04-29",
     "buy": 4610504372,   "sell": 6343282634},
    {"name": "Dealer_Hedging",     "date": "2026-04-29",
     "buy": 25753523687,  "sell": 25619864056},
    {"name": "total",              "date": "2026-04-29",
     "buy": 391368251570, "sell": 438986492911},
]


def test_parse_total_institutional_returns_three_net_buys_per_day():
    out = parse_total_institutional(SAMPLE_TOTAL_INST)
    day = out["2026-04-29"]
    # 外資 = Foreign_Investor + Foreign_Dealer_Self;((338.37 - 386.52) + (0 - 0)) × 10 億 ≈ -481.47 億
    assert day["total_foreign_net"] == pytest.approx(-481.474, rel=1e-2)
    # 投信:(22.63 - 20.50)億 ≈ 21.28 億
    assert day["total_trust_net"] == pytest.approx(21.283, rel=1e-2)
    # 自營商 = Dealer_self + Dealer_Hedging;((4.61 - 6.34) + (25.75 - 25.62))億 ≈ -15.99 億
    assert day["total_dealer_net"] == pytest.approx(-15.991, rel=1e-2)
