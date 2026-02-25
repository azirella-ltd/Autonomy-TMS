"""
Planning Decision Models

Full audit trail for planning decisions:
- OVERRIDE: Human override of AI recommendation
- ACCEPT: Accept AI recommendation as-is
- REJECT: Reject AI recommendation
- DEFER: Defer decision to next cycle

Part of the Planning Cycle Management system.
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, JSON, Boolean,
    Enum, Text, Index, Float
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from typing import Dict, Any

from .base import Base


class DecisionAction(str, enum.Enum):
    """Types of planning decision actions"""
    OVERRIDE = "override"     # Override AI recommendation
    ACCEPT = "accept"         # Accept AI recommendation
    REJECT = "reject"         # Reject AI recommendation
    DEFER = "defer"           # Defer to next cycle
    MODIFY = "modify"         # Modify recommendation parameters
    ESCALATE = "escalate"     # Escalate for approval
    CREATE = "create"         # Create new (no prior recommendation)


class DecisionCategory(str, enum.Enum):
    """Categories of planning decisions"""
    DEMAND_FORECAST = "demand_forecast"
    SUPPLY_PLAN = "supply_plan"
    INVENTORY_TARGET = "inventory_target"
    SAFETY_STOCK = "safety_stock"
    SOURCING = "sourcing"
    PRODUCTION = "production"
    DISTRIBUTION = "distribution"
    PRICING = "pricing"
    CAPACITY = "capacity"
    LEAD_TIME = "lead_time"
    ORDER = "order"


class DecisionStatus(str, enum.Enum):
    """Status of decision"""
    PENDING = "pending"                   # Awaiting action
    APPLIED = "applied"                   # Decision applied to snapshot
    PENDING_APPROVAL = "pending_approval" # Awaiting approval
    APPROVED = "approved"                 # Approved but not yet applied
    REJECTED = "rejected"                 # Decision rejected by approver
    REVERTED = "reverted"                 # Decision was reverted
    SUPERSEDED = "superseded"             # Replaced by newer decision


class DecisionPriority(str, enum.Enum):
    """Priority levels for decisions"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PlanningDecision(Base):
    """
    Planning Decision with Full Audit Trail

    Tracks all decisions made during planning cycles:
    - Links to AI recommendations
    - Captures reason codes and justifications
    - Maintains before/after state
    - Tracks approval workflow
    """
    __tablename__ = "planning_decisions"

    id = Column(Integer, primary_key=True, index=True)

    # Context
    cycle_id = Column(Integer, ForeignKey("planning_cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)

    # Decision Identification
    decision_code = Column(String(50), nullable=False, index=True)  # Unique code for reference
    category = Column(Enum(DecisionCategory, name="decision_category"), nullable=False, index=True)
    action = Column(Enum(DecisionAction, name="decision_action"), nullable=False, index=True)
    priority = Column(Enum(DecisionPriority, name="decision_priority"), default=DecisionPriority.MEDIUM)

    # Scope
    product_id = Column(String(100), nullable=True, index=True)
    site_id = Column(String(100), nullable=True, index=True)
    vendor_id = Column(String(100), nullable=True)
    customer_id = Column(String(100), nullable=True)
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)

    # AI Recommendation Reference
    recommendation_id = Column(String(36), nullable=True, index=True)  # UUID from recommendations table
    ai_recommended_value = Column(JSON, nullable=True)  # Original AI recommendation
    ai_confidence = Column(Float, nullable=True)  # AI confidence score (0-1)
    ai_explanation = Column(Text, nullable=True)  # AI's reasoning

    # Decision Details
    original_value = Column(JSON, nullable=True)      # Value before decision
    decided_value = Column(JSON, nullable=True)       # Value after decision
    value_delta = Column(JSON, nullable=True)         # Change summary
    # {
    #   "field": "quantity",
    #   "original": 1000,
    #   "decided": 1200,
    #   "delta": 200,
    #   "delta_percent": 20.0
    # }

    # Justification
    reason_code = Column(String(50), nullable=True, index=True)
    reason_text = Column(Text, nullable=True)
    supporting_data = Column(JSON, nullable=True)  # Attachments, links, evidence
    # {
    #   "documents": ["customer_email.pdf"],
    #   "links": ["https://crm.example.com/opportunity/123"],
    #   "notes": "Customer confirmed additional 200 units"
    # }

    # Impact Assessment
    estimated_impact = Column(JSON, nullable=True)
    # {
    #   "financial": {"cost_delta": 5000, "revenue_delta": 12000},
    #   "service_level": {"otif_delta": 0.02, "direction": "positive"},
    #   "inventory": {"dos_delta": 3, "holding_cost_delta": 500},
    #   "risk": {"level": "low", "description": "Minimal supply risk"}
    # }
    actual_impact = Column(JSON, nullable=True)  # Captured after execution

    # Status & Approval
    status = Column(Enum(DecisionStatus, name="decision_status"), default=DecisionStatus.PENDING, nullable=False, index=True)
    requires_approval = Column(Boolean, default=False)
    approval_level = Column(String(50), nullable=True)  # manager, director, vp
    approval_threshold = Column(Float, nullable=True)  # Value threshold that triggered approval

    # Decision Maker
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime, nullable=True)

    # Approval Chain
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_notes = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Execution
    applied_at = Column(DateTime, nullable=True)
    applied_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    execution_snapshot_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="SET NULL"), nullable=True)

    # Reversion
    reverted_at = Column(DateTime, nullable=True)
    reverted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revert_reason = Column(Text, nullable=True)
    revert_snapshot_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="SET NULL"), nullable=True)

    # Supersession
    superseded_by_id = Column(Integer, ForeignKey("planning_decisions.id", ondelete="SET NULL"), nullable=True)
    supersedes_id = Column(Integer, ForeignKey("planning_decisions.id", ondelete="SET NULL"), nullable=True)

    # Collaboration
    assigned_to = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    watchers = Column(JSON, nullable=True)  # List of user IDs
    comments_count = Column(Integer, default=0)

    # Tags and Classification
    tags = Column(JSON, nullable=True)  # ["urgent", "customer-request", "cost-saving"]

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    cycle = relationship("PlanningCycle", back_populates="decisions")
    snapshot = relationship("PlanningSnapshot",
                           foreign_keys=[snapshot_id],
                           back_populates="decisions")
    execution_snapshot = relationship("PlanningSnapshot", foreign_keys=[execution_snapshot_id])
    revert_snapshot = relationship("PlanningSnapshot", foreign_keys=[revert_snapshot_id])
    decider = relationship("User", foreign_keys=[decided_by])
    approver = relationship("User", foreign_keys=[approved_by])
    applier = relationship("User", foreign_keys=[applied_by])
    reverter = relationship("User", foreign_keys=[reverted_by])
    assignee = relationship("User", foreign_keys=[assigned_to])
    superseded_by = relationship("PlanningDecision",
                                 remote_side=[id],
                                 foreign_keys=[superseded_by_id])
    supersedes = relationship("PlanningDecision",
                             remote_side=[id],
                             foreign_keys=[supersedes_id])
    history = relationship("DecisionHistory", back_populates="decision", cascade="all, delete-orphan",
                          order_by="DecisionHistory.changed_at")
    customer = relationship("Customer")

    __table_args__ = (
        Index("ix_decision_cycle_category", "cycle_id", "category"),
        Index("ix_decision_product_site", "product_id", "site_id"),
        Index("ix_decision_status_created", "status", "created_at"),
        Index("ix_decision_action_category", "action", "category"),
        Index("ix_decision_reason_code", "reason_code"),
        Index("ix_decision_assigned", "assigned_to", "status"),
    )

    def __repr__(self):
        return f"<PlanningDecision(id={self.id}, code={self.decision_code}, action={self.action.value})>"

    @property
    def is_pending(self) -> bool:
        return self.status in (DecisionStatus.PENDING, DecisionStatus.PENDING_APPROVAL)

    @property
    def is_final(self) -> bool:
        return self.status in (DecisionStatus.APPLIED, DecisionStatus.REJECTED,
                              DecisionStatus.REVERTED, DecisionStatus.SUPERSEDED)

    @property
    def can_be_reverted(self) -> bool:
        return self.status == DecisionStatus.APPLIED and self.reverted_at is None

    def calculate_delta(self) -> Dict[str, Any]:
        """Calculate delta between original and decided values"""
        if not self.original_value or not self.decided_value:
            return {}

        delta = {}
        for key in set(list(self.original_value.keys()) + list(self.decided_value.keys())):
            orig = self.original_value.get(key)
            decided = self.decided_value.get(key)
            if orig != decided:
                delta[key] = {
                    "original": orig,
                    "decided": decided
                }
                if isinstance(orig, (int, float)) and isinstance(decided, (int, float)):
                    delta[key]["delta"] = decided - orig
                    if orig != 0:
                        delta[key]["delta_percent"] = ((decided - orig) / orig) * 100

        return delta


