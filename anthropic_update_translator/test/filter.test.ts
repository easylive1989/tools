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
