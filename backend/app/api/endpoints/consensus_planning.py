"""
Consensus Planning API Endpoints

Multi-stakeholder forecast consensus workflow:
- Create and manage consensus planning cycles
- Submit and compare forecast versions
- Vote on forecasts
- Finalize and publish consensus
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_sync_db
from app.models.user import User
from app.models.consensus_plan import (
    ConsensusPlan, ConsensusPlanVersion, ConsensusPlanVote,
    ConsensusPlanComment, ConsensusPlanStatus
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class ConsensusPlanCreate(BaseModel):
    """Create a new consensus planning cycle."""
    name: str
    description: Optional[str] = None
    planning_period: str  # "2026-Q1"
    period_start: datetime
    period_end: datetime
    config_id: Optional[int] = None
    submission_deadline: Optional[datetime] = None
    review_deadline: Optional[datetime] = None
    final_deadline: Optional[datetime] = None


class ConsensusPlanResponse(BaseModel):
    """Consensus plan response."""
    id: int
    name: str
    description: Optional[str]
    planning_period: str
    period_start: datetime
    period_end: datetime
    status: str
    current_phase: str
    submission_deadline: Optional[datetime]
    final_version_id: Optional[int]
    version_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class VersionCreate(BaseModel):
    """Create a forecast version submission."""
    source: str = Field(..., pattern="^(sales|marketing|finance|operations|statistical|consensus|blended)$")
    version_name: Optional[str] = None
    forecast_data: Dict[str, Any]  # {product_id: {site_id: {period: qty}}}
    assumptions: Optional[str] = None
    notes: Optional[str] = None


class VersionResponse(BaseModel):
    """Forecast version response."""
    id: int
    consensus_plan_id: int
    source: str
    version_number: int
    version_name: Optional[str]
    is_submitted: bool
    is_locked: bool
    is_final: bool
    submitted_at: Optional[datetime]
    vote_count: int

    class Config:
        from_attributes = True


class VoteCreate(BaseModel):
    """Create a vote on a forecast version."""
    vote: str = Field(..., pattern="^(approve|reject|abstain|request_changes)$")
    comment: Optional[str] = None
    requested_changes: Optional[Dict[str, Any]] = None


class VoteResponse(BaseModel):
    """Vote response."""
    id: int
    version_id: int
    voter_id: int
    vote: str
    comment: Optional[str]
    voted_at: datetime

    class Config:
        from_attributes = True


class CommentCreate(BaseModel):
    """Create a comment."""
    content: str
    version_id: Optional[int] = None
    parent_comment_id: Optional[int] = None
    context: Optional[Dict[str, Any]] = None


class CommentResponse(BaseModel):
    """Comment response."""
    id: int
    consensus_plan_id: int
    author_id: int
    content: str
    created_at: datetime
    is_resolved: bool

    class Config:
        from_attributes = True


class ComparisonResponse(BaseModel):
    """Forecast comparison response."""
    versions: List[Dict[str, Any]]
    differences: List[Dict[str, Any]]
    summary: Dict[str, Any]


# ============================================================================
# Consensus Plan CRUD Endpoints
# ============================================================================

@router.get("/", response_model=List[ConsensusPlanResponse])
def list_consensus_plans(
    status: Optional[str] = None,
    config_id: Optional[int] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """List consensus planning cycles."""
    query = db.query(ConsensusPlan)

    if status:
        query = query.filter(ConsensusPlan.status == status)
    if config_id:
        query = query.filter(ConsensusPlan.config_id == config_id)

    plans = query.order_by(ConsensusPlan.created_at.desc()).limit(limit).all()

    return [
        ConsensusPlanResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            planning_period=p.planning_period,
            period_start=p.period_start,
            period_end=p.period_end,
            status=p.status,
            current_phase=p.current_phase,
            submission_deadline=p.submission_deadline,
            final_version_id=p.final_version_id,
            version_count=len(p.versions) if p.versions else 0,
            created_at=p.created_at
        )
        for p in plans
    ]


@router.post("/", response_model=ConsensusPlanResponse)
def create_consensus_plan(
    plan: ConsensusPlanCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """Create a new consensus planning cycle."""
    consensus_plan = ConsensusPlan(
        name=plan.name,
        description=plan.description,
        planning_period=plan.planning_period,
        period_start=plan.period_start,
        period_end=plan.period_end,
        config_id=plan.config_id,
        submission_deadline=plan.submission_deadline,
        review_deadline=plan.review_deadline,
        final_deadline=plan.final_deadline,
        status=ConsensusPlanStatus.DRAFT.value,
        current_phase="collection",
        created_by_id=current_user.id
    )

    db.add(consensus_plan)
    db.commit()
    db.refresh(consensus_plan)

    logger.info(f"Consensus plan {consensus_plan.id} created by user {current_user.id}")

    return ConsensusPlanResponse(
        id=consensus_plan.id,
        name=consensus_plan.name,
        description=consensus_plan.description,
        planning_period=consensus_plan.planning_period,
        period_start=consensus_plan.period_start,
        period_end=consensus_plan.period_end,
        status=consensus_plan.status,
        current_phase=consensus_plan.current_phase,
        submission_deadline=consensus_plan.submission_deadline,
        final_version_id=consensus_plan.final_version_id,
        version_count=0,
        created_at=consensus_plan.created_at
    )


@router.get("/{plan_id}", response_model=ConsensusPlanResponse)
def get_consensus_plan(
    plan_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """Get a specific consensus plan."""
    plan = db.get(ConsensusPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Consensus plan not found")

    return ConsensusPlanResponse(
        id=plan.id,
        name=plan.name,
        description=plan.description,
        planning_period=plan.planning_period,
        period_start=plan.period_start,
        period_end=plan.period_end,
        status=plan.status,
        current_phase=plan.current_phase,
        submission_deadline=plan.submission_deadline,
        final_version_id=plan.final_version_id,
        version_count=len(plan.versions) if plan.versions else 0,
        created_at=plan.created_at
    )


@router.post("/{plan_id}/start")
def start_collection(
    plan_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """Start the collection phase - open for submissions."""
    plan = db.get(ConsensusPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Consensus plan not found")

    if plan.status != ConsensusPlanStatus.DRAFT.value:
        raise HTTPException(status_code=400, detail="Plan must be in draft status to start")

    plan.status = ConsensusPlanStatus.COLLECTING.value
    plan.current_phase = "collection"
    db.commit()

    logger.info(f"Consensus plan {plan_id} started collection phase")
    return {"success": True, "status": plan.status}


@router.post("/{plan_id}/advance-phase")
def advance_phase(
    plan_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """Advance to the next phase of the workflow."""
    plan = db.get(ConsensusPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Consensus plan not found")

    phase_transitions = {
        "collection": ("review", ConsensusPlanStatus.REVIEW.value),
        "review": ("voting", ConsensusPlanStatus.VOTING.value),
        "voting": ("finalization", ConsensusPlanStatus.APPROVED.value),
    }

    if plan.current_phase not in phase_transitions:
        raise HTTPException(status_code=400, detail="Cannot advance from current phase")

    new_phase, new_status = phase_transitions[plan.current_phase]
    plan.current_phase = new_phase
    plan.status = new_status
    db.commit()

    logger.info(f"Consensus plan {plan_id} advanced to {new_phase} phase")
    return {"success": True, "phase": new_phase, "status": new_status}


# ============================================================================
# Version Submission Endpoints
# ============================================================================

@router.get("/{plan_id}/versions", response_model=List[VersionResponse])
def list_versions(
    plan_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """List all submitted versions for a consensus plan."""
    versions = db.query(ConsensusPlanVersion).filter(
        ConsensusPlanVersion.consensus_plan_id == plan_id
    ).order_by(ConsensusPlanVersion.source, ConsensusPlanVersion.version_number.desc()).all()

    return [
        VersionResponse(
            id=v.id,
            consensus_plan_id=v.consensus_plan_id,
            source=v.source,
            version_number=v.version_number,
            version_name=v.version_name,
            is_submitted=v.is_submitted,
            is_locked=v.is_locked,
            is_final=v.is_final,
            submitted_at=v.submitted_at,
            vote_count=len(v.votes) if v.votes else 0
        )
        for v in versions
    ]


@router.post("/{plan_id}/versions", response_model=VersionResponse)
def submit_version(
    plan_id: int,
    version: VersionCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """Submit a new forecast version."""
    plan = db.get(ConsensusPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Consensus plan not found")

    if plan.status not in [ConsensusPlanStatus.DRAFT.value, ConsensusPlanStatus.COLLECTING.value]:
        raise HTTPException(status_code=400, detail="Plan is not accepting submissions")

    # Get next version number for this source
    existing = db.query(ConsensusPlanVersion).filter(
        ConsensusPlanVersion.consensus_plan_id == plan_id,
        ConsensusPlanVersion.source == version.source
    ).count()

    version_record = ConsensusPlanVersion(
        consensus_plan_id=plan_id,
        submitted_by_id=current_user.id,
        source=version.source,
        version_number=existing + 1,
        version_name=version.version_name or f"{version.source.title()} v{existing + 1}",
        forecast_data=version.forecast_data,
        assumptions=version.assumptions,
        notes=version.notes,
        is_submitted=True,
        submitted_at=datetime.utcnow()
    )

    db.add(version_record)
    db.commit()
    db.refresh(version_record)

    logger.info(f"Version {version_record.id} submitted for plan {plan_id}")

    return VersionResponse(
        id=version_record.id,
        consensus_plan_id=version_record.consensus_plan_id,
        source=version_record.source,
        version_number=version_record.version_number,
        version_name=version_record.version_name,
        is_submitted=version_record.is_submitted,
        is_locked=version_record.is_locked,
        is_final=version_record.is_final,
        submitted_at=version_record.submitted_at,
        vote_count=0
    )


@router.get("/{plan_id}/versions/{version_id}/data")
def get_version_data(
    plan_id: int,
    version_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """Get the forecast data for a specific version."""
    version = db.query(ConsensusPlanVersion).filter(
        ConsensusPlanVersion.id == version_id,
        ConsensusPlanVersion.consensus_plan_id == plan_id
    ).first()

    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    return {
        "version_id": version.id,
        "source": version.source,
        "forecast_data": version.forecast_data,
        "assumptions": version.assumptions,
        "notes": version.notes
    }


# ============================================================================
# Comparison Endpoints
# ============================================================================

@router.get("/{plan_id}/compare", response_model=ComparisonResponse)
def compare_versions(
    plan_id: int,
    version_ids: str = Query(..., description="Comma-separated version IDs to compare"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """Compare multiple forecast versions side-by-side."""
    ids = [int(x) for x in version_ids.split(",")]

    versions = db.query(ConsensusPlanVersion).filter(
        ConsensusPlanVersion.id.in_(ids),
        ConsensusPlanVersion.consensus_plan_id == plan_id
    ).all()

    if len(versions) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 versions to compare")

    # Build comparison
    version_data = []
    all_products = set()
    all_periods = set()

    for v in versions:
        version_data.append({
            "id": v.id,
            "source": v.source,
            "version_name": v.version_name,
            "data": v.forecast_data
        })
        for product_id, sites in v.forecast_data.items():
            all_products.add(product_id)
            for site_id, periods in sites.items():
                all_periods.update(periods.keys())

    # Calculate differences
    differences = []
    for product_id in all_products:
        for period in sorted(all_periods):
            values = []
            for v in version_data:
                val = None
                if product_id in v["data"]:
                    for site_id, periods in v["data"][product_id].items():
                        if period in periods:
                            val = periods[period]
                            break
                values.append({"version_id": v["id"], "source": v["source"], "value": val})

            non_null = [v["value"] for v in values if v["value"] is not None]
            if len(non_null) > 1:
                variance = max(non_null) - min(non_null)
                if variance > 0:
                    differences.append({
                        "product_id": product_id,
                        "period": period,
                        "values": values,
                        "variance": variance,
                        "variance_pct": (variance / sum(non_null) * len(non_null)) * 100
                    })

    # Summary statistics
    summary = {
        "version_count": len(versions),
        "products_compared": len(all_products),
        "periods_compared": len(all_periods),
        "cells_with_variance": len(differences),
        "avg_variance_pct": sum(d["variance_pct"] for d in differences) / len(differences) if differences else 0
    }

    return ComparisonResponse(
        versions=version_data,
        differences=sorted(differences, key=lambda x: -x["variance_pct"])[:50],
        summary=summary
    )


# ============================================================================
# Voting Endpoints
# ============================================================================

@router.post("/{plan_id}/versions/{version_id}/vote", response_model=VoteResponse)
def vote_on_version(
    plan_id: int,
    version_id: int,
    vote: VoteCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """Vote on a forecast version."""
    version = db.query(ConsensusPlanVersion).filter(
        ConsensusPlanVersion.id == version_id,
        ConsensusPlanVersion.consensus_plan_id == plan_id
    ).first()

    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    # Check if user already voted
    existing = db.query(ConsensusPlanVote).filter(
        ConsensusPlanVote.version_id == version_id,
        ConsensusPlanVote.voter_id == current_user.id
    ).first()

    if existing:
        # Update existing vote
        existing.vote = vote.vote
        existing.comment = vote.comment
        existing.requested_changes = vote.requested_changes
        existing.voted_at = datetime.utcnow()
        db.commit()
        vote_record = existing
    else:
        # Create new vote
        vote_record = ConsensusPlanVote(
            version_id=version_id,
            voter_id=current_user.id,
            vote=vote.vote,
            comment=vote.comment,
            requested_changes=vote.requested_changes
        )
        db.add(vote_record)
        db.commit()
        db.refresh(vote_record)

    logger.info(f"Vote {vote_record.id} recorded for version {version_id}")

    return VoteResponse(
        id=vote_record.id,
        version_id=vote_record.version_id,
        voter_id=vote_record.voter_id,
        vote=vote_record.vote,
        comment=vote_record.comment,
        voted_at=vote_record.voted_at
    )


@router.get("/{plan_id}/versions/{version_id}/votes", response_model=List[VoteResponse])
def get_version_votes(
    plan_id: int,
    version_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """Get all votes for a version."""
    votes = db.query(ConsensusPlanVote).filter(
        ConsensusPlanVote.version_id == version_id
    ).all()

    return [
        VoteResponse(
            id=v.id,
            version_id=v.version_id,
            voter_id=v.voter_id,
            vote=v.vote,
            comment=v.comment,
            voted_at=v.voted_at
        )
        for v in votes
    ]


# ============================================================================
# Finalization Endpoints
# ============================================================================

@router.post("/{plan_id}/finalize")
def finalize_consensus(
    plan_id: int,
    version_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Finalize the consensus plan with the selected version.

    Marks the selected version as final and locks it.
    """
    plan = db.get(ConsensusPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Consensus plan not found")

    version = db.query(ConsensusPlanVersion).filter(
        ConsensusPlanVersion.id == version_id,
        ConsensusPlanVersion.consensus_plan_id == plan_id
    ).first()

    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    # Lock all other versions
    db.query(ConsensusPlanVersion).filter(
        ConsensusPlanVersion.consensus_plan_id == plan_id
    ).update({"is_locked": True, "is_final": False})

    # Mark selected version as final
    version.is_final = True
    version.is_locked = True

    # Update plan
    plan.final_version_id = version_id
    plan.status = ConsensusPlanStatus.APPROVED.value
    plan.current_phase = "finalized"

    db.commit()

    logger.info(f"Consensus plan {plan_id} finalized with version {version_id}")

    return {
        "success": True,
        "message": f"Consensus plan finalized with version: {version.version_name}",
        "final_version_id": version_id
    }


@router.post("/{plan_id}/publish")
def publish_consensus(
    plan_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Publish the finalized consensus plan.

    Copies the consensus forecast to the main forecast table.
    """
    plan = db.get(ConsensusPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Consensus plan not found")

    if plan.status != ConsensusPlanStatus.APPROVED.value:
        raise HTTPException(status_code=400, detail="Plan must be approved before publishing")

    if not plan.final_version_id:
        raise HTTPException(status_code=400, detail="No final version selected")

    # Get final version data
    final_version = db.get(ConsensusPlanVersion, plan.final_version_id)
    if not final_version:
        raise HTTPException(status_code=404, detail="Final version not found")

    # In production: Copy forecast_data to main forecast table
    # For now, just update status
    plan.status = ConsensusPlanStatus.PUBLISHED.value
    plan.published_at = datetime.utcnow()
    plan.published_by_id = current_user.id

    db.commit()

    logger.info(f"Consensus plan {plan_id} published by user {current_user.id}")

    return {
        "success": True,
        "message": "Consensus plan published successfully",
        "published_at": plan.published_at.isoformat()
    }


# ============================================================================
# Comment Endpoints
# ============================================================================

@router.get("/{plan_id}/comments", response_model=List[CommentResponse])
def list_comments(
    plan_id: int,
    version_id: Optional[int] = None,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """List comments for a consensus plan."""
    query = db.query(ConsensusPlanComment).filter(
        ConsensusPlanComment.consensus_plan_id == plan_id
    )

    if version_id:
        query = query.filter(ConsensusPlanComment.version_id == version_id)

    comments = query.order_by(ConsensusPlanComment.created_at).all()

    return [
        CommentResponse(
            id=c.id,
            consensus_plan_id=c.consensus_plan_id,
            author_id=c.author_id,
            content=c.content,
            created_at=c.created_at,
            is_resolved=c.is_resolved
        )
        for c in comments
    ]


@router.post("/{plan_id}/comments", response_model=CommentResponse)
def add_comment(
    plan_id: int,
    comment: CommentCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """Add a comment to the consensus plan."""
    comment_record = ConsensusPlanComment(
        consensus_plan_id=plan_id,
        version_id=comment.version_id,
        parent_comment_id=comment.parent_comment_id,
        author_id=current_user.id,
        content=comment.content,
        context=comment.context
    )

    db.add(comment_record)
    db.commit()
    db.refresh(comment_record)

    return CommentResponse(
        id=comment_record.id,
        consensus_plan_id=comment_record.consensus_plan_id,
        author_id=comment_record.author_id,
        content=comment_record.content,
        created_at=comment_record.created_at,
        is_resolved=comment_record.is_resolved
    )
