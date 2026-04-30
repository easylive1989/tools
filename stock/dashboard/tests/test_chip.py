"""Chip fetcher tests."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import db
from app import app
from fetchers.chip_total import parse_total_margin

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
