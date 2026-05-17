import type { Env } from "../env";
import { GeminiTranslator } from "./gemini";
import { ClaudeTranslator } from "./claude";
import type { Translator } from "./types";

export type { Translator } from "./types";

export function createTranslator(env: Env): Translator {
  switch (env.TRANSLATOR) {
    case "gemini":
      return new GeminiTranslator(env.GEMINI_API_KEY, env.GEMINI_MODEL);
    case "claude": {
      if (!env.CLAUDE_API_KEY) {
        throw new Error("CLAUDE_API_KEY is required when TRANSLATOR=claude");
      }
      return new ClaudeTranslator(env.CLAUDE_API_KEY, env.CLAUDE_MODEL);
    }
    default:
      throw new Error(`Unknown TRANSLATOR: ${env.TRANSLATOR}`);
  }
}
