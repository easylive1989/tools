# Stock Dashboard FE-C1 — Per-Stock Technical Charts

**Date:** 2026-05-03
**Status:** spec
**Phase:** 5 sub-phase 5 (after FE-B3 alerts)

## Goal

Replace the legacy `stock.html` per-stock detail page's technical-chart top half with a React `StockDetailPage` containing a header + 5 chart cards (K-line, close+MA, volume, RSI, MACD). Time range is a URL search param shared by all 5 charts via a single `useStockHistory` query. Add `recharts` as the project chart library.

After FE-C1: dashboard click `2330.TW` → React detail page shows full technical view with the 5 chart cards. Fundamental cards (broker / chip / valuation / revenue / financial / dividend) move in FE-C2.

## Non-Goals

- Broker / chip / valuation / financial / dividend cards — FE-C2.
- Card visibility picker on the stock page — postponed (registry already supports it via `defaultPage: 'stock'`).
- Drawing tools, indicators, comparisons against benchmark — out of scope.
- Backend changes — `/api/stocks/{ticker}/history` already returns OHLCV + computed MA / RSI / MACD.

## Architecture

### Page + URL state

```
src/pages/StockDetailPage.tsx     MODIFY: full implementation, replaces FE-A placeholder
src/router.tsx                    UNCHANGED: route /stock/:code already exists
```

Page reads `code` from `useParams()` and `range` from `useSearchParams()`, defaulting to `'3M'`. Updating range writes back to URL via `setSearchParams({ range })`. All 5 cards subscribe to the shared query via `useStockHistory()`, which reads the same params internally.

### Shared query + flatten helper

```typescript
// src/hooks/useStockHistory.ts
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

export function useStockHistory(): UseQueryResult<StockHistoryResponse>;
```

```typescript
// src/lib/flatten-history.ts
export interface ChartRow {
  date: string;
  open: number; high: number; low: number; close: number; volume: number;
  ma5: number | null; ma20: number | null; ma60: number | null;
  rsi14: number | null;
  macd: number | null; macd_signal: number | null; macd_histogram: number | null;
  change_pct: number | null;   // computed: (close - prev_close) / prev_close * 100
}

export function flattenHistory(data: StockHistoryResponse): ChartRow[];
```

### Cards

All 5 register with `defaultPage: 'stock'` and `cols: 3`. Layout is a single-column vertical stack inside the page (no grid wrapping multiple columns in FE-C1; charts are tall + wide).

Each card:
- Calls `useStockHistory()`
- Calls `flattenHistory(data)` (memoized via `useMemo`)
- Renders a shadcn `Card` containing a `ResponsiveContainer` from recharts with the chart inside
- Loading / error states handled the same way as FE-B cards

### Chart specs

**KLineCard**

recharts `ComposedChart`. Candlestick is implemented as a `Customized` SVG element overlaid on the chart, computing per-row positions from xAxis/yAxis scales. Each candle:
- Body: rectangle from `min(open, close)` → `max(open, close)`, filled green when `close >= open`, red otherwise
- Wick: vertical line from `low` → `high`, same color as body

**PriceMACard**

`LineChart` with 4 `Line` series: `close` (gray, thicker) + `ma5` (orange) + `ma20` (blue) + `ma60` (purple). Tooltip shows all 4 values for the hovered date.

**VolumeCard**

`BarChart` of `volume`. Per-bar fill green when `change_pct >= 0`, red when `change_pct < 0`, neutral grey when `change_pct == null` (first row).

**RSICard**

`LineChart` of `rsi14`. Two `ReferenceLine`s: y=70 (light red) and y=30 (light green). Y axis fixed to 0–100.

**MACDCard**

`ComposedChart`:
- Bar series: `macd_histogram` (green when > 0, red when < 0)
- Line: `macd` (blue)
- Line: `macd_signal` (orange)

Y axis auto, with a ReferenceLine at y=0.

### Range selector

Header right side: 5 buttons (1M / 3M / 6M / 1Y / 3Y). Active range gets `variant="default"`, others `variant="outline"`. Clicking calls `setSearchParams({ range })`.

## File layout

```
src/
  hooks/useStockHistory.ts       NEW
  lib/flatten-history.ts         NEW
  cards/stock-charts.tsx         NEW (5 cards + shared chart shells)
  cards/index.ts                 MODIFY: import './stock-charts'
  pages/StockDetailPage.tsx      MODIFY: full implementation
tests/
  flatten-history.test.ts        NEW
  useStockHistory.test.tsx       NEW
  StockDetailPage.test.tsx       NEW
  stock-charts.test.tsx          NEW (3 representative cards)
```

## Testing strategy

- **flatten-history**: pure function. 1 test for shape; 1 for change_pct computation; 1 for null-padding (first row's change_pct should be null).
- **useStockHistory**: msw handler with example payload; verify queryKey includes ticker + range so changing range refetches.
- **StockDetailPage**:
  - Header shows `{ticker} · {name}`
  - Range buttons render; clicking updates `?range=` and triggers a refetch
- **Stock cards** (3 representative tests):
  - KLineCard renders N candles for N rows in dates
  - VolumeCard's bar fill changes based on change_pct sign
  - RSICard renders 70/30 reference lines

Total: ~10 tests across 4 files.

## Risks / open items

- recharts adds ~80KB gzip; bundle goes from 389KB → ~470KB JS, ~160KB gzip. Within budget.
- Custom candlestick shape requires manual scale math. Reference patterns exist (recharts/issues/3324) — but expect a 1–2 hour debug round on the first render. If the Customized approach is unstable, fall back to plain SVG candles in a wrapping `<svg>` instead of integrating with recharts axes.
- `useStockHistory` hook reads `useParams` + `useSearchParams`. In tests this requires wrapping with `MemoryRouter` and a `Routes` rendering the page at the matching path — boilerplate that's already used in `tests/router.test.tsx`.
- Stock page is currently a placeholder; once FE-C1 ships, refreshing on `/tools/stock/2330.TW?range=1Y` must hit the SPA 404 fallback (already configured in deploy workflow).
