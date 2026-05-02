# Stock Dashboard FE-A: React Frontend Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a Vite + React 18 + TypeScript app at `stock/dashboard/frontend/` with Tailwind + shadcn/ui + TanStack Query + Zustand + React Router. Establish card registry pattern, TokenGate, apiFetch. Update deploy workflow to build Vite output and deploy `dist/` to GitHub Pages with 404.html SPA-refresh trick.

**Architecture:** All new files under `frontend/src/`. Each task is mostly additive (new files); workflow update is the only modification to existing infrastructure. Card auto-registration via side-effect imports in `cards/index.ts`. Zustand auth store imperatively read by `apiFetch` so non-component code can call API.

**Tech Stack:** React 18, TypeScript 5, Vite 5, Tailwind 3, shadcn/ui, TanStack Query 5, Zustand 5, React Router 6, Vitest, React Testing Library, msw.

**Spec reference:** `docs/superpowers/specs/2026-05-03-stock-dashboard-fe-a-design.md`.

---

## File Structure

**Created:**
- `stock/dashboard/frontend/package.json`
- `stock/dashboard/frontend/package-lock.json`
- `stock/dashboard/frontend/vite.config.ts`
- `stock/dashboard/frontend/tsconfig.json`
- `stock/dashboard/frontend/tsconfig.node.json`
- `stock/dashboard/frontend/tailwind.config.ts`
- `stock/dashboard/frontend/postcss.config.js`
- `stock/dashboard/frontend/components.json` (shadcn)
- `stock/dashboard/frontend/.gitignore`
- `stock/dashboard/frontend/src/main.tsx`
- `stock/dashboard/frontend/src/App.tsx`
- `stock/dashboard/frontend/src/index.css`
- `stock/dashboard/frontend/src/routes/index.tsx`
- `stock/dashboard/frontend/src/routes/DashboardPage.tsx`
- `stock/dashboard/frontend/src/routes/StockDetailPage.tsx`
- `stock/dashboard/frontend/src/components/TokenGate.tsx`
- `stock/dashboard/frontend/src/components/ui/{button,card,input,dialog}.tsx` (shadcn copies)
- `stock/dashboard/frontend/src/cards/registry.ts`
- `stock/dashboard/frontend/src/cards/index.ts`
- `stock/dashboard/frontend/src/cards/TaiexCard.tsx`
- `stock/dashboard/frontend/src/lib/api-client.ts`
- `stock/dashboard/frontend/src/lib/query-client.ts`
- `stock/dashboard/frontend/src/store/auth-store.ts`
- `stock/dashboard/frontend/tests/setup.ts`
- `stock/dashboard/frontend/tests/auth-store.test.ts`
- `stock/dashboard/frontend/tests/TokenGate.test.tsx`
- `stock/dashboard/frontend/tests/api-client.test.ts`
- `stock/dashboard/frontend/tests/registry.test.ts`
- `stock/dashboard/frontend/tests/App.test.tsx`

**Overwritten:**
- `stock/dashboard/frontend/index.html` — replaced by Vite's entry HTML; old dashboard content lives in git history

**Modified:**
- `.github/workflows/deploy-stock-dashboard.yml` — Node setup + npm build steps + 404.html copy

**Untouched:**
- `stock/dashboard/frontend/stock.html` — left in working tree, not deployed; FE-D will delete
- All backend code (`stock/dashboard/backend/`)
- `travel/2026_austria_czechia/` — its build step in the workflow stays
- All existing tests (backend pytest)

---

## Pre-flight: Branch + Baseline

Before T1: create a branch, verify backend tests still green from a clean state.

```bash
cd /Users/paulwu/Documents/Github/tools
git checkout -b feat/fe-a-react-scaffold
cd stock/dashboard && python3 -m pytest tests/ -q | tail -3
```

