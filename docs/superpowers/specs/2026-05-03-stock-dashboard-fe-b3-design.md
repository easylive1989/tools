# Stock Dashboard FE-B3 — Alerts CRUD

**Date:** 2026-05-03
**Status:** spec
**Phase:** 5 sub-phase 4 (after FE-B2 news + watchlist)

## Goal

Migrate the legacy dashboard's price alert section to React. Keep it as a dashboard card (`AlertsCard`, `cols: 3`), but move the create form into a shadcn Dialog. List rows expose toggle (PATCH) and delete (DELETE) actions. Condition options in the form are driven by the `/api/indicators/spec` endpoint so users only see conditions actually supported for the selected indicator.

After FE-B3 the dashboard is feature-complete in React. Only the per-stock detail page remains on the legacy `stock.html` (FE-C).

## Non-Goals

- Edit existing alerts — alerts are create + toggle + delete only (matches legacy behavior).
- Bulk operations.
- Alert history / triggered log beyond the inline `triggered_at + triggered_value` pair already on each row.
- Backend changes — `/api/alerts` GET/POST/DELETE/PATCH and `/api/indicators/spec` already exist.

## Architecture

### Card layout

```
┌──────────────────────────────────────────────────────────────┐
│ 價格警示                              [+ 新增警示]            │
│ 觸發後自動停用，可手動重新啟用                                │
│                                                              │
│ ──────────────────────────────────────────────────────────   │
│ {target} {condition} {threshold}    [監控中]                 │
│ 建立於 2026-04-15 · 已於 2026-05-01 觸發 (18234.56)          │
│                                              [停用]  [✕]     │
│ ──────────────────────────────────────────────────────────   │
│ ...                                                          │
└──────────────────────────────────────────────────────────────┘
```

When the list is empty, render `尚未設定任何警示` muted text.

### Create dialog

shadcn Dialog. Form fields, top to bottom:

1. **target_type** select — `指標 / 股票 / 個股指標`
2. **target** select — depends on target_type:
   - `indicator` → 13 fixed options (the 12 dashboard indicators + `ndc`); labels from `INDICATOR_LABELS`
   - `stock` or `stock_indicator` → watchlist tickers (`useWatchlist().data`); empty list shows placeholder option `（請先在自選股新增）`
3. **indicator_key** select — only when `target_type === 'stock_indicator'`; 16 options from `STOCK_INDICATOR_LABELS`
4. **condition** select — 8 options filtered by the selected indicator's `supported_conditions` from `useIndicatorsSpec`
5. **window_n** input (number, 2..30) — only when `condition.startsWith('streak_')`; default 5
6. **threshold** input (number) — placeholder changes:
   - `percentile_*` → `百分位 0–100`
   - `yoy_*` → `YoY %（可正可負）`
   - else → `門檻數值`
7. Footer: `[取消]` `[建立]` buttons

Form-level error message line above the buttons displays backend 400 messages; dialog stays open.

### Hooks

```typescript
// src/hooks/useAlerts.ts
export interface AlertRecord {
  id: number;
  target_type: 'indicator' | 'stock' | 'stock_indicator';
  target: string;
  indicator_key: string | null;
  condition: string;
  threshold: number;
  window_n: number | null;
  enabled: 0 | 1 | boolean;
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

export function useAlerts();           // useQuery /api/alerts
export function useCreateAlert();      // POST → invalidate ['alerts']
export function useDeleteAlert();      // DELETE → invalidate
export function useToggleAlert();      // PATCH { enabled } → invalidate
```

```typescript
// src/hooks/useIndicatorsSpec.ts
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
export function useIndicatorsSpec();   // useQuery, staleTime: Infinity
```

### Label helpers

```typescript
// src/lib/alert-labels.ts
export const INDICATOR_LABELS: Record<string, string>;
export const STOCK_INDICATOR_LABELS: Record<string, string>;

export function alertTargetLabel(a: AlertRecord): string;
export function conditionLabel(a: AlertRecord): string;
export function thresholdPlaceholder(condition: string): string;
```

`alertTargetLabel`:
- `indicator` → `INDICATOR_LABELS[a.target] ?? a.target`
- `stock_indicator` → `${a.target} ${STOCK_INDICATOR_LABELS[a.indicator_key]}`
- `stock` → `a.target`

`conditionLabel`:
- `above` → `≥`
- `below` → `≤`
- `streak_above` → `連 ${a.window_n} 日 ≥`
- `streak_below` → `連 ${a.window_n} 日 ≤`
- `percentile_above` → `5y 百分位 ≥`
- `percentile_below` → `5y 百分位 ≤`
- `yoy_above` → `YoY ≥`
- `yoy_below` → `YoY ≤`

### shadcn Select

Adds `@radix-ui/react-select` dep + the standard shadcn `Select`, `SelectContent`, `SelectItem`, `SelectTrigger`, `SelectValue` exports. Used for all four selects in the dialog.

## File layout

```
src/
  cards/
    AlertsCard.tsx              NEW (cols=3)
    index.ts                    MODIFY: import './AlertsCard';
  components/
    AlertCreateDialog.tsx       NEW
    ui/select.tsx               NEW (shadcn)
  hooks/
    useAlerts.ts                NEW
    useIndicatorsSpec.ts        NEW
  lib/
    alert-labels.ts             NEW
tests/
  alert-labels.test.ts          NEW
  useAlerts.test.tsx            NEW
  AlertsCard.test.tsx           NEW
  AlertCreateDialog.test.tsx    NEW
```

## Testing strategy

- **alert-labels**: pure functions; 4 representative cases for `alertTargetLabel`, full table for `conditionLabel`, all branches for `thresholdPlaceholder`.
- **useAlerts**: msw-backed mutation tests — create + toggle + delete each invalidate the query (refetch counter goes from 1 → 2 after mutation).
- **AlertsCard read**: empty list shows placeholder; non-empty shows correct label/condition/threshold/status; toggle button label flips with enabled state; delete button is present.
- **AlertsCard mutations**: clicking 停用 calls PATCH; clicking ✕ calls DELETE; both invalidate.
- **AlertCreateDialog**:
  - target_type=indicator → target select shows indicator options; indicator_key select hidden
  - target_type=stock_indicator → indicator_key visible; target options come from watchlist
  - condition options filter by selected indicator's `supported_conditions`
  - condition=streak_above → window_n input visible; otherwise hidden
  - threshold placeholder reflects condition family
  - Create button calls POST with payload; success closes dialog and clears form
  - Backend 400 → error line shown, dialog stays open

Total ~18 new tests across 4 files.

## Risks / open items

- shadcn Select adds `@radix-ui/react-select` (~10KB minified). Bundle should stay under 360KB JS.
- The form has 4 cascading selects + 2 conditional inputs — biggest single component in the FE so far. Decompose into small subcomponents (TargetTypeSelect, TargetSelect, IndicatorKeySelect, ConditionSelect, WindowNInput, ThresholdInput) to keep individual files under ~80 lines.
- `useIndicatorsSpec` should set `staleTime: Infinity` since the spec is build-time static; otherwise the dialog will refetch on every open.
- Existing `INDICATOR_LABELS` is duplicated (the legacy HTML had its own copy + `dashboard-cards.tsx` has labels in the configs). Don't try to deduplicate in this phase — the dashboard-cards configs use camel labels (e.g. `恐懼貪婪指數`) that match what users see, but the alert label table also includes `ndc` and stripped variants. Keep them separate; merge only if a future card needs it.
