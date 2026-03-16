#!/usr/bin/env python3
"""Fetch stock price and send notification to Discord."""

import argparse
import os
import sys

import requests
import yfinance as yf


def fetch_stock_price(ticker: str) -> dict:
    stock = yf.Ticker(ticker)
    info = stock.info

    # fast_info is more reliable for current price
    fast = stock.fast_info
    current_price = fast.last_price
    prev_close = fast.previous_close

    if current_price is None or prev_close is None:
        raise ValueError(f"Unable to fetch price for {ticker}")

    change = current_price - prev_close
    change_pct = (change / prev_close) * 100
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

    # Format price with appropriate decimals
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch stock price and notify Discord.")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g. VOO, 0050.TW)")
    args = parser.parse_args()

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("Error: DISCORD_WEBHOOK_URL environment variable not set", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching price for {args.ticker}...")
    data = fetch_stock_price(args.ticker)
    print(
        f"{data['name']}: {data['price']:.2f} {data['currency']} "
        f"({data['change_pct']:+.2f}%)"
    )

    payload = build_discord_message(data)
    send_to_discord(webhook_url, payload)
    print("Discord notification sent.")


if __name__ == "__main__":
    main()
