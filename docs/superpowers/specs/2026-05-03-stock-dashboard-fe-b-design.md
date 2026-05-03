# Stock Dashboard FE-B — Migrate Dashboard Indicator Cards to React

**Date:** 2026-05-03
**Status:** spec
**Phase:** 5 sub-phase 2 (after FE-A scaffold)

## Goal

Replace the legacy vanilla `index.html` dashboard's 12 indicator cards with React cards registered through the FE-A registry pattern, sharing one `/api/dashboard` query, and add a card visibility picker (header gear → modal with checkboxes, persisted to `localStorage`).

After FE-B: legacy dashboard cards are gone; users can hide/show any of the 12 cards. The 4 functional sections (news / watchlist / alerts / history chart) and the per-stock detail page remain on the legacy `stock.html` until FE-B2 / FE-C.

## Non-Goals

- News list, watchlist CRUD, alert CRUD, history chart — pushed to FE-B2 (or rolled into FE-C).
- Per-card manual refresh button — pushed to FE-B2 if needed.
- Time range selector and per-card history expand — pushed to FE-B2 / FE-C.
- Card customization persisted to backend — `localStorage` is sufficient for one user per device.
- Backend changes — FE-B uses the existing `/api/dashboard` endpoint as-is.

## Architecture

Three units, plus a small picker UI:

### 1. Shared dashboard query

```
src/hooks/useDashboardData.ts
```

Single `useQuery({ queryKey: ['dashboard'], queryFn: () => apiFetch('/api/dashboard') })`. All 12 cards subscribe to it; TanStack Query dedupes the network call. Returns `Record<string, { value: number; timestamp: string; extra: Record<string, unknown> }>` keyed by indicator key (matches backend `INDICATOR_NAMES`).

### 2. Shared card view + per-indicator config

```
src/components/IndicatorCardView.tsx
src/cards/dashboard-cards.tsx       (config + registerCard for all 12)
```

`IndicatorCardView` is a presentational shadcn `Card` with: title, optional badge (top-right), main value, sub line. No data-fetching logic.

`dashboard-cards.tsx` defines a `IndicatorConfig` array and registers one card per entry:

```typescript
interface IndicatorConfig {
  key: string;
  label: string;
  formatValue: (v: number, extra: Record<string, unknown>) => string;
  formatSub:   (extra: Record<string, unknown>, ts: string) => string;
  formatBadge?: (extra: Record<string, unknown>, value: number) =>
    { text: string; tone: 'up' | 'down' | 'neutral' } | null;
  valueClass?: (v: number, extra: Record<string, unknown>) => string;
}
```

Each config produces a tiny inline component:

```typescript
function makeCard(cfg: IndicatorConfig): FC {
  return function IndicatorCard() {
    const { data, isLoading, isError } = useDashboardData();
    const slot = data?.[cfg.key];
    return (
      <IndicatorCardView
        title={cfg.label}
        loading={isLoading}
        error={isError || (data && !slot) ? '無法載入' : undefined}
        value={slot && cfg.formatValue(slot.value, slot.extra)}
        valueClass={slot && cfg.valueClass?.(slot.value, slot.extra)}
        sub={slot && cfg.formatSub(slot.extra, slot.timestamp)}
        badge={slot && cfg.formatBadge?.(slot.extra, slot.value) || null}
      />
    );
  };
}

CONFIGS.forEach(cfg => registerCard({
  id: cfg.key, label: cfg.label, defaultPage: 'dashboard',
  component: makeCard(cfg),
}));
```

Adding/removing indicators is one config entry — no new `.tsx` file.

### 3. Card visibility store

```
src/store/card-prefs-store.ts
```

Zustand store backed by `localStorage` key `sd_card_prefs`:

```typescript
interface CardPrefsStore {
  hiddenIds: Set<string>;
  toggle: (id: string) => void;
  isHidden: (id: string) => boolean;
}
```

