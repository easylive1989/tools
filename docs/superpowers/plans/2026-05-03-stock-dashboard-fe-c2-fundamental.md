# Stock Dashboard FE-C2 Implementation Plan

**Goal:** Add 7 fundamental cards to the per-stock detail page (chip, valuation, revenue, income, balance, cashflow, dividend). All register `defaultPage: 'stock'`, `cols: 3`. Skip broker (backend disabled). Tests assert card registration + title only; charts verified in browser smoke.

**Architecture:** Per-card data hook + per-card component. Three financial statements share a `FinancialTable` shadcn Table wrapper.

**Tech Stack:** React 18, TanStack Query v5, recharts (already installed), shadcn Table (already installed).

Branch: `feat/fe-c2-fundamental` off `master`.

---

### Task 1: Branch + 5 data hooks

**Files:**
- Create: `src/hooks/useChip.ts`, `src/hooks/useValuation.ts`, `src/hooks/useRevenue.ts`, `src/hooks/useFinancial.ts`, `src/hooks/useDividend.ts`
- Create: `tests/useFinancial.test.tsx`

- [ ] **Step 1: Branch**

```bash
git checkout master && git pull && git checkout -b feat/fe-c2-fundamental
```

- [ ] **Step 2: Five hooks (same shape; only names differ)**

```typescript
// src/hooks/useChip.ts
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export interface ChipRow {
  date: string;
  foreign_net: number | null;
  trust_net: number | null;
  dealer_net: number | null;
  margin_balance: number | null;
  short_balance: number | null;
}
export interface ChipResponse {
  ticker: string;
  days: number;
  ok: boolean;
  rows: ChipRow[];
}

export function useChip(days = 20) {
  const { code = '' } = useParams<{ code: string }>();
  return useQuery<ChipResponse>({
    queryKey: ['stock-chip', code, days],
    queryFn: () => apiFetch<ChipResponse>(`/api/stocks/${encodeURIComponent(code)}/chip?days=${days}`),
    enabled: !!code,
  });
}
```

```typescript
// src/hooks/useValuation.ts
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export interface ValuationEntry {
  date: string;
  per: number | null;
  pbr: number | null;
  dividend_yield: number | null;
}
export interface ValuationLatest {
  per: number | null;
  pbr: number | null;
  dividend_yield: number | null;
  per_percentile: number | null;
  pbr_percentile: number | null;
  dividend_yield_percentile: number | null;
}
export interface ValuationResponse {
  ticker: string;
  years: number;
  ok: boolean;
  latest: ValuationLatest;
  entries: ValuationEntry[];
}

export function useValuation(years = 5) {
  const { code = '' } = useParams<{ code: string }>();
  return useQuery<ValuationResponse>({
    queryKey: ['stock-valuation', code, years],
    queryFn: () => apiFetch<ValuationResponse>(`/api/stocks/${encodeURIComponent(code)}/valuation?years=${years}`),
    enabled: !!code,
  });
}
```

```typescript
// src/hooks/useRevenue.ts
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export interface RevenueRow {
  month: string;          // YYYY-MM
  revenue: number | null;
  yoy_pct: number | null;
  ma12: number | null;
}
export interface RevenueResponse {
  ticker: string;
  months: number;
  ok: boolean;
  rows: RevenueRow[];
}

export function useRevenue(months = 36) {
  const { code = '' } = useParams<{ code: string }>();
  return useQuery<RevenueResponse>({
    queryKey: ['stock-revenue', code, months],
    queryFn: () => apiFetch<RevenueResponse>(`/api/stocks/${encodeURIComponent(code)}/revenue?months=${months}`),
    enabled: !!code,
  });
}
```

```typescript
// src/hooks/useFinancial.ts
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export type FinancialStatement = 'income' | 'balance' | 'cashflow';

export interface FinancialAnnualSummary {
  current_4q: { eps: number | null; revenue: number | null };
  previous_4q: { eps: number | null; revenue: number | null };
  eps_yoy_pct: number | null;
  revenue_yoy_pct: number | null;
}
export interface FinancialResponse {
  ticker: string;
  statement: FinancialStatement;
  quarters: number;
  ok: boolean;
  rows: Record<string, number | null | string>[]; // each row keyed by 'date' + metric fields
  annual_summary: FinancialAnnualSummary | null;
}

export function useFinancial(statement: FinancialStatement, quarters = 12) {
  const { code = '' } = useParams<{ code: string }>();
  return useQuery<FinancialResponse>({
    queryKey: ['stock-financial', code, statement, quarters],
    queryFn: () =>
      apiFetch<FinancialResponse>(
        `/api/stocks/${encodeURIComponent(code)}/financial?statement=${statement}&quarters=${quarters}`,
      ),
    enabled: !!code,
  });
}
```

