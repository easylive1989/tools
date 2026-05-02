# Stock Dashboard FE-A: React Frontend Scaffold Design Spec

**Date**: 2026-05-03
**Phase**: FE-A (Phase 5 sub-phase 1 of 4)
**Parent spec**: `docs/superpowers/specs/2026-05-02-stock-dashboard-conventions-design.md` §3, §7 Phase 5
**Predecessors**: MIGR / BE-A / BE-B / BE-C / REG- / AUTH- (full backend deployed with auth enforcement)
**Scope (FE-A only)**:
- Scaffold a Vite + React 18 + TypeScript project under `stock/dashboard/frontend/`
- Configure Tailwind CSS + shadcn/ui (button, card, input, dialog)
- Wire TanStack Query (server state) + Zustand (client state, including auth token) + React Router v6
- Build core infrastructure components: `<TokenGate>`, `apiFetch`, `QueryClient`, card registry pattern
- Ship 1 example card (TaiexCard) to validate the registry + UI pattern
- Update `.github/workflows/deploy-stock-dashboard.yml` to build Vite output and deploy `frontend/dist/` (with 404.html SPA-refresh trick)
- The old `frontend/index.html` (dashboard) is **overwritten** by Vite's new entry HTML during scaffold; its old content is preserved in git history. The old `frontend/stock.html` remains untouched in the working tree but is no longer deployed (FE-D deletes it in the cleanup pass)

**Future sub-phases** (separate brainstorm cycles each):
- **FE-B**: Migrate dashboard page — implement ~16 cards (10 macro indicators + Watchlist + Alerts + News + ...)
- **FE-C**: Migrate stock detail page — ~20 cards including K-line / MA / volume / RSI / MACD charts
- **FE-D**: Cleanup — delete old HTML files, finalize CONVENTIONS.md backlog

## Goals

1. Stand up a working Vite + React + TS frontend that loads at `https://paul-learning.dev/stock/` after deploy.
2. Establish the **card registry** pattern so future cards (FE-B / FE-C) are 1-file additions.
3. Establish the auth flow: `<TokenGate>` reads/writes `localStorage`, `apiFetch` injects `Authorization: Bearer <token>`, 401 clears token and re-renders gate.
4. Establish the test toolchain: Vitest + React Testing Library + msw, with sample tests proving each piece works.
5. Update the deploy workflow once so subsequent FE phases need no infrastructure changes.

## Non-Goals

- Do not migrate any existing card content. FE-A ships only the example `TaiexCard`. FE-B / FE-C migrate the rest.
- Do not delete `frontend/index.html` or `frontend/stock.html`. They remain in git history; deploy stops shipping them but FE-D handles removal.
- Do not implement card customization UI (visibility toggles, drag-to-reorder). The registry pattern enables this later, but the UI is out of FE-A scope.
- Do not change the backend at all.
- Do not change `travel/2026_austria_czechia/` or its deploy logic.
- Do not introduce a charting library yet. K-line / Chart.js choice happens in FE-C when the first chart card lands.

---

## 1. Target File Structure

```
stock/dashboard/frontend/
├── .gitignore                          ← node_modules, dist
├── package.json
├── package-lock.json
├── vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
├── tailwind.config.ts
├── postcss.config.js
├── components.json                     ← shadcn config
├── index.html                          ← Vite entry (replaces old dashboard HTML)
├── public/                             ← static assets (empty in FE-A)
├── src/
│   ├── main.tsx                        ← React + Router mount
│   ├── App.tsx                         ← TokenGate + QueryClient + RouterProvider
│   ├── index.css                       ← Tailwind base
│   ├── routes/
│   │   ├── index.tsx                   ← createBrowserRouter config
│   │   ├── DashboardPage.tsx
│   │   └── StockDetailPage.tsx
│   ├── components/
│   │   ├── TokenGate.tsx
│   │   └── ui/                         ← shadcn copies (button, card, input, dialog)
│   ├── cards/
│   │   ├── registry.ts                 ← CardSpec + registerCard + listCards + getCard
│   │   ├── index.ts                    ← imports all card files (auto-register on load)
│   │   └── TaiexCard.tsx
│   ├── lib/
│   │   ├── api-client.ts               ← apiFetch + ApiError
│   │   ├── query-client.ts             ← TanStack QueryClient instance
│   │   └── formatters.ts               ← (empty, FE-B fills)
│   ├── store/
│   │   └── auth-store.ts               ← Zustand auth state
│   └── types/                          ← (empty, FE-B fills)
└── tests/
    ├── setup.ts                        ← Vitest setup (jsdom, RTL matchers, msw server)
    ├── App.test.tsx                    ← sample integration test
    ├── auth-store.test.ts
    ├── TokenGate.test.tsx
    ├── api-client.test.ts
    ├── registry.test.ts
    └── ...

(old `frontend/index.html`, `frontend/stock.html` retained in git but no longer deployed; FE-D deletes them)
```

