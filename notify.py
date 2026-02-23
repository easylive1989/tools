#!/usr/bin/env python3
"""Send a macOS notification with the given text."""

import argparse
import subprocess


def send_notification(message: str, title: str = "Notification") -> None:
    script = f'display notification "{message}" with title "{title}" sound name "default"'
    subprocess.run(["osascript", "-e", script], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a macOS notification.")
    parser.add_argument("message", help="The notification text to display.")
    parser.add_argument("-t", "--title", default="Notification", help="The notification title.")
    args = parser.parse_args()
    send_notification(args.message, args.title)


if __name__ == "__main__":
    main()
