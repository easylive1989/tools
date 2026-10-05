# Stock Pick Logger — 智選股截圖自動記錄 Design Spec

**Date:** 2026-10-05
**Status:** Draft

## Overview

使用者每天收盤後，會在 Discord 頻道 `1556684804731179070` 貼上智選股 App「自選」頁的截圖（一則訊息可能有多張）。
新工具 `stock_pick/` 跑在 oracle-arm VPS，每 5 分鐘輪詢這個頻道。它用 Codex CLI 讀出截圖中的股票名稱，
並用官方行情查出代號與當天收盤價，再寫入 Notion「智選股當天入場」資料庫。

截圖只用來辨識「有哪些股票」。代號與價格一律以官方行情為準，跟 `stock-pick-winrate` skill 的算法一致。

## 範圍

- 只處理工具上線後的新訊息；已經手動記錄在 Notion 的歷史資料不補登。
- 不填 `備註`，由使用者手動補。
- 不使用 Discord webhook。讀取頻道靠現有的 bot token。
- 不改動 `calorie_log`、`eat_later` 既有程式。

## Notion Database

「智選股當天入場」，data source `3ea8303f-78f7-801f-9742-000b47c34230`，使用 Notion API 版本 `2025-09-03`（與 calorie_log 相同）。

| 欄位 | 類型 | 寫入內容 |
|---|---|---|
| Name | title | `代號 官方名稱`，例如 `3293 鈊象`、`7731 火星生技*`（興櫃官方名稱本身帶 `*`） |
| 進場價格 | number | 選股日期的官方收盤價；興櫃用當日最後成交價 |
| 選股日期 | date | 貼圖時已收盤的最近一個交易日：交易日 13:30 以後貼的算當天，其餘（13:30 以前、週末、休市日）算前一個交易日（只存日期） |
| 備註 | multi_select | 不寫入 |
| Created time | created_time | Notion 自動記錄寫入時間 |

## File Structure

```
stock_pick/
├── runner.py          進入點：輪詢 Discord、state、重試、emoji 與回覆
├── reader.py          Codex CLI 讀圖 → 股票名稱清單
├── quotes.py          官方行情 → {官方名稱: Quote(code, market, day, price)}
├── notion_writer.py   查重、組 properties、寫入
├── run.sh             systemd 呼叫的啟動腳本（載入 .env、檢查 codex 登入）
├── deploy_vps.sh      在 VPS 上建 venv、安裝 systemd service + timer
├── requirements.txt
└── tests/
common/
└── discord.py         新的共用 Discord client（抓訊息、下載附件、加 emoji、回覆）
.github/workflows/
└── deploy-stock-pick.yml
```

`stock_pick/state.json` 只存在 VPS 上，不進 Git（加進 `.gitignore`）。

## Data Flow

每 5 分鐘執行一次 `runner.py`：

1. **載入 state。** 沒有 `last_message_id` 時（第一次執行），把它設成頻道目前最新的訊息 id，存檔後結束，不處理歷史。
2. **抓新訊息。** 取 `last_message_id` 之後的訊息，從舊到新處理。只處理「非 bot、至少有一個圖片附件」的訊息；其他訊息直接推進 `last_message_id`。
3. **選股日期。** 訊息 timestamp 轉 `Asia/Taipei`。當天是交易日且 13:30（收盤）以後貼的，`D` = 當天；其餘（13:30 以前，例如半夜過後才貼；或週末、休市日貼的），`D` = 前一個交易日。當天是否交易看週末與證交所休市日 `https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule?date={年}0101&response=json`（名稱以「交易日」結尾的列只是說明，例如「國曆新年開始交易日」，照常交易）。交易日取自證交所月度大盤統計 `https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={該月1日}&response=json`，當月找不到就往前一個月找。（2026-10-06 使用者決定加入 13:30 規則，並讓假日貼的圖也算最近一個交易日。）
4. **抓官方行情**（同一輪只抓一次，所有訊息共用）：
   - 上市：`https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={D:%Y%m%d}&response=json&type=ALLBUT0999`，取有「證券代號、證券名稱、收盤價」欄位的表。
   - 上櫃：`https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes`，欄位 `SecuritiesCompanyCode`、`CompanyName`、`Close`、`Date`（民國年）。
   - 興櫃：`https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics`，欄位 `SecuritiesCompanyCode`、`CompanyName`、`LatestPrice`、`Date`。
