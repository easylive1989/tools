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
