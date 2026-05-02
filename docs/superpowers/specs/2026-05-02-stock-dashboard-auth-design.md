# Stock Dashboard AUTH-: Multi-Token API Authentication Design Spec

**Date**: 2026-05-02
**Phase**: AUTH- (Phase 4)
**Parent spec**: `docs/superpowers/specs/2026-05-02-stock-dashboard-conventions-design.md` §2.5, §7 Phase 4
**Predecessors**: MIGR / BE-A / BE-B / BE-C / REG- (full layered backend with alert registry deployed)
**Scope**:
- Add `api_tokens` table via migration `0002_api_tokens.sql`
- New backend modules: `repositories/api_tokens.py`, `services/token_service.py`, `api/dependencies.py`, `scripts/issue_token.py`
- All 5 routers attach `Depends(require_token)` — every API endpoint requires `Authorization: Bearer <token>`
- `core/settings.py` adds `discord_ops_webhook_url`; auth-burst notifier uses it
- `tests/conftest.py` injects `app.dependency_overrides[require_token]` so existing 138+ tests need no modification
- Frontend: both `index.html` and `stock.html` get an `apiFetch(...)` wrapper that handles token storage + 401 retry; 25 existing `fetch(API_BASE + ...)` sites are replaced

## Goals

1. Enforce token-based authentication on every API endpoint immediately upon deploy.
2. Make token issuance / listing / revocation operable via SSH + CLI (no admin UI).
3. Preserve existing test surface: all 138+ tests pass without modification.
4. Provide an auth-burst Discord notifier so brute-force / misconfigured-client floods surface visibly.
5. Keep `index.html` and `stock.html` working with a minimal `apiFetch` wrapper, so the deployed dashboard continues to function once the user pastes a token.

## Non-Goals

- Do not introduce per-user accounts, JWT, OAuth, or password login. Single shared secret per token, multiple tokens per system.
- Do not add a token management UI. CLI on VPS handles issuance / revocation. (Reconsider in Phase 5 once React frontend exists.)
- Do not add token-rotation automation. Manual revoke + reissue when needed.
- Do not exempt any endpoint from auth (no health-check route, no public read endpoints).
- Do not modify `repositories/*`, `services/{alert_engine,alert_notifier,alert_registry,backfill,indicators/*}.py`, `fetchers/*`, `core/{logging,errors}.py`, `db/{runner,connection}.py`, or migrations other than the new `0002`.
- Do not modify existing test files (`test_alerts.py`, `test_db.py`, etc.). Tests bypass auth via `dependency_overrides`.

---

## 1. Target File Structure

```
backend/
├── db/migrations/
│   ├── 0001_initial.sql               ← unchanged
│   └── 0002_api_tokens.sql             ← NEW
├── repositories/
│   └── api_tokens.py                   ← NEW
├── services/
│   └── token_service.py                ← NEW
├── api/
│   ├── dependencies.py                 ← NEW (require_token Depends provider)
│   └── routes/
│       ├── indicators.py               ← MODIFIED (router-level dependency)
│       ├── stocks.py                   ← MODIFIED
│       ├── fundamentals.py             ← MODIFIED
│       ├── alerts.py                   ← MODIFIED
│       └── news.py                     ← MODIFIED
├── core/
│   └── settings.py                     ← MODIFIED (add discord_ops_webhook_url)
├── scripts/
│   ├── __init__.py                     ← NEW (empty)
│   └── issue_token.py                  ← NEW CLI
└── main.py                             ← unchanged

frontend/
├── index.html                          ← MODIFIED (apiFetch wrapper + ~15 fetch site replacements)
└── stock.html                          ← MODIFIED (apiFetch wrapper + ~10 fetch site replacements)

tests/
├── conftest.py                         ← MODIFIED (dependency_overrides for require_token)
├── unit/
│   └── test_token_service.py           ← NEW (~6 tests)
└── test_api.py                         ← MODIFIED (add 1 test verifying enforcement)
```

---

## 2. DB Migration

### `db/migrations/0002_api_tokens.sql`

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

Schema notes:

