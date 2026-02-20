"""
Collaboration Scenario Model

Stores cross-functional agent collaboration scenarios demonstrating
the Agentic Authorization Protocol (AAP). Each record represents a
complete collaboration lifecycle: trigger → evaluate → authorize → resolve.

Levels:
  - sop: Strategic S&OP-level policy decisions
  - tactical: MPS/MRP-level planning decisions
  - execution: Daily execution decisions (ATP, PO, rebalancing, order tracking)
"""

from datetime import datetime
from typing import Optional, Dict, List, Any
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, JSON, DateTime, Text,
    ForeignKey, Index
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from .base import Base


class CollaborationScenario(Base):
    """
    A cross-functional agent collaboration scenario.

    Captures the full AAP flow: trigger event → authorization requests
    with balanced scorecards → resolution with timeline.
    """
    __tablename__ = "collaboration_scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Context
    config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Scenario identification
    scenario_code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)  # sop, tactical, execution
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, in_progress, resolved, escalated
    priority: Mapped[str] = mapped_column(String(20), default="high")  # low, medium, high, critical

    # Agents involved
    originating_agent: Mapped[str] = mapped_column(String(100), nullable=False)
    target_agents: Mapped[Dict] = mapped_column(JSON, nullable=False)

    # Trigger context
    trigger_event: Mapped[Dict] = mapped_column(JSON, nullable=False)

    # Authorization requests (list of AAP AuthorizationRequest objects)
    authorization_requests: Mapped[Dict] = mapped_column(JSON, nullable=False)

    # Balanced scorecard (aggregate impact)
    balanced_scorecard: Mapped[Dict] = mapped_column(JSON, nullable=False)

    net_benefit: Mapped[Optional[float]] = mapped_column(Float)

    # Resolution
    resolution: Mapped[Optional[Dict]] = mapped_column(JSON)

    # Timeline of events
    timeline: Mapped[Optional[Dict]] = mapped_column(JSON)

    # Human involvement
    assigned_to: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    escalated_to: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index('idx_collab_scenario_group', 'group_id', 'level'),
    )
