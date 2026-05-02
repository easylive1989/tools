# Stock Dashboard AUTH-: Multi-Token Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce token-based authentication on every API endpoint. Add `api_tokens` table, repository, service (with auth-burst notifier), `require_token` dependency on all 5 routers, CLI for issuance/listing/revocation, and an `apiFetch` wrapper in both frontend HTML files. Tests bypass auth via `dependency_overrides` so the existing 138+ tests need no changes.

**Architecture:** Backend layered (migration → repo → service → dependency → router); frontend gets a thin wrapper. Token plaintext is stored once in `localStorage`; every API call includes `Authorization: Bearer <token>`. Failed verifications track per-IP burst and notify a Discord ops webhook on threshold breach.

**Tech Stack:** Python 3.12, FastAPI, sqlite3, stdlib `secrets`/`hashlib`, pytest, vanilla JS (no new dependencies).

**Spec reference:** `docs/superpowers/specs/2026-05-02-stock-dashboard-auth-design.md`.

---

## File Structure

**Created:**
- `stock/dashboard/backend/db/migrations/0002_api_tokens.sql`
- `stock/dashboard/backend/repositories/api_tokens.py`
- `stock/dashboard/backend/services/token_service.py`
- `stock/dashboard/backend/api/dependencies.py`
- `stock/dashboard/backend/scripts/__init__.py` (empty)
- `stock/dashboard/backend/scripts/issue_token.py`
- `stock/dashboard/tests/unit/test_api_tokens_repo.py`
- `stock/dashboard/tests/unit/test_token_service.py`

**Modified:**
- `stock/dashboard/backend/core/settings.py` (add `discord_ops_webhook_url`)
- `stock/dashboard/backend/api/routes/indicators.py` (router dependency)
- `stock/dashboard/backend/api/routes/stocks.py` (router dependency)
- `stock/dashboard/backend/api/routes/fundamentals.py` (router dependency)
- `stock/dashboard/backend/api/routes/alerts.py` (router dependency)
- `stock/dashboard/backend/api/routes/news.py` (router dependency)
- `stock/dashboard/tests/conftest.py` (`app.dependency_overrides[require_token]`)
- `stock/dashboard/tests/test_api.py` (1 enforcement test)
- `stock/dashboard/frontend/index.html` (`apiFetch` wrapper + ~15 fetch site replacements + clearToken button)
- `stock/dashboard/frontend/stock.html` (`apiFetch` wrapper + ~10 fetch site replacements)
- `stock/dashboard/README.md` (Bootstrap section)

**Unchanged:**
- All other backend modules (`alert_engine`, `alert_notifier`, `alert_registry`, `backfill`, `repositories/{alerts,chip,fundamentals,indicators,stocks}`, `fetchers/*`, `core/{logging,errors}`, `db/{runner,connection}`, `main.py`, `services/indicators/*`)
- `tests/conftest.py` autouse `reset_db` fixture (only adds dependency override at module level)
- All other test files
- `stock/dashboard/stock-dashboard.service`

---

## Baseline

Before starting: `5 failed, 137 passed`. Same 5 baseline failures (DO NOT FIX). After this phase: `5 failed, ~145 passed` (added: 4 token_service unit tests + 3 api_tokens repo tests + 1 enforcement test ≈ 8 new tests; final ≈ 145).

All commits use `(AUTH-Tn)` step IDs per CONVENTIONS.md §5.1.

---

## Task Breakdown

### Task 1 (AUTH-T1): Migration + repository + repo unit tests

**Files:**
- Create: `stock/dashboard/backend/db/migrations/0002_api_tokens.sql`
- Create: `stock/dashboard/backend/repositories/api_tokens.py`
- Create: `stock/dashboard/tests/unit/test_api_tokens_repo.py`

- [ ] **Step 1: Verify baseline**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 137 passed, 3 warnings`.

- [ ] **Step 2: Create migration file**

Write `stock/dashboard/backend/db/migrations/0002_api_tokens.sql`:

```sql
-- 0002_api_tokens.sql

CREATE TABLE api_tokens (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash   TEXT NOT NULL UNIQUE,
    prefix       TEXT NOT NULL,
    label        TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    expires_at   TEXT,
    last_used_at TEXT,
    revoked_at   TEXT
);
CREATE INDEX idx_token_hash ON api_tokens(token_hash);
```

- [ ] **Step 3: Create `repositories/api_tokens.py`**

Write `stock/dashboard/backend/repositories/api_tokens.py`:

```python
"""API token repository."""
from datetime import datetime, timezone

from db.connection import get_connection


def insert_token(token_hash: str, prefix: str, label: str,
                 expires_at: str | None = None) -> int:
    """Insert a new token row. Returns the row id."""
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO api_tokens "
            "(token_hash, prefix, label, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (token_hash, prefix, label, now_iso, expires_at),
        )
        return cur.lastrowid


def find_active_by_hash(token_hash: str) -> dict | None:
    """Return token row if hash matches and token is not revoked or expired."""
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM api_tokens "
            "WHERE token_hash = ? "
            "AND revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > ?) "
            "LIMIT 1",
            (token_hash, now_iso),
        ).fetchone()
        return dict(row) if row else None


