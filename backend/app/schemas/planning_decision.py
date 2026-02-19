"""
Planning Decision Pydantic Schemas

Request/response models for planning decision API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DecisionActionEnum(str, Enum):
    """Type of decision action."""
    OVERRIDE = "override"
    ACCEPT = "accept"
    REJECT = "reject"
    DEFER = "defer"
    MODIFY = "modify"
    APPROVE = "approve"
    ESCALATE = "escalate"


class DecisionCategoryEnum(str, Enum):
    """Category of planning decision."""
    DEMAND_FORECAST = "demand_forecast"
    SUPPLY_PLAN = "supply_plan"
    INVENTORY_TARGET = "inventory_target"
    SAFETY_STOCK = "safety_stock"
    SOURCING = "sourcing"
    CAPACITY = "capacity"
    PRICING = "pricing"
    PROMOTION = "promotion"
    NEW_PRODUCT = "new_product"
    PHASE_OUT = "phase_out"
    OTHER = "other"


class DecisionStatusEnum(str, Enum):
    """Status of planning decision."""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    REVERTED = "reverted"


class DecisionPriorityEnum(str, Enum):
    """Priority of planning decision."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================================
# Decision Reason Codes
# ============================================================================

DECISION_REASON_CODES = {
    "MARKET_INTELLIGENCE": "Market intelligence indicates different demand patterns",
    "CUSTOMER_COMMITMENT": "Customer commitment or contract requirement",
    "CAPACITY_CONSTRAINT": "Production or warehouse capacity limitation",
    "SUPPLIER_ISSUE": "Supplier delivery or quality issues",
    "QUALITY_CONCERN": "Product quality or compliance concerns",
    "COST_OPTIMIZATION": "Cost reduction or optimization opportunity",
    "RISK_MITIGATION": "Risk mitigation or safety stock adjustment",
    "PROMOTIONAL_EVENT": "Promotional or marketing event impact",
    "SEASONAL_ADJUSTMENT": "Seasonal demand pattern adjustment",
    "NEW_PRODUCT": "New product introduction considerations",
    "PHASE_OUT": "Product phase-out or discontinuation",
    "REGULATORY": "Regulatory or compliance requirement",
    "STRATEGIC": "Strategic business decision",
    "FORECAST_ERROR": "Correction of forecast error",
    "INVENTORY_POLICY": "Inventory policy change",
    "OTHER": "Other reason (see notes)"
}


# ============================================================================
# Planning Decision Schemas
# ============================================================================

class PlanningDecisionBase(BaseModel):
    """Base schema for planning decision."""
    category: DecisionCategoryEnum = Field(..., description="Category of decision")
    action: DecisionActionEnum = Field(..., description="Type of action taken")

    entity_type: str = Field(..., max_length=100, description="Type of entity affected")
    entity_id: Optional[str] = Field(None, max_length=100, description="ID of specific entity")

    original_value: Optional[Dict[str, Any]] = Field(None, description="Original value before decision")
    decided_value: Optional[Dict[str, Any]] = Field(None, description="New value after decision")

    reason_code: str = Field(..., max_length=50, description="Standardized reason code")
    reason_text: Optional[str] = Field(None, max_length=1000, description="Detailed explanation")

    priority: DecisionPriorityEnum = Field(default=DecisionPriorityEnum.MEDIUM)

    effective_date: Optional[datetime] = Field(None, description="When decision takes effect")
    expiry_date: Optional[datetime] = Field(None, description="When decision expires")


class PlanningDecisionCreate(PlanningDecisionBase):
    """Schema for creating a planning decision."""
    cycle_id: int = Field(..., gt=0, description="Planning cycle this decision belongs to")
    snapshot_id: Optional[int] = Field(None, description="Snapshot where decision was recorded")
    recommendation_id: Optional[int] = Field(None, description="AI recommendation being addressed")

    class Config:
        json_schema_extra = {
            "example": {
                "cycle_id": 1,
                "category": "demand_forecast",
                "action": "override",
                "entity_type": "forecast",
                "entity_id": "SKU-12345",
                "original_value": {"quantity": 1000, "period": "2026-W06"},
                "decided_value": {"quantity": 1200, "period": "2026-W06"},
                "reason_code": "MARKET_INTELLIGENCE",
                "reason_text": "Customer feedback indicates higher demand for Q1 launch",
                "priority": "high"
            }
        }


class PlanningDecisionUpdate(BaseModel):
    """Schema for updating a planning decision."""
    reason_text: Optional[str] = Field(None, max_length=1000)
    priority: Optional[DecisionPriorityEnum] = None
    effective_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None