Expected: `5 failed, 149 passed` (backend baseline; FE-A doesn't touch it).

All commits use `(FE-A-Tn)` step IDs.

---

## Task Breakdown

### Task 1 (FE-A-T1): `package.json` + Vite/TS config + `.gitignore`

**Files:**
- Create: `stock/dashboard/frontend/package.json`
- Create: `stock/dashboard/frontend/vite.config.ts`
- Create: `stock/dashboard/frontend/tsconfig.json`
- Create: `stock/dashboard/frontend/tsconfig.node.json`
- Create: `stock/dashboard/frontend/.gitignore`

- [ ] **Step 1: Create `package.json`**

Write to `stock/dashboard/frontend/package.json`:

```json
{
  "name": "stock-dashboard-frontend",
  "private": true,
  "version": "0.0.0",
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
    "@testing-library/user-event": "^14.5.2",
    "jsdom": "^25.0.1",
    "msw": "^2.6.0"
  }
}
```

- [ ] **Step 2: Create `vite.config.ts`**

```typescript
/// <reference types="vitest" />
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
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
  },
});
```

- [ ] **Step 3: Create `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] },
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "tests"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 4: Create `tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 5: Create `.gitignore`**

```
node_modules
dist
.env.local
.env.*.local
*.log
```

- [ ] **Step 6: Install dependencies**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm install
```

Expected: creates `node_modules/` and `package-lock.json`. May take ~30s. No errors at the end.

- [ ] **Step 7: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/frontend/package.json stock/dashboard/frontend/package-lock.json stock/dashboard/frontend/vite.config.ts stock/dashboard/frontend/tsconfig.json stock/dashboard/frontend/tsconfig.node.json stock/dashboard/frontend/.gitignore && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): scaffold frontend npm project (FE-A-T1)

package.json: react/router/tanstack-query/zustand + vite/tsc/vitest/RTL/msw.
tsconfig with @/ path alias + strict mode. vite.config with /stock/ base
and dev /api proxy to local backend. .gitignore: node_modules + dist.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2 (FE-A-T2): Tailwind setup

**Files:**
- Create: `stock/dashboard/frontend/tailwind.config.ts`
- Create: `stock/dashboard/frontend/postcss.config.js`
- Create: `stock/dashboard/frontend/src/index.css`

- [ ] **Step 1: Create `tailwind.config.ts`**

```typescript
import type { Config } from 'tailwindcss';

export default {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: '2rem',
      screens: { '2xl': '1400px' },
    },
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
    },
  },
  plugins: [],
} satisfies Config;
```

- [ ] **Step 2: Create `postcss.config.js`**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 3: Create `src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 240 10% 3.9%;
    --card: 0 0% 100%;
    --card-foreground: 240 10% 3.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 240 10% 3.9%;
    --primary: 240 5.9% 10%;
    --primary-foreground: 0 0% 98%;
    --secondary: 240 4.8% 95.9%;
    --secondary-foreground: 240 5.9% 10%;
    --muted: 240 4.8% 95.9%;
    --muted-foreground: 240 3.8% 46.1%;
    --accent: 240 4.8% 95.9%;
    --accent-foreground: 240 5.9% 10%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 0 0% 98%;
    --border: 240 5.9% 90%;
    --input: 240 5.9% 90%;
    --ring: 240 5.9% 10%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 240 10% 3.9%;
    --foreground: 0 0% 98%;
    --card: 240 10% 3.9%;
    --card-foreground: 0 0% 98%;
    --popover: 240 10% 3.9%;
    --popover-foreground: 0 0% 98%;
    --primary: 0 0% 98%;
    --primary-foreground: 240 5.9% 10%;
    --secondary: 240 3.7% 15.9%;
    --secondary-foreground: 0 0% 98%;
    --muted: 240 3.7% 15.9%;
    --muted-foreground: 240 5% 64.9%;
    --accent: 240 3.7% 15.9%;
    --accent-foreground: 0 0% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 0 0% 98%;
    --border: 240 3.7% 15.9%;
    --input: 240 3.7% 15.9%;
    --ring: 240 4.9% 83.9%;
  }
}

@layer base {
  * { @apply border-border; }
  body { @apply bg-background text-foreground; }
}
```

This is the standard shadcn/ui zinc-neutral palette in HSL form.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/frontend/tailwind.config.ts stock/dashboard/frontend/postcss.config.js stock/dashboard/frontend/src/index.css && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): tailwind + shadcn-ready CSS variables (FE-A-T2)

Tailwind 3 with content paths + extended color tokens that consume CSS
variables. Light/dark theme variables in src/index.css using shadcn's
zinc-neutral palette.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3 (FE-A-T3): shadcn init + add components

**Files:**
- Create: `stock/dashboard/frontend/components.json`
- Create: `stock/dashboard/frontend/src/lib/utils.ts` (shadcn helper)
- Create: `stock/dashboard/frontend/src/components/ui/{button,card,input,dialog}.tsx`

- [ ] **Step 1: Create `components.json`**

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/index.css",
    "baseColor": "zinc",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

- [ ] **Step 2: Create `src/lib/utils.ts`**

```typescript
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 3: Add shadcn components**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npx shadcn@latest add button card input dialog --yes
```

If the CLI prompts unexpectedly (network, version selection), pass `--yes` and re-try. The command writes `src/components/ui/button.tsx`, `card.tsx`, `input.tsx`, `dialog.tsx`.

- [ ] **Step 4: Verify created files**

```bash
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/src/components/ui/
```

Expected: `button.tsx`, `card.tsx`, `dialog.tsx`, `input.tsx`.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/frontend/components.json stock/dashboard/frontend/src/lib/utils.ts stock/dashboard/frontend/src/components/ui/ && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): shadcn init + button/card/input/dialog (FE-A-T3)

components.json with @ alias config. lib/utils.ts cn() helper. Four
shadcn primitives copied into src/components/ui/. Future cards consume
these.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4 (FE-A-T4): Minimal Vite entry + verify build

**Files:**
- Create: `stock/dashboard/frontend/index.html` (overwrites old dashboard HTML)
- Create: `stock/dashboard/frontend/src/main.tsx`
- Create: `stock/dashboard/frontend/src/App.tsx` (placeholder)

- [ ] **Step 1: Create `index.html`**

Overwrite `stock/dashboard/frontend/index.html` with:

```html
<!doctype html>
<html lang="zh-TW">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/stock/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Stock Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 2: Create `src/main.tsx`**

