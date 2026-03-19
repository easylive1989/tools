#!/bin/bash

# macOS 開發環境自動設定腳本
# 此腳本會檢查每個設定是否已完成，若已完成則跳過

set -e  # 遇到錯誤立即停止

echo "====================================="
echo "開始設定 macOS 開發環境"
echo "====================================="

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 工具函數
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
}

# 1. 設定 oh-my-zsh
setup_oh_my_zsh() {
    print_status "檢查 oh-my-zsh 安裝狀態..."

    if [ -d "$HOME/.oh-my-zsh" ]; then
        print_skip "oh-my-zsh 已安裝，跳過安裝步驟"
    else
        print_status "正在安裝 oh-my-zsh..."
        sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
        print_status "oh-my-zsh 安裝完成"
    fi

    # 檢查並設定 git plugin
    if grep -q "plugins=(git)" "$HOME/.zshrc" 2>/dev/null; then
        print_skip "git plugin 已設定，跳過"
    else
        print_status "設定 oh-my-zsh git plugin..."
        # 備份原始 .zshrc
        cp "$HOME/.zshrc" "$HOME/.zshrc.backup.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
        # 設定 git plugin
        sed -i '' 's/plugins=()/plugins=(git)/' "$HOME/.zshrc" 2>/dev/null || echo 'plugins=(git)' >> "$HOME/.zshrc"
        print_status "git plugin 設定完成"
    fi
}

# 2. 安裝 homebrew 與套件
setup_homebrew() {
    print_status "檢查 Homebrew 安裝狀態..."

    if command -v brew >/dev/null 2>&1; then
        print_skip "Homebrew 已安裝，跳過安裝步驟"
    else
        print_status "正在安裝 Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        print_status "Homebrew 安裝完成"
    fi

    # 更新 Homebrew
    print_status "更新 Homebrew..."
    brew update

    # 安裝套件列表
    packages=(git gh fvm neovim openjdk@17 node@22 cocoapods wget)

    for package in "${packages[@]}"; do
        if brew list "$package" >/dev/null 2>&1; then
            print_skip "$package 已安裝，跳過"
        else
            print_status "正在安裝 $package..."
            brew install "$package"
            print_status "$package 安裝完成"
        fi
    done
}

# 3. 設定環境變數 (~/.zshenv)
setup_environment_variables() {
    print_status "設定環境變數..."

    ZSHENV_FILE="$HOME/.zshenv"
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    ZSHENV_CONFIG="$SCRIPT_DIR/configs/zshenv"

    if [ -f "$ZSHENV_FILE" ] && grep -q "ANDROID_HOME" "$ZSHENV_FILE"; then
        print_skip "環境變數已設定，跳過"
    else
        if [ -f "$ZSHENV_CONFIG" ]; then
            print_status "從 configs/zshenv 讀取環境變數設定..."
            # 備份現有檔案
            [ -f "$ZSHENV_FILE" ] && cp "$ZSHENV_FILE" "$ZSHENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
            cp "$ZSHENV_CONFIG" "$ZSHENV_FILE"
            print_status "環境變數設定完成"
        else
            print_error "找不到設定檔案: $ZSHENV_CONFIG"
            exit 1
        fi
    fi
}

