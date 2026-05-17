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
