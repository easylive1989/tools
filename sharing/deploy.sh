#!/usr/bin/env bash
set -e

# 強制從 repo root 執行，確保相對路徑正確
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")"

VPS=root@178.104.240.236

echo "==> 同步程式碼到 VPS..."
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  sharing/ $VPS:/opt/sharing/
rsync -av --exclude='__pycache__' --exclude='*.pyc' \
  common/ $VPS:/opt/sharing/common/

echo "==> 在 VPS 安裝依賴..."
ssh $VPS "
  cd /opt/sharing
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
"

echo "==> 設定 systemd service（首次執行）..."
ssh $VPS "
  if [ ! -f /etc/systemd/system/sharing-bot.service ]; then
    cat > /etc/systemd/system/sharing-bot.service << 'EOF'
[Unit]
Description=Sharing Bot - Discord Restaurant Collector
After=network.target

[Service]
EnvironmentFile=/etc/sharing-bot.env
WorkingDirectory=/opt/sharing
ExecStart=/opt/sharing/.venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable sharing-bot
    echo 'service created and enabled'
  else
    echo 'service already exists, skipping'
  fi
"

echo "==> 重啟服務..."
ssh $VPS "systemctl restart sharing-bot && sleep 2 && systemctl status sharing-bot --no-pager"
