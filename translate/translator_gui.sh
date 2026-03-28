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

# 若 binary 不存在或 source 較新則重新編譯
if [ ! -f "$BINARY" ] || [ "$SOURCE" -nt "$BINARY" ]; then
    swiftc "$SOURCE" -o "$BINARY"
fi

osascript -e 'tell application "System Events" to keystroke "c" using command down'
sleep 0.1
SELECTED_TEXT=$(osascript -e 'the clipboard as text' 2>/dev/null || true)

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
