"""
Powell Training Configuration Models

Configures AI model training for the Powell framework:
1. S&OP GraphSAGE - trained on aggregated hierarchy data
2. Execution tGNN - trained on detailed transactional data
3. TRM models - role-specific training for each TRM type

Key Insight: One dataset generates training data at detailed level,
then aggregates to hierarchy levels for S&OP GraphSAGE training.
The Group Admin configures which hierarchy levels to use.
"""

from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, JSON, DateTime,
    ForeignKey, Enum as SAEnum, Text, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from .base import Base


class TRMType(str, Enum):
    """TRM role types — all 11 narrow execution decision scopes."""
    ATP_EXECUTOR = "ATP_EXECUTOR"
    REBALANCING = "REBALANCING"
    PO_CREATION = "PO_CREATION"
    ORDER_TRACKING = "ORDER_TRACKING"
    INVENTORY_BUFFER = "INVENTORY_BUFFER"
    MO_EXECUTION = "MO_EXECUTION"
    TO_EXECUTION = "TO_EXECUTION"
    QUALITY_DISPOSITION = "QUALITY_DISPOSITION"
    MAINTENANCE_SCHEDULING = "MAINTENANCE_SCHEDULING"
    SUBCONTRACTING = "SUBCONTRACTING"
    FORECAST_ADJUSTMENT = "FORECAST_ADJUSTMENT"

    # Backward compatibility alias (DB may still have SAFETY_STOCK)
    SAFETY_STOCK = "SAFETY_STOCK"


class TrainingStatus(str, Enum):
    """Status of training job"""
    PENDING = "pending"
    GENERATING_DATA = "generating_data"
    TRAINING_SOP = "training_sop"  # Training S&OP GraphSAGE
    TRAINING_TGNN = "training_tgnn"  # Training Execution tGNN
    TRAINING_TRM = "training_trm"  # Training TRM models
    COMPLETED = "completed"
    FAILED = "failed"


class LearningPhase(str, Enum):
    """Per-site TRM learning-depth phases"""
    ENGINE_IMITATION = "engine_imitation"           # Phase 1: BC from deterministic engines
    CONTEXT_LEARNING = "context_learning"           # Phase 2: Supervised from expert overrides
    OUTCOME_OPTIMIZATION = "outcome_optimization"   # Phase 3: RL/VFA from replay buffer


class PhaseStatus(str, Enum):
    """Status of a single learning phase"""
    PENDING = "pending"
    TRAINING = "training"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"  # TRM type not applicable for this site


# TRM applicability by site master type.
# Mirrors site_capabilities.py get_active_trms() — kept in sync for DB-layer
# references (TRMSiteTrainingConfig).  The canonical source of truth for
# runtime hive composition is site_capabilities.py.
TRM_APPLICABILITY = {
    "manufacturer": [
        TRMType.ATP_EXECUTOR, TRMType.ORDER_TRACKING, TRMType.INVENTORY_BUFFER,
        TRMType.FORECAST_ADJUSTMENT, TRMType.QUALITY_DISPOSITION, TRMType.PO_CREATION,
        TRMType.SUBCONTRACTING, TRMType.MAINTENANCE_SCHEDULING, TRMType.MO_EXECUTION,
        TRMType.TO_EXECUTION, TRMType.REBALANCING,
    ],
    "inventory": [
        TRMType.ATP_EXECUTOR, TRMType.ORDER_TRACKING, TRMType.INVENTORY_BUFFER,
        TRMType.FORECAST_ADJUSTMENT, TRMType.TO_EXECUTION, TRMType.REBALANCING,
        TRMType.PO_CREATION,
    ],
    # External TradingPartner sites — no TRM hive
    "vendor": [],
    "customer": [],
}


