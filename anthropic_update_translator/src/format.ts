import type { DiscordEmbed, DiscordMessage } from "./filter";

const ANTHROPIC_ORANGE = 0xd97757;
const TWITTER_URL_REGEX = /https?:\/\/(?:twitter\.com|x\.com)\/[^\s)"'<>,]+/i;

export interface OutgoingMessage {
  content: string;
  embeds: DiscordEmbed[];
}

export function buildOutgoingMessage(
  source: DiscordMessage,
  translated: string,
): OutgoingMessage {
  const sourceEmbed = source.embeds[0];
  if (!sourceEmbed) {
    throw new Error("buildOutgoingMessage: source has no embed");
  }

  const tweetUrl =
    sourceEmbed.url ?? source.content.match(TWITTER_URL_REGEX)?.[0] ?? "";

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
    content: tweetUrl,
    embeds: [embed],
  };
}
