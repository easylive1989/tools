import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser

import requests

log = logging.getLogger(__name__)

# 同時支援本機（common/ 在上一層）和 VPS（common/ 在同層）
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, ".."))
sys.path.insert(0, _here)

from common.gemini import GeminiClient

_URL_RE = re.compile(r"https?://[^\s\"'>]+(?<![.,;:!?)'\"）。，、])")


def extract_urls(content: str) -> list[str]:
    return _URL_RE.findall(content)


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.body_texts: list[str] = []
        self._in_title = False
        self._in_body = False
        self._skip_tags = {"script", "style"}
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "body":
            self._in_body = True
        if tag == "meta":
            attrs_dict = dict(attrs)
            if attrs_dict.get("name", "").lower() == "description":
                self.description = attrs_dict.get("content", "")

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_body and self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self.body_texts.append(stripped)


def fetch_page_text(url: str) -> str | None:
    """抓取網頁 title + description + body 前 1500 字，失敗回傳 None。"""
    try:
        resp = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SharingBot/1.0)"},
        )
        if resp.status_code != 200:
            return None
        content_type = resp.headers.get("Content-Type", "")
        if "html" not in content_type:
            return None
        parser = _PageParser()
        parser.feed(resp.text)
        body_preview = " ".join(parser.body_texts)[:1500]
        parts = []
        if parser.title.strip():
            parts.append(f"Title: {parser.title.strip()}")
        if parser.description.strip():
            parts.append(f"Description: {parser.description.strip()}")
        if body_preview:
            parts.append(f"Content: {body_preview}")
        return "\n".join(parts) if parts else None
    except Exception as exc:
        log.debug("fetch_page_text failed for %s: %s", url, exc)
        return None


_EXTRACT_PROMPT = """你是餐廳資訊萃取助手。根據以下訊息，輸出一個 JSON 物件，欄位如下：
- name: 餐廳名稱（字串，必填，找不到就用訊息第一行）
- url: 餐廳網址（字串或 null）
- region: 地區，例如「台北市」「新北市」（字串或 null）
- town: 鄉鎮區，例如「大安區」「板橋區」（字串或 null）
- types: 料理類型陣列，例如 ["日式", "拉麵"]（陣列，找不到給 []）
- note: 摘要或備註（字串，找不到給 ""）
- rating: 評分數字 1-5（數字或 null）

只輸出 JSON，不要任何說明或 markdown。

訊息內容：
{content}
"""

_JSON_RE = re.compile(r"\{[\s\S]*\}")


@dataclass
class ExtractResult:
    name: str
    url: str | None = None
    region: str | None = None
    town: str | None = None
    types: list[str] = field(default_factory=list)
    note: str = ""
    rating: float | None = None
    confidence: str = "full"  # "full" or "partial"


def extract(content: str, gemini: GeminiClient) -> ExtractResult:
    urls = extract_urls(content)
    page_parts = []
    for url in urls[:3]:
        text = fetch_page_text(url)
        if text:
            page_parts.append(f"[來自 {url}]\n{text}")

    full_content = content
    if page_parts:
        full_content += "\n\n" + "\n\n".join(page_parts)

    prompt = _EXTRACT_PROMPT.format(content=full_content)
    try:
        reply = gemini.generate(prompt, timeout=30)
        m = _JSON_RE.search(reply)
        if not m:
            raise ValueError("no JSON found")
        data = json.loads(m.group())
        return ExtractResult(
            name=str(data.get("name") or content.strip().splitlines()[0][:80]),
            url=data.get("url") or (urls[0] if urls else None),
            region=data.get("region") or None,
            town=data.get("town") or None,
            types=[str(t) for t in (data.get("types") or [])],
            note=str(data.get("note") or ""),
            rating=float(data["rating"]) if data.get("rating") is not None else None,
            confidence="full",
        )
    except Exception as exc:
        log.warning("extract failed, falling back to partial: %s", exc)
        first_line = content.strip().splitlines()[0][:80] if content.strip() else "未知餐廳"
        return ExtractResult(
            name=first_line,
            url=urls[0] if urls else None,
            note=content[:2000],
            confidence="partial",
        )
