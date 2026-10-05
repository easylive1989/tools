#!/bin/sh
set -eu

ROOT="/opt/stock-pick"
SERVICE_NAME="stock-pick"
RUN_USER="$(id -un)"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
trap 'rm -f "$ROOT/stock_pick/.env.new"' EXIT

if ! sudo -n true 2>/dev/null; then
  echo "部署帳號 $RUN_USER 需要免密碼 sudo 才能安裝 systemd 排程。" >&2
  exit 1
fi

python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --disable-pip-version-check -r "$ROOT/stock_pick/requirements.txt"

if [ ! -f "$ROOT/stock_pick/.env.new" ]; then
  echo "找不到由 CI 傳入的 .env.new" >&2
  exit 1
fi
install -m 600 "$ROOT/stock_pick/.env.new" "$ROOT/.env"
cat > "$ROOT/stock_pick/$SERVICE_NAME.service" <<EOF
[Unit]
Description=Log stock-pick screenshots from Discord to Notion
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=$RUN_USER
Environment=HOME=$HOME
WorkingDirectory=$ROOT
ExecStart=$ROOT/stock_pick/run.sh
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
EOF

cat > "$ROOT/stock_pick/$SERVICE_NAME.timer" <<EOF
[Unit]
Description=Check the stock-pick Discord channel every 5 minutes

[Timer]
OnCalendar=*-*-* *:0/5:00
Persistent=true
Unit=$SERVICE_NAME.service

[Install]
WantedBy=timers.target
EOF

sudo install -m 644 "$ROOT/stock_pick/$SERVICE_NAME.service" "/etc/systemd/system/$SERVICE_NAME.service"
sudo install -m 644 "$ROOT/stock_pick/$SERVICE_NAME.timer" "/etc/systemd/system/$SERVICE_NAME.timer"
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME.timer"
if command -v codex >/dev/null 2>&1 && codex login status >/dev/null 2>&1; then
  sudo systemctl start "$SERVICE_NAME.service"
else
  echo "Codex CLI 尚未安裝或登入；排程已啟用，完成 $RUN_USER 帳號登入後會自動開始處理。"
fi

echo "已部署 $SERVICE_NAME.timer；使用 journalctl -u $SERVICE_NAME.service 查看執行結果。"
