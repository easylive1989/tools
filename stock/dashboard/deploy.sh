#!/usr/bin/env bash
# Deploys stock dashboard backend to VPS
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$(dirname "$SCRIPT_DIR")")"   # repo root

VPS=root@178.104.240.236
REMOTE=/opt/stock-dashboard

echo "==> Syncing code to VPS..."
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='stock_dashboard.db' \
  stock/dashboard/backend/ $VPS:$REMOTE/backend/

echo "==> Syncing service file..."
rsync -av stock/dashboard/stock-dashboard.service $VPS:$REMOTE/

echo "==> Installing dependencies on VPS..."
ssh $VPS "
  cd $REMOTE/backend
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
"

echo "==> Installing systemd service..."
ssh $VPS "
  cp $REMOTE/stock-dashboard.service /etc/systemd/system/stock-dashboard.service
  systemctl daemon-reload
  systemctl enable stock-dashboard
  systemctl restart stock-dashboard
  systemctl status stock-dashboard --no-pager
"

echo "==> Done. API live at https://api.paul-learning.dev"
