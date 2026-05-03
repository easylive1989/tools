# Stock Dashboard USER Implementation Plan

**Goal:** Introduce a `users` entity backing 1 active token per user; scope watchlist + alerts by user; keep indicator/stock-detail endpoints open. CLI scripts manage users + tokens.

**Architecture:** Migration adds `users` table + `user_id` FK on `api_tokens`/`watched_stocks`/`price_alerts`, all backfilled to default user `paul` (id=1). `require_token` returns a record including `user_id`. Repos take `user_id` for scoped queries. Token rotation = revoke active row + insert new, enforced by partial UNIQUE index.

**Tech Stack:** SQLite migration runner (existing), FastAPI Depends, repository pattern (existing).

Branch: `feat/user-token` off `master`.

---

### Task 1: Migration 0003 — users table + user_id columns

**Files:**
- Create: `stock/dashboard/backend/db/migrations/0003_users.sql`

- [ ] **Step 1: Branch**

```bash
git checkout master && git pull && git checkout -b feat/user-token
```

- [ ] **Step 2: Migration**

```sql
-- stock/dashboard/backend/db/migrations/0003_users.sql

CREATE TABLE users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO users (name) VALUES ('paul');

ALTER TABLE api_tokens ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1
    REFERENCES users(id);
CREATE UNIQUE INDEX idx_api_tokens_active_user
    ON api_tokens(user_id) WHERE revoked_at IS NULL;

ALTER TABLE price_alerts ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1
    REFERENCES users(id);
CREATE INDEX idx_alert_user ON price_alerts(user_id, enabled);

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

- [ ] **Step 3: Run tests to confirm migration applies cleanly on in-memory DB**

```bash
cd stock/dashboard && python -m pytest tests/test_migration_runner.py -v
```

If migration test relies on counting rows pre/post, may need a small tweak; otherwise green.

- [ ] **Step 4: Commit**

```bash
git add stock/dashboard/backend/db/migrations/0003_users.sql
git commit -m "feat(stock-dashboard): migration 0003 — users + user_id FKs (USER-T1)"
```

---

### Task 2: `repositories/users.py`

**Files:**
- Create: `stock/dashboard/backend/repositories/users.py`

- [ ] **Step 1: Implementation**

```python
"""Users repository."""
from typing import Optional

from db.connection import get_conn


def create_user(name: str) -> int:
    """Insert a user. Raises sqlite3.IntegrityError if name already exists."""
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO users (name) VALUES (?)",
        (name,),
    )
    conn.commit()
    return cur.lastrowid


