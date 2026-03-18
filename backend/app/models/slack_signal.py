"""Slack Signal models — Supply chain signal intelligence from Slack channels.

Follows the same pattern as email_signal.py for ingesting supply chain signals,
but from Slack channels instead of email inboxes. Signals are classified by LLM
and routed to appropriate TRMs for action.

Two integration modes:
- Webhook: Slack sends messages to our endpoint (real-time)
- Bot: We poll Slack channels via Bot Token (polling-based)
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, JSON,
    ForeignKey, Index,
)
from sqlalchemy.sql import func

from app.models.base import Base


# ── Signal types (shared with email signals) ─────────────────────────────────

SIGNAL_TYPES = [
    "demand_increase",
    "demand_decrease",
    "supply_disruption",
    "lead_time_change",
    "price_change",
    "quality_issue",
    "new_product",
    "discontinuation",
    "order_exception",
    "capacity_change",
    "regulatory",
    "general_inquiry",
]

# Signal type -> primary TRM routing (same mapping as email signals)
SIGNAL_TRM_ROUTING = {
    "demand_increase": ["forecast_adjustment", "inventory_buffer"],
    "demand_decrease": ["forecast_adjustment", "inventory_buffer"],
    "supply_disruption": ["po_creation", "to_execution"],
    "lead_time_change": ["po_creation", "inventory_buffer"],
    "price_change": ["po_creation"],
    "quality_issue": ["quality_disposition", "mo_execution"],
    "new_product": ["forecast_adjustment", "inventory_buffer"],
    "discontinuation": ["forecast_adjustment", "inventory_buffer"],
    "order_exception": ["order_tracking", "atp_executor"],
    "capacity_change": ["mo_execution", "maintenance_scheduling"],
    "regulatory": [],  # Escalate to human
    "general_inquiry": [],  # Informational only
}


class SlackConnection(Base):
    """Configuration for a Slack workspace integration for SC signal monitoring.

    Supports two modes:
    - webhook: Incoming webhook URL for receiving messages pushed from Slack
    - bot: Slack Bot Token for actively polling channel history
    """
    __tablename__ = "slack_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)  # "Supply Chain Alerts", "Procurement Channel"

    connection_type = Column(String(20), nullable=False)  # "webhook" or "bot"

    # Webhook config (Slack sends messages to us)
    webhook_url = Column(Text, nullable=True)

    # Bot config (we read channels via Slack API)
    bot_token_encrypted = Column(Text, nullable=True)  # xoxb-... encrypted at rest
    channel_ids = Column(JSON, nullable=True)  # ["C01ABC123", "C02DEF456"]
    channel_names = Column(JSON, nullable=True)  # ["#supply-alerts", "#procurement"]

    # Signal filtering
    allowed_signal_types = Column(JSON, nullable=True)  # Only process these types

    # Polling state (for bot mode)
    poll_interval_minutes = Column(Integer, default=5)
    last_poll_at = Column(DateTime, nullable=True)
    last_message_ts = Column(String(50), nullable=True)  # Slack message timestamp for dedup

    # Auto-routing config
    auto_route_enabled = Column(Boolean, default=True)
    min_confidence_to_route = Column(Float, default=0.6)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_slack_conn_tenant", "tenant_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "connection_type": self.connection_type,
            "webhook_url": self.webhook_url,
            "channel_ids": self.channel_ids,
            "channel_names": self.channel_names,
            "allowed_signal_types": self.allowed_signal_types,
            "poll_interval_minutes": self.poll_interval_minutes,
            "last_poll_at": self.last_poll_at.isoformat() if self.last_poll_at else None,
            "last_message_ts": self.last_message_ts,
            "auto_route_enabled": self.auto_route_enabled,
            "min_confidence_to_route": self.min_confidence_to_route,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SlackSignal(Base):
    """A supply chain signal extracted from a Slack message.

    Messages are classified by LLM and routed to appropriate TRMs.
    Only display name (not email/PII) is stored for the sender.
    """
    __tablename__ = "slack_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=True)
    connection_id = Column(Integer, ForeignKey("slack_connections.id"), nullable=False)

    # Slack message metadata
    channel_id = Column(String(50), nullable=False)
    channel_name = Column(String(255), nullable=True)
    message_ts = Column(String(50), nullable=False)  # Slack message timestamp (unique per channel)
    sender_name = Column(String(255), nullable=True)  # Display name only (no email/PII)
    message_text = Column(Text, nullable=False)  # The message content
    thread_ts = Column(String(50), nullable=True)  # Parent thread timestamp if this is a reply

    # Signal classification (LLM output)
    signal_type = Column(String(50), nullable=True)  # See SIGNAL_TYPES
    signal_direction = Column(String(20), nullable=True)  # up, down, no_change
    signal_magnitude_pct = Column(Float, nullable=True)
    signal_confidence = Column(Float, nullable=True)
    signal_urgency = Column(String(20), nullable=True)  # low, medium, high, critical
    signal_summary = Column(Text, nullable=True)  # LLM 1-2 sentence summary

    # Scope resolution (matched against tenant's products/sites)
    resolved_product_ids = Column(JSON, nullable=True)
    resolved_site_ids = Column(JSON, nullable=True)
    time_horizon_weeks = Column(Integer, nullable=True)

    # Routing
    target_trm_types = Column(JSON, nullable=True)  # ["forecast_adjustment", "po_creation"]
    routed_decision_ids = Column(JSON, nullable=True)  # IDs of powell_*_decisions created

    # Processing lifecycle: INGESTED -> CLASSIFIED -> ROUTED -> ACTED -> DISMISSED
    status = Column(String(20), nullable=False, server_default="INGESTED")
    received_at = Column(DateTime, nullable=False)
    classified_at = Column(DateTime, nullable=True)
    routed_at = Column(DateTime, nullable=True)
    acted_at = Column(DateTime, nullable=True)
    dismissed_by = Column(Integer, nullable=True)  # user_id who dismissed
    dismiss_reason = Column(String(255), nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_slack_signal_tenant", "tenant_id"),
        Index("idx_slack_signal_status", "tenant_id", "status"),
        Index("idx_slack_signal_type", "signal_type"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "config_id": self.config_id,
            "connection_id": self.connection_id,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "message_ts": self.message_ts,
            "sender_name": self.sender_name,
            "message_text": self.message_text,
            "thread_ts": self.thread_ts,
            "signal_type": self.signal_type,
            "signal_direction": self.signal_direction,
            "signal_magnitude_pct": self.signal_magnitude_pct,
            "signal_confidence": self.signal_confidence,
            "signal_urgency": self.signal_urgency,
            "signal_summary": self.signal_summary,
            "resolved_product_ids": self.resolved_product_ids,
            "resolved_site_ids": self.resolved_site_ids,
            "time_horizon_weeks": self.time_horizon_weeks,
            "target_trm_types": self.target_trm_types,
            "routed_decision_ids": self.routed_decision_ids,
            "status": self.status,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "classified_at": self.classified_at.isoformat() if self.classified_at else None,
            "routed_at": self.routed_at.isoformat() if self.routed_at else None,
            "acted_at": self.acted_at.isoformat() if self.acted_at else None,
            "dismissed_by": self.dismissed_by,
            "dismiss_reason": self.dismiss_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
