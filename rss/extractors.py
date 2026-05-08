"""RSS 內容抽取器 registry。

介面：
    extract(html: str, entry: dict, feed_config: dict, scraper) -> str | None

- 回傳 HTML 字串（由 rss.py 統一用 markdownify 轉成 Markdown），或 None 表示失敗
- scraper 允許抽取器自行發 HTTP request（目前未使用，保留擴充用）
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import re
from urllib.parse import parse_qs, urlparse

import requests
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


APIFY_TOKEN_ENV = "APIFY_TOKEN"

# 社群平台 → Apify actor ID(用 ~ 取代 / 以符合 URL 路徑)
_APIFY_ACTORS = {
    "facebook": "apify~facebook-posts-scraper",
    "threads": "apify~threads-scraper",
    "instagram": "apify~instagram-post-scraper",
}


def detect_social_platform(url: str) -> str | None:
    """根據 URL host 判斷是否為 FB / Threads / IG 貼文，回傳平台代號或 None。"""
    if not url:
        return None
    host = urlparse(url).netloc.lower()
    if any(d in host for d in ("facebook.com", "fb.com", "fb.watch", "m.facebook.com")):
        return "facebook"
    if "threads.net" in host or "threads.com" in host:
        return "threads"
    if "instagram.com" in host:
        return "instagram"
    return None


def extract_social_post_id(url: str, platform: str) -> str:
    """從社群貼文 URL 抽出可作為唯一識別子的 post id / shortcode。

    抽不到時 fallback 到 URL 的 md5 前 8 碼,確保不同貼文一定有不同的 id,
    避免 RSS title 同名(e.g. Threads 全部叫「Thread」)導致檔名互相覆蓋。
    """
    if not url:
        return ""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]

    def _after(keyword: str) -> str | None:
        if keyword in parts:
            i = parts.index(keyword)
            if i + 1 < len(parts):
                return parts[i + 1]
        return None

    if platform == "threads":
        # /@user/post/{shortcode}
        if (pid := _after("post")):
            return pid
    elif platform == "instagram":
        # /p/{shortcode}/、/reel/{shortcode}/、/tv/{shortcode}/
        for kw in ("p", "reel", "tv"):
            if (pid := _after(kw)):
                return pid
    elif platform == "facebook":
        # /posts/{id}、/share/p/{id}、/videos/{id}、?story_fbid=...
        for kw in ("posts", "videos", "p"):
            if (pid := _after(kw)):
                return pid
        qs = parse_qs(parsed.query)
        if "story_fbid" in qs:
            return qs["story_fbid"][0]

    # fallback:最後一段 path,再 fallback 到 URL hash
    if parts:
        return parts[-1]
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:8]


def _apify_stub(link: str, reason: str) -> str:
    safe_link = html_lib.escape(link)
    safe_reason = html_lib.escape(reason)
    return (
        f"<p><strong>⚠️ 自動抽取失敗:</strong> {safe_reason}</p>\n"
        f'<p>原始連結: <a href="{safe_link}">{safe_link}</a></p>'
    )


def _build_apify_input(platform: str, url: str) -> dict:
    if platform == "facebook":
        return {"startUrls": [{"url": url}], "resultsLimit": 1}
    if platform == "threads":
        return {"urls": [url], "resultsLimit": 1}
    if platform == "instagram":
        return {"directUrls": [url], "resultsLimit": 1}
    return {"startUrls": [{"url": url}]}


def _pick_text(item: dict) -> str:
    for key in ("text", "caption", "content", "postText", "description"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _pick_author(item: dict) -> str:
    user = item.get("user")
    if isinstance(user, dict):
        for key in ("username", "fullName", "name"):
            if user.get(key):
                return str(user[key])
    owner = item.get("owner")
    if isinstance(owner, dict):
        for key in ("username", "fullName", "name"):
            if owner.get(key):
                return str(owner[key])
    for key in ("authorName", "ownerUsername", "pageName", "username"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _pick_media_urls(item: dict) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def push(u):
        if not u or not isinstance(u, str):
            return
        if u in seen:
            return
        seen.add(u)
        urls.append(u)

    for key in ("media", "images", "imageUrls", "videoUrls"):
        value = item.get(key)
        if isinstance(value, list):
            for m in value:
                if isinstance(m, dict):
                    push(m.get("url") or m.get("src") or m.get("displayUrl") or m.get("thumbnail"))
                elif isinstance(m, str):
                    push(m)

    push(item.get("displayUrl"))
    push(item.get("videoUrl"))
    return urls


def _format_apify_item(item: dict, link: str) -> str:
    parts = [
        f'<p><strong>來源:</strong> <a href="{html_lib.escape(link)}">{html_lib.escape(link)}</a></p>'
    ]

    author = _pick_author(item)
    if author:
        parts.append(f"<p><strong>作者:</strong> {html_lib.escape(author)}</p>")

    text = _pick_text(item)
    if text:
        text_html = html_lib.escape(text).replace("\n", "<br/>\n")
        parts.append(f"<p>{text_html}</p>")

    for media_url in _pick_media_urls(item)[:10]:
        parts.append(f'<p><img src="{html_lib.escape(media_url)}" /></p>')

    return "\n".join(parts)


def extract_apify(html: str, entry: dict, feed_config: dict, scraper) -> str | None:
    """用 Apify 抓 FB / Threads / IG 貼文內容；失敗回傳 stub HTML(含原始 link)。"""
    link = entry.get("link", "")
    platform = detect_social_platform(link)
    if not platform:
        return _apify_stub(link or "(空連結)", "無法辨識社群平台")

    token = os.environ.get(APIFY_TOKEN_ENV)
    if not token:
        print(f"  Apify: 未設定 {APIFY_TOKEN_ENV} 環境變數")
        return _apify_stub(link, f"未設定 {APIFY_TOKEN_ENV} 環境變數")

    actor = _APIFY_ACTORS[platform]
    api_url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
    payload = _build_apify_input(platform, link)

    print(f"  Apify {platform}: 呼叫 actor {actor.replace('~', '/')}")
    try:
        res = requests.post(
            api_url,
            params={"token": token},
            json=payload,
            timeout=180,
        )
        res.raise_for_status()
        data = res.json()
    except requests.exceptions.Timeout:
        return _apify_stub(link, "Apify 抓取逾時 (180s)")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        return _apify_stub(link, f"Apify HTTP 錯誤 ({status})")
    except Exception as e:
        return _apify_stub(link, f"Apify 抓取失敗 ({type(e).__name__})")

    if not isinstance(data, list) or not data:
        return _apify_stub(link, "Apify 回傳空結果")

    return _format_apify_item(data[0], link)


EXTRACTOR_REGISTRY = {
    "readability": extract_readability,
    "hellogithub": extract_hellogithub,
    "feed_content": extract_feed_content,
    "apify": extract_apify,
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


def requires_page_fetch(name: str) -> bool:
    """feed_content 與 apify 不需要 rss.py 預先抓網頁;其他都需要。"""
    return name not in {"feed_content", "apify"}
