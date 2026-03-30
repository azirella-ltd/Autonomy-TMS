"""
Conformal Prediction Schema Models (SOC II isolated)

Tables in the `conformal` schema for calibration state, observations,
drift detection, and coverage audit. All tenant+config isolated with RLS.

Schema: conformal
- calibration_snapshots: immutable append-only calibration history
- active_predictors: current predictor state per variable×entity
- observation_log: every prediction-vs-actual observation
- drift_events: drift detection and recalibration triggers
- coverage_audit: periodic coverage verification
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, JSON,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.sql import func
from app.models.base import Base


class CalibrationSnapshot(Base):
    """Immutable record of a calibration event. Append-only — never updated."""
    __tablename__ = "calibration_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "config_id", "variable_type", "entity_id", "calibrated_at",
                         name="uq_cal_snapshot"),
        Index("idx_cal_snap_tenant_config", "tenant_id", "config_id"),
        Index("idx_cal_snap_variable", "variable_type", "entity_id"),
        Index("idx_cal_snap_time", "calibrated_at"),
        {"schema": "conformal"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    variable_type = Column(String(50), nullable=False)
    entity_id = Column(String(200), nullable=False)
    alpha = Column(Float, nullable=False, default=0.1)
    quantile = Column(Float)
    empirical_coverage = Column(Float)
    n_samples = Column(Integer, nullable=False, default=0)
    method = Column(String(30), default="split")
    nonconformity_scores = Column(JSON)
    coverage_history = Column(JSON)
    distribution_fit = Column(JSON)
    calibrated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ActivePredictor(Base):
    """Current active predictor state — one row per tenant×config×variable×entity."""
    __tablename__ = "active_predictors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "config_id", "variable_type", "entity_id",
                         name="uq_active_pred"),
        Index("idx_active_pred_tenant", "tenant_id", "config_id"),
        Index("idx_active_pred_variable", "variable_type"),
        {"schema": "conformal"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    variable_type = Column(String(50), nullable=False)
    entity_id = Column(String(200), nullable=False)
    alpha = Column(Float, nullable=False, default=0.1)
    quantile = Column(Float, nullable=False)
    empirical_coverage = Column(Float)
    coverage_guarantee = Column(Float, nullable=False)
    interval_width_mean = Column(Float)
    n_samples = Column(Integer, nullable=False, default=0)
    method = Column(String(30), default="split")
    is_stale = Column(Boolean, default=False)
    last_calibrated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_observation_at = Column(DateTime)
    drift_detected = Column(Boolean, default=False)
    drift_score = Column(Float, default=0.0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class ObservationLog(Base):
    """Every prediction-vs-actual observation for audit trail."""
    __tablename__ = "observation_log"
    __table_args__ = (
        Index("idx_obs_log_tenant", "tenant_id", "config_id"),
        Index("idx_obs_log_variable", "variable_type", "entity_id"),
        Index("idx_obs_log_time", "observed_at"),
        {"schema": "conformal"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    variable_type = Column(String(50), nullable=False)
    entity_id = Column(String(200), nullable=False)
    predicted_value = Column(Float, nullable=False)
    actual_value = Column(Float, nullable=False)
    residual = Column(Float, nullable=False)
    nonconformity_score = Column(Float)
    was_covered = Column(Boolean)
    interval_lower = Column(Float)
    interval_upper = Column(Float)
    source_transaction_type = Column(String(50))
    source_transaction_id = Column(String(100))
    observed_at = Column(DateTime, nullable=False, server_default=func.now())


class DriftEvent(Base):
    """Drift detection events and recalibration triggers."""
    __tablename__ = "drift_events"
    __table_args__ = (
        Index("idx_drift_tenant", "tenant_id", "config_id"),
        {"schema": "conformal"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    variable_type = Column(String(50), nullable=False)
    entity_id = Column(String(200))
    drift_type = Column(String(30), nullable=False)
    drift_score = Column(Float, nullable=False)
    coverage_before = Column(Float)
    coverage_after = Column(Float)
    threshold = Column(Float, nullable=False, default=0.05)
    action_taken = Column(String(30), nullable=False)
    recalibration_snapshot_id = Column(Integer)
    detected_at = Column(DateTime, nullable=False, server_default=func.now())


class CoverageAudit(Base):
    """Periodic coverage verification for SOC II compliance."""
    __tablename__ = "coverage_audit"
    __table_args__ = (
        Index("idx_coverage_audit_tenant", "tenant_id", "config_id"),
        {"schema": "conformal"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    variable_type = Column(String(50), nullable=False)
    entity_id = Column(String(200))
    guaranteed_coverage = Column(Float, nullable=False)
    empirical_coverage = Column(Float, nullable=False)
    n_observations = Column(Integer, nullable=False)
    coverage_gap = Column(Float)
    is_compliant = Column(Boolean, nullable=False)
    audit_window_start = Column(DateTime)
    audit_window_end = Column(DateTime)
    audited_at = Column(DateTime, nullable=False, server_default=func.now())