---

## 2. Tooling Choices

### `package.json`

```json
{
  "name": "stock-dashboard-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.27.0",
    "@tanstack/react-query": "^5.59.0",
    "zustand": "^5.0.0",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.5.4",
    "class-variance-authority": "^0.7.0",
    "lucide-react": "^0.453.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.3",
    "typescript": "^5.6.0",
    "vite": "^5.4.10",
    "tailwindcss": "^3.4.14",
    "postcss": "^8.4.47",
    "autoprefixer": "^10.4.20",
    "vitest": "^2.1.4",
    "@testing-library/react": "^16.0.1",
    "@testing-library/jest-dom": "^6.6.2",
    "jsdom": "^25.0.1",
    "msw": "^2.6.0"
  }
}
```

shadcn components are NOT a runtime dependency — they're copied into `src/components/ui/` via the shadcn CLI:

```bash
npx shadcn@latest init     # one-time
npx shadcn@latest add button card input dialog
```

### `vite.config.ts`

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  base: '/stock/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
});
```

- `base: '/stock/'` matches GitHub Pages URL prefix.
- Dev proxy lets the React dev server forward `/api/...` calls to a locally running backend, sidestepping CORS during development.

### `tsconfig.json`

Standard Vite React-TS template plus `paths`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "isolatedModules": true,
    "useDefineForClassFields": true,
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src", "tests"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

### `tailwind.config.ts`

shadcn-managed; the CLI generates this. Content paths must include `src/**/*.{ts,tsx}` and `index.html`. Dark mode: `class` (FE-A keeps light theme; future toggle is out of scope).

---

## 3. Card Registry Pattern

### `src/cards/registry.ts`

```typescript
import type { FC } from 'react';

export type CardPage = 'dashboard' | 'stock';

export interface CardSpec {
  id: string;
  label: string;
  defaultPage: CardPage;
  component: FC;
}

const _registry: CardSpec[] = [];

export function registerCard(spec: CardSpec): void {
  if (_registry.some(c => c.id === spec.id)) {
    throw new Error(`Card already registered: ${spec.id}`);
  }
  _registry.push(spec);
}

export function listCards(page: CardPage): CardSpec[] {
  return _registry.filter(c => c.defaultPage === page);
}

export function getCard(id: string): CardSpec | undefined {
  return _registry.find(c => c.id === id);
}
```

### `src/cards/index.ts`

```typescript
// Auto-registration: importing this triggers all card files' side effects.
import './TaiexCard';
// FE-B / FE-C will append more imports here.
```

### Per-card pattern (`src/cards/TaiexCard.tsx`)

```typescript
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { apiFetch } from '@/lib/api-client';
import { registerCard } from './registry';

interface DashboardData {
  taiex?: { value: number; timestamp: string; extra: { change_pct?: number } };
}

function TaiexCard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['indicators', 'taiex'],
    queryFn: () => apiFetch<DashboardData>('/api/dashboard'),
  });

  if (isLoading) return <Card><CardContent>載入中…</CardContent></Card>;
  if (error)     return <Card><CardContent>無法載入</CardContent></Card>;

  const t = data?.taiex;
  return (
    <Card>
      <CardHeader><CardTitle>加權指數</CardTitle></CardHeader>
      <CardContent>
        <div className="text-3xl font-bold">{t ? t.value.toLocaleString('zh-TW') : '—'}</div>
        <div className="text-sm text-muted-foreground">
          {t?.extra?.change_pct != null ? `${t.extra.change_pct.toFixed(2)}%` : ''}
        </div>
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'taiex',
  label: '加權指數',
  defaultPage: 'dashboard',
  component: TaiexCard,
});
```

Each card is fully self-contained: its own data fetching (TanStack Query), its own loading/error states, its own UI. Multiple cards can subscribe to the same query key (e.g. `/api/dashboard`); TanStack Query dedupes within `staleTime`, so requesting it from 10 cards still results in one HTTP call.

---

## 4. Auth Store + TokenGate + apiFetch

### `src/store/auth-store.ts`

```typescript
import { create } from 'zustand';

