# Stock Dashboard REG-: Alert Indicator Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `alert_engine.py`'s `(target_type, condition, indicator_key)` switch with registry-driven dispatch. 7 grouped indicator files register 26 entries. Routes/alerts validation reads `spec.supports(condition)` instead of hardcoded `STOCK_*_KEYS` constants. New `GET /api/indicators/spec` endpoint exposes registry to frontend.

**Architecture:** `services/alert_registry.py` exposes `IndicatorSpec` + two namespaced registries (by `target_type`). T3-T9 register 26 indicators in 7 files. T10 atomically swaps `check_alerts` to use registry. T11 cleans up routes validation. T12 adds spec endpoint. T13 verifies + amends `CONVENTIONS.md`.

**Tech Stack:** Python 3.12, FastAPI, pytest. No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-02-stock-dashboard-reg-design.md`.

---

## File Structure

**Created:**
- `stock/dashboard/backend/services/alert_registry.py` — IndicatorSpec + 2 registries + APIs
- `stock/dashboard/backend/services/indicators/__init__.py` — auto-import sub-modules
- `stock/dashboard/backend/services/indicators/_helpers.py` — percentile_rank, fetch_indicator_history
- `stock/dashboard/backend/services/indicators/macro.py` — 4 entries
- `stock/dashboard/backend/services/indicators/chip_total.py` — 6 entries
- `stock/dashboard/backend/services/indicators/stock_per.py` — 3 entries
- `stock/dashboard/backend/services/indicators/stock_chip.py` — 5 entries
- `stock/dashboard/backend/services/indicators/stock_revenue.py` — 1 entry
- `stock/dashboard/backend/services/indicators/stock_quarterly.py` — 5 entries
- `stock/dashboard/backend/services/indicators/stock_yearly.py` — 2 entries
- `stock/dashboard/tests/unit/__init__.py` — empty (if not exists)
- `stock/dashboard/tests/unit/test_alert_registry.py` — registry semantics tests

**Modified:**
- `stock/dashboard/backend/services/alert_engine.py` — drastic shrink in T10 (404 → ~120 lines)
- `stock/dashboard/backend/api/routes/alerts.py` — T11 removes hardcoded `STOCK_*_KEYS`
- `stock/dashboard/backend/api/routes/indicators.py` — T12 adds `/api/indicators/spec`
- `stock/dashboard/tests/test_api.py` — T12 adds 1 test for spec endpoint
- `docs/superpowers/specs/2026-05-02-stock-dashboard-conventions-design.md` — T13 §2.2 amendment

**Unchanged:**
- All `repositories/`, `db/`, `core/`, `fetchers/`, `main.py`, other routes
- `services/alert_notifier.py`, `services/backfill.py`
- `tests/test_alerts.py` (~42 tests are the equivalence contract)
- `tests/conftest.py`

---

## Baseline

Before starting: `5 failed, 128 passed`. Same 5 baseline failures (DO NOT FIX).

After REG-T9: same `5 failed, 128 passed` (registry exists but engine still uses old switch).
After REG-T10: same `5 failed, 128 passed` (engine swapped to registry; 42 alert tests prove behaviour preserved).
After REG-T13: `5 failed, ≥ 134 passed` (5 new tests for registry + 1 for spec endpoint).

---

## Task Breakdown

### Task 1 (REG-T1): Registry skeleton + helpers

**Files:**
- Create: `stock/dashboard/backend/services/alert_registry.py`
- Create: `stock/dashboard/backend/services/indicators/__init__.py` (empty)
- Create: `stock/dashboard/backend/services/indicators/_helpers.py`

- [ ] **Step 1: Verify baseline**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed, 3 warnings`.

- [ ] **Step 2: Create `services/alert_registry.py`**

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

- [ ] **Step 3: Create empty `services/indicators/__init__.py`**

```bash
mkdir -p /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/services/indicators
touch /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/services/indicators/__init__.py
```

(Will be filled with auto-import lines as T3-T9 add modules.)

- [ ] **Step 4: Create `services/indicators/_helpers.py`**

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

