#!/usr/bin/env python3

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Translate to Traditional Chinese
# @raycast.mode fullOutput

# Optional parameters:
# @raycast.icon 🌐
# @raycast.packageName Translation

# Documentation:
# @raycast.description Translate selected text to Traditional Chinese using local Gemini CLI
# @raycast.author paulwu

import subprocess
import sys


def get_selected_text():
    """Get selected text via AppleScript, avoiding pbpaste encoding issues."""
    script = '''
        set oldClip to the clipboard
        tell application "System Events" to keystroke "c" using command down
        delay 0.3
        set selectedText to the clipboard as text
        set the clipboard to oldClip
        return selectedText
    '''
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def translate(text):
    prompt = (
        "Translate the following text into Traditional Chinese. "
        "Maintain the original tone and style. "
        "Do not add any explanations or extra text. "
        "Just provide the translation.\n\n"
        f"Text: {text}"
    )
    result = subprocess.run(
        ["/opt/homebrew/bin/gemini", "-m", "gemini-2.0-flash", "-e", "", "--sandbox", "-o", "text", prompt],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        errors = [
            line for line in result.stderr.splitlines()
            if not any(skip in line for skip in [
                "Loading extension", "Skipping MCP", "Loaded cached",
                "supports tool updates", "Error during discovery",
            ])
        ]
        print(f"Gemini CLI error: {chr(10).join(errors)}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def main():
    text = get_selected_text()
    if not text:
        print("No text selected.")
        sys.exit(1)

    print(translate(text))


if __name__ == "__main__":
    main()
