import os
import sys
from typing import Protocol

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.notify import send_to_discord
from scraper import ThreadPost

THREADS_BRAND_COLOR = 0x000000


class Notifier(Protocol):
    def notify(self, keyword: str, post: ThreadPost, translation: str | None = None) -> None: ...


class DiscordNotifier:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def notify(self, keyword: str, post: ThreadPost, translation: str | None = None) -> None:
        content_preview = post.content[:200] + ("…" if len(post.content) > 200 else "")
        embed = {
            "title": f"Threads 新貼文：{keyword}",
            "description": content_preview,
            "url": post.url,
            "author": {"name": f"@{post.author}"},
            "color": THREADS_BRAND_COLOR,
            "footer": {"text": post.url},
        }
        if translation:
            # Discord embed field value 上限 1024 字元
            translation_preview = translation[:1000] + ("…" if len(translation) > 1000 else "")
            embed["fields"] = [{"name": "🌐 中文翻譯", "value": translation_preview}]
        send_to_discord(self.webhook_url, {"embeds": [embed]})
