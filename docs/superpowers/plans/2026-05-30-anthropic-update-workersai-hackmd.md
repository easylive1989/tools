# anthropic-update-translator:Workers AI 翻譯 + 文章 → HackMD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `anthropic_update_translator` 的翻譯引擎換成 Cloudflare Workers AI,並在推文含 anthropic.com 文章連結時抓全文翻成繁中、寫進 HackMD,把筆記連結附在發到 Discord 的訊息上。

**Architecture:** 在現有「輪詢 → filter → 翻譯推文 → 發 Discord」流程上,新增一條容錯的 HackMD 支線(抓文章 → 分批翻譯 → 建 note → 附連結),支線失敗不影響推文翻譯。翻譯改用 `env.AI.run`,文章 HTML 用純函式 regex 解析(node 與 Workers 皆可跑、可測),`article.ts` 的 fetch 可注入以利測試。

**Tech Stack:** TypeScript、Cloudflare Workers、Workers AI binding、HackMD REST API、vitest(node 環境)。

工作目錄:所有相對路徑以 `anthropic_update_translator/` 為基準。

驗證指令(每個 Task 結尾都會用到):
- 單檔測試:`cd anthropic_update_translator && npx vitest run <path>`
- 全部:`cd anthropic_update_translator && npm test`
- 型別:`cd anthropic_update_translator && npm run typecheck`

---

## Task 1:翻譯介面加入 `translateArticle` 與文章 prompt/驗證

**Files:**
- Modify: `anthropic_update_translator/src/translator/types.ts`
- Modify: `anthropic_update_translator/src/translator/gemini.ts`
- Modify: `anthropic_update_translator/src/translator/claude.ts`
- Test: `anthropic_update_translator/test/translator/gemini.test.ts`

- [ ] **Step 1: 在 `types.ts` 加介面方法、文章 prompt 與驗證**

把 `types.ts` 改成(在現有內容後新增 `buildArticlePrompt`、`validateArticleTranslation`,並在 `Translator` 介面加方法):

```ts
export interface Translator {
  translate(text: string): Promise<string>;
  translateArticle(markdown: string): Promise<string>;
}

export class TranslationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TranslationError";
  }
}

export function buildPrompt(text: string): string {
  return [
    "你是一個專業翻譯,請將以下 Anthropic / Claude 官方推文翻譯成「繁體中文(台灣用語)」。",
    "",
    "規則:",
    "1. 保留所有 URL 連結原樣不翻譯。",
    "2. 保留所有 hashtag(例如 #ClaudeCode)原樣不翻譯。",
    "3. 保留所有 @mention(例如 @AnthropicAI)原樣不翻譯。",
    "4. 產品 / 品牌名稱(Claude, Anthropic, Sonnet, Opus, Haiku 等)保留原文。",
    "5. 技術術語(API, token, prompt, agent 等)視語境決定是否保留原文;若中文較自然就翻成中文。",
    "6. 只輸出翻譯結果,不要加任何說明、引言或前後綴。",
    "7. 換行請保留與原文一致。",
    "",
    "原文:",
    text,
  ].join("\n");
}

export function buildArticlePrompt(markdown: string): string {
  return [
    "你是一個專業翻譯,請將以下 Anthropic 官方文章內容翻譯成「繁體中文(台灣用語)」。",
    "",
    "規則:",
    "1. 保留所有 URL 連結與 markdown 連結語法原樣。",
    "2. 保留 markdown 結構(標題層級、清單、粗體等)。",
    "3. 程式碼區塊與行內程式碼的內容保留原樣不翻譯。",
    "4. 產品 / 品牌名稱(Claude, Anthropic, Sonnet, Opus, Haiku 等)保留原文。",
    "5. 技術術語視語境決定是否保留原文;若中文較自然就翻成中文。",
    "6. 只輸出翻譯結果,不要加任何說明、引言或前後綴。",
    "",
    "原文:",
    markdown,
  ].join("\n");
}

export function validateTranslation(original: string, translated: string): void {
  const t = translated.trim();
  if (t === "") {
    throw new TranslationError("translator returned empty string");
  }
  if (t.length > original.length * 10) {
    throw new TranslationError(
      `translator output too long: ${t.length} chars (original ${original.length})`,
    );
  }
}

export function validateArticleTranslation(translated: string): void {
  if (translated.trim() === "") {
    throw new TranslationError("translator returned empty string");
  }
}
```

- [ ] **Step 2: 在 `gemini.ts` 實作 `translateArticle`**

`gemini.ts` 頂部 import 改成包含新符號:

```ts
import {
  buildArticlePrompt,
  buildPrompt,
  TranslationError,
  validateArticleTranslation,
  validateTranslation,
  type Translator,
} from "./types";
```

把 `GeminiTranslator` 內的請求邏輯抽成私有 `request(prompt)`,並讓 `translate` / `translateArticle` 共用。整個 class 改成:

```ts
export class GeminiTranslator implements Translator {
  constructor(private apiKey: string, private model: string) {}

  async translate(text: string): Promise<string> {
    const translated = await this.request(buildPrompt(text));
    validateTranslation(text, translated);
    return translated.trim();
  }

  async translateArticle(markdown: string): Promise<string> {
    const translated = await this.request(buildArticlePrompt(markdown));
    validateArticleTranslation(translated);
    return translated.trim();
  }

  private async request(prompt: string): Promise<string> {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${this.model}:generateContent?key=${this.apiKey}`;
    const body = JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] });

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);

    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        signal: ctrl.signal,
      });
    } catch (err) {
      throw new TranslationError(`Gemini fetch failed: ${(err as Error).message}`);
    } finally {
      clearTimeout(timer);
    }

    if (!res.ok) {
      throw new TranslationError(`Gemini HTTP ${res.status}: ${await res.text()}`);
    }

    const data = (await res.json()) as GeminiResponse;
    const translated = data.candidates?.[0]?.content?.parts?.[0]?.text;
    if (typeof translated !== "string") {
      throw new TranslationError(
        `Gemini response missing candidates[0].content.parts[0].text: ${JSON.stringify(data)}`,
      );
    }
    return translated;
  }
}
```

(保留檔案頂部既有的 `const TIMEOUT_MS = 10_000;` 與 `interface GeminiResponse {...}`。)

- [ ] **Step 3: 在 `claude.ts` 實作 `translateArticle`**

`claude.ts` 頂部 import 改成:

```ts
import {
  buildArticlePrompt,
  buildPrompt,
  TranslationError,
  validateArticleTranslation,
  validateTranslation,
  type Translator,
} from "./types";
```

class 改成共用私有 `request(prompt)`:

```ts
export class ClaudeTranslator implements Translator {
  constructor(private apiKey: string, private model: string) {}

