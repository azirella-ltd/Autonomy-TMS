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
from app.services.user_scope_service import resolve_user_scope_sync, resolve_site_names_to_ids_sync

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_product_node_ids(db: Session, node_id: int, tenant_id: int) -> List[str]:
    """Resolve a product hierarchy node to all descendant product IDs.

    Walks the product_hierarchy_node tree recursively and collects
    product_id from leaf nodes (PRODUCT level).
    """
    from sqlalchemy import text as sqt
    try:
        rows = db.execute(sqt("""
            WITH RECURSIVE tree AS (
                SELECT id, product_id FROM product_hierarchy_node WHERE id = :nid AND tenant_id = :tid
                UNION ALL
                SELECT n.id, n.product_id FROM product_hierarchy_node n
                JOIN tree t ON n.parent_id = t.id
            )
            SELECT product_id FROM tree WHERE product_id IS NOT NULL
        """), {"nid": node_id, "tid": tenant_id}).fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []


def _apply_scope_filters(query, db, current_user, config_id=None):
    """Apply user scope filtering to a Forecast query."""
    allowed_sites, allowed_products = resolve_user_scope_sync(current_user)
    if allowed_sites is not None and config_id:
        site_ids = resolve_site_names_to_ids_sync(db, allowed_sites, config_id)
        if site_ids:
            query = query.filter(Forecast.site_id.in_(site_ids))
    if allowed_products is not None:
        query = query.filter(Forecast.product_id.in_(allowed_products))
    return query


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
    product_node_id: Optional[int] = Query(None, description="Product hierarchy node ID"),
    site_id: Optional[str] = None,
    category: Optional[str] = Query(None, description="Product category filter (legacy)"),
    family: Optional[str] = Query(None, description="Product family filter (legacy)"),
    geo_id: Optional[str] = Query(None, description="Geography node ID (drills into children)"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    config_id: Optional[int] = None,
    limit: int = Query(1000, le=10000),
):
    from app.models.supply_chain_config import Site
    from app.models.sc_entities import Product
    from sqlalchemy import text as sqt

    query = db.query(Forecast).filter(_active_filter())

    # Config scope — use explicit param, fall back to user's default
    # SOC II: NEVER return unscoped data — if no config, return empty
    effective_config_id = config_id or (current_user.default_config_id if current_user else None)
    if not effective_config_id:
        return []
    query = query.filter(Forecast.config_id == effective_config_id)

    # User scope filtering — restrict to sites/products the user can access
    query = _apply_scope_filters(query, db, current_user, effective_config_id)

    if product_id:
        query = query.filter(Forecast.product_id == product_id)
    elif product_node_id:
        pids = _resolve_product_node_ids(db, product_node_id, current_user.tenant_id)
        if pids:
            query = query.filter(Forecast.product_id.in_(pids))
    elif category:
        pids = [p[0] for p in db.query(Product.id).filter(
            Product.config_id == effective_config_id, Product.category == category).all()]
        if pids:
            query = query.filter(Forecast.product_id.in_(pids))
    elif family:
        pids = [p[0] for p in db.query(Product.id).filter(
            Product.config_id == effective_config_id, Product.family == family).all()]
        if pids:
            query = query.filter(Forecast.product_id.in_(pids))

    if site_id:
        query = query.filter(Forecast.site_id == site_id)
    elif geo_id:
        # Recursive geography drilldown
        try:
            geo_sites = db.execute(sqt("""
                WITH RECURSIVE geo_tree AS (
                    SELECT id FROM geography WHERE id = :gid
                    UNION ALL
                    SELECT g.id FROM geography g JOIN geo_tree gt ON g.parent_geo_id = gt.id
                )
                SELECT CAST(s.id AS TEXT) FROM site s
                WHERE s.config_id = :cfg AND (
                    s.geo_id IN (SELECT id FROM geo_tree)
                    OR s.id IN (
                        SELECT tl.from_site_id FROM transportation_lane tl
                        JOIN site dst ON dst.id = tl.to_site_id
                        WHERE tl.config_id = :cfg AND dst.geo_id IN (SELECT id FROM geo_tree)
                    )
                )
            """), {"gid": geo_id, "cfg": effective_config_id}).fetchall()
            sids = [s[0] for s in geo_sites]
            if sids:
                query = query.filter(Forecast.site_id.in_(sids))
        except Exception:
            pass
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
    config_id: Optional[int] = None,
):
    effective_config_id = config_id or (current_user.default_config_id if current_user else None)
    base_filter = _active_filter()
    if effective_config_id:
        base_filter = and_(base_filter, Forecast.config_id == effective_config_id)

    rows = (
        db.query(
            Forecast.source_event_id.label("version_id"),
            func.max(Forecast.source_update_dttm).label("updated_at"),
            func.max(Forecast.created_dttm).label("created_at"),
            func.max(Forecast.created_by).label("created_by"),
            func.count(Forecast.id).label("forecast_count"),
        )
        .filter(base_filter)
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
    config_id: Optional[int] = None,
    min_delta_pct: float = Query(0.0),
):
    effective_config_id = config_id or (current_user.default_config_id if current_user else None)
    q1 = db.query(Forecast).filter(Forecast.source_event_id == version1)
    q2 = db.query(Forecast).filter(Forecast.source_event_id == version2)
    if effective_config_id:
        q1 = q1.filter(Forecast.config_id == effective_config_id)
        q2 = q2.filter(Forecast.config_id == effective_config_id)
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
    config_id: Optional[int] = None,
    product_node_id: Optional[int] = Query(None, description="Product hierarchy node ID"),
    category: Optional[str] = Query(None),
    family: Optional[str] = Query(None),
    geo_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
):
    from app.models.supply_chain_config import Site
    from app.models.sc_entities import Product
    from sqlalchemy import text as sqt

    effective_config_id = config_id or (current_user.default_config_id if current_user else None)

    def _base():
        f = _active_filter()
        if effective_config_id:
            return and_(f, Forecast.config_id == effective_config_id)
        return f

    query_base = db.query(Forecast).filter(_base())

    # Apply hierarchy filters
    if product_node_id:
        pids = _resolve_product_node_ids(db, product_node_id, current_user.tenant_id)
        if pids:
            query_base = query_base.filter(Forecast.product_id.in_(pids))
    elif category and effective_config_id:
        pids = [p[0] for p in db.query(Product.id).filter(
            Product.config_id == effective_config_id, Product.category == category).all()]
        if pids:
            query_base = query_base.filter(Forecast.product_id.in_(pids))
    elif family and effective_config_id:
        pids = [p[0] for p in db.query(Product.id).filter(
            Product.config_id == effective_config_id, Product.family == family).all()]
        if pids:
            query_base = query_base.filter(Forecast.product_id.in_(pids))
    if site_id:
        query_base = query_base.filter(Forecast.site_id == site_id)
    elif geo_id and effective_config_id:
        try:
            geo_sites = db.execute(sqt("""
                WITH RECURSIVE geo_tree AS (
                    SELECT id FROM geography WHERE id = :gid
                    UNION ALL
                    SELECT g.id FROM geography g JOIN geo_tree gt ON g.parent_geo_id = gt.id
                )
                SELECT CAST(s.id AS TEXT) FROM site s
                WHERE s.config_id = :cfg AND (
                    s.geo_id IN (SELECT id FROM geo_tree)
                    OR s.id IN (
                        SELECT tl.from_site_id FROM transportation_lane tl
                        JOIN site dst ON dst.id = tl.to_site_id
                        WHERE tl.config_id = :cfg AND dst.geo_id IN (SELECT id FROM geo_tree)
                    )
                )
            """), {"gid": geo_id, "cfg": effective_config_id}).fetchall()
            sids = [s[0] for s in geo_sites]
            if sids:
                query_base = query_base.filter(Forecast.site_id.in_(sids))
        except Exception:
            pass

    total_forecasts = query_base.with_entities(func.count(Forecast.id)).scalar() or 0
    product_count = query_base.with_entities(func.count(distinct(Forecast.product_id))).scalar() or 0
    site_count = query_base.with_entities(func.count(distinct(Forecast.site_id))).scalar() or 0
    start_date, end_date = query_base.with_entities(func.min(Forecast.forecast_date), func.max(Forecast.forecast_date)).first()

    # Compute average demand per forecast period (meaningful metric)
    avg_demand = query_base.with_entities(func.avg(Forecast.forecast_p50)).scalar() or 0.0
    avg_demand_median = query_base.with_entities(func.avg(Forecast.forecast_median)).scalar()
    if not avg_demand_median:
        avg_demand_median = avg_demand

    # Count distinct forecast periods (weeks) for context
    period_count = query_base.with_entities(func.count(distinct(Forecast.forecast_date))).scalar() or 0

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


