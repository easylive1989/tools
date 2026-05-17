# Anthropic Update Translator — Design

**Date:** 2026-05-17
**Status:** Draft (pending user review)
**Location:** `anthropic_update_translator/` (new directory in `tools` repo)

## 1. 目的

把 Discord `anthropic-update-raw` 頻道裡 `Claude AutoMod` 轉發的 Anthropic / Claude 官方 Twitter 推文,翻譯成繁體中文後轉發到 `anthropic-updates` 頻道,維持類似的視覺風格(Discord embed)。

## 2. 範圍

**本次實作:**

- Cloudflare Worker(TypeScript),每 5 分鐘 cron 輪詢一次。
- 讀取 source 頻道訊息(Discord Bot Token)。
- 過濾出符合條件的 Twitter embed 訊息。
- 用 **Gemini API**(預設 `gemini-2.5-flash`)翻譯 embed 描述。
- 在 target 頻道用同一個 Bot 發送翻譯後的 embed。
- 用 Cloudflare KV 追蹤進度與重試計數。
- 全部走 GitHub Actions 部署(無本機 `wrangler deploy` 步驟)。

**保留彈性:**

- 之後可改用 Claude API(透過環境變數 `TRANSLATOR=claude` 切換),不需改 code,只需設定 `CLAUDE_API_KEY` secret 與 var。

**不做:**

- 不補翻歷史訊息(首次部署從「現在」開始)。
- 不做整合測試打真 Discord/Gemini。
- 不支援 thread / 多則連發推文的串接;每則訊息獨立處理。

## 3. 高階架構

```
                 ┌─────────────────────────────┐
                 │   Cloudflare Worker         │
  Cron(*/5)─▶  │   (anthropic-update-        │
                 │    translator)              │
                 └─────────────────────────────┘
                       │                  ▲
                       │                  │ KV: last_message_id
                       ▼                  │      retry_count:<id>
                 ┌──────────┐         ┌───┴────┐
                 │ Discord  │         │  KV    │
                 │ REST API │         │ binding│
                 └────┬─────┘         └────────┘
                      │
              ┌───────┴─────────┐
              ▼                 ▼
         GET /channels/{src}  POST /channels/{dst}
         /messages            /messages
              │                 ▲
              ▼                 │
         過濾 + 翻譯 ────────────┘
              │
              ▼
         ┌───────────────────────┐
         │   Translator (介面)   │
         │  ├─ GeminiTranslator  │ (預設)
         │  └─ ClaudeTranslator  │ (未來)
         └───────────────────────┘
```

## 4. 元件與檔案結構

```
anthropic_update_translator/
├── wrangler.toml              # Worker 設定:cron、KV、vars
├── package.json
├── tsconfig.json
├── README.md                  # 部署與環境變數說明
├── src/
│   ├── index.ts               # Worker entry(scheduled handler)
│   ├── discord.ts             # Discord API client(fetch / post)
│   ├── filter.ts              # Twitter embed 過濾邏輯
│   ├── translator/
│   │   ├── index.ts           # createTranslator(env) 工廠
│   │   ├── types.ts           # Translator interface
│   │   ├── gemini.ts          # GeminiTranslator(預設)
│   │   └── claude.ts          # ClaudeTranslator(預留)
│   ├── state.ts               # KV 讀寫(last_message_id、retry_count)
│   └── format.ts              # Discord embed payload 組裝
└── test/
    ├── filter.test.ts
    ├── format.test.ts
    └── translator.test.ts
```

### 4.1 Translator 介面

```ts
// translator/types.ts
export interface Translator {
  translate(text: string): Promise<string>; // 回傳繁體中文翻譯
}

// translator/index.ts
export function createTranslator(env: Env): Translator {
  switch (env.TRANSLATOR) {
    case "gemini": return new GeminiTranslator(env.GEMINI_API_KEY, env.GEMINI_MODEL);
    case "claude": return new ClaudeTranslator(env.CLAUDE_API_KEY);
    default: throw new Error(`Unknown TRANSLATOR: ${env.TRANSLATOR}`);
  }
}
```

### 4.2 GeminiTranslator 細節

- Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`
- 預設 model: `gemini-2.5-flash`
- 超時:10 秒(用 `AbortController`)
- 失敗條件:
  - HTTP 非 2xx
  - 回傳 JSON 結構異常 / 無 `candidates[0].content.parts[0].text`
  - 翻譯結果為空字串
  - 翻譯結果長度 > 原文 10 倍(疑似失控輸出)

### 4.3 翻譯 Prompt

```
你是一個專業翻譯,請將以下 Anthropic / Claude 官方推文翻譯成「繁體中文(台灣用語)」。

