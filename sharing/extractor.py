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

_URL_RE = re.compile(r"https?://[^\s\"'>]+")


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
