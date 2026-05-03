# Stock Dashboard FE-B3 Implementation Plan

**Goal:** Migrate the price alerts section to a React `AlertsCard` (cols=3) with a list view + a shadcn Dialog form for creating new alerts. Form-level condition options are driven by `/api/indicators/spec` so users only see conditions actually supported by the selected indicator. List rows expose toggle (PATCH) + delete (DELETE).

**Architecture:** AlertsCard registered as a dashboard card. List view is plain. Form lives in a Dialog with cascading selects: target_type → target / indicator_key → condition (filtered by spec) → window_n / threshold. Mutations invalidate `['alerts']`.

**Tech Stack:** React 18, TanStack Query v5 mutations, shadcn Select (new dep `@radix-ui/react-select`) + existing Dialog, Vitest + RTL + msw.

Branch: `feat/fe-b3-alerts` off `master`.

---

### Task 1: Branch + alert-labels + useAlerts + useIndicatorsSpec

**Files:**
- Create: `stock/dashboard/frontend/src/lib/alert-labels.ts`
- Create: `stock/dashboard/frontend/src/hooks/useAlerts.ts`
- Create: `stock/dashboard/frontend/src/hooks/useIndicatorsSpec.ts`
- Create: `stock/dashboard/frontend/tests/alert-labels.test.ts`
- Create: `stock/dashboard/frontend/tests/useAlerts.test.tsx`

- [ ] **Step 1: Branch**

```bash
git checkout master && git pull && git checkout -b feat/fe-b3-alerts
```

- [ ] **Step 2: alert-labels**

```typescript
// src/lib/alert-labels.ts
import type { AlertRecord } from '@/hooks/useAlerts';

export const INDICATOR_LABELS: Record<string, string> = {
  taiex: '加權指數',
  fx: '台幣兌美金',
  fear_greed: '恐懼貪婪指數',
  margin_balance: '融資餘額',
  short_balance: '融券餘額',
  short_margin_ratio: '券資比',
  total_foreign_net: '外資淨買超',
  total_trust_net: '投信淨買超',
  total_dealer_net: '自營商淨買超',
  ndc: '國發會景氣指標',
  tw_volume: '台股成交金額',
  us_volume: '美股 S&P500 成交量',
};

export const STOCK_INDICATOR_LABELS: Record<string, string> = {
  per: 'PER',
  pbr: 'PBR',
  dividend_yield: '殖利率',
  foreign_net: '外資淨買',
  trust_net: '投信淨買',
  dealer_net: '自營淨買',
  margin_balance: '融資餘額',
  short_balance: '融券餘額',
  revenue: '月營收',
  q_eps: '季 EPS',
  q_revenue: '季營收',
  q_operating_income: '季營業利益',
  q_net_income: '季稅後淨利',
  q_operating_cf: '季營業 CF',
  y_cash_dividend: '年現金股利',
  y_stock_dividend: '年股票股利',
};

export function alertTargetLabel(a: AlertRecord): string {
  if (a.target_type === 'indicator') {
    return INDICATOR_LABELS[a.target] ?? a.target;
  }
  if (a.target_type === 'stock_indicator') {
    const ik = a.indicator_key ?? '';
    return `${a.target} ${STOCK_INDICATOR_LABELS[ik] ?? ik}`.trim();
  }
  return a.target;
}

export function conditionLabel(a: AlertRecord): string {
  switch (a.condition) {
    case 'above': return '≥';
    case 'below': return '≤';
    case 'streak_above': return `連 ${a.window_n} 日 ≥`;
    case 'streak_below': return `連 ${a.window_n} 日 ≤`;
    case 'percentile_above': return '5y 百分位 ≥';
    case 'percentile_below': return '5y 百分位 ≤';
    case 'yoy_above': return 'YoY ≥';
    case 'yoy_below': return 'YoY ≤';
    default: return a.condition;
  }
}

export function thresholdPlaceholder(condition: string): string {
  if (condition.startsWith('percentile_')) return '百分位 0–100';
  if (condition.startsWith('yoy_')) return 'YoY %（可正可負）';
  return '門檻數值';
}
```

- [ ] **Step 3: useAlerts**

```typescript
// src/hooks/useAlerts.ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface AlertRecord {
  id: number;
  target_type: 'indicator' | 'stock' | 'stock_indicator';
  target: string;
  indicator_key: string | null;
  condition: string;
  threshold: number;
  window_n: number | null;
  enabled: number | boolean;
  created_at: string;
  triggered_at: string | null;
  triggered_value: number | null;
}

export interface CreateAlertPayload {
  target_type: AlertRecord['target_type'];
  target: string;
  indicator_key?: string;
  condition: string;
  threshold: number;
  window_n?: number;
}

export function useAlerts() {
  return useQuery<AlertRecord[]>({
    queryKey: ['alerts'],
    queryFn: () => apiFetch<AlertRecord[]>('/api/alerts'),
  });
}

export function useCreateAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateAlertPayload) =>
      apiFetch('/api/alerts', { method: 'POST', body: JSON.stringify(payload) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
}

export function useDeleteAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/api/alerts/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
}

export function useToggleAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      apiFetch(`/api/alerts/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
}
```

- [ ] **Step 4: useIndicatorsSpec**

```typescript
// src/hooks/useIndicatorsSpec.ts
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface IndicatorSpec {
  key: string;
  label: string;
  unit: string | null;
  supported_conditions: string[];
}

