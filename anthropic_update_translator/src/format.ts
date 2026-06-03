import type { DiscordEmbed, DiscordMessage } from "./filter";
import type { Article, ArticleFailure } from "./article";

const ANTHROPIC_ORANGE = 0xd97757;
const TWITTER_URL_REGEX = /https?:\/\/(?:twitter\.com|x\.com)\/[^\s)"'<>,]+/i;
const ERROR_DETAIL_MAX = 500;

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
  hackmdUrl?: string,
): OutgoingMessage {
  const sourceEmbed = source.embeds[0];
  if (!sourceEmbed) {
    throw new Error("buildOutgoingMessage: source has no embed");
  }

  const tweetUrl = resolveTweetUrl(source);

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

export type HackMdFailureReason = ArticleFailure | "translate-failed" | "hackmd-failed";

const HACKMD_REASON_TEXT: Record<HackMdFailureReason, string> = {
  "no-link": "此推文沒有 anthropic.com 文章連結,略過全文翻譯。",
  "fetch-failed": "找到文章連結,但抓取失敗(連線錯誤、非 200,或重導到非 anthropic.com)。",
  "no-content": "抓到文章頁面,但解析不到內文段落(<p>)。",
  "translate-failed": "文章內文翻譯失敗(Workers AI)。",
  "hackmd-failed": "建立 HackMD 筆記失敗。",
};

/** 全文翻譯未產生 HackMD 連結時,組出一則獨立的 Discord 通知訊息(純文字、無 embed)。 */
export function buildHackMdErrorMessage(
  source: DiscordMessage,
  reason: HackMdFailureReason,
  detail?: string,
): OutgoingMessage {
  const tweetUrl = resolveTweetUrl(source);
  const lines = ["⚠️ 全文翻譯未產生 HackMD 連結"];
  if (tweetUrl) lines.push(`推文:${tweetUrl}`);
  lines.push(`原因:${HACKMD_REASON_TEXT[reason]}`);
  if (detail) lines.push(`細節:${detail.slice(0, ERROR_DETAIL_MAX)}`);
  return { content: lines.join("\n"), embeds: [] };
}
