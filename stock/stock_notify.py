#!/usr/bin/env python3
"""Fetch stock prices and send notifications to Discord."""

import argparse
import os
import sys
import time
import requests
import yfinance as yf

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common.notify import send_to_discord

def fetch_stock_price(ticker: str) -> dict:
    stock = yf.Ticker(ticker)
    
    # 改用 history 獲取價格，這是目前 yfinance 最穩定的方式
    hist = stock.history(period="5d")
    if hist.empty:
        raise ValueError(f"No history data found for {ticker}")
    
    latest_data = hist.iloc[-1]
    current_price = latest_data['Close']
    
    # 獲取前一天的收盤價
    if len(hist) >= 2:
        prev_close = hist.iloc[-2]['Close']
    else:
        # 如果只有一天數據，嘗試使用 Open 作為基準（雖然不精準但可避免報錯）
        prev_close = latest_data['Open']

    change = current_price - prev_close
    change_pct = (change / prev_close) * 100 if prev_close != 0 else 0
    
    # 針對 .info 加上保護，因為 00679B.TW 這類 ETF 容易觸發 'currentTradingPeriod' KeyError
    name = ticker
    currency = ""
    try:
        info = stock.info
        name = info.get("shortName") or info.get("longName") or ticker
        currency = info.get("currency", "")
    except Exception as e:
        print(f"Warning: Could not fetch metadata for {ticker} via .info: {e}")
        # 如果失敗，嘗試從 history metadata 獲取一些資訊
        try:
            currency = stock.history_metadata.get('currency', '')
        except:
            pass

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
