"""
Full-Level Pegging Data Model

Implements Kinaxis-style supply-demand pegging with multi-stage chain tracking.
Every unit of supply is traceable to demand (customer order or forecast),
from vendor through factories and DCs to customer.

Tables:
- supply_demand_pegging: Core pegging link (demand ↔ supply with quantity)
- aatp_consumption_record: Persisted AATP consumption decisions
"""

from datetime import datetime, date
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, Integer, String, Double, Boolean, ForeignKey,
    DateTime, Date, Text, Index, Enum,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from .base import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DemandType(str, PyEnum):
    """Type of demand being pegged"""
    CUSTOMER_ORDER = "customer_order"
    FORECAST = "forecast"
    INTER_SITE_ORDER = "inter_site_order"
    SAFETY_STOCK = "safety_stock"


class SupplyType(str, PyEnum):
    """Type of supply being pegged"""
    ON_HAND = "on_hand"
    PURCHASE_ORDER = "purchase_order"
    TRANSFER_ORDER = "transfer_order"
    MANUFACTURING_ORDER = "manufacturing_order"
    PLANNED_ORDER = "planned_order"
    IN_TRANSIT = "in_transit"


class PeggingStatus(str, PyEnum):
    """Firmness of pegging link"""
    FIRM = "firm"
    PLANNED = "planned"
    TENTATIVE = "tentative"


# ---------------------------------------------------------------------------
# Supply-Demand Pegging
# ---------------------------------------------------------------------------

class SupplyDemandPegging(Base):
    """
    Core pegging link table.

    Each row links one supply record to one demand record with a pegged quantity.
    Supports multi-stage chains via upstream_pegging_id and chain_id.

    Example chain (customer order at DC sourcing from factory):
      depth=0: demand=customer_order/ORD-001, supply=on_hand/DC-001, qty=80
      depth=1: demand=inter_site_order/TO-001, supply=manufacturing_order/MO-001, qty=80
      depth=2: demand=inter_site_order/PO-001, supply=purchase_order/PO-V001, qty=160 (BOM 2:1)
    """
    __tablename__ = "supply_demand_pegging"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Ownership
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)

    # Product & site where pegging occurs
    product_id = Column(String(100), nullable=False)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)

    # --- Demand side ---
    demand_type = Column(
        Enum(DemandType, name="demand_type_enum", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    demand_id = Column(String(100), nullable=False)        # Polymorphic FK
    demand_line_id = Column(Integer, nullable=True)         # Line number within order
    demand_priority = Column(Integer, nullable=False, default=5)  # 1=critical, 5=standard
    demand_quantity = Column(Double, nullable=False)         # Total demand qty

    # --- Supply side ---
    supply_type = Column(
        Enum(SupplyType, name="supply_type_enum", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    supply_id = Column(String(100), nullable=False)         # Polymorphic FK
    supply_site_id = Column(Integer, ForeignKey("site.id"), nullable=True)  # Where supply originates

    # --- Pegging ---
    pegged_quantity = Column(Double, nullable=False)
    pegging_date = Column(Date, nullable=False, default=date.today)
    pegging_status = Column(
        Enum(PeggingStatus, name="pegging_status_enum", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=PeggingStatus.PLANNED.value,
    )

    # --- Chain tracking ---
    upstream_pegging_id = Column(Integer, ForeignKey("supply_demand_pegging.id"), nullable=True)
    chain_id = Column(String(64), nullable=False, index=True)  # UUID grouping end-to-end chain
    chain_depth = Column(Integer, nullable=False, default=0)   # 0=terminal demand, 1+

    # --- Audit ---
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by = Column(String(50), nullable=True)           # Service name that created it
    superseded_by = Column(Integer, ForeignKey("supply_demand_pegging.id"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    # Relationships
    site = relationship("Site", foreign_keys=[site_id])
    supply_site = relationship("Site", foreign_keys=[supply_site_id])
    upstream_pegging = relationship(
        "SupplyDemandPegging",
        remote_side=[id],
        foreign_keys=[upstream_pegging_id],
    )

    __table_args__ = (
        Index("ix_pegging_chain", "chain_id"),
        Index("ix_pegging_demand", "demand_type", "demand_id"),
        Index("ix_pegging_supply", "supply_type", "supply_id"),
        Index("ix_pegging_product_site", "product_id", "site_id"),
        Index("ix_pegging_config_active", "config_id", "is_active"),
        Index("ix_pegging_tenant", "tenant_id"),
    )

    def __repr__(self):
        return (
            f"<Pegging {self.id} chain={self.chain_id[:8]}.. "
            f"d={self.demand_type}/{self.demand_id} "
            f"s={self.supply_type}/{self.supply_id} "
            f"qty={self.pegged_quantity}>"
        )


# ---------------------------------------------------------------------------
# AATP Consumption Record
# ---------------------------------------------------------------------------

class AATPConsumptionRecord(Base):
    """
    Persists AATP consumption decisions.

    Previously, AATP consumption was tracked only in-memory in AATPEngine.
    This table provides a durable audit trail and links to pegging.
    """
    __tablename__ = "aatp_consumption_record"

    id = Column(Integer, primary_key=True, autoincrement=True)

    order_id = Column(String(100), nullable=False, index=True)
    product_id = Column(String(100), nullable=False)
    location_id = Column(String(100), nullable=False)   # Site key
    customer_id = Column(String(100), nullable=True)

    requested_qty = Column(Double, nullable=False)
    fulfilled_qty = Column(Double, nullable=False)
    priority = Column(Integer, nullable=False)           # 1-5

    # Breakdown of which priority tiers were consumed
    consumption_detail = Column(JSON, nullable=True)     # [{priority: int, qty: float}]

    # Link to pegging
    pegging_id = Column(Integer, ForeignKey("supply_demand_pegging.id"), nullable=True)

    # Context
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)

    consumed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    pegging = relationship("SupplyDemandPegging")

    __table_args__ = (
        Index("ix_aatp_order", "order_id"),
        Index("ix_aatp_product_location", "product_id", "location_id"),
        Index("ix_aatp_consumed_at", "consumed_at"),
    )

    def __repr__(self):
        return (
            f"<AATPConsumption order={self.order_id} "
            f"filled={self.fulfilled_qty}/{self.requested_qty}>"
        )
