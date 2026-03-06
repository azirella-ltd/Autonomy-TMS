"""
Demand Plan API Endpoints.

Canonical forecast fields:
- forecast_p10
- forecast_p50
- forecast_p90
"""

import logging
from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, distinct, func, or_
from sqlalchemy.orm import Session

from app.api import deps
from app.core.capabilities import require_capabilities
from app.db.session import get_sync_db
from app.models.sc_entities import Forecast
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


class ForecastItemSchema(BaseModel):
    product_id: str
    site_id: str
    forecast_date: datetime
    forecast_p50: float
    forecast_median: Optional[float] = None
    forecast_p10: Optional[float] = None
    forecast_p90: Optional[float] = None
    forecast_type: Optional[str] = "statistical"
    forecast_method: Optional[str] = None
    forecast_source: Optional[str] = None
    forecast_run_id: Optional[str] = None
    forecast_confidence: Optional[float] = None
    conformal_method: Optional[str] = None


class ExternalDemandPlanSchema(BaseModel):
    plan_id: str
    plan_name: str
    effective_date: datetime
    created_by: str
    forecasts: List[ForecastItemSchema]


class DemandPlanVersionSchema(BaseModel):
    version_id: str
    version_name: str
    created_at: datetime
    created_by: str
    is_active: bool
    forecast_count: int


class DemandPlanDeltaSchema(BaseModel):
    product_id: str
    site_id: str
    forecast_date: datetime
    version1_p50: Optional[float]
    version2_p50: Optional[float]
    version1_median: Optional[float] = None
    version2_median: Optional[float] = None
    delta_p50: float
    delta_pct: Optional[float]
    change_type: str


class ForecastOverrideItem(BaseModel):
    product_id: str
    site_id: str
    forecast_date: datetime
    forecast_p10: Optional[float] = None
    forecast_p50: float
    forecast_median: Optional[float] = None
    forecast_p90: Optional[float] = None
    reason: Optional[str] = None


class ForecastOverrideRequest(BaseModel):
    overrides: List[ForecastOverrideItem]


class ForecastOverrideResponse(BaseModel):
    success: bool
    message: str
    updated_count: int
    created_count: int
    failed: List[str] = []


def _active_filter() -> object:
    """Support legacy active markers Y/N and true/false string values."""
    return or_(
        Forecast.is_active.in_(["Y", "y", "true", "TRUE", "1"]),
        Forecast.is_active.is_(None),
    )


@router.get("/current", response_model=List[ForecastItemSchema])
@require_capabilities(["view_demand_planning"])
def get_current_demand_plan(
    *,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_user),
    product_id: Optional[str] = None,
    site_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(1000, le=10000),
):
    query = db.query(Forecast).filter(_active_filter())

    if product_id:
        query = query.filter(Forecast.product_id == product_id)
    if site_id:
        query = query.filter(Forecast.site_id == site_id)
    if start_date:
        query = query.filter(Forecast.forecast_date >= start_date)
    if end_date:
        query = query.filter(Forecast.forecast_date <= end_date)

    forecasts = query.order_by(Forecast.forecast_date, Forecast.product_id).limit(limit).all()

    return [
        ForecastItemSchema(
            product_id=str(f.product_id),
            site_id=str(f.site_id),
            forecast_date=f.forecast_date,
            forecast_p50=float(f.forecast_p50) if f.forecast_p50 is not None else float(f.forecast_quantity or 0.0),
            forecast_median=float(f.forecast_median) if f.forecast_median is not None else (float(f.forecast_p50) if f.forecast_p50 is not None else float(f.forecast_quantity or 0.0)),
            forecast_p10=float(f.forecast_p10) if f.forecast_p10 is not None else None,
            forecast_p90=float(f.forecast_p90) if f.forecast_p90 is not None else None,
            forecast_type=f.forecast_type or "statistical",
            forecast_method=f.forecast_method,
            forecast_source=f.source,
            forecast_run_id=f.source_event_id,
        )
        for f in forecasts
    ]


