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


def _check_streak(values: list, condition: str, threshold: float,
                  expected_n: int | None = None) -> bool:
    """檢查 values 是否全部達門檻(streak_above 全 >= threshold,streak_below 全 <= threshold)。

    values 中含 None 視為「資料不足」,直接 False。給空 list 也 False。
    expected_n 給定時:len(values) < expected_n 也 False(避免歷史不足卻誤觸發)。
    condition 不是 streak_above / streak_below 也 False。
    """
    if condition not in ('streak_above', 'streak_below'):
        return False
    if not values or any(v is None for v in values):
        return False
    if expected_n is not None and len(values) < expected_n:
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


def _pct_rank(value: float | None, history: list[float]) -> float | None:
    """Inclusive percentile rank: count(v <= value) / total * 100。

    history < 30 點(避免新上市股誤觸發)→ None。value=None → None。
    history 中的 None 過濾掉。
    """
    if value is None or len(history) < 30:
        return None
    clean = [v for v in history if v is not None]
    if len(clean) < 30:
        return None
    below = sum(1 for v in clean if v <= value)
    return round(below / len(clean) * 100, 2)


def _get_stock_revenue_yoy(ticker: str) -> float | None:
    """從 stock_revenue_monthly 取最新月 vs 去年同月,算 YoY %。

    缺資料(新上市股、去年同期沒值、去年同期 = 0)→ None。
    """
    from db import get_revenue_monthly_range, get_latest_revenue_ym
    latest = get_latest_revenue_ym(ticker)
    if not latest:
        return None
    y, m = latest
    rows = get_revenue_monthly_range(ticker, y - 1, m)
    by_ym = {(r["year"], r["month"]): r["revenue"] for r in rows}
    cur = by_ym.get((y, m))
    prev = by_ym.get((y - 1, m))
    if cur is None or not prev:
        return None
    return round((cur - prev) / prev * 100, 2)


QUARTERLY_INDICATOR_TYPES = {
    "q_eps":              ("income",    "EPS"),
    "q_revenue":          ("income",    "Revenue"),
    "q_operating_income": ("income",    "OperatingIncome"),
    "q_net_income":       ("income",    "IncomeAfterTaxes"),
    "q_operating_cf":     ("cash_flow", "CashFlowsFromOperatingActivities"),
}
YEARLY_INDICATOR_KEYS = {"y_cash_dividend", "y_stock_dividend"}


def _get_stock_quarterly_yoy(ticker: str, indicator_key: str) -> float | None:
    """從 stock_financial_quarterly 拉同一 (report_type, type) 序列,取最新季 vs 去年同季。

    缺資料 / 缺去年同季 / prev=0 → None。
    """
    if indicator_key not in QUARTERLY_INDICATOR_TYPES:
        return None
    report_type, type_name = QUARTERLY_INDICATOR_TYPES[indicator_key]

    from datetime import datetime, timezone
    from db import get_financial_quarterly_range
    today = datetime.now(timezone.utc).date()
    # 拉近 3 年(足夠覆蓋去年同季 + buffer)
    since = today.replace(year=today.year - 3, month=1, day=1).isoformat()
    rows = get_financial_quarterly_range(ticker, report_type, since)
    same_type = [(r["date"], r["value"]) for r in rows
                 if r["type"] == type_name and r["value"] is not None]
    if not same_type:
        return None
    same_type.sort(key=lambda x: x[0])
    latest_date, latest_value = same_type[-1]

    dt = datetime.strptime(latest_date, "%Y-%m-%d")
    target_prev_date = f"{dt.year - 1}-{dt.month:02d}-{dt.day:02d}"
    prev_value = next((v for d, v in same_type if d == target_prev_date), None)
    if prev_value is None or prev_value == 0:
        return None
    return round((latest_value - prev_value) / prev_value * 100, 2)