```typescript
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 3: Create placeholder `src/App.tsx`**

```typescript
export default function App() {
  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold">Stock Dashboard (FE-A scaffold)</h1>
    </div>
  );
}
```

- [ ] **Step 4: Run build to verify toolchain**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm run build
```

Expected: `tsc -b` then `vite build` runs without errors. Output `dist/` contains `index.html`, `assets/`. No TypeScript errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/frontend/index.html stock/dashboard/frontend/src/main.tsx stock/dashboard/frontend/src/App.tsx && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): vite entry HTML + placeholder App (FE-A-T4)

index.html replaces legacy dashboard HTML (its content lives in git
history). main.tsx mounts React StrictMode. App.tsx is a one-line
placeholder; T11 wires TokenGate + Router + QueryClient.

`npm run build` verified locally — toolchain green.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5 (FE-A-T5): Auth store

**Files:**
- Create: `stock/dashboard/frontend/src/store/auth-store.ts`
- Create: `stock/dashboard/frontend/tests/setup.ts`
- Create: `stock/dashboard/frontend/tests/auth-store.test.ts`

- [ ] **Step 1: Create `tests/setup.ts`**

```typescript
import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
  localStorage.clear();
});
```

- [ ] **Step 2: Write failing test `tests/auth-store.test.ts`**

```typescript
import { describe, it, expect, beforeEach } from 'vitest';

describe('auth-store', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('initializes token from localStorage', async () => {
    localStorage.setItem('sd_token', 'sd_existing');
    // Re-import to re-evaluate the module's lazy initial state
    const mod = await import('../src/store/auth-store?t=' + Date.now());
    expect(mod.useAuthStore.getState().token).toBe('sd_existing');
  });

  it('setToken persists to localStorage', async () => {
    const { useAuthStore } = await import('../src/store/auth-store');
    useAuthStore.getState().setToken('sd_new');
    expect(localStorage.getItem('sd_token')).toBe('sd_new');
    expect(useAuthStore.getState().token).toBe('sd_new');
  });

  it('clearToken removes from localStorage', async () => {
    const { useAuthStore } = await import('../src/store/auth-store');
    useAuthStore.getState().setToken('sd_x');
    useAuthStore.getState().clearToken();
    expect(localStorage.getItem('sd_token')).toBeNull();
    expect(useAuthStore.getState().token).toBeNull();
  });
});
```

- [ ] **Step 3: Run failing**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm test
```

Expected: tests fail because `src/store/auth-store.ts` doesn't exist.

- [ ] **Step 4: Create `src/store/auth-store.ts`**

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

- [ ] **Step 5: Re-run tests**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm test
```

Expected: 3 tests pass.

Note: the first test reloads the module to re-trigger initial-state evaluation; module caching means this only works on the first dynamic import per test run. The query-string trick (`?t=`) bypasses Vite's module cache. If still flaky, the test can use `vi.resetModules()` instead.

- [ ] **Step 6: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/frontend/src/store/auth-store.ts stock/dashboard/frontend/tests/setup.ts stock/dashboard/frontend/tests/auth-store.test.ts && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): zustand auth store (FE-A-T5)

useAuthStore.token reads from localStorage at module load. setToken /
clearToken keep state and storage in sync. 3 tests cover init,
set, clear.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6 (FE-A-T6): TokenGate component

**Files:**
- Create: `stock/dashboard/frontend/src/components/TokenGate.tsx`
- Create: `stock/dashboard/frontend/tests/TokenGate.test.tsx`

