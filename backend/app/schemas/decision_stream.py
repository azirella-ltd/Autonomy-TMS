"""
Pydantic Schemas for Decision Stream API

The Decision Stream is the LLM-First UI that surfaces pending TRM decisions,
CDC alerts, and condition monitor signals in a conversational "inbox" format.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================

class DecisionAction(str, Enum):
    ACCEPT = "accept"
    INSPECT = "inspect"
    MODIFY = "modify"      # Override with changed values
    CANCEL = "cancel"      # Reject the action entirely (no execution)
    OVERRIDE = "override"  # Backward compat: treated as MODIFY
    REJECT = "reject"      # Backward compat: treated as CANCEL


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


# ============================================================================
# Decision Items
# ============================================================================

class PendingDecisionItem(BaseModel):
    """A single pending TRM decision surfaced in the stream."""
    id: int
    decision_type: str = Field(
        ..., description="TRM type: atp, po_creation, rebalancing, order_tracking, etc."
    )
    summary: str = Field(..., description="Human-readable one-line summary")
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    urgency: Optional[str] = Field(None, description="Urgency label: Critical, High, Medium, Low, Routine")
    urgency_score: Optional[float] = Field(None, description="Raw urgency score 0-1 (for sorting)")
    likelihood: Optional[str] = Field(None, description="Likelihood label: Almost Certain, Likely, Possible, Unlikely, Never")
    likelihood_score: Optional[float] = Field(None, description="Raw likelihood score 0-1 (for sorting)")
    economic_impact: Optional[float] = Field(None, description="Estimated $ impact")
    suggested_action: Optional[str] = Field(None, description="What the TRM recommends")
    reason: Optional[str] = Field(None, description="Short reason code (e.g. capacity_constraint, expedite)")
    decision_reasoning: Optional[str] = Field(
        None, description="Full English explanation of why the TRM/tGNN/GraphSAGE made this decision"
    )
    deep_link: str = Field(..., description="Frontend route for Console deep-link")
    created_at: Optional[datetime] = None
    editable_values: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Current decision values that can be modified during override (decision-type-specific)",
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional context fields from the decision"
    )
    needs_attention: Optional[bool] = Field(
        default=None,
        description="True if this decision requires human review (agent uncertain)",
    )
    auto_actioned: Optional[bool] = Field(
        default=None,
        description="True if the agent auto-actioned this decision (high confidence)",
    )

    class Config:
        from_attributes = True


class AlertItem(BaseModel):
    """A CDC trigger or condition monitor alert."""
    id: Optional[int] = None
    alert_type: str = Field(..., description="CDC trigger type or condition type")
    message: str
    severity: AlertSeverity = AlertSeverity.WARNING
    source: str = Field(default="cdc", description="'cdc' or 'condition_monitor'")
    created_at: Optional[datetime] = None
    context: Optional[Dict[str, Any]] = None


# ============================================================================
# Digest Response
# ============================================================================

class DecisionDigestResponse(BaseModel):
    """Response for GET /decision-stream/digest."""
    digest_text: str = Field(
        ..., description="LLM-synthesized natural language digest paragraph"
    )
    decisions: List[PendingDecisionItem] = Field(default_factory=list)
    alerts: List[AlertItem] = Field(default_factory=list)
    total_pending: int = 0
    config_id: Optional[int] = None


# ============================================================================
# Action Request/Response
# ============================================================================

class DecisionActionRequest(BaseModel):
    """Request to act on a decision (accept/override/reject)."""
    decision_id: int
    decision_type: str = Field(
        ..., description="TRM type to dispatch to correct powell table"
    )
    action: DecisionAction
    override_reason_code: Optional[str] = None
    override_reason_text: Optional[str] = None
    override_values: Optional[Dict[str, Any]] = None


class DecisionActionResponse(BaseModel):
    """Response after acting on a decision."""
    success: bool = True
    message: str
    decision_id: int
    new_status: str


# ============================================================================
# Chat Request/Response
# ============================================================================

class DecisionStreamChatRequest(BaseModel):
    """Request for conversational interaction in the stream."""
    message: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    config_id: Optional[int] = None


class DataBlock(BaseModel):
    """Structured data for inline visualization in chat messages.

    block_type determines frontend rendering:
      - metrics_row:  Array of KPI cards  (data.metrics[])
      - table:        Data table           (data.columns[], data.rows[][])
      - inventory_bar: Inventory position  (data.on_hand, .in_transit, .allocated, etc.)
      - alert:        Alert box            (data.severity, data.message)
    """
    block_type: str
    title: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class DecisionStreamChatResponse(BaseModel):
    """Response from the conversational stream."""
    response: str
    conversation_id: str
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_followups: List[str] = Field(default_factory=list)
    embedded_decisions: Optional[List[PendingDecisionItem]] = None
    data_blocks: List[DataBlock] = Field(
        default_factory=list,
        description="Structured data blocks for inline visualization (charts, tables, KPI cards)",
    )
