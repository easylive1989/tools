# Sharing Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `sharing/` 建立一個 Discord bot，監聽指定頻道，自動以 Gemini 解析使用者貼上的餐廳資訊，寫入 Notion 資料庫「吃什麼」。

**Architecture:** 三個模組各司其職：`extractor.py` 負責 URL 偵測、網頁抓取與 Gemini 解析；`notion_writer.py` 負責將解析結果轉為 Notion properties 並寫入；`bot.py` 是 Discord 事件 loop，串接兩者。`common/notion.py` 與 `common/gemini.py` 從 repo root 或 VPS 上的同層 `common/` 引用。

**Tech Stack:** Python 3.12, discord.py 2.3, requests, google-generativeai, common.NotionApi, common.GeminiClient, pytest, unittest.mock

---

## File Map

| 路徑 | 職責 |
|---|---|
| `sharing/extractor.py` | URL 偵測、網頁抓取、Gemini 解析、fallback |
| `sharing/notion_writer.py` | ExtractResult → Notion properties → API 呼叫 |
| `sharing/bot.py` | Discord bot，on_message → extractor → writer → reaction |
| `sharing/requirements.txt` | 依賴宣告 |
| `sharing/deploy.sh` | 本機部署腳本 |
| `sharing/tests/test_extractor.py` | extractor 單元測試 |
| `sharing/tests/test_notion_writer.py` | notion_writer 單元測試 |

---

## Task 1: 建立專案骨架與依賴

**Files:**
- Create: `sharing/requirements.txt`
- Create: `sharing/tests/__init__.py`

- [ ] **Step 1: 建立 requirements.txt**

```
discord.py>=2.3
requests>=2.31
google-generativeai>=0.8
tenacity>=8.0
pytest>=8
```

- [ ] **Step 2: 建立 tests 目錄**

```bash
mkdir -p sharing/tests
touch sharing/tests/__init__.py
```

- [ ] **Step 3: 確認本機 Python 能安裝依賴**

```bash
cd sharing
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Expected: 安裝成功，無 error。

- [ ] **Step 4: Commit**

```bash
git add sharing/requirements.txt sharing/tests/__init__.py
git commit -m "feat(sharing): scaffold project structure"
```

---

## Task 2: extractor.py — URL 偵測與網頁抓取

**Files:**
- Create: `sharing/extractor.py`
- Create: `sharing/tests/test_extractor.py`

- [ ] **Step 1: 寫 URL 偵測的失敗測試**

新增 `sharing/tests/test_extractor.py`：

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from extractor import extract_urls, fetch_page_text


def test_extract_urls_finds_https():
    urls = extract_urls("去這家！https://www.google.com 很好吃")
    assert urls == ["https://www.google.com"]


def test_extract_urls_finds_multiple():
    urls = extract_urls("https://a.com 和 https://b.com/path?q=1")
    assert urls == ["https://a.com", "https://b.com/path?q=1"]


def test_extract_urls_empty():
    assert extract_urls("沒有網址的訊息") == []
```

- [ ] **Step 2: 確認測試失敗**

```bash
cd sharing && .venv/bin/pytest tests/test_extractor.py::test_extract_urls_finds_https -v
```

Expected: `ModuleNotFoundError: No module named 'extractor'`

- [ ] **Step 3: 實作 `extract_urls` 與 `fetch_page_text`**

新增 `sharing/extractor.py`：

```python
import json
import os
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser

import requests

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
        self._skip_tags = {"script", "style", "head"}
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
    except Exception:
        return None
```

- [ ] **Step 4: 確認 URL 測試通過**

```bash
cd sharing && .venv/bin/pytest tests/test_extractor.py::test_extract_urls_finds_https tests/test_extractor.py::test_extract_urls_finds_multiple tests/test_extractor.py::test_extract_urls_empty -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add sharing/extractor.py sharing/tests/test_extractor.py
git commit -m "feat(sharing): add URL detection and web page fetching"
```

---

## Task 3: extractor.py — Gemini 解析與 fallback

**Files:**
- Modify: `sharing/extractor.py`（加入 `ExtractResult`, `extract`）
- Modify: `sharing/tests/test_extractor.py`（加入 Gemini 解析測試）

- [ ] **Step 1: 寫 Gemini 解析的失敗測試**

