"""
Planning Hierarchy Configuration API Endpoints

Provides CRUD operations for planning hierarchy configurations.
Customer administrators can configure hierarchy levels for different planning types.
"""

from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel, Field

from app.db.session import get_db as get_async_session
from app.models.planning_hierarchy import (
    PlanningHierarchyConfig,
    SiteHierarchyNode,
    ProductHierarchyNode,
    TimeBucketConfig,
    PlanningHorizonTemplate,
    AggregatedPlan,
    PlanningType,
    SiteHierarchyLevel,
    ProductHierarchyLevel,
    TimeBucketType,
    DEFAULT_PLANNING_TEMPLATES
)
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class PlanningHierarchyConfigCreate(BaseModel):
    """Schema for creating a planning hierarchy configuration."""
    planning_type: PlanningType
    site_hierarchy_level: SiteHierarchyLevel = SiteHierarchyLevel.SITE
    product_hierarchy_level: ProductHierarchyLevel = ProductHierarchyLevel.PRODUCT
    time_bucket: TimeBucketType = TimeBucketType.WEEK
    horizon_months: int = Field(ge=1, le=120, default=6)
    frozen_periods: int = Field(ge=0, default=0)
    slushy_periods: int = Field(ge=0, default=0)
    update_frequency_hours: int = Field(ge=1, default=168)
    powell_policy_class: str = Field(default="vfa", pattern="^(pfa|cfa|vfa|dla)$")
    gnn_model_type: Optional[str] = None
    parent_planning_type: Optional[str] = None
    consistency_tolerance: float = Field(ge=0.01, le=0.50, default=0.10)
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    config_id: Optional[int] = None


class PlanningHierarchyConfigUpdate(BaseModel):
    """Schema for updating a planning hierarchy configuration."""
    site_hierarchy_level: Optional[SiteHierarchyLevel] = None
    product_hierarchy_level: Optional[ProductHierarchyLevel] = None
    time_bucket: Optional[TimeBucketType] = None
    horizon_months: Optional[int] = Field(None, ge=1, le=120)
    frozen_periods: Optional[int] = Field(None, ge=0)
    slushy_periods: Optional[int] = Field(None, ge=0)
    update_frequency_hours: Optional[int] = Field(None, ge=1)
    powell_policy_class: Optional[str] = Field(None, pattern="^(pfa|cfa|vfa|dla)$")
    gnn_model_type: Optional[str] = None
    parent_planning_type: Optional[str] = None
    consistency_tolerance: Optional[float] = Field(None, ge=0.01, le=0.50)
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PlanningHierarchyConfigResponse(BaseModel):
    """Response schema for planning hierarchy configuration."""
    id: int
    customer_id: int
    config_id: Optional[int]
    planning_type: str
    site_hierarchy_level: str
    product_hierarchy_level: str
    time_bucket: str
    horizon_months: int
    frozen_periods: int
    slushy_periods: int
    update_frequency_hours: int
    powell_policy_class: str
    gnn_model_type: Optional[str]
    parent_planning_type: Optional[str]
    consistency_tolerance: float
    name: str
    description: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


class TemplateResponse(BaseModel):
    """Response schema for planning horizon templates."""
    code: str
    name: str
    description: Optional[str]
    planning_type: str
    site_hierarchy_level: str
    product_hierarchy_level: str
    time_bucket: str
    horizon_months: int
    frozen_periods: int
    slushy_periods: int
    update_frequency_hours: int
    powell_policy_class: str
    gnn_model_type: Optional[str]
    parent_template_code: Optional[str]
    consistency_tolerance: float


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/templates", response_model=List[TemplateResponse])
async def list_planning_templates():
    """
    List all available planning horizon templates.

    These are pre-defined templates that can be used as starting points
    for planning hierarchy configuration.
    """
    templates = []
    for template in DEFAULT_PLANNING_TEMPLATES:
        templates.append(TemplateResponse(
            code=template["code"],
            name=template["name"],
            description=template.get("description"),
            planning_type=template["planning_type"].value,
            site_hierarchy_level=template["site_hierarchy_level"].value,
            product_hierarchy_level=template["product_hierarchy_level"].value,
            time_bucket=template["time_bucket"].value,
            horizon_months=template["horizon_months"],
            frozen_periods=template["frozen_periods"],
            slushy_periods=template["slushy_periods"],
            update_frequency_hours=template["update_frequency_hours"],
            powell_policy_class=template["powell_policy_class"],
            gnn_model_type=template.get("gnn_model_type"),
            parent_template_code=template.get("parent_template_code"),
            consistency_tolerance=template["consistency_tolerance"]
        ))
    return templates


