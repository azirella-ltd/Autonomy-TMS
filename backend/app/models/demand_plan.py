"""
Demand Plan Entity (AWS Supply Chain)

Represents the output of demand planning processes, including:
- Statistical forecasts
- Consensus-adjusted forecasts
- Multiple forecast scenarios
- Forecast accuracy metrics
- Demand plan approval workflow

AWS SC Entity: demand_plan
"""

from sqlalchemy import (
    Column, String, Float, Double, ForeignKey, DateTime, Date, JSON, Integer, text
)
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class DemandPlan(Base):
    """
    Demand Plan - Output of demand planning process

    A demand plan represents the agreed-upon forecast for a product at a site
    over a planning horizon. It includes statistical forecasts, manual adjustments,
    consensus decisions, and forecast accuracy metrics.

    AWS SC Entity: demand_plan
    """
    __tablename__ = "demand_plan"

    # Primary Key
    id = Column(String(100), primary_key=True)

    # Core Fields
    company_id = Column(String(100), ForeignKey("company.id"), nullable=False, index=True)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False, index=True)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False, index=True)
    plan_date = Column(Date, nullable=False, index=True)  # Date of the forecast

    # Forecast Values
    statistical_forecast = Column(Double)  # Statistical/ML forecast
    consensus_forecast = Column(Double)   # Final consensus forecast (approved)
    manual_adjustment = Column(Double)    # Manual adjustment amount
    baseline_forecast = Column(Double)    # Baseline before adjustments

    # Forecast Scenarios (P10/P50/P90)
    forecast_p10 = Column(Double)  # 10th percentile (pessimistic)
    forecast_p50 = Column(Double)  # 50th percentile (median)
    forecast_median = Column(Double)  # Explicit median forecast value
    forecast_p90 = Column(Double)  # 90th percentile (optimistic)

    # Units
    uom = Column(String(20))  # Unit of measure (EA, CS, KG, etc.)

    # Plan Metadata
    plan_version = Column(Integer, default=1)  # Version number
    plan_scenario = Column(String(50))  # budget, forecast, best_case, worst_case
    planning_cycle = Column(String(50))  # Monthly, quarterly, annual

    # Status and Approval
    status = Column(String(20), nullable=False, index=True)  # draft, submitted, approved, rejected
    approval_status = Column(String(20))  # pending, approved, rejected
    approved_by = Column(String(100))  # User ID who approved
    approved_at = Column(DateTime)  # Approval timestamp
    rejection_reason = Column(String(500))  # Reason for rejection

    # Accuracy Metrics (updated post-actuals)
    forecast_accuracy = Column(Double)  # % accuracy vs actuals
    forecast_bias = Column(Double)  # Systematic over/under forecast
    mape = Column(Double)  # Mean Absolute Percentage Error
    rmse = Column(Double)  # Root Mean Square Error

    # Confidence and Quality
    forecast_confidence = Column(Double)  # 0-1 confidence score
    data_quality_score = Column(Double)  # 0-100 quality score
    forecast_method = Column(String(50))  # arima, exp_smoothing, ml_model, manual

    # Business Context
    promotion_flag = Column(String(10))  # 'true' if promotion period
    seasonality_flag = Column(String(10))  # 'true' if high seasonality
    new_product_flag = Column(String(10))  # 'true' if new product
    phase_out_flag = Column(String(10))  # 'true' if being phased out

    # Event Impacts
    event_impact = Column(JSON)  # List of events affecting forecast
    # Example: [{"event": "Black Friday", "impact_pct": 0.25}, ...]

    # Demand Drivers
    demand_drivers = Column(JSON)  # Key drivers of demand
    # Example: {"price": -0.15, "promotion": 0.30, "seasonality": 0.20}

    # Notes and Comments
    planner_notes = Column(String(1000))  # Planner comments
    comments = Column(JSON)  # Structured comments array
    # Example: [{"user": "john", "timestamp": "...", "comment": "..."}]

    # Relationships
    product = relationship("Product")
    site = relationship("Site")
    company = relationship("Company")

    # Standard Metadata
    source = Column(String(100))  # Source system
    source_event_id = Column(String(100))  # Source event ID
    source_update_dttm = Column(DateTime)  # Source update timestamp
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))
    created_by = Column(String(100))  # User ID
    updated_by = Column(String(100))  # User ID

    def __repr__(self):
        return (
            f"<DemandPlan(id={self.id}, product={self.product_id}, "
            f"site={self.site_id}, date={self.plan_date}, "
            f"forecast={self.consensus_forecast}, status={self.status})>"
        )