export interface IndicatorsSpec {
  indicator: IndicatorSpec[];
  stock_indicator: IndicatorSpec[];
}

export function useIndicatorsSpec() {
  return useQuery<IndicatorsSpec>({
    queryKey: ['indicators-spec'],
    queryFn: () => apiFetch<IndicatorsSpec>('/api/indicators/spec'),
    staleTime: Infinity,
  });
}
```

- [ ] **Step 5: alert-labels test**

```typescript
// tests/alert-labels.test.ts
import { describe, it, expect } from 'vitest';
import { alertTargetLabel, conditionLabel, thresholdPlaceholder } from '../src/lib/alert-labels';
import type { AlertRecord } from '../src/hooks/useAlerts';

const base: AlertRecord = {
  id: 1, target_type: 'indicator', target: 'taiex', indicator_key: null,
  condition: 'above', threshold: 0, window_n: null, enabled: 1,
  created_at: '2026-01-01T00:00:00Z', triggered_at: null, triggered_value: null,
};

describe('alertTargetLabel', () => {
  it('indicator key resolves to Chinese label', () => {
    expect(alertTargetLabel(base)).toBe('加權指數');
  });
  it('unknown indicator falls back to raw target', () => {
    expect(alertTargetLabel({ ...base, target: 'xxx' })).toBe('xxx');
  });
  it('stock_indicator joins ticker + indicator label', () => {
    expect(alertTargetLabel({
      ...base, target_type: 'stock_indicator', target: '2330.TW', indicator_key: 'per',
    })).toBe('2330.TW PER');
  });
  it('stock returns ticker as-is', () => {
    expect(alertTargetLabel({ ...base, target_type: 'stock', target: 'AAPL' })).toBe('AAPL');
  });
});

describe('conditionLabel', () => {
  it.each([
    ['above', '≥'],
    ['below', '≤'],
    ['percentile_above', '5y 百分位 ≥'],
    ['percentile_below', '5y 百分位 ≤'],
    ['yoy_above', 'YoY ≥'],
    ['yoy_below', 'YoY ≤'],
  ])('%s -> %s', (cond, expected) => {
    expect(conditionLabel({ ...base, condition: cond })).toBe(expected);
  });
  it('streak_above includes window_n', () => {
    expect(conditionLabel({ ...base, condition: 'streak_above', window_n: 7 })).toBe('連 7 日 ≥');
  });
});

describe('thresholdPlaceholder', () => {
  it('percentile family', () => {
    expect(thresholdPlaceholder('percentile_above')).toBe('百分位 0–100');
  });
  it('yoy family', () => {
    expect(thresholdPlaceholder('yoy_below')).toBe('YoY %（可正可負）');
  });
  it('default', () => {
    expect(thresholdPlaceholder('above')).toBe('門檻數值');
  });
});
```

- [ ] **Step 6: useAlerts test (covers CRUD + invalidation)**

```tsx
// tests/useAlerts.test.tsx
import { describe, it, expect } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import { useAlerts, useCreateAlert, useDeleteAlert, useToggleAlert } from '../src/hooks/useAlerts';