Persists `Array.from(hiddenIds)` (Sets don't JSON-serialize). Hydrate on store init.

### 4. Picker UI

```
src/components/DashboardSettingsDialog.tsx
src/components/ui/checkbox.tsx        (shadcn add)
```

shadcn Dialog triggered by a gear icon button in the DashboardPage header. Lists every card from `listCards('dashboard')` with a Checkbox bound to `card-prefs-store`. Toggle is immediate; no Save/Cancel buttons.

### Page wiring

`DashboardPage` filters with the prefs store:

```tsx
const cards = listCards('dashboard');
const isHidden = useCardPrefsStore(s => s.isHidden);
const visible = cards.filter(c => !isHidden(c.id));
```

Header layout: title on the left, gear button + Dialog on the right.

## Indicator config table

| key                 | label              | main value                                                       | sub line                                  | badge                                        | value color |
|---------------------|--------------------|------------------------------------------------------------------|-------------------------------------------|----------------------------------------------|-------------|
| taiex               | 加權指數           | `value.toLocaleString()`                                          | `前收 {prev_close} · 更新 {date}`         | `change_pct` ▲▼ % (up/down)                  | —           |
| fx                  | 台幣兌美金         | `value.toFixed(2)`                                                | `前收 {prev_close} · 更新 {date}`         | `change_pct` ▲▼ %                            | —           |
| tw_volume           | 台股成交金額       | `value.toLocaleString() + ' 億'`                                  | `前日 {prev_value} 億 · 更新 {date}`      | `change_pct` ▲▼ %                            | —           |
| us_volume           | 美股 S&P500 成交量 | `value.toLocaleString() + ' 億股'`                                | `前日 {prev_value} 億股 · 更新 {date}`    | `change_pct` ▲▼ %                            | —           |
| fear_greed          | 恐懼貪婪指數       | `String(value)`                                                   | `更新 {date}`                              | `extra.label` (Fear/Neutral/Greed)          | <45 down, >55 up |
| ndc                 | 國發會景氣指標     | `value + ' 分'`                                                   | `{period} · 每月更新`                      | `extra.light` (e.g. 綠燈)                    | —           |
| margin_balance      | 融資餘額           | `value.toFixed(0) + ' 億'`                                        | `更新 {date}`                              | —                                            | —           |
| short_balance       | 融券餘額           | `(value/1000).toFixed(0) + ' 千張'`                               | `更新 {date}`                              | —                                            | —           |
| short_margin_ratio  | 券資比             | `value.toFixed(2) + ' %'`                                         | `更新 {date}`                              | —                                            | —           |
| total_foreign_net   | 外資淨買超         | `(value≥0?'+':'') + value.toFixed(2) + ' 億'`                     | `更新 {date}`                              | —                                            | up/down by sign |
| total_trust_net     | 投信淨買超         | 同上                                                               | `更新 {date}`                              | —                                            | up/down by sign |
| total_dealer_net    | 自營商淨買超       | 同上                                                               | `更新 {date}`                              | —                                            | up/down by sign |

**Dropped from legacy:** fear_greed slider/marker visualization; ndc 5-light traffic visualization. Keep the textual badge.

## FE-A TaiexCard cleanup

The TaiexCard from FE-A calls `/api/indicators/taiex` (which doesn't exist) and is currently broken on the live site. FE-B refactors it to use the shared dashboard query — same pattern as the other 11 cards. Concretely: delete `src/cards/TaiexCard.tsx`, remove its import from `src/cards/index.ts`, and let `dashboard-cards.tsx` register the `taiex` config like any other indicator. The legacy `tests/TaiexCard.test.tsx` is replaced by representative tests in `tests/dashboard-cards.test.tsx`.

## Testing strategy

- **`useDashboardData`**: msw handler returns the 12-key dict; verify cache shared across two consumer components (one fetch).
- **Formatters**: pure functions, unit-test 3 representative configs (taiex with badge, foreign_net with sign coloring, ndc with extra.period).
- **`IndicatorCardView`**: snapshot for value+badge+sub layout; loading/error states.
- **`card-prefs-store`**: toggle persists to localStorage; rehydrate on store init.
- **Dialog**: opens, lists 12 cards, toggling a checkbox re-renders DashboardPage without that card.
- **DashboardPage integration**: 12 cards render; toggle one off via store; verify it disappears.

Total ~10 new test files, ~25 new tests.

## File layout

```
src/
  hooks/
    useDashboardData.ts          NEW
  components/
    IndicatorCardView.tsx        NEW
    DashboardSettingsDialog.tsx  NEW
    ui/checkbox.tsx              NEW (shadcn)
  cards/
    dashboard-cards.tsx          NEW (12 configs + registerCard ×12)
    index.ts                     MODIFY: import './dashboard-cards'; remove TaiexCard import
    TaiexCard.tsx                DELETE
  store/
    card-prefs-store.ts          NEW
  pages/
    DashboardPage.tsx            MODIFY: filter by prefs + add SettingsDialog
tests/
  useDashboardData.test.tsx      NEW
  dashboard-cards.test.tsx       NEW (representative cards + formatters)
  IndicatorCardView.test.tsx     NEW
  card-prefs-store.test.ts       NEW
  DashboardSettingsDialog.test.tsx NEW
  DashboardPage.test.tsx         NEW (integration)
  TaiexCard.test.tsx             DELETE
```

## Risk / open items

- shadcn `checkbox` requires `@radix-ui/react-checkbox` — small new dep.
- Set serialization for Zustand persistence: handle manually (toJSON/fromJSON), not via `persist` middleware (we keep deps minimal).
- Live site verification: after deploy, dashboard at `paul-learning.dev/tools/stock/` should show 12 cards from real backend data.
