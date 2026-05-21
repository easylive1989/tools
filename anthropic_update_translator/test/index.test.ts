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
    COMMUNITY_BOT_TOKEN: "CBT",
    GEMINI_API_KEY: "GK",
    SOURCE_CHANNEL_ID: "SRC",
    TARGET_CHANNEL_ID: "TGT",
    COMMUNITY_CHANNEL_ID: "COM",
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
const event = { cron: "*/5 * * * *", scheduledTime: 0, type: "scheduled" } as unknown as ScheduledController;

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
          "/channels/COM/messages": () => new Response("{}", { status: 200 }),
        },
        (url, body) => posts.push({ url, body }),
      ),
    );

    await worker.scheduled(event, makeEnv(kv), ctx);

    expect(await kv.get("last_message_id")).toBe("101");
    const targetPost = posts.find((p) => p.url.includes("/channels/TGT/messages"));
    expect(targetPost).toBeDefined();
    expect(JSON.parse(targetPost!.body).embeds[0].description).toBe("你好世界");
    const communityPost = posts.find((p) => p.url.includes("/channels/COM/messages"));
    expect(communityPost).toBeDefined();
    expect(JSON.parse(communityPost!.body).embeds[0].description).toBe("你好世界");
  });

  it("社群頻道 POST 失敗時不阻塞:仍推進 last_message_id", async () => {
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
          "/channels/COM/messages": () =>
            new Response("forbidden", { status: 403 }),
        },
        (url, body) => posts.push({ url, body }),
      ),
    );

    await worker.scheduled(event, makeEnv(kv), ctx);

    expect(await kv.get("last_message_id")).toBe("101");
    expect(posts.some((p) => p.url.includes("/channels/TGT/messages"))).toBe(true);
    expect(posts.some((p) => p.url.includes("/channels/COM/messages"))).toBe(true);
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
