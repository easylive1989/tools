export interface DiscordEmbedAuthor {
  name?: string;
  url?: string;
  icon_url?: string;
}

export interface DiscordEmbed {
  title?: string;
  description?: string;
  url?: string;
  timestamp?: string;
  color?: number;
  author?: DiscordEmbedAuthor;
  thumbnail?: { url: string };
  footer?: { text: string; icon_url?: string };
}

export interface DiscordMessage {
  id: string;
  content: string;
  embeds: DiscordEmbed[];
}

const ALLOWED_AUTHOR_HANDLES = ["@AnthropicAI", "@claudeai"];

export function shouldTranslate(msg: DiscordMessage): boolean {
  const embed = msg.embeds[0];
  if (!embed) return false;
  if (!embed.description || embed.description.trim() === "") return false;
  const authorName = embed.author?.name ?? "";
  return ALLOWED_AUTHOR_HANDLES.some((handle) => authorName.includes(handle));
}
