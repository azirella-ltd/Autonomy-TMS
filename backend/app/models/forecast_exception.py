"""
Forecast Exception Alert Models

Tracks forecast exceptions, variance alerts, and demand anomalies.
Supports:
- Automated exception detection (variance > threshold)
- Manual exception flagging
- Exception workflows (acknowledge, resolve, escalate)
- Root cause analysis tracking
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Double,
    ForeignKey,
    DateTime,
    Date,
    Text,
    Boolean,
    Index,
    JSON,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
from typing import Optional, Dict, Any
from .base import Base


class ForecastException(Base):
    """
    Forecast Exception - Tracks demand variance alerts and anomalies

    Exception types:
    - VARIANCE: Actual vs forecast exceeds threshold
    - TREND_BREAK: Significant change in demand pattern
    - SEASONALITY_MISS: Seasonal pattern not matched
    - OUTLIER: Statistical outlier detected
    - BIAS: Consistent over/under forecasting
    - MANUAL: Manually flagged exception
    """
    __tablename__ = "forecast_exception"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Exception identification
    exception_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # Scope
    config_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"))
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"))
    product_id: Mapped[str] = mapped_column(String(100), ForeignKey("product.id"), nullable=False)
    site_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("site.id"))
    customer_id: Mapped[Optional[str]] = mapped_column(String(100))

    # Time period
    period_start: Mapped[datetime] = mapped_column(Date, nullable=False)
    period_end: Mapped[Optional[datetime]] = mapped_column(Date)
    time_bucket: Mapped[str] = mapped_column(String(20), default="WEEK")  # DAY, WEEK, MONTH

    # Exception type and severity
    exception_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="VARIANCE, TREND_BREAK, SEASONALITY_MISS, OUTLIER, BIAS, MANUAL"
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        default="MEDIUM",
        comment="LOW, MEDIUM, HIGH, CRITICAL"
    )
    priority: Mapped[int] = mapped_column(Integer, default=50)  # 1-100, higher = more urgent

    # Variance details
    forecast_quantity: Mapped[float] = mapped_column(Double, nullable=False)
    actual_quantity: Mapped[Optional[float]] = mapped_column(Double)
    variance_quantity: Mapped[Optional[float]] = mapped_column(Double)
    variance_percent: Mapped[Optional[float]] = mapped_column(Double)
    threshold_percent: Mapped[float] = mapped_column(Double, default=20.0)

    # Direction
    direction: Mapped[Optional[str]] = mapped_column(
        String(10),
        comment="OVER, UNDER"
    )

    # Impact assessment
    revenue_impact: Mapped[Optional[float]] = mapped_column(Double)
    cost_impact: Mapped[Optional[float]] = mapped_column(Double)
    service_level_impact: Mapped[Optional[float]] = mapped_column(Double)

    # Status workflow
    status: Mapped[str] = mapped_column(
        String(30),
        default="NEW",
        nullable=False,
        comment="NEW, ACKNOWLEDGED, INVESTIGATING, RESOLVED, ESCALATED, DISMISSED"
    )

    # Root cause
    root_cause_category: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="PROMOTION, SEASONALITY, MARKET_CHANGE, DATA_ERROR, SUPPLY_ISSUE, EXTERNAL_EVENT, UNKNOWN"
    )
    root_cause_description: Mapped[Optional[str]] = mapped_column(Text)

    # Resolution
    resolution_action: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="ADJUST_FORECAST, ADJUST_SAFETY_STOCK, EXPEDITE_SUPPLY, NO_ACTION, OTHER"
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)
    forecast_adjustment: Mapped[Optional[float]] = mapped_column(Double)  # Adjusted forecast value

    # Detection
    detection_method: Mapped[str] = mapped_column(
        String(30),
        default="AUTOMATED",
        comment="AUTOMATED, MANUAL, AI_AGENT"
    )
    detection_rule_id: Mapped[Optional[str]] = mapped_column(String(100))
    detection_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    # AI analysis
    ai_analysis: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    ai_recommendation: Mapped[Optional[str]] = mapped_column(Text)
    confidence_score: Mapped[Optional[float]] = mapped_column(Double)

    # Assignment
    assigned_to_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    assigned_to_role: Mapped[Optional[str]] = mapped_column(String(50))  # Role-based assignment
    escalated_to_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))

    # Workflow tracking
    workflow_template_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("exception_workflow_template.id", use_alter=True))
    current_escalation_level: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    last_escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sla_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)
    deferred_until: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Notifications
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_count: Mapped[int] = mapped_column(Integer, default=0)
    last_notification_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Audit
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    acknowledged_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    resolved_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_fe_config', 'config_id'),
        Index('idx_fe_tenant', 'tenant_id'),
        Index('idx_fe_product', 'product_id'),
        Index('idx_fe_site', 'site_id'),
        Index('idx_fe_status', 'status'),
        Index('idx_fe_type', 'exception_type'),
        Index('idx_fe_severity', 'severity'),
        Index('idx_fe_period', 'period_start', 'period_end'),
        Index('idx_fe_assigned', 'assigned_to_id'),
        Index('idx_fe_detected', 'detected_at'),
        Index('idx_fe_workflow', 'workflow_template_id'),
        Index('idx_fe_sla', 'sla_deadline'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "exception_number": self.exception_number,
            "config_id": self.config_id,
            "tenant_id": self.tenant_id,
            "product_id": self.product_id,
            "site_id": self.site_id,
            "customer_id": self.customer_id,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "time_bucket": self.time_bucket,
            "exception_type": self.exception_type,
            "severity": self.severity,
            "priority": self.priority,
            "forecast_quantity": self.forecast_quantity,
            "actual_quantity": self.actual_quantity,
            "variance_quantity": self.variance_quantity,
            "variance_percent": self.variance_percent,
            "threshold_percent": self.threshold_percent,
            "direction": self.direction,
            "revenue_impact": self.revenue_impact,
            "cost_impact": self.cost_impact,
            "service_level_impact": self.service_level_impact,
            "status": self.status,
            "root_cause_category": self.root_cause_category,
            "root_cause_description": self.root_cause_description,
            "resolution_action": self.resolution_action,
            "resolution_notes": self.resolution_notes,
            "forecast_adjustment": self.forecast_adjustment,
            "detection_method": self.detection_method,
            "detection_rule_id": self.detection_rule_id,
            "detection_details": self.detection_details,
            "ai_analysis": self.ai_analysis,
            "ai_recommendation": self.ai_recommendation,
            "confidence_score": self.confidence_score,
            "assigned_to_id": self.assigned_to_id,
            "assigned_to_role": self.assigned_to_role,
            "escalated_to_id": self.escalated_to_id,
            "workflow_template_id": self.workflow_template_id,
            "current_escalation_level": self.current_escalation_level,
            "last_escalated_at": self.last_escalated_at.isoformat() if self.last_escalated_at else None,
            "sla_deadline": self.sla_deadline.isoformat() if self.sla_deadline else None,
            "deferred_until": self.deferred_until.isoformat() if self.deferred_until else None,
            "notification_sent": self.notification_sent,
            "notification_count": self.notification_count,
            "last_notification_at": self.last_notification_at.isoformat() if self.last_notification_at else None,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "acknowledged_by_id": self.acknowledged_by_id,
            "resolved_by_id": self.resolved_by_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def calculate_variance(self):
        """Calculate variance from forecast to actual"""
        if self.actual_quantity is not None and self.forecast_quantity:
            self.variance_quantity = self.actual_quantity - self.forecast_quantity
            self.variance_percent = (self.variance_quantity / self.forecast_quantity) * 100 if self.forecast_quantity != 0 else 0
            self.direction = "OVER" if self.variance_quantity > 0 else "UNDER"

    def is_exception(self) -> bool:
        """Check if variance exceeds threshold"""
        if self.variance_percent is None:
            return False
        return abs(self.variance_percent) > self.threshold_percent


class ForecastExceptionRule(Base):
    """
    Exception Detection Rule - Configures automated exception detection
    """
    __tablename__ = "forecast_exception_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    rule_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Scope
    config_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"))
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"))
    product_ids: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)  # List of product IDs or patterns
    site_ids: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)  # List of site IDs

    # Rule type
    rule_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="VARIANCE_THRESHOLD, TREND_DETECTION, OUTLIER_DETECTION, BIAS_DETECTION, CUSTOM"
    )

    # Thresholds
    variance_threshold_percent: Mapped[float] = mapped_column(Double, default=20.0)
    variance_threshold_absolute: Mapped[Optional[float]] = mapped_column(Double)
    consecutive_periods: Mapped[int] = mapped_column(Integer, default=1)  # For trend/bias detection
    min_quantity_threshold: Mapped[Optional[float]] = mapped_column(Double)  # Ignore small volumes

    # Severity mapping
    severity_mapping: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    # e.g., {"0-25": "LOW", "25-50": "MEDIUM", "50-100": "HIGH", "100+": "CRITICAL"}

    # Actions
    auto_assign_to_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    notification_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    # e.g., {"email": true, "slack": true, "in_app": true, "escalation_hours": 24}

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Audit
    created_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_fer_config', 'config_id'),
        Index('idx_fer_tenant', 'tenant_id'),
        Index('idx_fer_type', 'rule_type'),
        Index('idx_fer_active', 'is_active'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "config_id": self.config_id,
            "tenant_id": self.tenant_id,
            "product_ids": self.product_ids,
            "site_ids": self.site_ids,
            "rule_type": self.rule_type,
            "variance_threshold_percent": self.variance_threshold_percent,
            "variance_threshold_absolute": self.variance_threshold_absolute,
            "consecutive_periods": self.consecutive_periods,
            "min_quantity_threshold": self.min_quantity_threshold,
            "severity_mapping": self.severity_mapping,
            "auto_assign_to_id": self.auto_assign_to_id,
            "notification_config": self.notification_config,
            "is_active": self.is_active,
            "created_by_id": self.created_by_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ForecastExceptionComment(Base):
    """
    Comment on a forecast exception for collaboration
    """
    __tablename__ = "forecast_exception_comment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exception_id: Mapped[int] = mapped_column(Integer, ForeignKey("forecast_exception.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_fec_exception', 'exception_id'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "exception_id": self.exception_id,
            "author_id": self.author_id,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ExceptionWorkflowTemplate(Base):
    """
    Exception Workflow Template - Defines automated routing and escalation paths

    Supports:
    - Automatic assignment based on exception type, severity, product category
    - Multi-level escalation with time-based triggers
    - Notification configuration per level
    - Auto-resolution rules for low-priority exceptions
    """
    __tablename__ = "exception_workflow_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Template identification
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Scope
    config_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"))
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"))

    # Matching criteria (when to apply this workflow)
    exception_types: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    # ["VARIANCE", "TREND_BREAK", "OUTLIER"]
    severity_levels: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    # ["HIGH", "CRITICAL"]
    product_categories: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    # Product category filters
    min_impact_value: Mapped[Optional[float]] = mapped_column(Double)
    # Only apply if impact > threshold

    # Initial assignment rules (JSON)
    initial_assignment: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    # {
    #   "type": "user" | "role" | "round_robin",
    #   "user_id": 123,  # if type=user
    #   "role": "demand_planner",  # if type=role
    #   "user_pool": [1, 2, 3],  # if type=round_robin
    #   "fallback_user_id": 1
    # }

    # Escalation levels (JSON array)
    escalation_levels: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    # [
    #   {"level": 1, "hours": 24, "assign_to": {"type": "role", "role": "supervisor"}, "notify": ["email", "slack"]},
    #   {"level": 2, "hours": 48, "assign_to": {"type": "user", "user_id": 1}, "notify": ["email", "sms"]}
    # ]

    # Auto-resolution rules
    auto_resolve_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    # {
    #   "enabled": true,
    #   "conditions": {"severity": ["LOW"], "age_hours": 168},  # Auto-resolve low severity after 7 days
    #   "resolution_action": "NO_ACTION",
    #   "resolution_notes": "Auto-resolved due to inactivity"
    # }

    # Notification defaults
    notification_channels: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    # {"email": true, "slack": true, "in_app": true, "sms": false}

    # SLA configuration
    sla_hours: Mapped[Optional[int]] = mapped_column(Integer)
    # Target resolution time
    sla_warning_hours: Mapped[Optional[int]] = mapped_column(Integer)
    # Warn when approaching SLA

    # Priority
    priority: Mapped[int] = mapped_column(Integer, default=100)  # Lower = higher priority
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    # Audit
    created_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_ewt_config', 'config_id'),
        Index('idx_ewt_tenant', 'tenant_id'),
        Index('idx_ewt_active', 'is_active', 'priority'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "description": self.description,
            "config_id": self.config_id,
            "tenant_id": self.tenant_id,
            "exception_types": self.exception_types,
            "severity_levels": self.severity_levels,
            "product_categories": self.product_categories,
            "min_impact_value": self.min_impact_value,
            "initial_assignment": self.initial_assignment,
            "escalation_levels": self.escalation_levels,
            "auto_resolve_config": self.auto_resolve_config,
            "notification_channels": self.notification_channels,
            "sla_hours": self.sla_hours,
            "sla_warning_hours": self.sla_warning_hours,
            "priority": self.priority,
            "is_active": self.is_active,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ExceptionEscalationLog(Base):
    """
    Tracks escalation events for audit trail
    """
    __tablename__ = "exception_escalation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exception_id: Mapped[int] = mapped_column(Integer, ForeignKey("forecast_exception.id", ondelete="CASCADE"), nullable=False)

    # Escalation details
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False)
    escalated_from_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    escalated_to_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    escalation_reason: Mapped[str] = mapped_column(String(200), nullable=False)
    # "SLA_BREACH", "MANUAL", "SEVERITY_UPGRADE", "NO_RESPONSE"

    # Trigger info
    triggered_by: Mapped[str] = mapped_column(String(50), nullable=False)
    # "SYSTEM", "USER", "WORKFLOW"
    trigger_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    workflow_template_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("exception_workflow_template.id"))

    # Notification tracking
    notifications_sent: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    # {"email": true, "slack": true, "sent_at": "2026-01-29T10:00:00Z"}

    # Timestamps
    escalated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        Index('idx_eel_exception', 'exception_id'),
        Index('idx_eel_escalated_to', 'escalated_to_id'),
        Index('idx_eel_escalated_at', 'escalated_at'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "exception_id": self.exception_id,
            "escalation_level": self.escalation_level,
            "escalated_from_id": self.escalated_from_id,
            "escalated_to_id": self.escalated_to_id,
            "escalation_reason": self.escalation_reason,
            "triggered_by": self.triggered_by,
            "trigger_user_id": self.trigger_user_id,
            "workflow_template_id": self.workflow_template_id,
            "notifications_sent": self.notifications_sent,
            "escalated_at": self.escalated_at.isoformat() if self.escalated_at else None,
        }