```typescript
// src/hooks/useDividend.ts
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export interface DividendYear {
  year: number;
  cash_dividend: number | null;
  stock_dividend: number | null;
  payout_ratio: number | null;
}
export interface DividendResponse {
  ticker: string;
  years: number;
  ok: boolean;
  rows: DividendYear[];
}

export function useDividend(years = 10) {
  const { code = '' } = useParams<{ code: string }>();
  return useQuery<DividendResponse>({
    queryKey: ['stock-dividend', code, years],
    queryFn: () => apiFetch<DividendResponse>(`/api/stocks/${encodeURIComponent(code)}/dividend?years=${years}`),
    enabled: !!code,
  });
}
```

- [ ] **Step 3: useFinancial test (statement-scoped queryKey)**

```tsx
// tests/useFinancial.test.tsx
import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import { useFinancial } from '../src/hooks/useFinancial';

function wrap(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/stock/2330.TW']}>
        <Routes><Route path="/stock/:code" element={<>{children}</>} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('useFinancial', () => {
  it('income and balance statements use distinct cache keys', async () => {
    const calls: string[] = [];
    server.use(
      http.get('*/api/stocks/2330.TW/financial', ({ request }) => {
        const u = new URL(request.url);
        calls.push(u.searchParams.get('statement') || '');
        return HttpResponse.json({
          ticker: '2330.TW', statement: u.searchParams.get('statement'), quarters: 12,
          ok: true, rows: [], annual_summary: null,
        });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(
      () => ({ a: useFinancial('income'), b: useFinancial('balance') }),
      { wrapper: wrap(client) },
    );
    await waitFor(() => expect(calls).toContain('income'));
    await waitFor(() => expect(calls).toContain('balance'));
    expect(new Set(calls).size).toBe(2); // distinct fetches
  });
});
```

- [ ] **Step 4: Tests + build**

```bash
npm test && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useChip.ts src/hooks/useValuation.ts src/hooks/useRevenue.ts src/hooks/useFinancial.ts src/hooks/useDividend.ts tests/useFinancial.test.tsx
git commit -m "feat(stock-dashboard): 5 fundamental data hooks (FE-C2-T1)"
```

---

### Task 2: ChipCard

**Files:**
- Create: `src/cards/stock-chip.tsx`
- Create: `tests/stock-chip.test.tsx`
- Modify: `src/cards/index.ts`

- [ ] **Step 1: ChipCard**

```tsx
// src/cards/stock-chip.tsx
import { useMemo } from 'react';
import {
  ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend, CartesianGrid,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useChip } from '@/hooks/useChip';
import { registerCard } from './registry';

function ChipCard() {
  const { data } = useChip();
  const rows = useMemo(() => data?.rows ?? [], [data]);
  if (!data) return null;
  if (rows.length === 0) {
    return (
      <Card>
        <CardHeader><CardTitle>籌碼面</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">尚無資料</p>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader><CardTitle>籌碼面</CardTitle></CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" hide />
            <YAxis yAxisId="net" />
            <YAxis yAxisId="margin" orientation="right" />
            <Tooltip formatter={(v: any) => (typeof v === 'number' ? v.toLocaleString() : v)} />
            <Legend />
            <ReferenceLine y={0} yAxisId="net" stroke="#71717a" />
            <Line yAxisId="net" dataKey="foreign_net" name="外資" stroke="#3b82f6" dot={false} />
            <Line yAxisId="net" dataKey="trust_net"   name="投信" stroke="#16a34a" dot={false} />
            <Line yAxisId="net" dataKey="dealer_net"  name="自營" stroke="#f97316" dot={false} />
            <Line yAxisId="margin" dataKey="margin_balance" name="融資" stroke="#a855f7" dot={false} strokeDasharray="3 3" />
            <Line yAxisId="margin" dataKey="short_balance"  name="融券" stroke="#dc2626" dot={false} strokeDasharray="3 3" />
          </ComposedChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'stock-chip',
  label: '籌碼面',
  defaultPage: 'stock',
  component: ChipCard,
  cols: 3,
});
```

