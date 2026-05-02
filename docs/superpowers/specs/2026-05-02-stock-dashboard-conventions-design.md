# Stock Dashboard Conventions — Design Spec

**Date**: 2026-05-02
**Scope**: Establish a written conventions document for `stock/dashboard/`, plus a migration path from the current state to a layered backend, formalised fetcher / alert pattern, hand-rolled DB migrations, multi-token auth, and a React + TypeScript frontend.
**Audience**: Future-self + AI agents (Claude Code, Codex, etc.).
**Output of this spec**: `stock/dashboard/CONVENTIONS.md` (the living conventions doc) and a phased plan to evolve the codebase to match it.

## Goals

1. Write a single conventions doc (`stock/dashboard/CONVENTIONS.md`) that captures directory structure, naming, fetcher pattern, alert flow, DB migration policy, testing, error handling, logging, frontend stack, and git workflow.
2. Define the **target state** for five concrete refactors that will be brainstormed and executed independently after this spec lands:
   - Backend layered architecture (was "A: backend bloat")
   - Frontend React + TypeScript rewrite (was "B: frontend reframe")
   - Hand-rolled DB migration runner (was "C: schema sprawl")
   - Fetcher / alert registry formalisation (was "D: fetcher/alert flow")
   - Multi-token auth (newly added during brainstorm)
3. Sequence those refactors so each phase leaves the system in a runnable, deployable state.

## Non-Goals

- This spec does not implement any of the refactors. Each phase will get its own spec → plan → implementation cycle.
- This spec does not cover other tools in the repo (`document_translator`, `personal_retro`, `medium`, etc.).
- This spec does not introduce a user-account system or per-user data isolation.

---

## 1. Target Directory Structure

```
stock/dashboard/
├── CONVENTIONS.md                  ← living conventions doc
├── README.md                       ← deployment / operational notes only
├── deploy.sh
├── stock-dashboard.service
│
├── backend/
│   ├── main.py                     ← FastAPI app assembly, CORS, startup hooks
│   ├── scheduler.py                ← APScheduler job definitions
│   ├── api/
│   │   ├── dependencies.py         ← verify_token, get_db_conn
│   │   ├── routes/
│   │   │   ├── stocks.py
│   │   │   ├── alerts.py
│   │   │   ├── indicators.py
│   │   │   ├── fundamentals.py
│   │   │   ├── watchlist.py
│   │   │   └── tokens.py           ← optional: list/revoke own tokens
│   │   └── schemas/                ← Pydantic request/response models per resource
│   ├── services/
│   │   ├── alert_engine.py         ← pure evaluation logic (extracted from alerts.py)
│   │   ├── alert_registry.py       ← @register_indicator registry
│   │   ├── alert_notifier.py       ← Discord push (extracted from alerts.py)
│   │   ├── backfill.py
│   │   ├── token_service.py
│   │   └── indicators/             ← one file per indicator (registers on import)
│   ├── repositories/               ← SQL only, one file per table domain
│   │   ├── indicators.py
│   │   ├── stocks.py
│   │   ├── alerts.py
│   │   ├── fundamentals.py
│   │   ├── chip.py
│   │   └── api_tokens.py
│   ├── fetchers/
│   │   ├── base.py                 ← Fetcher Protocol + Snapshot dataclass
│   │   ├── yfinance_fetcher.py
│   │   ├── fear_greed.py
│   │   ├── chip_total.py
│   │   ├── chip_stock.py
│   │   ├── ndc.py
│   │   ├── volume.py
│   │   ├── broker.py
│   │   ├── fundamentals_stock.py
│   │   └── news.py
│   ├── db/
│   │   ├── connection.py           ← get_connection / DB_PATH
│   │   ├── runner.py               ← migration runner (~50 LOC)
│   │   └── migrations/
│   │       ├── 0001_initial.sql
│   │       └── …
│   ├── core/                       ← cross-layer shared
│   │   ├── logging.py
│   │   ├── settings.py
│   │   └── errors.py
│   ├── scripts/
│   │   └── issue_token.py          ← CLI: issue / revoke / list tokens
│   └── requirements.txt
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── routes/
│       │   ├── index.tsx           ← React Router config
│       │   ├── DashboardPage.tsx
│       │   └── StockDetailPage.tsx
│       ├── components/
│       │   ├── TokenGate.tsx
│       │   └── ui/                 ← shadcn/ui copies (editable)
│       ├── features/
│       │   ├── alerts/
│       │   ├── watchlist/
│       │   ├── indicators/
│       │   └── fundamentals/
│       ├── lib/
│       │   ├── api-client.ts
│       │   └── formatters.ts
│       ├── store/
│       │   ├── auth-store.ts       ← Zustand: token state
│       │   └── ui-store.ts
│       └── types/                  ← cross-feature shared types
│
└── tests/
    ├── conftest.py
    ├── unit/
    ├── integration/
    └── api/
```

