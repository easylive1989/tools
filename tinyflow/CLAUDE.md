# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run

```bash
# 編譯
swift build

# 建立 .app bundle
make app

# 建立並直接執行
make run

# 清除 build 產物
make clean
```

> 注意：使用 `make` 建立的 `TinyFlow.app` 是未簽署的 debug build，無法透過 Gatekeeper。

## Architecture

TinyFlow 是一個 macOS SwiftUI app，提供統一介面來呼叫本機 CLI 版的 AI（Claude、Gemini），並以 streaming 方式顯示回應。

### 資料流

```
MessageInputView (Cmd+Return)
    → AppViewModel.sendMessage()
    → CLIRunner（啟動 subprocess）
    → AsyncStream<String>（逐行 stdout）
    → CLIStreamParser（解析 JSON）
    → AppViewModel（更新 Message state）
    → Views 重新渲染
    → SessionStorage（寫入 .tinyflow/sessions.json）
```

### 核心設計決策

- **AppViewModel** 是唯一的 state 來源，`@MainActor` + `ObservableObject`，所有 session/message 操作都在此。
- **Session continuity**：CLIStreamParser 從 streaming 回應中提取 session ID，存入 `Session.claudeSessionId` / `Session.geminiSessionId`，下次啟動 subprocess 時帶入 `--resume` / `--continue` 參數，讓對話可跨重啟延續。
- **Markdown rendering**：streaming 進行中顯示純文字，結束後才改用 `MarkdownUI` 渲染，避免頻繁 layout 計算。
- **Persistence**：每個 session 的對話記錄存在該 session 的工作目錄下的 `.tinyflow/sessions.json`，非全域統一位置。

### CLI 路徑（hardcoded in CLIRunner.swift）

- Claude: `/Users/paulwu/.claude/local/claude`
- Gemini: `/opt/homebrew/bin/gemini`

### 目錄結構

```
Sources/TinyFlow/
├── TinyFlowApp.swift       # @main entry point
├── Models/
│   ├── Session.swift       # CLIType, Message, Session 資料模型
│   └── CLIStreamParser.swift  # 解析 Claude/Gemini 的 JSON streaming 格式
├── ViewModels/
│   └── AppViewModel.swift  # 全域 state + subprocess 管理
├── Utils/
│   ├── CLIRunner.swift     # Process 啟動與 AsyncStream 輸出
│   └── SessionStorage.swift  # JSON 讀寫 .tinyflow/sessions.json
└── Views/
    ├── ContentView.swift   # NavigationSplitView 主框架
    ├── SidebarView.swift   # Session 列表 + 刪除
    ├── ChatView.swift      # 訊息列表 + 自動捲動
    ├── MessageView.swift   # User bubble / Assistant markdown
    ├── MessageInputView.swift  # 輸入框，Cmd+Return 送出
    ├── NewSessionSheet.swift   # 建立 session modal
    ├── SessionHeaderView.swift
    ├── EmptyStateView.swift
    └── TypingDotsView.swift    # Streaming 動畫指示
```
