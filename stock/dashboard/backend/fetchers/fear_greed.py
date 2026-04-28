import json
import requests
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator

# macromicro.me Fear & Greed Index chart ID 128747
FEAR_GREED_URL = "https://api.macromicro.me/charts/128747"
HEADERS = {"Referer": "https://www.macromicro.me/"}


def _value_to_label(v: float) -> str:
    if v < 25:
        return "極度恐懼"
    if v < 45:
        return "恐懼"
    if v < 55:
        return "中立"
    if v < 75:
        return "貪婪"
    return "極度貪婪"


def fetch_fear_greed():
    try:
        resp = requests.get(FEAR_GREED_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[fear_greed] Failed to fetch from macromicro.me: {e}")
        return

    try:
        payload = resp.json()
    except ValueError as e:
        print(f"[fear_greed] Invalid JSON response: {e}")
        return

    # Extract data array from response
    series = payload.get("data", [])
    if not series:
        print("[fear_greed] Empty data from macromicro.me")
        return

    # Expected format: [[timestamp, value], ...]
    # Find the entry with the highest timestamp (most recent)
    latest_entry = None
    try:
        # Filter to valid entries and sort by timestamp (descending)
        valid_entries = [
            entry for entry in series
            if isinstance(entry, (list, tuple)) and len(entry) >= 2
        ]
        if not valid_entries:
            print("[fear_greed] No valid entries in data")
            return
        latest_entry = max(valid_entries, key=lambda x: x[0])
    except (TypeError, ValueError) as e:
        print(f"[fear_greed] Error processing data entries: {e}")
        return

    try:
        value = float(latest_entry[1])
    except (IndexError, TypeError, ValueError) as e:
        print(f"[fear_greed] Could not parse value from entry: {e}")
        return

    save_indicator(
        "fear_greed",
        value,
        json.dumps({"label": _value_to_label(value)})
    )
