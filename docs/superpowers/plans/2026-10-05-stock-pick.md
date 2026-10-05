# Stock Pick Logger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用者在 Discord 頻道貼智選股截圖後，5 分鐘內把截圖中的股票（代號、官方收盤價、選股日期）寫進 Notion「智選股當天入場」。

**Architecture:** oracle-arm VPS 上的 systemd timer 每 5 分鐘執行 `stock_pick/runner.py`。runner 用共用的 `common/discord.py` 輪詢頻道，用 `reader.py`（Codex CLI）讀出股票名稱，再用 `quotes.py`（TWSE／TPEx 官方行情）查代號與收盤價，最後交給 `notion_writer.py` 查重並寫入。部署方式與 `calorie_log` 相同。

**Tech Stack:** Python 3.10+、`requests`、Codex CLI（`gpt-5.6-terra`）、Notion API `2025-09-03`、Discord REST API v10、systemd、GitHub Actions、pytest。

**Spec:** `docs/superpowers/specs/2026-10-05-stock-pick-design.md`

## Global Constraints

- Discord 頻道：`1556684804731179070`；時區：`Asia/Taipei`。
- Notion data source：`3ea8303f-78f7-801f-9742-000b47c34230`，API 版本 `2025-09-03`。
- Notion `Name` 格式：`代號 官方名稱`，例如 `3293 鈊象`、`7731 火星生技*`。`備註` 不寫入。
- Codex：`gpt-5.6-terra`，`model_reasoning_effort=medium`（low 會讀錯罕見字），`--sandbox read-only`。子行程環境變數要移除 `DISCORD_BOT_TOKEN`、`NOTION_SECRET`。
- 執行期依賴只有 `requests>=2.31,<3`；測試另裝 `pytest`。
- 測試一律在 repo 根目錄用 `python3 -m pytest` 執行。測試檔名要全 repo 唯一（不加 `__init__.py`，避免和其他工具的 `tests/` 撞名）。
- 使用者看得到的訊息（Discord 回覆、錯誤）用繁體中文，程式識別字用英文。
- 不得 commit secret（token、webhook、VPS IP）。不得 commit 根目錄的 `IMG_8812.jpeg`；`git add` 一律列出明確路徑。
- 每個 commit 訊息結尾加上 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。

## Review Focus

1. Codex 讀出的名稱夾雜半形或全形空白（`群益 證`、`群益　證`）時，仍要對到官方名稱 → Task 2 `test_match_ignores_whitespace_and_reports_missing_names`。
2. 台灣時間午夜過後才貼圖（UTC 仍是前一天）時，選股日期要用台灣日期 → Task 6 `test_pick_day_uses_taipei_date_after_midnight`。
3. 當天沒成交的股票（上市收盤價 `--`、興櫃 `LatestPrice` 空字串）要列為找不到，不能寫入 0 或空值 → Task 2 `test_parse_twse_reads_the_closing_table_and_cleans_names`、`test_parse_tpex_returns_latest_day_and_quotes` 與 match 測試。
4. 截圖頂端被裁切的指數列（`加權指`）或 `櫃買指數`，要直接丟掉，不能被當成「找不到的股票」回報 → Task 3 `test_clean_names_drops_indexes_blanks_and_duplicates`。
5. 同一則訊息的兩張截圖有重疊（往下捲動時重複的列），同一檔只能寫一次 → Task 3 去重測試，加上 Task 4 的 Notion 查重測試。

---

## 任務總覽

| Task | 內容 | 依賴 |
|---|---|---|
| 1 | 驗證前提：bot、Notion、官方行情、Codex 登入 | — |
| 2 | 官方行情 `stock_pick/quotes.py` | — |
| 3 | 讀圖 `stock_pick/reader.py` | — |
| 4 | Notion 寫入 `stock_pick/notion_writer.py` | Task 2（`Quote`） |
| 5 | 共用 Discord client `common/discord.py` | — |
| 6 | 主流程 `stock_pick/runner.py` | Task 2–5 |
| 7 | 部署腳本、workflow、文件 | Task 6 |
| 8 | 上線與實機驗證（需要 merge 到 master） | Task 1、7 |

---

### Task 1: 驗證前提

不寫程式。確認 VPS 上現有的 bot token 與 Notion secret 有權限，VPS 連得到官方行情，Codex 也已登入。任何一項失敗，都要先處理再做 Task 8。

**Files:** 無

- [ ] **Step 1: Bot 能讀頻道、有需要的權限**

`/opt/calorie-log/.env` 裡的 token 與 GitHub secret 是同一組。指令只印狀態碼與權限布林值，不印出 token。

```bash
ssh oracle-arm 'set -a; . /opt/calorie-log/.env; set +a
curl -s -o /dev/null -w "read messages: %{http_code}\n" -H "Authorization: Bot $DISCORD_BOT_TOKEN" "https://discord.com/api/v10/channels/1556684804731179070/messages?limit=1"
curl -s -H "Authorization: Bot $DISCORD_BOT_TOKEN" https://discord.com/api/v10/users/@me/guilds | python3 -c "import sys, json; g = [x for x in json.load(sys.stdin) if x[\"id\"] == \"1404465385058598972\"]; p = int(g[0][\"permissions\"]) if g else 0; print(\"in guild:\", bool(g), \"admin:\", bool(p & 8), \"add reactions:\", bool(p & 64), \"send:\", bool(p & 2048), \"history:\", bool(p & 65536))"'
```

Expected: `read messages: 200`，`in guild: True`，而且 `admin` 為 True，或 `add reactions`、`send`、`history` 三者都是 True。
失敗時：請使用者把 bot 邀請進該伺服器，並在頻道權限開啟「讀取訊息歷史、新增反應、傳送訊息」。

- [ ] **Step 2: Notion integration 能讀寫「智選股當天入場」**

```bash
ssh oracle-arm 'set -a; . /opt/calorie-log/.env; set +a
curl -s -o /dev/null -w "notion query: %{http_code}\n" -X POST -H "Authorization: Bearer $NOTION_SECRET" -H "Notion-Version: 2025-09-03" -H "Content-Type: application/json" -d "{\"page_size\":1}" https://api.notion.com/v1/data_sources/3ea8303f-78f7-801f-9742-000b47c34230/query'
```

Expected: `notion query: 200`
失敗時（404／403）：請使用者在 Notion 打開「智選股當天入場」，從右上角「⋯ → Connections」加入 `NOTION_SECRET` 對應的 integration。

- [ ] **Step 3: VPS 連得到三個官方行情**

```bash
ssh oracle-arm 'for u in "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20261005&response=json&type=ALLBUT0999" https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics; do curl -s -o /dev/null -w "%{http_code} $u\n" -A "Mozilla/5.0" "$u"; done'
```

Expected: 三行都是 `200`。
失敗時：記下狀態碼，回報使用者。設計假設 VPS 能直連官方行情，這點不成立就得改設計。

- [ ] **Step 4: Codex CLI 已登入**

```bash
ssh oracle-arm 'codex login status'
```

Expected: 顯示已登入（exit 0）。

- [ ] **Step 5: 回報結果**

把四項結果整理給使用者，不需要 commit。

---

### Task 2: 官方行情 `stock_pick/quotes.py`

**Files:**
- Create: `stock_pick/quotes.py`
- Test: `stock_pick/tests/test_stock_quotes.py`

**Interfaces:**
- Consumes: 無
- Produces:
  - `Quote(code: str, name: str, market: str, price: float | None)`：frozen dataclass，`name` 已去除空白，`market` 為 `上市`／`上櫃`／`興櫃`
  - `MarketQuotes(days: dict[str, date | None], by_name: dict[str, Quote])`：frozen dataclass
  - `READY`, `WAITING`, `PASSED`：字串常數
  - `normalize_name(name: object) -> str`
  - `fetch_quotes(day: date) -> MarketQuotes`
  - `quote_status(days: dict[str, date | None], day: date) -> str`：回傳 `READY`／`WAITING`／`PASSED`
  - `match(names: list[str], by_name: dict[str, Quote]) -> tuple[list[Quote], list[str]]`：（有價格的 quotes，找不到或無成交價的原始名稱）

