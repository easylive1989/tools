"""RSS 內容抽取器 registry。

介面：
    extract(html: str, entry: dict, feed_config: dict, scraper) -> str | None

- 回傳 HTML 字串（由 rss.py 統一用 markdownify 轉成 Markdown），或 None 表示失敗
- scraper 允許抽取器自行發 HTTP request（目前未使用，保留擴充用）
"""

from __future__ import annotations

import html as html_lib
import json
import re

from readability import Document


def extract_readability(html: str, entry: dict, feed_config: dict, scraper) -> str | None:
    doc = Document(html)
    summary = doc.summary()
    if not summary or len(summary) < 50:
        return None
    return summary


def extract_feed_content(html: str, entry: dict, feed_config: dict, scraper) -> str | None:
    content = entry.get("content")
    if content:
        value = content[0].get("value") if isinstance(content, list) else None
        if value:
            return value
    summary = entry.get("summary")
    return summary or None


_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


def _find_hellogithub_volume(data):
    """從 __NEXT_DATA__ 遞迴定位到 hellogithub 月刊資料。

    典型路徑：props.pageProps.volume.data (list of categories)
    以 duck typing 尋找，避免 schema 微調就整個壞掉。
    """
    if isinstance(data, dict):
        if (
            "data" in data
            and isinstance(data["data"], list)
            and data["data"]
            and isinstance(data["data"][0], dict)
            and "category_name" in data["data"][0]
            and "items" in data["data"][0]
        ):
            return data
        for v in data.values():
            result = _find_hellogithub_volume(v)
            if result is not None:
                return result
    elif isinstance(data, list):
        for v in data:
            result = _find_hellogithub_volume(v)
            if result is not None:
                return result
    return None


def _esc(text) -> str:
    return html_lib.escape(str(text or ""))


def extract_hellogithub(html: str, entry: dict, feed_config: dict, scraper) -> str | None:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return None
    try:
        next_data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    volume = _find_hellogithub_volume(next_data.get("props", {}).get("pageProps", {}))
    if volume is None:
        return None

    categories = volume.get("data") or []
    if not categories:
        return None

    parts: list[str] = []

    current_num = volume.get("current_num")
    publish_at = volume.get("publish_at", "")
    if current_num:
        parts.append(f"<h1>《HelloGitHub》第 {_esc(current_num)} 期</h1>")
    if publish_at:
        parts.append(f"<p><em>發佈於 {_esc(publish_at)}</em></p>")

    for category in categories:
        category_name = category.get("category_name", "")
        items = category.get("items") or []
        if not items:
            continue
        parts.append(f"<h2>{_esc(category_name)}</h2>")
        for item in items:
            name = item.get("name", "")
            full_name = item.get("full_name", "")
            github_url = item.get("github_url") or ""
            description = item.get("description", "")
            description_en = item.get("description_en", "")
            stars = item.get("stars")
            forks = item.get("forks")
            image_url = item.get("image_url")

            title_html = (
                f'<a href="{_esc(github_url)}">{_esc(name)}</a>'
                if github_url else _esc(name)
            )
            parts.append(f"<h3>{title_html}</h3>")

            meta_bits = []
            if full_name:
                meta_bits.append(_esc(full_name))
            if stars is not None:
                meta_bits.append(f"★ {_esc(stars)}")
            if forks is not None:
                meta_bits.append(f"⑂ {_esc(forks)}")
            if meta_bits:
                parts.append(f"<p>{' · '.join(meta_bits)}</p>")

            if description:
                parts.append(f"<p>{_esc(description)}</p>")
            if description_en and description_en != description:
                parts.append(f"<p><em>{_esc(description_en)}</em></p>")

            if image_url:
                parts.append(f'<p><img src="{_esc(image_url)}" alt="{_esc(name)}"/></p>')

    if len(parts) < 2:
        return None
    return "\n".join(parts)


EXTRACTOR_REGISTRY = {
    "readability": extract_readability,
    "hellogithub": extract_hellogithub,
    "feed_content": extract_feed_content,
}


def dispatch(name: str, html: str, entry: dict, feed_config: dict, scraper) -> str | None:
    fn = EXTRACTOR_REGISTRY.get(name)
    if fn is None:
        print(f"  Unknown extractor '{name}', falling back to readability")
        fn = EXTRACTOR_REGISTRY["readability"]
    try:
        return fn(html, entry, feed_config, scraper)
    except Exception as e:
        print(f"  Extractor '{name}' error: {e}")
        return None


NEEDS_PAGE_FETCH = {"readability", "hellogithub"}


def requires_page_fetch(name: str) -> bool:
    """feed_content 不需重抓網頁；其他都需要。未知名稱保守起見當作需要。"""
    return name != "feed_content"
