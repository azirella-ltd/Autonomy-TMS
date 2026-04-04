"""
Training Corpus Model — Unified training data for all 4 planning layers.

See docs/internal/architecture/UNIFIED_TRAINING_CORPUS.md for full architecture.

This is the SINGLE source of truth for all agent training data:
- Layer 1 (TRMs): per-decision samples from simulation
- Layer 2 (Site tGNN): aggregated by (site, time window)
- Layer 3 (Tactical tGNNs): aggregated by (scenario, period)
- Layer 4 (S&OP GraphSAGE): aggregated by (scenario) with inferred theta*

Real outcomes from powell_*_decisions post-provisioning append as new
Layer 1 samples with origin='real'. The aggregator re-runs to produce
updated higher-layer samples.
"""

from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, DateTime, ForeignKey, Index, Numeric,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from .base import Base


class TrainingCorpusSample(Base):
    """One training sample at some layer of the planning stack.

    layer values:
      1.0  = TRM decision (finest granularity)
      1.5  = Site tGNN aggregate (per site, per time window)
      2.0  = Tactical tGNN aggregate (per network, per period, per domain)
      4.0  = S&OP GraphSAGE aggregate (per scenario, with theta*)

    All layers share the same table — filtered by the `layer` column.
    The `sample_data` JSONB field holds layer-specific payload.
    """

    __tablename__ = "training_corpus"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    config_id = Column(
        Integer,
        ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Layer identifier (1.0, 1.5, 2.0, 4.0)
    layer = Column(Numeric(3, 1), nullable=False)

    # Scenario ID — UUID of the perturbation, or "real_{decision_id}" for real outcomes
    scenario_id = Column(String(64), nullable=True)

    # Origin: "perturbation" (from Digital Twin sim) or "real" (from live decision)
    origin = Column(String(20), nullable=False, default="perturbation")

    # Layer 1 specific
    trm_type = Column(String(50), nullable=True)
    product_id = Column(String(100), nullable=True)

    # Layer 1, 1.5 specific
    site_id = Column(String(100), nullable=True)

    # Layer 2 specific
    period = Column(String(20), nullable=True)

    # Layer 2 specific — "window" is a reserved PostgreSQL keyword, so the
    # attribute is named time_window in Python but the column is quoted "window"
    time_window = Column("window", String(20), nullable=True)

    # The full sample payload (TRM features, network graph, theta*, etc.)
    sample_data = Column(JSONB, nullable=False)

    # Aggregate reward (for sorting/filtering high-quality samples)
    reward = Column(Float, nullable=True)

    # Training weight (decays with age; real outcomes get higher weight)
    weight = Column(Float, nullable=False, default=1.0)

    # Link back to the powell_*_decisions row if origin='real'
    decision_id = Column(BigInteger, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index("idx_corpus_tenant_config", "tenant_id", "config_id"),
        Index("idx_corpus_config_layer", "config_id", "layer"),
        Index("idx_corpus_config_scenario", "config_id", "scenario_id"),
        Index("idx_corpus_config_origin", "config_id", "origin", "created_at"),
        Index("idx_corpus_trm_type", "config_id", "trm_type"),
        Index("idx_corpus_site", "config_id", "site_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "config_id": self.config_id,
            "layer": float(self.layer),
            "scenario_id": self.scenario_id,
            "origin": self.origin,
            "trm_type": self.trm_type,
            "site_id": self.site_id,
            "product_id": self.product_id,
            "period": self.period,
            "window": self.time_window,
            "reward": self.reward,
            "weight": self.weight,
            "decision_id": self.decision_id,
            "sample_data": self.sample_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
