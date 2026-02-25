"""
Vendor Lead Time API Endpoints
AWS Supply Chain Entity: vendor_lead_time

Manages supplier-specific lead times with hierarchical override logic:
- Company-level default lead times
- Region-specific lead times
- Site-specific lead times
- Product group lead times
- Product-specific lead times (most specific wins)

Supports stochastic planning with lead time variability.

Endpoints:
- POST / - Create vendor lead time
- POST /bulk - Bulk create
- GET / - List with filtering
- GET /{id} - Get specific lead time
- GET /resolve - Resolve effective lead time (hierarchical lookup)
- PUT /{id} - Update lead time
- DELETE /{id} - Delete lead time
- DELETE /bulk - Bulk delete
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal

from app.api import deps
from app.models.user import User
from app.models.supplier import VendorLeadTime
from app.models.sc_entities import TradingPartner, Product
from app.core.capabilities import require_capabilities

router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class VendorLeadTimeCreate(BaseModel):
    """Request schema for creating vendor lead time"""
    tpartner_id: str
    lead_time_days: float = Field(gt=0, description="Lead time in days")

    # Hierarchical override fields (most specific wins)
    company_id: Optional[str] = None
    region_id: Optional[str] = None
    site_id: Optional[int] = None
    product_group_id: Optional[str] = None
    product_id: Optional[str] = None

    # Lead time variability for stochastic planning
    lead_time_variability_days: Optional[float] = Field(None, ge=0, description="Standard deviation")

    # Effective dates
    eff_start_date: Optional[datetime] = None
    eff_end_date: Optional[datetime] = None

    # Source tracking
    source: Optional[str] = None
    source_event_id: Optional[str] = None


class VendorLeadTimeUpdate(BaseModel):
    """Request schema for updating vendor lead time"""
    lead_time_days: Optional[float] = Field(None, gt=0)
    lead_time_variability_days: Optional[float] = Field(None, ge=0)
    eff_end_date: Optional[datetime] = None


class VendorLeadTimeResponse(BaseModel):
    """Response schema for vendor lead time"""
    id: int
    company_id: Optional[str]
    region_id: Optional[str]
    site_id: Optional[int]
    product_group_id: Optional[str]
    product_id: Optional[str]
    tpartner_id: str
    lead_time_days: float
    lead_time_variability_days: Optional[float]
    eff_start_date: datetime
    eff_end_date: Optional[datetime]
    source: Optional[str]
    source_event_id: Optional[str]
    source_update_dttm: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BulkVendorLeadTimeCreate(BaseModel):
    """Bulk creation request"""
    lead_times: List[VendorLeadTimeCreate]


class LeadTimeResolveRequest(BaseModel):
    """Request to resolve effective lead time"""
    tpartner_id: str
    product_id: Optional[str] = None
    site_id: Optional[int] = None
    product_group_id: Optional[str] = None
    region_id: Optional[str] = None
    as_of_date: Optional[datetime] = None


class LeadTimeResolveResponse(BaseModel):
    """Resolved lead time with hierarchy level"""
    lead_time_days: float
    lead_time_variability_days: Optional[float]
    resolved_from: str  # "product", "product_group", "site", "region", "company"
    vendor_lead_time_id: int


# ============================================================================
# Helper Functions
# ============================================================================

async def resolve_vendor_lead_time(
    db: AsyncSession,
    company_id: str,
    tpartner_id: str,
    product_id: Optional[str] = None,
    site_id: Optional[int] = None,
    product_group_id: Optional[str] = None,
    region_id: Optional[str] = None,
    as_of_date: Optional[datetime] = None
) -> Optional[tuple[VendorLeadTime, str]]:
    """
    Resolve vendor lead time using hierarchical override logic

    Priority (most specific wins):
    1. Product-specific (tpartner + product)
    2. Product group (tpartner + product_group)
    3. Site-specific (tpartner + site)
    4. Region-specific (tpartner + region)
    5. Company-level default (tpartner + company)

    Returns:
        Tuple of (VendorLeadTime, resolved_from_level) or None
    """
    check_date = as_of_date or datetime.utcnow()

    # Build effective date filter
    def is_effective(lt):
        if check_date < lt.eff_start_date:
            return False
        if lt.eff_end_date and check_date > lt.eff_end_date:
            return False
        return True

    # 1. Try product-specific
    if product_id:
        stmt = select(VendorLeadTime).where(
            and_(
                VendorLeadTime.tpartner_id == tpartner_id,
                VendorLeadTime.product_id == product_id
            )
        )
        result = await db.execute(stmt)
        lead_times = result.scalars().all()
        for lt in lead_times:
            if is_effective(lt):
                return (lt, "product")

    # 2. Try product group
    if product_group_id:
        stmt = select(VendorLeadTime).where(
            and_(
                VendorLeadTime.tpartner_id == tpartner_id,
                VendorLeadTime.product_group_id == product_group_id,
                VendorLeadTime.product_id.is_(None)
            )
        )
        result = await db.execute(stmt)
        lead_times = result.scalars().all()
        for lt in lead_times:
            if is_effective(lt):
                return (lt, "product_group")

    # 3. Try site-specific
    if site_id:
        stmt = select(VendorLeadTime).where(
            and_(
                VendorLeadTime.tpartner_id == tpartner_id,
                VendorLeadTime.site_id == site_id,
                VendorLeadTime.product_id.is_(None),
                VendorLeadTime.product_group_id.is_(None)
            )
        )
        result = await db.execute(stmt)
        lead_times = result.scalars().all()
        for lt in lead_times:
            if is_effective(lt):
                return (lt, "site")

    # 4. Try region-specific
    if region_id:
        stmt = select(VendorLeadTime).where(
            and_(
                VendorLeadTime.tpartner_id == tpartner_id,
                VendorLeadTime.region_id == region_id,
                VendorLeadTime.site_id.is_(None),
                VendorLeadTime.product_id.is_(None),
                VendorLeadTime.product_group_id.is_(None)
            )
        )
        result = await db.execute(stmt)
        lead_times = result.scalars().all()
        for lt in lead_times:
            if is_effective(lt):
                return (lt, "region")

    # 5. Try company-level default
    stmt = select(VendorLeadTime).where(
        and_(
            VendorLeadTime.tpartner_id == tpartner_id,
            VendorLeadTime.company_id == company_id,
            VendorLeadTime.region_id.is_(None),
            VendorLeadTime.site_id.is_(None),
            VendorLeadTime.product_id.is_(None),
            VendorLeadTime.product_group_id.is_(None)
        )
    )
    result = await db.execute(stmt)
    lead_times = result.scalars().all()
    for lt in lead_times:
        if is_effective(lt):
            return (lt, "company")

    return None


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/", response_model=VendorLeadTimeResponse)
@require_capabilities(["manage_vendor_lead_times"])
async def create_vendor_lead_time(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    lead_time: VendorLeadTimeCreate
):
    """
    Create vendor lead time

    Supports hierarchical lead time definitions. Most specific level wins:
    - Product-specific > Product Group > Site > Region > Company

    Args:
        lead_time: Lead time parameters

    Returns:
        Created vendor lead time
    """
    company_id = current_user.customer_id

    # Verify trading partner exists
    stmt = select(TradingPartner).where(TradingPartner.id == lead_time.tpartner_id)
    result = await db.execute(stmt)
    trading_partner = result.scalar_one_or_none()
    if not trading_partner:
        raise HTTPException(status_code=404, detail=f"Trading partner {lead_time.tpartner_id} not found")

    # Verify product if specified
    if lead_time.product_id:
        stmt = select(Product).where(Product.id == lead_time.product_id)
        result = await db.execute(stmt)
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {lead_time.product_id} not found")

    # Create vendor lead time
    vendor_lead_time = VendorLeadTime(
        company_id=company_id,
        tpartner_id=lead_time.tpartner_id,
        lead_time_days=lead_time.lead_time_days,
        lead_time_variability_days=lead_time.lead_time_variability_days,
        region_id=lead_time.region_id,
        site_id=lead_time.site_id,
        product_group_id=lead_time.product_group_id,
        product_id=lead_time.product_id,
        eff_start_date=lead_time.eff_start_date or datetime.utcnow(),
        eff_end_date=lead_time.eff_end_date,
        source=lead_time.source,
        source_event_id=lead_time.source_event_id,
        source_update_dttm=datetime.utcnow()
    )

    db.add(vendor_lead_time)
    await db.commit()
    await db.refresh(vendor_lead_time)

    return VendorLeadTimeResponse.from_orm(vendor_lead_time)


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
@require_capabilities(["manage_vendor_lead_times"])
async def bulk_create_vendor_lead_times(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    bulk_request: BulkVendorLeadTimeCreate
):
    """Bulk create vendor lead times"""
    company_id = current_user.customer_id
    created_count = 0

    for lead_time in bulk_request.lead_times:
        vendor_lead_time = VendorLeadTime(
            company_id=company_id,
            tpartner_id=lead_time.tpartner_id,
            lead_time_days=lead_time.lead_time_days,
            lead_time_variability_days=lead_time.lead_time_variability_days,
            region_id=lead_time.region_id,
            site_id=lead_time.site_id,
            product_group_id=lead_time.product_group_id,
            product_id=lead_time.product_id,
            eff_start_date=lead_time.eff_start_date or datetime.utcnow(),
            eff_end_date=lead_time.eff_end_date,
            source=lead_time.source,
            source_event_id=lead_time.source_event_id,
            source_update_dttm=datetime.utcnow()
        )
        db.add(vendor_lead_time)
        created_count += 1

    await db.commit()

    return {
        "status": "success",
        "created_count": created_count,
        "message": f"Created {created_count} vendor lead times"
    }


@router.get("/", response_model=List[VendorLeadTimeResponse])
@require_capabilities(["view_vendor_lead_times"])
async def list_vendor_lead_times(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    tpartner_id: Optional[str] = None,
    product_id: Optional[str] = None,
    site_id: Optional[int] = None,
    active_only: bool = True,
    limit: int = Query(1000, le=10000)
):
    """
    List vendor lead times with filtering

    Args:
        tpartner_id: Filter by trading partner
        product_id: Filter by product
        site_id: Filter by site
        active_only: Only return effective lead times
        limit: Maximum results

    Returns:
        List of vendor lead times
    """
    stmt = select(VendorLeadTime)

    if tpartner_id:
        stmt = stmt.where(VendorLeadTime.tpartner_id == tpartner_id)

    if product_id:
        stmt = stmt.where(VendorLeadTime.product_id == product_id)

    if site_id:
        stmt = stmt.where(VendorLeadTime.site_id == site_id)

    if active_only:
        now = datetime.utcnow()
        stmt = stmt.where(
            and_(
                VendorLeadTime.eff_start_date <= now,
                or_(
                    VendorLeadTime.eff_end_date.is_(None),
                    VendorLeadTime.eff_end_date > now
                )
            )
        )

    stmt = stmt.order_by(VendorLeadTime.tpartner_id, VendorLeadTime.lead_time_days).limit(limit)

    result = await db.execute(stmt)
    lead_times = result.scalars().all()

    return [VendorLeadTimeResponse.from_orm(lt) for lt in lead_times]


@router.get("/{lead_time_id}", response_model=VendorLeadTimeResponse)
@require_capabilities(["view_vendor_lead_times"])
async def get_vendor_lead_time(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    lead_time_id: int
):
    """Get vendor lead time by ID"""
    stmt = select(VendorLeadTime).where(VendorLeadTime.id == lead_time_id)
    result = await db.execute(stmt)
    lead_time = result.scalar_one_or_none()

    if not lead_time:
        raise HTTPException(status_code=404, detail=f"Vendor lead time {lead_time_id} not found")

    return VendorLeadTimeResponse.from_orm(lead_time)


@router.post("/resolve", response_model=LeadTimeResolveResponse)
@require_capabilities(["view_vendor_lead_times"])
async def resolve_lead_time(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    request: LeadTimeResolveRequest
):
    """
    Resolve effective vendor lead time using hierarchical logic

    Returns the most specific lead time that applies:
    1. Product-specific
    2. Product group
    3. Site-specific
    4. Region-specific
    5. Company-level default

    Args:
        request: Resolution parameters

    Returns:
        Resolved lead time with hierarchy level
    """
    company_id = current_user.customer_id

    result = await resolve_vendor_lead_time(
        db,
        company_id,
        request.tpartner_id,
        request.product_id,
        request.site_id,
        request.product_group_id,
        request.region_id,
        request.as_of_date
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No lead time found for trading partner {request.tpartner_id}"
        )

    lead_time, resolved_from = result

    return LeadTimeResolveResponse(
        lead_time_days=lead_time.lead_time_days,
        lead_time_variability_days=lead_time.lead_time_variability_days,
        resolved_from=resolved_from,
        vendor_lead_time_id=lead_time.id
    )


@router.put("/{lead_time_id}", response_model=VendorLeadTimeResponse)
@require_capabilities(["manage_vendor_lead_times"])
async def update_vendor_lead_time(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    lead_time_id: int,
    lead_time_update: VendorLeadTimeUpdate
):
    """Update vendor lead time"""
    stmt = select(VendorLeadTime).where(VendorLeadTime.id == lead_time_id)
    result = await db.execute(stmt)
    lead_time = result.scalar_one_or_none()

    if not lead_time:
        raise HTTPException(status_code=404, detail=f"Vendor lead time {lead_time_id} not found")

    # Update fields
    if lead_time_update.lead_time_days is not None:
        lead_time.lead_time_days = lead_time_update.lead_time_days

    if lead_time_update.lead_time_variability_days is not None:
        lead_time.lead_time_variability_days = lead_time_update.lead_time_variability_days

    if lead_time_update.eff_end_date is not None:
        lead_time.eff_end_date = lead_time_update.eff_end_date

    lead_time.source_update_dttm = datetime.utcnow()

    await db.commit()
    await db.refresh(lead_time)

    return VendorLeadTimeResponse.from_orm(lead_time)


@router.delete("/{lead_time_id}")
@require_capabilities(["manage_vendor_lead_times"])
async def delete_vendor_lead_time(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    lead_time_id: int
):
    """Delete vendor lead time"""
    stmt = select(VendorLeadTime).where(VendorLeadTime.id == lead_time_id)
    result = await db.execute(stmt)
    lead_time = result.scalar_one_or_none()

    if not lead_time:
        raise HTTPException(status_code=404, detail=f"Vendor lead time {lead_time_id} not found")

    await db.delete(lead_time)
    await db.commit()

    return {"status": "success", "message": f"Vendor lead time {lead_time_id} deleted"}


@router.delete("/bulk/delete")
@require_capabilities(["manage_vendor_lead_times"])
async def bulk_delete_vendor_lead_times(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    tpartner_id: Optional[str] = None,
    product_id: Optional[str] = None,
    before_date: Optional[datetime] = None
):
    """
    Bulk delete vendor lead times

    Args:
        tpartner_id: Delete for this trading partner
        product_id: Delete for this product
        before_date: Delete lead times ending before this date

    Returns:
        Number of deleted lead times
    """
    stmt = select(VendorLeadTime)

    if tpartner_id:
        stmt = stmt.where(VendorLeadTime.tpartner_id == tpartner_id)

    if product_id:
        stmt = stmt.where(VendorLeadTime.product_id == product_id)

    if before_date:
        stmt = stmt.where(VendorLeadTime.eff_end_date < before_date)

    result = await db.execute(stmt)
    lead_times = result.scalars().all()

    deleted_count = len(lead_times)

    for lt in lead_times:
        await db.delete(lt)

    await db.commit()

    return {
        "status": "success",
        "deleted_count": deleted_count,
        "message": f"Deleted {deleted_count} vendor lead times"
    }
