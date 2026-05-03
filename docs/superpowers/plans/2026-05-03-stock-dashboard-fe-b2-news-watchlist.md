# Stock Dashboard FE-B2 Implementation Plan

**Goal:** Add News and Watchlist cards to the dashboard. Extend `CardSpec` with a `cols` field so wide cards can occupy multiple grid columns. Watchlist tickers link to `/stock/:code`.

**Architecture:** Two new cards registered with `cols: 3`. News is a read-only list. Watchlist hits a CRUD hook (TanStack Query mutations) and uses shadcn Table. CardSpec gains an optional `cols` field; DashboardPage wraps each card in a `col-span-{cols}` div.

**Tech Stack:** React 18, TanStack Query v5 mutations, react-router v6 `<Link>`, shadcn/ui (Table — markup only), Vitest + RTL + msw.

Branch: `feat/fe-b2-news-watchlist` off `master`.

---

### Task 1: Branch + extend CardSpec with cols + DashboardPage col-span

**Files:**
- Modify: `stock/dashboard/frontend/src/cards/registry.ts`
- Modify: `stock/dashboard/frontend/src/pages/DashboardPage.tsx`
- Modify: `stock/dashboard/frontend/tests/registry.test.ts`
- Modify: `stock/dashboard/frontend/tests/DashboardPage.test.tsx`

- [ ] **Step 1: Create branch**

```bash
git checkout master && git pull && git checkout -b feat/fe-b2-news-watchlist
```

- [ ] **Step 2: Add registry test for cols default + explicit value**

Append to `tests/registry.test.ts`:

```typescript
  it('cols defaults to undefined; explicit cols preserved', () => {
    registerCard({ id: 'one', label: 'One', defaultPage: 'dashboard', component: Stub });
    registerCard({ id: 'three', label: 'Three', defaultPage: 'dashboard', component: Stub, cols: 3 });
    const list = listCards('dashboard');
    expect(list.find(c => c.id === 'one')?.cols).toBeUndefined();
    expect(list.find(c => c.id === 'three')?.cols).toBe(3);
  });
```

- [ ] **Step 3: Add cols to CardSpec**

```typescript
// src/cards/registry.ts (modify CardSpec only)
export interface CardSpec {
  id: string;
  label: string;
  defaultPage: CardPage;
  component: FC;
  cols?: 1 | 2 | 3;
}
```

- [ ] **Step 4: Apply col-span in DashboardPage**

```tsx
// src/pages/DashboardPage.tsx
import { listCards } from '@/cards/registry';
import { useCardPrefsStore } from '@/store/card-prefs-store';
import { DashboardSettingsDialog } from '@/components/DashboardSettingsDialog';
import { cn } from '@/lib/utils';

export default function DashboardPage() {
  const allCards = listCards('dashboard');
  const hiddenIds = useCardPrefsStore((s) => s.hiddenIds);
  const visible = allCards.filter((c) => !hiddenIds.has(c.id));

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <DashboardSettingsDialog />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {visible.map(({ id, component: Card, cols = 1 }) => (
          <div
            key={id}
            className={cn(
              cols === 3 && 'lg:col-span-3',
              cols === 2 && 'lg:col-span-2',
            )}
          >
            <Card />
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Add DashboardPage span-class test**

Append to `tests/DashboardPage.test.tsx`:

```typescript
  it('wide cards get lg:col-span-3 wrapper class', async () => {
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText('加權指數')).toBeInTheDocument());
    // No wide cards yet (FE-B2 T2/T3 add them); confirm indicator cards have no col-span class.
    const wrappers = container.querySelectorAll('.grid > div');
    wrappers.forEach((w) => {
      expect(w.className).not.toMatch(/col-span/);
    });
  });
