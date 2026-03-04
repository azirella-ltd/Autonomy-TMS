"""
Data Drift Monitor — DB Models

Long-horizon distributional shift detection for supply chain forecasting models.

DataDriftRecord: one record per (config, product, site, window, drift_type, date).
DataDriftAlert:  aggregated alert when composite drift crosses an action threshold.

The "canary in the coal mine" framing:
- CDC fires reactively when a metric threshold is breached (hourly/daily)
- DataDriftMonitor fires proactively when input/error distributions are SHIFTING
  over weeks, before model performance degrades enough to trigger CDC
"""

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Double, ForeignKey,
    Index, Integer, String, Text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text

from app.db.base import Base


class DataDriftRecord(Base):
    """
    One distributional drift measurement.

    A record is written for each (config_id, product_id, site_id, window_days,
    drift_type) combination every time the weekly scan runs. The full history
    forms a time series of drift scores that the EscalationArbiter can trend.

    drift_type values:
      "demand"         — shift in ordered_quantity distribution (input drift)
      "forecast_error" — shift in (forecast - actual) residual distribution
      "calibration"    — shift in prediction interval width (p90 - p10)

    window_days values: 28 (4w canary), 56 (8w alarm), 84 (12w trend)

    PSI severity bands (industry standard from credit risk monitoring):
      < 0.10  → none   (stable)
      0.10–0.20 → low   (watch)
      0.20–0.25 → medium (investigate)
      > 0.25  → high   (action required)
    """

    __tablename__ = "data_drift_records"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Scope
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=True)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=True)

    # Time window
    analysis_date = Column(Date, nullable=False, server_default=func.current_date())
    baseline_start = Column(Date)           # Start of reference period
    baseline_end = Column(Date)             # End of reference period
    window_start = Column(Date)             # Start of analysis window
    window_end = Column(Date)               # End of analysis window
    window_days = Column(Integer, nullable=False)  # 28 / 56 / 84

    # What was measured
    drift_type = Column(String(30), nullable=False)

    # Statistical test results
    psi_score = Column(Double)              # Population Stability Index (primary)
    ks_statistic = Column(Double)           # KS test D-statistic
    ks_p_value = Column(Double)             # KS test p-value (< 0.05 → significant)
    js_divergence = Column(Double)          # Jensen-Shannon divergence [0, 1]
    mean_shift = Column(Double)             # (window_mean - baseline_mean) / baseline_std
    variance_ratio = Column(Double)         # window_var / baseline_var

    # Composite assessment
    drift_score = Column(Double)            # Weighted composite [0, 1]
    drift_severity = Column(String(20), server_default=text("'none'"))
    drift_detected = Column(Boolean, server_default=text("false"), nullable=False)

    # Distribution snapshots (for rendering sparklines / history)
    baseline_stats = Column(JSONB)          # {n, mean, std, p10, p50, p90, histogram}
    window_stats = Column(JSONB)            # {n, mean, std, p10, p50, p90, histogram}
    metrics = Column(JSONB)                 # Full detail dict for UI

    # Downstream actions
    alert_sent = Column(Boolean, server_default=text("false"), nullable=False)
    escalated = Column(Boolean, server_default=text("false"), nullable=False)
    escalation_log_id = Column(Integer, ForeignKey("powell_escalation_log.id"), nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    config = relationship("SupplyChainConfig")
    product = relationship("Product")
    site = relationship("Site")

    __table_args__ = (
        Index("idx_drift_config_date", "config_id", "analysis_date"),
        Index("idx_drift_product_site", "product_id", "site_id"),
        Index("idx_drift_window", "window_days"),
        Index("idx_drift_severity", "drift_severity"),
        Index("idx_drift_detected", "drift_detected", "analysis_date"),
    )


class DataDriftAlert(Base):
    """
    Aggregated alert record created when drift crosses an action threshold.

    One alert can cover multiple DataDriftRecord IDs (product-site combinations)
    within the same config. Used by the dashboard to show "alerts needing review"
    without flooding the UI with per-product records.
    """

    __tablename__ = "data_drift_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)

    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)
    alert_date = Column(Date, nullable=False, server_default=func.current_date())

    # Summary
    max_drift_score = Column(Double)        # Worst composite score in batch
    max_severity = Column(String(20))       # Worst severity level
    affected_products = Column(Integer)     # Count of distinct products drifting
    affected_sites = Column(Integer)        # Count of distinct sites drifting
    dominant_drift_type = Column(String(30))  # Most common drift_type in batch

    # What triggered
    psi_triggered = Column(Boolean, server_default=text("false"))
    ks_triggered = Column(Boolean, server_default=text("false"))
    calibration_triggered = Column(Boolean, server_default=text("false"))

    # Summary message shown in UI
    summary = Column(Text)

    # Resolution
    acknowledged = Column(Boolean, server_default=text("false"), nullable=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Link to escalation log entry
    escalation_log_id = Column(Integer, ForeignKey("powell_escalation_log.id"), nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    config = relationship("SupplyChainConfig")

    __table_args__ = (
        Index("idx_drift_alert_config", "config_id", "alert_date"),
        Index("idx_drift_alert_unacked", "acknowledged", "alert_date"),
        Index("idx_drift_alert_severity", "max_severity"),
    )