- [ ] **Step 2: Wire `cards/index.ts`**

```typescript
import './stock-chip';
```

- [ ] **Step 3: Test**

```tsx
// tests/stock-chip.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/stock-chip';
import { listCards } from '../src/cards/registry';

function renderCard() {
  const Card = listCards('stock').find((c) => c.id === 'stock-chip')!.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/stock/2330.TW']}>
        <Routes><Route path="/stock/:code" element={<Card />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ChipCard', () => {
  it('registers cols=3 on stock page', () => {
    expect(listCards('stock').find((c) => c.id === 'stock-chip')?.cols).toBe(3);
  });

  it('renders title; empty state when rows empty', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/chip', () =>
        HttpResponse.json({ ticker: '2330.TW', days: 20, ok: true, rows: [] }),
      ),
    );
    renderCard();
    await waitFor(() => expect(screen.getByText('籌碼面')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('尚無資料')).toBeInTheDocument());
  });
});
```

- [ ] **Step 4: Test + commit**

```bash
npm test
git add src/cards/stock-chip.tsx src/cards/index.ts tests/stock-chip.test.tsx
git commit -m "feat(stock-dashboard): ChipCard line chart (FE-C2-T2)"
```

---

### Task 3: ValuationCard

**Files:**
- Create: `src/cards/stock-valuation.tsx`
- Create: `tests/stock-valuation.test.tsx`
- Modify: `src/cards/index.ts`

- [ ] **Step 1: ValuationCard**

```tsx
// src/cards/stock-valuation.tsx
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useValuation } from '@/hooks/useValuation';
import { cn } from '@/lib/utils';
import { registerCard } from './registry';

function fmt(n: number | null, digits = 2): string {
  return n == null ? '—' : n.toFixed(digits);
}

function Stat({ label, value, percentile, suffix = '' }: { label: string; value: number | null; percentile: number | null; suffix?: string }) {
  const pBadge = percentile == null ? null : (
    <span className={cn(
      'text-xs px-2 py-0.5 rounded',
      percentile <= 30
        ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200'
        : percentile >= 70
          ? 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200'
          : 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200',
    )}>
      5y 百分位 {percentile.toFixed(0)}%
    </span>
  );
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-2xl font-bold">{fmt(value)}{suffix}</span>
      {pBadge}
    </div>
  );
}

function ValuationCard() {
  const { data } = useValuation();
  if (!data) return null;
  const { latest, entries } = data;
  if (!entries.length) {
    return (
      <Card>
        <CardHeader><CardTitle>估值快照</CardTitle></CardHeader>
        <CardContent><p className="text-sm text-muted-foreground">尚無資料</p></CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>估值快照</CardTitle>
        <p className="text-xs text-muted-foreground mt-1">PER / PBR / 殖利率 · 近 5 年</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-4">
          <Stat label="PER" value={latest.per} percentile={latest.per_percentile} />
          <Stat label="PBR" value={latest.pbr} percentile={latest.pbr_percentile} />
          <Stat label="殖利率" value={latest.dividend_yield} percentile={latest.dividend_yield_percentile} suffix="%" />
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={entries} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" hide />
            <YAxis />
            <Tooltip formatter={(v: any) => (typeof v === 'number' ? v.toFixed(2) : v)} />
            <Line dataKey="per" stroke="#3b82f6" dot={false} name="PER" />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'stock-valuation',
  label: '估值快照',
  defaultPage: 'stock',
  component: ValuationCard,
  cols: 3,
});
```

- [ ] **Step 2: Wire `cards/index.ts`**

- [ ] **Step 3: Test**

```tsx
// tests/stock-valuation.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/stock-valuation';
import { listCards } from '../src/cards/registry';

function renderCard() {
  const Card = listCards('stock').find((c) => c.id === 'stock-valuation')!.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/stock/2330.TW']}>
        <Routes><Route path="/stock/:code" element={<Card />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ValuationCard', () => {
  it('shows PER / PBR / yield latest values + 百分位 badges', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/valuation', () =>
        HttpResponse.json({
          ticker: '2330.TW', years: 5, ok: true,
          latest: {
            per: 22.5, pbr: 6.1, dividend_yield: 1.5,
            per_percentile: 80, pbr_percentile: 40, dividend_yield_percentile: 20,
          },
          entries: [
            { date: '2025-01-01', per: 20, pbr: 5, dividend_yield: 1.6 },
            { date: '2026-04-01', per: 22.5, pbr: 6.1, dividend_yield: 1.5 },
          ],
        }),
      ),
    );
    renderCard();
    await waitFor(() => expect(screen.getByText('估值快照')).toBeInTheDocument());
    expect(screen.getByText('22.50')).toBeInTheDocument();
    expect(screen.getByText('6.10')).toBeInTheDocument();
    expect(screen.getByText('1.50%')).toBeInTheDocument();
    expect(screen.getByText('5y 百分位 80%')).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Test + commit**

```bash
npm test
git add src/cards/stock-valuation.tsx src/cards/index.ts tests/stock-valuation.test.tsx
git commit -m "feat(stock-dashboard): ValuationCard PER/PBR/yield + percentile (FE-C2-T3)"
```

---

### Task 4: RevenueCard

**Files:**
- Create: `src/cards/stock-revenue.tsx`
- Create: `tests/stock-revenue.test.tsx`
- Modify: `src/cards/index.ts`

- [ ] **Step 1: RevenueCard**

```tsx
// src/cards/stock-revenue.tsx
import {
  Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useRevenue } from '@/hooks/useRevenue';
import { registerCard } from './registry';

function RevenueCard() {
  const { data } = useRevenue();
  if (!data) return null;
  if (!data.rows.length) {
    return (
      <Card>
        <CardHeader><CardTitle>月營收</CardTitle></CardHeader>
        <CardContent><p className="text-sm text-muted-foreground">尚無資料</p></CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>月營收</CardTitle>
        <p className="text-xs text-muted-foreground mt-1">近 36 個月</p>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={data.rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" hide />
            <YAxis yAxisId="rev" />
            <YAxis yAxisId="yoy" orientation="right" />
            <Tooltip formatter={(v: any) => (typeof v === 'number' ? v.toLocaleString() : v)} />
            <Legend />
            <Bar yAxisId="rev" dataKey="revenue" name="月營收" fill="#3b82f6" />
            <Line yAxisId="yoy" dataKey="yoy_pct" name="YoY %" stroke="#dc2626" dot={false} />
            <Line yAxisId="rev" dataKey="ma12" name="12MA" stroke="#a1a1aa" dot={false} strokeDasharray="3 3" />
          </ComposedChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'stock-revenue',
  label: '月營收',
  defaultPage: 'stock',
  component: RevenueCard,
  cols: 3,
});
```

- [ ] **Step 2: Wire `cards/index.ts`**

- [ ] **Step 3: Test (title + empty state)**

```tsx
// tests/stock-revenue.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/stock-revenue';
import { listCards } from '../src/cards/registry';

function renderCard() {
  const Card = listCards('stock').find((c) => c.id === 'stock-revenue')!.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/stock/2330.TW']}>
        <Routes><Route path="/stock/:code" element={<Card />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('RevenueCard', () => {
  it('renders title and empty placeholder when rows empty', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/revenue', () =>
        HttpResponse.json({ ticker: '2330.TW', months: 36, ok: true, rows: [] }),
      ),
    );
    renderCard();
    await waitFor(() => expect(screen.getByText('月營收')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('尚無資料')).toBeInTheDocument());
  });
});
```

- [ ] **Step 4: Commit**

```bash
git add src/cards/stock-revenue.tsx src/cards/index.ts tests/stock-revenue.test.tsx
git commit -m "feat(stock-dashboard): RevenueCard bar + YoY line (FE-C2-T4)"
```

---

### Task 5: IncomeStatementCard + shared FinancialTable + annual_summary header

**Files:**
- Create: `src/cards/stock-financial.tsx` (defines `FinancialTable` + 3 statement cards; only IncomeStatementCard registered in T5)
- Create: `tests/stock-financial.test.tsx`
- Modify: `src/cards/index.ts`

- [ ] **Step 1: FinancialTable + IncomeStatementCard**

```tsx
// src/cards/stock-financial.tsx
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  useFinancial, type FinancialResponse, type FinancialStatement,
} from '@/hooks/useFinancial';
import { cn } from '@/lib/utils';
import { registerCard } from './registry';

function fmtN(v: unknown, digits = 0): string {
  if (typeof v !== 'number') return '—';
  return v.toLocaleString(undefined, { maximumFractionDigits: digits });
}

