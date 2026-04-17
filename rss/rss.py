# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "cloudscraper",
#     "feedparser",
#     "markdownify",
#     "readability-lxml",
#     "requests",
# ]
# ///

import os
import re
import subprocess
import sys
import json
import time
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module='requests')
warnings.filterwarnings("ignore", message=".*doesn't match a supported version.*")

import feedparser
import requests
import cloudscraper
from datetime import datetime, timezone
from markdownify import markdownify as md
from readability import Document

# 設定檔案路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE_DIR))
from notify import send_notification

OBSIDIAN_DIR = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/RSS 訂閱")
RSS_LIST_FILE = os.path.join(OBSIDIAN_DIR, "rss_list.json")
HISTORY_FILE = os.path.join(OBSIDIAN_DIR, "history.json")
MAX_HISTORY_PER_FEED = 50

# 基準日期：第一次 sync 或 last_sync 不存在時的 fallback
FILTER_DATE = datetime(2026, 3, 18, tzinfo=timezone.utc)

def sanitize_filename(name):
    # 去除不能作為檔名的非法字元
    return re.sub(r'[\\/:*?"<>|]', '_', name)

def classify_content_type(entry, link):
    """判斷內容是影片還是文章，回傳 '影片' 或 '文章'。"""
    if "youtube.com/watch" in link or "youtu.be/" in link:
        return "影片"
    # 檢查 RSS enclosures 是否包含影片類型
    enclosures = entry.get("enclosures", [])
    for enc in enclosures:
        mime = enc.get("type", "")
        if mime.startswith("video/"):
            return "影片"
    # 檢查 media:content 標籤
    media_content = entry.get("media_content", [])
    for media in media_content:
        mime = media.get("type", "")
        if mime.startswith("video/"):
            return "影片"
    return "文章"


_TRANSLATE_SYSTEM_PROMPT = (
    "你是翻譯工具。將輸入內容翻譯成繁體中文。\n"
    "規則：\n"
    "- 僅輸出翻譯結果，不加解釋、引號或額外格式。\n"
    "- 保留原文 Markdown 排版（標題、粗體、清單、連結、圖片語法等）。\n"
    "- 若原文已是繁體中文，直接回傳原文即可。\n"
    "- 保持原文段落換行結構不變。\n"
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHFABCDJKsuhl]|\r")


