# Stock Dashboard FE-C1 Implementation Plan

**Goal:** Build the React per-stock detail page with header + 5 technical chart cards (K-line, close+MA, volume, RSI, MACD), driven by a single `useStockHistory` query keyed on ticker + URL `range` search param. Adds `recharts` as the project chart library.

**Architecture:** `StockDetailPage` reads ticker from `useParams` and range from `useSearchParams` (default `3M`), renders a header with range selector buttons, then mounts the 5 chart cards from the registry (`defaultPage: 'stock'`). All cards share one query through `useStockHistory()`. A `flattenHistory()` helper zips the parallel arrays into row objects recharts can consume.

**Tech Stack:** React 18, TanStack Query v5, react-router v6 (`useParams`, `useSearchParams`), recharts (new dep), Vitest + RTL + msw.

Branch: `feat/fe-c1-stock-charts` off `master`.

---

### Task 1: Branch + recharts + useStockHistory + flattenHistory

**Files:**
- Create: `stock/dashboard/frontend/src/hooks/useStockHistory.ts`
- Create: `stock/dashboard/frontend/src/lib/flatten-history.ts`
- Create: `stock/dashboard/frontend/tests/flatten-history.test.ts`
- Create: `stock/dashboard/frontend/tests/useStockHistory.test.tsx`
- Modify: `stock/dashboard/frontend/package.json` (recharts)

- [ ] **Step 1: Branch + install**

```bash
git checkout master && git pull && git checkout -b feat/fe-c1-stock-charts
cd stock/dashboard/frontend && npm install recharts
```

- [ ] **Step 2: useStockHistory**

```typescript
// src/hooks/useStockHistory.ts
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useParams, useSearchParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export interface Candle {
  open: number; high: number; low: number; close: number; volume: number;
}

export interface StockHistoryResponse {
  ticker: string;
  name: string;
  currency: string;
  time_range: string;
  dates: string[];
  candles: Candle[];
  indicators: {
    ma5: (number | null)[];
    ma20: (number | null)[];
    ma60: (number | null)[];
    rsi14: (number | null)[];
    macd: (number | null)[];
    macd_signal: (number | null)[];
    macd_histogram: (number | null)[];
  };
}

export function useStockHistory(): UseQueryResult<StockHistoryResponse> {
  const { code = '' } = useParams<{ code: string }>();
  const [params] = useSearchParams();
  const range = params.get('range') || '3M';
  return useQuery<StockHistoryResponse>({
    queryKey: ['stock-history', code, range],
    queryFn: () =>
      apiFetch<StockHistoryResponse>(
        `/api/stocks/${encodeURIComponent(code)}/history?time_range=${range}`,
      ),
    enabled: !!code,
  });
}
```

- [ ] **Step 3: flattenHistory**

```typescript
// src/lib/flatten-history.ts
import type { StockHistoryResponse } from '@/hooks/useStockHistory';

export interface ChartRow {
  date: string;
  open: number; high: number; low: number; close: number; volume: number;
  ma5: number | null;
  ma20: number | null;
  ma60: number | null;
  rsi14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  change_pct: number | null;
}

export function flattenHistory(data: StockHistoryResponse): ChartRow[] {
  const { dates, candles, indicators } = data;
  const out: ChartRow[] = [];
  for (let i = 0; i < dates.length; i++) {
    const c = candles[i];
    const prev = i > 0 ? candles[i - 1].close : null;
    const change_pct = prev != null && prev !== 0
      ? ((c.close - prev) / prev) * 100
      : null;
    out.push({
      date: dates[i],
      open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume,
      ma5: indicators.ma5[i] ?? null,
      ma20: indicators.ma20[i] ?? null,
      ma60: indicators.ma60[i] ?? null,
      rsi14: indicators.rsi14[i] ?? null,
      macd: indicators.macd[i] ?? null,
      macd_signal: indicators.macd_signal[i] ?? null,
      macd_histogram: indicators.macd_histogram[i] ?? null,
      change_pct,
    });
  }
  return out;
}
```