- [ ] **Step 5: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 128 passed`. (No callers of registry yet.)

- [ ] **Step 6: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/services/alert_registry.py stock/dashboard/backend/services/indicators/__init__.py stock/dashboard/backend/services/indicators/_helpers.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add alert_registry + indicators package skeleton (REG-T1)

IndicatorSpec dataclass with two registries (indicator vs stock_indicator).
register_indicator/get_indicator/list_indicators/all_indicators APIs.
Empty indicators/ package with _helpers (percentile_rank, fetch_indicator_history).
No callers yet — alert_engine still uses old switch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2 (REG-T2): Registry unit tests

**Files:**
- Create: `stock/dashboard/tests/unit/__init__.py` (empty, if not exists)
- Create: `stock/dashboard/tests/unit/test_alert_registry.py`

- [ ] **Step 1: Ensure `tests/unit/` exists**

```bash
mkdir -p /Users/paulwu/Documents/Github/tools/stock/dashboard/tests/unit
touch /Users/paulwu/Documents/Github/tools/stock/dashboard/tests/unit/__init__.py
```

- [ ] **Step 2: Write the registry tests**

Create `stock/dashboard/tests/unit/test_alert_registry.py`:

```python
"""Alert registry unit tests."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

import pytest
import importlib

import services.alert_registry as registry_mod
from services.alert_registry import IndicatorSpec, register_indicator, get_indicator, list_indicators, all_indicators


@pytest.fixture(autouse=True)
def reset_registry():
    """Snapshot and restore registry state between tests."""
    importlib.reload(registry_mod)
    yield
    importlib.reload(registry_mod)


def _make_spec(key: str = "test_a", target_type: str = "indicator", **kw) -> IndicatorSpec:
    return IndicatorSpec(
        key=key,
        label=kw.get("label", "Test"),
        unit=kw.get("unit", ""),
        target_type=target_type,
        supported_conditions=kw.get("supported_conditions", {"above"}),
        get_latest_value=lambda _t: 0.0,
    )


def test_register_and_get_indicator():
    spec = _make_spec(key="taiex", target_type="indicator")
    register_indicator(spec)
    assert get_indicator("indicator", "taiex") is spec


def test_register_and_get_stock_indicator():
    spec = _make_spec(key="per", target_type="stock_indicator")
    register_indicator(spec)
    assert get_indicator("stock_indicator", "per") is spec


def test_same_key_in_both_registries_does_not_collide():
    """`margin_balance` exists at both indicator-level (chip_total) and stock-level (chip_stock)."""
    indicator_spec = _make_spec(key="margin_balance", target_type="indicator", label="台股融資餘額")
    stock_spec = _make_spec(key="margin_balance", target_type="stock_indicator", label="融資餘額")
    register_indicator(indicator_spec)
    register_indicator(stock_spec)

    assert get_indicator("indicator", "margin_balance") is indicator_spec
    assert get_indicator("stock_indicator", "margin_balance") is stock_spec


def test_unknown_target_type_raises():
    spec = _make_spec()
    spec.target_type = "weather"
    with pytest.raises(ValueError, match="Unsupported target_type"):
        register_indicator(spec)


def test_get_indicator_unknown_returns_none():
    assert get_indicator("indicator", "nonexistent") is None
    assert get_indicator("stock_indicator", "nonexistent") is None
    assert get_indicator("weather", "anything") is None


def test_list_indicators_sorted_by_key():
    register_indicator(_make_spec(key="zeta", target_type="indicator"))
    register_indicator(_make_spec(key="alpha", target_type="indicator"))
    register_indicator(_make_spec(key="middle", target_type="indicator"))
    keys = [s.key for s in list_indicators("indicator")]
    assert keys == ["alpha", "middle", "zeta"]


def test_all_indicators_returns_both_buckets():
    register_indicator(_make_spec(key="taiex", target_type="indicator"))
    register_indicator(_make_spec(key="per", target_type="stock_indicator"))
    out = all_indicators()
    assert [s.key for s in out["indicator"]] == ["taiex"]
    assert [s.key for s in out["stock_indicator"]] == ["per"]


def test_supports_returns_membership():
    spec = _make_spec(supported_conditions={"above", "streak_above"})
    assert spec.supports("above") is True
    assert spec.supports("streak_above") is True
    assert spec.supports("below") is False
```

- [ ] **Step 3: Run the tests**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/unit/test_alert_registry.py -v 2>&1 | tail -15
```

Expected: 8 tests PASS.

- [ ] **Step 4: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 136 passed` (8 new tests passing).

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/tests/unit/__init__.py stock/dashboard/tests/unit/test_alert_registry.py && git commit -m "$(cat <<'EOF'
test(stock-dashboard): registry semantics + collision handling (REG-T2)

8 unit tests covering register/get/list, name collision across
target_types, unsupported target_type validation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3 (REG-T3): `indicators/macro.py` (4 entries)

**Files:**
- Create: `stock/dashboard/backend/services/indicators/macro.py`
- Modify: `stock/dashboard/backend/services/indicators/__init__.py` (add 1 import)

- [ ] **Step 1: Create `services/indicators/macro.py`**

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
            (lambda r: r["value"] if r else None)(get_latest_indicator(k))
        ),
        get_history=lambda _t, n, k=key: fetch_indicator_history(k, n),
    )


for _key, _label, _unit in (
    ("taiex",      "加權指數",      "點"),
    ("fx",         "台幣兌美金",   "TWD"),
    ("fear_greed", "恐懼與貪婪指數", ""),
    ("ndc",        "國發會景氣指標", "分"),
):
    register_indicator(_make_macro_spec(_key, _label, _unit))
```

- [ ] **Step 2: Update `services/indicators/__init__.py`**

Replace the empty file content with:

```python
"""Auto-registration: importing this package triggers all register_indicator calls."""
from . import macro              # noqa: F401
```

- [ ] **Step 3: Smoke-test registration**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from services import indicators  # triggers register
from services.alert_registry import list_indicators
keys = [s.key for s in list_indicators('indicator')]
print('indicator keys:', keys)
assert keys == ['fear_greed', 'fx', 'ndc', 'taiex'], f'unexpected: {keys}'
print('ok')
"
```

Expected: prints `indicator keys: ['fear_greed', 'fx', 'ndc', 'taiex']` and `ok`.

- [ ] **Step 4: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 136 passed`. No behavioural change yet.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/services/indicators/macro.py stock/dashboard/backend/services/indicators/__init__.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): register macro indicators in registry (REG-T3)

taiex, fx, fear_greed, ndc registered as target_type="indicator".
get_history uses fetch_indicator_history helper. Engine still uses
old switch — registry not yet wired in.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4 (REG-T4): `indicators/chip_total.py` (6 entries)

**Files:**
- Create: `stock/dashboard/backend/services/indicators/chip_total.py`
- Modify: `stock/dashboard/backend/services/indicators/__init__.py`

- [ ] **Step 1: Create the file**

Write `stock/dashboard/backend/services/indicators/chip_total.py`:

```python
"""Indicator-level chip totals from chip_total fetcher."""
from repositories.indicators import get_latest_indicator
from services.alert_registry import IndicatorSpec, register_indicator
from services.indicators._helpers import fetch_indicator_history


def _make_chip_total_spec(key: str, label: str, unit: str) -> IndicatorSpec:
    return IndicatorSpec(
        key=key,
        label=label,
        unit=unit,
        target_type="indicator",
        supported_conditions={"above", "below", "streak_above", "streak_below"},
        get_latest_value=lambda _t, k=key: (
            (lambda r: r["value"] if r else None)(get_latest_indicator(k))
        ),
        get_history=lambda _t, n, k=key: fetch_indicator_history(k, n),
    )


for _key, _label, _unit in (
    ("margin_balance",     "台股融資餘額", "億元"),
    ("short_balance",      "台股融券餘額", "張"),
    ("short_margin_ratio", "台股券資比",   "%"),
    ("total_foreign_net",  "外資淨買超",   "億元"),
    ("total_trust_net",    "投信淨買超",   "億元"),
    ("total_dealer_net",   "自營商淨買超", "億元"),
):
    register_indicator(_make_chip_total_spec(_key, _label, _unit))
```

- [ ] **Step 2: Update `__init__.py` to import**

```python
"""Auto-registration: importing this package triggers all register_indicator calls."""
from . import macro              # noqa: F401
from . import chip_total         # noqa: F401
```

- [ ] **Step 3: Smoke-test**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from services import indicators
from services.alert_registry import list_indicators
keys = [s.key for s in list_indicators('indicator')]
print('count:', len(keys), keys)
assert len(keys) == 10
print('ok')
"
```

Expected: count 10, includes `taiex/fx/fear_greed/ndc + 6 chip_total keys`.

- [ ] **Step 4: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 136 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/services/indicators/chip_total.py stock/dashboard/backend/services/indicators/__init__.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): register chip_total indicators in registry (REG-T4)

6 entries: margin_balance, short_balance, short_margin_ratio,
total_{foreign,trust,dealer}_net (target_type="indicator").

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5 (REG-T5): `indicators/stock_per.py` (3 entries)

**Files:**
- Create: `stock/dashboard/backend/services/indicators/stock_per.py`
- Modify: `stock/dashboard/backend/services/indicators/__init__.py`

- [ ] **Step 1: Create the file**

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


for _key, _label, _unit in (
    ("per",            "PER",   ""),
    ("pbr",            "PBR",   ""),
    ("dividend_yield", "殖利率", "%"),
):
    register_indicator(IndicatorSpec(
        key=_key,
        label=_label,
        unit=_unit,
        target_type="stock_indicator",
        supported_conditions=_DAILY_CONDS,
        get_latest_value=lambda t, f=_key: _get_latest(t, field=f),
        get_history=lambda t, n, f=_key: _get_history(t, n, field=f),
        get_percentile=lambda t, f=_key: _get_percentile(t, field=f),
    ))
```

- [ ] **Step 2: Update `__init__.py`**

Add line `from . import stock_per  # noqa: F401`.

- [ ] **Step 3: Smoke-test**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from services import indicators
from services.alert_registry import list_indicators
keys = [s.key for s in list_indicators('stock_indicator')]
print('count:', len(keys), keys)
assert keys == ['dividend_yield', 'pbr', 'per']
print('ok')
"
```

- [ ] **Step 4: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 136 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/services/indicators/stock_per.py stock/dashboard/backend/services/indicators/__init__.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): register stock_per indicators in registry (REG-T5)

per, pbr, dividend_yield (target_type="stock_indicator").
Supports above/below/streak_*/percentile_*.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6 (REG-T6): `indicators/stock_chip.py` (5 entries)

**Files:**
- Create: `stock/dashboard/backend/services/indicators/stock_chip.py`
- Modify: `stock/dashboard/backend/services/indicators/__init__.py`

- [ ] **Step 1: Create the file**

```python
"""Stock chip daily indicators: foreign/trust/dealer net + margin/short balance."""
from datetime import datetime, timedelta, timezone

from repositories.chip import get_chip_daily_range
from services.alert_registry import IndicatorSpec, register_indicator


_NET_KEYS = {"foreign_net", "trust_net", "dealer_net"}
_BAL_KEYS = {"margin_balance", "short_balance"}


def _get_history(ticker: str, n: int, *, key: str) -> list[float]:
    since_date = (datetime.now(timezone.utc).date() - timedelta(days=max(n * 3 + 30, 60))).isoformat()
    rows = get_chip_daily_range(ticker, since_date)
    if key in _NET_KEYS:
        bs_prefix = key[:-4]   # 'foreign_net' → 'foreign'
        values = []
        for r in rows:
            buy, sell = r[f"{bs_prefix}_buy"], r[f"{bs_prefix}_sell"]
            if buy is None or sell is None:
                values.append(None)
            else:
                values.append(buy - sell)
    else:  # margin_balance / short_balance
        values = [r[key] for r in rows]
    clean = [v for v in values if v is not None]
    return clean[-n:]


def _get_latest(ticker: str, *, key: str) -> float | None:
    history = _get_history(ticker, 1, key=key)
    return history[-1] if history else None


_CONDS = {"above", "below", "streak_above", "streak_below"}


_LABELS = {
    "foreign_net":      "外資淨買",
    "trust_net":        "投信淨買",
    "dealer_net":       "自營淨買",
    "margin_balance":   "融資餘額",
    "short_balance":    "融券餘額",
}

for _key, _label in _LABELS.items():
    register_indicator(IndicatorSpec(
        key=_key,
        label=_label,
        unit="",
        target_type="stock_indicator",
        supported_conditions=_CONDS,
        get_latest_value=lambda t, k=_key: _get_latest(t, key=k),
        get_history=lambda t, n, k=_key: _get_history(t, n, key=k),
    ))
```

- [ ] **Step 2: Update `__init__.py`**

Add line `from . import stock_chip  # noqa: F401`.

- [ ] **Step 3: Smoke-test**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from services import indicators
from services.alert_registry import list_indicators, get_indicator
keys = [s.key for s in list_indicators('stock_indicator')]
print('stock_indicator count:', len(keys), keys)
assert len(keys) == 8  # 3 per + 5 chip
# verify margin_balance disambiguates by target_type
ind_mb = get_indicator('indicator', 'margin_balance')
stk_mb = get_indicator('stock_indicator', 'margin_balance')
assert ind_mb.label == '台股融資餘額'
assert stk_mb.label == '融資餘額'
print('ok')
"
```

- [ ] **Step 4: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 136 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/services/indicators/stock_chip.py stock/dashboard/backend/services/indicators/__init__.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): register stock_chip indicators in registry (REG-T6)

5 entries: foreign_net, trust_net, dealer_net, margin_balance,
short_balance (target_type="stock_indicator"). Same key
margin_balance/short_balance disambiguates from chip_total via
target_type.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7 (REG-T7): `indicators/stock_revenue.py` (1 entry, yoy-only)

**Files:**
- Create: `stock/dashboard/backend/services/indicators/stock_revenue.py`
- Modify: `stock/dashboard/backend/services/indicators/__init__.py`

- [ ] **Step 1: Create the file**

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
    get_latest_value=lambda _t: None,  # not directly used; only yoy supported
    get_yoy=_get_revenue_yoy,
))
```

- [ ] **Step 2: Update `__init__.py`**

Add line `from . import stock_revenue  # noqa: F401`.

- [ ] **Step 3: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 136 passed`.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/services/indicators/stock_revenue.py stock/dashboard/backend/services/indicators/__init__.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): register revenue indicator (yoy-only) (REG-T7)

revenue (target_type="stock_indicator") supports yoy_above/yoy_below
only — matches existing alert engine routing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8 (REG-T8): `indicators/stock_quarterly.py` (5 entries)

**Files:**
- Create: `stock/dashboard/backend/services/indicators/stock_quarterly.py`
- Modify: `stock/dashboard/backend/services/indicators/__init__.py`

- [ ] **Step 1: Create the file**

```python
"""Stock quarterly financial indicators (yoy-only)."""
from datetime import datetime, timezone

from repositories.fundamentals import get_financial_quarterly_range
from services.alert_registry import IndicatorSpec, register_indicator


_QUARTERLY_TYPES = {
    "q_eps":              ("income",    "EPS"),
    "q_revenue":          ("income",    "Revenue"),
    "q_operating_income": ("income",    "OperatingIncome"),
    "q_net_income":       ("income",    "IncomeAfterTaxes"),
    "q_operating_cf":     ("cash_flow", "CashFlowsFromOperatingActivities"),
}


def _get_quarterly_yoy(ticker: str, *, key: str) -> float | None:
    if key not in _QUARTERLY_TYPES:
        return None
    report_type, type_name = _QUARTERLY_TYPES[key]
    today = datetime.now(timezone.utc).date()
    since = today.replace(year=today.year - 3, month=1, day=1).isoformat()
    rows = get_financial_quarterly_range(ticker, report_type, since)
    same_type = [(r["date"], r["value"]) for r in rows
                 if r["type"] == type_name and r["value"] is not None]
    if not same_type:
        return None
    same_type.sort(key=lambda x: x[0])
    latest_date, latest_value = same_type[-1]

    dt = datetime.strptime(latest_date, "%Y-%m-%d")
    target_prev_date = f"{dt.year - 1}-{dt.month:02d}-{dt.day:02d}"
    prev_value = next((v for d, v in same_type if d == target_prev_date), None)
    if prev_value is None or prev_value == 0:
        return None
    return round((latest_value - prev_value) / prev_value * 100, 2)


_LABELS = {
    "q_eps":              "季 EPS",
    "q_revenue":          "季營收",
    "q_operating_income": "季營業利益",
    "q_net_income":       "季稅後淨利",
    "q_operating_cf":     "季營運現金流",
}

for _key, _label in _LABELS.items():
    register_indicator(IndicatorSpec(
        key=_key,
        label=_label,
        unit="%",
        target_type="stock_indicator",
        supported_conditions={"yoy_above", "yoy_below"},
        get_latest_value=lambda _t: None,
        get_yoy=lambda t, k=_key: _get_quarterly_yoy(t, key=k),
    ))
```

- [ ] **Step 2: Update `__init__.py`**

Add line `from . import stock_quarterly  # noqa: F401`.

- [ ] **Step 3: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 136 passed`.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/services/indicators/stock_quarterly.py stock/dashboard/backend/services/indicators/__init__.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): register stock_quarterly indicators (REG-T8)

5 entries: q_eps, q_revenue, q_operating_income, q_net_income,
q_operating_cf (target_type="stock_indicator", yoy-only).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9 (REG-T9): `indicators/stock_yearly.py` (2 entries)

**Files:**
- Create: `stock/dashboard/backend/services/indicators/stock_yearly.py`
- Modify: `stock/dashboard/backend/services/indicators/__init__.py`

- [ ] **Step 1: Create the file**

```python
"""Stock yearly dividend indicators (yoy-only)."""
import re

from repositories.fundamentals import get_dividend_history
from services.alert_registry import IndicatorSpec, register_indicator


_FIELD_MAP = {
    "y_cash_dividend":  "cash_dividend",
    "y_stock_dividend": "stock_dividend",
}


def _get_yearly_yoy(ticker: str, *, key: str) -> float | None:
    if key not in _FIELD_MAP:
        return None
    field = _FIELD_MAP[key]
    raw_rows = get_dividend_history(ticker)
    if not raw_rows:
        return None

    by_year: dict[int, float] = {}
    for r in raw_rows:
        m = re.match(r"^(\d{2,3})年", r.get("year") or "")
        if not m:
            continue
        ce_year = int(m.group(1)) + 1911
        v = r.get(field) or 0
        by_year[ce_year] = by_year.get(ce_year, 0) + v

    if len(by_year) < 2:
        return None
    sorted_years = sorted(by_year.keys())
    latest_year = sorted_years[-1]
    prev_year = latest_year - 1
    cur = by_year.get(latest_year)
    prev = by_year.get(prev_year)
    if cur is None or not prev:
        return None
    return round((cur - prev) / prev * 100, 2)


_LABELS = {
    "y_cash_dividend":  "年度現金股利",
    "y_stock_dividend": "年度股票股利",
}

for _key, _label in _LABELS.items():
    register_indicator(IndicatorSpec(
        key=_key,
        label=_label,
        unit="%",
        target_type="stock_indicator",
        supported_conditions={"yoy_above", "yoy_below"},
        get_latest_value=lambda _t: None,
        get_yoy=lambda t, k=_key: _get_yearly_yoy(t, key=k),
    ))
```

- [ ] **Step 2: Update `__init__.py`**

Final state:

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

- [ ] **Step 3: Verify all 26 indicators registered**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from services import indicators
from services.alert_registry import all_indicators
out = all_indicators()
ind = [s.key for s in out['indicator']]
stk = [s.key for s in out['stock_indicator']]
print('indicator (', len(ind), '):', ind)
print('stock_indicator (', len(stk), '):', stk)
assert len(ind) == 10
assert len(stk) == 16
print('ok: 26 indicators registered')
"
```

Expected: `ok: 26 indicators registered`.

- [ ] **Step 4: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 136 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/services/indicators/stock_yearly.py stock/dashboard/backend/services/indicators/__init__.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): register stock_yearly indicators (REG-T9)

y_cash_dividend, y_stock_dividend (target_type="stock_indicator",
yoy-only). All 26 indicator entries now registered: 10 indicator-level
+ 16 stock-level. Engine still uses old switch — REG-T10 wires registry.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10 (REG-T10): Rewrite `alert_engine.py` to dispatch via registry

**Files:**
- Modify: `stock/dashboard/backend/services/alert_engine.py` (drastic shrink)

This is the critical equivalence-validation step. Existing 42 alert tests in `tests/test_alerts.py` are the contract — they must all pass without modification.

- [ ] **Step 1: Replace `alert_engine.py` entirely**

Replace the entire file `stock/dashboard/backend/services/alert_engine.py` with this content:

```python
"""Alert evaluation logic — registry-driven dispatch.

