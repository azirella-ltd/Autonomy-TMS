"""
Decision Embeddings — Vector store for past TRM/Skill decisions.

Stores embedded decision state+outcome pairs for RAG retrieval.
When a new decision is needed, similar past decisions are retrieved
as few-shot examples to reduce LLM cost and improve consistency.

Uses the same KBBase (pgvector, 768-dim) as the knowledge base,
sharing the embedding infrastructure.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, JSON, Index,
)
from sqlalchemy.sql import func

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None

from app.models.knowledge_base import KBBase


class DecisionEmbedding(KBBase):
    """Embedded past decision for RAG retrieval.

    Each row captures a single decision (from any of the 11 TRM types)
    along with its outcome and reward signal. The embedding is computed
    from the state description so similar future states retrieve relevant
    past decisions as few-shot context.
    """
    __tablename__ = "decision_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Decision identity
    trm_type = Column(String(50), nullable=False, index=True)
    site_key = Column(String(100), nullable=True, index=True)
    tenant_id = Column(Integer, nullable=True, index=True)

    # State at decision time (JSON for full features, text for embedding source)
    state_features = Column(JSON, nullable=False)
    state_summary = Column(Text, nullable=False)  # Human-readable summary used for embedding

    # Decision made
    decision = Column(JSON, nullable=False)  # The actual decision (action, quantity, etc.)
    decision_source = Column(String(50), nullable=False)  # "engine", "trm", "skill", "human_override"
    confidence = Column(Float, nullable=True)

    # Outcome (filled after feedback horizon)
    outcome = Column(JSON, nullable=True)  # Actual outcome metrics
    outcome_summary = Column(Text, nullable=True)
    reward = Column(Float, nullable=True)  # Normalized reward signal (0-1, higher=better)

    # Vector embedding (768 dimensions, same as knowledge base)
    embedding = Column(Vector(768)) if Vector else Column(JSON)

    # Metadata
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    outcome_recorded_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_de_trm_type", "trm_type"),
        Index("idx_de_site", "site_key"),
        Index("idx_de_tenant", "tenant_id"),
        Index("idx_de_reward", "reward"),
        Index("idx_de_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "trm_type": self.trm_type,
            "site_key": self.site_key,
            "state_summary": self.state_summary,
            "decision": self.decision,
            "decision_source": self.decision_source,
            "confidence": self.confidence,
            "outcome_summary": self.outcome_summary,
            "reward": self.reward,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_rag_example(self) -> dict:
        """Format as a RAG example for skill prompt injection."""
        return {
            "state_summary": self.state_summary,
            "decision": self.decision,
            "outcome_summary": self.outcome_summary,
            "reward": self.reward,
        }