class PlanningDecisionResponse(PlanningDecisionBase):
    """Schema for planning decision response."""
    id: int
    cycle_id: int
    snapshot_id: Optional[int] = None
    created_by_id: int
    status: DecisionStatusEnum

    recommendation_id: Optional[int] = None
    applied_snapshot_id: Optional[int] = None
    reverted_snapshot_id: Optional[int] = None

    approval_required: bool = False
    approved_by_id: Optional[int] = None
    approved_at: Optional[datetime] = None

    impact_assessment: Optional[Dict[str, Any]] = None

    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 42,
                "cycle_id": 1,
                "category": "demand_forecast",
                "action": "override",
                "entity_type": "forecast",
                "entity_id": "SKU-12345",
                "status": "applied",
                "reason_code": "MARKET_INTELLIGENCE",
                "priority": "high",
                "created_by_id": 5,
                "created_at": "2026-02-01T10:30:00Z",
                "applied_snapshot_id": 16
            }
        }


# ============================================================================
# Decision History Schemas
# ============================================================================

class DecisionHistoryResponse(BaseModel):
    """Schema for decision history entry."""
    id: int
    decision_id: int
    action: str
    old_status: Optional[DecisionStatusEnum] = None
    new_status: DecisionStatusEnum

    changed_by_id: int
    change_reason: Optional[str] = None
    change_details: Optional[Dict[str, Any]] = None

    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Decision Comment Schemas
# ============================================================================

class DecisionCommentCreate(BaseModel):
    """Schema for creating a decision comment."""
    content: str = Field(..., max_length=2000, description="Comment content")
    is_internal: bool = Field(default=False, description="Internal note vs visible comment")

    class Config:
        json_schema_extra = {
            "example": {
                "content": "Verified with sales team - customer confirmed increased order",
                "is_internal": False
            }
        }


class DecisionCommentResponse(BaseModel):
    """Schema for decision comment response."""
    id: int
    decision_id: int
    content: str
    is_internal: bool
    created_by_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Approval Schemas
# ============================================================================

class DecisionApprovalRequest(BaseModel):
    """Request to approve a decision."""
    comment: Optional[str] = Field(None, max_length=500, description="Approval comment")

    class Config:
        json_schema_extra = {
            "example": {
                "comment": "Approved based on Q1 sales projections"
            }
        }


class DecisionRejectRequest(BaseModel):
    """Request to reject a decision."""
    reason: str = Field(..., max_length=500, description="Rejection reason")

    class Config:
        json_schema_extra = {
            "example": {
                "reason": "Insufficient supporting data - please provide customer confirmation"
            }
        }


class DecisionRevertRequest(BaseModel):
    """Request to revert a decision."""
    reason: str = Field(..., max_length=500, description="Revert reason")

    class Config:
        json_schema_extra = {
            "example": {
                "reason": "Customer order was cancelled"
            }
        }


# ============================================================================
# Stats and Summary Schemas
# ============================================================================

class DecisionStatsResponse(BaseModel):
    """Response with decision statistics."""
    total_decisions: int
    by_status: Dict[str, int]
    by_category: Dict[str, int]
    by_action: Dict[str, int]
    pending_approval: int
    applied_this_cycle: int

    class Config:
        json_schema_extra = {
            "example": {
                "total_decisions": 45,
                "by_status": {"applied": 30, "pending_approval": 10, "draft": 5},
                "by_category": {"demand_forecast": 20, "supply_plan": 15, "inventory_target": 10},
                "by_action": {"override": 25, "accept": 15, "reject": 5},
                "pending_approval": 10,
                "applied_this_cycle": 30
            }
        }


class ReasonCodeResponse(BaseModel):
    """Response with available reason codes."""
    code: str
    description: str


class ReasonCodesResponse(BaseModel):
    """Response listing all available reason codes."""
    reason_codes: List[ReasonCodeResponse]


class ApprovalThresholdResponse(BaseModel):
    """Response with approval threshold configuration."""
    category: DecisionCategoryEnum
    amount_threshold: float
    percentage_threshold: float
    requires_approval: bool


class ApprovalThresholdsResponse(BaseModel):
    """Response listing all approval thresholds."""
    thresholds: List[ApprovalThresholdResponse]


# ============================================================================
# List Response Schemas
# ============================================================================

class PlanningDecisionListResponse(BaseModel):
    """Response for listing planning decisions."""
    items: List[PlanningDecisionResponse]
    total: int
    page: int
    page_size: int


class DecisionHistoryListResponse(BaseModel):
    """Response for listing decision history."""
    items: List[DecisionHistoryResponse]
    total: int
