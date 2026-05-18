"""
Transportation Planning Models

Planning-specific entities for transportation management:
- ShippingForecast: Predicted freight volumes by lane/mode/period
- CapacityTarget: Required carrier capacity by lane/mode
- TransportationPlan: The Plan of Record — load builds, carrier assignments
- TransportationPlanItem: Individual planned load within a transportation plan

These mirror the SC planning cascade (Demand → Supply → MPS → Execution)
adapted for transportation:
  ShippingForecast → CapacityTarget → TransportationPlan → Execution (TRM)

Plan versions follow the same strict separation as SC Planning:
- 'live': Plan of Record — what the business operates on (agent-generated)
- 'tms_baseline': Current TMS/ERP plan — comparison baseline
- 'decision_action': User overrides from Decision Stream
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Double,
    Boolean,
    ForeignKey,
    DateTime,
    Date,
    JSON,
    Text,
    Index,
    UniqueConstraint,
    Enum as SAEnum,
    text,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum
from .base import Base


# ============================================================================
# Enums + Shipping Forecast
# ============================================================================
#
# §3.79 Step 5 Substep 1b (2026-05-18) — ForecastMethod + ShippingForecast
# moved to Core's azirella_data_model.master.shipping_forecast.
# Re-export shim keeps existing
# `from app.models.tms_planning import ShippingForecast, ForecastMethod`
# callsites unchanged. Same Cat-A pattern §3.6 Phase 1B used for
# forecast_config / hierarchy_resolver / Commodity (Substep 1a).
#
# Table-creation migration stays in TMS's alembic chain for now; DP-Ship's
# eventual migration creates the same table with IF NOT EXISTS guards.

from azirella_data_model.master.shipping_forecast import (  # noqa: F401, E402
    ForecastMethod,
    ShippingForecast,
)


# PlanStatus + PlanItemStatus moved to Core 2026-05-02 per §3.39
# (canonical-state enum vocabulary parallels supply_plan).
# See Autonomy-Core docs/MIGRATION_REGISTER.md §3.39 for the rationale.
from azirella_data_model.transport_plan import PlanItemStatus, PlanStatus  # noqa: F401

from azirella_data_model.optimization.plan_versions import PlanVersion, is_constrained_for_version  # noqa: E402


# Today's system is NOT constrained-planning. Agent-written plans are
# decision records labelled `constrained_live` for UI continuity. Flip
# to True when the Integrated Balancer lands (Phase 3).
PLANNING_IS_CONSTRAINED = False


# Shipping Forecast (Demand Side) — moved to Core in §3.79 Step 5 Substep 1b.
# `ShippingForecast` + `ForecastMethod` are now re-exported from
# azirella_data_model.master.shipping_forecast at the top of this file.


# ============================================================================
# Capacity Target (Supply Side)
# ============================================================================

class CapacityTarget(Base):
    """
    Required carrier capacity by lane/mode/period
    TMS Entity: capacity_target
    Maps to InventoryTarget/SafetyStock in SC context

    Calculated from ShippingForecast + buffer policies.
    Feeds into TransportationPlan carrier assignment.
    """
    __tablename__ = "capacity_target"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    plan_version = Column(String(20), nullable=False, default="live")

    # Dimensions
    lane_id = Column(Integer, ForeignKey("transportation_lane.id"))
    origin_site_id = Column(Integer, ForeignKey("site.id"))
    destination_site_id = Column(Integer, ForeignKey("site.id"))
    mode = Column(String(20))
    carrier_id = Column(Integer, ForeignKey("carrier.id"))

    # Time period
    target_date = Column(Date, nullable=False)
    period_type = Column(String(10), default="WEEK")

    # Capacity requirements
    required_loads = Column(Double, nullable=False, comment="Loads needed for this period")
    committed_loads = Column(Double, default=0, comment="Loads committed by carriers")
    available_loads = Column(Double, default=0, comment="Carrier capacity available")
    gap_loads = Column(Double, default=0, comment="Unmet capacity (required - committed)")

    # Buffer (like safety stock for transport)
    buffer_loads = Column(Double, default=0, comment="Extra capacity buffer above forecast")
    buffer_policy = Column(String(20), comment="FIXED, PCT_FORECAST, CONFORMAL")
    buffer_pct = Column(Double, comment="Buffer as % of forecast")

    # Cost
    target_cost_per_load = Column(Double)
    target_total_cost = Column(Double)
    budget_limit = Column(Double)

    # Conformal bounds on capacity need
    required_loads_p10 = Column(Double)
    required_loads_p90 = Column(Double)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    config = relationship("SupplyChainConfig")
    lane = relationship("TransportationLane")
    origin = relationship("Site", foreign_keys=[origin_site_id])
    destination = relationship("Site", foreign_keys=[destination_site_id])
    carrier = relationship("Carrier")

    __table_args__ = (
        Index('idx_capacity_target_lookup', 'config_id', 'plan_version', 'target_date', 'lane_id'),
        Index('idx_capacity_target_gap', 'tenant_id', 'gap_loads'),
    )


