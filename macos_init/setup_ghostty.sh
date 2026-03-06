#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/setup_macos_dev_env.sh" 2>/dev/null || true

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_skip() { echo -e "${YELLOW}[SKIP]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

install_ghostty() {
    print_status "檢查 Ghostty 安裝狀態..."

    if command -v ghostty >/dev/null 2>&1; then
        print_skip "Ghostty 已安裝，跳過"
    else
        print_status "正在安裝 Ghostty..."
        brew install --cask ghostty
        print_status "Ghostty 安裝完成"
    fi
}

setup_ghostty_config() {
    print_status "設定 Ghostty config..."

    GHOSTTY_CONFIG_DIR="$HOME/.config/ghostty"
    GHOSTTY_CONFIG="$GHOSTTY_CONFIG_DIR/config"
    DROPBOX_CONFIG="$HOME/Dropbox/ghostty/config"

    if [ -f "$GHOSTTY_CONFIG" ] || [ -L "$GHOSTTY_CONFIG" ]; then
        print_skip "Ghostty config 已存在，跳過"
        return
    fi

    mkdir -p "$GHOSTTY_CONFIG_DIR"

    if [ -f "$DROPBOX_CONFIG" ]; then
        print_status "建立 Ghostty config 符號連結到 Dropbox..."
        ln -s "$DROPBOX_CONFIG" "$GHOSTTY_CONFIG"
        print_status "Ghostty config 符號連結設定完成"
    else
        print_error "找不到 Dropbox 中的 Ghostty config: $DROPBOX_CONFIG"
        exit 1
    fi
}

install_ghostty
setup_ghostty_config
