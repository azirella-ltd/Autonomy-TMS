"""Supply chain config models — partial re-export from canonical azirella-data-model.

4 classes re-exported from canonical (NodeType, SupplyChainConfig, Site,
TransportationLane). 8 classes remain TMS/SCP-local (MarketDemand, Market,
SupplyChainTrainingArtifact, ConfigDelta, ConfigLineage, DecisionProposal,
AuthorityDefinition, BusinessImpactSnapshot). Event listeners and helpers
also remain local.

Stage 3 Phase 3c — TMS adopts azirella-data-model master subpackage.
"""
from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, JSON, Boolean,
    UniqueConstraint, DateTime,
)
from sqlalchemy.orm import relationship
from typing import Optional
import datetime

from azirella_data_model.base import Base
from enum import Enum as PyEnum

# ── Canonical re-exports ─────────────────────────────────────────────────────
from azirella_data_model.master import (  # noqa: F401
    SupplyChainConfig,
    Site,
    TransportationLane,
    TimeBucket,
)

# NodeType — TMS-local extended version that includes legacy Beer Game site
# types (RETAILER, WHOLESALER, DISTRIBUTOR) not in the canonical enum.
# The canonical NodeType has 8 values; TMS adds 3 legacy values that existing
# DB rows reference. Kept local to avoid polluting the canonical with
# TBG-specific types.
class NodeType(str, PyEnum):
    # Canonical values (same as azirella_data_model.master.NodeType)
    DISTRIBUTION_CENTER = "DISTRIBUTION_CENTER"
    WAREHOUSE = "WAREHOUSE"
    MANUFACTURING_PLANT = "MANUFACTURING_PLANT"
    INVENTORY = "INVENTORY"
    MANUFACTURER = "MANUFACTURER"
    SUPPLIER = "SUPPLIER"
    VENDOR = "VENDOR"
    CUSTOMER = "CUSTOMER"
    # Legacy TBG types — retained for backward compatibility with existing DB rows
    RETAILER = "RETAILER"
    WHOLESALER = "WHOLESALER"
    DISTRIBUTOR = "DISTRIBUTOR"


# ── TMS/SCP-local classes (not in canonical) ─────────────────────────────────

class MarketDemand(Base):
    """Demand pattern configuration per product per customer (TradingPartner)."""
    __tablename__ = "market_demands"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    trading_partner_id = Column(Integer, ForeignKey("trading_partners._id"), nullable=True)
    market_id = Column(Integer, ForeignKey("markets.id"), nullable=True)
    demand_pattern = Column(JSON, default={
        "demand_type": "classic",
        "variability": {"type": "flat", "value": 4},
        "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
        "trend": {"type": "none", "slope": 0, "intercept": 0},
        "parameters": {"initial_demand": 4, "change_week": 15, "final_demand": 12},
        "params": {"initial_demand": 4, "change_week": 15, "final_demand": 12},
    })
    config = relationship("SupplyChainConfig")
    product = relationship("Product")
    trading_partner = relationship("TradingPartner", foreign_keys=[trading_partner_id])
    market = relationship("Market")


class Market(Base):
    """DEPRECATED: Demand pools replaced by TradingPartner(tpartner_type='customer')."""
    __tablename__ = "markets"
    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    company = Column(String(100), nullable=True)
    description = Column(String(255), nullable=True)
    __table_args__ = (UniqueConstraint("config_id", "name", name="uq_market_name_per_config"),)
    config = relationship("SupplyChainConfig")
    demands = relationship("MarketDemand", cascade="all, delete-orphan")


class SupplyChainTrainingArtifact(Base):
    """Records the generated dataset and trained model for a supply chain configuration."""
    __tablename__ = "supply_chain_training_artifacts"
    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    dataset_name = Column(String(255), nullable=False)
    model_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    config = relationship("SupplyChainConfig", back_populates="training_artifacts")


class ConfigDelta(Base):
    """Stores incremental changes (deltas) for supply chain configurations."""
    __tablename__ = "config_deltas"
    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(Integer, nullable=True)
    operation = Column(String(10), nullable=False)
    delta_data = Column(JSON, nullable=False)
    changed_fields = Column(JSON, nullable=True)
    original_values = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    created_by = Column(String(36), nullable=True)
    description = Column(String(500), nullable=True)
    config = relationship("SupplyChainConfig", back_populates="deltas")


class ConfigLineage(Base):
    """Stores the ancestor tree for supply chain configurations."""
    __tablename__ = "config_lineage"
    id = None  # Override Base class id column
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), primary_key=True)
    ancestor_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), primary_key=True)
    depth = Column(Integer, primary_key=True, nullable=False)


