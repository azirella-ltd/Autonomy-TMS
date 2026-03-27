"""
Supply Chain Data Model Extension Tables

Extension: Tables for SAP-specific data structures that enrich the core
AWS SC data model entities without modifying them. These support the 15
unprocessed SAP tables (VBEP, MARM, CRHD, MBEW, KAKO, VBUK, VBUP,
CDHDR, CDPOS) and provide detailed scheduling, UoM conversions, work
center definitions, material valuation, capacity resources, and status
tracking for outbound orders.

AWS SC compliance: These are extension tables. The core 35 AWS SC
entities in sc_entities.py remain unchanged. Field names follow SAP
conventions where appropriate with mapping documented inline.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, JSON,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func, text
from typing import Optional

from app.models.base import Base


# ============================================================================
# Outbound Order Schedule (SAP VBEP — SO Schedule Lines)
# ============================================================================

class OutboundOrderLineSchedule(Base):
    """
    Split delivery schedules for outbound (sales) order lines.

    Extension: Maps SAP VBEP schedule lines to outbound_order_line.
    Enables partial delivery tracking per SO line item.

    SAP mapping: VBELN→order_id, POSNR→line_number, ETENR→schedule_number,
    EDATU→requested_date, WMENG→ordered_qty, BMENG→confirmed_qty
    """
    __tablename__ = "outbound_order_line_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Parent references
    order_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("outbound_order.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Schedule details
    schedule_number: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ordered_qty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confirmed_qty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    shipped_qty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uom: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Tenant scoping and provenance
    config_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=True
    )
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index('idx_obl_sched_order_line', 'order_id', 'line_number'),
        Index('idx_obl_sched_date', 'requested_date'),
        Index('idx_obl_sched_config', 'config_id'),
    )


# ============================================================================
# Product UoM Conversion (SAP MARM — Alternate Units of Measure)
# ============================================================================

class ProductUomConversion(Base):
    """
    Alternate unit-of-measure conversions per product.

    Extension: Maps SAP MARM rows. Enables unit conversion between
    base UoM and alternate UoMs (e.g., EA→CS, EA→PAL).

    SAP mapping: MATNR→product_id, MEINH→alternate_uom,
    UMREZ→numerator, UMREN→denominator, BRGEW→gross_weight, VOLUM→volume
    """
    __tablename__ = "product_uom_conversion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    product_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    alternate_uom: Mapped[str] = mapped_column(String(20), nullable=False)

    # Conversion factors: qty_in_alternate = qty_in_base × numerator / denominator
    numerator: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    denominator: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Physical attributes in alternate UoM
    gross_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Tenant scoping and provenance
    config_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=True
    )
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    product = relationship("Product", foreign_keys=[product_id])

    __table_args__ = (
        UniqueConstraint('product_id', 'alternate_uom', 'config_id', name='uq_product_uom_config'),
        Index('idx_product_uom_product', 'product_id'),
        Index('idx_product_uom_config', 'config_id'),
    )


# ============================================================================
# Work Center Master (SAP CRHD — Work Center Definitions)
# ============================================================================

class WorkCenterMaster(Base):
    """
    Work center definitions for manufacturing sites.

    Extension: Maps SAP CRHD. Provides the master record for work centers
    referenced by process_operation.work_center_id and capacity resources.

    SAP mapping: OBJID→work_center_code, ARBPL→name, WERKS→site_id,
    VERWE→usage_category, OBJTY→object_type
    """
    __tablename__ = "work_center_master"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    work_center_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    site_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("site.id", ondelete="CASCADE"), nullable=True
    )
    usage_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    object_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Tenant scoping and provenance
    config_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=True
    )
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    site = relationship("Site", foreign_keys=[site_id])

    __table_args__ = (
        UniqueConstraint('work_center_code', 'config_id', name='uq_wc_code_config'),
        Index('idx_wc_site', 'site_id'),
        Index('idx_wc_config', 'config_id'),
    )


# ============================================================================
# Material Valuation (SAP MBEW — Cost Methods and GL)
# ============================================================================

class MaterialValuation(Base):
    """
    Material valuation records — cost method, standard/moving-avg prices.

    Extension: Maps SAP MBEW. Provides costing data per product-site for
    financial integration and cost-based planning decisions.

    SAP mapping: MATNR→product_id, BWKEY→site_id, BKLAS→valuation_class,
    VPRSV→price_control, STPRS→standard_price, VERPR→moving_avg_price,
    PEINH→price_unit, LBKUM→cumulative_quantity, SALK3→total_value
    """
    __tablename__ = "material_valuation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    product_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    site_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("site.id", ondelete="CASCADE"), nullable=True
    )

    # Valuation parameters
    valuation_class: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    price_control: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, comment="S=standard, V=moving_avg"
    )

    # Prices
    standard_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    moving_avg_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_unit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Inventory value
    cumulative_quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Tenant scoping and provenance
    config_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=True
    )
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    product = relationship("Product", foreign_keys=[product_id])
    site = relationship("Site", foreign_keys=[site_id])

    __table_args__ = (
        UniqueConstraint('product_id', 'site_id', 'config_id', name='uq_mat_val_product_site_config'),
        Index('idx_mat_val_product', 'product_id'),
        Index('idx_mat_val_site', 'site_id'),
        Index('idx_mat_val_config', 'config_id'),
    )


# ============================================================================
# Capacity Resource Detail (SAP KAKO — Capacity Headers)
# ============================================================================

class CapacityResourceDetail(Base):
    """
    Detailed capacity resource definitions from SAP capacity planning.

    Extension: Maps SAP KAKO. Note the existing capacity_resources table
    (CapacityResource in capacity_plan.py) is plan-scoped; this table stores
    master-level capacity definitions independent of any specific plan.

    SAP mapping: KAPID→capacity_id, site_id from work center plant,
    60+ optional SAP fields stored in sap_params JSON column.
    """
    __tablename__ = "capacity_resource_detail"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    capacity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    site_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("site.id", ondelete="CASCADE"), nullable=True
    )
    work_center_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("work_center_master.id", ondelete="SET NULL"), nullable=True
    )

    # Capacity parameters
    max_parallel_ops: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    standard_parallel_ops: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    base_net_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uom: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    planner_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Extensible SAP fields (60+ optional columns)
    sap_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Tenant scoping and provenance
    config_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=True
    )
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    site = relationship("Site", foreign_keys=[site_id])
    work_center = relationship("WorkCenterMaster", foreign_keys=[work_center_id])

    __table_args__ = (
        UniqueConstraint('capacity_id', 'config_id', name='uq_cap_res_detail_config'),
        Index('idx_cap_res_detail_site', 'site_id'),
        Index('idx_cap_res_detail_wc', 'work_center_id'),
        Index('idx_cap_res_detail_config', 'config_id'),
    )


# ============================================================================
# Outbound Order Status (SAP VBUK — SO Header Status)
# ============================================================================

class OutboundOrderStatus(Base):
    """
    Multi-dimensional status tracking for outbound (sales) orders.

    Extension: Maps SAP VBUK. Provides granular status beyond the single
    status column on outbound_order (delivery, billing, invoice, etc.).

    SAP mapping: VBELN→order_id, LFSTK→delivery_status,
    FKSTK→billing_status, FKSAK→invoice_status, WBSTK→goods_issue_status,
    ABSTK→rejection_status, RTSTK→return_status
    """
    __tablename__ = "outbound_order_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    order_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("outbound_order.id", ondelete="CASCADE"),
        nullable=False, unique=True
    )

    # Multi-dimensional status fields
    delivery_status: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    billing_status: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    invoice_status: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    goods_issue_status: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    rejection_status: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    return_status: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Tenant scoping and provenance
    config_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=True
    )
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    order = relationship("OutboundOrder", foreign_keys=[order_id])

    __table_args__ = (
        Index('idx_ob_status_config', 'config_id'),
    )


# ============================================================================
# Outbound Order Line Status (SAP VBUP — SO Item Status)
# ============================================================================

class OutboundOrderLineStatus(Base):
    """
    Line-level multi-dimensional status for outbound order items.

    Extension: Maps SAP VBUP. Per-line granular status tracking.

    SAP mapping: VBELN→order_id, POSNR→line_number,
    LFSTA→delivery_status, FKSTA→billing_status, etc.
    """
    __tablename__ = "outbound_order_line_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    order_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("outbound_order.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Multi-dimensional status fields
    delivery_status: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    billing_status: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    invoice_status: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    goods_issue_status: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    rejection_status: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    return_status: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Tenant scoping and provenance
    config_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=True
    )
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint('order_id', 'line_number', name='uq_obl_status_order_line'),
        Index('idx_obl_status_order', 'order_id'),
        Index('idx_obl_status_config', 'config_id'),
    )


# ============================================================================
# SAP Change Log Header (SAP CDHDR — Change Document Headers)
# ============================================================================

class SAPChangeLog(Base):
    """
    Change document headers for audit trail and CDC.

    Extension: Maps SAP CDHDR. Provides audit trail of master data
    and transactional changes for compliance and CDC processing.

    SAP mapping: CHANGENR→change_number, OBJECTCLAS→object_class,
    OBJECTID→object_id, USERNAME→changed_by, UDATE+UTIME→changed_at
    """
    __tablename__ = "sap_change_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    change_number: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    object_class: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    object_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    changed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Tenant scoping and provenance
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    details = relationship(
        "SAPChangeLogDetail", back_populates="change_log", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index('idx_sap_clog_object', 'object_class', 'object_id'),
        Index('idx_sap_clog_changed_at', 'changed_at'),
        Index('idx_sap_clog_tenant', 'tenant_id'),
    )


# ============================================================================
# SAP Change Log Detail (SAP CDPOS — Change Document Items)
# ============================================================================

class SAPChangeLogDetail(Base):
    """
    Change document line items — individual field changes.

    Extension: Maps SAP CDPOS. Each row records a single field-level
    change within a change document.

    SAP mapping: CHANGENR→change_log_id (via FK), TABNAME→table_name,
    FNAME→field_name, VALUE_OLD→old_value, VALUE_NEW→new_value
    """
    __tablename__ = "sap_change_log_detail"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    change_log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sap_change_log.id", ondelete="CASCADE"), nullable=False
    )

    table_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    field_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    change_log = relationship("SAPChangeLog", back_populates="details")

    __table_args__ = (
        Index('idx_sap_clog_detail_parent', 'change_log_id'),
        Index('idx_sap_clog_detail_table', 'table_name', 'field_name'),
    )
