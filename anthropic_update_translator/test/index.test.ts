import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import type { Env } from "../src/env";
import { MemoryKV, asKV } from "./helpers";

afterEach(() => {
  vi.unstubAllGlobals();
});

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
        },
        (url, body) => posts.push({ url, body }),
      ),
    );

    await worker.scheduled(event, makeEnv(kv), ctx);

    expect(await kv.get("last_message_id")).toBe("101");
    const targetPost = posts.find((p) => p.url.includes("/channels/TGT/messages"));
    expect(targetPost).toBeDefined();
    expect(JSON.parse(targetPost!.body).embeds[0].description).toBe("你好世界");
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

  it("HackMD 建立失敗:推文照常發,不附連結也不寫入 KV", async () => {
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
                  content: "https://www.anthropic.com/news/z",
                  embeds: [
                    {
                      author: { name: "Anthropic (@AnthropicAI)" },
                      description: "text https://www.anthropic.com/news/z",
                      url: "https://twitter.com/AnthropicAI/status/101",
                    },
                  ],
                },
              ]),
            ),
          "anthropic.com/news/z": () =>
            new Response("<article><h1>Z</h1><p>Body.</p></article>", { status: 200 }),
          "api.hackmd.io/v1/notes": () => new Response("boom", { status: 500 }),
          "/channels/TGT/messages": () => new Response("{}", { status: 200 }),
        },
        (url, body) => posts.push({ url, body }),
      ),
    );

    await worker.scheduled(event, makeEnv(kv, { TRANSLATOR: "workersai" }), ctx);

    const post = posts.find((p) => p.url.includes("/channels/TGT/messages"))!;
    expect(JSON.parse(post.body).embeds[0].description).toBe("譯文");
    expect(JSON.parse(post.body).content).not.toContain("hackmd.io");
    expect(await kv.get("hackmd:101")).toBeNull();
    expect(await kv.get("last_message_id")).toBe("101");
  });

  it("文章抓取失敗:補發一則錯誤通知說明原因(fetch-failed)", async () => {
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
          "/channels/TGT/messages": () => new Response("{}", { status: 200 }),
        },
        (url, body) => posts.push({ url, body }),
      ),
    );

    await worker.scheduled(event, makeEnv(kv, { TRANSLATOR: "workersai" }), ctx);

    const tgtPosts = posts.filter((p) => p.url.includes("/channels/TGT/messages"));
    expect(tgtPosts).toHaveLength(2); // 翻譯推文 + 錯誤通知
    const errPost = tgtPosts.find((p) => p.body.includes("全文翻譯未產生 HackMD 連結"))!;
    expect(errPost).toBeDefined();
    expect(JSON.parse(errPost.body).content).toContain("抓取失敗");
    expect(await kv.get("last_message_id")).toBe("101");
  });

  it("純文字推文(無 anthropic 連結):補發 no-link 通知", async () => {
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
                      description: "just text, no article link",
                      url: "https://twitter.com/AnthropicAI/status/101",
                    },
                  ],
                },
              ]),
            ),
          "/channels/TGT/messages": () => new Response("{}", { status: 200 }),
        },
        (url, body) => posts.push({ url, body }),
      ),
    );

    await worker.scheduled(event, makeEnv(kv, { TRANSLATOR: "workersai" }), ctx);

    const errPost = posts.find(
      (p) => p.url.includes("/channels/TGT/messages") && p.body.includes("全文翻譯未產生 HackMD 連結"),
    )!;
    expect(errPost).toBeDefined();
    expect(JSON.parse(errPost.body).content).toContain("anthropic.com 文章連結");
  });

  it("HackMD 建立失敗:補發 hackmd-failed 通知含細節", async () => {
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
                  content: "https://www.anthropic.com/news/z",
                  embeds: [
                    {
                      author: { name: "Anthropic (@AnthropicAI)" },
                      description: "text https://www.anthropic.com/news/z",
                      url: "https://twitter.com/AnthropicAI/status/101",
                    },
                  ],
                },
              ]),
            ),
          "anthropic.com/news/z": () =>
            new Response("<article><h1>Z</h1><p>Body.</p></article>", { status: 200 }),
          "api.hackmd.io/v1/notes": () => new Response("boom", { status: 500 }),
          "/channels/TGT/messages": () => new Response("{}", { status: 200 }),
        },
        (url, body) => posts.push({ url, body }),
      ),
    );

    await worker.scheduled(event, makeEnv(kv, { TRANSLATOR: "workersai" }), ctx);

    const errPost = posts.find(
      (p) => p.url.includes("/channels/TGT/messages") && p.body.includes("全文翻譯未產生 HackMD 連結"),
    )!;
    expect(errPost).toBeDefined();
    expect(JSON.parse(errPost.body).content).toContain("建立 HackMD 筆記失敗");
  });

  it("成功建立 HackMD:不補發錯誤通知", async () => {
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
                  content: "https://www.anthropic.com/news/ok",
                  embeds: [
                    {
                      author: { name: "Anthropic (@AnthropicAI)" },
                      description: "text https://www.anthropic.com/news/ok",
                      url: "https://twitter.com/AnthropicAI/status/101",
                    },
                  ],
                },
              ]),
            ),
          "anthropic.com/news/ok": () =>
            new Response("<article><h1>ok</h1><p>body</p></article>", { status: 200 }),
          "api.hackmd.io/v1/notes": () =>
            new Response(JSON.stringify({ publishLink: "https://hackmd.io/@x/ok" }), { status: 201 }),
          "/channels/TGT/messages": () => new Response("{}", { status: 200 }),
        },
        (url, body) => posts.push({ url, body }),
      ),
    );

    await worker.scheduled(event, makeEnv(kv, { TRANSLATOR: "workersai" }), ctx);

    const errPost = posts.find(
      (p) => p.url.includes("/channels/TGT/messages") && p.body.includes("全文翻譯未產生 HackMD 連結"),
    );
    expect(errPost).toBeUndefined();
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
});
