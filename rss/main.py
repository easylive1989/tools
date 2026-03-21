import os
import json
import re
import time
import feedparser
import requests
import cloudscraper
from datetime import datetime, timezone
from markdownify import markdownify as md
from readability import Document

# 設定檔案路徑
RSS_LIST_FILE = "rss/rss_list.txt"
HISTORY_FILE = "rss/history.json"
MAX_HISTORY_PER_FEED = 50
OBSIDIAN_DIR = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/RSS 訂閱")

# 基準日期：只抓取此日期(包含)之後的文章
FILTER_DATE = datetime(2026, 3, 18, tzinfo=timezone.utc)

def sanitize_filename(name):
    # 去除不能作為檔名的非法字元
    return re.sub(r'[\\/:*?"<>|]', '_', name)

def is_new_enough(entry):
    parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed_time:
        try:
            entry_date = datetime(*parsed_time[:6], tzinfo=timezone.utc)
            return entry_date >= FILTER_DATE
        except Exception:
            pass
    # 若文章完全沒有提供時間資訊，預設放行
    return True


def load_rss_list():
    if not os.path.exists(RSS_LIST_FILE):
        return []
    with open(RSS_LIST_FILE, "r", encoding="utf-8") as f:
        # 過濾掉註解與空行
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def main():
    # 確保 Obsidian 資料夾存在
    os.makedirs(OBSIDIAN_DIR, exist_ok=True)
    
    rss_urls = load_rss_list()
    history = load_history()
    
    if not rss_urls:
        print("No RSS URLs found.")
        return

    for url in rss_urls:
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

        site_name = feed.feed.get("title", url)
        
        # 確保該 URL 在 history 中有對應的 list
        if url not in history:
            history[url] = []
            
        new_entries = []
        for entry in feed.entries:
            # 優先順序：Atom 的 id > RSS 的 guid > 直接使用 link
            entry_id = entry.get("id", entry.get("guid", entry.get("link")))
            
            if entry_id not in history[url]:
                # 這是新文章！
                if not is_new_enough(entry):
                    continue

                title = entry.get("title", "No Title")
                link = entry.get("link", "")
                
                print(f"New post: {title}")
                
                # 取得文章內文
                html_content = ""
                if "content" in entry:
                    html_content = entry.content[0].value
                else:
                    try:
                        print(f"Fetching original page for full content: {link}")
                        article_res = scraper.get(link, timeout=15)
                        article_res.raise_for_status()
                        doc = Document(article_res.text)
                        html_content = doc.summary()
                        if not html_content or len(html_content) < 50:
                            raise ValueError("Extracted content too short")
                    except Exception as e:
                        print(f"Fallback fetch failed ({e}), using summary instead.")
                        if "summary" in entry:
                            html_content = entry.summary
                        else:
                            html_content = entry.get("description", "")
                
                # 轉換為 Markdown
                md_text = md(html_content, heading_style="ATX", escape_asterisks=False)
                pub_date = entry.get("published", entry.get("updated", ""))
                
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
                # 使用 [主站名] 文章標題 當作檔名
                filename = f"[{safe_site}] {safe_title}.md"
                filepath = os.path.join(OBSIDIAN_DIR, filename)
                
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write("---\n")
                        f.write(f"title: \"{title}\"\n")
                        f.write(f"source: \"{site_name}\"\n")
                        f.write(f"link: \"{link}\"\n")
                        f.write(f"date: \"{pub_date}\"\n")
                        f.write("---\n\n")
                        f.write(f"# {title}\n\n")
                        f.write(md_text)
                except Exception as e:
                    print(f"Error writing markdown {filepath}: {e}")
                
                new_entries.append(entry_id)
                # 避免頻率限制
                time.sleep(2)
        
        # 更新歷史紀錄並清理
        if new_entries:
            # 將新紀錄加到最前面
            history[url] = new_entries + history[url]
            # 只保留最新的 MAX_HISTORY_PER_FEED 筆
            history[url] = history[url][:MAX_HISTORY_PER_FEED]
            
    save_history(history)
    print("Done.")

if __name__ == "__main__":
    main()
