# Stock Dashboard FE-B2 — News + Watchlist Cards

**Date:** 2026-05-03
**Status:** spec
**Phase:** 5 sub-phase 3 (after FE-B dashboard cards)

## Goal

Migrate the legacy dashboard's two list-style sections — News list and Watchlist — into React cards registered through the FE-B registry pattern. Extend `CardSpec` with a `cols` field so wide cards can occupy multiple grid columns. Watchlist tickers link to `/stock/:code` (placeholder until FE-C populates the detail page).

After FE-B2: only the alerts CRUD section remains on the legacy `stock.html`. FE-B3 covers alerts; FE-C covers per-stock detail (including the history chart).

## Non-Goals

- Alerts UI — FE-B3.
- Per-indicator history chart — FE-C (chart lib shared with K-line/MA/RSI/MACD).
- Optimistic updates — invalidate-and-refetch is sufficient.
- Pagination, search, sort on watchlist or news — flat lists.
- Backend changes — uses existing `/api/news` and `/api/stocks` endpoints.

## Architecture

### CardSpec extension

```typescript
// src/cards/registry.ts
export interface CardSpec {
  id: string;
  label: string;
  defaultPage: CardPage;
  component: FC;
  cols?: 1 | 2 | 3;   // default 1
}
```

`DashboardPage` reads `cols` (defaulting to 1) and wraps each card in a `col-span-{cols}` div on lg breakpoint.

### News card

```
src/hooks/useNews.ts          NEW
src/cards/NewsCard.tsx        NEW
```

`useNews()` is `useQuery({ queryKey: ['news'], queryFn: () => apiFetch('/api/news?limit=15') })`. Backend returns `Array<{ title: string; url: string; source: string; published: string }>`.

`NewsCard` registers with `cols: 3, defaultPage: 'dashboard'`. Renders a shadcn Card containing a `<ul>` of 15 items: `<a href={url} target="_blank" rel="noopener">{title}</a>` + secondary line `{source} · {relativeTime(published)}`.

### Watchlist card

```
src/hooks/useWatchlist.ts     NEW (read + add + delete)
src/cards/WatchlistCard.tsx   NEW
src/components/ui/table.tsx   NEW (shadcn add)
```

`useWatchlist()` exposes:
- `query` — `useQuery(['stocks'], () => apiFetch('/api/stocks'))`
- `addStock` — `useMutation((ticker: string) => apiFetch('/api/stocks', { method: 'POST', body: JSON.stringify({ ticker }) }))` — `onSuccess` invalidates `['stocks']`
- `deleteStock` — `useMutation((ticker: string) => apiFetch('/api/stocks/' + encodeURIComponent(ticker), { method: 'DELETE' }))` — same invalidation

`WatchlistCard` registers with `cols: 3, defaultPage: 'dashboard'`. Layout:
- shadcn `Table` with columns: 代號 / 名稱 / 價格 / 漲跌 / 漲跌幅 / [×]
- Ticker cell wraps text in `<Link to={'/stock/' + ticker}>` (react-router)
- Change/change_pct text colored red (down) / green (up)
- Below the table: `Input` + `Button` row that calls `addStock.mutate(value.trim().toUpperCase())` on submit
- × button per row calls `deleteStock.mutate(ticker)` and is disabled while pending

### DashboardPage layout

```tsx
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
```

Indicator cards default to `cols: 1` (unchanged). News and Watchlist register at `cols: 3` and span the whole row on `lg` breakpoint.

## Display details

### News item rendering

```tsx
<li>
  <a href={item.url} target="_blank" rel="noopener" className="text-sm hover:underline">
    {item.title}
  </a>
  <p className="text-xs text-muted-foreground">
    {item.source} · {relativeTime(item.published)}
  </p>
</li>
```

`relativeTime` is a tiny helper: minutes/hours/days ago, falling back to `published.slice(0, 10)` when stale.

### Watchlist row rendering

| 代號 | 名稱 | 價格 | 漲跌 | 漲跌幅 | × |
|---|---|---|---|---|---|
| Link to /stock/2330 | row.name | `price.toLocaleString() + ' ' + currency` | `(±)change.toFixed(2)` (colored) | `(±)change_pct.toFixed(2)%` (colored) | delete btn |

When `price` is null (backend returned no row), render `—` for the four numeric cells.

## Testing strategy

| Test                              | Coverage                                                              |
|-----------------------------------|-----------------------------------------------------------------------|
| `registry.test.ts`                | CardSpec.cols default to 1; explicit cols preserved                   |
| `DashboardPage.test.tsx`          | wide card gets `lg:col-span-3` class                                  |
| `useNews.test.tsx`                | msw handler returns 3 items; hook returns parsed array                |
| `NewsCard.test.tsx`               | renders 3 items as anchor tags with target=_blank                      |
| `useWatchlist.test.tsx`           | addStock invalidates query (calls happen 2x: initial + post-mutation) |
| `WatchlistCard.test.tsx`          | renders rows; ticker is a `<a href="/stock/2330">`; delete and add wire to mutations correctly |

Total: ~12 new tests across 4–6 files.

## File layout

```
src/
  cards/
    registry.ts              MODIFY: add cols
    NewsCard.tsx             NEW
    WatchlistCard.tsx        NEW
    index.ts                 MODIFY: import './NewsCard'; import './WatchlistCard';
  hooks/
    useNews.ts               NEW
    useWatchlist.ts          NEW
  components/ui/table.tsx    NEW (shadcn)
  pages/DashboardPage.tsx    MODIFY: col-span wrapper
tests/
  NewsCard.test.tsx          NEW
  WatchlistCard.test.tsx     NEW
  useWatchlist.test.tsx      NEW
  useNews.test.tsx           NEW (optional — mostly covered by NewsCard test)
  registry.test.ts           MODIFY: add cols default test
  DashboardPage.test.tsx     MODIFY: col-span class assertion
```

## Risks / open items

- shadcn Table is just markup wrappers (no extra deps), so bundle should stay near 320KB.
- The `relativeTime` helper is a tiny pure function — keep it in a `src/lib/relative-time.ts` module so future cards can reuse without duplication.
- `react-router` `<Link>` requires the card to be mounted under a `Router`. In tests we wrap with `MemoryRouter`; in production it's the existing `BrowserRouter` from FE-A.