interface AuthStore {
  token: string | null;
  setToken: (t: string) => void;
  clearToken: () => void;
}

const STORAGE_KEY = 'sd_token';

export const useAuthStore = create<AuthStore>((set) => ({
  token: localStorage.getItem(STORAGE_KEY),
  setToken: (t) => {
    localStorage.setItem(STORAGE_KEY, t);
    set({ token: t });
  },
  clearToken: () => {
    localStorage.removeItem(STORAGE_KEY);
    set({ token: null });
  },
}));
```

The same `localStorage` key (`sd_token`) is used by the old HTML, so an existing logged-in user transitions to the React app without re-entering the token.

### `src/components/TokenGate.tsx`

```typescript
import { useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuthStore } from '@/store/auth-store';

export function TokenGate({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const setToken = useAuthStore((s) => s.setToken);
  const [input, setInput] = useState('');

  if (token) return <>{children}</>;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim()) setToken(input.trim());
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <form onSubmit={handleSubmit} className="w-full max-w-md p-6 space-y-4">
        <h1 className="text-2xl font-bold">Stock Dashboard</h1>
        <p className="text-sm text-muted-foreground">輸入 API token 以開始</p>
        <Input
          type="password"
          placeholder="sd_..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          autoFocus
        />
        <Button type="submit" className="w-full">登入</Button>
      </form>
    </div>
  );
}
```

### `src/lib/api-client.ts`

```typescript
import { useAuthStore } from '@/store/auth-store';

const API_BASE = import.meta.env.PROD
  ? 'https://api.paul-learning.dev'
  : '';

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(init.headers || {}),
  };
  if (token) (headers as Record<string, string>).Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (res.status === 401) {
    useAuthStore.getState().clearToken();
    throw new ApiError(401, 'Unauthorized');
  }
  if (!res.ok) {
    const detail = await res.text();
    throw new ApiError(res.status, detail || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}
```

`apiFetch` reads from the Zustand store imperatively (`useAuthStore.getState().token`) so it can be called from non-component code (TanStack Query queryFn). 401 clears the token, which flips Zustand state → React re-renders → `<TokenGate>` shows the login form.

### `src/lib/query-client.ts`

```typescript
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      retry: 2,
    },
  },
});
```

---

## 5. App Composition

### `src/main.tsx`

```typescript
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

// Trigger card auto-registration on app load
import './cards';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

### `src/App.tsx`

```typescript
import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';

import { TokenGate } from './components/TokenGate';
import { router } from './routes';
import { queryClient } from './lib/query-client';

export default function App() {
  return (
    <TokenGate>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </TokenGate>
  );
}
```

### `src/routes/index.tsx`

```typescript
import { createBrowserRouter } from 'react-router-dom';
import DashboardPage from './DashboardPage';
import StockDetailPage from './StockDetailPage';

export const router = createBrowserRouter([
  { path: '/', element: <DashboardPage /> },
  { path: '/stocks/:ticker', element: <StockDetailPage /> },
], { basename: '/stock' });
```

### `src/routes/DashboardPage.tsx`

```typescript
import { listCards } from '@/cards/registry';

export default function DashboardPage() {
  const cards = listCards('dashboard');
  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">市場總覽</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {cards.map(({ id, component: C }) => <C key={id} />)}
      </div>
    </div>
  );
}
```

### `src/routes/StockDetailPage.tsx` (FE-A placeholder)

```typescript
import { useParams } from 'react-router-dom';
import { listCards } from '@/cards/registry';

export default function StockDetailPage() {
  const { ticker } = useParams();
  const cards = listCards('stock');
  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">{ticker?.toUpperCase()}</h1>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {cards.map(({ id, component: C }) => <C key={id} />)}
      </div>
      {cards.length === 0 && <p className="text-muted-foreground">(stock detail cards land in FE-C)</p>}
    </div>
  );
}
```

---

## 6. Tests Setup

### `tests/setup.ts`

```typescript
import '@testing-library/jest-dom/vitest';
import { afterAll, afterEach, beforeAll } from 'vitest';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';

export const handlers = [
  http.get('https://api.paul-learning.dev/api/dashboard', () => {
    return HttpResponse.json({
      taiex: { value: 22000, timestamp: '2026-05-03T00:00:00', extra: { change_pct: 1.23 } },
    });
  }),
];

export const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

### `vite.config.ts` test config

Add a `test` block alongside `plugins`/`server`:

```typescript
test: {
  globals: true,
  environment: 'jsdom',
  setupFiles: ['./tests/setup.ts'],
}
```

(Will require `/// <reference types="vitest" />` at top of vite.config.ts.)

