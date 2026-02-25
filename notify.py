#!/usr/bin/env python3
"""Send a macOS notification with the given text."""

import argparse
import subprocess


def send_notification(
    message: str,
    title: str = "Notification",
    activate: str | None = None,
    open_url: str | None = None,
) -> None:
    cmd = [
        "terminal-notifier",
        "-message", message,
        "-title", title,
        "-sound", "default",
    ]
    if activate:
        cmd += ["-activate", activate]
    if open_url:
        cmd += ["-open", open_url]
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a macOS notification.")
    parser.add_argument("message", help="The notification text to display.")
    parser.add_argument("-t", "--title", default="Notification", help="The notification title.")
    parser.add_argument("-a", "--activate", help="Bundle ID of the app to activate on click (e.g. com.apple.Safari).")
    parser.add_argument("-o", "--open", dest="open_url", help="URL to open on click.")
    args = parser.parse_args()
    send_notification(args.message, args.title, args.activate, args.open_url)


if __name__ == "__main__":
    main()
