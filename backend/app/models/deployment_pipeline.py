"""
Deployment Pipeline DB Model

Tracks end-to-end pipeline runs for the Demo System Builder:
  Step 1: Seed Config
  Step 2: Deterministic Simulation
  Step 3: Stochastic Monte Carlo
  Step 4: Convert Training Data
  Step 5: Train Models (S&OP + tGNN + TRMs)
  Step 6: Generate Day 1 CSVs
  Step 7: Generate Day 2 CSVs
"""

from datetime import datetime
from typing import Optional, Dict
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, JSON, DateTime,
    ForeignKey, Text, Index
)
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class DeploymentPipelineRun(Base):
    """
    Record of a deployment pipeline execution.

    Each run chains 7 steps, tracking progress and results.
    Pipeline is resumable from any failed step.
    """
    __tablename__ = "deployment_pipeline_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Ownership
    customer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("customers.id"), index=True)

    # Config template used
    config_template: Mapped[str] = mapped_column(String(100), nullable=False)
    config_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("supply_chain_configs.id")
    )

    # Pipeline state
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, running, completed, failed, cancelled
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, default=7)

    # Per-step status tracking (JSON)
    # { "1": {"status": "completed", "elapsed": 12.3, "details": {...}},
    #   "2": {"status": "running", "progress": 0.45}, ... }
    step_statuses: Mapped[Dict] = mapped_column(JSON, default=dict)

    # Pipeline parameters
    parameters: Mapped[Dict] = mapped_column(JSON, default=lambda: {
        "periods": 52,
        "monte_carlo_runs": 128,
        "epochs": 50,
        "device": "cpu",
        "seed": 42,
        "demand_noise_cv": 0.15,
        "day2_profile": "mixed",
    })

    # Results
    results: Mapped[Dict] = mapped_column(JSON, default=dict)
    # { "config_id": 5, "gnn_samples": 6656, "trm_records": 15000,
    #   "day1_zip": "/path/to/zip", "day2_zip": "/path/to/zip",
    #   "checkpoints": {"sop": "...", "tgnn": "...", "trm_atp": "..."} }

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Error
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_step: Mapped[Optional[int]] = mapped_column(Integer)

    # Audit
    triggered_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_pipeline_status', 'status', 'created_at'),
        Index('idx_pipeline_customer', 'customer_id', 'created_at'),
    )
