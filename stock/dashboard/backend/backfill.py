"""一次性執行：補齊歷史資料到 SQLite DB。"""
import json
import re
import sys
import os
from datetime import datetime, timezone, timedelta

import yfinance as yf
import cloudscraper

sys.path.insert(0, os.path.dirname(__file__))
from db import init_db, get_connection, save_indicator

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "stock_dashboard.db"))


def _ts(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat()


def backfill_yfinance(ticker_symbol: str, indicator: str, extra_fn, period: str = "2y"):
    print(f"[backfill] {indicator} from yfinance {ticker_symbol} …")
    hist = yf.Ticker(ticker_symbol).history(period=period)
    if hist.empty:
        print(f"  No data")
        return
    inserted = 0
    with get_connection() as conn:
        for ts, row in hist.iterrows():
            price = float(row["Close"])
            dt = ts.to_pydatetime().replace(tzinfo=None)
            extra = extra_fn(price, hist, ts)
            conn.execute(
                "INSERT OR IGNORE INTO indicator_snapshots (indicator, timestamp, value, extra_json) VALUES (?,?,?,?)",
                (indicator, dt.isoformat(), price, json.dumps(extra)),
            )
            inserted += 1
    print(f"  Inserted {inserted} rows for {indicator}")


def backfill_taiex():
    def extra(price, hist, ts):
        idx = hist.index.get_loc(ts)
        prev = float(hist.iloc[idx - 1]["Close"]) if idx > 0 else price
        pct = round((price - prev) / prev * 100, 2) if prev else 0
        return {"change_pct": pct, "prev_close": round(prev, 2)}
    backfill_yfinance("^TWII", "taiex", extra)


def backfill_fx():
    def extra(price, hist, ts):
        idx = hist.index.get_loc(ts)
        prev = float(hist.iloc[idx - 1]["Close"]) if idx > 0 else price
        pct = round((price - prev) / prev * 100, 4) if prev else 0
        return {"change_pct": pct, "prev_close": round(prev, 4)}
    backfill_yfinance("TWD=X", "fx", extra)


def backfill_ndc():
    print("[backfill] ndc from NDC API …")
    NDC_PAGE_URL = "https://index.ndc.gov.tw/n/zh_tw/data/eco"
    NDC_API_URL = "https://index.ndc.gov.tw/n/json/data/eco/indicators"
    LIGHT_NAMES = {1: "藍燈", 2: "黃藍燈", 3: "綠燈", 4: "黃紅燈", 5: "紅燈"}

    scraper = cloudscraper.create_scraper()
    page = scraper.get(NDC_PAGE_URL, timeout=20)
    match = re.search(r'csrf-token[^>]*content=["\']([^"\']+)', page.text)
    if not match:
        print("  Cannot find CSRF token")
        return
    csrf = match.group(1)
    headers = {
        "X-CSRF-TOKEN": csrf,
        "Content-Type": "application/json",
        "Referer": NDC_PAGE_URL,
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = scraper.post(NDC_API_URL, headers=headers, json={}, timeout=30)
    data = resp.json()
    line = data.get("line", {})
    score_series = line.get("12", {}).get("data", [])
    light_series = line.get("2", {}).get("data", [])

    # 建立 x→light_code 快查表
    light_map = {d["x"]: int(d["y"]) for d in light_series if d.get("y") is not None}

    # 只補近 5 年資料
    cutoff_x = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y%m")
    rows = [d for d in score_series if d.get("y") is not None and d.get("x", "") >= cutoff_x]

    inserted = 0
    with get_connection() as conn:
        for d in rows:
            x = d["x"]  # YYYYMM
            score = float(d["y"])
            year, month = int(x[:4]), int(x[4:])
            dt = datetime(year, month, 1)
            light_code = light_map.get(x, 0)
            light_name = LIGHT_NAMES.get(light_code, "未知")
            period = f"{x[:4]}/{x[4:]}"
            conn.execute(
                "INSERT OR IGNORE INTO indicator_snapshots (indicator, timestamp, value, extra_json) VALUES (?,?,?,?)",
                ("ndc", dt.isoformat(), score, json.dumps({
                    "light": light_name, "light_code": light_code, "period": period
                })),
            )
            inserted += 1
    print(f"  Inserted {inserted} rows for ndc")


def backfill_fear_greed():
    """從 CNN API 補近一年 Fear & Greed 歷史資料。"""
    print("[backfill] fear_greed from CNN …")
    from fetchers.fear_greed import CNN_URL, HEADERS, _label
    resp = __import__("requests").get(CNN_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    historical = data.get("fear_and_greed_historical", {}).get("data", [])
    if not historical:
        print("  No historical data")
        return
    inserted = 0
    with get_connection() as conn:
        for point in historical:
            ts_ms = point.get("x")
            score = point.get("y")
            rating = point.get("rating", "")
            if ts_ms is None or score is None:
                continue
            dt = datetime.fromtimestamp(ts_ms / 1000)
            conn.execute(
                "INSERT OR IGNORE INTO indicator_snapshots (indicator, timestamp, value, extra_json) VALUES (?,?,?,?)",
                ("fear_greed", dt.isoformat(), round(float(score), 1),
                 json.dumps({"label": _label(rating), "rating_en": rating})),
            )
            inserted += 1
    print(f"  Inserted {inserted} rows for fear_greed")


def backfill_margin(days: int = 365):
    """逐日查詢 TWSE CSV 補歷史融資餘額（只查交易日，跳過無資料的日期）。"""
    from fetchers.margin import fetch_margin
    print(f"[backfill] margin 近 {days} 天 …")
    today = datetime.now()
    inserted = 0
    for i in range(days, 0, -1):
        dt = today - timedelta(days=i)
        if dt.weekday() >= 5:  # 跳過週末
            continue
        date_str = dt.strftime("%Y%m%d")
        fetch_margin(date_str)
        inserted += 1
    print(f"  嘗試查詢 {inserted} 個交易日（有資料才寫入）")


if __name__ == "__main__":
    import sys as _sys
    init_db()
    if len(_sys.argv) > 1 and _sys.argv[1] == "margin":
        backfill_margin(int(_sys.argv[2]) if len(_sys.argv) > 2 else 365)
    elif len(_sys.argv) > 1 and _sys.argv[1] == "fear_greed":
        backfill_fear_greed()
    else:
        backfill_taiex()
        backfill_fx()
        backfill_ndc()
        backfill_fear_greed()
        backfill_margin(365)
    print("[backfill] Done.")
