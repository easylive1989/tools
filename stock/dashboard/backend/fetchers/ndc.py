import csv
import io
import json
import requests
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator

NDC_URL = "https://index.ndc.gov.tw/n/zh_tw/download/eco/cycle"
SCORE_COL = "景氣綜合判斷分數"
DATE_COL = "年月"


def _score_to_light(score: int) -> tuple[str, int]:
    if score <= 9:
        return "藍燈", 1
    if score <= 16:
        return "黃藍燈", 2
    if score <= 23:
        return "綠燈", 3
    if score <= 31:
        return "黃紅燈", 4
    return "紅燈", 5


def fetch_ndc():
    resp = requests.get(NDC_URL, timeout=20)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    rows = [r for r in reader if r.get(SCORE_COL, "").strip()]
    if not rows:
        print("[ndc] No data rows found")
        return
    latest = rows[0]  # assume newest first; reverse if needed
    score = int(latest[SCORE_COL].strip())
    light, light_code = _score_to_light(score)
    save_indicator("ndc", float(score), json.dumps({
        "light": light,
        "light_code": light_code,
        "period": latest.get(DATE_COL, ""),
    }))