@router.get("/configs", response_model=List[PlanningHierarchyConfigResponse])
async def list_planning_configs(
    customer_id: int,
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    List all planning hierarchy configurations for a customer.

    Only customer members can view their customer's configurations.
    """
    # Verify user has access to this customer
    if current_user.customer_id != customer_id and not current_user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this customer's configurations"
        )

    query = select(PlanningHierarchyConfig).where(
        PlanningHierarchyConfig.customer_id == customer_id
    )

    if not include_inactive:
        query = query.where(PlanningHierarchyConfig.is_active == True)

    query = query.order_by(PlanningHierarchyConfig.display_order)

    result = await db.execute(query)
    configs = result.scalars().all()

    return [PlanningHierarchyConfigResponse(
        id=c.id,
        customer_id=c.customer_id,
        config_id=c.config_id,
        planning_type=c.planning_type.value,
        site_hierarchy_level=c.site_hierarchy_level.value,
        product_hierarchy_level=c.product_hierarchy_level.value,
        time_bucket=c.time_bucket.value,
        horizon_months=c.horizon_months,
        frozen_periods=c.frozen_periods,
        slushy_periods=c.slushy_periods,
        update_frequency_hours=c.update_frequency_hours,
        powell_policy_class=c.powell_policy_class,
        gnn_model_type=c.gnn_model_type,
        parent_planning_type=c.parent_planning_type,
        consistency_tolerance=c.consistency_tolerance,
        name=c.name,
        description=c.description,
        is_active=c.is_active
    ) for c in configs]


@router.post("/configs", response_model=PlanningHierarchyConfigResponse)
async def create_planning_config(
    customer_id: int,
    config: PlanningHierarchyConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new planning hierarchy configuration.

    Only customer administrators can create configurations.
    """
    # Verify user is admin of this customer
    if current_user.customer_id != customer_id and not current_user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create configurations for this customer"
        )

    # Check for existing config with same planning type
    existing = await db.execute(
        select(PlanningHierarchyConfig).where(
            and_(
                PlanningHierarchyConfig.customer_id == customer_id,
                PlanningHierarchyConfig.planning_type == config.planning_type,
                PlanningHierarchyConfig.config_id == config.config_id,
                PlanningHierarchyConfig.is_active == True
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active configuration for {config.planning_type.value} already exists"
        )

    db_config = PlanningHierarchyConfig(
        customer_id=customer_id,
        config_id=config.config_id,
        planning_type=config.planning_type,
        site_hierarchy_level=config.site_hierarchy_level,
        product_hierarchy_level=config.product_hierarchy_level,
        time_bucket=config.time_bucket,
        horizon_months=config.horizon_months,
        frozen_periods=config.frozen_periods,
        slushy_periods=config.slushy_periods,
        update_frequency_hours=config.update_frequency_hours,
        powell_policy_class=config.powell_policy_class,
        gnn_model_type=config.gnn_model_type,
        parent_planning_type=config.parent_planning_type,
        consistency_tolerance=config.consistency_tolerance,
        name=config.name,
        description=config.description,
        created_by=current_user.id
    )

    db.add(db_config)
    await db.commit()
    await db.refresh(db_config)

    return PlanningHierarchyConfigResponse(
        id=db_config.id,
        customer_id=db_config.customer_id,
        config_id=db_config.config_id,
        planning_type=db_config.planning_type.value,
        site_hierarchy_level=db_config.site_hierarchy_level.value,
        product_hierarchy_level=db_config.product_hierarchy_level.value,
        time_bucket=db_config.time_bucket.value,
        horizon_months=db_config.horizon_months,
        frozen_periods=db_config.frozen_periods,
        slushy_periods=db_config.slushy_periods,
        update_frequency_hours=db_config.update_frequency_hours,
        powell_policy_class=db_config.powell_policy_class,
        gnn_model_type=db_config.gnn_model_type,
        parent_planning_type=db_config.parent_planning_type,
        consistency_tolerance=db_config.consistency_tolerance,
        name=db_config.name,
        description=db_config.description,
        is_active=db_config.is_active
    )


@router.post("/configs/from-template/{template_code}", response_model=PlanningHierarchyConfigResponse)
async def create_config_from_template(
    customer_id: int,
    template_code: str,
    name: Optional[str] = None,
    config_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a planning configuration from a pre-defined template.

    Templates provide sensible defaults for common planning scenarios.
    """
    # Verify user is admin of this customer
    if current_user.customer_id != customer_id and not current_user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create configurations for this customer"
        )

    # Find template
    template = None
    for t in DEFAULT_PLANNING_TEMPLATES:
        if t["code"] == template_code:
            template = t
            break

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_code}' not found"
        )

    # Create configuration from template
    config_name = name or template["name"]

    db_config = PlanningHierarchyConfig(
        customer_id=customer_id,
        config_id=config_id,
        planning_type=template["planning_type"],
        site_hierarchy_level=template["site_hierarchy_level"],
        product_hierarchy_level=template["product_hierarchy_level"],
        time_bucket=template["time_bucket"],
        horizon_months=template["horizon_months"],
        frozen_periods=template["frozen_periods"],
        slushy_periods=template["slushy_periods"],
        update_frequency_hours=template["update_frequency_hours"],
        powell_policy_class=template["powell_policy_class"],
        gnn_model_type=template.get("gnn_model_type"),
        parent_planning_type=template.get("parent_template_code"),
        consistency_tolerance=template["consistency_tolerance"],
        name=config_name,
        description=template.get("description"),
        created_by=current_user.id
    )

    db.add(db_config)
    await db.commit()
    await db.refresh(db_config)

    return PlanningHierarchyConfigResponse(
        id=db_config.id,
        customer_id=db_config.customer_id,
        config_id=db_config.config_id,
        planning_type=db_config.planning_type.value,
        site_hierarchy_level=db_config.site_hierarchy_level.value,
        product_hierarchy_level=db_config.product_hierarchy_level.value,
        time_bucket=db_config.time_bucket.value,
        horizon_months=db_config.horizon_months,
        frozen_periods=db_config.frozen_periods,
        slushy_periods=db_config.slushy_periods,
        update_frequency_hours=db_config.update_frequency_hours,
        powell_policy_class=db_config.powell_policy_class,
        gnn_model_type=db_config.gnn_model_type,
        parent_planning_type=db_config.parent_planning_type,
        consistency_tolerance=db_config.consistency_tolerance,
        name=db_config.name,
        description=db_config.description,
        is_active=db_config.is_active
    )


@router.put("/configs/{config_id}", response_model=PlanningHierarchyConfigResponse)
async def update_planning_config(
    config_id: int,
    update: PlanningHierarchyConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update a planning hierarchy configuration.

    Only customer administrators can update configurations.
    """
    result = await db.execute(
        select(PlanningHierarchyConfig).where(PlanningHierarchyConfig.id == config_id)
    )
    db_config = result.scalar_one_or_none()

    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration not found"
        )

    # Verify user is admin of this customer
    if current_user.customer_id != db_config.customer_id and not current_user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this configuration"
        )

    # Apply updates
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_config, field, value)

    await db.commit()
    await db.refresh(db_config)

    return PlanningHierarchyConfigResponse(
        id=db_config.id,
        customer_id=db_config.customer_id,
        config_id=db_config.config_id,
        planning_type=db_config.planning_type.value,
        site_hierarchy_level=db_config.site_hierarchy_level.value,
        product_hierarchy_level=db_config.product_hierarchy_level.value,
        time_bucket=db_config.time_bucket.value,
        horizon_months=db_config.horizon_months,
        frozen_periods=db_config.frozen_periods,
        slushy_periods=db_config.slushy_periods,
        update_frequency_hours=db_config.update_frequency_hours,
        powell_policy_class=db_config.powell_policy_class,
        gnn_model_type=db_config.gnn_model_type,
        parent_planning_type=db_config.parent_planning_type,
        consistency_tolerance=db_config.consistency_tolerance,
        name=db_config.name,
        description=db_config.description,
        is_active=db_config.is_active
    )


