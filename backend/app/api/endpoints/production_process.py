"""
Production Process API Endpoints
AWS Supply Chain Entity: production_process

Manages manufacturing processes including:
- Operation times and setup times
- Lot sizing parameters
- Yield percentages
- Manufacturing lead times
- Capacity constraints

Used for:
- MPS/MRP calculations
- Capacity planning
- Manufacturing order generation

Endpoints:
- POST / - Create production process
- POST /bulk - Bulk create
- GET / - List with filtering
- GET /{id} - Get specific process
- PUT /{id} - Update process
- DELETE /{id} - Delete process
- GET /by-site/{site_id} - Get all processes for a site
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from app.api import deps
from app.models.user import User
from app.models.sc_entities import ProductionProcess
from app.models.supply_chain_config import Site
from app.core.capabilities import require_capabilities

router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class ProductionProcessCreate(BaseModel):
    """Request schema for creating production process"""
    id: str
    description: Optional[str] = None
    site_id: str
    process_type: Optional[str] = Field(None, description="assembly, machining, packaging, etc.")

    # Time parameters (hours)
    operation_time: float = Field(gt=0, description="Operation time per unit (hours)")
    setup_time: Optional[float] = Field(None, ge=0, description="Setup time (hours)")

    # Lot sizing
    lot_size: Optional[float] = Field(None, gt=0, description="Economic lot size")

    # Yield
    yield_percentage: float = Field(default=100.0, gt=0, le=100, description="Process yield %")

    # Manufacturing parameters
    manufacturing_leadtime: int = Field(default=0, ge=0, description="Manufacturing lead time (days)")
    manufacturing_capacity_hours: Optional[float] = Field(None, gt=0, description="Daily capacity (hours)")

    # Source tracking
    source: Optional[str] = None
    source_event_id: Optional[str] = None

    # Active status
    is_active: str = Field(default="Y", description="Y or N")


class ProductionProcessUpdate(BaseModel):
    """Request schema for updating production process"""
    description: Optional[str] = None
    operation_time: Optional[float] = Field(None, gt=0)
    setup_time: Optional[float] = Field(None, ge=0)
    lot_size: Optional[float] = Field(None, gt=0)
    yield_percentage: Optional[float] = Field(None, gt=0, le=100)
    manufacturing_leadtime: Optional[int] = Field(None, ge=0)
    manufacturing_capacity_hours: Optional[float] = Field(None, gt=0)
    is_active: Optional[str] = None


class ProductionProcessResponse(BaseModel):
    """Response schema for production process"""
    id: str
    description: Optional[str]
    company_id: Optional[str]
    site_id: Optional[str]
    process_type: Optional[str]
    operation_time: Optional[float]
    setup_time: Optional[float]
    lot_size: Optional[float]
    yield_percentage: Optional[float]
    manufacturing_leadtime: Optional[int]
    manufacturing_capacity_hours: Optional[float]
    is_active: Optional[str]
    source: Optional[str]
    source_event_id: Optional[str]
    source_update_dttm: Optional[datetime]

    class Config:
        from_attributes = True


class BulkProductionProcessCreate(BaseModel):
    """Bulk creation request"""
    processes: List[ProductionProcessCreate]


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/", response_model=ProductionProcessResponse)
@require_capabilities(["manage_production_process"])
async def create_production_process(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    process: ProductionProcessCreate
):
    """
    Create production process

    Defines manufacturing parameters for a site:
    - Operation and setup times
    - Lot sizing
    - Yield percentage
    - Manufacturing lead time
    - Capacity constraints

    Args:
        process: Production process parameters

    Returns:
        Created production process
    """
    company_id = current_user.tenant_id

    # Verify site exists
    stmt = select(Site).where(Site.id == process.site_id)
    result = await db.execute(stmt)
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail=f"Site {process.site_id} not found")

    # Check if process ID already exists
    stmt = select(ProductionProcess).where(ProductionProcess.id == process.id)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Production process with ID '{process.id}' already exists"
        )

    # Create production process
    production_process = ProductionProcess(
        id=process.id,
        description=process.description,
        company_id=company_id,
        site_id=process.site_id,
        process_type=process.process_type,
        operation_time=process.operation_time,
        setup_time=process.setup_time,
        lot_size=process.lot_size,
        yield_percentage=process.yield_percentage,
        manufacturing_leadtime=process.manufacturing_leadtime,
        manufacturing_capacity_hours=process.manufacturing_capacity_hours,
        is_active=process.is_active,
        source=process.source,
        source_event_id=process.source_event_id,
        source_update_dttm=datetime.utcnow()
    )

    db.add(production_process)
    await db.commit()
    await db.refresh(production_process)

    return ProductionProcessResponse.from_orm(production_process)


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
@require_capabilities(["manage_production_process"])
async def bulk_create_production_processes(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    bulk_request: BulkProductionProcessCreate
):
    """Bulk create production processes"""
    company_id = current_user.tenant_id
    created_count = 0

    for process in bulk_request.processes:
        # Check if process ID already exists
        stmt = select(ProductionProcess).where(ProductionProcess.id == process.id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            continue  # Skip duplicates

        production_process = ProductionProcess(
            id=process.id,
            description=process.description,
            company_id=company_id,
            site_id=process.site_id,
            process_type=process.process_type,
            operation_time=process.operation_time,
            setup_time=process.setup_time,
            lot_size=process.lot_size,
            yield_percentage=process.yield_percentage,
            manufacturing_leadtime=process.manufacturing_leadtime,
            manufacturing_capacity_hours=process.manufacturing_capacity_hours,
            is_active=process.is_active,
            source=process.source,
            source_event_id=process.source_event_id,
            source_update_dttm=datetime.utcnow()
        )
        db.add(production_process)
        created_count += 1

    await db.commit()

    return {
        "status": "success",
        "created_count": created_count,
        "message": f"Created {created_count} production processes"
    }


@router.get("/", response_model=List[ProductionProcessResponse])
@require_capabilities(["view_production_process"])
async def list_production_processes(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    site_id: Optional[str] = None,
    process_type: Optional[str] = None,
    active_only: bool = True,
    limit: int = Query(1000, le=10000)
):
    """
    List production processes with filtering

    Args:
        site_id: Filter by site
        process_type: Filter by process type
        active_only: Only return active processes
        limit: Maximum results

    Returns:
        List of production processes
    """
    stmt = select(ProductionProcess)

    if site_id:
        stmt = stmt.where(ProductionProcess.site_id == site_id)

    if process_type:
        stmt = stmt.where(ProductionProcess.process_type == process_type)

    if active_only:
        stmt = stmt.where(ProductionProcess.is_active == "Y")

    stmt = stmt.order_by(ProductionProcess.site_id, ProductionProcess.id).limit(limit)

    result = await db.execute(stmt)
    processes = result.scalars().all()

    return [ProductionProcessResponse.from_orm(p) for p in processes]


@router.get("/{process_id}", response_model=ProductionProcessResponse)
@require_capabilities(["view_production_process"])
async def get_production_process(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    process_id: str
):
    """Get production process by ID"""
    stmt = select(ProductionProcess).where(ProductionProcess.id == process_id)
    result = await db.execute(stmt)
    process = result.scalar_one_or_none()

    if not process:
        raise HTTPException(status_code=404, detail=f"Production process {process_id} not found")

    return ProductionProcessResponse.from_orm(process)


@router.get("/by-site/{site_id}", response_model=List[ProductionProcessResponse])
@require_capabilities(["view_production_process"])
async def get_production_processes_by_site(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    site_id: str,
    active_only: bool = True
):
    """
    Get all production processes for a site

    Useful for capacity planning and MPS/MRP calculations.

    Args:
        site_id: Site ID
        active_only: Only return active processes

    Returns:
        List of production processes for the site
    """
    stmt = select(ProductionProcess).where(ProductionProcess.site_id == site_id)

    if active_only:
        stmt = stmt.where(ProductionProcess.is_active == "Y")

    stmt = stmt.order_by(ProductionProcess.id)

    result = await db.execute(stmt)
    processes = result.scalars().all()

    return [ProductionProcessResponse.from_orm(p) for p in processes]


@router.put("/{process_id}", response_model=ProductionProcessResponse)
@require_capabilities(["manage_production_process"])
async def update_production_process(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    process_id: str,
    process_update: ProductionProcessUpdate
):
    """Update production process"""
    stmt = select(ProductionProcess).where(ProductionProcess.id == process_id)
    result = await db.execute(stmt)
    process = result.scalar_one_or_none()

    if not process:
        raise HTTPException(status_code=404, detail=f"Production process {process_id} not found")

    # Update fields
    if process_update.description is not None:
        process.description = process_update.description

    if process_update.operation_time is not None:
        process.operation_time = process_update.operation_time

    if process_update.setup_time is not None:
        process.setup_time = process_update.setup_time

    if process_update.lot_size is not None:
        process.lot_size = process_update.lot_size

    if process_update.yield_percentage is not None:
        process.yield_percentage = process_update.yield_percentage

    if process_update.manufacturing_leadtime is not None:
        process.manufacturing_leadtime = process_update.manufacturing_leadtime

    if process_update.manufacturing_capacity_hours is not None:
        process.manufacturing_capacity_hours = process_update.manufacturing_capacity_hours

    if process_update.is_active is not None:
        process.is_active = process_update.is_active

    process.source_update_dttm = datetime.utcnow()

    await db.commit()
    await db.refresh(process)

    return ProductionProcessResponse.from_orm(process)


@router.delete("/{process_id}")
@require_capabilities(["manage_production_process"])
async def delete_production_process(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    process_id: str
):
    """Delete production process"""
    stmt = select(ProductionProcess).where(ProductionProcess.id == process_id)
    result = await db.execute(stmt)
    process = result.scalar_one_or_none()

    if not process:
        raise HTTPException(status_code=404, detail=f"Production process {process_id} not found")

    await db.delete(process)
    await db.commit()

    return {"status": "success", "message": f"Production process {process_id} deleted"}
