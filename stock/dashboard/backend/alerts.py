"""Price alert evaluator + Discord notifier.

Called from fetchers after each new value lands. Triggered alerts auto-disable
to prevent spam; the user re-arms from the dashboard.
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    if os.path.isdir(os.path.join(_here, "common")):
        sys.path.insert(0, _here)
        break
    _here = os.path.dirname(_here)
from common.notify import send_to_discord

from db import get_active_alerts, mark_alert_triggered

INDICATOR_LABELS = {
    "taiex":              "加權指數",
    "fx":                 "台幣兌美金",
    "fear_greed":         "恐懼與貪婪指數",
    "margin_balance":     "台股融資餘額",
    "short_balance":      "台股融券餘額",
    "short_margin_ratio": "台股券資比",
    "total_foreign_net":  "外資淨買超",
    "total_trust_net":    "投信淨買超",
    "total_dealer_net":   "自營商淨買超",
    "ndc":                "國發會景氣指標",
}

INDICATOR_UNITS = {
    "taiex":              "點",
    "fx":                 "TWD",
    "fear_greed":         "",
    "margin_balance":     "億元",
    "short_balance":      "張",
    "short_margin_ratio": "%",
    "total_foreign_net":  "億元",
    "total_trust_net":    "億元",
    "total_dealer_net":   "億元",
    "ndc":                "分",
}


def _format_value(target_type: str, target: str, value: float) -> str:
    if target_type == "indicator":
        unit = INDICATOR_UNITS.get(target, "")
        if target == "fx":
            return f"{value:.4f} {unit}".strip()
        return f"{value:,.2f} {unit}".strip()
    return f"{value:,.4f}" if value < 100 else f"{value:,.2f}"


def _build_payload(alert: dict, value: float, display_name: str) -> dict:
    crossed = "突破" if alert["condition"] == "above" else "跌破"
    color = 0xE74C3C if alert["condition"] == "above" else 0x3498DB
    value_str = _format_value(alert["target_type"], alert["target"], value)
    threshold_str = _format_value(alert["target_type"], alert["target"], alert["threshold"])

    embed = {
        "title": f"🚨 價格警示：{display_name}",
        "description": (
            f"**{display_name}** 目前 **{value_str}**，已{crossed}門檻 **{threshold_str}**。\n"
            f"_警示已自動停用，請至 Dashboard 重新啟用。_"
        ),
        "color": color,
    }
    return {"embeds": [embed]}


def check_alerts(target_type: str, target: str, value: float, display_name: str | None = None) -> None:
    """Evaluate alerts for (target_type, target) against ``value``; notify on match."""
    if value is None:
        return

    name = display_name or INDICATOR_LABELS.get(target, target)
    webhook = os.environ.get("DISCORD_STOCK_WEBHOOK_URL")

    for alert in get_active_alerts(target_type, target):
        threshold = alert["threshold"]
        cond = alert["condition"]
        triggered = (cond == "above" and value >= threshold) or \
                    (cond == "below" and value <= threshold)
        if not triggered:
            continue

        mark_alert_triggered(alert["id"], value)

        if not webhook:
            print(f"[alerts] webhook not set, skipping notification for alert {alert['id']}")
            continue
        try:
            send_to_discord(webhook, _build_payload(alert, value, name))
            print(f"[alerts] notified: {name} {cond} {threshold} (value={value})")
        except Exception as e:
            print(f"[alerts] discord error for alert {alert['id']}: {e}")