@router.get("/versions", response_model=List[DemandPlanVersionSchema])
@require_capabilities(["view_demand_planning"])
def get_demand_plan_versions(
    *,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_user),
):
    rows = (
        db.query(
            Forecast.source_event_id.label("version_id"),
            func.max(Forecast.source_update_dttm).label("updated_at"),
            func.max(Forecast.created_dttm).label("created_at"),
            func.max(Forecast.created_by).label("created_by"),
            func.count(Forecast.id).label("forecast_count"),
        )
        .filter(_active_filter())
        .group_by(Forecast.source_event_id)
        .order_by(func.max(Forecast.source_update_dttm).desc(), func.max(Forecast.created_dttm).desc())
        .limit(20)
        .all()
    )

    output = []
    for row in rows:
        version_id = row.version_id or "legacy"
        created_at = row.updated_at or row.created_at or datetime.utcnow()
        output.append(
            DemandPlanVersionSchema(
                version_id=str(version_id),
                version_name=f"Forecast Run {version_id}",
                created_at=created_at,
                created_by=str(row.created_by or "system"),
                is_active=True,
                forecast_count=int(row.forecast_count or 0),
            )
        )
    return output


@router.get("/delta", response_model=List[DemandPlanDeltaSchema])
@require_capabilities(["view_demand_planning"])
def get_demand_plan_delta(
    *,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_user),
    version1: str = Query(...),
    version2: str = Query(...),
    product_id: Optional[str] = None,
    site_id: Optional[str] = None,
    min_delta_pct: float = Query(0.0),
):
    q1 = db.query(Forecast).filter(Forecast.source_event_id == version1)
    q2 = db.query(Forecast).filter(Forecast.source_event_id == version2)
    if product_id:
        q1 = q1.filter(Forecast.product_id == product_id)
        q2 = q2.filter(Forecast.product_id == product_id)
    if site_id:
        q1 = q1.filter(Forecast.site_id == site_id)
        q2 = q2.filter(Forecast.site_id == site_id)

    rows1 = q1.all()
    rows2 = q2.all()
    map1 = {(str(f.product_id), str(f.site_id), f.forecast_date): float(f.forecast_p50 or 0.0) for f in rows1}
    map2 = {(str(f.product_id), str(f.site_id), f.forecast_date): float(f.forecast_p50 or 0.0) for f in rows2}
    map1_median = {
        (str(f.product_id), str(f.site_id), f.forecast_date): float(f.forecast_median if f.forecast_median is not None else (f.forecast_p50 or 0.0))
        for f in rows1
    }
    map2_median = {
        (str(f.product_id), str(f.site_id), f.forecast_date): float(f.forecast_median if f.forecast_median is not None else (f.forecast_p50 or 0.0))
        for f in rows2
    }

    keys = sorted(set(map1.keys()) | set(map2.keys()), key=lambda x: (x[2], x[0], x[1]))
    deltas: List[DemandPlanDeltaSchema] = []
    for key in keys:
        v1 = map1.get(key)
        v2 = map2.get(key)
        if v1 is None:
            delta = float(v2 or 0.0)
            delta_pct = None
            change_type = "new"
        elif v2 is None:
            delta = -float(v1)
            delta_pct = -100.0
            change_type = "removed"
        else:
            delta = float(v2 - v1)
            delta_pct = (delta / v1 * 100.0) if v1 else None
            if delta > 0:
                change_type = "increase"
            elif delta < 0:
                change_type = "decrease"
            else:
                change_type = "unchanged"

        if delta_pct is not None and abs(delta_pct) < min_delta_pct:
            continue

        deltas.append(
            DemandPlanDeltaSchema(
                product_id=key[0],
                site_id=key[1],
                forecast_date=key[2],
                version1_p50=v1,
                version2_p50=v2,
                version1_median=map1_median.get(key),
                version2_median=map2_median.get(key),
                delta_p50=delta,
                delta_pct=delta_pct,
                change_type=change_type,
            )
        )
    return deltas


