# translate

macOS 隨身翻譯小工具：選取任意 app 裡的文字 → 按 Raycast hotkey → 在浮動視窗中看到繁體中文翻譯（使用 Gemini CLI）。

## 檔案組成

| 檔案 | 說明 |
|---|---|
| `translator.swift` | SwiftUI + AppKit 的 GUI 原始碼，同時內含 `--get-selection` CLI 模式 |
| `translator_gui.sh` | Raycast 進入點：編譯、簽章、擷取選取文字、啟動/通知 GUI |
| `translator_app` | 編譯產物（已 `.gitignore`，每台機器本地重建） |
| `translator_app.stamp` | 記錄 `OS 版本\|source mtime`，用來判斷是否需要重編（已 `.gitignore`） |

## 使用方式

1. 在任何 app 選取一段文字
2. 按 Raycast hotkey 觸發 `translator_gui.sh`
3. 浮動視窗出現，每次翻譯產生一個 Tab（Tab 1, Tab 2…）

視窗內的按鍵：
- **⌘↩** 翻譯目前輸入框內容
- **⌘V**（輸入框未 focus 時）把剪貼簿內容貼進輸入框並翻譯
- **⌘Q / Esc** 關閉視窗
- **📋** 複製目前 Tab 的翻譯結果
- **− / +** 調整輸出字級
- **×** 關閉單一 Tab

## 文字擷取流程

`translator_gui.sh` 擷取選取文字的策略：

1. **先試 Accessibility API**（不動剪貼簿）
   - 跳過 Raycast 和 translator_app 自己，取得來源 app 的 frontmost
   - 透過 `kAXFocusedUIElementAttribute` → `kAXSelectedTextAttribute` 讀取
2. **若 AX 失敗**（多半是 Electron app，例如 Obsidian / VS Code / Discord）
   - Snapshot 當前剪貼簿 → 模擬 ⌘C → 等 100ms → 再讀一次
   - **只有剪貼簿內容有變**才採用新值，避免「沒選取」或「射到 translator_app 自己」時誤讀舊內容

## 單一 instance + 多 Tab

- translator_app 啟動時將 PID 寫入 `/tmp/translator_gui_$USER.pid`
- 若已有 instance 在跑，`translator_gui.sh` 把新文字寫到 `/tmp/translator_gui_$USER.txt`，送 `SIGUSR1` 通知既有 instance 新增 Tab
- 沒跑才透過 `nohup` 啟動新 instance，並用 `TRANSLATOR_INITIAL_TEXT` 環境變數傳入初始文字

## 自動重建與簽章

`translator_gui.sh` 在每次執行時檢查 stamp；只要 `OS 版本` 或 `translator.swift` 的 mtime 任一改變就重編：

```bash
swiftc translator.swift -o translator_app
codesign --force --sign "Developer ID Application: Cheng Hua Wu (T9UXT366P9)" translator_app
```

用 Developer ID 簽章是為了讓 macOS TCC 能以穩定的簽章身份追蹤 `translator_app`，讓「輔助使用」授權在重編後不會失效。

## 前置需求

1. **Gemini CLI** 已安裝（`brew install gemini-cli` 或同等安裝方式），並可透過 `/opt/homebrew/bin` 或 `/usr/local/bin` 找到
2. **Accessibility 權限**：系統設定 → 隱私權與安全性 → 輔助使用 → 加入 `translator_app` 並開啟
3. **Developer ID Application 證書**在 login keychain，identity 名稱需與 `translator_gui.sh` 裡的 `SIGN_IDENTITY` 一致（跨機器使用請匯出 `.p12` 匯入到其他 Mac）

## 翻譯規則

固定將輸入翻譯成繁體中文（見 `translator.swift` 的 `SYSTEM_PROMPT`）。保留 Markdown 格式、換行結構不變。使用 `gemini-2.5-flash` 模型。
