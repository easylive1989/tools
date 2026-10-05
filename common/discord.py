"""Small Discord REST client shared by the polling bots in this repo."""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

DISCORD_API = "https://discord.com/api/v10"
ATTACHMENT_HOSTS = {"cdn.discordapp.com", "media.discordapp.net", "cdn.discord.com"}
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024


class DiscordClient:
    def __init__(self, token: str, user_agent: str = "tools-bot/1.0"):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bot {token}", "User-Agent": user_agent})

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        for attempt in range(5):
            response = self.session.request(method, f"{DISCORD_API}{path}", timeout=30, **kwargs)
            if response.status_code == 429:
                time.sleep(min(float(response.json().get("retry_after", 1)), 60))
                continue
            if response.status_code >= 500 and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response
        raise RuntimeError("Discord API 持續限流，稍後再試")

    def messages_since(self, channel_id: str, last_id: str) -> list[dict]:
        """Walk backward from the newest message so a busy channel loses none."""
        messages: list[dict] = []
        before = None
        while True:
            params = {"limit": 100}
            if before:
                params["before"] = before
            batch = self.request("GET", f"/channels/{channel_id}/messages", params=params).json()
            if not batch:
                break
            messages.extend(msg for msg in batch if int(msg["id"]) > int(last_id))
            oldest = min(int(msg["id"]) for msg in batch)
            if oldest <= int(last_id) or len(batch) < 100:
                break
            before = str(oldest)
        return sorted(messages, key=lambda msg: int(msg["id"]))

    def latest_message_id(self, channel_id: str) -> str | None:
        messages = self.request("GET", f"/channels/{channel_id}/messages", params={"limit": 1}).json()
        return messages[0]["id"] if messages else None

    def react(self, channel_id: str, message_id: str, emoji: str) -> None:
        self.request(
            "PUT",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}/@me",
        )

    def reply(self, channel_id: str, message_id: str, content: str) -> str:
        response = self.request("POST", f"/channels/{channel_id}/messages", json={
            "content": content,
            "nonce": message_id,
            "enforce_nonce": True,
            "allowed_mentions": {"parse": [], "replied_user": False},
            "message_reference": {
                "message_id": message_id,
                "channel_id": channel_id,
                "fail_if_not_exists": True,
            },
        })
        return response.json()["id"]

    def download(self, url: str, destination: Path) -> Path:
        # Attachment URLs are pre-signed; plain requests keeps the bot token off the CDN.
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ATTACHMENT_HOSTS:
            raise ValueError("Discord 附件網址不正確")
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            size = 0
            with destination.open("wb") as out:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        raise ValueError("Discord 附件超過 20 MiB")
                    out.write(chunk)
        return destination