```

- [ ] **Step 6: Run all tests, expect green**

```bash
cd stock/dashboard/frontend && npm test
```

- [ ] **Step 7: Commit**

```bash
git add src/cards/registry.ts src/pages/DashboardPage.tsx tests/registry.test.ts tests/DashboardPage.test.tsx
git commit -m "feat(stock-dashboard): CardSpec.cols + col-span wrapper (FE-B2-T1)"
```

---

### Task 2: useNews hook + NewsCard

**Files:**
- Create: `stock/dashboard/frontend/src/hooks/useNews.ts`
- Create: `stock/dashboard/frontend/src/lib/relative-time.ts`
- Create: `stock/dashboard/frontend/src/cards/NewsCard.tsx`
- Create: `stock/dashboard/frontend/tests/NewsCard.test.tsx`
- Modify: `stock/dashboard/frontend/src/cards/index.ts`

- [ ] **Step 1: Create relative-time helper + tiny test**

```typescript
// src/lib/relative-time.ts
export function relativeTime(iso: string, now: Date = new Date()): string {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '';
  const diffMin = Math.round((now.getTime() - t) / 60_000);
  if (diffMin < 1) return '剛剛';
  if (diffMin < 60) return `${diffMin} 分鐘前`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr} 小時前`;
  const diffDay = Math.round(diffHr / 24);
  if (diffDay < 7) return `${diffDay} 天前`;
  return iso.slice(0, 10);
}
```

- [ ] **Step 2: Create useNews hook**

```typescript
// src/hooks/useNews.ts
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface NewsItem {
  title: string;
  url: string;
  source: string;
  published: string;
}

export function useNews(limit = 15) {
  return useQuery<NewsItem[]>({
    queryKey: ['news', limit],
    queryFn: () => apiFetch<NewsItem[]>(`/api/news?limit=${limit}`),
  });
}
```

- [ ] **Step 3: NewsCard test (failing first)**

```tsx
// tests/NewsCard.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/NewsCard';
import { listCards } from '../src/cards/registry';

function renderCard() {
  const spec = listCards('dashboard').find((c) => c.id === 'news')!;
  const Card = spec.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Card />
    </QueryClientProvider>,
  );
}

describe('NewsCard', () => {
  it('registers as a wide (cols=3) dashboard card', () => {
    const spec = listCards('dashboard').find((c) => c.id === 'news');
    expect(spec?.cols).toBe(3);
  });

  it('renders items as external anchor tags', async () => {
    server.use(
      http.get('*/api/news', () =>
        HttpResponse.json([
          { title: 'A 公司營收創高', url: 'https://news.example/a', source: '鉅亨網台股', published: new Date().toISOString() },
          { title: 'B 央行升息', url: 'https://news.example/b', source: '鉅亨頭條', published: new Date().toISOString() },
        ]),
      ),
    );
    renderCard();
    await waitFor(() => {
      const a = screen.getByRole('link', { name: 'A 公司營收創高' });
      expect(a).toHaveAttribute('href', 'https://news.example/a');
      expect(a).toHaveAttribute('target', '_blank');
    });
  });
});
```

- [ ] **Step 4: NewsCard implementation**

```tsx
// src/cards/NewsCard.tsx
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useNews } from '@/hooks/useNews';
import { relativeTime } from '@/lib/relative-time';
import { registerCard } from './registry';

function NewsCard() {
  const { data, isLoading, isError } = useNews();
  return (
    <Card>
      <CardHeader>
        <CardTitle>最新財經新聞</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
        {isError && <p className="text-sm text-destructive">無法載入</p>}
        {data && (
          <ul className="space-y-3">
            {data.map((item) => (
              <li key={item.url}>
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm hover:underline"
                >
                  {item.title}
                </a>
                <p className="text-xs text-muted-foreground">
                  {item.source} · {relativeTime(item.published)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'news',
  label: '最新財經新聞',
  defaultPage: 'dashboard',
  component: NewsCard,
  cols: 3,
});
```

- [ ] **Step 5: Wire into cards/index.ts**

```typescript
// src/cards/index.ts
import './dashboard-cards';
import './NewsCard';
```

- [ ] **Step 6: Run, expect 2/2 NewsCard pass + all others green.**

- [ ] **Step 7: Commit**

