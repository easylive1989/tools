# anthropic-update-translator:Workers AI 翻譯 + 文章 → HackMD

日期:2026-05-30

## 目標

在現有 `anthropic_update_translator` Cloudflare Worker 上做兩件事:

1. 把翻譯引擎換成 **Cloudflare Workers AI**(`@cf/meta/llama-3.3-70b-instruct-fp8-fast`)。
2. 當 Anthropic 推文含有 **anthropic.com** 文章連結時,抓出該文章內容、翻成繁體中文、寫成一篇 **HackMD** 筆記,並把筆記連結附在發到 Discord 的訊息上。

核心 Discord 流程(每 5 分鐘輪詢 source 頻道 → filter → 翻譯推文 → 發 target 頻道)維持不變。HackMD 是**附加**功能,失敗不得中斷推文翻譯。

## 已確認的決策

| 項目 | 決定 |
|---|---|
| Discord 流程 | 保留;HackMD 為附加,連結附在 Discord 訊息上 |
| HackMD 組織 | 每篇文章一則新筆記 |
| 翻譯模型 | Workers AI `@cf/meta/llama-3.3-70b-instruct-fp8-fast` |
| 抓哪些連結 | 只抓 anthropic.com |
| 筆記內容 | 翻譯全文 + 原文標題/連結 |
| 筆記讀取權限 | guest(有連結就能看) |
| 長文章 | 段落分批翻譯後拼回 |

## 架構

新增 / 修改的模組:

### `src/translator/workersai.ts`(新增)

`WorkersAiTranslator implements Translator`。建構子接收 `env.AI`(型別 `Ai`)與 model 字串。

- `translate(text)`:推文翻譯,用 `buildPrompt(text)`(現有)。
- `translateArticle(markdown)`:文章翻譯,用 `buildArticlePrompt(markdown)`(新增)。

兩者都呼叫私有 `run(prompt)`:

```ts
const out = await this.ai.run(this.model, {
  messages: [{ role: "user", content: prompt }],
});
// out: { response: string }
```

錯誤統一丟 `TranslationError`(沿用現有型別)。

### `src/translator/types.ts`(修改)

- `Translator` 介面加 `translateArticle(markdown: string): Promise<string>`。
- 新增 `buildArticlePrompt(markdown)`:指示保留 markdown 結構、程式碼區塊、連結原樣,只輸出譯文。
- 新增 `validateArticleTranslation(translated)`:只檢查非空(放寬現有 `validateTranslation` 的「10 倍長度」上限,因為整篇文章譯文長度與單批原文不成比例)。

### `src/translator/index.ts`(修改)

`createTranslator(env)` 加 `case "workersai": return new WorkersAiTranslator(env.AI, env.WORKERSAI_MODEL)`。

gemini / claude 兩個實作各補上 `translateArticle`(換 prompt、用 `validateArticleTranslation`),維持三者介面一致與測試通過。

### `src/article.ts`(新增)

```ts
export interface Article {
  url: string;        // 最終(跟隨轉址後)的 anthropic.com 網址
  title: string;
  paragraphs: string[];
}

export async function extractAnthropicArticle(
  msg: DiscordMessage,
): Promise<Article | null>;
```

流程:
1. 從 `msg.content`、`msg.embeds[0].description`、`msg.embeds[0].url` 用 URL regex 收集候選連結。
2. 逐一 `fetch`(預設跟隨轉址),取 `res.url` 的 host;若 `host === "anthropic.com" || host.endsWith(".anthropic.com")` 即命中,讀取該 response 的 HTML。
3. 用 `HTMLRewriter` 抽 `<title>` / `<h1>` 當標題,抽正文段落(`article p`、`main p`,退而求其次 `p`),trim 後組成 `paragraphs`。
4. 任何失敗(無命中連結、fetch 失敗、無正文)→ 回傳 `null`。

> 風險:source 頻道訊息的實際結構未知(anthropic.com 連結可能是直接網址,也可能是 t.co 短網址)。「跟隨轉址看最終網址」可同時涵蓋兩者;若實作時行為不如預期,需取一則真實訊息 JSON 校正 URL 抽取邏輯。

### `src/chunk.ts`(新增)

```ts
export function chunkParagraphs(paragraphs: string[], maxChars: number): string[];
```

把段落貪婪地組成多個批次,每批字數(含段落間 `\n\n`)不超過 `maxChars`;單一段落超過 `maxChars` 時自成一批(不硬切字)。預設 `maxChars` 由 index 傳入(常數,例如 3000)。

### `src/hackmd.ts`(新增)

```ts
export class HackMdClient {
  constructor(private token: string) {}
  async createNote(content: string): Promise<{ publishLink: string }>;
}
```

`POST https://api.hackmd.io/v1/notes`,header `Authorization: Bearer <token>`、`Content-Type: application/json`,body:

```json
{ "content": "...", "readPermission": "guest", "writePermission": "owner", "commentPermission": "disabled" }
```

回傳 JSON 取 `publishLink`(若缺則丟錯)。非 2xx 丟錯。標題由 HackMD 從內文第一個 H1 推導。

### `src/format.ts`(修改)