Each indicator's value-fetching lives in services/indicators/<group>.py.
This module wires conditions to the right provider and handles formatting.
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
    return target  # stock or unknown


def _build_payload(alert: dict, value: float | None, display_name: str, spec) -> dict:
    cond = alert["condition"]
    threshold = alert["threshold"]
    window_n = alert.get("window_n")
    target_type = alert["target_type"]

    def _fmt(v: float) -> str:
        if v is None:
            return "—"
        if target_type == "indicator":
            return _format_value(target_type, alert["target"], v, spec)
        if target_type == "stock_indicator":
            ik = alert.get("indicator_key")
            if ik in ("per", "pbr"):
                return f"{v:.2f}"
            if ik == "dividend_yield":
                return f"{v:.2f}%"
            if ik == "revenue":
                return f"{v:.2f}%"
            return f"{v:,.0f}"
        # stock
        return f"{v:,.4f}" if v < 100 else f"{v:,.2f}"

    value_str = _fmt(value) if value is not None else "—"
    threshold_str = _fmt(threshold)

    if cond == "above":
        crossed = "突破"
        color = 0xE74C3C
    elif cond == "below":
        crossed = "跌破"
        color = 0x3498DB
    elif cond == "streak_above":
        crossed = f"連 {window_n} 日突破"
        color = 0xE74C3C
    elif cond == "streak_below":
        crossed = f"連 {window_n} 日跌破"
        color = 0x3498DB
    elif cond == "percentile_above":
        crossed = "5y 百分位突破"
        color = 0xE74C3C
    elif cond == "percentile_below":
        crossed = "5y 百分位跌破"
        color = 0x3498DB
    elif cond == "yoy_above":
        crossed = "YoY 突破"
        color = 0xE74C3C
    elif cond == "yoy_below":
        crossed = "YoY 跌破"
        color = 0x3498DB
    else:
        crossed = cond
        color = 0x95A5A6

    embed = {
        "title": f"🚨 警示:{display_name}",
        "description": (
            f"**{display_name}** 目前 **{value_str}**,已{crossed}門檻 **{threshold_str}**。\n"
            f"_警示已自動停用,請至 Dashboard 重新啟用。_"
        ),
        "color": color,
    }
    return {"embeds": [embed]}