  async translate(text: string): Promise<string> {
    const translated = await this.request(buildPrompt(text));
    validateTranslation(text, translated);
    return translated.trim();
  }

  async translateArticle(markdown: string): Promise<string> {
    const translated = await this.request(buildArticlePrompt(markdown));
    validateArticleTranslation(translated);
    return translated.trim();
  }

  private async request(prompt: string): Promise<string> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);

    let res: Response;
    try {
      res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "x-api-key": this.apiKey,
          "anthropic-version": "2023-06-01",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          model: this.model,
          max_tokens: MAX_TOKENS,
          messages: [{ role: "user", content: prompt }],
        }),
        signal: ctrl.signal,
      });
    } catch (err) {
      throw new TranslationError(`Claude fetch failed: ${(err as Error).message}`);
    } finally {
      clearTimeout(timer);
    }

    if (!res.ok) {
      throw new TranslationError(`Claude HTTP ${res.status}: ${await res.text()}`);
    }

    const data = (await res.json()) as ClaudeResponse;
    const block = data.content?.find((c) => c.type === "text");
    const translated = block?.text;
    if (typeof translated !== "string") {
      throw new TranslationError(
        `Claude response missing content[*].text: ${JSON.stringify(data)}`,
      );
    }
    return translated;
  }
}
```

(保留檔案頂部既有的 `const TIMEOUT_MS`、`const MAX_TOKENS`、`interface ClaudeResponse`。)

- [ ] **Step 4: 在 `gemini.test.ts` 加 `translateArticle` 測試**

在 `describe("GeminiTranslator", ...)` 內最後加:

```ts
  it("translateArticle 用文章 prompt 並回傳譯文", async () => {
    let capturedBody = "";
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init: RequestInit) => {
        capturedBody = init.body as string;
        return Promise.resolve(
          new Response(
            JSON.stringify({ candidates: [{ content: { parts: [{ text: "翻好的長文章內容" }] } }] }),
            { status: 200 },
          ),
        );
      }),
    );

    const t = new GeminiTranslator("KEY", "gemini-2.5-flash");
    const out = await t.translateArticle("# Title\n\nLong body paragraph.");

    expect(out).toBe("翻好的長文章內容");
    expect(JSON.parse(capturedBody).contents[0].parts[0].text).toContain("Long body paragraph.");
  });

  it("translateArticle 不套用 10 倍長度上限", async () => {
    const longOut = "中".repeat(500);
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({ candidates: [{ content: { parts: [{ text: longOut }] } }] }),
            { status: 200 },
          ),
        ),
      ),
    );
    const t = new GeminiTranslator("KEY", "gemini-2.5-flash");
    await expect(t.translateArticle("ab")).resolves.toBe(longOut);
  });
```

- [ ] **Step 5: 跑測試確認失敗再實作後通過**

Run: `cd anthropic_update_translator && npx vitest run test/translator/gemini.test.ts`
Expected: 上面新增的兩個測試先 FAIL(尚未實作)→ 完成 Step 1–3 後重跑全部 PASS。

- [ ] **Step 6: 型別檢查**

Run: `cd anthropic_update_translator && npm run typecheck`
Expected: 通過(此時 `index.ts`/factory 尚未用到 workersai,gemini/claude 已實作介面新方法)。

- [ ] **Step 7: Commit**

```bash
cd anthropic_update_translator
git add src/translator/types.ts src/translator/gemini.ts src/translator/claude.ts test/translator/gemini.test.ts
git commit -m "feat(translator): add translateArticle to Translator interface"
```

---

## Task 2:新增 `WorkersAiTranslator` 與 env/factory 接線

**Files:**
- Create: `anthropic_update_translator/src/translator/workersai.ts`
- Modify: `anthropic_update_translator/src/env.ts`
- Modify: `anthropic_update_translator/src/translator/index.ts`
- Test: `anthropic_update_translator/test/translator/workersai.test.ts`

- [ ] **Step 1: 寫失敗測試 `workersai.test.ts`**

```ts
import { describe, expect, it, vi } from "vitest";
import { WorkersAiTranslator } from "../../src/translator/workersai";
import { TranslationError } from "../../src/translator/types";

function fakeAi(run: (model: string, opts: { messages: { role: string; content: string }[] }) => unknown) {
  return { run: vi.fn(run) } as unknown as Ai;
}

const MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast";

