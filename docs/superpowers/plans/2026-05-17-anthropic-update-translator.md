# Anthropic Update Translator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `anthropic_update_translator/` 建立一個 Cloudflare Worker,每 5 分鐘輪詢 Discord `anthropic-update-raw` 頻道,把 Anthropic / Claude 官方推文 embed 用 Gemini API 翻成繁體中文後,在 `anthropic-updates` 頻道用 Discord Bot 發送同款 embed。Translator 介面可切換,之後改用 Claude API 不需改 code。

**Architecture:** Worker entry (`src/index.ts`) 是 scheduled handler;呼叫順序為 `state` (讀 last_message_id) → `discord` (抓新訊息) → `filter` (留 Twitter embed) → `translator` (Gemini / Claude) → `format` (組 embed) → `discord` (發送) → `state` (推進 ID)。Translator 用 factory pattern 由 `TRANSLATOR` env 切換。所有外部 I/O (Discord, Gemini) 走 `fetch`,測試時用 `vi.stubGlobal("fetch", ...)` mock。KV 在測試時用 in-memory 假物件。

**Tech Stack:** TypeScript, Cloudflare Workers (cron + KV), Vitest, Discord REST API v10, Gemini `generateContent` API, Anthropic Messages API。

---

## File Map

| 路徑 | 職責 |
|---|---|
| `anthropic_update_translator/package.json` | 依賴與 npm scripts |
| `anthropic_update_translator/tsconfig.json` | TS 編譯設定 |
| `anthropic_update_translator/wrangler.toml` | Worker 設定(cron、KV、vars) |
| `anthropic_update_translator/vitest.config.ts` | Vitest 設定 |
| `anthropic_update_translator/.gitignore` | node_modules、.dev.vars 等 |
| `anthropic_update_translator/README.md` | 部署與設定說明 |
| `anthropic_update_translator/src/env.ts` | `Env` 型別宣告 |
| `anthropic_update_translator/src/discord.ts` | Discord REST API client |
| `anthropic_update_translator/src/filter.ts` | 判斷 message 是否要翻譯 |
| `anthropic_update_translator/src/format.ts` | 把翻譯後文字組成發送 payload |
| `anthropic_update_translator/src/state.ts` | KV 讀寫(last_message_id、retry) |
| `anthropic_update_translator/src/translator/types.ts` | `Translator` interface |
| `anthropic_update_translator/src/translator/gemini.ts` | `GeminiTranslator` |
| `anthropic_update_translator/src/translator/claude.ts` | `ClaudeTranslator`(預留) |
| `anthropic_update_translator/src/translator/index.ts` | `createTranslator(env)` 工廠 |
| `anthropic_update_translator/src/index.ts` | Worker scheduled handler |
| `anthropic_update_translator/test/filter.test.ts` | filter 單元測試 |
| `anthropic_update_translator/test/format.test.ts` | format 單元測試 |
| `anthropic_update_translator/test/state.test.ts` | state 單元測試 |
| `anthropic_update_translator/test/discord.test.ts` | discord client 單元測試 |
| `anthropic_update_translator/test/translator/gemini.test.ts` | Gemini translator 測試 |
| `anthropic_update_translator/test/translator/claude.test.ts` | Claude translator 測試 |
| `anthropic_update_translator/test/translator/factory.test.ts` | factory 測試 |
| `anthropic_update_translator/test/index.test.ts` | scheduled handler 整合測試 |
| `anthropic_update_translator/test/helpers.ts` | 測試輔助(MemoryKV、fixtures) |
| `.github/workflows/deploy-anthropic-translator.yml` | CI 部署 |

---

## Task 1: 專案骨架

**Files:**
- Create: `anthropic_update_translator/package.json`
- Create: `anthropic_update_translator/tsconfig.json`
- Create: `anthropic_update_translator/wrangler.toml`
- Create: `anthropic_update_translator/vitest.config.ts`
- Create: `anthropic_update_translator/.gitignore`
- Create: `anthropic_update_translator/src/env.ts`

- [ ] **Step 1: 建立目錄與 package.json**

```bash
mkdir -p anthropic_update_translator/src/translator anthropic_update_translator/test/translator
```

`anthropic_update_translator/package.json`:

```json
{
  "name": "anthropic-update-translator",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc --noEmit",
    "deploy": "wrangler deploy"
  },
  "devDependencies": {
    "@cloudflare/workers-types": "^4.20250101.0",
    "typescript": "^5.6.3",
    "vitest": "^2.1.5",
    "wrangler": "^3.90.0"
  }
}
```

- [ ] **Step 2: 建立 tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "Bundler",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true
  },
  "include": ["src/**/*", "test/**/*", "vitest.config.ts"]
}
```

- [ ] **Step 3: 建立 wrangler.toml**

```toml
name = "anthropic-update-translator"
main = "src/index.ts"
compatibility_date = "2026-05-01"

[triggers]
crons = ["*/5 * * * *"]

[vars]
SOURCE_CHANNEL_ID = "REPLACE_WITH_SOURCE_CHANNEL_ID"
TARGET_CHANNEL_ID = "REPLACE_WITH_TARGET_CHANNEL_ID"
TRANSLATOR = "gemini"
GEMINI_MODEL = "gemini-2.5-flash"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

[[kv_namespaces]]
binding = "KV"
id = "REPLACE_WITH_KV_NAMESPACE_ID"
```

- [ ] **Step 4: 建立 vitest.config.ts**

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: false,
    environment: "node",
    include: ["test/**/*.test.ts"],
  },
});
```

- [ ] **Step 5: 建立 .gitignore**

```
node_modules/
.wrangler/
.dev.vars
dist/
*.log
```

- [ ] **Step 6: 建立 src/env.ts**

```ts
export interface Env {
  DISCORD_BOT_TOKEN: string;
  GEMINI_API_KEY: string;
  CLAUDE_API_KEY?: string;

  SOURCE_CHANNEL_ID: string;
  TARGET_CHANNEL_ID: string;
  TRANSLATOR: "gemini" | "claude";
  GEMINI_MODEL: string;
  CLAUDE_MODEL: string;

  KV: KVNamespace;
}
```

- [ ] **Step 7: 安裝依賴**

```bash
cd anthropic_update_translator
npm install
```