def _resolve_value(spec, alert, target, value, cond, indicator_key):
    """Return the current value to compare against threshold."""
    if spec is None:
        # target_type == "stock"; uses passed-in value directly
        return value
    if cond in ("above", "below"):
        if spec.target_type == "indicator" and value is not None:
            return value
        return spec.get_latest_value(target)
    if cond in ("streak_above", "streak_below"):
        if spec.get_history is None:
            return None
        n = alert.get("window_n") or 5
        history = spec.get_history(target, n)
        return history[-1] if history else None
    if cond in ("percentile_above", "percentile_below"):
        return spec.get_percentile(target) if spec.get_percentile else None
    if cond in ("yoy_above", "yoy_below"):
        return spec.get_yoy(target) if spec.get_yoy else None
    return None


def _compare(value: float, threshold: float, cond: str, window_n: int | None,
             spec, target: str) -> bool:
    """Return whether the alert should trigger."""
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
    """Evaluate alerts and notify on trigger.

    Dispatch via services.alert_registry: looks up IndicatorSpec by
    (target_type, indicator_key_or_target) and uses spec's value providers.
    """
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
        spec = None  # target_type == "stock"

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

- [ ] **Step 2: Run the full suite — equivalence validation**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 136 passed`. Same baseline, every alert test still passes.

If any alert test fails:
- Read the failure carefully — likely a behavioural divergence
- Common causes:
  - `_resolve_value` returns `None` where the old engine used the passed-in `value` (check `target_type == "indicator"` path)
  - `_compare` returns the wrong direction for percentile/yoy
  - `_alert_display_name` returns wrong string when spec is None vs not
  - `_build_payload` `_fmt` divergence for stock_indicator types
- Compare to the original `alert_engine.py` behaviour line-by-line for that condition

- [ ] **Step 3: Verify file size**

```bash
wc -l /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/services/alert_engine.py
```

Expected: ≤ 150 lines (the full content above is around 130 lines).

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/services/alert_engine.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): swap alert_engine to registry dispatch (REG-T10)

check_alerts now dispatches via services.alert_registry. Helpers
INDICATOR_LABELS/UNITS, STOCK_INDICATOR_LABELS, _check_streak,
_pct_rank, _get_stock_indicator_history, _get_stock_revenue_yoy,
_get_stock_quarterly_yoy, _get_stock_yearly_yoy, _latest_indicator_history
removed (lived in indicator files since REG-T3..T9 or _helpers.py).

alert_engine.py shrinks from 404 → ~130 lines. Behaviour unchanged:
all 42 existing alert tests pass.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11 (REG-T11): `routes/alerts.py` validation simplification

**Files:**
- Modify: `stock/dashboard/backend/api/routes/alerts.py`

- [ ] **Step 1: Replace `routes/alerts.py` entirely**

Replace the entire file with:

```python
"""Alert routes: list, create, delete, toggle."""
from fastapi import APIRouter, HTTPException