- [ ] **Step 1: 寫失敗的測試**

`stock_pick/tests/test_stock_quotes.py`：

```python
from datetime import date
from unittest.mock import patch

import pytest

from stock_pick.quotes import (
    PASSED, READY, TPEX_OTC, TWSE_DAILY, WAITING, Quote, fetch_quotes, match,
    parse_tpex, parse_twse, quote_status, roc_date,
)

DAY = date(2026, 10, 5)
TWSE_PAYLOAD = {
    "stat": "OK",
    "date": "20261005",
    "tables": [
        {"fields": ["指數", "收盤指數"], "data": [["發行量加權股價指數", "49,712.04"]]},
        {"fields": ["證券代號", "證券名稱", "成交股數", "收盤價"], "data": [
            ["1477", "聚陽", "1,000", "197.50"],
            ["2485", "兆赫  ", "2,000", "44.60"],
            ["9999", "停牌股", "0", "--"],
            ["2330", "台積電", "9,000", "1,234.50"],
        ]},
    ],
}
OTC_ROWS = [
    {"Date": "1151005", "SecuritiesCompanyCode": "3293", "CompanyName": "鈊象", "Close": "794.00"},
    {"Date": "1151005", "SecuritiesCompanyCode": "5452", "CompanyName": "佶優", "Close": "30.00"},
]
ESB_ROWS = [
    {"Date": "1151005", "SecuritiesCompanyCode": "7731", "CompanyName": "火星生技*", "LatestPrice": "4.51"},
    {"Date": "1151005", "SecuritiesCompanyCode": "1260", "CompanyName": "富味鄉", "LatestPrice": ""},
]


def test_roc_date_converts_minguo_year():
    assert roc_date("1151005") == date(2026, 10, 5)
    assert roc_date("991231") == date(2010, 12, 31)


def test_parse_twse_reads_the_closing_table_and_cleans_names():
    quotes = {quote.name: quote for quote in parse_twse(TWSE_PAYLOAD, DAY)}
    assert quotes["兆赫"] == Quote("2485", "兆赫", "上市", 44.6)
    assert quotes["台積電"].price == 1234.5
    assert quotes["停牌股"].price is None


def test_parse_twse_returns_none_when_the_day_is_not_published():
    assert parse_twse({"stat": "很抱歉，沒有符合條件的資料!"}, DAY) is None


def test_parse_twse_rejects_a_different_day():
    with pytest.raises(ValueError, match="日期不符"):
        parse_twse({**TWSE_PAYLOAD, "date": "20261002"}, DAY)


def test_parse_tpex_returns_latest_day_and_quotes():
    day, quotes = parse_tpex(ESB_ROWS, "興櫃", "LatestPrice")
    assert day == DAY
    assert quotes[0] == Quote("7731", "火星生技*", "興櫃", 4.51)
    assert quotes[1].price is None


def test_fetch_quotes_merges_three_markets():
    def fake_get(url, params=None):
        if url == TWSE_DAILY:
            assert params["date"] == "20261005"
            return TWSE_PAYLOAD
        return OTC_ROWS if url == TPEX_OTC else ESB_ROWS

    with patch("stock_pick.quotes._get_json", side_effect=fake_get):
        quotes = fetch_quotes(DAY)

    assert quotes.days == {"上市": DAY, "上櫃": DAY, "興櫃": DAY}
    assert quotes.by_name["聚陽"] == Quote("1477", "聚陽", "上市", 197.5)
    assert quotes.by_name["鈊象"].market == "上櫃"
    assert quotes.by_name["火星生技*"].code == "7731"


def test_fetch_quotes_marks_unpublished_twse_day_as_none():
    def fake_get(url, params=None):
        if url == TWSE_DAILY:
            return {"stat": "很抱歉，沒有符合條件的資料!"}
        return OTC_ROWS if url == TPEX_OTC else ESB_ROWS

    with patch("stock_pick.quotes._get_json", side_effect=fake_get):
        assert fetch_quotes(DAY).days["上市"] is None


@pytest.mark.parametrize(("days", "expected"), [
    ({"上市": DAY, "上櫃": DAY, "興櫃": DAY}, READY),
    ({"上市": None, "上櫃": DAY, "興櫃": DAY}, WAITING),
    ({"上市": DAY, "上櫃": date(2026, 10, 2), "興櫃": DAY}, WAITING),
    ({"上市": None, "上櫃": date(2026, 10, 6), "興櫃": date(2026, 10, 6)}, PASSED),
])
def test_quote_status(days, expected):
    assert quote_status(days, DAY) == expected


def test_match_ignores_whitespace_and_reports_missing_names():
    by_name = {
        "群益證": Quote("6005", "群益證", "上市", 33.0),
        "富味鄉": Quote("1260", "富味鄉", "興櫃", None),
    }
    found, missing = match(["群益 證", "群益　證", "富味鄉", "鈊像"], by_name)
    assert found == [Quote("6005", "群益證", "上市", 33.0)] * 2
    assert missing == ["富味鄉", "鈊像"]
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python3 -m pytest stock_pick/tests/test_stock_quotes.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'stock_pick.quotes'`

- [ ] **Step 3: 實作**

`stock_pick/quotes.py`：

```python
"""Official Taiwan stock quotes: 上市 (TWSE), 上櫃 and 興櫃 (TPEx).

The screenshot only tells us which stocks were picked; codes and prices always
come from here. 興櫃 has no official close, so its latest trade price stands in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import requests

TWSE_DAILY = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_OTC = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
TPEX_ESB = "https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics"
HEADERS = {"User-Agent": "Mozilla/5.0 (stock-pick-logger)", "Accept": "application/json"}

READY, WAITING, PASSED = "ready", "waiting", "passed"


@dataclass(frozen=True)
class Quote:
    code: str
    name: str
    market: str
    price: float | None


@dataclass(frozen=True)
class MarketQuotes:
    days: dict[str, date | None]
    by_name: dict[str, Quote]


def normalize_name(name: object) -> str:
    """Drop every kind of whitespace, including full-width spaces."""
    return "".join(str(name).split())


def to_price(value: object) -> float | None:
    try:
        number = float(str(value).replace(",", "").strip())
    except ValueError:
        return None
    return number if number > 0 else None


def roc_date(value: object) -> date:
    found = re.fullmatch(r"(\d{2,3})(\d{2})(\d{2})", str(value).strip())
    if not found:
        raise ValueError(f"無法解析民國日期：{value!r}")
    return date(int(found[1]) + 1911, int(found[2]), int(found[3]))


def parse_twse(payload: object, day: date) -> list[Quote] | None:
    """Return 上市 quotes for `day`, or None when TWSE has nothing for it (yet)."""
    if not isinstance(payload, dict) or str(payload.get("stat")).upper() != "OK":
        return None
    if str(payload.get("date")) != f"{day:%Y%m%d}":
        raise ValueError(f"上市行情日期不符：要 {day}，拿到 {payload.get('date')}")
    for table in payload.get("tables") or []:
        fields = [str(field).strip() for field in table.get("fields") or []]
        if {"證券代號", "證券名稱", "收盤價"} <= set(fields) and table.get("data"):
            code_at = fields.index("證券代號")
            name_at = fields.index("證券名稱")
            price_at = fields.index("收盤價")
            return [
                Quote(str(row[code_at]).strip(), normalize_name(row[name_at]), "上市",
                      to_price(row[price_at]))
                for row in table["data"]
            ]
    raise ValueError(f"{day} 的上市行情裡找不到收盤行情表")


def parse_tpex(rows: object, market: str, price_key: str) -> tuple[date | None, list[Quote]]:
    """Return (quote day, quotes) from a TPEx openapi list, which only serves the latest day."""
    if not isinstance(rows, list):
        raise ValueError(f"{market}行情格式不正確")
    if not rows:
        return None, []
    day = max(roc_date(row["Date"]) for row in rows)
    quotes = [
        Quote(str(row["SecuritiesCompanyCode"]).strip(), normalize_name(row["CompanyName"]),
              market, to_price(row.get(price_key)))
        for row in rows if roc_date(row["Date"]) == day
    ]
    return day, quotes


def fetch_quotes(day: date) -> MarketQuotes:
    twse = parse_twse(_get_json(TWSE_DAILY, {
        "date": f"{day:%Y%m%d}", "response": "json", "type": "ALLBUT0999",
    }), day)
    otc_day, otc = parse_tpex(_get_json(TPEX_OTC), "上櫃", "Close")
    esb_day, esb = parse_tpex(_get_json(TPEX_ESB), "興櫃", "LatestPrice")
    by_name: dict[str, Quote] = {}
    for quote in [*(twse or []), *otc, *esb]:
        by_name.setdefault(quote.name, quote)
    return MarketQuotes(
        days={"上市": day if twse is not None else None, "上櫃": otc_day, "興櫃": esb_day},
        by_name=by_name,
    )


def quote_status(days: dict[str, date | None], day: date) -> str:
    known = [value for value in days.values() if value is not None]
    if any(value > day for value in known):
        return PASSED
    if len(known) == len(days) and all(value == day for value in known):
        return READY
    return WAITING


def match(names: list[str], by_name: dict[str, Quote]) -> tuple[list[Quote], list[str]]:
    """Split names into quotes with a price and the names that have none."""
    found: list[Quote] = []
    missing: list[str] = []
    for name in names:
        quote = by_name.get(normalize_name(name))
        if quote is None or quote.price is None:
            missing.append(name)
        else:
            found.append(quote)
    return found, missing


def _get_json(url: str, params: dict | None = None) -> object:
    response = requests.get(url, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python3 -m pytest stock_pick/tests/test_stock_quotes.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 用真實行情做 smoke check**

用最近一個已收盤的交易日（例如今天收盤後跑，就填今天）：

```bash
python3 -c "from datetime import date; from stock_pick.quotes import fetch_quotes; q = fetch_quotes(date(2026, 10, 5)); print(q.days, len(q.by_name)); print([q.by_name.get(n) for n in ['聚陽', '鈊象', '火星生技*']])"
```

Expected：`days` 三個市場都有日期（TPEx 只提供最新一天，日期可能比填的晚），`by_name` 超過 3000 筆，三檔都查得到代號。

- [ ] **Step 6: Commit**

```bash
git add stock_pick/quotes.py stock_pick/tests/test_stock_quotes.py
git commit -m "$(cat <<'EOF'
feat(stock_pick): look up official closing quotes by stock name

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 讀圖 `stock_pick/reader.py`

