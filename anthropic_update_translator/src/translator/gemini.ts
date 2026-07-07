import { buildPrompt, TranslationError, validateTranslation, type Translator } from "./types";

const TIMEOUT_MS = 10_000;

interface GeminiResponse {
  candidates?: Array<{
    content?: { parts?: Array<{ text?: string }> };
  }>;
}

export class GeminiTranslator implements Translator {
  constructor(private apiKey: string, private model: string) {}

  async translate(text: string): Promise<string> {
    const translated = await this.request(buildPrompt(text));
    validateTranslation(text, translated);
    return translated.trim();
  }

  private async request(prompt: string): Promise<string> {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${this.model}:generateContent?key=${this.apiKey}`;
    const body = JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] });

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);

    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        signal: ctrl.signal,
      });
    } catch (err) {
      throw new TranslationError(`Gemini fetch failed: ${(err as Error).message}`);
    } finally {
      clearTimeout(timer);
    }

    if (!res.ok) {
      throw new TranslationError(`Gemini HTTP ${res.status}: ${await res.text()}`);
    }

    const data = (await res.json()) as GeminiResponse;
    const translated = data.candidates?.[0]?.content?.parts?.[0]?.text;
    if (typeof translated !== "string") {
      throw new TranslationError(
        `Gemini response missing candidates[0].content.parts[0].text: ${JSON.stringify(data)}`,
      );
    }
    return translated;
  }
}
