#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Translation
# @raycast.mode silent

# Optional parameters:
# @raycast.icon 🤖

# Documentation:
# @raycast.description Translation
# @raycast.author wu_paul
# @raycast.authorURL https://raycast.com/wu_paul

# 啟動 Gemini 隨身翻譯 GUI
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
uv run --python "$(which python3)" "$SCRIPT_DIR/translator.py" &
