"""
Edge Agent Models — PicoClaw Fleet, OpenClaw Gateway, Signal Ingestion, Security

ORM models for managing PicoClaw edge CDC monitors, OpenClaw chat gateway,
signal ingestion pipeline, and security audit state.

Tables:
  - edge_picoclaw_instances: Registered PicoClaw edge agents
  - edge_picoclaw_heartbeats: Heartbeat log for each instance
  - edge_picoclaw_alerts: CDC alerts from PicoClaw fleet
  - edge_service_accounts: JWT service accounts for PicoClaw auth
  - edge_openclaw_config: OpenClaw gateway configuration (singleton per customer)
  - edge_openclaw_channels: Configured messaging channels
  - edge_openclaw_skills: Installed skill toggles
  - edge_openclaw_sessions: Session activity log
  - edge_ingested_signals: Signals captured via OpenClaw channels
  - edge_signal_correlations: Multi-signal correlation groups
  - edge_source_reliability: Per-source reliability tracking
  - edge_security_checklist: Pre-deployment checklist state
  - edge_activity_log: Unified activity/audit log
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, JSON, ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.sql import func

from .base import Base


# ============================================================================
# PicoClaw Fleet
# ============================================================================

class EdgePicoClawInstance(Base):
    """Registered PicoClaw edge agent instance."""
    __tablename__ = "edge_picoclaw_instances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    site_key = Column(String(100), nullable=False, unique=True, index=True)
    site_name = Column(String(200), nullable=True)
    site_type = Column(String(50), nullable=True)  # warehouse, factory, dc, etc.
    region = Column(String(100), nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)

    # Configuration
    mode = Column(String(50), nullable=False, default="deterministic")  # deterministic, hybrid
    heartbeat_interval_min = Column(Integer, nullable=False, default=30)
    digest_interval_min = Column(Integer, nullable=False, default=60)
    alert_channel = Column(String(50), nullable=True)  # telegram, slack, email

    # Status (updated from heartbeats)
    status = Column(String(20), nullable=False, default="STALE")  # OK, WARNING, CRITICAL, STALE
    last_heartbeat = Column(DateTime, nullable=True)
    uptime_pct = Column(Float, nullable=True)
    memory_mb = Column(Float, nullable=True)

    # CDC metrics (latest snapshot from heartbeat)
    inventory_ratio = Column(Float, nullable=True)
    service_level = Column(Float, nullable=True)
    demand_deviation = Column(Float, nullable=True)
    capacity_utilization = Column(Float, nullable=True)
    orders_past_due = Column(Integer, nullable=True)
    forecast_mape = Column(Float, nullable=True)

    # Lifecycle
    is_active = Column(Boolean, nullable=False, default=True)
    registered_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_pico_status", "status"),
        Index("idx_pico_tenant", "tenant_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "site_key": self.site_key,
            "site_name": self.site_name,
            "site_type": self.site_type,
            "region": self.region,
            "mode": self.mode,
            "status": self.status,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "uptime_pct": self.uptime_pct,
            "memory_mb": self.memory_mb,
            "inventory_ratio": self.inventory_ratio,
            "service_level": self.service_level,
            "demand_deviation": self.demand_deviation,
            "capacity_utilization": self.capacity_utilization,
            "orders_past_due": self.orders_past_due,
            "forecast_mape": self.forecast_mape,
            "heartbeat_interval_min": self.heartbeat_interval_min,
            "alert_channel": self.alert_channel,
            "is_active": self.is_active,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
        }


class EdgePicoClawHeartbeat(Base):
    """Heartbeat record from a PicoClaw instance."""
    __tablename__ = "edge_picoclaw_heartbeats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    site_key = Column(String(100), ForeignKey("edge_picoclaw_instances.site_key", ondelete="CASCADE"), nullable=False)

    # System metrics
    memory_mb = Column(Float, nullable=True)
    cpu_pct = Column(Float, nullable=True)
    uptime_seconds = Column(Integer, nullable=True)

    # CDC condition snapshot
    conditions = Column(JSON, nullable=True)  # {metric: {value, threshold, status}}

    received_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_heartbeat_site", "site_key"),
        Index("idx_heartbeat_time", "received_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "site_key": self.site_key,
            "memory_mb": self.memory_mb,
            "cpu_pct": self.cpu_pct,
            "uptime_seconds": self.uptime_seconds,
            "conditions": self.conditions,
            "received_at": self.received_at.isoformat() if self.received_at else None,
        }


class EdgePicoClawAlert(Base):
    """CDC alert raised by a PicoClaw instance."""
    __tablename__ = "edge_picoclaw_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(64), nullable=False, unique=True, index=True)
    site_key = Column(String(100), ForeignKey("edge_picoclaw_instances.site_key", ondelete="CASCADE"), nullable=False)

    severity = Column(String(20), nullable=False)  # WARNING, CRITICAL
    condition = Column(String(100), nullable=False)  # atp_shortfall, inventory_breach, etc.
    metric_value = Column(Float, nullable=True)
    threshold_value = Column(Float, nullable=True)
    message = Column(Text, nullable=True)

    # Resolution
    acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved = Column(Boolean, nullable=False, default=False)
    resolved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_alert_site", "site_key"),
        Index("idx_alert_severity", "severity"),
        Index("idx_alert_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "alert_id": self.alert_id,
            "site_key": self.site_key,
            "severity": self.severity,
            "condition": self.condition,
            "metric_value": self.metric_value,
            "threshold_value": self.threshold_value,
            "message": self.message,
            "acknowledged": self.acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved": self.resolved,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EdgeServiceAccount(Base):
    """JWT service account for PicoClaw authentication."""
    __tablename__ = "edge_service_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    scope = Column(String(20), nullable=False, default="site")  # site, region, global
    site_key = Column(String(100), nullable=True)  # Null for region/global
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)

    # Token info (store hash, not plaintext)
    token_hash = Column(String(256), nullable=True)
    token_masked = Column(String(50), nullable=True)  # "eyJ...****"

    status = Column(String(20), nullable=False, default="active")  # active, revoked
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    revoked_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_sa_scope", "scope"),
        Index("idx_sa_status", "status"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "scope": self.scope,
            "site_key": self.site_key,
            "token_masked": self.token_masked,
            "status": self.status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================================
# OpenClaw Gateway
# ============================================================================

class EdgeOpenClawConfig(Base):
    """OpenClaw gateway configuration (one per group)."""
    __tablename__ = "edge_openclaw_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, unique=True)

    # LLM provider
    provider = Column(String(50), nullable=False, default="vllm")  # vllm, openai, anthropic
    model = Column(String(100), nullable=False, default="qwen3-8b")
    api_base = Column(String(500), nullable=True, default="http://localhost:8001/v1")
    api_key_masked = Column(String(50), nullable=True)
    max_tokens = Column(Integer, nullable=False, default=4096)
    temperature = Column(Float, nullable=False, default=0.1)

    # Gateway settings
    gateway_port = Column(Integer, nullable=False, default=3100)
    gateway_binding = Column(String(100), nullable=False, default="127.0.0.1")
    workspace_path = Column(String(500), nullable=True, default="/opt/openclaw/workspace")

    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "provider": self.provider,
            "model": self.model,
            "api_base": self.api_base,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "gateway_port": self.gateway_port,
            "gateway_binding": self.gateway_binding,
            "workspace_path": self.workspace_path,
        }


class EdgeOpenClawChannel(Base):
    """Configured messaging channel for OpenClaw."""
    __tablename__ = "edge_openclaw_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String(50), nullable=False, unique=True)  # slack, teams, whatsapp, telegram, email
    name = Column(String(100), nullable=False)
    channel_type = Column(String(50), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)

    # Config (stored as JSON to support channel-specific fields)
    config = Column(JSON, nullable=True)  # {bot_token, workspace, webhook_secret, etc.}

    status = Column(String(20), nullable=False, default="disconnected")  # connected, disconnected, error
    configured = Column(Boolean, nullable=False, default=False)
    warning = Column(Text, nullable=True)

    last_tested_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "name": self.name,
            "type": self.channel_type,
            "status": self.status,
            "configured": self.configured,
            "warning": self.warning,
            "last_tested_at": self.last_tested_at.isoformat() if self.last_tested_at else None,
        }


class EdgeOpenClawSkill(Base):
    """Installed skill toggle for OpenClaw."""
    __tablename__ = "edge_openclaw_skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    skill_id = Column(String(50), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)  # planning, execution, governance, etc.
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)

    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "skill_id": self.skill_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "enabled": self.enabled,
        }


class EdgeOpenClawSession(Base):
    """Session activity log entry for OpenClaw."""
    __tablename__ = "edge_openclaw_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    channel = Column(String(50), nullable=False)
    user_identifier = Column(String(200), nullable=True)  # anonymized user ref

    skill_used = Column(String(50), nullable=True)
    query_text = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    signal_captured = Column(Boolean, nullable=False, default=False)
    signal_id = Column(String(64), nullable=True)  # FK to ingested signal if captured

    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_session_channel", "channel"),
        Index("idx_session_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "channel": self.channel,
            "user_identifier": self.user_identifier,
            "skill_used": self.skill_used,
            "query_text": self.query_text[:200] if self.query_text else None,
            "signal_captured": self.signal_captured,
            "signal_id": self.signal_id,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================================
# Signal Ingestion
# ============================================================================

class EdgeIngestedSignal(Base):
    """Signal captured via OpenClaw channel and processed by ingestion pipeline."""
    __tablename__ = "edge_ingested_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(String(64), nullable=False, unique=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)

    # Source
    channel = Column(String(50), nullable=False)  # slack, teams, whatsapp, etc.
    source = Column(String(50), nullable=False)    # sales_input, customer_feedback, etc.
    raw_text = Column(Text, nullable=True)

    # Classification
    signal_type = Column(String(50), nullable=False)  # DEMAND_INCREASE, DISRUPTION, etc.
    direction = Column(String(20), nullable=True)  # up, down, no_change
    product_id = Column(String(100), nullable=True)
    site_id = Column(String(100), nullable=True)

    # Confidence
    base_confidence = Column(Float, nullable=True)
    source_reliability = Column(Float, nullable=True)
    time_decay = Column(Float, nullable=True, default=1.0)
    final_confidence = Column(Float, nullable=True)

    # Processing
    status = Column(String(20), nullable=False, default="pending")  # auto_applied, pending, approved, rejected
    magnitude_hint = Column(Float, nullable=True)
    magnitude_applied = Column(Float, nullable=True)

    # Review
    reviewed_by = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_reason = Column(Text, nullable=True)

    # Link to forecast adjustment
    adjustment_id = Column(Integer, nullable=True)  # FK to powell_forecast_adjustment_decisions

    # Correlation
    correlation_group_id = Column(String(64), nullable=True, index=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_signal_status", "status"),
        Index("idx_signal_source", "source"),
        Index("idx_signal_type", "signal_type"),
        Index("idx_signal_product_site", "product_id", "site_id"),
        Index("idx_signal_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "signal_id": self.signal_id,
            "channel": self.channel,
            "source": self.source,
            "signal_type": self.signal_type,
            "direction": self.direction,
            "product_id": self.product_id,
            "site_id": self.site_id,
            "base_confidence": self.base_confidence,
            "source_reliability": self.source_reliability,
            "time_decay": self.time_decay,
            "final_confidence": self.final_confidence,
            "status": self.status,
            "magnitude_hint": self.magnitude_hint,
            "magnitude_applied": self.magnitude_applied,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "review_reason": self.review_reason,
            "adjustment_id": self.adjustment_id,
            "correlation_group_id": self.correlation_group_id,
            "raw_text": self.raw_text[:500] if self.raw_text else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EdgeSignalCorrelation(Base):
    """Multi-signal correlation group."""
    __tablename__ = "edge_signal_correlations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    correlation_id = Column(String(64), nullable=False, unique=True, index=True)

    product_id = Column(String(100), nullable=True)
    site_id = Column(String(100), nullable=True)
    direction = Column(String(20), nullable=True)

    # Signals in this group
    signal_ids = Column(JSON, nullable=False, default=list)  # [signal_id, ...]
    signal_count = Column(Integer, nullable=False, default=0)

    # Combined confidence: 1 - product(1 - conf_i)
    combined_confidence = Column(Float, nullable=True)

    status = Column(String(20), nullable=False, default="active")  # active, applied, expired
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)  # Correlation window (e.g., +2h)

    __table_args__ = (
        Index("idx_corr_product_site", "product_id", "site_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "correlation_id": self.correlation_id,
            "product_id": self.product_id,
            "site_id": self.site_id,
            "direction": self.direction,
            "signal_ids": self.signal_ids,
            "signal_count": self.signal_count,
            "combined_confidence": self.combined_confidence,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class EdgeSourceReliability(Base):
    """Per-source reliability tracking and weight configuration."""
    __tablename__ = "edge_source_reliability"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False, unique=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)

    default_weight = Column(Float, nullable=False, default=0.5)
    learned_weight = Column(Float, nullable=True)  # Updated from outcome feedback
    manual_weight = Column(Float, nullable=True)    # Admin override

    # Tracking
    signals_count = Column(Integer, nullable=False, default=0)
    signals_correct = Column(Integer, nullable=False, default=0)
    accuracy = Column(Float, nullable=True)  # signals_correct / signals_count

    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    @property
    def effective_weight(self):
        """Manual override > learned > default."""
        if self.manual_weight is not None:
            return self.manual_weight
        if self.learned_weight is not None:
            return self.learned_weight
        return self.default_weight

    def to_dict(self):
        return {
            "source": self.source,
            "default_weight": self.default_weight,
            "learned_weight": self.learned_weight,
            "manual_weight": self.manual_weight,
            "effective_weight": self.effective_weight,
            "signals_count": self.signals_count,
            "signals_correct": self.signals_correct,
            "accuracy": self.accuracy,
        }


# ============================================================================
# Security & Audit
# ============================================================================

class EdgeSecurityChecklist(Base):
    """Pre-deployment security checklist state."""
    __tablename__ = "edge_security_checklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(String(50), nullable=False, unique=True, index=True)
    section = Column(String(100), nullable=False)
    label = Column(Text, nullable=False)
    checked = Column(Boolean, nullable=False, default=False)
    checked_by = Column(String(100), nullable=True)
    checked_at = Column(DateTime, nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)

    def to_dict(self):
        return {
            "id": self.item_id,
            "section": self.section,
            "label": self.label,
            "checked": self.checked,
            "checked_by": self.checked_by,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
        }


class EdgeActivityLog(Base):
    """Unified activity/audit log for all edge agent operations."""
    __tablename__ = "edge_activity_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    component = Column(String(50), nullable=False)  # picoclaw, openclaw, signal, security
    action = Column(String(100), nullable=False)
    details = Column(JSON, nullable=True)
    user_id = Column(Integer, nullable=True)
    site_key = Column(String(100), nullable=True)
    severity = Column(String(20), nullable=False, default="info")  # info, warning, error

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_activity_component", "component"),
        Index("idx_activity_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "component": self.component,
            "action": self.action,
            "details": self.details,
            "severity": self.severity,
            "site_key": self.site_key,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