from api.schemas.alerts import AlertRequest, AlertToggleRequest
from repositories.alerts import (
    add_alert, delete_alert, list_alerts, set_alert_enabled,
)
from services.alert_registry import get_indicator
from services import indicators  # noqa: F401  ← trigger auto-register
from fetchers.fundamentals_stock import to_finmind_id as fundamentals_to_finmind_id

router = APIRouter(prefix="/api", tags=["alerts"])


VALID_TARGET_TYPES = {"indicator", "stock", "stock_indicator"}
VALID_CONDITIONS = {
    "above", "below",
    "streak_above", "streak_below",
    "percentile_above", "percentile_below",
    "yoy_above", "yoy_below",
}


@router.get("/alerts")
def get_alerts():
    return list_alerts()


@router.post("/alerts")
def create_alert(req: AlertRequest):
    if req.target_type not in VALID_TARGET_TYPES:
        raise HTTPException(status_code=400, detail="Invalid target_type")
    if req.condition not in VALID_CONDITIONS:
        raise HTTPException(status_code=400, detail="Invalid condition")

    is_streak = req.condition.startswith("streak_")
    if is_streak:
        if req.window_n is None:
            raise HTTPException(status_code=400, detail="streak condition requires window_n")
        if req.window_n < 2 or req.window_n > 30:
            raise HTTPException(status_code=400, detail="window_n must be 2..30")

    is_percentile = req.condition.startswith("percentile_")
    if is_percentile and (req.threshold < 0 or req.threshold > 100):
        raise HTTPException(status_code=400, detail="percentile threshold must be 0..100")

    if req.target_type == "indicator":
        spec = get_indicator("indicator", req.target)
        if spec is None:
            raise HTTPException(status_code=400, detail="Unknown indicator")
        if not spec.supports(req.condition):
            raise HTTPException(
                status_code=400,
                detail=f"indicator {req.target} does not support {req.condition}",
            )
        target = req.target
    elif req.target_type == "stock_indicator":
        if not req.indicator_key:
            raise HTTPException(status_code=400, detail="stock_indicator requires indicator_key")
        spec = get_indicator("stock_indicator", req.indicator_key)
        if spec is None:
            raise HTTPException(status_code=400, detail="Unknown indicator_key")
        if fundamentals_to_finmind_id(req.target) is None:
            raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) supported")
        if not spec.supports(req.condition):
            raise HTTPException(
                status_code=400,
                detail=f"indicator {req.indicator_key} does not support condition {req.condition}",
            )
        target = req.target.upper()
    else:  # stock
        target = req.target.upper()

    alert_id = add_alert(req.target_type, target, req.condition, req.threshold,
                         indicator_key=req.indicator_key, window_n=req.window_n)
    return {"id": alert_id}