class DecisionHistory(Base):
    """
    Decision History/Audit Trail

    Tracks all state changes for a decision.
    """
    __tablename__ = "decision_history"

    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(Integer, ForeignKey("planning_decisions.id", ondelete="CASCADE"), nullable=False, index=True)

    # Change Info
    change_type = Column(String(50), nullable=False)  # created, updated, status_change, approved, applied, reverted
    previous_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=True)

    # Change Details
    changed_fields = Column(JSON, nullable=True)  # List of field names that changed
    previous_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=True)

    # Actor
    changed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    change_notes = Column(Text, nullable=True)

    # Context
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    session_id = Column(String(100), nullable=True)

    # Related Objects
    snapshot_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    decision = relationship("PlanningDecision", back_populates="history")
    actor = relationship("User", foreign_keys=[changed_by])
    snapshot = relationship("PlanningSnapshot")

    __table_args__ = (
        Index("ix_decision_history_decision_at", "decision_id", "changed_at"),
        Index("ix_decision_history_type", "decision_id", "change_type"),
    )

    def __repr__(self):
        return f"<DecisionHistory(id={self.id}, decision={self.decision_id}, type={self.change_type})>"


class DecisionComment(Base):
    """
    Comments on planning decisions for collaboration.
    """
    __tablename__ = "decision_comments"

    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(Integer, ForeignKey("planning_decisions.id", ondelete="CASCADE"), nullable=False, index=True)

    # Comment Content
    content = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=False)  # Internal notes vs public comments

    # Threading
    parent_comment_id = Column(Integer, ForeignKey("decision_comments.id", ondelete="SET NULL"), nullable=True)

    # Mentions
    mentioned_users = Column(JSON, nullable=True)  # List of user IDs

    # Audit
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, nullable=True)
    is_edited = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)

    # Relationships
    decision = relationship("PlanningDecision")
    author = relationship("User", foreign_keys=[created_by])
    parent = relationship("DecisionComment", remote_side=[id], backref="replies")

    __table_args__ = (
        Index("ix_decision_comment_decision", "decision_id", "created_at"),
    )

    def __repr__(self):
        return f"<DecisionComment(id={self.id}, decision={self.decision_id})>"