- [ ] **Step 4: flatten-history test**

```typescript
// tests/flatten-history.test.ts
import { describe, it, expect } from 'vitest';
import { flattenHistory } from '../src/lib/flatten-history';

const sample = {
  ticker: 'X', name: 'X', currency: 'TWD', time_range: '3M',
  dates: ['2026-04-30', '2026-05-01', '2026-05-02'],
  candles: [
    { open: 100, high: 105, low: 98, close: 102, volume: 1000 },
    { open: 102, high: 108, low: 101, close: 107, volume: 1200 },
    { open: 107, high: 109, low: 100, close: 101, volume: 900 },
  ],
  indicators: {
    ma5: [null, null, 103],
    ma20: [null, null, null],
    ma60: [null, null, null],
    rsi14: [null, null, 55],
    macd: [null, 1, 2],
    macd_signal: [null, 0, 1],
    macd_histogram: [null, 1, 1],
  },
};

describe('flattenHistory', () => {
  it('zips arrays to rows of equal length', () => {
    const rows = flattenHistory(sample);
    expect(rows).toHaveLength(3);
    expect(rows[0].date).toBe('2026-04-30');
    expect(rows[2].close).toBe(101);
    expect(rows[2].ma5).toBe(103);
  });

  it('first row change_pct is null; later rows compute (close - prev_close) / prev * 100', () => {
    const rows = flattenHistory(sample);
    expect(rows[0].change_pct).toBeNull();
    // (107 - 102) / 102 * 100 = 4.901...
    expect(rows[1].change_pct).toBeCloseTo(4.9019, 3);
    // (101 - 107) / 107 * 100 = -5.607...
    expect(rows[2].change_pct).toBeCloseTo(-5.6074, 3);
  });
});
```

- [ ] **Step 5: useStockHistory test (memory router + path)**

```tsx
// tests/useStockHistory.test.tsx
import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import { useStockHistory } from '../src/hooks/useStockHistory';

function wrap(initialEntry: string, client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/stock/:code" element={<>{children}</>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('useStockHistory', () => {
  it('reads ticker from path and range from ?range=', async () => {
    let calledUrl = '';
    server.use(
      http.get('*/api/stocks/2330.TW/history', ({ request }) => {
        calledUrl = request.url;
        return HttpResponse.json({
          ticker: '2330.TW', name: '台積電', currency: 'TWD', time_range: '1Y',
          dates: [], candles: [],
          indicators: { ma5: [], ma20: [], ma60: [], rsi14: [], macd: [], macd_signal: [], macd_histogram: [] },
        });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useStockHistory(), {
      wrapper: wrap('/stock/2330.TW?range=1Y', client),
    });
    await waitFor(() => expect(result.current.data?.name).toBe('台積電'));
    expect(calledUrl).toContain('time_range=1Y');
  });

  it('defaults range to 3M when query string absent', async () => {
    let calledUrl = '';
    server.use(
      http.get('*/api/stocks/AAPL/history', ({ request }) => {
        calledUrl = request.url;
        return HttpResponse.json({
          ticker: 'AAPL', name: 'Apple', currency: 'USD', time_range: '3M',
          dates: [], candles: [],
          indicators: { ma5: [], ma20: [], ma60: [], rsi14: [], macd: [], macd_signal: [], macd_histogram: [] },
        });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(() => useStockHistory(), { wrapper: wrap('/stock/AAPL', client) });
    await waitFor(() => expect(calledUrl).toContain('time_range=3M'));
  });
});
```

- [ ] **Step 6: Run tests, expect green; build to verify recharts dep loads.**

```bash
npm test
npm run build
```

- [ ] **Step 7: Commit**

```bash
git add src/hooks/useStockHistory.ts src/lib/flatten-history.ts tests/flatten-history.test.ts tests/useStockHistory.test.tsx package.json package-lock.json
git commit -m "feat(stock-dashboard): useStockHistory + flatten + recharts dep (FE-C1-T1)"
```

---

### Task 2: StockDetailPage header + range buttons + card mount

