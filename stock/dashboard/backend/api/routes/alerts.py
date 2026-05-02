"""Alert routes: list, create, delete, toggle."""
from fastapi import APIRouter, HTTPException

from api._constants import INDICATOR_NAMES
from api.schemas.alerts import AlertRequest, AlertToggleRequest
from repositories.alerts import (
    add_alert, delete_alert, list_alerts, set_alert_enabled,
)
from fetchers.fundamentals_stock import to_finmind_id as fundamentals_to_finmind_id

router = APIRouter(prefix="/api", tags=["alerts"])


VALID_TARGET_TYPES = {"indicator", "stock", "stock_indicator"}
VALID_CONDITIONS = {
    "above", "below",
    "streak_above", "streak_below",
    "percentile_above", "percentile_below",
    "yoy_above", "yoy_below",
}
STOCK_DAILY_INDICATOR_KEYS = {
    "per", "pbr", "dividend_yield",
    "foreign_net", "trust_net", "dealer_net",
    "margin_balance", "short_balance",
}
STOCK_MONTHLY_INDICATOR_KEYS = {"revenue"}
STOCK_QUARTERLY_INDICATOR_KEYS = {
    "q_eps", "q_revenue", "q_operating_income",
    "q_net_income", "q_operating_cf",
}
STOCK_YEARLY_INDICATOR_KEYS = {"y_cash_dividend", "y_stock_dividend"}
STOCK_YOY_COMPATIBLE_KEYS = (
    STOCK_MONTHLY_INDICATOR_KEYS
    | STOCK_QUARTERLY_INDICATOR_KEYS
    | STOCK_YEARLY_INDICATOR_KEYS
)
STOCK_INDICATOR_KEYS = STOCK_DAILY_INDICATOR_KEYS | STOCK_YOY_COMPATIBLE_KEYS
PERCENTILE_DAILY_KEYS = {"per", "pbr", "dividend_yield"}


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
    is_yoy = req.condition.startswith("yoy_")
    if is_percentile and (req.threshold < 0 or req.threshold > 100):
        raise HTTPException(status_code=400, detail="percentile threshold must be 0..100")

    if req.target_type == "indicator":
        if req.target not in INDICATOR_NAMES:
            raise HTTPException(status_code=400, detail="Unknown indicator")
        target = req.target
    elif req.target_type == "stock_indicator":
        if not req.indicator_key:
            raise HTTPException(status_code=400, detail="stock_indicator requires indicator_key")
        if req.indicator_key not in STOCK_INDICATOR_KEYS:
            raise HTTPException(status_code=400, detail="Unknown indicator_key")
        if fundamentals_to_finmind_id(req.target) is None:
            raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) supported")
        # 交叉驗證:percentile 只支援 daily;yoy 只支援 monthly
        if is_percentile and req.indicator_key not in PERCENTILE_DAILY_KEYS:
            raise HTTPException(
                status_code=400,
                detail="percentile condition requires daily indicator (per/pbr/dividend_yield)"
            )
        if is_yoy and req.indicator_key not in STOCK_YOY_COMPATIBLE_KEYS:
            raise HTTPException(
                status_code=400,
                detail="yoy condition requires monthly/quarterly/yearly indicator"
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