class DecisionProposal(Base):
    """Decision proposals for approval workflows."""
    __tablename__ = "decision_proposals"
    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=True)
    parent_scenario_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(200), nullable=False)
    description = Column(String(2000), nullable=True)
    proposed_by = Column(String(100), nullable=True)
    proposed_by_type = Column(String(20), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String(50), nullable=True)
    decision_type = Column(String(50), nullable=True)
    action_params = Column(JSON, nullable=True)
    proposal_metadata = Column(JSON, nullable=True)
    authority_level_required = Column(String(50), nullable=True)
    requires_approval_from = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default='pending')
    business_case = Column(JSON, nullable=True)
    financial_impact = Column(JSON, nullable=True)
    operational_impact = Column(JSON, nullable=True)
    strategic_impact = Column(JSON, nullable=True)
    risk_metrics = Column(JSON, nullable=True)
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(String(1000), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    executed_at = Column(DateTime, nullable=True)
    scenario = relationship("SupplyChainConfig", foreign_keys=[scenario_id], backref="proposals")
    parent_scenario = relationship("SupplyChainConfig", foreign_keys=[parent_scenario_id])
    impact_snapshots = relationship("BusinessImpactSnapshot", back_populates="proposal", cascade="all, delete-orphan")


class AuthorityDefinition(Base):
    """Defines authority levels for agents and humans."""
    __tablename__ = "authority_definitions"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=True)
    agent_id = Column(String(100), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    role = Column(String(50), nullable=True)
    action_type = Column(String(50), nullable=False)
    max_value = Column(Float, nullable=True)
    requires_approval = Column(Boolean, nullable=False, default=True)
    approval_authority = Column(String(50), nullable=True)
    conditions = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tenant = relationship("Tenant")
    config = relationship("SupplyChainConfig")


class BusinessImpactSnapshot(Base):
    """Stores computed business impact metrics for decision proposals."""
    __tablename__ = "business_impact_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    proposal_id = Column(Integer, ForeignKey("decision_proposals.id", ondelete="CASCADE"), nullable=False)
    scenario_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    snapshot_type = Column(String(20), nullable=False)
    planning_horizon = Column(Integer, nullable=False)
    simulation_runs = Column(Integer, nullable=True)
    financial_metrics = Column(JSON, nullable=False)
    customer_metrics = Column(JSON, nullable=False)
    operational_metrics = Column(JSON, nullable=False)
    strategic_metrics = Column(JSON, nullable=False)
    computed_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    proposal = relationship("DecisionProposal", back_populates="impact_snapshots")
    scenario = relationship("SupplyChainConfig")


# ── Backward compatibility aliases ───────────────────────────────────────────
Lane = TransportationLane  # DEPRECATED: Use TransportationLane
Node = Site                # DEPRECATED: Use Site


# ── Slug auto-population on insert ───────────────────────────────────────────
from sqlalchemy import event


def _sanitize_slug(value: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9]+", "-", value or "").strip("-").lower() or "tenant"


@event.listens_for(SupplyChainConfig, "before_insert")
def _populate_config_slug(mapper, connection, target):
    if target.slug:
        return
    tenant_name = None
    try:
        if getattr(target, "tenant", None) is not None:
            tenant_name = target.tenant.name
    except Exception:
        tenant_name = None
    if not tenant_name and target.tenant_id:
        row = connection.execute(
            __import__("sqlalchemy").text("SELECT name FROM tenants WHERE id = :tid"),
            {"tid": target.tenant_id},
        ).fetchone()
        if row:
            tenant_name = row[0]
    slug_base = _sanitize_slug(tenant_name or f"tenant-{target.tenant_id}")
    ts = (target.created_at or datetime.datetime.utcnow()).strftime("%Y%m%dT%H%M%SZ")
    target.slug = f"{slug_base}-{ts}"


@event.listens_for(SupplyChainConfig, "after_insert")
def _finalize_config_slug(mapper, connection, target):
    if not target.slug:
        return
    if target.slug.endswith(f"-c{target.id}"):
        return
    final_slug = f"{target.slug}-c{target.id}"
    connection.execute(
        __import__("sqlalchemy").text("UPDATE supply_chain_configs SET slug = :slug WHERE id = :id"),
        {"slug": final_slug, "id": target.id},
    )
    target.slug = final_slug


def resolve_config_id(db, slug_or_id) -> Optional[int]:
    """Accepts an int id or a string slug; returns the integer config id."""
    if slug_or_id is None:
        return None
    if isinstance(slug_or_id, int):
        return slug_or_id
    s = str(slug_or_id).strip()
    if s.isdigit():
        return int(s)
    from sqlalchemy import text as _text
    row = db.execute(_text("SELECT id FROM supply_chain_configs WHERE slug = :s"), {"s": s}).fetchone()
    return int(row[0]) if row else None