@router.delete("/alerts/{alert_id}")
def remove_alert(alert_id: int):
    delete_alert(alert_id)
    return {"ok": True}


@router.patch("/alerts/{alert_id}")
def toggle_alert(alert_id: int, req: AlertToggleRequest):
    set_alert_enabled(alert_id, req.enabled)
    return {"ok": True}
```

- [ ] **Step 2: Verify file size**

```bash
wc -l /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/routes/alerts.py
```

Expected: ≤ 90 lines (~85 lines).

- [ ] **Step 3: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 136 passed`. Existing alert validation tests in `test_api.py` cover error paths like "Unknown indicator", "Unknown indicator_key", "stock_indicator requires indicator_key", percentile-on-non-daily mismatch, yoy-on-non-monthly mismatch — all paths still work via spec.supports.

If any test fails with a different error message than expected:
- Original message: `"percentile condition requires daily indicator (per/pbr/dividend_yield)"`
- New message: `"indicator per does not support condition percentile_above"` (different but still 400)
- Test should assert on `r.status_code == 400`, not message text — verify which tests assert message and update if needed.

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/api/routes/alerts.py && git commit -m "$(cat <<'EOF'
refactor(stock-dashboard): alert validation reads from registry (REG-T11)

routes/alerts.py loses STOCK_DAILY_INDICATOR_KEYS, STOCK_MONTHLY_*,
STOCK_QUARTERLY_*, STOCK_YEARLY_*, STOCK_YOY_COMPATIBLE_KEYS,
STOCK_INDICATOR_KEYS, PERCENTILE_DAILY_KEYS constants. Cross-validation
(percentile only for daily, yoy only for monthly/quarterly/yearly) is
now expressed by each spec's supported_conditions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12 (REG-T12): Add `/api/indicators/spec` endpoint

