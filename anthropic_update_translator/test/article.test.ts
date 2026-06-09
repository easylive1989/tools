import { describe, expect, it, vi } from "vitest";
import {
  collectUrls,
  isAnthropicHost,
  extractArticleFromHtml,
  extractAnthropicArticle,
} from "../src/article";
import type { DiscordMessage } from "../src/filter";

function fakeResponse(opts: { ok?: boolean; url?: string; html?: string }) {
  return {
    ok: opts.ok ?? true,
    status: opts.ok === false ? 500 : 200,
    url: opts.url ?? "",
    text: async () => opts.html ?? "",
  } as unknown as Response;
}

const HTML = `
  <html><head><title>Fallback Title</title></head>
  <body><article>
    <h1>Real Title</h1>
    <p>First paragraph.</p>
    <p>  Second &amp; paragraph.  </p>
    <p></p>
  </article></body></html>`;

describe("collectUrls", () => {
  it("從 content / description / embed.url 收集並去重", () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "see https://www.anthropic.com/news/x and https://t.co/abc",
      embeds: [{ description: "https://www.anthropic.com/news/x", url: "https://twitter.com/AnthropicAI/status/1" }],
    };
    const urls = collectUrls(msg);
    expect(urls).toContain("https://www.anthropic.com/news/x");
    expect(urls).toContain("https://t.co/abc");
    expect(urls.filter((u) => u === "https://www.anthropic.com/news/x")).toHaveLength(1);
  });
});

describe("isAnthropicHost", () => {
  it("anthropic.com 與子網域為真,其他為假", () => {
    expect(isAnthropicHost("https://www.anthropic.com/news/x")).toBe(true);
    expect(isAnthropicHost("https://anthropic.com/x")).toBe(true);
    expect(isAnthropicHost("https://youtube.com/x")).toBe(false);
    expect(isAnthropicHost("not a url")).toBe(false);
  });
});

describe("extractArticleFromHtml", () => {
  it("抽出 h1 標題與非空段落,解碼 entity", () => {
    const parsed = extractArticleFromHtml(HTML);
    expect(parsed).not.toBeNull();
    expect(parsed!.title).toBe("Real Title");
    expect(parsed!.paragraphs).toEqual(["First paragraph.", "Second & paragraph."]);
  });

  it("無段落時回 null", () => {
    expect(extractArticleFromHtml("<html><h1>x</h1></html>")).toBeNull();
  });

  it("過濾掉 nav / header / footer 裡的選單文字,只留內文段落", () => {
    const html = `
      <html><body>
        <header><p>Research</p><p>Economic Futures</p></header>
        <nav><p>Learn</p><p>News</p><p>Try Claude</p><p>Science</p></nav>
        <main>
          <article>
            <h1>Paving the way for agents in biology</h1>
            <p>Actual first paragraph of the article.</p>
            <p>Actual second paragraph.</p>
          </article>
        </main>
        <footer><p>Commitments</p></footer>
      </body></html>`;
    const parsed = extractArticleFromHtml(html);
    expect(parsed).not.toBeNull();
    expect(parsed!.title).toBe("Paving the way for agents in biology");
    expect(parsed!.paragraphs).toEqual([
      "Actual first paragraph of the article.",
      "Actual second paragraph.",
    ]);
  });

  it("沒有 article 標籤時退回 main 範圍", () => {
    const html = `
      <html><body>
        <nav><p>Try Claude</p></nav>
        <main><p>Body paragraph.</p></main>
      </body></html>`;
    const parsed = extractArticleFromHtml(html);
    expect(parsed!.paragraphs).toEqual(["Body paragraph."]);
  });

  it("沒有 article / main 時退回整頁,但仍排除 nav/header/footer", () => {
    const html = `
      <html><body>
        <header><p>Research</p></header>
        <p>Loose body paragraph.</p>
        <footer><p>News</p></footer>
      </body></html>`;
    const parsed = extractArticleFromHtml(html);
    expect(parsed!.paragraphs).toEqual(["Loose body paragraph."]);
  });
});