@router.post("/integrate", status_code=status.HTTP_201_CREATED)
@require_capabilities(["manage_demand_planning"])
def receive_external_demand_plan(
    *,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_user),
    demand_plan: ExternalDemandPlanSchema,
    background_tasks: BackgroundTasks,
):
    try:
        query = db.query(Forecast).filter(_active_filter())
        existing_forecasts = query.all()
        for f in existing_forecasts:
            f.is_active = "false"

        imported_count = 0
        for item in demand_plan.forecasts:
            site_id = int(item.site_id) if str(item.site_id).isdigit() else None
            new_row = Forecast(
                product_id=str(item.product_id),
                site_id=site_id,
                forecast_date=item.forecast_date,
                forecast_p50=float(item.forecast_p50),
                forecast_median=float(item.forecast_median) if item.forecast_median is not None else float(item.forecast_p50),
                forecast_p10=float(item.forecast_p10) if item.forecast_p10 is not None else None,
                forecast_p90=float(item.forecast_p90) if item.forecast_p90 is not None else None,
                forecast_quantity=float(item.forecast_p50),
                forecast_type=item.forecast_type or "external",
                forecast_method="external",
                source="external_demand_plan",
                source_event_id=demand_plan.plan_id,
                source_update_dttm=datetime.utcnow(),
                created_dttm=datetime.utcnow(),
                created_by=str(current_user.id),
                config_id=getattr(current_user, "config_id", None),
                is_active="true",
            )
            db.add(new_row)
            imported_count += 1

        product_site_pairs = list({(str(fi.product_id), int(fi.site_id)) for fi in demand_plan.forecasts if str(fi.site_id).isdigit()})
        if product_site_pairs and getattr(current_user, "tenant_id", None):
            background_tasks.add_task(
                _trigger_conformal_forecast_hook,
                product_site_pairs=product_site_pairs,
                tenant_id=current_user.tenant_id,
            )

        return {
            "status": "success",
            "plan_id": demand_plan.plan_id,
            "plan_name": demand_plan.plan_name,
            "effective_date": demand_plan.effective_date,
            "imported_count": imported_count,
            "updated_count": 0,
            "archived_count": len(existing_forecasts),
            "message": f"Successfully imported {imported_count} forecasts",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to import demand plan: {exc}")


@router.get("/summary")
@require_capabilities(["view_demand_planning"])
def get_demand_plan_summary(
    *,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_user),
):
    total_forecasts = db.query(func.count(Forecast.id)).filter(_active_filter()).scalar() or 0
    product_count = db.query(func.count(distinct(Forecast.product_id))).filter(_active_filter()).scalar() or 0
    site_count = db.query(func.count(distinct(Forecast.site_id))).filter(_active_filter()).scalar() or 0
    start_date, end_date = db.query(func.min(Forecast.forecast_date), func.max(Forecast.forecast_date)).filter(_active_filter()).first()

    # Compute average demand per forecast period (meaningful metric)
    avg_demand = db.query(func.avg(Forecast.forecast_p50)).filter(_active_filter()).scalar() or 0.0
    avg_demand_median = db.query(func.avg(Forecast.forecast_median)).filter(_active_filter()).scalar()
    if not avg_demand_median:
        avg_demand_median = avg_demand

    # Count distinct forecast periods (weeks) for context
    period_count = db.query(func.count(distinct(Forecast.forecast_date))).filter(_active_filter()).scalar() or 0

    return {
        "total_forecasts": int(total_forecasts),
        "product_count": int(product_count),
        "site_count": int(site_count),
        "period_count": int(period_count),
        "start_date": start_date,
        "end_date": end_date,
        "avg_demand_p50": round(float(avg_demand), 1),
        "avg_demand_median": round(float(avg_demand_median), 1),
    }


