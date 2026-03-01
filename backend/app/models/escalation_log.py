"""
Escalation Arbiter audit log for vertical escalation between decision tiers.

Records when the Escalation Arbiter detects persistent anomalies at the
execution tier (TRMs) and routes to operational (tGNN) or strategic
(GraphSAGE/S&OP) replanning.

Maps to:
- Kahneman: System 1 (TRM) persistent failure → System 2 (tGNN/GraphSAGE) activation
- Boyd OODA: Inner loop anomaly → outer loop iteration triggered
- Powell: Belief state Bₜ drift → reframe at higher modeling tier

See docs/ESCALATION_ARCHITECTURE.md for theoretical foundation.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, Text,
    ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSON
from sqlalchemy.sql import func

from app.models.base import Base


class PowellEscalationLog(Base):
    """
    Audit trail for vertical escalation decisions.

    Each row represents a single escalation event where the Arbiter
    diagnosed persistent anomalies and routed to a higher decision tier.
    """
    __tablename__ = "powell_escalation_log"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    site_key = Column(String(100), nullable=False)

    # Escalation verdict
    escalation_level = Column(
        String(20), nullable=False,
    )  # "horizontal", "operational", "strategic"
    diagnosis = Column(Text, nullable=False)
    urgency = Column(String(20), nullable=False)  # "low", "medium", "high", "critical"
    recommended_action = Column(
        String(50), nullable=False,
    )  # "trm_retrain", "tgnn_refresh", "sop_review"

    # Affected scope
    affected_trm_types = Column(ARRAY(String), nullable=True)
    affected_sites = Column(ARRAY(String), nullable=True)

    # Persistence evidence (JSON blob with PersistenceSignal + CrossSitePattern data)
    evidence = Column(JSON, nullable=True)

    # Resolution tracking
    resolved = Column(Boolean, default=False, nullable=False)
    resolution = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_escalation_log_tenant", "tenant_id"),
        Index("idx_escalation_log_site", "site_key"),
        Index("idx_escalation_log_level", "escalation_level"),
        Index("idx_escalation_log_created", "created_at"),
        Index("idx_escalation_log_unresolved", "resolved", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "site_key": self.site_key,
            "escalation_level": self.escalation_level,
            "diagnosis": self.diagnosis,
            "urgency": self.urgency,
            "recommended_action": self.recommended_action,
            "affected_trm_types": self.affected_trm_types,
            "affected_sites": self.affected_sites,
            "evidence": self.evidence,
            "resolved": self.resolved,
            "resolution": self.resolution,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
