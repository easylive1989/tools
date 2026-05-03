# Stock Dashboard USER — User Concept + Per-User Token / Watchlist / Alerts

**Date:** 2026-05-03
**Status:** spec
**Phase:** Post Phase 5; replaces the AUTH multi-token model.

## Goal

Introduce a `users` entity. Each user owns at most one active API token (rotation = revoke old + insert new). Watchlist (`watched_stocks`) and alerts (`price_alerts`) become per-user. Indicator data and stock-detail endpoints stay open to any valid token.

## Decisions (from brainstorm)

- **Q1 User shape**: minimal — `id`, `name`, `created_at`.
- **Q2 Tokens per user**: 1 active. Rotation revokes the previous active token immediately; the new one becomes valid.
- **Q3 CRUD interface**: CLI scripts only (`scripts/manage_users.py`, modified `scripts/issue_token.py`).
- **Q4 Migration default user**: `paul`. All existing api_tokens / watched_stocks / price_alerts rows backfill to this user.
- **Q5 Detail endpoints**: open to any token (price/financial fetches are global caches; per-user gate has no benefit).

## Schema changes (migration `0003_users.sql`)

```sql
-- 1. New users table
CREATE TABLE users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 2. Seed default user
INSERT INTO users (name, created_at) VALUES ('paul', datetime('now'));

-- 3. api_tokens: add user_id; partial unique index for "1 active token per user"
ALTER TABLE api_tokens ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1
    REFERENCES users(id);
CREATE UNIQUE INDEX idx_api_tokens_active_user
    ON api_tokens(user_id) WHERE revoked_at IS NULL;

-- 4. price_alerts: add user_id (no schema reshape needed)
ALTER TABLE price_alerts ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1
    REFERENCES users(id);
CREATE INDEX idx_alert_user ON price_alerts(user_id, enabled);

-- 5. watched_stocks: rebuild because UNIQUE(ticker) must become UNIQUE(user_id, ticker)
CREATE TABLE watched_stocks_new (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker   TEXT NOT NULL,
    user_id  INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
    added_at TEXT NOT NULL,
    UNIQUE(user_id, ticker)
);
INSERT INTO watched_stocks_new (id, ticker, user_id, added_at)
SELECT id, ticker, 1, added_at FROM watched_stocks;
DROP TABLE watched_stocks;
ALTER TABLE watched_stocks_new RENAME TO watched_stocks;
CREATE INDEX idx_watched_user ON watched_stocks(user_id);
```

The partial unique index (`WHERE revoked_at IS NULL`) means rotation `UPDATE old SET revoked_at = NOW; INSERT new` is safe; revoked rows accumulate as history but don't block new tokens.

## API behavior

- `require_token` dependency now returns a record that includes `user_id`.
- A new helper `require_user` returns the resolved user dict directly (most route handlers want this).
- `/api/stocks` (watchlist GET/POST/DELETE) — scoped by `user_id`.
- `/api/alerts` (list/create/delete/toggle) — scoped by `user_id`.
- `/api/dashboard`, `/api/news`, `/api/indicators/spec`, `/api/stocks/{ticker}/*` (history / chip / valuation / revenue / financial / dividend) — unchanged, open to any valid token.

The frontend changes nothing. Token still in localStorage; backend resolves user transparently per request.

## CLI scripts

```
scripts/manage_users.py create <name>       # create new user
scripts/manage_users.py list                # list users + token status
scripts/issue_token.py --user-name paul --label laptop [--days 365]
                                             # revoke any existing active
                                             # token, insert a new one
```

`issue_token.py` errors out if the user doesn't exist (use `manage_users.py create` first). This keeps user creation explicit.

## Repository changes

| Function | Old signature | New signature |
|---|---|---|
| `add_watched_ticker(t)` | global | `add_watched_ticker(user_id, t)` |
| `remove_watched_ticker(t)` | global | `remove_watched_ticker(user_id, t)` |
| `get_watched_tickers()` | global | `get_watched_tickers(user_id)` |
| `list_alerts()` | global | `list_alerts(user_id)` |
| `add_alert(...)` | adds row | adds with `user_id` |
| `delete_alert(id)` | by id | scoped: `WHERE id=? AND user_id=?` |
| `set_alert_enabled(id, enabled)` | by id | scoped to user |
| `find_token_by_hash(h)` | row | row + joined `user_id` |
| `save_token(...)` | inserts | revokes existing active for user, then inserts |

## Service-layer changes

`services/token_service.py`:
- `verify_token(plaintext)` already returns the api_tokens row; with the new `user_id` column, callers can read it.
- New helper `issue_token(user_id, label, days)` — wraps the rotation: revoke old, insert new, return plaintext.
- `track_auth_failure` unchanged.

`services/alert_engine.py`: alerts loaded via `list_alerts()` now need to iterate per user OR pass user_id through. Existing callers iterate ALL alerts to evaluate; change `list_alerts()` (no args) to a separate name like `list_all_alerts_for_engine()` so the public per-user list_alerts(user_id) is clean. Simpler path: keep `list_alerts(user_id=None)` — None returns all rows (engine uses it), specific user_id filters.

## Test fixture changes

`tests/conftest.py`:
- `_fake_token()` returns a record including `user_id: 1`.
- `db.init_db()` already runs migrations on the in-memory DB; migration 0003 will seed `paul` (id=1) automatically.
- Existing tests calling `add_watched_ticker(t)` need updating to `add_watched_ticker(1, t)` — find/replace.

## Migration of live DB on VPS

The existing prod DB has rows in api_tokens / watched_stocks / price_alerts. The migration runner will:
1. Detect 0003 not yet applied.
2. Apply the SQL: creates `users` table, seeds `paul` (id=1), backfills all existing rows to user_id=1.
3. Existing tokens remain valid (now belonging to paul).

No frontend coordination, no service downtime beyond the systemd restart.

## File layout

```
stock/dashboard/backend/
  db/migrations/0003_users.sql                 NEW
  repositories/users.py                        NEW
  repositories/api_tokens.py                   MODIFY
  repositories/stocks.py                       MODIFY (watchlist ops)
  repositories/alerts.py                       MODIFY
  services/token_service.py                    MODIFY (rotation helper)
  services/alert_engine.py                     MODIFY (list_alerts arg)
  api/dependencies.py                          MODIFY (require_user helper)
  api/routes/stocks.py                         MODIFY
  api/routes/alerts.py                         MODIFY
  scripts/manage_users.py                      NEW
  scripts/issue_token.py                       MODIFY
  tests/conftest.py                            MODIFY
  tests/test_*.py                              MODIFY (function signatures)
```

## Risks / open items

- The migration changes a UNIQUE constraint on `watched_stocks`. The rebuild dance is standard SQLite practice but means brief downtime during deploy (systemd restart + migration). Acceptable for a personal tool.
- Existing tests may have many call sites for `add_watched_ticker` / `list_alerts` / etc. — bulk find-and-fix.
- The active token of paul (`sd_if1PYHChdZjjUNoV90awJlhTnelKrLaImfQJlKSovws`) keeps working post-migration (0003 backfills `user_id=1`). Will be visible in the new `manage_users.py list` output.