- [ ] **Step 1: Write failing test**

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TokenGate } from '../src/components/TokenGate';
import { useAuthStore } from '../src/store/auth-store';

describe('TokenGate', () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({ token: null });
  });

  it('renders login form when no token', () => {
    render(<TokenGate><div>SECRET CONTENT</div></TokenGate>);
    expect(screen.getByText(/輸入 API token/)).toBeInTheDocument();
    expect(screen.queryByText('SECRET CONTENT')).not.toBeInTheDocument();
  });

  it('renders children when token is set', () => {
    useAuthStore.setState({ token: 'sd_abc' });
    render(<TokenGate><div>SECRET CONTENT</div></TokenGate>);
    expect(screen.getByText('SECRET CONTENT')).toBeInTheDocument();
    expect(screen.queryByText(/輸入 API token/)).not.toBeInTheDocument();
  });

  it('login form sets token in store', async () => {
    const user = userEvent.setup();
    render(<TokenGate><div>SECRET CONTENT</div></TokenGate>);
    await user.type(screen.getByPlaceholderText('sd_...'), 'sd_typed');
    await user.click(screen.getByRole('button', { name: '登入' }));
    expect(useAuthStore.getState().token).toBe('sd_typed');
  });
});
```

- [ ] **Step 2: Run failing**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm test -- TokenGate
```

Expected: fails — module not found.

- [ ] **Step 3: Create `src/components/TokenGate.tsx`**

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

- [ ] **Step 4: Run tests**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm test
```

Expected: 6 tests pass (3 auth-store + 3 TokenGate).

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/frontend/src/components/TokenGate.tsx stock/dashboard/frontend/tests/TokenGate.test.tsx && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): TokenGate login screen (FE-A-T6)

Pure React component (replaces legacy prompt() pattern). Reads token
from useAuthStore; if absent renders shadcn Input + Button form;
submit calls setToken which persists to localStorage. 3 tests cover
gate behavior + form submission.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7 (FE-A-T7): apiFetch + QueryClient

**Files:**
- Create: `stock/dashboard/frontend/src/lib/api-client.ts`
- Create: `stock/dashboard/frontend/src/lib/query-client.ts`
- Create: `stock/dashboard/frontend/tests/api-client.test.ts`
- Modify: `stock/dashboard/frontend/tests/setup.ts` (add msw server)

- [ ] **Step 1: Update `tests/setup.ts` to add msw server**

```typescript
import '@testing-library/jest-dom/vitest';
import { afterEach, afterAll, beforeAll } from 'vitest';
import { cleanup } from '@testing-library/react';
import { setupServer } from 'msw/node';

export const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
  localStorage.clear();
});
afterAll(() => server.close());
```

- [ ] **Step 2: Write failing test `tests/api-client.test.ts`**

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import { apiFetch, ApiError } from '../src/lib/api-client';
import { useAuthStore } from '../src/store/auth-store';

describe('apiFetch', () => {
  beforeEach(() => {
    useAuthStore.setState({ token: 'sd_test' });
  });

  it('injects Authorization Bearer header', async () => {
    let captured = '';
    server.use(
      http.get('*/api/dashboard', ({ request }) => {
        captured = request.headers.get('authorization') || '';
        return HttpResponse.json({ ok: true });
      })
    );

    await apiFetch('/api/dashboard');
    expect(captured).toBe('Bearer sd_test');
  });

  it('returns parsed JSON', async () => {
    server.use(
      http.get('*/api/dashboard', () => HttpResponse.json({ value: 42 }))
    );
    const data = await apiFetch<{ value: number }>('/api/dashboard');
    expect(data).toEqual({ value: 42 });
  });

  it('on 401 clears token and throws ApiError', async () => {
    server.use(
      http.get('*/api/dashboard', () => new HttpResponse(null, { status: 401 }))
    );

    await expect(apiFetch('/api/dashboard')).rejects.toBeInstanceOf(ApiError);
    expect(useAuthStore.getState().token).toBeNull();
  });

  it('on non-2xx (other) throws ApiError with status', async () => {
    server.use(
      http.get('*/api/dashboard', () => HttpResponse.text('boom', { status: 500 }))
    );

    await expect(apiFetch('/api/dashboard')).rejects.toMatchObject({
      status: 500,
    });
  });
});
```

- [ ] **Step 3: Run failing**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm test -- api-client
```

Expected: fails — module not found.

- [ ] **Step 4: Create `src/lib/api-client.ts`**

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
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

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

- [ ] **Step 5: Create `src/lib/query-client.ts`**

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

- [ ] **Step 6: Run tests**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm test
```