**Files:**
- Create: `stock_pick/reader.py`
- Test: `stock_pick/tests/test_stock_reader.py`

**Interfaces:**
- Consumes: 無
- Produces:
  - `SUPPORTED_EXTENSIONS: set[str]` = `{".jpg", ".jpeg", ".png", ".webp"}`
  - `clean_names(names: list[object]) -> list[str]`：去空白、丟掉指數、去重，保留順序
  - `read_names(images: list[Path], *, timeout: int = 180) -> list[str]`：回傳已 `clean_names` 的名稱；Codex 失敗時 raise `RuntimeError`，圖片不合法時 raise `ValueError`

- [ ] **Step 1: 寫失敗的測試**

`stock_pick/tests/test_stock_reader.py`：

```python
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from stock_pick.reader import clean_names, read_names

ENV = {"DISCORD_BOT_TOKEN": "discord-secret", "NOTION_SECRET": "notion-secret",
       "CODEX_CLI_PATH": "/usr/local/bin/codex"}


def fake_codex(output, captured, returncode=0):
    def run(command, **kwargs):
        captured["command"] = command
        captured["prompt"] = kwargs["input"]
        captured["env"] = kwargs["env"]
        Path(command[command.index("--output-last-message") + 1]).write_text(output, encoding="utf-8")
        return type("Result", (), {"returncode": returncode})()
    return run


def images_in(tmp_path, *names):
    paths = [tmp_path / name for name in names]
    for path in paths:
        path.write_bytes(b"image")
    return paths


def test_clean_names_drops_indexes_blanks_and_duplicates():
    names = ["加權指", "鈊象", "火星生技 *", "", "櫃買指數", "鈊象", "群益證"]
    assert clean_names(names) == ["鈊象", "火星生技*", "群益證"]


def test_read_names_sends_every_image_to_codex(tmp_path):
    images = images_in(tmp_path, "a.png", "b.jpg")
    captured = {}
    output = json.dumps({"names": ["加權指", "鈊象", "火星生技*", "鈊象"]})
    with patch.dict("stock_pick.reader.os.environ", ENV), \
         patch("stock_pick.reader.subprocess.run", side_effect=fake_codex(output, captured)):
        assert read_names(images) == ["鈊象", "火星生技*"]

    command = captured["command"]
    sent = [command[i + 1] for i, part in enumerate(command) if part == "--image"]
    assert sent == [str(image.resolve()) for image in images]
    assert command[command.index("--model") + 1] == "gpt-5.6-terra"
    assert command[command.index("--config") + 1] == "model_reasoning_effort=low"
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "保留名稱後面的「*」" in captured["prompt"]
    assert "DISCORD_BOT_TOKEN" not in captured["env"]
    assert "NOTION_SECRET" not in captured["env"]


def test_read_names_rejects_malformed_codex_output(tmp_path):
    with patch.dict("stock_pick.reader.os.environ", ENV), \
         patch("stock_pick.reader.subprocess.run", side_effect=fake_codex("not json", {})):
        with pytest.raises(RuntimeError, match="格式不正確"):
            read_names(images_in(tmp_path, "a.png"))


def test_read_names_reports_codex_failure(tmp_path):
    with patch.dict("stock_pick.reader.os.environ", ENV), \
         patch("stock_pick.reader.subprocess.run", side_effect=fake_codex("", {}, returncode=1)):
        with pytest.raises(RuntimeError, match="讀取截圖失敗"):
            read_names(images_in(tmp_path, "a.png"))


def test_read_names_rejects_unsupported_images(tmp_path):
    with pytest.raises(ValueError, match="不支援的圖片格式"):
        read_names(images_in(tmp_path, "a.heic"))
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python3 -m pytest stock_pick/tests/test_stock_reader.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'stock_pick.reader'`

- [ ] **Step 3: 實作**

`stock_pick/reader.py`：

