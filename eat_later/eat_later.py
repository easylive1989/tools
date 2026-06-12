"""Poll a Discord channel for restaurant tips and save them to Notion.

Runs periodically (GitHub Actions). State (eat_later/state.json) tracks the last
processed message id, so each message is handled at most once and only new
messages are fetched on subsequent runs.

For every new message: extract restaurant info via Gemini (+ page scraping),
write it to Notion, and react ✅ (full) / 🔖 (partial) / ❌ (error).

Required env vars:
    DISCORD_BOT_TOKEN
    NOTION_SECRET
    GOOGLE_API_KEY        used by common.gemini for the extraction step
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, ".."))
sys.path.insert(0, _here)

from common.gemini import GeminiClient
from common.notion import NotionApi
from extractor import extract
from notion_writer import write

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "state.json"

DISCORD_API = "https://discord.com/api/v10"
CHANNEL_ID = "1498113717286600847"

REACTION_OK = "✅"
REACTION_PARTIAL = "🔖"
REACTION_ERROR = "❌"


def load_state() -> dict:
    if STATE_PATH.exists():
        with STATE_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {"last_message_id": None}


def save_state(state: dict) -> None:
    with STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def discord_get(path: str, token: str, params: dict | None = None) -> list:
    headers = {"Authorization": f"Bot {token}", "User-Agent": "eat-later-bot/1.0"}
    for attempt in range(5):
        resp = requests.get(f"{DISCORD_API}{path}", headers=headers, params=params, timeout=30)
        if resp.status_code == 429:
            retry_after = float(resp.json().get("retry_after", 1))
            log.info("rate limited, sleeping %ss", retry_after)
            time.sleep(retry_after)
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Discord API failed for {path}")


def discord_react(token: str, channel_id: str, message_id: str, emoji: str) -> bool:
    headers = {"Authorization": f"Bot {token}", "User-Agent": "eat-later-bot/1.0"}
    encoded = quote(emoji, safe="")
    url = f"{DISCORD_API}/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me"
    for attempt in range(3):
        try:
            resp = requests.put(url, headers=headers, timeout=30)
        except requests.RequestException as e:
            log.warning("reaction error for %s: %s", message_id, type(e).__name__)
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in (200, 204):
            return True
        if resp.status_code == 429:
            retry_after = float(resp.json().get("retry_after", 1))
            log.info("reaction rate limited, sleeping %ss", retry_after)
            time.sleep(retry_after)
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        log.warning("reaction failed for %s: HTTP %s", message_id, resp.status_code)
        return False
    log.warning("reaction gave up for %s", message_id)
    return False


def fetch_messages(token: str, channel_id: str, after_id: str | None) -> list[dict]:
    """Return all messages newer than after_id (or whole history if None), oldest first."""
    collected: list[dict] = []
    if after_id:
        cursor = after_id
        while True:
            batch = discord_get(
                f"/channels/{channel_id}/messages",
                token,
                params={"limit": 100, "after": cursor},
            )
            if not batch:
                break
            # `after` returns newest first; reverse to chronological.
            batch_sorted = sorted(batch, key=lambda m: int(m["id"]))
            collected.extend(batch_sorted)
            cursor = batch_sorted[-1]["id"]
            if len(batch) < 100:
                break
    else:
        # First run: walk backwards from newest.
        cursor = None
        all_msgs: list[dict] = []
        while True:
            params = {"limit": 100}
            if cursor:
                params["before"] = cursor
            batch = discord_get(f"/channels/{channel_id}/messages", token, params=params)
            if not batch:
                break
            all_msgs.extend(batch)
            cursor = batch[-1]["id"]
            if len(batch) < 100:
                break
        collected = sorted(all_msgs, key=lambda m: int(m["id"]))
    return collected


def is_bot_message(msg: dict) -> bool:
    return bool((msg.get("author") or {}).get("bot"))


def main() -> int:
    token = os.environ.get("DISCORD_BOT_TOKEN")
    notion_secret = os.environ.get("NOTION_SECRET")
    if not token or not notion_secret:
        log.error("DISCORD_BOT_TOKEN and NOTION_SECRET are required")
        return 1
    channel_id = CHANNEL_ID

    gemini = GeminiClient(model_name="flash")  # raises ValueError if GOOGLE_API_KEY missing
    notion = NotionApi(notion_secret)

    state = load_state()
    last_id = state.get("last_message_id")

    log.info("Fetching messages (after=%s)", last_id)
    messages = fetch_messages(token, channel_id, last_id)
    log.info("Got %d new messages", len(messages))

    highest_id = last_id
    for msg in messages:
        msg_id = msg["id"]
        if highest_id is None or int(msg_id) > int(highest_id):
            highest_id = msg_id
        if is_bot_message(msg):
            continue
        content = (msg.get("content") or "").strip()
        if not content:
            continue

        log.info("processing message %s", msg_id)
        try:
            result = extract(content, gemini)
            write(result, notion)
            reaction = REACTION_OK if result.confidence == "full" else REACTION_PARTIAL
            discord_react(token, channel_id, msg_id, reaction)
            log.info("saved %r (confidence=%s)", result.name, result.confidence)
        except Exception:
            log.exception("failed to process message %s", msg_id)
            discord_react(token, channel_id, msg_id, REACTION_ERROR)

    state["last_message_id"] = highest_id
    save_state(state)
    log.info("Done. last_message_id=%s", highest_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
