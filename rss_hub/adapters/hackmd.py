"""HackMD adapter: scrape a public user/team profile page for note list.

HackMD does not publish an open RSS feed for `https://hackmd.io/@<id>` pages,
and the v1 API requires a token scoped to the owner. We therefore parse the
profile HTML directly:

  1. Look for the SSR'd `<script id="__NEXT_DATA__">` JSON blob and pluck the
     note list out of it (preferred — gives us titles and timestamps).
  2. Fall back to anchor scraping for `/@<id>/<noteId>` links so the adapter
     keeps working if the page structure regresses to plain HTML.

Each item returned is a dict with: title, link, guid, pub_date (UTC datetime
or None when unknown).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup


SITE_ROOT = "https://hackmd.io"


@dataclass
class NoteItem:
    title: str
    link: str
    guid: str
    pub_date: datetime | None


def slug_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    # `@user` or `@user/...` -> user
    first = path.split("/", 1)[0]
    if first.startswith("@"):
        first = first[1:]
    return first or "hackmd"


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # HackMD uses millisecond epoch.
        if value > 1e12:
            value = value / 1000.0
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _walk_for_notes(node: Any) -> Iterable[dict]:
    """Yield dict-shaped objects that plausibly describe a HackMD note."""
    if isinstance(node, dict):
        keys = node.keys()
        if (
            ("title" in keys or "name" in keys)
            and ("shortId" in keys or "id" in keys or "permalink" in keys or "noteId" in keys)
        ):
            yield node
        for v in node.values():
            yield from _walk_for_notes(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_for_notes(v)


def _extract_from_next_data(soup: BeautifulSoup, base_url: str) -> list[NoteItem]:
    tag = soup.find("script", id="__NEXT_DATA__")
    if tag is None or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
    except json.JSONDecodeError:
        return []

    items: list[NoteItem] = []
    seen: set[str] = set()
    for note in _walk_for_notes(data):
        title = (note.get("title") or note.get("name") or "").strip()
        if not title:
            continue
        # Try several plausible URL fields.
        link = (
            note.get("publishLink")
            or note.get("publishUrl")
            or note.get("permalink")
            or note.get("url")
        )
        if not link:
            short = note.get("shortId") or note.get("id") or note.get("noteId")
            if not short:
                continue
            link = urljoin(base_url.rstrip("/") + "/", str(short))
        if not link.startswith("http"):
            link = urljoin(SITE_ROOT, link)
        if link in seen:
            continue
        seen.add(link)

        pub_date = (
            _parse_datetime(note.get("publishedAt"))
            or _parse_datetime(note.get("lastChangedAt"))
            or _parse_datetime(note.get("updatedAt"))
            or _parse_datetime(note.get("createdAt"))
        )
        items.append(NoteItem(title=title, link=link, guid=link, pub_date=pub_date))
    return items


_NOTE_LINK_RE = re.compile(r"^/@[^/]+/[^/?#]+$")


def _extract_from_anchors(soup: BeautifulSoup) -> list[NoteItem]:
    items: list[NoteItem] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not _NOTE_LINK_RE.match(href):
            continue
        title = a.get_text(" ", strip=True)
        if not title:
            continue
        link = urljoin(SITE_ROOT, href)
        if link in seen:
            continue
        seen.add(link)
        items.append(NoteItem(title=title, link=link, guid=link, pub_date=None))
    return items


def fetch_items(url: str, *, fetcher) -> list[NoteItem]:
    """Fetch the HackMD profile page and return parsed notes.

    `fetcher(url) -> str` is injected so the caller controls HTTP behaviour
    (cloudscraper, retries, user-agent, etc.).
    """
    html = fetcher(url)
    soup = BeautifulSoup(html, "html.parser")
    items = _extract_from_next_data(soup, url)
    if not items:
        items = _extract_from_anchors(soup)
    return items
