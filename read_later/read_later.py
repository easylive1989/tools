"""Pull URLs shared in a Discord channel and emit them as a full-text RSS feed.

For each URL, Firecrawl scrapes the page and returns metadata + cleaned-up
article HTML/markdown, which is embedded directly in the RSS <description>.

State (read_later/state.json) tracks which messages have been processed and
which URLs have already been emitted. Only newly discovered URLs are scraped;
cached content for existing items is preserved across runs to avoid burning
Firecrawl credits.

Required env vars:
    DISCORD_BOT_TOKEN
    FIRECRAWL_API_KEY

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
from urllib.parse import quote, urldefrag, urlparse

import requests

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "state.json"
FEED_PATH = BASE_DIR / "feed.xml"

DISCORD_API = "https://discord.com/api/v10"
DEFAULT_FEED_LINK = "https://tools.paul-learning.dev/read_later/feed.xml"
DEFAULT_MAX_ITEMS = 200
SUCCESS_REACTION = "✅"

FIRECRAWL_API = "https://api.firecrawl.dev/v2/scrape"
FIRECRAWL_TOKEN_ENV = "FIRECRAWL_API_KEY"

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


def discord_react(token: str, channel_id: str, message_id: str, emoji: str) -> tuple[bool, str]:
    """Add a reaction. Returns (success, reason). reason is a short human-readable string on failure."""
    headers = {"Authorization": f"Bot {token}", "User-Agent": "read-later-bot/1.0"}
    encoded = quote(emoji, safe="")
    url = f"{DISCORD_API}/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me"
    last_reason = "未知錯誤"
    for attempt in range(3):
        try:
            resp = requests.put(url, headers=headers, timeout=30)
        except requests.RequestException as e:
            last_reason = f"網路錯誤 ({type(e).__name__})"
            log(f"  reaction error for {message_id}: {last_reason}")
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in (200, 204):
            return True, ""
        if resp.status_code == 429:
            retry_after = float(resp.json().get("retry_after", 1))
            log(f"  reaction rate limited, sleeping {retry_after}s")
            time.sleep(retry_after)
            last_reason = "rate limited"
            continue
        if resp.status_code >= 500:
            last_reason = f"Discord 伺服器錯誤 (HTTP {resp.status_code})"
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 403:
            last_reason = "權限不足 (HTTP 403)"
        elif resp.status_code == 404:
            last_reason = "訊息已刪除 (HTTP 404)"
        else:
            last_reason = f"HTTP {resp.status_code}"
        log(f"  reaction failed for {message_id}: {last_reason}")
        return False, last_reason
    log(f"  reaction gave up for {message_id}: {last_reason}")
    return False, last_reason


def discord_post_message(token: str, channel_id: str, content: str) -> None:
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "read-later-bot/1.0",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            f"{DISCORD_API}/channels/{channel_id}/messages",
            headers=headers,
            json={"content": content},
            timeout=30,
        )
        if resp.status_code >= 400:
            log(f"  post message failed: HTTP {resp.status_code}")
    except requests.RequestException as e:
        log(f"  post message error: {type(e).__name__}")


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


def fetch_firecrawl_content(url: str) -> dict | None:
    """Scrape a URL via Firecrawl's /v2/scrape and return metadata + content.

    Returns a dict with keys: title, optionally og_description, og_image,
    og_site_name, og_url, content_html, content_markdown. Returns None when
    the API key is missing or the request fails, so callers can fall back to
    leaving the item with whatever it already had.
    """
    token = os.environ.get(FIRECRAWL_TOKEN_ENV)
    if not token:
        log("  FIRECRAWL_API_KEY not set, skipping content fetch")
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "url": url,
        "formats": ["markdown", "html"],
        "onlyMainContent": True,
        "timeout": 30000,
    }
    try:
        resp = requests.post(FIRECRAWL_API, headers=headers, json=payload, timeout=90)
    except requests.RequestException as e:
        log(f"  Firecrawl failed: {type(e).__name__}")
        return None
    if resp.status_code >= 400:
        log(f"  Firecrawl HTTP {resp.status_code}")
        return None
    try:
        body = resp.json()
    except ValueError:
        log("  Firecrawl returned non-JSON")
        return None
    if not body.get("success"):
        log(f"  Firecrawl unsuccessful: {body.get('error', '')}")
        return None

    data = body.get("data") or {}
    meta = data.get("metadata") or {}

    out: dict = {}
    title = meta.get("title") or meta.get("ogTitle") or url
    out["title"] = str(title)[:300]

    description = meta.get("description") or meta.get("ogDescription")
    if description:
        out["og_description"] = str(description)[:1000]

    image = meta.get("ogImage") or meta.get("image")
    if image:
        out["og_image"] = str(image)

    site_name = meta.get("ogSiteName")
    if site_name:
        out["og_site_name"] = str(site_name)[:200]

    canonical = meta.get("sourceURL") or meta.get("ogUrl")
    if canonical:
        out["og_url"] = str(canonical)

    html_content = data.get("html")
    if html_content:
        out["content_html"] = html_content

    markdown_content = data.get("markdown")
    if markdown_content:
        out["content_markdown"] = markdown_content

    return out


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


def label_from_url(url: str) -> str:
    """Derive a readable label from a URL when no scraped title is available.

    Firecrawl returns nothing for JS-rendered / login-walled sites (Threads,
    Instagram, …), so the raw URL would otherwise become the RSS title. Pull a
    handle or host out instead so the entry is recognizable in a reader.
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    segments = [s for s in parsed.path.split("/") if s]
    if segments and segments[0].startswith("@"):
        handle = segments[0][1:]
        if "threads" in host:
            return f"@{handle} 的 Threads 貼文"
        if "instagram" in host:
            return f"@{handle} 的 Instagram 貼文"
        return f"@{handle}（{host}）"
    return f"{host} 分享連結" if host else url