```python
"""Read stock names from stock-app watchlist screenshots with the local Codex CLI."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

MODEL = "gpt-5.6-terra"
REASONING_EFFORT = "low"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
# The index row is often cropped at the top of the screenshot (「加權指」).
INDEX_NAME = re.compile(r"指數?$")
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["names"],
    "properties": {"names": {"type": "array", "items": {"type": "string"}}},
}
INSTRUCTIONS = """這些圖片是台股看盤 App「自選」頁的截圖，每一列是一檔股票。
依截圖順序、由上到下，把每一列的股票名稱放進 names。
- 名稱照圖上的字原樣抄寫，保留名稱後面的「*」。名稱被折成兩行時（例如「火星生技」下一行是「*」），合併成「火星生技*」。
- 不要列出指數（例如加權指數、櫃買指數），也不要列出欄位標題、分頁或按鈕文字。
- 只要名稱，不要代號或價格。
- 截圖之間有重複的股票也照樣列出。"""


def clean_names(names: list[object]) -> list[str]:
    """Drop blanks, index rows and duplicates while keeping the screenshot order."""
    cleaned: list[str] = []
    for raw in names:
        name = "".join(str(raw).split())
        if name and not INDEX_NAME.search(name) and name not in cleaned:
            cleaned.append(name)
    return cleaned


def read_names(images: list[Path], *, timeout: int = 180) -> list[str]:
    if not images:
        raise ValueError("沒有可讀取的截圖")
    resolved = [Path(image).expanduser().resolve() for image in images]
    for image in resolved:
        if image.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支援的圖片格式：{image.suffix}")
        if not image.is_file():
            raise ValueError(f"找不到圖片：{image}")

    codex = os.environ.get("CODEX_CLI_PATH") or shutil.which(
        "codex", path="/opt/homebrew/bin:/usr/local/bin:"
        + str(Path.home() / ".local/bin") + ":" + os.environ.get("PATH", "")
    )
    if not codex:
        raise RuntimeError("找不到 codex CLI，請先安裝並登入")

    with tempfile.TemporaryDirectory(prefix="stock-pick-") as workdir:
        schema_path = Path(workdir) / "schema.json"
        output_path = Path(workdir) / "names.json"
        schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")
        command = [
            codex, "exec", "--model", MODEL, "--config", f"model_reasoning_effort={REASONING_EFFORT}",
            "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
            "--output-schema", str(schema_path), "--output-last-message", str(output_path),
            "-C", workdir,
        ]
        for image in resolved:
            command.extend(("--image", str(image)))
        command.append("-")
        child_env = {
            key: value for key, value in os.environ.items()
            if key not in {"DISCORD_BOT_TOKEN", "NOTION_SECRET"}
        }
        try:
            result = subprocess.run(
                command, input=INSTRUCTIONS, text=True, capture_output=True,
                timeout=timeout, env=child_env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Codex 讀取截圖逾時") from exc
        if result.returncode != 0:
            raise RuntimeError(f"Codex 讀取截圖失敗（exit {result.returncode}）")
        try:
            names = json.loads(output_path.read_text(encoding="utf-8"))["names"]
            if not isinstance(names, list):
                raise TypeError("names is not a list")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("Codex 回傳的股票名稱格式不正確") from exc
    return clean_names(names)
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python3 -m pytest stock_pick/tests/test_stock_reader.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 用真實截圖做 smoke check（本機已安裝 Codex）**

```bash
python3 -c "from pathlib import Path; from stock_pick.reader import read_names; print(read_names([Path('IMG_8812.jpeg')]))"
```

Expected: `['鈊象', '火星生技*', '信音', '兆赫', '佶優', '勤誠', '啟碁', '聚陽', '群益證']`
名稱有錯時，先調整 `INSTRUCTIONS` 再重跑，不要改測試期望。

- [ ] **Step 6: Commit**

```bash
git add stock_pick/reader.py stock_pick/tests/test_stock_reader.py
git commit -m "$(cat <<'EOF'
feat(stock_pick): read stock names from screenshots with Codex

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Notion 寫入 `stock_pick/notion_writer.py`

**Files:**
- Create: `stock_pick/notion_writer.py`
- Test: `stock_pick/tests/test_stock_notion_writer.py`

**Interfaces:**
- Consumes: `stock_pick.quotes.Quote(code, name, market, price)`；`common.notion.NotionApi` 的 `query_data_source(data_source_id, body)`、`create_page_in_data_source(data_source_id, properties)`（皆回傳 `requests.Response`）
- Produces:
  - `DATA_SOURCE_ID = "3ea8303f-78f7-801f-9742-000b47c34230"`
  - `build_properties(quote: Quote, day: date) -> dict`
  - `write(notion: NotionApi, quote: Quote, day: date) -> bool`：新增則回傳 True，當天已有同代號則回傳 False

- [ ] **Step 1: 寫失敗的測試**

`stock_pick/tests/test_stock_notion_writer.py`：

```python
from datetime import date
from unittest.mock import Mock

from stock_pick.notion_writer import DATA_SOURCE_ID, build_properties, write
from stock_pick.quotes import Quote

DAY = date(2026, 10, 5)
QUOTE = Quote("7731", "火星生技*", "興櫃", 4.51)


def response(payload):
    resp = Mock()
    resp.json.return_value = payload
    return resp


def test_build_properties_matches_existing_rows():
    assert build_properties(QUOTE, DAY) == {
        "Name": {"title": [{"text": {"content": "7731 火星生技*"}}]},
        "進場價格": {"number": 4.51},
        "選股日期": {"date": {"start": "2026-10-05"}},
    }


def test_write_creates_page_when_not_logged_yet():
    notion = Mock()
    notion.query_data_source.return_value = response({"results": []})

    assert write(notion, QUOTE, DAY) is True

    data_source, body = notion.query_data_source.call_args.args
    assert data_source == DATA_SOURCE_ID
    assert body["filter"]["and"] == [
        {"property": "選股日期", "date": {"equals": "2026-10-05"}},
        {"property": "Name", "title": {"starts_with": "7731 "}},
    ]
    notion.create_page_in_data_source.assert_called_once_with(
        DATA_SOURCE_ID, build_properties(QUOTE, DAY))


def test_write_skips_stock_already_logged_that_day():
    notion = Mock()
    notion.query_data_source.return_value = response({"results": [{"id": "page"}]})

    assert write(notion, QUOTE, DAY) is False
    notion.create_page_in_data_source.assert_not_called()
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python3 -m pytest stock_pick/tests/test_stock_notion_writer.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'stock_pick.notion_writer'`

- [ ] **Step 3: 實作**

`stock_pick/notion_writer.py`：

```python
"""Write matched stock picks to the Notion「智選股當天入場」data source."""

from __future__ import annotations

from datetime import date

from common.notion import NotionApi
from stock_pick.quotes import Quote

DATA_SOURCE_ID = "3ea8303f-78f7-801f-9742-000b47c34230"


def build_properties(quote: Quote, day: date) -> dict:
    return {
        "Name": {"title": [{"text": {"content": f"{quote.code} {quote.name}"}}]},
        "進場價格": {"number": quote.price},
        "選股日期": {"date": {"start": day.isoformat()}},
    }


def already_logged(notion: NotionApi, quote: Quote, day: date) -> bool:
    response = notion.query_data_source(DATA_SOURCE_ID, {
        "filter": {"and": [
            {"property": "選股日期", "date": {"equals": day.isoformat()}},
            {"property": "Name", "title": {"starts_with": f"{quote.code} "}},
        ]},
        "page_size": 1,
    })
    response.raise_for_status()
    return bool(response.json().get("results"))


def write(notion: NotionApi, quote: Quote, day: date) -> bool:
    """Create the pick unless this stock is already logged for `day`; True when created."""
    if already_logged(notion, quote, day):
        return False
    response = notion.create_page_in_data_source(DATA_SOURCE_ID, build_properties(quote, day))
    response.raise_for_status()
    return True
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python3 -m pytest stock_pick/tests/test_stock_notion_writer.py -q`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add stock_pick/notion_writer.py stock_pick/tests/test_stock_notion_writer.py
git commit -m "$(cat <<'EOF'
feat(stock_pick): write picks to Notion, skipping ones already logged

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 共用 Discord client `common/discord.py`

以 `calorie_log/discord_runner.py` 的 `DiscordClient` 為藍本，只保留這個工具需要的方法。這次不改動 `calorie_log`、`eat_later`。

**Files:**
- Create: `common/discord.py`
- Test: `common/tests/test_discord_client.py`

**Interfaces:**
- Consumes: 無
- Produces: `DiscordClient(token: str, user_agent: str = "tools-bot/1.0")`，方法如下：
  - `messages_since(channel_id: str, last_id: str) -> list[dict]`：id 大於 `last_id` 的訊息，由舊到新
  - `latest_message_id(channel_id: str) -> str | None`
  - `react(channel_id: str, message_id: str, emoji: str) -> None`
  - `reply(channel_id: str, message_id: str, content: str) -> str`：回傳新訊息 id
  - `download(url: str, destination: Path) -> Path`：只接受 Discord CDN 網址，上限 20 MiB，**不帶** bot token

- [ ] **Step 1: 寫失敗的測試**

`common/tests/test_discord_client.py`：