def touch_last_used(token_id: int) -> None:
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE api_tokens SET last_used_at = ? WHERE id = ?",
            (now_iso, token_id),
        )


def list_tokens() -> list[dict]:
    """Return all token rows for CLI listing (most recent first)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, prefix, label, created_at, expires_at, "
            "       last_used_at, revoked_at "
            "FROM api_tokens "
            "ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def revoke_token(token_id: int) -> bool:
    """Mark token revoked. Returns True if a row was updated."""
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE api_tokens SET revoked_at = ? "
            "WHERE id = ? AND revoked_at IS NULL",
            (now_iso, token_id),
        )
        return cur.rowcount > 0
```

- [ ] **Step 4: Create `tests/unit/test_api_tokens_repo.py`**

Write the test file:

```python
"""Repository tests for api_tokens table."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from repositories.api_tokens import (
    insert_token, find_active_by_hash, touch_last_used,
    list_tokens, revoke_token,
)


def test_insert_and_find_token():
    token_id = insert_token("hash_abc", "sd_aaa", "label-a")
    assert isinstance(token_id, int)

    row = find_active_by_hash("hash_abc")
    assert row is not None
    assert row["id"] == token_id
    assert row["prefix"] == "sd_aaa"
    assert row["label"] == "label-a"
    assert row["revoked_at"] is None


def test_revoke_token_makes_it_inactive():
    token_id = insert_token("hash_revoked", "sd_rev", "to-revoke")
    assert revoke_token(token_id) is True

    row = find_active_by_hash("hash_revoked")
    assert row is None  # filtered out by find_active

    # Re-revoking returns False (already revoked)
    assert revoke_token(token_id) is False


def test_expired_token_not_returned_by_find_active():
    # Insert with explicit past expires_at
    from datetime import datetime, timezone, timedelta
    past = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)).isoformat()
    insert_token("hash_expired", "sd_exp", "expired-token", expires_at=past)

    assert find_active_by_hash("hash_expired") is None


def test_touch_last_used_updates_timestamp():
    token_id = insert_token("hash_touch", "sd_tou", "touch-test")
    row_before = find_active_by_hash("hash_touch")
    assert row_before["last_used_at"] is None

    touch_last_used(token_id)

    row_after = find_active_by_hash("hash_touch")
    assert row_after["last_used_at"] is not None


def test_list_tokens_returns_all_including_revoked():
    insert_token("hash_l1", "sd_l1a", "list-1")
    rid = insert_token("hash_l2", "sd_l2a", "list-2")
    revoke_token(rid)

    rows = list_tokens()
    labels = {r["label"] for r in rows}
    assert "list-1" in labels
    assert "list-2" in labels
```

- [ ] **Step 5: Run the tests**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/unit/test_api_tokens_repo.py -v 2>&1 | tail -10
```

Expected: 5 tests PASS. (`reset_db` autouse fixture in conftest re-runs migrations including 0002, so the table exists fresh per test.)

- [ ] **Step 6: Run full suite to confirm no regression**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 142 passed` (137 + 5 new repo tests).

- [ ] **Step 7: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/db/migrations/0002_api_tokens.sql stock/dashboard/backend/repositories/api_tokens.py stock/dashboard/tests/unit/test_api_tokens_repo.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add api_tokens migration + repository (AUTH-T1)

Migration 0002 creates api_tokens table with token_hash UNIQUE +
prefix/label/expires_at/last_used_at/revoked_at. Repository exposes
insert_token, find_active_by_hash, touch_last_used, list_tokens,
revoke_token. 5 unit tests cover insert/find/revoke/expire/touch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2 (AUTH-T2): `core/settings.py` adds `discord_ops_webhook_url`

**Files:**
- Modify: `stock/dashboard/backend/core/settings.py`

- [ ] **Step 1: Add the setting**

Open `stock/dashboard/backend/core/settings.py`. The `Settings` class currently has `discord_stock_webhook_url`. Add `discord_ops_webhook_url` next to it:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "..", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: str = os.path.join(
        os.path.dirname(__file__), "..", "stock_dashboard.db"
    )
    discord_stock_webhook_url: SecretStr | None = None
    discord_ops_webhook_url: SecretStr | None = None     # ← NEW
    finmind_token: SecretStr = SecretStr("")
    log_level: str = "INFO"
    cors_origins: list[str] = ["https://paul-learning.dev"]


settings = Settings()
```

- [ ] **Step 2: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 142 passed`. Pydantic-settings happily loads with the new optional field unset.

- [ ] **Step 3: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/core/settings.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add discord_ops_webhook_url to settings (AUTH-T2)

SecretStr | None field; defaults to None. AUTH-T3 will read it for
auth-burst Discord notifications. VPS .env / GitHub Secret population
is a manual deploy-time step (documented in README in AUTH-T11).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3 (AUTH-T3): `services/token_service.py` + unit tests

**Files:**
- Create: `stock/dashboard/backend/services/token_service.py`
- Create: `stock/dashboard/tests/unit/test_token_service.py`

- [ ] **Step 1: Create `services/token_service.py`**

Write `stock/dashboard/backend/services/token_service.py`:

```python
"""Token issuance + verification + auth-burst tracking."""
import hashlib
import logging
import secrets
import threading
from collections import deque
from datetime import datetime, timedelta, timezone

