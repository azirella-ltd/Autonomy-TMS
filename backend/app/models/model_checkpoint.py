"""
Model Checkpoint Registry — SOC II Compliant Checkpoint Storage

Tracks all ML model checkpoints (TRM weights, GNN models, Site tGNN, LightGBM)
with tenant isolation, versioning, and lifecycle management.

Storage architecture:
  PostgreSQL: metadata, version tracking, tenant FK (CASCADE on delete)
  File system: binary checkpoint files at /{tenant_id}/{config_id}/{model_type}/
  Future: S3+KMS for production multi-region deployments

SOC II compliance:
  - tenant_id FK with ON DELETE CASCADE — tenant deletion removes all checkpoints
  - config_id FK with ON DELETE CASCADE — config deletion removes its checkpoints
  - RLS policy enforces tenant isolation at DB level
  - Audit columns (created_by, created_at) for change tracking
  - file_hash for integrity verification

Path convention:
  checkpoints/{tenant_id}/{config_id}/trm/trm_{type}_site{site_id}_v{N}.pt
  checkpoints/{tenant_id}/{config_id}/site_tgnn/{site_key}/site_tgnn_latest.pt
  checkpoints/{tenant_id}/{config_id}/sop_graphsage_best.pt
  checkpoints/{tenant_id}/{config_id}/execution_tgnn_best.pt
  checkpoints/{tenant_id}/{config_id}/lgbm/lgbm_{target}.txt
"""

from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Text, Boolean, DateTime,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from .base import Base


class ModelCheckpoint(Base):
    """Registry entry for a saved model checkpoint file.

    Each row tracks one .pt / .txt / .onnx file on disk (or in S3).
    The binary data is NOT stored in PostgreSQL — only metadata and
    the file path/key. This keeps the DB lean while providing
    lifecycle management via FK CASCADE.
    """
    __tablename__ = "model_checkpoints"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # ── Tenant & Config Isolation (SOC II) ───────────────────────────────
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    config_id = Column(
        Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # ── Model Identity ───────────────────────────────────────────────────
    model_type = Column(String(50), nullable=False)
    # "trm_atp_executor", "trm_po_creation", ..., "trm_inventory_buffer",
    # "site_tgnn", "sop_graphsage", "execution_tgnn", "lgbm_forecast"

    site_key = Column(String(100), nullable=True)
    # Site identifier (plant code, warehouse code) — NULL for network-wide models

    version = Column(Integer, nullable=False, default=1)
    # Monotonically increasing per (config_id, model_type, site_key)

    # ── Storage Location ─────────────────────────────────────────────────
    storage_backend = Column(String(20), nullable=False, default="filesystem")
    # "filesystem", "s3", "postgresql" (for small models stored as BYTEA)

    file_path = Column(String(500), nullable=False)
    # Filesystem: checkpoints/{tenant_id}/{config_id}/trm/trm_atp_site1562_v1.pt
    # S3: s3://autonomy-checkpoints/{tenant_id}/{config_id}/trm/...

    file_size_bytes = Column(BigInteger, nullable=True)
    file_hash = Column(String(64), nullable=True)
    # SHA-256 hash for integrity verification

    # ── Model Metadata ───────────────────────────────────────────────────
    model_class = Column(String(100), nullable=True)
    # Python class name: "NarrowTRM", "SiteTGNN", "SOPGraphSAGE"

    state_dim = Column(Integer, nullable=True)
    parameter_count = Column(BigInteger, nullable=True)

    training_phase = Column(String(30), nullable=True)
    # "phase1_bc", "phase2_rl", "phase3_production", "cdc_retrain"

    training_metadata = Column(JSONB, nullable=True)
    # {loss, decision_rate, epochs, learning_rate, stigmergic_phase, ...}

    # ── Lifecycle ────────────────────────────────────────────────────────
    is_active = Column(Boolean, nullable=False, default=True)
    # Only one checkpoint per (config, model_type, site_key) should be active

    is_best = Column(Boolean, nullable=False, default=False)
    # Marks the best-performing version (may differ from latest)

    superseded_by = Column(BigInteger, ForeignKey("model_checkpoints.id", ondelete="SET NULL"), nullable=True)
    # Points to the newer checkpoint that replaced this one

    # ── Audit (SOC II CC7.1) ─────────────────────────────────────────────
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)
    # Optional TTL for automatic cleanup of old versions

    __table_args__ = (
        Index("ix_ckpt_tenant_config", "tenant_id", "config_id"),
        Index("ix_ckpt_model_site", "config_id", "model_type", "site_key"),
        Index("ix_ckpt_active", "config_id", "model_type", "site_key", "is_active"),
        UniqueConstraint("config_id", "model_type", "site_key", "version",
                         name="uq_ckpt_version"),
    )