# 4. 設定 Claude Code CLI
setup_claude_code() {
    print_status "檢查 Claude Code CLI 安裝狀態..."

    if command -v claude-code >/dev/null 2>&1; then
        print_skip "Claude Code CLI 已安裝，跳過安裝步驟"
    else
        print_status "正在安裝 Claude Code CLI..."
        npm install -g @anthropic-ai/claude-code
        print_status "Claude Code CLI 安裝完成"
    fi

    # 設定 Claude 目錄
    CLAUDE_DIR="$HOME/.claude"
    mkdir -p "$CLAUDE_DIR"

    # 設定 CLAUDE.md
    CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"
    DROPBOX_CLAUDE_MD="$HOME/Dropbox/claude/CLAUDE.md"

    if [ -f "$CLAUDE_MD" ] || [ -L "$CLAUDE_MD" ]; then
        print_skip "CLAUDE.md 已存在，跳過"
    else
        if [ -f "$DROPBOX_CLAUDE_MD" ]; then
            print_status "建立 CLAUDE.md 符號連結到 Dropbox..."
            ln -s "$DROPBOX_CLAUDE_MD" "$CLAUDE_MD"
            print_status "CLAUDE.md 符號連結設定完成"
        else
            # 備用方案：從 configs 目錄複製
            SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
            CLAUDE_CONFIG="$SCRIPT_DIR/configs/CLAUDE.md"
            if [ -f "$CLAUDE_CONFIG" ]; then
                print_status "從 configs/CLAUDE.md 複製設定..."
                cp "$CLAUDE_CONFIG" "$CLAUDE_MD"
                print_status "CLAUDE.md 設定完成"
            else
                print_error "找不到 Dropbox 或 configs 中的 CLAUDE.md"
                exit 1
            fi
        fi
    fi

    # 設定 settings.json
    SETTINGS_JSON="$CLAUDE_DIR/settings.json"
    DROPBOX_SETTINGS_JSON="$HOME/Dropbox/claude/settings.json"

    if [ -f "$SETTINGS_JSON" ] || [ -L "$SETTINGS_JSON" ]; then
        print_skip "settings.json 已存在，跳過"
    else
        if [ -f "$DROPBOX_SETTINGS_JSON" ]; then
            print_status "建立 settings.json 符號連結到 Dropbox..."
            ln -s "$DROPBOX_SETTINGS_JSON" "$SETTINGS_JSON"
            print_status "settings.json 符號連結設定完成"
        else
            # 備用方案：從 configs 目錄複製
            SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
            SETTINGS_CONFIG="$SCRIPT_DIR/configs/settings.json"
            if [ -f "$SETTINGS_CONFIG" ]; then
                print_status "從 configs/settings.json 複製設定..."
                cp "$SETTINGS_CONFIG" "$SETTINGS_JSON"
                print_status "settings.json 設定完成"
            else
                print_error "找不到 Dropbox 或 configs 中的 settings.json"
                exit 1
            fi
        fi
    fi
}

# 5. 安裝 Android SDK
setup_android_sdk() {
    print_status "檢查 Android SDK 安裝狀態..."

    SDK_PATH="$HOME/Library/Android/sdk"

    if [ -d "$SDK_PATH/cmdline-tools" ] && [ -f "$SDK_PATH/cmdline-tools/cmdline-tools/bin/sdkmanager" ]; then
        print_skip "Android SDK 已安裝，跳過安裝步驟"
    else
        print_status "正在安裝 Android SDK..."

        # 創建 Android SDK 目錄
        mkdir -p "$SDK_PATH"

        # 下載 Android SDK 命令行工具
        cd /tmp
        wget -O commandlinetools.zip https://dl.google.com/android/repository/commandlinetools-mac-8092744_latest.zip

        # 解壓到 SDK 目錄
        unzip commandlinetools.zip -d "$SDK_PATH/cmdline-tools"

        # 清理下載的文件
        rm commandlinetools.zip

        # 設定環境變數
        export ANDROID_HOME="$SDK_PATH"
        export PATH="$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools"

        # 安裝必要的 Android SDK 組件
        SDKMANAGER="$SDK_PATH/cmdline-tools/cmdline-tools/bin/sdkmanager"

        yes | "$SDKMANAGER" --licenses
        "$SDKMANAGER" "platform-tools"
        "$SDKMANAGER" "platforms;android-35"
        "$SDKMANAGER" "build-tools;35.0.0"

        print_status "Android SDK 安裝完成"
    fi
}

# 6. 設定 VIM
setup_vim() {
    print_status "設定 VIM 環境..."

    # 設定 IdeaVim
    IDEAVIMRC="$HOME/.ideavimrc"
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    IDEAVIMRC_CONFIG="$SCRIPT_DIR/configs/ideavimrc"

    if [ -f "$IDEAVIMRC" ]; then
        print_skip ".ideavimrc 已存在，跳過"
    else
        if [ -f "$IDEAVIMRC_CONFIG" ]; then
            print_status "從 configs/ideavimrc 複製設定..."
            cp "$IDEAVIMRC_CONFIG" "$IDEAVIMRC"
            print_status ".ideavimrc 設定完成"
        else
            print_error "找不到設定檔案: $IDEAVIMRC_CONFIG"
            exit 1
        fi
    fi

    # 設定 NeoVim
    NVIM_CONFIG_DIR="$HOME/.config/nvim"
    NVIM_INIT="$NVIM_CONFIG_DIR/init.lua"
    NVIM_CONFIG="$SCRIPT_DIR/configs/init.lua"

    if [ -f "$NVIM_INIT" ]; then
        print_skip "NeoVim init.lua 已存在，跳過"
    else
        if [ -f "$NVIM_CONFIG" ]; then
            print_status "從 configs/init.lua 複製 NeoVim 設定..."
            mkdir -p "$NVIM_CONFIG_DIR"
            cp "$NVIM_CONFIG" "$NVIM_INIT"
            print_status "NeoVim init.lua 設定完成"
        else
            print_error "找不到設定檔案: $NVIM_CONFIG"
            exit 1
        fi
    fi
}

