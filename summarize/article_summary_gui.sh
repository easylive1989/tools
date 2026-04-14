#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Article Summary
# @raycast.mode silent

# Optional parameters:
# @raycast.icon 📰

# Documentation:
# @raycast.description Article Summary
# @raycast.author wu_paul
# @raycast.authorURL https://raycast.com/wu_paul

export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BINARY="$SCRIPT_DIR/article_summary_app"
SOURCE="$SCRIPT_DIR/article_summary.swift"

# 若 binary 不存在或 source 較新則重新編譯
if [ ! -f "$BINARY" ] || [ "$SOURCE" -nt "$BINARY" ]; then
    swiftc "$SOURCE" -o "$BINARY"
fi

PID_FILE="/tmp/article_summary_gui_${USER}.pid"

# 若程式已在執行，直接帶到前景
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill -USR1 "$PID"
        exit 0
    fi
fi

# 啟動新 instance
nohup "$BINARY" >/dev/null 2>&1 &
disown $!
