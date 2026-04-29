import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
os.environ["DB_PATH"] = ":memory:"

import db
import alerts as alerts_module


def test_above_alert_triggers_and_disables(monkeypatch):
    db.init_db()
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
    db.init_db()
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
    db.init_db()
    aid = db.add_alert("indicator", "fx", "above", 32.0)
    monkeypatch.delenv("DISCORD_STOCK_WEBHOOK_URL", raising=False)

    alerts_module.check_alerts("indicator", "fx", 32.5)
    # alert should be marked triggered even without webhook
    assert db.list_alerts()[0]["enabled"] == 0


def test_disabled_alert_is_skipped(monkeypatch):
    db.init_db()
    aid = db.add_alert("indicator", "taiex", "above", 100.0)
    db.set_alert_enabled(aid, False)

    sent = []
    monkeypatch.setattr(alerts_module, "send_to_discord", lambda url, payload: sent.append(payload))
    monkeypatch.setenv("DISCORD_STOCK_WEBHOOK_URL", "http://example.invalid/hook")

    alerts_module.check_alerts("indicator", "taiex", 200.0)
    assert sent == []