class TrainingDataset(Base):
    """Registry entry for a training dataset used to train a model.

    Tracks which data was used to train which model version — required
    for SOC II audit trail and reproducibility.

    The actual data may be in PostgreSQL (powell_*_decisions tables),
    in files (SimPy outputs, BC curriculum), or generated on-the-fly.
    This table records the provenance, not the data itself.
    """
    __tablename__ = "training_datasets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    config_id = Column(
        Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # ── Dataset Identity ─────────────────────────────────────────────────
    dataset_type = Column(String(50), nullable=False)
    # "bc_curriculum", "rl_replay", "simulation_traces", "decision_outcomes",
    # "coordinated_sim", "cdc_retraining"

    model_type = Column(String(50), nullable=True)
    # Which model type this dataset trains (NULL = generic)

    # ── Storage ──────────────────────────────────────────────────────────
    storage_backend = Column(String(20), nullable=False, default="postgresql")
    # "postgresql" (data in powell_*_decisions tables),
    # "filesystem" (CSV/Parquet files), "s3"

    storage_reference = Column(String(500), nullable=True)
    # For postgresql: "powell_atp_decisions WHERE config_id=94 AND created_at >= '2026-03-01'"
    # For filesystem: "training_data/{tenant_id}/{config_id}/bc_phase1.parquet"
    # For s3: "s3://autonomy-training/{tenant_id}/..."

    # ── Provenance ───────────────────────────────────────────────────────
    record_count = Column(BigInteger, nullable=True)
    date_range_start = Column(DateTime, nullable=True)
    date_range_end = Column(DateTime, nullable=True)

    source_description = Column(Text, nullable=True)
    # "Phase 1 BC from StochasticCurriculumWrapper, 50K samples × 3 sub-phases"
    # "Decision-outcome pairs from powell_atp_decisions, 4h feedback horizon"

    # ── Linked Checkpoint ────────────────────────────────────────────────
    checkpoint_id = Column(BigInteger, ForeignKey("model_checkpoints.id", ondelete="SET NULL"), nullable=True)
    # Which checkpoint was trained from this dataset

    # ── Data Quality ─────────────────────────────────────────────────────
    data_hash = Column(String(64), nullable=True)
    # SHA-256 of the dataset content for reproducibility verification

    quality_metrics = Column(JSONB, nullable=True)
    # {completeness, class_balance, outlier_fraction, ...}

    # ── Security Classification (SOC II) ─────────────────────────────────
    contains_customer_data = Column(Boolean, nullable=False, default=False)
    # True if dataset contains real customer supply chain patterns
    # (vs synthetic/simulated data which has lower sensitivity)

    data_classification = Column(String(30), nullable=False, default="confidential")
    # "confidential" (real customer data), "internal" (synthetic/simulation),
    # "public" (demo/sample data)

    # ── Audit ────────────────────────────────────────────────────────────
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_tds_tenant_config", "tenant_id", "config_id"),
        Index("ix_tds_type", "dataset_type", "model_type"),
    )
