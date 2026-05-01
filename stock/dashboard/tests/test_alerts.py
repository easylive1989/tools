import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
os.environ["DB_PATH"] = ":memory:"

import db
import alerts as alerts_module


def test_above_alert_triggers_and_disables(monkeypatch):
    aid = db.add_alert("indicator", "taiex", "above", 22000.0)

    sent = []
    monkeypatch.setattr(alerts_module, "send_to_discord", lambda url, payload: sent.append(payload))
    monkeypatch.setenv("DISCORD_STOCK_WEBHOOK_URL", "http://example.invalid/hook")

    alerts_module.check_alerts("indicator", "taiex", 21999.0)
    assert sent == []
    assert db.list_alerts()[0]["enabled"] == 1

    alerts_module.check_alerts("indicator", "taiex", 22050.0)
    assert len(sent) == 1
    embed = sent[0]["embeds"][0]
    assert "加權指數" in embed["title"]
    assert db.list_alerts()[0]["enabled"] == 0


def test_below_alert_triggers(monkeypatch):
    db.add_alert("stock", "2330.TW", "below", 800.0)

    sent = []
    monkeypatch.setattr(alerts_module, "send_to_discord", lambda url, payload: sent.append(payload))
    monkeypatch.setenv("DISCORD_STOCK_WEBHOOK_URL", "http://example.invalid/hook")

    alerts_module.check_alerts("stock", "2330.TW", 850.0)
    assert sent == []

    alerts_module.check_alerts("stock", "2330.TW", 795.0, display_name="台積電")
    assert len(sent) == 1
    assert "台積電" in sent[0]["embeds"][0]["title"]


def test_no_webhook_still_disables_alert(monkeypatch):
    aid = db.add_alert("indicator", "fx", "above", 32.0)
    monkeypatch.delenv("DISCORD_STOCK_WEBHOOK_URL", raising=False)

    alerts_module.check_alerts("indicator", "fx", 32.5)
    # alert should be marked triggered even without webhook
    assert db.list_alerts()[0]["enabled"] == 0


def test_disabled_alert_is_skipped(monkeypatch):
    aid = db.add_alert("indicator", "taiex", "above", 100.0)
    db.set_alert_enabled(aid, False)

    sent = []
    monkeypatch.setattr(alerts_module, "send_to_discord", lambda url, payload: sent.append(payload))
    monkeypatch.setenv("DISCORD_STOCK_WEBHOOK_URL", "http://example.invalid/hook")

    alerts_module.check_alerts("indicator", "taiex", 200.0)
    assert sent == []


from alerts import _check_streak


def test_check_streak_above_all_pass():
    assert _check_streak([220, 230, 210, 250, 200], 'streak_above', 200) is True


def test_check_streak_above_one_fails():
    assert _check_streak([220, 230, 199, 250, 200], 'streak_above', 200) is False


def test_check_streak_below_all_pass():
    assert _check_streak([90, 80, 70, 95, 100], 'streak_below', 100) is True


def test_check_streak_below_one_fails():
    assert _check_streak([90, 80, 70, 95, 101], 'streak_below', 100) is False


def test_check_streak_insufficient_values_returns_false():
    assert _check_streak([], 'streak_above', 100) is False
    assert _check_streak([220, None, 230], 'streak_above', 200) is False


def test_check_streak_length_below_expected_n_returns_false():
    # 只有 3 個值但 expected_n=5 → False(避免「連 5 日突破」誤觸發)
    assert _check_streak([220, 230, 240], 'streak_above', 200, expected_n=5) is False
    # 同樣值但 expected_n=3 → True
    assert _check_streak([220, 230, 240], 'streak_above', 200, expected_n=3) is True
    # expected_n=None 表示 backwards compat,不檢查長度
    assert _check_streak([220, 230, 240], 'streak_above', 200) is True


def test_check_streak_unknown_condition_returns_false():
    assert _check_streak([220, 230], 'above', 200) is False


import db
from alerts import _get_stock_indicator_history


def test_get_stock_indicator_history_per():
    db.save_per_daily_rows([
        {"ticker": "2330.TW", "date": "2026-04-28", "per": 30.0, "pbr": 9.0,  "dividend_yield": 1.5},
        {"ticker": "2330.TW", "date": "2026-04-29", "per": 31.0, "pbr": 9.5,  "dividend_yield": 1.4},
        {"ticker": "2330.TW", "date": "2026-04-30", "per": 32.0, "pbr": 10.0, "dividend_yield": 1.3},
    ])
    out = _get_stock_indicator_history("2330.TW", "per", n=3)
    assert out == [30.0, 31.0, 32.0]   # 舊→新

    out2 = _get_stock_indicator_history("2330.TW", "pbr", n=2)
    assert out2 == [9.5, 10.0]         # 取最近 2 個


def test_get_stock_indicator_history_chip_foreign_net():
    db.save_chip_daily_rows([
        {"ticker": "2330.TW", "date": "2026-04-29",
         "foreign_buy": 5_000_000, "foreign_sell": 3_000_000,
         "trust_buy": None, "trust_sell": None,
         "dealer_buy": None, "dealer_sell": None,
         "margin_balance": None, "short_balance": None},
        {"ticker": "2330.TW", "date": "2026-04-30",
         "foreign_buy": 6_000_000, "foreign_sell": 1_000_000,
         "trust_buy": None, "trust_sell": None,
         "dealer_buy": None, "dealer_sell": None,
         "margin_balance": None, "short_balance": None},
    ])
    # foreign_net = buy - sell;最近 2 日:2_000_000, 5_000_000
    assert _get_stock_indicator_history("2330.TW", "foreign_net", n=2) == [2_000_000, 5_000_000]


