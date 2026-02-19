"""
Forecast Adjustment Models

Track user adjustments to statistical forecasts with full audit trail.
Supports:
- Individual cell adjustments
- Bulk adjustments (percentage increase/decrease)
- Adjustment reasons and notes
- Version history
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    Text, ForeignKey, Index, JSON
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.models.base import Base


class ForecastAdjustment(Base):
    """
    Individual forecast adjustment record.

    Tracks a single change to a forecast value with reason and audit info.
    """

    __tablename__ = "forecast_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Reference to forecast being adjusted
    forecast_id: Mapped[int] = mapped_column(Integer, ForeignKey("forecast.id"), nullable=False)

    # Adjustment details
    adjustment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # absolute: Set to specific value
    # delta: Add/subtract value
    # percentage: Multiply by percentage

    original_value: Mapped[float] = mapped_column(Float, nullable=False)
    adjustment_value: Mapped[float] = mapped_column(Float, nullable=False)  # The adjustment amount
    new_value: Mapped[float] = mapped_column(Float, nullable=False)  # Final calculated value

    # Time bucket info
    period_start: Mapped[Optional[datetime]] = mapped_column(DateTime)
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime)
    time_bucket: Mapped[Optional[str]] = mapped_column(String(20))  # 2026-W01, 2026-01, etc.

    # Reason and notes
    reason_code: Mapped[Optional[str]] = mapped_column(String(50))
    # promotion, seasonal, event, market_intelligence, correction, other
    reason_text: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Source of adjustment
    source: Mapped[str] = mapped_column(String(50), default='manual')
    # manual, bulk, import, consensus, system

    # Batch tracking (for bulk adjustments)
    batch_id: Mapped[Optional[str]] = mapped_column(String(100))

    # Approval status
    status: Mapped[str] = mapped_column(String(20), default='applied')
    # draft, pending_approval, approved, applied, reverted
    approved_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Audit fields
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])

    __table_args__ = (
        Index('ix_forecast_adj_forecast', 'forecast_id'),
        Index('ix_forecast_adj_batch', 'batch_id'),
        Index('ix_forecast_adj_created', 'created_by_id', 'created_at'),
        Index('ix_forecast_adj_period', 'period_start', 'period_end'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'forecast_id': self.forecast_id,
            'adjustment_type': self.adjustment_type,
            'original_value': self.original_value,
            'adjustment_value': self.adjustment_value,
            'new_value': self.new_value,
            'time_bucket': self.time_bucket,
            'reason_code': self.reason_code,
            'reason_text': self.reason_text,
            'notes': self.notes,
            'source': self.source,
            'batch_id': self.batch_id,
            'status': self.status,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'approved_by_id': self.approved_by_id,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
        }


class ForecastVersion(Base):
    """
    Forecast version/snapshot for tracking complete forecast states.

    Captures a full forecast at a point in time for comparison and rollback.
    """

    __tablename__ = "forecast_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Version identification
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_name: Mapped[Optional[str]] = mapped_column(String(100))
    version_type: Mapped[str] = mapped_column(String(50), default='snapshot')
    # snapshot, baseline, consensus, published

    # Scope
    product_id: Mapped[Optional[str]] = mapped_column(String(100))
    site_id: Mapped[Optional[str]] = mapped_column(String(100))
    config_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"))

    # Planning period
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Snapshot data (JSON blob of all forecast values)
    forecast_data: Mapped[dict] = mapped_column(JSON, default=dict)
    # Structure: {product_id: {site_id: {period: quantity}}}

    # Status
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)

    # Audit
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index('ix_forecast_version_scope', 'config_id', 'product_id', 'site_id'),
        Index('ix_forecast_version_period', 'period_start', 'period_end'),
        Index('ix_forecast_version_current', 'is_current', 'config_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'version_number': self.version_number,
            'version_name': self.version_name,
            'version_type': self.version_type,
            'product_id': self.product_id,
            'site_id': self.site_id,
            'config_id': self.config_id,
            'period_start': self.period_start.isoformat() if self.period_start else None,
            'period_end': self.period_end.isoformat() if self.period_end else None,
            'is_current': self.is_current,
            'is_locked': self.is_locked,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'notes': self.notes,
        }


class BulkAdjustmentTemplate(Base):
    """
    Reusable templates for bulk forecast adjustments.

    Saves common adjustment patterns for easy reuse.
    """

    __tablename__ = "bulk_adjustment_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Adjustment configuration
    adjustment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # percentage, delta, absolute
    default_value: Mapped[Optional[float]] = mapped_column(Float)

    # Default reason
    default_reason_code: Mapped[Optional[str]] = mapped_column(String(50))
    default_reason_text: Mapped[Optional[str]] = mapped_column(Text)

    # Scope filters (JSON)
    scope_filters: Mapped[Optional[dict]] = mapped_column(JSON)
    # {product_ids: [], site_ids: [], categories: []}

    # Period configuration
    default_periods: Mapped[Optional[int]] = mapped_column(Integer)  # Number of periods to apply

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Audit
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_bulk_adj_template_active', 'is_active'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'adjustment_type': self.adjustment_type,
            'default_value': self.default_value,
            'default_reason_code': self.default_reason_code,
            'default_reason_text': self.default_reason_text,
            'scope_filters': self.scope_filters,
            'default_periods': self.default_periods,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