def display_title(item: dict) -> str:
    """Human-friendly RSS title.

    A real scraped title differs from the URL; when they match it means
    Firecrawl never returned one, so fall back to a label derived from the URL.
    """
    title = item.get("title")
    url = item["url"]
    if title and title != url:
        return title
    return label_from_url(url)


def shared_note(excerpt: str) -> str:
    """The user's note for a shared link, with the bare URL(s) stripped out.

    Many messages are just a URL; in that case there is no note to show and we
    avoid dumping the long link into the feed body.
    """
    note = ANGLE_URL_REGEX.sub("", excerpt)
    note = URL_REGEX.sub("", note)
    return note.strip()


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
        title = html.escape(display_title(item))
        original_url = item["url"]
        link_url = item.get("og_url") or original_url
        guid = html.escape(original_url)
        link = html.escape(link_url)
        excerpt = shared_note(item.get("message_excerpt") or "")
        og_image = item.get("og_image") or ""
        og_description = item.get("og_description") or ""
        og_site_name = item.get("og_site_name") or ""
        content_html = item.get("content_html") or ""

        body_parts: list[str] = []
        if og_image:
            body_parts.append(
                f'<p><img src="{html.escape(og_image)}" alt="" /></p>'
            )
        if og_site_name:
            body_parts.append(f"<p><em>{html.escape(og_site_name)}</em></p>")
        if content_html:
            body_parts.append(content_html)
        elif og_description:
            body_parts.append(f"<p>{html.escape(og_description)}</p>")
        if excerpt:
            body_parts.append(f"<hr /><p><em>Shared:</em> {html.escape(excerpt)}</p>")
        description_html = "".join(body_parts).replace("]]>", "]]&gt;")
        parts.append("<item>")
        parts.append(f"<title>{title}</title>")
        parts.append(f"<link>{link}</link>")
        parts.append(f'<guid isPermaLink="true">{guid}</guid>')
        parts.append(f"<pubDate>{pub}</pubDate>")
        parts.append(f"<description><![CDATA[{description_html}]]></description>")
        parts.append("</item>")

    parts.append("</channel>")
    parts.append("</rss>")
    parts.append("")
    return "\n".join(parts)


CONTENT_KEYS = (
    "title",
    "og_description",
    "og_image",
    "og_site_name",
    "og_url",
    "content_html",
    "content_markdown",
)


def main() -> int:
    token = os.environ.get("DISCORD_BOT_TOKEN")
    channel_id = "1501760423442251896"
    if not token:
        log("DISCORD_BOT_TOKEN is required")
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
            new_items.append(
                {
                    "url": url,
                    "title": url,
                    "author": author,
                    "shared_at": ts.isoformat(),
                    "message_id": msg["id"],
                    "message_link": link,
                    "message_excerpt": excerpt,
                }
            )

    if new_items:
        log(f"Scraping {len(new_items)} new URL(s) via Firecrawl")
        for item in new_items:
            content = fetch_firecrawl_content(item["url"])
            if content is None:
                continue
            for key in CONTENT_KEYS:
                if key in content:
                    item[key] = content[key]
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

    reacted: set[str] = set()
    for item in new_items:
        msg_id = item.get("message_id")
        if not msg_id or msg_id in reacted:
            continue
        reacted.add(msg_id)
        ok, reason = discord_react(token, channel_id, msg_id, SUCCESS_REACTION)
        if not ok:
            discord_post_message(
                token,
                channel_id,
                f"⚠️ 無法對訊息加 {SUCCESS_REACTION} reaction（訊息 ID: {msg_id}）：{reason}",
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