from common.notify import send_to_discord
from core.settings import settings
from repositories.api_tokens import (
    insert_token, find_active_by_hash, touch_last_used,
)

logger = logging.getLogger(__name__)


_TOKEN_PREFIX = "sd_"
_TOKEN_BODY_BYTES = 32
_DEFAULT_EXPIRY_DAYS = 365
_PREFIX_DISPLAY_LEN = 6

_BURST_WINDOW = timedelta(minutes=5)
_BURST_THRESHOLD = 5
_BURST_COOLDOWN = timedelta(hours=1)

_failures: dict[str, deque] = {}
_last_notified: dict[str, datetime] = {}
_burst_lock = threading.Lock()


def _hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def issue_token(label: str, expiry_days: int | None = _DEFAULT_EXPIRY_DAYS) -> tuple[str, int]:
    """Issue a new token. Returns (plaintext_token, db_id).

    Plaintext shown ONCE; only hash + display prefix stored.
    expiry_days=None for no-expiry tokens.
    """
    body = secrets.token_urlsafe(_TOKEN_BODY_BYTES)
    plaintext = f"{_TOKEN_PREFIX}{body}"
    digest = _hash_token(plaintext)
    display_prefix = f"{_TOKEN_PREFIX}{body[:_PREFIX_DISPLAY_LEN]}"

    expires_at = None
    if expiry_days is not None:
        expires_at = (datetime.now(timezone.utc).replace(tzinfo=None)
                      + timedelta(days=expiry_days)).isoformat()

    db_id = insert_token(digest, display_prefix, label, expires_at)
    logger.info("token_issued id=%s label=%s prefix=%s", db_id, label, display_prefix)
    return plaintext, db_id


def verify_token(plaintext: str | None) -> dict | None:
    """Return DB row if token is valid (active, not revoked, not expired). Else None."""
    if not plaintext:
        return None
    digest = _hash_token(plaintext)
    row = find_active_by_hash(digest)
    if row is None:
        return None
    touch_last_used(row["id"])
    return row


def track_auth_failure(client_ip: str) -> None:
    """Track 401 burst per client_ip; notify Discord ops on threshold breach."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    should_notify = False
    count = 0
    with _burst_lock:
        deq = _failures.setdefault(client_ip, deque())
        deq.append(now)
        while deq and (now - deq[0]) > _BURST_WINDOW:
            deq.popleft()
        count = len(deq)
        if count >= _BURST_THRESHOLD:
            last = _last_notified.get(client_ip)
            if not last or (now - last) >= _BURST_COOLDOWN:
                _last_notified[client_ip] = now
                should_notify = True

    if not should_notify:
        return

    webhook = settings.discord_ops_webhook_url
    if not webhook:
        logger.warning("auth_burst_no_ops_webhook ip=%s count=%d", client_ip, count)
        return
    payload = {
        "embeds": [{
            "title": "🚨 Stock Dashboard auth burst",
            "description": f"IP `{client_ip}` triggered {count} 401s in {_BURST_WINDOW}.",
            "color": 0xE74C3C,
        }]
    }
    try:
        send_to_discord(webhook.get_secret_value(), payload)
        logger.warning("auth_burst_notified ip=%s count=%d", client_ip, count)
    except Exception as e:
        logger.warning("auth_burst_notify_failed ip=%s error=%s", client_ip, e)
```

- [ ] **Step 2: Create `tests/unit/test_token_service.py`**

```python
"""Token service unit tests."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from services.token_service import issue_token, verify_token, _hash_token


def test_issue_token_returns_plaintext_and_id():
    plaintext, token_id = issue_token(label="test-issue")
    assert plaintext.startswith("sd_")
    assert len(plaintext) > 30
    assert isinstance(token_id, int)


def test_verify_token_returns_record_for_valid():
    plaintext, _ = issue_token(label="test-verify")
    rec = verify_token(plaintext)
    assert rec is not None
    assert rec["label"] == "test-verify"


def test_verify_token_returns_none_for_unknown():
    assert verify_token("sd_doesnotexist") is None
    assert verify_token("") is None
    assert verify_token(None) is None


def test_verify_token_returns_none_for_revoked():
    from repositories.api_tokens import revoke_token
    plaintext, token_id = issue_token(label="test-revoked")
    revoke_token(token_id)
    assert verify_token(plaintext) is None


def test_token_hash_is_deterministic():
    assert _hash_token("foo") == _hash_token("foo")
    assert _hash_token("foo") != _hash_token("bar")
    assert len(_hash_token("foo")) == 64


def test_issue_token_with_no_expiry():
    plaintext, _ = issue_token(label="no-expiry", expiry_days=None)
    rec = verify_token(plaintext)
    assert rec is not None
    assert rec["expires_at"] is None
```

- [ ] **Step 3: Run new tests**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/unit/test_token_service.py -v 2>&1 | tail -10
```

Expected: 6 tests PASS.

