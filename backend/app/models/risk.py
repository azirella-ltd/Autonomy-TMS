"""
Risk Analysis Models
Database models for risk alerts and watchlists
Sprint 1: Enhanced Insights & Risk Analysis
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime

from .base import Base


class RiskAlert(Base):
    """
    Risk Alert Model
    Stores detected risks (stock-out, overstock, vendor lead time variance)
    """
    __tablename__ = "risk_alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String(255), unique=True, nullable=False, index=True)  # SO-{product}-{site} or OS-{product}-{site}

    # Alert classification
    type = Column(String(50), nullable=False, index=True)  # STOCKOUT, OVERSTOCK, VENDOR_LEADTIME
    severity = Column(String(20), nullable=False, index=True)  # LOW, MEDIUM, HIGH, CRITICAL

    # Entity references
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=True)
    product_id = Column(String(255), nullable=False, index=True)
    site_id = Column(String(255), nullable=False, index=True)
    vendor_id = Column(String(255), nullable=True)  # For vendor lead time alerts

    # Risk metrics
    probability = Column(Float, nullable=True)  # 0-100 for stock-out risk
    days_until_stockout = Column(Integer, nullable=True)  # For stock-out alerts
    days_of_supply = Column(Float, nullable=True)  # For overstock alerts
    excess_quantity = Column(Float, nullable=True)  # For overstock alerts
    cost_impact = Column(Float, nullable=True)  # Estimated cost impact

    # Message and recommendation
    message = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=False)

    # Risk factors (JSON)
    factors = Column(JSON, nullable=True)  # Detailed factors contributing to risk

    # Status tracking
    status = Column(String(20), default="ACTIVE", index=True)  # ACTIVE, ACKNOWLEDGED, RESOLVED, DISMISSED
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    config = relationship("SupplyChainConfig", back_populates="risk_alerts")
    acknowledged_by_user = relationship("User", foreign_keys=[acknowledged_by])

    # Indexes for performance
    __table_args__ = (
        Index('idx_risk_product_site', 'product_id', 'site_id'),
        Index('idx_risk_type_severity', 'type', 'severity'),
        Index('idx_risk_status_created', 'status', 'created_at'),
    )

    def __repr__(self):
        return f"<RiskAlert {self.alert_id} {self.type} {self.severity}>"


class Watchlist(Base):
    """
    Watchlist Model
    User-defined monitoring lists for products/sites with custom thresholds
    """
    __tablename__ = "watchlists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Ownership
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True, index=True)

    # Monitoring configuration
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=True)

    # Filters (JSON)
    product_filter = Column(JSON, nullable=True)  # List of product IDs or patterns
    site_filter = Column(JSON, nullable=True)  # List of site IDs or patterns

    # Alert thresholds (override defaults)
    stockout_threshold = Column(Float, nullable=True)  # Probability threshold (0-100)
    overstock_threshold_days = Column(Float, nullable=True)  # Days of supply threshold
    leadtime_variance_threshold = Column(Float, nullable=True)  # CV% threshold

    # Notification settings
    enable_notifications = Column(Boolean, default=True)
    notification_frequency = Column(String(20), default="DAILY")  # REALTIME, HOURLY, DAILY, WEEKLY
    notification_channels = Column(JSON, nullable=True)  # ["email", "sms", "slack"]
    notification_recipients = Column(JSON, nullable=True)  # List of user IDs

    # Status
    is_active = Column(Boolean, default=True, index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_checked_at = Column(DateTime, nullable=True)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by], back_populates="watchlists")
    group = relationship("Group", back_populates="watchlists")
    config = relationship("SupplyChainConfig")

    def __repr__(self):
        return f"<Watchlist {self.name} by User {self.created_by}>"


class RiskPrediction(Base):
    """
    Risk Prediction Model
    Historical predictions for ML model tracking and validation
    """
    __tablename__ = "risk_predictions"

    id = Column(Integer, primary_key=True, index=True)

    # Prediction metadata
    model_name = Column(String(100), nullable=False)  # trm_agent, gnn_agent, statistical
    model_version = Column(String(50), nullable=False)
    prediction_date = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Entity references
    product_id = Column(String(255), nullable=False, index=True)
    site_id = Column(String(255), nullable=False, index=True)

    # Prediction type
    prediction_type = Column(String(50), nullable=False)  # DEMAND, STOCKOUT, OVERSTOCK, LEADTIME

    # Forecast horizon
    horizon_days = Column(Integer, nullable=False)  # Number of days ahead
    target_date = Column(DateTime, nullable=False, index=True)  # Date of predicted event

    # Predicted values
    predicted_value = Column(Float, nullable=False)  # Predicted demand, probability, etc.
    confidence = Column(Float, nullable=True)  # Model confidence (0-100)
    prediction_interval_lower = Column(Float, nullable=True)  # P10
    prediction_interval_upper = Column(Float, nullable=True)  # P90

    # Actual outcome (for validation)
    actual_value = Column(Float, nullable=True)
    actual_recorded_at = Column(DateTime, nullable=True)
    prediction_error = Column(Float, nullable=True)  # actual - predicted

    # Model features (JSON)
    features = Column(JSON, nullable=True)  # Feature values used for prediction

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_pred_product_site_date', 'product_id', 'site_id', 'target_date'),
        Index('idx_pred_model_type', 'model_name', 'prediction_type'),
    )

    def __repr__(self):
        return f"<RiskPrediction {self.prediction_type} {self.product_id} @ {self.target_date}>"