5. **等待行情。** 三個市場的報價日都等於 `D` 才繼續。若任一市場還早於 `D`，這則訊息標記為「等待中」，本輪停在這裡，不推進 `last_message_id`，下一輪再試。等待不算失敗次數。
6. **讀圖。** 下載該訊息所有圖片（png / jpg / jpeg / webp），一次交給 Codex CLI。輸出 JSON `{"names": ["鈊象", "火星生技*", ...]}`：依圖中順序列出股票名稱，原樣保留 `*`，不含指數。程式端再做兩件事：去重，並丟掉以「指」或「指數」結尾的名稱（例如截圖中被裁切的「加權指」）。
7. **比對。** 名稱去掉頭尾空白、全形空白後，與官方名稱完全比對，取得代號、市場與價格。價格為空或 0 視為「無成交價」，跟對不到的名稱一樣處理。
8. **寫入 Notion。** 先查是否已有 `選股日期 = D` 且 `Name` 以 `代號 ` 開頭的資料，有就跳過；沒有就新增。
9. **回饋。** 依結果加 emoji 或回覆（見下節），把這則訊息從 `attempts` 移除，推進 `last_message_id`。

### Codex 呼叫

沿用 calorie_log 的方式：`codex exec --model gpt-5.6-terra --config model_reasoning_effort=medium --output-schema <schema> --output-last-message <file> --image <每張圖>`。schema 限定輸出 `{"names": string[]}`。逾時 180 秒。

## Error Handling 與 Discord 回饋

| 情況 | 處理 |
|---|---|
| 全部名稱都對到並寫入（含查重後跳過的） | 加 ✅ |
| 至少一檔寫入，但有名稱對不到或無成交價 | 對到的照寫，加 ⚠️，回覆對不到的名稱，例如「找不到這些股票的 2026-10-05 收盤價：鈊像」 |
| 讀圖結果沒有任何股票 | 加 ❌，回覆「截圖中沒有辨識到股票」 |
| 有讀到名稱，但一檔都對不到 | 加 ❌，回覆對不到的名稱（同上格式） |
| 例外錯誤（Codex、Notion、Discord 下載、網路） | 下一輪重試；`attempts[訊息 id]` 累計，連續 3 次失敗就加 ❌、回覆錯誤摘要、推進 `last_message_id` |
| 發送後 12 小時仍等不到 `D` 的行情（例如假日貼圖） | 加 ❌，回覆「找不到 2026-10-05 的收盤行情，可能不是交易日」，推進 `last_message_id` |
| 行情已更新到晚於 `D` 的交易日（訊息等太久） | 加 ❌，回覆「官方行情已更新到 {新日期}，無法取得 {D} 的收盤價」，推進 `last_message_id` |

錯誤回覆不得包含 token 或其他 secret。

## State

`stock_pick/state.json`：

```json
{
  "last_message_id": "1556700000000000000",
  "attempts": {"1556700000000000001": 1}
}
```

## Deployment

仿照 `deploy-calorie-log.yml`：

- 觸發：push 到 `master` 且變更 `stock_pick/**`、`common/discord.py`、`common/notion.py` 或 workflow 本身；也可手動 `workflow_dispatch`。
- 先跑 `pytest stock_pick/tests`，通過才部署。
- 以 `ubuntu` 帳號 SSH 到 `VPS_HOST`（oracle-arm），程式放在 `/opt/stock-pick`，`.env` 權限 600，只放 `DISCORD_BOT_TOKEN`、`NOTION_SECRET`。
- systemd：`stock-pick.service`（oneshot，`User=ubuntu`）+ `stock-pick.timer`（`OnCalendar=*:0/5`）。
- 沿用 GitHub secrets：`VPS_HOST`、`VPS_SSH_KEY`、`VPS_KNOWN_HOSTS`（選用）、`DISCORD_BOT_TOKEN`、`NOTION_SECRET`。不新增 secret。
- `run.sh` 啟動前檢查 `codex login status`；未登入時印出錯誤並結束。

## 前提（動工前驗證）

1. 現有 bot 能讀取頻道 `1556684804731179070` 的訊息與附件，也有加 reaction、發訊息的權限。
2. `NOTION_SECRET` 對應的 integration 有權限查詢並寫入「智選股當天入場」。

## Testing

單元測試（`stock_pick/tests/`，不連網）：

- `quotes.py`：用 TWSE / TPEx 回應的 JSON fixture 測解析、民國日期轉換、報價日判斷、無成交價處理。
- 名稱比對：`*`、全形空白、指數名稱過濾、去重、對不到的名稱。
- 選股日期：UTC timestamp 換算成台灣時間；13:30 前後的切換、跳過週末、跨月找前一個交易日。
- `notion_writer.py`：properties 格式、查重時跳過。
- `reader.py`：用假的 Codex 輸出測 JSON 解析與錯誤處理。
- `runner.py`：等待行情不推進 state、3 次失敗後 ❌、12 小時逾時、全部成功 ✅、部分對不到 ⚠️。

實機驗證：部署後在頻道貼一張截圖，確認 Notion 新增的資料、價格與 emoji；再貼同一張，確認不會重複寫入。