Expected: 安裝成功,產生 `package-lock.json` 與 `node_modules/`。

- [ ] **Step 8: 確認 typecheck pass**

```bash
cd anthropic_update_translator
npm run typecheck
```

Expected: 無 output(成功)。

- [ ] **Step 9: Commit**

```bash
git add anthropic_update_translator/package.json anthropic_update_translator/tsconfig.json anthropic_update_translator/wrangler.toml anthropic_update_translator/vitest.config.ts anthropic_update_translator/.gitignore anthropic_update_translator/src/env.ts anthropic_update_translator/package-lock.json
git commit -m "$(cat <<'EOF'
feat(anthropic-update-translator): scaffold project

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: filter.ts — 訊息過濾邏輯

**Files:**
- Create: `anthropic_update_translator/src/filter.ts`
- Create: `anthropic_update_translator/test/filter.test.ts`

- [ ] **Step 1: 寫失敗測試**

`test/filter.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { shouldTranslate, type DiscordMessage } from "../src/filter";

function msg(overrides: Partial<DiscordMessage>): DiscordMessage {
  return {
    id: "1",
    content: "",
    embeds: [],
    ...overrides,
  };
}

describe("shouldTranslate", () => {
  it("回傳 true 當 embed author 含 @AnthropicAI 且有 description", () => {
    const m = msg({
      embeds: [
        {
          author: { name: "Anthropic (@AnthropicAI)" },
          description: "We're partnering with Gates Foundation",
        },
      ],
    });
    expect(shouldTranslate(m)).toBe(true);
  });

  it("回傳 true 當 embed author 含 @claudeai", () => {
    const m = msg({
      embeds: [
        {
          author: { name: "Claude (@claudeai)" },
          description: "What are you building at home?",
        },
      ],
    });
    expect(shouldTranslate(m)).toBe(true);
  });

  it("回傳 false 當沒有 embed", () => {
    const m = msg({ content: "just text" });
    expect(shouldTranslate(m)).toBe(false);
  });

  it("回傳 false 當 embed author 不符", () => {
    const m = msg({
      embeds: [
        {
          author: { name: "SomeOtherAccount (@other)" },
          description: "irrelevant",
        },
      ],
    });
    expect(shouldTranslate(m)).toBe(false);
  });

  it("回傳 false 當 embed description 為空", () => {
    const m = msg({
      embeds: [{ author: { name: "Anthropic (@AnthropicAI)" }, description: "" }],
    });
    expect(shouldTranslate(m)).toBe(false);
  });

  it("回傳 false 當 embed 沒有 author", () => {
    const m = msg({
      embeds: [{ description: "no author" }],
    });
    expect(shouldTranslate(m)).toBe(false);
  });
});
```

- [ ] **Step 2: 跑測試驗證失敗**

```bash
cd anthropic_update_translator
npm test -- filter
```

Expected: FAIL,因為 `src/filter.ts` 還不存在。

- [ ] **Step 3: 實作 filter.ts**

`src/filter.ts`:

```ts
export interface DiscordEmbedAuthor {
  name?: string;
  url?: string;
  icon_url?: string;
}

export interface DiscordEmbed {
  title?: string;
  description?: string;
  url?: string;
  timestamp?: string;
  color?: number;
  author?: DiscordEmbedAuthor;
  thumbnail?: { url: string };
  footer?: { text: string; icon_url?: string };
}

export interface DiscordMessage {
  id: string;
  content: string;
  embeds: DiscordEmbed[];
}

const ALLOWED_AUTHOR_HANDLES = ["@AnthropicAI", "@claudeai"];

export function shouldTranslate(msg: DiscordMessage): boolean {
  const embed = msg.embeds[0];
  if (!embed) return false;
  if (!embed.description || embed.description.trim() === "") return false;
  const authorName = embed.author?.name ?? "";
  return ALLOWED_AUTHOR_HANDLES.some((handle) => authorName.includes(handle));
}
```

- [ ] **Step 4: 跑測試驗證 pass**

```bash
npm test -- filter
```

Expected: 6 個測試全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add anthropic_update_translator/src/filter.ts anthropic_update_translator/test/filter.test.ts
git commit -m "$(cat <<'EOF'
feat(anthropic-update-translator): add filter for Anthropic/Claude tweet embeds

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: format.ts — 組裝發送 payload

**Files:**
- Create: `anthropic_update_translator/src/format.ts`
- Create: `anthropic_update_translator/test/format.test.ts`

- [ ] **Step 1: 寫失敗測試**

`test/format.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { buildOutgoingMessage } from "../src/format";
import type { DiscordMessage } from "../src/filter";

const ANTHROPIC_ORANGE = 0xd97757;

describe("buildOutgoingMessage", () => {
  it("組出含 content URL 與翻譯 embed 的 payload", () => {
    const source: DiscordMessage = {
      id: "100",
      content: "@News - ANTHROP\\C https://twitter.com/AnthropicAI/status/123",
      embeds: [
        {
          author: {
            name: "Anthropic (@AnthropicAI)",
            url: "https://twitter.com/AnthropicAI",
            icon_url: "https://example.com/icon.png",
          },
          description: "We're partnering with Gates Foundation.",
          url: "https://twitter.com/AnthropicAI/status/123",
          timestamp: "2026-05-14T15:08:00.000Z",
          thumbnail: { url: "https://example.com/thumb.png" },
        },
      ],
    };

    const out = buildOutgoingMessage(source, "我們與蓋茲基金會合作。");

    expect(out.content).toBe("https://twitter.com/AnthropicAI/status/123");
    expect(out.embeds).toHaveLength(1);
    const e = out.embeds[0]!;
    expect(e.description).toBe("我們與蓋茲基金會合作。");
    expect(e.url).toBe("https://twitter.com/AnthropicAI/status/123");
    expect(e.author?.name).toBe("Anthropic (@AnthropicAI)");
    expect(e.author?.icon_url).toBe("https://example.com/icon.png");
    expect(e.thumbnail?.url).toBe("https://example.com/thumb.png");
    expect(e.footer?.text).toBe("X");
    expect(e.timestamp).toBe("2026-05-14T15:08:00.000Z");
    expect(e.color).toBe(ANTHROPIC_ORANGE);
  });

  it("當 embed.url 缺失時,從 message.content 擷取第一個 twitter/x URL", () => {
    const source: DiscordMessage = {
      id: "101",
      content: "mention https://x.com/AnthropicAI/status/456 trailing",
      embeds: [
        {
          author: { name: "Anthropic (@AnthropicAI)" },
          description: "hello",
        },
      ],
    };

    const out = buildOutgoingMessage(source, "你好");
    expect(out.content).toBe("https://x.com/AnthropicAI/status/456");
  });

  it("當 content 與 embed.url 都沒有 URL 時,content 為空字串", () => {
    const source: DiscordMessage = {
      id: "102",
      content: "no url here",
      embeds: [
        {
          author: { name: "Anthropic (@AnthropicAI)" },
          description: "hello",
        },
      ],
    };

    const out = buildOutgoingMessage(source, "你好");
    expect(out.content).toBe("");
  });
});
```

- [ ] **Step 2: 跑測試驗證失敗**

```bash
npm test -- format
```

Expected: FAIL,模組不存在。

- [ ] **Step 3: 實作 format.ts**

`src/format.ts`:

```ts
import type { DiscordEmbed, DiscordMessage } from "./filter";

