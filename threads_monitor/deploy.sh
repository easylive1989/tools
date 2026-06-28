#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")"

if [ -z "$VPS_HOST" ]; then
  echo "Error: VPS_HOST 環境變數未設定（請在 ~/.zshrc 中 export VPS_HOST=...）" >&2
  exit 1
fi
VPS=root@$VPS_HOST

echo "==> 同步程式碼到 VPS..."
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  threads_monitor/ $VPS:/opt/threads_monitor/
rsync -av --exclude='__pycache__' --exclude='*.pyc' \
  common/ $VPS:/opt/threads_monitor/common/

echo "==> 在 VPS 安裝 Python 依賴..."
ssh $VPS "
  cd /opt/threads_monitor
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
"

echo "==> 安裝 Playwright chromium..."
ssh $VPS "/opt/threads_monitor/.venv/bin/playwright install chromium --with-deps"

echo "==> 建立執行包裝腳本..."
ssh $VPS "
  printf '#!/bin/bash\nset -a\nsource /etc/threads-monitor.env\nset +a\ncd /opt/threads_monitor\nexec .venv/bin/python monitor.py\n' \
    > /opt/threads_monitor/run.sh
  chmod +x /opt/threads_monitor/run.sh
"


echo "==> 確認 /etc/threads-monitor.env 存在..."
ssh $VPS "
  if [ ! -f /etc/threads-monitor.env ]; then
    echo 'WARNING: /etc/threads-monitor.env 不存在，請在 VPS 上執行：'
    echo '  echo \"NOTION_SECRET=xxx\" > /etc/threads-monitor.env'
    echo '  chmod 600 /etc/threads-monitor.env'
  else
    echo 'env file exists'
  fi
"

echo "==> 部署完成！"
