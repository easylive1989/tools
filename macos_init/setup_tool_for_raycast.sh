#!/bin/bash
# setup_tool_for_raycast.sh
# 此腳本會指引使用者並自動開啟 Raycast 設定，協助將 tools 目錄加入 Script Commands。

TARGET_DIR="/Users/paulwu/Documents/Github/tools"

echo "🤖 正在協助設定 Raycast Script Commands 目錄..."
echo "=========================================================="

# 將路徑複製到剪貼簿，節省使用者尋找目錄的時間
echo "${TARGET_DIR}" | pbcopy
echo "✅ 已自動將目標路徑「 ${TARGET_DIR} 」複製到你的剪貼簿！"
echo ""

# 說明技術限制
echo "⚠️  技術提示："
echo "由於 Raycast 的設定檔是使用加密的 SQLite 資料庫儲存，官方並未提供純粹指令列 (CLI) 新增腳本目錄的 API。"
echo "因此，這個腳本會引導並自動為你打開設定介面，請依循以下步驟完成最後的設定："
echo "=========================================================="
echo "  1️⃣  系統即將會喚起 Raycast，請進入設定 (General -> 快捷鍵通常為 ⌘ + ,)"
echo "  2️⃣  切換到「Extensions」分頁"
echo "  3️⃣  在左側選單往下滾動，找到字寫著「Script Commands」的選項"
echo "  4️⃣  點擊右側的「Add Script Directory」按鈕（或按捷徑鍵 ⌘ + shift + D）"
echo "  5️⃣  在跳出的檔案選擇視窗中，按下捷徑鍵「 ⌘ + ⇧ + G 」（前往資料夾）"
echo "  6️⃣  直接按下 ⌘ + V 貼上剛剛複製的路徑，按下 Enter 後再點擊右下角的打開或選擇 (Open/Choose)"
echo "=========================================================="
echo ""

# 嘗試打開 Raycast Extensions 設定，若 Deep link 不支援則至少把 App 開起來
open "raycast://extensions" 2>/dev/null || open -a "Raycast"

echo "👉 請在跳出來的 Raycast 設定視窗中完成最後的操作即可！"
