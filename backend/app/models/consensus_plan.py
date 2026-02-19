"""
Consensus Planning Models

Multi-stakeholder forecast consensus workflow:
- Sales, Marketing, Finance, Operations submit forecasts
- Review and comparison of different versions
- Voting/approval mechanism
- Final consensus selection and publication
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    Text, ForeignKey, Index, JSON, Enum
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
import enum

from app.models.base import Base


class ConsensusPlanStatus(str, enum.Enum):
    """Status of the consensus planning cycle."""
    DRAFT = "draft"
    COLLECTING = "collecting"  # Collecting submissions
    REVIEW = "review"  # Under review
    VOTING = "voting"  # Stakeholders voting
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ConsensusPlan(Base):
    """
    Consensus Planning Cycle

    Represents a single planning cycle where multiple stakeholders
    submit forecasts and collaborate to reach consensus.
    """

    __tablename__ = "consensus_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Plan identification
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Planning period
    planning_period: Mapped[str] = mapped_column(String(20), nullable=False)  # "2026-Q1", "2026-01"
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Scope
    config_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"))
    product_scope: Mapped[Optional[dict]] = mapped_column(JSON)  # {product_ids: [], categories: []}
    site_scope: Mapped[Optional[dict]] = mapped_column(JSON)  # {site_ids: [], regions: []}

    # Workflow state
    status: Mapped[str] = mapped_column(String(20), default=ConsensusPlanStatus.DRAFT.value)
    current_phase: Mapped[str] = mapped_column(String(50), default="collection")
    # collection, review, voting, finalization

    # Timeline
    submission_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)
    review_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)
    final_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Final consensus version
    final_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("consensus_plan_versions.id", use_alter=True))

    # Audit
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    published_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))

    # Relationships
    versions = relationship("ConsensusPlanVersion", back_populates="consensus_plan",
                          foreign_keys="ConsensusPlanVersion.consensus_plan_id")
    created_by = relationship("User", foreign_keys=[created_by_id])
    published_by = relationship("User", foreign_keys=[published_by_id])

    __table_args__ = (
        Index('ix_consensus_plan_period', 'planning_period', 'status'),
        Index('ix_consensus_plan_config', 'config_id', 'status'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'planning_period': self.planning_period,
            'period_start': self.period_start.isoformat() if self.period_start else None,
            'period_end': self.period_end.isoformat() if self.period_end else None,
            'config_id': self.config_id,
            'status': self.status,
            'current_phase': self.current_phase,
            'submission_deadline': self.submission_deadline.isoformat() if self.submission_deadline else None,
            'review_deadline': self.review_deadline.isoformat() if self.review_deadline else None,
            'final_deadline': self.final_deadline.isoformat() if self.final_deadline else None,
            'final_version_id': self.final_version_id,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'version_count': len(self.versions) if self.versions else 0,
        }


class ConsensusPlanVersion(Base):
    """
    Stakeholder Forecast Submission

    Individual forecast submission from a stakeholder (Sales, Marketing, Finance, etc.)
    """

    __tablename__ = "consensus_plan_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Parent consensus plan
    consensus_plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("consensus_plans.id"), nullable=False)

    # Submitter info
    submitted_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    # sales, marketing, finance, operations, statistical, consensus, blended

    # Version identification
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_name: Mapped[Optional[str]] = mapped_column(String(100))

    # Forecast data (JSON blob)
    # Structure: {product_id: {site_id: {period: quantity}}}
    forecast_data: Mapped[dict] = mapped_column(JSON, default=dict)

    # Assumptions and notes
    assumptions: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Supporting data
    supporting_data: Mapped[Optional[dict]] = mapped_column(JSON)
    # {attachments: [], market_research: {}, historical_refs: []}

    # Status
    is_submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    consensus_plan = relationship("ConsensusPlan", back_populates="versions",
                                 foreign_keys=[consensus_plan_id])
    submitted_by = relationship("User", foreign_keys=[submitted_by_id])
    votes = relationship("ConsensusPlanVote", back_populates="version")

    __table_args__ = (
        Index('ix_consensus_version_plan', 'consensus_plan_id', 'source'),
        Index('ix_consensus_version_submitter', 'submitted_by_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'consensus_plan_id': self.consensus_plan_id,
            'submitted_by_id': self.submitted_by_id,
            'source': self.source,
            'version_number': self.version_number,
            'version_name': self.version_name,
            'assumptions': self.assumptions,
            'notes': self.notes,
            'is_submitted': self.is_submitted,
            'is_locked': self.is_locked,
            'is_final': self.is_final,
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'vote_count': len(self.votes) if self.votes else 0,
        }


class ConsensusPlanVote(Base):
    """
    Stakeholder Vote on Forecast Version

    Records votes/approvals from stakeholders on submitted forecasts.
    """

    __tablename__ = "consensus_plan_votes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Version being voted on
    version_id: Mapped[int] = mapped_column(Integer, ForeignKey("consensus_plan_versions.id"), nullable=False)

    # Voter
    voter_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    voter_role: Mapped[Optional[str]] = mapped_column(String(50))  # sales_lead, finance_director, etc.

    # Vote details
    vote: Mapped[str] = mapped_column(String(20), nullable=False)
    # approve, reject, abstain, request_changes
    weight: Mapped[float] = mapped_column(Float, default=1.0)  # Vote weight for weighted voting

    # Feedback
    comment: Mapped[Optional[str]] = mapped_column(Text)
    requested_changes: Mapped[Optional[dict]] = mapped_column(JSON)
    # {product_id: {period: suggested_value}}

    # Timestamp
    voted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    version = relationship("ConsensusPlanVersion", back_populates="votes")
    voter = relationship("User")

    __table_args__ = (
        Index('ix_consensus_vote_version', 'version_id'),
        Index('ix_consensus_vote_voter', 'voter_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'version_id': self.version_id,
            'voter_id': self.voter_id,
            'voter_role': self.voter_role,
            'vote': self.vote,
            'weight': self.weight,
            'comment': self.comment,
            'voted_at': self.voted_at.isoformat() if self.voted_at else None,
        }


class ConsensusPlanComment(Base):
    """
    Discussion Comments on Consensus Plans

    Threaded comments for collaboration during consensus planning.
    """

    __tablename__ = "consensus_plan_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Parent references
    consensus_plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("consensus_plans.id"), nullable=False)
    version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("consensus_plan_versions.id"))
    parent_comment_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("consensus_plan_comments.id"))

    # Comment content
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Context (optional)
    context: Mapped[Optional[dict]] = mapped_column(JSON)
    # {product_id: "...", period: "...", cell_value: 100}

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    author = relationship("User")
    replies = relationship("ConsensusPlanComment", backref="parent",
                          remote_side=[id], lazy="selectin")

    __table_args__ = (
        Index('ix_consensus_comment_plan', 'consensus_plan_id'),
        Index('ix_consensus_comment_version', 'version_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'consensus_plan_id': self.consensus_plan_id,
            'version_id': self.version_id,
            'parent_comment_id': self.parent_comment_id,
            'author_id': self.author_id,
            'content': self.content,
            'context': self.context,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_resolved': self.is_resolved,
        }