在 `sharing/tests/test_extractor.py` 末尾加入：

```python
from unittest.mock import MagicMock, patch
from extractor import extract, ExtractResult


def _make_gemini(reply: str) -> MagicMock:
    g = MagicMock()
    g.generate.return_value = reply
    return g


def test_extract_full_json():
    gemini = _make_gemini(
        '{"name":"鼎泰豐","url":"https://dtf.com","region":"台北市",'
        '"town":"大安區","types":["台式","小籠包"],"note":"必點XO醬","rating":4.5}'
    )
    with patch("extractor.fetch_page_text", return_value=None):
        result = extract("https://dtf.com 鼎泰豐超讚", gemini)
    assert result.name == "鼎泰豐"
    assert result.region == "台北市"
    assert result.town == "大安區"
    assert result.types == ["台式", "小籠包"]
    assert result.rating == 4.5
    assert result.confidence == "full"


def test_extract_partial_fallback_on_bad_json():
    gemini = _make_gemini("抱歉我無法解析這個")
    with patch("extractor.fetch_page_text", return_value=None):
        result = extract("https://example.com 好吃的餐廳", gemini)
    assert result.confidence == "partial"
    assert result.url == "https://example.com"
    assert "好吃的餐廳" in result.note


def test_extract_no_url():
    gemini = _make_gemini('{"name":"某餐廳","url":null,"region":null,"town":null,"types":[],"note":"","rating":null}')
    result = extract("某餐廳在信義區，很好吃", gemini)
    assert result.name == "某餐廳"
    assert result.url is None
    assert result.confidence == "full"
```

- [ ] **Step 2: 確認測試失敗**

```bash
cd sharing && .venv/bin/pytest tests/test_extractor.py::test_extract_full_json -v
```

Expected: `ImportError: cannot import name 'extract' from 'extractor'`

- [ ] **Step 3: 實作 `ExtractResult` 與 `extract`**

在 `sharing/extractor.py` 末尾加入（`import json` 已在 Task 2 的檔案裡，不需重複）：

```python
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
    url: str | None
    region: str | None
    town: str | None
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
    except Exception:
        first_line = content.strip().splitlines()[0][:80] if content.strip() else "未知餐廳"
        return ExtractResult(
            name=first_line,
            url=urls[0] if urls else None,
            note=content[:2000],
            confidence="partial",
        )
```

- [ ] **Step 4: 確認所有 extractor 測試通過**

```bash
cd sharing && .venv/bin/pytest tests/test_extractor.py -v
```

Expected: 全部 PASSED（6 個測試）

- [ ] **Step 5: Commit**

```bash
git add sharing/extractor.py sharing/tests/test_extractor.py
git commit -m "feat(sharing): add Gemini extraction with fallback"
```

---

## Task 4: notion_writer.py

**Files:**
- Create: `sharing/notion_writer.py`
- Create: `sharing/tests/test_notion_writer.py`

- [ ] **Step 1: 寫 properties 建構的失敗測試**

新增 `sharing/tests/test_notion_writer.py`：

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from extractor import ExtractResult
from notion_writer import build_properties


def test_build_properties_full():
    result = ExtractResult(
        name="鼎泰豐",
        url="https://dtf.com",
        region="台北市",
        town="大安區",
        types=["台式", "小籠包"],
        note="必點XO醬",
        rating=4.5,
        confidence="full",
    )
    props = build_properties(result)
    assert props["Name"] == {"title": [{"text": {"content": "鼎泰豐"}}]}
    assert props["連結"] == {"url": "https://dtf.com"}
    assert props["地區"] == {"select": {"name": "台北市"}}
    assert props["鄉鎮"] == {"select": {"name": "大安區"}}
    assert props["類型"] == {"multi_select": [{"name": "台式"}, {"name": "小籠包"}]}
    assert props["Note"] == {"rich_text": [{"text": {"content": "必點XO醬"}}]}
    assert props["評級"] == {"number": 4.5}
    assert "吃過" not in props  # 不預設寫入，讓 Notion 用 DB 預設值


