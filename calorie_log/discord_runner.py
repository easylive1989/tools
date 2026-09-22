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
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.notion import NotionApi
from calorie_log.estimator import estimate
from calorie_log.meal_time import TAIPEI, choose_meal_time, meal_type_at, parse_discord_time
from calorie_log.notion_writer import write
from calorie_log.nutrition_advisor import advise, recent_meals
from calorie_log.weekly_advice import send_weekly_advice


LOG = logging.getLogger(__name__)
DISCORD_API = "https://discord.com/api/v10"
STATE_PATH = Path(__file__).resolve().parent / "state.json"
DEFAULT_DATA_SOURCE_ID = "76b1e061-2f4f-4bee-a8b2-3c361dc6a1dd"
DEFAULT_CHANNEL_ID = "1548580916765401088"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
ADVICE_PREFIXES = ("建議：", "建議:")
MEAL_PREFIXES = ("記錄：", "記錄:")
PLANNED_FOOD = re.compile(
    r"想(?:要)?(?:吃|喝|點)|打算(?:吃|喝|點)|考慮(?:吃|喝|點)|"
    r"準備(?:吃|喝|點)|預計(?:吃|喝|點)|可能會(?:吃|喝|點)|"
    r"(?:可以|能|該|要不要|適合)(?:吃|喝|點)|(?:吃|喝|點)什麼"
)
ADVICE_QUERY = re.compile(
    r"(?:請|幫我|給我|有沒有).{0,10}(?:建議|推薦|分析)|"
    r"(?:最近|這週|今天).{0,12}(?:飲食|吃得).{0,10}(?:如何|怎麼樣|怎樣)|"
    r"(?:怎麼|如何)(?:吃|搭配|選|點)"
)
PAST_DECISION = re.compile(
    r"(?:本來|原本|一開始).{0,30}(?:想|打算|考慮|準備)(?:吃|喝|點).{0,30}"
    r"(?:最後|結果|後來).{0,12}(?:吃了|喝了|點了)"
)


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

    def react(self, channel_id: str, message_id: str, emoji: str) -> None:
        self.request(
            "PUT",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}/@me",
        )

    def send_message(self, channel_or_thread_id: str, content: str) -> dict:
        return self.request(
            "POST",
            f"/channels/{channel_or_thread_id}/messages",
            json={"content": content},
        ).json()

    def get_or_create_thread(self, channel_id: str, message_id: str, name: str) -> str:
        trimmed_name = (name.strip() or "熱量估算")[:100]
        try:
            response = self.request(
                "POST",
                f"/channels/{channel_id}/messages/{message_id}/threads",
                json={"name": trimmed_name},
            )
            return response.json().get("id", message_id)
        except requests.HTTPError as exc:
            if exc.response is not None:
                if exc.response.status_code == 409:
                    return message_id
                if exc.response.status_code == 400:
                    try:
                        err_data = exc.response.json()
                    except Exception:
                        err_data = {}
                    if err_data.get("code") == 160004:
                        return message_id
            raise

    def send_weekly_report(self, channel_id: str, content: str, key: str, after_id: str) -> str:
        # Nonces only deduplicate recent requests. Also recover a delivered
        # outbox message after a restart, even days after the original send.
        bot_id = self.request("GET", "/users/@me").json()["id"]
        marker = f"\n\n週報編號：{key}"
        for message in self.messages_since(channel_id, after_id):
            if ((message.get("author") or {}).get("id") == bot_id
                    and (message.get("content") or "").endswith(marker)):
                return message["id"]
        response = self.request("POST", f"/channels/{channel_id}/messages", json={
            "content": content, "nonce": key, "enforce_nonce": True,
            "allowed_mentions": {"parse": []},
        })
        return response.json()["id"]

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


def is_advice_request(message: dict) -> bool:
    if (message.get("author") or {}).get("bot") or message.get("type", 0) not in (0, 19):
        return False
    content = (message.get("content") or "").strip()
    if content.startswith(MEAL_PREFIXES):
        return False
    if content.startswith(ADVICE_PREFIXES):
        return True
    if "?" in content or "？" in content or ADVICE_QUERY.search(content):
        return True
    return bool(PLANNED_FOOD.search(content) and not PAST_DECISION.search(content))


