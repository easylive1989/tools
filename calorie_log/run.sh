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

if ! command -v codex >/dev/null 2>&1; then
  echo "Hetzner VPS 上找不到 codex CLI；請先以 $(id -un) 帳號安裝並登入。" >&2
  exit 1
fi
if ! codex login status >/dev/null 2>&1; then
  echo "Hetzner VPS 上的 codex CLI 尚未登入；請先以 $(id -un) 帳號完成登入。" >&2
  exit 1
fi

cd "$SCRIPT_DIR/.."
exec "$SCRIPT_DIR/../.venv/bin/python" "$SCRIPT_DIR/discord_runner.py"