```python
from unittest.mock import MagicMock, Mock, patch

import pytest

from common.discord import DiscordClient


def fake_response(payload=None, status=200):
    response = Mock(status_code=status)
    response.json.return_value = payload
    return response


def test_messages_since_returns_only_newer_messages_oldest_first():
    client = DiscordClient("token")
    client.session.request = Mock(return_value=fake_response([
        {"id": "105"}, {"id": "104"}, {"id": "100"}, {"id": "99"},
    ]))
    assert [message["id"] for message in client.messages_since("1", "100")] == ["104", "105"]


def test_request_waits_out_rate_limits():
    client = DiscordClient("token")
    client.session.request = Mock(side_effect=[
        fake_response({"retry_after": 0.5}, status=429),
        fake_response([{"id": "7"}]),
    ])
    with patch("common.discord.time.sleep") as sleep:
        assert client.latest_message_id("1") == "7"
    sleep.assert_called_once_with(0.5)


def test_reply_quotes_the_original_without_pinging_anyone():
    client = DiscordClient("token")
    client.session.request = Mock(return_value=fake_response({"id": "900"}))
    assert client.reply("1", "100", "找不到") == "900"
    body = client.session.request.call_args.kwargs["json"]
    assert body["content"] == "找不到"
    assert body["message_reference"]["message_id"] == "100"
    assert body["allowed_mentions"] == {"parse": [], "replied_user": False}


def test_download_rejects_non_discord_hosts(tmp_path):
    with pytest.raises(ValueError, match="網址不正確"):
        DiscordClient("token").download("https://evil.example/a.png", tmp_path / "a.png")


def test_download_saves_attachment_without_the_bot_token(tmp_path):
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [b"abc", b"def"]
    with patch("common.discord.requests.get", return_value=response) as get:
        path = DiscordClient("token").download(
            "https://cdn.discordapp.com/attachments/1/2/a.png", tmp_path / "a.png")
    assert path.read_bytes() == b"abcdef"
    assert "headers" not in get.call_args.kwargs
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python3 -m pytest common/tests/test_discord_client.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'common.discord'`

- [ ] **Step 3: 實作**

`common/discord.py`：

```python
"""Small Discord REST client shared by the polling bots in this repo."""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

DISCORD_API = "https://discord.com/api/v10"
ATTACHMENT_HOSTS = {"cdn.discordapp.com", "media.discordapp.net", "cdn.discord.com"}
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024


class DiscordClient:
    def __init__(self, token: str, user_agent: str = "tools-bot/1.0"):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bot {token}", "User-Agent": user_agent})

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        for attempt in range(5):
            response = self.session.request(method, f"{DISCORD_API}{path}", timeout=30, **kwargs)
            if response.status_code == 429:
                time.sleep(min(float(response.json().get("retry_after", 1)), 60))
                continue
            if response.status_code >= 500 and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response
        raise RuntimeError("Discord API 持續限流，稍後再試")

    def messages_since(self, channel_id: str, last_id: str) -> list[dict]:
        """Walk backward from the newest message so a busy channel loses none."""
        messages: list[dict] = []
        before = None
        while True:
            params = {"limit": 100}
            if before:
                params["before"] = before
            batch = self.request("GET", f"/channels/{channel_id}/messages", params=params).json()
            if not batch:
                break
            messages.extend(msg for msg in batch if int(msg["id"]) > int(last_id))
            oldest = min(int(msg["id"]) for msg in batch)
            if oldest <= int(last_id) or len(batch) < 100:
                break
            before = str(oldest)
        return sorted(messages, key=lambda msg: int(msg["id"]))

    def latest_message_id(self, channel_id: str) -> str | None:
        messages = self.request("GET", f"/channels/{channel_id}/messages", params={"limit": 1}).json()
        return messages[0]["id"] if messages else None

    def react(self, channel_id: str, message_id: str, emoji: str) -> None:
        self.request(
            "PUT",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}/@me",
        )

    def reply(self, channel_id: str, message_id: str, content: str) -> str:
        response = self.request("POST", f"/channels/{channel_id}/messages", json={
            "content": content,
            "nonce": message_id,
            "enforce_nonce": True,
            "allowed_mentions": {"parse": [], "replied_user": False},
            "message_reference": {
                "message_id": message_id,
                "channel_id": channel_id,
                "fail_if_not_exists": True,
            },
        })
        return response.json()["id"]

    def download(self, url: str, destination: Path) -> Path:
        # Attachment URLs are pre-signed; plain requests keeps the bot token off the CDN.
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ATTACHMENT_HOSTS:
            raise ValueError("Discord 附件網址不正確")
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            size = 0
            with destination.open("wb") as out:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        raise ValueError("Discord 附件超過 20 MiB")
                    out.write(chunk)
        return destination
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python3 -m pytest common/tests/test_discord_client.py -q`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add common/discord.py common/tests/test_discord_client.py
git commit -m "$(cat <<'EOF'
feat(common): add a shared Discord REST client

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: 主流程 `stock_pick/runner.py`

**Files:**
- Create: `stock_pick/runner.py`
- Test: `stock_pick/tests/test_stock_runner.py`

**Interfaces:**
- Consumes:
  - `common.discord.DiscordClient`（Task 5）：`messages_since`、`latest_message_id`、`react`、`reply`、`download`
  - `common.notion.NotionApi(token, version="2025-09-03")`
  - `stock_pick.quotes`（Task 2）：`fetch_quotes`、`quote_status`、`match`、`MarketQuotes`、`WAITING`、`PASSED`
  - `stock_pick.reader`（Task 3）：`read_names`、`SUPPORTED_EXTENSIONS`
  - `stock_pick.notion_writer`（Task 4）：`write`
- Produces:
  - `run_once(now: datetime | None = None) -> None`、`main() -> int`
  - `pick_day(message: dict) -> date`
  - `CHANNEL_ID`、`STATE_PATH`、`load_state()`、`save_state(state)`
  - state 檔格式：`{"last_message_id": str | None, "attempts": {message_id: int}}`

- [ ] **Step 1: 寫失敗的測試**

`stock_pick/tests/test_stock_runner.py`：