const ANTHROPIC_ORANGE = 0xd97757;
const TWITTER_URL_REGEX = /https?:\/\/(?:twitter\.com|x\.com)\/[^\s]+/i;

export interface OutgoingMessage {
  content: string;
  embeds: DiscordEmbed[];
}

export function buildOutgoingMessage(
  source: DiscordMessage,
  translated: string,
): OutgoingMessage {
  const sourceEmbed = source.embeds[0];
  if (!sourceEmbed) {
    throw new Error("buildOutgoingMessage: source has no embed");
  }

  const tweetUrl =
    sourceEmbed.url ?? source.content.match(TWITTER_URL_REGEX)?.[0] ?? "";

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
    content: tweetUrl,
    embeds: [embed],
  };
}
```

- [ ] **Step 4: 跑測試驗證 pass**

```bash
npm test -- format
```

Expected: 3 個測試全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add anthropic_update_translator/src/format.ts anthropic_update_translator/test/format.test.ts
git commit -m "$(cat <<'EOF'
feat(anthropic-update-translator): add outgoing message formatter

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: test/helpers.ts — 共用測試輔助

**Files:**
- Create: `anthropic_update_translator/test/helpers.ts`

- [ ] **Step 1: 建立 MemoryKV 與 fixtures**

`test/helpers.ts`:

```ts
export class MemoryKV {
  store = new Map<string, string>();

  async get(key: string): Promise<string | null> {
    return this.store.get(key) ?? null;
  }

  async put(key: string, value: string): Promise<void> {
    this.store.set(key, value);
  }

  async delete(key: string): Promise<void> {
    this.store.delete(key);
  }

  // 其他 KVNamespace 方法不用,留 stub
  list(): never {
    throw new Error("not implemented");
  }
  getWithMetadata(): never {
    throw new Error("not implemented");
  }
}

export function asKV(kv: MemoryKV): KVNamespace {
  return kv as unknown as KVNamespace;
}
```

- [ ] **Step 2: 確認 typecheck pass**

```bash
cd anthropic_update_translator
npm run typecheck
```

Expected: 無錯誤。

- [ ] **Step 3: Commit**

```bash
git add anthropic_update_translator/test/helpers.ts
git commit -m "$(cat <<'EOF'
test(anthropic-update-translator): add MemoryKV test helper

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: state.ts — KV 狀態存取

**Files:**
- Create: `anthropic_update_translator/src/state.ts`
- Create: `anthropic_update_translator/test/state.test.ts`

- [ ] **Step 1: 寫失敗測試**

`test/state.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { State } from "../src/state";
import { MemoryKV, asKV } from "./helpers";

describe("State", () => {
  it("getLastMessageId 預設回 null", async () => {
    const state = new State(asKV(new MemoryKV()));
    expect(await state.getLastMessageId()).toBeNull();
  });

  it("setLastMessageId 後可讀回", async () => {
    const state = new State(asKV(new MemoryKV()));
    await state.setLastMessageId("123");
    expect(await state.getLastMessageId()).toBe("123");
  });

  it("getRetryCount 預設回 0", async () => {
    const state = new State(asKV(new MemoryKV()));
    expect(await state.getRetryCount("abc")).toBe(0);
  });

  it("incrementRetryCount 回傳新的次數並寫入", async () => {
    const state = new State(asKV(new MemoryKV()));
    expect(await state.incrementRetryCount("abc")).toBe(1);
    expect(await state.incrementRetryCount("abc")).toBe(2);
    expect(await state.getRetryCount("abc")).toBe(2);
  });

  it("clearRetryCount 把 key 移除", async () => {
    const state = new State(asKV(new MemoryKV()));
    await state.incrementRetryCount("abc");
    await state.clearRetryCount("abc");
    expect(await state.getRetryCount("abc")).toBe(0);
  });
});
```

- [ ] **Step 2: 跑測試驗證失敗**

```bash
npm test -- state
```

Expected: FAIL。

- [ ] **Step 3: 實作 state.ts**

`src/state.ts`:

```ts
const LAST_MESSAGE_KEY = "last_message_id";
const RETRY_PREFIX = "retry:";

export class State {
  constructor(private kv: KVNamespace) {}

  async getLastMessageId(): Promise<string | null> {
    return this.kv.get(LAST_MESSAGE_KEY);
  }

  async setLastMessageId(id: string): Promise<void> {
    await this.kv.put(LAST_MESSAGE_KEY, id);
  }

  async getRetryCount(messageId: string): Promise<number> {
    const raw = await this.kv.get(RETRY_PREFIX + messageId);
    if (raw === null) return 0;
    const n = Number.parseInt(raw, 10);
    return Number.isFinite(n) ? n : 0;
  }

  async incrementRetryCount(messageId: string): Promise<number> {
    const next = (await this.getRetryCount(messageId)) + 1;
    await this.kv.put(RETRY_PREFIX + messageId, String(next));
    return next;
  }

  async clearRetryCount(messageId: string): Promise<void> {
    await this.kv.delete(RETRY_PREFIX + messageId);
  }
}
```

