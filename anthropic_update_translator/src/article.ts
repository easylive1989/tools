import type { DiscordMessage } from "./filter";

export interface Article {
  url: string;
  title: string;
  paragraphs: string[];
}

const URL_REGEX = /https?:\/\/[^\s)"'<>]+/g;
const SHORT_LINK_HOSTS = new Set(["t.co", "bit.ly", "buff.ly", "ow.ly"]);

export function collectUrls(msg: DiscordMessage): string[] {
  const embed = msg.embeds[0];
  const haystack = [msg.content ?? "", embed?.description ?? "", embed?.url ?? ""].join("\n");
  const found = haystack.match(URL_REGEX) ?? [];
  const cleaned = found.map((u) => u.replace(/[.,);]+$/, ""));
  return [...new Set(cleaned)];
}

export function isAnthropicHost(urlString: string): boolean {
  try {
    const host = new URL(urlString).host.toLowerCase();
    return host === "anthropic.com" || host.endsWith(".anthropic.com");
  } catch {
    return false;
  }
}

function isShortLink(urlString: string): boolean {
  try {
    return SHORT_LINK_HOSTS.has(new URL(urlString).host.toLowerCase());
  } catch {
    return false;
  }
}

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, "");
}

function decodeEntities(text: string): string {
  return text
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ");
}

function clean(html: string): string {
  return decodeEntities(stripTags(html)).replace(/\s+/g, " ").trim();
}

export function extractArticleFromHtml(html: string): { title: string; paragraphs: string[] } | null {
  const h1 = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i);
  const titleTag = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  const title = clean(h1?.[1] ?? titleTag?.[1] ?? "") || "Anthropic";

  const paragraphs: string[] = [];
  for (const m of html.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/gi)) {
    const text = clean(m[1] ?? "");
    if (text !== "") paragraphs.push(text);
  }
  if (paragraphs.length === 0) return null;
  return { title, paragraphs };
}

export async function extractAnthropicArticle(
  msg: DiscordMessage,
  fetchImpl: typeof fetch = fetch,
): Promise<Article | null> {
  for (const url of collectUrls(msg)) {
    if (!isAnthropicHost(url) && !isShortLink(url)) continue;

    let resp: Response;
    try {
      resp = await fetchImpl(url, { redirect: "follow" });
    } catch {
      continue;
    }
    if (!resp.ok) continue;

    const finalUrl = resp.url || url;
    if (!isAnthropicHost(finalUrl)) continue;

    let html: string;
    try {
      html = await resp.text();
    } catch {
      continue;
    }

    const parsed = extractArticleFromHtml(html);
    if (!parsed) continue;

    return { url: finalUrl, title: parsed.title, paragraphs: parsed.paragraphs };
  }
  return null;
}
