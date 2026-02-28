#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BINARY="$SCRIPT_DIR/translate_window"

if [ ! -f "$BINARY" ]; then
    swiftc "$SCRIPT_DIR/TranslateWindow.swift" -o "$BINARY" 2>/dev/null
fi

# Automator Quick Action 會透過 stdin 傳入選取的文字
SELECTED_TEXT=$(cat)

if [ -z "$SELECTED_TEXT" ]; then
    osascript -e 'display notification "未選取任何文字" with title "翻譯"'
    exit 0
fi

osascript -e 'display notification "翻譯中..." with title "翻譯"'

TRANSLATED=$(printf '%s' "$SELECTED_TEXT" | gemini -m gemini-2.0-flash -p "檢測輸入文字的語言並將其翻譯為繁體中文（繁體中文）。僅輸出翻譯內容。不做解釋、不加引號、不做額外格式。翻譯內容有可能是一個單字，也有可能是一個句子，你只要忠實翻譯就好。" 2>/dev/null)

if [ -z "$TRANSLATED" ]; then
    osascript -e 'display notification "翻譯失敗" with title "翻譯"'
    exit 1
fi

echo "$TRANSLATED" | "$BINARY"