- [ ] **Step 4: 跑測試驗證 pass**

```bash
npm test -- state
```

Expected: 5 個測試 PASS。

- [ ] **Step 5: Commit**

```bash
git add anthropic_update_translator/src/state.ts anthropic_update_translator/test/state.test.ts
git commit -m "$(cat <<'EOF'
feat(anthropic-update-translator): add KV state wrapper

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: discord.ts — Discord REST client

**Files:**
- Create: `anthropic_update_translator/src/discord.ts`
- Create: `anthropic_update_translator/test/discord.test.ts`

- [ ] **Step 1: 寫失敗測試**

`test/discord.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { DiscordClient } from "../src/discord";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch(impl: (url: string, init: RequestInit) => Response | Promise<Response>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => Promise.resolve(impl(url, init))),
  );
}

describe("DiscordClient.fetchMessagesAfter", () => {
  it("帶上 after 與 limit 參數,並回傳依 snowflake 排序的訊息", async () => {
    stubFetch((url) => {
      expect(url).toBe(
        "https://discord.com/api/v10/channels/SRC/messages?after=100&limit=50",
      );
      return new Response(
        JSON.stringify([
          { id: "103", content: "c", embeds: [] },
          { id: "101", content: "a", embeds: [] },
          { id: "102", content: "b", embeds: [] },
        ]),
        { status: 200 },
      );
    });

    const client = new DiscordClient("TOKEN");
    const messages = await client.fetchMessagesAfter("SRC", "100", 50);
    expect(messages.map((m) => m.id)).toEqual(["101", "102", "103"]);
  });

  it("不帶 after 時改用 limit=1 取最新一則", async () => {
    stubFetch((url) => {
      expect(url).toBe(
        "https://discord.com/api/v10/channels/SRC/messages?limit=1",
      );
      return new Response(JSON.stringify([{ id: "999", content: "", embeds: [] }]), {
        status: 200,
      });
    });

    const client = new DiscordClient("TOKEN");
    const messages = await client.fetchLatest("SRC");
    expect(messages[0]!.id).toBe("999");
  });

  it("HTTP 429 拋 RateLimitError 並帶 retryAfter", async () => {
    stubFetch(
      () =>
        new Response("rate limit", {
          status: 429,
          headers: { "Retry-After": "3" },
        }),
    );
    const client = new DiscordClient("TOKEN");
    await expect(client.fetchMessagesAfter("SRC", "100", 50)).rejects.toMatchObject({
      name: "RateLimitError",
      retryAfterSec: 3,
    });
  });
});

