# Sharing Bot — 餐廳資訊自動整理 Design Spec

**Date:** 2026-04-27
**Status:** Approved

## Overview

在 `sharing/` 目錄下建立一個獨立的 Discord bot，監聽指定頻道。使用者將餐廳相關內容（thread、IG、Facebook、一般網頁連結或純文字）貼入頻道後，bot 自動以 Gemini AI 解析，並寫入 Notion 資料庫「吃什麼」（ID: `974f5e43cac84f818fe23f35e463286b`）。

## Notion Database Schema

資料庫「吃什麼」欄位：

| 欄位 | 類型 | 說明 |
|---|---|---|
| Name | title | 餐廳名稱（必填） |
| 連結 | url | 原始 URL |
| 地區 | select | 地區（例：台北市、新北市） |
| 鄉鎮 | select | 鄉鎮區（例：大安區、中山區） |
| 類型 | multi_select | 料理類型（例：日式、台式、義式） |
| Note | rich_text | 備註、摘要 |
| 評級 | number | 評分（若訊息中有提及） |
| 吃過 | checkbox | 預設 false |

## File Structure

```
sharing/
├── bot.py            Discord bot，on_message handler
├── extractor.py      URL 偵測、網頁抓取、Gemini 解析
├── notion_writer.py  寫入 Notion DB
├── requirements.txt  依賴套件
└── deploy.sh         部署腳本（本機執行）
```

## Data Flow

```
Discord 訊息（文字 / URL / 圖片說明）
   │
   ▼
[extractor.py]
   1. 用 regex 偵測訊息中的所有 URL
   2. 逐一 GET 網頁，抓取 <title>、<meta description>、前 1500 字 body text（失敗跳過）
   3. 把「原始訊息 + 網頁內容摘要」送 Gemini，要求輸出 JSON：
      { name, url, region, town, types[], note, rating }
   4a. JSON 解析成功 → 回傳 ExtractResult(confidence="full")
   4b. JSON 解析失敗 → fallback：
       name = 第一行 or 網頁 title
       url  = 第一個偵測到的 URL
       note = 原始訊息全文
       confidence = "partial"
   │
   ▼
[notion_writer.py]
   將 ExtractResult 對應到 Notion properties，呼叫 common.NotionApi.create_page()
   │
   ▼
[bot.py]
   ✅ reaction → full extract 成功
   🔖 reaction → partial fallback
   ❌ reaction → 例外錯誤（並 reply 錯誤訊息）
```

## Components

### bot.py

- 繼承 `discord.Client`，intents 需要 `message_content` + `messages`
- `on_message`：
  - 過濾非目標頻道、bot 自身訊息
  - 呼叫 `extractor.extract(content)`
  - 呼叫 `notion_writer.write(result)`
  - 加 reaction
- 入口：`asyncio.run(main())`，讀取環境變數

### extractor.py

- `extract(content: str) -> ExtractResult`
- URL 偵測：`re.findall(r'https?://\S+'，content)`
- 網頁抓取：`requests.get(url, timeout=10)`，解析 `html.parser`（stdlib），取 `<title>` + `<meta name="description">` + body 前 1500 字，超時或失敗靜默略過
- Gemini prompt：要求輸出純 JSON（no markdown fences），範例格式附在 prompt 內
- JSON 解析：先嘗試直接 `json.loads`，失敗用 regex 找 `{...}` block

### notion_writer.py

- `write(result: ExtractResult, notion: NotionApi, db_id: str) -> None`
- 對應欄位寫入；`rating` 為 None 時不寫（避免空 number）
- 使用 `common.notion.NotionApi`（不重複實作）

### deploy.sh

```bash
#!/usr/bin/env bash
set -e
VPS=root@178.104.240.236
# 同步 sharing/ 原始碼
rsync -av --exclude='.venv' --exclude='__pycache__' sharing/ $VPS:/opt/sharing/
# 同步 common/ 工具（notion.py、gemini.py）
rsync -av --exclude='__pycache__' common/ $VPS:/opt/sharing/common/
ssh $VPS "
  cd /opt/sharing
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
  systemctl restart sharing-bot || systemctl start sharing-bot
  systemctl status sharing-bot --no-pager
"
```

## Environment Variables

| 變數 | 說明 |
|---|---|
| `CLAW_DISCORD_TOKEN` | Discord bot token（與 claw 共用） |
| `SHARING_CHANNEL_ID` | 餐廳分享頻道 ID |
| `NOTION_SECRET` | Notion API token |
| `GOOGLE_API_KEY` | Gemini API key（免費 tier） |

VPS 上放在 `/etc/sharing-bot.env`。

## systemd Service

`/etc/systemd/system/sharing-bot.service`:

```ini
[Unit]
Description=Sharing Bot - Discord Restaurant Collector
After=network.target

[Service]
EnvironmentFile=/etc/sharing-bot.env
WorkingDirectory=/opt/sharing
ExecStart=/opt/sharing/.venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Dependencies (requirements.txt)

```
discord.py>=2.3
requests>=2.31
google-generativeai>=0.8
```

（`common/` 透過 `sys.path` 插入 repo root，無需額外安裝）

## Error Handling

- 網頁抓取失敗（timeout、403、非 HTML）：靜默略過，繼續用原始訊息
- Gemini 呼叫失敗（quota、網路）：fallback 到 partial 模式
- Notion 寫入失敗：❌ reaction + reply 錯誤訊息
- 所有未預期例外：log + ❌ reaction，bot 繼續運行

## Out of Scope

- 重複偵測（同一個 URL 貼兩次會建兩筆）
- 圖片 OCR（IG / FB 截圖）
- 編輯或刪除已存入的 Notion 記錄
