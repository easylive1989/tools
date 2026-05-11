"""HackMD adapter: parse the rendered profile page for note cards.

HackMD profile pages (https://hackmd.io/@<user>) are SPAs — see rss_hub.py for
the Playwright-based fetcher. The rendered DOM exposes each note as an
absolute-URL anchor under the profile, e.g.

    <a href="https://hackmd.io/@user/noteId">Title</a>

with a sibling `<span class="font-medium">Updated 3 days ago</span>` carrying
the timestamp as a relative string (no `<time datetime>` attribute).

We:
  1. Accept any anchor whose resolved URL is exactly `<source_url>/<noteId>`.
  2. Walk up a few ancestors to find an "Updated ... ago" text and compute
     `pub_date` relative to now.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag


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


_UNIT_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "week": 604800,
    "month": 2592000,   # 30d approximation, HackMD only shows this for old notes
    "year": 31536000,   # 365d approximation
}

_RELATIVE_RE = re.compile(
    r"(?:Updated|Created|Modified)\s+(?:(\d+)|an?|a)\s+(second|minute|hour|day|week|month|year)s?\s+ago",
    re.IGNORECASE,
)


def _parse_relative_time(text: str, *, now: datetime) -> datetime | None:
    m = _RELATIVE_RE.search(text)
    if not m:
        return None
    count = int(m.group(1)) if m.group(1) else 1
    unit = m.group(2).lower()
    dt = now - timedelta(seconds=count * _UNIT_SECONDS[unit])
    # Round to start-of-day UTC so the relative-time drift between runs
    # doesn't keep nudging pub_date and producing spurious diffs.
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _find_relative_time(anchor: Tag, *, now: datetime) -> datetime | None:
    container: Tag | None = anchor
    for _ in range(6):
        container = container.parent if container else None
        if container is None:
            break
        dt = _parse_relative_time(container.get_text(" ", strip=True), now=now)
        if dt is not None:
            return dt
    return None


def _clean_title(anchor: Tag) -> str:
    return re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).strip()


def fetch_items(url: str, *, fetcher) -> list[NoteItem]:
    html = fetcher(url)
    soup = BeautifulSoup(html, "html.parser")
    base = url.rstrip("/")
    base_for_join = base + "/"
    now = datetime.now(tz=timezone.utc)

    items: list[NoteItem] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        link = urljoin(base_for_join, a["href"].strip())
        if not link.startswith(base + "/"):
            continue
        suffix = link[len(base) + 1:]
        if not suffix or "/" in suffix or "?" in suffix or "#" in suffix:
            continue
        title = _clean_title(a)
        if not title:
            continue
        if link in seen:
            continue
        seen.add(link)
        items.append(NoteItem(
            title=title,
            link=link,
            guid=link,
            pub_date=_find_relative_time(a, now=now),
        ))
    return items
