# Stock Dashboard AUTO — Auto-track Taiwan Top-100 Stocks

**Date:** 2026-05-03
**Status:** spec
**Phase:** Post USER

## Goal

Maintain a hardcoded "auto-tracked" list of Taiwan top-100 (by market cap)
stocks. Background fetchers union this list with each user's watchlist,
so popular stocks have warm caches even if no user is currently
watching them. Detail endpoints gate by (in user's watchlist OR in
auto-tracked) — anyone can browse top-100 detail pages; outside that,
the user must add to their watchlist first.

## Decisions (from brainstorm)

- **Q1 source**: hardcoded list. FinMind ETF-holdings dataset is sponsor-only;
  paid tier or extra integration not worth it for a personal tool.
- **Q1 modifier**: monotonic. Removing a ticker from the seed file does NOT
  delete its `auto_tracked_stocks` row — only adds new ones.
- **Q2 storage**: separate `auto_tracked_stocks` table (not mixed into
  user watchlists).
- **Q3 refresh**: re-seed on every `init_db()` (cheap `INSERT OR IGNORE`,
  no removals). Operator updates seed file manually periodically.
- **Q4 detail endpoint gating**: outside top-100 + outside user's
  watchlist → 404.

## Schema (migration 0004_auto_tracked.sql)

```sql
CREATE TABLE auto_tracked_stocks (
    ticker     TEXT PRIMARY KEY,
    source     TEXT NOT NULL DEFAULT 'twse-top100',
    added_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

No FK to users. No `removed_at`. Once added, stays.

## Seed file

```
stock/dashboard/backend/seeds/auto_tracked_taiwan.txt
```

Newline-delimited Taiwan tickers in `XXXX.TW` form (or `.TWO`); `#`
comments allowed. Initial population aims at the well-known
台灣 50 + 中型 100 constituents (~80–100 tickers). Operator edits the
file periodically; on next service restart, new entries flow into
`auto_tracked_stocks`. Removed entries stay in the table.

## Loader

`db/__init__.py` `init_db()` runs migrations, then calls
`_seed_auto_tracked()` which:

1. Reads `seeds/auto_tracked_taiwan.txt`
2. For each non-comment, non-empty line: `INSERT OR IGNORE INTO
   auto_tracked_stocks (ticker, source) VALUES (?, 'twse-top100')`
3. Logs `auto_tracked_seeded count=N (added=K)`

No-op if the file is missing.

## Repository — `repositories/auto_tracked.py`

```python
def list_auto_tracked_tickers() -> list[str]: ...
def is_auto_tracked(ticker: str) -> bool: ...
def insert_if_missing(ticker: str) -> bool: ...   # for the seed loader
```

## Modify `get_watched_tickers(user_id=None)`

```python
def get_watched_tickers(user_id: int | None = None) -> list[str]:
    """Watched tickers for a user (specific id), or the global union of
    user watchlists + auto-tracked stocks (None — used by background
    fetchers + detail-endpoint gating)."""
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

`UNION` deduplicates automatically.

## Detail endpoint gating

A new helper `is_accessible(user_id, ticker) -> bool` returns True if
the ticker is in the user's watchlist OR in `auto_tracked_stocks`. Used
by all `/api/stocks/{ticker}/*` endpoints (history, chip, valuation,
revenue, financial, dividend). Non-accessible → `HTTPException(404)`.

The detail-route dependency switches from `require_token` to
`require_user` so we can scope by user.

## API surface (frontend coordination)

- `/api/stocks` (user's personal watchlist) — unchanged
- `/api/stocks/{ticker}/*` — now 404 for non-accessible tickers
- New `GET /api/auto-tracked` — returns the public top-100 list, used
  by the frontend if we want to show "市值前 100 — 自動追蹤" anywhere.
  (Optional; frontend doesn't need to use it now.)

If a user clicks a watchlist ticker they own, it works (their
watchlist). If they navigate to a Taiwan top-100 ticker not in their
watchlist, it works (auto-tracked). If they navigate to AAPL (not in
list, not top-100), they get 404 — they need to add to watchlist first.

## Frontend impact

Currently zero changes required. The detail page already handles
errors via `apiFetch` 404 paths. Future polish:
- Show a "+ Add to watchlist to view" prompt on 404 detail pages
- A new dashboard card listing the auto-tracked top-100

## Testing strategy

- Migration 0004 applies cleanly (existing migration runner test should
  still pass; add a new test for seed loader idempotency)
- `auto_tracked.py` repo: insert idempotent, list returns sorted,
  is_auto_tracked matches case-sensitively
- `get_watched_tickers(None)` includes both user watchlists + auto-tracked
- Detail endpoint route gating: 404 for unrelated ticker, 200 for
  auto-tracked, 200 for user-watched

## File layout

```
stock/dashboard/backend/
  db/migrations/0004_auto_tracked.sql        NEW
  seeds/auto_tracked_taiwan.txt              NEW
  repositories/auto_tracked.py               NEW
  repositories/stocks.py                     MODIFY (UNION query)
  db/__init__.py                             MODIFY (seed loader hook)
  api/routes/stocks.py                       MODIFY (detail gating)
  api/routes/fundamentals.py                 MODIFY (detail gating)

tests/
  test_auto_tracked_repo.py                  NEW
  test_db.py                                 MODIFY (seed loader test)
  test_api.py                                MODIFY (detail gating tests)
```

## Risks

- **Seed list accuracy**: hardcoded list won't perfectly match
  current market cap rankings; that's acceptable per the monotonic-add
  rule. New popular stocks need a manual file edit.
- **Frontend 404**: existing UI on the detail page shows "無法載入歷史資料"
  on errors. Acceptable but could be improved with a clearer
  "add this stock to your watchlist" message in a follow-up.
- **Backward compatibility**: existing users' bookmarked URLs to
  unrelated tickers (e.g. their old AAPL deep links) will start
  returning 404. AAPL is in many users' watchlists already so likely
  fine in practice; if not, the user just adds it.