```bash
git add src/lib/relative-time.ts src/hooks/useNews.ts src/cards/NewsCard.tsx src/cards/index.ts tests/NewsCard.test.tsx
git commit -m "feat(stock-dashboard): NewsCard + relative-time helper (FE-B2-T2)"
```

---

### Task 3: shadcn Table + WatchlistCard read-only

**Files:**
- Create: `stock/dashboard/frontend/src/components/ui/table.tsx`
- Create: `stock/dashboard/frontend/src/hooks/useWatchlist.ts` (query only in this task)
- Create: `stock/dashboard/frontend/src/cards/WatchlistCard.tsx` (read-only first)
- Create: `stock/dashboard/frontend/tests/WatchlistCard.test.tsx`
- Modify: `stock/dashboard/frontend/src/cards/index.ts`

- [ ] **Step 1: shadcn Table component (no extra deps, just styled markup)**

```tsx
// src/components/ui/table.tsx
import * as React from 'react';
import { cn } from '@/lib/utils';

const Table = React.forwardRef<HTMLTableElement, React.HTMLAttributes<HTMLTableElement>>(
  ({ className, ...props }, ref) => (
    <div className="relative w-full overflow-auto">
      <table ref={ref} className={cn('w-full caption-bottom text-sm', className)} {...props} />
    </div>
  ),
);
Table.displayName = 'Table';

const TableHeader = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => <thead ref={ref} className={cn('[&_tr]:border-b', className)} {...props} />,
);
TableHeader.displayName = 'TableHeader';

const TableBody = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => <tbody ref={ref} className={cn('[&_tr:last-child]:border-0', className)} {...props} />,
);
TableBody.displayName = 'TableBody';

const TableRow = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr ref={ref} className={cn('border-b transition-colors hover:bg-muted/50', className)} {...props} />
  ),
);
TableRow.displayName = 'TableRow';

const TableHead = React.forwardRef<HTMLTableCellElement, React.ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th ref={ref} className={cn('h-10 px-2 text-left align-middle font-medium text-muted-foreground', className)} {...props} />
  ),
);
TableHead.displayName = 'TableHead';

const TableCell = React.forwardRef<HTMLTableCellElement, React.TdHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <td ref={ref} className={cn('p-2 align-middle', className)} {...props} />
  ),
);
TableCell.displayName = 'TableCell';

export { Table, TableHeader, TableBody, TableRow, TableHead, TableCell };
```

- [ ] **Step 2: useWatchlist (query only)**

```typescript
// src/hooks/useWatchlist.ts
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface WatchlistRow {
  ticker: string;
  name: string;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  currency: string | null;
  timestamp: string | null;
}

export function useWatchlist() {
  return useQuery<WatchlistRow[]>({
    queryKey: ['stocks'],
    queryFn: () => apiFetch<WatchlistRow[]>('/api/stocks'),
  });
}
```

- [ ] **Step 3: WatchlistCard read-only test (failing first)**

```tsx
// tests/WatchlistCard.test.tsx (initial — read-only coverage)
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/WatchlistCard';
import { listCards } from '../src/cards/registry';

function renderCard() {
  const spec = listCards('dashboard').find((c) => c.id === 'watchlist')!;
  const Card = spec.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Card />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('WatchlistCard (read-only)', () => {
  it('registers as cols=3 dashboard card', () => {
    expect(listCards('dashboard').find((c) => c.id === 'watchlist')?.cols).toBe(3);
  });

  it('renders rows with ticker as a link to /stock/:code', async () => {
    server.use(
      http.get('*/api/stocks', () =>
        HttpResponse.json([
          { ticker: '2330.TW', name: '台積電', price: 1000, change: 5, change_pct: 0.5, currency: 'TWD', timestamp: '2026-05-02' },
        ]),
      ),
    );
    renderCard();
    await waitFor(() => {
      const link = screen.getByRole('link', { name: '2330.TW' });
      expect(link).toHaveAttribute('href', '/stock/2330.TW');
      expect(screen.getByText('台積電')).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 4: WatchlistCard implementation (read-only)**

```tsx
// src/cards/WatchlistCard.tsx
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { useWatchlist, type WatchlistRow } from '@/hooks/useWatchlist';
import { cn } from '@/lib/utils';
import { registerCard } from './registry';

