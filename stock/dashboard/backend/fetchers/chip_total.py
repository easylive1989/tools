"""整體市場籌碼面 fetcher。

從 FinMind 抓:
- TaiwanStockTotalMarginPurchaseShortSale (整體融資融券)
- TaiwanStockTotalInstitutionalInvestors  (整體三大法人)  ← Task 2 加上

不帶 data_id,免費 quota 內每日 1-2 個 request 即可。
寫入 indicator_snapshots 沿用既有 indicator pipeline。
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator
from alerts import check_alerts

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()


def _request(dataset: str, start_date: str, end_date: str | None = None) -> list[dict]:
    params = {"dataset": dataset, "start_date": start_date}
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


def parse_total_margin(rows: list[dict]) -> dict[str, dict[str, float]]:
    """Long-format → {date: {margin_balance, short_balance, short_margin_ratio}}.

    rows 每筆有 name in {MarginPurchase, MarginPurchaseMoney, ShortSale}。
    margin_balance 取自 MarginPurchaseMoney.TodayBalance(元 → 億元),
    short_balance  取自 ShortSale.TodayBalance(張),
    short_margin_ratio = ShortSale.TodayBalance / MarginPurchase.TodayBalance × 100。
    """
    by_day: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        d = r.get("date")
        n = r.get("name")
        if not d or not n:
            continue
        by_day[d][n] = r

    result: dict[str, dict[str, float]] = {}
    for d, names in by_day.items():
        margin_money = names.get("MarginPurchaseMoney")
        margin_lots  = names.get("MarginPurchase")
        short        = names.get("ShortSale")
        if not (margin_money and margin_lots and short):
            continue
        margin_balance = round(float(margin_money["TodayBalance"]) / 1e8, 3)  # 元 → 億元
        short_balance = float(short["TodayBalance"])
        margin_lots_balance = float(margin_lots["TodayBalance"])
        ratio = round(short_balance / margin_lots_balance * 100, 3) if margin_lots_balance else 0
        result[d] = {
            "margin_balance":     margin_balance,
            "short_balance":      short_balance,
            "short_margin_ratio": ratio,
        }
    return result


def fetch_chip_total(start_date: str | None = None, end_date: str | None = None) -> None:
    """每日 cron 用:預設抓最近 5 天(涵蓋週末跳天),寫入 indicator_snapshots。

    Backfill 用:傳 start_date / end_date(YYYY-MM-DD)拉指定區間。
    """
    if not start_date:
        from datetime import timedelta
        start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

    # --- 整體融資融券 ---
    try:
        raw = _request("TaiwanStockTotalMarginPurchaseShortSale", start_date, end_date)
    except Exception as e:
        print(f"[chip_total] margin fetch error: {e}")
        return
    margin_by_day = parse_total_margin(raw)

    for d, vals in sorted(margin_by_day.items()):
        ts = datetime.strptime(d, "%Y-%m-%d")
        save_indicator("margin_balance",     vals["margin_balance"],
                       json.dumps({"unit": "億元", "date": d}), timestamp=ts)
        save_indicator("short_balance",      vals["short_balance"],
                       json.dumps({"unit": "張", "date": d}), timestamp=ts)
        save_indicator("short_margin_ratio", vals["short_margin_ratio"],
                       json.dumps({"unit": "%", "date": d}), timestamp=ts)
    if margin_by_day:
        latest = max(margin_by_day.keys())
        check_alerts("indicator", "margin_balance",     margin_by_day[latest]["margin_balance"])
        check_alerts("indicator", "short_balance",      margin_by_day[latest]["short_balance"])
        check_alerts("indicator", "short_margin_ratio", margin_by_day[latest]["short_margin_ratio"])
        print(f"[chip_total] margin {latest}: balance={margin_by_day[latest]['margin_balance']} 億, "
              f"short={margin_by_day[latest]['short_balance']:.0f} 張, "
              f"ratio={margin_by_day[latest]['short_margin_ratio']:.2f}%")
