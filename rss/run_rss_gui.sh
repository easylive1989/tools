#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title RSS 管理
# @raycast.mode silent

# Optional parameters:
# @raycast.icon 📋

# Documentation:
# @raycast.description 開啟 RSS 來源管理工具
# @raycast.author wu_paul
# @raycast.authorURL https://raycast.com/wu_paul

export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

cd "$(dirname "$0")" || exit 1

uv run --python /usr/local/bin/python3.13 rss_gui.py