**Files:**
- Modify: `stock/dashboard/backend/api/routes/indicators.py` (add endpoint)
- Modify: `stock/dashboard/tests/test_api.py` (add 1 test)

- [ ] **Step 1: Add endpoint in `routes/indicators.py`**

Open `stock/dashboard/backend/api/routes/indicators.py`. After the existing `def refresh(...)` endpoint (the last one in the file), add:

```python


@router.get("/indicators/spec")
def indicators_spec():
    """Return alert-able indicator specs grouped by target_type.

    Frontend (Phase 5) uses this to render the alert creation form.
    """
    from services.alert_registry import all_indicators
    from services import indicators as _indicators_pkg  # noqa: F401  ← trigger auto-register

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

- [ ] **Step 2: Add test in `tests/test_api.py`**

Append to `stock/dashboard/tests/test_api.py`:

```python
def test_indicators_spec_endpoint():
    r = client.get("/api/indicators/spec")
    assert r.status_code == 200
    body = r.json()
    assert "indicator" in body
    assert "stock_indicator" in body
    assert len(body["indicator"]) == 10
    assert len(body["stock_indicator"]) == 16

    # spot-check known entries
    keys_indicator = {s["key"] for s in body["indicator"]}
    assert "taiex" in keys_indicator
    assert "fear_greed" in keys_indicator
    assert "margin_balance" in keys_indicator  # indicator-level

    keys_stock = {s["key"] for s in body["stock_indicator"]}
    assert "per" in keys_stock
    assert "revenue" in keys_stock
    assert "q_eps" in keys_stock
    assert "y_cash_dividend" in keys_stock
    assert "margin_balance" in keys_stock  # stock-level (collides with indicator-level by name)

    # verify schema fields
    sample = body["indicator"][0]
    assert {"key", "label", "unit", "supported_conditions"} <= set(sample.keys())
    assert isinstance(sample["supported_conditions"], list)
```

- [ ] **Step 3: Run full suite**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 137 passed` (+1 new test).

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools && git add stock/dashboard/backend/api/routes/indicators.py stock/dashboard/tests/test_api.py && git commit -m "$(cat <<'EOF'
feat(stock-dashboard): add GET /api/indicators/spec endpoint (REG-T12)

Returns the alert registry as JSON, grouped by target_type. Frontend
(Phase 5) consumes this to render the alert creation form dynamically.
1 new test verifies schema and entry counts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13 (REG-T13): Final verification + CONVENTIONS amendment

**Files:**
- Modify: `docs/superpowers/specs/2026-05-02-stock-dashboard-conventions-design.md`
- Inspect: backend file sizes / structure

- [ ] **Step 1: Verify final backend file structure and sizes**

```bash
ls /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/services/indicators/
wc -l /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/services/alert_engine.py /Users/paulwu/Documents/Github/tools/stock/dashboard/backend/api/routes/alerts.py
```

Expected:
- `services/indicators/` contains: `__init__.py`, `_helpers.py`, `macro.py`, `chip_total.py`, `stock_per.py`, `stock_chip.py`, `stock_revenue.py`, `stock_quarterly.py`, `stock_yearly.py` (and `__pycache__/`)
- `alert_engine.py` ≤ 150 lines (down from 404)
- `routes/alerts.py` ≤ 90 lines (down from 105)