def translate_markdown(text: str) -> str | None:
    """呼叫 Gemini CLI 將 Markdown 文字翻譯成繁體中文，失敗回傳 None。"""
    prompt = f"{_TRANSLATE_SYSTEM_PROMPT}\n---原文---\n{text}"
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
    try:
        result = subprocess.run(
            ["gemini", "-m", "gemini-2.5-flash", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        output = _ANSI_RE.sub("", result.stdout).strip()
        if not output:
            err = _ANSI_RE.sub("", result.stderr).strip()
            print(f"  Translation warning: {err[:200] or 'empty output'}")
            return None
        return output
    except subprocess.TimeoutExpired:
        print("  Translation warning: timeout after 300s")
        return None
    except Exception as e:
        print(f"  Translation warning: {e}")
        return None


def is_new_enough(entry, cutoff_date):
    """判斷文章是否在 cutoff_date 之後發布。"""
    parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed_time:
        try:
            entry_date = datetime(*parsed_time[:6], tzinfo=timezone.utc)
            return entry_date >= cutoff_date
        except Exception:
            pass
    # 若文章完全沒有提供時間資訊，預設放行
    return True


def load_rss_list():
    if not os.path.exists(RSS_LIST_FILE):
        return []
    with open(RSS_LIST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("feeds", [])

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

    # 自動遷移舊格式：{ url: [id_list] } → { url: { "entries": [id_list], "last_sync": null } }
    migrated = {}
    for url, value in data.items():
        if isinstance(value, list):
            migrated[url] = {"entries": value, "last_sync": None}
        else:
            migrated[url] = value
    return migrated

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def main():
    # 確保 Obsidian 資料夾存在
    os.makedirs(OBSIDIAN_DIR, exist_ok=True)
    
    feed_list = load_rss_list()
    history = load_history()

    if not feed_list:
        print("No RSS URLs found.")
        return

    total_new_entries = 0

    for feed_config in feed_list:
        url = feed_config["url"]
        print(f"Processing: {url}")
        try:
            # 使用 cloudscraper 模擬真實瀏覽器，繞過 Substack / Cloudflare 的反爬蟲機制
            scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                }
            )
            response = scraper.get(url, timeout=15)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            continue

        site_name = feed_config.get("name") or feed.feed.get("title", url)
        
        # 確保該 URL 在 history 中有對應的結構
        if url not in history:
            history[url] = {"entries": [], "last_sync": None}

        feed_history = history[url]
        # 決定 cutoff 日期：優先使用 last_sync，否則用全域 FILTER_DATE
        cutoff_date = FILTER_DATE
        if feed_history.get("last_sync"):
            try:
                cutoff_date = datetime.fromisoformat(feed_history["last_sync"])
            except (ValueError, TypeError):
                pass

        new_entries = []
        for entry in feed.entries:
            # 優先順序：Atom 的 id > RSS 的 guid > 直接使用 link
            entry_id = entry.get("id", entry.get("guid", entry.get("link")))
            
            if entry_id not in feed_history["entries"]:
                # 這是新文章！
                if not is_new_enough(entry, cutoff_date):
                    continue

                title = entry.get("title", "No Title")
                link = entry.get("link", "")
                content_type = classify_content_type(entry, link)

                print(f"New post [{content_type}]: {title}")
                
                # 一律從原網頁重新抓取文章內文
                html_content = ""
                try:
                    print(f"Fetching original page for full content: {link}")
                    article_res = scraper.get(link, timeout=15)
                    article_res.raise_for_status()

                    # 處理 requests 預設將沒有 charset 的網頁解析為 ISO-8859-1 導致的亂碼問題
                    if article_res.encoding and article_res.encoding.lower() == 'iso-8859-1':
                        article_res.encoding = article_res.apparent_encoding or 'utf-8'

                    doc = Document(article_res.text)
                    html_content = doc.summary()
                    if not html_content or len(html_content) < 50:
                        raise ValueError("Extracted content too short")
                except Exception as e:
                    print(f"Fetch from web failed ({e}), fallback to RSS content.")
                    if "content" in entry:
                        html_content = entry.content[0].value
                    elif "summary" in entry:
                        html_content = entry.summary
                    else:
                        html_content = entry.get("description", "")
                
                # 轉換為 Markdown
                md_text = md(html_content, heading_style="ATX", escape_asterisks=False)
                pub_date = entry.get("published", entry.get("updated", ""))

                # 自動翻譯（在 YouTube iframe 之前執行，只翻譯內文本身）
                if feed_config.get("auto_translate") and md_text.strip():
                    print("  Translating...")
                    translated = translate_markdown(md_text)
                    if translated:
                        md_text = f"{md_text}\n\n---\n\n## 翻譯（繁體中文）\n\n{translated}"

                # 如果是 YouTube 的文章，補上 iframe
                if "youtube.com/watch" in link or "youtu.be/" in link:
                    from urllib.parse import urlparse, parse_qs
                    parsed_link = urlparse(link)
                    video_id = ""
                    if "youtube.com" in link:
                        qs = parse_qs(parsed_link.query)
                        if "v" in qs:
                            video_id = qs["v"][0]
                    elif "youtu.be" in link:
                        video_id = parsed_link.path.strip("/")
                        
                    if video_id:
                        iframe = f'<iframe width="560" height="315" src="https://www.youtube.com/embed/{video_id}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>\n\n'
                        md_text = iframe + md_text
                
                # 準備存檔至 Obsidian
                safe_title = sanitize_filename(title)
                safe_site = sanitize_filename(site_name)
                # 使用 [主站名] [文章/影片] 標題 當作檔名
                filename = f"[{safe_site}] [{content_type}] {safe_title}.md"
                filepath = os.path.join(OBSIDIAN_DIR, filename)
                labeled_title = f"[{content_type}] {title}"

                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write("---\n")
                        f.write(f"title: \"{labeled_title}\"\n")
                        f.write(f"source: \"{site_name}\"\n")
                        f.write(f"link: \"{link}\"\n")
                        f.write(f"date: \"{pub_date}\"\n")
                        f.write("---\n\n")
                        f.write(f"# {labeled_title}\n\n")
                        f.write(md_text)
                except Exception as e:
                    print(f"Error writing markdown {filepath}: {e}")
                
                new_entries.append(entry_id)
                total_new_entries += 1
                # 避免頻率限制
                time.sleep(2)
        
        # 更新歷史紀錄並清理
        if new_entries:
            # 將新紀錄加到最前面
            feed_history["entries"] = new_entries + feed_history["entries"]
            # 只保留最新的 MAX_HISTORY_PER_FEED 筆
            feed_history["entries"] = feed_history["entries"][:MAX_HISTORY_PER_FEED]

        # 每次 sync 都更新 last_sync 時間
        feed_history["last_sync"] = datetime.now(timezone.utc).isoformat()
            
    save_history(history)
    print("Done.")
    send_notification(
        f"共抓取 {total_new_entries} 篇新文章／影片",
        title="RSS 同步完成",
    )

if __name__ == "__main__":
    main()