class PowellTrainingConfig(Base):
    """
    Master training configuration for Powell framework AI models.

    Links to PlanningHierarchyConfig for hierarchy level settings.
    Controls which models to train and with what parameters.

    Owned by Group Admin - they decide:
    - Which hierarchy levels for S&OP (via PlanningHierarchyConfig)
    - Training parameters for each model tier
    - Which TRM roles to train
    """
    __tablename__ = "powell_training_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Ownership
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    config_id: Mapped[int] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Link to planning hierarchy config for S&OP level
    sop_hierarchy_config_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("planning_hierarchy_config.id")
    )

    # Link to planning hierarchy config for execution level
    execution_hierarchy_config_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("planning_hierarchy_config.id")
    )

    # =========================================================================
    # Data Generation Settings
    # =========================================================================

    # Number of simulation runs to generate training data
    num_simulation_runs: Mapped[int] = mapped_column(Integer, default=128)

    # Timesteps per simulation run
    timesteps_per_run: Mapped[int] = mapped_column(Integer, default=64)

    # History window for temporal features
    history_window: Mapped[int] = mapped_column(Integer, default=52)

    # Forecast horizon
    forecast_horizon: Mapped[int] = mapped_column(Integer, default=8)

    # Demand patterns to include in training data
    demand_patterns: Mapped[Dict] = mapped_column(JSON, default=lambda: {
        "random": 0.3,
        "seasonal": 0.3,
        "step": 0.2,
        "trend": 0.2
    })

    # =========================================================================
    # S&OP GraphSAGE Training Settings
    # =========================================================================

    train_sop_graphsage: Mapped[bool] = mapped_column(Boolean, default=True)

    # Architecture
    sop_hidden_dim: Mapped[int] = mapped_column(Integer, default=128)
    sop_embedding_dim: Mapped[int] = mapped_column(Integer, default=64)
    sop_num_layers: Mapped[int] = mapped_column(Integer, default=3)

    # Training
    sop_epochs: Mapped[int] = mapped_column(Integer, default=50)
    sop_learning_rate: Mapped[float] = mapped_column(Float, default=1e-3)
    sop_batch_size: Mapped[int] = mapped_column(Integer, default=32)

    # How often to retrain (hours)
    sop_retrain_frequency_hours: Mapped[int] = mapped_column(Integer, default=168)  # Weekly

    # =========================================================================
    # Execution tGNN Training Settings
    # =========================================================================

    train_execution_tgnn: Mapped[bool] = mapped_column(Boolean, default=True)

    # Architecture
    tgnn_hidden_dim: Mapped[int] = mapped_column(Integer, default=128)
    tgnn_window_size: Mapped[int] = mapped_column(Integer, default=10)
    tgnn_num_layers: Mapped[int] = mapped_column(Integer, default=2)

    # Training
    tgnn_epochs: Mapped[int] = mapped_column(Integer, default=100)
    tgnn_learning_rate: Mapped[float] = mapped_column(Float, default=1e-3)
    tgnn_batch_size: Mapped[int] = mapped_column(Integer, default=32)

    # How often to retrain (hours)
    tgnn_retrain_frequency_hours: Mapped[int] = mapped_column(Integer, default=24)  # Daily

    # =========================================================================
    # TRM Training Settings (applies to all TRM types)
    # =========================================================================

    trm_training_method: Mapped[str] = mapped_column(String(50), default="hybrid")
    trm_bc_epochs: Mapped[int] = mapped_column(Integer, default=20)
    trm_rl_epochs: Mapped[int] = mapped_column(Integer, default=80)
    trm_learning_rate: Mapped[float] = mapped_column(Float, default=1e-4)
    trm_batch_size: Mapped[int] = mapped_column(Integer, default=64)

    # =========================================================================
    # State
    # =========================================================================

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))

    # Last training run info
    last_training_started: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_training_completed: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_training_status: Mapped[Optional[str]] = mapped_column(String(50))
    last_training_error: Mapped[Optional[str]] = mapped_column(Text)


