# Stock Dashboard REG-: Alert Indicator Registry Design Spec

**Date**: 2026-05-02
**Phase**: REG- (Phase 3, scope-narrowed from original CONVENTIONS.md)
**Parent spec**: `docs/superpowers/specs/2026-05-02-stock-dashboard-conventions-design.md` §2.3, §7 Phase 3
**Predecessors**: MIGR / BE-A / BE-B / BE-C (full layered backend now in place)
**Scope**:
- Add `services/alert_registry.py` with `IndicatorSpec` + register/lookup APIs
- Add `services/indicators/` package: 7 grouped files registering 26 indicator entries
- Replace `alert_engine.py`'s big switch with registry dispatch (`_resolve_value` + `_compare`)
- Replace `routes/alerts.py`'s hardcoded validation constants with `spec.supports(condition)`
- Add `GET /api/indicators/spec` endpoint (frontend will consume in Phase 5)
- Amendment: `CONVENTIONS.md` §2.2 Fetcher Protocol descoped (rationale below)

## Goals

1. Make adding a new alert-able indicator a **one-file change**: add a `register_indicator(...)` call in the appropriate `services/indicators/<group>.py` file. No changes to alert engine, routes, or frontend hardcoded lists.
2. Eliminate the giant `(target_type, condition, indicator_key)` switch in `check_alerts`. Each indicator's value-fetching logic lives next to its declaration.
3. Preserve every existing alert behaviour byte-for-byte: the existing ~42 alert tests must all pass after the refactor.
4. Provide a discoverable surface for the frontend: `GET /api/indicators/spec` returns the registry as JSON.

## Non-Goals

- Do not introduce a `Fetcher` Protocol or `Snapshot` dataclass. The original CONVENTIONS.md §2.2 idea doesn't fit the codebase reality; see "Amendment" below.
- Do not refactor any fetcher (`fetchers/*` unchanged).
- Do not change repositories, db, core, main.py, or other routes.
- Do not modify the frontend (HTML stays as-is until Phase 5).
- Do not register the `stock` target_type. `target_type="stock"` (raw price) bypasses the registry; the alert engine handles it directly with the passed `value` argument.
- Do not adopt `RepositoryError` / `FetcherError` raise sites in this phase.

## Amendment to CONVENTIONS.md §2.2 (Fetcher Protocol)

Original CONVENTIONS.md (committed 2026-05-02 earlier today) declared a strict `Fetcher` Protocol:

```python
class Fetcher(Protocol):
    name: str
    def fetch(self, **kwargs) -> list[Snapshot]: ...
```

After implementation context reveals that this Protocol does not fit the codebase:

- 9 fetchers have widely different shapes: numeric snapshots (taiex, fx), multi-column daily rows (chip_stock 8 columns), text articles (news), OHLC time-series (stock_history), multi-stock orchestrators (fetch_all_stocks).
- "Fetchers do not write to DB" requires moving all DB writes into scheduler-orchestrated callers — a substantial cross-cutting change with limited concrete payoff.
- The high-value goal of the original spec (one-file changes for new alert-able indicators) is fully achievable through the alert registry alone.

**Resolution**: REG- delivers the alert registry. Fetcher Protocol becomes a future-improvements item; in the interim, `CONVENTIONS.md §2.2` is updated to a "Fetcher Conventions" section describing naming, retry, error wrapping, and where DB writes happen (orchestrator-side preferred but not enforced). Strict Protocol/Snapshot is deferred to a hypothetical later phase only if pain emerges.

This is a deliberate scope reduction documented in `CONVENTIONS.md` itself (REG-T13 step).

---

## 1. Target File Structure

