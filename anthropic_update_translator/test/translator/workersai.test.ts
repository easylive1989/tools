import { describe, expect, it, vi } from "vitest";
import { WorkersAiTranslator } from "../../src/translator/workersai";
import { TranslationError } from "../../src/translator/types";

function fakeAi(run: (model: string, opts: { messages: { role: string; content: string }[] }) => unknown) {
  return { run: vi.fn(run) } as unknown as Ai;
}

const MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast";

describe("WorkersAiTranslator", () => {
  it("translate 呼叫 env.AI.run 並回傳 response", async () => {
    const ai = fakeAi(() => ({ response: "翻譯結果" }));
    const t = new WorkersAiTranslator(ai, MODEL);
    const out = await t.translate("Hello");

    expect(out).toBe("翻譯結果");
    expect((ai.run as ReturnType<typeof vi.fn>).mock.calls[0]![0]).toBe(MODEL);
    const messages = (ai.run as ReturnType<typeof vi.fn>).mock.calls[0]![1].messages;
    expect(messages[0].content).toContain("Hello");
  });

  it("response 缺 response 欄位時拋 TranslationError", async () => {
    const ai = fakeAi(() => ({ foo: "bar" }));
    const t = new WorkersAiTranslator(ai, MODEL);
    await expect(t.translate("x")).rejects.toBeInstanceOf(TranslationError);
  });

  it("env.AI.run 丟錯時轉成 TranslationError", async () => {
    const ai = fakeAi(() => {
      throw new Error("boom");
    });
    const t = new WorkersAiTranslator(ai, MODEL);
    await expect(t.translate("x")).rejects.toBeInstanceOf(TranslationError);
  });

  it("response 為空字串時拋 TranslationError", async () => {
    const ai = fakeAi(() => ({ response: "   " }));
    const t = new WorkersAiTranslator(ai, MODEL);
    await expect(t.translate("x")).rejects.toBeInstanceOf(TranslationError);
  });
});
