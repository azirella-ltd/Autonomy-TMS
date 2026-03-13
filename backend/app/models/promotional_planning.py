"""Promotional Planning models — Extension to AWS SC data model.

Manages promotional events and their impact on demand forecasts.
Promotions are a key source of forecast error; explicit modeling
enables better demand sensing and forecast adjustment.

Extension: Not part of AWS SC base model. Integrates with existing AWS SC entities:
- supplementary_time_series (series_type='PROMOTION') for demand driver signals
- forecast (via forecast adjustments with adjustment_type='PROMOTION')
- product (product_id references)
- site (site_id references)

The Promotion model is the planning/management wrapper; actual demand impact
flows through supplementary_time_series and forecast adjustments per AWS SC standard.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Float, Date, DateTime, JSON,
    ForeignKey, Index, Boolean,
)
from sqlalchemy.sql import func

from app.models.base import Base


# ============================================================================
# Promotion Types — aligns with supplementary_time_series series_type='PROMOTION'
# ============================================================================
PROMOTION_TYPES = [
    "price_discount",
    "bogo",
    "bundle",
    "display",
    "seasonal",
    "clearance",
    "loyalty",
    "new_product_launch",
]

PROMOTION_STATUSES = [
    "draft",
    "planned",
    "approved",
    "active",
    "completed",
    "cancelled",
]


class Promotion(Base):
    """Promotional event with demand impact tracking.

    Extension: Wraps AWS SC supplementary_time_series (PROMOTION type) and
    forecast adjustment (PROMOTION type) with planning workflow.

    When a promotion is activated, corresponding supplementary_time_series
    records are created for the affected products/sites/dates. When completed,
    actual uplift is measured against forecast adjustments.
    """
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=True)

    # --- Core fields ---
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    promotion_type = Column(String(50), nullable=False)  # from PROMOTION_TYPES
    status = Column(String(30), nullable=False, default="draft")

    # --- AWS SC time dimension (aligns with supplementary_time_series.order_date) ---
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    # --- AWS SC product/site/channel scope ---
    # product_id references: list of product.id (AWS SC entity)
    product_ids = Column(JSON, nullable=True)  # ["PROD-001", "PROD-002"]
    # site_id references: list of site.id (AWS SC entity); empty = all sites
    site_ids = Column(JSON, nullable=True)  # [1, 2, 3]
    # channel_id: aligns with supplementary_time_series.channel_id
    channel_ids = Column(JSON, nullable=True)  # ["retail", "online", "wholesale"]
    # customer_tpartner_id references: list of trading_partner.id (AWS SC entity)
    customer_tpartner_ids = Column(JSON, nullable=True)

    # --- Demand impact (drives supplementary_time_series.time_series_value) ---
    expected_uplift_pct = Column(Float, nullable=True)
    expected_cannibalization_pct = Column(Float, nullable=True)
    actual_uplift_pct = Column(Float, nullable=True)
    actual_cannibalization_pct = Column(Float, nullable=True)

    # --- Financial (Extension — not in AWS SC base) ---
    budget = Column(Float, nullable=True)
    actual_spend = Column(Float, nullable=True)
    roi = Column(Float, nullable=True)

    # --- AWS SC traceability ---
    # IDs of supplementary_time_series records created for this promotion
    supp_time_series_ids = Column(JSON, nullable=True)
    # IDs of forecast_adjustment records linked to this promotion
    forecast_adjustment_ids = Column(JSON, nullable=True)

    # --- Workflow ---
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    # --- AWS SC standard metadata fields ---
    source = Column(String(100), nullable=True)  # source system
    source_event_id = Column(String(100), nullable=True)
    source_update_dttm = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_promo_tenant", "tenant_id"),
        Index("idx_promo_status", "status"),
        Index("idx_promo_dates", "start_date", "end_date"),
        Index("idx_promo_type", "promotion_type"),
        Index("idx_promo_config", "config_id"),
    )


class PromotionHistory(Base):
    """Audit trail for promotion lifecycle changes."""
    __tablename__ = "promotion_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    promotion_id = Column(Integer, ForeignKey("promotions.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(50), nullable=False)  # created, updated, approved, activated, completed, cancelled
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    changes = Column(JSON, nullable=True)  # diff of what changed
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_promo_hist_promo", "promotion_id"),
        Index("idx_promo_hist_tenant", "tenant_id"),
    )