### Sample tests (FE-A ships these)

- `tests/auth-store.test.ts` (3 cases): initial null, setToken persists localStorage, clearToken removes
- `tests/TokenGate.test.tsx` (2 cases): no token → form visible; token → children visible
- `tests/api-client.test.ts` (2 cases): injects Authorization header; 401 calls clearToken
- `tests/registry.test.ts` (3 cases): register adds, listCards filters by page, duplicate id throws
- `tests/App.test.tsx` (1 case): full render with token shows DashboardPage

Total ~11 tests in FE-A.

---

## 7. Deploy Workflow Update

`.github/workflows/deploy-stock-dashboard.yml` — replace the "Assemble site" step:

```yaml
- name: Setup Node
  uses: actions/setup-node@v4
  with:
    node-version: '20'

- name: Build dashboard frontend
  working-directory: stock/dashboard/frontend
  run: npm ci && npm run build

- name: Build travel app
  working-directory: travel/2026_austria_czechia
  run: npm ci && npm run build

- name: Assemble site
  run: |
    mkdir -p _site/stock
    mkdir -p _site/travel/2026_austria_czechia
    cp -r stock/dashboard/frontend/dist/. _site/stock/
    cp stock/dashboard/frontend/dist/index.html _site/stock/404.html
    cp -r travel/2026_austria_czechia/dist/. _site/travel/2026_austria_czechia/
```

The 404.html copy is the SPA-refresh trick: GitHub Pages serves 404.html on any path it doesn't recognize, which loads the SPA, which lets React Router resolve client-side.

`paths:` filter in the workflow's `on:` block stays unchanged (already watches `stock/dashboard/frontend/**`).

---

## 8. Migration Order (13 tasks)

| # | Task |
|---|---|
| FE-A-T1 | `package.json` + `vite.config.ts` + `tsconfig.json` + `tsconfig.node.json` + `.gitignore`; run `npm install` |
| FE-A-T2 | Tailwind setup: `tailwind.config.ts` + `postcss.config.js` + `src/index.css` |
| FE-A-T3 | shadcn init + add `button`, `card`, `input`, `dialog` → copies into `src/components/ui/` |
| FE-A-T4 | React entry: `src/main.tsx` + `src/App.tsx` (placeholder) + minimal `index.html`; verify `npm run build` succeeds |
| FE-A-T5 | `src/store/auth-store.ts` + `tests/auth-store.test.ts` (3 tests) |
| FE-A-T6 | `src/components/TokenGate.tsx` + `tests/TokenGate.test.tsx` (2 tests) |
| FE-A-T7 | `src/lib/api-client.ts` + `src/lib/query-client.ts` + `tests/api-client.test.ts` (2 tests using msw) |
| FE-A-T8 | `src/cards/registry.ts` + `src/cards/index.ts` (empty re-import file) + `tests/registry.test.ts` (3 tests) |
| FE-A-T9 | `src/cards/TaiexCard.tsx` + register; update `cards/index.ts` to import it |
| FE-A-T10 | Routes: `src/routes/index.tsx` + `DashboardPage.tsx` + `StockDetailPage.tsx` placeholder |
| FE-A-T11 | Wire `App.tsx` (TokenGate + QueryClient + RouterProvider); local `npm run dev` smoke test; `tests/App.test.tsx` (1 test) |
| FE-A-T12 | Update `.github/workflows/deploy-stock-dashboard.yml` (Node setup + npm build + 404.html trick) |
| FE-A-T13 | Final verification: `npm run build` + `npm test` + structure check; merge + push triggers deploy; browser verifies React app loads |

T1-T4: scaffold runs locally; small verification commits.
T5-T11: each unit gets its own task + commit + tests where applicable.
T12: workflow change shipped without deploying yet (deploy happens on master push).
T13: read-only verification + merge + push + smoke test post-deploy.

---

## 9. Acceptance Criteria

