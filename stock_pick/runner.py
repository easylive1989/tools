"""Poll the stock-pick Discord channel and log each screenshot's stocks to Notion.

Required environment variables: DISCORD_BOT_TOKEN and NOTION_SECRET. Run this
script on the machine with an authenticated Codex CLI (oracle-arm, every 5 min).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.discord import DiscordClient
from common.notion import NotionApi
from stock_pick.notion_writer import write
from stock_pick.quotes import (
    PASSED, WAITING, MarketQuotes, fetch_quotes, is_trading_day, match, previous_trading_day,
    quote_status,
)
from stock_pick.reader import SUPPORTED_EXTENSIONS, read_names

LOG = logging.getLogger(__name__)
CHANNEL_ID = "1556684804731179070"
STATE_PATH = Path(__file__).resolve().parent / "state.json"
TAIPEI = ZoneInfo("Asia/Taipei")
MARKET_CLOSE = time(13, 30)
MAX_ATTEMPTS = 3
MAX_WAIT = timedelta(hours=12)
REACTION_OK, REACTION_PARTIAL, REACTION_ERROR = "✅", "⚠️", "❌"


@dataclass(frozen=True)
class Outcome:
    emoji: str
    reply: str | None = None


def load_state() -> dict:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    state.setdefault("last_message_id", None)
    state.setdefault("attempts", {})
    return state


def save_state(state: dict) -> None:
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(STATE_PATH)


def posted_at(message: dict) -> datetime:
    return datetime.fromisoformat(message["timestamp"].replace("Z", "+00:00"))


def pick_day(message: dict) -> date:
    """The latest trading day that had closed when the screenshot was posted."""
    local = posted_at(message).astimezone(TAIPEI)
    if local.time() >= MARKET_CLOSE and is_trading_day(local.date()):
        return local.date()
    return previous_trading_day(local.date())


def image_attachments(message: dict) -> list[dict]:
    return [
        attachment for attachment in message.get("attachments", [])
        if (attachment.get("content_type") or "").startswith("image/")
        or Path(attachment.get("filename", "")).suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def is_pick_message(message: dict) -> bool:
    return (
        not (message.get("author") or {}).get("bot")
        and message.get("type", 0) in (0, 19)
        and bool(image_attachments(message))
    )


def download_images(discord: DiscordClient, message: dict, directory: Path) -> list[Path]:
    paths = []
    for index, attachment in enumerate(image_attachments(message)):
        suffix = Path(attachment.get("filename", "")).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支援的圖片格式：{attachment.get('filename')}")
        paths.append(discord.download(attachment["url"], directory / f"screenshot{index}{suffix}"))
    return paths


def log_message(message: dict, day: date, discord: DiscordClient, notion: NotionApi,
                quotes: MarketQuotes, now: datetime) -> Outcome | None:
    """Log one screenshot message; None means the day's quotes are not out yet."""
    status = quote_status(quotes.days, day)
    if status == WAITING:
        if now - posted_at(message) < MAX_WAIT:
            return None
        return Outcome(REACTION_ERROR, f"找不到 {day} 的收盤行情，可能不是交易日")
    if status == PASSED:
        latest = max(value for value in quotes.days.values() if value is not None)
        return Outcome(REACTION_ERROR, f"官方行情已更新到 {latest}，無法取得 {day} 的收盤價")

    with tempfile.TemporaryDirectory(prefix="stock-pick-") as workdir:
        names = read_names(download_images(discord, message, Path(workdir)))
    if not names:
        return Outcome(REACTION_ERROR, "截圖中沒有辨識到股票")
    found, missing = match(names, quotes.by_name)
    for quote in found:
        write(notion, quote, day)
    if missing:
        emoji = REACTION_PARTIAL if found else REACTION_ERROR
        return Outcome(emoji, f"找不到這些股票的 {day} 收盤價：{'、'.join(missing)}")
    return Outcome(REACTION_OK)


def describe(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]


def gave_up(state: dict, message_id: str) -> bool:
    """Count a failure for the message; True once it has failed MAX_ATTEMPTS times in a row."""
    attempts = state["attempts"].get(message_id, 0) + 1
    state["attempts"][message_id] = attempts
    LOG.exception("message %s failed (attempt %d/%d)", message_id, attempts, MAX_ATTEMPTS)
    if attempts < MAX_ATTEMPTS:
        save_state(state)
        return False
    return True


def run_once(now: datetime | None = None) -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN")
    notion_secret = os.environ.get("NOTION_SECRET")
    if not token or not notion_secret:
        raise RuntimeError("DISCORD_BOT_TOKEN and NOTION_SECRET are required")
    discord = DiscordClient(token, user_agent="stock-pick-bot/1.0")
    notion = NotionApi(notion_secret, version="2025-09-03")

    state = load_state()
    if state["last_message_id"] is None:
        # First run: only screenshots posted from now on are logged.
        state["last_message_id"] = discord.latest_message_id(CHANNEL_ID) or "0"
        save_state(state)
        LOG.info("first run: starting after message %s", state["last_message_id"])
        return

    now = now or datetime.now(timezone.utc)
    quotes_by_day: dict[date, MarketQuotes] = {}
    for message in discord.messages_since(CHANNEL_ID, state["last_message_id"]):
        message_id = message["id"]
        if is_pick_message(message):
            try:
                day = pick_day(message)
                if day not in quotes_by_day:
                    quotes_by_day[day] = fetch_quotes(day)
                outcome = log_message(message, day, discord, notion, quotes_by_day[day], now)
            except Exception as exc:
                if not gave_up(state, message_id):
                    return
                outcome = Outcome(REACTION_ERROR, f"處理失敗（已試 {MAX_ATTEMPTS} 次）：{describe(exc)}")
            if outcome is None:
                # Waiting breaks a failure streak: only consecutive failures give up.
                if state["attempts"].pop(message_id, None) is not None:
                    save_state(state)
                LOG.info("message %s: waiting for %s quotes", message_id, day)
                return
            try:
                discord.react(CHANNEL_ID, message_id, outcome.emoji)
                if outcome.reply:
                    discord.reply(CHANNEL_ID, message_id, outcome.reply)
            except Exception:
                # Rows are already in Notion; without Discord there is no one to tell.
                if not gave_up(state, message_id):
                    return
                LOG.error("message %s: Discord feedback failed %d times, skipping", message_id, MAX_ATTEMPTS)
            LOG.info("message %s: %s %s", message_id, outcome.emoji, outcome.reply or "")
        state["attempts"].pop(message_id, None)
        state["last_message_id"] = message_id
        save_state(state)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_once()
    return 0


if __name__ == "__main__":
    sys.exit(main())
