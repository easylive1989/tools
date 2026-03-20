import os
import json
import time
import feedparser
import requests

# 設定檔案路徑
RSS_LIST_FILE = "rss/rss_list.txt"
HISTORY_FILE = "rss/history.json"
MAX_HISTORY_PER_FEED = 50

# 獲取 Discord Webhook URL (從環境變數讀取)
DISCORD_RSS_WEBHOOK_URL = os.environ.get("DISCORD_RSS_WEBHOOK_URL")

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

def send_to_discord(title, link, site_name):
    if not DISCORD_RSS_WEBHOOK_URL:
        print("Error: DISCORD_RSS_WEBHOOK_URL not set.")
        return False
    
    payload = {
        "content": f"**[{site_name}]**\n{title}\n{link}"
    }
    
    try:
        response = requests.post(DISCORD_RSS_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Failed to send to Discord: {e}")
        return False

def main():
    rss_urls = load_rss_list()
    history = load_history()
    
    if not rss_urls:
        print("No RSS URLs found.")
        return

    for url in rss_urls:
        print(f"Processing: {url}")
        feed = feedparser.parse(url)
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
                title = entry.get("title", "No Title")
                link = entry.get("link", "")
                
                print(f"New post: {title}")
                if send_to_discord(title, link, site_name):
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
