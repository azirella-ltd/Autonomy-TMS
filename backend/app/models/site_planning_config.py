"""
Site Planning Configuration — ERP-agnostic planning heuristic config per (product, site).

Extension: Stores planning method and lot sizing parameters extracted from ERP systems
(SAP MARC, D365 ReqItemTable, Odoo orderpoint). The digital twin simulation dispatches
to the correct heuristic based on these fields.

AWS SC compliance: This is an extension table, not a modification of any of the 35 core
AWS SC entities. See DIGITAL_TWIN.md §8A.9 for architectural rationale.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Double, ForeignKey, Index, Integer, String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.models.base import Base


# ---------------------------------------------------------------------------
# Enums (Python-side documentation; stored as VARCHAR in DB)
# ---------------------------------------------------------------------------


class PlanningMethod(str, enum.Enum):
    """Universal planning method codes mapped from ERP-specific types.

    SAP DISMM mapping:
      VB → REORDER_POINT, VV → FORECAST_BASED, V1/V2 → MRP_AUTO,
      PD → MRP_DETERMINISTIC, ND → NO_PLANNING
    D365 CoverageCode mapping:
      0 → NO_PLANNING, 1 → PERIOD_BATCHING, 2 → LOT_FOR_LOT,
      3 → MIN_MAX, 4 → DDMRP
    Odoo trigger mapping:
      auto → REORDER_POINT, manual → NO_PLANNING
    """

    REORDER_POINT = "REORDER_POINT"
    FORECAST_BASED = "FORECAST_BASED"
    MRP_AUTO = "MRP_AUTO"
    MRP_DETERMINISTIC = "MRP_DETERMINISTIC"
    LOT_FOR_LOT = "LOT_FOR_LOT"
    PERIOD_BATCHING = "PERIOD_BATCHING"
    MIN_MAX = "MIN_MAX"
    DDMRP = "DDMRP"
    NO_PLANNING = "NO_PLANNING"


class LotSizingRule(str, enum.Enum):
    """Universal lot sizing codes.

    SAP DISLS mapping:
      EX → LOT_FOR_LOT, FX → FIXED, HB → REPLENISH_TO_MAX,
      WB → WEEKLY_BATCH, MB → MONTHLY_BATCH, TB → DAILY_BATCH
    D365: implicit from CoverageCode (Period → WEEKLY_BATCH, MinMax → REPLENISH_TO_MAX).
    Odoo: qty_multiple applied as rounding; default is LOT_FOR_LOT.
    """

    LOT_FOR_LOT = "LOT_FOR_LOT"
    FIXED = "FIXED"
    REPLENISH_TO_MAX = "REPLENISH_TO_MAX"
    WEEKLY_BATCH = "WEEKLY_BATCH"
    MONTHLY_BATCH = "MONTHLY_BATCH"
    DAILY_BATCH = "DAILY_BATCH"
    EOQ = "EOQ"


# ---------------------------------------------------------------------------
# ERP type → PlanningMethod / LotSizingRule mapping helpers
# ---------------------------------------------------------------------------

SAP_DISMM_MAP: dict[str, str] = {
    "VB": PlanningMethod.REORDER_POINT.value,
    "VM": PlanningMethod.REORDER_POINT.value,  # auto-calculated ROP
    "V1": PlanningMethod.MRP_AUTO.value,
    "V2": PlanningMethod.MRP_AUTO.value,
    "VV": PlanningMethod.FORECAST_BASED.value,
    "PD": PlanningMethod.MRP_DETERMINISTIC.value,
    "ND": PlanningMethod.NO_PLANNING.value,
}

SAP_DISLS_MAP: dict[str, str] = {
    "EX": LotSizingRule.LOT_FOR_LOT.value,
    "FX": LotSizingRule.FIXED.value,
    "HB": LotSizingRule.REPLENISH_TO_MAX.value,
    "WB": LotSizingRule.WEEKLY_BATCH.value,
    "MB": LotSizingRule.MONTHLY_BATCH.value,
    "TB": LotSizingRule.DAILY_BATCH.value,
}

D365_COVERAGE_CODE_MAP: dict[int, str] = {
    0: PlanningMethod.NO_PLANNING.value,
    1: PlanningMethod.PERIOD_BATCHING.value,
    2: PlanningMethod.LOT_FOR_LOT.value,
    3: PlanningMethod.MIN_MAX.value,
    4: PlanningMethod.DDMRP.value,
}


# ---------------------------------------------------------------------------
# SQLAlchemy model
# ---------------------------------------------------------------------------


class SitePlanningConfig(Base):
    """ERP-agnostic planning configuration per (product, site).

    The simulation dispatches to the correct heuristic based on
    ``planning_method`` and ``lot_sizing_rule``.  Raw ERP-specific
    fields (SAP VRMOD/VINT, D365 positive/negative days, Odoo DDMRP
    buffers) are stored in the ``erp_params`` JSONB column.
    """

    __tablename__ = "site_planning_config"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Scope keys ---
    config_id = Column(
        Integer,
        ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    site_id = Column(
        Integer,
        ForeignKey("site.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(String(100), nullable=False)

    # --- Universal planning parameters (typed columns) ---
    planning_method = Column(
        String(30), nullable=False, default=PlanningMethod.REORDER_POINT.value,
    )
    lot_sizing_rule = Column(
        String(30), nullable=False, default=LotSizingRule.LOT_FOR_LOT.value,
    )

    # Lot sizing parameters
    fixed_lot_size = Column(Double, nullable=True)
    min_order_quantity = Column(Double, nullable=True)
    max_order_quantity = Column(Double, nullable=True)
    order_multiple = Column(Double, nullable=True)

    # Time fences (days)
    frozen_horizon_days = Column(Integer, nullable=True)
    planning_time_fence_days = Column(Integer, nullable=True)

    # Forecast consumption (SAP-specific but universally useful)
    forecast_consumption_mode = Column(String(10), nullable=True)
    forecast_consumption_fwd_days = Column(Integer, nullable=True)
    forecast_consumption_bwd_days = Column(Integer, nullable=True)

    # Procurement type
    procurement_type = Column(String(20), nullable=True)

    # Strategy / controller
    strategy_group = Column(String(10), nullable=True)
    mrp_controller = Column(String(10), nullable=True)

    # --- ERP-specific extension ---
    erp_source = Column(String(20), nullable=True)
    erp_params = Column(JSONB, nullable=True)

    # --- Audit ---
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- Relationships ---
    config = relationship("SupplyChainConfig")
    site = relationship("Site")

    __table_args__ = (
        Index(
            "ix_spc_config_site_product",
            "config_id", "site_id", "product_id",
            unique=True,
        ),
        Index("ix_spc_tenant", "tenant_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<SitePlanningConfig site={self.site_id} product={self.product_id} "
            f"method={self.planning_method} lot={self.lot_sizing_rule}>"
        )