```
backend/
├── services/
│   ├── alert_engine.py             ← MODIFIED: ~404 → ~120 lines (dispatch via registry)
│   ├── alert_notifier.py           ← unchanged
│   ├── alert_registry.py           ← NEW: IndicatorSpec + 2 registries + APIs
│   ├── backfill.py                 ← unchanged
│   └── indicators/                 ← NEW package
│       ├── __init__.py             ← imports all sub-modules (auto-register)
│       ├── _helpers.py             ← shared: percentile_rank, fetch_indicator_history
│       ├── macro.py                ← taiex, fx, fear_greed, ndc (4 entries)
│       ├── chip_total.py           ← margin_balance, short_balance, short_margin_ratio,
│       │                             total_{foreign,trust,dealer}_net (6 entries)
│       ├── stock_per.py            ← per, pbr, dividend_yield (3 entries)
│       ├── stock_chip.py           ← foreign_net, trust_net, dealer_net,
│       │                             margin_balance (stock), short_balance (stock) (5)
│       ├── stock_revenue.py        ← revenue (1, yoy-only)
│       ├── stock_quarterly.py      ← q_eps, q_revenue, q_operating_income,
│       │                             q_net_income, q_operating_cf (5)
│       └── stock_yearly.py         ← y_cash_dividend, y_stock_dividend (2)
│
├── api/routes/
│   ├── alerts.py                   ← MODIFIED: hardcoded STOCK_*_KEYS removed,
│   │                                  validation reads spec.supports(condition)
│   └── indicators.py               ← MODIFIED: add GET /api/indicators/spec endpoint
│
├── docs/
│   └── ...                         ← CONVENTIONS.md amendment in REG-T13
│
└── tests/
    ├── unit/
    │   └── test_alert_registry.py  ← NEW: registry semantics, conflict handling
    └── test_alerts.py              ← unchanged (~42 tests verify behaviour preserved)
```

---

## 2. `services/alert_registry.py`

```python
"""Alert indicator registry.

Each indicator declares its capabilities (which conditions it supports) and
exposes value providers. The alert engine dispatches by looking up
(target_type, indicator_key) → IndicatorSpec.
"""
from dataclasses import dataclass
from typing import Callable


@dataclass
class IndicatorSpec:
    key: str
    label: str
    unit: str
    target_type: str  # "indicator" | "stock_indicator"
    supported_conditions: set[str]

    get_latest_value: Callable[[str], float | None]
    get_history: Callable[[str, int], list[float]] | None = None
    get_percentile: Callable[[str], float | None] | None = None
    get_yoy: Callable[[str], float | None] | None = None

    def supports(self, condition: str) -> bool:
        return condition in self.supported_conditions


_INDICATOR_REGISTRY: dict[str, IndicatorSpec] = {}
_STOCK_INDICATOR_REGISTRY: dict[str, IndicatorSpec] = {}


def register_indicator(spec: IndicatorSpec) -> None:
    if spec.target_type == "indicator":
        _INDICATOR_REGISTRY[spec.key] = spec
    elif spec.target_type == "stock_indicator":
        _STOCK_INDICATOR_REGISTRY[spec.key] = spec
    else:
        raise ValueError(f"Unsupported target_type: {spec.target_type}")


def get_indicator(target_type: str, key: str) -> IndicatorSpec | None:
    if target_type == "indicator":
        return _INDICATOR_REGISTRY.get(key)
    if target_type == "stock_indicator":
        return _STOCK_INDICATOR_REGISTRY.get(key)
    return None


def list_indicators(target_type: str) -> list[IndicatorSpec]:
    if target_type == "indicator":
        return sorted(_INDICATOR_REGISTRY.values(), key=lambda s: s.key)
    if target_type == "stock_indicator":
        return sorted(_STOCK_INDICATOR_REGISTRY.values(), key=lambda s: s.key)
    return []


def all_indicators() -> dict[str, list[IndicatorSpec]]:
    return {
        "indicator": list_indicators("indicator"),
        "stock_indicator": list_indicators("stock_indicator"),
    }
```

Design notes:
- **Two registries** disambiguate name collisions (e.g. indicator-level `margin_balance` from `chip_total` vs stock-level `margin_balance` from `chip_stock`).
- **Optional `get_*` callables**: each spec only fills the providers relevant to its `supported_conditions`. Engine checks for `None` before calling.
- **No `evaluate()` method on the spec**: condition dispatch lives in the engine (DRY across indicators); each indicator only has to declare its 0–4 value providers.

