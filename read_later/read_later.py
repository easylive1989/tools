"""Pull URLs shared in a Discord channel and emit them as an RSS feed.

State (read_later/state.json) tracks which messages have been processed and
which URLs have already been emitted, so each URL appears at most once and only
new messages are fetched on subsequent runs.

Required env vars:
    DISCORD_BOT_TOKEN
    DISCORD_READ_LATER_CHANNEL_ID

Optional env vars:
    READ_LATER_FEED_LINK   public URL where feed.xml will be served
                           (default: https://tools.paul-learning.dev/read_later/feed.xml)
    READ_LATER_MAX_ITEMS   max items kept in the RSS feed (default: 200)
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urldefrag, urlparse

import requests

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "state.json"
FEED_PATH = BASE_DIR / "feed.xml"

DISCORD_API = "https://discord.com/api/v10"
DEFAULT_FEED_LINK = "https://tools.paul-learning.dev/read_later/feed.xml"
DEFAULT_MAX_ITEMS = 200

URL_REGEX = re.compile(r"https?://[^\s<>\"'\)\]]+")
TRAILING_PUNCT = ".,;:!?)]}>"

# Strip Discord's <url> angle brackets that suppress link previews.
ANGLE_URL_REGEX = re.compile(r"<(https?://[^>\s]+)>")


def log(msg: str) -> None:
    print(msg, flush=True)


def load_state() -> dict:
    if STATE_PATH.exists():
        with STATE_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {"last_message_id": None, "seen_urls": [], "items": []}


def save_state(state: dict) -> None:
    with STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def discord_get(path: str, token: str, params: dict | None = None) -> list:
    headers = {"Authorization": f"Bot {token}", "User-Agent": "read-later-bot/1.0"}
    for attempt in range(5):
        resp = requests.get(f"{DISCORD_API}{path}", headers=headers, params=params, timeout=30)
        if resp.status_code == 429:
            retry_after = float(resp.json().get("retry_after", 1))
            log(f"  rate limited, sleeping {retry_after}s")
            time.sleep(retry_after)
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Discord API failed for {path}")


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
        cursor: str | None = None
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


def normalize_url(url: str) -> str:
    url = url.rstrip(TRAILING_PUNCT)
    url, _ = urldefrag(url)
    return url


def extract_urls(content: str) -> list[str]:
    if not content:
        return []
    # Treat <url> the same as bare URLs.
    cleaned = ANGLE_URL_REGEX.sub(r"\1", content)
    raw = URL_REGEX.findall(cleaned)
    seen: set[str] = set()
    out: list[str] = []
    for u in raw:
        n = normalize_url(u)
        if not n or n in seen:
            continue
        parsed = urlparse(n)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        seen.add(n)
        out.append(n)
    return out


TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
OG_TITLE_RE_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
    re.IGNORECASE,
)


def fetch_title(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
        ),
        "Accept-Language": "en,zh-TW;q=0.8,zh;q=0.7",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if resp.status_code >= 400:
            return url
        text = resp.text
    except requests.RequestException:
        return url

    for pattern in (OG_TITLE_RE, OG_TITLE_RE_REV, TITLE_RE):
        m = pattern.search(text)
        if m:
            title = html.unescape(m.group(1)).strip()
            title = re.sub(r"\s+", " ", title)
            if title:
                return title[:300]
    return url


def message_link(guild_id: str | None, channel_id: str, message_id: str) -> str:
    guild = guild_id or "@me"
    return f"https://discord.com/channels/{guild}/{channel_id}/{message_id}"


def message_timestamp(msg: dict) -> datetime:
    ts = msg.get("timestamp")
    if ts:
        # Discord timestamps look like 2024-01-02T03:04:05.123000+00:00
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return datetime.now(tz=timezone.utc)


def author_name(msg: dict) -> str:
    author = msg.get("author") or {}
    return author.get("global_name") or author.get("username") or "unknown"


def build_feed(items: list[dict], feed_link: str) -> str:
    now = format_datetime(datetime.now(tz=timezone.utc))
    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append('<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">')
    parts.append("<channel>")
    parts.append("<title>Discord Read Later</title>")
    parts.append(f"<link>{html.escape(feed_link)}</link>")
    parts.append(
        f'<atom:link href="{html.escape(feed_link)}" rel="self" type="application/rss+xml" />'
    )
    parts.append("<description>URLs shared in Discord, ready for your RSS reader.</description>")
    parts.append("<language>zh-tw</language>")
    parts.append(f"<lastBuildDate>{now}</lastBuildDate>")

    for item in items:
        pub = format_datetime(datetime.fromisoformat(item["shared_at"]))
        title = html.escape(item.get("title") or item["url"])
        url = html.escape(item["url"])
        author = html.escape(item.get("author") or "unknown")
        msg_link = html.escape(item.get("message_link") or "")
        excerpt = html.escape(item.get("message_excerpt") or "")
        description_lines = [f"Shared by {author}"]
        if excerpt:
            description_lines.append("")
            description_lines.append(excerpt)
        if msg_link:
            description_lines.append("")
            description_lines.append(f"Discord: {msg_link}")
        description = "\n".join(description_lines)
        parts.append("<item>")
        parts.append(f"<title>{title}</title>")
        parts.append(f"<link>{url}</link>")
        parts.append(f"<guid isPermaLink=\"true\">{url}</guid>")
        parts.append(f"<pubDate>{pub}</pubDate>")
        parts.append(f"<description>{description}</description>")
        parts.append("</item>")

    parts.append("</channel>")
    parts.append("</rss>")
    parts.append("")
    return "\n".join(parts)


def main() -> int:
    token = os.environ.get("DISCORD_BOT_TOKEN")
    channel_id = os.environ.get("DISCORD_READ_LATER_CHANNEL_ID")
    if not token or not channel_id:
        log("DISCORD_BOT_TOKEN and DISCORD_READ_LATER_CHANNEL_ID are required")
        return 1

    feed_link = os.environ.get("READ_LATER_FEED_LINK", DEFAULT_FEED_LINK)
    max_items = int(os.environ.get("READ_LATER_MAX_ITEMS", DEFAULT_MAX_ITEMS))

    state = load_state()
    last_id = state.get("last_message_id")
    seen_urls: set[str] = set(state.get("seen_urls", []))
    items: list[dict] = list(state.get("items", []))

    log(f"Fetching messages (after={last_id})")
    messages = fetch_messages(token, channel_id, last_id)
    log(f"Got {len(messages)} new messages")

    new_items: list[dict] = []
    highest_id = last_id
    for msg in messages:
        highest_id = msg["id"] if highest_id is None or int(msg["id"]) > int(highest_id) else highest_id
        urls = extract_urls(msg.get("content", ""))
        if not urls:
            continue
        ts = message_timestamp(msg)
        author = author_name(msg)
        guild_id = msg.get("guild_id")
        link = message_link(guild_id, channel_id, msg["id"])
        excerpt = (msg.get("content") or "").strip()
        if len(excerpt) > 500:
            excerpt = excerpt[:500] + "..."
        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            log(f"  + {url}")
            title = fetch_title(url)
            new_items.append(
                {
                    "url": url,
                    "title": title,
                    "author": author,
                    "shared_at": ts.isoformat(),
                    "message_id": msg["id"],
                    "message_link": link,
                    "message_excerpt": excerpt,
                }
            )

    if new_items:
        items.extend(new_items)

    items.sort(key=lambda i: i["shared_at"], reverse=True)
    items = items[:max_items]

    state["last_message_id"] = highest_id
    state["seen_urls"] = sorted(seen_urls)
    state["items"] = items
    save_state(state)

    feed_xml = build_feed(items, feed_link)
    FEED_PATH.write_text(feed_xml, encoding="utf-8")
    log(f"Wrote {FEED_PATH} with {len(items)} items ({len(new_items)} new)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