Expected: 10 tests pass (3 + 3 + 4).

- [ ] **Step 7: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/frontend/src/lib/api-client.ts stock/dashboard/frontend/src/lib/query-client.ts stock/dashboard/frontend/tests/api-client.test.ts stock/dashboard/frontend/tests/setup.ts && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): apiFetch + TanStack QueryClient (FE-A-T7)

apiFetch reads token from useAuthStore.getState() (imperative;
callable from non-component code). Production hits api.paul-learning.dev;
dev uses relative paths (Vite proxy). 401 auto-clears token. msw
server in tests/setup.ts. 4 new tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8 (FE-A-T8): Card registry

**Files:**
- Create: `stock/dashboard/frontend/src/cards/registry.ts`
- Create: `stock/dashboard/frontend/src/cards/index.ts`
- Create: `stock/dashboard/frontend/tests/registry.test.ts`

- [ ] **Step 1: Write failing test**

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { registerCard, listCards, getCard } from '../src/cards/registry';

const Stub = () => null;

describe('card registry', () => {
  beforeEach(async () => {
    // Reset registry between tests by re-importing
    const mod = await import('../src/cards/registry');
    // @ts-expect-error reach into private state via module re-import
    (mod as any)._reset?.();
  });

  it('register and list cards', () => {
    registerCard({ id: 'a', label: 'A', defaultPage: 'dashboard', component: Stub });
    registerCard({ id: 'b', label: 'B', defaultPage: 'stock', component: Stub });
    expect(listCards('dashboard').map(c => c.id)).toEqual(['a']);
    expect(listCards('stock').map(c => c.id)).toEqual(['b']);
  });

  it('getCard returns spec by id', () => {
    registerCard({ id: 'x', label: 'X', defaultPage: 'dashboard', component: Stub });
    expect(getCard('x')?.label).toBe('X');
    expect(getCard('nope')).toBeUndefined();
  });

  it('duplicate id throws', () => {
    registerCard({ id: 'dup', label: 'D', defaultPage: 'dashboard', component: Stub });
    expect(() =>
      registerCard({ id: 'dup', label: 'D2', defaultPage: 'dashboard', component: Stub })
    ).toThrow(/already registered/);
  });
});
```

Note: the `_reset` private function lets tests start with a clean registry. We'll add it.

- [ ] **Step 2: Run failing**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm test -- registry
```

Expected: fails — module not found.

- [ ] **Step 3: Create `src/cards/registry.ts`**

```typescript
import type { FC } from 'react';

export type CardPage = 'dashboard' | 'stock';

export interface CardSpec {
  id: string;
  label: string;
  defaultPage: CardPage;
  component: FC;
}

let _registry: CardSpec[] = [];

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

// Test-only: clear all registrations. Not exported via module index in production.
export function _reset(): void {
  _registry = [];
}
```

- [ ] **Step 4: Create empty `src/cards/index.ts`**

```typescript
// Auto-registration: importing this triggers all card files' side effects.
// FE-A-T9 adds the first import (TaiexCard); FE-B / FE-C append more.
```

- [ ] **Step 5: Run tests**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm test
```

Expected: 13 tests pass (10 + 3 registry).

- [ ] **Step 6: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/frontend/src/cards/registry.ts stock/dashboard/frontend/src/cards/index.ts stock/dashboard/frontend/tests/registry.test.ts && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): card registry skeleton (FE-A-T8)

CardSpec dataclass + registerCard / listCards / getCard. Page filter
('dashboard' | 'stock'). Duplicate id throws. _reset() exposed for
tests only. cards/index.ts is the auto-import file (empty in T8;
T9 adds TaiexCard).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9 (FE-A-T9): TaiexCard example

**Files:**
- Create: `stock/dashboard/frontend/src/cards/TaiexCard.tsx`
- Modify: `stock/dashboard/frontend/src/cards/index.ts`

- [ ] **Step 1: Create `src/cards/TaiexCard.tsx`**

```typescript
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { apiFetch } from '@/lib/api-client';
import { registerCard } from './registry';

interface DashboardData {
  taiex?: {
    value: number;
    timestamp: string;
    extra: { change_pct?: number };
  };
}

