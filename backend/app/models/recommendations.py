"""
Recommendations Models
Inventory rebalancing and optimization recommendations

Part of AWS Supply Chain Implementation - Sprint 4
"""

from sqlalchemy import Column, String, Float, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from typing import Optional

from .base import Base


class Recommendation(Base):
    """
    Recommendation Model

    Stores inventory rebalancing recommendations with ML-based scoring

    Recommendation Types:
    - rebalance: Transfer inventory from excess to deficit site
    - expedite: Expedite incoming shipment
    - safety_stock: Adjust safety stock targets

    Scoring Algorithm (0-100 points):
    - Risk resolution: 40 points (resolving stockout risk)
    - Distance: 20 points (shorter transfers preferred)
    - Sustainability: 15 points (lower CO2 emissions)
    - Service level: 15 points (improving service level)
    - Cost: 10 points (lower cost preferred)
    """

    __tablename__ = "recommendations"

    # Primary identification
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recommendation_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Transfer details
    from_site_id: Mapped[Optional[str]] = mapped_column(String(40))
    to_site_id: Mapped[Optional[str]] = mapped_column(String(40))
    product_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)

    # Scoring components (0-100 scale)
    risk_resolution_score: Mapped[Optional[float]] = mapped_column(Float)  # 0-40
    distance_score: Mapped[Optional[float]] = mapped_column(Float)         # 0-20
    sustainability_score: Mapped[Optional[float]] = mapped_column(Float)   # 0-15
    service_level_score: Mapped[Optional[float]] = mapped_column(Float)    # 0-15
    cost_score: Mapped[Optional[float]] = mapped_column(Float)             # 0-10
    total_score: Mapped[Optional[float]] = mapped_column(Float, index=True)  # 0-100

    # Impact estimates (from simulation)
    estimated_cost_impact: Mapped[Optional[float]] = mapped_column(Float)
    estimated_service_level_impact: Mapped[Optional[float]] = mapped_column(Float)
    estimated_co2_impact: Mapped[Optional[float]] = mapped_column(Float)

    # Context fields for scoring
    context_data: Mapped[Optional[dict]] = mapped_column(JSON)  # Stores excess_dos, deficit_risk, etc.

    # Decision tracking (for ML learning loop)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default='pending',
        index=True
    )  # pending, accepted, rejected, modified, executed, rolled_back
    decision_user_id: Mapped[Optional[str]] = mapped_column(String(36))
    decision_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    decision_reason: Mapped[Optional[str]] = mapped_column(String(500))

    # Execution tracking (for rollback support)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    executed_by_id: Mapped[Optional[str]] = mapped_column(String(36))
    execution_snapshot: Mapped[Optional[dict]] = mapped_column(JSON)
    # Stores pre-execution state: {from_site_inventory: X, to_site_inventory: Y, transfer_order_id: Z}

    # Rollback tracking
    is_rolled_back: Mapped[bool] = mapped_column(default=False)
    rolled_back_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    rolled_back_by_id: Mapped[Optional[str]] = mapped_column(String(36))
    rollback_reason: Mapped[Optional[str]] = mapped_column(String(500))
    rollback_transfer_order_id: Mapped[Optional[str]] = mapped_column(String(36))

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(String(36))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=datetime.utcnow)

    # Indexes for performance
    __table_args__ = (
        Index('ix_recommendations_status_score', 'status', 'total_score'),
        Index('ix_recommendations_product_site', 'product_id', 'to_site_id'),
        Index('ix_recommendations_created', 'created_at'),
    )

    def to_dict(self):
        """Convert recommendation to dictionary"""
        return {
            'id': self.id,
            'recommendation_type': self.recommendation_type,
            'from_site_id': self.from_site_id,
            'to_site_id': self.to_site_id,
            'product_id': self.product_id,
            'quantity': self.quantity,
            'risk_resolution_score': self.risk_resolution_score,
            'distance_score': self.distance_score,
            'sustainability_score': self.sustainability_score,
            'service_level_score': self.service_level_score,
            'cost_score': self.cost_score,
            'total_score': self.total_score,
            'estimated_cost_impact': self.estimated_cost_impact,
            'estimated_service_level_impact': self.estimated_service_level_impact,
            'estimated_co2_impact': self.estimated_co2_impact,
            'context_data': self.context_data,
            'status': self.status,
            'decision_user_id': self.decision_user_id,
            'decision_date': self.decision_date.isoformat() if self.decision_date else None,
            'decision_reason': self.decision_reason,
            'executed_at': self.executed_at.isoformat() if self.executed_at else None,
            'executed_by_id': self.executed_by_id,
            'is_rolled_back': self.is_rolled_back,
            'rolled_back_at': self.rolled_back_at.isoformat() if self.rolled_back_at else None,
            'rollback_reason': self.rollback_reason,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by': self.created_by,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class RecommendationDecision(Base):
    """
    Recommendation Decision Log

    Tracks all decisions made on recommendations for ML learning loop
    Used to train models to predict which recommendations users accept
    """

    __tablename__ = "recommendation_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recommendation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Decision details
    decision: Mapped[str] = mapped_column(String(20), nullable=False)  # accepted, rejected, modified
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decision_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    reason: Mapped[Optional[str]] = mapped_column(String(500))

    # Original recommendation snapshot (for ML training)
    recommendation_snapshot: Mapped[Optional[dict]] = mapped_column(JSON)

    # Execution tracking (if accepted)
    executed: Mapped[str] = mapped_column(String(1), default='N')
    execution_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    actual_impact: Mapped[Optional[dict]] = mapped_column(JSON)  # Actual vs estimated impact

    __table_args__ = (
        Index('ix_recommendation_decisions_recommendation', 'recommendation_id'),
        Index('ix_recommendation_decisions_user', 'user_id', 'decision_date'),
    )

    def to_dict(self):
        """Convert decision to dictionary"""
        return {
            'id': self.id,
            'recommendation_id': self.recommendation_id,
            'decision': self.decision,
            'user_id': self.user_id,
            'decision_date': self.decision_date.isoformat() if self.decision_date else None,
            'reason': self.reason,
            'recommendation_snapshot': self.recommendation_snapshot,
            'executed': self.executed,
            'execution_date': self.execution_date.isoformat() if self.execution_date else None,
            'actual_impact': self.actual_impact
        }
