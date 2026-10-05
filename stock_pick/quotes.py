"""Official Taiwan stock quotes: 上市 (TWSE), 上櫃 and 興櫃 (TPEx).

The screenshot only tells us which stocks were picked; codes and prices always
come from here. 興櫃 has no official close, so its latest trade price stands in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import requests

TWSE_DAILY = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_OTC = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
TPEX_ESB = "https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics"
HEADERS = {"User-Agent": "Mozilla/5.0 (stock-pick-logger)", "Accept": "application/json"}

READY, WAITING, PASSED = "ready", "waiting", "passed"


@dataclass(frozen=True)
class Quote:
    code: str
    name: str
    market: str
    price: float | None


@dataclass(frozen=True)
class MarketQuotes:
    days: dict[str, date | None]
    by_name: dict[str, Quote]


def normalize_name(name: object) -> str:
    """Drop every kind of whitespace, including full-width spaces."""
    return "".join(str(name).split())


def to_price(value: object) -> float | None:
    try:
        number = float(str(value).replace(",", "").strip())
    except ValueError:
        return None
    return number if number > 0 else None


def roc_date(value: object) -> date:
    found = re.fullmatch(r"(\d{2,3})(\d{2})(\d{2})", str(value).strip())
    if not found:
        raise ValueError(f"無法解析民國日期：{value!r}")
    return date(int(found[1]) + 1911, int(found[2]), int(found[3]))


def parse_twse(payload: object, day: date) -> list[Quote] | None:
    """Return 上市 quotes for `day`, or None when TWSE has nothing for it (yet)."""
    if not isinstance(payload, dict) or str(payload.get("stat")).upper() != "OK":
        return None
    if str(payload.get("date")) != f"{day:%Y%m%d}":
        raise ValueError(f"上市行情日期不符：要 {day}，拿到 {payload.get('date')}")
    for table in payload.get("tables") or []:
        fields = [str(field).strip() for field in table.get("fields") or []]
        if {"證券代號", "證券名稱", "收盤價"} <= set(fields) and table.get("data"):
            code_at = fields.index("證券代號")
            name_at = fields.index("證券名稱")
            price_at = fields.index("收盤價")
            return [
                Quote(str(row[code_at]).strip(), normalize_name(row[name_at]), "上市",
                      to_price(row[price_at]))
                for row in table["data"]
            ]
    raise ValueError(f"{day} 的上市行情裡找不到收盤行情表")


def parse_tpex(rows: object, market: str, price_key: str) -> tuple[date | None, list[Quote]]:
    """Return (quote day, quotes) from a TPEx openapi list, which only serves the latest day."""
    if not isinstance(rows, list):
        raise ValueError(f"{market}行情格式不正確")
    if not rows:
        return None, []
    day = max(roc_date(row["Date"]) for row in rows)
    quotes = [
        Quote(str(row["SecuritiesCompanyCode"]).strip(), normalize_name(row["CompanyName"]),
              market, to_price(row.get(price_key)))
        for row in rows if roc_date(row["Date"]) == day
    ]
    return day, quotes


def fetch_quotes(day: date) -> MarketQuotes:
    twse = parse_twse(_get_json(TWSE_DAILY, {
        "date": f"{day:%Y%m%d}", "response": "json", "type": "ALLBUT0999",
    }), day)
    otc_day, otc = parse_tpex(_get_json(TPEX_OTC), "上櫃", "Close")
    esb_day, esb = parse_tpex(_get_json(TPEX_ESB), "興櫃", "LatestPrice")
    by_name: dict[str, Quote] = {}
    for quote in [*(twse or []), *otc, *esb]:
        by_name.setdefault(quote.name, quote)
    return MarketQuotes(
        days={"上市": day if twse is not None else None, "上櫃": otc_day, "興櫃": esb_day},
        by_name=by_name,
    )


def quote_status(days: dict[str, date | None], day: date) -> str:
    known = [value for value in days.values() if value is not None]
    if any(value > day for value in known):
        return PASSED
    if len(known) == len(days) and all(value == day for value in known):
        return READY
    return WAITING


def match(names: list[str], by_name: dict[str, Quote]) -> tuple[list[Quote], list[str]]:
    """Split names into quotes with a price and the names that have none."""
    found: list[Quote] = []
    missing: list[str] = []
    for name in names:
        quote = by_name.get(normalize_name(name))
        if quote is None or quote.price is None:
            missing.append(name)
        else:
            found.append(quote)
    return found, missing


def _get_json(url: str, params: dict | None = None) -> object:
    response = requests.get(url, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()
