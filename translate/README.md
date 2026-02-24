# 翻譯工具

按下 `Ctrl + Cmd + L` 自動擷取選取文字，透過 Gemini CLI 翻譯成繁體中文，並以浮動視窗顯示結果。

## 需求

- macOS 15+
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) (`brew install gemini`)

## 檔案結構

```
translate/
├── translate.sh              # 主腳本
├── TranslateWindow.swift     # 浮動視窗原始碼
├── translate_window           # 編譯後的執行檔（首次執行自動產生）
└── README.md
```

## 設定步驟

### 步驟一：建立 Automator Quick Action

1. 按 `Cmd + Space` 輸入 **Automator** 開啟
2. 點選 **檔案** → **新增** (或歡迎畫面的「新增文件」)
3. 文件類型選擇 **快速動作** (Quick Action)，點擊「選擇」
4. 視窗上方會有兩個下拉選單，設定如下：
   - **工作流程接收**：選擇「**文字**」(預設可能是「自動（文字）」也可以)
   - **位於**：選擇「**任何應用程式**」
5. 在左側搜尋欄輸入「**Shell**」，找到「**執行 Shell 工序指令**」(Run Shell Script)
6. 將它**雙擊**或**拖拉**到右側工作流程區域
7. 在出現的 Shell 指令區塊中，設定上方的兩個下拉選單：
   - **Shell**：選擇 `/bin/bash`
   - **傳送輸入**：選擇「**到 stdin**」（這很重要，預設是「到引數」）
8. 將指令區塊中的預設文字 `cat` 刪除，替換為：
   ```
   /Users/paulwu/Documents/Github/tools/translate/translate.sh
   ```
9. 按 `Cmd + S` 儲存，名稱輸入「**翻譯**」

### 步驟二：設定鍵盤快速鍵

1. 開啟 **系統設定** (System Settings)
2. 點選左側 **鍵盤** (Keyboard)
3. 點擊 **鍵盤快速鍵...** (Keyboard Shortcuts...) 按鈕
4. 在彈出視窗的左側，點選 **服務** (Services)
5. 在右側列表中，展開 **文字** (Text) 分類
6. 找到剛才建立的「**翻譯**」，勾選啟用它
7. 點擊「翻譯」右側的「**無**」或「**新增快速鍵**」
8. 按下 `Ctrl + Cmd + L` 作為快速鍵
9. 點擊「**完成**」

### 步驟三：授予權限（首次使用時）

首次執行時，macOS 可能會要求授權：

- 如果彈出「Automator 想要控制...」的對話框，點擊「**好**」
- 如果沒有反應，到 **系統設定** → **隱私權與安全性** → **輔助使用**，確認 **Automator** 已勾選

## 使用方式

1. 在任何 App 中選取（反白）文字
2. 按 `Ctrl + Cmd + L`
3. 等待翻譯（會先出現「翻譯中...」通知）
4. 浮動視窗顯示翻譯結果，按 `Esc` 關閉

## 翻譯邏輯

- 自動偵測來源語言，翻譯成繁體中文
- 若來源已是繁體中文，則翻譯成英文
