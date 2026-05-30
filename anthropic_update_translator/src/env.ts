export interface Env {
  DISCORD_BOT_TOKEN: string;
  GEMINI_API_KEY: string;
  CLAUDE_API_KEY?: string;

  SOURCE_CHANNEL_ID: string;
  TARGET_CHANNEL_ID: string;
  TRANSLATOR: "gemini" | "claude" | "workersai";
  GEMINI_MODEL: string;
  CLAUDE_MODEL: string;
  WORKERSAI_MODEL: string;
  HACKMD_API_TOKEN: string;

  AI: Ai;
  KV: KVNamespace;
}