class TRMTrainingConfig(Base):
    """
    Per-TRM-type training configuration.

    Each TRM role has different:
    - Input features (state representation)
    - Output actions (decision space)
    - Reward function (what makes a good decision)
    - Training data requirements
    """
    __tablename__ = "trm_training_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Link to master config
    powell_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("powell_training_config.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # TRM type
    trm_type: Mapped[TRMType] = mapped_column(
        SAEnum(TRMType, name="trm_type_enum"),
        nullable=False
    )

    # Whether to train this TRM
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # =========================================================================
    # TRM-Specific Settings
    # =========================================================================

    # Model architecture
    state_dim: Mapped[int] = mapped_column(Integer, default=26)
    hidden_dim: Mapped[int] = mapped_column(Integer, default=128)
    num_heads: Mapped[int] = mapped_column(Integer, default=4)
    num_layers: Mapped[int] = mapped_column(Integer, default=2)

    # Training parameters (overrides if set)
    epochs: Mapped[Optional[int]] = mapped_column(Integer)
    learning_rate: Mapped[Optional[float]] = mapped_column(Float)
    batch_size: Mapped[Optional[int]] = mapped_column(Integer)

    # Reward function weights (JSON - varies by TRM type)
    reward_weights: Mapped[Dict] = mapped_column(JSON, default=dict)

    # How often to retrain
    retrain_frequency_hours: Mapped[int] = mapped_column(Integer, default=24)

    # Minimum samples before training
    min_training_samples: Mapped[int] = mapped_column(Integer, default=1000)

    # =========================================================================
    # State
    # =========================================================================

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Last training info
    last_trained: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_training_samples: Mapped[Optional[int]] = mapped_column(Integer)
    last_training_loss: Mapped[Optional[float]] = mapped_column(Float)
    model_checkpoint_path: Mapped[Optional[str]] = mapped_column(String(255))


class TrainingRun(Base):
    """
    Record of a training run.

    Tracks the full pipeline: data generation → S&OP → tGNN → TRMs
    """
    __tablename__ = "powell_training_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Link to config
    powell_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("powell_training_config.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Run info
    status: Mapped[TrainingStatus] = mapped_column(
        SAEnum(TrainingStatus, name="training_status_enum"),
        default=TrainingStatus.PENDING
    )

    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Progress
    current_phase: Mapped[str] = mapped_column(String(50), default="pending")
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0)

    # Data generation results
    samples_generated: Mapped[Optional[int]] = mapped_column(Integer)
    data_generation_time_seconds: Mapped[Optional[float]] = mapped_column(Float)

    # S&OP training results
    sop_epochs_completed: Mapped[Optional[int]] = mapped_column(Integer)
    sop_final_loss: Mapped[Optional[float]] = mapped_column(Float)
    sop_training_time_seconds: Mapped[Optional[float]] = mapped_column(Float)
    sop_checkpoint_path: Mapped[Optional[str]] = mapped_column(String(255))

    # tGNN training results
    tgnn_epochs_completed: Mapped[Optional[int]] = mapped_column(Integer)
    tgnn_final_loss: Mapped[Optional[float]] = mapped_column(Float)
    tgnn_training_time_seconds: Mapped[Optional[float]] = mapped_column(Float)
    tgnn_checkpoint_path: Mapped[Optional[str]] = mapped_column(String(255))

    # TRM training results (JSON - per TRM type, legacy)
    trm_results: Mapped[Dict] = mapped_column(JSON, default=dict)

    # Per-site TRM training results (JSON - per site × TRM type)
    trm_site_results: Mapped[Dict] = mapped_column(JSON, default=dict)

    # Error info
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_phase: Mapped[Optional[str]] = mapped_column(String(50))

    # User who triggered
    triggered_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))


# Default reward weights per TRM type
DEFAULT_TRM_REWARD_WEIGHTS = {
    TRMType.ATP_EXECUTOR: {
        "fill_rate": 0.4,
        "on_time_bonus": 0.2,
        "priority_weight": 0.2,
        "fairness_penalty": 0.2,
    },
    TRMType.REBALANCING: {
        "service_improvement": 0.5,
        "transfer_cost_penalty": 0.3,
        "balance_improvement": 0.2,
    },
    TRMType.PO_CREATION: {
        "stockout_penalty": 0.4,
        "dos_target_reward": 0.3,
        "cost_efficiency": 0.2,
        "timing_accuracy": 0.1,
    },
    TRMType.ORDER_TRACKING: {
        "correct_exception_detection": 0.4,
        "resolution_speed": 0.3,
        "escalation_appropriateness": 0.3,
    },
    TRMType.INVENTORY_BUFFER: {
        "stockout_penalty": 0.4,
        "dos_target_reward": 0.3,
        "excess_cost_penalty": 0.2,
        "stability_bonus": 0.1,
    },
    TRMType.MO_EXECUTION: {
        "on_time_completion": 0.3,
        "sequence_efficiency": 0.3,
        "utilization": 0.2,
        "changeover_penalty": 0.2,
    },
    TRMType.TO_EXECUTION: {
        "on_time_delivery": 0.4,
        "consolidation_bonus": 0.3,
        "cost_efficiency": 0.3,
    },
    TRMType.QUALITY_DISPOSITION: {
        "correct_disposition": 0.5,
        "cost_efficiency": 0.3,
        "throughput_impact": 0.2,
    },
    TRMType.MAINTENANCE_SCHEDULING: {
        "uptime_improvement": 0.4,
        "cost_efficiency": 0.3,
        "schedule_adherence": 0.3,
    },
    TRMType.SUBCONTRACTING: {
        "cost_efficiency": 0.4,
        "quality_score": 0.3,
        "lead_time_adherence": 0.3,
    },
    TRMType.FORECAST_ADJUSTMENT: {
        "forecast_accuracy": 0.5,
        "signal_relevance": 0.3,
        "adjustment_stability": 0.2,
    },
    # Legacy alias — same weights as INVENTORY_BUFFER
    TRMType.SAFETY_STOCK: {
        "stockout_penalty": 0.4,
        "dos_target_reward": 0.3,
        "excess_cost_penalty": 0.2,
        "stability_bonus": 0.1,
    },
}


