#!/usr/bin/env bash
set -e

# 強制從 repo root 執行，確保相對路徑正確
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")"

if [ -z "$VPS_HOST" ]; then
  echo "Error: VPS_HOST 環境變數未設定（請在 ~/.zshrc 中 export VPS_HOST=...）" >&2
  exit 1
fi
VPS=root@$VPS_HOST

echo "==> 同步程式碼到 VPS..."
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  eat_later/ $VPS:/opt/eat_later/
rsync -av --exclude='__pycache__' --exclude='*.pyc' \
  common/ $VPS:/opt/eat_later/common/

echo "==> 在 VPS 安裝依賴..."
ssh $VPS "
  cd /opt/eat_later
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
"

echo "==> 設定 systemd service（首次執行）..."
ssh $VPS "
  if [ ! -f /etc/systemd/system/eat-later-bot.service ]; then
    cat > /etc/systemd/system/eat-later-bot.service << 'EOF'
[Unit]
Description=Eat Later Bot - Discord Restaurant Collector
After=network.target

[Service]
EnvironmentFile=/etc/eat-later-bot.env
WorkingDirectory=/opt/eat_later
ExecStart=/opt/eat_later/.venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable eat-later-bot
    echo 'service created and enabled'
  else
    echo 'service already exists, skipping'
  fi
"

echo "==> 重啟服務..."
ssh $VPS "systemctl restart eat-later-bot && sleep 2 && systemctl status eat-later-bot --no-pager"