Naming conventions:

- Python: `snake_case` modules and functions, `PascalCase` classes.
- TypeScript: `PascalCase` for components and types, `camelCase` for functions/variables, `kebab-case` for filenames except React components (`PascalCase.tsx`).
- Migration files: `NNNN_<snake_name>.sql` (4-digit zero-padded).

---

## 2. Backend Conventions

### 2.1 Layered Architecture

| Layer | Responsibility | Allowed to call | Forbidden |
|---|---|---|---|
| `api/routes/` | Parse request, dispatch to service or repository, build response | services, repositories (read-only), schemas | SQL strings, external HTTP, business logic |
| `api/schemas/` | Pydantic models | — | — |
| `api/dependencies.py` | FastAPI `Depends` providers | repositories | business logic |
| `services/` | Business logic, orchestration | repositories, fetchers, other services, core | direct SQL |
| `repositories/` | SQL queries against `db/connection.py` | db | services, business judgement |
| `fetchers/` | External data sources, conform to `Fetcher` Protocol | core | repositories, DB writes |
| `db/` | Connection + migration runner | — | — |
| `core/` | Logging, settings, common exceptions | — | other layers |

Dependency direction (strict, one-way):

```
routes → services → repositories → db
            ↓
         fetchers → core
```

**Forbidden imports**: a repository must never import a service; a fetcher must never import a repository; a route must not call a fetcher directly (orchestrate via a service).

Fetchers explicitly do not write to the DB. Scheduler jobs become thin orchestrators: `fetch → list[Snapshot] → repository.bulk_insert → service.check_alerts`.

### 2.2 Fetcher Protocol

> **Status amendment (REG-T13, 2026-05-02)**: After implementation of Phase 1–3, the strict Fetcher Protocol described below was found to misfit the codebase reality (9 fetchers have widely different shapes: numeric snapshots, multi-column daily rows, text articles, OHLC time-series, multi-stock orchestrators). The high-value goal of "one-file changes for new alert-able indicators" is fully achieved through the **Alert Indicator Registry** (§2.3); strict Fetcher Protocol/Snapshot is **deferred** and may be revisited only if pain emerges. The original spec text below is retained for context. New fetchers should follow these lighter conventions:
>
> - Module named after source + topic (e.g. `chip_stock.py`, `fundamentals_stock.py`).
> - HTTP calls wrap with `tenacity.retry` (exponential backoff, max 3 attempts).
> - Failures log via stdlib `logging` and return a falsy/None signal to callers — do not propagate raw exceptions.
> - Where possible, fetchers return data structures that callers persist via `repositories/`. Existing fetchers that write the DB themselves are not a regression.
>
> See `docs/superpowers/specs/2026-05-02-stock-dashboard-reg-design.md` for rationale.

#### Original Fetcher Protocol design (deferred, retained for context)

`backend/fetchers/base.py`:

```python
from typing import Protocol, runtime_checkable
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Snapshot:
    """A single data point fetched from an external source."""
    indicator: str           # maps to indicator_snapshots.indicator OR a stock ticker
    timestamp: datetime
    value: float
    extra: dict | None = None  # serialised into extra_json

@runtime_checkable
class Fetcher(Protocol):
    name: str  # unique identifier, used in logging / scheduler job IDs

    def fetch(self, **kwargs) -> list[Snapshot]:
        """Fetch latest data points. Must be idempotent.

        Raise FetcherError on transient failure (let tenacity retry handle it).
        """
```

Rules:

- Each fetcher module is named after its source + topic (e.g. `chip_stock.py`, `fundamentals_stock.py`).
- A module exposes objects/functions that conform to the `Fetcher` protocol.
- HTTP calls are wrapped with `tenacity.retry` (exponential backoff, max 3 attempts).
- Failures raise `FetcherError`; raw exceptions never escape.
- Fetchers do not write to the DB. Callers (scheduler jobs, backfill service) decide what to persist.

### 2.3 Alert Indicator Registry

`backend/services/alert_registry.py`:

