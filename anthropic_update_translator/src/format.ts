import type { DiscordEmbed, DiscordMessage } from "./filter";

const ANTHROPIC_ORANGE = 0xd97757;
const TWITTER_URL_REGEX = /https?:\/\/(?:twitter\.com|x\.com)\/[^\s)"'<>,]+/i;

export interface OutgoingMessage {
  content: string;
  embeds: DiscordEmbed[];
}

/** 取得推文連結:優先 embed.url,其次從 content 擷取第一個 twitter/x URL。 */
function resolveTweetUrl(source: DiscordMessage): string {
  return source.embeds[0]?.url ?? source.content.match(TWITTER_URL_REGEX)?.[0] ?? "";
}

export function buildOutgoingMessage(
  source: DiscordMessage,
  translated: string,
): OutgoingMessage {
  const sourceEmbed = source.embeds[0];
  if (!sourceEmbed) {
    throw new Error("buildOutgoingMessage: source has no embed");
  }

  const tweetUrl = resolveTweetUrl(source);

  const lines: string[] = [];
  if (tweetUrl) lines.push(tweetUrl);

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
