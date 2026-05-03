# Stock Dashboard AUTO Implementation Plan

**Goal:** Hardcoded auto-tracked Taiwan top-100 list. Background fetchers union user watchlists + auto-tracked. Detail endpoints gate by (in user's watchlist OR auto-tracked). Monotonic accumulation.

Branch: `feat/auto-track` off `master`.

---

### Task 1: Migration 0004 + seed file + branch

**Files:**
- Create: `stock/dashboard/backend/db/migrations/0004_auto_tracked.sql`
- Create: `stock/dashboard/backend/seeds/auto_tracked_taiwan.txt`

- [ ] **Step 1: Branch + files**

```bash
git checkout master && git pull && git checkout -b feat/auto-track
```

Migration:

```sql
-- 0004_auto_tracked.sql
CREATE TABLE auto_tracked_stocks (
    ticker     TEXT PRIMARY KEY,
    source     TEXT NOT NULL DEFAULT 'twse-top100',
    added_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Seed file (well-known top Taiwan stocks; exact roster can be edited
by operator over time):

```
# Taiwan top-100 by market cap (auto-tracked).
# Edit and re-restart the service to pick up additions.
# Removals do NOT delete existing rows (monotonic).

# 半導體
2330.TW    # 台積電
2454.TW    # 聯發科
2303.TW    # 聯電
2308.TW    # 台達電
2317.TW    # 鴻海
2382.TW    # 廣達
2474.TW    # 可成
3008.TW    # 大立光
3034.TW    # 聯詠
3037.TW    # 欣興
3231.TW    # 緯創
3661.TW    # 世芯-KY
3711.TW    # 日月光投控
4938.TW    # 和碩
6669.TW    # 緯穎
8046.TW    # 南電
2357.TW    # 華碩
2376.TW    # 技嘉
2379.TW    # 瑞昱
2395.TW    # 研華
2408.TW    # 南亞科
2449.TW    # 京元電子
2891.TW    # 中信金
3017.TW    # 奇鋐
3533.TW    # 嘉澤
3653.TW    # 健策
6285.TW    # 啟碁
6488.TW    # 環球晶
8069.TW    # 元太

# 金融
2880.TW    # 華南金
2881.TW    # 富邦金
2882.TW    # 國泰金
2883.TW    # 開發金
2884.TW    # 玉山金
2885.TW    # 元大金
2886.TW    # 兆豐金
2887.TW    # 台新金
2888.TW    # 新光金
2889.TW    # 國票金
2890.TW    # 永豐金
2892.TW    # 第一金
5871.TW    # 中租-KY
5876.TW    # 上海商銀
5880.TW    # 合庫金
2823.TW    # 中壽

# 電信 / 公用
3045.TW    # 台灣大
4904.TW    # 遠傳
2412.TW    # 中華電
9904.TW    # 寶成
9910.TW    # 豐泰

# 傳產 / 化工 / 鋼鐵
1101.TW    # 台泥
1102.TW    # 亞泥
1216.TW    # 統一
1301.TW    # 台塑
1303.TW    # 南亞
1326.TW    # 台化
1402.TW    # 遠東新
2002.TW    # 中鋼
6505.TW    # 台塑化
1722.TW    # 台肥
1227.TW    # 佳格

# 運輸 / 航空
2603.TW    # 長榮
2609.TW    # 陽明
2610.TW    # 華航
2615.TW    # 萬海
2618.TW    # 長榮航
2912.TW    # 統一超
2207.TW    # 和泰車
2105.TW    # 正新

# 生技 / 醫療
1707.TW    # 葡萄王
4174.TW    # 浩鼎
4128.TW    # 中天
6446.TW    # 藥華藥
6504.TW    # 南六

# 其他大型權值
2354.TW    # 鴻準
2451.TW    # 創見
3045.TW    # 台灣大
3105.TW    # 穩懋
3702.TW    # 大聯大
4958.TW    # 臻鼎-KY
6121.TW    # 新普
6213.TW    # 聯茂
6239.TW    # 力成
6271.TW    # 同欣電
8454.TW    # 富邦媒
8464.TW    # 億豐
9914.TW    # 美利達
9921.TW    # 巨大
2027.TW    # 大成鋼

# ETF (常見指標)
0050.TW    # 元大台灣 50
0051.TW    # 元大中型 100
0056.TW    # 元大高股息
00713.TW   # 元大台灣高息低波
00878.TW   # 國泰永續高股息
```

- [ ] **Step 2: Run migration runner test**

```bash
cd stock/dashboard && python3 -m pytest tests/test_migration_runner.py -v
```

- [ ] **Step 3: Commit**

```bash
git add stock/dashboard/backend/db/migrations/0004_auto_tracked.sql \
        stock/dashboard/backend/seeds/auto_tracked_taiwan.txt
git commit -m "feat(stock-dashboard): migration 0004 + auto-track seed (AUTO-T1)"
```

---

### Task 2: `repositories/auto_tracked.py`

**Files:**
- Create: `stock/dashboard/backend/repositories/auto_tracked.py`
- Create: `stock/dashboard/tests/test_auto_tracked_repo.py`

- [ ] **Step 1: Implementation**

```python
"""Auto-tracked stocks repository (Taiwan top-100, monotonic)."""
from db.connection import get_connection


def insert_if_missing(ticker: str, source: str = 'twse-top100') -> bool:
    """INSERT OR IGNORE; returns True if a new row was inserted."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO auto_tracked_stocks (ticker, source) "
            "VALUES (?, ?)",
            (ticker, source),
        )
        return cur.rowcount > 0


def list_auto_tracked_tickers() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ticker FROM auto_tracked_stocks ORDER BY ticker"
        ).fetchall()
        return [r["ticker"] for r in rows]


def is_auto_tracked(ticker: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM auto_tracked_stocks WHERE ticker = ? LIMIT 1",
            (ticker,),
        ).fetchone()
        return row is not None
```

- [ ] **Step 2: Test**

```python
# tests/test_auto_tracked_repo.py
from repositories.auto_tracked import (
    insert_if_missing, list_auto_tracked_tickers, is_auto_tracked,
)


def test_insert_then_query():
    assert insert_if_missing('2330.TW') is True
    assert insert_if_missing('2330.TW') is False  # idempotent
    assert is_auto_tracked('2330.TW') is True
    assert is_auto_tracked('NOTHERE.TW') is False


def test_list_returns_sorted():
    insert_if_missing('2330.TW')
    insert_if_missing('0050.TW')
    tickers = list_auto_tracked_tickers()
    assert '0050.TW' in tickers
    assert '2330.TW' in tickers
    assert tickers == sorted(tickers)
```

- [ ] **Step 3: Commit**

```bash
git add stock/dashboard/backend/repositories/auto_tracked.py \
        stock/dashboard/tests/test_auto_tracked_repo.py
git commit -m "feat(stock-dashboard): auto_tracked repository (AUTO-T2)"
```

---

### Task 3: Seed loader hook

**Files:**
- Modify: `stock/dashboard/backend/db/__init__.py`
- Modify: `stock/dashboard/tests/test_db.py` (add idempotency test)

- [ ] **Step 1: Add `_seed_auto_tracked()` + invoke from init_db()**

```python
# stock/dashboard/backend/db/__init__.py
import logging
import os
from repositories.auto_tracked import insert_if_missing

_logger = logging.getLogger(__name__)
_SEED_PATH = os.path.join(
    os.path.dirname(__file__), "..", "seeds", "auto_tracked_taiwan.txt"
)


def _seed_auto_tracked() -> None:
    if not os.path.exists(_SEED_PATH):
        return
    added = 0
    total = 0
    with open(_SEED_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            total += 1
            if insert_if_missing(line):
                added += 1
    _logger.info(
        "auto_tracked_seeded total=%d added=%d", total, added,
    )


# Call from existing init_db() AFTER migrations apply.
def init_db() -> None:
    # ... existing migration runner call ...
    _seed_auto_tracked()
```

The exact splice point depends on the existing `init_db()` body — append the new call at the end, after migrations run.

- [ ] **Step 2: Test**

```python
# tests/test_db.py — append
def test_seed_loader_is_idempotent():
    """init_db is auto-called by reset_db fixture; running again should
    not add duplicates."""
    from repositories.auto_tracked import list_auto_tracked_tickers
    before = set(list_auto_tracked_tickers())
    db.init_db()  # second time — INSERT OR IGNORE keeps it stable
    after = set(list_auto_tracked_tickers())
    assert before == after
    # The seed file should produce ≥ 80 tickers.
    assert len(after) >= 80
```

- [ ] **Step 3: Run + commit**

```bash
python3 -m pytest tests/test_db.py -v
git add stock/dashboard/backend/db/__init__.py stock/dashboard/tests/test_db.py
git commit -m "feat(stock-dashboard): seed auto-tracked from text file (AUTO-T3)"
```

---

### Task 4: `get_watched_tickers(None)` returns union

**Files:**
- Modify: `stock/dashboard/backend/repositories/stocks.py`
- Modify: `stock/dashboard/tests/test_db.py`

- [ ] **Step 1: Update query**

In `get_watched_tickers`:

```python
def get_watched_tickers(user_id: int | None = None) -> list[str]:
    with get_connection() as conn:
        if user_id is None:
            rows = conn.execute(
                "SELECT ticker FROM watched_stocks "
                "UNION "
                "SELECT ticker FROM auto_tracked_stocks "
                "ORDER BY ticker"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT ticker FROM watched_stocks WHERE user_id=? "
                "ORDER BY added_at",
                (user_id,),
            ).fetchall()
        return [r["ticker"] for r in rows]
```

- [ ] **Step 2: Test**

```python
# tests/test_db.py — append
def test_global_watched_tickers_includes_auto_tracked():
    """get_watched_tickers(None) is the union used by background fetchers."""
    db.add_watched_ticker(1, 'XXXTEST.TW')   # user-only
    auto = db.get_watched_tickers()
    # auto-tracked seeded e.g. 2330.TW + user's XXXTEST.TW
    assert '2330.TW' in auto
    assert 'XXXTEST.TW' in auto
```

- [ ] **Step 3: Commit**

```bash
git add stock/dashboard/backend/repositories/stocks.py stock/dashboard/tests/test_db.py
git commit -m "feat(stock-dashboard): get_watched_tickers union with auto-tracked (AUTO-T4)"
```

---

### Task 5: Detail endpoint gating

**Files:**
- Modify: `stock/dashboard/backend/api/routes/stocks.py`
- Modify: `stock/dashboard/backend/api/routes/fundamentals.py`
- Modify: `stock/dashboard/tests/test_api.py`

- [ ] **Step 1: Helper**

In a small new module or top of `routes/stocks.py`:

```python
from repositories.auto_tracked import is_auto_tracked
from repositories.stocks import get_watched_tickers


def _ticker_accessible(user_id: int, ticker: str) -> bool:
    if is_auto_tracked(ticker):
        return True
    return ticker in set(get_watched_tickers(user_id))


def _gate_or_404(user_id: int, ticker: str) -> None:
    if not _ticker_accessible(user_id, ticker):
        raise HTTPException(
            status_code=404,
            detail="Ticker not in your watchlist and not in the auto-tracked list",
        )
```

- [ ] **Step 2: Apply on each detail route**

`routes/stocks.py` — `/stocks/{ticker}/brokers`, `/stocks/{ticker}/chip`,
`/stocks/{ticker}/history`: switch dep to `require_user`, call
`_gate_or_404(user["id"], ticker.upper())` first.

`routes/fundamentals.py` — `/stocks/{ticker}/valuation`,
`/stocks/{ticker}/revenue`, `/stocks/{ticker}/financial`,
`/stocks/{ticker}/dividend`: same pattern.

- [ ] **Step 3: Tests**

```python
# tests/test_api.py — append (replacing the conftest fake user mock helper)
def test_detail_404_when_not_watched_and_not_auto_tracked(client):
    r = client.get("/api/stocks/UNKNOWN.TW/history")
    assert r.status_code == 404


def test_detail_200_for_auto_tracked(client):
    r = client.get("/api/stocks/2330.TW/history?time_range=1M")
    # 2330.TW is in seed list; access allowed regardless of watchlist
    assert r.status_code == 200


def test_detail_200_after_user_adds_to_watchlist(client):
    db.add_watched_ticker(1, "AAPL")
    r = client.get("/api/stocks/AAPL/history?time_range=1M")
    assert r.status_code in (200, 502)  # 502 if yfinance upstream errors
```

- [ ] **Step 4: Commit**

```bash
git add stock/dashboard/backend/api/routes/stocks.py \
        stock/dashboard/backend/api/routes/fundamentals.py \
        stock/dashboard/tests/test_api.py
git commit -m "feat(stock-dashboard): detail endpoint gating by watchlist + auto-tracked (AUTO-T5)"
```

---

### Task 6: Verify, merge, push, deploy + smoke

- [ ] **Step 1: Full test pass**

```bash
cd stock/dashboard && python3 -m pytest --tb=short -q
```

- [ ] **Step 2: Merge + push**

```bash
git checkout master
git merge --no-ff feat/auto-track -m "feat(stock-dashboard): auto-track Taiwan top-100 (AUTO)"
git push origin master
```

- [ ] **Step 3: Watch backend deploy**

```bash
gh run list --workflow=deploy-stock-dashboard-backend.yml --limit 1
gh run watch <id> --exit-status
```

- [ ] **Step 4: Smoke test**

```bash
TOKEN="<paul's token>"
# Auto-tracked, should work without watchlist
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://api.paul-learning.dev/api/stocks/2330.TW/history?time_range=1M" \
  | python3 -c "import sys,json; print('rows:', len(json.load(sys.stdin).get('dates', [])))"

# Random unrelated ticker not in paul's watchlist + not auto-tracked
# Should 404.
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOKEN" \
  "https://api.paul-learning.dev/api/stocks/QQQ/history?time_range=1M"
```

## Self-Review

**Spec coverage:** migration (T1) → repo (T2) → seed loader (T3) → fetcher
union (T4) → detail gating (T5) → deploy (T6).

**Risks:**
- Seed file may include a ticker that doesn't actually exist on TWSE — fetchers will log warnings but won't crash. Operator removes from file (existing DB row stays).
- Detail-endpoint gating is a behavior change — paul's existing usage
  is fine because his watchlist + the seed cover everything he was
  previously viewing. Foreign tickers (AAPL, GOOG) are in his
  watchlist already.