- [ ] **Step 4: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 148 passed` (142 + 6 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/services/token_service.py stock/dashboard/tests/unit/test_token_service.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add token_service + unit tests (AUTH-T3)

issue_token: secrets.token_urlsafe(32) + sd_ prefix + SHA-256 hash;
365-day default expiry. verify_token: hash-lookup, touches last_used_at
on success. track_auth_failure: in-memory per-IP rolling 5-minute
window; >=5 failures trigger Discord ops notification with 1-hour
cooldown. 6 unit tests cover issue/verify/revoke/no-expiry/hash.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4 (AUTH-T4): `api/dependencies.py` `require_token`

**Files:**
- Create: `stock/dashboard/backend/api/dependencies.py`

- [ ] **Step 1: Create the file**

Write `stock/dashboard/backend/api/dependencies.py`:

```python
"""FastAPI Depends providers."""
import logging

from fastapi import Header, HTTPException, Request

from services.token_service import verify_token, track_auth_failure

logger = logging.getLogger(__name__)


async def require_token(
    request: Request,
    authorization: str | None = Header(None),
) -> dict:
    """Verify Authorization: Bearer <token>. Raises 401 on miss/invalid.

    On failure, tracks the client IP for Discord ops-burst notification.
    """
    client_ip = request.client.host if request.client else "unknown"

    if not authorization or not authorization.startswith("Bearer "):
        track_auth_failure(client_ip)
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header",
        )

    token = authorization[len("Bearer "):].strip()
    record = verify_token(token)
    if record is None:
        track_auth_failure(client_ip)
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    return record
```

- [ ] **Step 2: Smoke-import**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "from api.dependencies import require_token; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 148 passed`. (No callers yet.)

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/api/dependencies.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add api/dependencies.py require_token (AUTH-T4)

FastAPI dependency that parses Authorization: Bearer <token>, calls
services.token_service.verify_token, raises 401 on miss/invalid.
Failures invoke services.token_service.track_auth_failure for Discord
ops-burst tracking. Not yet wired to routers — that's AUTH-T6.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5 (AUTH-T5): `tests/conftest.py` injects `dependency_overrides`

**Files:**
- Modify: `stock/dashboard/tests/conftest.py`

- [ ] **Step 1: Modify conftest**

The current `tests/conftest.py` is:

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
os.environ["DB_PATH"] = ":memory:"

import pytest
import db


@pytest.fixture(autouse=True)
def reset_db():
    """Reset the in-memory database before each test."""
    db.connection._memory_conn = None
    db.init_db()
    yield
    if db.connection._memory_conn is not None:
        db.connection._memory_conn.close()
        db.connection._memory_conn = None
```

Replace with:

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
os.environ["DB_PATH"] = ":memory:"

import pytest
import db
from main import app
from api.dependencies import require_token


def _fake_token():
    """Bypass auth in tests — returns a synthetic token row."""
    return {
        "id": 0,
        "prefix": "test_",
        "label": "test",
        "created_at": "2026-01-01T00:00:00",
        "expires_at": None,
        "last_used_at": None,
        "revoked_at": None,
    }


# Module-level override: applies to every TestClient(app) request.
app.dependency_overrides[require_token] = _fake_token


@pytest.fixture(autouse=True)
def reset_db():
    """Reset the in-memory database before each test."""
    db.connection._memory_conn = None
    db.init_db()
    yield
    if db.connection._memory_conn is not None:
        db.connection._memory_conn.close()
        db.connection._memory_conn = None
```

- [ ] **Step 2: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 148 passed`. The override has no observable effect yet because no router has the dependency attached. The next task wires the routers.

- [ ] **Step 3: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/tests/conftest.py && git commit -m "$(cat <<'EOF'
test(stock-dashboard): inject dependency_overrides for require_token (AUTH-T5)

Module-level override runs at conftest import; every TestClient(app)
request bypasses auth. Existing 138+ tests need no modification.
Override has no observable effect until AUTH-T6 attaches the
dependency to routers.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6 (AUTH-T6): Attach `Depends(require_token)` to all 5 routers

**Files:**
- Modify: `stock/dashboard/backend/api/routes/indicators.py`
- Modify: `stock/dashboard/backend/api/routes/stocks.py`
- Modify: `stock/dashboard/backend/api/routes/fundamentals.py`
- Modify: `stock/dashboard/backend/api/routes/alerts.py`
- Modify: `stock/dashboard/backend/api/routes/news.py`

- [ ] **Step 1: Update `routes/indicators.py`**

Find the line `router = APIRouter(prefix="/api", tags=["indicators"])`. Replace with:

```python
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_token
# ... (existing imports remain)

router = APIRouter(
    prefix="/api",
    tags=["indicators"],
    dependencies=[Depends(require_token)],
)
```

(Add `Depends` to the existing `from fastapi import APIRouter, HTTPException` line; add the new import.)

- [ ] **Step 2: Update `routes/stocks.py`**

Same pattern. Find `router = APIRouter(prefix="/api", tags=["stocks"])` and add `dependencies=[Depends(require_token)]`. Add the import:

```python
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_token
```

- [ ] **Step 3: Update `routes/fundamentals.py`**

Same pattern.

- [ ] **Step 4: Update `routes/alerts.py`**

Same pattern.

- [ ] **Step 5: Update `routes/news.py`**

Same pattern. The current `news.py` only imports `from fastapi import APIRouter`, so:

```python
from fastapi import APIRouter, Depends

