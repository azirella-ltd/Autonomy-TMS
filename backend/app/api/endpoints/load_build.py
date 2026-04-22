"""
Load Build TRM API — Shipment→Load consolidation (BUILD phase)

Seventh TMS-native TRM endpoint. Operates on shipment groups clustered
by (origin, destination, mode, pickup-day) rather than individual
entities. Returns ACCEPT / CONSOLIDATE / SPLIT / DEFER / REJECT per
group.

Endpoints:
  POST /load-build/evaluate-all               — every DRAFT group for tenant
  POST /load-build/evaluate-group             — one group by query params
                                                (?origin_site_id=&destination_site_id=&mode=&pickup_date=YYYY-MM-DD)

No single-shipment `evaluate/{id}` endpoint because LoadBuild is a
group-level decision. To evaluate a specific shipment's group, pass
its origin/dest/mode/pickup-day to evaluate-group.
"""
import logging
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.tms_entities import ShipmentStatus, TMSShipment
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/load-build", tags=["load-build"])


class LoadBuildResult(BaseModel):
    origin_site_id: int
    destination_site_id: int
    mode: str
    pickup_date: Optional[str] = None
    shipment_ids: List[int]
    shipment_count: int
    total_weight: float = 0.0
    total_volume: float = 0.0
    total_pallets: int = 0
    weight_util_pct: float = 0.0
    volume_util_pct: float = 0.0
    stop_count: int = 1
    has_hazmat_conflict: bool = False
    has_temp_conflict: bool = False
    ftl_rate: float = 0.0
    ltl_rate_sum: float = 0.0
    consolidation_savings: float = 0.0
    optimal_mode: Optional[str] = None
    total_savings: Optional[float] = None
    action_name: str
    confidence: float = 1.0
    urgency: float = 0.3
    reasoning: str = ""
    decision_method: str = "heuristic"


@router.post("/evaluate-all", response_model=List[LoadBuildResult])
async def evaluate_all_groups(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate every DRAFT-shipment group for the current tenant.

    Shipments are grouped by (origin, destination, mode, pickup-day).
    Single-shipment groups still evaluate — the TRM can return LTL-accept
    or DEFER on them.

    SYSTEM_ADMIN (tenant_id=None) returns [] — load-build is tenant-scoped.
    """
    from app.db.session import sync_session_factory

    if user.tenant_id is None:
        return []

    with sync_session_factory() as sync_db:
        from app.services.powell.load_build_trm import LoadBuildTRM
        trm = LoadBuildTRM(sync_db, user.tenant_id, 0)
        results = trm.evaluate_all_groups()
        return [
            LoadBuildResult(**{
                k: v for k, v in r.items()
                if k in LoadBuildResult.model_fields
            })
            for r in results
        ]


@router.post("/evaluate-group", response_model=LoadBuildResult)
async def evaluate_specific_group(
    origin_site_id: int = Query(..., description="Origin Site.id"),
    destination_site_id: int = Query(..., description="Destination Site.id"),
    mode: str = Query(..., description="TransportMode value (FTL, LTL, etc.)"),
    pickup_date: Optional[date] = Query(
        None, description="Grouping pickup day (YYYY-MM-DD). None groups NULL-date shipments."
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate a single shipment group identified by (origin, destination,
    mode, pickup_date).

    Returns 404 if no DRAFT shipments match the grouping key.
    """
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        # Resolve effective tenant (SYSTEM_ADMIN uses the first shipment's
        # tenant as a convenience — matches the pattern in the other TRMs).
        effective_tenant_id = user.tenant_id
        if effective_tenant_id is None:
            first = sync_db.execute(
                select(TMSShipment).where(
                    TMSShipment.origin_site_id == origin_site_id
                ).limit(1)
            ).scalar_one_or_none()
            if not first:
                raise HTTPException(
                    404,
                    f"No shipments found for origin={origin_site_id}",
                )
            effective_tenant_id = first.tenant_id

        q = select(TMSShipment).where(
            and_(
                TMSShipment.tenant_id == effective_tenant_id,
                TMSShipment.status == ShipmentStatus.DRAFT,
                TMSShipment.origin_site_id == origin_site_id,
                TMSShipment.destination_site_id == destination_site_id,
            )
        )
        all_matching = sync_db.execute(q).scalars().all()

        # Filter by mode + pickup_date in Python (mode is an enum stored
        # as a PG enum; same-day grouping needs date truncation that's
        # awkward in SQLAlchemy without a function expression).
        group = []
        for s in all_matching:
            if (s.mode.value if s.mode else "FTL") != mode:
                continue
            s_day = (
                s.requested_pickup_date.date()
                if s.requested_pickup_date else None
            )
            if s_day != pickup_date:
                continue
            group.append(s)

        if not group:
            raise HTTPException(
                404,
                f"No DRAFT shipments for ({origin_site_id}→{destination_site_id}, "
                f"mode={mode}, pickup_date={pickup_date})",
            )

        from app.services.powell.load_build_trm import LoadBuildTRM
        trm = LoadBuildTRM(sync_db, effective_tenant_id, 0)
        result = trm.evaluate_and_log(
            group, origin_site_id, destination_site_id, mode, pickup_date,
        )
        if not result:
            raise HTTPException(422, "No load-build decision produced")

        return LoadBuildResult(**{
            k: v for k, v in result.items()
            if k in LoadBuildResult.model_fields
        })
