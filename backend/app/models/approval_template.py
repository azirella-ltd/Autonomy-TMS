"""
Approval Workflow Template Models

Configurable approval workflows for supply chain entities:
- Purchase Orders (PO)
- Transfer Orders (TO)
- Manufacturing Orders (MO)
- Supply Plans
- Recommendations
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Text, ForeignKey, Index
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.models.base import Base


class ApprovalTemplate(Base):
    """
    Approval Workflow Template

    Defines multi-level approval rules for different entity types.
    Supports:
    - Sequential approvals (Level 1 → Level 2 → Level 3)
    - Parallel approvals (any approver at level can approve)
    - Conditional routing based on amount, category, etc.
    """

    __tablename__ = "approval_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Template identification
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # Entity type this template applies to
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # purchase_order, transfer_order, manufacturing_order, supply_plan, recommendation

    # Approval levels configuration (JSON array)
    # Example:
    # [
    #   {"level": 1, "name": "Manager Review", "approvers": [1, 2], "type": "any", "timeout_hours": 24},
    #   {"level": 2, "name": "Finance Approval", "approvers": [3], "type": "all", "timeout_hours": 48}
    # ]
    levels: Mapped[dict] = mapped_column(JSON, default=list)

    # Conditions for when this template applies (JSON)
    # Example:
    # {
    #   "min_value": 10000,
    #   "max_value": 100000,
    #   "categories": ["critical", "high"],
    #   "regions": ["US", "EU"]
    # }
    conditions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Template settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)  # Lower = higher priority

    # Auto-approval settings
    auto_approve_below: Mapped[Optional[float]] = mapped_column(Integer)  # Auto-approve if value below this
    auto_escalate_after_hours: Mapped[Optional[int]] = mapped_column(Integer)  # Escalate if no response

    # Audit fields
    created_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_approval_template_entity_type', 'entity_type', 'is_active'),
        Index('ix_approval_template_code', 'code'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'code': self.code,
            'entity_type': self.entity_type,
            'levels': self.levels,
            'conditions': self.conditions,
            'is_active': self.is_active,
            'is_default': self.is_default,
            'priority': self.priority,
            'auto_approve_below': self.auto_approve_below,
            'auto_escalate_after_hours': self.auto_escalate_after_hours,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ApprovalRequest(Base):
    """
    Approval Request Instance

    Tracks individual approval requests for entities.
    Links to the template and tracks progress through approval levels.
    """

    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Template reference
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("approval_templates.id"), nullable=False)

    # Entity being approved
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # Request details
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    value: Mapped[Optional[float]] = mapped_column(Integer)  # Total value for threshold checks
    request_data: Mapped[Optional[dict]] = mapped_column(JSON)  # Additional request data

    # Current status
    status: Mapped[str] = mapped_column(String(20), default='pending')
    # pending, in_progress, approved, rejected, cancelled, expired
    current_level: Mapped[int] = mapped_column(Integer, default=1)

    # Requester
    requested_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Completion tracking
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    final_decision_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_approval_request_entity', 'entity_type', 'entity_id'),
        Index('ix_approval_request_status', 'status', 'current_level'),
        Index('ix_approval_request_requester', 'requested_by_id', 'status'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'template_id': self.template_id,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'title': self.title,
            'description': self.description,
            'value': self.value,
            'request_data': self.request_data,
            'status': self.status,
            'current_level': self.current_level,
            'requested_by_id': self.requested_by_id,
            'requested_at': self.requested_at.isoformat() if self.requested_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ApprovalAction(Base):
    """
    Approval Action Log

    Records each approval/rejection action taken on a request.
    Used for audit trail and workflow history.
    """

    __tablename__ = "approval_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Request reference
    request_id: Mapped[int] = mapped_column(Integer, ForeignKey("approval_requests.id"), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)

    # Action details
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # approved, rejected, delegated, comment
    actor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    acted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_approval_action_request', 'request_id', 'level'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'request_id': self.request_id,
            'level': self.level,
            'action': self.action,
            'actor_id': self.actor_id,
            'comment': self.comment,
            'acted_at': self.acted_at.isoformat() if self.acted_at else None,
        }
