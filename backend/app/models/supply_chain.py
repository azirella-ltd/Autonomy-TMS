"""Supplemental supply-chain tables that hang off the primary Scenario / ScenarioUser models.

Terminology (Feb 2026):
- Game -> Scenario
- Player -> ScenarioUser
- GameRound -> ScenarioRound
- PlayerRound -> ScenarioUserPeriod
- PlayerInventory -> ScenarioUserInventory
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Dict, Any

from sqlalchemy import Column, Integer, Float, DateTime, Date, ForeignKey, JSON, Boolean, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship

from .base import Base


class RoundPhase(str, Enum):
    """Round phase for DAG-ordered sequential execution"""
    FULFILLMENT = "FULFILLMENT"  # Phase 1: Users fulfill downstream orders (ATP-based)
    REPLENISHMENT = "REPLENISHMENT"  # Phase 2: Users order from upstream (after receiving POs)
    DECISION = "DECISION"  # Legacy: Single decision point (original simulation)
    COMPLETED = "COMPLETED"  # Round finished, ready for next round


class ScenarioUserInventory(Base):
    """Inventory state for a scenario user in the simulation."""
    __tablename__ = "scenario_user_inventory"

    id = Column(Integer, primary_key=True, index=True)
    scenario_user_id = Column(Integer, ForeignKey("scenario_users.id", ondelete="CASCADE"), nullable=False)
    current_stock = Column(Integer, default=12)
    incoming_shipments = Column(JSON, default=list)
    backorders = Column(Integer, default=0)
    cost = Column(Float, default=0.0)

    scenario_user = relationship("ScenarioUser", back_populates="inventory")


class Order(Base):
    """Orders placed by scenario users during simulation rounds."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False)
    scenario_user_id = Column(Integer, ForeignKey("scenario_users.id", ondelete="CASCADE"), nullable=False)
    round_number = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    scenario_user = relationship("ScenarioUser", back_populates="orders")
    scenario = relationship("Scenario")


class ScenarioRound(Base):
    """A round within a scenario/simulation.

    Tracks the state and progress of each round including demand,
    completion status, and DAG sequential execution phases.
    """
    __tablename__ = "scenario_rounds"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False)
    round_number = Column(Integer, nullable=False)
    customer_demand = Column(Integer, nullable=False)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)

    # DAG Sequential Execution fields
    current_phase = Column(SQLEnum(RoundPhase), server_default="DECISION", nullable=False)
    phase_started_at = Column(DateTime, nullable=True)
    fulfillment_completed_at = Column(DateTime, nullable=True)
    replenishment_completed_at = Column(DateTime, nullable=True)

    scenario = relationship("Scenario", back_populates="supply_chain_rounds")
    scenario_user_periods = relationship("ScenarioUserPeriod", back_populates="scenario_round")


class UpstreamOrderType(str, Enum):
    """Type of upstream order created during replenishment"""
    TO = "TO"  # Transfer Order (inter-site inventory movement)
    PO = "PO"  # Purchase Order (external vendor purchase)
    MO = "MO"  # Manufacturing Order (production at manufacturer node)


class ScenarioUserPeriod(Base):
    """Per-scenario-user metrics and state for each round.

    Tracks orders placed/received, inventory changes, costs,
    and DAG execution phase details.
    """
    __tablename__ = "scenario_user_periods"

    id = Column(Integer, primary_key=True, index=True)
    scenario_user_id = Column(Integer, ForeignKey("scenario_users.id", ondelete="CASCADE"), nullable=False)
    scenario_round_id = Column(Integer, ForeignKey("scenario_rounds.id", ondelete="CASCADE"), nullable=False)
    order_placed = Column(Integer, nullable=False)
    order_received = Column(Integer, default=0)
    inventory_before = Column(Integer, nullable=False)
    inventory_after = Column(Integer, nullable=False)
    backorders_before = Column(Integer, default=0)
    backorders_after = Column(Integer, default=0)
    holding_cost = Column(Float, default=0.0)
    backorder_cost = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)
    comment = Column(JSON, default=dict)

    # DAG Sequential Execution - Upstream Order Tracking (Phase 1)
    upstream_order_id = Column(Integer, nullable=True)
    upstream_order_type = Column(SQLEnum(UpstreamOrderType), nullable=True)
    round_phase = Column(SQLEnum(RoundPhase), default=RoundPhase.DECISION, nullable=False)

    # Fulfillment phase tracking
    fulfillment_qty = Column(Integer, nullable=True)
    fulfillment_submitted_at = Column(DateTime, nullable=True)

    # Replenishment phase tracking
    replenishment_qty = Column(Integer, nullable=True)
    replenishment_submitted_at = Column(DateTime, nullable=True)

    scenario_user = relationship("ScenarioUser", back_populates="scenario_user_periods")
    scenario_round = relationship("ScenarioRound", back_populates="scenario_user_periods")

    __table_args__ = (
        Index('idx_sup_upstream_order', 'upstream_order_id', 'upstream_order_type'),
        Index('idx_sup_round_phase', 'scenario_round_id', 'round_phase'),
        Index('idx_sup_scenario_user_round', 'scenario_user_id', 'scenario_round_id'),
    )


# Backward compatibility aliases (temporary - remove after full migration)
ParticipantInventory = ScenarioUserInventory
ParticipantRound = ScenarioUserPeriod
PlayerInventory = ScenarioUserInventory
PlayerRound = ScenarioUserPeriod
GameRound = ScenarioRound
AlternativeRound = ScenarioRound