# 7. 提示使用者設定機密資料
setup_secrets() {
    print_status "檢查機密資料設定..."

    if grep -q "NOTION_SECRET" "$HOME/.zshrc" 2>/dev/null && grep -q "MEDIUM_TOKEN" "$HOME/.zshrc" 2>/dev/null; then
        print_skip "基本機密資料已設定，跳過"
    else
        print_warning "需要設定機密資料到 ~/.zshrc"
        echo ""
        echo "請手動將以下內容加入到 ~/.zshrc："
        echo ""
        echo 'export NOTION_SECRET="your_notion_secret"'
        echo 'export MEDIUM_TOKEN="your_medium_token"  # 從 Medium Settings -> Security and apps -> Integration tokens 取得'
        echo ""
        read -p "請輸入您的 NOTION_SECRET: " notion_secret
        read -p "請輸入您的 MEDIUM_TOKEN: " medium_token

        # 備份 .zshrc
        cp "$HOME/.zshrc" "$HOME/.zshrc.backup.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true

        # 添加機密資料
        echo "" >> "$HOME/.zshrc"
        echo "# 機密資料設定" >> "$HOME/.zshrc"
        echo "export NOTION_SECRET=\"$notion_secret\"" >> "$HOME/.zshrc"
        echo "export MEDIUM_TOKEN=\"$medium_token\"" >> "$HOME/.zshrc"

        print_status "機密資料已添加到 ~/.zshrc"
    fi

    # 檢查 MEDIUM_USER_ID
    if grep -q "MEDIUM_USER_ID" "$HOME/.zshrc" 2>/dev/null; then
        print_skip "MEDIUM_USER_ID 已設定，跳過"
    else
        print_status "使用 get_medium_user_id.py 取得 Medium User ID..."

        if [ -f "get_medium_user_id.py" ]; then
            # 載入環境變數
            source "$HOME/.zshrc" 2>/dev/null || true

            # 執行腳本取得 User ID
            medium_user_id=$(python3 get_medium_user_id.py 2>/dev/null || echo "")

            if [ -n "$medium_user_id" ]; then
                echo "export MEDIUM_USER_ID=\"$medium_user_id\"" >> "$HOME/.zshrc"
                print_status "MEDIUM_USER_ID 已設定: $medium_user_id"
            else
                print_warning "無法自動取得 MEDIUM_USER_ID，請手動設定"
                read -p "請輸入您的 MEDIUM_USER_ID: " manual_user_id
                echo "export MEDIUM_USER_ID=\"$manual_user_id\"" >> "$HOME/.zshrc"
                print_status "MEDIUM_USER_ID 已手動設定"
            fi
        else
            print_warning "找不到 get_medium_user_id.py 檔案"
            read -p "請輸入您的 MEDIUM_USER_ID: " manual_user_id
            echo "export MEDIUM_USER_ID=\"$manual_user_id\"" >> "$HOME/.zshrc"
            print_status "MEDIUM_USER_ID 已手動設定"
        fi
    fi
}

# 主要執行流程
main() {
    print_status "開始執行 macOS 開發環境設定..."

    setup_oh_my_zsh
    setup_homebrew
    setup_environment_variables
    setup_claude_code
    setup_android_sdk
    setup_vim
    setup_secrets

    echo ""
    echo "====================================="
    echo -e "${GREEN}✅ macOS 開發環境設定完成！${NC}"
    echo "====================================="
    echo ""
    echo "📝 後續步驟："
    echo "1. 重新啟動終端機或執行: source ~/.zshrc"
    echo "2. 確認所有環境變數已正確載入"
    echo "3. 測試各項工具是否正常運作"
    echo ""
}

# 執行主函數
main "$@"