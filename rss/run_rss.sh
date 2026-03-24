#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Run RSS
# @raycast.mode silent

# Optional parameters:
# @raycast.icon 🤖

# Documentation:
# @raycast.description Run RSS
# @raycast.author wu_paul
# @raycast.authorURL https://raycast.com/wu_paul

# 確保 Raycast 可以找到 uv 指令 (適用於 Homebrew, pipx 或 rust/cargo 的預設安裝路徑)
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

# 切換到腳本所在的目錄，確保各種相對路徑處理（例如讀取 rss_list.txt）能夠正常運作
cd "$(dirname "$0")" || exit 1

# 透過 uv 執行 Python 腳本，uv 會自動讀取並安裝 rss.py 頂部宣告的依賴
echo "開始執行 RSS 同步..."
uv run rss.py