---

## 3. `services/indicators/__init__.py`

```python
"""Auto-registration: importing this package triggers all register_indicator calls."""
from . import macro              # noqa: F401
from . import chip_total         # noqa: F401
from . import stock_per          # noqa: F401
from . import stock_chip         # noqa: F401
from . import stock_revenue      # noqa: F401
from . import stock_quarterly    # noqa: F401
from . import stock_yearly       # noqa: F401
```

`alert_engine.check_alerts` lazy-imports this at first invocation so the registry is fully populated before any lookup.

---

## 4. `services/indicators/_helpers.py`

```python
"""Common helpers shared across indicator modules."""
from datetime import datetime, timedelta, timezone


def percentile_rank(latest: float | None, history: list[float], min_n: int = 30) -> float | None:
    """Inclusive percentile rank: count(v <= latest) / total * 100.

    Returns None if `latest` is None or there are fewer than `min_n` clean samples.
    """
    if latest is None or len(history) < min_n:
        return None
    clean = [v for v in history if v is not None]
    if len(clean) < min_n:
        return None
    below = sum(1 for v in clean if v <= latest)
    return round(below / len(clean) * 100, 2)


def fetch_indicator_history(indicator: str, n: int) -> list[float]:
    """Get latest n values of a top-level indicator (oldest→newest)."""
    from repositories.indicators import get_indicator_history
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(n * 3, 30))
    rows = get_indicator_history(indicator, since)
    values = [r["value"] for r in rows if r["value"] is not None]
    return values[-n:]
```

---

## 5. Indicator Module Examples

### `services/indicators/macro.py`

```python
"""Indicator-level macro signals: TAIEX, FX, Fear & Greed, NDC."""
from repositories.indicators import get_latest_indicator
from services.alert_registry import IndicatorSpec, register_indicator
from services.indicators._helpers import fetch_indicator_history


def _make_macro_spec(key: str, label: str, unit: str) -> IndicatorSpec:
    return IndicatorSpec(
        key=key,
        label=label,
        unit=unit,
        target_type="indicator",
        supported_conditions={"above", "below", "streak_above", "streak_below"},
        get_latest_value=lambda _t, k=key: (
            (row := get_latest_indicator(k)) and row["value"]
        ),
        get_history=lambda _t, n, k=key: fetch_indicator_history(k, n),
    )


for key, label, unit in (
    ("taiex",      "加權指數",      "點"),
    ("fx",         "台幣兌美金",   "TWD"),
    ("fear_greed", "恐懼與貪婪指數", ""),
    ("ndc",        "國發會景氣指標", "分"),
):
    register_indicator(_make_macro_spec(key, label, unit))
```

`get_latest_value` accepts an unused `target` parameter (lookup is by indicator key, target is the same as key for `target_type="indicator"`).

### `services/indicators/stock_per.py`

```python
"""PER / PBR / Dividend Yield (stock daily)."""
from datetime import datetime, timedelta, timezone

from repositories.fundamentals import get_per_daily_range
from services.alert_registry import IndicatorSpec, register_indicator
from services.indicators._helpers import percentile_rank


def _get_history(ticker: str, n: int, *, field: str) -> list[float]:
    since_date = (datetime.now(timezone.utc).date() - timedelta(days=max(n * 3 + 30, 60))).isoformat()
    rows = get_per_daily_range(ticker, since_date)
    values = [r[field] for r in rows if r[field] is not None]
    return values[-n:]


def _get_latest(ticker: str, *, field: str) -> float | None:
    history = _get_history(ticker, 1, field=field)
    return history[-1] if history else None


def _get_percentile(ticker: str, *, field: str) -> float | None:
    history = _get_history(ticker, 1825, field=field)
    if not history:
        return None
    return percentile_rank(history[-1], history)


_DAILY_CONDS = {
    "above", "below", "streak_above", "streak_below",
    "percentile_above", "percentile_below",
}


for key, label, unit in (
    ("per",            "PER",   ""),
    ("pbr",            "PBR",   ""),
    ("dividend_yield", "殖利率", "%"),
):
    register_indicator(IndicatorSpec(
        key=key,
        label=label,
        unit=unit,
        target_type="stock_indicator",
        supported_conditions=_DAILY_CONDS,
        get_latest_value=lambda t, f=key: _get_latest(t, field=f),
        get_history=lambda t, n, f=key: _get_history(t, n, field=f),
        get_percentile=lambda t, f=key: _get_percentile(t, field=f),
    ))
```

