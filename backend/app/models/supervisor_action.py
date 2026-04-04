"""Supervisor action model for tracking AI supervisor decisions.

Terminology (Feb 2026):
- Game -> Scenario
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base


class SupervisorAction(Base):
    """Tracks all actions taken by the supervisor agent in a simulation."""
    __tablename__ = "supervisor_actions"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    role = Column(String(20), nullable=False)  # retailer, wholesaler, etc.
    original_order = Column(Integer, nullable=False)
    adjusted_order = Column(Integer, nullable=False)
    reason = Column(String(100), nullable=False)  # bullwhip_mitigation, etc.
    bullwhip_metric = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    scenario = relationship("Scenario", back_populates="supervisor_actions")

    def __repr__(self):
        return f"<SupervisorAction(scenario_id={self.scenario_id}, role={self.role}, original={self.original_order}, adjusted={self.adjusted_order})>"