def test_get_stock_indicator_history_unknown_key_returns_empty():
    assert _get_stock_indicator_history("2330.TW", "unknown_key", n=5) == []


from unittest.mock import patch
from alerts import check_alerts


def test_check_alerts_stock_indicator_above_triggers():
    db.save_per_daily_rows([
        {"ticker": "2330.TW", "date": "2026-04-30", "per": 35.0, "pbr": 10.0, "dividend_yield": 1.0},
    ])
    db.add_alert("stock_indicator", "2330.TW", "above", 30.0,
                 indicator_key="per", window_n=None)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("stock_indicator", "2330.TW", indicator_key="per")
    assert mock_send.called
    args = mock_send.call_args
    payload = args[0][1]
    assert "2330.TW" in payload["embeds"][0]["title"] or "2330.TW" in payload["embeds"][0]["description"]


def test_check_alerts_stock_indicator_below_does_not_trigger_when_above():
    db.save_per_daily_rows([
        {"ticker": "2330.TW", "date": "2026-04-30", "per": 35.0, "pbr": 10.0, "dividend_yield": 1.0},
    ])
    db.add_alert("stock_indicator", "2330.TW", "below", 30.0,
                 indicator_key="per", window_n=None)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("stock_indicator", "2330.TW", indicator_key="per")
    assert not mock_send.called


def test_check_alerts_stock_indicator_streak_above_triggers():
    db.save_chip_daily_rows([
        {"ticker": "2330.TW", "date": f"2026-04-{day:02d}",
         "foreign_buy": 6_000_000, "foreign_sell": 1_000_000,
         "trust_buy": None, "trust_sell": None,
         "dealer_buy": None, "dealer_sell": None,
         "margin_balance": None, "short_balance": None}
        for day in (24, 25, 28, 29, 30)
    ])
    db.add_alert("stock_indicator", "2330.TW", "streak_above", 0,
                 indicator_key="foreign_net", window_n=5)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("stock_indicator", "2330.TW", indicator_key="foreign_net")
    assert mock_send.called


def test_check_alerts_indicator_streak_above_triggers():
    for d, v in [("2026-04-28T00:00:00", 5100),
                 ("2026-04-29T00:00:00", 5200),
                 ("2026-04-30T00:00:00", 5300)]:
        db.save_indicator("margin_balance", v, timestamp=__import__("datetime").datetime.fromisoformat(d))
    db.add_alert("indicator", "margin_balance", "streak_above", 5000,
                 indicator_key=None, window_n=3)
    with patch("alerts.send_to_discord") as mock_send:
        with patch.dict("os.environ", {"DISCORD_STOCK_WEBHOOK_URL": "https://example/x"}):
            check_alerts("indicator", "margin_balance", value=5300)
    assert mock_send.called


import pytest
from alerts import _pct_rank, _get_stock_revenue_yoy


def test_pct_rank_inclusive_at_max():
    # history 50 點,最大值 → 100
    history = list(range(1, 51))
    assert _pct_rank(50, history) == 100.0


def test_pct_rank_at_min():
    # 最小值 → 1/N * 100
    history = list(range(1, 51))
    assert _pct_rank(1, history) == 2.0


def test_pct_rank_middle():
    history = list(range(1, 51))   # 50 點
    # value=25 → count(<=25) = 25,25/50*100 = 50
    assert _pct_rank(25, history) == 50.0


def test_pct_rank_insufficient_history_returns_none():
    # < 30 點 → None
    assert _pct_rank(20, [10, 20, 30]) is None


def test_pct_rank_none_value_returns_none():
    history = list(range(1, 51))
    assert _pct_rank(None, history) is None


def test_get_stock_revenue_yoy_positive():
    db.save_revenue_monthly_rows([
        {"ticker": "2330.TW", "year": 2025, "month": 4, "revenue": 1_000_000_000_000, "announced_date": ""},
        {"ticker": "2330.TW", "year": 2026, "month": 4, "revenue": 1_500_000_000_000, "announced_date": ""},
    ])
    yoy = _get_stock_revenue_yoy("2330.TW")
    assert yoy == pytest.approx(50.0, abs=0.01)


def test_get_stock_revenue_yoy_negative():
    db.save_revenue_monthly_rows([
        {"ticker": "2330.TW", "year": 2025, "month": 4, "revenue": 1_500_000_000_000, "announced_date": ""},
        {"ticker": "2330.TW", "year": 2026, "month": 4, "revenue": 1_000_000_000_000, "announced_date": ""},
    ])
    yoy = _get_stock_revenue_yoy("2330.TW")
    assert yoy == pytest.approx(-33.33, abs=0.05)


def test_get_stock_revenue_yoy_missing_prev_year_returns_none():
    db.save_revenue_monthly_rows([
        {"ticker": "2330.TW", "year": 2026, "month": 4, "revenue": 1_500_000_000_000, "announced_date": ""},
    ])
    assert _get_stock_revenue_yoy("2330.TW") is None


def test_get_stock_revenue_yoy_no_data_returns_none():
    assert _get_stock_revenue_yoy("2330.TW") is None