# Reason Code definitions with descriptions
DECISION_REASON_CODES: Dict[str, Dict[str, str]] = {
    "MARKET_INTELLIGENCE": {
        "label": "Market Intelligence",
        "description": "Based on market intelligence or customer feedback"
    },
    "CUSTOMER_COMMITMENT": {
        "label": "Customer Commitment",
        "description": "Customer commitment or contract obligation"
    },
    "CAPACITY_CONSTRAINT": {
        "label": "Capacity Constraint",
        "description": "Production or warehouse capacity constraint"
    },
    "SUPPLIER_ISSUE": {
        "label": "Supplier Issue",
        "description": "Supplier reliability or availability concern"
    },
    "QUALITY_CONCERN": {
        "label": "Quality Concern",
        "description": "Quality or compliance requirement"
    },
    "COST_OPTIMIZATION": {
        "label": "Cost Optimization",
        "description": "Cost reduction or budget optimization"
    },
    "RISK_MITIGATION": {
        "label": "Risk Mitigation",
        "description": "Risk mitigation strategy"
    },
    "PROMOTIONAL_EVENT": {
        "label": "Promotional Event",
        "description": "Promotional or marketing event"
    },
    "SEASONAL_ADJUSTMENT": {
        "label": "Seasonal Adjustment",
        "description": "Seasonal pattern adjustment"
    },
    "NEW_PRODUCT": {
        "label": "New Product",
        "description": "New product introduction"
    },
    "PHASE_OUT": {
        "label": "Phase Out",
        "description": "Product discontinuation or phase-out"
    },
    "REGULATORY": {
        "label": "Regulatory",
        "description": "Regulatory or compliance requirement"
    },
    "DEMAND_SIGNAL": {
        "label": "Demand Signal",
        "description": "Strong demand signal from sales or POS data"
    },
    "INVENTORY_REBALANCE": {
        "label": "Inventory Rebalance",
        "description": "Network inventory rebalancing"
    },
    "LOGISTICS_CONSTRAINT": {
        "label": "Logistics Constraint",
        "description": "Transportation or logistics constraint"
    },
    "OTHER": {
        "label": "Other",
        "description": "Other reason - see notes"
    }
}

# Approval thresholds by decision category
DEFAULT_APPROVAL_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    DecisionCategory.DEMAND_FORECAST.value: {
        "manager": {"delta_percent": 10},  # >10% change needs manager
        "director": {"delta_percent": 25},  # >25% change needs director
        "vp": {"delta_percent": 50}         # >50% change needs VP
    },
    DecisionCategory.SUPPLY_PLAN.value: {
        "manager": {"cost_delta": 10000},
        "director": {"cost_delta": 50000},
        "vp": {"cost_delta": 100000}
    },
    DecisionCategory.SAFETY_STOCK.value: {
        "manager": {"delta_percent": 20},
        "director": {"delta_percent": 50}
    },
    DecisionCategory.SOURCING.value: {
        "manager": {"cost_delta": 25000},
        "director": {"cost_delta": 100000},
        "vp": {"cost_delta": 500000}
    }
}