- [ ] **Step 2: Verify spec endpoint live**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard/backend && python3 -c "
from main import app
from fastapi.testclient import TestClient
client = TestClient(app)
r = client.get('/api/indicators/spec')
data = r.json()
print('indicator count:', len(data['indicator']))
print('stock_indicator count:', len(data['stock_indicator']))
print('sample stock_indicator:', data['stock_indicator'][0])
"
```

Expected: 10 indicator + 16 stock_indicator entries with valid schema.

- [ ] **Step 3: Run full suite one final time**

```bash
cd /Users/paulwu/Documents/Github/tools/stock/dashboard && python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: `5 failed, 137 passed`.

- [ ] **Step 4: Update `CONVENTIONS.md` §2.2 (Fetcher Protocol amendment)**

Open `docs/superpowers/specs/2026-05-02-stock-dashboard-conventions-design.md`. Find section **§2.2 Fetcher Protocol** (which currently shows the strict `Fetcher` Protocol class).

Insert at the very top of §2.2 (before the existing content), this amendment block:

```markdown
> **Status amendment (REG-T13, 2026-05-02)**: After implementation of Phase 1–3, the strict Fetcher Protocol described below was found to misfit the codebase reality (9 fetchers have widely different shapes: numeric snapshots, multi-column daily rows, text articles, OHLC time-series, multi-stock orchestrators). The high-value goal of "one-file changes for new alert-able indicators" is fully achieved through the **Alert Indicator Registry** (§2.3); strict Fetcher Protocol/Snapshot is **deferred** and may be revisited only if pain emerges. The original spec text below is retained for context. New fetchers should follow these lighter conventions:
>
> - Module named after source + topic (e.g. `chip_stock.py`, `fundamentals_stock.py`).
> - HTTP calls wrap with `tenacity.retry` (exponential backoff, max 3 attempts).
> - Failures log via stdlib `logging` and return a falsy/None signal to callers — do not propagate raw exceptions.
> - Where possible, fetchers return data structures that callers persist via `repositories/`. Existing fetchers that write the DB themselves are not a regression.
>
> See `docs/superpowers/specs/2026-05-02-stock-dashboard-reg-design.md` for the rationale.

```

(The existing `### 2.2 Fetcher Protocol` heading and code block stay below, unchanged.)

- [ ] **Step 5: Verify final branch log**

```bash
cd /Users/paulwu/Documents/Github/tools && git log --oneline master..HEAD
```

Expected (in reverse chronological order):

```
… REG-T13
… REG-T12
… REG-T11
… REG-T10
… REG-T9
… REG-T8
… REG-T7
… REG-T6
… REG-T5
… REG-T4
… REG-T3
… REG-T2
… REG-T1
```

(13 commits.)

- [ ] **Step 6: Commit the amendment**

```bash
cd /Users/paulwu/Documents/Github/tools && git add docs/superpowers/specs/2026-05-02-stock-dashboard-conventions-design.md && git commit -m "$(cat <<'EOF'
docs(stock-dashboard): amend CONVENTIONS §2.2 Fetcher Protocol (REG-T13)

Phase 3 finalised: Alert Indicator Registry shipped. Original Fetcher
Protocol idea retained as text but deferred — light conventions
(naming, retry, error handling) replace the strict Protocol/Snapshot
requirement. Rationale in REG- spec.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Spec Coverage Self-Check

| Spec section | Task |
|---|---|
| §1 Target file structure | T1 (registry + helpers + empty package), T3-T9 (7 indicator files) |
| §2 alert_registry.py mechanics | T1 |
| §3 indicators/__init__.py auto-register | T3-T9 progressive update |
| §4 _helpers.py (percentile_rank, fetch_indicator_history) | T1 |
| §5 indicator module examples | T3 (macro), T5 (stock_per), T7 (stock_revenue), and T4/T6/T8/T9 follow same pattern |
| §6 alert_engine simplification | T10 |
| §7 routes/alerts validation refactor | T11 |
| §8 GET /api/indicators/spec endpoint | T12 |
| §9 13-task migration order | T1–T13 (1:1 mapping) |
| §10 Acceptance criteria | T13 |
| §11 Risks (lambda capture, import order, behavioural regression) | Lambda default-arg pattern in T3-T9; lazy `from services import indicators` in T10/T11; equivalence validation in T10 |
| Amendment to CONVENTIONS §2.2 | T13 step 4 |

All sections covered.

---

## Execution Notes

- **Branch strategy**: per CONVENTIONS.md §5.3, large refactors get a feature branch. Recommended: `git checkout -b feat/reg-alert-registry` from master before T1, merge `--no-ff` after T13 passes.
- **Total tasks**: 13 (T1-T13). 13 commits.
- **Estimated time**: ~5-15 minutes per task; total 1.5-2 hours. T10 is the largest (engine rewrite + equivalence validation) — budget 20 minutes.
- **No new dependencies**.
- **Critical task**: T10. If any of the 42 existing alert tests fail, debug before commit. The plan does not break tests intentionally.
- **Deploy timing**: after T13 verification + merge to master + push. Backend rsync triggers; service restart picks up the new alert_engine + spec endpoint.

## Future-phase Notes

- **Phase 4 (AUTH-)** is unaffected by REG- (no auth interaction with registry).
- **Phase 5 (FE-)** consumes `GET /api/indicators/spec` for dynamic alert form rendering.
- **Future**: if adding a new fetcher proves repeatedly painful, revisit Fetcher Protocol idea. For now, light conventions in CONVENTIONS.md §2.2 are sufficient.