```python
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from stock_pick import runner
from stock_pick.quotes import MarketQuotes, Quote

DAY = date(2026, 10, 5)
NOW = datetime(2026, 10, 5, 15, 30, tzinfo=timezone.utc)  # 台灣 23:30
QUOTES = MarketQuotes({"上市": DAY, "上櫃": DAY, "興櫃": DAY}, {
    "鈊象": Quote("3293", "鈊象", "上櫃", 794.0),
    "火星生技*": Quote("7731", "火星生技*", "興櫃", 4.51),
})
NOT_PUBLISHED = MarketQuotes({"上市": None, "上櫃": date(2026, 10, 2), "興櫃": date(2026, 10, 2)}, {})


def screenshot(message_id="200", timestamp="2026-10-05T14:57:00.000000+00:00"):
    return {
        "id": message_id, "type": 0, "timestamp": timestamp, "author": {"bot": False},
        "content": "",
        "attachments": [{"url": "https://cdn.discordapp.com/x.jpeg",
                         "filename": "IMG_8812.jpeg", "content_type": "image/jpeg"}],
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token")
    monkeypatch.setenv("NOTION_SECRET", "secret")
    monkeypatch.setattr(runner, "STATE_PATH", tmp_path / "state.json")
    discord = Mock()
    discord.download.side_effect = lambda url, path: path
    monkeypatch.setattr(runner, "DiscordClient", Mock(return_value=discord))
    monkeypatch.setattr(runner, "NotionApi", Mock())
    fakes = SimpleNamespace(
        discord=discord,
        write=Mock(return_value=True),
        fetch=Mock(return_value=QUOTES),
        read=Mock(return_value=["鈊象", "火星生技*"]),
    )
    monkeypatch.setattr(runner, "write", fakes.write)
    monkeypatch.setattr(runner, "fetch_quotes", fakes.fetch)
    monkeypatch.setattr(runner, "read_names", fakes.read)
    runner.save_state({"last_message_id": "100", "attempts": {}})
    return fakes


def test_first_run_starts_after_the_latest_message(env):
    runner.save_state({})
    env.discord.latest_message_id.return_value = "555"
    runner.run_once(NOW)
    assert runner.load_state()["last_message_id"] == "555"
    env.discord.messages_since.assert_not_called()


def test_logs_every_stock_and_reacts_ok(env):
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(NOW)
    env.fetch.assert_called_once_with(DAY)
    assert [call.args[1].code for call in env.write.call_args_list] == ["3293", "7731"]
    assert all(call.args[2] == DAY for call in env.write.call_args_list)
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "✅")
    env.discord.reply.assert_not_called()
    assert runner.load_state() == {"last_message_id": "200", "attempts": {}}


def test_pick_day_uses_taipei_date_after_midnight():
    assert runner.pick_day(screenshot(timestamp="2026-10-05T16:10:00+00:00")) == date(2026, 10, 6)
    assert runner.pick_day(screenshot(timestamp="2026-10-05T15:59:00Z")) == DAY


def test_downloads_every_image_in_the_message(env):
    message = screenshot()
    message["attachments"].append({"url": "https://cdn.discordapp.com/y.png",
                                   "filename": "b.png", "content_type": "image/png"})
    env.discord.messages_since.return_value = [message]
    runner.run_once(NOW)
    assert [path.name for path in env.read.call_args.args[0]] == ["screenshot0.jpeg", "screenshot1.png"]


def test_partial_match_writes_found_and_lists_missing(env):
    env.read.return_value = ["鈊象", "鈊像"]
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(NOW)
    assert env.write.call_count == 1
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "⚠️")
    env.discord.reply.assert_called_once_with(
        runner.CHANNEL_ID, "200", "找不到這些股票的 2026-10-05 收盤價：鈊像")


def test_no_match_at_all_is_an_error(env):
    env.read.return_value = ["鈊像"]
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(NOW)
    env.write.assert_not_called()
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "❌")
    env.discord.reply.assert_called_once_with(
        runner.CHANNEL_ID, "200", "找不到這些股票的 2026-10-05 收盤價：鈊像")


def test_empty_screenshot_is_an_error(env):
    env.read.return_value = []
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(NOW)
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "❌")
    env.discord.reply.assert_called_once_with(runner.CHANNEL_ID, "200", "截圖中沒有辨識到股票")


def test_waits_without_reading_when_quotes_are_not_published(env):
    env.fetch.return_value = NOT_PUBLISHED
    env.discord.messages_since.return_value = [screenshot(), screenshot("201")]
    runner.run_once(NOW)
    env.read.assert_not_called()
    env.discord.react.assert_not_called()
    assert runner.load_state() == {"last_message_id": "100", "attempts": {}}


def test_gives_up_waiting_after_twelve_hours(env):
    env.fetch.return_value = NOT_PUBLISHED
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(datetime(2026, 10, 6, 3, 0, tzinfo=timezone.utc))
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "❌")
    env.discord.reply.assert_called_once_with(
        runner.CHANNEL_ID, "200", "找不到 2026-10-05 的收盤行情，可能不是交易日")
    assert runner.load_state()["last_message_id"] == "200"


def test_reports_when_quotes_moved_past_the_pick_day(env):
    env.fetch.return_value = MarketQuotes(
        {"上市": None, "上櫃": date(2026, 10, 6), "興櫃": date(2026, 10, 6)}, {})
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(NOW)
    env.discord.reply.assert_called_once_with(
        runner.CHANNEL_ID, "200", "官方行情已更新到 2026-10-06，無法取得 2026-10-05 的收盤價")


def test_retries_failures_then_gives_up_on_the_third(env):
    env.read.side_effect = RuntimeError("Codex 讀取截圖失敗（exit 1）")
    env.discord.messages_since.return_value = [screenshot()]
    runner.run_once(NOW)
    runner.run_once(NOW)
    assert runner.load_state() == {"last_message_id": "100", "attempts": {"200": 2}}
    env.discord.react.assert_not_called()

    runner.run_once(NOW)
    env.discord.react.assert_called_once_with(runner.CHANNEL_ID, "200", "❌")
    assert "Codex 讀取截圖失敗" in env.discord.reply.call_args.args[2]
    assert runner.load_state() == {"last_message_id": "200", "attempts": {}}


def test_skips_text_and_bot_messages(env):
    text = {"id": "150", "type": 0, "timestamp": "2026-10-05T14:00:00+00:00",
            "author": {"bot": False}, "content": "今天大漲", "attachments": []}
    bot = {**screenshot("160"), "author": {"bot": True}}
    env.discord.messages_since.return_value = [text, bot]
    runner.run_once(NOW)
    env.fetch.assert_not_called()
    assert runner.load_state()["last_message_id"] == "160"
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python3 -m pytest stock_pick/tests/test_stock_runner.py -q`
Expected: FAIL，`ImportError: cannot import name 'runner' from 'stock_pick'`

- [ ] **Step 3: 實作**

`stock_pick/runner.py`：

```python
"""Poll the stock-pick Discord channel and log each screenshot's stocks to Notion.

Required environment variables: DISCORD_BOT_TOKEN and NOTION_SECRET. Run this
script on the machine with an authenticated Codex CLI (oracle-arm, every 5 min).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.discord import DiscordClient
from common.notion import NotionApi
from stock_pick.notion_writer import write
from stock_pick.quotes import PASSED, WAITING, MarketQuotes, fetch_quotes, match, quote_status
from stock_pick.reader import SUPPORTED_EXTENSIONS, read_names

LOG = logging.getLogger(__name__)
CHANNEL_ID = "1556684804731179070"
STATE_PATH = Path(__file__).resolve().parent / "state.json"
TAIPEI = ZoneInfo("Asia/Taipei")
MAX_ATTEMPTS = 3
MAX_WAIT = timedelta(hours=12)
REACTION_OK, REACTION_PARTIAL, REACTION_ERROR = "✅", "⚠️", "❌"


@dataclass(frozen=True)
class Outcome:
    emoji: str
    reply: str | None = None


def load_state() -> dict:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    state.setdefault("last_message_id", None)
    state.setdefault("attempts", {})
    return state


def save_state(state: dict) -> None:
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(STATE_PATH)


def posted_at(message: dict) -> datetime:
    return datetime.fromisoformat(message["timestamp"].replace("Z", "+00:00"))


def pick_day(message: dict) -> date:
    return posted_at(message).astimezone(TAIPEI).date()


def image_attachments(message: dict) -> list[dict]:
    return [
        attachment for attachment in message.get("attachments", [])
        if (attachment.get("content_type") or "").startswith("image/")
        or Path(attachment.get("filename", "")).suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def is_pick_message(message: dict) -> bool:
    return (
        not (message.get("author") or {}).get("bot")
        and message.get("type", 0) in (0, 19)
        and bool(image_attachments(message))
    )


def download_images(discord: DiscordClient, message: dict, directory: Path) -> list[Path]:
    paths = []
    for index, attachment in enumerate(image_attachments(message)):
        suffix = Path(attachment.get("filename", "")).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支援的圖片格式：{attachment.get('filename')}")
        paths.append(discord.download(attachment["url"], directory / f"screenshot{index}{suffix}"))
    return paths


def log_message(message: dict, discord: DiscordClient, notion: NotionApi,
                quotes: MarketQuotes, now: datetime) -> Outcome | None:
    """Log one screenshot message; None means the day's quotes are not out yet."""
    day = pick_day(message)
    status = quote_status(quotes.days, day)
    if status == WAITING:
        if now - posted_at(message) < MAX_WAIT:
            return None
        return Outcome(REACTION_ERROR, f"找不到 {day} 的收盤行情，可能不是交易日")
    if status == PASSED:
        latest = max(value for value in quotes.days.values() if value is not None)
        return Outcome(REACTION_ERROR, f"官方行情已更新到 {latest}，無法取得 {day} 的收盤價")

    with tempfile.TemporaryDirectory(prefix="stock-pick-") as workdir:
        names = read_names(download_images(discord, message, Path(workdir)))
    if not names:
        return Outcome(REACTION_ERROR, "截圖中沒有辨識到股票")
    found, missing = match(names, quotes.by_name)
    for quote in found:
        write(notion, quote, day)
    if missing:
        emoji = REACTION_PARTIAL if found else REACTION_ERROR
        return Outcome(emoji, f"找不到這些股票的 {day} 收盤價：{'、'.join(missing)}")
    return Outcome(REACTION_OK)


def describe(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]


def run_once(now: datetime | None = None) -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN")
    notion_secret = os.environ.get("NOTION_SECRET")
    if not token or not notion_secret:
        raise RuntimeError("DISCORD_BOT_TOKEN and NOTION_SECRET are required")
    discord = DiscordClient(token, user_agent="stock-pick-bot/1.0")
    notion = NotionApi(notion_secret, version="2025-09-03")

    state = load_state()
    if state["last_message_id"] is None:
        # First run: only screenshots posted from now on are logged.
        state["last_message_id"] = discord.latest_message_id(CHANNEL_ID) or "0"
        save_state(state)
        LOG.info("first run: starting after message %s", state["last_message_id"])
        return

    now = now or datetime.now(timezone.utc)
    quotes_by_day: dict[date, MarketQuotes] = {}
    for message in discord.messages_since(CHANNEL_ID, state["last_message_id"]):
        message_id = message["id"]
        if is_pick_message(message):
            try:
                day = pick_day(message)
                if day not in quotes_by_day:
                    quotes_by_day[day] = fetch_quotes(day)
                outcome = log_message(message, discord, notion, quotes_by_day[day], now)
            except Exception as exc:
                attempts = state["attempts"].get(message_id, 0) + 1
                state["attempts"][message_id] = attempts
                LOG.exception("message %s failed (attempt %d/%d)", message_id, attempts, MAX_ATTEMPTS)
                if attempts < MAX_ATTEMPTS:
                    save_state(state)
                    return
                outcome = Outcome(REACTION_ERROR, f"處理失敗（已試 {MAX_ATTEMPTS} 次）：{describe(exc)}")
            if outcome is None:
                LOG.info("message %s: waiting for %s quotes", message_id, pick_day(message))
                return
            discord.react(CHANNEL_ID, message_id, outcome.emoji)
            if outcome.reply:
                discord.reply(CHANNEL_ID, message_id, outcome.reply)
            LOG.info("message %s: %s %s", message_id, outcome.emoji, outcome.reply or "")
        state["attempts"].pop(message_id, None)
        state["last_message_id"] = message_id
        save_state(state)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_once()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python3 -m pytest stock_pick/tests/test_stock_runner.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 跑整組測試**

Run: `python3 -m pytest stock_pick/tests common/tests -q`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add stock_pick/runner.py stock_pick/tests/test_stock_runner.py
git commit -m "$(cat <<'EOF'
feat(stock_pick): poll the channel and log each screenshot to Notion

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: 部署腳本、workflow、文件

**Files:**
- Create: `stock_pick/requirements.txt`
- Create: `stock_pick/run.sh`（可執行）
- Create: `stock_pick/deploy_vps.sh`
- Create: `stock_pick/README.md`
- Create: `.github/workflows/deploy-stock-pick.yml`
- Modify: `.gitignore`（在 `calorie_log/state.tmp` 後面加兩行）
- Modify: `CLAUDE.md`（在 `## translate` 段落前加一段）