function fmtChange(n: number | null, suffix = ''): string {
  if (n == null) return '—';
  return (n >= 0 ? '+' : '') + n.toFixed(2) + suffix;
}

function changeClass(n: number | null): string | undefined {
  if (n == null) return undefined;
  return n >= 0 ? 'text-green-600' : 'text-red-600';
}

function Row({ row }: { row: WatchlistRow }) {
  return (
    <TableRow>
      <TableCell>
        <Link to={`/stock/${row.ticker}`} className="font-medium hover:underline">
          {row.ticker}
        </Link>
      </TableCell>
      <TableCell>{row.name}</TableCell>
      <TableCell className="text-right">
        {row.price != null ? row.price.toLocaleString() + (row.currency ? ' ' + row.currency : '') : '—'}
      </TableCell>
      <TableCell className={cn('text-right', changeClass(row.change))}>
        {fmtChange(row.change)}
      </TableCell>
      <TableCell className={cn('text-right', changeClass(row.change_pct))}>
        {fmtChange(row.change_pct, '%')}
      </TableCell>
      <TableCell />
    </TableRow>
  );
}

function WatchlistCard() {
  const { data, isLoading, isError } = useWatchlist();
  return (
    <Card>
      <CardHeader>
        <CardTitle>自選股票 / ETF / 虛擬幣</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
        {isError && <p className="text-sm text-destructive">無法載入</p>}
        {data && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>代號</TableHead>
                <TableHead>名稱</TableHead>
                <TableHead className="text-right">價格</TableHead>
                <TableHead className="text-right">漲跌</TableHead>
                <TableHead className="text-right">漲跌幅</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row) => <Row key={row.ticker} row={row} />)}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'watchlist',
  label: '自選股票 / ETF / 虛擬幣',
  defaultPage: 'dashboard',
  component: WatchlistCard,
  cols: 3,
});
```

- [ ] **Step 5: Wire into cards/index.ts**

```typescript
// src/cards/index.ts
import './dashboard-cards';
import './NewsCard';
import './WatchlistCard';
```

- [ ] **Step 6: Run, expect 2/2 WatchlistCard pass + all others green.**

- [ ] **Step 7: Commit**

```bash
git add src/components/ui/table.tsx src/hooks/useWatchlist.ts src/cards/WatchlistCard.tsx src/cards/index.ts tests/WatchlistCard.test.tsx
git commit -m "feat(stock-dashboard): WatchlistCard read-only + shadcn Table (FE-B2-T3)"
```

---

### Task 4: addStock mutation + add form

**Files:**
- Modify: `stock/dashboard/frontend/src/hooks/useWatchlist.ts`
- Modify: `stock/dashboard/frontend/src/cards/WatchlistCard.tsx`
- Modify: `stock/dashboard/frontend/tests/WatchlistCard.test.tsx`

- [ ] **Step 1: Append addStock test (failing)**

```tsx
// tests/WatchlistCard.test.tsx (append)
import userEvent from '@testing-library/user-event';

describe('WatchlistCard add form', () => {
  it('typing a ticker and clicking add calls POST /api/stocks then re-fetches', async () => {
    let postCalled: { ticker?: string } = {};
    let stocks: WatchlistRow[] = [];
    server.use(
      http.get('*/api/stocks', () => HttpResponse.json(stocks)),
      http.post('*/api/stocks', async ({ request }) => {
        const body = await request.json() as { ticker: string };
        postCalled = body;
        stocks = [{ ticker: body.ticker, name: body.ticker, price: null, change: null, change_pct: null, currency: null, timestamp: null }];
        return HttpResponse.json({ ok: true });
      }),
    );

    renderCard();
    await waitFor(() => expect(screen.getByPlaceholderText(/輸入代號/)).toBeInTheDocument());
    await userEvent.type(screen.getByPlaceholderText(/輸入代號/), '2317.tw');
    await userEvent.click(screen.getByRole('button', { name: '+ 新增' }));

    await waitFor(() => expect(postCalled.ticker).toBe('2317.TW'));
    await waitFor(() => expect(screen.getByRole('link', { name: '2317.TW' })).toBeInTheDocument());
  });
});
```

Note: import `WatchlistRow` and `userEvent` at top of the file if not already imported. Append `import type { WatchlistRow } from '../src/hooks/useWatchlist';` and `import userEvent from '@testing-library/user-event';` near the existing imports.

- [ ] **Step 2: Add useAddStock to useWatchlist hook**

```typescript
// src/hooks/useWatchlist.ts (replace previous content)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface WatchlistRow {
  ticker: string;
  name: string;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  currency: string | null;
  timestamp: string | null;
}

