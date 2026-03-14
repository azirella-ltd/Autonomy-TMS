"""
Agent Stochastic Parameters

Per-agent stochastic variable values with default tracking.
Each TRM agent type uses a subset of stochastic variables (supplier lead time,
manufacturing yield, etc.). Values can come from three sources:
  - industry_default: Auto-populated based on tenant industry vertical
  - sap_import: Derived from SAP operational statistics extraction
  - manual_edit: Manually set by a user through the UI

The `is_default` flag tracks whether the value is still at its industry default.
When the tenant's industry changes, only rows with is_default=True are updated.
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, JSON, DateTime, ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base


class AgentStochasticParam(Base):
    """Per-agent stochastic variable value with source tracking.

    Each row stores one distribution parameter for one TRM agent type
    within a supply chain config, optionally scoped to a specific site.
    """
    __tablename__ = "agent_stochastic_params"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(
        Integer,
        ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # NULL site_id = config-wide default for this TRM type
    site_id = Column(
        Integer,
        ForeignKey("site.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # TRM agent type: atp_executor, po_creation, mo_execution, etc.
    trm_type = Column(String(50), nullable=False, index=True)
    # Parameter name: supplier_lead_time, manufacturing_yield, etc.
    param_name = Column(String(80), nullable=False)
    # Distribution JSON: {"type": "lognormal", "mean_log": ..., ...}
    distribution = Column(JSON, nullable=False)
    # True = value came from industry defaults and can be auto-updated
    is_default = Column(Boolean, nullable=False, default=True)
    # Source of the value
    source = Column(
        String(20),
        nullable=False,
        default="industry_default",
        comment="industry_default | sap_import | manual_edit",
    )
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    # Relationships
    config = relationship("SupplyChainConfig", foreign_keys=[config_id])
    site = relationship("Site", foreign_keys=[site_id])

    __table_args__ = (
        UniqueConstraint(
            "config_id", "site_id", "trm_type", "param_name",
            name="uq_agent_stochastic_param",
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "trm_type": self.trm_type,
            "param_name": self.param_name,
            "distribution": self.distribution,
            "is_default": self.is_default,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ============================================================================
# TRM Type → Stochastic Parameter Mapping
#
# Defines which stochastic variables each TRM agent type uses.
# This mapping drives:
#   1. Which rows to create per TRM type when applying industry defaults
#   2. Which parameters appear in the UI for each agent type
#   3. Which distribution to sample from during agent execution
# ============================================================================

TRM_PARAM_MAP = {
    "atp_executor": [
        "demand_variability",
    ],
    "inventory_rebalancing": [
        "demand_variability",
        "supplier_lead_time",
        "transport_lead_time",
    ],
    "po_creation": [
        "supplier_lead_time",
        "supplier_on_time",
    ],
    "order_tracking": [
        "supplier_lead_time",
        "transport_lead_time",
    ],
    "mo_execution": [
        "manufacturing_cycle_time",
        "manufacturing_yield",
        "setup_time",
        "mtbf",
        "mttr",
    ],
    "to_execution": [
        "transport_lead_time",
    ],
    "quality_disposition": [
        "quality_rejection_rate",
        "manufacturing_yield",
    ],
    "maintenance_scheduling": [
        "mtbf",
        "mttr",
    ],
    "subcontracting": [
        "manufacturing_cycle_time",
        "supplier_lead_time",
    ],
    "forecast_adjustment": [
        "demand_variability",
    ],
    "inventory_buffer": [
        "demand_variability",
        "supplier_lead_time",
    ],
}

# Reverse map: param_name → industry defaults key for distribution generation
PARAM_TO_INDUSTRY_KEY = {
    "demand_variability": "demand_variability",
    "supplier_lead_time": "supplier_lead_time",
    "supplier_on_time": "supplier_on_time",
    "manufacturing_cycle_time": "manufacturing_cycle_time",
    "manufacturing_yield": "manufacturing_yield",
    "setup_time": "setup_time",
    "mtbf": "mtbf",
    "mttr": "mttr",
    "transport_lead_time": "transport_lead_time",
    "quality_rejection_rate": "quality_rejection_rate",
}

# Human-readable labels for the UI
PARAM_LABELS = {
    "demand_variability": "Demand Variability",
    "supplier_lead_time": "Supplier Lead Time",
    "supplier_on_time": "Supplier On-Time Rate",
    "manufacturing_cycle_time": "Manufacturing Cycle Time",
    "manufacturing_yield": "Manufacturing Yield",
    "setup_time": "Setup / Changeover Time",
    "mtbf": "Mean Time Between Failures",
    "mttr": "Mean Time To Repair",
    "transport_lead_time": "Transportation Lead Time",
    "quality_rejection_rate": "Quality Rejection Rate",
}

TRM_LABELS = {
    "atp_executor": "ATP Executor",
    "inventory_rebalancing": "Inventory Rebalancing",
    "po_creation": "PO Creation",
    "order_tracking": "Order Tracking",
    "mo_execution": "MO Execution",
    "to_execution": "TO Execution",
    "quality_disposition": "Quality Disposition",
    "maintenance_scheduling": "Maintenance Scheduling",
    "subcontracting": "Subcontracting",
    "forecast_adjustment": "Forecast Adjustment",
    "inventory_buffer": "Inventory Buffer",
}
