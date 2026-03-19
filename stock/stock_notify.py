#!/usr/bin/env python3
"""Fetch stock prices and send notifications to Discord."""

import argparse
import os
import sys
import time
import requests
import yfinance as yf

def fetch_stock_price(ticker: str) -> dict:
    stock = yf.Ticker(ticker)
    # fast_info is more reliable for current price
    fast = stock.fast_info
    current_price = fast.last_price
    prev_close = fast.previous_close

    if current_price is None or prev_close is None:
        raise ValueError(f"Unable to fetch price for {ticker}")

    change = current_price - prev_close
    change_pct = (change / prev_close) * 100
    info = stock.info
    currency = info.get("currency", "")
    name = info.get("shortName") or info.get("longName") or ticker

    return {
        "ticker": ticker,
        "name": name,
        "price": current_price,
        "change": change,
        "change_pct": change_pct,
        "currency": currency,
        "prev_close": prev_close,
    }

def build_discord_message(data: dict) -> dict:
    ticker = data["ticker"]
    name = data["name"]
    price = data["price"]
    change = data["change"]
    change_pct = data["change_pct"]
    currency = data["currency"]

    arrow = "▲" if change >= 0 else "▼"
    color = 0x2ECC71 if change >= 0 else 0xE74C3C  # green / red

    if price >= 100:
        price_str = f"{price:.2f}"
    else:
        price_str = f"{price:.4f}"

    description = (
        f"**價格**: {price_str} {currency}\n"
        f"**漲跌**: {arrow} {abs(change):.2f} ({change_pct:+.2f}%)\n"
        f"**前收**: {data['prev_close']:.2f} {currency}"
    )

    embed = {
        "title": f"📈 {name} ({ticker})",
        "description": description,
        "color": color,
    }

    return {"embeds": [embed]}

def send_to_discord(webhook_url: str, payload: dict) -> None:
    resp = requests.post(webhook_url, json=payload, timeout=10)
    resp.raise_for_status()

def load_stock_list(file_path: str) -> list:
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch stock prices from a list and notify Discord.")
    parser.add_argument("--list", "-f", help="Path to stock list file", required=True)
    args = parser.parse_args()

    webhook_url = os.environ.get("DISCORD_STOCK_WEBHOOK_URL")
    if not webhook_url:
        print("Error: DISCORD_STOCK_WEBHOOK_URL environment variable not set", file=sys.stderr)
        sys.exit(1)

    tickers = load_stock_list(args.list)
    if not tickers:
        print("No stock tickers found.")
        return

    for ticker in tickers:
        print(f"Fetching price for {ticker}...")
        try:
            data = fetch_stock_price(ticker)
            print(f"{data['name']}: {data['price']:.2f} {data['currency']} ({data['change_pct']:+.2f}%)")
            
            payload = build_discord_message(data)
            send_to_discord(webhook_url, payload)
            print(f"Notification sent for {ticker}")
            # Avoid hitting Discord rate limits
            time.sleep(2)
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

if __name__ == "__main__":
    main()
