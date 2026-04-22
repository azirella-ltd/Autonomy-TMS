"""
Analytics & Optimization API Endpoints
AWS Supply Chain Entities: inventory_optimization, capacity_optimization,
                           network_optimization, kpi_configuration

Consolidated analytics and optimization endpoints.

Key Features:
- Inventory optimization (safety stock, reorder points)
- Capacity optimization (resource leveling, bottleneck resolution)
- Network optimization (DC site, production allocation)
- KPI configuration and monitoring

Endpoints organized by entity type with standard CRUD operations.
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, date

from app.api import deps
from app.models.user import User
from app.models.analytics import (
    InventoryOptimization,
    CapacityOptimization,
    NetworkOptimization,
    KPIConfiguration
)
from app.core.capabilities import require_capabilities

router = APIRouter()


# ============================================================================
# Inventory Optimization Schemas & Endpoints
# ============================================================================

class InventoryOptimizationCreate(BaseModel):
    product_id: str
    site_id: Optional[str] = None
    optimization_date: date
    optimization_method: str = Field(description="newsvendor, base_stock, ss_rop, monte_carlo")
    current_safety_stock: Optional[float] = Field(None, ge=0)
    recommended_safety_stock: float = Field(ge=0)
    expected_service_level: float = Field(ge=0, le=100)


class InventoryOptimizationResponse(BaseModel):
    id: int
    company_id: Optional[str]
    site_id: Optional[str]
    product_id: Optional[str]
    optimization_date: date
    optimization_method: str
    current_safety_stock: Optional[float]
    recommended_safety_stock: float
    expected_service_level: float
    expected_total_cost: Optional[float]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/inventory-optimization", response_model=InventoryOptimizationResponse)
@require_capabilities(["manage_inventory_optimization"])
async def create_inventory_optimization(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    optimization: InventoryOptimizationCreate
):
    """Create inventory optimization recommendation"""
    inv_opt = InventoryOptimization(
        company_id=current_user.tenant_id,
        site_id=optimization.site_id,
        product_id=optimization.product_id,
        optimization_date=optimization.optimization_date,
        optimization_method=optimization.optimization_method,
        current_safety_stock=optimization.current_safety_stock,
        recommended_safety_stock=optimization.recommended_safety_stock,
        expected_service_level=optimization.expected_service_level,
        created_by=current_user.id,
        source_update_dttm=datetime.utcnow()
    )

    db.add(inv_opt)
    await db.commit()
    await db.refresh(inv_opt)

    return InventoryOptimizationResponse.from_orm(inv_opt)


@router.get("/inventory-optimization", response_model=List[InventoryOptimizationResponse])
@require_capabilities(["view_inventory_optimization"])
async def list_inventory_optimizations(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    product_id: Optional[str] = None,
    site_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(1000, le=10000)
):
    """List inventory optimizations"""
    stmt = select(InventoryOptimization)

    if product_id:
        stmt = stmt.where(InventoryOptimization.product_id == product_id)
    if site_id:
        stmt = stmt.where(InventoryOptimization.site_id == site_id)
    if status:
        stmt = stmt.where(InventoryOptimization.status == status)

    stmt = stmt.order_by(InventoryOptimization.optimization_date.desc()).limit(limit)

    result = await db.execute(stmt)
    optimizations = result.scalars().all()

    return [InventoryOptimizationResponse.from_orm(o) for o in optimizations]


# ============================================================================
# Capacity Optimization Schemas & Endpoints
# ============================================================================

class CapacityOptimizationCreate(BaseModel):
    site_id: Optional[str] = None
    resource_id: Optional[str] = None
    optimization_date: date
    optimization_horizon_weeks: int = Field(default=13, ge=1, le=52)
    optimization_method: str = Field(description="linear_program, constraint_programming, heuristic")
    expected_utilization_pct: float = Field(ge=0, le=150)


class CapacityOptimizationResponse(BaseModel):
    id: int
    company_id: Optional[str]
    site_id: Optional[str]
    resource_id: Optional[str]
    optimization_date: date
    optimization_horizon_weeks: int
    optimization_method: str
    expected_utilization_pct: float
    is_bottleneck: bool
    bottleneck_severity: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/capacity-optimization", response_model=CapacityOptimizationResponse)
@require_capabilities(["manage_capacity_optimization"])
async def create_capacity_optimization(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    optimization: CapacityOptimizationCreate
):
    """Create capacity optimization recommendation"""
    cap_opt = CapacityOptimization(
        company_id=current_user.tenant_id,
        site_id=optimization.site_id,
        resource_id=optimization.resource_id,
        optimization_date=optimization.optimization_date,
        optimization_horizon_weeks=optimization.optimization_horizon_weeks,
        optimization_method=optimization.optimization_method,
        expected_utilization_pct=optimization.expected_utilization_pct,
        created_by=current_user.id,
        source_update_dttm=datetime.utcnow()
    )

    db.add(cap_opt)
    await db.commit()
    await db.refresh(cap_opt)

    return CapacityOptimizationResponse.from_orm(cap_opt)


@router.get("/capacity-optimization", response_model=List[CapacityOptimizationResponse])
@require_capabilities(["view_capacity_optimization"])
async def list_capacity_optimizations(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    resource_id: Optional[str] = None,
    site_id: Optional[str] = None,
    is_bottleneck: Optional[bool] = None,
    limit: int = Query(1000, le=10000)
):
    """List capacity optimizations"""
    stmt = select(CapacityOptimization)

    if resource_id:
        stmt = stmt.where(CapacityOptimization.resource_id == resource_id)
    if site_id:
        stmt = stmt.where(CapacityOptimization.site_id == site_id)
    if is_bottleneck is not None:
        stmt = stmt.where(CapacityOptimization.is_bottleneck == is_bottleneck)

    stmt = stmt.order_by(CapacityOptimization.optimization_date.desc()).limit(limit)

    result = await db.execute(stmt)
    optimizations = result.scalars().all()

    return [CapacityOptimizationResponse.from_orm(o) for o in optimizations]


# ============================================================================
# Network Optimization Schemas & Endpoints
# ============================================================================

class NetworkOptimizationCreate(BaseModel):
    optimization_date: date
    optimization_type: str = Field(description="dc_location, production_allocation, flow_optimization, end_to_end")
    optimization_method: str = Field(description="mixed_integer_program, genetic_algorithm, simulated_annealing")
    optimization_horizon_weeks: int = Field(default=52, ge=1, le=104)
    expected_network_cost: float = Field(ge=0)


class NetworkOptimizationResponse(BaseModel):
    id: int
    company_id: Optional[str]
    optimization_date: date
    optimization_type: str
    optimization_method: str
    expected_network_cost: float
    expected_cost_reduction_pct: Optional[float]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/network-optimization", response_model=NetworkOptimizationResponse)
@require_capabilities(["manage_network_optimization"])
async def create_network_optimization(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    optimization: NetworkOptimizationCreate
):
    """Create network optimization recommendation"""
    net_opt = NetworkOptimization(
        company_id=current_user.tenant_id,
        optimization_date=optimization.optimization_date,
        optimization_type=optimization.optimization_type,
        optimization_method=optimization.optimization_method,
        optimization_horizon_weeks=optimization.optimization_horizon_weeks,
        expected_network_cost=optimization.expected_network_cost,
        created_by=current_user.id,
        source_update_dttm=datetime.utcnow()
    )

    db.add(net_opt)
    await db.commit()
    await db.refresh(net_opt)

    return NetworkOptimizationResponse.from_orm(net_opt)


@router.get("/network-optimization", response_model=List[NetworkOptimizationResponse])
@require_capabilities(["view_network_optimization"])
async def list_network_optimizations(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    optimization_type: Optional[str] = None,
    limit: int = Query(1000, le=10000)
):
    """List network optimizations"""
    stmt = select(NetworkOptimization)

    if optimization_type:
        stmt = stmt.where(NetworkOptimization.optimization_type == optimization_type)

    stmt = stmt.order_by(NetworkOptimization.optimization_date.desc()).limit(limit)

    result = await db.execute(stmt)
    optimizations = result.scalars().all()

    return [NetworkOptimizationResponse.from_orm(o) for o in optimizations]


# ============================================================================
# KPI Configuration Schemas & Endpoints
# ============================================================================

class KPIConfigurationCreate(BaseModel):
    kpi_name: str
    kpi_category: str = Field(description="financial, customer, operational, strategic")
    site_id: Optional[str] = None
    target_value: float
    threshold_green: Optional[float] = None
    threshold_yellow: Optional[float] = None
    threshold_red: Optional[float] = None
    calculation_method: str = Field(description="formula, aggregate, custom_function")
    is_higher_better: bool = Field(default=True)


class KPIConfigurationResponse(BaseModel):
    id: int
    company_id: Optional[str]
    site_id: Optional[str]
    kpi_name: str
    kpi_category: str
    target_value: float
    threshold_green: Optional[float]
    threshold_yellow: Optional[float]
    threshold_red: Optional[float]
    is_higher_better: bool
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/kpi-configuration", response_model=KPIConfigurationResponse)
@require_capabilities(["manage_kpi_configuration"])
async def create_kpi_configuration(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    kpi_config: KPIConfigurationCreate
):
    """Create KPI configuration"""
    kpi = KPIConfiguration(
        company_id=current_user.tenant_id,
        site_id=kpi_config.site_id,
        kpi_name=kpi_config.kpi_name,
        kpi_category=kpi_config.kpi_category,
        target_value=kpi_config.target_value,
        threshold_green=kpi_config.threshold_green,
        threshold_yellow=kpi_config.threshold_yellow,
        threshold_red=kpi_config.threshold_red,
        calculation_method=kpi_config.calculation_method,
        is_higher_better=kpi_config.is_higher_better,
        created_by=current_user.id,
        source_update_dttm=datetime.utcnow()
    )

    db.add(kpi)
    await db.commit()
    await db.refresh(kpi)

    return KPIConfigurationResponse.from_orm(kpi)


@router.get("/kpi-configuration", response_model=List[KPIConfigurationResponse])
@require_capabilities(["view_kpi_configuration"])
async def list_kpi_configurations(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    kpi_category: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = Query(1000, le=10000)
):
    """List KPI configurations"""
    stmt = select(KPIConfiguration)

    if kpi_category:
        stmt = stmt.where(KPIConfiguration.kpi_category == kpi_category)
    if is_active is not None:
        stmt = stmt.where(KPIConfiguration.is_active == is_active)

    stmt = stmt.order_by(KPIConfiguration.kpi_name).limit(limit)

    result = await db.execute(stmt)
    kpis = result.scalars().all()

    return [KPIConfigurationResponse.from_orm(k) for k in kpis]
