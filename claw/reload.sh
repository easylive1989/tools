#!/usr/bin/env bash
# Quick reload of the claw launchd agent. Tails stderr afterwards so you can
# confirm it came back up clean. Ctrl-C stops the tail (agent keeps running).
set -euo pipefail

PLIST="$HOME/Library/LaunchAgents/com.paulwu.claw.plist"
LOG="$HOME/.pclaw/logs/stderr.log"

if [[ ! -f "$PLIST" ]]; then
    echo "launchd plist not installed at $PLIST" >&2
    echo "run: cp launchd/com.paulwu.claw.plist $PLIST" >&2
    exit 1
fi

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
sleep 2
echo "--- launchctl ---"
launchctl list | grep claw || echo "(agent not listed yet)"
echo "--- tail $LOG (Ctrl-C to stop) ---"
exec tail -F "$LOG"