- **`token_hash`**: SHA-256 hex of plaintext token. UNIQUE so duplicate accidental re-issues fail loudly.
- **`prefix`**: `sd_` + first 6 chars of the URL-safe body (e.g. `sd_AbCdEf`). Used for human identification in CLI list output without revealing the full token.
- **`expires_at`**: ISO timestamp. NULL = never expires. CLI default = 365 days from issuance.
- **`last_used_at`**: ISO timestamp updated on every successful verification.
- **`revoked_at`**: ISO timestamp set by CLI revoke; non-NULL means rejected by `verify_token`.

VPS migration applies via the runner (REG- runner unchanged); existing rows in other tables are not touched. The runner's baseline mechanism does not apply because `0002_*` is a new migration after `0001` was already recorded — it'll execute normally on the VPS DB.

---

## 3. `repositories/api_tokens.py`

Pure SQL layer; no business logic. Five functions:

| Function | Signature | Purpose |
|---|---|---|
| `insert_token` | `(token_hash, prefix, label, expires_at=None) -> int` | Insert and return row id |
| `find_active_by_hash` | `(token_hash) -> dict \| None` | Return row if not revoked and not expired |
| `touch_last_used` | `(token_id) -> None` | UPDATE last_used_at to now |
| `list_tokens` | `() -> list[dict]` | All rows (CLI listing) |
| `revoke_token` | `(token_id) -> bool` | UPDATE revoked_at; True if a row was updated |

Standard repository pattern (uses `db.connection.get_connection`).

---

## 4. `services/token_service.py`

Business logic for token issuance, verification, and auth-burst tracking.

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
_TOKEN_BODY_BYTES = 32          # secrets.token_urlsafe(32) == 43 chars
_DEFAULT_EXPIRY_DAYS = 365
_PREFIX_DISPLAY_LEN = 6

# Auth-burst tracking (in-memory; resets on restart per CONVENTIONS §4.3)
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

    Plaintext shown ONCE to caller; only hash + display prefix stored.
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


def verify_token(plaintext: str) -> dict | None:
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

Design notes:

- **Token format**: `sd_<43 url-safe chars>` = 46 chars total. `secrets.token_urlsafe(32)` = 32 bytes → 43-char base64-url. `sd_` prefix follows GitHub PAT / Stripe key conventions for secret scanning.
- **Hash with SHA-256** (not bcrypt/scrypt): tokens are high-entropy random strings (256 bits), so peppered hash is overkill. Standard practice for API tokens.
- **`last_used_at` UPDATE on every verify**: writes are cheap on SQLite with our scale (~1 update/sec at peak); enables stale-token detection.
- **Auth-burst lock + Discord call**: notification is dispatched outside the lock to avoid blocking other 401s. `should_notify` flag captures the decision inside the lock.

---

## 5. `core/settings.py` Addition

```python
class Settings(BaseSettings):
    ...
    discord_stock_webhook_url: SecretStr | None = None
    discord_ops_webhook_url: SecretStr | None = None     # ← NEW
    finmind_token: SecretStr = SecretStr("")
    ...
```

VPS bootstrap (manual, after deploy):
- Add `DISCORD_OPS_WEBHOOK_URL=https://discord.com/api/webhooks/...` to `/opt/stock-dashboard/backend/.env`
- Add `DISCORD_OPS_WEBHOOK_URL` GitHub Secret so subsequent deploys preserve it

If unset, auth-burst tracking still runs; Discord call is skipped with a `logger.warning`.

---

