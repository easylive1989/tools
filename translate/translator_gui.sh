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
TRANSLATOR_INITIAL_TEXT="$SELECTED_TEXT" nohup "$BINARY" >/dev/null 2>&1 &
disown $!
