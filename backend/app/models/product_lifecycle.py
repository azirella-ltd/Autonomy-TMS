"""Product Lifecycle Management models — Extension to AWS SC data model.

Manages the full product lifecycle: NPI (New Product Introduction),
active management, EOL (End of Life), and markdown/clearance.

Extension: Not part of AWS SC base model. Integrates with existing AWS SC entities:
- product (product.is_active, product.is_deleted for lifecycle state)
- product_bom (product_bom.lifecycle_phase for BOM lifecycle tracking)
- forecast (adjustment_type='NEW_PRODUCT' for NPI, 'PHASE_OUT' for EOL)
- supplementary_time_series (series_type='PROMOTION' for clearance events)
- inv_policy (safety stock adjustments during NPI ramp-up and EOL drawdown)
- sourcing_rules (supplier qualification status for NPI)
- vendor_product (vendor qualification for NPI)

Lifecycle stage changes update the underlying AWS SC entities:
- launch/growth → product.is_active='true', product.is_deleted='false'
- eol/discontinued → product.is_active='false', product.is_deleted='true'
- NPI supplier qualification → vendor_product records
- EOL last-buy → inbound_order scheduling constraints
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Float, Date, DateTime, JSON,
    ForeignKey, Index, UniqueConstraint, Boolean,
)
from sqlalchemy.sql import func

from app.models.base import Base


# ============================================================================
# Lifecycle Stages — maps to product.is_active + product_bom.lifecycle_phase
# ============================================================================
LIFECYCLE_STAGES = [
    "concept",       # product.is_active='false', product.is_deleted='false'
    "development",   # product.is_active='false', product.is_deleted='false'
    "launch",        # product.is_active='true'  — NPI project triggers this
    "growth",        # product.is_active='true'
    "maturity",      # product.is_active='true'
    "decline",       # product.is_active='true'
    "eol",           # product.is_active='true'  — EOL plan active, still selling
    "discontinued",  # product.is_active='false', product.is_deleted='true'
]

# Maps lifecycle_stage → product_bom.lifecycle_phase (AWS SC field)
STAGE_TO_BOM_PHASE = {
    "concept": "DESIGN",
    "development": "PILOT",
    "launch": "PRODUCTION",
    "growth": "PRODUCTION",
    "maturity": "PRODUCTION",
    "decline": "PRODUCTION",
    "eol": "PHASE_OUT",
    "discontinued": "OBSOLETE",
}


class ProductLifecycle(Base):
    """Lifecycle stage tracking for a product.

    Extension: Links to AWS SC product entity. Stage changes propagate to:
    - product.is_active / product.is_deleted (AWS SC standard)
    - product_bom.lifecycle_phase (AWS SC standard)
    - forecast adjustments (adjustment_type='NEW_PRODUCT' or 'PHASE_OUT')
    """
    __tablename__ = "product_lifecycle"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=True)

    # --- AWS SC product reference ---
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)

    # --- Lifecycle state ---
    lifecycle_stage = Column(String(30), nullable=False, default="concept")
    stage_entered_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # --- AWS SC time dimension ---
    expected_launch_date = Column(Date, nullable=True)
    actual_launch_date = Column(Date, nullable=True)
    expected_eol_date = Column(Date, nullable=True)
    actual_eol_date = Column(Date, nullable=True)

    # --- AWS SC product references for succession ---
    successor_product_id = Column(String(100), nullable=True)  # product.id
    predecessor_product_id = Column(String(100), nullable=True)  # product.id

    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # --- AWS SC standard metadata ---
    source = Column(String(100), nullable=True)
    source_event_id = Column(String(100), nullable=True)
    source_update_dttm = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "product_id", name="uq_lifecycle_tenant_product"),
        Index("idx_lifecycle_tenant", "tenant_id"),
        Index("idx_lifecycle_product", "product_id"),
        Index("idx_lifecycle_stage", "lifecycle_stage"),
        Index("idx_lifecycle_tenant_stage", "tenant_id", "lifecycle_stage"),
    )


class NPIProject(Base):
    """New Product Introduction project.

    Extension: Orchestrates product launch using AWS SC entities:
    - vendor_product (supplier qualification → vendor_product records)
    - sourcing_rules (new sourcing rules for NPI products)
    - forecast (adjustment_type='NEW_PRODUCT' for demand ramp)
    - inv_policy (initial safety stock for new products)
    - product_bom (BOM creation with lifecycle_phase='PILOT'→'PRODUCTION')
    """
    __tablename__ = "npi_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=True)
    lifecycle_id = Column(Integer, ForeignKey("product_lifecycle.id"), nullable=True)

    project_name = Column(String(255), nullable=False)
    project_code = Column(String(50), nullable=True)
    status = Column(String(30), nullable=False, default="planning")
    # planning, qualification, pilot, ramp_up, launched, cancelled

    # --- AWS SC time dimension ---
    target_launch_date = Column(Date, nullable=False)
    actual_launch_date = Column(Date, nullable=True)

    # --- AWS SC product/site scope ---
    product_ids = Column(JSON, nullable=True)  # product.id references
    site_ids = Column(JSON, nullable=True)  # site.id references
    channel_ids = Column(JSON, nullable=True)  # channel references

    # --- Demand planning (feeds forecast adjustment_type='NEW_PRODUCT') ---
    demand_ramp_curve = Column(JSON, nullable=True)
    # Week-by-week demand ramp %: [10, 25, 50, 75, 100]
    initial_forecast_qty = Column(Float, nullable=True)

    # --- Supplier qualification (maps to vendor_product + vendor_lead_time) ---
    # {vendor_tpartner_id: "qualified"|"pending"|"failed"|"not_started"}
    supplier_qualification_status = Column(JSON, nullable=True)

    # --- Quality gates ---
    # [{gate: "prototype", status: "passed", date: "2026-03-01"}, ...]
    quality_gates = Column(JSON, nullable=True)

    # --- Financial ---
    investment = Column(Float, nullable=True)
    expected_revenue_yr1 = Column(Float, nullable=True)
    risk_assessment = Column(Text, nullable=True)

    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)

    # --- AWS SC standard metadata ---
    source = Column(String(100), nullable=True)
    source_event_id = Column(String(100), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_npi_tenant", "tenant_id"),
        Index("idx_npi_status", "status"),
        Index("idx_npi_lifecycle", "lifecycle_id"),
    )


class EOLPlan(Base):
    """End of Life plan for product discontinuation.

    Extension: Orchestrates product phase-out using AWS SC entities:
    - forecast (adjustment_type='PHASE_OUT' for demand phase-out)
    - inv_policy (reduce safety stock targets during EOL)
    - inbound_order (last-buy date constrains PO creation)
    - product (is_active→'false', is_deleted→'true' at discontinuation)
    - product_bom (lifecycle_phase→'PHASE_OUT'→'OBSOLETE')
    """
    __tablename__ = "eol_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=True)
    lifecycle_id = Column(Integer, ForeignKey("product_lifecycle.id"), nullable=True)

    status = Column(String(30), nullable=False, default="planning")
    # planning, approved, in_progress, completed, cancelled

    # --- AWS SC product scope ---
    product_ids = Column(JSON, nullable=True)  # product.id references

    # --- Successor products (AWS SC product references) ---
    successor_product_ids = Column(JSON, nullable=True)

    # --- AWS SC time dimension (constrains inbound_order, supply_plan) ---
    last_buy_date = Column(Date, nullable=True)
    last_manufacture_date = Column(Date, nullable=True)
    last_ship_date = Column(Date, nullable=True)

    # --- Demand phase-out (feeds forecast adjustment_type='PHASE_OUT') ---
    demand_phaseout_curve = Column(JSON, nullable=True)
    # Week-by-week demand % reduction: [90, 75, 50, 25, 10, 0]

    # --- Disposition (Extension — inventory disposition plan) ---
    # [{action: "sell_through"|"transfer"|"scrap"|"donate"|"return_to_vendor",
    #   qty: N, site_id: "...", product_id: "..."}]
    disposition_plan = Column(JSON, nullable=True)

    # --- AWS SC inv_level snapshot ---
    remaining_inventory = Column(JSON, nullable=True)  # {site_id: qty}

    # --- Stakeholder notification ---
    notification_sent_to = Column(JSON, nullable=True)
    # {customers: bool, suppliers: bool, internal: bool}

    # --- Financial ---
    estimated_write_off = Column(Float, nullable=True)
    actual_write_off = Column(Float, nullable=True)

    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)

    # --- AWS SC standard metadata ---
    source = Column(String(100), nullable=True)
    source_event_id = Column(String(100), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_eol_tenant", "tenant_id"),
        Index("idx_eol_status", "status"),
        Index("idx_eol_lifecycle", "lifecycle_id"),
    )


class MarkdownPlan(Base):
    """Markdown/clearance plan for inventory liquidation.

    Extension: Integrates with AWS SC entities:
    - supplementary_time_series (series_type='PROMOTION', clearance events)
    - inv_level (track sell-through against current inventory)
    - product (unit_price for original price reference)
    - customer_cost (markdown pricing impact)
    """
    __tablename__ = "markdown_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=True)
    eol_plan_id = Column(Integer, ForeignKey("eol_plans.id"), nullable=True)

    name = Column(String(255), nullable=False)
    status = Column(String(30), nullable=False, default="draft")
    # draft, approved, active, completed, cancelled

    # --- AWS SC product/site scope ---
    product_ids = Column(JSON, nullable=True)  # product.id references
    site_ids = Column(JSON, nullable=True)  # site.id references
    channel_ids = Column(JSON, nullable=True)

    # --- Markdown schedule ---
    # [{week: 1, discount_pct: 10}, {week: 3, discount_pct: 25}, {week: 5, discount_pct: 50}]
    markdown_schedule = Column(JSON, nullable=True)
    current_discount_pct = Column(Float, default=0)

    # --- AWS SC product.unit_price reference ---
    original_price = Column(Float, nullable=True)  # from product.unit_price
    floor_price = Column(Float, nullable=True)  # minimum (cost or scrap threshold)

    # --- Sell-through tracking (measured against inv_level) ---
    target_sell_through_pct = Column(Float, default=100)
    actual_sell_through_pct = Column(Float, nullable=True)
    revenue_recovered = Column(Float, nullable=True)
    units_sold = Column(Float, nullable=True)
    units_remaining = Column(Float, nullable=True)

    # --- Disposition if unsold ---
    disposition_if_unsold = Column(String(30), default="scrap")
    # scrap, donate, return_to_vendor, hold

    # --- AWS SC time dimension ---
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)

    # --- AWS SC standard metadata ---
    source = Column(String(100), nullable=True)
    source_event_id = Column(String(100), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_markdown_tenant", "tenant_id"),
        Index("idx_markdown_status", "status"),
        Index("idx_markdown_eol", "eol_plan_id"),
    )


class LifecycleHistory(Base):
    """Unified audit trail for all lifecycle entities."""
    __tablename__ = "lifecycle_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(30), nullable=False)  # lifecycle, npi, eol, markdown
    entity_id = Column(Integer, nullable=False)
    action = Column(String(50), nullable=False)
    # created, stage_changed, updated, approved, launched, completed, cancelled
    previous_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_lc_hist_entity", "entity_type", "entity_id"),
        Index("idx_lc_hist_tenant", "tenant_id"),
    )