def test_build_properties_partial_no_rating():
    result = ExtractResult(
        name="某餐廳",
        url=None,
        region=None,
        town=None,
        types=[],
        note="原始訊息",
        rating=None,
        confidence="partial",
    )
    props = build_properties(result)
    assert props["Name"] == {"title": [{"text": {"content": "某餐廳"}}]}
    assert "連結" not in props
    assert "地區" not in props
    assert "鄉鎮" not in props
    assert props["類型"] == {"multi_select": []}
    assert "評級" not in props


def test_build_properties_note_truncated():
    result = ExtractResult(
        name="x", url=None, region=None, town=None,
        types=[], note="a" * 3000, rating=None, confidence="partial"
    )
    props = build_properties(result)
    # Notion rich_text 單欄位限 2000 字
    content = props["Note"]["rich_text"][0]["text"]["content"]
    assert len(content) <= 2000
```

- [ ] **Step 2: 確認測試失敗**

```bash
cd sharing && .venv/bin/pytest tests/test_notion_writer.py::test_build_properties_full -v
```

Expected: `ModuleNotFoundError: No module named 'notion_writer'`

- [ ] **Step 3: 實作 `notion_writer.py`**

新增 `sharing/notion_writer.py`：

```python
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, ".."))
sys.path.insert(0, _here)

from common.notion import NotionApi
from extractor import ExtractResult

DB_ID = "974f5e43cac84f818fe23f35e463286b"


def build_properties(result: ExtractResult) -> dict:
    props: dict = {}
    props["Name"] = {"title": [{"text": {"content": result.name}}]}
    if result.url:
        props["連結"] = {"url": result.url}
    if result.region:
        props["地區"] = {"select": {"name": result.region}}
    if result.town:
        props["鄉鎮"] = {"select": {"name": result.town}}
    props["類型"] = {"multi_select": [{"name": t} for t in result.types]}
    note = result.note[:2000]
    props["Note"] = {"rich_text": [{"text": {"content": note}}]}
    if result.rating is not None:
        props["評級"] = {"number": result.rating}
    return props


def write(result: ExtractResult, notion: NotionApi) -> None:
    properties = build_properties(result)
    resp = notion.create_page(DB_ID, properties)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Notion API error {resp.status_code}: {resp.text[:200]}")
```

- [ ] **Step 4: 確認所有 notion_writer 測試通過**

```bash
cd sharing && .venv/bin/pytest tests/test_notion_writer.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add sharing/notion_writer.py sharing/tests/test_notion_writer.py
git commit -m "feat(sharing): add Notion writer with property builder"
```

---

## Task 5: bot.py — Discord bot 主體

**Files:**
- Create: `sharing/bot.py`

（bot 整合 Discord 事件 loop，不做 unit test，部署後用實際頻道驗證）

- [ ] **Step 1: 建立 `sharing/bot.py`**

```python
import asyncio
import logging
import os
import sys

import discord

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, ".."))
sys.path.insert(0, _here)

from common.gemini import GeminiClient
from common.notion import NotionApi
from extractor import extract
from notion_writer import write

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

REACTION_OK = "✅"
REACTION_PARTIAL = "🔖"
REACTION_ERROR = "❌"


class SharingBot(discord.Client):
    def __init__(self, channel_id: int, gemini: GeminiClient, notion: NotionApi):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        super().__init__(intents=intents)
        self.channel_id = channel_id
        self.gemini = gemini
        self.notion = notion

    async def on_ready(self) -> None:
        log.info("sharing bot ready, watching channel %s", self.channel_id)

    async def on_message(self, msg: discord.Message) -> None:
        if msg.author.bot:
            return
        if msg.channel.id != self.channel_id:
            return
        if not msg.content.strip():
            return

        log.info("processing message %s from %s", msg.id, msg.author)
        try:
            result = extract(msg.content, self.gemini)
            write(result, self.notion)
            reaction = REACTION_OK if result.confidence == "full" else REACTION_PARTIAL
            await msg.add_reaction(reaction)
            log.info("saved %r (confidence=%s)", result.name, result.confidence)
        except Exception as e:
            log.exception("failed to process message %s", msg.id)
            await msg.add_reaction(REACTION_ERROR)
            try:
                await msg.reply(f"❌ 儲存失敗：{str(e)[:200]}")
            except discord.HTTPException:
                pass


