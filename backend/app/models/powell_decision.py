"""
Powell Framework Decision Models

Database models for tracking SiteAgent decisions for audit trail and RLHF.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, Boolean, JSON,
    ForeignKey, Index
)
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class SiteAgentDecision(Base):
    """
    Record of a SiteAgent TRM decision.

    Tracks all TRM-adjusted decisions with context, adjustments, and outcomes
    for audit trail and RLHF training data collection.
    """
    __tablename__ = "powell_site_agent_decisions"

    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(String(32), unique=True, index=True, nullable=False)

    # Context
    site_key = Column(String(64), index=True, nullable=False)
    decision_type = Column(String(32), index=True, nullable=False)  # atp_exception, inventory_adjustment, po_timing, cdc_trigger
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Input state
    input_state = Column(JSON)  # Context provided to TRM

    # Deterministic baseline
    deterministic_result = Column(JSON)  # Result from engines without TRM

    # TRM adjustment
    trm_adjustment = Column(JSON)  # Adjustment applied by TRM
    confidence = Column(Float, default=1.0)

    # Final result
    final_result = Column(JSON)  # Final decision after TRM

    # Outcome tracking (filled in later)
    actual_outcome = Column(JSON)  # What actually happened
    outcome_recorded_at = Column(DateTime)

    # Reward signal for RLHF
    reward_signal = Column(Float)

    # Human feedback
    human_feedback = Column(Text)
    human_rating = Column(Integer)  # 1-5 rating
    feedback_recorded_at = Column(DateTime)
    feedback_user_id = Column(Integer, ForeignKey("users.id"))

    # Hive signal context (Sprint 4 — nullable for backward compatibility)
    signal_context = Column(JSON)           # Snapshot of signals read before decision
    urgency_at_time = Column(Float)          # Urgency vector value for this TRM at decision time
    triggered_by = Column(String(200))       # Comma-separated signal types that influenced decision
    signals_emitted = Column(JSON)           # List of signal types emitted after decision
    cycle_phase = Column(String(50))         # DecisionCyclePhase name (SENSE..REFLECT)
    cycle_id = Column(String(100))           # UUID of the decision cycle run

    # Metadata
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), index=True)
    period_number = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Indexes for efficient querying
    __table_args__ = (
        Index("ix_powell_decisions_site_type", "site_key", "decision_type"),
        Index("ix_powell_decisions_timestamp_type", "timestamp", "decision_type"),
        Index("ix_powell_decisions_reward", "reward_signal"),
        Index("ix_powell_decisions_cycle_id", "cycle_id"),
    )


class SiteAgentCheckpoint(Base):
    """
    Model checkpoint for a SiteAgent.

    Tracks trained model versions with performance metrics.
    """
    __tablename__ = "powell_site_agent_checkpoints"

    id = Column(Integer, primary_key=True, index=True)
    checkpoint_id = Column(String(64), unique=True, index=True, nullable=False)

    # Checkpoint metadata
    site_key = Column(String(64), index=True)  # Null for shared models
    model_version = Column(String(32), nullable=False)
    checkpoint_path = Column(String(512), nullable=False)

    # Training info
    training_phase = Column(String(32))  # behavioral_cloning, supervised, rl
    training_samples = Column(Integer)
    training_epochs = Column(Integer)
    training_loss = Column(Float)

    # Validation metrics
    val_loss = Column(Float)
    val_accuracy = Column(Float)
    val_atp_accuracy = Column(Float)
    val_inventory_mae = Column(Float)
    val_po_timing_mae = Column(Float)

    # Performance benchmarks
    benchmark_service_level = Column(Float)
    benchmark_cost_reduction = Column(Float)
    benchmark_vs_baseline = Column(Float)

    # Model config
    model_config = Column(JSON)  # SiteAgentModelConfig as dict

    # Status
    is_active = Column(Boolean, default=False)  # Currently deployed
    is_validated = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    deployed_at = Column(DateTime)
    retired_at = Column(DateTime)

    # Relationships
    training_run_id = Column(Integer)  # Link to training run


class CDCTriggerLog(Base):
    """
    Log of CDC trigger events.

    Records when CDC thresholds were exceeded and actions taken.
    """
    __tablename__ = "powell_cdc_trigger_log"

    id = Column(Integer, primary_key=True, index=True)

    # Context
    site_key = Column(String(64), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Trigger details
    triggered = Column(Boolean, nullable=False)
    reasons = Column(JSON)  # List of TriggerReason values
    severity = Column(String(16))  # info, warning, critical
    recommended_action = Column(String(32))  # ReplanAction value

    # Metrics at trigger time
    metrics_snapshot = Column(JSON)

    # Threshold breaches
    threshold_breaches = Column(JSON)  # {metric: {actual, threshold, deviation}}

    # Action taken
    action_taken = Column(String(32))
    action_user_id = Column(Integer, ForeignKey("users.id"))
    action_timestamp = Column(DateTime)
    action_notes = Column(Text)

    # Outcome
    replan_completed = Column(Boolean, default=False)
    replan_duration_seconds = Column(Integer)
    post_replan_metrics = Column(JSON)

    # Metadata
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), index=True)
    planning_cycle_id = Column(Integer)

    __table_args__ = (
        Index("ix_cdc_trigger_site_time", "site_key", "timestamp"),
    )


class CDCThresholdConfig(Base):
    """
    CDC threshold configuration for a site.

    Allows per-site customization of CDC trigger thresholds.
    """
    __tablename__ = "powell_cdc_thresholds"

    id = Column(Integer, primary_key=True, index=True)

    # Context
    site_key = Column(String(64), index=True, nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), index=True)

    # Thresholds
    demand_deviation = Column(Float, default=0.15)
    inventory_low_pct = Column(Float, default=0.70)
    inventory_high_pct = Column(Float, default=1.50)
    service_level_drop = Column(Float, default=0.05)
    lead_time_increase = Column(Float, default=0.20)
    backlog_growth_days = Column(Integer, default=3)
    supplier_reliability_drop = Column(Float, default=0.10)

    # Cooldown
    cooldown_hours = Column(Integer, default=24)

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"))

    __table_args__ = (
        Index("ix_cdc_thresholds_site_group", "site_key", "group_id"),
    )