# ---------------------------------------------------------------------------
# Hierarchical aggregation — dynamic dimensions from DAG
# ---------------------------------------------------------------------------

@router.get("/hierarchy-dimensions")
def get_hierarchy_dimensions(
    config_id: int = Query(...),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Return available hierarchy dimensions for filtering, derived from the DAG.

    Dimensions are dynamic — they come from actual product/site data in the config,
    not hardcoded lists.
    """
    from app.models.supply_chain_config import Site
    from app.models.sc_entities import Product, Geography, Segmentation
    from sqlalchemy import text

    # Product hierarchy tree (from AWS SC DM product_hierarchy_node)
    from app.models.planning_hierarchy import ProductHierarchyNode
    product_tree = []
    try:
        phn_rows = db.query(ProductHierarchyNode).filter(
            ProductHierarchyNode.tenant_id == current_user.tenant_id,
        ).order_by(ProductHierarchyNode.hierarchy_level, ProductHierarchyNode.name).all()
        for n in phn_rows:
            product_tree.append({
                "id": n.id, "name": n.name, "parent_id": n.parent_id,
                "level": n.hierarchy_level, "product_id": n.product_id,
            })
    except Exception as e:
        logger.warning("Product hierarchy tree load failed: %s", e)

    # Geography hierarchy — dynamically derived from the tenant's own data.
    #
    # The tree MUST come from whichever geo_ids this config's sites actually
    # reference. Earlier code filtered by `company_id`, which produced a
    # hardcoded hierarchy that often didn't match `site.geo_id` values
    # (multiple parallel hierarchies exist in the geography table). That
    # broke the drill-down below Region level because the IDs the UI sent
    # couldn't be matched to any site.
    #
    # The correct approach: start from the distinct geo_ids referenced by
    # sites in this config, then walk upward via parent_geo_id to collect
    # every ancestor. The result is a per-tenant tree guaranteed to match
    # `site.geo_id`, which makes filtering consistent at every level.
    geo_tree = []
    try:
        geo_rows = db.execute(text("""
            WITH RECURSIVE ancestors AS (
                SELECT g.id, g.description, g.parent_geo_id, g.state_prov, g.city
                FROM geography g
                WHERE g.id IN (
                    SELECT DISTINCT geo_id FROM site
                    WHERE config_id = :cfg AND geo_id IS NOT NULL
                )
                UNION
                SELECT g.id, g.description, g.parent_geo_id, g.state_prov, g.city
                FROM geography g
                JOIN ancestors a ON a.parent_geo_id = g.id
            )
            SELECT id, description, parent_geo_id, state_prov, city
            FROM ancestors
            ORDER BY parent_geo_id NULLS FIRST, description
        """), {"cfg": config_id}).fetchall()
        for g in geo_rows:
            geo_tree.append({
                "id": g[0], "name": g[1], "parent_id": g[2],
                "state": g[3], "city": g[4],
            })
    except Exception as e:
        logger.warning("Dynamic geography tree build failed: %s", e)

    # Sites with geo linkage
    sites = db.query(Site.id, Site.name, Site.type, Site.geo_id).filter(
        Site.config_id == config_id,
    ).all()

    # Channel segmentation (AWS SC DM segmentation table)
    channels = []
    try:
        seg_rows = db.query(Segmentation).filter(
            Segmentation.segment_type == "channel",
            Segmentation.is_active == True,
        ).all()
        channels = [{"id": s.id, "name": s.name, "classification": s.classification} for s in seg_rows]
    except Exception:
        pass

    # Distinct products and sites that appear in forecasts (for table filter dropdowns)
    forecast_products = []
    forecast_sites = []
    try:
        fp_rows = db.execute(text("""
            SELECT DISTINCT f.product_id,
                   COALESCE(p.description, p.id, f.product_id) AS product_name
            FROM forecast f
            LEFT JOIN product p ON p.id = f.product_id AND p.config_id = f.config_id
            WHERE f.config_id = :cfg AND f.forecast_p50 IS NOT NULL
            ORDER BY product_name
        """), {"cfg": config_id}).fetchall()
        forecast_products = [{"id": r[0], "name": r[1]} for r in fp_rows]

        fs_rows = db.execute(text("""
            SELECT DISTINCT f.site_id, s.name AS site_name, s.type AS site_type, s.geo_id
            FROM forecast f
            JOIN site s ON CAST(s.id AS TEXT) = f.site_id AND s.config_id = f.config_id
            WHERE f.config_id = :cfg AND f.forecast_p50 IS NOT NULL
            ORDER BY s.name
        """), {"cfg": config_id}).fetchall()
        forecast_sites = [{"id": r[0], "name": r[1], "type": r[2], "geo_id": r[3]} for r in fs_rows]
    except Exception as e:
        logger.warning("Forecast product/site list failed: %s", e)

    return {
        "product_tree": product_tree,
        "geography": geo_tree,
        "sites": [{"id": s[0], "name": s[1], "type": s[2], "geo_id": s[3]} for s in sites],
        "forecast_products": forecast_products,
        "forecast_sites": forecast_sites,
        "channels": channels,
        "time_buckets": ["day", "week", "month"],
    }


@router.get("/aggregated")
def get_aggregated_forecast(
    config_id: int = Query(...),
    time_bucket: str = Query("week", description="day, week, or month"),
    product_node_id: Optional[int] = Query(None, description="Product hierarchy node ID"),
    category: Optional[str] = Query(None, description="Product category filter (legacy)"),
    family: Optional[str] = Query(None, description="Product family filter (legacy)"),
    product_id: Optional[str] = Query(None, description="Specific product"),
    geo_id: Optional[str] = Query(None, description="Geography node ID (drills into children)"),
    site_id: Optional[str] = Query(None, description="Specific site"),
    channel: Optional[str] = Query(None, description="Channel segmentation filter"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Aggregate forecasts by time bucket with hierarchy filtering.

    Supports drilldown via product_hierarchy_node tree and geography tree.
    """
    from app.models.supply_chain_config import Site
    from app.models.sc_entities import Product
    from sqlalchemy import text

    # Build product filter
    product_filters = []
    if product_id:
        product_filters.append(f"f.product_id = '{product_id}'")
    elif product_node_id:
        pids = _resolve_product_node_ids(db, product_node_id, current_user.tenant_id)
        if pids:
            pid_list = ",".join(f"'{p}'" for p in pids)
            product_filters.append(f"f.product_id IN ({pid_list})")
        else:
            return {"series": [], "summary": {"total_records": 0}}
    else:
        if category:
            # Get product_ids in this category
            prods = db.query(Product.id).filter(
                Product.config_id == config_id, Product.category == category,
            ).all()
            pids = [p[0] for p in prods]
            if pids:
                pid_list = ",".join(f"'{p}'" for p in pids)
                product_filters.append(f"f.product_id IN ({pid_list})")
            else:
                return {"series": [], "summary": {"total_records": 0}}
        if family:
            prods = db.query(Product.id).filter(
                Product.config_id == config_id, Product.family == family,
            ).all()
            pids = [p[0] for p in prods]
            if pids:
                pid_list = ",".join(f"'{p}'" for p in pids)
                product_filters.append(f"f.product_id IN ({pid_list})")
            else:
                return {"series": [], "summary": {"total_records": 0}}

    # Build site filter (geography-based drilldown)
    site_filters = []
    sids = []  # Track resolved site IDs for actuals query reuse
    if site_id:
        site_filters.append(f"f.site_id = {site_id}")
    elif geo_id:
        # Find all sites within this geography node and its descendants
        # Uses recursive CTE to walk the geography tree
        try:
            geo_sites = db.execute(text("""
                WITH RECURSIVE geo_tree AS (
                    SELECT id FROM geography WHERE id = :gid
                    UNION ALL
                    SELECT g.id FROM geography g JOIN geo_tree gt ON g.parent_geo_id = gt.id
                )
                SELECT CAST(s.id AS TEXT) FROM site s
                WHERE s.config_id = :cfg AND (
                    s.geo_id IN (SELECT id FROM geo_tree)
                    OR s.id IN (
                        SELECT tl.from_site_id FROM transportation_lane tl
                        JOIN site dst ON dst.id = tl.to_site_id
                        WHERE tl.config_id = :cfg AND dst.geo_id IN (SELECT id FROM geo_tree)
                    )
                )
            """), {"gid": geo_id, "cfg": config_id}).fetchall()
            sids = [str(s[0]) for s in geo_sites]
            if sids:
                quoted = ",".join(f"'{s}'" for s in sids)
                site_filters.append(f"f.site_id IN ({quoted})")
            else:
                return {"series": [], "summary": {"total_records": 0}}
        except Exception as e:
            logger.warning("Geography filter failed: %s", e)

    # Time bucket truncation
    trunc_map = {"day": "day", "week": "week", "month": "month"}
    trunc = trunc_map.get(time_bucket, "week")

    # Build WHERE clause
    where_parts = [f"f.config_id = {config_id}", "f.forecast_p50 IS NOT NULL"]
    where_parts.extend(product_filters)
    where_parts.extend(site_filters)
    if start_date:
        where_parts.append(f"f.forecast_date >= '{start_date}'")
    if end_date:
        where_parts.append(f"f.forecast_date <= '{end_date}'")

    where_clause = " AND ".join(where_parts)

    # Forecast query
    sql = f"""
        SELECT
            date_trunc('{trunc}', f.forecast_date) AS bucket,
            SUM(f.forecast_p10) AS p10,
            SUM(f.forecast_p50) AS p50,
            SUM(f.forecast_p90) AS p90,
            COUNT(*) AS record_count,
            COUNT(DISTINCT f.product_id) AS product_count,
            COUNT(DISTINCT f.site_id) AS site_count
        FROM forecast f
        WHERE {where_clause}
        GROUP BY date_trunc('{trunc}', f.forecast_date)
        ORDER BY bucket
    """

    try:
        result = db.execute(text(sql))
        rows = result.fetchall()
    except Exception as e:
        logger.warning("Aggregated forecast query failed: %s", e)
        return {"series": [], "summary": {"total_records": 0, "error": str(e)}}

    # Build series with forecast data
    series_map = {}
    for row in rows:
        d = row[0].strftime("%Y-%m-%d") if row[0] else None
        series_map[d] = {
            "date": d,
            "p10": round(float(row[1] or 0), 1),
            "p50": round(float(row[2] or 0), 1),
            "p90": round(float(row[3] or 0), 1),
            "actual": None,
            "records": row[4],
            "products": row[5],
            "sites": row[6],
        }

    # Overlay actuals from outbound_order_line (real fulfilled demand)
    try:
        actual_parts = [f"ool.config_id = {config_id}"]
        # Mirror product filters
        if product_id:
            actual_parts.append(f"ool.product_id = '{product_id}'")
        elif product_node_id:
            pids = _resolve_product_node_ids(db, product_node_id, current_user.tenant_id)
            if pids:
                actual_parts.append(f"ool.product_id IN ({','.join(repr(p) for p in pids)})")
        elif category:
            prods = db.query(Product.id).filter(Product.config_id == config_id, Product.category == category).all()
            if prods:
                actual_parts.append(f"ool.product_id IN ({','.join(repr(p[0]) for p in prods)})")
        # Mirror site filters — use ship_from_site_id on outbound_order
        if site_id:
            actual_parts.append(f"oo.ship_from_site_id = {site_id}")
        elif geo_id:
            # Reuse the sids we already computed for the forecast query
            if sids:
                actual_parts.append(f"CAST(oo.ship_from_site_id AS TEXT) IN ({','.join(repr(s) for s in sids)})")
        if start_date:
            actual_parts.append(f"oo.order_date >= '{start_date}'")
        if end_date:
            actual_parts.append(f"oo.order_date <= '{end_date}'")

        actual_where = " AND ".join(actual_parts)
        actual_sql = f"""
            SELECT
                date_trunc('{trunc}', oo.order_date) AS bucket,
                SUM(COALESCE(ool.shipped_quantity, ool.ordered_quantity)) AS actual_demand
            FROM outbound_order_line ool
            JOIN outbound_order oo ON oo.id = ool.order_id
            WHERE {actual_where}
            GROUP BY date_trunc('{trunc}', oo.order_date)
            ORDER BY bucket
        """
        actual_result = db.execute(text(actual_sql))
        for arow in actual_result.fetchall():
            d = arow[0].strftime("%Y-%m-%d") if arow[0] else None
            if d in series_map:
                series_map[d]["actual"] = round(float(arow[1] or 0), 1)
            elif d:
                series_map[d] = {
                    "date": d, "p10": None, "p50": None, "p90": None,
                    "actual": round(float(arow[1] or 0), 1),
                    "records": 0, "products": 0, "sites": 0,
                }
    except Exception as e:
        logger.warning("Actuals overlay failed: %s", e)

    # Build response
    series = sorted(series_map.values(), key=lambda x: x["date"] or "")
    total_records = sum(s.get("records", 0) for s in series)
    return {
        "series": series,
        "summary": {
            "total_records": total_records,
            "buckets": len(series),
            "time_bucket": time_bucket,
        },
    }


@router.get("/grid")
def get_plan_grid(
    config_id: int = Query(...),
    time_bucket: str = Query("week"),
    product_node_id: Optional[int] = Query(None),
    geo_id: Optional[str] = Query(None),
    weeks: int = Query(12, le=52, description="Number of weeks to show"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Kinaxis-style MPS grid: product×site rows × week columns.

    Returns the Plan of Record pivoted for grid display.
    Each row = one product at one site.
    Each column = one week with planned quantity.
    """
    from app.models.supply_chain_config import Site
    from app.models.sc_entities import Product

    # Build filters
    product_filter = ""
    site_filter = ""
    params = {"cfg": config_id, "weeks": weeks}

    if product_node_id:
        pids = _resolve_product_node_ids(db, product_node_id, current_user.tenant_id)
        if pids:
            product_filter = f"AND sp.product_id IN ({','.join(repr(p) for p in pids)})"

    if geo_id:
        try:
            geo_sites = db.execute(text("""
                WITH RECURSIVE geo_tree AS (
                    SELECT id FROM geography WHERE id = :gid
                    UNION ALL
                    SELECT g.id FROM geography g JOIN geo_tree gt ON g.parent_geo_id = gt.id
                )
                SELECT CAST(s.id AS TEXT) FROM site s
                WHERE s.config_id = :cfg AND (
                    s.geo_id IN (SELECT id FROM geo_tree)
                    OR s.id IN (
                        SELECT tl.from_site_id FROM transportation_lane tl
                        JOIN site dst ON dst.id = tl.to_site_id
                        WHERE tl.config_id = :cfg AND dst.geo_id IN (SELECT id FROM geo_tree)
                    )
                )
            """), {"gid": geo_id, "cfg": config_id}).fetchall()
            sids = [s[0] for s in geo_sites]
            if sids:
                site_filter = f"AND CAST(sp.site_id AS TEXT) IN ({','.join(repr(s) for s in sids)})"
        except Exception:
            pass

    # Get weeks (columns)
    week_rows = db.execute(text(f"""
        SELECT DISTINCT plan_date FROM supply_plan
        WHERE config_id = :cfg AND plan_version = 'live'
        AND plan_date >= CURRENT_DATE - INTERVAL '4 weeks'
        {product_filter} {site_filter}
        ORDER BY plan_date
        LIMIT :weeks
    """), params).fetchall()
    week_dates = [r[0].strftime("%Y-%m-%d") for r in week_rows]

    if not week_dates:
        return {"columns": [], "rows": [], "total_rows": 0}

    # Week labels (W01, W02, ...)
    columns = []
    for d in week_dates:
        from datetime import datetime as dt
        parsed = dt.strptime(d, "%Y-%m-%d")
        columns.append({
            "date": d,
            "label": f"W{parsed.isocalendar()[1]:02d}",
            "month": parsed.strftime("%b"),
        })

    # Get product×site rows with pivoted weekly quantities
    grid_rows = db.execute(text(f"""
        SELECT
            sp.product_id,
            SPLIT_PART(p.description, ' - ', 1) AS product_name,
            p.category, p.family,
            sp.site_id,
            s.name AS site_name,
            sp.plan_date,
            sp.planned_order_quantity
        FROM supply_plan sp
        JOIN product p ON p.id = sp.product_id
        JOIN site s ON s.id = sp.site_id
        WHERE sp.config_id = :cfg AND sp.plan_version = 'live'
        AND sp.plan_date >= CURRENT_DATE - INTERVAL '4 weeks'
        {product_filter} {site_filter}
        ORDER BY p.category, p.family, sp.product_id, sp.site_id, sp.plan_date
    """), params).fetchall()

    # Pivot into rows
    row_map = {}
    for r in grid_rows:
        key = f"{r[0]}|{r[4]}"
        if key not in row_map:
            row_map[key] = {
                "product_id": r[0],
                "product_name": r[1],
                "category": r[2],
                "family": r[3],
                "site_id": r[4],
                "site_name": r[5],
                "weeks": {},
            }
        d = r[6].strftime("%Y-%m-%d")
        row_map[key]["weeks"][d] = round(float(r[7] or 0), 0)

    rows = list(row_map.values())

    return {
        "columns": columns,
        "rows": rows,
        "total_rows": len(rows),
    }

    series = sorted(series_map.values(), key=lambda x: x["date"] or "")

    return {
        "series": series,
        "summary": {
            "total_records": sum(s["records"] for s in series),
            "total_products": max((s["products"] for s in series), default=0),
            "total_sites": max((s["sites"] for s in series), default=0),
            "time_bucket": time_bucket,
            "filters": {
                "category": category,
                "family": family,
                "product_id": product_id,
                "geo_id": geo_id,
                "site_id": site_id,
            },
        },
    }