async def main() -> None:
    token = os.environ["CLAW_DISCORD_TOKEN"]
    channel_id = int(os.environ["SHARING_CHANNEL_ID"])
    notion_secret = os.environ["NOTION_SECRET"]
    google_api_key = os.environ.get("GOOGLE_API_KEY", "")

    if not google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is required")

    gemini = GeminiClient(model_name="flash")
    notion = NotionApi(notion_secret)
    bot = SharingBot(channel_id, gemini, notion)

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 確認語法無誤**

```bash
cd sharing && .venv/bin/python -c "import bot; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 執行全部測試確認沒有 regression**

```bash
cd sharing && .venv/bin/pytest tests/ -v
```

Expected: 全部 PASSED（9 個測試）

- [ ] **Step 4: Commit**

```bash
git add sharing/bot.py
git commit -m "feat(sharing): add Discord bot main entry point"
```

---

## Task 6: deploy.sh 與 systemd service

**Files:**
- Create: `sharing/deploy.sh`

- [ ] **Step 1: 建立 `sharing/deploy.sh`**

```bash
#!/usr/bin/env bash
set -e

VPS=root@178.104.240.236

echo "==> 同步程式碼到 VPS..."
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  sharing/ $VPS:/opt/sharing/
rsync -av --exclude='__pycache__' --exclude='*.pyc' \
  common/ $VPS:/opt/sharing/common/

echo "==> 在 VPS 安裝依賴..."
ssh $VPS "
  cd /opt/sharing
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
"

echo "==> 設定 systemd service（首次執行）..."
ssh $VPS "
  if [ ! -f /etc/systemd/system/sharing-bot.service ]; then
    cat > /etc/systemd/system/sharing-bot.service << 'EOF'
[Unit]
Description=Sharing Bot - Discord Restaurant Collector
After=network.target

[Service]
EnvironmentFile=/etc/sharing-bot.env
WorkingDirectory=/opt/sharing
ExecStart=/opt/sharing/.venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable sharing-bot
    echo 'service created and enabled'
  else
    echo 'service already exists, skipping'
  fi
"

echo "==> 重啟服務..."
ssh $VPS "systemctl restart sharing-bot && sleep 2 && systemctl status sharing-bot --no-pager"
```

- [ ] **Step 2: 給予執行權限並確認語法**

```bash
chmod +x sharing/deploy.sh
bash -n sharing/deploy.sh && echo "syntax OK"
```

Expected: `syntax OK`

- [ ] **Step 3: 在 VPS 建立 `/etc/sharing-bot.env`**

SSH 進 VPS 手動建立（含真實值）：

```bash
ssh root@178.104.240.236
cat > /etc/sharing-bot.env << 'EOF'
CLAW_DISCORD_TOKEN=你的token
SHARING_CHANNEL_ID=你的頻道ID
NOTION_SECRET=你的notion_secret
GOOGLE_API_KEY=你的google_api_key
EOF
chmod 600 /etc/sharing-bot.env
exit
```

- [ ] **Step 4: 執行部署**

```bash
./sharing/deploy.sh
```

Expected: 最後輸出 `Active: active (running)`

- [ ] **Step 5: Commit**

```bash
git add sharing/deploy.sh
git commit -m "feat(sharing): add deploy script and systemd service"
```

---

## Task 7: 端對端驗證

- [ ] **Step 1: 在目標 Discord 頻道貼一個餐廳 URL**

貼入類似：
```
https://www.ichiran.com/tw/ 一蘭拉麵，必吃！
```

Expected：bot 在訊息上加 ✅ reaction，Notion「吃什麼」資料庫新增一筆含名稱、URL、類型的記錄。

- [ ] **Step 2: 測試 fallback — 貼一段純文字（無 URL）**

```
某家超好吃的炸雞店，在台北大安區忠孝東路四段
```

Expected：bot 加 🔖 reaction，Notion 新增一筆，name 為第一行文字，note 為全文。

- [ ] **Step 3: 查看 VPS logs 確認無 exception**

```bash
ssh root@178.104.240.236 "journalctl -u sharing-bot -n 50 --no-pager"
```

Expected: 看到兩筆 `saved "..." (confidence=...)` log，無 ERROR 行。

- [ ] **Step 4: Commit（若有任何修正）**

```bash
git add -p
git commit -m "fix(sharing): <描述修正內容>"
```
