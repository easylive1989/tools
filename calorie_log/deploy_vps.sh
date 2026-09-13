#!/bin/sh
set -eu

ROOT="/opt/calorie-log"
SERVICE_NAME="calorie-log"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
trap 'rm -f "$ROOT/calorie_log/.env.new"' EXIT

if [ "$(id -u)" -ne 0 ]; then
  echo "Hetzner 部署腳本需要以 root 執行。" >&2
  exit 1
fi

python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --disable-pip-version-check -r "$ROOT/calorie_log/requirements.txt"

if [ ! -f "$ROOT/calorie_log/.env.new" ]; then
  echo "找不到由 CI 傳入的 .env.new" >&2
  exit 1
fi
install -m 600 "$ROOT/calorie_log/.env.new" "$ROOT/.env"
cat > "$ROOT/calorie_log/$SERVICE_NAME.service" <<EOF
[Unit]
Description=Discord meal calorie logger
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=root
Environment=HOME=/root
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
OnCalendar=*-*-* *:*:00
Persistent=true
Unit=$SERVICE_NAME.service

[Install]
WantedBy=timers.target
EOF

install -m 644 "$ROOT/calorie_log/$SERVICE_NAME.service" "/etc/systemd/system/$SERVICE_NAME.service"
install -m 644 "$ROOT/calorie_log/$SERVICE_NAME.timer" "/etc/systemd/system/$SERVICE_NAME.timer"
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME.timer"
if command -v codex >/dev/null 2>&1 && codex login status >/dev/null 2>&1; then
  systemctl start "$SERVICE_NAME.service"
else
  echo "Codex CLI 尚未安裝或登入；排程已啟用，完成 root 帳號登入後會自動開始處理。"
fi

echo "已部署 $SERVICE_NAME.timer；使用 journalctl -u $SERVICE_NAME.service 查看執行結果。"