**Interfaces:**
- Consumes: `stock_pick/runner.py` 的 `main()`（Task 6）
- Produces: push 到 master 後，自動部署到 oracle-arm `/opt/stock-pick` 的 `stock-pick.timer`

- [ ] **Step 1: requirements 與 .gitignore**

`stock_pick/requirements.txt`：

```
requests>=2.31,<3
```

`.gitignore` 在 `calorie_log/state.tmp` 那行後面加上：

```
stock_pick/state.json
stock_pick/state.tmp
```

- [ ] **Step 2: run.sh**

`stock_pick/run.sh`：

```sh
#!/bin/sh
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="/opt/stock-pick/.env"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export PYTHONUNBUFFERED=1

if [ ! -r "$ENV_FILE" ]; then
  echo "找不到可讀取的 $ENV_FILE" >&2
  exit 1
fi
set -a
. "$ENV_FILE"
set +a

if ! command -v codex >/dev/null 2>&1; then
  echo "VPS 上找不到 codex CLI；請先以 $(id -un) 帳號安裝並登入。" >&2
  exit 1
fi
if ! codex login status >/dev/null 2>&1; then
  echo "VPS 上的 codex CLI 尚未登入；請先以 $(id -un) 帳號完成登入。" >&2
  exit 1
fi

cd "$SCRIPT_DIR/.."
exec "$SCRIPT_DIR/../.venv/bin/python" "$SCRIPT_DIR/runner.py"
```

- [ ] **Step 3: deploy_vps.sh**

`stock_pick/deploy_vps.sh`：

```sh
#!/bin/sh
set -eu

ROOT="/opt/stock-pick"
SERVICE_NAME="stock-pick"
RUN_USER="$(id -un)"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
trap 'rm -f "$ROOT/stock_pick/.env.new"' EXIT

if ! sudo -n true 2>/dev/null; then
  echo "部署帳號 $RUN_USER 需要免密碼 sudo 才能安裝 systemd 排程。" >&2
  exit 1
fi

python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --disable-pip-version-check -r "$ROOT/stock_pick/requirements.txt"

if [ ! -f "$ROOT/stock_pick/.env.new" ]; then
  echo "找不到由 CI 傳入的 .env.new" >&2
  exit 1
fi
install -m 600 "$ROOT/stock_pick/.env.new" "$ROOT/.env"
cat > "$ROOT/stock_pick/$SERVICE_NAME.service" <<EOF
[Unit]
Description=Log stock-pick screenshots from Discord to Notion
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=$RUN_USER
Environment=HOME=$HOME
WorkingDirectory=$ROOT
ExecStart=$ROOT/stock_pick/run.sh
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
EOF

cat > "$ROOT/stock_pick/$SERVICE_NAME.timer" <<EOF
[Unit]
Description=Check the stock-pick Discord channel every 5 minutes

[Timer]
OnCalendar=*-*-* *:0/5:00
Persistent=true
Unit=$SERVICE_NAME.service

[Install]
WantedBy=timers.target
EOF

sudo install -m 644 "$ROOT/stock_pick/$SERVICE_NAME.service" "/etc/systemd/system/$SERVICE_NAME.service"
sudo install -m 644 "$ROOT/stock_pick/$SERVICE_NAME.timer" "/etc/systemd/system/$SERVICE_NAME.timer"
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME.timer"
if command -v codex >/dev/null 2>&1 && codex login status >/dev/null 2>&1; then
  sudo systemctl start "$SERVICE_NAME.service"
else
  echo "Codex CLI 尚未安裝或登入；排程已啟用，完成 $RUN_USER 帳號登入後會自動開始處理。"
fi

echo "已部署 $SERVICE_NAME.timer；使用 journalctl -u $SERVICE_NAME.service 查看執行結果。"
```

- [ ] **Step 4: 設定執行權限並檢查語法**

```bash
chmod +x stock_pick/run.sh
sh -n stock_pick/run.sh && sh -n stock_pick/deploy_vps.sh && echo ok
```

Expected: `ok`

- [ ] **Step 5: workflow**

`.github/workflows/deploy-stock-pick.yml`：

