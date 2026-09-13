#!/bin/sh
set -eu

ROOT="$HOME/tools"
SERVICE_NAME="calorie-log"
SECRETS_DIR="/opt/calorie-log"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
trap 'rm -f "$ROOT/calorie_log/.env.new"' EXIT

if ! command -v codex >/dev/null 2>&1; then
  echo "VM 上找不到 codex CLI；請先用部署帳號安裝並登入。" >&2
  exit 1
fi
if ! codex login status >/dev/null 2>&1; then
  echo "VM 上的 codex CLI 尚未登入；請先用部署帳號完成登入。" >&2
  exit 1
fi

python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --disable-pip-version-check -r "$ROOT/calorie_log/requirements.txt"

if [ ! -f "$ROOT/calorie_log/.env.new" ]; then
  echo "找不到由 CI 傳入的 .env.new" >&2
  exit 1
fi
if [ "$(id -u)" -eq 0 ]; then
  install -d -m 700 "$SECRETS_DIR"
  install -m 600 "$ROOT/calorie_log/.env.new" "$SECRETS_DIR/.env"
else
  sudo -n install -d -m 700 -o "$(id -un)" -g "$(id -gn)" "$SECRETS_DIR"
  sudo -n install -m 600 -o "$(id -un)" -g "$(id -gn)" "$ROOT/calorie_log/.env.new" "$SECRETS_DIR/.env"
fi
cat > "$ROOT/calorie_log/$SERVICE_NAME.service" <<EOF
[Unit]
Description=Discord meal calorie logger
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=$(id -un)
Environment=HOME=$HOME
WorkingDirectory=$ROOT
ExecStart=$ROOT/calorie_log/run.sh
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
EOF

cat > "$ROOT/calorie_log/$SERVICE_NAME.timer" <<EOF
[Unit]
Description=Check Discord meal messages every minute

[Timer]
OnBootSec=1min
OnUnitInactiveSec=1min
Persistent=true
Unit=$SERVICE_NAME.service

[Install]
WantedBy=timers.target
EOF

if [ "$(id -u)" -eq 0 ]; then
  install -m 644 "$ROOT/calorie_log/$SERVICE_NAME.service" "/etc/systemd/system/$SERVICE_NAME.service"
  install -m 644 "$ROOT/calorie_log/$SERVICE_NAME.timer" "/etc/systemd/system/$SERVICE_NAME.timer"
  systemctl daemon-reload
  systemctl enable --now "$SERVICE_NAME.timer"
  systemctl start "$SERVICE_NAME.service"
else
  sudo -n install -m 644 "$ROOT/calorie_log/$SERVICE_NAME.service" "/etc/systemd/system/$SERVICE_NAME.service"
  sudo -n install -m 644 "$ROOT/calorie_log/$SERVICE_NAME.timer" "/etc/systemd/system/$SERVICE_NAME.timer"
  sudo -n systemctl daemon-reload
  sudo -n systemctl enable --now "$SERVICE_NAME.timer"
  sudo -n systemctl start "$SERVICE_NAME.service"
fi

echo "已部署 $SERVICE_NAME.timer；使用 journalctl -u $SERVICE_NAME.service 查看執行結果。"
