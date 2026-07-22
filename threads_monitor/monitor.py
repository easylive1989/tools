import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.gemini import GeminiClient
from common.notion import NotionApi
from notifier import DiscordNotifier
from scraper import ThreadPost, search_threads
from translator import Translator, is_chinese

KEYWORDS_DB_ID = "37e8303f78f7807196e8dfa2bfdeb96e"
SEEN_POSTS_DB_ID = "37e8303f78f780d79770e6cd32c881f4"


def fetch_active_keywords(notion: NotionApi) -> list[tuple[str, str]]:
    resp = notion.query_database(KEYWORDS_DB_ID, {
        "filter": {
            "property": "Active",
            "checkbox": {"equals": True}
        }
    })
    resp.raise_for_status()
    results = []
    for page in resp.json()["results"]:
        props = page["properties"]
        title_parts = props.get("Keyword", {}).get("title", [])
        keyword = title_parts[0]["plain_text"] if title_parts else None
        webhook_url = props.get("Discord Webhook URL", {}).get("url")
        if keyword and webhook_url:
            results.append((keyword, webhook_url))
    return results


def fetch_seen_post_ids(notion: NotionApi) -> set[str]:
    seen: set[str] = set()
    cursor = None
    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = notion.query_database(SEEN_POSTS_DB_ID, body)
        resp.raise_for_status()
        data = resp.json()
        for page in data["results"]:
            title_parts = page["properties"].get("Post ID", {}).get("title", [])
            if title_parts:
                seen.add(title_parts[0]["plain_text"])
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return seen


def record_seen_post(notion: NotionApi, keyword: str, post: ThreadPost) -> None:
    props = {
        "Post ID": {"title": [{"text": {"content": post.post_id}}]},
        "Keyword": {"rich_text": [{"text": {"content": keyword}}]},
        "Author": {"rich_text": [{"text": {"content": post.author}}]},
        "Content": {"rich_text": [{"text": {"content": post.content[:2000]}}]},
        "URL": {"url": post.url},
        "Notified At": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
    }
    resp = notion.create_page(SEEN_POSTS_DB_ID, props)
    resp.raise_for_status()


def build_translator() -> Translator | None:
    if not os.environ.get("GOOGLE_API_KEY"):
        print("Warning: GOOGLE_API_KEY not set, translation disabled.", file=sys.stderr)
        return None
    return Translator(GeminiClient(model_name="flash"))


def translate_if_needed(translator: Translator | None, post: ThreadPost) -> str | None:
    if translator is None or not post.content or is_chinese(post.content):
        return None
    try:
        return translator.translate_to_chinese(post.content)
    except Exception as e:
        print(f"  Translate error for {post.post_id}: {e}", file=sys.stderr)
        return None


def main() -> None:
    hour = datetime.now(ZoneInfo("Asia/Taipei")).hour
    if 0 <= hour < 10:
        print(f"Quiet hours (TW 00:00–10:00), skipping. Current hour: {hour:02d}:xx")
        return

    notion_secret = os.environ.get("NOTION_SECRET")
    if not notion_secret:
        print("Error: NOTION_SECRET not set", file=sys.stderr)
        sys.exit(1)

    notion = NotionApi(notion_secret)

    keywords = fetch_active_keywords(notion)
    if not keywords:
        print("No active keywords found.")
        return
    print(f"Found {len(keywords)} active keyword(s).")

    seen_ids = fetch_seen_post_ids(notion)
    print(f"Loaded {len(seen_ids)} seen post IDs from Notion.")

    translator = build_translator()

    for keyword, webhook_url in keywords:
        print(f"Searching: {keyword}")
        try:
            posts = search_threads(keyword)
        except Exception as e:
            print(f"  Scrape error: {e}", file=sys.stderr)
            continue

        notifier = DiscordNotifier(webhook_url)
        new_count = 0
        for post in posts:
            if post.post_id in seen_ids:
                continue
            translation = translate_if_needed(translator, post)
            try:
                notifier.notify(keyword, post, translation)
                record_seen_post(notion, keyword, post)
                seen_ids.add(post.post_id)
                new_count += 1
            except Exception as e:
                print(f"  Notify/record error for {post.post_id}: {e}", file=sys.stderr)

        print(f"  → {new_count} new post(s) notified.")


if __name__ == "__main__":
    main()