from api.dependencies import require_token

router = APIRouter(
    prefix="/api",
    tags=["news"],
    dependencies=[Depends(require_token)],
)
```

- [ ] **Step 6: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 148 passed`. (`dependency_overrides[require_token]` from T5 bypasses the now-attached dependency.)

- [ ] **Step 7: Smoke check enforcement is real (without override)**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from main import app
from api.dependencies import require_token
from fastapi.testclient import TestClient

# Pop override, simulate a fresh process
app.dependency_overrides.pop(require_token, None)

client = TestClient(app)
r = client.get('/api/dashboard')
print('status:', r.status_code, 'detail:', r.json())
assert r.status_code == 401
print('ok - 401 enforced')
"
```

Expected: prints `status: 401 ...` and `ok - 401 enforced`.

- [ ] **Step 8: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/api/routes/indicators.py stock/dashboard/backend/api/routes/stocks.py stock/dashboard/backend/api/routes/fundamentals.py stock/dashboard/backend/api/routes/alerts.py stock/dashboard/backend/api/routes/news.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): enforce require_token on all 5 routers (AUTH-T6)

Every API endpoint now requires Authorization: Bearer <token>.
Tests bypass via dependency_overrides[require_token] (AUTH-T5).
Without the override, /api/dashboard returns 401 (verified via
in-process TestClient smoke check).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7 (AUTH-T7): Lock down enforcement with a test

**Files:**
- Modify: `stock/dashboard/tests/test_api.py` (append 1 test)

- [ ] **Step 1: Append the test**

Append to `stock/dashboard/tests/test_api.py`:

```python
def test_endpoint_returns_401_without_auth_override():
    """Without dependency_override, endpoints require Authorization header."""
    from api.dependencies import require_token

    saved = app.dependency_overrides.pop(require_token, None)
    try:
        unauthed = TestClient(app)
        r = unauthed.get("/api/dashboard")
        assert r.status_code == 401
        assert "Missing" in r.json()["detail"] or "Invalid" in r.json()["detail"]
    finally:
        if saved is not None:
            app.dependency_overrides[require_token] = saved
```

This test pops the override, hits an endpoint, asserts 401, then restores the override so subsequent tests still bypass. (`saved` will be the conftest's `_fake_token` function.)

- [ ] **Step 2: Run the test**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/test_api.py::test_endpoint_returns_401_without_auth_override -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 3: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 149 passed`.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/tests/test_api.py && git commit -m "$(cat <<'EOF'
test(stock-dashboard): lock enforcement with 401 assertion (AUTH-T7)

test_endpoint_returns_401_without_auth_override pops the dependency
override, hits /api/dashboard, asserts 401, then restores the override
for subsequent tests. Catches regressions where someone removes
require_token from a router.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8 (AUTH-T8): CLI `scripts/issue_token.py`

**Files:**
- Create: `stock/dashboard/backend/scripts/__init__.py` (empty)
- Create: `stock/dashboard/backend/scripts/issue_token.py`

- [ ] **Step 1: Create the package marker**

```bash
mkdir -p /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/scripts
touch /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/scripts/__init__.py
```

- [ ] **Step 2: Create `scripts/issue_token.py`**

Write `stock/dashboard/backend/scripts/issue_token.py`:

```python
"""CLI: issue / list / revoke API tokens.

Usage (from backend/):
  python -m scripts.issue_token issue --label paul-laptop
  python -m scripts.issue_token issue --label friend --expires-days 90
  python -m scripts.issue_token issue --label permanent --no-expiry
  python -m scripts.issue_token list
  python -m scripts.issue_token revoke <id>
"""
import argparse
import sys
from datetime import datetime, timezone

from core.logging import setup_logging
from db import init_db
from repositories.api_tokens import list_tokens, revoke_token
from services.token_service import issue_token


def cmd_issue(args: argparse.Namespace) -> int:
    expiry = None if args.no_expiry else args.expires_days
    plaintext, token_id = issue_token(label=args.label, expiry_days=expiry)
    print(f"Token id:    {token_id}")
    print(f"Label:       {args.label}")
    print(f"Expires:     {'never' if expiry is None else f'in {expiry} days'}")
    print(f"Token (only shown once):")
    print(f"  {plaintext}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    rows = list_tokens()
    if not rows:
        print("(no tokens)")
        return 0
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    print(f"{'ID':>4}  {'PREFIX':<14}  {'LABEL':<30}  {'CREATED':<24}  {'LAST_USED':<24}  {'STATUS':<10}")
    for r in rows:
        if r["revoked_at"]:
            status = "revoked"
        elif r["expires_at"] and r["expires_at"] < now_iso:
            status = "expired"
        else:
            status = "active"
        print(f"{r['id']:>4}  {r['prefix']:<14}  {r['label']:<30}  "
              f"{r['created_at']:<24}  {(r['last_used_at'] or '-'):<24}  {status:<10}")
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    ok = revoke_token(args.id)
    if ok:
        print(f"Revoked token id={args.id}")
        return 0
    print(f"Token id={args.id} not found or already revoked", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    init_db()  # ensure migrations applied (including 0002)

    parser = argparse.ArgumentParser(description="Stock Dashboard API token CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_issue = sub.add_parser("issue", help="issue a new token")
    p_issue.add_argument("--label", required=True, help="human-readable label (e.g. paul-laptop)")
    p_issue.add_argument("--expires-days", type=int, default=365, help="default 365")
    p_issue.add_argument("--no-expiry", action="store_true", help="never expires")
    p_issue.set_defaults(func=cmd_issue)

    p_list = sub.add_parser("list", help="list all tokens")
    p_list.set_defaults(func=cmd_list)

    p_revoke = sub.add_parser("revoke", help="revoke a token by id")
    p_revoke.add_argument("id", type=int)
    p_revoke.set_defaults(func=cmd_revoke)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Smoke-test the CLI against an in-memory DB**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && DB_PATH=:memory: python3 -c "
import sys
sys.argv = ['issue_token', 'list']
from scripts.issue_token import main
main()
" 2>&1 | head -5
```