**Files:**
- Modify: `stock/dashboard/frontend/src/pages/StockDetailPage.tsx`
- Create: `stock/dashboard/frontend/tests/StockDetailPage.test.tsx`

- [ ] **Step 1: Page implementation**

```tsx
// src/pages/StockDetailPage.tsx
import { useParams, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { listCards } from '@/cards/registry';
import { useStockHistory } from '@/hooks/useStockHistory';

const RANGES = ['1M', '3M', '6M', '1Y', '3Y'] as const;

export default function StockDetailPage() {
  const { code = '' } = useParams<{ code: string }>();
  const [params, setParams] = useSearchParams();
  const range = params.get('range') || '3M';
  const { data, isLoading, isError } = useStockHistory();
  const cards = listCards('stock');

  const lastDate = data?.dates[data.dates.length - 1] ?? '';
  const titleSub = lastDate
    ? `最後資料日 ${lastDate}${data?.currency ? ' · ' + data.currency : ''}`
    : '';

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">
            {code}{data?.name && ` · ${data.name}`}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">{titleSub}</p>
        </div>
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <Button
              key={r}
              size="sm"
              variant={r === range ? 'default' : 'outline'}
              onClick={() => setParams({ range: r })}
            >
              {r}
            </Button>
          ))}
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
      {isError && <p className="text-sm text-destructive">無法載入歷史資料</p>}
      {data && (
        <div className="space-y-4">
          {cards.map(({ id, component: Card }) => <Card key={id} />)}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: StockDetailPage test**

```tsx
// tests/StockDetailPage.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import StockDetailPage from '../src/pages/StockDetailPage';

function emptyHistory(ticker: string, range: string) {
  return {
    ticker, name: '台積電', currency: 'TWD', time_range: range,
    dates: ['2026-05-02'], candles: [{ open: 1000, high: 1010, low: 990, close: 1005, volume: 10000 }],
    indicators: { ma5: [null], ma20: [null], ma60: [null], rsi14: [null], macd: [null], macd_signal: [null], macd_histogram: [null] },
  };
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/stock/:code" element={<StockDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('StockDetailPage', () => {
  it('renders header with ticker name + last data date + currency', async () => {
    server.use(http.get('*/api/stocks/2330.TW/history', () => HttpResponse.json(emptyHistory('2330.TW', '3M'))));
    renderAt('/stock/2330.TW');
    await waitFor(() => expect(screen.getByRole('heading', { name: /2330.TW · 台積電/ })).toBeInTheDocument());
    expect(screen.getByText(/最後資料日 2026-05-02 · TWD/)).toBeInTheDocument();
  });

  it('range buttons reflect active state and clicking changes ?range=', async () => {
    let calledRange = '';
    server.use(http.get('*/api/stocks/2330.TW/history', ({ request }) => {
      const u = new URL(request.url);
      calledRange = u.searchParams.get('time_range') || '';
      return HttpResponse.json(emptyHistory('2330.TW', calledRange));
    }));
    renderAt('/stock/2330.TW?range=3M');
    await waitFor(() => expect(calledRange).toBe('3M'));
    await userEvent.click(screen.getByRole('button', { name: '1Y' }));
    await waitFor(() => expect(calledRange).toBe('1Y'));
  });
});
```

- [ ] **Step 3: Run, expect 2/2 pass.**

- [ ] **Step 4: Commit**

```bash
git add src/pages/StockDetailPage.tsx tests/StockDetailPage.test.tsx
git commit -m "feat(stock-dashboard): StockDetailPage header + range tabs (FE-C1-T2)"
```

---

### Task 3: KLineCard

**Files:**
- Create: `stock/dashboard/frontend/src/cards/stock-charts.tsx` (start with KLine; later tasks append)
- Create: `stock/dashboard/frontend/tests/stock-charts.test.tsx`
- Modify: `stock/dashboard/frontend/src/cards/index.ts`

- [ ] **Step 1: Wrapper + KLineCard**

```tsx
// src/cards/stock-charts.tsx
import { useMemo } from 'react';
import {
  ComposedChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Customized,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useStockHistory } from '@/hooks/useStockHistory';