class DemandPlanVersion(Base):
    """
    Demand Plan Version History

    Tracks version history of demand plans for audit trail and
    rollback capabilities.

    Extension to AWS SC demand_plan entity
    """
    __tablename__ = "demand_plan_version"

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Keys
    demand_plan_id = Column(String(100), ForeignKey("demand_plan.id"), nullable=False, index=True)
    company_id = Column(String(100), ForeignKey("company.id"), nullable=False)

    # Version Info
    version_number = Column(Integer, nullable=False)
    version_date = Column(DateTime, nullable=False)
    version_type = Column(String(20))  # baseline, revision, reforecast

    # Snapshot of Values
    statistical_forecast = Column(Double)
    consensus_forecast = Column(Double)
    manual_adjustment = Column(Double)

    # Change Metadata
    changed_by = Column(String(100))  # User who made change
    change_reason = Column(String(500))  # Reason for change
    change_summary = Column(JSON)  # Detailed change log
    # Example: {"field": "consensus_forecast", "old": 100, "new": 120}

    # Relationships
    demand_plan = relationship("DemandPlan")

    # Standard Metadata
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    def __repr__(self):
        return (
            f"<DemandPlanVersion(demand_plan_id={self.demand_plan_id}, "
            f"version={self.version_number}, date={self.version_date})>"
        )


class DemandPlanApproval(Base):
    """
    Demand Plan Approval Workflow

    Tracks approval workflow for demand plans, including
    multi-stage approval processes.

    Extension to AWS SC demand_plan entity
    """
    __tablename__ = "demand_plan_approval"

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Keys
    demand_plan_id = Column(String(100), ForeignKey("demand_plan.id"), nullable=False, index=True)
    company_id = Column(String(100), ForeignKey("company.id"), nullable=False)

    # Approval Stage
    approval_stage = Column(String(50), nullable=False)  # planner, manager, director, executive
    approval_order = Column(Integer)  # 1, 2, 3, ... for multi-stage approval

    # Approver Info
    approver_user_id = Column(String(100), nullable=False)
    approver_role = Column(String(50))  # Role of approver

    # Decision
    decision = Column(String(20), nullable=False)  # approved, rejected, pending
    decision_date = Column(DateTime)
    decision_notes = Column(String(1000))

    # Delegation
    delegated_from = Column(String(100))  # If approval was delegated
    delegation_reason = Column(String(500))

    # Relationships
    demand_plan = relationship("DemandPlan")

    # Standard Metadata
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))

    def __repr__(self):
        return (
            f"<DemandPlanApproval(demand_plan_id={self.demand_plan_id}, "
            f"stage={self.approval_stage}, decision={self.decision})>"
        )


class DemandPlanAccuracy(Base):
    """
    Demand Plan Forecast Accuracy Tracking

    Tracks forecast accuracy metrics by product, site, time horizon,
    and planner for continuous improvement.

    Extension to AWS SC demand_plan entity
    """
    __tablename__ = "demand_plan_accuracy"

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Keys
    demand_plan_id = Column(String(100), ForeignKey("demand_plan.id"), nullable=False, index=True)
    company_id = Column(String(100), ForeignKey("company.id"), nullable=False, index=True)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False, index=True)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False, index=True)

    # Dates
    forecast_date = Column(Date, nullable=False)  # When forecast was made
    actual_date = Column(Date, nullable=False)    # When actual occurred
    time_horizon_days = Column(Integer)  # Days between forecast and actual

    # Values
    forecasted_value = Column(Double, nullable=False)
    actual_value = Column(Double, nullable=False)
    absolute_error = Column(Double)  # |forecast - actual|
    percentage_error = Column(Double)  # (forecast - actual) / actual
    squared_error = Column(Double)  # (forecast - actual)^2

    # Accuracy Metrics
    mape = Column(Double)  # Mean Absolute Percentage Error
    bias = Column(Double)  # Average error (positive = over-forecast)
    forecast_value_add = Column(Double)  # vs naive forecast

    # Context
    forecast_method = Column(String(50))  # Method used
    planner_id = Column(String(100))  # Who made forecast
    had_promotion = Column(String(10))  # Was there a promotion?
    had_event = Column(String(10))  # Was there an event?

    # Relationships
    demand_plan = relationship("DemandPlan")
    product = relationship("Product")
    site = relationship("Site")

    # Standard Metadata
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    calculated_at = Column(DateTime)  # When accuracy was calculated

    def __repr__(self):
        return (
            f"<DemandPlanAccuracy(demand_plan_id={self.demand_plan_id}, "
            f"forecast={self.forecasted_value}, actual={self.actual_value}, "
            f"error_pct={self.percentage_error:.2f}%)>"
        )
