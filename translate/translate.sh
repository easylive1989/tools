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

TRANSLATED=$(printf '%s' "$SELECTED_TEXT" | gemini -m gemini-2.5-flash -p "Detect the language of the input text and translate it to Traditional Chinese (繁體中文). If it is already in Traditional Chinese, translate it to English. Output ONLY the translation. No explanations, no quotes, no extra formatting." 2>/dev/null)

if [ -z "$TRANSLATED" ]; then
    osascript -e 'display notification "翻譯失敗" with title "翻譯"'
    exit 1
fi

echo "$TRANSLATED" | "$BINARY"
