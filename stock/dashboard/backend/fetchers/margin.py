import json
import requests
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN"
# Field name as returned by TWSE API (verified 2026-04-28)
BALANCE_FIELD = "融資今日餘額"


def fetch_margin():
    resp = requests.get(TWSE_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        print("[margin] Empty response from TWSE")
        return
    total_thousands = sum(
        int(row.get(BALANCE_FIELD, "0").replace(",", ""))
        for row in data
        if row.get(BALANCE_FIELD)
    )
    # TWSE reports in thousands of TWD → convert to 億元 (100 million)
    total_yi = total_thousands * 1000 / 1e8
    save_indicator("margin", round(total_yi, 2), json.dumps({
        "unit": "億元",
    }))
