"""
Sourcing Rules API Endpoints

REST API for managing sourcing rules (transfer, buy, manufacture).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.api import deps
from app.models.user import User
from app.models.sc_entities import SourcingRules
from pydantic import BaseModel, Field


router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class SourcingRuleBase(BaseModel):
    product_id: str = Field(..., description="Product ID")
    product_group_id: Optional[str] = Field(None, description="Product group ID")
    from_site_id: Optional[int] = Field(None, description="Source site ID")
    to_site_id: int = Field(..., description="Destination site ID")
    tpartner_id: Optional[str] = Field(None, description="Trading partner ID (for buy type)")
    sourcing_rule_type: str = Field(..., description="Rule type: transfer, buy, manufacture")
    sourcing_priority: int = Field(1, ge=1, description="Priority (1 = highest)")
    sourcing_ratio: float = Field(1.0, ge=0.0, le=1.0, description="Allocation ratio")
    min_quantity: Optional[float] = Field(0, ge=0, description="Minimum order quantity")
    max_quantity: Optional[float] = Field(999999, ge=0, description="Maximum order quantity")
    lot_size: Optional[float] = Field(1, ge=1, description="Lot size for ordering")
    transportation_lane_id: Optional[str] = Field(None, description="Transportation lane ID")
    production_process_id: Optional[str] = Field(None, description="Production process ID")
    is_active: str = Field("Y", description="Active flag (Y/N)")


class SourcingRuleCreate(SourcingRuleBase):
    pass


class SourcingRuleUpdate(BaseModel):
    product_id: Optional[str] = None
    product_group_id: Optional[str] = None
    from_site_id: Optional[int] = None
    to_site_id: Optional[int] = None
    tpartner_id: Optional[str] = None
    sourcing_rule_type: Optional[str] = None
    sourcing_priority: Optional[int] = None
    sourcing_ratio: Optional[float] = None
    min_quantity: Optional[float] = None
    max_quantity: Optional[float] = None
    lot_size: Optional[float] = None
    transportation_lane_id: Optional[str] = None
    production_process_id: Optional[str] = None
    is_active: Optional[str] = None


class SourcingRuleResponse(SourcingRuleBase):
    id: str
    company_id: Optional[str]
    eff_start_date: Optional[datetime]
    eff_end_date: Optional[datetime]
    is_deleted: Optional[str]
    source: Optional[str]
    source_event_id: Optional[str]
    source_update_dttm: Optional[datetime]

    class Config:
        from_attributes = True


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/", response_model=List[SourcingRuleResponse])
def list_sourcing_rules(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    product_id: Optional[str] = None,
    site_id: Optional[int] = None,
    rule_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[SourcingRuleResponse]:
    """
    List sourcing rules with optional filtering.

    Filters:
    - product_id: Filter by product
    - site_id: Filter by from_site_id or to_site_id
    - rule_type: Filter by sourcing_rule_type (transfer, buy, manufacture)
    """
    query = db.query(SourcingRules).filter(
        SourcingRules.is_deleted != "Y"
    )

    if product_id:
        query = query.filter(SourcingRules.product_id == product_id)

    if site_id:
        query = query.filter(
            (SourcingRules.from_site_id == site_id) |
            (SourcingRules.to_site_id == site_id)
        )

    if rule_type:
        query = query.filter(SourcingRules.sourcing_rule_type == rule_type)

    # Order by priority (ascending) then by id
    query = query.order_by(
        SourcingRules.sourcing_priority,
        SourcingRules.id
    )

    rules = query.offset(skip).limit(limit).all()

    return rules


@router.get("/{rule_id}", response_model=SourcingRuleResponse)
def get_sourcing_rule(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    rule_id: str,
) -> SourcingRuleResponse:
    """
    Get a specific sourcing rule by ID.
    """
    rule = db.query(SourcingRules).filter(
        SourcingRules.id == rule_id,
        SourcingRules.is_deleted != "Y"
    ).first()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sourcing rule {rule_id} not found"
        )

    return rule


@router.post("/", response_model=SourcingRuleResponse, status_code=status.HTTP_201_CREATED)
def create_sourcing_rule(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    rule_in: SourcingRuleCreate,
) -> SourcingRuleResponse:
    """
    Create a new sourcing rule.

    Validates:
    - Rule type is one of: transfer, buy, manufacture
    - For transfer: from_site_id and to_site_id are required
    - For buy: to_site_id and tpartner_id are required
    - For manufacture: to_site_id is required
    """
    # Validate rule type
    if rule_in.sourcing_rule_type not in ["transfer", "buy", "manufacture"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sourcing_rule_type must be one of: transfer, buy, manufacture"
        )

    # Validate required fields based on rule type
    if rule_in.sourcing_rule_type == "transfer":
        if not rule_in.from_site_id or not rule_in.to_site_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transfer rules require both from_site_id and to_site_id"
            )

    if rule_in.sourcing_rule_type == "buy":
        if not rule_in.to_site_id or not rule_in.tpartner_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Buy rules require both to_site_id and tpartner_id"
            )

    if rule_in.sourcing_rule_type == "manufacture":
        if not rule_in.to_site_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manufacture rules require to_site_id"
            )

    # Generate ID
    import uuid
    rule_id = f"SR-{uuid.uuid4().hex[:8].upper()}"

    # Create rule
    rule = SourcingRules(
        id=rule_id,
        company_id=None,  # TODO: Set from user's company
        product_id=rule_in.product_id,
        product_group_id=rule_in.product_group_id,
        from_site_id=rule_in.from_site_id,
        to_site_id=rule_in.to_site_id,
        tpartner_id=rule_in.tpartner_id,
        sourcing_rule_type=rule_in.sourcing_rule_type,
        sourcing_priority=rule_in.sourcing_priority,
        sourcing_ratio=rule_in.sourcing_ratio,
        min_quantity=rule_in.min_quantity,
        max_quantity=rule_in.max_quantity,
        lot_size=rule_in.lot_size,
        transportation_lane_id=rule_in.transportation_lane_id,
        production_process_id=rule_in.production_process_id,
        eff_start_date=datetime.utcnow(),
        eff_end_date=None,
        is_active=rule_in.is_active,
        is_deleted="N",
        source="UI",
        source_event_id=rule_id,
        source_update_dttm=datetime.utcnow(),
    )

    db.add(rule)
    db.commit()
    db.refresh(rule)

    return rule


@router.put("/{rule_id}", response_model=SourcingRuleResponse)
def update_sourcing_rule(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    rule_id: str,
    rule_in: SourcingRuleUpdate,
) -> SourcingRuleResponse:
    """
    Update an existing sourcing rule.
    """
    rule = db.query(SourcingRules).filter(
        SourcingRules.id == rule_id,
        SourcingRules.is_deleted != "Y"
    ).first()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sourcing rule {rule_id} not found"
        )

    # Update fields
    update_data = rule_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    # Update metadata
    rule.source_update_dttm = datetime.utcnow()

    db.add(rule)
    db.commit()
    db.refresh(rule)

    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sourcing_rule(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    rule_id: str,
):
    """
    Soft delete a sourcing rule (sets is_deleted = 'Y').
    """
    rule = db.query(SourcingRules).filter(
        SourcingRules.id == rule_id,
        SourcingRules.is_deleted != "Y"
    ).first()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sourcing rule {rule_id} not found"
        )

    # Soft delete
    rule.is_deleted = "Y"
    rule.is_active = "N"
    rule.source_update_dttm = datetime.utcnow()

    db.add(rule)
    db.commit()

    return None


@router.get("/products/{product_id}/rules", response_model=List[SourcingRuleResponse])
def get_product_sourcing_rules(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    product_id: str,
) -> List[SourcingRuleResponse]:
    """
    Get all sourcing rules for a specific product, ordered by priority.
    """
    rules = db.query(SourcingRules).filter(
        SourcingRules.product_id == product_id,
        SourcingRules.is_active == "Y",
        SourcingRules.is_deleted != "Y"
    ).order_by(
        SourcingRules.sourcing_priority,
        SourcingRules.id
    ).all()

    return rules
