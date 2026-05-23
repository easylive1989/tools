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