- `frontend/package.json` lists all expected dependencies (react, react-dom, react-router-dom, @tanstack/react-query, zustand, tailwindcss, vite, vitest, RTL, msw)
- `frontend/src/` contains: `main.tsx`, `App.tsx`, `index.css`, plus subdirs `routes/`, `components/`, `cards/`, `lib/`, `store/`, `types/`
- `frontend/components/ui/` includes shadcn copies of at least `button.tsx`, `card.tsx`, `input.tsx`, `dialog.tsx`
- From a clean checkout, `cd frontend && npm ci && npm run build` succeeds with output `dist/`
- `cd frontend && npm test` passes (≈ 11 unit tests)
- `frontend/src/cards/TaiexCard.tsx` exists and registers itself; `listCards('dashboard')` returns at least 1 entry
- `.github/workflows/deploy-stock-dashboard.yml` has the Node + npm build steps and the 404.html trick
- Post-deploy, `https://paul-learning.dev/stock/`:
  - shows the TokenGate login form when no token in localStorage
  - shows DashboardPage with TaiexCard once a valid token is entered
  - refreshing `/stock/stocks/2330.TW` does not 404 (404.html trick works)
  - F12 console has no errors
- `https://paul-learning.dev/travel/2026_austria_czechia/...` still works (travel app build untouched)
- Old `frontend/stock.html` remains in the git tree (FE-D will delete) but is not present in the deployed `_site/`. `frontend/index.html` exists at HEAD but its content is now Vite's entry HTML (legacy dashboard content lives in git history)

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Vite `base: '/stock/'` vs Router `basename: '/stock'` mismatch | T11 runs `npm run preview` locally with the same base; verifies asset paths and routing |
| GitHub Pages SPA refresh 404 | 404.html trick (T12); T13 deliberately refreshes a sub-route post-deploy |
| Old `index.html` no longer deployed → FE-D will delete from git, but in interim someone might think it's gone | Old files retained in git tree (FE-A doesn't `git rm`); commit message documents "no longer deployed but kept for history" |
| CORS preflight on `Authorization` header for cross-origin (`paul-learning.dev` → `api.paul-learning.dev`) | Backend already allows the origin; FastAPI CORSMiddleware handles `OPTIONS` automatically; T13 manually verifies via browser DevTools network tab |
| Same `localStorage.sd_token` key shared between old HTML (still cached in browser) and new React app | Intentional: existing logged-in user transitions seamlessly. No clash. |
| TanStack Query dedupes by exact queryKey; if cards use slightly different keys, `/api/dashboard` may be fetched multiple times | TaiexCard uses `['indicators', 'taiex']` not `['dashboard']` (semantic); FE-B will need a convention. For FE-A's single card, dedupe is moot. |
| `npm ci` on every deploy adds ~30s | Acceptable; `actions/cache@v4` can be added later if it becomes painful |
| shadcn CLI is interactive | T3 uses `--defaults` flag + scripts the choices; if blocking, fall back to manual `components.json` + `npx shadcn add` per component |
| TypeScript strict catches things I didn't | Each task ends with `tsc -b` + `vitest`; failures fix in the same task |
| Tailwind purge misses paths and styles vanish in production | `tailwind.config.ts` content includes `./src/**/*.{ts,tsx}` and `./index.html` — covers everything |
| Card auto-registration via `import './TaiexCard'` runs at app start; if a card throws during register, app fails to load | Each card's `registerCard` is small and pure; T13 validates in browser |

## 11. Future-phase Notes (reference)

- **FE-B (Dashboard migration)**: ~16 cards (taiex, fx, fear_greed, ndc, margin_balance, short_balance, short_margin_ratio, total_foreign_net, total_trust_net, total_dealer_net, tw_volume, us_volume, watchlist, alerts CRUD, news, refresh button block). Charts will use Chart.js via `react-chartjs-2` (not yet introduced).
- **FE-C (Stock detail migration)**: ~20 cards (per, pbr, dividend_yield, foreign_net, trust_net, dealer_net, margin_balance (stock), short_balance (stock), revenue, q_eps, q_revenue, q_operating_income, q_net_income, q_operating_cf, y_cash_dividend, y_stock_dividend, K-line + technical, chip detail, brokers, ...). K-line custom chart is the main technical risk.
- **FE-D (Cleanup)**: delete `frontend/stock.html` (the legacy stock detail HTML, retained through FE-A/B/C as a non-deployed file in the working tree). The legacy dashboard `index.html` was already overwritten in FE-A by Vite's entry HTML — its old content lives in git history. Finalize CONVENTIONS.md backlog (mark FE-* future improvements).
- **Future feature: card customization UI**. The registry already exposes `listCards()`; building a settings drawer that filters this list per user preference is a follow-up phase, not part of FE-*.
