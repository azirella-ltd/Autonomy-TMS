"""Email Signal models — GDPR-safe email ingestion for supply chain intelligence.

Stores scrubbed email content (no PII) with domain→TradingPartner resolution.
Signals are classified by LLM and routed to appropriate TRMs for action.

GDPR compliance:
- NO sender name, sender email, or personal identifiers stored
- Only sender domain and resolved company (TradingPartner) are persisted
- Original email is never stored; only PII-scrubbed text
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, JSON,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.sql import func

from app.models.base import Base


class EmailConnection(Base):
    """Configuration for an email inbox to monitor for SC signals."""
    __tablename__ = "email_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)  # "Customer Inbox", "Procurement"
    connection_type = Column(String(20), nullable=False)  # "gmail", "imap"

    # IMAP config (encrypted at rest via application layer)
    imap_host = Column(String(255), nullable=True)
    imap_port = Column(Integer, nullable=True)
    imap_username = Column(String(255), nullable=True)
    imap_password_encrypted = Column(Text, nullable=True)
    imap_folder = Column(String(100), default="INBOX")
    imap_use_ssl = Column(Boolean, default=True)

    # Gmail config
    gmail_label_filter = Column(String(255), nullable=True)  # e.g., "supply-chain"

    # Domain allowlist/blocklist for filtering
    domain_allowlist = Column(JSON, nullable=True)  # Only process from these domains
    domain_blocklist = Column(JSON, nullable=True)  # Never process from these domains

    # Polling state
    poll_interval_minutes = Column(Integer, default=5)
    last_poll_at = Column(DateTime, nullable=True)
    last_poll_uid = Column(String(255), nullable=True)  # High-water mark for dedup

    # Auto-routing config
    auto_route_enabled = Column(Boolean, default=True)
    min_confidence_to_route = Column(Float, default=0.6)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_email_conn_tenant", "tenant_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "connection_type": self.connection_type,
            "imap_host": self.imap_host,
            "imap_port": self.imap_port,
            "imap_username": self.imap_username,
            "imap_folder": self.imap_folder,
            "imap_use_ssl": self.imap_use_ssl,
            "gmail_label_filter": self.gmail_label_filter,
            "domain_allowlist": self.domain_allowlist,
            "domain_blocklist": self.domain_blocklist,
            "poll_interval_minutes": self.poll_interval_minutes,
            "last_poll_at": self.last_poll_at.isoformat() if self.last_poll_at else None,
            "auto_route_enabled": self.auto_route_enabled,
            "min_confidence_to_route": self.min_confidence_to_route,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── Signal types for classification ─────────────────────────────────────────

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

# Signal type → primary TRM routing
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


class EmailSignal(Base):
    """A GDPR-safe supply chain signal extracted from an email.

    The original email is never stored. Only PII-scrubbed text and
    the resolved company (via domain→TradingPartner) are persisted.
    """
    __tablename__ = "email_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    connection_id = Column(Integer, ForeignKey("email_connections.id"), nullable=True)

    # Email metadata (GDPR-safe: NO sender name, NO sender email stored)
    email_uid = Column(String(255), nullable=False)  # Message-ID for dedup
    received_at = Column(DateTime, nullable=False)
    ingested_at = Column(DateTime, server_default=func.now(), nullable=False)
    subject_scrubbed = Column(Text, nullable=True)  # Subject with PII removed
    body_scrubbed = Column(Text, nullable=False)  # Body with PII removed

    # Sender resolution (GDPR-compliant: company only, not person)
    sender_domain = Column(String(255), nullable=False)  # e.g., "acme-corp.com"
    resolved_partner_id = Column(String(100), nullable=True)  # trading_partners.id
    partner_type = Column(String(50), nullable=True)  # "customer" or "supplier"/"vendor"
    partner_name = Column(String(255), nullable=True)  # Resolved company name

    # Signal classification (LLM output)
    signal_type = Column(String(50), nullable=False)  # See SIGNAL_TYPES
    signal_direction = Column(String(20), nullable=True)  # up, down, no_change
    signal_magnitude_pct = Column(Float, nullable=True)
    signal_confidence = Column(Float, nullable=False)
    signal_urgency = Column(Float, nullable=False, default=0.5)  # 0-1
    signal_summary = Column(Text, nullable=False)  # LLM 1-2 sentence summary

    # Scope resolution (matched against tenant's products/sites)
    resolved_product_ids = Column(JSON, nullable=True)  # ["CFG22_RD005", ...]
    resolved_site_ids = Column(JSON, nullable=True)  # ["FOODDIST_DC", ...]
    time_horizon_weeks = Column(Integer, nullable=True)

    # Routing
    target_trm_types = Column(JSON, nullable=True)  # ["forecast_adjustment", "po_creation"]
    routed_decision_ids = Column(JSON, nullable=True)  # IDs of powell_*_decisions created

    # Processing lifecycle
    status = Column(String(20), nullable=False, server_default="INGESTED")
    # INGESTED → CLASSIFIED → ROUTED → ACTED → DISMISSED
    classified_at = Column(DateTime, nullable=True)
    routed_at = Column(DateTime, nullable=True)
    acted_at = Column(DateTime, nullable=True)
    dismissed_by = Column(Integer, nullable=True)  # user_id who dismissed
    dismiss_reason = Column(String(255), nullable=True)

    __table_args__ = (
        Index("idx_email_signal_tenant_status", "tenant_id", "status"),
        Index("idx_email_signal_config", "config_id"),
        Index("idx_email_signal_partner", "resolved_partner_id"),
        Index("idx_email_signal_type", "signal_type"),
        Index("idx_email_signal_received", "received_at"),
        UniqueConstraint("tenant_id", "email_uid", name="uq_email_signal_uid"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "config_id": self.config_id,
            "connection_id": self.connection_id,
            "email_uid": self.email_uid,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "ingested_at": self.ingested_at.isoformat() if self.ingested_at else None,
            "subject_scrubbed": self.subject_scrubbed,
            "body_scrubbed": self.body_scrubbed,
            "sender_domain": self.sender_domain,
            "resolved_partner_id": self.resolved_partner_id,
            "partner_type": self.partner_type,
            "partner_name": self.partner_name,
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
            "classified_at": self.classified_at.isoformat() if self.classified_at else None,
            "routed_at": self.routed_at.isoformat() if self.routed_at else None,
            "acted_at": self.acted_at.isoformat() if self.acted_at else None,
            "dismissed_by": self.dismissed_by,
            "dismiss_reason": self.dismiss_reason,
        }