### `services/indicators/stock_revenue.py`

```python
"""Stock monthly revenue (yoy-only)."""
from repositories.fundamentals import (
    get_latest_revenue_ym, get_revenue_monthly_range,
)
from services.alert_registry import IndicatorSpec, register_indicator


def _get_revenue_yoy(ticker: str) -> float | None:
    latest = get_latest_revenue_ym(ticker)
    if not latest:
        return None
    y, m = latest
    rows = get_revenue_monthly_range(ticker, y - 1, m)
    by_ym = {(r["year"], r["month"]): r["revenue"] for r in rows}
    cur = by_ym.get((y, m))
    prev = by_ym.get((y - 1, m))
    if cur is None or not prev:
        return None
    return round((cur - prev) / prev * 100, 2)


register_indicator(IndicatorSpec(
    key="revenue",
    label="月營收",
    unit="%",
    target_type="stock_indicator",
    supported_conditions={"yoy_above", "yoy_below"},
    get_latest_value=lambda _t: None,  # not directly used; only yoy-mode supported
    get_yoy=_get_revenue_yoy,
))
```

The other indicator modules (`chip_total.py`, `stock_chip.py`, `stock_quarterly.py`, `stock_yearly.py`) follow the same pattern and reuse the existing logic from `alert_engine.py` (helpers like `_get_stock_quarterly_yoy` / `_get_stock_yearly_yoy` move into their respective indicator files).

---

## 6. `alert_engine.py` After REG-T10

Estimated final shape (~120 lines):