import { flattenHistory, type ChartRow } from '@/lib/flatten-history';
import { registerCard } from './registry';

const CHART_HEIGHT = 320;

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

interface CandleProps {
  rows: ChartRow[];
  xAxisMap: Record<string, { scale: (v: any) => number; bandSize: number }>;
  yAxisMap: Record<string, { scale: (v: number) => number }>;
}

// Custom candlestick layer — receives axis scales from recharts via Customized
function CandleLayer({ rows, xAxisMap, yAxisMap }: CandleProps) {
  const xKey = Object.keys(xAxisMap)[0];
  const yKey = Object.keys(yAxisMap)[0];
  if (!xKey || !yKey) return null;
  const x = xAxisMap[xKey];
  const y = yAxisMap[yKey];
  const width = Math.max(2, x.bandSize * 0.6);
  return (
    <g data-testid="candles">
      {rows.map((r) => {
        const cx = x.scale(r.date) + x.bandSize / 2;
        const yHigh = y.scale(r.high);
        const yLow = y.scale(r.low);
        const yOpen = y.scale(r.open);
        const yClose = y.scale(r.close);
        const up = r.close >= r.open;
        const fill = up ? '#16a34a' : '#dc2626';
        const top = Math.min(yOpen, yClose);
        const h = Math.max(1, Math.abs(yOpen - yClose));
        return (
          <g key={r.date}>
            <line x1={cx} x2={cx} y1={yHigh} y2={yLow} stroke={fill} strokeWidth={1} />
            <rect x={cx - width / 2} y={top} width={width} height={h} fill={fill} />
          </g>
        );
      })}
    </g>
  );
}