describe("WorkersAiTranslator", () => {
  it("translate 呼叫 env.AI.run 並回傳 response", async () => {
    const ai = fakeAi(() => ({ response: "翻譯結果" }));
    const t = new WorkersAiTranslator(ai, MODEL);
    const out = await t.translate("Hello");

    expect(out).toBe("翻譯結果");
    expect((ai.run as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(MODEL);
    const messages = (ai.run as ReturnType<typeof vi.fn>).mock.calls[0][1].messages;
    expect(messages[0].content).toContain("Hello");
  });

  it("translateArticle 用文章 prompt 並回傳 response", async () => {
    const ai = fakeAi(() => ({ response: "翻好的文章" }));
    const t = new WorkersAiTranslator(ai, MODEL);
    const out = await t.translateArticle("Long body");

    expect(out).toBe("翻好的文章");
    const messages = (ai.run as ReturnType<typeof vi.fn>).mock.calls[0][1].messages;
    expect(messages[0].content).toContain("Long body");
  });

  it("response 缺 response 欄位時拋 TranslationError", async () => {
    const ai = fakeAi(() => ({ foo: "bar" }));
    const t = new WorkersAiTranslator(ai, MODEL);
    await expect(t.translate("x")).rejects.toBeInstanceOf(TranslationError);
  });

  it("env.AI.run 丟錯時轉成 TranslationError", async () => {
    const ai = fakeAi(() => {
      throw new Error("boom");
    });
    const t = new WorkersAiTranslator(ai, MODEL);
    await expect(t.translate("x")).rejects.toBeInstanceOf(TranslationError);
  });

  it("response 為空字串時拋 TranslationError", async () => {
    const ai = fakeAi(() => ({ response: "   " }));
    const t = new WorkersAiTranslator(ai, MODEL);
    await expect(t.translate("x")).rejects.toBeInstanceOf(TranslationError);
  });
});
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd anthropic_update_translator && npx vitest run test/translator/workersai.test.ts`
Expected: FAIL(`Cannot find module ../../src/translator/workersai`)。

- [ ] **Step 3: 實作 `workersai.ts`**

```ts
import {
  buildArticlePrompt,
  buildPrompt,
  TranslationError,
  validateArticleTranslation,
  validateTranslation,
  type Translator,
} from "./types";

interface WorkersAiTextOutput {
  response?: string;
}

export class WorkersAiTranslator implements Translator {
  constructor(private ai: Ai, private model: string) {}

  async translate(text: string): Promise<string> {
    const translated = await this.run(buildPrompt(text));
    validateTranslation(text, translated);
    return translated.trim();
  }

  async translateArticle(markdown: string): Promise<string> {
    const translated = await this.run(buildArticlePrompt(markdown));
    validateArticleTranslation(translated);
    return translated.trim();
  }

  private async run(prompt: string): Promise<string> {
    let out: unknown;
    try {
      out = await this.ai.run(this.model as keyof AiModels, {
        messages: [{ role: "user", content: prompt }],
      });
    } catch (err) {
      throw new TranslationError(`Workers AI run failed: ${(err as Error).message}`);
    }
    const text = (out as WorkersAiTextOutput).response;
    if (typeof text !== "string") {
      throw new TranslationError(
        `Workers AI response missing 'response': ${JSON.stringify(out)}`,
      );
    }
    return text;
  }
}
```

> 註:`this.model as keyof AiModels` 是為了滿足 `Ai.run` 的型別簽章;若 typecheck 對該 cast 有意見,改用 `(this.ai.run as (model: string, opts: unknown) => Promise<unknown>)(this.model, { messages: [...] })`。

- [ ] **Step 4: 更新 `env.ts`**

```ts
export interface Env {
  DISCORD_BOT_TOKEN: string;
  GEMINI_API_KEY: string;
  CLAUDE_API_KEY?: string;

  SOURCE_CHANNEL_ID: string;
  TARGET_CHANNEL_ID: string;
  TRANSLATOR: "gemini" | "claude" | "workersai";
  GEMINI_MODEL: string;
  CLAUDE_MODEL: string;
  WORKERSAI_MODEL: string;
  HACKMD_API_TOKEN: string;

  AI: Ai;
  KV: KVNamespace;
}
```

- [ ] **Step 5: 更新 factory `translator/index.ts`**

```ts
import type { Env } from "../env";
import { GeminiTranslator } from "./gemini";
import { ClaudeTranslator } from "./claude";
import { WorkersAiTranslator } from "./workersai";
import type { Translator } from "./types";

export type { Translator } from "./types";

export function createTranslator(env: Env): Translator {
  switch (env.TRANSLATOR) {
    case "gemini":
      return new GeminiTranslator(env.GEMINI_API_KEY, env.GEMINI_MODEL);
    case "claude": {
      if (!env.CLAUDE_API_KEY) {
        throw new Error("CLAUDE_API_KEY is required when TRANSLATOR=claude");
      }
      return new ClaudeTranslator(env.CLAUDE_API_KEY, env.CLAUDE_MODEL);
    }
    case "workersai":
      return new WorkersAiTranslator(env.AI, env.WORKERSAI_MODEL);
    default:
      throw new Error(`Unknown TRANSLATOR: ${env.TRANSLATOR}`);
  }
}
```

- [ ] **Step 6: 跑測試 + 型別檢查**

Run: `cd anthropic_update_translator && npx vitest run test/translator/workersai.test.ts && npm run typecheck`
Expected: 測試 PASS;typecheck 此時會因 `index.test.ts` 的 `makeEnv` 缺 `AI`/`WORKERSAI_MODEL`/`HACKMD_API_TOKEN` 而報錯 —— **此屬預期**,將在 Task 8 修正 `makeEnv`。先確認 workersai 測試本身 PASS 即可。

- [ ] **Step 7: Commit**

```bash
cd anthropic_update_translator
git add src/translator/workersai.ts src/env.ts src/translator/index.ts test/translator/workersai.test.ts
git commit -m "feat(translator): add WorkersAiTranslator and factory wiring"
```

---

## Task 3:段落分批 `chunk.ts`

**Files:**
- Create: `anthropic_update_translator/src/chunk.ts`
- Test: `anthropic_update_translator/test/chunk.test.ts`

- [ ] **Step 1: 寫失敗測試 `chunk.test.ts`**

```ts
import { describe, expect, it } from "vitest";
import { chunkParagraphs } from "../src/chunk";

describe("chunkParagraphs", () => {
  it("空輸入回傳空陣列", () => {
    expect(chunkParagraphs([], 100)).toEqual([]);
  });

  it("全部塞得下時只回一批", () => {
    const out = chunkParagraphs(["aaa", "bbb"], 100);
    expect(out).toEqual(["aaa\n\nbbb"]);
  });

  it("超過上限時切成多批(以 \\n\\n 連接計長)", () => {
    // "aaaa"(4) + "\n\n"(2) + "bbbb"(4) = 10 > 8,所以拆開
    const out = chunkParagraphs(["aaaa", "bbbb"], 8);
    expect(out).toEqual(["aaaa", "bbbb"]);
  });

  it("單一段落超過上限時自成一批,不硬切字", () => {
    const long = "x".repeat(50);
    const out = chunkParagraphs([long, "y"], 10);
    expect(out).toEqual([long, "y"]);
  });
});
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd anthropic_update_translator && npx vitest run test/chunk.test.ts`
Expected: FAIL(`Cannot find module ../src/chunk`)。

- [ ] **Step 3: 實作 `chunk.ts`**

```ts
/**
 * 把段落貪婪地組成多批,每批(以 "\n\n" 連接後)的長度不超過 maxChars。
 * 單一段落本身超過 maxChars 時自成一批,不硬切字。
 */
export function chunkParagraphs(paragraphs: string[], maxChars: number): string[] {
  const batches: string[] = [];
  let cur: string[] = [];

  for (const p of paragraphs) {
    if (cur.length > 0) {
      const candidate = [...cur, p].join("\n\n");
      if (candidate.length > maxChars) {
        batches.push(cur.join("\n\n"));
        cur = [p];
        continue;
      }
    }
    cur.push(p);
  }

  if (cur.length > 0) {
    batches.push(cur.join("\n\n"));
  }
  return batches;
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd anthropic_update_translator && npx vitest run test/chunk.test.ts`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
cd anthropic_update_translator
git add src/chunk.ts test/chunk.test.ts
git commit -m "feat: add chunkParagraphs for batched article translation"
```

---

## Task 4:文章抓取 `article.ts`

**Files:**
- Create: `anthropic_update_translator/src/article.ts`
- Test: `anthropic_update_translator/test/article.test.ts`

說明:`extractAnthropicArticle(msg, fetchImpl=fetch)` 的 `fetchImpl` 預設為 global `fetch`,測試時注入假 fetch 以控制 `res.url`、`res.ok`、`res.text()`。HTML 解析用純函式 regex(node/Workers 皆可)。

- [ ] **Step 1: 寫失敗測試 `article.test.ts`**

```ts
import { describe, expect, it, vi } from "vitest";
import {
  collectUrls,
  isAnthropicHost,
  extractArticleFromHtml,
  extractAnthropicArticle,
} from "../src/article";
import type { DiscordMessage } from "../src/filter";

function fakeResponse(opts: { ok?: boolean; url?: string; html?: string }) {
  return {
    ok: opts.ok ?? true,
    status: opts.ok === false ? 500 : 200,
    url: opts.url ?? "",
    text: async () => opts.html ?? "",
  } as unknown as Response;
}

const HTML = `
  <html><head><title>Fallback Title</title></head>
  <body><article>
    <h1>Real Title</h1>
    <p>First paragraph.</p>
    <p>  Second &amp; paragraph.  </p>
    <p></p>
  </article></body></html>`;

describe("collectUrls", () => {
  it("從 content / description / embed.url 收集並去重", () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "see https://www.anthropic.com/news/x and https://t.co/abc",
      embeds: [{ description: "https://www.anthropic.com/news/x", url: "https://twitter.com/AnthropicAI/status/1" }],
    };
    const urls = collectUrls(msg);
    expect(urls).toContain("https://www.anthropic.com/news/x");
    expect(urls).toContain("https://t.co/abc");
    expect(urls.filter((u) => u === "https://www.anthropic.com/news/x")).toHaveLength(1);
  });
});

describe("isAnthropicHost", () => {
  it("anthropic.com 與子網域為真,其他為假", () => {
    expect(isAnthropicHost("https://www.anthropic.com/news/x")).toBe(true);
    expect(isAnthropicHost("https://anthropic.com/x")).toBe(true);
    expect(isAnthropicHost("https://youtube.com/x")).toBe(false);
    expect(isAnthropicHost("not a url")).toBe(false);
  });
});

describe("extractArticleFromHtml", () => {
  it("抽出 h1 標題與非空段落,解碼 entity", () => {
    const parsed = extractArticleFromHtml(HTML);
    expect(parsed).not.toBeNull();
    expect(parsed!.title).toBe("Real Title");
    expect(parsed!.paragraphs).toEqual(["First paragraph.", "Second & paragraph."]);
  });

  it("無段落時回 null", () => {
    expect(extractArticleFromHtml("<html><h1>x</h1></html>")).toBeNull();
  });
});

describe("extractAnthropicArticle", () => {
  it("直連 anthropic.com → 抓 HTML 並回傳 Article", async () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "https://www.anthropic.com/news/x",
      embeds: [{ description: "text", url: "https://twitter.com/AnthropicAI/status/1" }],
    };
    const fetchImpl = vi.fn(async () => fakeResponse({ html: HTML }));
    const article = await extractAnthropicArticle(msg, fetchImpl as unknown as typeof fetch);

    expect(article).not.toBeNull();
    expect(article!.url).toBe("https://www.anthropic.com/news/x");
    expect(article!.title).toBe("Real Title");
    expect(article!.paragraphs[0]).toBe("First paragraph.");
  });

  it("t.co 短網址轉址到 anthropic.com → 用最終網址", async () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "https://t.co/abc",
      embeds: [{ description: "text", url: "https://twitter.com/AnthropicAI/status/1" }],
    };
    const fetchImpl = vi.fn(async () =>
      fakeResponse({ url: "https://www.anthropic.com/news/y", html: HTML }),
    );
    const article = await extractAnthropicArticle(msg, fetchImpl as unknown as typeof fetch);

    expect(article).not.toBeNull();
    expect(article!.url).toBe("https://www.anthropic.com/news/y");
  });

  it("沒有 anthropic.com 連結 → 回 null,不 fetch", async () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "https://youtube.com/watch?v=1",
      embeds: [{ description: "text", url: "https://twitter.com/AnthropicAI/status/1" }],
    };
    const fetchImpl = vi.fn();
    const article = await extractAnthropicArticle(msg, fetchImpl as unknown as typeof fetch);

    expect(article).toBeNull();
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("fetch 失敗 → 回 null", async () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "https://www.anthropic.com/news/x",
      embeds: [{ description: "text" }],
    };
    const fetchImpl = vi.fn(async () => fakeResponse({ ok: false }));
    const article = await extractAnthropicArticle(msg, fetchImpl as unknown as typeof fetch);
    expect(article).toBeNull();
  });
});
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd anthropic_update_translator && npx vitest run test/article.test.ts`
Expected: FAIL(`Cannot find module ../src/article`)。

- [ ] **Step 3: 實作 `article.ts`**

```ts
import type { DiscordMessage } from "./filter";

export interface Article {
  url: string;
  title: string;
  paragraphs: string[];
}

const URL_REGEX = /https?:\/\/[^\s)"'<>]+/g;
const SHORT_LINK_HOSTS = new Set(["t.co", "bit.ly", "buff.ly", "ow.ly"]);

export function collectUrls(msg: DiscordMessage): string[] {
  const embed = msg.embeds[0];
  const haystack = [msg.content ?? "", embed?.description ?? "", embed?.url ?? ""].join("\n");
  const found = haystack.match(URL_REGEX) ?? [];
  const cleaned = found.map((u) => u.replace(/[.,);]+$/, ""));
  return [...new Set(cleaned)];
}

export function isAnthropicHost(urlString: string): boolean {
  try {
    const host = new URL(urlString).host.toLowerCase();
    return host === "anthropic.com" || host.endsWith(".anthropic.com");
  } catch {
    return false;
  }
}

function isShortLink(urlString: string): boolean {
  try {
    return SHORT_LINK_HOSTS.has(new URL(urlString).host.toLowerCase());
  } catch {
    return false;
  }
}

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, "");
}

function decodeEntities(text: string): string {
  return text
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ");
}

function clean(html: string): string {
  return decodeEntities(stripTags(html)).replace(/\s+/g, " ").trim();
}

export function extractArticleFromHtml(html: string): { title: string; paragraphs: string[] } | null {
  const h1 = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i);
  const titleTag = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  const title = clean(h1?.[1] ?? titleTag?.[1] ?? "") || "Anthropic";

  const paragraphs: string[] = [];
  for (const m of html.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/gi)) {
    const text = clean(m[1] ?? "");
    if (text !== "") paragraphs.push(text);
  }
  if (paragraphs.length === 0) return null;
  return { title, paragraphs };
}

export async function extractAnthropicArticle(
  msg: DiscordMessage,
  fetchImpl: typeof fetch = fetch,
): Promise<Article | null> {
  for (const url of collectUrls(msg)) {
    if (!isAnthropicHost(url) && !isShortLink(url)) continue;

    let resp: Response;
    try {
      resp = await fetchImpl(url, { redirect: "follow" });
    } catch {
      continue;
    }
    if (!resp.ok) continue;

    const finalUrl = resp.url || url;
    if (!isAnthropicHost(finalUrl)) continue;

    let html: string;
    try {
      html = await resp.text();
    } catch {
      continue;
    }

    const parsed = extractArticleFromHtml(html);
    if (!parsed) continue;

    return { url: finalUrl, title: parsed.title, paragraphs: parsed.paragraphs };
  }
  return null;
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd anthropic_update_translator && npx vitest run test/article.test.ts`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
cd anthropic_update_translator
git add src/article.ts test/article.test.ts
git commit -m "feat: add anthropic.com article extraction"
```

---

## Task 5:HackMD 客戶端 `hackmd.ts`

**Files:**
- Create: `anthropic_update_translator/src/hackmd.ts`
- Test: `anthropic_update_translator/test/hackmd.test.ts`

- [ ] **Step 1: 寫失敗測試 `hackmd.test.ts`**

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { HackMdClient } from "../src/hackmd";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HackMdClient", () => {
  it("POST 到 /v1/notes 帶正確 header 與 body,回傳 publishLink", async () => {
    let capturedUrl = "";
    let capturedInit: RequestInit = {};
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit) => {
        capturedUrl = url;
        capturedInit = init;
        return Promise.resolve(
          new Response(JSON.stringify({ id: "abc", publishLink: "https://hackmd.io/@x/abc" }), {
            status: 201,
          }),
        );
      }),
    );

    const client = new HackMdClient("TOKEN");
    const out = await client.createNote("# Title\n\nbody");

    expect(out.publishLink).toBe("https://hackmd.io/@x/abc");
    expect(capturedUrl).toBe("https://api.hackmd.io/v1/notes");
    const headers = capturedInit.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer TOKEN");
    const body = JSON.parse(capturedInit.body as string);
    expect(body.content).toBe("# Title\n\nbody");
    expect(body.readPermission).toBe("guest");
    expect(body.writePermission).toBe("owner");
  });

  it("非 2xx 時丟錯", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("nope", { status: 403 }))));
    const client = new HackMdClient("TOKEN");
    await expect(client.createNote("x")).rejects.toThrow(/HackMD createNote failed/);
  });

  it("回應缺 publishLink 時丟錯", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({ id: "abc" }), { status: 201 }))),
    );
    const client = new HackMdClient("TOKEN");
    await expect(client.createNote("x")).rejects.toThrow(/missing publishLink/);
  });
});
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd anthropic_update_translator && npx vitest run test/hackmd.test.ts`
Expected: FAIL(`Cannot find module ../src/hackmd`)。

- [ ] **Step 3: 實作 `hackmd.ts`**

```ts
const API_URL = "https://api.hackmd.io/v1/notes";

interface CreateNoteResponse {
  id?: string;
  publishLink?: string;
}

export class HackMdClient {
  constructor(private token: string) {}

  async createNote(content: string): Promise<{ publishLink: string }> {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        content,
        readPermission: "guest",
        writePermission: "owner",
        commentPermission: "disabled",
      }),
    });

    if (!res.ok) {
      throw new Error(`HackMD createNote failed: ${res.status} ${await res.text()}`);
    }

    const data = (await res.json()) as CreateNoteResponse;
    if (!data.publishLink) {
      throw new Error(`HackMD response missing publishLink: ${JSON.stringify(data)}`);
    }
    return { publishLink: data.publishLink };
  }
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd anthropic_update_translator && npx vitest run test/hackmd.test.ts`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
cd anthropic_update_translator
git add src/hackmd.ts test/hackmd.test.ts
git commit -m "feat: add HackMD note client"
```

---

## Task 6:`format.ts` —— HackMD 內文與 Discord 訊息附連結

**Files:**
- Modify: `anthropic_update_translator/src/format.ts`
- Test: `anthropic_update_translator/test/format.test.ts`

- [ ] **Step 1: 在 `format.test.ts` 加測試**

先讀現有 `test/format.test.ts` 的 import 與 helper(建立 `DiscordMessage` 的方式),在其 `describe` 內新增以下測試(沿用該檔既有的訊息建構 helper;若無 helper 則用內聯物件如下):

```ts
import { buildHackMdContent } from "../src/format";
import type { Article } from "../src/article";

describe("buildHackMdContent", () => {
  it("組出 H1 標題 + 來源行 + 譯文", () => {
    const article: Article = {
      url: "https://www.anthropic.com/news/x",
      title: "New Model",
      paragraphs: ["a", "b"],
    };
    const out = buildHackMdContent(article, "翻好的內文");
    expect(out).toContain("# New Model");
    expect(out).toContain("> 原文:https://www.anthropic.com/news/x");
    expect(out).toContain("翻好的內文");
    expect(out.indexOf("# New Model")).toBeLessThan(out.indexOf("翻好的內文"));
  });
});

describe("buildOutgoingMessage with hackmdUrl", () => {
  it("有 hackmdUrl 時附在 content", () => {
    const source = {
      id: "1",
      content: "https://twitter.com/AnthropicAI/status/1",
      embeds: [{ author: { name: "Anthropic (@AnthropicAI)" }, description: "hi", url: "https://twitter.com/AnthropicAI/status/1" }],
    };
    const out = buildOutgoingMessage(source, "你好", "https://hackmd.io/@x/abc");
    expect(out.content).toContain("https://twitter.com/AnthropicAI/status/1");
    expect(out.content).toContain("https://hackmd.io/@x/abc");
    expect(out.embeds[0].description).toBe("你好");
  });

  it("無 hackmdUrl 時 content 不變(只有 tweet 連結)", () => {
    const source = {
      id: "1",
      content: "https://twitter.com/AnthropicAI/status/1",
      embeds: [{ author: { name: "Anthropic (@AnthropicAI)" }, description: "hi", url: "https://twitter.com/AnthropicAI/status/1" }],
    };
    const out = buildOutgoingMessage(source, "你好");
    expect(out.content).toBe("https://twitter.com/AnthropicAI/status/1");
  });
});
```

> 註:若 `format.test.ts` 既有 import 已有 `buildOutgoingMessage`,不要重複 import;只補上 `buildHackMdContent` 與 `Article` 型別的 import。

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd anthropic_update_translator && npx vitest run test/format.test.ts`
Expected: FAIL(`buildHackMdContent` 不存在 / `buildOutgoingMessage` 第三參數行為未實作)。

- [ ] **Step 3: 修改 `format.ts`**

```ts
import type { DiscordEmbed, DiscordMessage } from "./filter";
import type { Article } from "./article";

const ANTHROPIC_ORANGE = 0xd97757;
const TWITTER_URL_REGEX = /https?:\/\/(?:twitter\.com|x\.com)\/[^\s)"'<>,]+/i;

export interface OutgoingMessage {
  content: string;
  embeds: DiscordEmbed[];
}

export function buildOutgoingMessage(
  source: DiscordMessage,
  translated: string,
  hackmdUrl?: string,
): OutgoingMessage {
  const sourceEmbed = source.embeds[0];
  if (!sourceEmbed) {
    throw new Error("buildOutgoingMessage: source has no embed");
  }

  const tweetUrl =
    sourceEmbed.url ?? source.content.match(TWITTER_URL_REGEX)?.[0] ?? "";

  const lines: string[] = [];
  if (tweetUrl) lines.push(tweetUrl);
  if (hackmdUrl) lines.push(`📄 全文翻譯:${hackmdUrl}`);

  const embed: DiscordEmbed = {
    author: sourceEmbed.author,
    description: translated,
    url: sourceEmbed.url,
    timestamp: sourceEmbed.timestamp,
    thumbnail: sourceEmbed.thumbnail,
    footer: { text: "X" },
    color: ANTHROPIC_ORANGE,
  };

  return {
    content: lines.join("\n"),
    embeds: [embed],
  };
}

export function buildHackMdContent(article: Article, translatedBody: string): string {
  return [`# ${article.title}`, "", `> 原文:${article.url}`, "", translatedBody, ""].join("\n");
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd anthropic_update_translator && npx vitest run test/format.test.ts`
Expected: PASS(含既有測試)。

- [ ] **Step 5: Commit**

```bash
cd anthropic_update_translator
git add src/format.ts test/format.test.ts
git commit -m "feat(format): HackMD content builder and Discord link append"
```

---

## Task 7:`state.ts` —— HackMD note 連結的冪等快取

**Files:**
- Modify: `anthropic_update_translator/src/state.ts`
- Test: `anthropic_update_translator/test/state.test.ts`

- [ ] **Step 1: 在 `state.test.ts` 加測試**

在現有 `describe("State", ...)`(沿用該檔建立 `State` 與 `MemoryKV` 的方式)內加:

```ts
  it("getHackMdLink 預設為 null,set 後可取回", async () => {
    const kv = new MemoryKV();
    const state = new State(asKV(kv));
    expect(await state.getHackMdLink("101")).toBeNull();
    await state.setHackMdLink("101", "https://hackmd.io/@x/abc");
    expect(await state.getHackMdLink("101")).toBe("https://hackmd.io/@x/abc");
  });
```

> 註:`state.test.ts` 既有 import 應已含 `State`、`MemoryKV`、`asKV`;若缺 `asKV` 則從 `./helpers` 補。

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd anthropic_update_translator && npx vitest run test/state.test.ts`
Expected: FAIL(`getHackMdLink` 不存在)。

- [ ] **Step 3: 修改 `state.ts`,在 class 內加兩個方法與前綴常數**

頂部常數區加:

```ts
const HACKMD_PREFIX = "hackmd:";
```

`State` class 內加:

```ts
  async getHackMdLink(messageId: string): Promise<string | null> {
    return this.kv.get(HACKMD_PREFIX + messageId);
  }

  async setHackMdLink(messageId: string, link: string): Promise<void> {
    await this.kv.put(HACKMD_PREFIX + messageId, link);
  }
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd anthropic_update_translator && npx vitest run test/state.test.ts`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
cd anthropic_update_translator
git add src/state.ts test/state.test.ts
git commit -m "feat(state): cache HackMD note link per message for idempotency"
```

---

## Task 8:`index.ts` 編排 + 整合測試

**Files:**
- Modify: `anthropic_update_translator/src/index.ts`
- Test: `anthropic_update_translator/test/index.test.ts`

- [ ] **Step 1: 更新 `index.test.ts` 的 `makeEnv` 並加整合測試**

把 `makeEnv` 改成包含新欄位(預設給 workersai 用的 AI mock 與 hackmd token):

```ts
function makeAi(response: string) {
  return { run: async () => ({ response }) } as unknown as Ai;
}

function makeEnv(kv: MemoryKV, overrides: Partial<Env> = {}): Env {
  return {
    DISCORD_BOT_TOKEN: "BT",
    GEMINI_API_KEY: "GK",
    SOURCE_CHANNEL_ID: "SRC",
    TARGET_CHANNEL_ID: "TGT",
    TRANSLATOR: "gemini",
    GEMINI_MODEL: "gemini-2.5-flash",
    CLAUDE_MODEL: "claude-haiku-4-5-20251001",
    WORKERSAI_MODEL: "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    HACKMD_API_TOKEN: "HMTOKEN",
    AI: makeAi("譯文"),
    KV: asKV(kv),
    ...overrides,
  };
}
```

在 `describe("scheduled handler", ...)` 內新增整合測試(用 `TRANSLATOR: "workersai"`,讓推文與文章翻譯都走 AI mock,fetch 只處理 Discord/article/HackMD):

```ts
  it("推文含 anthropic.com 文章連結:建 HackMD note 並把連結附在 Discord content", async () => {
    const kv = new MemoryKV();
    await kv.put("last_message_id", "100");

    const posts: { url: string; body: string }[] = [];
    let hackmdCalled = 0;
    vi.stubGlobal(
      "fetch",
      routedFetch(
        {
          "/messages?after=100": () =>
            new Response(
              JSON.stringify([
                {
                  id: "101",
                  content: "https://www.anthropic.com/news/new-model",
                  embeds: [
                    {
                      author: { name: "Anthropic (@AnthropicAI)" },
                      description: "We released something. https://www.anthropic.com/news/new-model",
                      url: "https://twitter.com/AnthropicAI/status/101",
                    },
                  ],
                },
              ]),
            ),
          "anthropic.com/news/new-model": () =>
            new Response("<article><h1>New Model</h1><p>Body paragraph.</p></article>", { status: 200 }),
          "api.hackmd.io/v1/notes": () => {
            hackmdCalled += 1;
            return new Response(JSON.stringify({ id: "n1", publishLink: "https://hackmd.io/@x/n1" }), { status: 201 });
          },
          "/channels/TGT/messages": () => new Response("{}", { status: 200 }),
        },
        (url, body) => posts.push({ url, body }),
      ),
    );

    await worker.scheduled(event, makeEnv(kv, { TRANSLATOR: "workersai" }), ctx);

    expect(hackmdCalled).toBe(1);
    expect(await kv.get("hackmd:101")).toBe("https://hackmd.io/@x/n1");
    const post = posts.find((p) => p.url.includes("/channels/TGT/messages"))!;
    expect(JSON.parse(post.body).content).toContain("https://hackmd.io/@x/n1");
    expect(await kv.get("last_message_id")).toBe("101");
  });

  it("文章抓取失敗:推文照常發,content 不含 HackMD 連結", async () => {
    const kv = new MemoryKV();
    await kv.put("last_message_id", "100");

    const posts: { url: string; body: string }[] = [];
    let hackmdCalled = 0;
    vi.stubGlobal(
      "fetch",
      routedFetch(
        {
          "/messages?after=100": () =>
            new Response(
              JSON.stringify([
                {
                  id: "101",
                  content: "https://www.anthropic.com/news/broken",
                  embeds: [
                    {
                      author: { name: "Anthropic (@AnthropicAI)" },
                      description: "text https://www.anthropic.com/news/broken",
                      url: "https://twitter.com/AnthropicAI/status/101",
                    },
                  ],
                },
              ]),
            ),
          "anthropic.com/news/broken": () => new Response("err", { status: 500 }),
          "api.hackmd.io/v1/notes": () => {
            hackmdCalled += 1;
            return new Response("{}", { status: 201 });
          },
          "/channels/TGT/messages": () => new Response("{}", { status: 200 }),
        },
        (url, body) => posts.push({ url, body }),
      ),
    );

    await worker.scheduled(event, makeEnv(kv, { TRANSLATOR: "workersai" }), ctx);

    expect(hackmdCalled).toBe(0);
    const post = posts.find((p) => p.url.includes("/channels/TGT/messages"))!;
    expect(JSON.parse(post.body).content).not.toContain("hackmd.io");
    expect(JSON.parse(post.body).embeds[0].description).toBe("譯文");
    expect(await kv.get("last_message_id")).toBe("101");
  });

  it("KV 已有 hackmd 連結:不重建 note,直接附用既有連結", async () => {
    const kv = new MemoryKV();
    await kv.put("last_message_id", "100");
    await kv.put("hackmd:101", "https://hackmd.io/@x/cached");

    const posts: { url: string; body: string }[] = [];
    let hackmdCalled = 0;
    let articleFetched = false;
    vi.stubGlobal(
      "fetch",
      routedFetch(
        {
          "/messages?after=100": () =>
            new Response(
              JSON.stringify([
                {
                  id: "101",
                  content: "https://www.anthropic.com/news/x",
                  embeds: [
                    {
                      author: { name: "Anthropic (@AnthropicAI)" },
                      description: "text https://www.anthropic.com/news/x",
                      url: "https://twitter.com/AnthropicAI/status/101",
                    },
                  ],
                },
              ]),
            ),
          "anthropic.com/news/x": () => {
            articleFetched = true;
            return new Response("<article><h1>x</h1><p>y</p></article>", { status: 200 });
          },
          "api.hackmd.io/v1/notes": () => {
            hackmdCalled += 1;
            return new Response(JSON.stringify({ publishLink: "new" }), { status: 201 });
          },
          "/channels/TGT/messages": () => new Response("{}", { status: 200 }),
        },
        (url, body) => posts.push({ url, body }),
      ),
    );

    await worker.scheduled(event, makeEnv(kv, { TRANSLATOR: "workersai" }), ctx);

    expect(hackmdCalled).toBe(0);
    expect(articleFetched).toBe(false);
    const post = posts.find((p) => p.url.includes("/channels/TGT/messages"))!;
    expect(JSON.parse(post.body).content).toContain("https://hackmd.io/@x/cached");
  });
```

> 註:既有以 `TRANSLATOR: "gemini"` 為預設的測試訊息都是 `twitter.com` 連結,`extractAnthropicArticle` 會回 `null`,行為不變,仍應綠燈。

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd anthropic_update_translator && npx vitest run test/index.test.ts`
Expected: 新增三個測試 FAIL(index 尚未編排 HackMD 支線)。

- [ ] **Step 3: 改寫 `index.ts`**

```ts
import { DiscordClient, RateLimitError } from "./discord";
import { shouldTranslate } from "./filter";
import { buildHackMdContent, buildOutgoingMessage } from "./format";
import { State } from "./state";
import { createTranslator, type Translator } from "./translator";
import { TranslationError } from "./translator/types";
import { extractAnthropicArticle } from "./article";
import { chunkParagraphs } from "./chunk";
import { HackMdClient } from "./hackmd";
import type { DiscordMessage } from "./filter";
import type { Env } from "./env";

const FETCH_BATCH_LIMIT = 50;
const MAX_RETRIES = 4;
const ARTICLE_CHUNK_CHARS = 3000;

/**
 * 嘗試把推文連到的 anthropic.com 文章翻成繁中、寫進 HackMD,回傳 note 連結。
 * 已建過(KV 有快取)就直接回快取連結;沒有 anthropic.com 連結就回 undefined。
 * 任一步驟失敗會往上丟,由呼叫端 try/catch 吞掉(HackMD 為附加功能)。
 */
async function resolveHackMdLink(
  msg: DiscordMessage,
  translator: Translator,
  hackmd: HackMdClient,
  state: State,
): Promise<string | undefined> {
  const cached = await state.getHackMdLink(msg.id);
  if (cached) return cached;

  const article = await extractAnthropicArticle(msg);
  if (!article) return undefined;

  const batches = chunkParagraphs(article.paragraphs, ARTICLE_CHUNK_CHARS);
  const parts: string[] = [];
  for (const batch of batches) {
    parts.push(await translator.translateArticle(batch));
  }

  const content = buildHackMdContent(article, parts.join("\n\n"));
  const { publishLink } = await hackmd.createNote(content);
  await state.setHackMdLink(msg.id, publishLink);
  return publishLink;
}

export default {
  async scheduled(_event: ScheduledController, env: Env, _ctx: ExecutionContext): Promise<void> {
    const state = new State(env.KV);
    const discord = new DiscordClient(env.DISCORD_BOT_TOKEN);

    const lastId = await state.getLastMessageId();
    if (lastId === null) {
      const latest = await discord.fetchLatest(env.SOURCE_CHANNEL_ID);
      if (latest[0]) {
        await state.setLastMessageId(latest[0].id);
        console.log(`bootstrap: last_message_id = ${latest[0].id}`);
      } else {
        console.log("bootstrap: source channel empty, will retry next cron");
      }
      return;
    }

    let messages;
    try {
      messages = await discord.fetchMessagesAfter(
        env.SOURCE_CHANNEL_ID,
        lastId,
        FETCH_BATCH_LIMIT,
      );
    } catch (err) {
      if (err instanceof RateLimitError) {
        console.error(`Discord rate limited, retry in ${err.retryAfterSec}s`);
        return;
      }
      console.error(`fetchMessagesAfter failed: ${(err as Error).message}`);
      return;
    }

    if (messages.length === 0) return;

    const translator = createTranslator(env);
    const hackmd = new HackMdClient(env.HACKMD_API_TOKEN);

    for (const msg of messages) {
      if (!shouldTranslate(msg)) {
        await state.setLastMessageId(msg.id);
        continue;
      }

      const text = msg.embeds[0]!.description!;
      let translated: string;
      try {
        translated = await translator.translate(text);
      } catch (err) {
        if (err instanceof TranslationError) {
          const retry = await state.incrementRetryCount(msg.id);
          console.error(
            `translate failed for ${msg.id} (retry ${retry}/${MAX_RETRIES}): ${err.message}`,
          );
          if (retry >= MAX_RETRIES) {
            console.error(`giving up on ${msg.id}, skipping`);
            await state.clearRetryCount(msg.id);
            await state.setLastMessageId(msg.id);
            continue;
          }
          return; // 等下次 cron 重試
        }
        throw err;
      }

      // HackMD 支線:附加功能,失敗只 log,不影響推文發送
      let hackmdUrl: string | undefined;
      try {
        hackmdUrl = await resolveHackMdLink(msg, translator, hackmd, state);
      } catch (err) {
        console.error(`HackMD pipeline failed for ${msg.id}: ${(err as Error).message}`);
      }

      const outgoing = buildOutgoingMessage(msg, translated, hackmdUrl);
      try {
        await discord.postMessage(env.TARGET_CHANNEL_ID, outgoing);
      } catch (err) {
        console.error(`postMessage failed for ${msg.id}: ${(err as Error).message}`);
        return; // 不推進,下次重做(可能重發)
      }

      await state.setLastMessageId(msg.id);
      await state.clearRetryCount(msg.id);
    }
  },
};
```

- [ ] **Step 4: 跑全部測試 + 型別檢查**

Run: `cd anthropic_update_translator && npm test && npm run typecheck`
Expected: 全綠、typecheck 通過。

- [ ] **Step 5: Commit**

```bash
cd anthropic_update_translator
git add src/index.ts test/index.test.ts
git commit -m "feat: orchestrate anthropic.com article -> HackMD pipeline"
```

---

## Task 9:設定與部署接線(`wrangler.toml`、workflow、README)

**Files:**
- Modify: `anthropic_update_translator/wrangler.toml`
- Modify: `.github/workflows/deploy-anthropic-translator.yml`
- Modify: `anthropic_update_translator/README.md`
- Modify: `CLAUDE.md`(更新 secrets 清單)

- [ ] **Step 1: 更新 `wrangler.toml`**

```toml
name = "anthropic-update-translator"
main = "src/index.ts"
compatibility_date = "2026-05-01"

[triggers]
crons = ["*/5 * * * *"]

[ai]
binding = "AI"

[vars]
SOURCE_CHANNEL_ID = "1505413807017562172"
TARGET_CHANNEL_ID = "1505415363058339910"
TRANSLATOR = "workersai"
GEMINI_MODEL = "gemini-2.5-flash"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
WORKERSAI_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

[[kv_namespaces]]
binding = "KV"
id = "0b83bbc84d2c4b568f9f9678d3b72094"
```

- [ ] **Step 2: 更新 workflow `deploy-anthropic-translator.yml` 的 Deploy step**

把 `secrets:` 清單與 `env:` 區塊改成(加入 `HACKMD_API_TOKEN`,對應 repo secret `HACK_MD_API_KEY`):

```yaml
      - name: Deploy to Cloudflare
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          workingDirectory: anthropic_update_translator
          secrets: |
            DISCORD_BOT_TOKEN
            GEMINI_API_KEY
            HACKMD_API_TOKEN
        env:
          DISCORD_BOT_TOKEN: ${{ secrets.DISCORD_BOT_TOKEN }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          HACKMD_API_TOKEN: ${{ secrets.HACK_MD_API_KEY }}
```

- [ ] **Step 3: 更新 `README.md`**

把開頭描述補上 HackMD 行為,並調整設定段落。具體編輯:

1. 首段改為說明:除了翻譯推文發 Discord,當推文連到 anthropic.com 文章時,會抓全文翻成繁中、建立 guest 權限的 HackMD 筆記,並把連結附在 Discord 訊息上。
2. 「一次性設定」第 5 點 GitHub Secrets 清單,移除/調整翻譯供應商說明並加入:
   - 預設用 Workers AI(`TRANSLATOR = "workersai"`),AI binding 由 `wrangler.toml` 的 `[ai]` 提供,**不需** API key。
   - `HACK_MD_API_KEY`(HackMD personal access token;workflow 會以此注入 Worker 的 `HACKMD_API_TOKEN`)。
3. 「切換到 Claude 翻譯」段落保留(gemini/claude 仍是可選備援),並加一句:預設為 Workers AI。

> 安全:README 不可出現任何真實 token;只描述變數名稱。

- [ ] **Step 4: 更新根目錄 `CLAUDE.md` 的 Required secrets 清單**

在 `## GitHub Actions` 的 `Required secrets:` 那行末尾加入 `HACK_MD_API_KEY`。

- [ ] **Step 5: 最終驗證(全測試 + 型別)**

Run: `cd anthropic_update_translator && npm test && npm run typecheck`
Expected: 全綠、typecheck 通過。

- [ ] **Step 6: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools
git add anthropic_update_translator/wrangler.toml .github/workflows/deploy-anthropic-translator.yml anthropic_update_translator/README.md CLAUDE.md
git commit -m "chore(anthropic_update_translator): switch to Workers AI + wire HackMD token"
```

---

## 自我檢查對照(spec coverage)

- Workers AI 翻譯 → Task 2(translator)+ Task 9(wrangler `[ai]`/`TRANSLATOR`)。
- 文章抓取(只抓 anthropic.com,含轉址)→ Task 4。
- 段落分批翻譯 → Task 3 + Task 8 編排。
- HackMD note(guest、翻譯全文 + 原文連結)→ Task 5(client)+ Task 6(內文)。
- Discord 附連結(保留主流程)→ Task 6 + Task 8。
- 冪等性(KV 快取)→ Task 7 + Task 8。
- 容錯(HackMD 支線失敗不影響推文)→ Task 8 try/catch。
- 部署 secret(`HACK_MD_API_KEY` → `HACKMD_API_TOKEN`)→ Task 9。
- 測試覆蓋 → 每個 Task 的測試 + Task 8 整合測試。
```