describe("extractAnthropicArticle", () => {
  it("直連 anthropic.com → 抓 HTML 並回傳 { ok: true, article }", async () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "https://www.anthropic.com/news/x",
      embeds: [{ description: "text", url: "https://twitter.com/AnthropicAI/status/1" }],
    };
    const fetchImpl = vi.fn(async () => fakeResponse({ html: HTML }));
    const result = await extractAnthropicArticle(msg, fetchImpl as unknown as typeof fetch);

    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error("expected ok");
    expect(result.article.url).toBe("https://www.anthropic.com/news/x");
    expect(result.article.title).toBe("Real Title");
    expect(result.article.paragraphs[0]).toBe("First paragraph.");
  });

  it("t.co 短網址轉址到 anthropic.com → 用最終網址", async () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "https://t.co/abc",
      embeds: [{ description: "text", url: "https://twitter.com/AnthropicAI/status/1" }],
    };
    const fetchImpl = vi.fn(async () =>
      fakeResponse({ url: "https://www.anthropic.com/news/y", html: HTML }),
    );
    const result = await extractAnthropicArticle(msg, fetchImpl as unknown as typeof fetch);

    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error("expected ok");
    expect(result.article.url).toBe("https://www.anthropic.com/news/y");
  });

  it("沒有 anthropic.com 連結 → { ok: false, reason: 'no-link' },不 fetch", async () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "https://youtube.com/watch?v=1",
      embeds: [{ description: "text", url: "https://twitter.com/AnthropicAI/status/1" }],
    };
    const fetchImpl = vi.fn();
    const result = await extractAnthropicArticle(msg, fetchImpl as unknown as typeof fetch);

    expect(result).toEqual({ ok: false, reason: "no-link" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("fetch 非 200 → { ok: false, reason: 'fetch-failed' }", async () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "https://www.anthropic.com/news/x",
      embeds: [{ description: "text" }],
    };
    const fetchImpl = vi.fn(async () => fakeResponse({ ok: false }));
    const result = await extractAnthropicArticle(msg, fetchImpl as unknown as typeof fetch);

    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected failure");
    expect(result.reason).toBe("fetch-failed");
    expect(result.url).toBe("https://www.anthropic.com/news/x");
  });

  it("fetch 拋例外 → { ok: false, reason: 'fetch-failed' }", async () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "https://www.anthropic.com/news/x",
      embeds: [{ description: "text" }],
    };
    const fetchImpl = vi.fn(async () => {
      throw new Error("network down");
    });
    const result = await extractAnthropicArticle(msg, fetchImpl as unknown as typeof fetch);

    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected failure");
    expect(result.reason).toBe("fetch-failed");
  });

  it("短網址轉址到非 anthropic.com → { ok: false, reason: 'fetch-failed' }", async () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "https://t.co/abc",
      embeds: [{ description: "text" }],
    };
    const fetchImpl = vi.fn(async () =>
      fakeResponse({ url: "https://youtube.com/watch?v=1", html: HTML }),
    );
    const result = await extractAnthropicArticle(msg, fetchImpl as unknown as typeof fetch);

    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected failure");
    expect(result.reason).toBe("fetch-failed");
  });

  it("抓到 anthropic 頁面但無內文段落 → { ok: false, reason: 'no-content' }", async () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "https://www.anthropic.com/news/x",
      embeds: [{ description: "text" }],
    };
    const fetchImpl = vi.fn(async () =>
      fakeResponse({ html: "<html><h1>標題但無段落</h1></html>" }),
    );
    const result = await extractAnthropicArticle(msg, fetchImpl as unknown as typeof fetch);

    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected failure");
    expect(result.reason).toBe("no-content");
    expect(result.url).toBe("https://www.anthropic.com/news/x");
  });

  it("有多個連結,no-content 優先於 fetch-failed 回報", async () => {
    const msg: DiscordMessage = {
      id: "1",
      content: "https://www.anthropic.com/news/broken https://www.anthropic.com/news/empty",
      embeds: [{ description: "text" }],
    };
    const fetchImpl = vi.fn(async (url: string) => {
      if (url.includes("/broken")) return fakeResponse({ ok: false });
      return fakeResponse({ html: "<html><h1>no p</h1></html>" });
    });
    const result = await extractAnthropicArticle(msg, fetchImpl as unknown as typeof fetch);

    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected failure");
    expect(result.reason).toBe("no-content");
  });
});
