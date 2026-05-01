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


def _check_streak(values: list, condition: str, threshold: float) -> bool:
    """檢查 values 是否全部達門檻(streak_above 全 >= threshold,streak_below 全 <= threshold)。

    values 中含 None 視為「資料不足」,直接 False(不允許部分)。
    給空 list 也 False。
    condition 不是 streak_above / streak_below 也 False。
    """
    if condition not in ('streak_above', 'streak_below'):
        return False
    if not values or any(v is None for v in values):
        return False
    if condition == 'streak_above':
        return all(v >= threshold for v in values)
    return all(v <= threshold for v in values)


# --- 個股 daily 指標查詢路由 ---

# Phase 4 個股 daily 指標 → 對應 stock_*_daily 表 + 衍生計算規則
_PER_KEYS = {"per", "pbr", "dividend_yield"}
_CHIP_NET_KEYS = {"foreign_net", "trust_net", "dealer_net"}
_CHIP_BAL_KEYS = {"margin_balance", "short_balance"}

STOCK_INDICATOR_KEYS = _PER_KEYS | _CHIP_NET_KEYS | _CHIP_BAL_KEYS


def _get_stock_indicator_history(ticker: str, indicator_key: str, n: int) -> list[float]:
    """從 stock_per_daily / stock_chip_daily 取最近 n 個非 None 值,舊→新排序。"""
    if indicator_key not in STOCK_INDICATOR_KEYS:
        return []

    from datetime import datetime, timedelta, timezone
    from db import get_per_daily_range, get_chip_daily_range
    since_date = (datetime.now(timezone.utc).date() - timedelta(days=n * 3 + 30)).isoformat()

    if indicator_key in _PER_KEYS:
        rows = get_per_daily_range(ticker, since_date)
        values = [r[indicator_key] for r in rows]
    elif indicator_key in _CHIP_NET_KEYS:
        rows = get_chip_daily_range(ticker, since_date)
        bs_prefix = indicator_key[:-4]   # 'foreign_net' → 'foreign'
        values = []
        for r in rows:
            buy, sell = r[f"{bs_prefix}_buy"], r[f"{bs_prefix}_sell"]
            if buy is None or sell is None:
                values.append(None)
            else:
                values.append(buy - sell)
    else:  # margin_balance / short_balance
        rows = get_chip_daily_range(ticker, since_date)
        values = [r[indicator_key] for r in rows]

    clean = [v for v in values if v is not None]
    return clean[-n:]


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
