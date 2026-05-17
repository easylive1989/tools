import {
  buildPrompt,
  TranslationError,
  validateTranslation,
  type Translator,
} from "./types";

const TIMEOUT_MS = 10_000;
const MAX_TOKENS = 2048;

interface ClaudeResponse {
  content?: Array<{ type?: string; text?: string }>;
}

export class ClaudeTranslator implements Translator {
  constructor(private apiKey: string, private model: string) {}

  async translate(text: string): Promise<string> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);

    let res: Response;
    try {
      res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "x-api-key": this.apiKey,
          "anthropic-version": "2023-06-01",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          model: this.model,
          max_tokens: MAX_TOKENS,
          messages: [{ role: "user", content: buildPrompt(text) }],
        }),
        signal: ctrl.signal,
      });
    } catch (err) {
      throw new TranslationError(`Claude fetch failed: ${(err as Error).message}`);
    } finally {
      clearTimeout(timer);
    }

    if (!res.ok) {
      throw new TranslationError(`Claude HTTP ${res.status}: ${await res.text()}`);
    }

    const data = (await res.json()) as ClaudeResponse;
    const block = data.content?.find((c) => c.type === "text");
    const translated = block?.text;
    if (typeof translated !== "string") {
      throw new TranslationError(
        `Claude response missing content[*].text: ${JSON.stringify(data)}`,
      );
    }

    validateTranslation(text, translated);
    return translated.trim();
  }
}
