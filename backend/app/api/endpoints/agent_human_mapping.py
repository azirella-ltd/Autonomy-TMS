"""Agent-Human Mapping API — topology-based user recommendations for a config."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db as get_async_db
from app.core.security import get_current_active_user
from app.models.user import User, UserTypeEnum
from app.models.supply_chain_config import Site, TransportationLane

router = APIRouter()


# ---------- Response schemas ----------

class SiteAnalysisItem(BaseModel):
    site_key: str
    site_name: str
    master_type: str
    role: str
    active_trm_count: int
    human_trm_count: int
    human_trms: List[str]


class UserRecommendationItem(BaseModel):
    decision_level: str
    site_scope: List[str]
    product_scope: Optional[List[str]] = None
    trm_types_covered: List[str]
    site_names: List[str]
    rationale: str


class MappingRecommendationResponse(BaseModel):
    config_id: int
    site_analysis: List[SiteAnalysisItem]
    recommendations: List[UserRecommendationItem]
    summary: str


# ---------- Endpoints ----------

@router.get("/recommendations/{config_id}", response_model=MappingRecommendationResponse)
async def get_mapping_recommendations(
    config_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get agent-human mapping recommendations for a supply chain config.

    Analyzes the DAG topology to classify sites (hub/spoke/factory/standalone)
    and recommends which users (by decision_level) should be created with
    which site_scope to cover the TRM agents at each site.

    Requires tenant admin or system admin.
    """
    is_admin = current_user.user_type in (
        UserTypeEnum.SYSTEM_ADMIN,
        UserTypeEnum.TENANT_ADMIN,
    )
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin or system admin required",
        )

    from app.services.agent_human_mapping import (
        SiteInfo,
        LaneInfo,
        classify_site_roles,
        get_human_trms_for_site,
        recommend_users_for_config,
    )
    from app.services.powell.site_capabilities import get_active_trms

    # Get user recommendations
    recs = await recommend_users_for_config(db, config_id)

    # Load sites and lanes for site analysis display
    result = await db.execute(
        select(Site).where(Site.config_id == config_id)
    )
    db_sites = result.scalars().all()

    result = await db.execute(
        select(TransportationLane).where(
            TransportationLane.config_id == config_id
        )
    )
    db_lanes = result.scalars().all()

    # Build SiteInfo list and classify
    sites = []
    for s in db_sites:
        mt = (s.master_type or "inventory").lower()
        is_ext = bool(getattr(s, "is_external", False))
        tpt = getattr(s, "tpartner_type", None)
        if tpt in ("vendor", "customer"):
            is_ext = True
            mt = tpt
        site_key = f"SITE_{s.name}" if s.name else str(s.id)
        sites.append(SiteInfo(
            id=s.id,
            key=site_key,
            name=s.name or str(s.id),
            master_type=mt,
            sc_site_type=getattr(s, "type", None),
            dag_type=getattr(s, "dag_type", None),
            is_external=is_ext,
        ))

    lanes = [
        LaneInfo(source_site_id=ln.from_site_id, dest_site_id=ln.to_site_id)
        for ln in db_lanes
        if ln.from_site_id and ln.to_site_id
    ]

    classify_site_roles(sites, lanes)

    # Build site analysis (internal sites only)
    site_analysis = []
    for s in sites:
        if s.role.value == "external":
            continue
        active = get_active_trms(s.master_type, s.sc_site_type)
        human = get_human_trms_for_site(s.master_type, s.role, s.sc_site_type)
        site_analysis.append(SiteAnalysisItem(
            site_key=s.key,
            site_name=s.name,
            master_type=s.master_type,
            role=s.role.value,
            active_trm_count=len(active),
            human_trm_count=len(human),
            human_trms=sorted(human),
        ))

    rec_items = [
        UserRecommendationItem(
            decision_level=r.decision_level,
            site_scope=r.site_scope,
            product_scope=r.product_scope,
            trm_types_covered=r.trm_types_covered,
            site_names=r.site_names,
            rationale=r.rationale,
        )
        for r in recs
    ]

    return MappingRecommendationResponse(
        config_id=config_id,
        site_analysis=site_analysis,
        recommendations=rec_items,
        summary=f"{len(rec_items)} user roles recommended across {len(site_analysis)} internal sites",
    )