```python
"""Alert evaluation logic — registry-driven dispatch.

Each indicator's value-fetching lives in services/indicators/<group>.py.
This module just wires conditions to the right provider.
"""
import logging

from services.alert_notifier import notify_triggered

logger = logging.getLogger(__name__)


def _format_value(target_type: str, target: str, value: float, spec) -> str:
    """Display formatting for the alert payload."""
    if target_type == "indicator" and spec is not None:
        unit = spec.unit
        if target == "fx":
            return f"{value:.4f} {unit}".strip()
        return f"{value:,.2f} {unit}".strip()
    return f"{value:,.4f}" if value < 100 else f"{value:,.2f}"


def _alert_display_name(target_type: str, target: str, indicator_key: str | None, spec) -> str:
    if spec is not None:
        if target_type == "indicator":
            return spec.label
        if target_type == "stock_indicator":
            return f"{target} {spec.label}"
    return target


def _build_payload(alert: dict, value: float | None, display_name: str, spec) -> dict:
    # ... condition-to-display-text mapping (unchanged from before, just receives spec)
    ...


def _resolve_value(spec, alert, target, value, cond, indicator_key):
    if spec is None:  # target_type == "stock"
        return value
    if cond in ("above", "below"):
        if spec.target_type == "indicator" and value is not None:
            return value
        return spec.get_latest_value(target)
    if cond in ("streak_above", "streak_below"):
        n = alert.get("window_n") or 5
        if spec.get_history is None:
            return None
        history = spec.get_history(target, n)
        return history[-1] if history else None
    if cond in ("percentile_above", "percentile_below"):
        return spec.get_percentile(target) if spec.get_percentile else None
    if cond in ("yoy_above", "yoy_below"):
        return spec.get_yoy(target) if spec.get_yoy else None
    return None


def _compare(value: float, threshold: float, cond: str, window_n: int | None,
             spec, target: str) -> bool:
    if cond in ("above", "percentile_above", "yoy_above"):
        return value >= threshold
    if cond in ("below", "percentile_below", "yoy_below"):
        return value <= threshold
    if cond in ("streak_above", "streak_below"):
        n = window_n or 5
        if spec is None or spec.get_history is None:
            return False
        history = spec.get_history(target, n)
        if not history or any(v is None for v in history) or len(history) < n:
            return False
        if cond == "streak_above":
            return all(v >= threshold for v in history)
        return all(v <= threshold for v in history)
    return False


def check_alerts(target_type: str, target: str, value: float | None = None,
                 *, indicator_key: str | None = None, display_name: str | None = None) -> None:
    from repositories.alerts import get_active_alerts, mark_alert_triggered
    from services.alert_registry import get_indicator
    from services import indicators  # noqa: F401  ← trigger auto-register

    all_active = get_active_alerts(target_type, target)
    if target_type == "stock_indicator":
        active_alerts = [a for a in all_active if a.get("indicator_key") == indicator_key]
    else:
        active_alerts = all_active

    if target_type == "indicator":
        spec = get_indicator("indicator", target)
    elif target_type == "stock_indicator":
        spec = get_indicator("stock_indicator", indicator_key) if indicator_key else None
    else:
        spec = None

    name = display_name or _alert_display_name(target_type, target, indicator_key, spec)

    for alert in active_alerts:
        cond = alert["condition"]
        threshold = alert["threshold"]
        if spec is not None and not spec.supports(cond):
            continue
        cur_value = _resolve_value(spec, alert, target, value, cond, indicator_key)
        if cur_value is None:
            continue
        triggered = _compare(cur_value, threshold, cond, alert.get("window_n"), spec, target)
        if triggered:
            payload = _build_payload(alert, cur_value, name, spec)
            notify_triggered(payload, alert_id=alert["id"])
            mark_alert_triggered(alert["id"], cur_value)
```

**Removed from `alert_engine.py`** in REG-T10:
- `INDICATOR_LABELS` dict (label moves into each spec)
- `INDICATOR_UNITS` dict (unit moves into each spec)
- `STOCK_INDICATOR_LABELS` dict (label in spec)
- `STOCK_INDICATOR_KEYS`, `_PER_KEYS`, `_CHIP_NET_KEYS`, `_CHIP_BAL_KEYS` constants (replaced by registry membership)
- `QUARTERLY_INDICATOR_TYPES`, `YEARLY_INDICATOR_KEYS` (move into respective indicator files)
- `_check_streak()` (folded into `_compare`)
- `_pct_rank()` (moved to `_helpers.percentile_rank`)
- `_get_stock_indicator_history()` (split per indicator file)
- `_get_stock_revenue_yoy()` (moved to `stock_revenue.py`)
- `_get_stock_quarterly_yoy()` (moved to `stock_quarterly.py`)
- `_get_stock_yearly_yoy()` (moved to `stock_yearly.py`)
- `_latest_indicator_history()` (moved to `_helpers.fetch_indicator_history`)

---

## 7. `routes/alerts.py` Validation Refactor

Removed module-level constants (in REG-T11):
- `STOCK_DAILY_INDICATOR_KEYS`
- `STOCK_MONTHLY_INDICATOR_KEYS`
- `STOCK_QUARTERLY_INDICATOR_KEYS`
- `STOCK_YEARLY_INDICATOR_KEYS`
- `STOCK_YOY_COMPATIBLE_KEYS`
- `STOCK_INDICATOR_KEYS`
- `PERCENTILE_DAILY_KEYS`

Kept (top-level state, not indicator-specific):
- `VALID_TARGET_TYPES = {"indicator", "stock", "stock_indicator"}`
- `VALID_CONDITIONS = {"above", "below", "streak_*", "percentile_*", "yoy_*"}`

The `create_alert` body uses `spec.supports(condition)` for cross-validation:

```python
if req.target_type == "indicator":
    spec = get_indicator("indicator", req.target)
    if spec is None:
        raise HTTPException(400, "Unknown indicator")
    if not spec.supports(req.condition):
        raise HTTPException(400, f"indicator {req.target} does not support {req.condition}")
    target = req.target
elif req.target_type == "stock_indicator":
    if not req.indicator_key:
        raise HTTPException(400, "stock_indicator requires indicator_key")
    spec = get_indicator("stock_indicator", req.indicator_key)
    if spec is None:
        raise HTTPException(400, "Unknown indicator_key")
    if fundamentals_to_finmind_id(req.target) is None:
        raise HTTPException(400, "Only Taiwan tickers (.TW/.TWO) supported")
    if not spec.supports(req.condition):
        raise HTTPException(400, f"indicator {req.indicator_key} does not support {req.condition}")
    target = req.target.upper()
else:  # stock
    target = req.target.upper()
```

`alerts.py` shrinks from 105 → ~80 lines.

---

## 8. `GET /api/indicators/spec` Endpoint

In `routes/indicators.py`:

```python
@router.get("/indicators/spec")
def indicators_spec():
    """Return alert-able indicator specs grouped by target_type.

    Frontend (Phase 5) will use this to render alert creation form.
    """
    from services.alert_registry import all_indicators
    from services import indicators  # noqa: F401  ← trigger auto-register

    def _to_dict(spec):
        return {
            "key": spec.key,
            "label": spec.label,
            "unit": spec.unit,
            "supported_conditions": sorted(spec.supported_conditions),
        }

    bundle = all_indicators()
    return {
        "indicator":       [_to_dict(s) for s in bundle["indicator"]],
        "stock_indicator": [_to_dict(s) for s in bundle["stock_indicator"]],
    }
```

Returns a JSON dict with two keys (`indicator`, `stock_indicator`), each a sorted list of spec dicts. Plain-dict response (no Pydantic model) — keeps the schema flexible.

---

## 9. Migration Order (13 tasks)

| # | Task |
|---|---|
| T1 | `services/alert_registry.py` + `services/indicators/__init__.py` (empty for now) + `services/indicators/_helpers.py` |
| T2 | `tests/unit/test_alert_registry.py` covering register/get/list, name collision (same key in both registries), unsupported `target_type` raises |
| T3 | `services/indicators/macro.py`: 4 entries (taiex, fx, fear_greed, ndc); update `__init__.py` to import |
| T4 | `services/indicators/chip_total.py`: 6 entries; update `__init__.py` |
| T5 | `services/indicators/stock_per.py`: 3 entries |
| T6 | `services/indicators/stock_chip.py`: 5 entries |
| T7 | `services/indicators/stock_revenue.py`: 1 entry (yoy-only) |
| T8 | `services/indicators/stock_quarterly.py`: 5 entries |
| T9 | `services/indicators/stock_yearly.py`: 2 entries |
| T10 | Rewrite `alert_engine.check_alerts` to dispatch via registry. Move/delete the helpers consolidated into indicator files or `_helpers.py`. ~404 → ~120 lines. **Critical**: existing 42 alert tests must all pass without modification. |
| T11 | `routes/alerts.py` validation switches to `spec.supports(condition)`; delete `STOCK_*_KEYS` constants. |
| T12 | `routes/indicators.py` adds `GET /api/indicators/spec` + 1 unit test verifying schema (key/label/unit/supported_conditions present, two target_type buckets). |
| T13 | Final verification + amendment: full suite green; `alert_engine.py` ≤ 150 lines; `routes/alerts.py` ≤ 90 lines; spec endpoint returns 26 entries; **CONVENTIONS.md** §2.2 amended with Fetcher Protocol → Conventions note. |

T1-T9: each task adds new files / spec entries but `alert_engine` still has its old switch — behaviour is unchanged.
T10: the critical equivalence-validation step. Engine swaps switch for registry; suite proves behaviour unchanged.
T11: route validation cleanup, no behaviour change.
T12: new endpoint, no existing behaviour change.
T13: read-only verification + docs.