規則:
1. 保留所有 URL 連結原樣不翻譯。
2. 保留所有 hashtag(例如 #ClaudeCode)原樣不翻譯。
3. 保留所有 @mention(例如 @AnthropicAI)原樣不翻譯。
4. 產品 / 品牌名稱(Claude, Anthropic, Sonnet, Opus, Haiku 等)保留原文。
5. 技術術語(API, token, prompt, agent 等)視語境決定是否保留原文;若中文較自然就翻成中文。
6. 只輸出翻譯結果,不要加任何說明、引言或前後綴。
7. 換行請保留與原文一致。

原文:
{{text}}
```

## 5. 資料流(每次 cron 執行)

```
1. 讀 KV: last_message_id
   - 若無 → GET /channels/{SRC}/messages?limit=1 取得當下最新 message id
                寫入 KV 後結束(首次部署不補翻歷史)
2. GET /channels/{SRC}/messages?after={last_message_id}&limit=50
3. 在程式中依 message ID(Snowflake)由小到大排序,確保處理順序為「舊 → 新」
4. for each message (舊到新):
   a. filter.shouldTranslate(msg) ?
        - 必須有 msg.embeds[0]
        - embed.author?.name 包含 "@AnthropicAI" 或 "@claudeai"
        - embed.description 非空
      否則跳過(只把 last_message_id 推進)
   b. text = msg.embeds[0].description
   c. try:
        translated = await translator.translate(text)
      catch:
        retry = await state.getRetryCount(msg.id) + 1
        若 retry >= 4:
          - state.clearRetryCount(msg.id)
          - state.setLastMessageId(msg.id)        // 永久跳過這則
          - 繼續下一則
        否則:
          - state.setRetryCount(msg.id, retry)
          - return                                 // 不推進 ID,等下次 cron
   d. POST /channels/{TGT}/messages
        - content: 推文 URL(優先 `embed.url`;若無,用 regex 從 `msg.content` 擷取第一個 `https://twitter.com/...` 或 `https://x.com/...`)
        - embeds: [{
            author: { name: 原 author.name, icon_url: 原 author.icon_url, url: 原 author.url },
            description: translated,
            url: 原 embed.url,
            thumbnail: 原 embed.thumbnail,
            footer: { text: "X" },        // Discord 會自動顯示下方 timestamp
            timestamp: 原 embed.timestamp,  // ISO 8601,沿用原 embed 的 timestamp
            color: 0xD97757
          }]
   e. state.setLastMessageId(msg.id)
   f. state.clearRetryCount(msg.id)  // 若有
5. 結束
```

### 5.1 重試機制細節

- KV key 格式:`retry:<message_id>` → value 為次數(數字字串)
- 重試上限 = **4 次**(對應 ~20 分鐘)
- 超過上限後該訊息**永久跳過**,並寫 `console.error` 記錄
- 訊息成功後立即清除對應的 retry key(避免累積)

## 6. 錯誤處理

| 錯誤類型 | 處理 |
|---|---|
| Discord 429 rate limit | 讀 `Retry-After` header,本次 return,不推進 ID |
| Discord 5xx / 網路錯誤 | 同上 |
| Discord 401/403(token 失效) | `console.error`,本次 return |
| Gemini 失敗 / 超時 / 空結果 / 長度異常 | 進入 retry_count 流程 |
| 目標頻道 POST 失敗 | 不推進 ID,下次 cron 整則重做(可能造成重複發送 — 接受) |
| KV 讀寫失敗 | `console.error`,本次 return |
| `embed.description` 超過 Gemini token 限制 | 不太可能(Twitter 280 字),不處理 |

所有錯誤都用 `console.error`,可在 Cloudflare Dashboard → Workers → Logs 觀察。

## 7. Env 變數與 Bindings

### `wrangler.toml`(commit 進 repo)

```toml
name = "anthropic-update-translator"
main = "src/index.ts"
compatibility_date = "2026-05-01"

[triggers]
crons = ["*/5 * * * *"]

[vars]
SOURCE_CHANNEL_ID = "<source channel id, 明文>"
TARGET_CHANNEL_ID = "<target channel id, 明文>"
TRANSLATOR = "gemini"
GEMINI_MODEL = "gemini-2.5-flash"

[[kv_namespaces]]
binding = "KV"
id = "<KV namespace id, 明文>"
```

### Secrets(透過 GitHub Actions 注入)

| Secret | 用途 | 首次部署是否必要 |
|---|---|---|
| `DISCORD_BOT_TOKEN` | Discord Bot 認證 | 必要 |
| `GEMINI_API_KEY` | Gemini API key | 必要 |
| `CLAUDE_API_KEY` | Claude API key | 否(切換 translator 時才加) |

## 8. 部署(純 GitHub Actions)

### 8.1 一次性手動設定

1. **Discord Bot 權限**:Bot 需加入 server,擁有 source 頻道的 `Read Messages` + `Read Message History`,以及 target 頻道的 `Send Messages` + `Embed Links`。
2. **Cloudflare Dashboard → Workers & Pages → KV** → 建立 namespace 命名 `anthropic-update-translator`,取得 namespace ID,寫進 `wrangler.toml` 並 commit。
3. **Cloudflare Dashboard → My Profile → API Tokens** → 建立 token,權限:
   - Account → Workers Scripts → Edit
   - Account → Workers KV Storage → Edit
   - Zone → 不需要
4. **GitHub repo Settings → Secrets and variables → Actions** 新增:
   - `CLOUDFLARE_API_TOKEN`
   - `CLOUDFLARE_ACCOUNT_ID`(在 Cloudflare Dashboard 右側面板可見)
   - `DISCORD_BOT_TOKEN`
   - `GEMINI_API_KEY`

### 8.2 GitHub Actions workflow

新增 `.github/workflows/deploy-anthropic-translator.yml`:

```yaml
name: Deploy anthropic-update-translator

on:
  push:
    branches: [master]
    paths:
      - "anthropic_update_translator/**"
      - ".github/workflows/deploy-anthropic-translator.yml"
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
        working-directory: anthropic_update_translator
      - run: npm test
        working-directory: anthropic_update_translator
      - uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          workingDirectory: anthropic_update_translator
          secrets: |
            DISCORD_BOT_TOKEN
            GEMINI_API_KEY
        env:
          DISCORD_BOT_TOKEN: ${{ secrets.DISCORD_BOT_TOKEN }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

### 8.3 首次部署流程

1. 完成 8.1 所有手動設定。
2. push 含 `anthropic_update_translator/` 與 workflow 的 commit 到 master(或手動觸發 `workflow_dispatch`)。
3. CI 跑完後,Cron 在下一個 5 分鐘整點觸發。
4. 觀察 Cloudflare Dashboard → Workers → Logs 確認執行結果。
5. 在 source 頻道測試:用個人 / 測試帳號貼一則含 Twitter URL 的訊息,等 5 分鐘看 target 頻道有沒有翻譯版。
   - 若 source 頻道無法測,改用 `workflow_dispatch` 觸發後手動發推驗證。

## 9. 測試策略

- **單元測試(Vitest + `@cloudflare/vitest-pool-workers`)**:
  - `filter.test.ts` — 驗證各種訊息形狀的過濾結果
    - 含 @AnthropicAI embed → 翻譯
    - 含 @claudeai embed → 翻譯
    - 無 embed 純文字 → 跳過
    - embed 沒有 description → 跳過
    - embed author 不符 → 跳過
  - `format.test.ts` — 驗證 Discord embed payload 組裝正確
  - `translator.test.ts` — mock `fetch`,驗證 Gemini request body 與回應解析
    - 成功 case
    - HTTP error
    - 空字串
    - 長度異常
- **本機開發**:`wrangler dev` 配合 vitest;不依賴本機部署。
- **不寫整合測試**打真 Discord 或 Gemini(成本與不穩定)。
- **部署後驗收**:GitHub Actions 部署成功後,觀察 Cloudflare Logs + target 頻道輸出。

## 10. 切換到 Claude(未來步驟)

1. 在 GitHub Secrets 新增 `CLAUDE_API_KEY`。
2. 在 `wrangler.toml` `[vars]` 修改 `TRANSLATOR = "claude"`。
3. 修改 workflow,在 `secrets:` 區塊與 `env:` 區塊加上 `CLAUDE_API_KEY`。
4. push 到 master 觸發部署。

無需改 code(`ClaudeTranslator` 在初版就寫好)。

## 11. 開放問題 / 待確認

(目前無;若實作中發現再補充)

## 12. 與其他工具的關係

獨立 Cloudflare Worker,不依賴 `common/` 下任何 Python 工具。Repo 根目錄 README / CLAUDE.md 之後可加一行說明這個工具的存在。
