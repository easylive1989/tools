import { describe, it, expect } from "vitest";
import {
  buildOutgoingMessage,
  buildHackMdContent,
  buildHackMdErrorMessage,
} from "../src/format";
import type { DiscordMessage } from "../src/filter";
import type { Article } from "../src/article";

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

  it("當 source.embeds 為空時 throw", () => {
    expect(() =>
      buildOutgoingMessage({ id: "x", content: "", embeds: [] }, "text"),
    ).toThrow("buildOutgoingMessage: source has no embed");
  });

  it("regex 不擷取尾端標點(括號)", () => {
    const source: DiscordMessage = {
      id: "103",
      content: "see this (https://twitter.com/AnthropicAI/status/789)",
      embeds: [
        {
          author: { name: "Anthropic (@AnthropicAI)" },
          description: "hello",
        },
      ],
    };
    const out = buildOutgoingMessage(source, "你好");
    expect(out.content).toBe("https://twitter.com/AnthropicAI/status/789");
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

describe("buildHackMdErrorMessage", () => {
  const source: DiscordMessage = {
    id: "1",
    content: "https://twitter.com/AnthropicAI/status/1",
    embeds: [
      {
        author: { name: "Anthropic (@AnthropicAI)" },
        description: "hi",
        url: "https://twitter.com/AnthropicAI/status/1",
      },
    ],
  };

  it("no-link:含 ⚠️ 標頭、推文連結與對應原因說明,embeds 為空", () => {
    const out = buildHackMdErrorMessage(source, "no-link");
    expect(out.content).toContain("⚠️");
    expect(out.content).toContain("全文翻譯未產生 HackMD 連結");
    expect(out.content).toContain("https://twitter.com/AnthropicAI/status/1");
    expect(out.content).toContain("anthropic.com 文章連結");
    expect(out.embeds).toEqual([]);
  });

  it("各 reason 對應不同中文說明", () => {
    expect(buildHackMdErrorMessage(source, "fetch-failed").content).toContain("抓取失敗");
    expect(buildHackMdErrorMessage(source, "no-content").content).toContain("內文段落");
    expect(buildHackMdErrorMessage(source, "translate-failed").content).toContain("翻譯失敗");
    expect(buildHackMdErrorMessage(source, "hackmd-failed").content).toContain("HackMD");
  });

  it("有 detail 時附在訊息中", () => {
    const out = buildHackMdErrorMessage(source, "hackmd-failed", "500 boom");
    expect(out.content).toContain("500 boom");
  });

  it("detail 過長時截斷到 500 字", () => {
    const long = "x".repeat(900);
    const out = buildHackMdErrorMessage(source, "hackmd-failed", long);
    expect(out.content).toContain("x".repeat(500));
    expect(out.content).not.toContain("x".repeat(501));
  });

  it("從 content 擷取推文連結(embed.url 缺失時)", () => {
    const noUrl: DiscordMessage = {
      id: "2",
      content: "see https://x.com/AnthropicAI/status/456 here",
      embeds: [{ author: { name: "Anthropic (@AnthropicAI)" }, description: "hi" }],
    };
    const out = buildHackMdErrorMessage(noUrl, "no-link");
    expect(out.content).toContain("https://x.com/AnthropicAI/status/456");
  });
});

describe("buildOutgoingMessage with hackmdUrl", () => {
  it("有 hackmdUrl 時附在 content", () => {
    const source: DiscordMessage = {
      id: "1",
      content: "https://twitter.com/AnthropicAI/status/1",
      embeds: [{ author: { name: "Anthropic (@AnthropicAI)" }, description: "hi", url: "https://twitter.com/AnthropicAI/status/1" }],
    };
    const out = buildOutgoingMessage(source, "你好", "https://hackmd.io/@x/abc");
    expect(out.content).toContain("https://twitter.com/AnthropicAI/status/1");
    expect(out.content).toContain("https://hackmd.io/@x/abc");
    expect(out.embeds[0]!.description).toBe("你好");
  });

  it("無 hackmdUrl 時 content 不變(只有 tweet 連結)", () => {
    const source: DiscordMessage = {
      id: "1",
      content: "https://twitter.com/AnthropicAI/status/1",
      embeds: [{ author: { name: "Anthropic (@AnthropicAI)" }, description: "hi", url: "https://twitter.com/AnthropicAI/status/1" }],
    };
    const out = buildOutgoingMessage(source, "你好");
    expect(out.content).toBe("https://twitter.com/AnthropicAI/status/1");
  });
});