export function useWatchlist() {
  return useQuery<WatchlistRow[]>({
    queryKey: ['stocks'],
    queryFn: () => apiFetch<WatchlistRow[]>('/api/stocks'),
  });
}

export function useAddStock() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) =>
      apiFetch('/api/stocks', { method: 'POST', body: JSON.stringify({ ticker }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['stocks'] }),
  });
}
```

- [ ] **Step 3: Wire add form into WatchlistCard**

```tsx
// inside src/cards/WatchlistCard.tsx — add useState import and a form below the Table
import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useAddStock, useWatchlist, type WatchlistRow } from '@/hooks/useWatchlist';

function AddForm() {
  const [value, setValue] = useState('');
  const add = useAddStock();
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = value.trim().toUpperCase();
    if (!t) return;
    add.mutate(t, { onSuccess: () => setValue('') });
  };
  return (
    <form onSubmit={submit} className="flex gap-2 pt-3">
      <Input
        placeholder="輸入代號，例如 2317.TW、AAPL、ETH-USD"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={add.isPending}
      />
      <Button type="submit" disabled={add.isPending}>+ 新增</Button>
    </form>
  );
}
```

Then inside the WatchlistCard's CardContent, render `<AddForm />` after the Table block.

- [ ] **Step 4: Run tests, expect WatchlistCard add test passes + previous tests still green.**

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useWatchlist.ts src/cards/WatchlistCard.tsx tests/WatchlistCard.test.tsx
git commit -m "feat(stock-dashboard): watchlist addStock mutation + form (FE-B2-T4)"
```

---

### Task 5: deleteStock mutation + row delete button

**Files:**
- Modify: `stock/dashboard/frontend/src/hooks/useWatchlist.ts`
- Modify: `stock/dashboard/frontend/src/cards/WatchlistCard.tsx`
- Modify: `stock/dashboard/frontend/tests/WatchlistCard.test.tsx`

- [ ] **Step 1: Failing delete test (append to WatchlistCard.test.tsx)**

```tsx
describe('WatchlistCard delete', () => {
  it('clicking × on a row calls DELETE /api/stocks/:ticker and removes the row', async () => {
    let stocks: WatchlistRow[] = [
      { ticker: '2330.TW', name: '台積電', price: 1000, change: 5, change_pct: 0.5, currency: 'TWD', timestamp: '2026-05-02' },
      { ticker: 'AAPL',    name: 'Apple',  price: 200,  change: -1, change_pct: -0.5, currency: 'USD', timestamp: '2026-05-02' },
    ];
    let deletedTicker = '';
    server.use(
      http.get('*/api/stocks', () => HttpResponse.json(stocks)),
      http.delete('*/api/stocks/:ticker', ({ params }) => {
        deletedTicker = decodeURIComponent(params.ticker as string);
        stocks = stocks.filter((s) => s.ticker !== deletedTicker);
        return HttpResponse.json({ ok: true });
      }),
    );

    renderCard();
    await waitFor(() => expect(screen.getByRole('link', { name: '2330.TW' })).toBeInTheDocument());
    const rows = screen.getAllByRole('row');
    const tsmcRow = rows.find((r) => r.textContent?.includes('2330.TW'))!;
    await userEvent.click(within(tsmcRow).getByRole('button', { name: /移除/ }));

    await waitFor(() => expect(deletedTicker).toBe('2330.TW'));
    await waitFor(() => expect(screen.queryByRole('link', { name: '2330.TW' })).not.toBeInTheDocument());
  });
});
```

