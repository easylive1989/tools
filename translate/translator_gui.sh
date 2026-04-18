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
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BINARY="$SCRIPT_DIR/translator_app"
SOURCE="$SCRIPT_DIR/translator.swift"

# 用 build stamp 綁定「OS 版本 + source mtime」：任何一項改變就重編。
# 這樣可避免 binary 被帶到不同 macOS 版本時因 dyld 不相容而無法啟動。
STAMP_FILE="$BINARY.stamp"
OS_VERSION="$(sw_vers -productVersion 2>/dev/null || echo unknown)"
SOURCE_MTIME="$(stat -f %m "$SOURCE" 2>/dev/null || echo 0)"
EXPECTED_STAMP="${OS_VERSION}|${SOURCE_MTIME}"
CURRENT_STAMP="$(cat "$STAMP_FILE" 2>/dev/null || true)"

if [ ! -f "$BINARY" ] || [ "$CURRENT_STAMP" != "$EXPECTED_STAMP" ]; then
    swiftc "$SOURCE" -o "$BINARY" && printf '%s' "$EXPECTED_STAMP" > "$STAMP_FILE"
fi

SELECTED_TEXT=$("$BINARY" --get-selection 2>/dev/null || true)

PID_FILE="/tmp/translator_gui_${USER}.pid"
INPUT_FILE="/tmp/translator_gui_${USER}.txt"

# 若程式已在執行，送文字給它即可
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        printf '%s' "$SELECTED_TEXT" > "$INPUT_FILE"
        kill -USR1 "$PID"
        exit 0
    fi
fi

# 啟動新 instance
TRANSLATOR_INITIAL_TEXT="$SELECTED_TEXT" nohup "$BINARY" >/dev/null 2>&1 &
disown $!
