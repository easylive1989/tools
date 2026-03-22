#!/bin/bash

# 取得腳本所在的絕對路徑
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 從環境變數中取得的 uv 絕對路徑，確保 crontab 能正確找得到 uv
UV_PATH="/Users/paulwu/.local/bin/uv"

# 用來標記此 crontab 的字眼，方便日後移除
MARKER="RSS_AUTO_UPDATE_JOB"

# crontab 指令內容：每小時 (0 * * * *) 執行一次，並將錯誤及標準輸出寫進 cron.log
CRON_CMD="0 * * * * cd \"$DIR\" && $UV_PATH run rss.py >> \"$DIR/cron.log\" 2>&1 # $MARKER"

# 檢查是否已經存在我們建立的排程
if crontab -l 2>/dev/null | grep -q "$MARKER"; then
    echo "排程已存在，無需重複加入。"
else
    # 備份現有的 crontab 並加入新的排程
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "已成功加到系統背景定時器 (crontab)。"
    echo "排程：預設每小時整點會自動執行一次。"
    echo "日誌：執行結果會紀錄在 $DIR/cron.log"
fi
