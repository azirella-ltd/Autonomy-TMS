"""
Planning Scenario — Scenario tree for hive-aware what-if evaluation.

Provides copy-on-write branching with balanced-scorecard evaluation,
promotion/pruning lifecycle, and decision audit trail.

Builds on top of ScenarioBranchingService (which handles supply chain
config deltas) by adding planning-specific metadata: status workflow,
balanced scorecard, net benefit, and hive health snapshots.

Architecture reference: TRM_HIVE_ARCHITECTURE.md Section 11-12
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime,
    ForeignKey, Enum as SAEnum, JSON,
)
from sqlalchemy.orm import relationship

from app.models.base import Base


class ScenarioStatus(str, enum.Enum):
    """Planning scenario lifecycle status."""
    DRAFT = "DRAFT"               # Created, not yet evaluated
    EVALUATING = "EVALUATING"     # What-if engine running
    EVALUATED = "EVALUATED"       # Scorecard available
    SHARED = "SHARED"             # Shared for review
    APPROVED = "APPROVED"         # Approved by reviewer
    PROMOTED = "PROMOTED"         # Promoted as winning scenario
    PRUNED = "PRUNED"             # Pruned (sibling of promoted)
    REJECTED = "REJECTED"         # Explicitly rejected


class PlanningScenario(Base):
    """A planning scenario node in a scenario tree.

    Each scenario represents a set of variable overrides (deltas) applied
    on top of a parent scenario's effective configuration.  The root
    scenario (parent_scenario_id=NULL) represents the baseline.

    After evaluation via HiveWhatIfEngine, the balanced_scorecard and
    net_benefit are populated.  Promotion prunes sibling branches.
    """
    __tablename__ = "planning_scenario"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Tree structure
    parent_scenario_id = Column(Integer, ForeignKey("planning_scenario.id"), nullable=True)
    root_scenario_id = Column(Integer, ForeignKey("planning_scenario.id"), nullable=True)
    depth = Column(Integer, nullable=False, default=0)

    # Link to supply chain config (for ScenarioBranchingService integration)
    config_id = Column(Integer, nullable=True)

    # Variable overrides applied on top of parent
    variable_deltas = Column(JSON, nullable=True, default=dict)

    # Lifecycle
    status = Column(SAEnum(ScenarioStatus), nullable=False, default=ScenarioStatus.DRAFT)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)

    # Evaluation results
    balanced_scorecard = Column(JSON, nullable=True)
    net_benefit = Column(Float, nullable=True)
    evaluation_duration_ms = Column(Float, nullable=True)

    # Hive health at evaluation time
    hive_health_snapshot = Column(JSON, nullable=True)

    # Relationships
    parent = relationship(
        "PlanningScenario",
        remote_side=[id],
        foreign_keys=[parent_scenario_id],
        backref="children",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parent_scenario_id": self.parent_scenario_id,
            "root_scenario_id": self.root_scenario_id,
            "depth": self.depth,
            "config_id": self.config_id,
            "variable_deltas": self.variable_deltas,
            "status": self.status.value if self.status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
            "balanced_scorecard": self.balanced_scorecard,
            "net_benefit": self.net_benefit,
            "hive_health_snapshot": self.hive_health_snapshot,
        }


class ScenarioDecisionRecord(Base):
    """Audit trail for scenario promotion/pruning decisions.

    Created when a scenario is promoted, recording which siblings
    were pruned, the ranking rationale, and hive health at the time.
    """
    __tablename__ = "scenario_decision_record"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Which scenario was promoted
    promoted_scenario_id = Column(
        Integer, ForeignKey("planning_scenario.id"), nullable=False,
    )

    # Siblings that were pruned (stored as JSON list of IDs)
    pruned_sibling_ids = Column(JSON, nullable=True, default=list)

    # Rationale for selection
    ranking_rationale = Column(Text, nullable=True)
    decision_criteria = Column(JSON, nullable=True)

    # Snapshots at decision time
    hive_health_snapshot = Column(JSON, nullable=True)
    scorecard_comparison = Column(JSON, nullable=True)

    # Audit
    decided_by = Column(String(255), nullable=True)
    decided_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationship
    promoted_scenario = relationship("PlanningScenario", foreign_keys=[promoted_scenario_id])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "promoted_scenario_id": self.promoted_scenario_id,
            "pruned_sibling_ids": self.pruned_sibling_ids,
            "ranking_rationale": self.ranking_rationale,
            "decision_criteria": self.decision_criteria,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
        }