class TRMSiteTrainingConfig(Base):
    """
    Per-site × per-TRM-type training configuration and progress.

    Tracks the 3-phase learning-depth curriculum for each (site, TRM type) pair:
    - Phase 1: Engine Imitation (BC) — always available
    - Phase 2: Context Learning (Supervised) — requires ≥500 expert decisions
    - Phase 3: Outcome Optimization (RL/VFA) — requires ≥1000 outcome records
    """
    __tablename__ = "trm_site_training_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Link to master config
    powell_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("powell_training_config.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Site info
    site_id: Mapped[int] = mapped_column(Integer, ForeignKey("site.id"), nullable=False, index=True)
    site_name: Mapped[str] = mapped_column(String(100), nullable=False)
    master_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # TRM type
    trm_type: Mapped[str] = mapped_column(
        SAEnum(TRMType, name="trm_type_enum", create_constraint=False),
        nullable=False
    )

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # =========================================================================
    # Phase 1: Engine Imitation (Behavioral Cloning)
    # =========================================================================
    phase1_status: Mapped[str] = mapped_column(
        String(20), default=PhaseStatus.PENDING.value
    )
    phase1_epochs_completed: Mapped[int] = mapped_column(Integer, default=0)
    phase1_epochs_target: Mapped[int] = mapped_column(Integer, default=20)
    phase1_loss: Mapped[Optional[float]] = mapped_column(Float)
    phase1_accuracy: Mapped[Optional[float]] = mapped_column(Float)

    # =========================================================================
    # Phase 2: Context Learning (Supervised from expert overrides)
    # =========================================================================
    phase2_status: Mapped[str] = mapped_column(
        String(20), default=PhaseStatus.PENDING.value
    )
    phase2_epochs_completed: Mapped[int] = mapped_column(Integer, default=0)
    phase2_epochs_target: Mapped[int] = mapped_column(Integer, default=50)
    phase2_loss: Mapped[Optional[float]] = mapped_column(Float)
    phase2_accuracy: Mapped[Optional[float]] = mapped_column(Float)
    phase2_expert_samples: Mapped[int] = mapped_column(Integer, default=0)
    phase2_min_samples: Mapped[int] = mapped_column(Integer, default=500)

    # =========================================================================
    # Phase 3: Outcome Optimization (RL/VFA)
    # =========================================================================
    phase3_status: Mapped[str] = mapped_column(
        String(20), default=PhaseStatus.PENDING.value
    )
    phase3_epochs_completed: Mapped[int] = mapped_column(Integer, default=0)
    phase3_epochs_target: Mapped[int] = mapped_column(Integer, default=80)
    phase3_loss: Mapped[Optional[float]] = mapped_column(Float)
    phase3_reward_mean: Mapped[Optional[float]] = mapped_column(Float)
    phase3_outcome_samples: Mapped[int] = mapped_column(Integer, default=0)
    phase3_min_samples: Mapped[int] = mapped_column(Integer, default=1000)

    # =========================================================================
    # Model State
    # =========================================================================
    model_checkpoint_path: Mapped[Optional[str]] = mapped_column(String(255))
    model_version: Mapped[int] = mapped_column(Integer, default=0)

    # Evaluation metrics
    eval_accuracy: Mapped[Optional[float]] = mapped_column(Float)
    eval_vs_engine_improvement: Mapped[Optional[float]] = mapped_column(Float)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_trained_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint('powell_config_id', 'site_id', 'trm_type',
                         name='uq_site_trm_config'),
        Index('idx_site_training_config_site', 'site_id', 'trm_type'),
    )


class TRMBaseModel(Base):
    """
    Base model per (group, master_type, trm_type) for cold-start.

    When a new site is added, it can initialize from the base model
    for its master_type instead of training from scratch.
    """
    __tablename__ = "trm_base_model"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    master_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trm_type: Mapped[str] = mapped_column(
        SAEnum(TRMType, name="trm_type_enum", create_constraint=False),
        nullable=False
    )

    checkpoint_path: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Aggregation stats
    sites_trained_on: Mapped[int] = mapped_column(Integer, default=0)
    total_samples: Mapped[int] = mapped_column(Integer, default=0)
    final_loss: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'master_type', 'trm_type',
                         name='uq_base_model_tenant_type'),
    )