function wrap(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe('useAlerts CRUD', () => {
  it('createAlert invalidates ["alerts"] (refetches once)', async () => {
    let calls = 0;
    let list: any[] = [];
    server.use(
      http.get('*/api/alerts', () => { calls += 1; return HttpResponse.json(list); }),
      http.post('*/api/alerts', async ({ request }) => {
        const body = await request.json() as any;
        list = [{ id: 1, ...body, indicator_key: null, window_n: null, enabled: 1, created_at: '2026-05-03', triggered_at: null, triggered_value: null }];
        return HttpResponse.json({ id: 1 });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => ({ q: useAlerts(), m: useCreateAlert() }), { wrapper: wrap(client) });
    await waitFor(() => expect(result.current.q.data).toEqual([]));
    await act(async () => {
      await result.current.m.mutateAsync({
        target_type: 'indicator', target: 'taiex', condition: 'above', threshold: 18000,
      });
    });
    await waitFor(() => expect(calls).toBe(2));
    expect(result.current.q.data?.[0].target).toBe('taiex');
  });

  it('toggleAlert PATCHes with {enabled}', async () => {
    let patched: any = null;
    server.use(
      http.get('*/api/alerts', () => HttpResponse.json([])),
      http.patch('*/api/alerts/:id', async ({ request, params }) => {
        patched = { id: Number(params.id), body: await request.json() };
        return HttpResponse.json({ ok: true });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useToggleAlert(), { wrapper: wrap(client) });
    await act(async () => { await result.current.mutateAsync({ id: 7, enabled: false }); });
    expect(patched).toEqual({ id: 7, body: { enabled: false } });
  });

  it('deleteAlert DELETEs the id', async () => {
    let deletedId = 0;
    server.use(
      http.get('*/api/alerts', () => HttpResponse.json([])),
      http.delete('*/api/alerts/:id', ({ params }) => {
        deletedId = Number(params.id);
        return HttpResponse.json({ ok: true });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useDeleteAlert(), { wrapper: wrap(client) });
    await act(async () => { await result.current.mutateAsync(3); });
    expect(deletedId).toBe(3);
  });
});
```

- [ ] **Step 7: Run tests, expect green.**

- [ ] **Step 8: Commit**

```bash
git add src/lib/alert-labels.ts src/hooks/useAlerts.ts src/hooks/useIndicatorsSpec.ts tests/alert-labels.test.ts tests/useAlerts.test.tsx
git commit -m "feat(stock-dashboard): alert hooks + label helpers (FE-B3-T1)"
```

---

### Task 2: shadcn Select component

**Files:**
- Create: `stock/dashboard/frontend/src/components/ui/select.tsx`
- Modify: `stock/dashboard/frontend/package.json` (adds `@radix-ui/react-select`)

- [ ] **Step 1: Install dep**

```bash
cd stock/dashboard/frontend && npm install @radix-ui/react-select
```

- [ ] **Step 2: Create Select wrapper (shadcn default — minimal subset we use: Root, Trigger, Value, Content, Item)**

```tsx
// src/components/ui/select.tsx
import * as React from 'react';
import * as SelectPrimitive from '@radix-ui/react-select';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

const Select = SelectPrimitive.Root;
const SelectGroup = SelectPrimitive.Group;
const SelectValue = SelectPrimitive.Value;

const SelectTrigger = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      'flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
      className,
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDown className="h-4 w-4 opacity-50" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
));
SelectTrigger.displayName = SelectPrimitive.Trigger.displayName;

const SelectContent = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>
>(({ className, children, position = 'popper', ...props }, ref) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={ref}
      position={position}
      className={cn(
        'relative z-50 max-h-96 min-w-[8rem] overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md',
        position === 'popper' && 'translate-y-1',
        className,
      )}
      {...props}
    >
      <SelectPrimitive.Viewport className={cn('p-1', position === 'popper' && 'h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)]')}>
        {children}
      </SelectPrimitive.Viewport>
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
));
SelectContent.displayName = SelectPrimitive.Content.displayName;

const SelectItem = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    className={cn(
      'relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-2 pr-8 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
      className,
    )}
    {...props}
  >
    <span className="absolute right-2 flex h-3.5 w-3.5 items-center justify-center">
      <SelectPrimitive.ItemIndicator>
        <Check className="h-4 w-4" />
      </SelectPrimitive.ItemIndicator>
    </span>
    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
));
SelectItem.displayName = SelectPrimitive.Item.displayName;

export { Select, SelectGroup, SelectValue, SelectTrigger, SelectContent, SelectItem };
```

- [ ] **Step 3: Run build to verify import paths**

```bash
npm run build
```

- [ ] **Step 4: Commit**

```bash
git add src/components/ui/select.tsx package.json package-lock.json
git commit -m "feat(stock-dashboard): shadcn Select component (FE-B3-T2)"
```

---

### Task 3: AlertsCard list view (read-only)

**Files:**
- Create: `stock/dashboard/frontend/src/cards/AlertsCard.tsx`
- Create: `stock/dashboard/frontend/tests/AlertsCard.test.tsx`
- Modify: `stock/dashboard/frontend/src/cards/index.ts`

- [ ] **Step 1: Read-only AlertsCard**

```tsx
// src/cards/AlertsCard.tsx
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useAlerts } from '@/hooks/useAlerts';
import { alertTargetLabel, conditionLabel } from '@/lib/alert-labels';
import { cn } from '@/lib/utils';
import { registerCard } from './registry';

function fmtThreshold(v: number | null): string {
  if (v == null) return '';
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function StatusBadge({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={cn(
        'rounded px-2 py-0.5 text-xs font-medium',
        enabled
          ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200'
          : 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200',
      )}
    >
      {enabled ? '監控中' : '已停用'}
    </span>
  );
}

function AlertsCard() {
  const { data, isLoading, isError } = useAlerts();

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>價格警示</CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            觸發後自動停用，可手動重新啟用
          </p>
        </div>
        <Button size="sm" disabled>+ 新增警示</Button>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
        {isError && <p className="text-sm text-destructive">無法載入</p>}
        {data && data.length === 0 && (
          <p className="text-sm text-muted-foreground py-2 text-center">
            尚未設定任何警示
          </p>
        )}
        {data && data.length > 0 && (
          <ul className="divide-y">
            {data.map((a) => {
              const enabled = a.enabled === 1 || a.enabled === true;
              const meta = `建立於 ${a.created_at?.slice(0, 10) ?? ''}`
                + (a.triggered_at
                    ? ` · 已於 ${a.triggered_at.slice(0, 10)} 觸發 (${fmtThreshold(a.triggered_value)})`
                    : '');
              return (
                <li key={a.id} className="py-2 flex items-center justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm">
                      <strong>{alertTargetLabel(a)}</strong>{' '}
                      {conditionLabel(a)}{' '}
                      <strong>{fmtThreshold(a.threshold)}</strong>{' '}
                      <StatusBadge enabled={enabled} />
                    </div>
                    <div className="text-xs text-muted-foreground">{meta}</div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'alerts',
  label: '價格警示',
  defaultPage: 'dashboard',
  component: AlertsCard,
  cols: 3,
});
```

- [ ] **Step 2: Wire into cards/index.ts**

```typescript
// src/cards/index.ts (modify)
import './dashboard-cards';
import './NewsCard';
import './WatchlistCard';
import './AlertsCard';
```

- [ ] **Step 3: Tests for read view**

```tsx
// tests/AlertsCard.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/AlertsCard';
import { listCards } from '../src/cards/registry';

function renderCard() {
  const spec = listCards('dashboard').find((c) => c.id === 'alerts')!;
  const Card = spec.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Card />
    </QueryClientProvider>,
  );
}

describe('AlertsCard (read-only)', () => {
  it('registers as cols=3 dashboard card', () => {
    expect(listCards('dashboard').find((c) => c.id === 'alerts')?.cols).toBe(3);
  });

  it('shows empty placeholder when no alerts', async () => {
    server.use(http.get('*/api/alerts', () => HttpResponse.json([])));
    renderCard();
    await waitFor(() => expect(screen.getByText('尚未設定任何警示')).toBeInTheDocument());
  });

  it('renders an alert row with target label, condition, threshold, status', async () => {
    server.use(
      http.get('*/api/alerts', () =>
        HttpResponse.json([
          {
            id: 1, target_type: 'indicator', target: 'taiex', indicator_key: null,
            condition: 'above', threshold: 18000, window_n: null,
            enabled: 1, created_at: '2026-04-15T00:00:00Z',
            triggered_at: null, triggered_value: null,
          },
        ]),
      ),
    );
    renderCard();
    await waitFor(() => {
      expect(screen.getByText('加權指數')).toBeInTheDocument();
      expect(screen.getByText('≥')).toBeInTheDocument();
      expect(screen.getByText('18,000')).toBeInTheDocument();
      expect(screen.getByText('監控中')).toBeInTheDocument();
      expect(screen.getByText(/建立於 2026-04-15/)).toBeInTheDocument();
    });
  });

  it('shows triggered info when triggered_at present', async () => {
    server.use(
      http.get('*/api/alerts', () =>
        HttpResponse.json([
          {
            id: 2, target_type: 'indicator', target: 'taiex', indicator_key: null,
            condition: 'above', threshold: 18000, window_n: null,
            enabled: 0, created_at: '2026-04-15T00:00:00Z',
            triggered_at: '2026-05-01T08:00:00Z', triggered_value: 18234.56,
          },
        ]),
      ),
    );
    renderCard();
    await waitFor(() => {
      expect(screen.getByText('已停用')).toBeInTheDocument();
      expect(screen.getByText(/已於 2026-05-01 觸發 \(18,234.56\)/)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 4: Run all tests, expect green.**

- [ ] **Step 5: Commit**

```bash
git add src/cards/AlertsCard.tsx src/cards/index.ts tests/AlertsCard.test.tsx
git commit -m "feat(stock-dashboard): AlertsCard read-only list (FE-B3-T3)"
```

---

### Task 4: AlertCreateDialog scaffold (target_type + target + indicator_key cascade)

**Files:**
- Create: `stock/dashboard/frontend/src/components/AlertCreateDialog.tsx`
- Create: `stock/dashboard/frontend/tests/AlertCreateDialog.test.tsx`
- Modify: `stock/dashboard/frontend/src/cards/AlertsCard.tsx` (wire trigger)

- [ ] **Step 1: AlertCreateDialog scaffold (target cascade only)**

```tsx
// src/components/AlertCreateDialog.tsx
import { useState } from 'react';
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { useWatchlist } from '@/hooks/useWatchlist';
import { INDICATOR_LABELS, STOCK_INDICATOR_LABELS } from '@/lib/alert-labels';

type TargetType = 'indicator' | 'stock' | 'stock_indicator';

export function AlertCreateDialog({ trigger }: { trigger: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [targetType, setTargetType] = useState<TargetType>('indicator');
  const [target, setTarget] = useState('');
  const [indicatorKey, setIndicatorKey] = useState('per');
  const watchlist = useWatchlist();

  const indicatorOptions = Object.entries(INDICATOR_LABELS);
  const stockIndicatorOptions = Object.entries(STOCK_INDICATOR_LABELS);
  const tickerOptions = watchlist.data ?? [];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新增價格警示</DialogTitle>
          <DialogDescription>達到門檻時將推送 Discord 通知。</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <div>
            <label className="text-sm font-medium">類型</label>
            <Select value={targetType} onValueChange={(v) => {
              setTargetType(v as TargetType);
              setTarget('');
            }}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="indicator">指標</SelectItem>
                <SelectItem value="stock">股票 / ETF</SelectItem>
                <SelectItem value="stock_indicator">個股指標</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <label className="text-sm font-medium">目標</label>
            <Select value={target} onValueChange={setTarget}>
              <SelectTrigger><SelectValue placeholder="選擇" /></SelectTrigger>
              <SelectContent>
                {targetType === 'indicator' && indicatorOptions.map(([k, label]) => (
                  <SelectItem key={k} value={k}>{label}</SelectItem>
                ))}
                {targetType !== 'indicator' && tickerOptions.length === 0 && (
                  <SelectItem value="__none__" disabled>（請先在自選股新增）</SelectItem>
                )}
                {targetType !== 'indicator' && tickerOptions.map((s) => (
                  <SelectItem key={s.ticker} value={s.ticker}>
                    {s.name ? `${s.ticker} · ${s.name}` : s.ticker}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {targetType === 'stock_indicator' && (
            <div>
              <label className="text-sm font-medium">個股指標</label>
              <Select value={indicatorKey} onValueChange={setIndicatorKey}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {stockIndicatorOptions.map(([k, label]) => (
                    <SelectItem key={k} value={k}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => setOpen(false)}>取消</Button>
          <Button disabled>建立</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Wire dialog trigger into AlertsCard**

Replace the `<Button size="sm" disabled>+ 新增警示</Button>` placeholder with:

```tsx
import { AlertCreateDialog } from '@/components/AlertCreateDialog';

// in the header:
<AlertCreateDialog trigger={<Button size="sm">+ 新增警示</Button>} />
```

- [ ] **Step 3: Test: cascade behavior**

```tsx
// tests/AlertCreateDialog.test.tsx
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import { AlertCreateDialog } from '../src/components/AlertCreateDialog';
import { Button } from '../src/components/ui/button';

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AlertCreateDialog trigger={<Button>open</Button>} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  server.use(
    http.get('*/api/stocks', () =>
      HttpResponse.json([
        { ticker: '2330.TW', name: '台積電', price: null, change: null, change_pct: null, currency: null, timestamp: null },
      ]),
    ),
  );
});

describe('AlertCreateDialog cascade', () => {
  it('default target_type=indicator shows indicator options; indicator_key hidden', async () => {
    renderDialog();
    await userEvent.click(screen.getByRole('button', { name: 'open' }));
    expect(screen.getByText('類型')).toBeInTheDocument();
    expect(screen.queryByText('個股指標')).not.toBeInTheDocument();
  });

  it('switching to stock_indicator reveals indicator_key select; target options come from watchlist', async () => {
    renderDialog();
    await userEvent.click(screen.getByRole('button', { name: 'open' }));
    // Open the type select; click '個股指標'.
    const typeTrigger = screen.getAllByRole('combobox')[0];
    await userEvent.click(typeTrigger);
    await userEvent.click(screen.getByRole('option', { name: '個股指標' }));
    expect(await screen.findByText('個股指標', { selector: 'label' })).toBeInTheDocument();

    // Open target select - should show watchlist ticker
    const targetTrigger = screen.getAllByRole('combobox')[1];
    await userEvent.click(targetTrigger);
    expect(await screen.findByRole('option', { name: '2330.TW · 台積電' })).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Run, expect 2/2 pass.**

- [ ] **Step 5: Commit**

```bash
git add src/components/AlertCreateDialog.tsx src/cards/AlertsCard.tsx tests/AlertCreateDialog.test.tsx
git commit -m "feat(stock-dashboard): AlertCreateDialog target cascade (FE-B3-T4)"
```

---

### Task 5: AlertCreateDialog condition + window_n + threshold (spec-driven filter)

**Files:**
- Modify: `stock/dashboard/frontend/src/components/AlertCreateDialog.tsx`
- Modify: `stock/dashboard/frontend/tests/AlertCreateDialog.test.tsx`

- [ ] **Step 1: Add condition / window_n / threshold to dialog body**

In `AlertCreateDialog.tsx`, add state + fields. After the existing target/indicator_key block:

```tsx
// near top, more imports
import { Input } from '@/components/ui/input';
import { useIndicatorsSpec } from '@/hooks/useIndicatorsSpec';
import { thresholdPlaceholder } from '@/lib/alert-labels';

// add state
const [condition, setCondition] = useState('above');
const [windowN, setWindowN] = useState('5');
const [threshold, setThreshold] = useState('');

const spec = useIndicatorsSpec();

const ALL_CONDITIONS = [
  ['above', '大於等於'],
  ['below', '小於等於'],
  ['streak_above', '連 N 日突破'],
  ['streak_below', '連 N 日跌破'],
  ['percentile_above', '5y 百分位突破'],
  ['percentile_below', '5y 百分位跌破'],
  ['yoy_above', 'YoY 突破'],
  ['yoy_below', 'YoY 跌破'],
] as const;

function supportedConditions(): string[] {
  if (!spec.data) return ALL_CONDITIONS.map(([k]) => k);
  if (targetType === 'indicator' && target) {
    return spec.data.indicator.find((s) => s.key === target)?.supported_conditions
      ?? ALL_CONDITIONS.map(([k]) => k);
  }
  if (targetType === 'stock_indicator') {
    return spec.data.stock_indicator.find((s) => s.key === indicatorKey)?.supported_conditions
      ?? ALL_CONDITIONS.map(([k]) => k);
  }
  return ALL_CONDITIONS.map(([k]) => k);
}
const allowed = supportedConditions();
const conditionOptions = ALL_CONDITIONS.filter(([k]) => allowed.includes(k));
```

Add fields after the `targetType === 'stock_indicator'` block:

```tsx
<div>
  <label className="text-sm font-medium">條件</label>
  <Select value={condition} onValueChange={setCondition}>
    <SelectTrigger><SelectValue /></SelectTrigger>
    <SelectContent>
      {conditionOptions.map(([k, label]) => (
        <SelectItem key={k} value={k}>{label}</SelectItem>
      ))}
    </SelectContent>
  </Select>
</div>

{condition.startsWith('streak_') && (
  <div>
    <label className="text-sm font-medium">N 日</label>
    <Input
      type="number" min={2} max={30}
      value={windowN}
      onChange={(e) => setWindowN(e.target.value)}
    />
  </div>
)}

<div>
  <label className="text-sm font-medium">門檻</label>
  <Input
    type="number" step="any"
    placeholder={thresholdPlaceholder(condition)}
    value={threshold}
    onChange={(e) => setThreshold(e.target.value)}
  />
</div>
```

- [ ] **Step 2: Test: spec-driven condition filtering**

Append to `tests/AlertCreateDialog.test.tsx`:

```tsx
describe('AlertCreateDialog condition filter', () => {
  it('limits condition options to indicator supported_conditions from spec', async () => {
    server.use(
      http.get('*/api/stocks', () => HttpResponse.json([])),
      http.get('*/api/indicators/spec', () =>
        HttpResponse.json({
          indicator: [
            { key: 'taiex', label: '加權指數', unit: null, supported_conditions: ['above', 'below'] },
          ],
          stock_indicator: [],
        }),
      ),
    );
    renderDialog();
    await userEvent.click(screen.getByRole('button', { name: 'open' }));

    // pick indicator: taiex
    const targetTrigger = screen.getAllByRole('combobox')[1];
    await userEvent.click(targetTrigger);
    await userEvent.click(screen.getByRole('option', { name: '加權指數' }));

    // open condition select
    const condTrigger = screen.getAllByRole('combobox')[2];
    await userEvent.click(condTrigger);
    expect(screen.getByRole('option', { name: '大於等於' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '小於等於' })).toBeInTheDocument();
    // streak / percentile / yoy NOT shown
    expect(screen.queryByRole('option', { name: /連 N 日/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /百分位/ })).not.toBeInTheDocument();
  });

  it('streak condition reveals N 日 input', async () => {
    server.use(
      http.get('*/api/stocks', () => HttpResponse.json([])),
      http.get('*/api/indicators/spec', () =>
        HttpResponse.json({
          indicator: [
            { key: 'taiex', label: '加權指數', unit: null, supported_conditions: ['above', 'streak_above'] },
          ],
          stock_indicator: [],
        }),
      ),
    );
    renderDialog();
    await userEvent.click(screen.getByRole('button', { name: 'open' }));
    const targetTrigger = screen.getAllByRole('combobox')[1];
    await userEvent.click(targetTrigger);
    await userEvent.click(screen.getByRole('option', { name: '加權指數' }));
    const condTrigger = screen.getAllByRole('combobox')[2];
    await userEvent.click(condTrigger);
    await userEvent.click(screen.getByRole('option', { name: '連 N 日突破' }));
    expect(screen.getByLabelText('N 日')).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run tests, expect green.**

- [ ] **Step 4: Commit**

```bash
git add src/components/AlertCreateDialog.tsx tests/AlertCreateDialog.test.tsx
git commit -m "feat(stock-dashboard): AlertCreateDialog condition+window+threshold w/ spec filter (FE-B3-T5)"
```

---

### Task 6: AlertCreateDialog create mutation + error display

**Files:**
- Modify: `stock/dashboard/frontend/src/components/AlertCreateDialog.tsx`
- Modify: `stock/dashboard/frontend/src/lib/api-client.ts` (expose detail from 400)
- Modify: `stock/dashboard/frontend/tests/AlertCreateDialog.test.tsx`

- [ ] **Step 1: Wire useCreateAlert + Submit logic**

In `AlertCreateDialog.tsx`:

```tsx
import { useCreateAlert } from '@/hooks/useAlerts';
import { ApiError } from '@/lib/api-client';

const create = useCreateAlert();
const [error, setError] = useState<string | null>(null);

const submit = () => {
  setError(null);
  if (!target) { setError('請選擇目標'); return; }
  if (threshold === '') { setError('請輸入門檻數值'); return; }
  const payload: any = {
    target_type: targetType,
    target,
    condition,
    threshold: Number(threshold),
  };
  if (targetType === 'stock_indicator') payload.indicator_key = indicatorKey;
  if (condition.startsWith('streak_')) payload.window_n = Number(windowN);
  create.mutate(payload, {
    onSuccess: () => {
      setTarget('');
      setThreshold('');
      setOpen(false);
    },
    onError: (e: unknown) => {
      if (e instanceof ApiError) setError(e.message);
      else setError('建立失敗');
    },
  });
};
```

Replace dialog footer:

```tsx
{error && <p className="text-sm text-destructive">{error}</p>}
<div className="flex justify-end gap-2 pt-2">
  <Button variant="outline" onClick={() => setOpen(false)} disabled={create.isPending}>
    取消
  </Button>
  <Button onClick={submit} disabled={create.isPending}>
    {create.isPending ? '建立中…' : '建立'}
  </Button>
</div>
```

- [ ] **Step 2: Tests: success + 400**

```tsx
describe('AlertCreateDialog submit', () => {
  it('successful POST closes dialog and clears state', async () => {
    let posted: any = null;
    server.use(
      http.get('*/api/alerts', () => HttpResponse.json([])),
      http.get('*/api/stocks', () => HttpResponse.json([])),
      http.get('*/api/indicators/spec', () =>
        HttpResponse.json({
          indicator: [{ key: 'taiex', label: '加權指數', unit: null, supported_conditions: ['above'] }],
          stock_indicator: [],
        }),
      ),
      http.post('*/api/alerts', async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json({ id: 1 });
      }),
    );

    renderDialog();
    await userEvent.click(screen.getByRole('button', { name: 'open' }));
    const targetTrigger = screen.getAllByRole('combobox')[1];
    await userEvent.click(targetTrigger);
    await userEvent.click(screen.getByRole('option', { name: '加權指數' }));
    await userEvent.type(screen.getByPlaceholderText('門檻數值'), '18000');
    await userEvent.click(screen.getByRole('button', { name: '建立' }));

    await waitFor(() => expect(posted).toMatchObject({
      target_type: 'indicator', target: 'taiex', condition: 'above', threshold: 18000,
    }));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '建立' })).not.toBeInTheDocument(),
    );
  });

  it('backend 400 keeps dialog open and shows error', async () => {
    server.use(
      http.get('*/api/alerts', () => HttpResponse.json([])),
      http.get('*/api/stocks', () => HttpResponse.json([])),
      http.get('*/api/indicators/spec', () =>
        HttpResponse.json({
          indicator: [{ key: 'taiex', label: '加權指數', unit: null, supported_conditions: ['above'] }],
          stock_indicator: [],
        }),
      ),
      http.post('*/api/alerts', () => HttpResponse.text('Invalid threshold', { status: 400 })),
    );

    renderDialog();
    await userEvent.click(screen.getByRole('button', { name: 'open' }));
    const targetTrigger = screen.getAllByRole('combobox')[1];
    await userEvent.click(targetTrigger);
    await userEvent.click(screen.getByRole('option', { name: '加權指數' }));
    await userEvent.type(screen.getByPlaceholderText('門檻數值'), '18000');
    await userEvent.click(screen.getByRole('button', { name: '建立' }));

    await waitFor(() => expect(screen.getByText('Invalid threshold')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '建立' })).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run, expect green.**

- [ ] **Step 4: Commit**

```bash
git add src/components/AlertCreateDialog.tsx tests/AlertCreateDialog.test.tsx
git commit -m "feat(stock-dashboard): AlertCreateDialog submit + error (FE-B3-T6)"
```

---

### Task 7: List row toggle + delete buttons

**Files:**
- Modify: `stock/dashboard/frontend/src/cards/AlertsCard.tsx`
- Modify: `stock/dashboard/frontend/tests/AlertsCard.test.tsx`

- [ ] **Step 1: Add buttons to alert row**

```tsx
// inside AlertsCard.tsx — modify the <li> body:
import { X } from 'lucide-react';
import { useDeleteAlert, useToggleAlert } from '@/hooks/useAlerts';

// inside AlertsCard:
const toggle = useToggleAlert();
const del = useDeleteAlert();

// per row (replace previous <li>):
<li key={a.id} className="py-2 flex items-center justify-between gap-3">
  <div className="flex-1 min-w-0">
    <div className="text-sm">
      <strong>{alertTargetLabel(a)}</strong>{' '}
      {conditionLabel(a)}{' '}
      <strong>{fmtThreshold(a.threshold)}</strong>{' '}
      <StatusBadge enabled={enabled} />
    </div>
    <div className="text-xs text-muted-foreground">{meta}</div>
  </div>
  <div className="flex gap-2">
    <Button
      variant="outline"
      size="sm"
      onClick={() => toggle.mutate({ id: a.id, enabled: !enabled })}
      disabled={toggle.isPending && toggle.variables?.id === a.id}
    >
      {enabled ? '停用' : '啟用'}
    </Button>
    <Button
      variant="ghost"
      size="sm"
      onClick={() => del.mutate(a.id)}
      disabled={del.isPending && del.variables === a.id}
      aria-label={`刪除警示 ${a.id}`}
    >
      <X className="h-4 w-4" />
    </Button>
  </div>
</li>
```

- [ ] **Step 2: Tests for toggle + delete**

```tsx
// append to tests/AlertsCard.test.tsx
import userEvent from '@testing-library/user-event';

describe('AlertsCard interactions', () => {
  it('clicking 停用 calls PATCH with enabled:false', async () => {
    let patched: any = null;
    let alerts: any[] = [
      { id: 5, target_type: 'indicator', target: 'taiex', indicator_key: null,
        condition: 'above', threshold: 18000, window_n: null,
        enabled: 1, created_at: '2026-04-15', triggered_at: null, triggered_value: null },
    ];
    server.use(
      http.get('*/api/alerts', () => HttpResponse.json(alerts)),
      http.patch('*/api/alerts/:id', async ({ request, params }) => {
        patched = { id: Number(params.id), body: await request.json() };
        alerts = alerts.map((a) => a.id === Number(params.id) ? { ...a, enabled: 0 } : a);
        return HttpResponse.json({ ok: true });
      }),
    );

    renderCard();
    await waitFor(() => expect(screen.getByRole('button', { name: '停用' })).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: '停用' }));
    await waitFor(() => expect(patched).toEqual({ id: 5, body: { enabled: false } }));
  });

  it('clicking ✕ calls DELETE and removes row', async () => {
    let alerts: any[] = [
      { id: 9, target_type: 'indicator', target: 'taiex', indicator_key: null,
        condition: 'above', threshold: 18000, window_n: null,
        enabled: 1, created_at: '2026-04-15', triggered_at: null, triggered_value: null },
    ];
    let deletedId = 0;
    server.use(
      http.get('*/api/alerts', () => HttpResponse.json(alerts)),
      http.delete('*/api/alerts/:id', ({ params }) => {
        deletedId = Number(params.id);
        alerts = alerts.filter((a) => a.id !== deletedId);
        return HttpResponse.json({ ok: true });
      }),
    );

    renderCard();
    await waitFor(() => expect(screen.getByText('加權指數')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /刪除警示 9/ }));
    await waitFor(() => expect(deletedId).toBe(9));
    await waitFor(() => expect(screen.queryByText('加權指數')).not.toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Run, expect green.**

- [ ] **Step 4: Commit**

```bash
git add src/cards/AlertsCard.tsx tests/AlertsCard.test.tsx
git commit -m "feat(stock-dashboard): alert row toggle + delete buttons (FE-B3-T7)"
```

---

### Task 8: Final verify, merge, push, deploy check

- [ ] **Step 1: Full test + build**

```bash
npm test
npm run build
```

- [ ] **Step 2: Merge**

```bash
git checkout master
git merge --no-ff feat/fe-b3-alerts -m "feat(stock-dashboard): alerts CRUD card + dialog (FE-B3)"
```

- [ ] **Step 3: Push, watch deploy**

```bash
git push origin master
gh run list --workflow=deploy-stock-dashboard.yml --limit 1
gh run watch <id> --exit-status
```

- [ ] **Step 4: Smoke test**

```bash
curl -sI "https://paul-learning.dev/tools/stock/?cb=$(date +%s)" | head -3
```

- [ ] **Step 5: Browser verification (manual)**

- 15 cards (12 indicator + News + Watchlist + Alerts)
- AlertsCard shows existing alerts (or empty placeholder)
- Click `+ 新增警示` → dialog opens
- Pick `指標` + `加權指數` → only `≥` and `≤` show in condition (taiex doesn't support streak/percentile/yoy)
- Pick `個股指標` + a watchlist ticker + `PER` + `streak_above` → N 日 input appears
- Submit → row appears in list
- Toggle 停用/啟用 → status badge changes
- × → row disappears

## Self-Review

**Spec coverage:** label helpers + hooks (T1) → Select dep (T2) → list view (T3) → form cascade (T4) → spec-filtered conditions + window_n + threshold (T5) → submit + error (T6) → toggle/delete (T7) → deploy (T8).

**Placeholder scan:** No TBDs. Code blocks complete in every step. Backend already provides everything; no spec gaps.

**Type consistency:** `AlertRecord` defined in T1, used everywhere. `CreateAlertPayload` in T1, used in T6. `IndicatorsSpec` in T1, used in T5.

**Risks:**
- shadcn Select uses Radix Portal — combobox a11y role is `combobox` on trigger; tests use `getAllByRole('combobox')[index]` which works as long as we list all selects in render order. Brittle if order changes; if a test breaks, swap to `getByLabelText('類型')` etc.
- Bundle: Select adds ~10KB; expect ~340KB JS / 110KB gzip after FE-B3.
- T6's `ApiError.message` carries the response body text; backend returns plain text for these 400s (the existing code path in api-client.ts already does `await res.text()` — good).
