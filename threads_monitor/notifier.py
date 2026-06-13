import os
import sys
from typing import Protocol

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.notify import send_to_discord
from scraper import ThreadPost

THREADS_BRAND_COLOR = 0x000000


class Notifier(Protocol):
    def notify(self, keyword: str, post: ThreadPost) -> None: ...


class DiscordNotifier:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def notify(self, keyword: str, post: ThreadPost) -> None:
        content_preview = post.content[:200] + ("…" if len(post.content) > 200 else "")
        payload = {
            "embeds": [
                {
                    "title": f"Threads 新貼文：{keyword}",
                    "description": content_preview,
                    "url": post.url,
                    "author": {"name": f"@{post.author}"},
                    "color": THREADS_BRAND_COLOR,
                    "footer": {"text": post.url},
                }
            ]
        }
        send_to_discord(self.webhook_url, payload)
