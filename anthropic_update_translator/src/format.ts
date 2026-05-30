import type { DiscordEmbed, DiscordMessage } from "./filter";
import type { Article } from "./article";

const ANTHROPIC_ORANGE = 0xd97757;
const TWITTER_URL_REGEX = /https?:\/\/(?:twitter\.com|x\.com)\/[^\s)"'<>,]+/i;

export interface OutgoingMessage {
  content: string;
  embeds: DiscordEmbed[];
}

export function buildOutgoingMessage(
  source: DiscordMessage,
  translated: string,
  hackmdUrl?: string,
): OutgoingMessage {
  const sourceEmbed = source.embeds[0];
  if (!sourceEmbed) {
    throw new Error("buildOutgoingMessage: source has no embed");
  }

  const tweetUrl =
    sourceEmbed.url ?? source.content.match(TWITTER_URL_REGEX)?.[0] ?? "";

  const lines: string[] = [];
  if (tweetUrl) lines.push(tweetUrl);
  if (hackmdUrl) lines.push(`📄 全文翻譯:${hackmdUrl}`);

  const embed: DiscordEmbed = {
    author: sourceEmbed.author,
    description: translated,
    url: sourceEmbed.url,
    timestamp: sourceEmbed.timestamp,
    thumbnail: sourceEmbed.thumbnail,
    footer: { text: "X" },
    color: ANTHROPIC_ORANGE,
  };

  return {
    content: lines.join("\n"),
    embeds: [embed],
  };
}

export function buildHackMdContent(article: Article, translatedBody: string): string {
  return [`# ${article.title}`, "", `> 原文:${article.url}`, "", translatedBody, ""].join("\n");
}
