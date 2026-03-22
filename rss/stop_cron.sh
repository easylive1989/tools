#!/bin/bash

# 當初設定的標記字眼
MARKER="RSS_AUTO_UPDATE_JOB"

# 檢查是否還有該排程
if crontab -l 2>/dev/null | grep -q "$MARKER"; then
    # 移除只有含標記的這行排程
    crontab -l 2>/dev/null | grep -v "$MARKER" | crontab -
    echo "已成功移除 RSS 自動執行的 crontab 排程。"
else
    echo "目前看起來沒有找到 RSS 自動執行的背景定時排程。"
fi