```python
from dataclasses import dataclass
from typing import Callable

@dataclass
class IndicatorSpec:
    key: str                                       # e.g. "revenue_yoy"
    label: str                                     # human-readable, e.g. "月營收年增率"
    unit: str                                      # display unit, e.g. "%"
    evaluator: Callable[[Alert, Snapshot], bool]   # decides whether alert fires
    fetcher_hook: Callable[[str], None]            # triggers the relevant fetcher
    api_validator: Callable[[AlertCreate], None]   # validates payload at create time

_REGISTRY: dict[str, IndicatorSpec] = {}

def register_indicator(key: str, *, label: str, unit: str,
                       fetcher_hook, api_validator):
    def decorator(evaluator):
        _REGISTRY[key] = IndicatorSpec(
            key=key, label=label, unit=unit,
            evaluator=evaluator,
            fetcher_hook=fetcher_hook,
            api_validator=api_validator,
        )
        return evaluator
    return decorator

def get_indicator(key: str) -> IndicatorSpec: ...
def list_indicators() -> list[IndicatorSpec]: ...
```

Adding a new indicator (formalised flow):

1. Create `services/indicators/<key>.py` with the evaluator and `@register_indicator(...)` call.
2. Ensure the matching fetcher exists (or add one to `fetchers/`).
3. The API validator and frontend form auto-read from the registry; no other layer changes required.

### 2.4 DB Migration Runner

File naming: `db/migrations/NNNN_<snake_name>.sql` starting at `0001`.

Runner behaviour (`db/runner.py`):

1. On startup, ensure `schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT)` exists.
2. Discover files in `migrations/`, sort by the numeric prefix.
3. Skip already-applied versions; apply the rest in order, each inside its own transaction.
4. On failure, log + raise. The service does not start.

Rules:

- Forward-only. No down migrations.
- One file = one logical change. Commit messages reference the file.
- A migration that has been pushed to master is immutable. To fix mistakes, write a follow-up migration.
- `init_db()` is removed. The `:memory:` DB used in tests also runs through the migration runner via a fixture.

### 2.5 Auth Dependency

`backend/api/dependencies.py`:

```python
async def verify_token(authorization: str | None = Header(None)) -> ApiToken:
    if not authorization or not authorization.startswith("Bearer "):
        _track_auth_failure(client_ip)
        raise HTTPException(401, "Missing token")
    token = authorization[7:]
    record = api_tokens_repo.find_by_hash(sha256(token))
    if not record or record.revoked_at or (record.expires_at and now() > record.expires_at):
        _track_auth_failure(client_ip)
        raise HTTPException(401, "Invalid token")
    api_tokens_repo.touch_last_used(record.id)
    return record
```

All routers attach the dependency once: `APIRouter(dependencies=[Depends(verify_token)])`.

`api_tokens` table:

```sql
CREATE TABLE api_tokens (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash   TEXT NOT NULL UNIQUE,    -- sha256(token)
    prefix       TEXT NOT NULL,           -- "sd_" + first 6 chars, for display
    label        TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    expires_at   TEXT,                    -- NULL = never; CLI default = +1 year
    last_used_at TEXT,
    revoked_at   TEXT
);
CREATE INDEX idx_token_hash ON api_tokens(token_hash);
```

Token format: `sd_` + `secrets.token_urlsafe(32)`. Returned in plaintext **once** at issuance; only the hash is stored.

Auth failure tracking (in-memory, resets on restart):

- Per-IP rolling window: 5 failures within 5 minutes.
- On threshold breach, push to `DISCORD_OPS_WEBHOOK_URL` once; cooldown of 1 hour per IP.
- No DB persistence — this is transient operational signal.

---

## 3. Frontend Conventions

### 3.1 Stack

| Concern | Choice |
|---|---|
| Framework | React 18 + TypeScript |
| Build | Vite |
| Server state | TanStack Query v5 |
| Client state | Zustand |
| Routing | React Router v6 (config-based, not file-based) |
| Styling | Tailwind CSS |
| Components | shadcn/ui (copied into `components/ui/`) |
| Forms | react-hook-form + zod (recommended for non-trivial forms) |
| Testing | Vitest + React Testing Library + msw |

### 3.2 State Management Boundaries

- **TanStack Query** owns all server-derived data. Use `useQuery` / `useMutation`. Never copy server data into Zustand.
- **Zustand** holds purely client-side state: auth token, UI toggles, selected ticker (when shared across pages).
- **`useState`** for component-local transient state.
- **URL state** (`useSearchParams`) for the current page, filters, selected ticker — favoured over Zustand to keep links shareable and refresh-stable.