function TaiexCard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => apiFetch<DashboardData>('/api/dashboard'),
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader><CardTitle>加權指數</CardTitle></CardHeader>
        <CardContent>載入中…</CardContent>
      </Card>
    );
  }
  if (error) {
    return (
      <Card>
        <CardHeader><CardTitle>加權指數</CardTitle></CardHeader>
        <CardContent>無法載入</CardContent>
      </Card>
    );
  }

  const t = data?.taiex;
  const changePct = t?.extra?.change_pct;
  return (
    <Card>
      <CardHeader><CardTitle>加權指數</CardTitle></CardHeader>
      <CardContent>
        <div className="text-3xl font-bold">
          {t ? t.value.toLocaleString('zh-TW') : '—'}
        </div>
        {changePct != null && (
          <div className={`text-sm ${changePct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {changePct >= 0 ? '+' : ''}{changePct.toFixed(2)}%
          </div>
        )}
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

- [ ] **Step 2: Update `src/cards/index.ts` to import TaiexCard**

```typescript
// Auto-registration: importing this triggers all card files' side effects.
import './TaiexCard';
// FE-B / FE-C append more imports here.
```

- [ ] **Step 3: Verify TypeScript builds**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm run build
```

Expected: `tsc -b && vite build` succeeds. Output `dist/index.html` and `dist/assets/`.

- [ ] **Step 4: Run all tests**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm test
```

Expected: 13 tests pass (no new tests added in T9; TaiexCard's behavior is exercised in App.test.tsx in T11).

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/frontend/src/cards/TaiexCard.tsx stock/dashboard/frontend/src/cards/index.ts && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): TaiexCard example (FE-A-T9)

First card validating the registry pattern. useQuery on
['dashboard'] queryKey (multiple cards on dashboard will share this
query). Renders加權指數 value + change_pct from /api/dashboard.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10 (FE-A-T10): Routes

**Files:**
- Create: `stock/dashboard/frontend/src/routes/index.tsx`
- Create: `stock/dashboard/frontend/src/routes/DashboardPage.tsx`
- Create: `stock/dashboard/frontend/src/routes/StockDetailPage.tsx`

- [ ] **Step 1: Create `src/routes/DashboardPage.tsx`**

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

- [ ] **Step 2: Create `src/routes/StockDetailPage.tsx`**

```typescript
import { useParams } from 'react-router-dom';
import { listCards } from '@/cards/registry';

export default function StockDetailPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const cards = listCards('stock');
  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">{ticker?.toUpperCase()}</h1>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {cards.map(({ id, component: C }) => <C key={id} />)}
      </div>
      {cards.length === 0 && (
        <p className="text-muted-foreground">(stock detail cards land in FE-C)</p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create `src/routes/index.tsx`**

```typescript
import { createBrowserRouter } from 'react-router-dom';
import DashboardPage from './DashboardPage';
import StockDetailPage from './StockDetailPage';

export const router = createBrowserRouter([
  { path: '/', element: <DashboardPage /> },
  { path: '/stocks/:ticker', element: <StockDetailPage /> },
], { basename: '/stock' });
```

- [ ] **Step 4: Run build**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm run build
```

Expected: passes.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/frontend/src/routes/ && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): React Router config + page placeholders (FE-A-T10)

createBrowserRouter with basename '/stock'. DashboardPage renders
listCards('dashboard'). StockDetailPage reads :ticker param and
renders listCards('stock'). T11 wires this into App.tsx.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11 (FE-A-T11): App composition + integration test

**Files:**
- Modify: `stock/dashboard/frontend/src/main.tsx` (import cards/index for auto-register)
- Modify: `stock/dashboard/frontend/src/App.tsx` (TokenGate + QueryClient + RouterProvider)
- Create: `stock/dashboard/frontend/tests/App.test.tsx`

- [ ] **Step 1: Update `src/main.tsx`**

Replace existing content with:

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

- [ ] **Step 2: Replace `src/App.tsx`**

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

- [ ] **Step 3: Create `tests/App.test.tsx`**

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import App from '../src/App';
import { useAuthStore } from '../src/store/auth-store';

import '../src/cards';

describe('App', () => {
  beforeEach(() => {
    useAuthStore.setState({ token: null });
    localStorage.clear();
  });

  it('shows TokenGate when no token', () => {
    render(<App />);
    expect(screen.getByText(/輸入 API token/)).toBeInTheDocument();
  });

  it('renders DashboardPage with TaiexCard when token is set', async () => {
    useAuthStore.setState({ token: 'sd_test' });
    server.use(
      http.get('*/api/dashboard', () =>
        HttpResponse.json({
          taiex: { value: 22000, timestamp: '2026-05-03', extra: { change_pct: 1.5 } },
        })
      )
    );

    render(<App />);
    expect(screen.getByText('市場總覽')).toBeInTheDocument();
    expect(screen.getByText('加權指數')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/22,000/)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm test
```

Expected: 15 tests pass (13 + 2).

- [ ] **Step 5: Smoke test dev server**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm run dev
```

Open `http://localhost:5173/stock/` in a browser:
- TokenGate should show
- Enter `sd_if1PYHChdZjjUNoV90awJlhTnelKrLaImfQJlKSovws` (the token issued earlier in real terminal session)
- Should see "市場總覽" with "加權指數" card
- Open Network tab to confirm `/api/dashboard` request hits backend (Vite proxies to localhost:8000)

If backend not running locally, the card shows "無法載入" — that's still OK, proves the chain works.

Stop dev server with Ctrl+C.

- [ ] **Step 6: Run production build to verify**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm run build && npm run preview
```

Open the preview URL in browser. Verify the same flow works against the production build.

- [ ] **Step 7: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/frontend/src/main.tsx stock/dashboard/frontend/src/App.tsx stock/dashboard/frontend/tests/App.test.tsx && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): wire App with TokenGate + Router + QueryClient (FE-A-T11)

main.tsx imports './cards' to trigger auto-registration before render.
App.tsx composes TokenGate > QueryClientProvider > RouterProvider.
App.test.tsx integration test: token gate visible without token;
DashboardPage with TaiexCard rendered with token + msw fixture.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12 (FE-A-T12): Deploy workflow update

**Files:**
- Modify: `.github/workflows/deploy-stock-dashboard.yml`

- [ ] **Step 1: Read current workflow**

```bash
cat /Users/paulwu/Documents/Github/tools/.github/workflows/deploy-stock-dashboard.yml
```

The current "Assemble site" step copies HTML files directly. We replace it.

- [ ] **Step 2: Replace the assemble step**

Open `.github/workflows/deploy-stock-dashboard.yml`. Find the section:

```yaml
      - name: Build travel app
        working-directory: travel/2026_austria_czechia
        run: npm ci && npm run build

      - name: Assemble site
        run: |
          mkdir -p _site/stock
          mkdir -p _site/travel/2026_austria_czechia
          cp stock/dashboard/frontend/index.html _site/stock/index.html
          cp stock/dashboard/frontend/stock.html _site/stock/stock.html
          cp -r travel/2026_austria_czechia/dist/. _site/travel/2026_austria_czechia/
```

Replace with:

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

(`Setup Node` step moved before both build steps; the existing travel build already used Node so this is now consolidated.)

If the existing workflow has a `Setup Node` step elsewhere (before travel build), it can be removed since the new one above covers both.

- [ ] **Step 3: Verify YAML lint**

```bash
cat /Users/paulwu/Documents/Github/tools/.github/workflows/deploy-stock-dashboard.yml
```

Visually verify indentation is consistent (2 spaces, no tabs).

- [ ] **Step 4: Commit (do not push yet)**

```bash
cd /Users/paulwu/Documents/Github/tools && git add .github/workflows/deploy-stock-dashboard.yml && git commit -m "$(cat <<'EOF'
build(stock-dashboard): build Vite frontend + 404.html SPA trick (FE-A-T12)

deploy-stock-dashboard.yml now runs npm ci && npm run build in
stock/dashboard/frontend before assembling _site. Output dist/ is
copied to _site/stock/. dist/index.html is also copied to
_site/stock/404.html so GitHub Pages serves the SPA on unknown
sub-routes (/stock/stocks/:ticker etc.).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13 (FE-A-T13): Final verification + merge + post-deploy smoke

- [ ] **Step 1: Final structure check**

```bash
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/src/
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/src/cards/
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend/src/components/ui/
```

Expected:
- `frontend/`: package.json, vite.config.ts, tsconfig.json, tsconfig.node.json, tailwind.config.ts, postcss.config.js, components.json, .gitignore, index.html, package-lock.json, src/, tests/, node_modules/, dist/ (if recently built), stock.html (legacy, untouched)
- `src/`: main.tsx, App.tsx, index.css, routes/, components/, cards/, lib/, store/
- `src/cards/`: registry.ts, index.ts, TaiexCard.tsx
- `src/components/ui/`: button.tsx, card.tsx, dialog.tsx, input.tsx

- [ ] **Step 2: Final build + test**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/frontend && npm run build && npm test
```

Expected: build succeeds; 15 tests pass.

- [ ] **Step 3: Branch log inspection**

```bash
cd /Users/paulwu/Documents/Github/tools && git log --oneline master..HEAD
```

Expected (12 commits, T1 through T12 — T13 doesn't commit code, just verifies):

```
… FE-A-T12  build: vite frontend + 404.html
… FE-A-T11  feat: wire App
… FE-A-T10  feat: routes
… FE-A-T9   feat: TaiexCard
… FE-A-T8   feat: card registry
… FE-A-T7   feat: apiFetch + QueryClient
… FE-A-T6   feat: TokenGate
… FE-A-T5   feat: auth store
… FE-A-T4   feat: vite entry
… FE-A-T3   feat: shadcn
… FE-A-T2   feat: tailwind
… FE-A-T1   feat: scaffold npm project
```

- [ ] **Step 4: Merge to master**

```bash
cd /Users/paulwu/Documents/Github/tools && git checkout master && git merge --no-ff feat/fe-a-react-scaffold -m "$(cat <<'EOF'
Merge branch 'feat/fe-a-react-scaffold'

FE-A complete: 12 commits scaffolding Vite + React 18 + TS frontend
with Tailwind, shadcn/ui (button/card/input/dialog), TanStack Query,
Zustand auth store, React Router. Card registry pattern with
TaiexCard example. Deploy workflow runs npm build + 404.html SPA
trick. 15 frontend tests pass. Backend untouched.

Post-deploy: visit https://paul-learning.dev/stock/ — TokenGate,
paste sd_... token, see DashboardPage with TaiexCard.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Push and watch deploy**

```bash
git push origin master
```

Then:

```bash
gh run watch $(gh run list --workflow=deploy-stock-dashboard.yml --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
```

Expected: workflow `Deploy Stock Dashboard to GitHub Pages` succeeds (~1-2 minutes including npm ci).

- [ ] **Step 6: Browser verification**

Open in browser:
- `https://paul-learning.dev/stock/` — should show TokenGate
- Paste the existing token (`sd_if1PYHChdZjjUNoV90awJlhTnelKrLaImfQJlKSovws` from earlier in conversation)
- Should see "市場總覽" + TaiexCard with current TAIEX value
- Manually visit `https://paul-learning.dev/stock/stocks/2330.TW` — should not 404; should show stock detail page placeholder
- Refresh that URL — still works (404.html trick verified)
- F12 console — no errors
- Network tab — `/api/dashboard` request returns 200 with JSON

- [ ] **Step 7: Verify travel app still works**

Open `https://paul-learning.dev/travel/2026_austria_czechia/` — verify nothing broke (workflow change should not affect travel build).

- [ ] **Step 8: Done — no commit needed for verification**

---

## Spec Coverage Self-Check

| Spec section | Task |
|---|---|
| §1 Target file structure | T1 (configs), T2 (Tailwind), T3 (shadcn), T4 (Vite entry), T5-T11 (src/) |
| §2 Tooling (package.json + vite.config + tsconfig) | T1 |
| §3 Card registry pattern | T8 (registry.ts), T9 (TaiexCard sample) |
| §4 Auth store + TokenGate + apiFetch | T5 + T6 + T7 |
| §5 App composition | T11 |
| §6 Tests setup | T5 (setup.ts initial), T7 (msw added), T5-T11 (5 test files, 15 tests) |
| §7 Deploy workflow update | T12 |
| §8 Migration order (13 tasks) | T1-T13 (1:1) |
| §9 Acceptance criteria | T13 |
| §10 Risks (basename, 404.html, CORS) | Mitigated through design; T11 local preview + T13 post-deploy verification |
| §11 Future-phase notes | Reference only |

All sections covered.

---

## Execution Notes

- **Branch**: `feat/fe-a-react-scaffold` from master before T1; merge `--no-ff` after T13.
- **Total tasks**: 13. ~12 commits (T13 is verification only).
- **Estimated time**: T1-T4 mostly mechanical (~5 min each); T5-T11 each include real test writing (~15 min each); T12 quick; T13 verifies + waits for deploy. Total ~2-3 hours.
- **No new backend dependencies**.
- **Each task ends green**: `npm test` passes (or build for tasks without tests). Backend tests are not run during FE-A — they're not affected.
- **Deploy timing**: T13 step 5 pushes; deploy workflow runs ~1-2 minutes.

## Future-phase Notes (do not implement here)

- **FE-B (Dashboard migration)**: implement remaining ~15 dashboard cards. New deps may include `react-chartjs-2` for charts. Each card is a standalone file + register call.
- **FE-C (Stock detail migration)**: ~20 stock detail cards including K-line / MA / volume / RSI / MACD charts.
- **FE-D (Cleanup)**: delete `frontend/stock.html`, finalize CONVENTIONS.md backlog. Confirm legacy paths fully retired.
- **Future feature: card customization UI**: ships as a separate phase. Registry already exposes the data model; UI is a settings drawer that filters `listCards()` per user preference.
