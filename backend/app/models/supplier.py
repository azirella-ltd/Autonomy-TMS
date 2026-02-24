"""
Supplier Entity Models - SC Compliant

Supply Chain Entity #17: Supplier (Trading Partner)
Based on SC entities: trading_partner, vendor_product, vendor_lead_time

IMPORTANT: This implementation follows the Supply Chain Data Model as the foundation.
Extensions for simulation and platform-specific features are clearly marked.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Index, UniqueConstraint, text, Double
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional, List
from enum import Enum

from app.models.base import Base

# Import TradingPartner from sc_entities (avoid circular import)
if False:  # TYPE_CHECKING only
    from app.models.sc_entities import TradingPartner


# ============================================================================
# SC Core Entity: TradingPartner (type='vendor')
# ============================================================================


# ============================================================================
# SC Core Entity: VendorProduct
# ============================================================================

class VendorProduct(Base):
    """
    Vendor-Product Association with Supplier-Specific Costs

    SC Entity: vendor_product

    Links suppliers (trading_partner with type='vendor') to products with vendor-specific pricing.
    Supports multi-sourcing with priority rankings.

    SC Core Fields (REQUIRED):
    - company_id, tpartner_id, product_id
    - vendor_product_id, vendor_unit_cost, currency
    - eff_start_date, eff_end_date, is_active
    - source, source_event_id, source_update_dttm

    Extensions:
    - priority: Multi-sourcing priority (1=primary, 2=secondary, etc.)
    - is_primary: Primary supplier flag
    - min/max order quantities
    - order_multiple: Must order in multiples of this quantity
    """
    __tablename__ = "vendor_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # SC Core Fields
    company_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("company.id"))
    # References TradingPartner's business key 'id' (which is unique)
    tpartner_id: Mapped[str] = mapped_column(String(100), ForeignKey("trading_partners.id", name="fk_vendor_products_trading_partner"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(100), ForeignKey("product.id"), nullable=False)  # SC Product table
    vendor_product_id: Mapped[Optional[str]] = mapped_column(String(100))  # Supplier's item code
    vendor_unit_cost: Mapped[float] = mapped_column(Double, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    eff_start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    eff_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[str] = mapped_column(String(10), default="true", nullable=False)  # 'true' or 'false'
    source: Mapped[Optional[str]] = mapped_column(String(100))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(100))
    source_update_dttm: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Extension: Multi-sourcing Support
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1 = primary, 2 = secondary, etc.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Extension: Quantity Constraints
    minimum_order_quantity: Mapped[Optional[float]] = mapped_column(Double)
    maximum_order_quantity: Mapped[Optional[float]] = mapped_column(Double)
    order_multiple: Mapped[Optional[float]] = mapped_column(Double)  # Must order in multiples of this

    # Extension: Supplier-specific item naming
    vendor_item_name: Mapped[Optional[str]] = mapped_column(String(255))

    # Extension: Audit Fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    trading_partner = relationship("TradingPartner", back_populates="vendor_products")
    product = relationship("Product")  # Using Item model for Beer Game

    # Constraints
    __table_args__ = (
        UniqueConstraint('tpartner_id', 'product_id', 'eff_start_date', name='uq_vendor_product_effective'),
        Index('ix_vendor_products_tpartner_id', 'tpartner_id'),
        Index('ix_vendor_products_product_id', 'product_id'),
        Index('ix_vendor_products_priority', 'priority'),
        Index('ix_vendor_products_is_primary', 'is_primary'),
        Index('ix_vendor_products_effective_dates', 'eff_start_date', 'eff_end_date'),
    )

    def __repr__(self):
        return f"<VendorProduct(id={self.id}, tpartner_id='{self.tpartner_id}', product_id={self.product_id}, priority={self.priority})>"

    def is_effective(self, as_of_date: Optional[datetime] = None) -> bool:
        """Check if vendor-product relationship is effective on a given date"""
        check_date = as_of_date or datetime.utcnow()

        if self.is_active != "true":
            return False

        if check_date < self.eff_start_date:
            return False

        if self.eff_end_date and check_date > self.eff_end_date:
            return False

        return True


# ============================================================================
# SC Core Entity: VendorLeadTime
# ============================================================================

class VendorLeadTime(Base):
    """
    Vendor Lead Times with Hierarchical Override Logic

    SC Entity: vendor_lead_time

    Supports hierarchical lead time definitions with override priority:
    product_id > product_group_id > site_id > region_id > company_id

    SC Core Fields (REQUIRED):
    - company_id, region_id, site_id, product_group_id, product_id
    - tpartner_id, lead_time_days
    - eff_start_date, eff_end_date
    - source, source_event_id, source_update_dttm

    Extensions:
    - lead_time_variability_days: Standard deviation for stochastic modeling
    """
    __tablename__ = "vendor_lead_times"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # SC Core Fields - Hierarchy Levels (most specific wins)
    company_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("company.id"))
    region_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("geography.id"))
    site_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("site.id"))  # Using nodes for Beer Game
    product_group_id: Mapped[Optional[str]] = mapped_column(String(100))  # Future: link to product_hierarchy
    product_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("product.id"))  # SC Product table

    # SC Core Fields - Lead Time
    tpartner_id: Mapped[str] = mapped_column(String(100), ForeignKey("trading_partners.id"), nullable=False)
    lead_time_days: Mapped[float] = mapped_column(Double, nullable=False)

    # SC Core Fields - Effective Dates
    eff_start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    eff_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # SC Core Fields - Source Tracking
    source: Mapped[Optional[str]] = mapped_column(String(100))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(100))
    source_update_dttm: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Extension: Lead Time Variability (for stochastic planning)
    lead_time_variability_days: Mapped[Optional[float]] = mapped_column(Double)  # Standard deviation

    # Extension: Audit Fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    trading_partner = relationship("TradingPartner", back_populates="vendor_lead_times")
    product = relationship("Product")  # Using Item model for Beer Game
    site = relationship("Site")  # Using Node model for Beer Game

    # Indexes
    __table_args__ = (
        Index('ix_vendor_lead_times_tpartner_id', 'tpartner_id'),
        Index('ix_vendor_lead_times_product_id', 'product_id'),
        Index('ix_vendor_lead_times_site_id', 'site_id'),
        Index('ix_vendor_lead_times_effective_dates', 'eff_start_date', 'eff_end_date'),
    )

    def __repr__(self):
        return f"<VendorLeadTime(id={self.id}, tpartner_id='{self.tpartner_id}', lead_time_days={self.lead_time_days})>"

    def is_effective(self, as_of_date: Optional[datetime] = None) -> bool:
        """Check if lead time is effective on a given date"""
        check_date = as_of_date or datetime.utcnow()

        if check_date < self.eff_start_date:
            return False

        if self.eff_end_date and check_date > self.eff_end_date:
            return False

        return True


# ============================================================================
# Extension: SupplierPerformance (Not in SC - Platform Extension)
# ============================================================================

class SupplierPerformance(Base):
    """
    Supplier Performance Tracking Over Time

    Extension: Not a core SC entity - platform-specific extension for performance analytics.

    Periodic snapshots of supplier performance metrics.
    Used to track trends and inform sourcing decisions.
    """
    __tablename__ = "supplier_performance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to TradingPartner
    tpartner_id: Mapped[str] = mapped_column(String(100), ForeignKey("trading_partners.id"), nullable=False)

    # Performance period
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_type: Mapped[str] = mapped_column(String(20), default="MONTHLY", nullable=False)  # WEEKLY, MONTHLY, QUARTERLY, YEARLY

    # Delivery metrics
    orders_placed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_delivered_on_time: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_delivered_late: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_days_late: Mapped[Optional[float]] = mapped_column(Double)

    # Quality metrics
    units_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    units_accepted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    units_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reject_rate_percent: Mapped[Optional[float]] = mapped_column(Double)

    # Lead time metrics
    average_lead_time_days: Mapped[Optional[float]] = mapped_column(Double)
    std_dev_lead_time_days: Mapped[Optional[float]] = mapped_column(Double)

    # Cost metrics
    total_spend: Mapped[float] = mapped_column(Double, default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)

    # Calculated metrics
    on_time_delivery_rate: Mapped[Optional[float]] = mapped_column(Double)  # Percentage (0-100)
    quality_rating: Mapped[Optional[float]] = mapped_column(Double)  # Score (0-100)
    overall_performance_score: Mapped[Optional[float]] = mapped_column(Double)  # Score (0-100)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    supplier = relationship("TradingPartner", back_populates="performance_records")

    # Indexes
    __table_args__ = (
        Index('ix_supplier_performance_tpartner_id', 'tpartner_id'),
        Index('ix_supplier_performance_period', 'period_start', 'period_end'),
        Index('ix_supplier_performance_period_type', 'period_type'),
    )

    def __repr__(self):
        return f"<SupplierPerformance(id={self.id}, tpartner_id='{self.tpartner_id}', period={self.period_start} to {self.period_end})>"

    def calculate_metrics(self) -> None:
        """Calculate derived performance metrics"""
        # On-time delivery rate
        if self.orders_placed > 0:
            self.on_time_delivery_rate = (self.orders_delivered_on_time / self.orders_placed) * 100
        else:
            self.on_time_delivery_rate = None

        # Quality rating (acceptance rate)
        if self.units_received > 0:
            acceptance_rate = (self.units_accepted / self.units_received) * 100
            self.quality_rating = acceptance_rate
            self.reject_rate_percent = 100 - acceptance_rate
        else:
            self.quality_rating = None
            self.reject_rate_percent = None

        # Overall performance score (weighted average)
        if self.on_time_delivery_rate is not None and self.quality_rating is not None:
            # 50% delivery, 50% quality
            self.overall_performance_score = (self.on_time_delivery_rate * 0.5) + (self.quality_rating * 0.5)
        else:
            self.overall_performance_score = None
