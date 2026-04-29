"""台股融資餘額（融資金額，億元）。

TWSE CSV 優先（www.twse.com.tw，可能被 VPS IP 封鎖）；
失敗時嘗試 cloudscraper 繞過；
兩者都失敗則略過。
"""
import csv
import io
import json
import requests
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator
from alerts import check_alerts

TWSE_CSV_BASE = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=csv&selectType=MS"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.twse.com.tw/zh/",
}


def _parse_margin_csv(text: str) -> float | None:
    """從 TWSE CSV 取出「融資金額(仟元)」今日餘額，回傳億元。"""
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        label = row[0].strip().strip('"')
        if "融資金額" in label and "仟元" in label:
            try:
                balance = int(row[5].replace(",", "").replace('"', "").strip())
                return round(balance / 100_000, 2)  # 千元 → 億元
            except (IndexError, ValueError):
                return None
    return None


def _fetch_csv(url: str) -> str | None:
    # cloudscraper 優先（能繞過 TWSE 的 IP 封鎖）
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper()
        r = scraper.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=20)
        r.encoding = "ms950"
        if "融資金額" in r.text:
            return r.text
    except Exception:
        pass

    # fallback: requests
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        r.encoding = "ms950"
        if "融資金額" in r.text:
            return r.text
    except Exception:
        pass

    return None


def fetch_margin(date_str: str | None = None):
    url = TWSE_CSV_BASE
    if date_str:
        url += f"&date={date_str}"

    text = _fetch_csv(url)
    if text is None:
        print(f"[margin] 無法取得資料（date={date_str or '今日'}），TWSE 可能封鎖此 IP")
        return

    value = _parse_margin_csv(text)
    if value is None:
        print(f"[margin] 解析失敗（date={date_str or '今日'}）")
        return

    ts = None
    if date_str:
        ts = datetime(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))

    save_indicator("margin", value, json.dumps({"unit": "億元"}), timestamp=ts)
    check_alerts("indicator", "margin", value)
    print(f"[margin] {date_str or '今日'} 融資餘額 = {value} 億元")
