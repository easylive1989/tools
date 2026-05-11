"""HackMD adapter: render the profile page with Playwright then parse anchors.

HackMD profile pages (https://hackmd.io/@<user>) are fully client-side rendered
— the initial HTML has no note data. The caller MUST supply a `fetcher` that
returns the post-render DOM (typically via Playwright's `page.content()`).

We accept several anchor shapes since HackMD's permalinks vary:
  - /@<user>/<noteId>                user-scoped permalinks
  - /<22-ish-char-shortId>           anonymous/published shortlinks
  - /s/<shortId>                     publish-link style
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag


SITE_ROOT = "https://hackmd.io"


@dataclass
class NoteItem:
    title: str
    link: str
    guid: str
    pub_date: datetime | None


def slug_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    first = path.split("/", 1)[0]
    if first.startswith("@"):
        first = first[1:]
    return first or "hackmd"


_USER_HREF_RE = re.compile(r"^/@[^/]+/[^/?#]+$")
_SHORT_HREF_RE = re.compile(r"^/(?:s/)?[A-Za-z0-9_-]{12,32}(?:[/?#].*)?$")
# Junk we never want as a "note": auth, settings, marketing pages, etc.
_BLOCK_PREFIXES = (
    "/auth",
    "/settings",
    "/join",
    "/login",
    "/logout",
    "/c/",
    "/s/terms",
    "/s/privacy",
    "/api",
)


def _looks_like_note(href: str) -> bool:
    if not href.startswith("/"):
        return False
    if any(href.startswith(p) for p in _BLOCK_PREFIXES):
        return False
    if _USER_HREF_RE.match(href):
        return True
    if _SHORT_HREF_RE.match(href):
        # `/@user` itself is short-ish — exclude single-segment user pages.
        return not href.lstrip("/").startswith("@")
    return False


def _nearby_time(anchor: Tag) -> datetime | None:
    # Look at the anchor itself, its descendants, and its closest ancestors
    # for a <time datetime="..."> element. HackMD typically shows relative
    # times with the absolute datetime stashed in the attribute.
    candidates: list[Tag] = []
    candidates.extend(anchor.find_all("time"))
    parent = anchor.parent
    depth = 0
    while parent is not None and depth < 4:
        candidates.extend(parent.find_all("time", recursive=False))
        for child in parent.children:
            if isinstance(child, Tag) and child is not anchor:
                candidates.extend(child.find_all("time"))
        parent = parent.parent
        depth += 1
    for t in candidates:
        dt = t.get("datetime") or t.get("data-time") or t.get("title")
        if not dt:
            continue
        try:
            return datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def _clean_title(anchor: Tag) -> str:
    text = anchor.get_text(" ", strip=True)
    # Strip duplicated whitespace.
    return re.sub(r"\s+", " ", text).strip()


def fetch_items(url: str, *, fetcher) -> list[NoteItem]:
    html = fetcher(url)
    soup = BeautifulSoup(html, "html.parser")

    items: list[NoteItem] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not _looks_like_note(href):
            continue
        title = _clean_title(a)
        if not title or len(title) < 2:
            continue
        link = urljoin(SITE_ROOT, href.split("#", 1)[0])
        if link in seen:
            continue
        seen.add(link)
        items.append(NoteItem(
            title=title,
            link=link,
            guid=link,
            pub_date=_nearby_time(a),
        ))
    return items
