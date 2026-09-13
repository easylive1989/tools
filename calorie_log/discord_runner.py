"""Poll a Discord meal channel, estimate calories locally, and save to Notion.

Required environment variables: DISCORD_BOT_TOKEN and NOTION_SECRET. Run this
script on the machine with an authenticated Codex CLI.
"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.notion import NotionApi
from calorie_log.estimator import estimate
from calorie_log.meal_time import choose_meal_time, meal_type_at, parse_discord_time
from calorie_log.notion_writer import write


LOG = logging.getLogger(__name__)
DISCORD_API = "https://discord.com/api/v10"
STATE_PATH = Path(__file__).resolve().parent / "state.json"
DEFAULT_DATA_SOURCE_ID = "76b1e061-2f4f-4bee-a8b2-3c361dc6a1dd"
DEFAULT_CHANNEL_ID = "1548580916765401088"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


class DiscordClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bot {token}",
            "User-Agent": "calorie-log-bot/1.0",
        })

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        for attempt in range(5):
            response = self.session.request(
                method, f"{DISCORD_API}{path}", timeout=30, **kwargs,
            )
            if response.status_code == 429:
                time.sleep(min(float(response.json().get("retry_after", 1)), 60))
                continue
            if response.status_code >= 500 and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response
        raise RuntimeError("Discord API 持續限流，稍後再試")

    def messages_since(self, channel_id: str, last_id: str | None) -> list[dict]:
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
            messages.extend(msg for msg in batch if last_id is None or int(msg["id"]) > int(last_id))
            oldest = min(int(msg["id"]) for msg in batch)
            if (last_id is not None and oldest <= int(last_id)) or len(batch) < 100:
                break
            before = str(oldest)
        return sorted(messages, key=lambda msg: int(msg["id"]))

    def latest_message_id(self, channel_id: str) -> str | None:
        messages = self.request("GET", f"/channels/{channel_id}/messages", params={"limit": 1}).json()
        return messages[0]["id"] if messages else None

    def get_message(self, channel_id: str, message_id: str) -> dict:
        return self.request("GET", f"/channels/{channel_id}/messages/{message_id}").json()

    def active_public_threads(self, channel_id: str) -> list[dict]:
        channel = self.request("GET", f"/channels/{channel_id}").json()
        guild_id = channel["guild_id"]
        payload = self.request("GET", f"/guilds/{guild_id}/threads/active").json()
        return [
            thread for thread in payload.get("threads", [])
            if thread.get("parent_id") == channel_id and thread.get("type") == 11
        ]

def first_image(message: dict) -> dict | None:
    for attachment in message.get("attachments", []):
        suffix = Path(attachment.get("filename", "")).suffix.lower()
        if (attachment.get("content_type") or "").startswith("image/") or suffix in IMAGE_EXTENSIONS:
            return attachment
    return None


def download_image(attachment: dict, destination: Path) -> Path:
    url = attachment["url"]
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "cdn.discordapp.com", "media.discordapp.net", "cdn.discord.com"
    }:
        raise ValueError("Discord 圖片網址不正確")
    suffix = Path(attachment.get("filename", "")).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        suffix = mimetypes.guess_extension(attachment.get("content_type", "")) or ".jpg"
    if suffix not in IMAGE_EXTENSIONS:
        raise ValueError("不支援的 Discord 圖片格式")
    path = destination / f"meal{suffix}"
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with path.open("wb") as out:
            size = 0
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                size += len(chunk)
                if size > 20 * 1024 * 1024:
                    raise ValueError("圖片超過 20 MiB，無法上傳 Notion")
                out.write(chunk)
    return path


def codex_image(path: Path, destination: Path) -> Path:
    if path.suffix.lower() != ".heic":
        return path
    from pillow_heif import register_heif_opener

    register_heif_opener()
    jpeg = destination / "meal.jpg"
    with Image.open(path) as photo:
        photo.convert("RGB").save(jpeg, format="JPEG", quality=90)
    return jpeg


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"last_message_id": None}


def save_state(state: dict) -> None:
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE_PATH)


def supplementary_messages(messages: list[dict]) -> list[dict]:
    return [
        message for message in messages
        if not (message.get("author") or {}).get("bot")
        and message.get("type", 0) in (0, 19)
        and (message.get("content") or "").strip()
    ]


def combined_description(parent: dict, supplements: list[dict]) -> str:
    pieces = [f"原始說明：{(parent.get('content') or '').strip() or '未提供'}"]
    for supplement in supplements:
        pieces.append(f"補充：{supplement['content'].strip()}")
    return "\n".join(pieces)


def update_active_threads(
    discord: DiscordClient, notion: NotionApi, channel_id: str,
    data_source_id: str, state: dict,
) -> None:
    tracked = state.setdefault("threads", {})
    for thread in discord.active_public_threads(channel_id):
        parent_id = thread["id"]  # A public thread shares its starter message ID.
        if parent_id not in tracked:
            continue
        messages = supplementary_messages(discord.messages_since(parent_id, None))
        if not messages:
            continue
        latest_id = messages[-1]["id"]
        if int(latest_id) <= int(tracked[parent_id]):
            continue
        try:
            parent = discord.get_message(channel_id, parent_id)
            attachment = first_image(parent)
            if not attachment:
                raise ValueError("原始餐點訊息沒有照片")
            with tempfile.TemporaryDirectory(prefix="discord-meal-thread-") as temp:
                directory = Path(temp)
                photo = download_image(attachment, directory)
                model_photo = codex_image(photo, directory)
                description = combined_description(parent, messages)
                result = estimate([model_photo], description)
                eaten_at = choose_meal_time(photo, parse_discord_time(parent["timestamp"]))
                write(
                    result, description, [], notion, data_source_id, eaten_at,
                    meal_type_at(eaten_at), include_photos=False,
                    source_message_id=parent_id, update_existing=True,
                )
            tracked[parent_id] = latest_id
            save_state(state)
            LOG.info("Updated meal from thread %s through %s", parent_id, latest_id)
        except Exception:
            LOG.exception("Failed to update meal from thread %s", parent_id)
            continue


def run_once(*, backfill: bool = False) -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN")
    channel_id = os.environ.get("DISCORD_CALORIE_CHANNEL_ID", DEFAULT_CHANNEL_ID)
    notion_secret = os.environ.get("NOTION_SECRET")
    if not token or not notion_secret:
        raise RuntimeError("需要 DISCORD_BOT_TOKEN、NOTION_SECRET")

    discord = DiscordClient(token)
    notion = NotionApi(notion_secret, version="2025-09-03")
    data_source_id = os.environ.get("NOTION_CALORIE_DATA_SOURCE_ID", DEFAULT_DATA_SOURCE_ID)
    state = load_state()
    last_id = state.get("last_message_id")
    if last_id is None and not backfill:
        latest_id = discord.latest_message_id(channel_id)
        state["last_message_id"] = latest_id or "0"
        save_state(state)
        LOG.info("Initial cursor set; future messages will be processed")
        return
    messages = discord.messages_since(channel_id, last_id)

    for message in messages:
        message_id = message["id"]
        if (message.get("author") or {}).get("bot"):
            state["last_message_id"] = message_id
            save_state(state)
            continue
        attachment = first_image(message)
        if not attachment:
            state["last_message_id"] = message_id
            save_state(state)
            continue
        try:
            with tempfile.TemporaryDirectory(prefix="discord-meal-") as temp:
                directory = Path(temp)
                photo = download_image(attachment, directory)
                model_photo = codex_image(photo, directory)
                description = (message.get("content") or "").strip()
                result = estimate([model_photo], description)
                eaten_at = choose_meal_time(photo, parse_discord_time(message["timestamp"]))
                write(
                    result, description, [photo], notion, data_source_id, eaten_at,
                    meal_type_at(eaten_at), source_message_id=message_id,
                )
            state["last_message_id"] = message_id
            state.setdefault("threads", {})[message_id] = "0"
            save_state(state)
            LOG.info("Recorded Discord message %s", message_id)
        except Exception:
            LOG.exception("Failed to process Discord message %s", message_id)
            return  # Keep the cursor here so a later run can retry.
    update_active_threads(discord, notion, channel_id, data_source_id, state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backfill", action="store_true", help="首次執行時補登頻道既有訊息")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        run_once(backfill=args.backfill)
    except Exception:
        LOG.exception("Calorie log run failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
