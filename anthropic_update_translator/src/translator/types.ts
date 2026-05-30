export interface Translator {
  translate(text: string): Promise<string>;
  translateArticle(markdown: string): Promise<string>;
}

export class TranslationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TranslationError";
  }
}

export function buildPrompt(text: string): string {
  return [
    "你是一個專業翻譯,請將以下 Anthropic / Claude 官方推文翻譯成「繁體中文(台灣用語)」。",
    "",
    "規則:",
    "1. 保留所有 URL 連結原樣不翻譯。",
    "2. 保留所有 hashtag(例如 #ClaudeCode)原樣不翻譯。",
    "3. 保留所有 @mention(例如 @AnthropicAI)原樣不翻譯。",
    "4. 產品 / 品牌名稱(Claude, Anthropic, Sonnet, Opus, Haiku 等)保留原文。",
    "5. 技術術語(API, token, prompt, agent 等)視語境決定是否保留原文;若中文較自然就翻成中文。",
    "6. 只輸出翻譯結果,不要加任何說明、引言或前後綴。",
    "7. 換行請保留與原文一致。",
    "",
    "原文:",
    text,
  ].join("\n");
}

export function buildArticlePrompt(markdown: string): string {
  return [
    "你是一個專業翻譯,請將以下 Anthropic 官方文章內容翻譯成「繁體中文(台灣用語)」。",
    "",
    "規則:",
    "1. 保留所有 URL 連結與 markdown 連結語法原樣。",
    "2. 保留 markdown 結構(標題層級、清單、粗體等)。",
    "3. 程式碼區塊與行內程式碼的內容保留原樣不翻譯。",
    "4. 產品 / 品牌名稱(Claude, Anthropic, Sonnet, Opus, Haiku 等)保留原文。",
    "5. 技術術語視語境決定是否保留原文;若中文較自然就翻成中文。",
    "6. 只輸出翻譯結果,不要加任何說明、引言或前後綴。",
    "",
    "原文:",
    markdown,
  ].join("\n");
}

export function validateTranslation(original: string, translated: string): void {
  const t = translated.trim();
  if (t === "") {
    throw new TranslationError("translator returned empty string");
  }
  if (t.length > original.length * 10) {
    throw new TranslationError(
      `translator output too long: ${t.length} chars (original ${original.length})`,
    );
  }
}

export function validateArticleTranslation(translated: string): void {
  if (translated.trim() === "") {
    throw new TranslationError("translator returned empty string");
  }
}
