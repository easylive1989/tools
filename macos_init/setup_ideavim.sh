#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_skip() { echo -e "${YELLOW}[SKIP]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

setup_ideavim() {
    print_status "設定 IdeaVim..."

    IDEAVIMRC="$HOME/.ideavimrc"

    if [ -f "$IDEAVIMRC" ]; then
        print_skip ".ideavimrc 已存在，跳過"
        return
    fi

    print_status "建立 .ideavimrc..."
    cat > "$IDEAVIMRC" <<EOF
source ~/Dropbox/ideavimrc
nmap zso :source ${HOME}/.ideavimrc<CR>
EOF
    print_status ".ideavimrc 設定完成"
}

setup_ideavim