Expected: prints `(no tokens)`.

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && DB_PATH=/tmp/auth_smoke.db python3 -m scripts.issue_token issue --label smoke-test --expires-days 1 2>&1 | tail -10
```

Expected: prints token details with `sd_...` plaintext.

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && DB_PATH=/tmp/auth_smoke.db python3 -m scripts.issue_token list 2>&1 | tail -5
```

Expected: shows the issued token with `active` status.

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && DB_PATH=/tmp/auth_smoke.db python3 -m scripts.issue_token revoke 1 2>&1 | tail -3
```

Expected: prints `Revoked token id=1`.

```bash
rm -f /tmp/auth_smoke.db  # cleanup
```

- [ ] **Step 4: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 149 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/scripts/__init__.py stock/dashboard/backend/scripts/issue_token.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add scripts/issue_token CLI (AUTH-T8)

Three sub-commands: issue (--label / --expires-days / --no-expiry),
list, revoke <id>. Calls init_db() to ensure migrations are applied
before any operation. Plaintext token shown ONCE on issuance; only
hash + display prefix saved to DB.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9 (AUTH-T9): `frontend/index.html` — apiFetch wrapper + replacements

**Files:**
- Modify: `stock/dashboard/frontend/index.html`

- [ ] **Step 1: Inject the `apiFetch` wrapper**

Open `stock/dashboard/frontend/index.html`. Find line 428 (or wherever `const API_BASE = ...` is). Immediately after that line, insert:

```javascript
async function apiFetch(path, opts = {}) {
  let token = localStorage.getItem('sd_token');
  if (!token) {
    token = prompt('輸入 API token (sd_...):');
    if (!token) throw new Error('No token provided');
    localStorage.setItem('sd_token', token);
  }
  const res = await fetch(API_BASE + path, {
    ...opts,
    headers: {
      ...(opts.headers || {}),
      'Authorization': `Bearer ${token}`,
    },
  });
  if (res.status === 401) {
    localStorage.removeItem('sd_token');
    alert('Token 無效或過期，請重新整理頁面並輸入新 token');
    throw new Error('Unauthorized');
  }
  return res;
}

