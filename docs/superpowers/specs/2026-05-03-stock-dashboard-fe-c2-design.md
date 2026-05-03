# Stock Dashboard FE-C2 — Per-Stock Fundamental Cards

**Date:** 2026-05-03
**Status:** spec
**Phase:** 5 sub-phase 6 (after FE-C1 stock charts)

## Goal

Add 7 fundamental cards to the per-stock detail page: chip, valuation, monthly revenue, three financial statements (income / balance / cashflow), and dividend history. After FE-C2 the per-stock detail page is feature-complete; FE-D removes the legacy `stock.html`.

## Non-Goals

- Top-5 broker rank: backend endpoint is permanently disabled (FinMind sponsor-only); skip the card.
- Per-card customization picker on the stock page (registry already supports it; UI deferred).
- Backend changes — every endpoint already exists.

## Architecture

Each card has its own query hook (no shared cache key like history). All register `defaultPage: 'stock'`, `cols: 3`. Tests assert card registration + key title text only — chart internals stay jsdom-fragile, verified visually in deploy smoke.

```
src/hooks/
  useChip.ts             /api/stocks/{ticker}/chip?days=20
  useValuation.ts        /api/stocks/{ticker}/valuation?years=5
  useRevenue.ts          /api/stocks/{ticker}/revenue?months=36
  useFinancial.ts        /api/stocks/{ticker}/financial?statement=...&quarters=12
  useDividend.ts         /api/stocks/{ticker}/dividend?years=10

src/cards/
  stock-chip.tsx         ChipCard
  stock-valuation.tsx    ValuationCard
  stock-revenue.tsx      RevenueCard
  stock-financial.tsx    IncomeStatementCard, BalanceSheetCard, CashFlowCard (one file, share table component)
  stock-dividend.tsx     DividendCard
  index.ts               import the new files
```

### Per-card render summary

| Card | Render |
|---|---|
| ChipCard | ComposedChart: 3 lines (foreign_net / trust_net / dealer_net, ±values) + 2 lines (margin_balance / short_balance on right axis), legend, ReferenceLine y=0 |
| ValuationCard | 3 number stats (latest PER / PBR / yield), each with a `5y 百分位 X%` badge; below: small LineChart showing 5y trend of PER (or whichever the user clicks — for FE-C2 just PER trend) |
| RevenueCard | ComposedChart: revenue Bar + YoY % Line on right axis; 12MA Line if present |
| IncomeStatementCard / BalanceSheetCard / CashFlowCard | Shared `FinancialTable` component: shadcn Table with N quarter columns + row per metric (revenue / gross / op income / net income / eps for income; assets / liabilities / equity for balance; etc). For income: also show the `annual_summary` block (current 4Q vs previous 4Q EPS + revenue + YoY %) as a header strip |
| DividendCard | ComposedChart: cash dividend Bar + stock dividend Bar (stacked) + payout ratio Line |

### Hook pattern (same shape for all 5 hooks)

```typescript
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export function useChip(days = 20) {
  const { code = '' } = useParams<{ code: string }>();
  return useQuery({
    queryKey: ['stock-chip', code, days],
    queryFn: () => apiFetch(`/api/stocks/${encodeURIComponent(code)}/chip?days=${days}`),
    enabled: !!code,
  });
}
```

`useFinancial(statement)` keys on statement so income / balance / cashflow each get their own query.

## Tests

7 tests minimum (registration + title for each new card) plus 1 hook test for `useFinancial(statement)` to confirm the query key is statement-scoped. Total ~10 tests.

## Risks / open items

- Bundle: only data hooks, no new chart lib. Recharts already loaded in FE-C1; new cards reuse it. Bundle should grow ~10–20KB.
- Some endpoints return `{ ok: false, rows: [] }` when the upstream fetcher fails — every card should render a "尚無資料" placeholder gracefully.
- `valuation` returns an `entries` time series; `quartile_percent` for percentile. Need to handle nulls (some Taiwan stocks have no PBR).
- `dividend` returns yearly aggregates; payout ratio can be > 100% in lean years; line just plots the value.
