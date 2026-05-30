import {
  buildArticlePrompt,
  buildPrompt,
  TranslationError,
  validateArticleTranslation,
  validateTranslation,
  type Translator,
} from "./types";

interface WorkersAiTextOutput {
  response?: string;
}

export class WorkersAiTranslator implements Translator {
  constructor(private ai: Ai, private model: string) {}

  async translate(text: string): Promise<string> {
    const translated = await this.run(buildPrompt(text));
    validateTranslation(text, translated);
    return translated.trim();
  }

  async translateArticle(markdown: string): Promise<string> {
    const translated = await this.run(buildArticlePrompt(markdown));
    validateArticleTranslation(translated);
    return translated.trim();
  }

  private async run(prompt: string): Promise<string> {
    let out: unknown;
    try {
      const ai = this.ai as unknown as {
        run(
          model: string,
          opts: { messages: { role: string; content: string }[] },
        ): Promise<unknown>;
      };
      out = await ai.run(this.model, {
        messages: [{ role: "user", content: prompt }],
      });
    } catch (err) {
      throw new TranslationError(`Workers AI run failed: ${(err as Error).message}`);
    }
    const text = (out as WorkersAiTextOutput).response;
    if (typeof text !== "string") {
      throw new TranslationError(
        `Workers AI response missing 'response': ${JSON.stringify(out)}`,
      );
    }
    return text;
  }
}
