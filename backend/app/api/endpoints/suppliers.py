"""
Supplier API Endpoints - SC Compliant

Endpoints for managing suppliers (TradingPartner with type='vendor'),
vendor-product associations, vendor lead times, and supplier performance.

Based on SC entities: trading_partner, vendor_product, vendor_lead_time
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from typing import List, Optional
from datetime import datetime, timezone

from app.db.session import get_db
from app.models.sc_entities import TradingPartner
from app.models.supplier import VendorProduct, VendorLeadTime, SupplierPerformance
from app.models.user import User
from app.api.deps import get_current_user
from app.schemas.supplier import (
    # TradingPartner (Supplier) schemas
    TradingPartnerCreate,
    TradingPartnerUpdate,
    TradingPartnerResponse,
    TradingPartnerList,
    TradingPartnerSummary,
    # VendorProduct schemas
    VendorProductCreate,
    VendorProductUpdate,
    VendorProductResponse,
    VendorProductList,
    # VendorLeadTime schemas
    VendorLeadTimeCreate,
    VendorLeadTimeUpdate,
    VendorLeadTimeResponse,
    VendorLeadTimeList,
    LeadTimeResolutionRequest,
    LeadTimeResolutionResponse,
    # SupplierPerformance schemas
    SupplierPerformanceCreate,
    SupplierPerformanceResponse,
    SupplierPerformanceList,
    SupplierPerformanceTrend,
    # Multi-sourcing schemas
    MultiSourcingAnalysis,
    SourceRecommendation,
)

router = APIRouter()


# ============================================================================
# TradingPartner (Supplier) Endpoints
# ============================================================================

@router.post("/suppliers", response_model=TradingPartnerResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    supplier: TradingPartnerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new supplier (TradingPartner with type='vendor')

    SC Compliance: Uses trading_partner entity with temporal tracking
    """
    # Check if supplier already exists with same ID and effective dates
    existing = await db.execute(
        select(TradingPartner).where(
            and_(
                TradingPartner.id == supplier.id,
                TradingPartner.tpartner_type == supplier.tpartner_type,
                TradingPartner.geo_id == supplier.geo_id,
                TradingPartner.eff_start_date == supplier.eff_start_date,
                TradingPartner.eff_end_date == supplier.eff_end_date
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supplier with this ID and effective dates already exists"
        )

    # Create new supplier
    db_supplier = TradingPartner(
        **supplier.model_dump(),
        created_by=current_user.id,
        updated_by=current_user.id
    )

    db.add(db_supplier)
    await db.commit()
    await db.refresh(db_supplier)

    return db_supplier


@router.get("/suppliers", response_model=TradingPartnerList)
async def list_suppliers(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    tpartner_type: str = Query("vendor", description="Filter by partner type"),
    is_active: Optional[str] = Query(None, description="Filter by active status: 'true' or 'false'"),
    tier: Optional[str] = Query(None, description="Filter by tier"),
    country: Optional[str] = Query(None, description="Filter by country"),
    search: Optional[str] = Query(None, description="Search by ID or description"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List suppliers with filtering and pagination

    Default: Returns only active suppliers (type='vendor')
    """
    # Build query
    query = select(TradingPartner).where(TradingPartner.tpartner_type == tpartner_type)

    # Apply filters
    if is_active:
        query = query.where(TradingPartner.is_active == is_active)

    if tier:
        query = query.where(TradingPartner.tier == tier)

    if country:
        query = query.where(TradingPartner.country == country)

    if search:
        search_filter = or_(
            TradingPartner.id.ilike(f"%{search}%"),
            TradingPartner.description.ilike(f"%{search}%")
        )
        query = query.where(search_filter)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(desc(TradingPartner.created_at))

    # Execute query
    result = await db.execute(query)
    suppliers = result.scalars().all()

    # Calculate performance scores
    suppliers_with_scores = []
    for supplier in suppliers:
        supplier_dict = {
            **{k: v for k, v in supplier.__dict__.items() if not k.startswith('_')},
            'performance_score': supplier.calculate_performance_rating()
        }
        suppliers_with_scores.append(TradingPartnerResponse(**supplier_dict))

    return TradingPartnerList(
        items=suppliers_with_scores,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@router.get("/suppliers/summary", response_model=TradingPartnerSummary)
async def get_suppliers_summary(
    tpartner_type: str = Query("vendor", description="Partner type"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get summary statistics for suppliers
    """
    # Total suppliers
    total_result = await db.execute(
        select(func.count()).select_from(TradingPartner).where(
            TradingPartner.tpartner_type == tpartner_type
        )
    )
    total_suppliers = total_result.scalar()

    # Active suppliers
    active_result = await db.execute(
        select(func.count()).select_from(TradingPartner).where(
            and_(
                TradingPartner.tpartner_type == tpartner_type,
                TradingPartner.is_active == 'true'
            )
        )
    )
    active_suppliers = active_result.scalar()

    # Get all suppliers for detailed stats
    all_suppliers_result = await db.execute(
        select(TradingPartner).where(TradingPartner.tpartner_type == tpartner_type)
    )
    all_suppliers = all_suppliers_result.scalars().all()

    # Count by tier
    by_tier = {}
    for supplier in all_suppliers:
        tier = supplier.tier or "UNASSIGNED"
        by_tier[tier] = by_tier.get(tier, 0) + 1

    # Count by country
    by_country = {}
    for supplier in all_suppliers:
        country = supplier.country or "UNKNOWN"
        by_country[country] = by_country.get(country, 0) + 1

    # Calculate averages
    performance_scores = [s.calculate_performance_rating() for s in all_suppliers if s.calculate_performance_rating() > 0]
    on_time_rates = [s.on_time_delivery_rate for s in all_suppliers if s.on_time_delivery_rate is not None]
    quality_ratings = [s.quality_rating for s in all_suppliers if s.quality_rating is not None]

    avg_performance_score = sum(performance_scores) / len(performance_scores) if performance_scores else None
    avg_on_time_delivery = sum(on_time_rates) / len(on_time_rates) if on_time_rates else None
    avg_quality_rating = sum(quality_ratings) / len(quality_ratings) if quality_ratings else None

    # Count high risk and ISO certified
    high_risk_count = sum(1 for s in all_suppliers if s.risk_level in ['HIGH', 'CRITICAL'])
    iso_certified_count = sum(1 for s in all_suppliers if s.iso_certified)

    return TradingPartnerSummary(
        total_suppliers=total_suppliers,
        active_suppliers=active_suppliers,
        inactive_suppliers=total_suppliers - active_suppliers,
        by_tier=by_tier,
        by_country=by_country,
        avg_performance_score=avg_performance_score,
        avg_on_time_delivery=avg_on_time_delivery,
        avg_quality_rating=avg_quality_rating,
        high_risk_count=high_risk_count,
        iso_certified_count=iso_certified_count
    )


@router.get("/suppliers/{supplier_id}", response_model=TradingPartnerResponse)
async def get_supplier(
    supplier_id: str,
    tpartner_type: str = Query("vendor", description="Partner type"),
    geo_id: Optional[str] = Query(None, description="Geographic ID (if multiple)"),
    as_of_date: Optional[datetime] = Query(None, description="Date for temporal resolution"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get supplier by ID

    If as_of_date is provided, returns the record effective on that date.
    If geo_id is not provided, returns the most recent record.
    """
    query = select(TradingPartner).where(
        and_(
            TradingPartner.id == supplier_id,
            TradingPartner.tpartner_type == tpartner_type
        )
    )

    if geo_id:
        query = query.where(TradingPartner.geo_id == geo_id)

    if as_of_date:
        query = query.where(
            and_(
                TradingPartner.eff_start_date <= as_of_date,
                TradingPartner.eff_end_date >= as_of_date
            )
        )
    else:
        # Get most recent
        query = query.order_by(desc(TradingPartner.eff_start_date)).limit(1)

    result = await db.execute(query)
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found"
        )

    supplier_dict = {
        **{k: v for k, v in supplier.__dict__.items() if not k.startswith('_')},
        'performance_score': supplier.calculate_performance_rating()
    }

    return TradingPartnerResponse(**supplier_dict)


@router.patch("/suppliers/{supplier_id}", response_model=TradingPartnerResponse)
async def update_supplier(
    supplier_id: str,
    supplier_update: TradingPartnerUpdate,
    tpartner_type: str = Query("vendor", description="Partner type"),
    geo_id: str = Query(..., description="Geographic ID"),
    eff_start_date: datetime = Query(..., description="Effective start date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update supplier (specific temporal record)

    Note: This updates an existing temporal record. To create a new effective date range,
    use the create endpoint with new effective dates.
    """
    # Get existing record
    result = await db.execute(
        select(TradingPartner).where(
            and_(
                TradingPartner.id == supplier_id,
                TradingPartner.tpartner_type == tpartner_type,
                TradingPartner.geo_id == geo_id,
                TradingPartner.eff_start_date == eff_start_date
            )
        )
    )
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found"
        )

    # Update fields
    update_data = supplier_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(supplier, field, value)

    supplier.updated_by = current_user.id

    await db.commit()
    await db.refresh(supplier)

    supplier_dict = {
        **{k: v for k, v in supplier.__dict__.items() if not k.startswith('_')},
        'performance_score': supplier.calculate_performance_rating()
    }

    return TradingPartnerResponse(**supplier_dict)


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(
    supplier_id: str,
    tpartner_type: str = Query("vendor", description="Partner type"),
    geo_id: str = Query(..., description="Geographic ID"),
    eff_start_date: datetime = Query(..., description="Effective start date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Soft delete supplier (sets is_deleted = true)
    """
    result = await db.execute(
        select(TradingPartner).where(
            and_(
                TradingPartner.id == supplier_id,
                TradingPartner.tpartner_type == tpartner_type,
                TradingPartner.geo_id == geo_id,
                TradingPartner.eff_start_date == eff_start_date
            )
        )
    )
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found"
        )

    supplier.is_deleted = True
    supplier.updated_by = current_user.id

    await db.commit()


# ============================================================================
# VendorProduct Endpoints
# ============================================================================

@router.post("/vendor-products", response_model=VendorProductResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor_product(
    vendor_product: VendorProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create vendor-product association

    Links a supplier to a product with vendor-specific pricing and constraints.
    Supports multi-sourcing with priority rankings.
    """
    # Check for duplicate
    existing = await db.execute(
        select(VendorProduct).where(
            and_(
                VendorProduct.tpartner_id == vendor_product.tpartner_id,
                VendorProduct.product_id == vendor_product.product_id,
                VendorProduct.eff_start_date == vendor_product.eff_start_date
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vendor-product association with these effective dates already exists"
        )

    # Create association
    db_vendor_product = VendorProduct(**vendor_product.model_dump())

    db.add(db_vendor_product)
    await db.commit()
    await db.refresh(db_vendor_product)

    return db_vendor_product


@router.get("/vendor-products", response_model=VendorProductList)
async def list_vendor_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    tpartner_id: Optional[str] = Query(None, description="Filter by supplier ID"),
    product_id: Optional[int] = Query(None, description="Filter by product ID"),
    is_active: Optional[str] = Query(None, description="Filter by active status"),
    is_primary: Optional[bool] = Query(None, description="Filter by primary supplier"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List vendor-product associations with filtering and pagination
    """
    query = select(VendorProduct)

    if tpartner_id:
        query = query.where(VendorProduct.tpartner_id == tpartner_id)

    if product_id:
        query = query.where(VendorProduct.product_id == product_id)

    if is_active:
        query = query.where(VendorProduct.is_active == is_active)

    if is_primary is not None:
        query = query.where(VendorProduct.is_primary == is_primary)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(VendorProduct.priority, desc(VendorProduct.created_at))

    result = await db.execute(query)
    vendor_products = result.scalars().all()

    return VendorProductList(
        items=vendor_products,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@router.get("/vendor-products/{vendor_product_id}", response_model=VendorProductResponse)
async def get_vendor_product(
    vendor_product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get vendor-product by ID"""
    result = await db.execute(
        select(VendorProduct).where(VendorProduct.id == vendor_product_id)
    )
    vendor_product = result.scalar_one_or_none()

    if not vendor_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor-product association not found"
        )

    return vendor_product


@router.patch("/vendor-products/{vendor_product_id}", response_model=VendorProductResponse)
async def update_vendor_product(
    vendor_product_id: int,
    vendor_product_update: VendorProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update vendor-product association"""
    result = await db.execute(
        select(VendorProduct).where(VendorProduct.id == vendor_product_id)
    )
    vendor_product = result.scalar_one_or_none()

    if not vendor_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor-product association not found"
        )

    update_data = vendor_product_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(vendor_product, field, value)

    await db.commit()
    await db.refresh(vendor_product)

    return vendor_product


@router.delete("/vendor-products/{vendor_product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor_product(
    vendor_product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete vendor-product association"""
    result = await db.execute(
        select(VendorProduct).where(VendorProduct.id == vendor_product_id)
    )
    vendor_product = result.scalar_one_or_none()

    if not vendor_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor-product association not found"
        )

    await db.delete(vendor_product)
    await db.commit()


# ============================================================================
# VendorLeadTime Endpoints
# ============================================================================

@router.post("/vendor-lead-times", response_model=VendorLeadTimeResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor_lead_time(
    lead_time: VendorLeadTimeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create vendor lead time

    Supports hierarchical lead time management:
    product_id > product_group_id > site_id > region_id > company_id
    """
    db_lead_time = VendorLeadTime(**lead_time.model_dump())

    db.add(db_lead_time)
    await db.commit()
    await db.refresh(db_lead_time)

    return db_lead_time


@router.get("/vendor-lead-times", response_model=VendorLeadTimeList)
async def list_vendor_lead_times(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    tpartner_id: Optional[str] = Query(None),
    product_id: Optional[int] = Query(None),
    site_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List vendor lead times with filtering"""
    query = select(VendorLeadTime)

    if tpartner_id:
        query = query.where(VendorLeadTime.tpartner_id == tpartner_id)

    if product_id:
        query = query.where(VendorLeadTime.product_id == product_id)

    if site_id:
        query = query.where(VendorLeadTime.site_id == site_id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(desc(VendorLeadTime.created_at))

    result = await db.execute(query)
    lead_times = result.scalars().all()

    return VendorLeadTimeList(
        items=lead_times,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@router.post("/vendor-lead-times/resolve", response_model=LeadTimeResolutionResponse)
async def resolve_lead_time(
    request: LeadTimeResolutionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Resolve lead time using hierarchical override logic

    Priority (most specific wins):
    1. product_id (specific product)
    2. product_group_id (product category)
    3. site_id (specific site)
    4. region_id (geographic region)
    5. company_id (company-wide default)
    """
    as_of_date = request.as_of_date or datetime.now(timezone.utc)

    # Try each level in order of specificity
    for level, filter_value in [
        ('product_id', request.product_id),
        ('product_group_id', request.product_group_id),
        ('site_id', request.site_id),
        ('region_id', request.region_id),
        ('company_id', request.company_id)
    ]:
        if filter_value is None:
            continue

        query = select(VendorLeadTime).where(
            and_(
                VendorLeadTime.tpartner_id == request.tpartner_id,
                getattr(VendorLeadTime, level) == filter_value,
                VendorLeadTime.eff_start_date <= as_of_date,
                or_(
                    VendorLeadTime.eff_end_date >= as_of_date,
                    VendorLeadTime.eff_end_date == None
                )
            )
        ).order_by(desc(VendorLeadTime.eff_start_date)).limit(1)

        result = await db.execute(query)
        lead_time = result.scalar_one_or_none()

        if lead_time:
            return LeadTimeResolutionResponse(
                tpartner_id=lead_time.tpartner_id,
                lead_time_days=lead_time.lead_time_days,
                lead_time_variability_days=lead_time.lead_time_variability_days,
                resolution_level=level,
                lead_time_record_id=lead_time.id,
                eff_start_date=lead_time.eff_start_date,
                eff_end_date=lead_time.eff_end_date
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No lead time found for this supplier and context"
    )


# ============================================================================
# SupplierPerformance Endpoints
# ============================================================================

@router.post("/supplier-performance", response_model=SupplierPerformanceResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier_performance(
    performance: SupplierPerformanceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create supplier performance record"""
    db_performance = SupplierPerformance(**performance.model_dump())

    # Calculate derived metrics
    db_performance.calculate_metrics()

    db.add(db_performance)
    await db.commit()
    await db.refresh(db_performance)

    return db_performance


@router.get("/supplier-performance", response_model=SupplierPerformanceList)
async def list_supplier_performance(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    tpartner_id: Optional[str] = Query(None),
    period_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List supplier performance records"""
    query = select(SupplierPerformance)

    if tpartner_id:
        query = query.where(SupplierPerformance.tpartner_id == tpartner_id)

    if period_type:
        query = query.where(SupplierPerformance.period_type == period_type)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(desc(SupplierPerformance.period_end))

    result = await db.execute(query)
    performance_records = result.scalars().all()

    return SupplierPerformanceList(
        items=performance_records,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )
