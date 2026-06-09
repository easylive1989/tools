import type { DiscordMessage } from "./filter";

export interface Article {
  url: string;
  title: string;
  paragraphs: string[];
}

export type ArticleFailure = "no-link" | "fetch-failed" | "no-content";

export type ArticleExtraction =
  | { ok: true; article: Article }
  | { ok: false; reason: ArticleFailure; url?: string };

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

// 非內文區塊:導覽列、頁首頁尾、側欄、script/style。這些區塊裡的 <p>
// (例如 anthropic.com 頂部選單的 Research / News / Try Claude 等)
// 不該被當成文章段落送去翻譯。
const NOISE_TAGS = ["script", "style", "nav", "header", "footer", "aside"];

function stripNoiseBlocks(html: string): string {
  let out = html;
  for (const tag of NOISE_TAGS) {
    out = out.replace(new RegExp(`<${tag}\\b[^>]*>[\\s\\S]*?</${tag}>`, "gi"), " ");
  }
  return out;
}

// 將內文範圍縮到 <article>(優先)或 <main>,排除版面其他區塊;
// 找不到語意標籤時退回整份 HTML。
function scopeToMainContent(html: string): string {
  const article = html.match(/<article[^>]*>([\s\S]*?)<\/article>/i);
  if (article?.[1]) return article[1];
  const main = html.match(/<main[^>]*>([\s\S]*?)<\/main>/i);
  if (main?.[1]) return main[1];
  return html;
}

export function extractArticleFromHtml(html: string): { title: string; paragraphs: string[] } | null {
  const cleaned = stripNoiseBlocks(html);

  const h1 = cleaned.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i);
  const titleTag = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  const title = clean(h1?.[1] ?? titleTag?.[1] ?? "") || "Anthropic";

  const scope = scopeToMainContent(cleaned);

  const paragraphs: string[] = [];
  for (const m of scope.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/gi)) {
    const text = clean(m[1] ?? "");
    if (text !== "") paragraphs.push(text);
  }
  if (paragraphs.length === 0) return null;
  return { title, paragraphs };
}

// 失敗原因優先序:抓到頁面卻無內文(no-content)比抓取失敗(fetch-failed)更有資訊。
const FAILURE_RANK: Record<Exclude<ArticleFailure, "no-link">, number> = {
  "fetch-failed": 1,
  "no-content": 2,
};

export async function extractAnthropicArticle(
  msg: DiscordMessage,
  fetchImpl: typeof fetch = fetch,
): Promise<ArticleExtraction> {
  const candidates = collectUrls(msg).filter((u) => isAnthropicHost(u) || isShortLink(u));
  if (candidates.length === 0) return { ok: false, reason: "no-link" };

  let failure: { reason: Exclude<ArticleFailure, "no-link">; url: string } | null = null;
  const recordFailure = (reason: Exclude<ArticleFailure, "no-link">, url: string) => {
    if (!failure || FAILURE_RANK[reason] > FAILURE_RANK[failure.reason]) {
      failure = { reason, url };
    }
  };

  for (const url of candidates) {
    let resp: Response;
    try {
      resp = await fetchImpl(url, { redirect: "follow" });
    } catch {
      recordFailure("fetch-failed", url);
      continue;
    }
    if (!resp.ok) {
      recordFailure("fetch-failed", url);
      continue;
    }

    const finalUrl = resp.url || url;
    if (!isAnthropicHost(finalUrl)) {
      recordFailure("fetch-failed", url);
      continue;
    }

    let html: string;
    try {
      html = await resp.text();
    } catch {
      recordFailure("fetch-failed", finalUrl);
      continue;
    }

    const parsed = extractArticleFromHtml(html);
    if (!parsed) {
      recordFailure("no-content", finalUrl);
      continue;
    }

    return {
      ok: true,
      article: { url: finalUrl, title: parsed.title, paragraphs: parsed.paragraphs },
    };
  }

  // candidates 非空,迴圈未成功 → failure 必為非 null
  return { ok: false, reason: failure!.reason, url: failure!.url };
}