function clearToken() {
  localStorage.removeItem('sd_token');
  alert('Token 已清除，重新整理頁面後會要求輸入');
}
```

- [ ] **Step 2: Replace all `fetch(API_BASE + ...)` sites**

Use sed to replace the calls (operates only on this file):

```bash
sed -i.bak 's|fetch(API_BASE + |apiFetch(|g' /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/index.html
rm /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/index.html.bak
```

Verify the count of replacements:

```bash
grep -c "apiFetch(" /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/index.html
grep -c "fetch(API_BASE +" /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/index.html
```

Expected: ~16 hits for `apiFetch(` (15 replaced + 1 inside the wrapper definition's reference; actually the wrapper uses `fetch(API_BASE + path,` which the sed pattern won't catch because it has `path` not `'/api/...'` — verify), 0 hits for `fetch(API_BASE +`.

Note: the wrapper itself contains `await fetch(API_BASE + path, ...)` — but the path argument is a JS variable `path`, not a string literal starting with `'/api/`. The sed pattern `fetch(API_BASE + ` matches BOTH `fetch(API_BASE + '/api/...')` AND `fetch(API_BASE + path, ...)`. After sed runs, the wrapper becomes `apiFetch(path, ...)` — broken! It would recurse into itself.

**Fix**: do the sed BEFORE inserting the wrapper, OR carefully replace only the call-site pattern.

Better order:
1. Replace all `fetch(API_BASE + '` (note the apostrophe, only matches string-literal calls) sites first
2. Then insert the wrapper

Re-do step 2 with the corrected sed:

```bash
# Restore from git (if previous sed corrupted)
git -C /Users/paulwu/Documents/Github/tools checkout stock/dashboard/frontend/index.html

# Now insert wrapper at line 429 (after API_BASE line)
# Done via Edit tool in step 1.

# Now replace ONLY string-literal fetch sites, not wrapper internals
sed -i.bak "s|fetch(API_BASE + '|apiFetch('|g" /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/index.html
rm /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/index.html.bak
```

Verify:

```bash
grep -c "apiFetch(" /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/index.html
grep -c "fetch(API_BASE +" /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/index.html
```

Expected: `apiFetch(` count is 16+ (15 replaced + 1 in wrapper definition? No, wrapper uses `fetch(API_BASE + path` not apiFetch). The wrapper's internal `fetch(API_BASE + path, ...)` is NOT changed by the sed (path is not a string-literal). So:
- `apiFetch(` count: ~15 replaced sites + 0 in wrapper = 15
- `fetch(API_BASE +` count: 1 (the wrapper's internal call to fetch)

Confirm before proceeding.

- [ ] **Step 3: Add a "Logout" button (optional)**

Find the dashboard header — search for the area near top of `<body>`. Add a small button somewhere visible. Open `index.html` in the editor and locate the header `<div>` or similar. Insert near the top header element:

```html
<button onclick="clearToken(); location.reload();" style="float:right; margin:8px; padding:4px 8px; font-size:12px; background:#666; color:#fff; border:none; border-radius:3px; cursor:pointer;">🔓 重新登入</button>
```

(Skip if the layout makes this awkward; the `clearToken()` function in the global scope can be invoked from browser DevTools console.)

- [ ] **Step 4: Lint-check by reading the file**

```bash
grep -n "apiFetch\|clearToken\|API_BASE" /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/index.html | head -20
```

Verify the wrapper and the replaced calls all look right.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/frontend/index.html && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add apiFetch + token UI to index.html (AUTH-T9)

apiFetch(path, opts) wrapper:
- Reads sd_token from localStorage; prompts if missing
- Injects Authorization: Bearer header
- On 401, clears token and alerts user to refresh

clearToken() helper for "logout". Optional 重新登入 button in header.
~15 fetch(API_BASE + '...') call sites converted to apiFetch('...').

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10 (AUTH-T10): `frontend/stock.html` — same pattern

**Files:**
- Modify: `stock/dashboard/frontend/stock.html`

- [ ] **Step 1: Insert `apiFetch` wrapper**

Open `stock/dashboard/frontend/stock.html`. Find line 224 (`const API_BASE = 'https://api.paul-learning.dev';`). Immediately after, insert the same wrapper as in T9:

```javascript
async function apiFetch(path, opts = {}) {
  let token = localStorage.getItem('sd_token');
  if (!token) {
    token = prompt('輸入 API token (sd_...):');
    if (!token) throw new Error('No token provided');
    localStorage.setItem('sd_token', token);
  }
  const res = await fetch(API_BASE + path, {
    ...opts,
    headers: {
      ...(opts.headers || {}),
      'Authorization': `Bearer ${token}`,
    },
  });
  if (res.status === 401) {
    localStorage.removeItem('sd_token');
    alert('Token 無效或過期，請重新整理頁面並輸入新 token');
    throw new Error('Unauthorized');
  }
  return res;
}
```

(No `clearToken` button needed in the per-stock page; the dashboard has it.)

- [ ] **Step 2: Replace `fetch(API_BASE + '...')` sites**

```bash
sed -i.bak "s|fetch(API_BASE + \`|apiFetch(\`|g" /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/stock.html
sed -i.bak2 "s|fetch(API_BASE + '|apiFetch('|g" /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/stock.html
rm /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/stock.html.bak /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/stock.html.bak2
```

Note: stock.html uses backtick template literals (`` fetch(`${API_BASE}/...`) `` and `fetch(API_BASE + '...')`), so two seds.

Looking again at the original grep, the patterns in stock.html are:
- `fetch(\`${API_BASE}/api/stocks/${...}\`)` — backtick template literal style
- These need a different sed pattern.

Actually:

```bash
grep -n "fetch(\`\${API_BASE}\|fetch(API_BASE +" /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/stock.html | head -5
```

If template-literal style is used:

```bash
sed -i.bak 's|fetch(`${API_BASE}|apiFetch(`|g' /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/stock.html
rm /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/stock.html.bak
```

Verify all sites are replaced:

```bash
grep -c "apiFetch(" /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/stock.html
grep -c "fetch(\`\${API_BASE}\|fetch(API_BASE +" /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/stock.html
```

Expected: `apiFetch(` ~10 hits; second pattern returns 1 (the wrapper's internal `fetch(API_BASE + path,`).

- [ ] **Step 3: Manually inspect a few replacements**

```bash
grep -n "apiFetch" /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/stock.html | head -20
```

Verify each line looks like `apiFetch(\`/api/stocks/...\`)` rather than malformed.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/frontend/stock.html && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add apiFetch to stock.html (AUTH-T10)

Same pattern as index.html (AUTH-T9): wrapper + ~10 fetch site
replacements. stock.html uses backtick template literals so the
sed pattern is fetch(`${API_BASE} → apiFetch(`.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11 (AUTH-T11): Final verification + README Bootstrap section

**Files:**
- Modify: `stock/dashboard/README.md`

- [ ] **Step 1: Verify file structure**

```bash
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/scripts/
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/db/migrations/
[ -f /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/dependencies.py ] && echo "dependencies.py: OK" || echo "MISSING"
[ -f /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/services/token_service.py ] && echo "token_service.py: OK" || echo "MISSING"
[ -f /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/repositories/api_tokens.py ] && echo "api_tokens.py: OK" || echo "MISSING"
```

Expected: scripts/ has `__init__.py` and `issue_token.py`; migrations/ has `0001_initial.sql` and `0002_api_tokens.sql`; all three module files OK.

- [ ] **Step 2: Verify all routers have the dependency**

```bash
grep -l "Depends(require_token)" /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/routes/
```

Expected: 5 files listed (alerts.py, fundamentals.py, indicators.py, news.py, stocks.py).

- [ ] **Step 3: Run final suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 149 passed`.

- [ ] **Step 4: Append Bootstrap section to README**

Append to `stock/dashboard/README.md`:

```markdown

## API Authentication (Bootstrap)

After deploy lands, the API enforces `Authorization: Bearer <token>` on every endpoint. To bootstrap the first token:

```bash
# 1. Add the ops Discord webhook (one-time, persists in VPS .env via deploy workflow)
ssh root@$VPS_HOST 'echo "DISCORD_OPS_WEBHOOK_URL=https://discord.com/api/webhooks/..." >> /opt/stock-dashboard/backend/.env'
ssh root@$VPS_HOST 'systemctl restart stock-dashboard'

# 2. Issue your first token
ssh root@$VPS_HOST 'cd /opt/stock-dashboard/backend && .venv/bin/python -m scripts.issue_token issue --label paul-laptop'
# → Copies the printed `sd_...` token

# 3. Open https://paul-learning.dev/, paste token into the prompt
```

The token is stored in browser `localStorage`. The 🔓 重新登入 button on the dashboard header clears it. Subsequent deploys preserve the DB and the `.env`, so the token keeps working.

CLI commands:

```bash
python -m scripts.issue_token issue --label <name>            # default 365 days
python -m scripts.issue_token issue --label <name> --no-expiry
python -m scripts.issue_token list
python -m scripts.issue_token revoke <id>
```

Add `DISCORD_OPS_WEBHOOK_URL` as a GitHub Secret so future deploys re-populate it.
```

- [ ] **Step 5: Verify branch log**

```bash
cd /Users/paulwu/Documents/Github/tools && git log --oneline master..HEAD
```

Expected: 11 commits (T1-T10 + T11). T11 is the last (this commit).

Wait — T11 is THIS task. So the prior commits should be T1-T10 (10 commits), and this task adds T11 making 11 total.

Re-run after the next commit.

- [ ] **Step 6: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/README.md && git commit -m "$(cat <<'EOF'
docs(stock-dashboard): add API auth bootstrap runbook to README (AUTH-T11)

Documents the post-deploy SSH procedure: add DISCORD_OPS_WEBHOOK_URL
to .env, restart, issue first token, paste into dashboard. CLI
sub-commands reference. Closes out Phase 4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 7: Branch log check (post-commit)**

```bash
git log --oneline master..HEAD
```

Expected (newest first):

```
… AUTH-T11
… AUTH-T10
… AUTH-T9
… AUTH-T8
… AUTH-T7
… AUTH-T6
… AUTH-T5
… AUTH-T4
… AUTH-T3
… AUTH-T2
… AUTH-T1
```

11 commits.

---

## Spec Coverage Self-Check

| Spec section | Task |
|---|---|
| §2 DB migration | T1 |
| §3 repositories/api_tokens.py | T1 |
| §4 services/token_service.py | T3 |
| §5 settings.discord_ops_webhook_url | T2 |
| §6 api/dependencies.py require_token | T4 |
| §7 routers attach dependency | T6 |
| §8 conftest dependency_overrides | T5; enforcement test in T7 |
| §9 CLI scripts/issue_token.py | T8 |
| §10 frontend HTML changes | T9 (index.html), T10 (stock.html) |
| §11 migration order | T1-T11 (11 tasks) |
| §12 acceptance | T11 (verification steps) |
| §13 risks (CORS preflight, last_used UPDATE rate) | Mitigated through design; verified in deploy |
| Bootstrap runbook | T11 README append |

All sections covered.

---

## Execution Notes

- **Branch strategy**: `git checkout -b feat/auth-multi-token` from master before T1; merge `--no-ff` after T11 passes. Same as prior phases.
- **Total tasks**: 11. 11 commits.
- **Estimated time**: ~5-15 minutes per task; total 1.5-2 hours. T6 (5 router edits) and T9-T10 (HTML changes) are the longest.
- **No new dependencies**.
- **Each task ends green**: 5 baseline failures + a steadily growing pass count (T1: 142, T3: 148, T7: 149).
- **Deploy timing**: after T11 verification + merge to master + push. Bootstrap runbook in README guides the post-deploy SSH steps.

## Future-phase Notes

- **Phase 5 (FE-)** deletes the HTML `apiFetch` wrappers and replaces with React + `<TokenGate>` + `apiFetch.ts`.
- The 401 enforcement test (T7) stays useful indefinitely as a regression guard.
- Auth-burst threshold tuning may surface from real ops data — adjust `_BURST_*` constants in `services/token_service.py` if needed.
