"""
Demand Collaboration Entity Model - AWS SC Compliant
AWS Supply Chain Entity: demand_collaboration

Manages collaborative demand planning (CPFR) with trading partners.
Supports consensus forecasting, demand signal sharing, and approval workflows.

IMPORTANT: This implementation follows the AWS Supply Chain Data Model as the foundation.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, text, Double, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime, date
from typing import Optional

from app.models.base import Base


class DemandCollaboration(Base):
    """
    Demand Collaboration - Collaborative forecasting with trading partners

    AWS SC Entity: demand_collaboration

    Supports CPFR (Collaborative Planning, Forecasting, and Replenishment):
    - Shared demand forecasts with suppliers/customers
    - Consensus planning workflows
    - Version control for collaborative forecasts
    - Approval and exception management

    AWS SC Core Fields (REQUIRED):
    - company_id, site_id, product_id, tpartner_id
    - collaboration_date, forecast_quantity
    - collaboration_type (forecast_share, consensus, alert)
    - status (draft, submitted, approved, rejected)
    - source, source_event_id, source_update_dttm

    Extensions:
    - version_number: Track forecast revisions
    - variance_from_baseline: % difference from internal forecast
    - comments: Collaboration notes
    - approval workflow fields
    """
    __tablename__ = "demand_collaboration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # AWS SC Core Fields - Identifiers
    company_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("company.id"))
    site_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("site.id"))
    product_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("product.id"))
    tpartner_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("trading_partners.id"))

    # AWS SC Core Fields - Date and Forecast
    collaboration_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    forecast_quantity: Mapped[float] = mapped_column(Double, nullable=False)  # Collaborative forecast quantity

    # AWS SC Core Fields - Collaboration Type
    collaboration_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="forecast_share, consensus, alert, exception"
    )

    # AWS SC Core Fields - Status and Workflow
    status: Mapped[str] = mapped_column(
        String(50),
        default="draft",
        nullable=False,
        comment="draft, submitted, approved, rejected, revised"
    )

    # Extension: Version Control
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    baseline_forecast_quantity: Mapped[Optional[float]] = mapped_column(Double)  # Original internal forecast
    variance_from_baseline: Mapped[Optional[float]] = mapped_column(Double)  # % difference from baseline

    # Extension: Approval Workflow
    submitted_by: Mapped[Optional[str]] = mapped_column(String(100))
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[Optional[str]] = mapped_column(String(100))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected_by: Mapped[Optional[str]] = mapped_column(String(100))
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(500))

    # Extension: Collaboration Details
    comments: Mapped[Optional[str]] = mapped_column(String(1000))  # Collaboration notes
    exception_flag: Mapped[bool] = mapped_column(Boolean, default=False)  # Flagged for review
    exception_type: Mapped[Optional[str]] = mapped_column(String(100))  # large_variance, stockout_risk, etc.

    # Extension: Forecast Accuracy Tracking
    actual_demand: Mapped[Optional[float]] = mapped_column(Double)  # Actual demand after the fact
    forecast_accuracy_pct: Mapped[Optional[float]] = mapped_column(Double)  # Accuracy percentage

    # AWS SC Core Fields - Source Tracking
    source: Mapped[Optional[str]] = mapped_column(String(100))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(100))
    source_update_dttm: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Extension: Audit Fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    # Relationships
    site = relationship("Site")
    product = relationship("Product")

    def __repr__(self):
        return (
            f"<DemandCollaboration(id={self.id}, product_id='{self.product_id}', "
            f"tpartner_id='{self.tpartner_id}', date={self.collaboration_date}, "
            f"qty={self.forecast_quantity}, status='{self.status}')>"
        )

    def calculate_variance(self) -> Optional[float]:
        """Calculate variance from baseline forecast"""
        if self.baseline_forecast_quantity and self.baseline_forecast_quantity > 0:
            variance = ((self.forecast_quantity - self.baseline_forecast_quantity) /
                       self.baseline_forecast_quantity) * 100
            return round(variance, 2)
        return None

    def calculate_forecast_accuracy(self) -> Optional[float]:
        """Calculate forecast accuracy if actual demand is available"""
        if self.actual_demand is not None and self.forecast_quantity > 0:
            error = abs(self.forecast_quantity - self.actual_demand)
            accuracy = (1 - (error / max(self.forecast_quantity, self.actual_demand))) * 100
            return max(0.0, round(accuracy, 2))
        return None

    def is_exception(self, variance_threshold: float = 20.0) -> bool:
        """Check if this collaboration record is an exception"""
        if self.exception_flag:
            return True

        variance = self.calculate_variance()
        if variance is not None and abs(variance) > variance_threshold:
            return True

        return False


class DemandCollaborationEvent(Base):
    """
    Demand Collaboration Event History

    Tracks all events in the collaboration lifecycle:
    - Submissions
    - Approvals/Rejections
    - Revisions
    - Comments

    Extension to AWS SC demand_collaboration entity
    """
    __tablename__ = "demand_collaboration_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Reference to parent collaboration record
    demand_collaboration_id: Mapped[int] = mapped_column(Integer, ForeignKey("demand_collaboration.id"), nullable=False)

    # Event details
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="created, submitted, approved, rejected, revised, commented"
    )
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    event_by: Mapped[str] = mapped_column(String(100), nullable=False)

    # Event data
    previous_value: Mapped[Optional[str]] = mapped_column(String(500))  # JSON of previous state
    new_value: Mapped[Optional[str]] = mapped_column(String(500))  # JSON of new state
    comment: Mapped[Optional[str]] = mapped_column(String(1000))

    def __repr__(self):
        return (
            f"<DemandCollaborationEvent(id={self.id}, collaboration_id={self.demand_collaboration_id}, "
            f"type='{self.event_type}', by='{self.event_by}')>"
        )