describe("DiscordClient.postMessage", () => {
  it("POST 到正確 endpoint,帶 Bot token 與 JSON body", async () => {
    let capturedInit: RequestInit | undefined;
    stubFetch((url, init) => {
      expect(url).toBe("https://discord.com/api/v10/channels/TGT/messages");
      capturedInit = init;
      return new Response("{}", { status: 200 });
    });

    const client = new DiscordClient("TOKEN");
    await client.postMessage("TGT", { content: "hi", embeds: [] });

    expect(capturedInit?.method).toBe("POST");
    expect((capturedInit?.headers as Record<string, string>).Authorization).toBe(
      "Bot TOKEN",
    );
    expect((capturedInit?.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    );
    expect(capturedInit?.body).toBe(JSON.stringify({ content: "hi", embeds: [] }));
  });

  it("POST 失敗時 throw", async () => {
    stubFetch(() => new Response("forbidden", { status: 403 }));
    const client = new DiscordClient("TOKEN");
    await expect(
      client.postMessage("TGT", { content: "", embeds: [] }),
    ).rejects.toThrow(/403/);
  });
});
```

- [ ] **Step 2: 跑測試驗證失敗**

```bash
npm test -- discord
```

Expected: FAIL。

- [ ] **Step 3: 實作 discord.ts**

`src/discord.ts`:

```ts
import type { DiscordMessage } from "./filter";
import type { OutgoingMessage } from "./format";

const API_BASE = "https://discord.com/api/v10";

export class RateLimitError extends Error {
  name = "RateLimitError";
  constructor(public retryAfterSec: number) {
    super(`Discord rate limited, retry after ${retryAfterSec}s`);
  }
}

export class DiscordClient {
  constructor(private botToken: string) {}

  private headers(): Record<string, string> {
    return {
      Authorization: `Bot ${this.botToken}`,
      "Content-Type": "application/json",
    };
  }

  async fetchMessagesAfter(
    channelId: string,
    afterMessageId: string,
    limit: number,
  ): Promise<DiscordMessage[]> {
    const url = `${API_BASE}/channels/${channelId}/messages?after=${afterMessageId}&limit=${limit}`;
    const res = await fetch(url, { headers: this.headers() });
    if (res.status === 429) {
      const retryAfter = Number.parseInt(res.headers.get("Retry-After") ?? "5", 10);
      throw new RateLimitError(retryAfter);
    }
    if (!res.ok) {
      throw new Error(`Discord fetchMessagesAfter failed: ${res.status} ${await res.text()}`);
    }
    const data = (await res.json()) as DiscordMessage[];
    return sortBySnowflake(data);
  }

  async fetchLatest(channelId: string): Promise<DiscordMessage[]> {
    const url = `${API_BASE}/channels/${channelId}/messages?limit=1`;
    const res = await fetch(url, { headers: this.headers() });
    if (!res.ok) {
      throw new Error(`Discord fetchLatest failed: ${res.status} ${await res.text()}`);
    }
    return (await res.json()) as DiscordMessage[];
  }

  async postMessage(channelId: string, payload: OutgoingMessage): Promise<void> {
    const url = `${API_BASE}/channels/${channelId}/messages`;
    const res = await fetch(url, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Discord postMessage failed: ${res.status} ${await res.text()}`);
    }
  }
}

function sortBySnowflake(msgs: DiscordMessage[]): DiscordMessage[] {
  return [...msgs].sort((a, b) => {
    const ai = BigInt(a.id);
    const bi = BigInt(b.id);
    if (ai < bi) return -1;
    if (ai > bi) return 1;
    return 0;
  });
}
```

- [ ] **Step 4: 跑測試驗證 pass**

```bash
npm test -- discord
```

Expected: 5 個測試 PASS。

- [ ] **Step 5: Commit**

```bash
git add anthropic_update_translator/src/discord.ts anthropic_update_translator/test/discord.test.ts
git commit -m "$(cat <<'EOF'
feat(anthropic-update-translator): add Discord REST client

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: translator/types.ts — 介面與共用 prompt

**Files:**
- Create: `anthropic_update_translator/src/translator/types.ts`

- [ ] **Step 1: 建立介面與 prompt 建構函式**

`src/translator/types.ts`:

```ts
export interface Translator {
  translate(text: string): Promise<string>;
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
```

- [ ] **Step 2: 確認 typecheck pass**

```bash
npm run typecheck
```

Expected: 無錯誤。

- [ ] **Step 3: Commit**

```bash
git add anthropic_update_translator/src/translator/types.ts
git commit -m "$(cat <<'EOF'
feat(anthropic-update-translator): add Translator interface and shared prompt

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: translator/gemini.ts

**Files:**
- Create: `anthropic_update_translator/src/translator/gemini.ts`
- Create: `anthropic_update_translator/test/translator/gemini.test.ts`

- [ ] **Step 1: 寫失敗測試**

`test/translator/gemini.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { GeminiTranslator } from "../../src/translator/gemini";
import { TranslationError } from "../../src/translator/types";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubOnce(response: Response) {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response)));
}

describe("GeminiTranslator", () => {
  it("POST 到正確 endpoint 並回傳翻譯結果", async () => {
    let capturedUrl = "";
    let capturedBody = "";
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit) => {
        capturedUrl = url;
        capturedBody = init.body as string;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              candidates: [
                { content: { parts: [{ text: "翻譯結果" }] } },
              ],
            }),
            { status: 200 },
          ),
        );
      }),
    );

    const t = new GeminiTranslator("KEY", "gemini-2.5-flash");
    const out = await t.translate("Hello");

    expect(out).toBe("翻譯結果");
    expect(capturedUrl).toBe(
      "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=KEY",
    );
    expect(JSON.parse(capturedBody).contents[0].parts[0].text).toContain("Hello");
  });

  it("HTTP 非 2xx 時拋 TranslationError", async () => {
    stubOnce(new Response("err", { status: 500 }));
    const t = new GeminiTranslator("KEY", "gemini-2.5-flash");
    await expect(t.translate("x")).rejects.toBeInstanceOf(TranslationError);
  });

  it("回應結構異常時拋 TranslationError", async () => {
    stubOnce(new Response(JSON.stringify({ foo: "bar" }), { status: 200 }));
    const t = new GeminiTranslator("KEY", "gemini-2.5-flash");
    await expect(t.translate("x")).rejects.toBeInstanceOf(TranslationError);
  });

  it("回應為空字串時拋 TranslationError", async () => {
    stubOnce(
      new Response(
        JSON.stringify({ candidates: [{ content: { parts: [{ text: "  " }] } }] }),
        { status: 200 },
      ),
    );
    const t = new GeminiTranslator("KEY", "gemini-2.5-flash");
    await expect(t.translate("x")).rejects.toBeInstanceOf(TranslationError);
  });

  it("回應過長時拋 TranslationError", async () => {
    const tooLong = "a".repeat(200);
    stubOnce(
      new Response(
        JSON.stringify({
          candidates: [{ content: { parts: [{ text: tooLong }] } }],
        }),
        { status: 200 },
      ),
    );
    const t = new GeminiTranslator("KEY", "gemini-2.5-flash");
    await expect(t.translate("ab")).rejects.toBeInstanceOf(TranslationError);
  });
});
```

- [ ] **Step 2: 跑測試驗證失敗**

```bash
npm test -- gemini
```

Expected: FAIL。

- [ ] **Step 3: 實作 gemini.ts**

`src/translator/gemini.ts`:

```ts
import {
  buildPrompt,
  TranslationError,
  validateTranslation,
  type Translator,
} from "./types";

const TIMEOUT_MS = 10_000;

interface GeminiResponse {
  candidates?: Array<{
    content?: { parts?: Array<{ text?: string }> };
  }>;
}

export class GeminiTranslator implements Translator {
  constructor(private apiKey: string, private model: string) {}

  async translate(text: string): Promise<string> {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${this.model}:generateContent?key=${this.apiKey}`;
    const body = JSON.stringify({
      contents: [{ parts: [{ text: buildPrompt(text) }] }],
    });

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

    validateTranslation(text, translated);
    return translated.trim();
  }
}
```

- [ ] **Step 4: 跑測試驗證 pass**

```bash
npm test -- gemini
```

Expected: 5 個測試 PASS。

- [ ] **Step 5: Commit**

```bash
git add anthropic_update_translator/src/translator/gemini.ts anthropic_update_translator/test/translator/gemini.test.ts
git commit -m "$(cat <<'EOF'
feat(anthropic-update-translator): add GeminiTranslator

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: translator/claude.ts

**Files:**
- Create: `anthropic_update_translator/src/translator/claude.ts`
- Create: `anthropic_update_translator/test/translator/claude.test.ts`

- [ ] **Step 1: 寫失敗測試**

`test/translator/claude.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ClaudeTranslator } from "../../src/translator/claude";
import { TranslationError } from "../../src/translator/types";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ClaudeTranslator", () => {
  it("POST 到 Anthropic API 並帶正確 headers", async () => {
    let capturedUrl = "";
    let capturedInit: RequestInit | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit) => {
        capturedUrl = url;
        capturedInit = init;
        return Promise.resolve(
          new Response(
            JSON.stringify({ content: [{ type: "text", text: "翻譯結果" }] }),
            { status: 200 },
          ),
        );
      }),
    );

    const t = new ClaudeTranslator("CKEY", "claude-haiku-4-5-20251001");
    const out = await t.translate("Hello world");

    expect(out).toBe("翻譯結果");
    expect(capturedUrl).toBe("https://api.anthropic.com/v1/messages");
    const headers = capturedInit?.headers as Record<string, string>;
    expect(headers["x-api-key"]).toBe("CKEY");
    expect(headers["anthropic-version"]).toBe("2023-06-01");
    expect(headers["content-type"]).toBe("application/json");
    const body = JSON.parse(capturedInit?.body as string);
    expect(body.model).toBe("claude-haiku-4-5-20251001");
    expect(body.messages[0].content).toContain("Hello world");
  });

  it("HTTP 失敗時拋 TranslationError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("err", { status: 500 }))),
    );
    const t = new ClaudeTranslator("CKEY", "claude-haiku-4-5-20251001");
    await expect(t.translate("x")).rejects.toBeInstanceOf(TranslationError);
  });

  it("回應缺 text 時拋 TranslationError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(new Response(JSON.stringify({ content: [] }), { status: 200 })),
      ),
    );
    const t = new ClaudeTranslator("CKEY", "claude-haiku-4-5-20251001");
    await expect(t.translate("x")).rejects.toBeInstanceOf(TranslationError);
  });
});
```

- [ ] **Step 2: 跑測試驗證失敗**

```bash
npm test -- claude
```

Expected: FAIL。

- [ ] **Step 3: 實作 claude.ts**

`src/translator/claude.ts`:

```ts
import {
  buildPrompt,
  TranslationError,
  validateTranslation,
  type Translator,
} from "./types";

const TIMEOUT_MS = 10_000;
const MAX_TOKENS = 2048;

interface ClaudeResponse {
  content?: Array<{ type?: string; text?: string }>;
}

export class ClaudeTranslator implements Translator {
  constructor(private apiKey: string, private model: string) {}

  async translate(text: string): Promise<string> {
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
          messages: [{ role: "user", content: buildPrompt(text) }],
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

    validateTranslation(text, translated);
    return translated.trim();
  }
}
```

- [ ] **Step 4: 跑測試驗證 pass**

```bash
npm test -- claude
```

Expected: 3 個測試 PASS。

- [ ] **Step 5: Commit**

```bash
git add anthropic_update_translator/src/translator/claude.ts anthropic_update_translator/test/translator/claude.test.ts
git commit -m "$(cat <<'EOF'
feat(anthropic-update-translator): add ClaudeTranslator

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: translator/index.ts — Factory

**Files:**
- Create: `anthropic_update_translator/src/translator/index.ts`
- Create: `anthropic_update_translator/test/translator/factory.test.ts`

- [ ] **Step 1: 寫失敗測試**

`test/translator/factory.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { createTranslator } from "../../src/translator";
import { GeminiTranslator } from "../../src/translator/gemini";
import { ClaudeTranslator } from "../../src/translator/claude";
import type { Env } from "../../src/env";

function env(overrides: Partial<Env>): Env {
  return {
    DISCORD_BOT_TOKEN: "DT",
    GEMINI_API_KEY: "GK",
    SOURCE_CHANNEL_ID: "S",
    TARGET_CHANNEL_ID: "T",
    TRANSLATOR: "gemini",
    GEMINI_MODEL: "gemini-2.5-flash",
    CLAUDE_MODEL: "claude-haiku-4-5-20251001",
    KV: {} as KVNamespace,
    ...overrides,
  };
}

describe("createTranslator", () => {
  it("回傳 GeminiTranslator 當 TRANSLATOR=gemini", () => {
    const t = createTranslator(env({ TRANSLATOR: "gemini" }));
    expect(t).toBeInstanceOf(GeminiTranslator);
  });

  it("回傳 ClaudeTranslator 當 TRANSLATOR=claude", () => {
    const t = createTranslator(env({ TRANSLATOR: "claude", CLAUDE_API_KEY: "CK" }));
    expect(t).toBeInstanceOf(ClaudeTranslator);
  });

  it("TRANSLATOR=claude 但缺 CLAUDE_API_KEY 時 throw", () => {
    expect(() => createTranslator(env({ TRANSLATOR: "claude" }))).toThrow(/CLAUDE_API_KEY/);
  });

  it("未知 TRANSLATOR 值 throw", () => {
    expect(() =>
      createTranslator(env({ TRANSLATOR: "foo" as Env["TRANSLATOR"] })),
    ).toThrow(/Unknown TRANSLATOR/);
  });
});
```

- [ ] **Step 2: 跑測試驗證失敗**

```bash
npm test -- factory
```

Expected: FAIL。

- [ ] **Step 3: 實作 translator/index.ts**

`src/translator/index.ts`:

```ts
import type { Env } from "../env";
import { GeminiTranslator } from "./gemini";
import { ClaudeTranslator } from "./claude";
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
    default:
      throw new Error(`Unknown TRANSLATOR: ${env.TRANSLATOR}`);
  }
}
```

- [ ] **Step 4: 跑測試驗證 pass**

```bash
npm test -- factory
```

Expected: 4 個測試 PASS。

- [ ] **Step 5: Commit**

```bash
git add anthropic_update_translator/src/translator/index.ts anthropic_update_translator/test/translator/factory.test.ts
git commit -m "$(cat <<'EOF'
feat(anthropic-update-translator): add translator factory

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: src/index.ts — Scheduled handler

**Files:**
- Create: `anthropic_update_translator/src/index.ts`
- Create: `anthropic_update_translator/test/index.test.ts`

- [ ] **Step 1: 寫失敗測試**

`test/index.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import type { Env } from "../src/env";
import { MemoryKV, asKV } from "./helpers";

afterEach(() => {
  vi.unstubAllGlobals();
});

function makeEnv(kv: MemoryKV, overrides: Partial<Env> = {}): Env {
  return {
    DISCORD_BOT_TOKEN: "BT",
    GEMINI_API_KEY: "GK",
    SOURCE_CHANNEL_ID: "SRC",
    TARGET_CHANNEL_ID: "TGT",
    TRANSLATOR: "gemini",
    GEMINI_MODEL: "gemini-2.5-flash",
    CLAUDE_MODEL: "claude-haiku-4-5-20251001",
    KV: asKV(kv),
    ...overrides,
  };
}

// 控制不同 URL 的 fetch 回應
function routedFetch(
  routes: Record<string, () => Response>,
  onPost?: (url: string, body: string) => void,
): ReturnType<typeof vi.fn> {
  return vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "POST" && onPost) onPost(url, init.body as string);
    for (const [pattern, handler] of Object.entries(routes)) {
      if (url.includes(pattern)) return handler();
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });
}

const ctx = {
  waitUntil: () => undefined,
  passThroughOnException: () => undefined,
} as unknown as ExecutionContext;
const event = { cron: "*/5 * * * *", scheduledTime: 0, type: "scheduled" } as ScheduledController;

describe("scheduled handler", () => {
  it("首次執行(KV 空):只記錄當下最新 id,不翻譯也不發送", async () => {
    const kv = new MemoryKV();
    const posts: string[] = [];
    vi.stubGlobal(
      "fetch",
      routedFetch({
        "/messages?limit=1": () =>
          new Response(JSON.stringify([{ id: "999", content: "", embeds: [] }])),
      }, (url) => posts.push(url)),
    );

    await worker.scheduled(event, makeEnv(kv), ctx);

    expect(await kv.get("last_message_id")).toBe("999");
    expect(posts).toHaveLength(0);
  });

  it("有新訊息且符合條件:翻譯後 POST 並推進 last_message_id", async () => {
    const kv = new MemoryKV();
    await kv.put("last_message_id", "100");

    const posts: { url: string; body: string }[] = [];
    vi.stubGlobal(
      "fetch",
      routedFetch(
        {
          "/messages?after=100": () =>
            new Response(
              JSON.stringify([
                {
                  id: "101",
                  content: "https://twitter.com/AnthropicAI/status/101",
                  embeds: [
                    {
                      author: { name: "Anthropic (@AnthropicAI)" },
                      description: "Hello world",
                      url: "https://twitter.com/AnthropicAI/status/101",
                    },
                  ],
                },
              ]),
            ),
          "generativelanguage.googleapis.com": () =>
            new Response(
              JSON.stringify({
                candidates: [{ content: { parts: [{ text: "你好世界" }] } }],
              }),
            ),
          "/channels/TGT/messages": () => new Response("{}", { status: 200 }),
        },
        (url, body) => posts.push({ url, body }),
      ),
    );

    await worker.scheduled(event, makeEnv(kv), ctx);

    expect(await kv.get("last_message_id")).toBe("101");
    const discordPost = posts.find((p) => p.url.includes("/channels/TGT/messages"));
    expect(discordPost).toBeDefined();
    expect(JSON.parse(discordPost!.body).embeds[0].description).toBe("你好世界");
  });

  it("不符合 filter 的訊息只推進 ID,不翻譯也不發送", async () => {
    const kv = new MemoryKV();
    await kv.put("last_message_id", "100");

    let geminiCalled = false;
    let postCalled = false;
    vi.stubGlobal(
      "fetch",
      routedFetch(
        {
          "/messages?after=100": () =>
            new Response(
              JSON.stringify([
                { id: "101", content: "no embed text only", embeds: [] },
              ]),
            ),
          "generativelanguage.googleapis.com": () => {
            geminiCalled = true;
            return new Response("{}");
          },
          "/channels/TGT/messages": () => {
            postCalled = true;
            return new Response("{}");
          },
        },
      ),
    );

    await worker.scheduled(event, makeEnv(kv), ctx);

    expect(geminiCalled).toBe(false);
    expect(postCalled).toBe(false);
    expect(await kv.get("last_message_id")).toBe("101");
  });

  it("翻譯失敗時遞增 retry,不推進 ID", async () => {
    const kv = new MemoryKV();
    await kv.put("last_message_id", "100");

    vi.stubGlobal(
      "fetch",
      routedFetch({
        "/messages?after=100": () =>
          new Response(
            JSON.stringify([
              {
                id: "101",
                content: "",
                embeds: [
                  {
                    author: { name: "Anthropic (@AnthropicAI)" },
                    description: "Hello",
                  },
                ],
              },
            ]),
          ),
        "generativelanguage.googleapis.com": () =>
          new Response("err", { status: 500 }),
      }),
    );

    await worker.scheduled(event, makeEnv(kv), ctx);

    expect(await kv.get("last_message_id")).toBe("100"); // 沒推進
    expect(await kv.get("retry:101")).toBe("1");
  });

  it("retry 達到 4 次後跳過該訊息(推進 ID + 清除 retry)", async () => {
    const kv = new MemoryKV();
    await kv.put("last_message_id", "100");
    await kv.put("retry:101", "3"); // 下一次會變 4

    vi.stubGlobal(
      "fetch",
      routedFetch({
        "/messages?after=100": () =>
          new Response(
            JSON.stringify([
              {
                id: "101",
                content: "",
                embeds: [
                  {
                    author: { name: "Anthropic (@AnthropicAI)" },
                    description: "Hello",
                  },
                ],
              },
            ]),
          ),
        "generativelanguage.googleapis.com": () =>
          new Response("err", { status: 500 }),
      }),
    );

    await worker.scheduled(event, makeEnv(kv), ctx);

    expect(await kv.get("last_message_id")).toBe("101");
    expect(await kv.get("retry:101")).toBeNull();
  });
});
```

- [ ] **Step 2: 跑測試驗證失敗**

```bash
npm test -- index
```

Expected: FAIL。

- [ ] **Step 3: 實作 src/index.ts**

`src/index.ts`:

```ts
import { DiscordClient, RateLimitError } from "./discord";
import { shouldTranslate } from "./filter";
import { buildOutgoingMessage } from "./format";
import { State } from "./state";
import { createTranslator } from "./translator";
import { TranslationError } from "./translator/types";
import type { Env } from "./env";

const FETCH_BATCH_LIMIT = 50;
const MAX_RETRIES = 4;

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

      try {
        await discord.postMessage(
          env.TARGET_CHANNEL_ID,
          buildOutgoingMessage(msg, translated),
        );
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

- [ ] **Step 4: 跑測試驗證 pass**

```bash
npm test -- index
```

Expected: 5 個測試 PASS。

- [ ] **Step 5: 跑全部測試**

```bash
npm test
```

Expected: 所有測試 PASS。

- [ ] **Step 6: 跑 typecheck**

```bash
npm run typecheck
```

Expected: 無錯誤。

- [ ] **Step 7: Commit**

```bash
git add anthropic_update_translator/src/index.ts anthropic_update_translator/test/index.test.ts
git commit -m "$(cat <<'EOF'
feat(anthropic-update-translator): wire scheduled handler

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: README 與設定說明

**Files:**
- Create: `anthropic_update_translator/README.md`

- [ ] **Step 1: 撰寫 README**

`anthropic_update_translator/README.md`:

````markdown
# anthropic-update-translator

Cloudflare Worker:每 5 分鐘輪詢 Discord `anthropic-update-raw` 頻道,把 Anthropic / Claude 官方推文 embed 翻成繁體中文,在 `anthropic-updates` 頻道用 Bot 發送同款 embed。

## 一次性設定

1. **Discord Bot**(假設你已經有 Bot):確認 Bot 在你的 server 中,且擁有
   - source 頻道 `anthropic-update-raw`: `Read Messages` + `Read Message History`
   - target 頻道 `anthropic-updates`: `Send Messages` + `Embed Links`
   - 取得 source / target 兩個頻道的 channel ID(右鍵頻道 → 複製頻道 ID,需先開啟 Discord 開發者模式)。

2. **Cloudflare KV namespace**
   - Cloudflare Dashboard → Workers & Pages → KV → Create namespace
   - 命名:`anthropic-update-translator`
   - 把 namespace ID 寫進 `wrangler.toml` 的 `[[kv_namespaces]] id`。

3. **Cloudflare API token**
   - My Profile → API Tokens → Create Token → Custom token
   - 權限:
     - Account → Workers Scripts → Edit
     - Account → Workers KV Storage → Edit
   - 取得 token 字串;Account ID 在 Dashboard 右側面板可見。

4. **填入 `wrangler.toml` 兩個 channel ID 與 KV namespace ID**,commit 推上 master。

5. **GitHub Secrets**(Settings → Secrets and variables → Actions → New):
   - `CLOUDFLARE_API_TOKEN`
   - `CLOUDFLARE_ACCOUNT_ID`
   - `DISCORD_BOT_TOKEN`
   - `GEMINI_API_KEY`

6. push 觸發 `.github/workflows/deploy-anthropic-translator.yml`,或在 Actions 頁面手動 `workflow_dispatch`。

## 切換到 Claude 翻譯

1. GitHub Secrets 新增 `CLAUDE_API_KEY`。
2. 修改 `wrangler.toml`:`TRANSLATOR = "claude"`。
3. 修改 workflow,在 `secrets:` 與 `env:` 區塊加入 `CLAUDE_API_KEY`。
4. push 觸發部署。

## 本機開發

```bash
cd anthropic_update_translator
npm install
npm test          # vitest
npm run typecheck # tsc --noEmit
```

不需在本機跑 `wrangler deploy`;部署一律走 GitHub Actions。

## 監控

Cloudflare Dashboard → Workers & Pages → `anthropic-update-translator` → Logs(real-time)。所有錯誤都會 `console.error`。
````

- [ ] **Step 2: Commit**

```bash
git add anthropic_update_translator/README.md
git commit -m "$(cat <<'EOF'
docs(anthropic-update-translator): add README

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/deploy-anthropic-translator.yml`

- [ ] **Step 1: 撰寫 workflow**

`.github/workflows/deploy-anthropic-translator.yml`:

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
    defaults:
      run:
        working-directory: anthropic_update_translator
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: anthropic_update_translator/package-lock.json

      - run: npm ci

      - name: Typecheck
        run: npm run typecheck

      - name: Test
        run: npm test

      - name: Deploy to Cloudflare
        uses: cloudflare/wrangler-action@v3
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

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/deploy-anthropic-translator.yml
git commit -m "$(cat <<'EOF'
ci(anthropic-update-translator): add deploy workflow

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: 更新根目錄 CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 在 GitHub Actions 區塊新增條目**

讀 `CLAUDE.md`,找到 `## GitHub Actions` 區塊,在現有 active workflows 列表加入一行:

原本:

```markdown
Active workflows (triggered on schedule + `workflow_dispatch`):
- `monthly-ledger-analysis.yml` — monthly ledger summary to Notion
- `deploy-pages.yml` — builds the travel apps and deploys to GitHub Pages (custom domain `tools.paul-learning.dev`)
- `deploy-eat-later-bot.yml` — rsyncs eat_later bot to VPS, restarts systemd service
```

改為(加入第四行):

```markdown
Active workflows (triggered on schedule + `workflow_dispatch`):
- `monthly-ledger-analysis.yml` — monthly ledger summary to Notion
- `deploy-pages.yml` — builds the travel apps and deploys to GitHub Pages (custom domain `tools.paul-learning.dev`)
- `deploy-eat-later-bot.yml` — rsyncs eat_later bot to VPS, restarts systemd service
- `deploy-anthropic-translator.yml` — deploys the Anthropic update translator Cloudflare Worker (cron: every 5 min)
```

- [ ] **Step 2: 在 Required secrets 行加入新 secret 名稱**

原本:

```markdown
Required secrets: `NOTION_SECRET`, `DISCORD_*_WEBHOOK_URL`, `GOOGLE_API_KEY`.
```

改為:

```markdown
Required secrets: `NOTION_SECRET`, `DISCORD_*_WEBHOOK_URL`, `GOOGLE_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `DISCORD_BOT_TOKEN`, `GEMINI_API_KEY`.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(CLAUDE.md): mention anthropic-update-translator workflow

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: 最終驗收檢查

**Files:** 無(只跑指令)

- [ ] **Step 1: 從 repo root 跑完整 npm install + 測試**

```bash
cd anthropic_update_translator
npm ci
npm run typecheck
npm test
```

Expected:
- typecheck:無錯誤
- vitest:所有測試 PASS,且檔案涵蓋 filter / format / state / discord / gemini / claude / factory / index

- [ ] **Step 2: 提醒使用者完成 README 中的「一次性設定」**

向使用者列出:
1. 確認 Discord Bot 已加入兩個頻道並有對應權限。
2. 建立 Cloudflare KV namespace,把 id 填入 `wrangler.toml`,commit + push。
3. 建立 Cloudflare API Token 並設定 4 個 GitHub Secrets。
4. push 到 master(或在 Actions 頁手動觸發 workflow_dispatch)。
5. 觀察 Cloudflare Dashboard → Workers Logs,以及 target 頻道是否收到翻譯訊息。

完成後本任務結束。