@router.delete("/configs/{config_id}")
async def delete_planning_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Delete (deactivate) a planning hierarchy configuration.

    Only customer administrators can delete configurations.
    """
    result = await db.execute(
        select(PlanningHierarchyConfig).where(PlanningHierarchyConfig.id == config_id)
    )
    db_config = result.scalar_one_or_none()

    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration not found"
        )

    # Verify user is admin of this customer
    if current_user.customer_id != db_config.customer_id and not current_user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this configuration"
        )

    # Soft delete (deactivate)
    db_config.is_active = False
    await db.commit()

    return {"message": "Configuration deactivated", "id": config_id}


@router.post("/configs/initialize-defaults/{customer_id}")
async def initialize_default_configs(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Initialize a customer with default planning configurations from all templates.

    This creates one configuration for each planning type using the default templates.
    """
    # Verify user is admin of this customer
    if current_user.customer_id != customer_id and not current_user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to initialize configurations for this customer"
        )

    created_configs = []

    for template in DEFAULT_PLANNING_TEMPLATES:
        # Check if config already exists for this planning type
        existing = await db.execute(
            select(PlanningHierarchyConfig).where(
                and_(
                    PlanningHierarchyConfig.customer_id == customer_id,
                    PlanningHierarchyConfig.planning_type == template["planning_type"],
                    PlanningHierarchyConfig.is_active == True
                )
            )
        )
        if existing.scalar_one_or_none():
            continue  # Skip if already exists

        db_config = PlanningHierarchyConfig(
            customer_id=customer_id,
            planning_type=template["planning_type"],
            site_hierarchy_level=template["site_hierarchy_level"],
            product_hierarchy_level=template["product_hierarchy_level"],
            time_bucket=template["time_bucket"],
            horizon_months=template["horizon_months"],
            frozen_periods=template["frozen_periods"],
            slushy_periods=template["slushy_periods"],
            update_frequency_hours=template["update_frequency_hours"],
            powell_policy_class=template["powell_policy_class"],
            gnn_model_type=template.get("gnn_model_type"),
            parent_planning_type=template.get("parent_template_code"),
            consistency_tolerance=template["consistency_tolerance"],
            name=template["name"],
            description=template.get("description"),
            created_by=current_user.id
        )

        db.add(db_config)
        created_configs.append(template["code"])

    await db.commit()

    return {
        "message": f"Initialized {len(created_configs)} planning configurations",
        "created": created_configs
    }