interface RowSpec { key: string; label: string; digits?: number }

interface FinancialTableProps {
  data: FinancialResponse;
  rowSpecs: RowSpec[];
}

function FinancialTable({ data, rowSpecs }: FinancialTableProps) {
  const cols = data.rows.map((r) => String(r.date)).reverse(); // newest first
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>項目</TableHead>
          {cols.map((d) => (
            <TableHead key={d} className="text-right">{d}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rowSpecs.map((spec) => (
          <TableRow key={spec.key}>
            <TableCell className="font-medium">{spec.label}</TableCell>
            {[...data.rows].reverse().map((r) => (
              <TableCell key={String(r.date)} className="text-right">
                {fmtN(r[spec.key], spec.digits ?? 0)}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function AnnualSummaryStrip({ summary }: { summary: NonNullable<FinancialResponse['annual_summary']> }) {
  function pct(v: number | null) {
    if (v == null) return '—';
    const cls = v >= 0 ? 'text-green-600' : 'text-red-600';
    return <span className={cls}>{(v >= 0 ? '+' : '') + v.toFixed(2)}%</span>;
  }
  return (
    <div className="grid grid-cols-2 gap-4 pb-3 mb-3 border-b text-sm">
      <div>
        <div className="text-xs text-muted-foreground">近 4 季 EPS</div>
        <div className="text-lg font-bold">
          {fmtN(summary.current_4q.eps, 2)}{' '}
          {pct(summary.eps_yoy_pct)}
        </div>
      </div>
      <div>
        <div className="text-xs text-muted-foreground">近 4 季營收</div>
        <div className="text-lg font-bold">
          {fmtN(summary.current_4q.revenue)}{' '}
          {pct(summary.revenue_yoy_pct)}
        </div>
      </div>
    </div>
  );
}

interface StatementCardProps {
  title: string;
  hint: string;
  statement: FinancialStatement;
  rowSpecs: RowSpec[];
  showAnnualSummary?: boolean;
}

function StatementCard({ title, hint, statement, rowSpecs, showAnnualSummary }: StatementCardProps) {
  const { data } = useFinancial(statement);
  if (!data) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <p className="text-xs text-muted-foreground mt-1">{hint}</p>
      </CardHeader>
      <CardContent>
        {data.rows.length === 0 && (
          <p className="text-sm text-muted-foreground">尚無資料</p>
        )}
        {data.rows.length > 0 && (
          <>
            {showAnnualSummary && data.annual_summary && (
              <AnnualSummaryStrip summary={data.annual_summary} />
            )}
            <FinancialTable data={data} rowSpecs={rowSpecs} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

const INCOME_ROWS: RowSpec[] = [
  { key: 'revenue',          label: '營收' },
  { key: 'gross_profit',     label: '毛利' },
  { key: 'operating_income', label: '營業利益' },
  { key: 'net_income',       label: '稅後淨利' },
  { key: 'eps',              label: 'EPS', digits: 2 },
];

function IncomeStatementCard() {
  return (
    <StatementCard
      title="損益表"
      hint="近 12 季"
      statement="income"
      rowSpecs={INCOME_ROWS}
      showAnnualSummary
    />
  );
}

registerCard({
  id: 'stock-income',
  label: '損益表',
  defaultPage: 'stock',
  component: IncomeStatementCard,
  cols: 3,
});

// BalanceSheetCard + CashFlowCard exported in T6
export { StatementCard };
```

Wait — exporting `StatementCard` from a side-effect module is fine; T6 will import it from `'./stock-financial'`. But actually we want T6's cards to register too — easier path: keep all 3 register calls in this same file but split across T5 and T6 commits. The safer pattern is: T5 only adds Income; T6 amends to add Balance + CashFlow. Each task's diff stays focused.

- [ ] **Step 2: Wire `cards/index.ts`**

- [ ] **Step 3: Test**

```tsx
// tests/stock-financial.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/stock-financial';
import { listCards } from '../src/cards/registry';

function renderCard(id: string) {
  const Card = listCards('stock').find((c) => c.id === id)!.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/stock/2330.TW']}>
        <Routes><Route path="/stock/:code" element={<Card />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('IncomeStatementCard', () => {
  it('renders 損益表 with EPS / 營收 rows + annual_summary strip', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/financial', () =>
        HttpResponse.json({
          ticker: '2330.TW', statement: 'income', quarters: 12, ok: true,
          rows: [
            { date: '2026-Q1', revenue: 50000, gross_profit: 25000, operating_income: 18000, net_income: 16000, eps: 6.0 },
          ],
          annual_summary: {
            current_4q: { eps: 24.0, revenue: 200000 },
            previous_4q: { eps: 20.0, revenue: 180000 },
            eps_yoy_pct: 20.0,
            revenue_yoy_pct: 11.11,
          },
        }),
      ),
    );
    renderCard('stock-income');
    await waitFor(() => expect(screen.getByText('損益表')).toBeInTheDocument());
    expect(screen.getByText('EPS')).toBeInTheDocument();
    expect(screen.getByText('近 4 季 EPS')).toBeInTheDocument();
    expect(screen.getByText('+20.00%')).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Commit**

```bash
git add src/cards/stock-financial.tsx src/cards/index.ts tests/stock-financial.test.tsx
git commit -m "feat(stock-dashboard): IncomeStatementCard + shared FinancialTable (FE-C2-T5)"
```

---

### Task 6: BalanceSheet + CashFlow cards (reuse FinancialTable)

**Files:**
- Modify: `src/cards/stock-financial.tsx` (append BalanceSheet + CashFlow cards)
- Modify: `tests/stock-financial.test.tsx` (append tests)

- [ ] **Step 1: Append both cards**

```tsx
// append to src/cards/stock-financial.tsx
const BALANCE_ROWS: RowSpec[] = [
  { key: 'total_assets',      label: '總資產' },
  { key: 'total_liabilities', label: '總負債' },
  { key: 'total_equity',      label: '股東權益' },
  { key: 'cash_and_equiv',    label: '現金' },
];

function BalanceSheetCard() {
  return (
    <StatementCard
      title="資產負債表"
      hint="近 12 季"
      statement="balance"
      rowSpecs={BALANCE_ROWS}
    />
  );
}

registerCard({
  id: 'stock-balance',
  label: '資產負債表',
  defaultPage: 'stock',
  component: BalanceSheetCard,
  cols: 3,
});

const CASHFLOW_ROWS: RowSpec[] = [
  { key: 'operating_cash_flow', label: '營業 CF' },
  { key: 'investing_cash_flow', label: '投資 CF' },
  { key: 'financing_cash_flow', label: '融資 CF' },
  { key: 'free_cash_flow',      label: '自由現金流' },
];

function CashFlowCard() {
  return (
    <StatementCard
      title="現金流量表"
      hint="近 12 季"
      statement="cashflow"
      rowSpecs={CASHFLOW_ROWS}
    />
  );
}

registerCard({
  id: 'stock-cashflow',
  label: '現金流量表',
  defaultPage: 'stock',
  component: CashFlowCard,
  cols: 3,
});
```

- [ ] **Step 2: Append tests for both (smoke titles only)**

```tsx
describe('BalanceSheetCard', () => {
  it('renders 資產負債表 title + table rows', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/financial', () =>
        HttpResponse.json({
          ticker: '2330.TW', statement: 'balance', quarters: 12, ok: true,
          rows: [{ date: '2026-Q1', total_assets: 1, total_liabilities: 1, total_equity: 1, cash_and_equiv: 1 }],
          annual_summary: null,
        }),
      ),
    );
    renderCard('stock-balance');
    await waitFor(() => expect(screen.getByText('資產負債表')).toBeInTheDocument());
    expect(screen.getByText('總資產')).toBeInTheDocument();
  });
});

describe('CashFlowCard', () => {
  it('renders 現金流量表 title', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/financial', () =>
        HttpResponse.json({
          ticker: '2330.TW', statement: 'cashflow', quarters: 12, ok: true,
          rows: [{ date: '2026-Q1', operating_cash_flow: 1, investing_cash_flow: 1, financing_cash_flow: 1, free_cash_flow: 1 }],
          annual_summary: null,
        }),
      ),
    );
    renderCard('stock-cashflow');
    await waitFor(() => expect(screen.getByText('現金流量表')).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Test + commit**

```bash
npm test
git add src/cards/stock-financial.tsx tests/stock-financial.test.tsx
git commit -m "feat(stock-dashboard): BalanceSheet + CashFlow cards (FE-C2-T6)"
```

---

### Task 7: DividendCard

**Files:**
- Create: `src/cards/stock-dividend.tsx`
- Create: `tests/stock-dividend.test.tsx`
- Modify: `src/cards/index.ts`

- [ ] **Step 1: DividendCard**

```tsx
// src/cards/stock-dividend.tsx
import {
  Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useDividend } from '@/hooks/useDividend';
import { registerCard } from './registry';

function DividendCard() {
  const { data } = useDividend();
  if (!data) return null;
  if (!data.rows.length) {
    return (
      <Card>
        <CardHeader><CardTitle>股利歷史</CardTitle></CardHeader>
        <CardContent><p className="text-sm text-muted-foreground">尚無資料</p></CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>股利歷史</CardTitle>
        <p className="text-xs text-muted-foreground mt-1">近 10 年</p>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={data.rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="year" />
            <YAxis yAxisId="div" />
            <YAxis yAxisId="payout" orientation="right" unit="%" />
            <Tooltip formatter={(v: any) => (typeof v === 'number' ? v.toFixed(2) : v)} />
            <Legend />
            <Bar yAxisId="div" dataKey="cash_dividend"  name="現金股利" stackId="d" fill="#16a34a" />
            <Bar yAxisId="div" dataKey="stock_dividend" name="股票股利" stackId="d" fill="#3b82f6" />
            <Line yAxisId="payout" dataKey="payout_ratio" name="配發率" stroke="#dc2626" dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'stock-dividend',
  label: '股利歷史',
  defaultPage: 'stock',
  component: DividendCard,
  cols: 3,
});
```

- [ ] **Step 2: Wire `cards/index.ts`**

- [ ] **Step 3: Test (title + empty state)**

```tsx
// tests/stock-dividend.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/stock-dividend';
import { listCards } from '../src/cards/registry';

function renderCard() {
  const Card = listCards('stock').find((c) => c.id === 'stock-dividend')!.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/stock/2330.TW']}>
        <Routes><Route path="/stock/:code" element={<Card />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DividendCard', () => {
  it('renders 股利歷史 + empty placeholder', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/dividend', () =>
        HttpResponse.json({ ticker: '2330.TW', years: 10, ok: true, rows: [] }),
      ),
    );
    renderCard();
    await waitFor(() => expect(screen.getByText('股利歷史')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('尚無資料')).toBeInTheDocument());
  });
});
```

- [ ] **Step 4: Commit**

```bash
git add src/cards/stock-dividend.tsx src/cards/index.ts tests/stock-dividend.test.tsx
git commit -m "feat(stock-dashboard): DividendCard cash + stock + payout (FE-C2-T7)"
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
git merge --no-ff feat/fe-c2-fundamental -m "feat(stock-dashboard): per-stock fundamental cards (FE-C2)"
```

- [ ] **Step 3: Push, watch deploy, smoke test**

```bash
git push origin master
gh run list --workflow=deploy-stock-dashboard.yml --limit 1
gh run watch <id> --exit-status
curl -sI "https://paul-learning.dev/tools/stock/2330.TW?cb=$(date +%s)" | head -3
```

- [ ] **Step 4: Browser verification**

- 12 cards on per-stock page (5 from FE-C1 + 7 new)
- Chip / Revenue / Dividend charts render with real data
- Income statement shows annual_summary strip + 12 quarter columns
- Balance / Cashflow render rows from their respective metrics
- Switching ticker (browser back to dashboard, click another) → all queries refetch with new code

## Self-Review

**Spec coverage:** 5 hooks (T1) → ChipCard (T2) → ValuationCard (T3) → RevenueCard (T4) → IncomeStatement + shared FinancialTable (T5) → Balance + Cashflow (T6) → Dividend (T7) → deploy (T8). Broker explicitly out (backend disabled).

**Placeholder scan:** Code blocks complete in every step. Schema fields (`gross_profit`, `total_assets`, etc.) are best-guess based on backend builders; if a row key doesn't match, the table cell will render `—` and the only fix is to update the `RowSpec` keys — not a structural failure.

**Risks:**
- Backend financial row schema isn't fully grep-able from this plan's context. Verify in browser smoke; if labels render `—` everywhere for a metric, inspect the live `/api/stocks/{ticker}/financial?statement=...` response and update the matching RowSpec key.
- Bundle: ~10–20KB growth (new hook code + small components). Recharts already loaded.