@router.post("/override", response_model=ForecastOverrideResponse)
@require_capabilities(["manage_demand_planning"])
def apply_forecast_overrides(
    *,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_user),
    request: ForecastOverrideRequest,
    background_tasks: BackgroundTasks,
):
    updated_count = 0
    created_count = 0
    failed: List[str] = []

    for override in request.overrides:
        try:
            site_id = int(override.site_id) if str(override.site_id).isdigit() else None
            existing = (
                db.query(Forecast)
                .filter(
                    and_(
                        Forecast.product_id == str(override.product_id),
                        Forecast.site_id == site_id,
                        Forecast.forecast_date == override.forecast_date,
                        _active_filter(),
                    )
                )
                .first()
            )

            if existing:
                existing.forecast_p10 = float(override.forecast_p10) if override.forecast_p10 is not None else existing.forecast_p10
                existing.forecast_p50 = float(override.forecast_p50)
                existing.forecast_median = float(override.forecast_median) if override.forecast_median is not None else float(override.forecast_p50)
                existing.forecast_p90 = float(override.forecast_p90) if override.forecast_p90 is not None else existing.forecast_p90
                existing.forecast_quantity = float(override.forecast_p50)
                existing.user_override_quantity = float(override.forecast_p50)
                existing.override_reason = override.reason
                existing.forecast_type = "override"
                existing.forecast_method = existing.forecast_method or "manual"
                existing.source = existing.source or "manual"
                existing.source_update_dttm = datetime.utcnow()
                updated_count += 1
            else:
                db.add(
                    Forecast(
                        product_id=str(override.product_id),
                        site_id=site_id,
                        forecast_date=override.forecast_date,
                        forecast_p50=float(override.forecast_p50),
                        forecast_median=float(override.forecast_median) if override.forecast_median is not None else float(override.forecast_p50),
                        forecast_p10=float(override.forecast_p10) if override.forecast_p10 is not None else None,
                        forecast_p90=float(override.forecast_p90) if override.forecast_p90 is not None else None,
                        forecast_quantity=float(override.forecast_p50),
                        user_override_quantity=float(override.forecast_p50),
                        override_reason=override.reason,
                        forecast_type="override",
                        forecast_method="manual",
                        source="manual_override",
                        source_update_dttm=datetime.utcnow(),
                        created_dttm=datetime.utcnow(),
                        created_by=str(current_user.id),
                        is_active="true",
                    )
                )
                created_count += 1

        except Exception as exc:
            failed.append(f"{override.product_id}/{override.site_id}/{override.forecast_date}: {exc}")

    product_site_pairs = [
        (str(o.product_id), int(o.site_id))
        for o in request.overrides
        if str(o.site_id).isdigit()
    ]
    if product_site_pairs and getattr(current_user, "tenant_id", None):
        background_tasks.add_task(
            _trigger_conformal_forecast_hook,
            product_site_pairs=list(set(product_site_pairs)),
            tenant_id=current_user.tenant_id,
        )

    return ForecastOverrideResponse(
        success=len(failed) == 0,
        message=f"Applied {updated_count + created_count} overrides ({updated_count} updated, {created_count} created)",
        updated_count=updated_count,
        created_count=created_count,
        failed=failed,
    )


async def _trigger_conformal_forecast_hook(
    product_site_pairs: List[Tuple[str, int]],
    tenant_id: int,
) -> None:
    """Background task: notify conformal orchestrator of forecast load."""
    from app.db.session import async_session_factory
    from app.services.conformal_orchestrator import ConformalOrchestrator

    try:
        if async_session_factory is None:
            return
        async with async_session_factory() as db:
            orchestrator = ConformalOrchestrator.get_instance()
            result = await orchestrator.on_forecasts_loaded(db, product_site_pairs, tenant_id)
            await db.commit()
            logger.info(f"Conformal forecast hook: {result}")
    except Exception as exc:
        logger.error(f"Conformal forecast hook failed: {exc}")