def _get_stock_yearly_yoy(ticker: str, indicator_key: str) -> float | None:
    """從 stock_dividend_history aggregate by 西元年(parse "114年第N季" → 2025),
    比較最新年 vs 去年。"""
    if indicator_key not in YEARLY_INDICATOR_KEYS:
        return None
    from db import get_dividend_history
    raw_rows = get_dividend_history(ticker)
    if not raw_rows:
        return None

    field = "cash_dividend" if indicator_key == "y_cash_dividend" else "stock_dividend"

    import re
    by_year: dict[int, float] = {}
    for r in raw_rows:
        m = re.match(r"^(\d{2,3})年", r.get("year") or "")
        if not m:
            continue
        ce_year = int(m.group(1)) + 1911
        v = r.get(field) or 0
        by_year[ce_year] = by_year.get(ce_year, 0) + v

    if len(by_year) < 2:
        return None
    sorted_years = sorted(by_year.keys())
    latest_year = sorted_years[-1]
    prev_year = latest_year - 1
    cur = by_year.get(latest_year)
    prev = by_year.get(prev_year)
    if cur is None or not prev:
        return None
    return round((cur - prev) / prev * 100, 2)


def _format_value(target_type: str, target: str, value: float) -> str:
    if target_type == "indicator":
        unit = INDICATOR_UNITS.get(target, "")
        if target == "fx":
            return f"{value:.4f} {unit}".strip()
        return f"{value:,.2f} {unit}".strip()
    return f"{value:,.4f}" if value < 100 else f"{value:,.2f}"


# 個股 indicator 顯示用中文 label
STOCK_INDICATOR_LABELS = {
    "per":              "PER",
    "pbr":              "PBR",
    "dividend_yield":   "殖利率",
    "foreign_net":      "外資淨買",
    "trust_net":        "投信淨買",
    "dealer_net":       "自營淨買",
    "margin_balance":   "融資餘額",
    "short_balance":    "融券餘額",
}


def _latest_indicator_history(indicator: str, n: int) -> list[float]:
    """取整體 indicator 最近 n 個值(舊→新)。"""
    from datetime import datetime, timedelta, timezone
    from db import get_indicator_history
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(n * 3, 30))
    rows = get_indicator_history(indicator, since)
    values = [r["value"] for r in rows if r["value"] is not None]
    return values[-n:]


def _alert_display_name(target_type: str, target: str, indicator_key: str | None) -> str:
    if target_type == "indicator":
        return INDICATOR_LABELS.get(target, target)
    if target_type == "stock_indicator":
        ik_label = STOCK_INDICATOR_LABELS.get(indicator_key, indicator_key or "")
        return f"{target} {ik_label}"
    # stock
    return target


def _build_payload(alert: dict, value: float | None, display_name: str) -> dict:
    cond = alert["condition"]
    threshold = alert["threshold"]
    window_n = alert.get("window_n")
    target_type = alert["target_type"]

    def _fmt(v: float) -> str:
        if v is None:
            return "—"
        if target_type == "indicator":
            return _format_value(target_type, alert["target"], v)
        if target_type == "stock_indicator":
            ik = alert.get("indicator_key")
            if ik in ("per", "pbr"):
                return f"{v:.2f}"
            if ik == "dividend_yield":
                return f"{v:.2f}%"
            if ik == "revenue":
                return f"{v:.2f}%"   # revenue alert 多為 yoy_*,顯示 %
            return f"{v:,.0f}"
        # stock
        return f"{v:,.4f}" if v < 100 else f"{v:,.2f}"

    value_str = _fmt(value) if value is not None else "—"
    threshold_str = _fmt(threshold)

    if cond == "above":
        crossed = "突破"
        color = 0xE74C3C
    elif cond == "below":
        crossed = "跌破"
        color = 0x3498DB
    elif cond == "streak_above":
        crossed = f"連 {window_n} 日突破"
        color = 0xE74C3C
    elif cond == "streak_below":
        crossed = f"連 {window_n} 日跌破"
        color = 0x3498DB
    elif cond == "percentile_above":
        crossed = "5y 百分位突破"
        color = 0xE74C3C
    elif cond == "percentile_below":
        crossed = "5y 百分位跌破"
        color = 0x3498DB
    elif cond == "yoy_above":
        crossed = "YoY 突破"
        color = 0xE74C3C
    elif cond == "yoy_below":
        crossed = "YoY 跌破"
        color = 0x3498DB
    else:
        crossed = cond
        color = 0x95A5A6

    embed = {
        "title": f"🚨 警示:{display_name}",
        "description": (
            f"**{display_name}** 目前 **{value_str}**,已{crossed}門檻 **{threshold_str}**。\n"
            f"_警示已自動停用,請至 Dashboard 重新啟用。_"
        ),
        "color": color,
    }
    return {"embeds": [embed]}