- 新增 `buildHackMdContent(article: Article, translatedBody: string): string`:

  ```markdown
  # <article.title>

  > 原文:<article.url>

  <translatedBody>
  ```

- `buildOutgoingMessage(source, translated, hackmdUrl?)`:多一個可選參數;有 `hackmdUrl` 時把它附加到 `content`(在既有 tweet URL 後換行附上),embed 不變。

### `src/index.ts`(修改編排)

對每則通過 `shouldTranslate` 的訊息:

1. `translated = translator.translate(tweetText)`(沿用現有 retry / 推進 ID 邏輯)。
2. HackMD 支線,**整段包在 try/catch**:
   a. 先查 KV `hackmd:<msgId>`;有就直接用該 `publishLink`。
   b. 否則 `extractAnthropicArticle(msg)`;為 `null` 就跳過支線。
   c. `chunkParagraphs` → 逐批 `translator.translateArticle(batch)` → `\n\n` 拼回。
   d. `buildHackMdContent` → `hackmd.createNote(content)` → 取 `publishLink`。
   e. 存 KV `hackmd:<msgId>` = `publishLink`(冪等)。
   f. 任何步驟丟錯 → `console.error` 後 `hackmdUrl = undefined`,**繼續主流程**。
3. `buildOutgoingMessage(msg, translated, hackmdUrl)` → `discord.postMessage`(沿用現有失敗處理)。
4. 推進 `last_message_id`、清 retry(沿用)。

> 冪等性說明:推文翻譯失敗會在發 Discord 前 return 重試,此時尚未建 note,無副作用。HackMD note 建立後若 Discord 發送失敗,下次重跑會先命中 KV `hackmd:<msgId>`,不會重建 note。

### `src/env.ts`(修改)

```ts
export interface Env {
  // 既有
  DISCORD_BOT_TOKEN: string;
  GEMINI_API_KEY: string;
  CLAUDE_API_KEY?: string;
  SOURCE_CHANNEL_ID: string;
  TARGET_CHANNEL_ID: string;
  TRANSLATOR: "gemini" | "claude" | "workersai";
  GEMINI_MODEL: string;
  CLAUDE_MODEL: string;
  KV: KVNamespace;
  // 新增
  AI: Ai;
  WORKERSAI_MODEL: string;
  HACKMD_API_TOKEN: string;
}
```

## 設定 / 部署變更

- `wrangler.toml`:
  - `[vars]` 設 `TRANSLATOR = "workersai"`、`WORKERSAI_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"`。
  - 新增 `[ai]` 區塊 `binding = "AI"`。
- `.github/workflows/deploy-anthropic-translator.yml`:沿用現有 `cloudflare/wrangler-action` 的做法 —
  - `with.secrets:` 清單加一行 `HACKMD_API_TOKEN`(讓 wrangler 把它設為 Worker secret)。
  - `env:` 區塊加 `HACKMD_API_TOKEN: ${{ secrets.HACK_MD_API_KEY }}`(repo secret 名為 `HACK_MD_API_KEY`,Worker 內 env 名為 `HACKMD_API_TOKEN`,在此對應)。
  - Workers AI 是 binding 而非 secret,毋須在此加任何 key。
- README 更新:新增 Workers AI 設定(AI binding、無需 API key)、HackMD token 設定、anthropic.com → HackMD 行為說明。

> 安全:`HACK_MD_API_KEY` 只透過 GitHub Secrets 注入,不得寫入 git history、log 或文件範例。

## 測試

沿用現有 vitest 模式(`vi.stubGlobal("fetch", ...)`,KV 用 `MemoryKV`)。`env.AI` 以 mock 物件提供 `run()`。

新增測試檔:
- `test/translator/workersai.test.ts`:`translate` / `translateArticle` 解析 `{ response }`、錯誤丟 `TranslationError`。
- `test/article.test.ts`:命中 anthropic.com(含經由轉址)、非 anthropic.com 回 `null`、無正文回 `null`、HTML 解析出標題與段落。
- `test/chunk.test.ts`:多段落分批不超過上限、單一超長段落自成一批、空輸入。
- `test/hackmd.test.ts`:POST 帶正確 header/body、回傳 `publishLink`、非 2xx 丟錯。

擴充 `test/index.test.ts`:
- 有 anthropic.com 連結 → 建 HackMD note 且 Discord `content` 含 `publishLink`。
- 文章抓取/HackMD 失敗 → 推文照常發、Discord `content` 不含 HackMD 連結。
- KV 已有 `hackmd:<msgId>` → 不重建 note,直接用既有連結。
- 無 anthropic.com 連結 → 維持原行為(只發推文翻譯)。

`format.test.ts`、`filter.test.ts`、`state.test.ts` 既有測試維持綠燈;`gemini.test.ts` / `claude.test.ts` 補 `translateArticle` 案例。

## 不做(YAGNI)

- 不做文章內容的 readability 評分 / 去廣告等進階淨化,HTMLRewriter 抽段落即可。
- 不做 HackMD 筆記更新/累積(每篇一則新 note)。
- 不做非 anthropic.com 連結(youtube、github 等)。
- 不做中英對照排版(只放譯文 + 原文連結)。