---

## 10. Acceptance Criteria

- `services/indicators/` contains exactly 9 files: `__init__.py`, `_helpers.py`, plus 7 indicator modules (`macro`, `chip_total`, `stock_per`, `stock_chip`, `stock_revenue`, `stock_quarterly`, `stock_yearly`).
- `services/alert_registry.py` exists with `IndicatorSpec`, `register_indicator`, `get_indicator`, `list_indicators`, `all_indicators`.
- 26 indicator entries register: 10 indicator-level (4 macro + 6 chip_total) + 16 stock-level (3 per + 5 chip + 1 revenue + 5 quarterly + 2 yearly).
- `alert_engine.py` ≤ 150 lines (down from 404).
- `routes/alerts.py` ≤ 90 lines (down from 105). No `STOCK_*_KEYS`, `PERCENTILE_DAILY_KEYS` constants remain.
- `GET /api/indicators/spec` returns the registry as JSON; the response includes both `indicator` (10 entries) and `stock_indicator` (16 entries).
- Full test suite: 5 baseline failures (unchanged) + every other test passes + new `test_alert_registry.py` (~5 tests) + new `test_indicators_spec_endpoint` (~1 test). Total ≥ 134 passed.
- `CONVENTIONS.md §2.2` amended with Fetcher Protocol scope adjustment note.

---

## 11. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Lambda closure variable capture (`lambda t: _get_latest(t, field=key)` captures the loop variable) | Use default-arg freezing: `lambda t, f=key: _get_latest(t, field=f)`. Spec examples follow this pattern. |
| Import order: `alert_engine` loads before any indicator is registered | `alert_engine.check_alerts` lazy-imports `from services import indicators  # noqa: F401` at first call, ensuring all `register_indicator()` runs before lookup. |
| Behavioural regression in REG-T10 (engine rewrite) | T10 is the equivalence-validation point. The 42 existing alert tests are the contract; if any fails, debug before commit. |
| Naming collision: indicator-level `margin_balance` vs stock-level `margin_balance` | Two separate registries (`_INDICATOR_REGISTRY` vs `_STOCK_INDICATOR_REGISTRY`) keyed by string; `target_type` selects which dict to consult. |
| `fundamentals_to_finmind_id` (FinMind ticker validator) called from routes/alerts.py — still needed after registry refactor | Yes, kept; ticker shape validation is orthogonal to indicator registration. |
| `revenue` indicator currently appears in `STOCK_INDICATOR_KEYS` (which `STOCK_DAILY_INDICATOR_KEYS | STOCK_YOY_COMPATIBLE_KEYS` includes). After registry refactor, it only supports yoy_*; non-yoy creates should error. | The new `spec.supports(req.condition)` check enforces this; existing tests cover yoy paths. |
| Existing `test_alerts.py` patches `alerts_module.send_to_discord` and `alerts_module.settings`; T10 must not break those references | `alerts_module` is the thin `backend/alerts.py` re-export module (BE-B); engine internals change but the re-export surface stays. |
| `_format_value` and `_build_payload` in old engine consult `INDICATOR_UNITS` directly for `fx`'s 4-decimal display. After refactor unit lookup goes through `spec.unit`. | Engine helpers receive `spec` (or `None` for `stock`). The `fx` 4-decimal special case stays inline (`if target == "fx": return ...`). |

---

## 12. After This Phase

- **Phase 4 (AUTH-)**: tokens. The exception handler from BE-C will map `AuthError` → 401 automatically. Auth has no interaction with the indicator registry.
- **Phase 5 (FE-)**: React frontend will consume `GET /api/indicators/spec` to render the alert creation form dynamically. Adding a new indicator becomes purely a backend change.
- **Future improvement (deferred from CONVENTIONS.md §2.2)**: re-evaluate Fetcher Protocol after the registry has lived for a few months. If "adding a new fetcher" stays painful, formalize the pattern then.
