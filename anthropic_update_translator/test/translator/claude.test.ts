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