function KLineCard() {
  const { data } = useStockHistory();
  const rows = useMemo(() => (data ? flattenHistory(data) : []), [data]);
  if (!rows.length) return null;
  return (
    <ChartCard title="日 K 棒">
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <XAxis dataKey="date" hide />
          <YAxis domain={['auto', 'auto']} />
          <Tooltip
            formatter={(v: number) => v.toLocaleString()}
            labelFormatter={(label) => label as string}
          />
          {/* Hidden bar so recharts allocates the chart area; the candles are drawn via Customized */}
          <Bar dataKey="high" fill="transparent" isAnimationActive={false} />
          <Customized
            component={(props: any) => (
              <CandleLayer rows={rows} xAxisMap={props.xAxisMap} yAxisMap={props.yAxisMap} />
            )}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

registerCard({
  id: 'stock-kline',
  label: '日 K 棒',
  defaultPage: 'stock',
  component: KLineCard,
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
import './stock-charts';
```

- [ ] **Step 3: KLineCard test (renders N candles)**

```tsx
// tests/stock-charts.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/stock-charts';
import { listCards } from '../src/cards/registry';

function makeHistory(rows: number) {
  const dates: string[] = [];
  const candles: any[] = [];
  for (let i = 0; i < rows; i++) {
    const d = new Date(2026, 4, 1 + i).toISOString().slice(0, 10);
    dates.push(d);
    candles.push({ open: 100 + i, high: 110 + i, low: 90 + i, close: 105 + i, volume: 1000 + i });
  }
  return {
    ticker: '2330.TW', name: '台積電', currency: 'TWD', time_range: '3M',
    dates, candles,
    indicators: {
      ma5: dates.map(() => null), ma20: dates.map(() => null), ma60: dates.map(() => null),
      rsi14: dates.map(() => 50),
      macd: dates.map(() => 0), macd_signal: dates.map(() => 0), macd_histogram: dates.map(() => 0),
    },
  };
}

function renderCardOnPage(id: string) {
  const Card = listCards('stock').find((c) => c.id === id)!.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/stock/2330.TW']}>
        <Routes>
          <Route path="/stock/:code" element={<Card />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('KLineCard', () => {
  it('registers cols=3 on stock page', () => {
    expect(listCards('stock').find((c) => c.id === 'stock-kline')?.cols).toBe(3);
  });

  it('renders one candle per row in dates', async () => {
    server.use(http.get('*/api/stocks/2330.TW/history', () => HttpResponse.json(makeHistory(4))));
    const { container } = renderCardOnPage('stock-kline');
    await waitFor(() => expect(screen.getByText('日 K 棒')).toBeInTheDocument());
    await waitFor(() => {
      const candles = container.querySelector('[data-testid="candles"]');
      expect(candles?.children.length).toBe(4);
    });
  });
});
```

- [ ] **Step 4: Run, expect 2/2 pass + all others green.**

- [ ] **Step 5: Commit**

```bash
git add src/cards/stock-charts.tsx src/cards/index.ts tests/stock-charts.test.tsx
git commit -m "feat(stock-dashboard): KLineCard + stock-charts shell (FE-C1-T3)"
```

---

### Task 4: PriceMACard (close + 3 MA lines)

**Files:**
- Modify: `stock/dashboard/frontend/src/cards/stock-charts.tsx`
- Modify: `stock/dashboard/frontend/tests/stock-charts.test.tsx`

- [ ] **Step 1: Append PriceMACard to stock-charts.tsx**

```tsx
// src/cards/stock-charts.tsx (append at bottom — keep imports up top consolidated)
// Add to imports: LineChart, Line, CartesianGrid, Legend
import { CartesianGrid, Legend, Line, LineChart } from 'recharts';

function PriceMACard() {
  const { data } = useStockHistory();
  const rows = useMemo(() => (data ? flattenHistory(data) : []), [data]);
  if (!rows.length) return null;
  return (
    <ChartCard title="收盤價 + 移動平均">
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <LineChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" hide />
          <YAxis domain={['auto', 'auto']} />
          <Tooltip formatter={(v: number) => v?.toLocaleString?.() ?? v} />
          <Legend />
          <Line dataKey="close" stroke="#52525b" dot={false} strokeWidth={2} />
          <Line dataKey="ma5"   stroke="#f97316" dot={false} />
          <Line dataKey="ma20"  stroke="#3b82f6" dot={false} />
          <Line dataKey="ma60"  stroke="#a855f7" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

registerCard({
  id: 'stock-price-ma',
  label: '收盤價 + 移動平均',
  defaultPage: 'stock',
  component: PriceMACard,
  cols: 3,
});
```

- [ ] **Step 2: Append test**

```tsx
// tests/stock-charts.test.tsx (append)
describe('PriceMACard', () => {
  it('renders 4 line series (close + ma5/20/60)', async () => {
    server.use(http.get('*/api/stocks/2330.TW/history', () => HttpResponse.json(makeHistory(8))));
    const { container } = renderCardOnPage('stock-price-ma');
    await waitFor(() => expect(screen.getByText('收盤價 + 移動平均')).toBeInTheDocument());
    await waitFor(() => {
      const lines = container.querySelectorAll('.recharts-line');
      expect(lines.length).toBe(4);
    });
  });
});
```

- [ ] **Step 3: Run, expect green.**

- [ ] **Step 4: Commit**

```bash
git add src/cards/stock-charts.tsx tests/stock-charts.test.tsx
git commit -m "feat(stock-dashboard): PriceMACard close + MA5/20/60 lines (FE-C1-T4)"
```

---

### Task 5: VolumeCard (colored bars)

**Files:**
- Modify: `stock/dashboard/frontend/src/cards/stock-charts.tsx`
- Modify: `stock/dashboard/frontend/tests/stock-charts.test.tsx`

- [ ] **Step 1: Append VolumeCard**

```tsx
// imports add: Cell
import { Cell } from 'recharts';

function VolumeCard() {
  const { data } = useStockHistory();
  const rows = useMemo(() => (data ? flattenHistory(data) : []), [data]);
  if (!rows.length) return null;
  return (
    <ChartCard title="成交量">
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <XAxis dataKey="date" hide />
          <YAxis />
          <Tooltip formatter={(v: number) => v?.toLocaleString?.() ?? v} />
          <Bar dataKey="volume">
            {rows.map((r) => (
              <Cell
                key={r.date}
                fill={r.change_pct == null ? '#a1a1aa' : r.change_pct >= 0 ? '#16a34a' : '#dc2626'}
              />
            ))}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

registerCard({
  id: 'stock-volume',
  label: '成交量',
  defaultPage: 'stock',
  component: VolumeCard,
  cols: 3,
});
```

- [ ] **Step 2: Append test**

```tsx
describe('VolumeCard', () => {
  it('colors bars by change_pct sign', async () => {
    server.use(http.get('*/api/stocks/2330.TW/history', () => HttpResponse.json(makeHistory(3))));
    const { container } = renderCardOnPage('stock-volume');
    await waitFor(() => expect(screen.getByText('成交量')).toBeInTheDocument());
    await waitFor(() => {
      // makeHistory increases close monotonically → positive change_pct after row 0
      const bars = container.querySelectorAll('.recharts-bar-rectangle path');
      expect(bars.length).toBeGreaterThan(0);
    });
    // first bar (no prev) → grey
    const firstBar = container.querySelectorAll('.recharts-bar-rectangle path')[0];
    expect(firstBar.getAttribute('fill')).toBe('#a1a1aa');
  });
});
```

- [ ] **Step 3: Run, expect green.**

- [ ] **Step 4: Commit**

```bash
git add src/cards/stock-charts.tsx tests/stock-charts.test.tsx
git commit -m "feat(stock-dashboard): VolumeCard colored bars (FE-C1-T5)"
```

---

### Task 6: RSICard (line + reference 70/30)

**Files:**
- Modify: `stock/dashboard/frontend/src/cards/stock-charts.tsx`
- Modify: `stock/dashboard/frontend/tests/stock-charts.test.tsx`

- [ ] **Step 1: Append RSICard**

```tsx
// imports add: ReferenceLine
import { ReferenceLine } from 'recharts';

function RSICard() {
  const { data } = useStockHistory();
  const rows = useMemo(() => (data ? flattenHistory(data) : []), [data]);
  if (!rows.length) return null;
  return (
    <ChartCard title="RSI(14)">
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" hide />
          <YAxis domain={[0, 100]} ticks={[0, 30, 50, 70, 100]} />
          <Tooltip formatter={(v: number) => v?.toFixed?.(2) ?? v} />
          <ReferenceLine y={70} stroke="#fca5a5" strokeDasharray="4 4" />
          <ReferenceLine y={30} stroke="#86efac" strokeDasharray="4 4" />
          <Line dataKey="rsi14" stroke="#3b82f6" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

registerCard({
  id: 'stock-rsi',
  label: 'RSI(14)',
  defaultPage: 'stock',
  component: RSICard,
  cols: 3,
});
```

- [ ] **Step 2: Append test**

```tsx
describe('RSICard', () => {
  it('renders 70 and 30 reference lines', async () => {
    server.use(http.get('*/api/stocks/2330.TW/history', () => HttpResponse.json(makeHistory(5))));
    const { container } = renderCardOnPage('stock-rsi');
    await waitFor(() => expect(screen.getByText('RSI(14)')).toBeInTheDocument());
    await waitFor(() => {
      const refs = container.querySelectorAll('.recharts-reference-line');
      expect(refs.length).toBe(2);
    });
  });
});
```

- [ ] **Step 3: Run, expect green.**

- [ ] **Step 4: Commit**

```bash
git add src/cards/stock-charts.tsx tests/stock-charts.test.tsx
git commit -m "feat(stock-dashboard): RSICard with 70/30 reference lines (FE-C1-T6)"
```

---

### Task 7: MACDCard (composed: 2 lines + histogram bars)

**Files:**
- Modify: `stock/dashboard/frontend/src/cards/stock-charts.tsx`
- Modify: `stock/dashboard/frontend/tests/stock-charts.test.tsx`

- [ ] **Step 1: Append MACDCard**

```tsx
function MACDCard() {
  const { data } = useStockHistory();
  const rows = useMemo(() => (data ? flattenHistory(data) : []), [data]);
  if (!rows.length) return null;
  return (
    <ChartCard title="MACD(12,26,9)">
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" hide />
          <YAxis />
          <Tooltip formatter={(v: number) => v?.toFixed?.(3) ?? v} />
          <ReferenceLine y={0} stroke="#71717a" />
          <Bar dataKey="macd_histogram">
            {rows.map((r) => (
              <Cell
                key={r.date}
                fill={(r.macd_histogram ?? 0) >= 0 ? '#16a34a' : '#dc2626'}
              />
            ))}
          </Bar>
          <Line dataKey="macd"        stroke="#3b82f6" dot={false} />
          <Line dataKey="macd_signal" stroke="#f97316" dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

registerCard({
  id: 'stock-macd',
  label: 'MACD(12,26,9)',
  defaultPage: 'stock',
  component: MACDCard,
  cols: 3,
});
```

- [ ] **Step 2: Append test**

```tsx
describe('MACDCard', () => {
  it('renders both MACD and signal lines plus a histogram bar series', async () => {
    server.use(http.get('*/api/stocks/2330.TW/history', () => HttpResponse.json(makeHistory(6))));
    const { container } = renderCardOnPage('stock-macd');
    await waitFor(() => expect(screen.getByText('MACD(12,26,9)')).toBeInTheDocument());
    await waitFor(() => {
      const lines = container.querySelectorAll('.recharts-line');
      const bars = container.querySelectorAll('.recharts-bar');
      expect(lines.length).toBe(2);
      expect(bars.length).toBe(1);
    });
  });
});
```

- [ ] **Step 3: Run all tests + build, expect green.**

- [ ] **Step 4: Commit**

```bash
git add src/cards/stock-charts.tsx tests/stock-charts.test.tsx
git commit -m "feat(stock-dashboard): MACDCard composed line + histogram (FE-C1-T7)"
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
git merge --no-ff feat/fe-c1-stock-charts -m "feat(stock-dashboard): per-stock detail page + 5 chart cards (FE-C1)"
```

- [ ] **Step 3: Push, watch deploy**

```bash
git push origin master
gh run list --workflow=deploy-stock-dashboard.yml --limit 1
gh run watch <id> --exit-status
```

- [ ] **Step 4: Smoke test**

```bash
curl -sI "https://paul-learning.dev/tools/stock/2330.TW?cb=$(date +%s)" | head -3
```

Expect HTTP 200 (404.html SPA fallback boots the React app).

- [ ] **Step 5: Browser verification (manual)**

- Click any ticker on dashboard watchlist → navigates to `/tools/stock/{ticker}`
- Page shows ticker · name in title; range buttons present
- 5 cards stacked vertically: K-line / Close+MA / Volume / RSI / MACD
- Click 1Y → URL becomes `?range=1Y` and chart data refetches
- Refresh on `/tools/stock/2330.TW?range=1Y` → still loads (404.html fallback works)

## Self-Review

**Spec coverage:** hooks + recharts (T1) → page + range UI (T2) → 5 cards in dedicated tasks (T3-T7) → deploy (T8). Each card is self-contained.

**Placeholder scan:** No TBDs. Code blocks are complete. The custom candlestick `Customized` integration is the riskiest part; T3 spec calls out the risk (recharts/issues/3324). If it fails to integrate with axes, the spec already provides the fallback option.

**Type consistency:** `StockHistoryResponse` defined in T1, used everywhere. `ChartRow` in T1, used in T3-T7.

**Risks:**
- Bundle: recharts adds ~80KB gzip. Total expected ~470KB JS / ~160KB gzip — within rough ceiling.
- Custom candlestick: T3's `Customized` access to `xAxisMap` / `yAxisMap` is documented but not officially typed in recharts. If `props.xAxisMap` is empty in test (jsdom layout), the candle assertion may fail; in that case adjust the test to assert presence of the wrapping `[data-testid="candles"]` element only and validate visually in deploy smoke.
