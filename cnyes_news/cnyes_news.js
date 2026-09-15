#!/usr/bin/env node

// Required parameters:
// @raycast.schemaVersion 1
// @raycast.title 鉅亨網台股新聞
// @raycast.mode fullOutput
// @raycast.packageName Finance

// Optional parameters:
// @raycast.icon 📈
// @raycast.refreshTime 10m

// Documentation:
// @raycast.description 列出鉅亨網最新台股即時新聞卡片清單
// @raycast.author wu_paul
// @raycast.authorURL https://github.com/easylive1989

const https = require("https");
const http = require("http");

// ANSI 樣式設定
const RESET = "\x1b[0m";
const BOLD = "\x1b[1m";
const CYAN = "\x1b[36m";
const YELLOW = "\x1b[33m";
const GRAY = "\x1b[90m";
const BLACK = "\x1b[1m\x1b[30m";

const API_URL = "https://api.cnyes.com/media/api/v1/newslist/category/tw_stock?limit=10";
const RSS_URL = "https://news.cnyes.com/rss/category/tw_stock";

/**
 * 通用 HTTP GET 請求（相容 Node 16 及以下沒有全域 fetch 的環境）
 */
function fetchUrl(url, headers = {}) {
  if (typeof fetch === "function") {
    return fetch(url, { headers }).then(async (res) => {
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      return res.text();
    });
  }

  return new Promise((resolve, reject) => {
    const client = url.startsWith("https") ? https : http;
    const req = client.get(url, { headers }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return fetchUrl(res.headers.location, headers).then(resolve).catch(reject);
      }
      if (res.statusCode < 200 || res.statusCode >= 300) {
        return reject(new Error(`HTTP error ${res.statusCode}`));
      }
      let data = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        data += chunk;
      });
      res.on("end", () => {
        resolve(data);
      });
    });
    req.on("error", reject);
  });
}

/**
 * 格式化時間 (若為今天顯示 HH:mm，若非今天顯示 MM/DD HH:mm)
 */
function formatTime(date) {
  const now = new Date();
  const isToday =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  const hours = date.getHours().toString().padStart(2, "0");
  const minutes = date.getMinutes().toString().padStart(2, "0");

  if (isToday) {
    return `${hours}:${minutes}`;
  }
  const month = (date.getMonth() + 1).toString().padStart(2, "0");
  const day = date.getDate().toString().padStart(2, "0");
  return `${month}/${day} ${hours}:${minutes}`;
}

/**
 * 從鉅亨網公開 API 取得最新新聞 (免 Token / 免 Key，穩定快速)
 */
async function fetchViaApi() {
  const text = await fetchUrl(API_URL, {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    Accept: "application/json",
  });

  const json = JSON.parse(text);
  const items = json && json.items && json.items.data ? json.items.data : [];
  return items.map((item) => ({
    title: (item.title || "").trim() || "無標題",
    link: item.newsId ? `https://news.cnyes.com/news/id/${item.newsId}` : "",
    date: item.publishAt ? new Date(item.publishAt * 1000) : null,
  }));
}

/**
 * 從 RSS XML 備援取得新聞 (若官方 RSS 恢復提供或有支援時使用)
 */
async function fetchViaRss() {
  const xml = await fetchUrl(RSS_URL, {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
  });

  const rawItems = [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].slice(0, 10);

  return rawItems.map((item) => {
    const titleMatch =
      item[1].match(/<title><!\[CDATA\[(.*?)\]\]><\/title>/) ||
      item[1].match(/<title>(.*?)<\/title>/);
    const title = titleMatch ? titleMatch[1].trim() : "無標題";

    const linkMatch = item[1].match(/<link>(.*?)<\/link>/);
    const link = linkMatch ? linkMatch[1].trim() : "";

    const dateMatch = item[1].match(/<pubDate>(.*?)<\/pubDate>/);
    const date = dateMatch ? new Date(dateMatch[1]) : null;

    return { title, link, date };
  });
}

async function fetchCnyesNews() {
  try {
    let news = [];
    try {
      news = await fetchViaApi();
    } catch (apiErr) {
      news = await fetchViaRss();
    }

    if (!news || news.length === 0) {
      console.log("今日目前暫無更新新聞。");
      return;
    }

    // 頂部標題列
    console.log(`${CYAN}${BOLD}📈 鉅亨網台股即時新聞${RESET} ${GRAY}(共 ${news.length} 則)${RESET}\n`);

    news.slice(0, 10).forEach((item, idx) => {
      const num = (idx + 1).toString().padStart(2, "0");
      const timeStr = item.date ? formatTime(item.date) : "";

      // 卡片上框線與序號時間標籤
      console.log(`${GRAY}╭─── ${CYAN}${BOLD}#${num}${RESET} ${timeStr ? `${YELLOW}🕒 ${timeStr}${RESET}` : ""} ${GRAY}────────────────────────────────────────${RESET}`);
      // 標題加粗黑色
      console.log(`${GRAY}│${RESET}  ${BLACK}${item.title}${RESET}`);
      // 連結
      if (item.link) {
        console.log(`${GRAY}│${RESET}  🔗 ${item.link}`);
      }
      // 卡片下框線
      console.log(`${GRAY}╰───────────────────────────────────────────────────${RESET}\n`);
    });
  } catch (err) {
    console.error("取得鉅亨網新聞失敗：", err.message);
  }
}

fetchCnyesNews();