def advice_question(message: dict) -> str:
    content = (message.get("content") or "").strip()
    for prefix in ADVICE_PREFIXES:
        if content.startswith(prefix):
            return content[len(prefix):].strip()
    return content


def is_meal_message(message: dict) -> bool:
    return (
        not (message.get("author") or {}).get("bot")
        and message.get("type", 0) in (0, 19)
        and not is_advice_request(message)
        and bool(first_image(message) or (message.get("content") or "").strip())
    )

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
        and not is_advice_request(message)
        and (message.get("content") or "").strip()
    ]


def answer_advice_message(
    discord: DiscordClient, notion: NotionApi, channel_id: str,
    data_source_id: str, state: dict, message: dict, *,
    advance_cursor: bool = True, context_message: dict | None = None,
) -> bool:
    message_id = message["id"]
    try:
        days = int(os.environ.get("NUTRITION_LOOKBACK_DAYS", "7"))
        history = recent_meals(notion, data_source_id, days=days)
        attachment = first_image(message) or (first_image(context_message) if context_message else None)
        question = advice_question(message)
        if context_message:
            context = (context_message.get("content") or "").strip()
            question = f"此問題位於一則餐點的討論串。原餐點說明：{context or '未提供'}\n目前問題：{question}"
        with tempfile.TemporaryDirectory(prefix="discord-food-advice-") as temp:
            directory = Path(temp)
            photo = download_image(attachment, directory) if attachment else None
            images = [codex_image(photo, directory)] if photo else []
            reply = advise(
                images, question, history, lookback_days=days,
                profile=os.environ.get("NUTRITION_PROFILE", ""),
            )
        reply_id = discord.reply(channel_id, message_id, reply)
        state.setdefault("advice_replies", {})[message_id] = reply_id
        if advance_cursor:
            state["last_message_id"] = message_id
        save_state(state)
        LOG.info("Answered nutrition question %s with %s", message_id, reply_id)
    except Exception:
        LOG.exception("Failed to answer nutrition question %s", message_id)
        return False
    return True


def combined_description(parent: dict, supplements: list[dict]) -> str:
    pieces = [f"原始說明：{(parent.get('content') or '').strip() or '未提供'}"]
    for supplement in supplements:
        pieces.append(f"補充：{supplement['content'].strip()}")
    return "\n".join(pieces)


def format_calorie_reply(estimate: Estimate) -> str:
    meal_name = estimate.meal_name.strip() or "餐點"
    kcal = estimate.total_kcal
    kcal_str = str(int(kcal)) if kcal.is_integer() else f"{kcal:.1f}"
    return f"【{meal_name}】預估總熱量：{kcal_str} kcal"


def update_active_threads(
    discord: DiscordClient, notion: NotionApi, channel_id: str,
    data_source_id: str, state: dict,
) -> None:
    tracked = state.setdefault("threads", {})
    for thread in discord.active_public_threads(channel_id):
        parent_id = thread["id"]  # A public thread shares its starter message ID.
        if parent_id not in tracked:
            continue
        all_messages = discord.messages_since(parent_id, None)
        messages = supplementary_messages(all_messages)
        parent = None
        if messages and int(messages[-1]["id"]) > int(tracked[parent_id]):
            latest_id = messages[-1]["id"]
            try:
                parent = discord.get_message(channel_id, parent_id)
                attachment = first_image(parent)
                with tempfile.TemporaryDirectory(prefix="discord-meal-thread-") as temp:
                    directory = Path(temp)
                    photo = download_image(attachment, directory) if attachment else None
                    model_images = [codex_image(photo, directory)] if photo else []
                    description = combined_description(parent, messages)
                    result = estimate(model_images, description)
                    message_time = parse_discord_time(parent["timestamp"])
                    eaten_at = (
                        choose_meal_time(photo, message_time) if photo
                        else message_time.astimezone(TAIPEI)
                    )
                    write(
                        result, description, [], notion, data_source_id, eaten_at,
                        meal_type_at(eaten_at), include_photos=False,
                        source_message_id=parent_id, update_existing=True,
                    )
                discord.send_message(parent_id, format_calorie_reply(result))
                discord.react(parent_id, latest_id, "✅")
                tracked[parent_id] = latest_id
                save_state(state)
                LOG.info("Updated meal from thread %s through %s", parent_id, latest_id)
            except Exception:
                LOG.exception("Failed to update meal from thread %s", parent_id)
                continue
        for question in all_messages:
            if not is_advice_request(question) or question["id"] in state.get("advice_replies", {}):
                continue
            if parent is None:
                parent = discord.get_message(channel_id, parent_id)
            answer_advice_message(
                discord, notion, parent_id, data_source_id, state, question,
                advance_cursor=False, context_message=parent,
            )


