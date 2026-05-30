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
});