Forbidden:

- Caching server data in Zustand.
- Manual `useEffect` synchronisation between server and client state.

### 3.3 Feature Folder Layout

```
features/
└── <feature>/
    ├── api.ts          ← TanStack Query hooks (useAlerts, useCreateAlert, …)
    ├── components/
    ├── types.ts        ← TS types for this feature
    └── utils.ts        ← feature-local helpers
```

Rules:

- One feature per backend resource or related route group.
- Features may **not** import each other. Anything shared moves up: components → `components/`, utils → `lib/`, types → `types/`.
- Features may import from `components/`, `lib/`, `store/`, `types/`. The reverse is forbidden.

### 3.4 API Client + Auth Flow

`src/lib/api-client.ts`:

```ts
const BASE_URL = import.meta.env.VITE_API_BASE_URL;

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = useAuthStore.getState().token;
    const res = await fetch(`${BASE_URL}${path}`, {
        ...init,
        headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...init.headers,
        },
    });
    if (res.status === 401) {
        useAuthStore.getState().clearToken();
        throw new ApiError(401, "Unauthorized");
    }
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.json();
}
```

Rules:

- Every `features/<x>/api.ts` calls `apiFetch`. Never use raw `fetch`.
- A 401 clears the token, which causes `<TokenGate>` to re-render the input form.
- 5xx is left to TanStack Query's default retry (3 attempts) plus a toast.
- Query keys are arrays starting with the feature name: `['alerts']`, `['stocks', ticker]`, `['indicators', key, 'history']`.

### 3.5 TokenGate

```tsx
<TokenGate>
  <QueryClientProvider client={queryClient}>
    <RouterProvider router={router} />
  </QueryClientProvider>
</TokenGate>
```

Rules:

- Token persists in `localStorage` only. No cookies.
- A "logout" action clears the token and reloads the app to flush the React Query cache.
- A 5xx or network failure does not clear the token. Only an actual 401 does.

### 3.6 Type Sharing

For now: hand-write `features/<x>/types.ts` to mirror the backend Pydantic schemas. Listed in §6 as a future improvement: generate types from `/openapi.json` via `openapi-typescript`.

### 3.7 Routing

Config-based (`src/routes/index.tsx`), not file-based, while page count is small:

```tsx
export const router = createBrowserRouter([
  { path: "/", element: <DashboardPage /> },
  { path: "/stocks/:ticker", element: <StockDetailPage /> },
]);
```

### 3.8 Styling

- Tailwind utility classes first.
- No CSS-in-JS, no CSS Modules.
- Recurring class combinations may use `@apply` in `index.css` or be extracted into a component.
- shadcn/ui components are editable after copy-in; preserve `displayName` and `cn()` usage when modifying.
- Dark mode is deferred (see §6).

### 3.9 Frontend Testing

- Vitest + React Testing Library.
- TDD applies (see §4.1).
- Priority: custom hooks > business-logic components > pure presentational components (latter optional).
- TanStack Query hooks tested via a `QueryClient` wrapper. HTTP mocked with `msw`.

---

## 4. Cross-cutting Conventions

### 4.1 Testing

| Folder | Subject under test | May touch | Must mock |
|---|---|---|---|
| `tests/unit/` | Pure functions, alert evaluators, helpers | nothing external | n/a |
| `tests/integration/` | Repositories, fetcher parsing, service wiring | `:memory:` SQLite via migration runner | external HTTP (`responses` / `pytest-httpx`) |
| `tests/api/` | FastAPI routes including auth | TestClient + `:memory:` DB | HTTP + scheduler must not run |

TDD rules:

1. Each new feature begins with a task list (committed under `(T0)`).
2. For each `Tn`: a failing test must precede or be committed alongside the implementation. The test is written first.
3. Allowed: red-green-refactor in a single commit (`feat(scope): add X with tests (T1)`). Forbidden: merging implementation first and adding tests in a later commit.

Shared fixtures (in `conftest.py`):

- `db_conn` — `:memory:` connection, migrations applied.
- `client` — `TestClient(app)` with a valid token auto-injected.
- `frozen_now(monkeypatch)` — pin `datetime.now()`.
- `mock_finmind`, `mock_yfinance` — HTTP-layer mocks.

Naming:

- Files: `test_<module>.py`.
- Functions: `test_<scenario>_<expected_result>`.
- English only; no `test_should_…`.

### 4.2 Logging

`backend/core/logging.py`:

- stdlib `logging`, `StreamHandler` to stdout (systemd journalctl on the VPS picks it up).
- Format: `%(asctime)s %(levelname)s %(name)s %(message)s`.
- Root level `INFO`; overridable via `LOG_LEVEL`.
- Third-party noise (`urllib3`, `apscheduler`) clamped to `WARNING`.

Usage:

```python
logger = logging.getLogger(__name__)  # at module top
```

Rules:

- No `print()`.
- Messages: English, grep-friendly tokens (e.g. `fetch_failed indicator=fear_greed`).
- Truncate long payloads. Never log the full response body.
- **Never log**: API tokens, `Authorization` headers, Discord webhook URLs, FinMind tokens.

Levels:

| Level | Use for |
|---|---|
| `DEBUG` | Local development; off in production |
| `INFO` | Normal events (fetch ok, alert fired, token issued) |
| `WARNING` | Recoverable: tenacity retry, single-fetcher failure |
| `ERROR` | Unrecoverable: migration failure, scheduler crash, auth burst |
| `CRITICAL` | Service cannot start |

### 4.3 Error Handling

`backend/core/errors.py`:

```python
class StockDashboardError(Exception): ...
class FetcherError(StockDashboardError): ...
class FetcherParseError(FetcherError): ...
class RepositoryError(StockDashboardError): ...
class AlertEvaluationError(StockDashboardError): ...
class AuthError(StockDashboardError): ...
```

Per-layer strategy:

- **Fetcher**: retry → on persistent failure raise `FetcherError`.
- **Scheduler job (thin orchestrator)**: catch `FetcherError`, log, push throttled message to ops Discord. Other fetchers continue.
- **Service**: catch only what it expects; let everything else propagate.
- **Route**: a FastAPI exception handler maps `StockDashboardError` to HTTP responses:
  - `RepositoryError` → 500
  - `FetcherError` → 502, message "資料來源暫時無法取得"
  - `AuthError` → 401 (already handled by the dependency)
  - Unknown exception → 500 + full traceback in logs
- Silent `except: pass` is forbidden.

Auth failure ops alert (in-memory):

- Per-IP sliding window: 5 failures within 5 minutes triggers a Discord ops notification.
- Per-IP cooldown of 1 hour. Resets on service restart. Not persisted.

### 4.4 Secrets & Configuration

Rules (also in root `CLAUDE.md`):

- Never commit tokens, webhooks, hostnames, `.env` contents, or SSH keys — including in code, comments, test fixtures, or commit messages.
- Local development: `backend/.env` (gitignored).
- VPS: `/opt/stock-dashboard/backend/.env`, written by deploy workflow from GitHub Secrets.
- GitHub Actions: `${{ secrets.X }}`.

Environment variables:

| Variable | Required | Purpose | Source |
|---|---|---|---|
| `DB_PATH` | no | SQLite file path | default `backend/stock_dashboard.db` |
| `DISCORD_STOCK_WEBHOOK_URL` | yes | Stock alert delivery | GitHub Secret |
| `DISCORD_OPS_WEBHOOK_URL` | yes (new) | Ops alerts (fetcher failure, auth burst) | GitHub Secret |
| `FINMIND_TOKEN` | yes | FinMind API | GitHub Secret |
| `LOG_LEVEL` | no | default `INFO` | — |
| `CORS_ORIGINS` | no | default `https://paul-learning.dev` | — |

`backend/core/settings.py` uses `pydantic-settings`:

```python
class Settings(BaseSettings):
    db_path: str = "stock_dashboard.db"
    discord_stock_webhook_url: SecretStr
    discord_ops_webhook_url: SecretStr
    finmind_token: SecretStr
    log_level: str = "INFO"
    cors_origins: list[str] = ["https://paul-learning.dev"]

    class Config:
        env_file = ".env"

settings = Settings()
```

Loaded once at startup. Direct `os.environ.get(...)` is forbidden outside `settings.py`.

---

## 5. Git Workflow

### 5.1 Commit Format

```
<type>(<scope>): <summary> (<step-id>)
```

- `type`: `feat` / `fix` / `refactor` / `test` / `docs` / `chore` / `perf`.
- `scope`: `stock-dashboard` for this project.
- `summary`: imperative, ≤ 72 chars.
- `step-id`: project prefix + number. Examples: `T3`, `Q-T2`, `MVP-T4`, `AUTH-T1`.

Examples:

```
feat(stock-dashboard): add Fetcher Protocol and Snapshot dataclass (REFACTOR-T1)
test(stock-dashboard): add failing tests for migration runner (DB-T1)
fix(stock-dashboard): handle 401 auth failure in apiFetch (AUTH-T7)
```

### 5.2 Step Decomposition

Each new feature or refactor begins with a task list. The list lives in the corresponding spec or in conversation. Prefix per project (`Q`, `MVP`, `AUTH`, `REFACTOR`, …):

- `T0`: spec / plan / docs only.
- `T1, T2, …`: each step has a single purpose, is independently revertable, and ships with tests.
- Optional `Phase N final polish`: cleanup, naming, dead-code removal.

### 5.3 Branching

- Day-to-day: push to master directly (current behaviour preserved).
- Large refactors or experimental work: feature branch, self-merge after diff review. GitHub Actions runs lint + tests on push.
- Never push a state where a migration is half-applied.

### 5.4 Forbidden in Git History

Tokens, webhook URLs, hostnames, `.env` contents, SSH keys — across code, comments, test fixtures, log samples, and commit messages.

---

## 6. Future Improvements (Backlog)

Not part of this spec, but surfaced during brainstorming:

- `openapi-typescript` to generate frontend types from `/openapi.json`.
- Frontend dark mode.
- Token management admin UI (currently CLI only — see "B2" in brainstorm).
- Structured JSON logs.
- Loki / Better Stack log aggregation.
- PR-based workflow with CI gate before merge.
- SQLite → Postgres migration when scale demands it.
- Multi-user accounts / password login. Tokens are not currently bound to a user record.

---

## 7. Migration Path — Five Phased Refactors

Each phase will be brainstormed and executed independently as its own spec → plan → implementation cycle. Listed in execution order:

### Phase 1 — `MIGR-`: DB Migration Runner

- Build `db/runner.py` (~50 LOC).
- Extract current schema as `db/migrations/0001_initial.sql`.
- Retire `init_db()`. Tests use the runner via fixture.
- No other layer changes. Independent and small.

### Phase 2 — `BE-`: Backend Layered Refactor

- Split `app.py` → `api/routes/*.py` + `api/schemas/*.py`.
- Split `db.py` → `repositories/*.py`.
- Split `alerts.py` → `services/alert_engine.py` + `services/alert_notifier.py`.
- Move `backfill.py` → `services/backfill.py`.
- Add `core/logging.py`, `core/settings.py`, `core/errors.py`.
- Existing tests remain green throughout (use re-exports as a temporary bridge).
- After completion, `app.py` (renamed `main.py`) is FastAPI assembly only.

### Phase 3 — `REG-`: Fetcher Protocol + Alert Registry

- Add `fetchers/base.py` with `Snapshot` and `Fetcher`.
- Migrate the nine existing fetchers one at a time (each its own `Tn`).
- Add `services/alert_registry.py`.
- Convert each existing indicator to `@register_indicator`.
- API validation and the frontend alert form read from the registry. Adding a new indicator becomes a one-file change.

### Phase 4 — `AUTH-`: Token Auth

- Migration adds `api_tokens` table.
- `repositories/api_tokens.py` + `services/token_service.py`.
- `api/dependencies.py` adds `verify_token`.
- `scripts/issue_token.py` CLI.
- Wire `DISCORD_OPS_WEBHOOK_URL` for auth-burst notifications.

### Phase 5 — `FE-`: Frontend Rewrite

- Scaffold Vite + React + TS in `frontend/`.
- Old `index.html` / `stock.html` remain alongside the new build until the React app reaches feature parity.
- Migrate page by page: dashboard first, then stock detail.
- Wire `<TokenGate>` and `apiFetch`.
- Update GitHub Actions to deploy `frontend/dist/`.
- Delete the old HTML files once parity is reached.

### Why This Order

- Migration runner first: every later phase that touches schema uses it.
- Backend layering before fetcher / alert registry: the registry depends on the service / repository split.
- Auth before frontend rewrite: when the new `apiFetch` lands, the token-injection contract already exists.
- Frontend last: backend contract is stable before React consumes it.

---

## 8. Maintenance of `CONVENTIONS.md`

The conventions doc is a living document.

- Whenever a new convention emerges in practice, update it.
- After each phase ships, audit the doc and reconcile any drift.
- When the doc and code disagree, decide which is wrong and fix that side. Do not tolerate prolonged inconsistency.
- AI agents working in the repo follow the doc. When they encounter a situation the doc doesn't cover, they raise it for discussion before improvising.