def record_meal_message(
    discord: DiscordClient, notion: NotionApi, channel_id: str,
    data_source_id: str, state: dict, message: dict, *, advance_cursor: bool,
) -> bool:
    message_id = message["id"]
    attachment = first_image(message)
    description = (message.get("content") or "").strip()
    try:
        with tempfile.TemporaryDirectory(prefix="discord-meal-") as temp:
            directory = Path(temp)
            photo = download_image(attachment, directory) if attachment else None
            model_images = [codex_image(photo, directory)] if photo else []
            result = estimate(model_images, description)
            message_time = parse_discord_time(message["timestamp"])
            eaten_at = (
                choose_meal_time(photo, message_time) if photo
                else message_time.astimezone(TAIPEI)
            )
            write(
                result, description, [photo] if photo else [], notion,
                data_source_id, eaten_at, meal_type_at(eaten_at),
                include_photos=bool(photo), source_message_id=message_id,
            )
        thread_id = discord.get_or_create_thread(channel_id, message_id, result.meal_name)
        discord.send_message(thread_id, format_calorie_reply(result))
        discord.react(channel_id, message_id, "✅")
        if advance_cursor:
            state["last_message_id"] = message_id
        state.setdefault("threads", {})[message_id] = "0"
        save_state(state)
        LOG.info("Recorded Discord message %s", message_id)
    except Exception:
        LOG.exception("Failed to process Discord message %s", message_id)
        return False
    return True


def backfill_recent_text(
    discord: DiscordClient, notion: NotionApi, channel_id: str,
    data_source_id: str, state: dict, last_id: str,
) -> bool:
    """Recover recent text meals skipped by the old photo-only version once."""
    if state.get("text_only_backfill_v1"):
        return True
    recent = discord.request(
        "GET", f"/channels/{channel_id}/messages", params={"limit": 100},
    ).json()
    cutoff = datetime.now(timezone.utc) - timedelta(days=2)
    for message in sorted(recent, key=lambda item: int(item["id"])):
        if int(message["id"]) > int(last_id):
            continue
        if not is_meal_message(message) or first_image(message):
            continue
        if parse_discord_time(message["timestamp"]) < cutoff:
            continue
        if not record_meal_message(
            discord, notion, channel_id, data_source_id, state, message,
            advance_cursor=False,
        ):
            return False
    state["text_only_backfill_v1"] = True
    save_state(state)
    return True


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
        send_weekly_advice(discord, notion, channel_id, data_source_id, state, save_state)
        return
    if last_id is not None and not backfill_recent_text(
        discord, notion, channel_id, data_source_id, state, last_id,
    ):
        raise RuntimeError("補登先前略過的文字餐點失敗")
    messages = discord.messages_since(channel_id, last_id)

    for message in messages:
        message_id = message["id"]
        if is_advice_request(message):
            if not answer_advice_message(
                discord, notion, channel_id, data_source_id, state, message,
            ):
                raise RuntimeError(f"處理 Discord 飲食問題 {message_id} 失敗")
            continue
        if not is_meal_message(message):
            state["last_message_id"] = message_id
            save_state(state)
            continue
        if not record_meal_message(
            discord, notion, channel_id, data_source_id, state, message,
            advance_cursor=True,
        ):
            raise RuntimeError(f"處理 Discord 餐點訊息 {message_id} 失敗")
    if backfill and not state.get("text_only_backfill_v1"):
        state["text_only_backfill_v1"] = True
        save_state(state)
    update_active_threads(discord, notion, channel_id, data_source_id, state)
    send_weekly_advice(discord, notion, channel_id, data_source_id, state, save_state)


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