def check_alerts(target_type: str, target: str, value: float | None = None,
                 *, indicator_key: str | None = None, display_name: str | None = None) -> None:
    """評估 alerts 並 notify。

    Routing by (target_type, condition):
    - target_type='indicator', condition='above'/'below'  → value 跟 threshold 比(沿用既有)
    - target_type='indicator', condition='streak_above'/'streak_below'
        → _latest_indicator_history(target, alert.window_n) 跟 threshold 比
    - target_type='stock_indicator', condition='above'/'below'
        → _get_stock_indicator_history(target, indicator_key, 1) 取最新值跟 threshold 比
    - target_type='stock_indicator', condition='streak_above'/'streak_below'
        → _get_stock_indicator_history(target, indicator_key, alert.window_n) 跟 threshold 比
    - target_type='stock', condition='above'/'below'  → value 跟 threshold 比(沿用既有)

    觸發後 mark_alert_triggered 並送 Discord。
    """
    from db import get_active_alerts, mark_alert_triggered

    all_active = get_active_alerts(target_type, target)
    if target_type == "stock_indicator":
        active_alerts = [a for a in all_active if a.get("indicator_key") == indicator_key]
    else:
        active_alerts = all_active

    name = display_name or _alert_display_name(target_type, target, indicator_key)
    webhook = os.environ.get("DISCORD_STOCK_WEBHOOK_URL")

    for alert in active_alerts:
        threshold = alert["threshold"]
        cond = alert["condition"]
        triggered_value = None

        if cond in ("above", "below"):
            cur_value = value
            if target_type == "stock_indicator":
                hist = _get_stock_indicator_history(target, indicator_key, 1)
                cur_value = hist[-1] if hist else None
            if cur_value is None:
                continue
            triggered = ((cond == "above" and cur_value >= threshold) or
                         (cond == "below" and cur_value <= threshold))
            triggered_value = cur_value if triggered else None
        elif cond in ("streak_above", "streak_below"):
            window_n = alert.get("window_n") or 5
            if target_type == "indicator":
                hist = _latest_indicator_history(target, window_n)
            elif target_type == "stock_indicator":
                hist = _get_stock_indicator_history(target, indicator_key, window_n)
            else:
                continue   # streak 不適用於 stock 價格(沒有 history 表)
            triggered = _check_streak(hist, cond, threshold, expected_n=window_n)
            triggered_value = hist[-1] if (triggered and hist) else None
        elif cond in ("percentile_above", "percentile_below"):
            # 只支援 daily indicator(per/pbr/dividend_yield)
            if target_type != "stock_indicator" or indicator_key not in {"per", "pbr", "dividend_yield"}:
                continue
            hist = _get_stock_indicator_history(target, indicator_key, 1825)
            cur_value = hist[-1] if hist else None
            rank = _pct_rank(cur_value, hist)
            if rank is None:
                continue
            triggered = ((cond == "percentile_above" and rank >= threshold) or
                         (cond == "percentile_below" and rank <= threshold))
            triggered_value = rank if triggered else None
        elif cond in ("yoy_above", "yoy_below"):
            # 只支援 monthly indicator(目前僅 revenue)
            if target_type != "stock_indicator" or indicator_key != "revenue":
                continue
            yoy = _get_stock_revenue_yoy(target)
            if yoy is None:
                continue
            triggered = ((cond == "yoy_above" and yoy >= threshold) or
                         (cond == "yoy_below" and yoy <= threshold))
            triggered_value = yoy if triggered else None
        else:
            continue

        if not triggered:
            continue

        mark_alert_triggered(alert["id"], triggered_value)
        if not webhook:
            print(f"[alerts] webhook not set, skipping notification for alert {alert['id']}")
            continue
        try:
            send_to_discord(webhook, _build_payload(alert, triggered_value, name))
            print(f"[alerts] notified: {name} {cond} {threshold} (value={triggered_value})")
        except Exception as e:
            print(f"[alerts] discord error for alert {alert['id']}: {e}")
