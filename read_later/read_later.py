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
    APIFY_TOKEN            if set, FB / Threads / IG URLs are enriched via Apify
                           instead of plain HTML scraping (which those sites block).
    APIFY_FACEBOOK_ACTOR   override actor IDs (default: apify~facebook-posts-scraper,
    APIFY_THREADS_ACTOR    apify~threads-scraper, apify~instagram-post-scraper).
    APIFY_INSTAGRAM_ACTOR
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

OG_PROPERTIES = ("og:title", "og:description", "og:image", "og:site_name", "og:type", "og:url")


def _og_pattern(prop: str) -> tuple[re.Pattern, re.Pattern]:
    forward = re.compile(
        rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']*)["\']',
        re.IGNORECASE,
    )
    reverse = re.compile(
        rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']{re.escape(prop)}["\']',
        re.IGNORECASE,
    )
    return forward, reverse


_OG_PATTERNS = {prop: _og_pattern(prop) for prop in OG_PROPERTIES}


def _clean(text: str, limit: int | None = None) -> str:
    cleaned = html.unescape(text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if limit and len(cleaned) > limit:
        cleaned = cleaned[:limit]
    return cleaned


APIFY_TOKEN_ENV = "APIFY_TOKEN"
APIFY_DEFAULT_ACTORS = {
    "facebook": "apify~facebook-posts-scraper",
    "threads": "apify~threads-scraper",
    "instagram": "apify~instagram-post-scraper",
}
SOCIAL_HOSTS = {
    "facebook": ("facebook.com", "fb.com", "fb.watch", "m.facebook.com"),
    "threads": ("threads.net", "threads.com"),
    "instagram": ("instagram.com",),
}
PLATFORM_LABEL = {"facebook": "Facebook", "threads": "Threads", "instagram": "Instagram"}


def detect_social_platform(url: str) -> str | None:
    if not url:
        return None
    host = urlparse(url).netloc.lower()
    for platform, hosts in SOCIAL_HOSTS.items():
        if any(h in host for h in hosts):
            return platform
    return None


def _apify_input(platform: str, url: str) -> dict:
    if platform == "facebook":
        return {"startUrls": [{"url": url}], "resultsLimit": 1}
    if platform == "threads":
        return {"urls": [url], "resultsLimit": 1}
    if platform == "instagram":
        return {"directUrls": [url], "resultsLimit": 1}
    return {"startUrls": [{"url": url}]}


def _apify_pick(item: dict, *keys: str) -> str:
    for k in keys:
        v = item.get(k)
        if v:
            return str(v)
    return ""


def _apify_author(item: dict) -> str:
    for sub in ("user", "owner"):
        u = item.get(sub)
        if isinstance(u, dict):
            for k in ("username", "fullName", "name"):
                if u.get(k):
                    return str(u[k])
    return _apify_pick(item, "authorName", "ownerUsername", "pageName", "username")


def _apify_text(item: dict) -> str:
    return _apify_pick(item, "text", "caption", "content", "postText", "description")


def _apify_image(item: dict) -> str:
    for key in ("media", "images", "imageUrls", "videoUrls"):
        v = item.get(key)
        if isinstance(v, list):
            for m in v:
                if isinstance(m, dict):
                    u = m.get("url") or m.get("src") or m.get("displayUrl") or m.get("thumbnail")
                    if u:
                        return str(u)
                elif isinstance(m, str) and m:
                    return m
    return _apify_pick(item, "displayUrl", "thumbnailUrl", "videoThumbnailUrl")


def fetch_apify_metadata(url: str, platform: str) -> dict | None:
    """Hit Apify's run-sync endpoint for a single FB/Threads/IG post.

    Returns metadata dict matching fetch_og_metadata's shape, or None on any failure
    so the caller can fall back to plain OG scraping.
    """
    token = os.environ.get(APIFY_TOKEN_ENV)
    if not token:
        return None
    override = os.environ.get(f"APIFY_{platform.upper()}_ACTOR", "").strip()
    actor = (override or APIFY_DEFAULT_ACTORS[platform]).replace("/", "~")
    api_url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
    log(f"  Apify {platform}: {actor.replace('~', '/')}")
    try:
        resp = requests.post(
            api_url,
            params={"token": token},
            json=_apify_input(platform, url),
            timeout=180,
        )
        if resp.status_code >= 400:
            log(f"  Apify {platform} HTTP {resp.status_code}")
            return None
        data = resp.json()
    except requests.RequestException as e:
        log(f"  Apify {platform} failed: {type(e).__name__}")
        return None

    if not isinstance(data, list) or not data:
        log(f"  Apify {platform} returned no items")
        return None

    item = data[0]
    text = _apify_text(item).strip()
    author = _apify_author(item).strip()
    image = _apify_image(item)
    canonical = _apify_pick(item, "url", "postUrl", "permalink") or url
    label = PLATFORM_LABEL.get(platform, platform)

    if text:
        first_line = text.split("\n", 1)[0].strip()
        title = first_line[:200] if first_line else f"{author or label} on {label}"
    elif author:
        title = f"{author} on {label}"
    else:
        title = url

    metadata: dict = {"title": title[:300]}
    if text:
        metadata["og_description"] = text[:1000]
    if image:
        metadata["og_image"] = image
    if author:
        metadata["og_site_name"] = f"{author} · {label}"
    else:
        metadata["og_site_name"] = label
    metadata["og_url"] = canonical
    metadata["og_type"] = "article"
    return metadata


def fetch_metadata(url: str) -> dict | None:
    """Choose the right backend (Apify for socials, generic OG scrape otherwise)."""
    platform = detect_social_platform(url)
    if platform:
        result = fetch_apify_metadata(url, platform)
        if result:
            return result
        log(f"  Apify {platform} unavailable, falling back to og: scrape")
    return fetch_og_metadata(url)


def fetch_og_metadata(url: str) -> dict | None:
    """Return a dict with title/description/image/site_name/type/og_url for the URL.

    Returns None if the page can't be fetched, so callers can keep prior metadata.
    Missing fields are omitted.
    """
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
            return None
        text = resp.text
    except requests.RequestException:
        return None

    found: dict[str, str] = {}
    for prop, (forward, reverse) in _OG_PATTERNS.items():
        m = forward.search(text) or reverse.search(text)
        if m:
            value = _clean(m.group(1), limit=2000)
            if value:
                found[prop] = value

    title = found.get("og:title")
    if not title:
        m = TITLE_RE.search(text)
        if m:
            title = _clean(m.group(1), limit=300)

    metadata: dict = {"title": (title or url)[:300]}
    if found.get("og:description"):
        metadata["og_description"] = found["og:description"][:1000]
    if found.get("og:image"):
        metadata["og_image"] = found["og:image"]
    if found.get("og:site_name"):
        metadata["og_site_name"] = found["og:site_name"][:200]
    if found.get("og:type"):
        metadata["og_type"] = found["og:type"][:100]
    if found.get("og:url"):
        metadata["og_url"] = found["og:url"]
    return metadata


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
        original_url = item["url"]
        link_url = item.get("og_url") or original_url
        guid = html.escape(original_url)
        link = html.escape(link_url)
        author = html.escape(item.get("author") or "unknown")
        msg_link = item.get("message_link") or ""
        excerpt = item.get("message_excerpt") or ""
        og_image = item.get("og_image") or ""
        og_description = item.get("og_description") or ""
        og_site_name = item.get("og_site_name") or ""

        body_parts: list[str] = []
        if og_image:
            body_parts.append(
                f'<p><img src="{html.escape(og_image)}" alt="" /></p>'
            )
        if og_site_name:
            body_parts.append(f"<p><em>{html.escape(og_site_name)}</em></p>")
        if og_description:
            body_parts.append(f"<p>{html.escape(og_description)}</p>")
        body_parts.append(f"<p>Shared by {author}</p>")
        if excerpt:
            body_parts.append(f"<p>{html.escape(excerpt)}</p>")
        if msg_link:
            body_parts.append(
                f'<p>Discord: <a href="{html.escape(msg_link)}">{html.escape(msg_link)}</a></p>'
            )
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
        items.extend(new_items)

    items.sort(key=lambda i: i["shared_at"], reverse=True)
    items = items[:max_items]

    log(f"Refreshing OG metadata for {len(items)} items")
    og_keys = ("title", "og_description", "og_image", "og_site_name", "og_type", "og_url")
    for item in items:
        if not item.get("url"):
            continue
        metadata = fetch_metadata(item["url"])
        if metadata is None:
            continue
        for key in og_keys:
            if key in metadata:
                item[key] = metadata[key]
            else:
                item.pop(key, None)

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