```yaml
name: Deploy Stock Pick

on:
  push:
    branches: [master]
    paths:
      - 'stock_pick/**'
      - 'common/discord.py'
      - 'common/notion.py'
      - '.github/workflows/deploy-stock-pick.yml'
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: deploy-stock-pick
  cancel-in-progress: false

jobs:
  test-and-deploy:
    runs-on: ubuntu-latest
    env:
      VPS_USER: ubuntu
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Test stock pick logger
        run: |
          python -m pip install --disable-pip-version-check -r stock_pick/requirements.txt pytest
          python -m pytest stock_pick/tests common/tests -q

      - name: Check deployment secrets
        env:
          VPS_HOST: ${{ secrets.VPS_HOST }}
          VPS_SSH_KEY: ${{ secrets.VPS_SSH_KEY }}
          DISCORD_BOT_TOKEN: ${{ secrets.DISCORD_BOT_TOKEN }}
          NOTION_SECRET: ${{ secrets.NOTION_SECRET }}
        run: |
          missing=0
          for name in VPS_HOST VPS_SSH_KEY DISCORD_BOT_TOKEN NOTION_SECRET; do
            if [ -z "${!name}" ]; then
              echo "::error::Missing GitHub Actions secret: $name"
              missing=1
            fi
          done
          exit "$missing"

      - name: Configure SSH
        env:
          VPS_HOST: ${{ secrets.VPS_HOST }}
          VPS_SSH_KEY: ${{ secrets.VPS_SSH_KEY }}
          VPS_KNOWN_HOSTS: ${{ secrets.VPS_KNOWN_HOSTS }}
        run: |
          umask 077
          printf '%s\n' "$VPS_SSH_KEY" > "$RUNNER_TEMP/vps_key"
          if [ -n "$VPS_KNOWN_HOSTS" ]; then
            printf '%s\n' "$VPS_KNOWN_HOSTS" > "$RUNNER_TEMP/vps_known_hosts"
          else
            ssh-keyscan -H -T 10 "$VPS_HOST" > "$RUNNER_TEMP/vps_known_hosts"
          fi
          test -s "$RUNNER_TEMP/vps_known_hosts"

      - name: Deploy to VPS
        env:
          VPS_HOST: ${{ secrets.VPS_HOST }}
          DISCORD_BOT_TOKEN: ${{ secrets.DISCORD_BOT_TOKEN }}
          NOTION_SECRET: ${{ secrets.NOTION_SECRET }}
        run: |
          remote="$VPS_USER@$VPS_HOST"
          ssh_opts=(-i "$RUNNER_TEMP/vps_key" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$RUNNER_TEMP/vps_known_hosts")

          ssh "${ssh_opts[@]}" "$remote" 'sudo install -d -o "$(id -un)" -g "$(id -gn)" /opt/stock-pick && mkdir -p /opt/stock-pick/stock_pick /opt/stock-pick/common'
          tar -cf - stock_pick/*.py stock_pick/run.sh stock_pick/deploy_vps.sh stock_pick/requirements.txt common/__init__.py common/notion.py common/discord.py \
            | ssh "${ssh_opts[@]}" "$remote" 'cd /opt/stock-pick && tar -xf -'

          python - <<'PY'
          import os
          import shlex
          from pathlib import Path
          destination = Path(os.environ['RUNNER_TEMP']) / 'stock-pick.env'
          lines = [
              f'export {name}={shlex.quote(os.environ[name])}'
              for name in ('DISCORD_BOT_TOKEN', 'NOTION_SECRET')
          ]
          destination.write_text('\n'.join(lines) + '\n', encoding='utf-8')
          destination.chmod(0o600)
          PY
          ssh "${ssh_opts[@]}" "$remote" 'umask 077; cat > /opt/stock-pick/stock_pick/.env.new' < "$RUNNER_TEMP/stock-pick.env"
          ssh "${ssh_opts[@]}" "$remote" 'sh /opt/stock-pick/stock_pick/deploy_vps.sh'

          ssh "${ssh_opts[@]}" "$remote" 'systemctl is-active --quiet stock-pick.timer'
```

- [ ] **Step 6: 檢查 workflow YAML 能解析**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-stock-pick.yml')); print('ok')"
```

Expected: `ok`（若沒有 PyYAML，先 `python3 -m pip install pyyaml`）

- [ ] **Step 7: README 與 CLAUDE.md**

`stock_pick/README.md`：

```markdown
# 智選股截圖 → Notion

收盤後把智選股 App「自選」頁的截圖貼到 Discord 頻道（`1556684804731179070`），一則訊息可以附多張。
VPS 每 5 分鐘檢查一次：用 Codex CLI 讀出股票名稱，用證交所／櫃買中心官方行情查代號與當天收盤價（興櫃用最後成交價），
寫入 Notion「智選股當天入場」，選股日期是貼圖當天（台灣時間）。

## 訊息上的 emoji

| emoji | 意思 |
|---|---|
| ✅ | 全部寫入（已存在的同日同代號會略過，不重複寫） |
| ⚠️ | 部分寫入；回覆裡列出對不到或當天沒成交的名稱，請手動補 |
| ❌ | 沒有寫入；回覆說明原因（沒辨識到股票、不是交易日、重試 3 次仍失敗等） |

官方行情還沒更新到貼圖當天時會自動等待，最多 12 小時。工具只處理上線之後的新訊息。

## 部署與除錯

push 到 `master` 且改到 `stock_pick/`、`common/discord.py` 或 `common/notion.py` 時，
`Deploy Stock Pick` workflow 會跑測試並部署到 oracle-arm 的 `/opt/stock-pick`（`stock-pick.timer`）。
沿用 GitHub secrets：`VPS_HOST`、`VPS_SSH_KEY`、`DISCORD_BOT_TOKEN`、`NOTION_SECRET`。

- 看執行紀錄：`ssh oracle-arm 'journalctl -u stock-pick.service -n 50 --no-pager'`
- 手動跑一次：`ssh oracle-arm 'sudo systemctl start stock-pick.service'`
- 處理進度：`/opt/stock-pick/stock_pick/state.json`（不進 Git）
```

`CLAUDE.md`：在 `## translate (隨身翻譯 + 檔案翻譯)` 這行前面插入：

```markdown
## stock_pick (智選股截圖 → Notion)

Polls Discord channel `1556684804731179070` every 5 minutes on oracle-arm (`/opt/stock-pick`,
`stock-pick.timer`). Codex CLI reads stock names from each screenshot; official TWSE/TPEx quotes
supply the code and that day's close (興櫃 = last trade); rows go to Notion「智選股當天入場」.
Shared Discord client: `common/discord.py`. Deployed by `deploy-stock-pick.yml`.
Design: `docs/superpowers/specs/2026-10-05-stock-pick-design.md`.

```

- [ ] **Step 8: 跑整組測試**

Run: `python3 -m pytest stock_pick/tests common/tests -q`
Expected: 全部 PASS

- [ ] **Step 9: Commit**

```bash
git add stock_pick/requirements.txt stock_pick/run.sh stock_pick/deploy_vps.sh stock_pick/README.md \
  .github/workflows/deploy-stock-pick.yml .gitignore CLAUDE.md
git commit -m "$(cat <<'EOF'
feat(stock_pick): deploy to oracle-arm on a five-minute timer

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: 上線與實機驗證

會 merge 到 master 並 push，push 之後會自動部署到 VPS。**執行前要先徵得使用者同意。**

**Files:** 無（只部署與驗證）

- [ ] **Step 1: 確認 Task 1 全部通過**

任何一項前提沒過，都先停下來處理。

- [ ] **Step 2: 經使用者同意後 merge 並 push**

```bash
git checkout master
git merge --ff-only feat/stock-pick
git push origin master
```

- [ ] **Step 3: 確認部署成功**

```bash
gh run list --workflow deploy-stock-pick.yml --limit 1
```

Expected: 最新一次是 `completed success`。失敗就用 `gh run view <run-id> --log-failed` 看原因。

- [ ] **Step 4: 確認 VPS 上的排程與起點**

```bash
ssh oracle-arm 'systemctl list-timers stock-pick.timer --no-pager; cat /opt/stock-pick/stock_pick/state.json; journalctl -u stock-pick.service -n 20 --no-pager'
```

Expected: timer 每 5 分鐘一次；`state.json` 有 `last_message_id`；log 有 `first run: starting after message ...`。

- [ ] **Step 5: 實機測試（請使用者操作）**

請使用者在**收盤後**貼上**當天**的截圖。不要貼舊截圖測試：選股日期會被算成今天，價格也會抓今天的，等於寫入錯誤資料。

貼圖後 5 分鐘內確認：
- 訊息被加上 ✅（或 ⚠️／❌ 並附回覆）
- Notion 該日新增的資料，代號、價格與截圖一致（用 Notion MCP 查 `date:選股日期:start` 為當天的列）
- `journalctl -u stock-pick.service -n 20 --no-pager` 沒有 traceback

- [ ] **Step 6: 查重測試**

請使用者再貼一次同一張截圖。Expected：仍然加 ✅，但 Notion 沒有新增重複的列。

- [ ] **Step 7: 回報**

把結果整理給使用者。如果 Codex 讀錯字，回到 Task 3 調整 `INSTRUCTIONS`。