## 6. `api/dependencies.py`

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
    """Verify Authorization: Bearer <token>. Raises 401 on miss/invalid."""
    client_ip = request.client.host if request.client else "unknown"

    if not authorization or not authorization.startswith("Bearer "):
        track_auth_failure(client_ip)
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization[len("Bearer "):].strip()
    record = verify_token(token)
    if record is None:
        track_auth_failure(client_ip)
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return record
```

Naming clarification: `services.token_service.verify_token` is the pure verification function (returns dict or None). `api.dependencies.require_token` is the FastAPI dependency that calls `verify_token` and raises HTTPException. Different concerns, different names.

---

## 7. Routers attach the dependency

Each `api/routes/*.py` modifies its router declaration:

```python
# OLD
router = APIRouter(prefix="/api", tags=["indicators"])

# NEW
from fastapi import Depends
from api.dependencies import require_token

router = APIRouter(
    prefix="/api",
    tags=["indicators"],
    dependencies=[Depends(require_token)],
)
```

5 router files: `indicators.py`, `stocks.py`, `fundamentals.py`, `alerts.py`, `news.py`. ~10 lines of diff total.

---

## 8. Test Strategy

### `tests/conftest.py` change

```python
# At top, after `import db`:
from main import app
from api.dependencies import require_token


def _fake_token():
    return {
        "id": 0, "prefix": "test_", "label": "test",
        "created_at": "2026-01-01T00:00:00",
        "expires_at": None, "last_used_at": None, "revoked_at": None,
    }


app.dependency_overrides[require_token] = _fake_token
```

This module-level override applies to every `TestClient(app)` request across all tests. Existing 138+ tests need no modification.

### New tests

- `tests/unit/test_token_service.py` — 6 tests:
  - `test_issue_token_returns_plaintext_and_id`
  - `test_verify_token_returns_record_for_valid`
  - `test_verify_token_returns_none_for_unknown`
  - `test_verify_token_returns_none_for_revoked`
  - `test_token_hash_is_deterministic`
  - `test_issue_token_with_no_expiry`
- `tests/test_api.py::test_endpoint_returns_401_without_auth_override` — verifies enforcement is real by temporarily popping the override.

(`auth_burst` is intentionally not unit-tested at first round — its in-memory state and time-window logic are awkward to test deterministically. Manual smoke check in deploy verification covers it.)

---

## 9. CLI: `scripts/issue_token.py`

Three sub-commands: `issue`, `list`, `revoke`. Full implementation in plan; here's the usage:

```bash
# Issue a new token (default 365 days)
python -m scripts.issue_token issue --label paul-laptop

# Issue with custom expiry
python -m scripts.issue_token issue --label friend --expires-days 90

# Issue with no expiry
python -m scripts.issue_token issue --label permanent --no-expiry

# List all tokens (active + revoked + expired)
python -m scripts.issue_token list

# Revoke by id
python -m scripts.issue_token revoke 1
```

Run from `backend/` directory on the VPS. The CLI imports `init_db()` first to ensure migrations are up-to-date.

---

## 10. Frontend HTML Changes

Both `index.html` and `stock.html` get this `apiFetch` wrapper (placed near the top of the `<script>` block):

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

Then mechanical replacement of every `fetch(API_BASE + ...)` site with `apiFetch(...)`:

- `index.html` ~15 sites
- `stock.html` ~10 sites

POST/DELETE/PATCH calls work because `apiFetch` merges `opts.headers` into the final request, preserving `Content-Type: application/json` and any other headers the caller passes.

`index.html` gets an additional `🔓 重新登入` button in the header bar that triggers `clearToken(); location.reload();`. (Optional UX touch; can be omitted.)

---

## 11. Migration Order (11 tasks)

| # | Task |
|---|---|
| AUTH-T1 | `0002_api_tokens.sql` migration + `repositories/api_tokens.py` + 3 unit tests for repo |
| AUTH-T2 | `core/settings.py` adds `discord_ops_webhook_url` |
| AUTH-T3 | `services/token_service.py` (issue/verify/burst) + `tests/unit/test_token_service.py` (6 tests) |
| AUTH-T4 | `api/dependencies.py` `require_token` |
| AUTH-T5 | `tests/conftest.py` adds `app.dependency_overrides[require_token]` (no router changes yet — verify suite still 5/138 pass) |
| AUTH-T6 | Add `dependencies=[Depends(require_token)]` to all 5 routers; suite stays 5/138 (override bypasses) |
| AUTH-T7 | `tests/test_api.py::test_endpoint_returns_401_without_auth_override` (5/139) |
| AUTH-T8 | `scripts/__init__.py` + `scripts/issue_token.py` CLI; smoke-test from terminal |
| AUTH-T9 | `frontend/index.html`: `apiFetch` + `clearToken` + 重新登入 button + ~15 `fetch` site replacements |
| AUTH-T10 | `frontend/stock.html`: `apiFetch` + ~10 `fetch` site replacements |
| AUTH-T11 | Final verification (suite, file structure) + add Bootstrap section to `stock/dashboard/README.md` |

T1-T5 ship infrastructure; T6 enforces (with override in tests); T7 locks down enforcement is real; T8 makes CLI usable; T9-T10 bring frontend in sync; T11 closes out.

After merge + push, the manual deploy runbook (NOT in the plan):

```bash
# After deploy completes:
ssh root@$VPS_HOST 'echo "DISCORD_OPS_WEBHOOK_URL=https://discord.com/api/webhooks/..." >> /opt/stock-dashboard/backend/.env'
ssh root@$VPS_HOST 'cd /opt/stock-dashboard/backend && systemctl restart stock-dashboard'
ssh root@$VPS_HOST 'cd /opt/stock-dashboard/backend && .venv/bin/python -m scripts.issue_token issue --label paul-laptop'
# → Copy printed token, paste into dashboard prompt
```

---

## 12. Acceptance Criteria

- `db/migrations/0002_api_tokens.sql` exists; runner applies it on VPS without re-running 0001
- `api_tokens` table exists on VPS DB with the documented schema
- `repositories/api_tokens.py` exposes 5 functions with the documented signatures
- `services/token_service.py` exposes `issue_token`, `verify_token`, `track_auth_failure`
- `api/dependencies.py` exposes `require_token` (async function)
- All 5 routers list `dependencies=[Depends(require_token)]` in their `APIRouter(...)` constructors
- `core/settings.py` `Settings` class includes `discord_ops_webhook_url: SecretStr | None`
- `scripts/issue_token.py` CLI three sub-commands work
- Full test suite: 5 baseline + ~145 passed (138 existing + 6 token_service + 1 enforcement-check)
- VPS deploy: service `active`; without `Authorization` header, `curl http://127.0.0.1:8000/api/dashboard` returns 401; with valid token, returns 200
- `journalctl -u stock-dashboard` shows `token_issued` line after CLI issuance, no startup errors

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Bootstrap window: deploy lands but no token issued yet → dashboard locked out | Runbook < 2 minutes; documented in README; only affects single-developer workflow |
| `Authorization` header CORS preflight | FastAPI's CORS middleware handles `OPTIONS` before route dependencies; preflight does not invoke `require_token`. Verified empirically post-deploy. |
| `localStorage` cleared on browser cache wipe → user has to re-paste token | Acceptable; `prompt()` re-asks. Tokens last 1 year so once-set rarely needs refresh. |
| `last_used_at` UPDATE on every verify writes to DB constantly | At ~1 verify/sec peak SQLite handles trivially. If DB write contention emerges, batch the update via deque + periodic flush — not needed at current scale. |
| Auth-burst dict grows unbounded with random IPs | Acceptable for personal dashboard. If DDoS-class concerns arise, add LRU cap to `_failures` dict; YAGNI now. |
| `prompt()` UX: ugly modal, copy-paste token | Acceptable interim UX; Phase 5 React rewrite replaces with `<TokenGate>` component. |
| Test override at module load could leak between sessions | `dependency_overrides` is a dict on the `app` instance; for our single-process pytest run it works. If a future test wants to test the real path, it can `app.dependency_overrides.pop(require_token)` and restore in teardown. |
| `sd_` prefix and SHA-256 hash means GitHub secret scanning may detect leaked tokens in commits | This is desirable; if you accidentally push a token, GitHub will warn you. Aligns with industry secret-scanning conventions. |

---

## 14. After This Phase

- **Phase 5 (FE-)**: React rewrite consumes `apiFetch` pattern in a proper `<TokenGate>` component. The `Authorization: Bearer` header logic moves into the React-Query / `lib/api-client.ts` wrapper. The HTML `apiFetch` is deleted.
- **Future improvement**: token management admin UI inside the React dashboard (issue / list / revoke from web). Listed in CONVENTIONS.md §6 backlog.
- **Future improvement**: structured / tagged scopes per token (read-only, admin) — currently every token has full access; YAGNI now since one developer.