def get_user_by_id(user_id: int) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT id, name, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def get_user_by_name(name: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT id, name, created_at FROM users WHERE name = ?",
        (name,),
    ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    rows = get_conn().execute(
        "SELECT id, name, created_at FROM users ORDER BY id",
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Test (append to `tests/test_db.py` or new `tests/test_users_repo.py`)**

```python
# tests/test_users_repo.py
from repositories.users import (
    create_user, get_user_by_id, get_user_by_name, list_users,
)


def test_default_paul_seeded():
    assert get_user_by_name('paul') is not None


def test_create_and_lookup():
    uid = create_user('alice')
    assert uid > 1
    assert get_user_by_id(uid)['name'] == 'alice'


def test_list_users_includes_seed_and_new():
    create_user('bob')
    names = [u['name'] for u in list_users()]
    assert 'paul' in names
    assert 'bob' in names
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest tests/test_users_repo.py -v
git add stock/dashboard/backend/repositories/users.py stock/dashboard/tests/test_users_repo.py
git commit -m "feat(stock-dashboard): users repository (USER-T2)"
```

---

### Task 3: `api_tokens` repository — user_id + rotation

**Files:**
- Modify: `stock/dashboard/backend/repositories/api_tokens.py`
- Modify: `stock/dashboard/backend/services/token_service.py`

- [ ] **Step 1: Read current api_tokens.py + token_service.py to understand existing API.**

- [ ] **Step 2: Modify `save_token` (in `api_tokens.py`)**

```python
def save_token(token_hash: str, prefix: str, label: str,
               user_id: int, expires_at: str | None = None) -> int:
    """Insert a new active token for `user_id`, revoking the prior active row.

    Enforced by partial UNIQUE index on (user_id) WHERE revoked_at IS NULL —
    we revoke first, then insert.
    """
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE api_tokens SET revoked_at = ? "
        "WHERE user_id = ? AND revoked_at IS NULL",
        (now, user_id),
    )
    cur = conn.execute(
        "INSERT INTO api_tokens (token_hash, prefix, label, user_id, "
        "created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (token_hash, prefix, label, user_id, now, expires_at),
    )
    conn.commit()
    return cur.lastrowid
```

- [ ] **Step 3: Modify `find_token_by_hash` to return `user_id`**

```python
def find_token_by_hash(token_hash: str) -> dict | None:
    row = get_conn().execute(
        "SELECT id, token_hash, prefix, label, user_id, created_at, "
        "expires_at, last_used_at, revoked_at "
        "FROM api_tokens WHERE token_hash = ?",
        (token_hash,),
    ).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 4: Update `services/token_service.py`** — `issue_token(user_id, label, days)` becomes the public API; verify_token returned dict will carry user_id automatically.

```python
def issue_token(user_id: int, label: str, days: int = 365) -> str:
    """Generate, hash, store, and return the plaintext token."""
    plaintext = _generate_token()
    token_hash = _hash(plaintext)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    save_token(token_hash, plaintext[:8], label, user_id, expires_at)
    return plaintext
```

- [ ] **Step 5: Tests** — update existing token tests to pass user_id; add a rotation test.

```python
def test_save_token_revokes_previous_active(in_memory_db):
    save_token('h1', 'p', 'first', user_id=1)
    save_token('h2', 'p', 'second', user_id=1)
    rows = list_all_tokens_for_user(1)  # helper or raw SELECT
    actives = [r for r in rows if r['revoked_at'] is None]
    assert len(actives) == 1
    assert actives[0]['token_hash'] == 'h2'
```

- [ ] **Step 6: Commit**

```bash
git add stock/dashboard/backend/repositories/api_tokens.py \
  stock/dashboard/backend/services/token_service.py \
  stock/dashboard/tests/test_*.py
git commit -m "feat(stock-dashboard): api_tokens user_id + rotation (USER-T3)"
```

---

### Task 4: Watchlist repo — scope by user

**Files:**
- Modify: `stock/dashboard/backend/repositories/stocks.py`
- Modify: `stock/dashboard/tests/test_*.py` (callers)

- [ ] **Step 1: Update signatures**

```python
def add_watched_ticker(user_id: int, ticker: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO watched_stocks (user_id, ticker, added_at) "
        "VALUES (?, ?, ?)",
        (user_id, ticker, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def remove_watched_ticker(user_id: int, ticker: str) -> None:
    conn = get_conn()
    conn.execute(
        "DELETE FROM watched_stocks WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    )
    conn.commit()


def get_watched_tickers(user_id: int) -> list[str]:
    rows = get_conn().execute(
        "SELECT ticker FROM watched_stocks WHERE user_id = ? "
        "ORDER BY added_at",
        (user_id,),
    ).fetchall()
    return [r["ticker"] for r in rows]
```

- [ ] **Step 2: Update callers** — `api/routes/stocks.py` will need to pass user_id (Task 7); for now, also fix any tests that hit these helpers directly.

- [ ] **Step 3: Run tests, fix call sites until green**

- [ ] **Step 4: Commit**

```bash
git add stock/dashboard/backend/repositories/stocks.py stock/dashboard/tests/test_*.py
git commit -m "feat(stock-dashboard): watchlist repo scoped by user_id (USER-T4)"
```

---

### Task 5: Alerts repo — scope by user

**Files:**
- Modify: `stock/dashboard/backend/repositories/alerts.py`
- Modify: callers / tests

- [ ] **Step 1: Update signatures**

```python
def add_alert(user_id: int, target_type: str, target: str, condition: str,
              threshold: float, indicator_key: str | None = None,
              window_n: int | None = None) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO price_alerts (user_id, target_type, target, condition, "
        "threshold, indicator_key, window_n, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, target_type, target, condition, threshold,
         indicator_key, window_n, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def list_alerts(user_id: int | None = None) -> list[dict]:
    """Return alerts. Pass user_id to scope; pass None for the engine
    (which evaluates every alert regardless of user)."""
    conn = get_conn()
    if user_id is None:
        rows = conn.execute("SELECT * FROM price_alerts").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM price_alerts WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_alert(user_id: int, alert_id: int) -> None:
    get_conn().execute(
        "DELETE FROM price_alerts WHERE id = ? AND user_id = ?",
        (alert_id, user_id),
    )
    get_conn().commit()


def set_alert_enabled(user_id: int, alert_id: int, enabled: bool) -> None:
    get_conn().execute(
        "UPDATE price_alerts SET enabled = ? "
        "WHERE id = ? AND user_id = ?",
        (1 if enabled else 0, alert_id, user_id),
    )
    get_conn().commit()
```

- [ ] **Step 2: Update `services/alert_engine.py`** — calls `list_alerts()` (now `list_alerts(user_id=None)`). The engine iterates all alerts globally; the repo signature still works.

- [ ] **Step 3: Run tests, fix call sites, commit**

```bash
git add stock/dashboard/backend/repositories/alerts.py \
  stock/dashboard/backend/services/alert_engine.py \
  stock/dashboard/tests/test_*.py
git commit -m "feat(stock-dashboard): alerts repo scoped by user_id (USER-T5)"
```

---

### Task 6: `api/dependencies.py` — require_user helper

**Files:**
- Modify: `stock/dashboard/backend/api/dependencies.py`

- [ ] **Step 1: Add `require_user` helper**

```python
from fastapi import Depends
from repositories.users import get_user_by_id


async def require_user(record: dict = Depends(require_token)) -> dict:
    """Resolve the user backing the token. Raises 401 if user record missing."""
    user = get_user_by_id(record["user_id"])
    if user is None:
        raise HTTPException(status_code=401, detail="Token user not found")
    return user
```

`require_token` is unchanged externally — its return now includes `user_id` because `find_token_by_hash` selects the new column.

- [ ] **Step 2: Commit**

```bash
git add stock/dashboard/backend/api/dependencies.py
git commit -m "feat(stock-dashboard): require_user FastAPI dep (USER-T6)"
```

---

### Task 7: Routes — pass user to repos

**Files:**
- Modify: `stock/dashboard/backend/api/routes/stocks.py`
- Modify: `stock/dashboard/backend/api/routes/alerts.py`

- [ ] **Step 1: stocks.py** — replace `Depends(require_token)` with `Depends(require_user)` on the watchlist routes; read `user["id"]` and pass to repo.

```python
@router.get("/stocks", dependencies=[])
def get_stocks(user: dict = Depends(require_user)):
    result = []
    for ticker in get_watched_tickers(user["id"]):
        ...

@router.post("/stocks")
def add_stock(req: AddStockRequest, user: dict = Depends(require_user)):
    add_watched_ticker(user["id"], req.ticker.upper())
    ...

@router.delete("/stocks/{ticker}")
def delete_stock(ticker: str, user: dict = Depends(require_user)):
    remove_watched_ticker(user["id"], ticker.upper())
    ...
```

The `/api/stocks/{ticker}/...` detail routes stay on `require_token` (no user scoping needed).

- [ ] **Step 2: alerts.py** — same pattern for list/create/delete/toggle.

- [ ] **Step 3: Run full test suite** — TestClient tests use the conftest override; conftest update happens in Task 11.

- [ ] **Step 4: Commit**

```bash
git add stock/dashboard/backend/api/routes/stocks.py \
  stock/dashboard/backend/api/routes/alerts.py
git commit -m "feat(stock-dashboard): routes scope watchlist+alerts by user (USER-T7)"
```

---

### Task 8: `scripts/manage_users.py` (new)

**Files:**
- Create: `stock/dashboard/backend/scripts/manage_users.py`

- [ ] **Step 1: CLI implementation**

```python
"""Manage users (CRUD-lite). Usage:
    python scripts/manage_users.py create <name>
    python scripts/manage_users.py list
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import sqlite3
from datetime import datetime, timezone

import db
from repositories.users import create_user, list_users


def cmd_create(name: str) -> None:
    db.init_db()
    try:
        uid = create_user(name)
    except sqlite3.IntegrityError:
        print(f"error: user '{name}' already exists", file=sys.stderr)
        sys.exit(1)
    print(f"Created user id={uid} name={name}")


def cmd_list() -> None:
    db.init_db()
    users = list_users()
    if not users:
        print("(no users)")
        return
    print(f"{'ID':<4} {'NAME':<20} {'CREATED':<25}")
    for u in users:
        print(f"{u['id']:<4} {u['name']:<20} {u['created_at']:<25}")


def main() -> None:
    p = argparse.ArgumentParser(prog="manage_users.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("create"); pc.add_argument("name")
    sub.add_parser("list")
    args = p.parse_args()
    if args.cmd == "create":
        cmd_create(args.name)
    elif args.cmd == "list":
        cmd_list()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test (in-memory)**

```bash
cd stock/dashboard
DB_PATH=:memory: python backend/scripts/manage_users.py list
```

- [ ] **Step 3: Commit**

```bash
git add stock/dashboard/backend/scripts/manage_users.py
git commit -m "feat(stock-dashboard): manage_users.py CLI (USER-T8)"
```

---

### Task 9: `scripts/issue_token.py` — require --user-name

**Files:**
- Modify: `stock/dashboard/backend/scripts/issue_token.py`

- [ ] **Step 1: Update argparse + main**

```python
def main() -> None:
    p = argparse.ArgumentParser(prog="issue_token.py")
    p.add_argument("--user-name", required=True,
                   help="user this token belongs to (must exist; create with manage_users.py)")
    p.add_argument("--label", default="default")
    p.add_argument("--days", type=int, default=365)
    args = p.parse_args()

    db.init_db()
    user = get_user_by_name(args.user_name)
    if user is None:
        print(f"error: user '{args.user_name}' not found. "
              f"Run: python scripts/manage_users.py create {args.user_name}",
              file=sys.stderr)
        sys.exit(1)

    plaintext = issue_token(user["id"], args.label, args.days)
    print(plaintext)
    print(f"# user={args.user_name} label={args.label} days={args.days}",
          file=sys.stderr)
```

- [ ] **Step 2: Commit**

```bash
git add stock/dashboard/backend/scripts/issue_token.py
git commit -m "feat(stock-dashboard): issue_token.py scoped to user (USER-T9)"
```

---

### Task 10: Test fixtures

**Files:**
- Modify: `stock/dashboard/tests/conftest.py`

- [ ] **Step 1: Update fake_token to include user_id**

```python
def _fake_token():
    return {
        "id": 0,
        "prefix": "test_",
        "label": "test",
        "user_id": 1,
        "created_at": "2026-01-01T00:00:00",
        "expires_at": None,
        "last_used_at": None,
        "revoked_at": None,
    }


def _fake_user():
    return {"id": 1, "name": "paul", "created_at": "2026-01-01T00:00:00"}


from api.dependencies import require_user
app.dependency_overrides[require_user] = _fake_user
```

- [ ] **Step 2: Run all tests, fix any remaining mismatches**

```bash
cd stock/dashboard && python -m pytest -x
```

- [ ] **Step 3: Commit**

```bash
git add stock/dashboard/tests/conftest.py
git commit -m "test(stock-dashboard): conftest user fixtures (USER-T10)"
```

---

### Task 11: Final verify, merge, push, prod migration smoke

- [ ] **Step 1: Full test pass**

```bash
cd stock/dashboard && python -m pytest -v
```

- [ ] **Step 2: Merge + push**

```bash
git checkout master
git merge --no-ff feat/user-token -m "feat(stock-dashboard): user concept + per-user watchlist+alerts (USER)"
git push origin master
```

- [ ] **Step 3: Watch backend deploy**

```bash
gh run list --workflow=deploy-stock-dashboard-backend.yml --limit 1
gh run watch <id> --exit-status
```

- [ ] **Step 4: Verify prod migration applied**

After deploy completes (systemd restart applies migrations on boot), curl the dashboard with the existing token to confirm watchlist still returns the same tickers (i.e., paul's data backfilled correctly).

```bash
curl -s "https://api.paul-learning.dev/api/stocks" \
  -H "Authorization: Bearer sd_if1PYHChdZjjUNoV90awJlhTnelKrLaImfQJlKSovws" \
  | python3 -m json.tool | head
```

- [ ] **Step 5: SSH + smoke CLI scripts on prod (manual; user instruction)**

The CLI scripts run on the VPS where the DB lives. From the user's laptop:

```bash
ssh <vps>
cd /opt/stock-dashboard
python backend/scripts/manage_users.py list           # should show paul
python backend/scripts/manage_users.py create test    # create second user
python backend/scripts/issue_token.py --user-name test --label tmp --days 7
# copy plaintext, curl /api/stocks with it → empty list (test user has no watchlist)
```

The user runs this themselves; report the script paths in the merge commit message.

## Self-Review

**Spec coverage:** migration (T1) → users repo (T2) → api_tokens rotation (T3) → watchlist repo (T4) → alerts repo (T5) → require_user dep (T6) → routes (T7) → manage_users CLI (T8) → issue_token CLI (T9) → test fixtures (T10) → deploy + smoke (T11). Maps cleanly to the spec.

**Placeholder scan:** Code blocks use real signatures; no TBD. Test code is illustrative — the goal is "all existing tests pass + new rotation test"; cross-test edits are mechanical find/fix.

**Type consistency:** `user_id: int` everywhere. Dict shapes (`{id, name, created_at}` for user, token row with extra `user_id`) consistent across repo + dependencies + CLI.

**Risks:**
- The migration's `ALTER TABLE ADD COLUMN ... REFERENCES users(id)` — SQLite tolerates declared FK in ADD COLUMN syntactically but doesn't enforce FK constraints unless `PRAGMA foreign_keys=ON`. Backfill via DEFAULT 1 is the practical guarantee.
- Tests that pass tickers/alert ids by position to repo functions will need their argument order swapped (user_id is now the first arg).
- The frontend continues to work because the token still resolves to a record; nothing about the wire format changes.