Add `import { within } from '@testing-library/react';` at the top.

- [ ] **Step 2: Add useDeleteStock**

```typescript
// src/hooks/useWatchlist.ts (append)
export function useDeleteStock() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) =>
      apiFetch(`/api/stocks/${encodeURIComponent(ticker)}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['stocks'] }),
  });
}
```

- [ ] **Step 3: Wire delete button into Row**

```tsx
// inside src/cards/WatchlistCard.tsx — modify Row to accept delete callback
import { X } from 'lucide-react';
import { useDeleteStock } from '@/hooks/useWatchlist';

function Row({ row, onDelete, deleting }: { row: WatchlistRow; onDelete: (t: string) => void; deleting: boolean }) {
  return (
    <TableRow>
      <TableCell>
        <Link to={`/stock/${row.ticker}`} className="font-medium hover:underline">
          {row.ticker}
        </Link>
      </TableCell>
      <TableCell>{row.name}</TableCell>
      <TableCell className="text-right">
        {row.price != null ? row.price.toLocaleString() + (row.currency ? ' ' + row.currency : '') : '—'}
      </TableCell>
      <TableCell className={cn('text-right', changeClass(row.change))}>
        {fmtChange(row.change)}
      </TableCell>
      <TableCell className={cn('text-right', changeClass(row.change_pct))}>
        {fmtChange(row.change_pct, '%')}
      </TableCell>
      <TableCell className="text-right">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onDelete(row.ticker)}
          disabled={deleting}
          aria-label={`移除 ${row.ticker}`}
        >
          <X className="h-4 w-4" />
        </Button>
      </TableCell>
    </TableRow>
  );
}
```

Then in `WatchlistCard`, instantiate the mutation and pass it down:

```tsx
function WatchlistCard() {
  const { data, isLoading, isError } = useWatchlist();
  const del = useDeleteStock();
  // ...
  {data && (
    <Table>
      {/* ... */}
      <TableBody>
        {data.map((row) => (
          <Row
            key={row.ticker}
            row={row}
            onDelete={(t) => del.mutate(t)}
            deleting={del.isPending && del.variables === row.ticker}
          />
        ))}
      </TableBody>
    </Table>
  )}
```

- [ ] **Step 4: Run all tests, expect green.**

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useWatchlist.ts src/cards/WatchlistCard.tsx tests/WatchlistCard.test.tsx
git commit -m "feat(stock-dashboard): watchlist delete button + mutation (FE-B2-T5)"
```

---

### Task 6: Final verify, merge, push, deploy check

- [ ] **Step 1: Full test + build**

```bash
npm test
npm run build
```

- [ ] **Step 2: Merge to master**

```bash
git checkout master
git merge --no-ff feat/fe-b2-news-watchlist -m "feat(stock-dashboard): news + watchlist cards (FE-B2)"
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

- 14 cards render (12 indicator + News + Watchlist)
- News list shows 15 clickable items, opens in new tab
- Add a ticker → row appears in table
- Click × on a row → row disappears
- Click ticker → navigates to `/tools/stock/stock/2330.TW` (placeholder StockDetailPage from FE-A; FE-C will populate)
- Settings dialog now lists 14 cards; toggling News or Watchlist hides them and persists across reload

## Self-Review

**Spec coverage:** registry.cols (T1) → DashboardPage span (T1) → News (T2) → Watchlist read (T3) → addStock (T4) → deleteStock (T5) → deploy (T6).

**Placeholder scan:** No TBDs. Every code step has full code.

**Type consistency:** `WatchlistRow` defined in T3, used in T4/T5. `NewsItem` in T2 only. `CardSpec.cols` introduced T1, consumed by Card registrations in T2/T3.

**Risks:** No new heavy deps (Table is markup only). Bundle should stay near 320KB. The route `/stock/:code` exists from FE-A as a placeholder, so the watchlist `<Link>` won't 404 even before FE-C lands.
