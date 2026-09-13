#!/bin/sh
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="/opt/calorie-log/.env"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export PYTHONUNBUFFERED=1

if [ ! -r "$ENV_FILE" ]; then
  echo "找不到可讀取的 $ENV_FILE" >&2
  exit 1
fi
set -a
. "$ENV_FILE"
set +a

cd "$SCRIPT_DIR/.."
exec "$SCRIPT_DIR/../.venv/bin/python" "$SCRIPT_DIR/discord_runner.py"
